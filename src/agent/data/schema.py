"""Pydantic models for the 150-bad-case evaluation dataset.

Schema is aligned with:
- consensus-plan-150bad.md §4 Phase 1 exit criteria
- deep-interview-150-bad-case-detection.md Acceptance Criteria ("Dataset" section)
"""

from typing import Literal, Optional
from pydantic import BaseModel, Field, ConfigDict


VulnerabilityType = Literal["access_control", "privilege_escalation"]
GroundTruthLabel = Literal["vulnerable", "safe"]
SourceType = Literal[
    "code4rena_bad",
    "swc_bad",
    "oz_safe",
    "c4_invalid_safe",
    "fixed_code_safe",
]
SplitName = Literal["dev", "test"]


class Case(BaseModel):
    """Single evaluation case. `ground_truth_label` disambiguates bad vs safe."""

    model_config = ConfigDict(extra="allow")  # tolerate extra fields from legacy JSONs

    id: str
    contract_source: str
    contract_name: str = ""
    ground_truth_label: GroundTruthLabel = "vulnerable"
    source: str = ""
    source_type: SourceType = "code4rena_bad"
    project_name: str = ""
    buildable: bool = True

    vulnerable_function: Optional[str] = None
    vulnerability_type: VulnerabilityType = "access_control"
    severity: str = "high"
    description: str = ""
    missing_check: str = ""

    attack_surface: str = ""
    vulnerable_code_snippet: str = ""
    issue_category: str = ""
    fix_recommendation: str = ""
    fixed_code: str = ""
    poc_code: str = ""
    tags: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)

    split: Optional[SplitName] = None


class EvalSet(BaseModel):
    cases: list[Case]

    def count_by_label(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for c in self.cases:
            out[c.ground_truth_label] = out.get(c.ground_truth_label, 0) + 1
        return out

    def count_by_source_type(self, label: GroundTruthLabel) -> dict[str, int]:
        out: dict[str, int] = {}
        for c in self.cases:
            if c.ground_truth_label == label:
                out[c.source_type] = out.get(c.source_type, 0) + 1
        return out
