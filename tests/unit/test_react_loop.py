"""Day-5 S1 — ReAct loop scaffold tests.

Mocks `chat_with_tools` to return scripted tool-call sequences. Verifies:
- Loop dispatches tools in order
- Terminal tools (submit_finding / give_up) end the loop
- Forced give_up synthesis at iter cap
- Per-case USD ceiling halts the loop
- 3-strike no-tool-call circuit breaker fires
- Trace records each step + markdown export non-empty
- AC5b counter increments only when memory recall returns non-empty
"""
from __future__ import annotations

import json
from typing import Any

import pytest

from agent.react.loop import run_react_agent


CASE = {
    "id": "TEST-1",
    "contract_name": "Foo",
    "contract_source": "contract Foo { function bar() external {} }",
    "verifier_mode": "replica_only",
    "severity": "high",
}


def _make_chat_fn(scripted_responses: list[dict[str, Any]]):
    """Each scripted response is a dict with 'content' and 'tool_calls'."""
    calls = {"i": 0}

    def fake_chat(messages, tools, annotations, **kwargs):
        idx = calls["i"]
        calls["i"] += 1
        # Simulate token cost
        annotations["tokens_prompt"] = annotations.get("tokens_prompt", 0) + 1000
        annotations["tokens_completion"] = annotations.get("tokens_completion", 0) + 100
        annotations["llm_calls"] = annotations.get("llm_calls", 0) + 1
        if idx >= len(scripted_responses):
            return {"content": "no more scripted responses", "tool_calls": [], "raw_tool_calls": []}
        return scripted_responses[idx]

    return fake_chat


def _tc(name: str, args: dict, call_id: str = "tc1") -> dict:
    return {"id": call_id, "name": name, "arguments": args}


def _resp(content: str = "", tool_calls=None) -> dict:
    return {
        "content": content,
        "tool_calls": tool_calls or [],
        "raw_tool_calls": [],  # not exercised in unit tests
    }


# ---------------------------------------------------------------------------
# Termination paths
# ---------------------------------------------------------------------------


class TestTerminationPaths:
    def test_submit_finding_terminates_immediately(self):
        chat = _make_chat_fn([
            _resp("I'll submit", [_tc("submit_finding", {"target_function": "bar", "evidence": "ok"})]),
        ])
        r = run_react_agent(CASE, memory_backend=None, chat_with_tools_fn=chat)
        assert r.terminal_reason == "submit_finding"
        assert r.target_function == "bar"
        assert r.distinct_tool_count == 1

    def test_give_up_terminates_immediately(self):
        chat = _make_chat_fn([
            _resp("can't do it", [_tc("give_up", {"reason": "too hard"})]),
        ])
        r = run_react_agent(CASE, memory_backend=None, chat_with_tools_fn=chat)
        assert r.terminal_reason == "give_up"
        assert "too hard" in r.state.given_up_reason

    def test_max_iter_forces_give_up_synthesis(self):
        # 25 calls each of `list_functions` (non-terminal) → loop hits max_iter=3
        chat = _make_chat_fn([
            _resp("step", [_tc("list_functions", {}, f"tc{i}")]) for i in range(10)
        ])
        r = run_react_agent(CASE, memory_backend=None, chat_with_tools_fn=chat, max_iter=3)
        assert r.terminal_reason == "max_iter"
        assert "max_iter=3" in r.state.given_up_reason


# ---------------------------------------------------------------------------
# R8 guards
# ---------------------------------------------------------------------------


