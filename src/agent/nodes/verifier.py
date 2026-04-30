"""Verifier node — run forge test on the builder's PoC, classify verdict,
update state.

Returns a dict with execution_result / execution_trace / error_summary so the
graph router can decide: report / safe / refine.
"""

from __future__ import annotations

import time

from agent.adapters.foundry import run_forge_test


def verify(
    contract_source: str,
    contract_name: str,
    poc_code: str,
    install_forge_std: bool = True,
    timeout_s: int = 180,
    verifier_mode: str | None = None,
) -> dict:
    """Return:
        {
            "execution_result": Verdict,
            "execution_trace": str (stdout+stderr, truncated),
            "error_summary": str (one-line for retry prompt),
            "wall_clock_s": float,
            "return_code": int,
        }
    """
    if not poc_code.strip():
        return {
            "execution_result": "fail_error_runtime",
            "execution_trace": "",
            "error_summary": "empty poc_code",
            "wall_clock_s": 0.0,
            "return_code": -1,
        }

    t0 = time.time()
    result = run_forge_test(
        contract_source=contract_source,
        contract_name=contract_name,
        poc_code=poc_code,
        install_forge_std=install_forge_std,
        timeout_s=timeout_s,
        verifier_mode=verifier_mode,
    )

    stdout = result.stdout or ""
    stderr = result.stderr or ""
    trace = (stdout + "\n" + stderr)[-4000:]  # bound state size

    return {
        "execution_result": result.verdict,
        "execution_trace": trace,
        "error_summary": result.error_summary,
        "wall_clock_s": round(time.time() - t0, 2),
        "return_code": result.return_code,
    }
