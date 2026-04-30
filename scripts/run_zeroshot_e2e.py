#!/usr/bin/env python3
"""Day-3 control experiment — zero-shot GPT + same builder/verifier pipeline.

Answers the apples-to-apples question: how does **raw GPT zero-shot prediction
piped through the same builder + forge verifier** compare to agent-full?

This is the missing baseline arm. Without it, the agent's "4/10 pass rate"
claim is incomparable — zero-shot didn't get a PoC pipeline. Now it does.

Pipeline per case:
  1. `agent.baselines.gpt_zeroshot.evaluate(case)` → top-1 predicted function
     (deliberately minimal prompt — no RAG, no static facts, no tool-use)
  2. `agent.nodes.builder.build_poc(...)` → single-shot PoC for that function
  3. `agent.nodes.verifier.verify(...)` → single forge run; no retry, no cascade
  4. Record verdict in same schema as `smoke_<arm>.json`

Output:
  data/evaluation/smoke_gpt-zeroshot-e2e.json
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from agent.baselines.gpt_zeroshot import evaluate as zs_evaluate  # noqa: E402
from agent.nodes.builder import build_poc  # noqa: E402
from agent.nodes.verifier import verify  # noqa: E402
from agent.state import empty_annotations  # noqa: E402


SMOKE_PATH = REPO_ROOT / "data" / "dataset" / "smoke_set.json"
OUT_PATH = REPO_ROOT / "data" / "evaluation" / "smoke_gpt-zeroshot-e2e.json"

PROMPT_RATE_PER_1K = 0.00025  # gpt-5-mini estimate
COMPLETION_RATE_PER_1K = 0.002


def _is_recall_hit(predicted: str, gt: str) -> bool:
    if not predicted or not gt:
        return False
    p = predicted.lower().strip()
    g = gt.lower().strip()
    return p == g or p in g or g in p


def main() -> int:
    smoke = json.loads(SMOKE_PATH.read_text(encoding="utf-8"))
    cases = smoke.get("cases", [])
    print(f"[zeroshot-e2e] running on {len(cases)} smoke cases")

    records: list[dict] = []
    running_usd = 0.0
    t_start = time.time()

    for i, case in enumerate(cases, 1):
        case_id = case["id"]
        contract_name = case["contract_name"]
        contract_source = case.get("contract_source", "")
        gt_fn = case.get("vulnerable_function", "")
        verifier_mode = case.get("verifier_mode")

        ann = dict(empty_annotations())
        ann["case_id"] = case_id
        ann["contract_name"] = contract_name

        # Step 1: zero-shot prediction (mimic Case-like object).
        case_obj = SimpleNamespace(
            id=case_id,
            contract_name=contract_name,
            contract_source=contract_source,
            vulnerable_function=gt_fn,
        )
        zs_pred = zs_evaluate(case_obj)
        target_function = (zs_pred.predicted_function or "").strip()

        # zero-shot uses its own annotations (separate ann inside evaluate).
        # Pull token counts from PredictionRecord:
        zs_p = int(zs_pred.tokens_prompt or 0)
        zs_c = int(zs_pred.tokens_completion or 0)

        if not target_function:
            verdict_str = "skipped"
            poc_code = ""
            execution_trace = ""
            error_summary = "zero-shot returned no flagged functions"
            wall_clock_s = 0.0
            ann["tokens_prompt"] = zs_p
            ann["tokens_completion"] = zs_c
            ann["llm_calls"] = zs_pred.llm_calls or 0
        else:
            # Step 2: builder (single shot, empty error history).
            t0 = time.time()
            poc_code = build_poc(
                contract_source=contract_source,
                contract_name=contract_name,
                target_function=target_function,
                hypothesis="Zero-shot baseline: no hypothesis text",
                error_history=[],
                annotations=ann,
            )
            # Step 3: verifier (single shot, no retry).
            v = verify(
                contract_source=contract_source,
                contract_name=contract_name,
                poc_code=poc_code,
                verifier_mode=verifier_mode,
            )
            verdict_str = v["execution_result"]
            execution_trace = v["execution_trace"]
            error_summary = v["error_summary"]
            wall_clock_s = round(time.time() - t0, 2)

            # Add zero-shot tokens to ann (which builder also wrote into).
            ann["tokens_prompt"] = ann.get("tokens_prompt", 0) + zs_p
            ann["tokens_completion"] = ann.get("tokens_completion", 0) + zs_c

        tp = int(ann.get("tokens_prompt", 0))
        tc = int(ann.get("tokens_completion", 0))
        case_usd = (tp / 1000.0) * PROMPT_RATE_PER_1K + (
            tc / 1000.0
        ) * COMPLETION_RATE_PER_1K
        running_usd += case_usd

        rec = {
            "arm": "gpt-zeroshot-e2e",
            "case_id": case_id,
            "verdict": verdict_str,
            "finding_confirmed": verdict_str == "pass",
            "target_function": target_function,
            "ground_truth_function": gt_fn,
            "recall_at_1": _is_recall_hit(target_function, gt_fn),
            "tokens_prompt": tp,
            "tokens_completion": tc,
            "case_usd": round(case_usd, 4),
            "running_usd": round(running_usd, 4),
            "wall_clock_s": wall_clock_s,
            "poc_attempts": 1,
            "cascade_depth": 1 if target_function else 0,
            "reflection_calls": 0,
            "abstained": False,
            "error_summary": (error_summary or "")[:200],
            "method": "gpt_zeroshot + builder + forge",
        }
        records.append(rec)
        print(
            f"  [zeroshot-e2e] {i}/{len(cases)} {case_id}: "
            f"verdict={verdict_str} pred={target_function!r} gt={gt_fn!r} "
            f"hit={rec['recall_at_1']} ${case_usd:.4f} "
            f"(running ${running_usd:.4f})",
            flush=True,
        )
        OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUT_PATH.write_text(
            json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    elapsed = time.time() - t_start
    n = len(records)
    n_pass = sum(1 for r in records if r["verdict"] == "pass")
    n_skip = sum(1 for r in records if r["verdict"] == "skipped")
    n_recall = sum(1 for r in records if r["recall_at_1"])
    print()
    print(f"=== gpt-zeroshot-e2e summary (n={n}) ===")
    print(f"  Recall@1     : {n_recall}/{n} = {n_recall*100//n}%")
    print(f"  PoC pass     : {n_pass}/{n} = {n_pass*100//n}%")
    print(f"  skipped      : {n_skip}/{n}")
    print(f"  total wall   : {elapsed:.1f}s")
    print(f"  total USD    : ${running_usd:.4f}")
    print(f"  written to   : {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
