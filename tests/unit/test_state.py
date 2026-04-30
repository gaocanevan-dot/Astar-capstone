"""Unit tests for AuditCore + AuditAnnotations schemas."""

from agent.state import (
    AuditAnnotations,
    AuditCore,
    empty_annotations,
    empty_core,
)


def test_empty_core_has_all_ten_fields():
    core = empty_core()
    required = {
        "contract_source",
        "contract_abi",
        "defined_roles",
        "sensitive_functions",
        "audit_hypothesis",
        "verification_poc",
        "execution_trace",
        "retry_count",
        "finding_confirmed",
        "audit_report",
    }
    assert set(core.keys()) == required
    assert len(required) == 10


def test_empty_core_types():
    core = empty_core()
    assert isinstance(core["contract_source"], str)
    assert isinstance(core["contract_abi"], list)
    assert isinstance(core["defined_roles"], list)
    assert isinstance(core["sensitive_functions"], list)
    assert isinstance(core["retry_count"], int)
    assert core["retry_count"] == 0
    assert core["finding_confirmed"] is False
    assert isinstance(core["audit_report"], dict)


def test_empty_annotations_has_six_core_fields():
    ann = empty_annotations()
    # total=False means fields are optional in the type, but empty_annotations
    # explicitly populates six defaults:
    assert ann["error_history"] == []
    assert ann["tokens_prompt"] == 0
    assert ann["tokens_completion"] == 0
    assert ann["llm_calls"] == 0
    assert ann["system_fingerprint"] == ""
    assert ann["wall_clock_seconds"] == 0.0


def test_annotations_accepts_optional_fields():
    ann: AuditAnnotations = empty_annotations()
    # total=False means these are allowed but not required
    ann["target_function"] = "setFee"
    ann["confidence"] = 0.8
    ann["case_id"] = "C4-42"
    assert ann["target_function"] == "setFee"


def test_typeddict_names_exported():
    # Sanity: the symbols are importable (not just types exported privately)
    assert AuditCore is not None
    assert AuditAnnotations is not None
