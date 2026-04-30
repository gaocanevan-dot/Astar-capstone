#!/usr/bin/env python3
"""Single-agent analyst runner — loops over eval_set.json, calls the analyst
node once per case, writes per-case predictions + aggregate summary.

Usage:
    # smoke (3 cases)
    python scripts/run_single_agent.py --limit 3

    # full 42-case run
    python scripts/run_single_agent.py

    # dry-run (no LLM calls, prints schema check only)
    python scripts/run_single_agent.py --dry-run

Outputs:
    data/evaluation/single_agent_predictions.json
    data/evaluation/single_agent_summary.md
"""

from __future__ import annotations

import argparse
import io
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

# UTF-8 stdout on Windows
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from agent.adapters.rag import (  # noqa: E402
    EmbeddingRagStore,
    TfidfRagStore,
    format_few_shot_context,
    load_embedding_store_from_rag_dataset,
    load_store_from_predictions,
    load_store_from_rag_dataset,
)
from agent.adapters.static_analyzer import analyze as static_analyze  # noqa: E402
from agent.data.schema import Case, EvalSet  # noqa: E402
from agent.eval.metrics import compute_analyst_recall  # noqa: E402
from agent.nodes.analyst import analyze, analyze_consistent  # noqa: E402
from agent.state import empty_annotations  # noqa: E402


def load_eval_set(path: Path) -> EvalSet:
    data = json.loads(path.read_text(encoding="utf-8"))
    return EvalSet(cases=[Case(**c) for c in data.get("cases", [])])


def run_one(
    case: Case,
    rag_store: TfidfRagStore | None = None,
    use_static: bool = False,
    static_filtered: bool = False,
    n_consistency: int = 1,
) -> dict:
    annotations = empty_annotations()
    annotations["case_id"] = case.id
    annotations["contract_name"] = case.contract_name
    t0 = time.time()
    if not case.contract_source.strip():
        return {
            "case_id": case.id,
            "contract_name": case.contract_name,
            "ground_truth_function": case.vulnerable_function or "",
            "predicted_function": "",
            "candidates": [],
            "hypothesis": "",
            "confidence": 0.0,
            "reasoning": "",
            "buildable": False,
            "skipped_reason": "empty contract_source",
            "tokens_prompt": 0,
            "tokens_completion": 0,
            "llm_calls": 0,
            "system_fingerprint": "",
            "wall_clock_seconds": 0.0,
        }

    static_context = ""
    if use_static:
        try:
            facts = static_analyze(case.contract_source, case.contract_name)
            static_context = (
                facts.suspicious_summary() if static_filtered else facts.compact_summary()
            )
        except Exception as exc:  # pragma: no cover
            static_context = f"(static analyzer failed: {exc})"

    rag_few_shot = ""
    if rag_store is not None and len(rag_store) > 0:
        retrieved = rag_store.retrieve(
            case.contract_source, top_k=3, exclude_id=case.id
        )
        rag_few_shot = format_few_shot_context(retrieved)

    try:
        if n_consistency > 1:
            pred = analyze_consistent(
                case.contract_source,
                case.contract_name,
                annotations,
                static_context=static_context,
                rag_few_shot=rag_few_shot,
                n_runs=n_consistency,
            )
        else:
            pred = analyze(
                case.contract_source,
                case.contract_name,
                annotations,
                static_context=static_context,
                rag_few_shot=rag_few_shot,
            )
        error = None
    except Exception as exc:  # pragma: no cover - runtime errors captured per case
        pred = {
            "target_function": "",
            "candidates": [],
            "hypothesis": "",
            "confidence": 0.0,
            "reasoning": "",
        }
        error = f"{type(exc).__name__}: {exc}"
    elapsed = time.time() - t0

    return {
        "case_id": case.id,
        "contract_name": case.contract_name,
        "ground_truth_function": case.vulnerable_function or "",
        "predicted_function": pred["target_function"],
        "candidates": pred.get("candidates", []),
        "hypothesis": pred["hypothesis"],
        "confidence": pred["confidence"],
        "reasoning": pred["reasoning"],
        "buildable": case.buildable,
        "tokens_prompt": annotations.get("tokens_prompt", 0),
        "tokens_completion": annotations.get("tokens_completion", 0),
        "llm_calls": annotations.get("llm_calls", 0),
        "system_fingerprint": annotations.get("system_fingerprint", ""),
        "wall_clock_seconds": round(elapsed, 3),
        "error": error,
    }


