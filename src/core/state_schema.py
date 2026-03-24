"""
Shared state schema for the audit agent.

This file is a clean replacement for the older state module and is intended to
support a lightweight demo with optional static analysis and RAG.
"""

from enum import Enum
from typing import Dict, List, Literal, TypedDict

from pydantic import BaseModel, Field


class VulnerabilityType(str, Enum):
    ACCESS_CONTROL = "access_control"
    PRIVILEGE_ESCALATION = "privilege_escalation"


class SensitiveFunction(BaseModel):
    name: str = Field(description="Function name")
    signature: str = Field(description="Function signature")
    has_access_control: bool = Field(default=False, description="Whether access control exists")
    modifiers: List[str] = Field(default_factory=list, description="Function modifiers")
    risk_level: Literal["high", "medium", "low"] = Field(default="medium")


class VulnerabilityFinding(BaseModel):
    function_name: str
    vulnerability_type: VulnerabilityType
    severity: Literal["critical", "high", "medium", "low"]
    description: str
    poc_code: str = ""


class RetrievedCase(BaseModel):
    id: str = Field(description="Case id")
    vulnerability_type: str = Field(description="Vulnerability type")
    description: str = Field(description="Vulnerability description")
    affected_code: str = Field(description="Affected code snippet")
    poc_code: str = Field(default="", description="PoC code")
    similarity_score: float = Field(default=0.0, description="Similarity score")


class AuditGraphState(TypedDict):
    contract_source: str
    contract_name: str
    use_static_analysis: bool
    use_rag: bool

    similar_cases: List[Dict]
    few_shot_examples: List[Dict]

    static_analysis_summary: str
    function_summaries: List[Dict]
    call_graph: Dict[str, List[str]]
    storage_write_map: Dict[str, List[str]]
    modifier_map: Dict[str, List[str]]
    sensitive_candidates: List[Dict]
    static_tool_findings: List[Dict]

    sensitive_functions: List[Dict]
    audit_hypothesis: str
    current_target_function: str

    verification_poc: str
    execution_result: Literal["pass", "fail_revert", "fail_error", "pending"]
    error_message: str

    retry_count: int
    max_retries: int

    finding_confirmed: bool
    findings: List[Dict]
    audit_report: Dict


def create_initial_state(
    contract_source: str,
    contract_name: str = "TargetContract",
    max_retries: int = 3,
    use_static_analysis: bool = True,
    use_rag: bool = True,
) -> AuditGraphState:
    return AuditGraphState(
        contract_source=contract_source,
        contract_name=contract_name,
        use_static_analysis=use_static_analysis,
        use_rag=use_rag,
        similar_cases=[],
        few_shot_examples=[],
        static_analysis_summary="",
        function_summaries=[],
        call_graph={},
        storage_write_map={},
        modifier_map={},
        sensitive_candidates=[],
        static_tool_findings=[],
        sensitive_functions=[],
        audit_hypothesis="",
        current_target_function="",
        verification_poc="",
        execution_result="pending",
        error_message="",
        retry_count=0,
        max_retries=max_retries,
        finding_confirmed=False,
        findings=[],
        audit_report={},
    )
