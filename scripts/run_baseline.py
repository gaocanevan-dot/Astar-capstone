#!/usr/bin/env python3
"""Driver for the Slither / GPT-zeroshot baselines.

Usage:
    python scripts/run_baseline.py --method slither
    python scripts/run_baseline.py --method gpt_zeroshot
    python scripts/run_baseline.py --method slither --limit 5

Outputs:
    data/evaluation/baseline_{method}_predictions.json
    data/evaluation/baseline_{method}_summary.md
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from agent.data.schema import Case  # noqa: E402


def load_cases(eval_path: Path) -> list[Case]:
    data = json.loads(eval_path.read_text(encoding="utf-8"))
    return [Case(**c) for c in data.get("cases", [])]


def get_evaluator(method: str):
    if method == "slither":
        from agent.baselines.slither_baseline import evaluate
    elif method == "gpt_zeroshot":
        from agent.baselines.gpt_zeroshot import evaluate
    else:
        raise ValueError(f"unknown method: {method}")
    return evaluate


def write_summary(preds: list[dict], method: str, out_path: Path, elapsed: float):
    n = len(preds)
    evaluable = [p for p in preds if (p.get("ground_truth_function") or "").strip()]
    total = len(evaluable)
    hits_strict = sum(
        1 for p in evaluable
        if p.get("predicted_function") and p["predicted_function"] == p["ground_truth_function"]
    )
    hits_loose = sum(
        1 for p in evaluable
        if p.get("predicted_function") and p["ground_truth_function"]
        and (
            p["predicted_function"].lower() in p["ground_truth_function"].lower()
            or p["ground_truth_function"].lower() in p["predicted_function"].lower()
        )
    )
    # Contract-level: "flagged" = True treated as predicted-positive
    flagged_count = sum(1 for p in preds if p.get("flagged"))
    # All dataset cases are positives (no safe cases yet) → no FP measurable
    total_llm_calls = sum(p.get("llm_calls", 0) for p in preds)
    total_tokens = sum(p.get("tokens_prompt", 0) + p.get("tokens_completion", 0) for p in preds)

    lines = [
        f"# Baseline Summary — {method}",
        "",
        f"- cases: {n}",
        f"- evaluable (GT present): {total}",
        f"- flagged (contract-level positive): {flagged_count}",
        f"- elapsed: {elapsed:.1f}s",
        f"- total LLM calls: {total_llm_calls}",
        f"- total tokens: {total_tokens}",
        "",
        "## Function-level Recall",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Strict | {hits_strict}/{total} = {(hits_strict/total*100) if total else 0:.1f}% |",
        f"| Loose  | {hits_loose}/{total} = {(hits_loose/total*100) if total else 0:.1f}% |",
        "",
        "## Per-case",
        "",
        "| case_id | GT | flagged | primary pred | strict | loose | err |",
        "|---------|----|---------|--------------|--------|-------|-----|",
    ]
    for p in preds:
        gt = p.get("ground_truth_function", "")
        pred = p.get("predicted_function", "") or ""
        strict = "✓" if gt and pred == gt else "✗"
        loose = "✓" if gt and pred and (pred.lower() in gt.lower() or gt.lower() in pred.lower()) else "✗"
        err = (p.get("error") or "")[:50]
        lines.append(f"| {p['case_id']} | `{gt}` | {p.get('flagged')} | `{pred}` | {strict} | {loose} | {err} |")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--method", required=True, choices=["slither", "gpt_zeroshot"])
    ap.add_argument("--eval-set", default="data/dataset/eval_set.json")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--predictions-out", default=None)
    ap.add_argument("--summary-out", default=None)
    args = ap.parse_args()

    pred_path = Path(args.predictions_out or f"data/evaluation/baseline_{args.method}_predictions.json")
    sum_path = Path(args.summary_out or f"data/evaluation/baseline_{args.method}_summary.md")

    cases = load_cases(Path(args.eval_set))
    if args.limit:
        cases = cases[: args.limit]

    evaluator = get_evaluator(args.method)
    print(f"[{args.method}] running on {len(cases)} cases", flush=True)
    t0 = time.time()
    preds: list[dict] = []
    for i, case in enumerate(cases, 1):
        print(f"[{i}/{len(cases)}] {case.id} ({case.contract_name})...", end="", flush=True)
        rec = evaluator(case)
        d = asdict(rec)
        preds.append(d)
        marker = "flagged" if rec.flagged else "clean"
        pred = rec.predicted_function or "-"
        print(f" {marker} pred={pred!r} err={rec.error[:40]!r}", flush=True)

    elapsed = time.time() - t0
    pred_path.parent.mkdir(parents=True, exist_ok=True)
    pred_path.write_text(json.dumps(preds, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    write_summary(preds, args.method, sum_path, elapsed)
    print()
    print(f"Elapsed: {elapsed:.1f}s  Preds: {pred_path}  Summary: {sum_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
