#!/usr/bin/env python3
"""Day-6 Step 0a — BLIND forge buildability pre-screen.

Per Architect closure (v5 → v6) and Critic minor finding:
  - Operator records ONLY the buildable count integer.
  - NO per-ID inspection logged.
  - NO per-case toolchain fixup.
  - Failure mode: <18 buildable → escalate to Path B (Step 0c spot-check),
    do NOT shrink n further.

Usage:
  python scripts/day6_blind_screen.py

Output:
  data/evaluation/day6_buildability.md  (count-only artifact)
  Exit code: 0 if buildable >= 18, 2 if <18 (path B trigger), 1 on harness error.

Pre-condition: `.omc/plans/day-6-blind-screen-rule.md` MUST be committed
to git BEFORE this script runs (R2 hash gate). The script asserts the
rule file exists; it does NOT verify the git state because hooks vary
across operator setups — operator is responsible for the commit.
"""
from __future__ import annotations

import csv
import json
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HOLDOUT_CSV = REPO / "data" / "dataset" / "c5_access_control_dataset_remaining33.csv"
RULE_FILE = REPO / ".omc" / "plans" / "day-6-blind-screen-rule.md"
OUT_MD = REPO / "data" / "evaluation" / "day6_buildability.md"

# 23 clean unused ACF IDs (ACF-086..ACF-118 minus the 10 used in Day-5b)
USED_IN_DAY5B = {"ACF-087", "ACF-091", "ACF-092", "ACF-093", "ACF-101",
                 "ACF-102", "ACF-103", "ACF-106", "ACF-109", "ACF-114"}

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def load_holdout_ids() -> list[str]:
    """Return the 23 candidate ACF IDs (ACF-086..118 minus Day-5b 10)."""
    ids = []
    with HOLDOUT_CSV.open("r", encoding="utf-8-sig") as fp:
        for row in csv.DictReader(fp):
            iid = row["incident_id"]
            if iid not in USED_IN_DAY5B:
                ids.append(iid)
    return ids


def try_build_one(case_id: str) -> bool:
    """Attempt forge build for one case. Returns True iff exit=0.

    Implementation note: this function intentionally does NOT log which
    case it attempted, beyond returning a bool. Per blind-screen rule,
    aggregation is count-only.

    The build harness is the same one used by Day-5b react agent runs.
    Adapt this stub to whatever the project's `forge build` invocation
    is (foundry workspace path, contract file, etc.). For now this is
    a placeholder that the operator wires up to the real harness.
    """
    # PLACEHOLDER: replace with actual forge build invocation.
    # Real implementation should:
    #   1. Locate contract source file via source_map_remaining33.csv
    #   2. Run `forge build --root <project_root> 2>&1`
    #   3. Return True iff exit code 0
    # For the kickoff-prep phase we simply return True for all cases as
    # a structural check; operator MUST replace this before Step 0a real run.
    return True


def main() -> int:
    if not RULE_FILE.exists():
        print(f"ERROR: blind-screen-rule.md not found at {RULE_FILE}", file=sys.stderr)
        print("       R2 condition: rule file must be committed BEFORE this run.", file=sys.stderr)
        return 1

    ids = load_holdout_ids()
    if len(ids) != 23:
        print(f"ERROR: expected 23 holdout IDs, got {len(ids)}", file=sys.stderr)
        return 1

    print(f"Blind-screening {len(ids)} candidate cases for forge buildability...")
    print("(Per blind rule: only the aggregate count will be logged.)")

    started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    buildable = 0
    for cid in ids:
        if try_build_one(cid):
            buildable += 1

    finished_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "screened_at_start": started_at,
        "screened_at_finish": finished_at,
        "candidates_total": len(ids),
        "buildable_count": buildable,
    }
    with OUT_MD.open("w", encoding="utf-8") as fp:
        fp.write("# Day-6 Step 0a — Blind Buildability Pre-Screen\n\n")
        fp.write("Per blind-screen rule: count-only artifact. Per-ID results NOT logged.\n\n")
        fp.write("## Result\n\n")
        fp.write("```json\n")
        fp.write(json.dumps(record, indent=2))
        fp.write("\n```\n\n")
        fp.write("## Preliminary n routing (PENDING AC10d at Step 0b)\n\n")
        fp.write("The final routing decision is made at Step 1 (freeze holdout)\n")
        fp.write("after Step 0b reports AC10d Jaccard-survivor count. Effective\n")
        fp.write("candidate count = min(buildable_count, ac10d_survivor_count).\n\n")
        if buildable >= 21:
            fp.write(f"buildable={buildable} >= 21 → preliminary **n=18 routing**\n")
            decision = "n18-preliminary"
        elif buildable >= 18:
            fp.write(f"buildable={buildable} in [18,20] → preliminary **n=15 routing**\n")
            decision = "n15-preliminary"
        else:
            fp.write(f"buildable={buildable} < 18 → **PATH B ESCALATION** (Step 0c spot-check)\n")
            decision = "pathB"
        fp.write(f"\nPreliminary decision: `{decision}`\n")

    print(json.dumps(record, indent=2))
    print(f"\nWrote {OUT_MD}")
    print(f"Decision: {decision}")
    return 0 if buildable >= 18 else 2


if __name__ == "__main__":
    raise SystemExit(main())
