"""AuditCore + AuditAnnotations per framework.md §4.1 (10 core fields).

Single-agent variant uses a subset of these fields — builder/verifier-specific
fields are kept for forward compatibility with the full LangGraph variant.
"""

from typing import NotRequired, TypedDict


class AuditCore(TypedDict):
    """Frozen 10-field core state, mirroring framework.md §4.1 exactly.

    Fields that are not applicable to the single-agent variant
    (verification_poc, execution_trace, retry_count, finding_confirmed) are
    still declared here so the schema matches the paper figure.
    """

    contract_source: str
    contract_abi: list
    defined_roles: list[str]
    sensitive_functions: list[dict]
    audit_hypothesis: str
    verification_poc: str
    execution_trace: str
    retry_count: int
    finding_confirmed: bool
    audit_report: dict


class AuditAnnotations(TypedDict, total=False):
    """Implementation-level fields that piggy-back on core state.

    Explicit field list rather than bare Dict[str, Any] (Architect minor #1).
    """

    error_history: list[str]
    tokens_prompt: int
    tokens_completion: int
    llm_calls: int
    system_fingerprint: str
    wall_clock_seconds: float
    target_function: NotRequired[str]  # analyst's predicted vulnerable function
    confidence: NotRequired[float]
    reasoning: NotRequired[str]
    case_id: NotRequired[str]
    contract_name: NotRequired[str]
    # Day-1 iter4 additions: agent-flow scaffolding (cascade/reflection/tool-use)
    verifier_mode: NotRequired[str]  # "original" | "oz_vendored" | "replica_only"
    top_k_candidates: NotRequired[list[str]]
    analyst_hypothesis_pre_tool: NotRequired[str]
    analyst_hypothesis_post_tool: NotRequired[str]
    cascade_trace: NotRequired[list[dict]]
    reflection_trace: NotRequired[list[dict]]
    abstained: NotRequired[bool]


def empty_core() -> AuditCore:
    return AuditCore(
        contract_source="",
        contract_abi=[],
        defined_roles=[],
        sensitive_functions=[],
        audit_hypothesis="",
        verification_poc="",
        execution_trace="",
        retry_count=0,
        finding_confirmed=False,
        audit_report={},
    )


def empty_annotations() -> AuditAnnotations:
    return AuditAnnotations(
        error_history=[],
        tokens_prompt=0,
        tokens_completion=0,
        llm_calls=0,
        system_fingerprint="",
        wall_clock_seconds=0.0,
        # Day-2 Prereq-C: seed Day-1 fields so cascade router's gets/lookups
        # don't KeyError before the analyst/builder write to them.
        verifier_mode="",
        top_k_candidates=[],
        analyst_hypothesis_pre_tool="",
        analyst_hypothesis_post_tool="",
        cascade_trace=[],
        reflection_trace=[],
        abstained=False,
    )
