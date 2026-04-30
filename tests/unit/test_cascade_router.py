"""Unit tests for Day-2 T8 cascade router in `src/agent/graph.py::run_pipeline`.

Asserts the routing rules from Critic #10:
  - `pass`              → SUCCESS, exit cascade (early-exit)
  - `fail_revert_ac`    → advance candidate (no inner retry)
  - `fail_error_compile`/`fail_error_runtime` → retry within candidate
  - retry-exhausted     → abstain (cascade exits, NOT advance)

Mocks `analyze`, `build_poc`, `verify` so no real LLM/forge calls happen.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from agent.graph import run_pipeline


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mk_analyst_out(candidates: list[str], hypothesis: str = "test hypothesis"):
    return {
        "target_function": candidates[0] if candidates else "",
        "candidates": candidates,
        "hypothesis": hypothesis,
        "confidence": 0.9,
        "reasoning": "test",
        "raw_response": "",
    }


def _mk_verdict(execution_result: str, error_summary: str = ""):
    return {
        "execution_result": execution_result,
        "execution_trace": "",
        "error_summary": error_summary,
        "wall_clock_s": 0.0,
        "return_code": 0 if execution_result == "pass" else 1,
    }


class _ScriptedVerifier:
    """Returns verdicts in order from a scripted list, indefinitely repeats
    the last verdict if exhausted."""

    def __init__(self, verdicts: list[dict]):
        self.verdicts = verdicts
        self.calls = 0

    def __call__(self, **kwargs):
        idx = min(self.calls, len(self.verdicts) - 1)
        self.calls += 1
        return self.verdicts[idx]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.fixture
def patches():
    """Patch analyze + build_poc + verify in `agent.graph`'s imports."""
    with patch("agent.graph.analyze") as m_analyze, \
         patch("agent.graph.build_poc") as m_build, \
         patch("agent.graph.verify") as m_verify:
        m_build.return_value = "// stub PoC"
        yield m_analyze, m_build, m_verify


class TestCascadeEarlyExit:
    def test_pass_at_top_1_does_not_advance(self, patches: Any):
        m_analyze, _, m_verify = patches
        m_analyze.return_value = _mk_analyst_out(["foo", "bar", "baz"])
        m_verify.side_effect = [_mk_verdict("pass")]

        r = run_pipeline(
            case_id="T1",
            contract_source="contract C {}",
            contract_name="C",
            max_retries=3,
        )

        assert r.finding_confirmed is True
        assert r.execution_result == "pass"
        assert r.target_function == "foo"
        trace = r.annotations.get("cascade_trace", [])
        assert len(trace) == 1
        assert trace[0]["outcome"] == "pass"
        assert m_verify.call_count == 1


class TestCascadeAdvanceOnAcRevert:
    def test_top_1_ac_revert_advances_to_top_2_pass(self, patches: Any):
        m_analyze, _, m_verify = patches
        m_analyze.return_value = _mk_analyst_out(["foo", "bar", "baz"])
        m_verify.side_effect = [
            _mk_verdict("fail_revert_ac"),
            _mk_verdict("pass"),
        ]

        r = run_pipeline(
            case_id="T2",
            contract_source="contract C {}",
            contract_name="C",
            max_retries=3,
        )

        assert r.finding_confirmed is True
        assert r.target_function == "bar"
        trace = r.annotations.get("cascade_trace", [])
        assert len(trace) == 2
        assert trace[0]["outcome"] == "fail_revert_ac"
        assert trace[1]["outcome"] == "pass"
        assert "depth 2" in r.finding_reason
        assert m_verify.call_count == 2

    def test_all_three_candidates_ac_intercepted(self, patches: Any):
        m_analyze, _, m_verify = patches
        m_analyze.return_value = _mk_analyst_out(["a", "b", "c"])
        m_verify.side_effect = [
            _mk_verdict("fail_revert_ac"),
            _mk_verdict("fail_revert_ac"),
            _mk_verdict("fail_revert_ac"),
        ]

        r = run_pipeline(
            case_id="T3",
            contract_source="contract C {}",
            contract_name="C",
            max_retries=3,
        )

        assert r.finding_confirmed is False
        assert r.annotations.get("abstained") is False
        trace = r.annotations.get("cascade_trace", [])
        assert len(trace) == 3
        assert all(s["outcome"] == "fail_revert_ac" for s in trace)
        assert "intercepted by access control" in r.finding_reason


