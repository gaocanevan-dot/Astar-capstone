#!/usr/bin/env python3
"""Day-1 T7 — Measure baseline `confirmed_vulnerability_rate` (cvr).

CVR formula (Critic-approved, vulnerable-only corpus, denominator excludes
compile-fails and skips):

    cvr = pass / (pass + fail_revert_ac + fail_error_runtime)

We post-classify the EXISTING `data/evaluation/full_pipeline_predictions.json`
on the smoke 10 case-IDs without spending any LLM tokens (zero-cost baseline).
For the legacy `fail_error` verdict label still present in those JSONs (run
before Day-1 T2 verdict split landed), we re-classify by inspecting the
`execution_trace` for compile-marker substrings (same logic as
`agent.adapters.foundry.classify_verdict`).

Output:
    data/evaluation/baseline_cvr.txt — single float on first line, then a
    structured caveat block.

**HONEST CAVEAT (write this in the output too):**
The current `full_pipeline_predictions.json` records replica-path passes
(GPT-fabricated self-contained PoCs), not validation against the original
contract. Until the Day-2 cascade router runs against `verifier_mode`
sources, this baseline is structurally inflated (cvr → 1.0 when all
attempts trivially pass on the replica). The AC11 ≥ baseline+0.10 target
must therefore be re-measured after Day-2/3 once the seam fires on the
original contract — at which point real `fail_revert_ac` and
`fail_error_runtime` cases will deflate the baseline to a meaningful
number.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Same compile markers used in agent.adapters.foundry.classify_verdict
COMPILE_MARKERS = (
    "compiler run failed",
    "parsererror",
    "identifiernotfound",
    "syntaxerror",
    "typeerror: ",
    "declarationerror",
    "unresolved import",
)


def _reclassify_legacy_fail_error(trace: str) -> str:
    """Map the deprecated `fail_error` label to either compile or runtime
    based on substring inspection of the execution trace.
    """
    tr = (trace or "").lower()
    if any(m in tr for m in COMPILE_MARKERS):
        return "fail_error_compile"
    return "fail_error_runtime"


def _normalize_verdict(row: dict) -> str:
    """Return the canonical verdict for a prediction row.

    Handles legacy `fail_error` label (pre-Day-1) by re-classifying via the
    `execution_trace` substring rule.
    """
    raw = row.get("execution_result") or ""
    if raw == "fail_error":
        return _reclassify_legacy_fail_error(row.get("execution_trace", ""))
    return raw


def _compute_cvr(rows: list[dict]) -> tuple[float, dict]:
    """Return (cvr, breakdown_counts). Skips and unknown verdicts excluded
    from the denominator.
    """
    counts = {
        "pass": 0,
        "fail_revert_ac": 0,
        "fail_error_compile": 0,
        "fail_error_runtime": 0,
        "skipped": 0,
        "other": 0,
    }
    for row in rows:
        v = _normalize_verdict(row)
        if v in counts:
            counts[v] += 1
        else:
            counts["other"] += 1
    denom = counts["pass"] + counts["fail_revert_ac"] + counts["fail_error_runtime"]
    cvr = (counts["pass"] / denom) if denom else float("nan")
    return cvr, counts


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--predictions",
        default=str(REPO_ROOT / "data" / "evaluation" / "full_pipeline_predictions.json"),
    )
    ap.add_argument(
        "--smoke-set",
        default=str(REPO_ROOT / "data" / "dataset" / "smoke_set.json"),
    )
    ap.add_argument(
        "--out",
        default=str(REPO_ROOT / "data" / "evaluation" / "baseline_cvr.txt"),
    )
    args = ap.parse_args()

    pred_path = Path(args.predictions)
    smoke_path = Path(args.smoke_set)
    if not pred_path.exists():
        print(f"ERROR: predictions not found: {pred_path}", file=sys.stderr)
        return 1
    if not smoke_path.exists():
        print(f"ERROR: smoke set not found: {smoke_path}", file=sys.stderr)
        return 1

    smoke = json.loads(smoke_path.read_text(encoding="utf-8"))
    smoke_ids = {c["id"] for c in smoke.get("cases", [])}

    preds_raw = json.loads(pred_path.read_text(encoding="utf-8"))
    # full_pipeline_predictions.json is a flat list of dicts.
    preds = preds_raw if isinstance(preds_raw, list) else preds_raw.get("rows", [])
    smoke_rows = [r for r in preds if r.get("case_id") in smoke_ids]

    print(
        f"Smoke set has {len(smoke_ids)} ids; matched {len(smoke_rows)} in {pred_path.name}"
    )
    missing = smoke_ids - {r.get("case_id") for r in smoke_rows}
    if missing:
        print(f"WARN: missing prediction rows for: {sorted(missing)}")

    cvr, counts = _compute_cvr(smoke_rows)
    print(f"baseline_cvr = {cvr:.4f}")
    print(f"breakdown    = {json.dumps(counts)}")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    import math

    lines: list[str] = []
    if math.isnan(cvr):
        # Day-2 consumer contract: NaN means "no baseline available; denominator
        # was 0 (smoke verdicts were all skipped or compile-fail)". Consumers
        # MUST treat absence-of-comparable-baseline distinctly — comparisons
        # against NaN silently return False which would mask Day-2 lifts.
        # We emit `nan denom=0` so downstream parsers can detect this cleanly.
        denom = (
            counts["pass"] + counts["fail_revert_ac"] + counts["fail_error_runtime"]
        )
        lines.append(f"nan denom={denom}")
    else:
        lines.append(f"{cvr:.6f}")
    lines.append("")
    lines.append("# HONEST CAVEAT — pre-Day-2 baseline")
    lines.append("# Measured from data/evaluation/full_pipeline_predictions.json,")
    lines.append("# which records REPLICA-PATH passes (GPT-fabricated self-contained")
    lines.append("# PoCs), not validation against the original contract.")
    lines.append("# The Day-2 cascade router will re-run with verifier_mode-driven")
    lines.append("# source-write seam, at which point real fail_revert_ac and")
    lines.append("# fail_error_runtime cases will appear and deflate the baseline to")
    lines.append("# a meaningful number. AC11's `≥ baseline + 0.10` target MUST be")
    lines.append("# re-measured at that point.")
    lines.append("#")
    lines.append("# Smoke 10 IDs (this baseline):")
    for cid in sorted(smoke_ids):
        lines.append(f"#   {cid}")
    lines.append("#")
    lines.append("# Verdict breakdown on the smoke 10:")
    for k, v in counts.items():
        lines.append(f"#   {k}: {v}")
    lines.append("#")
    lines.append(
        f"# Denominator (pass + fail_revert_ac + fail_error_runtime): "
        f"{counts['pass'] + counts['fail_revert_ac'] + counts['fail_error_runtime']}"
    )
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"Wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
