#!/usr/bin/env python3
"""Merge vulnerabilities.json + vulnerabilities_pre.json into bad_cases.json
and eval_set.json. Fill missing contract_source from data/contracts/raw/.

Per task P1.1, P1.2, P1.7, P1.8.

Usage:
    python scripts/build_eval_set.py                    # merge + write
    python scripts/build_eval_set.py --validate         # also validate
    python scripts/build_eval_set.py --validate --strict # fail if <90% buildable
    python scripts/build_eval_set.py --count safe_by_type
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from agent.data.schema import Case  # noqa: E402


PROJECT_TO_RAW_DIR = {
    "NOYA": "NOYA",
    "The Graph": "GRA",
    "Coinbase Smart Wallet": "CSW",
    "Gitcoin Passport": "GIT",
}


def _infer_source_type(meta: dict) -> str:
    source = (meta.get("source") or "").lower()
    if "code4rena" in source or "c4" in source:
        return "code4rena_bad"
    if "swc" in source:
        return "swc_bad"
    return "code4rena_bad"


def _normalize(raw: dict) -> dict:
    meta = raw.get("metadata") or {}
    contract_source = raw.get("contract_source", "") or ""
    return {
        "id": raw["id"],
        "contract_source": contract_source,
        "contract_name": raw.get("contract_name", ""),
        "ground_truth_label": "vulnerable",
        "source": meta.get("source", ""),
        "source_type": _infer_source_type(meta),
        "project_name": meta.get("project_name", ""),
        "buildable": bool(contract_source.strip()),
        "vulnerable_function": raw.get("vulnerable_function"),
        "vulnerability_type": raw.get("vulnerability_type", "access_control"),
        "severity": raw.get("severity", "high"),
        "description": raw.get("description", ""),
        "missing_check": raw.get("missing_check", ""),
        "attack_surface": raw.get("attack_surface", ""),
        "vulnerable_code_snippet": raw.get("vulnerable_code_snippet", ""),
        "issue_category": raw.get("issue_category", ""),
        "fix_recommendation": raw.get("fix_recommendation", ""),
        "fixed_code": raw.get("fixed_code", ""),
        "poc_code": raw.get("poc_code", ""),
        "tags": raw.get("tags", []),
        "metadata": meta,
    }


def merge_and_dedupe(sources: list[Path]) -> list[Case]:
    """Later file wins on duplicate id IF it has a longer contract_source."""
    seen: dict[str, Case] = {}
    for src in sources:
        data = json.loads(src.read_text(encoding="utf-8"))
        for raw in data.get("cases", []):
            try:
                normalized = _normalize(raw)
                case = Case(**normalized)
            except Exception as exc:  # pragma: no cover - defensive
                print(f"WARN parse failed for {raw.get('id')!r}: {exc}", file=sys.stderr)
                continue
            existing = seen.get(case.id)
            if existing is None or len(case.contract_source) > len(existing.contract_source):
                seen[case.id] = case
    return list(seen.values())


def fill_missing_source(cases: list[Case], raw_root: Path) -> int:
    filled = 0
    for case in cases:
        if case.contract_source:
            continue
        dir_key = PROJECT_TO_RAW_DIR.get(case.project_name)
        if not dir_key:
            continue
        candidate = raw_root / dir_key / f"{case.contract_name}.sol"
        if candidate.exists():
            case.contract_source = candidate.read_text(encoding="utf-8")
            case.buildable = True
            filled += 1
    return filled


def load_safe_cases(path: Path) -> list[Case]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return [Case(**c) for c in data.get("cases", [])]


def write_json(path: Path, cases: list[Case]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"cases": [c.model_dump() for c in cases]}
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def cmd_count(args: argparse.Namespace) -> int:
    path = Path(args.eval_out)
    if not path.exists():
        print(f"ERROR: {path} does not exist", file=sys.stderr)
        return 1
    data = json.loads(path.read_text(encoding="utf-8"))
    if args.count == "safe_by_type":
        ctr: Counter[str] = Counter()
        for c in data.get("cases", []):
            if c.get("ground_truth_label") == "safe":
                ctr[c.get("source_type", "?")] += 1
        if not ctr:
            print("(no safe cases yet)")
        for k, v in sorted(ctr.items()):
            print(f"{k}\t{v}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Merge + validate eval dataset.")
    ap.add_argument(
        "--sources",
        nargs="+",
        default=[
            "data/dataset/vulnerabilities.json",
            "data/dataset/vulnerabilities_pre.json",
        ],
    )
    ap.add_argument("--bad-out", default="data/dataset/bad_cases.json")
    ap.add_argument("--eval-out", default="data/dataset/eval_set.json")
    ap.add_argument("--raw-root", default="data/contracts/raw")
    ap.add_argument("--safe-path", default="data/dataset/safe_cases.json")
    ap.add_argument("--validate", action="store_true")
    ap.add_argument(
        "--strict",
        action="store_true",
        help="Fail if <90%% buildable or <100 bad cases",
    )
    ap.add_argument(
        "--count",
        choices=["safe_by_type"],
        default=None,
        help="Print counts then exit (no merge)",
    )
    args = ap.parse_args()

    if args.count:
        return cmd_count(args)

    sources = [Path(p) for p in args.sources]
    missing = [p for p in sources if not p.exists()]
    if missing:
        print(f"ERROR: missing sources: {missing}", file=sys.stderr)
        return 1

    cases = merge_and_dedupe(sources)
    filled = fill_missing_source(cases, Path(args.raw_root))
    print(
        f"Merged {len(cases)} unique bad cases (from {sum(len(json.loads(s.read_text(encoding='utf-8')).get('cases', [])) for s in sources)} raw entries);"
        f" filled {filled} from {args.raw_root}"
    )

    write_json(Path(args.bad_out), cases)
    print(f"Wrote {len(cases)} bad cases → {args.bad_out}")

    safe_cases = load_safe_cases(Path(args.safe_path))
    all_cases = cases + safe_cases
    write_json(Path(args.eval_out), all_cases)
    print(
        f"Wrote {len(all_cases)} total cases → {args.eval_out}"
        f" (vulnerable={len(cases)}, safe={len(safe_cases)})"
    )

    if args.validate:
        errors: list[str] = []
        if len(cases) < 100:
            msg = f"bad case count {len(cases)} < 100"
            (errors if args.strict else []).append(msg)
            print(f"{'ERROR' if args.strict else 'INFO'}: {msg}")
        buildable_frac = (
            sum(1 for c in cases if c.buildable) / max(1, len(cases))
        )
        if args.strict and buildable_frac < 0.90:
            errors.append(f"buildable fraction {buildable_frac:.2%} < 90%")
        empty_source = [c.id for c in cases if not c.contract_source.strip()]
        missing_fn = [
            c.id
            for c in cases
            if c.ground_truth_label == "vulnerable" and not c.vulnerable_function
        ]
        if errors:
            print(f"VALIDATION ERRORS: {errors}", file=sys.stderr)
            return 1
        print(
            f"VALIDATION OK: bad={len(cases)}, safe={len(safe_cases)},"
            f" buildable={buildable_frac:.2%},"
            f" empty_source={len(empty_source)}, missing_vuln_fn={len(missing_fn)}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