class TestR8Guards:
    def test_per_case_usd_ceiling_halts(self):
        chat = _make_chat_fn([
            _resp("step", [_tc("list_functions", {}, "tc1")]),
            _resp("step", [_tc("list_functions", {}, "tc2")]),
            _resp("step", [_tc("list_functions", {}, "tc3")]),
        ])
        # Each fake call adds ~$0.00045 USD (1000p × $0.00025/1K + 100c × $0.002/1K)
        # Setting ceiling well below 3 calls' worth
        r = run_react_agent(
            CASE, memory_backend=None, chat_with_tools_fn=chat,
            max_usd_per_case=0.0008, max_iter=10,
        )
        assert r.terminal_reason == "case_budget_exceeded"

    def test_malformed_streak_circuit_breaker(self):
        # 3 consecutive no-tool-call responses → circuit breaker
        chat = _make_chat_fn([
            _resp("just thinking", []),
            _resp("still thinking", []),
            _resp("hmm", []),
        ])
        r = run_react_agent(
            CASE, memory_backend=None, chat_with_tools_fn=chat,
            max_iter=10, max_malformed_streak=3,
        )
        assert r.terminal_reason == "malformed_circuit_breaker"

    def test_malformed_streak_resets_on_valid_tool_call(self):
        # malformed × 2, valid call, malformed × 2 → no breaker
        chat = _make_chat_fn([
            _resp("thinking", []),
            _resp("still thinking", []),
            _resp("ok", [_tc("list_functions", {}, "tc1")]),
            _resp("thinking again", []),
            _resp("ok", [_tc("give_up", {"reason": "done"})]),
        ])
        r = run_react_agent(
            CASE, memory_backend=None, chat_with_tools_fn=chat,
            max_iter=10, max_malformed_streak=3,
        )
        assert r.terminal_reason == "give_up"


# ---------------------------------------------------------------------------
# Tool dispatch + state tracking
# ---------------------------------------------------------------------------


class TestToolDispatch:
    def test_distinct_tool_count(self):
        chat = _make_chat_fn([
            _resp("a", [_tc("list_functions", {}, "1")]),
            _resp("b", [_tc("list_functions", {}, "2")]),  # duplicate
            _resp("c", [_tc("check_imports", {}, "3")]),
            _resp("d", [_tc("give_up", {"reason": "done"}, "4")]),
        ])
        r = run_react_agent(CASE, memory_backend=None, chat_with_tools_fn=chat)
        # 3 calls of 2 distinct tools (list_functions x2, check_imports x1) + give_up
        assert r.distinct_tool_count == 3  # list_functions, check_imports, give_up
        assert r.state.tools_called == ["list_functions", "list_functions", "check_imports", "give_up"]

    def test_unknown_tool_returns_error_observation(self):
        chat = _make_chat_fn([
            _resp("a", [_tc("not_a_real_tool", {}, "1")]),
            _resp("b", [_tc("give_up", {"reason": "fine"}, "2")]),
        ])
        r = run_react_agent(CASE, memory_backend=None, chat_with_tools_fn=chat)
        assert r.terminal_reason == "give_up"
        # Verify trace records the bad call without crashing
        steps = r.trace.steps
        first = steps[0]
        assert first.tool_name == "not_a_real_tool"
        result = json.loads(first.tool_result)
        assert result["ok"] is False
        assert "unknown tool" in result["error"]


# ---------------------------------------------------------------------------
# Trace export (AC8)
# ---------------------------------------------------------------------------


class TestTraceExport:
    def test_markdown_export_non_empty(self):
        chat = _make_chat_fn([
            _resp("Let me list functions first.",
                  [_tc("list_functions", {}, "1")]),
            _resp("Now I'll terminate.",
                  [_tc("submit_finding", {"target_function": "bar", "evidence": "see trace"}, "2")]),
        ])
        r = run_react_agent(CASE, memory_backend=None, chat_with_tools_fn=chat)
        md = r.trace.to_markdown()
        assert "TEST-1" in md
        assert "submit_finding" in md
        assert "list_functions" in md
        assert "Let me list functions" in md

    def test_trace_json_serializable(self):
        chat = _make_chat_fn([
            _resp("", [_tc("give_up", {"reason": "fast"})]),
        ])
        r = run_react_agent(CASE, memory_backend=None, chat_with_tools_fn=chat)
        j = r.trace.to_json()
        # Must round-trip through json
        s = json.dumps(j)
        assert "TEST-1" in s
        assert j["terminal_reason"] == "give_up"


# ---------------------------------------------------------------------------
# AC5b — recall_self_lesson nonempty counter
# ---------------------------------------------------------------------------


class _StubMemory:
    def __init__(self, recall_results=None):
        self._results = recall_results or []

    def recall_self_lesson(self, query, top_k=3):
        return list(self._results)


