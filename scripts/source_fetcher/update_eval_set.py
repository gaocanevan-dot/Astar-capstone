"""Rebuild data/dataset/eval_set.json from access_control_dataset.csv (190 cases) +
local sources copied by local_copier.py + (later) MCP-fetched sources.

Strategy (per user instruction):
- Ignore existing eval_set.json's 42 hand-curated cases; archive to .bak before overwrite.
- 118 c5 cases (ACF-*):   read source from data/contracts/raw/<incident_id>/<target>.sol
- 72 c4 cases (C4-*):     placeholder; contract_source="", contract_source_path=null,
                          status="pending_mcp" until P_mcp populates them.

Output schema mirrors the existing eval_set.json `{"cases": [...]}` shape with these fields per case:
  id, incident_id, project_name, contract_name, attack_surface, vulnerable_function,
  vulnerable_code_snippet, source, source_category, year, severity, issue_category,
  issue_subtype, root_cause, impact, affected_contracts, reference_url,
  contract_source (inline str, empty for pending_mcp),
  contract_source_path (str relative to repo root, null for pending_mcp),
  sibling_files (list of co-located .sol filenames for MCC closure extraction),
  status ("ok" | "function_not_found" | "pending_mcp"),
  start_line, end_line,
  ground_truth_label ("vulnerable"),
  source_type ("c5_local" | "c4_mcp_pending"),
  buildable (null until MCC build_probe runs)

CLI:
    python -m scripts.source_fetcher.update_eval_set            # backup + rebuild
    python -m scripts.source_fetcher.update_eval_set --dry-run  # print stats, no write
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ACCESS_CSV = REPO_ROOT / "data" / "dataset" / "access_control_dataset.csv"
C5_118_CSV = REPO_ROOT / "data" / "dataset" / "c5_access_control_dataset_118.csv"
RAW_DIR = REPO_ROOT / "data" / "contracts" / "raw"
RAW_INDEX = REPO_ROOT / "data" / "contracts" / "raw_local_index.json"
EVAL_SET_JSON = REPO_ROOT / "data" / "dataset" / "eval_set.json"


def _read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _function_name(attack_surface: str) -> str:
    return attack_surface.split("(", 1)[0].strip()


def _int_or_none(s: str) -> int | None:
    try:
        return int(s)
    except (TypeError, ValueError):
        return None


def _safe_relpath(p: Path) -> str:
    try:
        return str(p.relative_to(REPO_ROOT))
    except ValueError:
        return str(p)


def build_case_record(
    row: dict,
    *,
    raw_index: dict,
    pending_mcp: bool,
) -> dict:
    """Convert a CSV row into an eval_set.json case dict."""
    iid = row["incident_id"]
    case_dir = RAW_DIR / iid

    record = {
        "id": iid,
        "incident_id": iid,
        "project_name": row.get("project_name", ""),
        "contract_name": row.get("contract_name", ""),
        "attack_surface": row.get("attack_surface", ""),
        "vulnerable_function": _function_name(row.get("attack_surface", "")),
        "vulnerable_code_snippet": row.get("vulnerable_code", ""),
        "source": row.get("source", ""),
        "source_category": row.get("source", ""),
        "year": _int_or_none(row.get("year", "")),
        "severity": row.get("priority_type", ""),
        "issue_category": row.get("issue_category", ""),
        "issue_subtype": row.get("issue_subtype", ""),
        "root_cause": row.get("root_cause", ""),
        "impact": row.get("impact", ""),
        "affected_contracts": row.get("affected_contracts", ""),
        "reference_url": row.get("reference", ""),
        "start_line": _int_or_none(row.get("start_line", "")),
        "end_line": _int_or_none(row.get("end_line", "")),
        "ground_truth_label": "vulnerable",
        "contract_source": "",
        "contract_source_path": None,
        "sibling_files": [],
        "status": "ok",
        "source_type": "c4_mcp_pending" if pending_mcp else "c5_local",
        "buildable": None,
    }

    if pending_mcp:
        record["status"] = "pending_mcp"
        return record

    # c5 local: find target file from raw_local_index manifest
    manifest = raw_index.get(iid)
    if manifest is None:
        record["status"] = "missing_source"
        return record

    target_dest = manifest.get("target_dest")
    if not target_dest:
        record["status"] = "missing_source"
        return record

    target_path = REPO_ROOT / target_dest
    if not target_path.is_file():
        record["status"] = "missing_source"
        return record

    try:
        record["contract_source"] = target_path.read_text(
            encoding="utf-8", errors="replace"
        )
    except OSError:
        record["status"] = "missing_source"
        return record

    record["contract_source_path"] = _safe_relpath(target_path)
    record["sibling_files"] = list(manifest.get("sibling_files", []))
    # Inherit the function_not_found flag from local_copier's manifest
    if manifest.get("status") == "function_not_found":
        record["status"] = "function_not_found"

    return record


def load_raw_index() -> dict:
    """incident_id -> manifest entry from raw_local_index.json."""
    if not RAW_INDEX.is_file():
        return {}
    data = json.loads(RAW_INDEX.read_text(encoding="utf-8"))
    return {m["incident_id"]: m for m in data.get("manifests", [])}


def run(dry_run: bool = False) -> dict:
    rows_190 = _read_csv(ACCESS_CSV)
    rows_118 = _read_csv(C5_118_CSV)
    ids_118 = {r["incident_id"] for r in rows_118}

    raw_index = load_raw_index()
    if not raw_index:
        raise SystemExit(
            f"raw_local_index.json missing or empty; run local_copier.py first ({RAW_INDEX})"
        )

    cases: list[dict] = []
    # Expand row-by-row: an incident with N attack_surface rows becomes N cases.
    # Duplicate incident_ids get unique `id` suffix `_<seq>` (seq starts at 2);
    # `contract_source_path` is shared across rows of the same incident_id.
    seen_count: dict[str, int] = {}
    for row in rows_190:
        iid = row["incident_id"]
        seen_count[iid] = seen_count.get(iid, 0) + 1
        seq = seen_count[iid]
        unique_id = iid if seq == 1 else f"{iid}_{seq}"

        is_c5 = iid in ids_118
        rec = build_case_record(row, raw_index=raw_index, pending_mcp=not is_c5)
        # Override the `id` field for uniqueness; keep `incident_id` as the
        # incident-level grouping key (shared across multi-row incidents).
        rec["id"] = unique_id
        cases.append(rec)

    cases.sort(key=lambda c: (c["incident_id"], c["id"]))

    report = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "total_cases": len(cases),
        "c5_local": sum(1 for c in cases if c["source_type"] == "c5_local"),
        "c4_mcp_pending": sum(1 for c in cases if c["source_type"] == "c4_mcp_pending"),
        "with_inline_source": sum(1 for c in cases if c["contract_source"]),
        "status_ok": sum(1 for c in cases if c["status"] == "ok"),
        "status_function_not_found": sum(
            1 for c in cases if c["status"] == "function_not_found"
        ),
        "status_missing_source": sum(1 for c in cases if c["status"] == "missing_source"),
        "status_pending_mcp": sum(1 for c in cases if c["status"] == "pending_mcp"),
    }

    if dry_run:
        return {**report, "cases": []}

    # Backup existing eval_set.json
    if EVAL_SET_JSON.is_file():
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = EVAL_SET_JSON.with_suffix(f".json.bak.{stamp}")
        shutil.copy2(EVAL_SET_JSON, backup)
        report["backup_path"] = _safe_relpath(backup)

    payload = {
        "schema_version": "2",
        "cases": cases,
        "meta": {
            "generated_at": report["generated_at"],
            "total": len(cases),
            "c5_local": report["c5_local"],
            "c4_mcp_pending": report["c4_mcp_pending"],
        },
    }
    EVAL_SET_JSON.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False)
    )
    report["output_path"] = _safe_relpath(EVAL_SET_JSON)
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description="Rebuild eval_set.json from 118+72 split")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    report = run(dry_run=args.dry_run)
    print(json.dumps(
        {k: v for k, v in report.items() if k != "cases"},
        indent=2,
        ensure_ascii=False,
    ))
    return 0


if __name__ == "__main__":
    sys.exit(main())
