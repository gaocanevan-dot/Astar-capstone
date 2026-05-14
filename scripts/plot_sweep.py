"""Plot the 4-arm ablation sweep results from data/evaluation/sweep_A*.json.

Generates 4 PNG files under data/evaluation/figures/:

  1. headline_metrics.png    — grouped bar: strict R@1, loose R@1, hit@3, PoC-pass, phantom-pass per arm
  2. recall_comparison.png   — focused: strict R@1 vs hit@3 (the most informative pair)
  3. cost_vs_recall.png      — scatter: $/case vs strict R@1
  4. verdict_distribution.png — stacked bar of forge verdicts per arm (A1/A2 only; A3/A4 don't run forge)

Usage:
    python scripts/plot_sweep.py
    python scripts/plot_sweep.py --out-dir custom/dir
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Callable

import matplotlib.pyplot as plt
import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_EVAL_DIR = REPO_ROOT / "data" / "evaluation"

# Pricing for cost calc — must match run_ablation_sweep.py
PRICE_PROMPT_PER_1K = 0.00025
PRICE_COMPLETION_PER_1K = 0.002

ARM_INFO = [
    ("A1", "sweep_A1_full_cascade.json", "Agent (full)\ncascade", "#1f77b4"),
    ("A2", "sweep_A2_no_cascade.json",   "Agent (top-1)\nno-cascade", "#ff7f0e"),
    ("A3", "sweep_A3_gpt_zeroshot.json", "GPT zero-shot\nbaseline", "#2ca02c"),
    ("A4", "sweep_A4_slither.json",      "Slither\nstatic", "#d62728"),
]


def _load(p: Path) -> list[dict]:
    if not p.is_file():
        raise FileNotFoundError(p)
    return json.loads(p.read_text(encoding="utf-8"))


def _gt_evaluable(r: dict) -> bool:
    gt = (r.get("ground_truth_function") or "").strip()
    return bool(gt) and gt != "Unknown"


def _pred(r: dict) -> str:
    return (r.get("target_function") or r.get("predicted_function") or "").strip()


def _strict_hit(r: dict) -> bool:
    return _pred(r) and _pred(r) == r.get("ground_truth_function", "")


def _loose_hit(r: dict) -> bool:
    p = _pred(r).lower()
    g = (r.get("ground_truth_function") or "").lower().strip()
    if not p or not g:
        return False
    return p == g or p in g or g in p


def _candidates(r: dict) -> list[str]:
    """Top-K candidates from various shapes."""
    ann = r.get("annotations") or {}
    cs = ann.get("top_k_candidates") or []
    if cs:
        return cs
    fl = r.get("flagged_functions") or []
    if fl:
        return fl
    p = _pred(r)
    return [p] if p else []


def _hit_at_k(r: dict, k: int = 3) -> bool:
    cands = _candidates(r)[:k]
    gt = r.get("ground_truth_function") or ""
    return any(c == gt for c in cands if c)


def _poc_pass(r: dict) -> bool:
    return r.get("execution_result") == "pass" or r.get("flagged") is True


def _phantom_pass(r: dict) -> bool:
    return _poc_pass(r) and not _strict_hit(r)


def _cost(r: dict) -> float:
    tp = r.get("tokens_prompt", 0) or (r.get("annotations") or {}).get("tokens_prompt", 0)
    tc = r.get("tokens_completion", 0) or (r.get("annotations") or {}).get("tokens_completion", 0)
    return tp / 1000 * PRICE_PROMPT_PER_1K + tc / 1000 * PRICE_COMPLETION_PER_1K


def compute_metrics(results: list[dict]) -> dict[str, float]:
    n = len(results)
    evaluable = [r for r in results if _gt_evaluable(r)]
    n_eval = len(evaluable)

    def rate(pred: Callable[[dict], bool], pool: list[dict]) -> float:
        return sum(1 for r in pool if pred(r)) / len(pool) * 100 if pool else 0.0

    return {
        "n_total": n,
        "n_evaluable": n_eval,
        "strict_r1": rate(_strict_hit, evaluable),
        "loose_r1": rate(_loose_hit, evaluable),
        "hit_at_3": rate(_hit_at_k, evaluable),
        "poc_pass": rate(_poc_pass, results),
        "phantom_pass": rate(_phantom_pass, results),
        "avg_cost_per_case": sum(_cost(r) for r in results) / n if n else 0.0,
    }


def plot_headline(metrics: dict[str, dict], out: Path) -> None:
    metric_labels = ["strict R@1", "loose R@1", "hit@3", "PoC-pass", "phantom-pass"]
    metric_keys = ["strict_r1", "loose_r1", "hit_at_3", "poc_pass", "phantom_pass"]

    arms = list(metrics.keys())
    n_arms = len(arms)
    n_metrics = len(metric_keys)

    x = np.arange(n_metrics)
    width = 0.8 / n_arms

    fig, ax = plt.subplots(figsize=(12, 6))

    for i, arm in enumerate(arms):
        vals = [metrics[arm][k] for k in metric_keys]
        label = next(a[2].replace("\n", " ") for a in ARM_INFO if a[0] == arm)
        color = next(a[3] for a in ARM_INFO if a[0] == arm)
        bars = ax.bar(x + i * width - 0.4 + width / 2, vals, width, label=label, color=color, edgecolor="black", linewidth=0.5)
        for bar, v in zip(bars, vals):
            ax.text(bar.get_x() + bar.get_width() / 2, v + 1, f"{v:.0f}",
                    ha="center", va="bottom", fontsize=8)

    ax.set_xticks(x)
    ax.set_xticklabels(metric_labels)
    ax.set_ylabel("Rate (%)")
    ax.set_title("Ablation Sweep — Headline Metrics (172 cases per arm)")
    ax.set_ylim(0, 100)
    ax.legend(loc="upper right", fontsize=9)
    ax.grid(axis="y", linestyle="--", alpha=0.4)
    plt.tight_layout()
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"wrote {out}")


def plot_recall_comparison(metrics: dict[str, dict], out: Path) -> None:
    arms = list(metrics.keys())
    labels = [next(a[2] for a in ARM_INFO if a[0] == arm) for arm in arms]
    strict = [metrics[a]["strict_r1"] for a in arms]
    hit3 = [metrics[a]["hit_at_3"] for a in arms]
    colors = [next(a[3] for a in ARM_INFO if a[0] == arm) for arm in arms]

    x = np.arange(len(arms))
    width = 0.38

    fig, ax = plt.subplots(figsize=(9, 5.5))
    b1 = ax.bar(x - width / 2, strict, width, label="strict R@1", color=colors, alpha=0.85, edgecolor="black", linewidth=0.5)
    b2 = ax.bar(x + width / 2, hit3, width, label="hit@3 (top-3 includes GT)", color=colors, alpha=0.45, edgecolor="black", linewidth=0.5, hatch="//")

    for bar, v in list(zip(b1, strict)) + list(zip(b2, hit3)):
        ax.text(bar.get_x() + bar.get_width() / 2, v + 1, f"{v:.0f}%",
                ha="center", va="bottom", fontsize=9)

    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=10)
    ax.set_ylabel("Recall (%)")
    ax.set_title("Recall@1 (strict, exact match) vs Recall@3 (top-3 covers GT)")
    ax.set_ylim(0, 80)
    ax.legend(loc="upper right", fontsize=9)
    ax.grid(axis="y", linestyle="--", alpha=0.4)
    plt.tight_layout()
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"wrote {out}")


def plot_cost_vs_recall(metrics: dict[str, dict], out: Path) -> None:
    fig, ax = plt.subplots(figsize=(9, 6))
    for arm in metrics:
        m = metrics[arm]
        cost = m["avg_cost_per_case"]
        r1 = m["strict_r1"]
        label = next(a[2].replace("\n", " ") for a in ARM_INFO if a[0] == arm)
        color = next(a[3] for a in ARM_INFO if a[0] == arm)
        ax.scatter(cost, r1, s=250, color=color, edgecolor="black", linewidth=1, label=label, zorder=3)
        ax.annotate(arm, (cost, r1), textcoords="offset points", xytext=(0, -22), ha="center", fontsize=10, fontweight="bold")
        ax.annotate(f"${cost*1000:.1f}/k case", (cost, r1), textcoords="offset points", xytext=(15, 8), ha="left", fontsize=8, alpha=0.6)

    ax.set_xlabel("Avg cost per case (USD)")
    ax.set_ylabel("Strict R@1 (%)")
    ax.set_title("Cost vs Recall — efficiency frontier (172 cases per arm)")
    ax.set_xscale("symlog", linthresh=1e-4)
    ax.set_ylim(-3, 55)
    ax.grid(linestyle="--", alpha=0.4)
    ax.legend(loc="lower right", fontsize=9)
    plt.tight_layout()
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"wrote {out}")


def plot_verdict_distribution(per_arm: dict[str, list[dict]], out: Path) -> None:
    """Stacked bar of forge verdicts per arm — A1/A2 (which actually run forge)."""
    arms_with_forge = ["A1", "A2"]
    verdict_order = ["pass", "fail_revert_ac", "fail_error_compile", "fail_error_runtime", "abstain", "skipped", "crashed"]
    color_map = {
        "pass": "#2ca02c",
        "fail_revert_ac": "#1f77b4",
        "fail_error_compile": "#ff7f0e",
        "fail_error_runtime": "#d62728",
        "abstain": "#9467bd",
        "skipped": "#7f7f7f",
        "crashed": "#000000",
    }

    counts: dict[str, dict[str, int]] = {}
    for arm in arms_with_forge:
        counts[arm] = {v: 0 for v in verdict_order}
        for r in per_arm[arm]:
            v = r.get("execution_result", "")
            if v not in counts[arm]:
                counts[arm][v] = 0
            counts[arm][v] += 1

    fig, ax = plt.subplots(figsize=(9, 5.5))
    bottom = np.zeros(len(arms_with_forge))
    x = np.arange(len(arms_with_forge))
    for v in verdict_order:
        vals = np.array([counts[a][v] for a in arms_with_forge])
        if vals.sum() == 0:
            continue
        ax.bar(x, vals, bottom=bottom, label=v, color=color_map[v], edgecolor="black", linewidth=0.5)
        for i, val in enumerate(vals):
            if val > 0:
                ax.text(x[i], bottom[i] + val / 2, str(val), ha="center", va="center", fontsize=8, color="white" if v == "crashed" else "black")
        bottom += vals

    labels = [next(a[2] for a in ARM_INFO if a[0] == arm) for arm in arms_with_forge]
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=10)
    ax.set_ylabel("Case count")
    ax.set_title("Forge verdict distribution — A1 vs A2 (172 cases each)")
    ax.legend(loc="center left", bbox_to_anchor=(1, 0.5), fontsize=9)
    ax.grid(axis="y", linestyle="--", alpha=0.4)
    plt.tight_layout()
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"wrote {out}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Plot 4-arm ablation sweep results")
    ap.add_argument("--eval-dir", default=str(DEFAULT_EVAL_DIR))
    ap.add_argument("--out-dir", default=None, help="default: <eval-dir>/figures")
    args = ap.parse_args()

    eval_dir = Path(args.eval_dir)
    out_dir = Path(args.out_dir) if args.out_dir else eval_dir / "figures"
    out_dir.mkdir(parents=True, exist_ok=True)

    per_arm: dict[str, list[dict]] = {}
    metrics: dict[str, dict] = {}
    for arm_key, fname, _, _ in ARM_INFO:
        path = eval_dir / fname
        try:
            results = _load(path)
        except FileNotFoundError:
            print(f"  [skip] {arm_key}: {path} not found")
            continue
        per_arm[arm_key] = results
        metrics[arm_key] = compute_metrics(results)
        m = metrics[arm_key]
        print(f"  {arm_key}: n={m['n_total']} eval={m['n_evaluable']} "
              f"strict={m['strict_r1']:.1f}% loose={m['loose_r1']:.1f}% "
              f"hit3={m['hit_at_3']:.1f}% poc={m['poc_pass']:.1f}% "
              f"phantom={m['phantom_pass']:.1f}% cost/case=${m['avg_cost_per_case']:.4f}")

    if not metrics:
        print("no data found")
        return 1

    plot_headline(metrics, out_dir / "headline_metrics.png")
    plot_recall_comparison(metrics, out_dir / "recall_comparison.png")
    plot_cost_vs_recall(metrics, out_dir / "cost_vs_recall.png")
    if "A1" in per_arm and "A2" in per_arm:
        plot_verdict_distribution(per_arm, out_dir / "verdict_distribution.png")

    # Also dump computed metrics JSON for downstream use
    (out_dir / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(f"wrote {out_dir / 'metrics.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
