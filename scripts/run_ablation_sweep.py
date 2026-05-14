"""4-arm ablation sweep over the full 190-case eval_set.json.

Arms:
    A1 full-cascade     graph.run_pipeline default (cascade=True, retries=2)
    A2 no-cascade       graph.run_pipeline (cascade=False) — top-1 only
    A3 gpt-zero-shot    baselines.gpt_zeroshot.evaluate (single LLM call)
    A4 slither          baselines.slither_baseline.evaluate (static)

Features:
    - Incremental per-case write (resume-friendly: skip case_id already in JSON)
    - Cross-arm cumulative cost guard (hard cap default $5)
    - Optional --arms filter to run a subset
    - --include-snippet to include snippet_only cases (default skip)
    - Each arm writes its own predictions JSON
    - Final sweep_summary.md is mechanical: per-arm Recall@1/3, PoC-pass, $/case

Outputs:
    data/evaluation/sweep_A1_full_cascade.json
    data/evaluation/sweep_A2_no_cascade.json
    data/evaluation/sweep_A3_gpt_zeroshot.json
    data/evaluation/sweep_A4_slither.json
    data/evaluation/sweep_summary.md

Resume semantics:
    - Reads existing per-arm JSON (if present); collects case_ids already there.
    - Skips those ids; appends new results to the same file.
    - Safe to Ctrl-C and restart.
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

from agent.data.schema import Case  # noqa: E402

# gpt-5-mini pricing per 1K tokens (per docs)
PRICE_PROMPT_PER_1K = 0.00025
PRICE_COMPLETION_PER_1K = 0.002


def coerce_case(raw: dict) -> Case:
    """Normalize new-schema dict → legacy Case shape."""
    if raw.get("source_type") in ("c5_local", "c4_local", "snippet_only"):
        raw = {**raw, "source_type": "code4rena_bad"}
    raw["severity"] = (raw.get("severity") or "high").lower() or "high"
    if not raw.get("vulnerability_type"):
        raw["vulnerability_type"] = "access_control"
    if raw.get("buildable") is None:
        raw["buildable"] = True
    return Case(**raw)


def load_cases(eval_path: Path, include_snippet: bool) -> list[tuple[Case, dict]]:
    """Returns [(Case, raw_dict), ...]; raw_dict carries source_type for stratification."""
    data = json.loads(eval_path.read_text(encoding="utf-8"))
    out: list[tuple[Case, dict]] = []
    for raw in data.get("cases", []):
        if not include_snippet and raw.get("source_type") == "snippet_only":
            continue
        try:
            out.append((coerce_case(raw), raw))
        except Exception as exc:
            print(f"  [skip] {raw.get('id','?')}: {type(exc).__name__}: {str(exc)[:80]}")
    return out


def estimate_cost(record: dict) -> float:
    """Return USD cost for one prediction record (looks at tokens fields)."""
    tp = record.get("tokens_prompt", 0) or record.get("annotations", {}).get("tokens_prompt", 0)
    tc = record.get("tokens_completion", 0) or record.get("annotations", {}).get("tokens_completion", 0)
    return tp / 1000 * PRICE_PROMPT_PER_1K + tc / 1000 * PRICE_COMPLETION_PER_1K


def existing_ids(json_path: Path) -> set[str]:
    if not json_path.is_file():
        return set()
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return set()
    if isinstance(data, list):
        return {r.get("case_id") for r in data if isinstance(r, dict)}
    return set()


def write_atomic(path: Path, results: list) -> None:
    """Atomic write: tmp + rename. Avoids half-written JSON on crash."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(results, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    tmp.replace(path)


# ============================================================
# Arm runners
# ============================================================


def run_arm_pipeline(case: Case, use_cascade: bool, max_retries: int) -> dict:
    """A1 or A2 — call graph.run_pipeline with cascade flag."""
    from agent.graph import run_pipeline
    try:
        r = run_pipeline(
            case_id=case.id,
            contract_source=case.contract_source,
            contract_name=case.contract_name,
            max_retries=max_retries,
            use_cascade=use_cascade,
        )
        d = asdict(r)
        d["ground_truth_function"] = case.vulnerable_function or ""
        return d
    except Exception as exc:
        return {
            "case_id": case.id,
            "contract_name": case.contract_name,
            "ground_truth_function": case.vulnerable_function or "",
            "error": f"{type(exc).__name__}: {exc}",
            "execution_result": "crashed",
            "target_function": "",
            "poc_attempts": 0,
            "annotations": {},
        }


