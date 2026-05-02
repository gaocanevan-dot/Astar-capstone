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
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HOLDOUT_CSV = REPO / "data" / "dataset" / "c5_access_control_dataset_remaining33.csv"
SOURCE_MAP_CSV = REPO / "data" / "dataset" / "source_map_remaining33.csv"
ARCHIVE_PREFIX = REPO / "data" / "dataset" / "Repair-Access-Control-C-main" / "Repair-Access-Control-C-main"
RULE_FILE = REPO / ".omc" / "plans" / "day-6-blind-screen-rule.md"
OUT_MD = REPO / "data" / "evaluation" / "day6_buildability.md"

# Reuse foundry adapter primitives to keep pragma + cache logic consistent
sys.path.insert(0, str(REPO / "src"))
from agent.adapters.foundry import (  # noqa: E402
    _ensure_forge_std_cache, _resolve_pragma, resolve_forge,
)

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


_SOURCE_MAP_CACHE: dict[str, str] | None = None


def _load_source_map() -> dict[str, str]:
    """ACF-id -> archive-relative contract path (e.g. data/contracts/cve/B2X.sol)."""
    global _SOURCE_MAP_CACHE
    if _SOURCE_MAP_CACHE is None:
        _SOURCE_MAP_CACHE = {}
        with SOURCE_MAP_CSV.open("r", encoding="utf-8-sig") as fp:
            for row in csv.DictReader(fp):
                _SOURCE_MAP_CACHE[row["incident_id"]] = row["matched_solidity_file"]
    return _SOURCE_MAP_CACHE


def _resolve_contract_path(case_id: str) -> Path | None:
    """Map ACF id -> absolute path under archive prefix. None if unmappable."""
    rel = _load_source_map().get(case_id)
    if not rel:
        return None
    full = ARCHIVE_PREFIX / rel
    return full if full.exists() else None


def try_build_one(case_id: str, forge: str, build_timeout_s: int = 60) -> bool:
    """Attempt `forge build` on one case's contract source. Returns True iff exit=0.

    Per blind-screen rule, this function does NOT log which case attempted
    or what error it produced — caller aggregates count only.

    Strategy:
      1. Resolve source path via source_map_remaining33.csv + archive prefix.
      2. Apply pragma policy (`_resolve_pragma`) so 0.7.x sources still compile
         under solc 0.8 by being treated as `pre_08_force_replica` (skip build,
         since they cannot bridge — return False).
      3. Write contract to temp foundry workspace + minimal foundry.toml.
      4. Copy forge-std cache into workspace lib/ (some contracts import it).
      5. Run `forge build` with auto_detect_solc enabled.
    """
    src_path = _resolve_contract_path(case_id)
    if src_path is None:
        return False  # source missing -> not buildable

    try:
        contract_source = src_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False

    pragma_directive, pragma_hint = _resolve_pragma(contract_source)
    if pragma_hint == "pre_08_force_replica":
        # Pre-0.8 contracts can't be compiled standalone with our solc setup
        # Treat as not-buildable for Day-6 RAG purposes (PoC harness can't
        # use them either, so they're not viable holdout cases anyway).
        return False

    cached_lib, cache_status = _ensure_forge_std_cache(forge)
    if cache_status == "install_failed":
        return False  # treat as not buildable; aggregate count is what matters

    with tempfile.TemporaryDirectory(prefix="day6_blind_") as tmpdir:
        proj = Path(tmpdir)
        (proj / "src").mkdir()
        (proj / "lib").mkdir()
        # Use generic name to avoid case-id leak via filesystem inspection
        # (defensive: even if the build artifact dir survives, no per-id signal).
        source_to_write = (
            pragma_directive + "\n" + contract_source
            if pragma_hint == "no_pragma_force_0820"
            else contract_source
        )
        (proj / "src" / "Candidate.sol").write_text(source_to_write, encoding="utf-8")
        (proj / "foundry.toml").write_text(
            "[profile.default]\n"
            'src = "src"\n'
            'out = "out"\n'
            'libs = ["lib"]\n'
            "auto_detect_solc = true\n",
            encoding="utf-8",
        )
        try:
            shutil.copytree(cached_lib, proj / "lib" / "forge-std")
        except OSError:
            return False

        try:
            result = subprocess.run(
                [forge, "build"],
                cwd=str(proj),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=build_timeout_s,
            )
        except (subprocess.TimeoutExpired, OSError):
            return False
        return result.returncode == 0


def main() -> int:
    if not RULE_FILE.exists():
        print(f"ERROR: blind-screen-rule.md not found at {RULE_FILE}", file=sys.stderr)
        print("       R2 condition: rule file must be committed BEFORE this run.", file=sys.stderr)
        return 1

    ids = load_holdout_ids()
    if len(ids) != 23:
        print(f"ERROR: expected 23 holdout IDs, got {len(ids)}", file=sys.stderr)
        return 1

    forge = resolve_forge()
    if forge is None:
        print("ERROR: forge executable not found on PATH / FOUNDRY_PATH", file=sys.stderr)
        return 1
    if not ARCHIVE_PREFIX.exists():
        print(f"ERROR: contract archive not found at {ARCHIVE_PREFIX}", file=sys.stderr)
        return 1

    print(f"Blind-screening {len(ids)} candidate cases for forge buildability...")
    print(f"(Forge: {forge})")
    print("(Per blind rule: only the aggregate count will be logged.)")
    print()

    started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    buildable = 0
    for i, cid in enumerate(ids, 1):
        # Per blind rule: print only progress dot, never the case id alongside result.
        ok = try_build_one(cid, forge)
        sys.stdout.write("." if ok else "x")
        sys.stdout.flush()
        if ok:
            buildable += 1
    print()  # newline after progress

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
