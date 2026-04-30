#!/usr/bin/env python3
"""Day-3 fix — rebuild smoke set from the C5/Repair-Access-Control corpus.

The original `build_smoke_set.py` picked from `eval_set.json`, which the
Day-3 dry-run revealed is dominated by FRAGMENT-shaped sources (30/42 have
no `contract X { ... }` wrapper). The C5 dataset under
`data/dataset/Repair-Access-Control-C-main/.../data/contracts/defi_hack_ac/`
provides 11 COMPLETE Solidity files (+ 4 fragments we filter out).

Pipeline:
  1. Load `data/dataset/source_map_remaining33.csv` (33 incidents → file path)
  2. Load `data/dataset/c5_access_control_dataset_remaining33.csv` for severity
     and issue metadata
  3. Filter out incidents whose mapped file is a fragment (no pragma OR no
     contract declaration)
  4. Extract `vulnerable_function` name from the `attack_surface` field
  5. Stratify-pick 10 incidents diverse on (project_name, issue_subtype)
  6. Write `data/dataset/smoke_set.json` with FULL source content; tag every
     case `verifier_mode="original"` since these compile standalone.
"""
from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATASET_DIR = REPO_ROOT / "data" / "dataset"
REPAIR_ROOT = (
    DATASET_DIR
    / "Repair-Access-Control-C-main"
    / "Repair-Access-Control-C-main"
)

SOURCE_MAP_CSV = DATASET_DIR / "source_map_remaining33.csv"
C5_DATASET_CSV = DATASET_DIR / "c5_access_control_dataset_remaining33.csv"
OUT_PATH = DATASET_DIR / "smoke_set.json"
N_PICK = 10

_RE_PRAGMA = re.compile(r"^\s*pragma\s+solidity", re.MULTILINE)
_RE_CONTRACT = re.compile(
    r"\b(?:contract|library|interface|abstract\s+contract)\s+\w+"
)
_RE_FN_NAME = re.compile(r"^\s*([A-Za-z_]\w*)\s*\(")


def _is_complete(source: str) -> bool:
    """Has a Solidity pragma AND at least one contract/library/interface decl."""
    return bool(_RE_PRAGMA.search(source)) and bool(_RE_CONTRACT.search(source))


def _extract_fn_name(attack_surface: str) -> str:
    """Get function name from `attack_surface` field, e.g.
    'setToken(address _addr) public' → 'setToken'.
    """
    m = _RE_FN_NAME.match((attack_surface or "").strip())
    return m.group(1) if m else ""