class TestCascadeAbstainOnRetryExhausted:
    """Day-4 Issue 1 (hybrid routing) changes the behavior on
    `fail_error_runtime`: 1st occurrence retries (preserves Critic #10
    transient-PoC caution), 2nd occurrence ADVANCES (cascade unblocked).

    Pre-Day-4 expectation (preserved here in comments for transparency,
    documented in `.omc/plans/day4-routing-reversal-disclosure.md`):
        3x `fail_error_runtime` → abstain at depth 1, no cascade advance.
    Day-4 expectation:
        runtime#1 retry → runtime#2 advance to top-2.
    """

    def test_two_runtime_fails_on_top1_advances_to_top2(self, patches: Any):
        """Day-4 hybrid routing: 2nd runtime fail → advance, not abstain."""
        m_analyze, _, m_verify = patches
        m_analyze.return_value = _mk_analyst_out(["foo", "bar", "baz"])
        m_verify.side_effect = [
            _mk_verdict("fail_error_runtime", "boom 1"),  # top-1 attempt 1
            _mk_verdict("fail_error_runtime", "boom 2"),  # top-1 attempt 2 → advance
            _mk_verdict("pass"),                          # top-2 passes
        ]

        r = run_pipeline(
            case_id="T4-hybrid",
            contract_source="contract C {}",
            contract_name="C",
            max_retries=3,
        )

        assert r.finding_confirmed is True
        assert r.target_function == "bar"
        trace = r.annotations.get("cascade_trace", [])
        assert len(trace) == 2
        assert trace[0]["outcome"] == "advanced_runtime_fail"
        assert trace[1]["outcome"] == "pass"
        assert m_verify.call_count == 3

    def test_one_runtime_fail_then_pass_stays_on_same_candidate(
        self, patches: Any
    ):
        """1st runtime fail → retry once on SAME candidate; if retry passes,
        cascade does NOT advance (preserves Critic #10 caution)."""
        m_analyze, _, m_verify = patches
        m_analyze.return_value = _mk_analyst_out(["foo", "bar", "baz"])
        m_verify.side_effect = [
            _mk_verdict("fail_error_runtime", "transient flake"),
            _mk_verdict("pass"),
        ]

        r = run_pipeline(
            case_id="T4-retry-once",
            contract_source="contract C {}",
            contract_name="C",
            max_retries=3,
        )

        assert r.finding_confirmed is True
        assert r.target_function == "foo"  # never advanced
        trace = r.annotations.get("cascade_trace", [])
        assert len(trace) == 1
        assert trace[0]["outcome"] == "pass"
        assert m_verify.call_count == 2

    def test_compile_fail_retry_exhausted_abstains(self, patches: Any):
        m_analyze, _, m_verify = patches
        m_analyze.return_value = _mk_analyst_out(["foo", "bar"])
        m_verify.side_effect = [
            _mk_verdict("fail_error_compile", "ParserError"),
            _mk_verdict("fail_error_compile", "TypeError"),
            _mk_verdict("fail_error_compile", "DeclarationError"),
        ]

        r = run_pipeline(
            case_id="T5",
            contract_source="contract C {}",
            contract_name="C",
            max_retries=3,
        )

        assert r.execution_result == "abstain"
        assert r.annotations.get("abstained") is True
        # Compile failures also abstain post-retry — they don't advance candidate
        trace = r.annotations.get("cascade_trace", [])
        assert len(trace) == 1
        assert trace[0]["outcome"] == "abstain_retry_exhausted"


