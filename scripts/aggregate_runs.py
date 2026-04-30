#!/usr/bin/env python3
"""Aggregate baseline + pipeline runs into a single RAG-ablation summary table.

Expects per-run prediction files under data/evaluation/:
  - baseline_slither_predictions.json
  - baseline_gpt_zeroshot_predictions.json
  - full_pipeline_predictions.json            (no RAG, the baseline)
  - full_pipeline_rag_predictions.json        (+RAG)
  - single_agent_predictions.json             (optional, for analyst-only row)
  - single_agent_rag_static_predictions.json  (optional)

Outputs:
  data/evaluation/ABLATION_SUMMARY.md
"""

from __future__ import annotations

import json
from pathlib import Path


METHODS = [
    # (label, file, kind)
    ("Slither (baseline)",                     "baseline_slither_predictions.json",               "baseline"),
    ("GPT-X zero-shot (baseline)",             "baseline_gpt_zeroshot_predictions.json",          "baseline"),
    ("Single-agent analyst (no RAG)",          "single_agent_predictions.json",                   "analyst"),
    ("Single-agent + RAG (self-hits)",         "single_agent_rag_predictions.json",               "analyst"),
    ("Single-agent + RAG (curated 85 docs)",   "single_agent_ragcur_predictions.json",            "analyst"),
    ("Full pipeline (no RAG)",                 "full_pipeline_predictions.json",                  "pipeline"),
    ("Full pipeline + RAG (self-hits)",        "full_pipeline_rag_predictions.json",              "pipeline"),
    ("Full pipeline + RAG (curated 85 docs)",  "full_pipeline_ragcur_predictions.json",           "pipeline"),
]


def _load(path: Path) -> list | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _tally_baseline(rows: list[dict]) -> dict:
    n = len(rows)
    eval_rows = [r for r in rows if (r.get("ground_truth_function") or "").strip()]
    total = len(eval_rows)
    strict = sum(
        1 for r in eval_rows
        if r.get("predicted_function") and r["predicted_function"] == r["ground_truth_function"]
    )
    loose = sum(
        1 for r in eval_rows
        if r.get("predicted_function") and r["ground_truth_function"]
        and (
            r["predicted_function"].lower() in r["ground_truth_function"].lower()
            or r["ground_truth_function"].lower() in r["predicted_function"].lower()
        )
    )
    flagged = sum(1 for r in rows if r.get("flagged"))
    tokens = sum(r.get("tokens_prompt", 0) + r.get("tokens_completion", 0) for r in rows)
    llm_calls = sum(r.get("llm_calls", 0) for r in rows)
    wall = sum(r.get("wall_clock_seconds", 0) for r in rows)
    return {
        "n": n,
        "evaluable": total,
        "func_recall_strict": strict,
        "func_recall_loose": loose,
        "flagged_contract_level": flagged,
        "tokens": tokens,
        "llm_calls": llm_calls,
        "wall_s": wall,
        "poc_pass": None,
        "retries": None,
    }


def _tally_analyst(rows: list[dict]) -> dict:
    # same analyst shape as baseline's contract-level-is-irrelevant view
    n = len(rows)
    eval_rows = [r for r in rows if (r.get("ground_truth_function") or "").strip()]
    total = len(eval_rows)
    strict = sum(
        1 for r in eval_rows
        if r.get("predicted_function") and r["predicted_function"] == r["ground_truth_function"]
    )
    loose = sum(
        1 for r in eval_rows
        if r.get("predicted_function") and r["ground_truth_function"]
        and (
            r["predicted_function"].lower() in r["ground_truth_function"].lower()
            or r["ground_truth_function"].lower() in r["predicted_function"].lower()
        )
    )
    tokens = sum(r.get("tokens_prompt", 0) + r.get("tokens_completion", 0) for r in rows)
    llm_calls = sum(r.get("llm_calls", 0) for r in rows)
    return {
        "n": n,
        "evaluable": total,
        "func_recall_strict": strict,
        "func_recall_loose": loose,
        "flagged_contract_level": None,
        "tokens": tokens,
        "llm_calls": llm_calls,
        "wall_s": sum(r.get("wall_clock_seconds", 0) for r in rows),
        "poc_pass": None,
        "retries": None,
    }


