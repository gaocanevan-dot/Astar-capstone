"""Driver: fetch source for all 72 c4 cases in eval_set.json.

Reads:
    data/dataset/eval_set.json (c4_mcp_pending cases)

Writes:
    data/contracts/raw/<incident_id>/<file>.sol  + siblings
    data/dataset/eval_set.json                   (in-place update)
    data/dataset/source_unresolved.json          (failure manifest)
    data/contracts/raw_c4_index.json             (per-case fetch manifest)

Deduplication: cases with the same reference_url are fetched once; results
applied to all rows. (35 unique findings issues span 72 rows.)

Idempotent: re-runs only fetch cases still marked pending_mcp. Use --refetch
to force re-pull all c4 cases.

CLI:
    python -m scripts.source_fetcher.run_c4_fetch              # process pending only
    python -m scripts.source_fetcher.run_c4_fetch --refetch    # force-refetch all c4
    python -m scripts.source_fetcher.run_c4_fetch --dry-run    # show plan only
    python -m scripts.source_fetcher.run_c4_fetch --limit 5    # first N cases
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path

from scripts.source_fetcher import c4_fetcher, gh_client

REPO_ROOT = Path(__file__).resolve().parents[2]
EVAL_SET_JSON = REPO_ROOT / "data" / "dataset" / "eval_set.json"
UNRESOLVED_JSON = REPO_ROOT / "data" / "dataset" / "source_unresolved.json"
C4_INDEX_JSON = REPO_ROOT / "data" / "contracts" / "raw_c4_index.json"


def _load_eval_set() -> dict:
    return json.loads(EVAL_SET_JSON.read_text(encoding="utf-8"))


def _safe_relpath(p: Path) -> str:
    try:
        return str(p.relative_to(REPO_ROOT))
    except ValueError:
        return str(p)


def run(*, refetch: bool = False, dry_run: bool = False, limit: int | None = None) -> dict:
    eval_set = _load_eval_set()
    cases = eval_set["cases"]

    # Select target cases
    target = []
    for c in cases:
        if c["source_type"] not in ("c4_mcp_pending", "c4_local"):
            continue
        if not refetch and c["status"] != "pending_mcp":
            continue
        target.append(c)

    if limit is not None:
        target = target[:limit]

    # Group by reference_url for dedup
    by_url: dict[str, list[dict]] = {}
    for c in target:
        url = c.get("reference_url", "")
        by_url.setdefault(url, []).append(c)

    print(f"[run_c4_fetch] {len(target)} target cases, {len(by_url)} unique URLs, refetch={refetch} dry_run={dry_run}")

    if dry_run:
        return {
            "dry_run": True,
            "target_count": len(target),
            "unique_urls": len(by_url),
        }

    fetch_manifest: list[dict] = []
    unresolved: list[dict] = []
    ok_count = 0
    fail_count = 0
    t0 = time.time()

    for url_idx, (url, group) in enumerate(by_url.items()):
        leader = group[0]
        print(f"[{url_idx+1}/{len(by_url)}] {leader['incident_id']} ({len(group)} row(s)) <- {url[:70]}")
        try:
            res, content, sibs = c4_fetcher.fetch_one(leader)
        except Exception as e:  # noqa: BLE001
            res = c4_fetcher.C4FetchResult(
                incident_id=leader["incident_id"],
                case_id=leader["id"],
                status="unknown_error",
                reason=f"{type(e).__name__}: {str(e)[:120]}",
            )
            content, sibs = None, []

        if res.status != "ok" or content is None:
            for case in group:
                unresolved.append({
                    "id": case["id"],
                    "incident_id": case["incident_id"],
                    "reference_url": url,
                    "status": res.status,
                    "reason": res.reason,
                })
                # Keep status pending_mcp; user can re-run after diagnosing
            fail_count += len(group)
            fetch_manifest.append({**asdict(res), "rows_affected": [c["id"] for c in group]})
            continue

        # Write files (once per incident_id; group members share contract_source_path)
        target_relpath, sib_relpaths = c4_fetcher.write_to_raw(
            leader["incident_id"], res.source_path, content, sibs
        )

        # Update all rows in this group
        for case in group:
            case["contract_source"] = content
            case["contract_source_path"] = target_relpath
            case["sibling_files"] = res.sibling_files
            case["source_type"] = "c4_local"
            case["status"] = "ok"
            # Fix "Unknown" function name using enclosing function
            if case.get("vulnerable_function") in ("Unknown", "") and res.enclosing_function:
                case["vulnerable_function"] = res.enclosing_function
            # Carry provenance metadata (don't mutate originals from CSV)
            case["c4_source_repo"] = res.source_repo
            case["c4_source_ref"] = res.source_ref
            case["c4_issue"] = f"code-423n4/{res.findings_repo}-findings#{res.issue_num}"
            case["c4_line_start"] = res.line_start
            case["c4_line_end"] = res.line_end

        ok_count += len(group)
        fetch_manifest.append({**asdict(res), "rows_affected": [c["id"] for c in group], "target_relpath": target_relpath})

    elapsed = time.time() - t0
    rs = gh_client.rate_state()

    # Refresh eval_set.json meta
    eval_set["meta"]["c5_local"] = sum(1 for c in cases if c["source_type"] == "c5_local")
    eval_set["meta"]["c4_local"] = sum(1 for c in cases if c["source_type"] == "c4_local")
    eval_set["meta"]["c4_mcp_pending"] = sum(1 for c in cases if c["source_type"] == "c4_mcp_pending")
    eval_set["meta"]["last_c4_fetch_at"] = dt.datetime.now(dt.timezone.utc).isoformat()

    # Write artifacts
    EVAL_SET_JSON.write_text(json.dumps(eval_set, indent=2, ensure_ascii=False))
    UNRESOLVED_JSON.write_text(json.dumps({"unresolved": unresolved}, indent=2, ensure_ascii=False))
    C4_INDEX_JSON.parent.mkdir(parents=True, exist_ok=True)
    C4_INDEX_JSON.write_text(json.dumps({"manifests": fetch_manifest}, indent=2, ensure_ascii=False))

    report = {
        "target_count": len(target),
        "unique_urls": len(by_url),
        "ok_count": ok_count,
        "fail_count": fail_count,
        "elapsed_seconds": round(elapsed, 1),
        "rate_remaining": rs.remaining,
        "rate_limit": rs.limit,
        "outputs": {
            "eval_set": _safe_relpath(EVAL_SET_JSON),
            "unresolved": _safe_relpath(UNRESOLVED_JSON),
            "c4_index": _safe_relpath(C4_INDEX_JSON),
        },
    }
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description="P_mcp: fetch c4 sources via GitHub REST API")
    ap.add_argument("--refetch", action="store_true", help="re-pull all c4 cases (not only pending)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=None, help="process first N cases")
    args = ap.parse_args()

    report = run(refetch=args.refetch, dry_run=args.dry_run, limit=args.limit)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report.get("fail_count", 0) == 0 else 0  # report-only; not fatal


if __name__ == "__main__":
    sys.exit(main())
