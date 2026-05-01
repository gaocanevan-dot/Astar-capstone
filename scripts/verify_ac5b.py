#!/usr/bin/env python3
"""Day-5 S5 — AC5b mechanical verifier.

AC5b (weakened from Architect's "used downstream"):
    "≥2 cases where `recall_self_lesson` was invoked AND the memory store
    returned at least one result (i.e. lesson_count > 0)."

This script reads `data/evaluation/react_sweep_run1.json` (or any
react-sweep aggregate) and emits PASS/FAIL based on the
`recall_self_lesson_nonempty` field per case.

Exit code: 0 if PASS, 1 if FAIL.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    REPO_ROOT = Path(__file__).resolve().parent.parent
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--sweep-json",
        default=str(REPO_ROOT / "data" / "evaluation" / "react_sweep_run1.json"),
    )
    ap.add_argument("--threshold", type=int, default=2, help="Min cases with non-empty recall.")
    args = ap.parse_args()

    p = Path(args.sweep_json)
    if not p.exists():
        print(f"ERROR: sweep file not found: {p}", file=sys.stderr)
        return 1

    data = json.loads(p.read_text(encoding="utf-8"))
    records = data.get("records") or data.get("cases") or []

    qualifying = []
    for r in records:
        n_recall_nonempty = int(r.get("recall_self_lesson_nonempty", 0) or 0)
        if n_recall_nonempty > 0:
            qualifying.append({
                "case_id": r.get("case_id"),
                "n_recall_nonempty": n_recall_nonempty,
            })

    n_qualify = len(qualifying)
    n_total = len(records)
    pass_ = n_qualify >= args.threshold

    print(f"[verify_ac5b] cases analyzed: {n_total}")
    print(f"[verify_ac5b] cases with recall_self_lesson returning >=1 result: {n_qualify}")
    print(f"[verify_ac5b] threshold: >={args.threshold}")
    for q in qualifying:
        print(f"  PASS {q['case_id']} (n_recall={q['n_recall_nonempty']})")

    if pass_:
        print(f"\n[verify_ac5b] ✅ PASS ({n_qualify} >= {args.threshold})")
        return 0
    print(f"\n[verify_ac5b] ❌ FAIL ({n_qualify} < {args.threshold})")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
