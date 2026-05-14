"""Copy 118 c5 access-control source files from Repair-Access-Control-C-main into data/contracts/raw/.

Per-case layout:
    data/contracts/raw/<incident_id>/
        <target_solidity_file>.sol             # the file containing the vulnerable function
        <sibling>.sol ... (cap=20)             # same-directory .sol files for closure extraction

Reads:
    data/dataset/c5_access_control_dataset_118.csv  (full case metadata)
    data/dataset/source_map_118.csv                 (incident_id -> repair-relative path)

Writes:
    data/contracts/raw/<incident_id>/*.sol
    data/contracts/raw_local_index.json             (manifest)

CLI:
    python -m scripts.source_fetcher.local_copier              # default paths, copy mode
    python -m scripts.source_fetcher.local_copier --symlink    # symlink instead of copy
    python -m scripts.source_fetcher.local_copier --dry-run    # report-only
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
REPAIR_ROOT = REPO_ROOT / "data" / "dataset" / "Repair-Access-Control-C-main"
SOURCE_MAP_CSV = REPO_ROOT / "data" / "dataset" / "source_map_118.csv"
C5_DATASET_CSV = REPO_ROOT / "data" / "dataset" / "c5_access_control_dataset_118.csv"
OUT_DIR = REPO_ROOT / "data" / "contracts" / "raw"
INDEX_FILE = REPO_ROOT / "data" / "contracts" / "raw_local_index.json"

SIBLING_CAP = 20


@dataclass
class CaseManifest:
    incident_id: str
    project_name: str
    target_file: str
    target_dest: str
    sibling_files: list[str] = field(default_factory=list)
    sibling_capped: bool = False
    function_found_in_target: bool = False
    attack_surface: str = ""
    status: str = "ok"  # ok | missing_source | function_not_found
    reason: str = ""


def _function_name(attack_surface: str) -> str:
    """Extract bare function name from `funcName(args, ...)`."""
    s = attack_surface.split("(", 1)[0].strip()
    return s


def _has_function_signature(src_text: str, fn_name: str) -> bool:
    """Loose match: 'function <name>' appears in the source."""
    if not fn_name:
        return False
    return f"function {fn_name}" in src_text or f"function  {fn_name}" in src_text


def _gather_siblings(target: Path, cap: int = SIBLING_CAP) -> tuple[list[Path], bool]:
    """Return up to `cap` .sol files from the same directory as `target` (excluding target)."""
    parent = target.parent
    sibs = sorted(p for p in parent.glob("*.sol") if p != target)
    capped = len(sibs) > cap
    return sibs[:cap], capped


def _safe_relpath(p: Path) -> str:
    try:
        return str(p.relative_to(REPO_ROOT))
    except ValueError:
        return str(p)


def copy_one_case(
    incident_id: str,
    project_name: str,
    target_rel: str,
    attack_surface: str,
    *,
    use_symlink: bool = False,
    dry_run: bool = False,
) -> CaseManifest:
    """Copy one case's target + siblings into data/contracts/raw/<incident_id>/."""
    target_src = REPAIR_ROOT / target_rel
    case_dir = OUT_DIR / incident_id

    manifest = CaseManifest(
        incident_id=incident_id,
        project_name=project_name,
        target_file=target_rel,
        target_dest=_safe_relpath(case_dir / target_src.name),
        attack_surface=attack_surface,
    )

    if not target_src.is_file():
        manifest.status = "missing_source"
        manifest.reason = f"target not found at {target_src}"
        return manifest

    if not dry_run:
        case_dir.mkdir(parents=True, exist_ok=True)

    # Place target
    dst = case_dir / target_src.name
    if not dry_run:
        _place_file(target_src, dst, use_symlink)

    # Verify function name appears in the target file
    fn_name = _function_name(attack_surface)
    try:
        target_text = target_src.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        manifest.status = "missing_source"
        manifest.reason = f"could not read target: {exc}"
        return manifest
    manifest.function_found_in_target = _has_function_signature(target_text, fn_name)
    if not manifest.function_found_in_target:
        manifest.status = "function_not_found"
        manifest.reason = f"`function {fn_name}` not found in target text"

    # Siblings
    siblings, capped = _gather_siblings(target_src, cap=SIBLING_CAP)
    manifest.sibling_capped = capped
    for sib in siblings:
        sib_dst = case_dir / sib.name
        if not dry_run:
            _place_file(sib, sib_dst, use_symlink)
        manifest.sibling_files.append(sib.name)

    return manifest


