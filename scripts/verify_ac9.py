#!/usr/bin/env python3
"""Day-5b AC9 mechanical verifier (Architect R5 + Critic-pruned).

AC9: cascade should fire EXACTLY when needed.

Mechanical definition (no human judgment):
    For each case in a sweep, "cascade was needed" iff the trace shows
    at least one `run_forge` call returning a `fail_*` verdict before
    any terminal tool. "Cascade fired" iff `cascade_invocations >= 1`.

We compute three numbers per arm:
  - cases_needing_cascade  — first run_forge returned fail_*
  - cases_with_cascade     — cascade_invocations > 0
  - cascade_precision      — (needed AND fired) / fired
  - cascade_recall         — (needed AND fired) / needed

For 5-baseline arm, cascade_invocations is always 0 (tool not exposed).
For 5b-tool, cascade is agent's choice (low usage expected per AC5b precedent).
For 5b-mandate, cascade is forced via prompt + system intercept (high usage).

Exit code: 0 if AC9 thresholds met, 1 otherwise.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def _classify_case(rec: dict, mode: str) -> dict:
    """Determine if cascade was needed AND fired for one case.

    "Needed" uses `first_forge_verdict` (the verdict on the FIRST run_forge
    call, never overwritten) — this is the question 'did the original target
    fail?', not 'did the case end on a fail?'.
    """
    first_forge = rec.get("first_forge_verdict", "") or rec.get("forge_verdict", "") or ""
    cascade_n = int(rec.get("cascade_invocations", 0) or 0)
    needed = first_forge.startswith("fail")
    fired = cascade_n > 0
    return {
        "case_id": rec.get("case_id", "?"),
        "needed": needed,
        "fired": fired,
        "system_forced": bool(rec.get("cascade_was_system_forced")),
        "first_forge_verdict": first_forge,
        "final_forge_verdict": rec.get("forge_verdict", "") or "",
        "cascade_invocations": cascade_n,
    }


def main() -> int:
    REPO_ROOT = Path(__file__).resolve().parent.parent
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--sweep-json",
        required=True,
        help="Per-arm sweep JSON (e.g. data/evaluation/react_5b_5b-mandate.json)",
    )
    ap.add_argument(
        "--mode",
        default="auto",
        help="Mode of the sweep (auto-infer from filename if 'auto')",
    )
    ap.add_argument(
        "--min-precision",
        type=float,
        default=0.5,
        help="Minimum precision (cascade fired AND needed / cascade fired). Default 0.5.",
    )
    args = ap.parse_args()

    sweep_path = Path(args.sweep_json)
    if not sweep_path.exists():
        print(f"ERROR: sweep file not found: {sweep_path}", file=sys.stderr)
        return 1
    sweep = json.loads(sweep_path.read_text(encoding="utf-8"))
    records = sweep.get("records") or []
    if not records:
        print("ERROR: empty records", file=sys.stderr)
        return 1

    mode = args.mode
    if mode == "auto":
        # Infer from filename: react_5b_<mode>.json
        stem = sweep_path.stem
        if "5b-mandate" in stem:
            mode = "5b-mandate"
        elif "5b-tool" in stem:
            mode = "5b-tool"
        elif "5-baseline" in stem or "agent-full" in stem:
            mode = "5-baseline"
        else:
            mode = "default"

    classified = [_classify_case(r, mode) for r in records]
    n_total = len(classified)
    n_needed = sum(1 for c in classified if c["needed"])
    n_fired = sum(1 for c in classified if c["fired"])
    n_needed_and_fired = sum(1 for c in classified if c["needed"] and c["fired"])
    n_system_forced = sum(1 for c in classified if c["system_forced"])

    precision = (n_needed_and_fired / n_fired) if n_fired else 0.0
    recall = (n_needed_and_fired / n_needed) if n_needed else 0.0

    print(f"=== AC9 mechanical verifier — mode={mode} ===")
    print(f"Cases analyzed: {n_total}")
    print(f"Cases needing cascade (first forge=fail): {n_needed}")
    print(f"Cases with cascade fired (invocations≥1): {n_fired}")
    print(f"  of which system-forced: {n_system_forced}")
    print(f"Needed AND fired: {n_needed_and_fired}")
    print()
    print(f"Cascade precision (fired→needed): {precision:.2f}")
    print(f"Cascade recall    (needed→fired): {recall:.2f}")
    print()

    # Per-case detail
    print("Per-case:")
    for c in classified:
        marker = "✅" if (c["needed"] and c["fired"]) else (
            "—" if (not c["needed"] and not c["fired"]) else (
                "⚠️ over-fire" if (c["fired"] and not c["needed"]) else "❌ under-fire"
            )
        )
        sys_tag = " (sys)" if c["system_forced"] else ""
        print(f"  {marker} {c['case_id']}: first_verdict={c['first_forge_verdict'] or '-'} "
              f"cascade_n={c['cascade_invocations']}{sys_tag}")

    print()
    if mode == "5-baseline":
        # Baseline arm: no cascade tool, no firing expected
        if n_fired == 0:
            print("[ac9] ✅ baseline arm: 0 cascade invocations (expected)")
            return 0
        print("[ac9] ❌ baseline arm: cascade fired but tool not exposed — bug")
        return 1

    # 5b-tool / 5b-mandate: at least precision threshold required
    if precision >= args.min_precision and n_fired > 0:
        print(f"[ac9] ✅ {mode}: precision {precision:.2f} ≥ {args.min_precision}")
        return 0
    if n_fired == 0:
        print(f"[ac9] ⚠️ {mode}: cascade tool exposed but agent never used it (AC5b-shape recurrence)")
        return 1
    print(f"[ac9] ❌ {mode}: precision {precision:.2f} < {args.min_precision}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
