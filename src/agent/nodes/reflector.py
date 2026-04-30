"""Day-2 T9 — Reflection node (LOCKED).

The reflection node is a single LLM re-prompt that runs between cascade
candidate advances. It receives the prior attempt's (target, hypothesis,
verdict, error_summary) plus the analyst's top-K candidate list, and returns
a refined `(target_function, hypothesis)` for the next cascade step.

**LOCKED invariant** (Critic acceptance bar #3):
    The returned `target_function` MUST be a member of the input `candidates`
    list. The reflection node CANNOT introduce new candidates — that would
    require a different state-mutation contract, and on n=10 + cascade
    early-exit the experiment can't validate "expand candidate set" cleanly.

Failure mode: if the LLM returns an off-list `target_function`, the reflector
silently falls back to the first un-tried candidate, logging the deviation
into `reflection_trace` for downstream auditing.

This module is import-cheap (no LLM call at import); call `reflect()` to
trigger a single LLM round-trip. The cascade router can choose whether to
call it (currently opt-in via `enable_reflection` flag).
"""

from __future__ import annotations

import json
import re
from typing import TypedDict

from agent.adapters.llm import invoke_json
from agent.state import AuditAnnotations


class ReflectionOutput(TypedDict):
    target_function: str
    hypothesis: str
    reasoning: str
    candidate_in_set: bool  # False if the LLM returned an off-list candidate


SYSTEM_PROMPT = """You are a reflection step inside a smart-contract security
audit cascade. The previous attempt to exploit a candidate function failed.
Your job: pick the NEXT candidate to try from a FIXED list, and refine the
exploitation hypothesis.

**HARD CONSTRAINT — DO NOT VIOLATE:**
Your output `target_function` MUST be a member of the provided
`available_candidates` list, verbatim. You may NOT invent new function names.

Output STRICT JSON with exactly:
{
  "target_function": "<verbatim from available_candidates>",
  "hypothesis": "<one-sentence refined exploit hypothesis>",
  "reasoning": "<one-sentence rationale for the pick>"
}
"""


USER_PROMPT_TEMPLATE = """A cascade attempt just terminated. Decide what to try next.

Prior target function: {prior_target}
Prior hypothesis: {prior_hypothesis}
Prior verdict: {prior_verdict}
Prior error summary: {prior_error}

Available candidates (PICK FROM THIS LIST ONLY):
{candidates_block}

Already-tried candidates (avoid re-picking unless no others remain):
{tried_block}

Return JSON as specified."""


def _format_list(items: list[str]) -> str:
    if not items:
        return "  (none)"
    return "\n".join(f"  - {x}" for x in items)


def reflect(
    *,
    prior_target: str,
    prior_hypothesis: str,
    prior_verdict: str,
    prior_error: str,
    candidates: list[str],
    tried_candidates: list[str],
    annotations: AuditAnnotations,
) -> ReflectionOutput:
    """Single-call reflection. Always returns an in-set `target_function`.

    Falls back deterministically when the LLM returns an off-list candidate.
    Mutates `annotations` (token counts via invoke_json; appends a
    `reflection_trace` entry).
    """
    if not candidates:
        return ReflectionOutput(
            target_function="",
            hypothesis=prior_hypothesis,
            reasoning="reflection skipped: no candidates",
            candidate_in_set=True,
        )

    user_prompt = USER_PROMPT_TEMPLATE.format(
        prior_target=prior_target or "<none>",
        prior_hypothesis=prior_hypothesis or "<none>",
        prior_verdict=prior_verdict or "<none>",
        prior_error=(prior_error or "<none>")[:300],
        candidates_block=_format_list(candidates),
        tried_block=_format_list(tried_candidates),
    )

    raw = invoke_json(SYSTEM_PROMPT, user_prompt, annotations)
    parsed = _safe_parse_json(raw)
    target = str(parsed.get("target_function", "")).strip()
    hypothesis = str(parsed.get("hypothesis", "")).strip() or prior_hypothesis
    reasoning = str(parsed.get("reasoning", "")).strip()

    in_set = target in candidates
    if not in_set:
        # LOCKED invariant violation — fall back to first un-tried candidate.
        fallback = next(
            (c for c in candidates if c not in tried_candidates),
            candidates[0],
        )
        target = fallback
        reasoning = (
            f"[locked-fallback: LLM returned off-list candidate; substituted "
            f"{fallback!r}] {reasoning}"
        )

    trace_entry = {
        "prior_target": prior_target,
        "prior_verdict": prior_verdict,
        "picked_target": target,
        "in_set": in_set,
        "reasoning": reasoning[:200],
    }
    rt = annotations.get("reflection_trace") or []
    rt.append(trace_entry)
    annotations["reflection_trace"] = rt

    return ReflectionOutput(
        target_function=target,
        hypothesis=hypothesis,
        reasoning=reasoning,
        candidate_in_set=in_set,
    )


def _safe_parse_json(raw: str) -> dict:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        cleaned = (raw or "").strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("```", 2)[1]
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]
            cleaned = cleaned.strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            # Last resort: regex an object literal out of the response.
            m = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if m:
                try:
                    return json.loads(m.group(0))
                except json.JSONDecodeError:
                    pass
            return {}