def _tally_pipeline(rows: list[dict]) -> dict:
    n = len(rows)
    eval_rows = [r for r in rows if (r.get("ground_truth_function") or "").strip()]
    total = len(eval_rows)
    strict = sum(
        1 for r in eval_rows
        if r.get("target_function") and r["target_function"] == r["ground_truth_function"]
    )
    loose = sum(
        1 for r in eval_rows
        if r.get("target_function") and r["ground_truth_function"]
        and (
            r["target_function"].lower() in r["ground_truth_function"].lower()
            or r["ground_truth_function"].lower() in r["target_function"].lower()
        )
    )
    poc_pass = sum(1 for r in rows if r.get("execution_result") == "pass")
    poc_ac_safe = sum(1 for r in rows if r.get("execution_result") == "fail_revert_ac")
    poc_err = sum(
        1
        for r in rows
        if r.get("execution_result")
        in ("fail_error", "fail_error_compile", "fail_error_runtime")
    )
    poc_skip = sum(1 for r in rows if r.get("execution_result") == "skipped")
    retries = sum(max(0, r.get("poc_attempts", 1) - 1) for r in rows)
    tokens = sum(
        (r.get("annotations", {}) or {}).get("tokens_prompt", 0)
        + (r.get("annotations", {}) or {}).get("tokens_completion", 0)
        for r in rows
    )
    llm_calls = sum((r.get("annotations", {}) or {}).get("llm_calls", 0) for r in rows)
    return {
        "n": n,
        "evaluable": total,
        "func_recall_strict": strict,
        "func_recall_loose": loose,
        "flagged_contract_level": poc_pass,  # pass ~= strong "vulnerable" signal
        "tokens": tokens,
        "llm_calls": llm_calls,
        "wall_s": sum(r.get("wall_clock_s", 0) for r in rows),
        "poc_pass": poc_pass,
        "poc_ac_safe": poc_ac_safe,
        "poc_err": poc_err,
        "poc_skip": poc_skip,
        "retries": retries,
    }


def _fmt_rate(hit: int | None, total: int | None) -> str:
    if hit is None or total is None or total == 0:
        return "-"
    return f"{hit}/{total} ({hit/total*100:.1f}%)"


def main():
    root = Path("data/evaluation")
    rows: list[tuple[str, dict]] = []

    for label, fname, kind in METHODS:
        data = _load(root / fname)
        if data is None:
            rows.append((label, {"missing": True, "file": fname}))
            continue
        if kind == "baseline":
            t = _tally_baseline(data)
        elif kind == "analyst":
            t = _tally_analyst(data)
        elif kind == "pipeline":
            t = _tally_pipeline(data)
        else:
            t = {}
        rows.append((label, t))

    # Build markdown
    out: list[str] = []
    out.append("# Ablation Summary (RAG on/off + baselines)")
    out.append("")
    out.append("Dataset: 42-case Code4rena access-control bad cases (2 empty-source, 40 evaluable).")
    out.append("")
    out.append("## Main results")
    out.append("")
    out.append("| Method | N | Flagged | Func-Recall (strict) | Func-Recall (loose) | PoC-pass | Retries | LLM calls | Tokens |")
    out.append("|--------|---|---------|----------------------|---------------------|----------|---------|-----------|--------|")
    for label, t in rows:
        if t.get("missing"):
            out.append(f"| {label} | *missing:* `{t['file']}` | | | | | | | |")
            continue
        flagged_rate = _fmt_rate(t["flagged_contract_level"], t["n"]) if t["flagged_contract_level"] is not None else "-"
        out.append(
            f"| {label} | {t['n']} | {flagged_rate} | "
            f"{_fmt_rate(t['func_recall_strict'], t['evaluable'])} | "
            f"{_fmt_rate(t['func_recall_loose'], t['evaluable'])} | "
            f"{_fmt_rate(t['poc_pass'], t['n']) if t.get('poc_pass') is not None else '-'} | "
            f"{t.get('retries', 0) if t.get('retries') is not None else '-'} | "
            f"{t.get('llm_calls', 0)} | {t.get('tokens', 0)} |"
        )
    out.append("")
    out.append("## Pipeline-row breakdown (verdict distribution)")
    out.append("")
    out.append("| Method | pass | fail_revert_ac | fail_error | skipped |")
    out.append("|--------|------|----------------|------------|---------|")
    for label, t in rows:
        if t.get("missing") or t.get("poc_pass") is None:
            continue
        out.append(
            f"| {label} | {t.get('poc_pass', 0)} | {t.get('poc_ac_safe', 0)} | "
            f"{t.get('poc_err', 0)} | {t.get('poc_skip', 0)} |"
        )
    out.append("")
    out.append("## Notes")
    out.append("")
    out.append(
        "- Dataset currently has **42 unique cases** (per US-002 dedup finding), "
        "below the plan target of 150. Numbers here are feasibility signals, not statistical claims."
    )
    out.append(
        "- All dataset cases are labeled vulnerable → Precision/F1 require safe cases "
        "(US-003, deferred). Current table reports Recall-side metrics only."
    )
    out.append(
        "- \"Flagged\" for pipeline rows = cases where forge confirmed the PoC "
        "(`execution_result == pass`). For baselines it is the raw contract-level flag."
    )
    out.append(
        "- Static analyzer (US-007) is written but intentionally excluded from ablation per "
        "user direction — only RAG on/off is ablated this round."
    )

    out_path = root / "ABLATION_SUMMARY.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(out), encoding="utf-8")
    print(f"wrote {out_path}")
    print()
    # Echo to stdout
    for label, t in rows:
        print(f"  {label}: {t}")


if __name__ == "__main__":
    main()
