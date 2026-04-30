"""LangGraph-native implementation of the audit agent.

Provides four **compile-time distinct** graphs per plan §5 Phase 2 US-013:
  - build_graph_full            : preprocess_static → rag_retrieve → analyst → builder → verifier (retry loop)
  - build_graph_no_static       : rag_retrieve → analyst → builder → verifier (retry loop)
  - build_graph_no_rag          : preprocess_static → analyst → builder → verifier (retry loop)
  - build_graph_no_verify_loop  : preprocess_static → rag_retrieve → analyst → builder → mark_vulnerable_on_poc → END

Each arm is a separate `StateGraph.compile()` call — the ablation is *structural*,
not `if use_rag: ...`. Consumers (runner scripts) pick an arm by name.

Coexists with the simpler `src/agent/graph.py::run_pipeline()` (sequential Python);
see docs/ARCHITECTURE.md §LangGraph migration.
"""

from __future__ import annotations

import time
from operator import add
from typing import Annotated, Optional, TypedDict

from langgraph.graph import END, StateGraph

from agent.adapters.rag import TfidfRagStore, format_few_shot_context
from agent.adapters.static_analyzer import analyze as static_analyze
from agent.nodes.analyst import analyze as analyst_fn
from agent.nodes.builder import build_poc
from agent.nodes.verifier import verify
from agent.state import empty_annotations


MAX_RETRIES_DEFAULT = 3


class AuditGraphState(TypedDict, total=False):
    """Shared state threaded through all graph nodes.

    `error_history` uses `Annotated[..., add]` so retries APPEND rather than
    overwrite (LangGraph semantic). Everything else is replace-on-write.
    """
    # --- inputs ---
    case_id: str
    contract_source: str
    contract_name: str
    max_retries: int
    # Day-2 Prereq-A: verifier_mode threaded from smoke manifest into the
    # forge invocation. None = legacy text-sniff fallback.
    verifier_mode: Optional[str]

    # --- preprocess_static output (if arm includes it) ---
    static_context: str

    # --- rag_retrieve output (if arm includes it) ---
    rag_few_shot: str

    # --- analyst output ---
    target_function: str
    hypothesis: str
    confidence: float
    reasoning: str

    # --- builder output ---
    verification_poc: str
    poc_attempts: int
    error_history: Annotated[list[str], add]  # append on retries

    # --- verifier output ---
    execution_result: str  # pass / fail_revert_ac / fail_error / skipped
    execution_trace: str
    error_summary: str

    # --- terminal ---
    finding_confirmed: bool
    finding_reason: str

    # --- meta ---
    annotations: dict
    wall_clock_s: float


def _init_state(
    case_id: str,
    contract_source: str,
    contract_name: str,
    max_retries: int = MAX_RETRIES_DEFAULT,
    verifier_mode: str | None = None,
) -> AuditGraphState:
    return AuditGraphState(
        case_id=case_id,
        contract_source=contract_source,
        contract_name=contract_name,
        max_retries=max_retries,
        verifier_mode=verifier_mode,
        static_context="",
        rag_few_shot="",
        target_function="",
        hypothesis="",
        confidence=0.0,
        reasoning="",
        verification_poc="",
        poc_attempts=0,
        error_history=[],
        execution_result="pending",
        execution_trace="",
        error_summary="",
        finding_confirmed=False,
        finding_reason="",
        annotations=dict(empty_annotations()),
        wall_clock_s=0.0,
    )


# ============================================================
# Node functions — each takes state, returns a partial update
# ============================================================


def _node_preprocess_static(state: AuditGraphState) -> dict:
    try:
        facts = static_analyze(state["contract_source"], state["contract_name"])
        return {"static_context": facts.compact_summary()}
    except Exception as exc:  # pragma: no cover
        return {"static_context": f"(static analyzer failed: {exc})"}


def _make_rag_retrieve(rag_store: Optional[TfidfRagStore]):
    def _node_rag_retrieve(state: AuditGraphState) -> dict:
        if rag_store is None or len(rag_store) == 0:
            return {"rag_few_shot": ""}
        retrieved = rag_store.retrieve(
            state["contract_source"], top_k=3, exclude_id=state["case_id"]
        )
        return {"rag_few_shot": format_few_shot_context(retrieved)}
    return _node_rag_retrieve


def _node_analyst(state: AuditGraphState) -> dict:
    ann = state.get("annotations") or dict(empty_annotations())
    ann["case_id"] = state["case_id"]
    ann["contract_name"] = state["contract_name"]
    if not (state.get("contract_source") or "").strip():
        return {
            "target_function": "",
            "hypothesis": "",
            "confidence": 0.0,
            "reasoning": "",
            "annotations": ann,
            "finding_reason": "empty contract_source",
            "execution_result": "skipped",
        }
    pred = analyst_fn(
        state["contract_source"],
        state["contract_name"],
        ann,
        static_context=state.get("static_context", ""),
        rag_few_shot=state.get("rag_few_shot", ""),
    )
    return {
        "target_function": pred["target_function"],
        "hypothesis": pred["hypothesis"],
        "confidence": pred["confidence"],
        "reasoning": pred["reasoning"],
        "annotations": ann,
    }