class TestCascadeMixedRetryThenAdvance:
    def test_compile_fail_then_pass_within_same_candidate(self, patches: Any):
        m_analyze, _, m_verify = patches
        m_analyze.return_value = _mk_analyst_out(["foo", "bar"])
        m_verify.side_effect = [
            _mk_verdict("fail_error_compile", "first try bad"),
            _mk_verdict("pass"),
        ]

        r = run_pipeline(
            case_id="T6",
            contract_source="contract C {}",
            contract_name="C",
            max_retries=3,
        )

        assert r.finding_confirmed is True
        trace = r.annotations.get("cascade_trace", [])
        # Same candidate retried, then passed — cascade depth 1
        assert len(trace) == 1
        assert trace[0]["outcome"] == "pass"
        assert trace[0]["verdicts"] == ["fail_error_compile", "pass"]


class TestCascadeStateAnnotations:
    def test_top_k_candidates_recorded(self, patches: Any):
        m_analyze, _, m_verify = patches
        m_analyze.return_value = _mk_analyst_out(["fn1", "fn2", "fn3", "fn4"])
        m_verify.side_effect = [_mk_verdict("pass")]

        r = run_pipeline(
            case_id="T7",
            contract_source="contract C {}",
            contract_name="C",
            max_retries=3,
        )

        # Cascade caps at top-3 even if analyst returned more
        top_k = r.annotations.get("top_k_candidates", [])
        assert top_k == ["fn1", "fn2", "fn3"]

    def test_skip_forge_short_circuits_cascade(self, patches: Any):
        m_analyze, _, m_verify = patches
        m_analyze.return_value = _mk_analyst_out(["foo", "bar"])

        r = run_pipeline(
            case_id="T8",
            contract_source="contract C {}",
            contract_name="C",
            max_retries=3,
            skip_forge=True,
        )

        assert r.execution_result == "skipped"
        # No verifier calls under skip_forge
        assert m_verify.call_count == 0
        trace = r.annotations.get("cascade_trace", [])
        assert len(trace) == 1
        assert trace[0]["outcome"] == "skipped"


# ---------------------------------------------------------------------------
# Day-3 W3: arm-flag behavior
# ---------------------------------------------------------------------------


class TestUseCascadeFlag:
    def test_use_cascade_false_truncates_to_top_1(self, patches: Any):
        """no-cascade arm: even with 3 analyst candidates, only top-1 is tried.
        After fail_revert_ac on top-1, cascade exits (no advance)."""
        m_analyze, _, m_verify = patches
        m_analyze.return_value = _mk_analyst_out(["foo", "bar", "baz"])
        m_verify.side_effect = [_mk_verdict("fail_revert_ac")]

        r = run_pipeline(
            case_id="T_NC",
            contract_source="contract C {}",
            contract_name="C",
            max_retries=3,
            use_cascade=False,
        )

        assert r.finding_confirmed is False
        # Only top-1 attempted
        top_k = r.annotations.get("top_k_candidates", [])
        assert top_k == ["foo"]
        trace = r.annotations.get("cascade_trace", [])
        assert len(trace) == 1
        assert trace[0]["target_function"] == "foo"
        assert m_verify.call_count == 1


