#!/usr/bin/env python3
"""Day-5 S0 — Slither environment probe.

5-min pre-flight: runs `static_analyzer.analyze()` on each of the 10 smoke
cases and records whether it actually executed Slither or fell back to the
regex parser. Output is a single JSON file the agent's `static_analyze` tool
can consult to set its `tool_used` field correctly during Day-5 sweep.

Zero LLM cost. Just subprocess timing + boolean per case.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from agent.adapters.static_analyzer import analyze  # noqa: E402


def main() -> int:
    smoke = json.loads(
        (REPO_ROOT / "data" / "dataset" / "smoke_set.json").read_text(encoding="utf-8")
    )
    cases = smoke.get("cases", [])
    print(f"Probing static_analyzer on {len(cases)} smoke cases...\n")

    results = []
    slither_count = 0
    regex_count = 0
    for case in cases:
        cid = case["id"]
        cname = case["contract_name"]
        src = case.get("contract_source", "")
        loc = src.count("\n") + 1
        t0 = time.time()
        try:
            facts = analyze(src, cname)
            err = ""
        except Exception as exc:  # pragma: no cover - defensive
            facts = None
            err = f"{type(exc).__name__}: {exc}"
        dt = time.time() - t0
        if facts:
            tool = facts.tool
            n_funcs = len(facts.functions)
            n_findings = len(facts.slither_findings)
        else:
            tool = "error"
            n_funcs = 0
            n_findings = 0
        if tool == "slither":
            slither_count += 1
        elif tool == "regex":
            regex_count += 1
        rec = {
            "case_id": cid,
            "contract_name": cname,
            "loc": loc,
            "tool_used": tool,
            "n_functions": n_funcs,
            "n_slither_findings": n_findings,
            "wall_clock_s": round(dt, 2),
            "error": err,
        }
        results.append(rec)
        marker = "🔬" if tool == "slither" else ("📝" if tool == "regex" else "❌")
        print(
            f"  {marker} {cid:8s} ({cname[:30]:30s}) "
            f"loc={loc:>4d} tool={tool:>7s} "
            f"funcs={n_funcs:>3d} findings={n_findings:>2d} dt={dt:>5.2f}s"
            f"{'  ERR=' + err if err else ''}"
        )

    print(
        f"\n=== Summary: slither={slither_count}/{len(cases)} "
        f"regex={regex_count}/{len(cases)} ==="
    )

    out = REPO_ROOT / "data" / "evaluation" / "static_analyzer_probe.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {
                "n_cases": len(cases),
                "slither_count": slither_count,
                "regex_count": regex_count,
                "error_count": len(cases) - slither_count - regex_count,
                "results": results,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"\nWritten → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
