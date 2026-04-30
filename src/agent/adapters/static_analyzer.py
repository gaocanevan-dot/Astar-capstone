"""Static-analysis adapter — Slither subprocess + regex fallback.

Returns a compact structured summary (list of functions with their modifiers
+ any Slither access-control detector findings) suitable for injection into
the analyst prompt.

Design notes:
- Writes contract_source to a tmpfile (no disk-resident src needed).
- If Slither is missing or times out, falls back to a pure regex walker.
- Output is *deliberately small* to keep analyst prompt tokens bounded.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


_FN_RE = re.compile(
    r"function\s+(?P<name>\w+)\s*\([^)]*\)\s*(?P<attrs>[^{;]*)\{",
    re.DOTALL,
)


@dataclass
class FunctionFact:
    name: str
    visibility: str
    modifiers: list[str]
    state_changing: bool


@dataclass
class StaticFacts:
    functions: list[FunctionFact] = field(default_factory=list)
    slither_findings: list[dict] = field(default_factory=list)
    tool: str = "regex"  # "slither" or "regex"

    def compact_summary(self, max_lines: int = 12) -> str:
        """Bounded string injection for the analyst prompt."""
        if not self.functions and not self.slither_findings:
            return "No static facts available."
        lines = []
        if self.functions:
            lines.append("# Functions (name · visibility · modifiers):")
            for fn in self.functions[:max_lines]:
                mods = ", ".join(fn.modifiers) or "-"
                vis = fn.visibility or "?"
                flag = " [STATE]" if fn.state_changing else ""
                lines.append(f"- `{fn.name}` · {vis} · mods=[{mods}]{flag}")
        if self.slither_findings:
            lines.append("# Slither AC-category findings:")
            for f in self.slither_findings[:5]:
                lines.append(f"- {f.get('check','?')}: {f.get('description','')[:120]}")
        return "\n".join(lines)

    def suspicious_summary(self, max_candidates: int = 10) -> str:
        """Filtered, directed prompt: pre-narrow candidate pool for the analyst.

        Keeps only functions that:
          - are externally callable (external/public)
          - mutate state
          - lack obvious access-control modifiers (onlyOwner, onlyRole, role-based, nonReentrant-only, etc.)
          - are not internal helpers (no leading underscore)

        Falls back to the unfiltered compact_summary when the filter empties out
        — better to give the analyst noisy context than nothing.
        """
        ac_mod_markers = ("only", "Role", "Auth", "Owner", "Admin", "Manager")
        suspicious: list[FunctionFact] = []
        for fn in self.functions:
            if fn.visibility not in ("external", "public"):
                continue
            if not fn.state_changing:
                continue
            if fn.name.startswith("_"):
                continue
            has_ac_mod = any(
                any(marker in m for marker in ac_mod_markers) for m in fn.modifiers
            )
            if has_ac_mod:
                continue
            suspicious.append(fn)
        if not suspicious:
            # Filter empty (small contract or all functions guarded) →
            # fall back so analyst still sees something
            return self.compact_summary(max_lines=12)
        lines = [
            "# Pre-filtered suspicious candidates "
            "(external/public + state-changing + no obvious access-control modifier):"
        ]
        for fn in suspicious[:max_candidates]:
            mods = ", ".join(fn.modifiers) or "none"
            lines.append(f"- `{fn.name}` (visibility={fn.visibility}, modifiers={mods})")
        if self.slither_findings:
            lines.append("# Slither AC-category findings:")
            for f in self.slither_findings[:5]:
                lines.append(f"- {f.get('check','?')}: {f.get('description','')[:120]}")
        lines.append(
            "\nThe ground-truth vulnerable function is highly likely to be in the "
            "list above. Use this as your primary candidate pool when ranking top-3."
        )
        return "\n".join(lines)


def _resolve_slither() -> Optional[str]:
    repo_root = Path(__file__).resolve().parents[3]
    venv_slither = repo_root / "venv" / "Scripts" / ("slither.exe" if os.name == "nt" else "slither")
    if venv_slither.exists():
        return str(venv_slither)
    return shutil.which("slither")


def analyze(contract_source: str, contract_name: str = "Target") -> StaticFacts:
    """Return structured static facts. Always succeeds (worst case: empty)."""
    slither = _resolve_slither()
    if slither:
        try:
            return _run_slither(slither, contract_source, contract_name)
        except Exception:
            pass  # fall through to regex
    return _regex_fallback(contract_source)


def _run_slither(
    slither_bin: str, contract_source: str, contract_name: str, timeout_s: int = 60
) -> StaticFacts:
    with tempfile.TemporaryDirectory(prefix="agent_slither_") as tmp:
        src = Path(tmp) / f"{contract_name}.sol"
        src.write_text(contract_source, encoding="utf-8")
        try:
            result = subprocess.run(
                [slither_bin, str(src), "--json", "-", "--disable-color"],
                capture_output=True,
                text=True,
                timeout=timeout_s,
            )
        except subprocess.TimeoutExpired:
            raise
        findings: list[dict] = []
        if result.stdout:
            try:
                parsed = json.loads(result.stdout)
                raw_detectors = parsed.get("results", {}).get("detectors", [])
                for det in raw_detectors:
                    check = det.get("check", "")
                    # Only keep AC-related detectors for bounded output
                    if any(
                        k in check.lower()
                        for k in ("access", "authorization", "owner", "role", "initializer")
                    ):
                        findings.append(
                            {
                                "check": check,
                                "impact": det.get("impact", ""),
                                "confidence": det.get("confidence", ""),
                                "description": (det.get("description") or "").replace("\n", " ")[:200],
                            }
                        )
            except json.JSONDecodeError:
                pass
    facts = _regex_fallback(contract_source)
    facts.slither_findings = findings
    facts.tool = "slither" if findings or result.returncode == 0 else "regex"
    return facts


def _regex_fallback(contract_source: str) -> StaticFacts:
    state_change_markers = (
        "=",
        "push",
        "pop",
        "delete ",
        "transfer(",
        "call{",
        "selfdestruct",
    )
    visibility_keywords = ("external", "public", "internal", "private")
    known_non_mods = {
        "external", "public", "internal", "private", "view", "pure",
        "payable", "virtual", "override", "returns", "memory", "calldata",
    }
    functions: list[FunctionFact] = []
    for m in _FN_RE.finditer(contract_source):
        name = m.group("name")
        attrs = m.group("attrs") or ""
        vis = next((k for k in visibility_keywords if re.search(rf"\b{k}\b", attrs)), "public")
        tokens = re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", attrs)
        modifiers = [t for t in tokens if t not in known_non_mods and t != vis]
        # crude body slice for state-changing check
        body_start = m.end()
        depth = 1
        end = body_start
        while end < len(contract_source) and depth > 0:
            ch = contract_source[end]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
            end += 1
        body = contract_source[body_start:end]
        state_changing = any(marker in body for marker in state_change_markers)
        functions.append(
            FunctionFact(
                name=name, visibility=vis, modifiers=modifiers, state_changing=state_changing
            )
        )
    return StaticFacts(functions=functions, tool="regex")
