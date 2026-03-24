"""
Static-analysis preprocessing node.
"""

from pathlib import Path

from ..core.state_schema import AuditGraphState
from ..tools.static_adapter import analyze_contract_static


def preprocess_static_analysis(state: AuditGraphState) -> AuditGraphState:
    """Extract lightweight static-analysis facts before the analyst runs."""

    if not state.get("use_static_analysis", True):
        return {
            **state,
            "static_analysis_summary": "Static analysis disabled.",
            "function_summaries": [],
            "call_graph": {},
            "storage_write_map": {},
            "modifier_map": {},
            "sensitive_candidates": [],
            "static_tool_findings": [],
        }

    contract_path = _resolve_contract_path(state)
    if contract_path is None:
        return {
            **state,
            "static_analysis_summary": "Static analysis skipped because contract path could not be resolved.",
            "function_summaries": [],
            "call_graph": {},
            "storage_write_map": {},
            "modifier_map": {},
            "sensitive_candidates": [],
            "static_tool_findings": [],
        }

    analysis = analyze_contract_static(str(contract_path), state["contract_source"])
    return {**state, **analysis}


def _resolve_contract_path(state: AuditGraphState) -> Path | None:
    candidate = Path("data/contracts") / f"{state.get('contract_name', '')}.sol"
    if candidate.exists():
        return candidate

    fallback_name = f"{state.get('contract_name', '')}.sol"
    for path in Path.cwd().rglob(fallback_name):
        if path.is_file():
            return path
    return None
