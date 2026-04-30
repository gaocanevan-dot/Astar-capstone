"""Unit tests for the analyst node.

Mocks agent.adapters.llm.invoke_json so no real API calls are made.
"""

from unittest.mock import patch

import pytest

from agent.nodes.analyst import (
    _safe_parse,
    _truncate_source,
    analyze,
    analyze_consistent,
)
from agent.state import empty_annotations


class TestSafeParse:
    def test_clean_json(self):
        out = _safe_parse('{"target_function": "mint", "confidence": 0.9}')
        assert out == {"target_function": "mint", "confidence": 0.9}

    def test_malformed_returns_empty(self):
        out = _safe_parse("not json at all")
        assert out == {}

    def test_fenced_json_block(self):
        raw = '```json\n{"target_function": "burn"}\n```'
        out = _safe_parse(raw)
        assert out == {"target_function": "burn"}

    def test_fenced_no_lang(self):
        raw = '```\n{"target_function": "transfer"}\n```'
        out = _safe_parse(raw)
        assert out == {"target_function": "transfer"}


class TestTruncateSource:
    def test_short_unchanged(self):
        s = "pragma solidity ^0.8.0; contract X {}"
        assert _truncate_source(s) == s

    def test_long_truncated_with_marker(self):
        s = "x" * 30000
        out = _truncate_source(s, max_chars=1000)
        assert len(out) < len(s)
        assert "truncated" in out
        assert out.startswith("x" * 1000)


class TestAnalyze:
    def test_happy_path(self):
        fake_response = '{"target_function": "setFee", "hypothesis": "missing onlyOwner", "confidence": 0.85, "reasoning": "no modifier on external setter"}'

        def fake_invoke(system_prompt, user_prompt, annotations, **kwargs):
            # simulate the real LLM adapter updating annotations
            annotations["tokens_prompt"] = 1500
            annotations["tokens_completion"] = 120
            annotations["llm_calls"] = annotations.get("llm_calls", 0) + 1
            annotations["system_fingerprint"] = "fp_test_abc"
            annotations["wall_clock_seconds"] = 2.0
            return fake_response

        ann = empty_annotations()
        with patch("agent.nodes.analyst.invoke_json", side_effect=fake_invoke):
            pred = analyze("pragma solidity ^0.8.0; contract X {}", "X", ann)

        assert pred["target_function"] == "setFee"
        assert pred["hypothesis"] == "missing onlyOwner"
        assert pred["confidence"] == pytest.approx(0.85)
        assert pred["reasoning"] == "no modifier on external setter"
        assert pred["raw_response"] == fake_response
        # annotations mutated
        assert ann["llm_calls"] == 1
        assert ann["tokens_prompt"] == 1500
        assert ann["system_fingerprint"] == "fp_test_abc"

    def test_malformed_response_returns_empty_fields(self):
        def fake_invoke(system_prompt, user_prompt, annotations, **kwargs):
            return "totally not json"

        ann = empty_annotations()
        with patch("agent.nodes.analyst.invoke_json", side_effect=fake_invoke):
            pred = analyze("pragma solidity ^0.8.0; contract X {}", "X", ann)

        assert pred["target_function"] == ""
        assert pred["hypothesis"] == ""
        assert pred["confidence"] == 0.0

    def test_confidence_coerced_from_string(self):
        fake_response = '{"target_function": "mint", "confidence": "0.5"}'

        def fake_invoke(system_prompt, user_prompt, annotations, **kwargs):
            return fake_response

        ann = empty_annotations()
        with patch("agent.nodes.analyst.invoke_json", side_effect=fake_invoke):
            pred = analyze("pragma solidity ^0.8.0;", "X", ann)

        assert pred["confidence"] == pytest.approx(0.5)

    def test_confidence_non_numeric_defaults_zero(self):
        fake_response = '{"target_function": "x", "confidence": "high"}'

        def fake_invoke(system_prompt, user_prompt, annotations, **kwargs):
            return fake_response

        ann = empty_annotations()
        with patch("agent.nodes.analyst.invoke_json", side_effect=fake_invoke):
            pred = analyze("pragma solidity ^0.8.0;", "X", ann)

        assert pred["confidence"] == 0.0

    def test_very_long_source_is_truncated_before_prompt(self):
        captured = {}

        def fake_invoke(system_prompt, user_prompt, annotations, **kwargs):
            captured["user_prompt"] = user_prompt
            return '{"target_function": "x"}'

        ann = empty_annotations()
        long_src = "pragma solidity ^0.8.0;\n" + "// filler\n" * 5000
        with patch("agent.nodes.analyst.invoke_json", side_effect=fake_invoke):
            analyze(long_src, "X", ann)

        # prompt should contain "truncated" marker from _truncate_source
        assert "truncated" in captured["user_prompt"]

    def test_static_context_injected_when_provided(self):
        captured = {}

        def fake_invoke(system_prompt, user_prompt, annotations, **kwargs):
            captured["user_prompt"] = user_prompt
            return '{"target_function": "x"}'

        ann = empty_annotations()
        with patch("agent.nodes.analyst.invoke_json", side_effect=fake_invoke):
            analyze(
                "pragma solidity 0.8.20;",
                "X",
                ann,
                static_context="- `mint` · external · mods=[]",
            )
        assert "Static analysis facts" in captured["user_prompt"]
        assert "mint" in captured["user_prompt"]

    def test_static_context_absent_by_default(self):
        captured = {}

        def fake_invoke(system_prompt, user_prompt, annotations, **kwargs):
            captured["user_prompt"] = user_prompt
            return '{"target_function": "x"}'

        ann = empty_annotations()
        with patch("agent.nodes.analyst.invoke_json", side_effect=fake_invoke):
            analyze("pragma solidity 0.8.20;", "X", ann)
        assert "Static analysis facts" not in captured["user_prompt"]
        assert "Similar known-vulnerable" not in captured["user_prompt"]

    def test_rag_few_shot_injected(self):
        captured = {}

        def fake_invoke(system_prompt, user_prompt, annotations, **kwargs):
            captured["user_prompt"] = user_prompt
            return '{"target_function": "x"}'

        ann = empty_annotations()
        with patch("agent.nodes.analyst.invoke_json", side_effect=fake_invoke):
            analyze(
                "pragma solidity 0.8.20;",
                "X",
                ann,
                rag_few_shot="## Example 1 (similarity=0.9)\nVulnerable: `mint`",
            )
        assert "Similar known-vulnerable" in captured["user_prompt"]
        assert "similarity=0.9" in captured["user_prompt"]

    def test_both_contexts_can_coexist(self):
        captured = {}

        def fake_invoke(system_prompt, user_prompt, annotations, **kwargs):
            captured["user_prompt"] = user_prompt
            return '{"target_function": "x"}'

        ann = empty_annotations()
        with patch("agent.nodes.analyst.invoke_json", side_effect=fake_invoke):
            analyze(
                "pragma solidity 0.8.20;",
                "X",
                ann,
                static_context="- `mint`",
                rag_few_shot="## Example 1",
            )
        assert "Static analysis facts" in captured["user_prompt"]
        assert "Similar known-vulnerable" in captured["user_prompt"]