def _node_builder(state: AuditGraphState) -> dict:
    # Early-exit if analyst produced no target (don't waste a builder call)
    if not state.get("target_function"):
        return {
            "verification_poc": "",
            "poc_attempts": state.get("poc_attempts", 0),
            "finding_reason": "analyst returned empty target_function",
            "execution_result": "skipped",
        }

    ann = state.get("annotations") or dict(empty_annotations())
    poc_code = build_poc(
        contract_source=state["contract_source"],
        contract_name=state["contract_name"],
        target_function=state["target_function"],
        hypothesis=state.get("hypothesis", ""),
        error_history=state.get("error_history", []),
        annotations=ann,
    )
    return {
        "verification_poc": poc_code,
        "poc_attempts": state.get("poc_attempts", 0) + 1,
        "annotations": ann,
    }


def _node_verifier(state: AuditGraphState) -> dict:
    # If the pre-verifier nodes marked the run skipped, don't invoke forge
    if state.get("execution_result") == "skipped":
        return {}
    t0 = time.time()
    verdict = verify(
        contract_source=state["contract_source"],
        contract_name=state["contract_name"],
        poc_code=state.get("verification_poc", ""),
        verifier_mode=state.get("verifier_mode"),
    )
    elapsed = time.time() - t0
    return {
        "execution_result": verdict["execution_result"],
        "execution_trace": verdict["execution_trace"],
        "error_summary": verdict["error_summary"],
        "error_history": (
            [verdict["error_summary"]]
            if verdict["execution_result"] in ("fail_error_compile", "fail_error_runtime")
            else []
        ),
        "wall_clock_s": state.get("wall_clock_s", 0.0) + elapsed,
    }


def _node_report(state: AuditGraphState) -> dict:
    return {
        "finding_confirmed": True,
        "finding_reason": "PoC executed and attack succeeded",
    }


def _node_mark_safe(state: AuditGraphState) -> dict:
    res = state.get("execution_result")
    if res == "fail_revert_ac":
        reason = "Access control intercepted the attack — contract appears safe for this function"
    elif res == "skipped":
        reason = state.get("finding_reason") or "pipeline skipped (no source or no target function)"
    else:
        attempts = state.get("poc_attempts", 0)
        err = state.get("error_summary", "")[:200]
        reason = f"Gave up after {attempts} attempts; last error: {err}"
    return {"finding_confirmed": False, "finding_reason": reason}


def _node_mark_vulnerable_on_poc(state: AuditGraphState) -> dict:
    """no_verify_loop arm: if builder produced a PoC, claim vulnerable without running forge."""
    has_poc = bool(state.get("verification_poc", "").strip())
    return {
        "execution_result": "pass" if has_poc else "skipped",
        "finding_confirmed": has_poc,
        "finding_reason": (
            "PoC generated (no verifier — no-verify-loop arm)"
            if has_poc else "no PoC produced"
        ),
    }


# ============================================================
# Routers — conditional edges
# ============================================================


def _router_analyst_result(state: AuditGraphState) -> str:
    """If analyst already marked skipped (empty source), go straight to mark_safe."""
    if state.get("execution_result") == "skipped":
        return "mark_safe"
    return "builder"


def _router_builder_result(state: AuditGraphState) -> str:
    """If builder skipped (no target), go to mark_safe; else continue to verifier."""
    if state.get("execution_result") == "skipped":
        return "mark_safe"
    return "verifier"


def _router_verify_result(state: AuditGraphState) -> str:
    """After verifier: report on pass, mark_safe on AC-revert, builder-retry on error."""
    result = state.get("execution_result")
    if result == "pass":
        return "report"
    if result == "fail_revert_ac":
        return "mark_safe"
    # Day-1 T2 verdict split: route both compile-fail and runtime-fail back
    # to builder for retry until cascade router (Day-2) refines this. Day-2
    # will route fail_error_runtime post-retry to abstain instead.
    if result in ("fail_error_compile", "fail_error_runtime") and state.get(
        "poc_attempts", 0
    ) < state.get("max_retries", MAX_RETRIES_DEFAULT):
        return "builder"
    return "mark_safe"


def _router_builder_result_no_verify(state: AuditGraphState) -> str:
    """For no_verify_loop arm: after builder, either mark_vulnerable or mark_safe."""
    if state.get("execution_result") == "skipped":
        return "mark_safe"
    return "mark_vulnerable_on_poc"


# ============================================================
# Graph factories — one per ablation arm
# ============================================================


def _add_verify_loop(g: StateGraph) -> None:
    """Shared sub-constructor for the arms that include the verifier loop."""
    g.add_node("verifier", _node_verifier)
    g.add_node("report", _node_report)
    g.add_node("mark_safe", _node_mark_safe)
    g.add_edge("builder", "verifier")
    g.add_conditional_edges(
        "verifier",
        _router_verify_result,
        {"report": "report", "mark_safe": "mark_safe", "builder": "builder"},
    )
    g.add_edge("report", END)
    g.add_edge("mark_safe", END)


