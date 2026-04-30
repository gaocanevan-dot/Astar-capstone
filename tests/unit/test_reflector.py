"""Unit tests for Day-2 T9 reflection node — `agent.nodes.reflector.reflect`.

Asserts the LOCKED invariant: output `target_function` MUST be a member of
the input candidate list. Mocks `invoke_json` so no real LLM call happens.
"""

from __future__ import annotations

from unittest.mock import patch

from agent.nodes.reflector import reflect
from agent.state import empty_annotations


def _ann():
    return dict(empty_annotations())


class TestReflectorLockedInvariant:
    def test_picks_in_set_candidate_when_llm_obeys(self):
        with patch("agent.nodes.reflector.invoke_json") as m:
            m.return_value = '{"target_function": "bar", "hypothesis": "h2", "reasoning": "r"}'
            ann = _ann()
            out = reflect(
                prior_target="foo",
                prior_hypothesis="h1",
                prior_verdict="fail_revert_ac",
                prior_error="",
                candidates=["foo", "bar", "baz"],
                tried_candidates=["foo"],
                annotations=ann,
            )
        assert out["target_function"] == "bar"
        assert out["candidate_in_set"] is True
        assert out["hypothesis"] == "h2"
        # reflection_trace recorded
        assert len(ann["reflection_trace"]) == 1
        assert ann["reflection_trace"][0]["picked_target"] == "bar"
        assert ann["reflection_trace"][0]["in_set"] is True

    def test_off_list_target_falls_back_to_untried_candidate(self):
        with patch("agent.nodes.reflector.invoke_json") as m:
            m.return_value = '{"target_function": "INVENTED_FN", "hypothesis": "h2", "reasoning": "r"}'
            ann = _ann()
            out = reflect(
                prior_target="foo",
                prior_hypothesis="h1",
                prior_verdict="fail_revert_ac",
                prior_error="",
                candidates=["foo", "bar", "baz"],
                tried_candidates=["foo"],
                annotations=ann,
            )
        # LOCKED invariant: must pick from candidates list.
        assert out["target_function"] in ["foo", "bar", "baz"]
        # Specifically: first un-tried candidate is "bar".
        assert out["target_function"] == "bar"
        assert out["candidate_in_set"] is False
        assert "locked-fallback" in out["reasoning"]
        assert ann["reflection_trace"][0]["in_set"] is False

    def test_off_list_with_all_tried_falls_back_to_first(self):
        with patch("agent.nodes.reflector.invoke_json") as m:
            m.return_value = '{"target_function": "INVENTED", "hypothesis": "h", "reasoning": "r"}'
            ann = _ann()
            out = reflect(
                prior_target="foo",
                prior_hypothesis="h",
                prior_verdict="fail_revert_ac",
                prior_error="",
                candidates=["foo", "bar"],
                tried_candidates=["foo", "bar"],  # all tried
                annotations=ann,
            )
        assert out["target_function"] == "foo"  # falls back to candidates[0]
        assert out["candidate_in_set"] is False

    def test_empty_candidates_returns_empty_target(self):
        ann = _ann()
        out = reflect(
            prior_target="foo",
            prior_hypothesis="h",
            prior_verdict="abstain",
            prior_error="",
            candidates=[],
            tried_candidates=[],
            annotations=ann,
        )
        assert out["target_function"] == ""
        assert out["candidate_in_set"] is True
        # No LLM call when candidate set empty
        assert ann.get("reflection_trace") in (None, [])


class TestReflectorJsonRobustness:
    def test_handles_markdown_fenced_json(self):
        with patch("agent.nodes.reflector.invoke_json") as m:
            m.return_value = '```json\n{"target_function": "bar", "hypothesis": "h", "reasoning": "r"}\n```'
            out = reflect(
                prior_target="foo",
                prior_hypothesis="h",
                prior_verdict="fail_revert_ac",
                prior_error="",
                candidates=["foo", "bar"],
                tried_candidates=["foo"],
                annotations=_ann(),
            )
        assert out["target_function"] == "bar"
        assert out["candidate_in_set"] is True

    def test_handles_garbage_response_falls_back(self):
        with patch("agent.nodes.reflector.invoke_json") as m:
            m.return_value = "not json at all sorry"
            out = reflect(
                prior_target="foo",
                prior_hypothesis="h",
                prior_verdict="fail_revert_ac",
                prior_error="",
                candidates=["foo", "bar"],
                tried_candidates=["foo"],
                annotations=_ann(),
            )
        # Garbage → empty target → off-list → fallback to first un-tried "bar"
        assert out["target_function"] == "bar"
        assert out["candidate_in_set"] is False
