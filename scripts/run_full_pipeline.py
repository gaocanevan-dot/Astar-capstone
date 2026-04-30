#!/usr/bin/env python3
"""Full-pipeline driver — analyst → builder → verifier, retry on fail_error.

Usage:
    # smoke (3 cases, real forge)
    python scripts/run_full_pipeline.py --limit 3

    # demo contract only (self-contained, most likely to compile)
    python scripts/run_full_pipeline.py --demo

    # skip forge (pipeline structure check, still calls LLM x2)
    python scripts/run_full_pipeline.py --limit 3 --skip-forge

Outputs:
    data/evaluation/full_pipeline_predictions.json
    data/evaluation/full_pipeline_summary.md
"""

from __future__ import annotations

import argparse
import json
import os
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
from agent.graph import run_pipeline  # noqa: E402


def load_cases(eval_path: Path) -> list[Case]:
    data = json.loads(eval_path.read_text(encoding="utf-8"))
    return [Case(**c) for c in data.get("cases", [])]


def load_demo_case() -> Case:
    """The self-contained VulnerableAccessControl demo contract bundled in repo."""
    demo_path = REPO_ROOT / "data" / "contracts" / "VulnerableAccessControl.sol"
    source = demo_path.read_text(encoding="utf-8")
    return Case(
        id="DEMO-001",
        contract_source=source,
        contract_name="VulnerableAccessControl",
        ground_truth_label="vulnerable",
        source_type="code4rena_bad",
        project_name="demo",
        buildable=True,
        vulnerable_function="withdraw",
        vulnerability_type="access_control",
        severity="high",
    )


def pipeline_result_to_dict(r, case: Case) -> dict:
    """Serialize result + ground truth for the report."""
    d = asdict(r)
    d["ground_truth_function"] = case.vulnerable_function or ""
    d["buildable_hint"] = case.buildable
    d["source_type"] = case.source_type
    return d


