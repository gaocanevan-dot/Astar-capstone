#!/usr/bin/env python3
"""Day-6 R1 — Empirical Jaccard threshold calibration (Critic kickoff condition).

Computes token-level Jaccard similarity between every clean-pool holdout case's
`vulnerable_code` and every anti_patterns library entry's `exploit_template`.
For each holdout case, records the MAX Jaccard against the library — this is
the AC10d contamination metric.

Outputs a histogram + recommended threshold to
data/evaluation/day6_jaccard_distribution.md.

Threshold selection (Architect-prescribed, in order of preference):
  1. Natural gap in distribution (>= 0.10 wide gap between adjacent bins)
  2. P90 of within-pool distribution (defensible default)
  3. Hard floor 0.30 (final fallback if distribution is uniformly high)

The recommended threshold is then transcribed into
.omc/plans/day-6-blind-screen-rule.md (R2) and used by scripts/day6_audit.py
as AC10d's mechanical gate.

Usage:
  python scripts/calibrate_jaccard.py
"""
from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HOLDOUT_CSV = REPO / "data" / "dataset" / "c5_access_control_dataset_remaining33.csv"
ANTIPATTERNS = REPO / "data" / "agent_memory" / "anti_patterns.jsonl"
OUT_MD = REPO / "data" / "evaluation" / "day6_jaccard_distribution.md"

# 23 clean unused ACF IDs (ACF-086..ACF-118 minus the 10 used in Day-5b)
USED_IN_DAY5B = {"ACF-087", "ACF-091", "ACF-092", "ACF-093", "ACF-101",
                 "ACF-102", "ACF-103", "ACF-106", "ACF-109", "ACF-114"}

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def tokenize(code: str) -> set[str]:
    """Extract identifier-like tokens, lowercased.

    Splits on non-alphanumeric, drops 1-char tokens (mostly noise) and pure
    digits. Keeps `solidity` keywords as-is — boilerplate-shared tokens like
    `function`, `public`, `require` will inflate Jaccard for shallow matches,
    which is *exactly* what AC10d wants to detect.
    """
    tokens = re.split(r"[^A-Za-z0-9_]+", code.lower())
    return {t for t in tokens if len(t) >= 2 and not t.isdigit()}


def jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def load_holdout() -> list[dict]:
    rows = []
    with HOLDOUT_CSV.open("r", encoding="utf-8-sig") as fp:
        reader = csv.DictReader(fp)
        for row in reader:
            iid = row["incident_id"]
            if iid in USED_IN_DAY5B:
                continue
            rows.append({
                "id": iid,
                "code": row.get("vulnerable_code", ""),
                "tokens": tokenize(row.get("vulnerable_code", "")),
            })
    return rows


def load_library() -> list[dict]:
    items = []
    with ANTIPATTERNS.open("r", encoding="utf-8") as fp:
        for line in fp:
            rec = json.loads(line)
            tpl = rec.get("exploit_template", "")
            items.append({
                "id": rec.get("id", "?"),
                "tokens": tokenize(tpl),
            })
    return items


def histogram(values: list[float], bins: int = 10) -> list[tuple[float, float, int]]:
    if not values:
        return []
    lo, hi = 0.0, 1.0
    width = (hi - lo) / bins
    counts = [0] * bins
    for v in values:
        b = min(int((v - lo) / width), bins - 1)
        counts[b] += 1
    return [(lo + i * width, lo + (i + 1) * width, counts[i]) for i in range(bins)]


def find_natural_gap(sorted_vals: list[float], min_gap: float = 0.10) -> float | None:
    """Return midpoint of the largest gap >= min_gap, if any.

    Sorted ascending. The gap is between consecutive values.
    """
    if len(sorted_vals) < 2:
        return None
    best_gap = 0.0
    best_mid = None
    for i in range(1, len(sorted_vals)):
        gap = sorted_vals[i] - sorted_vals[i - 1]
        if gap >= min_gap and gap > best_gap:
            best_gap = gap
            best_mid = (sorted_vals[i] + sorted_vals[i - 1]) / 2
    return best_mid


def percentile(sorted_vals: list[float], p: float) -> float:
    if not sorted_vals:
        return 0.0
    k = (len(sorted_vals) - 1) * p
    f = int(k)
    c = min(f + 1, len(sorted_vals) - 1)
    if f == c:
        return sorted_vals[f]
    return sorted_vals[f] * (c - k) + sorted_vals[c] * (k - f)


