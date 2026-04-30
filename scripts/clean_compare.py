#!/usr/bin/env python3
"""Compute hit@k for every method, on both the FULL evaluable set (41) and a
CLEAN subset (32) where dirty labels (unknown_function, setUp, testExploit,
testMisleadingGetAddress) are excluded.

Output a single Markdown table with both columns side by side.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from agent.eval.metrics import compute_analyst_recall  # noqa: E402

DIRTY = {
    "unknown_function",
    "setUp",
    "testExploit",
    "testMisleadingGetAddress",
}


def load_predictions(path: str) -> list[dict]:
    p = Path(path)
    if not p.exists():
        return []
    return json.loads(p.read_text(encoding="utf-8"))


def shape(preds: list[dict], use_flagged_functions: bool = False) -> list[dict]:
    out = []
    for p in preds:
        cands = p.get("candidates")
        if cands is None and use_flagged_functions:
            cands = p.get("flagged_functions", [])
        # Full-pipeline outputs use `target_function`; copy it to predicted_function
        # and synthesize a 1-element candidates list so hit@k == hit@1 for that row.
        pred = p.get("predicted_function") or p.get("target_function") or ""
        if cands is None and pred:
            cands = [pred]
        out.append(
            {
                "case_id": p.get("case_id", ""),
                "ground_truth_function": p.get("ground_truth_function", ""),
                "predicted_function": pred,
                "candidates": cands or ([pred] if pred else []),
                "confidence": p.get("confidence", 1.0),
            }
        )
    return out


def filter_clean(preds: list[dict]) -> list[dict]:
    return [p for p in preds if (p.get("ground_truth_function") or "").strip() not in DIRTY]


def compute(preds: list[dict]) -> tuple[float, float, int, int, int]:
    """Return (hit@1, hit@3, total, hits@1, hits@3)."""
    if not preds:
        return 0.0, 0.0, 0, 0, 0
    r = compute_analyst_recall(preds, k_values=(1, 3))
    if r.recall_at_k:
        h1, h3 = r.recall_at_k[1], r.recall_at_k[3]
        hh1, hh3 = r.hits_at_k[1], r.hits_at_k[3]
    else:
        h1 = h3 = r.recall_strict
        hh1 = hh3 = r.hits_strict
    return h1, h3, r.total, hh1, hh3


METHODS = [
    ("Slither baseline", "data/evaluation/baseline_slither_predictions.json", True),
    ("GPT zero-shot (1-fn prompt)", "data/evaluation/baseline_gpt_zeroshot_predictions.json", True),
    ("GPT zero-shot (top-3 prompt)", "data/evaluation/baseline_gpt_zeroshot_top3_predictions.json", True),
    ("Single-agent (no RAG)", "data/evaluation/single_agent_predictions.json", False),
    ("Single-agent + RAG curated", "data/evaluation/single_agent_ragcur_predictions.json", False),
    ("Single-agent + static (top-k)", "data/evaluation/single_agent_topk_static_predictions.json", False),
    ("Single-agent + static (FILTERED) ⭐", "data/evaluation/single_agent_static_filtered_predictions.json", False),
    ("Single-agent SC=5 (self-consistency) ⭐", "data/evaluation/single_agent_sc5_predictions.json", False),
    ("Single-agent SC=5 + Embedding RAG 🆕", "data/evaluation/single_agent_sc5_embrag_predictions.json", False),
    ("Full pipeline (no RAG)", "data/evaluation/full_pipeline_predictions.json", False),
    ("Full pipeline + RAG curated", "data/evaluation/full_pipeline_ragcur_predictions.json", False),
]


def main() -> int:
    rows = []
    for name, path, use_ff in METHODS:
        raw = load_predictions(path)
        if not raw:
            rows.append((name, "(missing)", "(missing)", "(missing)", "(missing)"))
            continue
        all_p = shape(raw, use_flagged_functions=use_ff)
        clean_p = filter_clean(all_p)
        h1_a, h3_a, n_a, hh1_a, hh3_a = compute(all_p)
        h1_c, h3_c, n_c, hh1_c, hh3_c = compute(clean_p)
        rows.append(
            (
                name,
                f"{h1_a:.1%} ({hh1_a}/{n_a})",
                f"{h3_a:.1%} ({hh3_a}/{n_a})",
                f"{h1_c:.1%} ({hh1_c}/{n_c})",
                f"{h3_c:.1%} ({hh3_c}/{n_c})",
            )
        )

    out = ["# Clean-vs-Full Comparison", "",
           "Dirty labels excluded from CLEAN: `unknown_function`, `setUp`, `testExploit`, `testMisleadingGetAddress`.",
           "Empty-GT cases (GRA-H-01) already excluded by `evaluable` filter.",
           "",
           "| Method | hit@1 (full 41) | hit@3 (full 41) | hit@1 (clean 32) | hit@3 (clean 32) |",
           "|--------|------------------|------------------|-------------------|-------------------|"]
    for r in rows:
        out.append(f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]} |")

    txt = "\n".join(out)
    print(txt)
    Path("data/evaluation/CLEAN_COMPARE.md").write_text(txt, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
