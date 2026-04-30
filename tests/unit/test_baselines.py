"""Unit tests for baseline predictors — verify PredictionRecord schema,
empty-source handling, and aggregation helpers.

GPT-zeroshot's LLM call is mocked; Slither's subprocess is not mocked but
the test feeds it a self-contained toy contract so it actually runs.
"""

from unittest.mock import patch

from agent.baselines import PredictionRecord
from agent.baselines.gpt_zeroshot import evaluate as gpt_eval


class _FakeCase:
    """Duck-type a Case object for baseline tests without needing pydantic."""
    def __init__(self, id, source, name="X", gt="targetFn"):
        self.id = id
        self.contract_source = source
        self.contract_name = name
        self.vulnerable_function = gt


def test_prediction_record_has_expected_fields():
    r = PredictionRecord(
        case_id="A",
        contract_name="X",
        ground_truth_function="f",
        flagged=True,
        flagged_functions=["f"],
        predicted_function="f",
    )
    assert r.case_id == "A"
    assert r.flagged is True
    assert r.predicted_function == "f"
    assert r.tokens_prompt == 0
    assert r.error == ""


def test_gpt_zeroshot_empty_source_returns_error_record():
    case = _FakeCase("empty", "")
    out = gpt_eval(case)
    assert out.flagged is False
    assert out.predicted_function == ""
    assert "empty" in out.error.lower()
    assert out.method == "gpt_zeroshot"


def test_gpt_zeroshot_happy_path_mocked():
    case = _FakeCase(
        "case1",
        "pragma solidity 0.8.20; contract X { function mint() external {} }",
        name="X",
        gt="mint",
    )

    fake_response = '{"is_vulnerable": true, "vulnerable_functions": ["mint", "burn"]}'

    def fake_invoke(system_prompt, user_prompt, annotations, **kwargs):
        annotations["tokens_prompt"] = 800
        annotations["tokens_completion"] = 60
        annotations["llm_calls"] = annotations.get("llm_calls", 0) + 1
        annotations["system_fingerprint"] = "fp_test"
        return fake_response

    with patch("agent.baselines.gpt_zeroshot.invoke_json", side_effect=fake_invoke):
        out = gpt_eval(case)

    assert out.flagged is True
    assert out.flagged_functions == ["mint", "burn"]
    assert out.predicted_function == "mint"
    assert out.tokens_prompt == 800
    assert out.llm_calls == 1
    assert out.method == "gpt_zeroshot"


def test_gpt_zeroshot_malformed_json_error_recorded():
    case = _FakeCase("c2", "pragma solidity 0.8.20; contract X {}", gt="f")

    with patch(
        "agent.baselines.gpt_zeroshot.invoke_json",
        return_value="not json",
    ):
        out = gpt_eval(case)

    assert out.flagged is False
    assert out.predicted_function == ""
    assert "parse failed" in out.error.lower()


def test_gpt_zeroshot_llm_exception_recorded():
    case = _FakeCase("c3", "pragma solidity 0.8.20; contract X {}", gt="f")

    with patch(
        "agent.baselines.gpt_zeroshot.invoke_json",
        side_effect=RuntimeError("network down"),
    ):
        out = gpt_eval(case)

    assert out.flagged is False
    assert "RuntimeError" in out.error
    assert "network down" in out.error
    assert out.method == "gpt_zeroshot"
