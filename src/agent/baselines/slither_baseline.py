"""Slither static-analysis baseline.

Runs `slither --json` on each contract; if any access-control-category
detector fires, the case is flagged. Extracts function names from the
detectors' element lists for function-level comparison.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from agent.baselines import PredictionRecord


# Detectors we consider as "access-control" for the function-level match.
AC_DETECTOR_KEYWORDS = (
    "access",
    "authorization",
    "owner",
    "role",
    "initializer",
    "privileg",
)


def _resolve_slither() -> str | None:
    repo_root = Path(__file__).resolve().parents[3]
    venv = repo_root / "venv" / "Scripts" / ("slither.exe" if os.name == "nt" else "slither")
    if venv.exists():
        return str(venv)
    return shutil.which("slither")


def evaluate(case) -> PredictionRecord:
    """Evaluate one case via Slither. Always returns a PredictionRecord
    (no exceptions bubble)."""
    slither = _resolve_slither()
    t0 = time.time()
    if slither is None:
        return PredictionRecord(
            case_id=case.id,
            contract_name=case.contract_name,
            ground_truth_function=case.vulnerable_function or "",
            flagged=False,
            flagged_functions=[],
            predicted_function="",
            error="slither executable not found",
            method="slither",
            wall_clock_seconds=time.time() - t0,
        )

    if not (case.contract_source or "").strip():
        return PredictionRecord(
            case_id=case.id,
            contract_name=case.contract_name,
            ground_truth_function=case.vulnerable_function or "",
            flagged=False,
            flagged_functions=[],
            predicted_function="",
            error="empty contract_source",
            method="slither",
            wall_clock_seconds=time.time() - t0,
        )

    with tempfile.TemporaryDirectory(prefix="agent_slither_bl_") as tmp:
        src_path = Path(tmp) / f"{case.contract_name or 'Target'}.sol"
        src_path.write_text(case.contract_source, encoding="utf-8")
        try:
            proc = subprocess.run(
                [slither, str(src_path), "--json", "-", "--disable-color"],
                capture_output=True,
                text=True,
                timeout=90,
            )
        except subprocess.TimeoutExpired:
            return PredictionRecord(
                case_id=case.id,
                contract_name=case.contract_name,
                ground_truth_function=case.vulnerable_function or "",
                flagged=False,
                flagged_functions=[],
                predicted_function="",
                error="slither timeout",
                method="slither",
                wall_clock_seconds=time.time() - t0,
            )

    flagged = False
    flagged_functions: list[str] = []
    error = ""
    stdout = proc.stdout or ""
    if stdout:
        try:
            parsed = json.loads(stdout)
            detectors = parsed.get("results", {}).get("detectors", []) or []
            for det in detectors:
                check = (det.get("check") or "").lower()
                if not any(k in check for k in AC_DETECTOR_KEYWORDS):
                    continue
                flagged = True
                # Element list contains the affected functions/contracts
                for el in det.get("elements", []) or []:
                    if (el.get("type") or "") == "function":
                        name = el.get("name")
                        if name and name not in flagged_functions:
                            flagged_functions.append(name)
        except json.JSONDecodeError as e:
            error = f"slither JSON parse failed: {e}"

    if not flagged and proc.returncode != 0 and not error:
        error = (proc.stderr or "").splitlines()[0][:200] if proc.stderr else f"slither rc={proc.returncode}"

    return PredictionRecord(
        case_id=case.id,
        contract_name=case.contract_name,
        ground_truth_function=case.vulnerable_function or "",
        flagged=flagged,
        flagged_functions=flagged_functions,
        predicted_function=flagged_functions[0] if flagged_functions else "",
        error=error,
        method="slither",
        wall_clock_seconds=time.time() - t0,
        raw_output=stdout[:2000],
    )