class TestAnalyzeConsistent:
    """Self-consistency wrapper: N runs + reciprocal-rank voting."""

    @staticmethod
    def _make_invoke(responses: list[str]):
        """Yield each response on successive calls."""
        idx = {"i": 0}

        def fake_invoke(system_prompt, user_prompt, annotations, **kwargs):
            r = responses[idx["i"] % len(responses)]
            idx["i"] += 1
            annotations["llm_calls"] = annotations.get("llm_calls", 0) + 1
            annotations["tokens_prompt"] = annotations.get("tokens_prompt", 0) + 100
            return r

        return fake_invoke

    def test_n_equals_one_falls_back_to_plain_analyze(self):
        ann = empty_annotations()
        invoke = self._make_invoke(['{"target_function": "mint", "candidates": ["mint"], "confidence": 0.9}'])
        with patch("agent.nodes.analyst.invoke_json", side_effect=invoke):
            pred = analyze_consistent("src", "X", ann, n_runs=1)
        assert pred["target_function"] == "mint"
        assert ann["llm_calls"] == 1

    def test_unanimous_top1_wins(self):
        # All 5 runs return the same top-1 → consensus is unambiguous
        ann = empty_annotations()
        responses = ['{"candidates": ["mint", "burn", "transfer"], "target_function": "mint", "confidence": 0.9}'] * 5
        with patch("agent.nodes.analyst.invoke_json", side_effect=self._make_invoke(responses)):
            pred = analyze_consistent("src", "X", ann, n_runs=5)
        assert pred["candidates"][0] == "mint"
        assert pred["target_function"] == "mint"
        assert ann["llm_calls"] == 5

    def test_majority_top1_beats_minority(self):
        # 3 of 5 runs favor "mint" at rank 1, 2 favor "burn" at rank 1
        # mint score: 3 * (1/1) = 3.0, burn score: 2 * (1/1) = 2.0
        responses = (
            ['{"candidates": ["mint", "burn"], "target_function": "mint"}'] * 3
            + ['{"candidates": ["burn", "mint"], "target_function": "burn"}'] * 2
        )
        ann = empty_annotations()
        with patch("agent.nodes.analyst.invoke_json", side_effect=self._make_invoke(responses)):
            pred = analyze_consistent("src", "X", ann, n_runs=5)
        # Total scores: mint = 3*1 + 2*0.5 = 4.0, burn = 3*0.5 + 2*1 = 3.5 → mint wins
        assert pred["candidates"][0] == "mint"
        assert pred["candidates"][1] == "burn"

    def test_reciprocal_rank_promotes_consistent_lower_ranked(self):
        # Candidate "X" is rank-1 only once but rank-2 in all 5 → cumulative 1 + 5*0.5 = 3.5
        # Candidate "Y" is rank-1 in 4 → cumulative 4
        # Y wins despite X showing in more runs at #2
        responses = (
            ['{"candidates": ["X", "Y"], "target_function": "X"}']
            + ['{"candidates": ["Y", "X"], "target_function": "Y"}'] * 4
        )
        ann = empty_annotations()
        with patch("agent.nodes.analyst.invoke_json", side_effect=self._make_invoke(responses)):
            pred = analyze_consistent("src", "X", ann, n_runs=5)
        assert pred["candidates"][0] == "Y"

    def test_annotations_accumulate_across_runs(self):
        responses = ['{"candidates": ["fn"], "target_function": "fn"}'] * 5
        ann = empty_annotations()
        with patch("agent.nodes.analyst.invoke_json", side_effect=self._make_invoke(responses)):
            analyze_consistent("src", "X", ann, n_runs=5)
        assert ann["llm_calls"] == 5
        assert ann["tokens_prompt"] == 500

    def test_reasoning_includes_self_consistency_marker(self):
        responses = ['{"candidates": ["fn"], "target_function": "fn", "reasoning": "no modifier"}'] * 3
        ann = empty_annotations()
        with patch("agent.nodes.analyst.invoke_json", side_effect=self._make_invoke(responses)):
            pred = analyze_consistent("src", "X", ann, n_runs=3)
        assert "self-consistency" in pred["reasoning"].lower()
        assert "no modifier" in pred["reasoning"]
