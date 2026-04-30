#!/usr/bin/env python3
"""Day-1 T6 — auto-select a 10-case smoke subset from eval_set.json.

The user picked Option (C) "auto-heuristic" for the smoke set: deterministic,
re-runnable, no manual review burden. The plan's stratification rules:

  1. `buildable=True`
  2. severity coverage: ≥1 high AND ≥1 medium
  3. `verifier_mode` coverage: ≥2 distinct tags (relaxed from the strict-mode
     ≥3 because the corpus has no `oz_vendored` tag candidates without manual
     library work — DEF2)

Each picked case is tagged with a `verifier_mode` field via an import-sniff
heuristic:

  - `replica_only` if the stored `contract_source` references either:
      * sibling-relative imports (`import "../...";`)  → unresolvable in our
        single-file snapshot
      * external libraries (`@openzeppelin/`, `solady/`, `@account-abstraction/`,
        `forge-std/`, `ds-test/`)  → won't compile without remappings
  - `original` otherwise (small or fully self-contained sources)

If the heuristic cannot satisfy the constraints, raise `SmokeSetInfeasible`
with diagnostics.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent

EXTERNAL_LIB_PREFIXES = (
    "@openzeppelin/",
    "@oz/",
    "solady/",
    "@account-abstraction/",
    "@uniswap/",
    "@chainlink/",
    "ds-test/",
)

_SIBLING_IMPORT_RE = re.compile(r'import\s+(?:[^"\']*from\s+)?["\']\.\./[^"\']+["\']')
_NAMED_IMPORT_RE = re.compile(r'import\s+(?:[^"\']*from\s+)?["\']([^"\']+)["\']')


class SmokeSetInfeasible(RuntimeError):
    """Raised when auto-heuristic cannot satisfy the smoke-set constraints."""


def _sniff_verifier_mode(contract_source: str) -> str:
    """Return `replica_only` if the source references unresolvable imports;
    `original` otherwise. (No `oz_vendored` candidate without DEF2 work.)
    """
    if not contract_source:
        return "replica_only"
    if _SIBLING_IMPORT_RE.search(contract_source):
        return "replica_only"
    for m in _NAMED_IMPORT_RE.finditer(contract_source):
        ref = m.group(1)
        if any(ref.startswith(prefix) for prefix in EXTERNAL_LIB_PREFIXES):
            return "replica_only"
    return "original"


# Number of "anchor" picks we admit before requiring strict coverage gain.
# These small-LOC seeds bias the smoke set toward cases that are likely to
# compile cleanly in `original` mode — the primary debug-cost lever.
_ANCHOR_SEEDS = 4


def _stratified_pick(
    candidates: list[dict[str, Any]], n: int = 10
) -> list[dict[str, Any]]:
    """Greedy stratified selection: prefer mixing severity AND verifier_mode.

    Strategy:
      1. Sort by `len(contract_source)` ascending — small files compile better
         in `original` mode (and run faster).
      2. Walk in order; admit a case if it strictly improves coverage. The
         first `_ANCHOR_SEEDS` picks are admitted unconditionally to anchor
         the smoke run on cases likely to compile.
      3. Stop when we have N cases AND coverage constraints met.
      4. If at end we still don't have N, fill with any remaining buildable.
    """
    by_loc = sorted(candidates, key=lambda c: len(c.get("contract_source", "")))
    picked: list[dict[str, Any]] = []
    seen_severities: set[str] = set()
    seen_modes: set[str] = set()

    # Pass 1: anchor + strict-coverage-gain.
    for case in by_loc:
        if len(picked) >= n:
            break
        sev = case["severity"]
        mode = case["verifier_mode"]
        improves = (sev not in seen_severities) or (mode not in seen_modes)
        if improves or len(picked) < _ANCHOR_SEEDS:
            picked.append(case)
            seen_severities.add(sev)
            seen_modes.add(mode)

    # Pass 2: backfill to N from remaining buildable cases (smallest LOC first).
    if len(picked) < n:
        picked_ids = {c["id"] for c in picked}
        for case in by_loc:
            if len(picked) >= n:
                break
            if case["id"] in picked_ids:
                continue
            picked.append(case)

    return picked[:n]


def _validate(picked: list[dict[str, Any]]) -> None:
    if len(picked) != 10:
        raise SmokeSetInfeasible(
            f"need 10 cases; got {len(picked)}. Buildable corpus too small?"
        )
    severities = {c["severity"] for c in picked}
    if "high" not in severities:
        raise SmokeSetInfeasible(
            f"no high-severity case in pick; severities seen: {severities}"
        )
    if "medium" not in severities:
        raise SmokeSetInfeasible(
            f"no medium-severity case in pick; severities seen: {severities}"
        )
    modes = {c["verifier_mode"] for c in picked}
    if len(modes) < 2:
        raise SmokeSetInfeasible(
            f"need ≥2 distinct verifier_mode tags (auto-mode relaxed from strict ≥3); "
            f"got: {modes}"
        )


def _summary(picked: list[dict[str, Any]]) -> dict[str, Any]:
    sev_counts: dict[str, int] = {}
    mode_counts: dict[str, int] = {}
    for c in picked:
        sev_counts[c["severity"]] = sev_counts.get(c["severity"], 0) + 1
        mode_counts[c["verifier_mode"]] = mode_counts.get(c["verifier_mode"], 0) + 1
    return {
        "n": len(picked),
        "severity": sev_counts,
        "verifier_mode": mode_counts,
        "ids": [c["id"] for c in picked],
        "deviation_from_strict_plan": (
            "auto-mode: ≥2 verifier_mode tags accepted (strict plan: ≥3). "
            "`oz_vendored` tag candidates require manual library work (DEF2)."
        ),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--eval-set",
        default=str(REPO_ROOT / "data" / "dataset" / "eval_set.json"),
        help="Source eval_set.json",
    )
    ap.add_argument(
        "--out",
        default=str(REPO_ROOT / "data" / "dataset" / "smoke_set.json"),
        help="Output smoke_set.json",
    )
    ap.add_argument("--n", type=int, default=10, help="Number of cases to pick")
    args = ap.parse_args()

    eval_path = Path(args.eval_set)
    if not eval_path.exists():
        print(f"ERROR: eval set not found: {eval_path}", file=sys.stderr)
        return 1

    data = json.loads(eval_path.read_text(encoding="utf-8"))
    cases: list[dict[str, Any]] = list(data.get("cases", []))
    print(f"Loaded {len(cases)} cases from {eval_path}")

    candidates: list[dict[str, Any]] = []
    for case in cases:
        if not case.get("buildable"):
            continue
        case_copy = dict(case)
        case_copy["verifier_mode"] = _sniff_verifier_mode(
            case.get("contract_source", "")
        )
        candidates.append(case_copy)
    print(f"Buildable candidates: {len(candidates)}")

    picked = _stratified_pick(candidates, n=args.n)
    _validate(picked)

    out_payload = {
        "cases": picked,
        "_smoke_meta": _summary(picked),
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(out_payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(f"Wrote {out_path}")
    print(json.dumps(out_payload["_smoke_meta"], indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
