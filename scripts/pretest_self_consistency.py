#!/usr/bin/env python3
"""Day-4 R8 pre-test — gate Issue 3 (self-consistency) on real divergence.

For the 6 cases that did NOT pass under agent-full (4 abstain + 2 skipped),
run `analyze_consistent(n=3)` and compare its top-1 vs single-shot top-1
(captured from `data/evaluation/smoke_agent-full.json`).

Decision rule: if ≥2 cases produce a DIFFERENT top-1 under self-consistency
(i.e., the consensus would change the function under analysis), Issue 3 is
empirically justified. Otherwise drop Issue 3 entirely.

Cost: 6 cases × 3 LLM calls = 18 calls; ~$0.20-0.40.
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

from agent.nodes.analyst import analyze_consistent  # noqa: E402
from agent.state import empty_annotations  # noqa: E402


SMOKE_PATH = REPO_ROOT / "data" / "dataset" / "smoke_set.json"
AGENT_FULL_PATH = REPO_ROOT / "data" / "evaluation" / "smoke_agent-full.json"
OUT_PATH = REPO_ROOT / "data" / "evaluation" / "pretest_self_consistency.json"

# Cases to test: those that did NOT pass under agent-full
NON_PASS_VERDICTS = {"abstain", "skipped", "fail_error_runtime", "fail_error_compile"}


def main() -> int:
    smoke = json.loads(SMOKE_PATH.read_text(encoding="utf-8"))
    agent_full = json.loads(AGENT_FULL_PATH.read_text(encoding="utf-8"))

    cases_by_id = {c["id"]: c for c in smoke["cases"]}
    af_by_id = {r["case_id"]: r for r in agent_full}

    target_cases = [
        c for c in smoke["cases"]
        if af_by_id.get(c["id"], {}).get("verdict") in NON_PASS_VERDICTS
    ]
    print(f"[pretest] {len(target_cases)} non-pass cases to test under SC=3")
    for c in target_cases:
        af = af_by_id.get(c["id"], {})
        print(
            f"  {c['id']:8} | gt={c.get('vulnerable_function',''):28} | "
            f"single-shot pred={af.get('target_function','') or '(empty)':28} | "
            f"agent verdict={af.get('verdict','')}"
        )
    print()

    results = []
    diverge_count = 0
    t0 = time.time()
    for i, case in enumerate(target_cases, 1):
        case_id = case["id"]
        ann = dict(empty_annotations())
        ann["case_id"] = case_id
        ann["contract_name"] = case["contract_name"]
        af = af_by_id.get(case_id, {})
        single_shot_pred = (af.get("target_function") or "").strip()

        try:
            sc_pred = analyze_consistent(
                contract_source=case.get("contract_source", ""),
                contract_name=case["contract_name"],
                annotations=ann,
                n_runs=3,
            )
        except Exception as exc:
            sc_pred = {
                "target_function": "",
                "candidates": [],
                "hypothesis": "",
                "confidence": 0.0,
                "reasoning": f"FAILED: {type(exc).__name__}: {exc}",
            }

        sc_top1 = (sc_pred.get("target_function") or "").strip()
        diverged = bool(single_shot_pred) and bool(sc_top1) and (
            single_shot_pred.lower() != sc_top1.lower()
        )
        # Also consider divergence if single-shot was empty but SC produced something
        if not single_shot_pred and sc_top1:
            diverged = True
        if diverged:
            diverge_count += 1

        rec = {
            "case_id": case_id,
            "contract_name": case["contract_name"],
            "ground_truth_function": case.get("vulnerable_function", ""),
            "single_shot_pred": single_shot_pred,
            "sc3_top1": sc_top1,
            "sc3_candidates": sc_pred.get("candidates", []),
            "diverged": diverged,
            "tokens_prompt": ann.get("tokens_prompt", 0),
            "tokens_completion": ann.get("tokens_completion", 0),
            "llm_calls": ann.get("llm_calls", 0),
        }
        results.append(rec)
        print(
            f"  [{i}/{len(target_cases)}] {case_id}: "
            f"single='{single_shot_pred}' SC3='{sc_top1}' "
            f"{'DIVERGED' if diverged else 'same'}"
        )

    elapsed = time.time() - t0
    n = len(results)
    total_p = sum(r["tokens_prompt"] for r in results)
    total_c = sum(r["tokens_completion"] for r in results)
    cost = total_p / 1000 * 0.00025 + total_c / 1000 * 0.002
    print()
    print(f"=== Pre-test summary (n={n}) ===")
    print(f"  Diverged: {diverge_count}/{n}")
    print(f"  Total LLM calls: {sum(r['llm_calls'] for r in results)}")
    print(f"  Total tokens: {total_p} prompt + {total_c} completion")
    print(f"  Cost: ${cost:.4f}")
    print(f"  Wall: {elapsed:.1f}s")
    print()
    if diverge_count >= 2:
        print(f"[GATE-PASS] {diverge_count}/{n} cases diverged → Issue 3 JUSTIFIED")
    else:
        print(
            f"[GATE-DROP] only {diverge_count}/{n} cases diverged → "
            f"Issue 3 NOT justified; drop self-consistency wiring"
        )

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(
        json.dumps(
            {
                "summary": {
                    "n": n,
                    "diverge_count": diverge_count,
                    "decision": "JUSTIFIED" if diverge_count >= 2 else "DROP",
                    "cost_usd": round(cost, 4),
                    "wall_clock_s": round(elapsed, 1),
                    "total_tokens_prompt": total_p,
                    "total_tokens_completion": total_c,
                },
                "results": results,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"Written: {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