def main() -> int:
    holdout = load_holdout()
    library = load_library()
    print(f"Loaded {len(holdout)} holdout cases and {len(library)} library entries")

    if len(holdout) != 23:
        print(f"WARN: expected 23 holdout cases, got {len(holdout)}", file=sys.stderr)

    # For each holdout case, compute max Jaccard against the library
    per_case = []
    for h in holdout:
        max_j = 0.0
        max_against = "?"
        for lib in library:
            j = jaccard(h["tokens"], lib["tokens"])
            if j > max_j:
                max_j = j
                max_against = lib["id"]
        per_case.append({"id": h["id"], "max_jaccard": max_j, "matched": max_against})

    max_vals = sorted(c["max_jaccard"] for c in per_case)

    p50 = percentile(max_vals, 0.50)
    p75 = percentile(max_vals, 0.75)
    p90 = percentile(max_vals, 0.90)
    p95 = percentile(max_vals, 0.95)
    natural_gap = find_natural_gap(max_vals, min_gap=0.10)

    # Hub detection: a library entry that is top-1 for >=5 holdout cases is
    # a contamination hub — natural-gap can miss this even when individual
    # Jaccards are below the gap (cluster of 0.4-0.7 against one library entry).
    from collections import Counter
    top1 = Counter()
    for h in holdout:
        best_id, best_j = "?", 0.0
        for lib in library:
            j = jaccard(h["tokens"], lib["tokens"])
            if j > best_j:
                best_id, best_j = lib["id"], j
        top1[best_id] += 1
    hubs = [(lid, cnt) for lid, cnt in top1.most_common(3) if cnt >= 5]

    # Threshold selection (revised — hub-aware):
    # If hubs exist, the natural gap is misleading. Use max(P75, 0.40) — this
    # catches the hub cluster (which typically lives in 0.4-0.6 range) while
    # not over-rejecting legitimate cases.
    if hubs:
        recommended = max(p75, 0.40)
        rationale = (f"contamination hub(s) detected ({hubs}); using "
                     f"max(P75={p75:.3f}, 0.40) = {recommended:.3f} "
                     f"to catch hub cluster (natural gap {natural_gap} is misleading here)")
    elif natural_gap is not None:
        recommended = natural_gap
        rationale = f"no hubs; natural gap >= 0.10 detected at midpoint {natural_gap:.3f}"
    elif p90 < 0.40:
        recommended = max(p90, 0.30)
        rationale = f"no hubs; P90 = {p90:.3f}, threshold = max(P90, 0.30) = {recommended:.3f}"
    else:
        recommended = 0.30
        rationale = f"no hubs; P90 = {p90:.3f} too high; floor 0.30"

    hist = histogram(max_vals, bins=10)

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    with OUT_MD.open("w", encoding="utf-8") as fp:
        fp.write("# Day-6 AC10d — Jaccard Threshold Calibration (R1)\n\n")
        fp.write("**Computed by**: `scripts/calibrate_jaccard.py`\n")
        fp.write(f"**Holdout pool**: {len(holdout)} clean unused ACF cases (086..118 minus Day-5b 10)\n")
        fp.write(f"**Library**: {len(library)} anti_patterns entries\n\n")

        fp.write("## Distribution of max-Jaccard per holdout case\n\n")
        fp.write("| bin | range | count |\n|---|---|---|\n")
        for lo, hi, cnt in hist:
            fp.write(f"| [{lo:.2f}, {hi:.2f}) | | {cnt} |\n")

        fp.write("\n## Statistics\n\n")
        fp.write(f"- P50: {p50:.3f}\n")
        fp.write(f"- P75: {p75:.3f}\n")
        fp.write(f"- P90: {p90:.3f}\n")
        fp.write(f"- P95: {p95:.3f}\n")
        fp.write(f"- Min: {min(max_vals):.3f}\n")
        fp.write(f"- Max: {max(max_vals):.3f}\n")
        fp.write(f"- Natural gap (>=0.10 wide): "
                 f"{f'{natural_gap:.3f}' if natural_gap is not None else 'none'}\n\n")

        fp.write("## Hub detection (top-1 match counts)\n\n")
        fp.write("| library_id | times top-1 | hub? |\n|---|---|---|\n")
        for lid, cnt in top1.most_common(5):
            fp.write(f"| {lid} | {cnt} | {'**YES**' if cnt >= 5 else 'no'} |\n")
        fp.write("\n")

        fp.write("## Recommended AC10d threshold\n\n")
        fp.write(f"**Threshold: {recommended:.3f}**\n\n")
        fp.write(f"Rationale: {rationale}\n\n")
        fp.write("Cases with max-Jaccard >= threshold are flagged as contaminated\n")
        fp.write("and dropped from the holdout. If drops bring n below 15, escalate\n")
        fp.write("to Path B (per Day-5b stop-rule + Critic minor finding).\n\n")

        fp.write("## Per-case detail (sorted by max_jaccard descending)\n\n")
        fp.write("| ACF id | max_jaccard | matched_against | drop? |\n|---|---|---|---|\n")
        for c in sorted(per_case, key=lambda x: -x["max_jaccard"]):
            drop = "YES" if c["max_jaccard"] >= recommended else "no"
            fp.write(f"| {c['id']} | {c['max_jaccard']:.3f} | {c['matched']} | {drop} |\n")

    n_drop = sum(1 for c in per_case if c["max_jaccard"] >= recommended)
    print(f"\nWrote {OUT_MD}")
    print(f"Recommended threshold: {recommended:.3f} ({rationale})")
    print(f"Cases that would be dropped: {n_drop}/{len(per_case)}")
    print(f"Holdout after AC10d: {len(per_case) - n_drop} cases")
    if len(per_case) - n_drop < 15:
        print("WARN: AC10d would drop pool below 15 — Path B escalation likely")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
