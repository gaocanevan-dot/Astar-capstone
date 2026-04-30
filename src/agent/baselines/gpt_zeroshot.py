"""GPT-X zero-shot baseline.

Single-prompt analyst: no static facts, no RAG few-shot, no retry loop. This is
the "raw LLM" comparison against our RAG-enhanced analyst. The prompt is
deliberately minimal so we don't accidentally coach the model.
"""

from __future__ import annotations

import json
import time

from agent.adapters.llm import invoke_json
from agent.baselines import PredictionRecord
from agent.state import empty_annotations


SYSTEM_PROMPT = """You are a smart-contract security auditor. Given Solidity
source, identify access-control vulnerabilities. Rank the TOP-3 functions
most likely to lack adequate access control or allow privilege escalation.

Return STRICT JSON:
{
  "is_vulnerable": boolean,
  "vulnerable_functions": [string]  // EXACTLY up to 3 function names, ordered by likelihood (most-likely first). If you cannot find any, return [].
}
"""


USER_PROMPT_TEMPLATE = """Contract name: {contract_name}

```solidity
{contract_source}
```

Return JSON as specified."""


def _truncate(source: str, max_chars: int = 20000) -> str:
    if len(source) <= max_chars:
        return source
    return source[:max_chars] + f"\n// ... (truncated; original {len(source)} chars)"


def evaluate(case) -> PredictionRecord:
    t0 = time.time()
    if not (case.contract_source or "").strip():
        return PredictionRecord(
            case_id=case.id,
            contract_name=case.contract_name,
            ground_truth_function=case.vulnerable_function or "",
            flagged=False,
            flagged_functions=[],
            predicted_function="",
            error="empty contract_source",
            method="gpt_zeroshot",
            wall_clock_seconds=time.time() - t0,
        )

    ann = empty_annotations()
    user_prompt = USER_PROMPT_TEMPLATE.format(
        contract_name=case.contract_name,
        contract_source=_truncate(case.contract_source),
    )
    try:
        raw = invoke_json(SYSTEM_PROMPT, user_prompt, ann)
    except Exception as exc:
        return PredictionRecord(
            case_id=case.id,
            contract_name=case.contract_name,
            ground_truth_function=case.vulnerable_function or "",
            flagged=False,
            flagged_functions=[],
            predicted_function="",
            error=f"{type(exc).__name__}: {exc}",
            method="gpt_zeroshot",
            wall_clock_seconds=time.time() - t0,
            tokens_prompt=ann.get("tokens_prompt", 0),
            tokens_completion=ann.get("tokens_completion", 0),
            llm_calls=ann.get("llm_calls", 0),
        )

    # Parse
    flagged = False
    flagged_functions: list[str] = []
    error = ""
    try:
        data = json.loads(raw)
        flagged = bool(data.get("is_vulnerable", False))
        fns = data.get("vulnerable_functions", []) or []
        if isinstance(fns, list):
            flagged_functions = [str(f) for f in fns if f]
    except json.JSONDecodeError as e:
        error = f"JSON parse failed: {e}"

    return PredictionRecord(
        case_id=case.id,
        contract_name=case.contract_name,
        ground_truth_function=case.vulnerable_function or "",
        flagged=flagged,
        flagged_functions=flagged_functions,
        predicted_function=flagged_functions[0] if flagged_functions else "",
        tokens_prompt=ann.get("tokens_prompt", 0),
        tokens_completion=ann.get("tokens_completion", 0),
        llm_calls=ann.get("llm_calls", 0),
        wall_clock_seconds=time.time() - t0,
        raw_output=raw[:2000],
        error=error,
        method="gpt_zeroshot",
    )
