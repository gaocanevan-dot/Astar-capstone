"""B smoke — run existing pipeline (analyst+builder+verifier) on the new
190-case eval_set.json to establish the pre-MCC baseline.

Schema bridge: the new eval_set uses source_type in {"c5_local", "c4_local",
"snippet_only"} which is outside the legacy Case Literal. We coerce all to
"code4rena_bad" since they're public-audit bad cases.

Snippet-only cases are skipped by default (--include-snippet to override) since
the analyst won't have enough context (snippet is 1-10 lines).

Outputs:
    data/evaluation/b_smoke_predictions.json
    data/evaluation/b_smoke_summary.md
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
from agent.graph import run_pipeline  # noqa: E402

LEGACY_SOURCE_TYPE = "code4rena_bad"


def coerce_case(raw: dict) -> Case:
    """Normalize a new-schema case dict into the legacy Case shape."""
    src_type = raw.get("source_type", "code4rena_bad")
    if src_type in ("c5_local", "c4_local", "snippet_only"):
        raw = {**raw, "source_type": LEGACY_SOURCE_TYPE}
    # `severity` field comes as e.g. "High" in CSV; legacy expects "high"
    raw["severity"] = (raw.get("severity") or "high").lower() or "high"
    # vulnerability_type default = access_control (legacy literal)
    if not raw.get("vulnerability_type"):
        raw["vulnerability_type"] = "access_control"
    # New eval_set has buildable=None until MCC build_probe runs; legacy is bool
    if raw.get("buildable") is None:
        raw["buildable"] = True
    return Case(**raw)


def load_cases(eval_path: Path, include_snippet: bool) -> list[Case]:
    data = json.loads(eval_path.read_text(encoding="utf-8"))
    raw_cases = data.get("cases", [])
    out: list[Case] = []
    for raw in raw_cases:
        if not include_snippet and raw.get("source_type") == "snippet_only":
            continue
        try:
            out.append(coerce_case(raw))
        except Exception as exc:
            print(f"  [skip] {raw.get('id','?')}: {type(exc).__name__}: {str(exc)[:100]}")
    return out


def write_summary(results: list[dict], out_path: Path, elapsed: float) -> None:
    n = len(results)
    verdicts: dict[str, int] = {}
    for r in results:
        v = r.get("execution_result", "skipped")
        verdicts[v] = verdicts.get(v, 0) + 1

    strict_hits = sum(
        1 for r in results
        if r.get("target_function")
        and r["target_function"] == r.get("ground_truth_function", "")
    )
    total_llm = sum(r.get("annotations", {}).get("llm_calls", 0) for r in results)
    total_tok = sum(
        r.get("annotations", {}).get("tokens_prompt", 0)
        + r.get("annotations", {}).get("tokens_completion", 0)
        for r in results
    )

    lines = [
        "# B Smoke Summary — pre-MCC baseline on new dataset",
        "",
        f"- cases run: {n}",
        f"- elapsed: {elapsed:.1f}s",
        f"- total LLM calls: {total_llm}",
        f"- total tokens (prompt+completion): {total_tok}",
        f"- analyst strict-recall: {strict_hits}/{n}" + (f" ({strict_hits/n*100:.0f}%)" if n else ""),
        "",
        "## Verdict distribution",
        "",
        "| verdict | count | % |",
        "|---|---|---|",
    ]
    for v, c in sorted(verdicts.items()):
        pct = f"{c/n*100:.0f}%" if n else "-"
        lines.append(f"| {v} | {c} | {pct} |")
    lines.append("")
    lines.append("## Per-case")
    lines.append("")
    lines.append("| case_id | GT fn | pred | verdict | attempts | reason |")
    lines.append("|---|---|---|---|---|---|")
    for r in results:
        gt = r.get("ground_truth_function", "")
        pred = r.get("target_function", "")
        v = r.get("execution_result", "")
        attempts = r.get("poc_attempts", 0)
        reason = (r.get("finding_reason", "") or r.get("error_summary", ""))[:80]
        lines.append(
            f"| {r['case_id']} | `{gt}` | `{pred}` | {v} | {attempts} | {reason} |"
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="B smoke — pre-MCC baseline on new dataset")
    ap.add_argument("--eval-set", default="data/dataset/eval_set.json")
    ap.add_argument("--limit", type=int, default=10, help="N cases to run")
    ap.add_argument("--include-snippet", action="store_true", help="include snippet_only cases")
    ap.add_argument("--max-retries", type=int, default=2)
    ap.add_argument("--predictions-out", default="data/evaluation/b_smoke_predictions.json")
    ap.add_argument("--summary-out", default="data/evaluation/b_smoke_summary.md")
    args = ap.parse_args()

    eval_path = Path(args.eval_set)
    cases = load_cases(eval_path, include_snippet=args.include_snippet)
    if args.limit:
        cases = cases[: args.limit]
    print(f"loaded {len(cases)} cases (limit={args.limit}, include_snippet={args.include_snippet})")

    results: list[dict] = []
    t0 = time.time()
    for i, case in enumerate(cases, 1):
        print(f"[{i}/{len(cases)}] {case.id}  contract={case.contract_name}  gt={case.vulnerable_function!r}", flush=True)
        try:
            r = run_pipeline(
                case_id=case.id,
                contract_source=case.contract_source,
                contract_name=case.contract_name,
                max_retries=args.max_retries,
            )
        except Exception as exc:
            print(f"  CRASH: {type(exc).__name__}: {exc}")
            continue
        d = asdict(r)
        d["ground_truth_function"] = case.vulnerable_function or ""
        results.append(d)
        # Write incrementally
        Path(args.predictions_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.predictions_out).write_text(
            json.dumps(results, indent=2, ensure_ascii=False, default=str)
        )
        print(
            f"  -> verdict={r.execution_result}  attempts={r.poc_attempts}  pred={r.target_function!r}  reason={r.finding_reason[:80]!r}",
            flush=True,
        )

    elapsed = time.time() - t0
    write_summary(results, Path(args.summary_out), elapsed)
    print(f"\nelapsed: {elapsed:.1f}s  predictions: {args.predictions_out}  summary: {args.summary_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
