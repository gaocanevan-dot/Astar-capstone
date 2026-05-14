"""For c4 cases whose upstream source is permanently dead (upstream repo deleted
and c4 mirror empty), fall back to the CSV `vulnerable_code` snippet so the
case still has *some* `contract_source` for analyst-only evaluation.

Side effects on each affected case (status was "pending_mcp"):
    contract_source         = vulnerable_code_snippet  (from CSV)
    source_type             = "snippet_only"
    status                  = "ok_snippet"             (degraded ok)
    contract_source_path    = None                     (unchanged; no real file)
    buildable               = False                    (cannot forge build)
    snippet_only_reason     = (carried from source_unresolved.json)

Idempotent: only updates cases whose source_type is currently "c4_mcp_pending".
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
EVAL_SET_JSON = REPO_ROOT / "data" / "dataset" / "eval_set.json"
UNRESOLVED_JSON = REPO_ROOT / "data" / "dataset" / "source_unresolved.json"


def run() -> dict:
    eval_set = json.loads(EVAL_SET_JSON.read_text(encoding="utf-8"))
    cases = eval_set["cases"]

    # Build reason map by case id
    reasons: dict[str, str] = {}
    if UNRESOLVED_JSON.is_file():
        ur = json.loads(UNRESOLVED_JSON.read_text(encoding="utf-8")).get("unresolved", [])
        for u in ur:
            reasons[u["id"]] = u.get("reason", "")

    affected = 0
    for case in cases:
        if case["source_type"] != "c4_mcp_pending":
            continue
        snippet = (case.get("vulnerable_code_snippet") or "").strip()
        if not snippet:
            # Nothing to fall back to; leave as-is.
            continue
        case["contract_source"] = snippet
        case["source_type"] = "snippet_only"
        case["status"] = "ok_snippet"
        case["buildable"] = False
        case["snippet_only_reason"] = reasons.get(case["id"], "upstream source unavailable")
        affected += 1

    # Refresh meta
    from collections import Counter
    type_counter = Counter(c["source_type"] for c in cases)
    eval_set.setdefault("meta", {})
    eval_set["meta"].update({k: type_counter.get(k, 0) for k in (
        "c5_local", "c4_local", "c4_mcp_pending", "snippet_only"
    )})
    eval_set["meta"]["snippet_fallback_applied_at"] = dt.datetime.now(dt.timezone.utc).isoformat()

    EVAL_SET_JSON.write_text(json.dumps(eval_set, indent=2, ensure_ascii=False))

    return {
        "affected_cases": affected,
        "total_cases": len(cases),
        "source_type_distribution": dict(type_counter),
    }


def main() -> int:
    report = run()
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
