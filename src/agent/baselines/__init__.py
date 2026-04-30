"""Baseline predictors — Slither static + GPT-X zero-shot.

Both conform to the PredictionRecord protocol so the aggregator can compare
them 1:1 with our agent's output.
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass
class PredictionRecord:
    """Unified per-case baseline output."""

    case_id: str
    contract_name: str
    ground_truth_function: str
    # Contract-level binary
    flagged: bool
    # Function-level
    flagged_functions: list[str]
    # Primary function prediction (first of flagged_functions, or "" if none)
    predicted_function: str
    # Compute accounting
    tokens_prompt: int = 0
    tokens_completion: int = 0
    llm_calls: int = 0
    wall_clock_seconds: float = 0.0
    # Debugging
    raw_output: str = ""
    error: str = ""
    method: str = "unknown"


class BaselinePredictor(Protocol):
    def evaluate(self, case) -> PredictionRecord: ...
