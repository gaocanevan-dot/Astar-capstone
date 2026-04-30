"""Sequential pipeline (Phase 2 interim) — analyst → builder → verifier
with retry loop on fail_error.

NOT LangGraph yet. This is a minimal executable graph so we can see the full
flow end-to-end before investing in compile-time graph splitting (US-013/014).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from agent.adapters.llm import invoke_json as _warm_llm_import  # noqa: F401 - ensure OpenAI client loads
from agent.adapters.rag import TfidfRagStore, format_few_shot_context
from agent.nodes.analyst import analyze
from agent.nodes.builder import build_poc
from agent.nodes.verifier import verify
from agent.state import AuditAnnotations, empty_annotations


MAX_RETRIES = 3  # lower than plan default 5 to bound wall-clock / cost


@dataclass
class PipelineResult:
    case_id: str
    contract_name: str
    target_function: str
    hypothesis: str
    confidence: float

    poc_code: str = ""
    poc_attempts: int = 0
    error_history: list[str] = field(default_factory=list)

    execution_result: str = "pending"  # pass / fail_revert_ac / fail_error / skipped
    execution_trace: str = ""
    error_summary: str = ""

    annotations: dict = field(default_factory=dict)

    finding_confirmed: bool = False
    finding_reason: str = ""  # human-readable explanation of terminal state

    wall_clock_s: float = 0.0


def run_pipeline(
    case_id: str,
    contract_source: str,
    contract_name: str,
    max_retries: int = MAX_RETRIES,
    skip_forge: bool = False,
    rag_store: TfidfRagStore | None = None,
    verifier_mode: str | None = None,
    use_cascade: bool = True,
    use_reflection: bool = False,
    use_tools: bool = False,
) -> PipelineResult:
    """Run analyst → builder → verifier loop on a single contract.

    skip_forge=True returns after builder (for tests where Foundry is unavailable).
    rag_store (optional) enables RAG few-shot in analyst with LOO by case_id.
    verifier_mode (Day-2 Prereq-A): passed through to the verifier so the seam
    fires per the smoke manifest tag (`original`/`oz_vendored`/`replica_only`).

    Day-3 W1 arm flags:
    - use_cascade=False truncates the candidate cascade to top-1 (no advance).
    - use_reflection=True wedges a `reflector.reflect()` LLM call between
      candidates to re-pick the next target from the remaining LOCKED set.
    - use_tools=True dispatches to `analyst_with_tools.analyze_with_tools`,
      doubling the analyst LLM calls (pre + post tool re-prompt) and writing
      `analyst_hypothesis_pre_tool` / `_post_tool` to annotations.
    """
    ann: AuditAnnotations = empty_annotations()
    ann["case_id"] = case_id
    ann["contract_name"] = contract_name

    if not contract_source.strip():
        return PipelineResult(
            case_id=case_id,
            contract_name=contract_name,
            target_function="",
            hypothesis="",
            confidence=0.0,
            execution_result="skipped",
            finding_reason="empty contract_source",
            annotations=dict(ann),
        )

    # --- Node 1: Analyst (optionally tool-augmented) ---
    rag_few_shot = ""
    if rag_store is not None and len(rag_store) > 0:
        retrieved = rag_store.retrieve(contract_source, top_k=3, exclude_id=case_id)
        rag_few_shot = format_few_shot_context(retrieved)
    if use_tools:
        from agent.nodes.analyst_with_tools import analyze_with_tools
        analyst_out = analyze_with_tools(
            contract_source=contract_source,
            contract_name=contract_name,
            annotations=ann,
            use_tools=True,
            rag_few_shot=rag_few_shot,
        )
    else:
        analyst_out = analyze(
            contract_source, contract_name, ann, rag_few_shot=rag_few_shot
        )

    result = PipelineResult(
        case_id=case_id,
        contract_name=contract_name,
        target_function=analyst_out["target_function"],
        hypothesis=analyst_out["hypothesis"],
        confidence=analyst_out["confidence"],
    )

    if not analyst_out["target_function"]:
        result.execution_result = "skipped"
        result.finding_reason = "analyst returned empty target_function"
        result.annotations = dict(ann)
        return result

    # --- Day-2 T8: Cascade router (A1) ---
    # Outer loop: candidate cascade (top-K=3, early-exit on pass).
    # Inner loop: builder → verifier, retry on compile/runtime fail.
    # Routing per Critic #10:
    #   pass                   → SUCCESS, exit cascade
    #   fail_revert_ac         → advance to next candidate (no inner retry)
    #   fail_error_compile     → retry builder (PoC issue)
    #   fail_error_runtime     → retry builder (PoC issue)
    #   any retry-exhausted    → abstain (PoC was wrong, no candidate evidence)
    candidates: list[str] = list(analyst_out.get("candidates") or [])
    if not candidates and analyst_out["target_function"]:
        candidates = [analyst_out["target_function"]]
    # Day-3 W1: use_cascade=False → top-1 only (single-candidate baseline arm).
    top_k: list[str] = candidates[: (3 if use_cascade else 1)]
    ann["top_k_candidates"] = list(top_k)

    cascade_trace: list[dict] = []
    abstained: bool = False

    # Queue-based cascade so reflection (Day-3 W1) can re-pick from remaining.
    remaining: list[str] = list(top_k)
    tried: list[str] = []
    cand_idx = 0
    prev_target = ""
    prev_verdict = ""
    prev_error = ""

    while remaining:
        # Pick next candidate. Default = remaining[0]. With use_reflection,
        # the reflector picks from remaining (LOCKED to the existing set).
        if use_reflection and tried:
            from agent.nodes.reflector import reflect

            refl = reflect(
                prior_target=prev_target,
                prior_hypothesis=analyst_out["hypothesis"],
                prior_verdict=prev_verdict,
                prior_error=prev_error,
                candidates=top_k,
                tried_candidates=tried,
                annotations=ann,
            )
            picked = refl["target_function"]
            target = picked if picked in remaining else remaining[0]
        else:
            target = remaining[0]

        # Commit pick: remove from remaining, append to tried.
        remaining = [c for c in remaining if c != target]
        tried.append(target)

        cascade_step: dict = {
            "idx": cand_idx,
            "target_function": target,
            "verdicts": [],
            "outcome": "in_progress",
        }
        cascade_trace.append(cascade_step)
        result.target_function = target  # the candidate actually exercised

        error_history: list[str] = []
        candidate_resolved = False  # True if pass | fail_revert_ac (terminal verdict)
        # Day-4 Issue 1 (hybrid routing): on `fail_error_runtime` the first
        # occurrence is treated as a transient PoC issue (retry once, preserves
        # Critic #10 caution); the second occurrence triggers cascade advance
        # (PoC keeps reverting on this candidate — try a different function).
        # Compile failures still retry up to max_retries (PoC writer needs the
        # error feedback to fix). This is a deliberate, post-hoc-yet-disclosed
        # adjustment (see .omc/plans/day4-routing-reversal-disclosure.md).
        runtime_fail_count = 0
        runtime_advance = False

        for attempt in range(max_retries):
            result.poc_attempts = attempt + 1

            poc_code = build_poc(
                contract_source=contract_source,
                contract_name=contract_name,
                target_function=target,
                hypothesis=analyst_out["hypothesis"],
                error_history=error_history,
                annotations=ann,
            )
            result.poc_code = poc_code

            if skip_forge:
                result.execution_result = "skipped"
                result.finding_reason = "skip_forge=True; builder produced PoC but verifier bypassed"
                cascade_step["outcome"] = "skipped"
                ann["cascade_trace"] = cascade_trace
                ann["abstained"] = False
                result.annotations = dict(ann)
                return result

            verdict = verify(
                contract_source=contract_source,
                contract_name=contract_name,
                poc_code=poc_code,
                verifier_mode=verifier_mode,
            )
            result.execution_result = verdict["execution_result"]
            result.execution_trace = verdict["execution_trace"]
            result.error_summary = verdict["error_summary"]
            result.wall_clock_s += verdict["wall_clock_s"]
            cascade_step["verdicts"].append(verdict["execution_result"])

            if verdict["execution_result"] == "pass":
                result.finding_confirmed = True
                result.finding_reason = (
                    f"PoC succeeded at cascade depth {cand_idx + 1} (target={target!r})"
                )
                cascade_step["outcome"] = "pass"
                candidate_resolved = True
                break

            if verdict["execution_result"] == "fail_revert_ac":
                cascade_step["outcome"] = "fail_revert_ac"
                candidate_resolved = True
                break

            error_history.append(verdict["error_summary"])
            result.error_history = list(error_history)

            if verdict["execution_result"] == "fail_error_runtime":
                runtime_fail_count += 1
                if runtime_fail_count >= 2:
                    # Day-4 Issue 1: 2nd runtime fail on same candidate →
                    # likely the function isn't the bug; advance cascade.
                    cascade_step["outcome"] = "advanced_runtime_fail"
                    runtime_advance = True
                    break
                # else: 1st runtime fail → retry once
            # fail_error_compile → fall through to retry (existing behavior)

        cand_idx += 1

        if result.finding_confirmed:
            break  # cascade success — exit

        if not (candidate_resolved or runtime_advance):
            # Inner retries exhausted on compile-fails (no runtime escape) →
            # PoC writer couldn't compile a valid PoC for this candidate.
            # Honor Critic #10: abstain rather than advance, since this is
            # PoC-side error not candidate-side evidence.
            cascade_step["outcome"] = "abstain_retry_exhausted"
            abstained = True
            break  # exit cascade

        # candidate_resolved (fail_revert_ac) OR runtime_advance → continue outer
        prev_target = target
        prev_verdict = (
            "fail_revert_ac" if candidate_resolved else "fail_error_runtime"
        )
        prev_error = result.error_summary

    # Terminal reasoning
    if abstained:
        result.execution_result = "abstain"
        result.finding_reason = (
            f"Cascade abstained at depth {len(cascade_trace)}: PoC retries "
            f"exhausted (last error: {result.error_summary[:200]})"
        )
    elif not result.finding_confirmed:
        result.finding_reason = (
            f"All top-{len(top_k)} candidates intercepted by access control "
            f"— contract appears safe for these functions"
        )

    ann["cascade_trace"] = cascade_trace
    ann["abstained"] = abstained
    result.annotations = dict(ann)
    return result
