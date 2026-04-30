"""Evaluation metrics for single-agent analyst variant.

Two Recall flavors:
- strict: exact string match on vulnerable_function
- loose:  case-insensitive substring match (handles overload disambiguation,
          partial name recall)
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AnalystRecall:
    total: int
    hits_strict: int
    hits_loose: int
    recall_strict: float
    recall_loose: float
    per_case: list[dict]
    # Top-k metrics (empty dict if beam output not present)
    hits_at_k: dict[int, int] = None  # type: ignore[assignment]  # {1: n, 2: n, 3: n}
    recall_at_k: dict[int, float] = None  # type: ignore[assignment]

    def summary_line(self) -> str:
        base = (
            f"Analyst Recall: strict={self.recall_strict:.2%} "
            f"({self.hits_strict}/{self.total}), "
            f"loose={self.recall_loose:.2%} "
            f"({self.hits_loose}/{self.total})"
        )
        if self.recall_at_k:
            parts = ", ".join(
                f"hit@{k}={self.recall_at_k[k]:.2%} ({self.hits_at_k[k]}/{self.total})"
                for k in sorted(self.recall_at_k)
            )
            base += f" | {parts}"
        return base


def _is_strict_hit(predicted: str, truth: str) -> bool:
    return bool(predicted) and bool(truth) and predicted == truth


def _is_loose_hit(predicted: str, truth: str) -> bool:
    if not predicted or not truth:
        return False
    p = predicted.lower().strip()
    t = truth.lower().strip()
    return p == t or p in t or t in p


def compute_analyst_recall(
    predictions: list[dict], k_values: tuple[int, ...] = (1, 2, 3)
) -> AnalystRecall:
    """
    predictions: list of dicts with keys:
      - case_id: str
      - ground_truth_function: str (may be empty/None)
      - predicted_function: str       (top-1)
      - candidates: list[str]         (optional, top-k ordered)
      - confidence: float
    Only cases with non-empty ground_truth_function count toward recall.
    """
    evaluable = [p for p in predictions if (p.get("ground_truth_function") or "").strip()]
    total = len(evaluable)
    per_case: list[dict] = []
    hits_strict = 0
    hits_loose = 0
    hits_at_k: dict[int, int] = {k: 0 for k in k_values}
    has_any_candidates = any(isinstance(p.get("candidates"), list) and p["candidates"] for p in evaluable)

    for p in evaluable:
        truth = (p.get("ground_truth_function") or "").strip()
        pred = (p.get("predicted_function") or "").strip()
        s = _is_strict_hit(pred, truth)
        l = _is_loose_hit(pred, truth)
        if s:
            hits_strict += 1
        if l:
            hits_loose += 1

        # Top-k hit computation (only if candidates supplied)
        candidates = p.get("candidates") or []
        if isinstance(candidates, list):
            per_case_topk: dict[int, bool] = {}
            for k in k_values:
                top_k = [c for c in candidates[:k] if isinstance(c, str)]
                hit = any(_is_strict_hit(c.strip(), truth) for c in top_k)
                per_case_topk[k] = hit
                if hit:
                    hits_at_k[k] += 1
        else:
            per_case_topk = {k: False for k in k_values}

        per_case.append(
            {
                "case_id": p.get("case_id", ""),
                "ground_truth_function": truth,
                "predicted_function": pred,
                "candidates": candidates if isinstance(candidates, list) else [],
                "confidence": p.get("confidence", 0.0),
                "strict_hit": s,
                "loose_hit": l,
                **{f"hit_at_{k}": per_case_topk[k] for k in k_values},
            }
        )

    recall_strict = hits_strict / total if total else 0.0
    recall_loose = hits_loose / total if total else 0.0
    recall_at_k = (
        {k: (hits_at_k[k] / total if total else 0.0) for k in k_values}
        if has_any_candidates
        else None
    )

    return AnalystRecall(
        total=total,
        hits_strict=hits_strict,
        hits_loose=hits_loose,
        recall_strict=recall_strict,
        recall_loose=recall_loose,
        per_case=per_case,
        hits_at_k=hits_at_k if has_any_candidates else None,
        recall_at_k=recall_at_k,
    )