class TestAc5bRecallCounter:
    def test_recall_returns_empty_does_not_increment(self):
        chat = _make_chat_fn([
            _resp("", [_tc("recall_self_lesson", {"query": "missing modifier"}, "1")]),
            _resp("", [_tc("give_up", {"reason": "ok"})]),
        ])
        mem = _StubMemory(recall_results=[])
        r = run_react_agent(CASE, memory_backend=mem, chat_with_tools_fn=chat)
        assert r.recall_self_lesson_nonempty == 0

    def test_recall_returns_nonempty_increments(self):
        chat = _make_chat_fn([
            _resp("", [_tc("recall_self_lesson", {"query": "missing modifier"}, "1")]),
            _resp("", [_tc("recall_self_lesson", {"query": "another query"}, "2")]),
            _resp("", [_tc("give_up", {"reason": "ok"})]),
        ])
        mem = _StubMemory(recall_results=[{"trigger": "x", "takeaway": "y"}])
        r = run_react_agent(CASE, memory_backend=mem, chat_with_tools_fn=chat)
        assert r.recall_self_lesson_nonempty == 2  # both calls returned non-empty


# ---------------------------------------------------------------------------
# Auto save_episode at termination (Day-5 S5 wiring)
# ---------------------------------------------------------------------------


class _StubMemoryWithEpisode:
    """Records save_episode invocations for assertion."""

    def __init__(self):
        self.episodes = []

    def recall_self_lesson(self, query, top_k=3):
        return []

    def save_episode(self, **kwargs):
        self.episodes.append(kwargs)
        return f"ep_{len(self.episodes)}"


class TestAutoSaveEpisode:
    def test_save_episode_called_on_submit_finding(self):
        # NOTE: this test calls submit_finding without first calling run_forge,
        # so last_forge_verdict stays empty and the lesson falls into the
        # "Terminated unclean" branch. That's expected — the auto-save path
        # always records, but the lesson template depends on whether forge
        # actually ran. Real agent flow: list_functions → ... → run_forge →
        # submit_finding (which triggers the "Found bug at" branch).
        chat = _make_chat_fn([
            _resp("found it", [_tc("submit_finding", {"target_function": "bar", "evidence": "ok"})]),
        ])
        mem = _StubMemoryWithEpisode()
        r = run_react_agent(CASE, memory_backend=mem, chat_with_tools_fn=chat)
        assert r.terminal_reason == "submit_finding"
        assert len(mem.episodes) == 1
        ep = mem.episodes[0]
        assert ep["case_id"] == "TEST-1"
        assert ep["terminal_reason"] == "submit_finding"
        # Lesson present + non-empty (template depends on forge_verdict)
        assert ep["lesson"]
        assert "TEST-1" in ep["lesson"] or ep["contract_name"] == "Foo"

    def test_save_episode_called_on_give_up(self):
        chat = _make_chat_fn([
            _resp("can't", [_tc("give_up", {"reason": "imports broken"})]),
        ])
        mem = _StubMemoryWithEpisode()
        r = run_react_agent(CASE, memory_backend=mem, chat_with_tools_fn=chat)
        assert r.terminal_reason == "give_up"
        assert len(mem.episodes) == 1
        assert "Gave up" in mem.episodes[0]["lesson"]
        assert "imports broken" in mem.episodes[0]["lesson"]

    def test_save_episode_skipped_when_no_memory(self):
        chat = _make_chat_fn([
            _resp("", [_tc("give_up", {"reason": "ok"})]),
        ])
        # memory_backend=None → no save_episode attempted, no crash
        r = run_react_agent(CASE, memory_backend=None, chat_with_tools_fn=chat)
        assert r.terminal_reason == "give_up"

    def test_save_episode_failure_does_not_crash_loop(self):
        class BrokenMem:
            def recall_self_lesson(self, q, top_k=3):
                return []

            def save_episode(self, **kwargs):
                raise RuntimeError("mem disk full")

        chat = _make_chat_fn([
            _resp("", [_tc("submit_finding", {"target_function": "bar", "evidence": "ok"})]),
        ])
        # Despite mem.save_episode raising, agent terminates cleanly
        r = run_react_agent(CASE, memory_backend=BrokenMem(), chat_with_tools_fn=chat)
        assert r.terminal_reason == "submit_finding"  # not crashed

    def test_save_episode_max_iter_records_synthesis_lesson(self):
        chat = _make_chat_fn([
            _resp("", [_tc("list_functions", {}, f"tc{i}")]) for i in range(10)
        ])
        mem = _StubMemoryWithEpisode()
        r = run_react_agent(CASE, memory_backend=mem, chat_with_tools_fn=chat, max_iter=3)
        assert r.terminal_reason == "max_iter"
        assert len(mem.episodes) == 1
        assert "max_iter" in mem.episodes[0]["lesson"].lower()