def write_summary(results: list[dict], out_path: Path, elapsed_total: float) -> None:
    n = len(results)
    verdicts = {
        "pass": 0,
        "fail_revert_ac": 0,
        "fail_error_compile": 0,
        "fail_error_runtime": 0,
        "skipped": 0,
    }
    for r in results:
        v = r.get("execution_result", "skipped")
        verdicts[v] = verdicts.get(v, 0) + 1

    strict_analyst_hit = sum(
        1
        for r in results
        if r.get("target_function")
        and r["target_function"] == r.get("ground_truth_function", "")
    )
    loose_analyst_hit = sum(
        1
        for r in results
        if r.get("target_function") and r.get("ground_truth_function")
        and (
            r["target_function"].lower() == r["ground_truth_function"].lower()
            or r["target_function"].lower() in r["ground_truth_function"].lower()
            or r["ground_truth_function"].lower() in r["target_function"].lower()
        )
    )
    poc_pass = verdicts["pass"]
    ac_safe = verdicts["fail_revert_ac"]
    still_broken = verdicts["fail_error_compile"] + verdicts["fail_error_runtime"]
    skipped = verdicts["skipped"]
    total_retries = sum(max(0, r.get("poc_attempts", 1) - 1) for r in results)
    total_llm_calls = sum(r.get("annotations", {}).get("llm_calls", 0) for r in results)
    total_tokens = sum(
        r.get("annotations", {}).get("tokens_prompt", 0)
        + r.get("annotations", {}).get("tokens_completion", 0)
        for r in results
    )
    fingerprints = sorted(
        {
            r.get("annotations", {}).get("system_fingerprint", "")
            for r in results
            if r.get("annotations", {}).get("system_fingerprint")
        }
    )

    lines = []
    lines.append("# Full-Pipeline Summary (analyst + builder + verifier)")
    lines.append("")
    lines.append(f"- cases run: {n}")
    lines.append(f"- total wall-clock: {elapsed_total:.1f}s")
    lines.append(f"- total LLM calls: {total_llm_calls}")
    lines.append(f"- total tokens (prompt+completion): {total_tokens}")
    lines.append(f"- total builder retries: {total_retries}")
    lines.append(f"- system fingerprints: {', '.join(fingerprints) if fingerprints else 'none'}")
    lines.append("")
    lines.append("## Verdict distribution")
    lines.append("")
    lines.append("| Verdict | Count | % |")
    lines.append("|---------|-------|---|")
    for v in ("pass", "fail_revert_ac", "fail_error_compile", "fail_error_runtime", "skipped"):
        c = verdicts[v]
        pct = f"{c/n*100:.0f}%" if n else "-"
        lines.append(f"| {v} | {c} | {pct} |")
    lines.append("")
    lines.append("## Layer metrics")
    lines.append("")
    lines.append(f"- Analyst-level function-recall (strict): {strict_analyst_hit}/{n}")
    lines.append(f"- Analyst-level function-recall (loose):  {loose_analyst_hit}/{n}")
    lines.append(f"- End-to-end PoC-pass (forge test success): {poc_pass}/{n}")
    lines.append(f"- AC-intercepted (contract appears safe):  {ac_safe}/{n}")
    lines.append(f"- Retry-exhausted (likely compile/dep issue): {still_broken}/{n}")
    lines.append(f"- Skipped (empty source or no target):       {skipped}/{n}")
    lines.append("")
    lines.append("## Per-case outcomes")
    lines.append("")
    lines.append("| case_id | GT fn | Analyst pred | Verdict | Attempts | Reason |")
    lines.append("|---------|-------|--------------|---------|----------|--------|")
    for r in results:
        gt = r.get("ground_truth_function", "")
        pred = r.get("target_function", "")
        verdict = r.get("execution_result", "")
        attempts = r.get("poc_attempts", 0)
        reason = (r.get("finding_reason", "") or r.get("error_summary", ""))[:80]
        lines.append(
            f"| {r['case_id']} | `{gt}` | `{pred}` | {verdict} | {attempts} | {reason} |"
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--eval-set", default="data/dataset/eval_set.json")
    ap.add_argument("--predictions-out", default="data/evaluation/full_pipeline_predictions.json")
    ap.add_argument("--summary-out", default="data/evaluation/full_pipeline_summary.md")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--demo", action="store_true", help="run only the bundled VulnerableAccessControl demo")
    ap.add_argument("--skip-forge", action="store_true", help="skip verifier, return after builder")
    ap.add_argument("--max-retries", type=int, default=3)
    ap.add_argument(
        "--use-langgraph",
        action="store_true",
        help="Use LangGraph-native 4-arm implementation (src/agent/graph_lg.py) instead of sequential Python graph",
    )
    ap.add_argument(
        "--arm",
        default="full",
        choices=["full", "no-static", "no-rag", "no-verify-loop"],
        help="LangGraph arm to compile. Only effective with --use-langgraph.",
    )
    ap.add_argument("--use-rag", action="store_true", help="inject RAG few-shot into analyst")
    ap.add_argument(
        "--rag-source",
        default="data/evaluation/single_agent_predictions.json",
        help="predictions JSON to mine for the RAG corpus (strict hits only). Ignored if --rag-dataset is set.",
    )
    ap.add_argument(
        "--rag-dataset",
        default=None,
        help="Path to a curated RAG dataset (documents format, e.g. data/dataset/rag_training_dataset.json). Overrides --rag-source.",
    )
    args = ap.parse_args()

    if args.demo:
        cases = [load_demo_case()]
        print("Demo mode: running only VulnerableAccessControl.sol")
    else:
        eval_path = Path(args.eval_set)
        cases = load_cases(eval_path)
        if args.limit:
            # Skip first 3 NOYA entries by default (NOYA-H-04/NOYA-M-03 empty + NOYA-H-08 slow)
            # but keep deterministic: just take first N
            cases = cases[: args.limit]
        print(f"Loaded {len(cases)} cases from {eval_path}")

    from agent.adapters.rag import (
        load_store_from_predictions,
        load_store_from_rag_dataset,
    )
    rag_store = None
    if getattr(args, "use_rag", False) or os.environ.get("PIPE_USE_RAG") == "1":
        rag_dataset = getattr(args, "rag_dataset", None)
        if rag_dataset:
            rag_store = load_store_from_rag_dataset(rag_dataset)
            print(f"RAG: enabled, corpus={len(rag_store)} docs from {rag_dataset}", flush=True)
        else:
            rag_store = load_store_from_predictions(
                getattr(args, "rag_source", "data/evaluation/single_agent_predictions.json"),
                args.eval_set,
            )
            print(f"RAG: enabled, corpus={len(rag_store)} hit cases from predictions", flush=True)

    if args.use_langgraph:
        from agent.graph_lg import run_single_case as _lg_run
        print(f"LangGraph: enabled, arm={args.arm}", flush=True)

    t_start = time.time()
    results: list[dict] = []
    for i, case in enumerate(cases, 1):
        print(f"[{i}/{len(cases)}] {case.id} ({case.contract_name})...", flush=True)
        try:
            if args.use_langgraph:
                final = _lg_run(
                    case_id=case.id,
                    contract_source=case.contract_source,
                    contract_name=case.contract_name,
                    arm=args.arm,
                    max_retries=args.max_retries,
                    rag_store=rag_store,
                )
                from agent.graph import PipelineResult
                res = PipelineResult(
                    case_id=case.id,
                    contract_name=case.contract_name,
                    target_function=final.get("target_function", ""),
                    hypothesis=final.get("hypothesis", ""),
                    confidence=final.get("confidence", 0.0),
                    poc_code=final.get("verification_poc", ""),
                    poc_attempts=final.get("poc_attempts", 0),
                    error_history=final.get("error_history", []),
                    execution_result=final.get("execution_result", "pending"),
                    execution_trace=final.get("execution_trace", ""),
                    error_summary=final.get("error_summary", ""),
                    annotations=final.get("annotations", {}),
                    finding_confirmed=final.get("finding_confirmed", False),
                    finding_reason=final.get("finding_reason", ""),
                    wall_clock_s=final.get("wall_clock_s", 0.0),
                )
            else:
                res = run_pipeline(
                    case_id=case.id,
                    contract_source=case.contract_source,
                    contract_name=case.contract_name,
                    max_retries=args.max_retries,
                    skip_forge=args.skip_forge,
                    rag_store=rag_store,
                )
        except Exception as exc:
            # Isolate per-case crash so a single broken contract does not lose
            # all prior work; log the error into the record and continue.
            from agent.graph import PipelineResult
            res = PipelineResult(
                case_id=case.id,
                contract_name=case.contract_name,
                target_function="",
                hypothesis="",
                confidence=0.0,
                execution_result="fail_error_runtime",
                finding_reason=f"unhandled {type(exc).__name__}: {exc}"[:300],
            )
        d = pipeline_result_to_dict(res, case)
        results.append(d)
        # Write incrementally so a later crash doesn't lose progress
        try:
            out = Path(args.predictions_out)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(
                json.dumps(results, indent=2, ensure_ascii=False, default=str),
                encoding="utf-8",
            )
        except Exception:  # pragma: no cover
            pass
        print(
            f"    → verdict={res.execution_result} attempts={res.poc_attempts} "
            f"pred={res.target_function!r} gt={case.vulnerable_function!r} "
            f"reason={res.finding_reason[:100]!r}",
            flush=True,
        )

    elapsed_total = time.time() - t_start

    Path(args.predictions_out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.predictions_out).write_text(
        json.dumps(results, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )

    write_summary(results, Path(args.summary_out), elapsed_total)

    print()
    print(f"Summary: {args.summary_out}")
    print(f"Predictions: {args.predictions_out}")
    print(f"Elapsed: {elapsed_total:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
