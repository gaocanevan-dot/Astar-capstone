"""Unit tests for analyst tool-use wrapper.

Day-2 ORIGINAL: dual-call (pre + post) when use_tools=True.
Day-4 Issue 2: SINGLE augmented analyst call.
Day-4 Issue 3: when use_tools=True, default n_consistency=3 (RRF voting via
                 `analyze_consistent`), gated by R8 pre-test (3/6 cases
                 diverged on smoke).

Tests cover:
- single-call path (n_consistency=1)
- self-consistency path (n_consistency=3 → analyze_consistent invoked)
- use_tools=False bypass (no static-fact injection, no SC)
- static_context augmentation includes the suspicious_summary tool block
- dual-log fields populated for downstream consumer stability
"""

from __future__ import annotations

from unittest.mock import patch

from agent.nodes.analyst_with_tools import (
    _build_tool_block,
    _get_function_body,
    analyze_with_tools,
)
from agent.state import empty_annotations


def _ann():
    return dict(empty_annotations())


def _stub_pred(target: str, hypothesis: str):
    return {
        "target_function": target,
        "candidates": [target],
        "hypothesis": hypothesis,
        "confidence": 0.9,
        "reasoning": "test",
        "raw_response": "",
    }


class TestAnalyzeWithToolsSingleCall:
    def test_use_tools_true_n_consistency_1_calls_analyze_once(self):
        """Day-4 Issue 2: tools-on with n=1 → single analyze() call."""
        ann = _ann()
        with patch("agent.nodes.analyst_with_tools.analyze") as m_analyze, \
             patch("agent.nodes.analyst_with_tools.static_analyze") as m_static:
            m_analyze.return_value = _stub_pred("foo", "single hypothesis")
            m_static.return_value.suspicious_summary.return_value = (
                "- `foo` · external · mods=[-]"
            )
            result = analyze_with_tools(
                contract_source="contract C { function foo() external {} }",
                contract_name="C",
                annotations=ann,
                use_tools=True,
                n_consistency=1,
            )
        assert m_analyze.call_count == 1
        assert ann["analyst_hypothesis_pre_tool"] == "single hypothesis"
        assert ann["analyst_hypothesis_post_tool"] == "single hypothesis"
        assert result["hypothesis"] == "single hypothesis"

    def test_use_tools_false_calls_analyze_once_no_tool_block(self):
        ann = _ann()
        with patch("agent.nodes.analyst_with_tools.analyze") as m_analyze:
            m_analyze.return_value = _stub_pred("foo", "raw hypothesis")
            analyze_with_tools(
                contract_source="contract C { function foo() external {} }",
                contract_name="C",
                annotations=ann,
                use_tools=False,
                n_consistency=1,
            )
        assert m_analyze.call_count == 1
        # Without tools, static_context passed through unchanged (default empty)
        kwargs = m_analyze.call_args.kwargs
        assert "Static analysis" not in kwargs.get("static_context", "")


class TestAnalyzeWithToolsSelfConsistency:
    def test_use_tools_true_n_consistency_3_invokes_analyze_consistent(self):
        """Day-4 Issue 3: tools-on with n=3 routes through analyze_consistent."""
        ann = _ann()
        with patch("agent.nodes.analyst_with_tools.analyze_consistent") as m_sc, \
             patch("agent.nodes.analyst_with_tools.analyze") as m_single, \
             patch("agent.nodes.analyst_with_tools.static_analyze") as m_static:
            m_sc.return_value = _stub_pred("voted_target", "consensus hypothesis")
            m_static.return_value.suspicious_summary.return_value = "fn list"
            result = analyze_with_tools(
                contract_source="contract C {}",
                contract_name="C",
                annotations=ann,
                use_tools=True,
                n_consistency=3,
            )
        # analyze_consistent called once with n_runs=3; bare analyze NOT called.
        assert m_sc.call_count == 1
        assert m_sc.call_args.kwargs.get("n_runs") == 3
        assert m_single.call_count == 0
        assert result["target_function"] == "voted_target"

    def test_use_tools_false_with_n_3_still_uses_single_call(self):
        """SC path is gated on use_tools=True; n_consistency alone doesn't trigger."""
        ann = _ann()
        with patch("agent.nodes.analyst_with_tools.analyze_consistent") as m_sc, \
             patch("agent.nodes.analyst_with_tools.analyze") as m_single:
            m_single.return_value = _stub_pred("foo", "single")
            analyze_with_tools(
                contract_source="contract C {}",
                contract_name="C",
                annotations=ann,
                use_tools=False,
                n_consistency=3,
            )
        assert m_sc.call_count == 0
        assert m_single.call_count == 1


class TestStaticContextAugmentation:
    def test_tool_block_prepended_to_caller_static_context(self):
        ann = _ann()
        with patch("agent.nodes.analyst_with_tools.analyze") as m_analyze, \
             patch("agent.nodes.analyst_with_tools.static_analyze") as m_static:
            m_analyze.return_value = _stub_pred("transferOwnership", "h")
            m_static.return_value.suspicious_summary.return_value = (
                "- `transferOwnership` · external · mods=[-]"
            )
            analyze_with_tools(
                contract_source="contract C {}",
                contract_name="C",
                annotations=ann,
                use_tools=True,
                n_consistency=1,
                static_context="caller-provided context",
            )
        sent_static = m_analyze.call_args.kwargs["static_context"]
        # Caller context comes first, tool block appended.
        assert sent_static.startswith("caller-provided context")
        assert "Static analysis: suspicious functions" in sent_static
        assert "transferOwnership" in sent_static

    def test_build_tool_block_uses_suspicious_summary(self):
        with patch("agent.nodes.analyst_with_tools.static_analyze") as m_static:
            m_static.return_value.suspicious_summary.return_value = (
                "- `withdraw` · external · mods=[-] [STATE]"
            )
            block = _build_tool_block(
                contract_source="contract C {}", contract_name="C"
            )
        assert "Static analysis: suspicious functions" in block
        assert "withdraw" in block

    def test_build_tool_block_static_analyzer_failure_falls_back(self):
        with patch("agent.nodes.analyst_with_tools.static_analyze") as m_static:
            m_static.side_effect = RuntimeError("slither missing")
            block = _build_tool_block(
                contract_source="contract C {}", contract_name="C"
            )
        # Block still rendered with header + failure note (no exception)
        assert "Static analysis" in block
        assert "static analyzer failed" in block


class TestGetFunctionBody:
    """`_get_function_body` retained as a utility (used in tests + future
    body-fetch features); not currently called by `analyze_with_tools` post
    Day-4 Issue 2 simplification."""

    def test_simple_function(self):
        src = "contract C { function foo() external { return; } }"
        body = _get_function_body(src, "foo")
        assert body is not None
        assert "return;" in body

    def test_nested_braces(self):
        src = (
            "contract C { function bar() external { if (true) { x = 1; } } }"
        )
        body = _get_function_body(src, "bar")
        assert body is not None
        assert "if (true)" in body
        assert "x = 1" in body

    def test_missing_function_returns_none(self):
        src = "contract C { function foo() external {} }"
        assert _get_function_body(src, "doesNotExist") is None

    def test_empty_name_returns_none(self):
        assert _get_function_body("contract C {}", "") is None