def _read_csv_dict(path: Path) -> list[dict]:
    rows: list[dict] = []
    with open(path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append({k: (v or "") for k, v in r.items()})
    return rows


def _load_full_source(matched_solidity_file: str) -> str | None:
    """Resolve `matched_solidity_file` against REPAIR_ROOT. Return None if missing."""
    if not matched_solidity_file:
        return None
    path = REPAIR_ROOT / matched_solidity_file
    if not path.exists():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        try:
            return path.read_text(encoding="latin-1")
        except Exception:
            return None


def _stratified_pick(candidates: list[dict], n: int) -> list[dict]:
    """Greedy stratified pick: maximize coverage on (project_name, issue_subtype).

    1. Sort candidates by source length DESCENDING — full contracts first.
    2. Walk in order; admit if it improves project OR subtype coverage.
    3. After coverage saturated, fill with longest-source remainders.
    """
    by_size = sorted(
        candidates, key=lambda c: -len(c.get("contract_source", ""))
    )
    picked: list[dict] = []
    seen_projects: set[str] = set()
    seen_subtypes: set[str] = set()

    for c in by_size:
        if len(picked) >= n:
            break
        improves = (
            c["project_name"] not in seen_projects
            or c["issue_subtype"] not in seen_subtypes
        )
        if improves or len(picked) < 4:
            picked.append(c)
            seen_projects.add(c["project_name"])
            seen_subtypes.add(c["issue_subtype"])

    if len(picked) < n:
        picked_ids = {c["id"] for c in picked}
        for c in by_size:
            if len(picked) >= n:
                break
            if c["id"] in picked_ids:
                continue
            picked.append(c)

    return picked[:n]


def main() -> int:
    if not SOURCE_MAP_CSV.exists():
        print(f"ERROR: source_map missing: {SOURCE_MAP_CSV}", file=sys.stderr)
        return 1
    if not C5_DATASET_CSV.exists():
        print(f"ERROR: c5 dataset missing: {C5_DATASET_CSV}", file=sys.stderr)
        return 1

    source_map = _read_csv_dict(SOURCE_MAP_CSV)
    c5_rows = _read_csv_dict(C5_DATASET_CSV)
    c5_by_incident: dict[str, dict] = {
        (r.get("incident_id") or "").strip(): r for r in c5_rows
    }
    print(
        f"Loaded {len(source_map)} source-map rows, "
        f"{len(c5_rows)} c5 rows ({len(c5_by_incident)} unique incidents)."
    )

    candidates: list[dict] = []
    skipped_fragment: list[str] = []
    skipped_missing: list[str] = []

    for sm_row in source_map:
        incident_id = (sm_row.get("incident_id") or "").strip()
        matched_file = (sm_row.get("matched_solidity_file") or "").strip()
        attack_surface = (sm_row.get("attack_surface") or "").strip()

        full_source = _load_full_source(matched_file)
        if full_source is None:
            skipped_missing.append(incident_id)
            continue
        if not _is_complete(full_source):
            skipped_fragment.append(incident_id)
            continue

        c5 = c5_by_incident.get(incident_id, {})
        contract_name = Path(matched_file).stem
        fn_name = _extract_fn_name(attack_surface)

        # Map c5 priority_type → severity. Default high (most are "High").
        priority = (c5.get("priority_type") or "").strip().lower()
        severity = "high" if priority == "high" else (
            "medium" if priority == "medium" else "high"
        )

        candidates.append(
            {
                "id": incident_id,
                "project_name": (sm_row.get("project_name") or "").strip(),
                "contract_name": contract_name,
                "vulnerable_function": fn_name,
                "vulnerability_type": "access_control",
                "severity": severity,
                "issue_category": (c5.get("issue_category") or "").strip(),
                "issue_subtype": (c5.get("issue_subtype") or "").strip(),
                "attack_surface": attack_surface,
                "source": (c5.get("source") or "").strip(),
                "ground_truth_label": "vulnerable",
                "buildable": True,
                "verifier_mode": "original",  # all picked files are complete
                "matched_solidity_file": matched_file,
                "matched_start_line_est": sm_row.get("matched_start_line_est", ""),
                "matched_end_line_est": sm_row.get("matched_end_line_est", ""),
                "vulnerable_code_snippet": (c5.get("vulnerable_code") or "").strip(),
                "contract_source": full_source,
                "metadata": {
                    "year": (c5.get("year") or "").strip(),
                    "reference": (c5.get("reference") or "").strip(),
                    "root_cause": (c5.get("root_cause") or "").strip(),
                    "impact": (c5.get("impact") or "").strip(),
                    "affected_contracts": (c5.get("affected_contracts") or "").strip(),
                    "affected_lines": f"{sm_row.get('matched_start_line_est','')}-{sm_row.get('matched_end_line_est','')}",
                },
            }
        )

    print(f"Eligible (full source): {len(candidates)}")
    print(f"Skipped (fragment files): {len(skipped_fragment)} → {skipped_fragment}")
    print(f"Skipped (missing files): {len(skipped_missing)} → {skipped_missing}")

    if len(candidates) < N_PICK:
        print(
            f"ERROR: only {len(candidates)} eligible candidates; need {N_PICK}",
            file=sys.stderr,
        )
        return 2

    picked = _stratified_pick(candidates, n=N_PICK)

    # Smoke meta summary
    sev_counts: dict[str, int] = {}
    proj_counts: dict[str, int] = {}
    subtype_counts: dict[str, int] = {}
    for c in picked:
        sev_counts[c["severity"]] = sev_counts.get(c["severity"], 0) + 1
        proj_counts[c["project_name"]] = proj_counts.get(c["project_name"], 0) + 1
        subtype_counts[c["issue_subtype"]] = (
            subtype_counts.get(c["issue_subtype"], 0) + 1
        )

    payload = {
        "cases": picked,
        "_smoke_meta": {
            "n": len(picked),
            "source_dataset": "C5/Repair-Access-Control-C-main (remaining33)",
            "severity": sev_counts,
            "project_name": proj_counts,
            "issue_subtype": subtype_counts,
            "verifier_mode": {"original": len(picked)},
            "selection_policy": (
                "Filter to incidents whose mapped Solidity file is a COMPLETE "
                "contract (has pragma + contract decl). Stratify by "
                "(project_name, issue_subtype) and prefer longer sources."
            ),
        },
    }

    OUT_PATH.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"Wrote {OUT_PATH}")
    print(json.dumps(payload["_smoke_meta"], indent=2, ensure_ascii=False))
    print()
    print("Picked incidents:")
    for c in picked:
        loc = c["contract_source"].count("\n") + 1
        print(
            f"  - {c['id']:8} {c['project_name']:20} {c['contract_name']:25} "
            f"fn={c['vulnerable_function']:20} sev={c['severity']:6} "
            f"loc={loc:5} subtype={c['issue_subtype']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
