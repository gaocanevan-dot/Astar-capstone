#!/usr/bin/env python3
"""Compute Precision@k and MRR for every method.

Clarifications:
- Our 42-case dataset has no labeled `safe` contracts, so contract-level
  Precision (TP / (TP+FP)) is undefined. We report function-level metrics.
- Precision@k per case = (#correct picks in top-k) / (#picks in top-k).
  Since GT is a single function, numerator is 0 or 1. Denominator varies:
  methods that output <3 candidates are NOT unfairly penalized.
- MRR per case = 1/rank if GT appears in top-k else 0.
- All metrics reported on both FULL (41 evaluable) and CLEAN (32) sets.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

DIRTY = {"unknown_function", "setUp", "testExploit", "testMisleadingGetAddress"}

METHODS = [
    ("Slither baseline", "data/evaluation/baseline_slither_predictions.json", True),
    ("GPT zero-shot (1-fn prompt)", "data/evaluation/baseline_gpt_zeroshot_predictions.json", True),
    ("GPT zero-shot (top-3 prompt)", "data/evaluation/baseline_gpt_zeroshot_top3_predictions.json", True),
    ("Single-agent (no RAG)", "data/evaluation/single_agent_predictions.json", False),
    ("Single-agent + RAG curated (TF-IDF)", "data/evaluation/single_agent_ragcur_predictions.json", False),
    ("Single-agent + static (top-k)", "data/evaluation/single_agent_topk_static_predictions.json", False),
    ("Single-agent + static (FILTERED)", "data/evaluation/single_agent_static_filtered_predictions.json", False),
    ("Single-agent SC=5 ⭐", "data/evaluation/single_agent_sc5_predictions.json", False),
    ("Single-agent SC=5 + Embedding RAG 🆕", "data/evaluation/single_agent_sc5_embrag_predictions.json", False),
    ("Full pipeline (no RAG)", "data/evaluation/full_pipeline_predictions.json", False),
]


def load(path: str) -> list[dict]:
    p = Path(path)
    if not p.exists():
        return []
    return json.loads(p.read_text(encoding="utf-8"))


def pick_candidates(pred: dict, use_flagged: bool) -> list[str]:
    """Extract top-k candidate list from one prediction record."""
    cands = pred.get("candidates")
    if cands is None and use_flagged:
        cands = pred.get("flagged_functions", [])
    if cands is None:
        # Full-pipeline: only top-1 via target_function
        top1 = pred.get("predicted_function") or pred.get("target_function") or ""
        cands = [top1] if top1 else []
    return [c for c in (cands or []) if isinstance(c, str) and c.strip()]


def compute_metrics(preds: list[dict], use_flagged: bool) -> dict:
    """Return dict with precision@1, precision@3, mrr, and raw counts."""
    evaluable = [p for p in preds if (p.get("ground_truth_function") or "").strip()]
    if not evaluable:
        return {"n": 0, "p_at_1": 0.0, "p_at_3": 0.0, "mrr": 0.0}

    n = len(evaluable)
    sum_p1_num = 0.0
    sum_p1_den = 0.0
    sum_p3_num = 0.0
    sum_p3_den = 0.0
    sum_rr = 0.0

    for p in evaluable:
        gt = (p.get("ground_truth_function") or "").strip()
        cands = pick_candidates(p, use_flagged)

        # Precision@1
        top1 = cands[:1]
        if top1:
            sum_p1_den += 1
            if top1[0] == gt:
                sum_p1_num += 1

        # Precision@3 — denominator = number of actual picks (may be < 3)
        top3 = cands[:3]
        if top3:
            sum_p3_den += len(top3)
            sum_p3_num += sum(1 for c in top3 if c == gt)

        # MRR — rank within top-3
        rr = 0.0
        for rank, c in enumerate(cands[:3], 1):
            if c == gt:
                rr = 1.0 / rank
                break
        sum_rr += rr

    return {
        "n": n,
        "p_at_1": (sum_p1_num / sum_p1_den) if sum_p1_den else 0.0,
        "p_at_3": (sum_p3_num / sum_p3_den) if sum_p3_den else 0.0,
        "mrr": sum_rr / n,
        "p_at_1_frac": f"{int(sum_p1_num)}/{int(sum_p1_den)}",
        "p_at_3_frac": f"{int(sum_p3_num)}/{int(sum_p3_den)}",
    }


def filter_clean(preds: list[dict]) -> list[dict]:
    return [p for p in preds if (p.get("ground_truth_function") or "").strip() not in DIRTY]


def main() -> int:
    rows = []
    for name, path, use_ff in METHODS:
        raw = load(path)
        if not raw:
            rows.append((name,) + ("(missing)",) * 6)
            continue
        evaluable = [p for p in raw if (p.get("ground_truth_function") or "").strip()]
        clean = filter_clean(raw)
        m_all = compute_metrics(evaluable, use_ff)
        m_clean = compute_metrics(clean, use_ff)
        rows.append(
            (
                name,
                f"{m_all['p_at_1']:.1%} ({m_all['p_at_1_frac']})",
                f"{m_all['p_at_3']:.1%} ({m_all['p_at_3_frac']})",
                f"{m_all['mrr']:.3f}",
                f"{m_clean['p_at_1']:.1%} ({m_clean['p_at_1_frac']})",
                f"{m_clean['p_at_3']:.1%} ({m_clean['p_at_3_frac']})",
                f"{m_clean['mrr']:.3f}",
            )
        )

    lines = [
        "# Function-level Precision & MRR",
        "",
        "**Contract-level precision is undefined** on this dataset because all 42 cases",
        "are labeled `vulnerable` (no safe cases → FP has no source).",
        "",
        "**Function-level Precision@k** = (correct picks in top-k) / (picks in top-k).",
        "Methods that output <3 candidates per case are NOT unfairly penalized —",
        "denominator uses actual pick count.",
        "",
        "**MRR** = mean reciprocal rank of GT within top-3 (0 if GT not in top-3).",
        "",
        "| Method | P@1 (41) | P@3 (41) | MRR (41) | P@1 (clean 32) | P@3 (clean 32) | MRR (clean 32) |",
        "|--------|----------|----------|----------|-----------------|-----------------|-----------------|",
    ]
    for r in rows:
        lines.append(f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]} | {r[5]} | {r[6]} |")

    txt = "\n".join(lines)
    print(txt)
    Path("data/evaluation/PRECISION_MRR.md").write_text(txt, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
