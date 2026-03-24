"""
Lightweight static-analysis adapter for the demo pipeline.

It prefers cheap source parsing and optionally enriches the result with Slither
if the executable is available. This keeps the demo lightweight while still
making static analysis a first-class input.
"""

from __future__ import annotations

import re
from typing import Dict, List

from .slither import SlitherTool, check_slither_installed

SENSITIVE_KEYWORDS = (
    "owner",
    "admin",
    "fee",
    "withdraw",
    "pause",
    "mint",
    "burn",
    "upgrade",
    "role",
)

WRITE_PATTERNS = {
    "owner": r"\bowner\s*=",
    "admin": r"\badmin\s*=",
    "protocolFee": r"\bprotocolFee\s*=",
    "paused": r"\bpaused\s*=",
    "balances": r"\bbalances\s*\[",
}


def analyze_contract_static(contract_path: str, contract_source: str) -> Dict:
    """Return normalized static-analysis facts for the analyst node."""

    functions = _extract_functions(contract_source)
    modifier_map = {func["name"]: func["modifiers"] for func in functions}
    storage_write_map = {func["name"]: func["writes"] for func in functions}

    findings: List[Dict] = []
    if check_slither_installed():
        tool = SlitherTool()
        success, slither_findings, _ = tool.get_access_control_findings(contract_path)
        if success:
            findings = [
                {
                    "check": finding.check,
                    "impact": finding.impact,
                    "confidence": finding.confidence,
                    "description": finding.description,
                }
                for finding in slither_findings
            ]

    sensitive_candidates = [
        {
            "name": func["name"],
            "visibility": func["visibility"],
            "modifiers": func["modifiers"],
            "writes": func["writes"],
            "reason": _build_sensitivity_reason(func),
        }
        for func in functions
        if func["is_sensitive"]
    ]

    summary_lines = []
    for func in sensitive_candidates[:6]:
        access = "protected" if func["modifiers"] else "unprotected"
        writes = ", ".join(func["writes"]) if func["writes"] else "no tracked writes"
        summary_lines.append(
            f"- {func['name']} ({func['visibility']}, {access}) writes: {writes}; reason: {func['reason']}"
        )
    if findings:
        summary_lines.append("- Tool findings:")
        summary_lines.extend(
            f"  - {item['check']} [{item['impact']}/{item['confidence']}]: {item['description'][:160]}"
            for item in findings[:5]
        )

    return {
        "static_analysis_summary": "\n".join(summary_lines) if summary_lines else "No static-analysis facts available.",
        "function_summaries": functions,
        "call_graph": {func["name"]: [] for func in functions},
        "storage_write_map": storage_write_map,
        "modifier_map": modifier_map,
        "sensitive_candidates": sensitive_candidates,
        "static_tool_findings": findings,
    }


def _extract_functions(contract_source: str) -> List[Dict]:
    pattern = re.compile(
        r"function\s+(?P<name>\w+)\s*\((?P<params>[^)]*)\)\s*"
        r"(?P<attrs>[^{;]*)\{(?P<body>.*?)\}",
        re.DOTALL,
    )
    functions: List[Dict] = []
    for match in pattern.finditer(contract_source):
        name = match.group("name")
        attrs = match.group("attrs")
        body = match.group("body")
        visibility = _extract_visibility(attrs)
        modifiers = _extract_modifiers(attrs)
        writes = [var for var, expr in WRITE_PATTERNS.items() if re.search(expr, body)]
        is_sensitive = _is_sensitive_function(name, modifiers, writes, body)
        functions.append(
            {
                "name": name,
                "signature": f"{name}({match.group('params').strip()})",
                "visibility": visibility,
                "modifiers": modifiers,
                "writes": writes,
                "has_access_control": any(mod.lower().startswith("only") for mod in modifiers),
                "is_sensitive": is_sensitive,
            }
        )
    return functions


def _extract_visibility(attrs: str) -> str:
    for keyword in ("external", "public", "internal", "private"):
        if re.search(rf"\b{keyword}\b", attrs):
            return keyword
    return "public"


def _extract_modifiers(attrs: str) -> List[str]:
    known_keywords = {
        "external",
        "public",
        "internal",
        "private",
        "view",
        "pure",
        "payable",
        "virtual",
        "override",
        "returns",
        "memory",
        "calldata",
    }
    tokens = re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", attrs)
    return [token for token in tokens if token not in known_keywords]


def _is_sensitive_function(name: str, modifiers: List[str], writes: List[str], body: str) -> bool:
    lowered = name.lower()
    if any(keyword in lowered for keyword in SENSITIVE_KEYWORDS):
        return True
    if writes:
        return True
    return "transfer(" in body or "call{" in body or "selfdestruct" in body


def _build_sensitivity_reason(func: Dict) -> str:
    reasons = []
    if func["writes"]:
        reasons.append(f"writes {', '.join(func['writes'])}")
    if any(keyword in func["name"].lower() for keyword in SENSITIVE_KEYWORDS):
        reasons.append("name suggests privileged action")
    if not func["modifiers"]:
        reasons.append("no modifier")
    return ", ".join(reasons) if reasons else "candidate by static heuristic"