class TestUseReflectionFlag:
    def test_use_reflection_calls_reflect_between_advances(self, patches: Any):
        """use_reflection=True wedges reflect() between candidate advances.
        Reflector's pick (must be in candidates set) drives the next target."""
        m_analyze, _, m_verify = patches
        m_analyze.return_value = _mk_analyst_out(["foo", "bar", "baz"])
        # foo fails AC; reflection picks "baz" (skip "bar"); baz passes.
        m_verify.side_effect = [
            _mk_verdict("fail_revert_ac"),
            _mk_verdict("pass"),
        ]
        with patch("agent.nodes.reflector.invoke_json") as m_reflect_llm:
            m_reflect_llm.return_value = (
                '{"target_function": "baz", "hypothesis": "h2", "reasoning": "r"}'
            )
            r = run_pipeline(
                case_id="T_RFL",
                contract_source="contract C {}",
                contract_name="C",
                max_retries=3,
                use_reflection=True,
            )

        assert r.finding_confirmed is True
        # Cascade order: foo → baz (reflection-picked, skipping bar)
        trace = r.annotations.get("cascade_trace", [])
        assert len(trace) == 2
        assert trace[0]["target_function"] == "foo"
        assert trace[1]["target_function"] == "baz"
        # Reflector was called once (between candidates)
        rt = r.annotations.get("reflection_trace", [])
        assert len(rt) == 1
        assert rt[0]["picked_target"] == "baz"

    def test_use_reflection_off_uses_natural_order(self, patches: Any):
        """use_reflection=False (default) advances candidates in analyst order."""
        m_analyze, _, m_verify = patches
        m_analyze.return_value = _mk_analyst_out(["foo", "bar", "baz"])
        m_verify.side_effect = [
            _mk_verdict("fail_revert_ac"),
            _mk_verdict("pass"),
        ]
        # No reflector mock needed — should not be called.
        r = run_pipeline(
            case_id="T_NORFL",
            contract_source="contract C {}",
            contract_name="C",
            max_retries=3,
            use_reflection=False,
        )

        trace = r.annotations.get("cascade_trace", [])
        assert trace[0]["target_function"] == "foo"
        assert trace[1]["target_function"] == "bar"  # natural order
        assert r.annotations.get("reflection_trace", []) == []


class TestUseToolsFlag:
    def test_use_tools_dispatches_to_analyze_with_tools(self, patches: Any):
        """Day-4 Issue 2+3: use_tools=True routes through `analyze_consistent`
        (RRF voting, default n=3) inside `analyst_with_tools`. The
        single-augmented-call refactor (Day-2 dual-call removed) means we
        no longer assert exactly 2 `analyze()` invocations — instead, we
        verify `analyze_consistent` was called once with n_runs=3 and the
        dual-log fields are populated for downstream stability."""
        _, _, m_verify = patches  # graph.py m_analyze unused under use_tools
        m_verify.side_effect = [_mk_verdict("pass")]
        with patch("agent.nodes.analyst_with_tools.analyze_consistent") as m_sc, \
             patch("agent.nodes.analyst_with_tools.static_analyze") as m_static:
            m_sc.return_value = _mk_analyst_out(
                ["foo", "bar"], hypothesis="consensus hypothesis"
            )
            m_static.return_value.suspicious_summary.return_value = "fn list"
            r = run_pipeline(
                case_id="T_TOOLS",
                contract_source="contract C { function foo() external {} }",
                contract_name="C",
                max_retries=3,
                use_tools=True,
            )
            sc_calls = m_sc.call_count
            sc_n_runs = m_sc.call_args.kwargs.get("n_runs") if sc_calls else None

        assert r.finding_confirmed is True
        ann = r.annotations
        # Dual-log populated (both = single consensus result under Day-4)
        assert ann.get("analyst_hypothesis_pre_tool") == "consensus hypothesis"
        assert ann.get("analyst_hypothesis_post_tool") == "consensus hypothesis"
        # analyze_consistent invoked once with n_runs=3 (DEFAULT_N_CONSISTENCY)
        assert sc_calls == 1
        assert sc_n_runs == 3

    def test_use_tools_false_calls_analyze_once(self, patches: Any):
        m_analyze, _, m_verify = patches
        m_analyze.return_value = _mk_analyst_out(["foo"])
        m_verify.side_effect = [_mk_verdict("pass")]

        r = run_pipeline(
            case_id="T_NOTOOLS",
            contract_source="contract C {}",
            contract_name="C",
            max_retries=3,
            use_tools=False,
        )

        assert r.finding_confirmed is True
        assert m_analyze.call_count == 1
        # Pre/post fields not populated when tools off
        ann = r.annotations
        assert ann.get("analyst_hypothesis_pre_tool", "") == ""
        assert ann.get("analyst_hypothesis_post_tool", "") == ""