def write_summary(
    predictions: list[dict],
    recall,
    out_path: Path,
    eval_set_path: Path,
    elapsed_total: float,
) -> None:
    total_tokens_prompt = sum(p.get("tokens_prompt", 0) for p in predictions)
    total_tokens_completion = sum(
        p.get("tokens_completion", 0) for p in predictions
    )
    total_llm_calls = sum(p.get("llm_calls", 0) for p in predictions)
    skipped = [p for p in predictions if p.get("skipped_reason")]
    errored = [p for p in predictions if p.get("error")]
    fingerprints = sorted({p.get("system_fingerprint", "") for p in predictions if p.get("system_fingerprint")})

    lines = []
    lines.append("# Single-Agent Analyst Summary")
    lines.append("")
    lines.append(f"- eval_set: `{eval_set_path}`")
    lines.append(f"- total cases: {len(predictions)}")
    lines.append(f"- evaluable cases (have ground truth): {recall.total}")
    lines.append(f"- skipped (empty source): {len(skipped)}")
    lines.append(f"- errored: {len(errored)}")
    lines.append("")
    lines.append("## Analyst Recall (function-level)")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Strict Recall (exact name, top-1) | {recall.recall_strict:.2%} ({recall.hits_strict}/{recall.total}) |")
    lines.append(f"| Loose Recall (substring, top-1) | {recall.recall_loose:.2%} ({recall.hits_loose}/{recall.total}) |")
    if recall.recall_at_k:
        for k in sorted(recall.recall_at_k):
            lines.append(
                f"| hit@{k} (any of top-{k} matches GT) | "
                f"{recall.recall_at_k[k]:.2%} ({recall.hits_at_k[k]}/{recall.total}) |"
            )
    lines.append("")
    lines.append("## Compute")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Total LLM calls | {total_llm_calls} |")
    lines.append(f"| Total prompt tokens | {total_tokens_prompt} |")
    lines.append(f"| Total completion tokens | {total_tokens_completion} |")
    lines.append(f"| Wall-clock total (s) | {elapsed_total:.1f} |")
    lines.append(f"| System fingerprints | {', '.join(fingerprints) if fingerprints else 'none'} |")
    lines.append("")

    lines.append("## Per-case outcomes")
    lines.append("")
    lines.append("| case_id | GT function | Predicted (top-1) | Top-3 candidates | hit@1 | hit@3 |")
    lines.append("|---------|-------------|-------------------|------------------|-------|-------|")
    for c in recall.per_case:
        hit1 = "✓" if c.get("hit_at_1") or c["strict_hit"] else "✗"
        hit3 = "✓" if c.get("hit_at_3") else "✗"
        cands = ", ".join(f"`{x}`" for x in (c.get("candidates") or [])[:3])
        lines.append(
            f"| {c['case_id']} | `{c['ground_truth_function']}` | "
            f"`{c['predicted_function']}` | {cands or '—'} | {hit1} | {hit3} |"
        )
    if skipped:
        lines.append("")
        lines.append("## Skipped (empty source)")
        lines.append("")
        for s in skipped:
            lines.append(f"- {s['case_id']} ({s['contract_name']}): {s['skipped_reason']}")
    if errored:
        lines.append("")
        lines.append("## Errored")
        lines.append("")
        for e in errored:
            lines.append(f"- {e['case_id']}: `{e['error']}`")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--eval-set", default="data/dataset/eval_set.json", help="path to eval_set.json"
    )
    ap.add_argument(
        "--predictions-out",
        default="data/evaluation/single_agent_predictions.json",
    )
    ap.add_argument("--summary-out", default="data/evaluation/single_agent_summary.md")
    ap.add_argument("--limit", type=int, default=None, help="limit to first N cases (smoke)")
    ap.add_argument("--dry-run", action="store_true", help="skip LLM calls")
    ap.add_argument(
        "--use-rag",
        action="store_true",
        help="Inject RAG few-shot context (uses prior single-agent hits as corpus)",
    )
    ap.add_argument(
        "--rag-source",
        default="data/evaluation/single_agent_predictions.json",
        help="Predictions JSON to mine for RAG corpus (strict hits only). Ignored if --rag-dataset is set.",
    )
    ap.add_argument(
        "--rag-dataset",
        default=None,
        help="Path to a curated RAG dataset (documents format, e.g. data/dataset/rag_training_dataset.json). Overrides --rag-source.",
    )
    ap.add_argument(
        "--rag-embedding",
        action="store_true",
        help="Use OpenAI text-embedding-3-small for retrieval instead of TF-IDF. Requires --rag-dataset.",
    )
    ap.add_argument(
        "--use-static",
        action="store_true",
        help="Inject static-analysis facts (Slither + regex fallback)",
    )
    ap.add_argument(
        "--static-filtered",
        action="store_true",
        help="Use suspicious-only filter (external/public + state-changing + no AC mod) instead of dumping all functions. Requires --use-static.",
    )
    ap.add_argument(
        "--n-consistency",
        type=int,
        default=1,
        help="Self-consistency: run analyst N times and vote on top-3 (default 1 = no SC). Multiplies LLM cost by N.",
    )
    args = ap.parse_args()

    eval_path = Path(args.eval_set)
    eval_set = load_eval_set(eval_path)
    cases = eval_set.cases[: args.limit] if args.limit else eval_set.cases
    print(f"Loaded {len(cases)}/{len(eval_set.cases)} cases from {eval_path}", flush=True)

    if args.dry_run:
        print("DRY RUN: schema valid, not calling LLM")
        return 0

    rag_store = None
    if args.use_rag:
        if args.rag_dataset:
            if args.rag_embedding:
                rag_store = load_embedding_store_from_rag_dataset(args.rag_dataset)
                # Force index now so first retrieve is fast & cache fills upfront
                rag_store.index()
                print(f"RAG corpus (EMBEDDING text-embedding-3-small) loaded from {args.rag_dataset}: {len(rag_store)} docs", flush=True)
            else:
                rag_store = load_store_from_rag_dataset(args.rag_dataset)
                print(f"RAG corpus (TF-IDF) loaded from {args.rag_dataset}: {len(rag_store)} docs", flush=True)
        else:
            if args.rag_embedding:
                ap.error("--rag-embedding requires --rag-dataset (predictions-mined corpus only supported in TF-IDF mode)")
            rag_store = load_store_from_predictions(args.rag_source, args.eval_set)
            print(f"RAG corpus (TF-IDF) loaded from predictions: {len(rag_store)} prior-hit cases", flush=True)

    if args.use_static:
        mode = "FILTERED (suspicious-only)" if args.static_filtered else "FULL (all functions)"
        print(f"Static analysis: ENABLED ({mode})", flush=True)
    if args.n_consistency > 1:
        print(f"Self-consistency: ENABLED (N={args.n_consistency} runs per case)", flush=True)

    t_start = time.time()
    predictions: list[dict] = []
    for i, case in enumerate(cases, 1):
        print(f"[{i}/{len(cases)}] {case.id} ({case.contract_name})...", end="", flush=True)
        row = run_one(
            case,
            rag_store=rag_store,
            use_static=args.use_static,
            static_filtered=args.static_filtered,
            n_consistency=args.n_consistency,
        )
        predictions.append(row)
        pred = row.get("predicted_function", "")
        gt = row.get("ground_truth_function", "")
        if row.get("skipped_reason"):
            print(f" SKIP ({row['skipped_reason']})")
        elif row.get("error"):
            print(f" ERROR ({row['error']})")
        else:
            match = "✓strict" if pred == gt else ("~loose" if pred and (pred.lower() in gt.lower() or gt.lower() in pred.lower()) else "✗miss")
            print(f" pred={pred!r} gt={gt!r} {match}")

    elapsed_total = time.time() - t_start

    out_pred = Path(args.predictions_out)
    out_pred.parent.mkdir(parents=True, exist_ok=True)
    out_pred.write_text(
        json.dumps(predictions, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    recall = compute_analyst_recall(predictions)
    write_summary(predictions, recall, Path(args.summary_out), eval_path, elapsed_total)

    print("")
    print(recall.summary_line())
    print(f"Total wall-clock: {elapsed_total:.1f}s  LLM calls: {sum(p.get('llm_calls', 0) for p in predictions)}")
    print(f"Summary: {args.summary_out}")
    print(f"Predictions: {args.predictions_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
