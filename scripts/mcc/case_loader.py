"""Load a CaseInfo from eval_set.json — pragma, target file path, project root.

CaseInfo is the input to extract_closure.py. It is intentionally minimal so the
closure extractor knows nothing about CSV fields, MCC project layout, etc.

Lookup strategy (any one is sufficient):
  1. by `incident_id`           (e.g. "ACF-001")
  2. by `id`                    (e.g. "C4-111_2") — disambiguates multi-row cases

Skips snippet_only cases by default (they have no contract_source_path).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
EVAL_SET_JSON = REPO_ROOT / "data" / "dataset" / "eval_set.json"
RAW_DIR = REPO_ROOT / "data" / "contracts" / "raw"

# pragma solidity ^0.8.20;
# pragma solidity 0.8.10;
# pragma solidity >=0.7.0 <0.9.0;
_PRAGMA_RE = re.compile(r"pragma\s+solidity\s+([^;]+);", re.IGNORECASE)


@dataclass
class CaseInfo:
    case_id: str           # eval_set `id` (may have _N suffix)
    incident_id: str       # incident-level key (ACF-XXX, C4-XXX)
    contract_name: str
    target_file: Path      # absolute path to <case_dir>/<target>.sol
    project_root: Path     # absolute path to case dir = data/contracts/raw/<incident_id>/
    pragma: str            # raw pragma string (e.g. "^0.8.20") — empty if missing
    source_type: str       # c5_local | c4_local | snippet_only
    vulnerable_function: str = ""
    sibling_files: tuple[str, ...] = ()


def _extract_pragma(source: str) -> str:
    """Return the pragma version requirement, or "" if not found."""
    if not source:
        return ""
    m = _PRAGMA_RE.search(source)
    if not m:
        return ""
    return m.group(1).strip()


def _load_eval_set_cases() -> list[dict]:
    """Read all cases from data/dataset/eval_set.json."""
    if not EVAL_SET_JSON.is_file():
        raise FileNotFoundError(f"eval_set.json missing: {EVAL_SET_JSON}")
    data = json.loads(EVAL_SET_JSON.read_text(encoding="utf-8"))
    return list(data.get("cases", []))


def load_case(case_id_or_incident: str) -> CaseInfo:
    """Return CaseInfo for a single case.

    Raises:
      KeyError                  — case not found
      ValueError                — case has no `contract_source_path` (snippet_only)
      FileNotFoundError         — target file missing on disk
    """
    cases = _load_eval_set_cases()
    target_case: Optional[dict] = None
    for c in cases:
        if c.get("id") == case_id_or_incident or c.get("incident_id") == case_id_or_incident:
            target_case = c
            break
    if target_case is None:
        raise KeyError(f"case {case_id_or_incident!r} not found in eval_set.json")

    src_type = target_case.get("source_type", "")
    target_rel = target_case.get("contract_source_path")
    if not target_rel:
        raise ValueError(
            f"case {target_case['id']!r} has no contract_source_path "
            f"(source_type={src_type!r}); skipping MCC"
        )

    target_file = REPO_ROOT / target_rel
    if not target_file.is_file():
        raise FileNotFoundError(f"target file missing on disk: {target_file}")

    project_root = RAW_DIR / target_case["incident_id"]
    if not project_root.is_dir():
        raise FileNotFoundError(f"project root missing: {project_root}")

    source = target_file.read_text(encoding="utf-8", errors="replace")
    pragma = _extract_pragma(source)

    return CaseInfo(
        case_id=target_case["id"],
        incident_id=target_case["incident_id"],
        contract_name=target_case.get("contract_name", ""),
        target_file=target_file,
        project_root=project_root,
        pragma=pragma,
        source_type=src_type,
        vulnerable_function=target_case.get("vulnerable_function", ""),
        sibling_files=tuple(target_case.get("sibling_files", [])),
    )


def load_all_cases(*, skip_snippet: bool = True) -> list[CaseInfo]:
    """Load every eval_set case that has a usable contract_source_path."""
    out: list[CaseInfo] = []
    for c in _load_eval_set_cases():
        if skip_snippet and c.get("source_type") == "snippet_only":
            continue
        if not c.get("contract_source_path"):
            continue
        try:
            out.append(load_case(c["id"]))
        except (FileNotFoundError, ValueError):
            continue
    return out


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="MCC case_loader debug CLI")
    ap.add_argument("case_id", nargs="?", default=None, help="case id; omitted = list summary")
    args = ap.parse_args()

    if args.case_id:
        ci = load_case(args.case_id)
        print(json.dumps({
            "case_id": ci.case_id,
            "incident_id": ci.incident_id,
            "contract_name": ci.contract_name,
            "target_file": str(ci.target_file.relative_to(REPO_ROOT)),
            "project_root": str(ci.project_root.relative_to(REPO_ROOT)),
            "pragma": ci.pragma,
            "source_type": ci.source_type,
            "vulnerable_function": ci.vulnerable_function,
            "sibling_count": len(ci.sibling_files),
        }, indent=2, ensure_ascii=False))
    else:
        cases = load_all_cases()
        # Pragma distribution
        from collections import Counter
        pragma_dist = Counter(c.pragma for c in cases)
        type_dist = Counter(c.source_type for c in cases)
        print(json.dumps({
            "loadable_cases": len(cases),
            "source_type": dict(type_dist),
            "pragma_distribution (top 10)": dict(pragma_dist.most_common(10)),
        }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