def run_arm_zero(case: Case) -> dict:
    """A3 — zero-shot."""
    from agent.baselines import gpt_zeroshot
    try:
        rec = gpt_zeroshot.evaluate(case)
        return asdict(rec)
    except Exception as exc:
        return {
            "case_id": case.id,
            "contract_name": case.contract_name,
            "ground_truth_function": case.vulnerable_function or "",
            "error": f"{type(exc).__name__}: {exc}",
            "method": "gpt_zeroshot",
        }


def run_arm_slither(case: Case) -> dict:
    """A4 — slither."""
    from agent.baselines import slither_baseline
    try:
        rec = slither_baseline.evaluate(case)
        return asdict(rec)
    except Exception as exc:
        return {
            "case_id": case.id,
            "contract_name": case.contract_name,
            "ground_truth_function": case.vulnerable_function or "",
            "error": f"{type(exc).__name__}: {exc}",
            "method": "slither",
        }


# ============================================================
# Sweep driver
# ============================================================


ARMS = {
    "A1": ("full_cascade", lambda case, ctx: run_arm_pipeline(case, use_cascade=True, max_retries=ctx["retries"])),
    "A2": ("no_cascade", lambda case, ctx: run_arm_pipeline(case, use_cascade=False, max_retries=ctx["retries"])),
    "A3": ("gpt_zeroshot", lambda case, _ctx: run_arm_zero(case)),
    "A4": ("slither", lambda case, _ctx: run_arm_slither(case)),
}


def run_sweep(
    *,
    eval_set: Path,
    arms: list[str],
    out_dir: Path,
    cost_cap: float,
    retries: int,
    include_snippet: bool,
    limit: int | None,
) -> dict:
    cases_with_raw = load_cases(eval_set, include_snippet=include_snippet)
    if limit:
        cases_with_raw = cases_with_raw[:limit]
    cases = [cwr[0] for cwr in cases_with_raw]
    print(f"[sweep] loaded {len(cases)} cases (include_snippet={include_snippet}, limit={limit})")
    print(f"[sweep] arms: {arms}, cost_cap=${cost_cap}, retries={retries}")

    out_dir.mkdir(parents=True, exist_ok=True)
    ctx = {"retries": retries}
    arm_results: dict[str, list[dict]] = {}
    cumulative_cost = 0.0
    aborted = False
    t_start = time.time()

    # Run arms in order (cheapest first for fail-fast): A4, A3, A2, A1
    order = sorted(arms, key=lambda a: {"A4": 0, "A3": 1, "A2": 2, "A1": 3}.get(a, 99))

    for arm_key in order:
        name, runner = ARMS[arm_key]
        out_path = out_dir / f"sweep_{arm_key}_{name}.json"
        existing = existing_ids(out_path)
        results: list[dict] = (
            json.loads(out_path.read_text(encoding="utf-8"))
            if out_path.is_file() and existing else []
        )
        print(f"\n[arm {arm_key}/{name}] file={out_path.name}  resume from {len(existing)} existing")

        arm_t0 = time.time()
        for i, case in enumerate(cases, 1):
            if case.id in existing:
                continue
            r = runner(case, ctx)
            results.append(r)
            cumulative_cost += estimate_cost(r)
            write_atomic(out_path, results)
            verdict = r.get("execution_result", r.get("flagged", "?"))
            pred = r.get("target_function") or r.get("predicted_function", "")
            print(
                f"  [{arm_key}][{i:3d}/{len(cases)}] {case.id:12s}  v={verdict}  pred={pred!r}  "
                f"cumcost=${cumulative_cost:.3f}",
                flush=True,
            )
            if cumulative_cost > cost_cap:
                print(f"  [arm {arm_key}] COST CAP HIT (${cumulative_cost:.3f} > ${cost_cap}); aborting sweep")
                aborted = True
                break
        arm_results[arm_key] = results
        elapsed_arm = time.time() - arm_t0
        print(f"[arm {arm_key}] done: {len(results)} records, {elapsed_arm:.0f}s")
        if aborted:
            break

    elapsed = time.time() - t_start
    summary_md = write_sweep_summary(arm_results, out_dir, cumulative_cost, elapsed)

    return {
        "cases_processed": len(cases),
        "arms_run": order,
        "cumulative_cost_usd": round(cumulative_cost, 4),
        "elapsed_seconds": round(elapsed, 1),
        "aborted_on_cost": aborted,
        "summary_path": str(summary_md),
    }


def _strict_loose_hit(pred: str, gt: str) -> tuple[bool, bool]:
    if not pred or not gt:
        return False, False
    s = pred == gt
    p, t = pred.lower().strip(), gt.lower().strip()
    l = s or p == t or p in t or t in p
    return s, l