def build_graph_full(rag_store: Optional[TfidfRagStore] = None):
    """Arm 1: preprocess_static → rag_retrieve → analyst → builder → verifier loop."""
    g = StateGraph(AuditGraphState)
    g.add_node("preprocess_static", _node_preprocess_static)
    g.add_node("rag_retrieve", _make_rag_retrieve(rag_store))
    g.add_node("analyst", _node_analyst)
    g.add_node("builder", _node_builder)
    g.set_entry_point("preprocess_static")
    g.add_edge("preprocess_static", "rag_retrieve")
    g.add_edge("rag_retrieve", "analyst")
    g.add_conditional_edges(
        "analyst", _router_analyst_result, {"builder": "builder", "mark_safe": "mark_safe"}
    )
    g.add_conditional_edges(
        "builder", _router_builder_result, {"verifier": "verifier", "mark_safe": "mark_safe"}
    )
    _add_verify_loop(g)
    return g.compile()


def build_graph_no_static(rag_store: Optional[TfidfRagStore] = None):
    """Arm 2: no preprocess_static node at all."""
    g = StateGraph(AuditGraphState)
    g.add_node("rag_retrieve", _make_rag_retrieve(rag_store))
    g.add_node("analyst", _node_analyst)
    g.add_node("builder", _node_builder)
    g.set_entry_point("rag_retrieve")
    g.add_edge("rag_retrieve", "analyst")
    g.add_conditional_edges(
        "analyst", _router_analyst_result, {"builder": "builder", "mark_safe": "mark_safe"}
    )
    g.add_conditional_edges(
        "builder", _router_builder_result, {"verifier": "verifier", "mark_safe": "mark_safe"}
    )
    _add_verify_loop(g)
    return g.compile()


def build_graph_no_rag():
    """Arm 3: no rag_retrieve node at all."""
    g = StateGraph(AuditGraphState)
    g.add_node("preprocess_static", _node_preprocess_static)
    g.add_node("analyst", _node_analyst)
    g.add_node("builder", _node_builder)
    g.set_entry_point("preprocess_static")
    g.add_edge("preprocess_static", "analyst")
    g.add_conditional_edges(
        "analyst", _router_analyst_result, {"builder": "builder", "mark_safe": "mark_safe"}
    )
    g.add_conditional_edges(
        "builder", _router_builder_result, {"verifier": "verifier", "mark_safe": "mark_safe"}
    )
    _add_verify_loop(g)
    return g.compile()


def build_graph_no_verify_loop(rag_store: Optional[TfidfRagStore] = None):
    """Arm 4: no verifier node; mark vulnerable directly on PoC generation."""
    g = StateGraph(AuditGraphState)
    g.add_node("preprocess_static", _node_preprocess_static)
    g.add_node("rag_retrieve", _make_rag_retrieve(rag_store))
    g.add_node("analyst", _node_analyst)
    g.add_node("builder", _node_builder)
    g.add_node("mark_vulnerable_on_poc", _node_mark_vulnerable_on_poc)
    g.add_node("mark_safe", _node_mark_safe)
    g.set_entry_point("preprocess_static")
    g.add_edge("preprocess_static", "rag_retrieve")
    g.add_edge("rag_retrieve", "analyst")
    g.add_conditional_edges(
        "analyst", _router_analyst_result, {"builder": "builder", "mark_safe": "mark_safe"}
    )
    g.add_conditional_edges(
        "builder",
        _router_builder_result_no_verify,
        {"mark_vulnerable_on_poc": "mark_vulnerable_on_poc", "mark_safe": "mark_safe"},
    )
    g.add_edge("mark_vulnerable_on_poc", END)
    g.add_edge("mark_safe", END)
    return g.compile()


# Registry for runners
GRAPH_FACTORIES = {
    "full": build_graph_full,
    "no-static": build_graph_no_static,
    "no-rag": build_graph_no_rag,
    "no-verify-loop": build_graph_no_verify_loop,
}


def build_graph(arm: str, rag_store: Optional[TfidfRagStore] = None):
    """Select and compile a graph by arm name."""
    if arm not in GRAPH_FACTORIES:
        raise ValueError(f"Unknown arm {arm!r}; choose from {list(GRAPH_FACTORIES)}")
    factory = GRAPH_FACTORIES[arm]
    # no-rag doesn't take rag_store
    if arm == "no-rag":
        return factory()
    return factory(rag_store=rag_store)


def run_single_case(
    case_id: str,
    contract_source: str,
    contract_name: str,
    arm: str = "full",
    max_retries: int = MAX_RETRIES_DEFAULT,
    rag_store: Optional[TfidfRagStore] = None,
):
    """Convenience: build the arm, invoke on one case, return final state."""
    graph = build_graph(arm, rag_store=rag_store)
    initial = _init_state(
        case_id=case_id,
        contract_source=contract_source,
        contract_name=contract_name,
        max_retries=max_retries,
    )
    # Recursion limit must cover: analyst + builder + verifier + retry * max_retries + terminal
    return graph.invoke(initial, config={"recursion_limit": 50 + max_retries * 3})