def _place_file(src: Path, dst: Path, use_symlink: bool) -> None:
    """Copy or symlink `src` to `dst`. Overwrites silently."""
    if dst.exists() or dst.is_symlink():
        dst.unlink()
    if use_symlink:
        os.symlink(src.resolve(), dst)
    else:
        shutil.copy2(src, dst)


def load_source_map() -> dict[str, dict]:
    """incident_id -> row dict."""
    out: dict[str, dict] = {}
    with SOURCE_MAP_CSV.open(encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            out[row["incident_id"]] = row
    return out


def load_c5_cases() -> list[dict]:
    """All 118 c5 case rows (full schema)."""
    with C5_DATASET_CSV.open(encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def run(use_symlink: bool = False, dry_run: bool = False) -> dict:
    """Main entry: copy all 118 c5 cases. Returns aggregated report."""
    if not REPAIR_ROOT.is_dir():
        raise SystemExit(f"Repair folder not found: {REPAIR_ROOT}")
    if not SOURCE_MAP_CSV.is_file():
        raise SystemExit(f"source_map_118.csv not found: {SOURCE_MAP_CSV}")
    if not C5_DATASET_CSV.is_file():
        raise SystemExit(f"c5_access_control_dataset_118.csv not found: {C5_DATASET_CSV}")

    source_map = load_source_map()
    cases = load_c5_cases()

    manifests: list[CaseManifest] = []
    for case in cases:
        iid = case["incident_id"]
        if iid not in source_map:
            manifests.append(
                CaseManifest(
                    incident_id=iid,
                    project_name=case["project_name"],
                    target_file="",
                    target_dest="",
                    attack_surface=case.get("attack_surface", ""),
                    status="missing_source",
                    reason="no entry in source_map_118.csv",
                )
            )
            continue
        sm = source_map[iid]
        m = copy_one_case(
            incident_id=iid,
            project_name=case["project_name"],
            target_rel=sm["matched_solidity_file"],
            attack_surface=case.get("attack_surface", ""),
            use_symlink=use_symlink,
            dry_run=dry_run,
        )
        manifests.append(m)

    report = {
        "total": len(manifests),
        "ok": sum(1 for m in manifests if m.status == "ok"),
        "function_not_found": sum(1 for m in manifests if m.status == "function_not_found"),
        "missing_source": sum(1 for m in manifests if m.status == "missing_source"),
        "fn_match_rate": (
            sum(1 for m in manifests if m.function_found_in_target) / len(manifests)
            if manifests else 0.0
        ),
        "total_sibling_files": sum(len(m.sibling_files) for m in manifests),
        "cases_with_capped_siblings": sum(1 for m in manifests if m.sibling_capped),
        "manifests": [asdict(m) for m in manifests],
        "dry_run": dry_run,
        "mode": "symlink" if use_symlink else "copy",
    }

    if not dry_run:
        INDEX_FILE.parent.mkdir(parents=True, exist_ok=True)
        INDEX_FILE.write_text(json.dumps(report, indent=2, ensure_ascii=False))

    return report


def main() -> int:
    ap = argparse.ArgumentParser(description="P_local: copy 118 c5 sources from Repair folder")
    ap.add_argument("--symlink", action="store_true", help="symlink instead of copy")
    ap.add_argument("--dry-run", action="store_true", help="report only, no writes")
    args = ap.parse_args()

    report = run(use_symlink=args.symlink, dry_run=args.dry_run)
    print(json.dumps(
        {k: v for k, v in report.items() if k != "manifests"},
        indent=2,
        ensure_ascii=False,
    ))
    # Show first 3 problem cases for fast triage
    problems = [m for m in report["manifests"] if m["status"] != "ok"]
    if problems:
        print(f"\n=== {len(problems)} problem cases (first 5 shown) ===")
        for p in problems[:5]:
            print(f"  {p['incident_id']:10s} {p['status']:20s} {p['reason']}")
    return 0 if report["missing_source"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