def _candidates_of(r: dict) -> list[str]:
    """Get top-K candidate list from various result shapes."""
    # graph.PipelineResult stores it in annotations
    ann = r.get("annotations", {}) or {}
    cands = ann.get("top_k_candidates") or []
    if cands:
        return cands
    # baselines store flagged_functions
    fl = r.get("flagged_functions") or []
    if fl:
        return fl
    pred = r.get("target_function") or r.get("predicted_function") or ""
    return [pred] if pred else []


def write_sweep_summary(arm_results: dict[str, list[dict]], out_dir: Path, total_cost: float, elapsed: float) -> Path:
    lines = [
        "# Ablation Sweep Summary",
        "",
        f"- Cumulative cost (estimated): ${total_cost:.3f}",
        f"- Total elapsed: {elapsed:.0f}s",
        f"- Arms: {sorted(arm_results.keys())}",
        "",
        "## Per-arm headline metrics",
        "",
        "| arm | N | strict R@1 | loose R@1 | hit@3 | PoC-pass | phantom-pass | error | $/case |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for arm in sorted(arm_results.keys()):
        results = arm_results[arm]
        n = len(results)
        if n == 0:
            lines.append(f"| {arm} | 0 | - | - | - | - | - | - | - |")
            continue
        evaluable = [r for r in results if (r.get("ground_truth_function") or "").strip()
                     and (r.get("ground_truth_function") not in ("Unknown",))]
        n_eval = len(evaluable)
        strict = sum(1 for r in evaluable if _strict_loose_hit(
            r.get("target_function") or r.get("predicted_function") or "",
            r.get("ground_truth_function") or "")[0])
        loose = sum(1 for r in evaluable if _strict_loose_hit(
            r.get("target_function") or r.get("predicted_function") or "",
            r.get("ground_truth_function") or "")[1])
        hit3 = 0
        for r in evaluable:
            gt = r.get("ground_truth_function") or ""
            cands = _candidates_of(r)[:3]
            if any(_strict_loose_hit(c, gt)[0] for c in cands):
                hit3 += 1
        passes = sum(1 for r in results if r.get("execution_result") == "pass" or r.get("flagged") is True)
        phantom = sum(
            1 for r in results
            if (r.get("execution_result") == "pass" or r.get("flagged") is True)
            and not _strict_loose_hit(
                r.get("target_function") or r.get("predicted_function") or "",
                r.get("ground_truth_function") or "")[0]
        )
        errors = sum(1 for r in results if r.get("error"))
        arm_cost = sum(estimate_cost(r) for r in results)
        per = arm_cost / n if n else 0.0

        def pct(num: int, den: int) -> str:
            return f"{num}/{den} ({num/den*100:.0f}%)" if den else "-"

        lines.append(
            f"| {arm} | {n} | {pct(strict, n_eval)} | {pct(loose, n_eval)} | {pct(hit3, n_eval)} | "
            f"{pct(passes, n)} | {pct(phantom, n)} | {errors}/{n} | ${per:.4f} |"
        )

    lines.append("")
    lines.append("## Notes")
    lines.append("- evaluable = cases where ground_truth_function is non-empty and != 'Unknown'")
    lines.append("- strict R@1: predicted == GT (exact)")
    lines.append("- loose R@1: case-insensitive substring match either direction")
    lines.append("- hit@3: GT appears in top-3 candidates (strict)")
    lines.append("- PoC-pass: forge verdict='pass' (A1/A2) or `flagged=True` (A3/A4)")
    lines.append("- phantom-pass: PoC-pass but pred != GT (inline-replica self-attack)")

    md_path = out_dir / "sweep_summary.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return md_path


def main() -> int:
    ap = argparse.ArgumentParser(description="4-arm ablation sweep over 190 cases")
    ap.add_argument("--eval-set", default="data/dataset/eval_set.json")
    ap.add_argument("--out-dir", default="data/evaluation")
    ap.add_argument("--arms", default="A1,A2,A3,A4", help="comma-separated arms")
    ap.add_argument("--cost-cap", type=float, default=5.0, help="hard cap USD")
    ap.add_argument("--retries", type=int, default=2, help="max retries for A1/A2 builder loop")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--include-snippet", action="store_true", help="include snippet_only cases")
    args = ap.parse_args()

    arms = [a.strip() for a in args.arms.split(",") if a.strip()]
    invalid = [a for a in arms if a not in ARMS]
    if invalid:
        raise SystemExit(f"invalid arms: {invalid}; choose from {list(ARMS)}")

    report = run_sweep(
        eval_set=Path(args.eval_set),
        arms=arms,
        out_dir=Path(args.out_dir),
        cost_cap=args.cost_cap,
        retries=args.retries,
        include_snippet=args.include_snippet,
        limit=args.limit,
    )
    print()
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if not report.get("aborted_on_cost") else 2


if __name__ == "__main__":
    raise SystemExit(main())
