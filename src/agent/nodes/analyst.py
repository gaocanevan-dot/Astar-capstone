"""Access-control analyst node — single-agent variant.

One-shot LLM call: contract source → JSON {target_function, hypothesis,
confidence, reasoning}. No static analysis, no RAG (those come online when the
full LangGraph variant activates).
"""

from __future__ import annotations

import json
from typing import TypedDict

from agent.adapters.llm import invoke_json
from agent.state import AuditAnnotations


class AnalystPrediction(TypedDict):
    target_function: str        # top-1 candidate, == candidates[0] when present
    candidates: list[str]       # top-k ranked candidate functions (up to 3)
    hypothesis: str
    confidence: float
    reasoning: str
    raw_response: str


SYSTEM_PROMPT = """You are a smart-contract security auditor specialized in access-control
vulnerabilities. Given Solidity source code, rank the TOP-3 functions most
likely to lack adequate access control OR allow privilege escalation.

Focus on:
- State-changing external/public functions without onlyOwner / AccessControl / role-check
- Upgrade paths without initializer guards
- Role-transfer functions that accept arbitrary addresses

Output strict JSON with exactly these keys:
{
  "candidates": [
      "name of the #1 most likely vulnerable function",
      "name of the #2 most likely vulnerable function",
      "name of the #3 most likely vulnerable function"
  ],
  "target_function": "same as candidates[0] — kept for backward compatibility",
  "hypothesis": "one-sentence description of the access-control weakness in candidates[0]",
  "confidence": 0.0-1.0 float for candidates[0],
  "reasoning": "brief explanation of why candidates[0] is the primary target"
}

Rules:
- `candidates` MUST be a list of up to 3 distinct function names, ordered by likelihood
- If you truly cannot find any suspicious function, emit `candidates: []` and `target_function: ""`
- If you can only find 1 or 2, still output a list of 1 or 2 (don't invent fillers)
- `target_function` must equal `candidates[0]` when candidates is non-empty"""


USER_PROMPT_TEMPLATE = """Analyze this Solidity contract for access-control vulnerabilities.

Contract name: {contract_name}
{static_block}{rag_block}
```solidity
{contract_source}
```

Return JSON as specified."""


def analyze(
    contract_source: str,
    contract_name: str,
    annotations: AuditAnnotations,
    static_context: str = "",
    rag_few_shot: str = "",
) -> AnalystPrediction:
    """Run single-agent analyst on one contract. Mutates annotations.

    `static_context` and `rag_few_shot` are optional — when empty, the prompt
    is identical to the original single-agent variant (preserves baseline).
    """
    static_block = f"\n## Static analysis facts\n{static_context}\n" if static_context else ""
    rag_block = f"\n## Similar known-vulnerable cases (few-shot)\n{rag_few_shot}\n" if rag_few_shot else ""

    user_prompt = USER_PROMPT_TEMPLATE.format(
        contract_name=contract_name,
        contract_source=_truncate_source(contract_source),
        static_block=static_block,
        rag_block=rag_block,
    )
    raw = invoke_json(SYSTEM_PROMPT, user_prompt, annotations)

    parsed = _safe_parse(raw)
    raw_candidates = parsed.get("candidates") or []
    candidates: list[str] = []
    if isinstance(raw_candidates, list):
        for c in raw_candidates:
            if isinstance(c, str):
                name = c.strip()
            elif isinstance(c, dict):
                # Tolerate {"function": "fn", ...} shape
                name = str(c.get("function") or c.get("name") or "").strip()
            else:
                continue
            if name and name not in candidates:
                candidates.append(name)
            if len(candidates) >= 3:
                break

    target_function = str(parsed.get("target_function", "")).strip()
    # Reconcile: if candidates empty but target_function set, use it
    if not candidates and target_function:
        candidates = [target_function]
    # If candidates set but target_function missing, use candidates[0]
    if candidates and not target_function:
        target_function = candidates[0]

    return AnalystPrediction(
        target_function=target_function,
        candidates=candidates,
        hypothesis=str(parsed.get("hypothesis", "")).strip(),
        confidence=_safe_float(parsed.get("confidence", 0.0)),
        reasoning=str(parsed.get("reasoning", "")).strip(),
        raw_response=raw,
    )


def analyze_consistent(
    contract_source: str,
    contract_name: str,
    annotations: AuditAnnotations,
    static_context: str = "",
    rag_few_shot: str = "",
    n_runs: int = 5,
) -> AnalystPrediction:
    """Self-consistency: run `analyze` N times, vote on top-3 by reciprocal-rank.

    Score for candidate c = sum over runs of (1 / rank), where rank is c's
    position in that run's top-3 (1-indexed). Higher score = more consistent.

    The hypothesis/confidence/reasoning are inherited from the run whose top-1
    matches the consensus top-1; this keeps the explanation aligned with the
    final ranked answer rather than averaging incoherent text.

    Tokens & llm_calls accumulate across all N runs (annotations is mutated).
    """
    if n_runs <= 1:
        return analyze(
            contract_source, contract_name, annotations,
            static_context=static_context, rag_few_shot=rag_few_shot,
        )

    runs: list[AnalystPrediction] = []
    for _ in range(n_runs):
        runs.append(
            analyze(
                contract_source, contract_name, annotations,
                static_context=static_context, rag_few_shot=rag_few_shot,
            )
        )

    scores: dict[str, float] = {}
    for run in runs:
        for rank, cand in enumerate(run["candidates"], start=1):
            scores[cand] = scores.get(cand, 0.0) + 1.0 / rank
    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    top3 = [name for name, _ in ranked[:3]]
    target = top3[0] if top3 else ""

    # Inherit hypothesis/reasoning from the first run whose top-1 == consensus top-1
    chosen = next(
        (r for r in runs if r["candidates"] and r["candidates"][0] == target),
        runs[0],
    )

    return AnalystPrediction(
        target_function=target,
        candidates=top3,
        hypothesis=chosen["hypothesis"],
        confidence=chosen["confidence"],
        reasoning=(
            f"[self-consistency over {n_runs} runs; consensus top-1={target!r}] "
            + chosen["reasoning"]
        ),
        raw_response="",
    )


def _truncate_source(source: str, max_chars: int = 20000) -> str:
    """Keep prompt tokens bounded. GPT-4-turbo handles ~128k context but
    our bill scales with prompt length."""
    if len(source) <= max_chars:
        return source
    return (
        source[:max_chars]
        + f"\n\n// ... (truncated; original was {len(source)} chars)"
    )


def _safe_parse(raw: str) -> dict:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Some models sometimes wrap in ```json ... ```; try a brute-force strip
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("```", 2)[1]
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]
            cleaned = cleaned.strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            return {}


def _safe_float(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0
