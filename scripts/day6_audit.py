#!/usr/bin/env python3
"""Day-6 Step 0b — Library audit + AC10a/b/c/d gate.

Runs the four library-quality acceptance criteria as a single mechanical
check. Hard PASS / ABORT decision.

  AC10a coverage   ≥60% of holdout vuln families have ≥1 library entry
  AC10b leakage    function-name overlap < 30% across holdout × library
  AC10c id-overlap no holdout case_id in ACF-036..085 (auto-satisfied)
  AC10d Jaccard    every holdout case max-Jaccard < threshold (R1-derived)

Threshold for AC10d is read from
.omc/plans/day-6-blind-screen-rule.md (R2). If absent, exits 1.

If AC10d drops the holdout below n=15 floor → ABORT and escalate to
Path B (Critic minor finding closure).

Usage:
  python scripts/day6_audit.py
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
RULE_FILE = REPO / ".omc" / "plans" / "day-6-blind-screen-rule.md"
OUT_MD = REPO / "data" / "evaluation" / "day6_audit.md"

USED_IN_DAY5B = {"ACF-087", "ACF-091", "ACF-092", "ACF-093", "ACF-101",
                 "ACF-102", "ACF-103", "ACF-106", "ACF-109", "ACF-114"}

# AC10c forbidden range
ACF_LIBRARY_RANGE = {f"ACF-{i:03d}" for i in range(36, 86)}

# Thresholds (AC10a/b/c are constants; AC10d comes from R2 rule file)
AC10A_COVERAGE_MIN = 0.60
AC10B_LEAKAGE_MAX = 0.30
N_FLOOR = 15  # if holdout drops below this, escalate to Path B

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def tokenize(code: str) -> set[str]:
    return {t for t in re.split(r"[^A-Za-z0-9_]+", code.lower())
            if len(t) >= 2 and not t.isdigit()}


def jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 0.0
    union = len(a | b)
    return (len(a & b) / union) if union else 0.0


def read_ac10d_threshold() -> float:
    """Parse AC10d threshold from blind-screen-rule.md.

    Looks for line matching:  AC10d threshold: <float>
    """
    if not RULE_FILE.exists():
        raise FileNotFoundError(f"R2 rule file missing: {RULE_FILE}")
    text = RULE_FILE.read_text(encoding="utf-8")
    m = re.search(r"AC10d threshold[:\s]+([0-9.]+)", text)
    if not m:
        raise ValueError("AC10d threshold not found in blind-screen-rule.md")
    return float(m.group(1))


def load_holdout() -> list[dict]:
    rows = []
    with HOLDOUT_CSV.open("r", encoding="utf-8-sig") as fp:
        for r in csv.DictReader(fp):
            iid = r["incident_id"]
            if iid in USED_IN_DAY5B:
                continue
            rows.append({
                "id": iid,
                "function": r.get("attack_surface", ""),
                "category": r.get("issue_subtype", "unknown"),
                "code": r.get("vulnerable_code", ""),
                "tokens": tokenize(r.get("vulnerable_code", "")),
            })
    return rows


def load_library() -> list[dict]:
    items = []
    with ANTIPATTERNS.open("r", encoding="utf-8") as fp:
        for line in fp:
            rec = json.loads(line)
            indicators = rec.get("indicators", [])
            fn_pattern = next(
                (s.split(":", 1)[1].strip() for s in indicators
                 if isinstance(s, str) and s.startswith("function name pattern:")),
                "",
            )
            items.append({
                "id": rec.get("id", "?"),
                "function": fn_pattern,
                "category": rec.get("name", ""),
                "tokens": tokenize(rec.get("exploit_template", "")),
            })
    return items


def main() -> int:
    try:
        ac10d_threshold = read_ac10d_threshold()
    except (FileNotFoundError, ValueError) as e:
        print(f"ERROR reading R2 rule: {e}", file=sys.stderr)
        return 1

    holdout = load_holdout()
    library = load_library()

    def bare_name(s: str) -> str:
        s = s.strip()
        idx = s.find("(")
        return (s[:idx] if idx > 0 else s).strip().lower()

    # AC10c: ID-overlap with library ACF range. Always evaluated on full
    # candidate set — illegal IDs are illegal regardless of other filters.
    illegal_ids = [h["id"] for h in holdout if h["id"] in ACF_LIBRARY_RANGE]
    ac10c_pass = len(illegal_ids) == 0

    # AC10d: per-case max Jaccard. Run FIRST as the contamination filter;
    # AC10a/AC10b are then evaluated on the SURVIVORS (post-drop holdout).
    # Rationale: dropping near-duplicates first is the natural order — there's
    # no point grading library coverage / leakage on cases that are about to
    # be removed. Pre-drop and post-drop metrics are both reported for
    # transparency.
    drops = []
    survivor_records = []
    for h in holdout:
        max_j = 0.0
        match = "?"
        for ent in library:
            j = jaccard(h["tokens"], ent["tokens"])
            if j > max_j:
                max_j = j
                match = ent["id"]
        if max_j >= ac10d_threshold:
            drops.append({"id": h["id"], "max_jaccard": max_j, "matched": match})
        else:
            survivor_records.append({**h, "max_jaccard": max_j})

    n_after = len(survivor_records)
    ac10d_pass = n_after >= N_FLOOR
    survivors_for_view = [{"id": s["id"], "max_jaccard": s["max_jaccard"]}
                           for s in survivor_records]

    # AC10a (coverage on SURVIVORS): fraction of distinct holdout subtypes
    # with ≥1 library entry
    holdout_subtypes = {h["category"] for h in survivor_records}
    holdout_families = {s.lower().split()[0] for s in holdout_subtypes if s}
    library_families = set()
    for ent in library:
        for s in ent["category"].split():
            library_families.add(s.lower())
    covered = sum(1 for f in holdout_families if f in library_families)
    coverage = covered / max(len(holdout_families), 1)
    ac10a_pass = coverage >= AC10A_COVERAGE_MIN

    # AC10b (function-name leakage on SURVIVORS): exact bare-name match.
    # Computed both on full holdout (pre_leakage) for transparency and on
    # survivors (post_leakage) which is the gating metric.
    def count_leakage(rows):
        n = 0
        hits = []
        for h in rows:
            hn = bare_name(h["function"])
            if not hn:
                continue
            for ent in library:
                ln = bare_name(ent["function"])
                if ln and hn == ln:
                    n += 1
                    hits.append((h["id"], hn))
                    break
        return n, hits

    pre_leak_n, pre_hits = count_leakage(holdout)
    post_leak_n, post_hits = count_leakage(survivor_records)
    pre_leakage = pre_leak_n / max(len(holdout), 1)
    leakage = post_leak_n / max(len(survivor_records), 1)
    ac10b_pass = leakage < AC10B_LEAKAGE_MAX
    survivors = survivors_for_view  # backward-compat alias for output block

    overall_pass = ac10a_pass and ac10b_pass and ac10c_pass and ac10d_pass

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    with OUT_MD.open("w", encoding="utf-8") as fp:
        fp.write("# Day-6 Step 0b — Library Audit (AC10a/b/c/d)\n\n")
        fp.write(f"Threshold for AC10d (from R2 rule file): **{ac10d_threshold:.3f}**\n\n")

        fp.write("## Acceptance results\n\n")
        fp.write("| AC | Threshold | Observed | Pass? |\n|---|---|---|---|\n")
        fp.write(f"| AC10a coverage | ≥{AC10A_COVERAGE_MIN:.0%} | {coverage:.0%} "
                 f"({covered}/{len(holdout_families)} families) | "
                 f"{'YES' if ac10a_pass else 'NO'} |\n")
        fp.write(f"| AC10b function-name leakage (on survivors) | <{AC10B_LEAKAGE_MAX:.0%} | "
                 f"{leakage:.0%} ({post_leak_n}/{len(survivor_records)}) | "
                 f"{'YES' if ac10b_pass else 'NO'} |\n")
        fp.write(f"| AC10b pre-drop leakage (transparency) | (informational) | "
                 f"{pre_leakage:.0%} ({pre_leak_n}/{len(holdout)}) | n/a |\n")
        fp.write(f"| AC10c ID overlap (ACF 036-085) | 0 | {len(illegal_ids)} | "
                 f"{'YES' if ac10c_pass else 'NO'} |\n")
        fp.write(f"| AC10d Jaccard drops AND n_after≥{N_FLOOR} | {N_FLOOR} | "
                 f"{n_after} survivors ({len(drops)} drops) | "
                 f"{'YES' if ac10d_pass else 'NO'} |\n")

        if drops:
            fp.write(f"\n## AC10d drops ({len(drops)} cases)\n\n")
            fp.write("| id | max_jaccard | matched_against |\n|---|---|---|\n")
            for d in sorted(drops, key=lambda x: -x["max_jaccard"]):
                fp.write(f"| {d['id']} | {d['max_jaccard']:.3f} | {d['matched']} |\n")

        fp.write(f"\n## Survivors ({len(survivors)} cases)\n\n")
        for s in sorted(survivors, key=lambda x: x["id"]):
            fp.write(f"- {s['id']} (max_jaccard={s['max_jaccard']:.3f})\n")

        fp.write("\n## Decision\n\n")
        if overall_pass:
            fp.write(f"**PASS** — proceed to Step 1 (freeze holdout, n_target depends on "
                     f"buildability + AC10d survivor count = {n_after}).\n")
        else:
            fp.write("**ABORT** — branch decision per pre-mortem:\n")
            if not ac10a_pass and ac10b_pass:
                fp.write("- AC10a fail, AC10b ok → Day-6.5a library expansion phase\n")
            elif ac10a_pass and not ac10b_pass:
                fp.write("- AC10a ok, AC10b fail → Day-6.5b library re-curation\n")
            elif not ac10a_pass and not ac10b_pass:
                fp.write("- Both AC10a and AC10b fail → human pivot decision required\n")
            if not ac10c_pass:
                fp.write(f"- AC10c violated ({len(illegal_ids)} illegal IDs) → fix holdout source\n")
            if not ac10d_pass:
                fp.write(f"- AC10d Jaccard drops below n_floor={N_FLOOR} "
                         f"({n_after} survivors) → escalate to Path B (Step 0c spot-check)\n")

    print(f"Wrote {OUT_MD}")
    print(f"AC10a: {'PASS' if ac10a_pass else 'FAIL'} (coverage={coverage:.0%})")
    print(f"AC10b: {'PASS' if ac10b_pass else 'FAIL'} (leakage={leakage:.0%})")
    print(f"AC10c: {'PASS' if ac10c_pass else 'FAIL'} (illegal={len(illegal_ids)})")
    print(f"AC10d: {'PASS' if ac10d_pass else 'FAIL'} (survivors={n_after}, drops={len(drops)})")
    return 0 if overall_pass else 2


if __name__ == "__main__":
    raise SystemExit(main())
