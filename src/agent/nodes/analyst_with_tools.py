"""Analyst tool-use wrapper — single augmented call (Day-4 Issue 2).

Day-2 ORIGINAL behavior (preserved here for transparency):
  1. Pre-tool baseline analyze() (1 LLM call)
  2. Build static-fact tool block (deterministic, list_functions + body of
     pre top-1 candidate)
  3. Post-tool analyze() with augmented context (1 LLM call)
  Total: 2 LLM calls per case → "dual-log" (pre/post hypothesis)

Day-3 EMPIRICAL FINDING:
  Across 10 smoke cases (agent-full vs zero-shot baseline), 4/10 cases
  produced IDENTICAL top-1 predictions in the dual-call (pre == post). The
  doubling of LLM cost did not measurably shift analyst output.

Day-4 ISSUE 2 CHANGE:
  Single augmented LLM call. Build the deterministic tool block FIRST
  (`suspicious_summary` from static analyzer — pre-narrows the function
  pool), inject it into `static_context`, then call analyze() ONCE with the
  augmented context. The dual-log fields (`analyst_hypothesis_pre_tool` /
  `_post_tool`) are still populated for downstream consumer stability — both
  point at the single result.

Documented in `.omc/plans/day4-routing-reversal-disclosure.md` as a
disclosed post-Day-3 simplification motivated by zero-shot tied baseline.
"""

from __future__ import annotations

import re

from agent.adapters.static_analyzer import analyze as static_analyze
from agent.nodes.analyst import AnalystPrediction, analyze, analyze_consistent
from agent.state import AuditAnnotations


# Day-4 Issue 3 — self-consistency over n analyst runs (RRF voting).
# Pre-test on 6 non-pass cases showed 3/6 (50%) divergence between single-shot
# and SC=3 (above the ≥2 acceptance gate). Notable: ACF-102 recovered from a
# `skipped` (single-shot returned empty target) to a real candidate under
# SC=3. Wired here as the default when use_tools=True.
DEFAULT_N_CONSISTENCY = 3


def analyze_with_tools(
    contract_source: str,
    contract_name: str,
    annotations: AuditAnnotations,
    *,
    use_tools: bool = True,
    static_context: str = "",
    rag_few_shot: str = "",
    n_consistency: int = DEFAULT_N_CONSISTENCY,
) -> AnalystPrediction:
    """Augmented analyst call with optional self-consistency.

    When `use_tools=True`:
      - Builds deterministic static-fact tool block (`suspicious_summary`).
      - Runs analyst with `n_consistency` runs (RRF top-3 voting); n=1 falls
        back to single `analyze()` call.

    When `use_tools=False`: passes `static_context` through unchanged and
    runs single `analyze()` call (n_consistency ignored).

    Dual-log fields populated for downstream consumer stability — both
    point at the (potentially RRF-aggregated) result.
    """
    if use_tools:
        tool_block = _build_tool_block(
            contract_source=contract_source,
            contract_name=contract_name,
        )
        augmented_static = (
            f"{static_context}\n\n{tool_block}".strip()
            if static_context
            else tool_block
        )
    else:
        augmented_static = static_context

    if use_tools and n_consistency > 1:
        pred = analyze_consistent(
            contract_source=contract_source,
            contract_name=contract_name,
            annotations=annotations,
            static_context=augmented_static,
            rag_few_shot=rag_few_shot,
            n_runs=n_consistency,
        )
    else:
        pred = analyze(
            contract_source=contract_source,
            contract_name=contract_name,
            annotations=annotations,
            static_context=augmented_static,
            rag_few_shot=rag_few_shot,
        )

    annotations["analyst_hypothesis_pre_tool"] = pred["hypothesis"]
    annotations["analyst_hypothesis_post_tool"] = pred["hypothesis"]
    return pred


# ---------------------------------------------------------------------------
# Deterministic tool helpers
# ---------------------------------------------------------------------------


_FN_BODY_RE_TMPL = (
    r"function\s+{name}\s*\([^)]*\)[^{{]*\{{(?P<body>(?:[^{{}}]|\{{[^{{}}]*\}})*)\}}"
)


def _build_tool_block(
    contract_source: str,
    contract_name: str,
) -> str:
    """Day-4 Issue 2 — deterministic static-fact tool block.

    Single tool: `suspicious_summary` from the static analyzer. This pre-narrows
    the function pool to externally-callable, state-changing, AC-modifier-free
    candidates — directs the analyst at the most likely targets without
    requiring a separate LLM round-trip to identify them.

    Falls back gracefully on analyzer failure (no LLM impact, just fewer hints).
    """
    parts: list[str] = ["## Static analysis: suspicious functions"]
    try:
        facts = static_analyze(contract_source, contract_name)
        parts.append(facts.suspicious_summary())
    except Exception as exc:  # pragma: no cover - defensive
        parts.append(f"(static analyzer failed: {exc})")
    return "\n\n".join(parts)


def _get_function_body(contract_source: str, fn_name: str) -> str | None:
    """Best-effort regex slice of a function body. Returns None on no match."""
    if not fn_name:
        return None
    pattern = _FN_BODY_RE_TMPL.format(name=re.escape(fn_name))
    m = re.search(pattern, contract_source, re.DOTALL)
    if not m:
        return None
    return m.group("body").strip()
