"""
Lightweight LangGraph workflow used by the demo.
"""

from typing import Literal

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from .config import get_settings
from .state_schema import AuditGraphState
from ..nodes.analyst import analyze_access_control, retrieve_similar_cases
from ..nodes.builder import build_verification_poc
from ..nodes.preprocess_static import preprocess_static_analysis
from ..nodes.verifier import verify_poc

_vectorstore = None


def get_vectorstore():
    global _vectorstore

    if _vectorstore is None:
        settings = get_settings()
        if settings.use_rag:
            try:
                from ..rag.vectorstore import VulnerabilityVectorStore

                _vectorstore = VulnerabilityVectorStore(
                    persist_directory=settings.vectorstore_path,
                    use_openai_embeddings=not settings.use_local_embeddings,
                )
                print(f"VectorStore initialized: {settings.vectorstore_path}")
            except Exception as exc:
                print(f"Warning: Could not initialize VectorStore: {exc}")
                _vectorstore = None
    return _vectorstore


def rag_retrieval_node(state: AuditGraphState) -> AuditGraphState:
    return retrieve_similar_cases(state, get_vectorstore())


def should_use_rag(state: AuditGraphState) -> Literal["rag", "skip"]:
    return "rag" if state.get("use_rag", True) else "skip"


def should_continue(state: AuditGraphState) -> Literal["refine", "report", "safe"]:
    result = state.get("execution_result", "pending")
    retry_count = state.get("retry_count", 0)
    max_retries = state.get("max_retries", 3)

    if result == "pass":
        return "report"
    if result == "fail_revert":
        return "safe"
    if result == "fail_error" and retry_count < max_retries:
        return "refine"
    return "safe"


def generate_report(state: AuditGraphState) -> AuditGraphState:
    findings = state.get("findings", [])
    findings.append(
        {
            "function": state.get("current_target_function", ""),
            "hypothesis": state.get("audit_hypothesis", ""),
            "poc": state.get("verification_poc", ""),
            "confirmed": True,
            "similar_cases_used": len(state.get("similar_cases", [])),
            "static_candidates_used": len(state.get("sensitive_candidates", [])),
        }
    )
    return {
        **state,
        "findings": findings,
        "audit_report": {
            "contract_name": state.get("contract_name", ""),
            "total_findings": len(findings),
            "findings": findings,
            "status": "vulnerabilities_found",
            "rag_enhanced": len(state.get("similar_cases", [])) > 0,
            "static_analysis_used": state.get("use_static_analysis", True),
        },
        "finding_confirmed": True,
    }


def mark_safe(state: AuditGraphState) -> AuditGraphState:
    return {
        **state,
        "audit_report": {
            "contract_name": state.get("contract_name", ""),
            "total_findings": 0,
            "findings": [],
            "status": "no_vulnerabilities_found",
            "rag_enhanced": len(state.get("similar_cases", [])) > 0,
            "static_analysis_used": state.get("use_static_analysis", True),
        },
        "finding_confirmed": False,
    }


def create_audit_graph(use_rag: bool = True) -> StateGraph:
    workflow = StateGraph(AuditGraphState)

    workflow.add_node("preprocess_static", preprocess_static_analysis)
    workflow.add_node("rag_retrieval", rag_retrieval_node)
    workflow.add_node("analyst", analyze_access_control)
    workflow.add_node("builder", build_verification_poc)
    workflow.add_node("verifier", verify_poc)
    workflow.add_node("report", generate_report)
    workflow.add_node("safe", mark_safe)

    workflow.set_entry_point("preprocess_static")
    if use_rag:
        workflow.add_conditional_edges(
            "preprocess_static",
            should_use_rag,
            {
                "rag": "rag_retrieval",
                "skip": "analyst",
            },
        )
        workflow.add_edge("rag_retrieval", "analyst")
    else:
        workflow.add_edge("preprocess_static", "analyst")

    workflow.add_edge("analyst", "builder")
    workflow.add_edge("builder", "verifier")
    workflow.add_conditional_edges(
        "verifier",
        should_continue,
        {
            "refine": "builder",
            "report": "report",
            "safe": "safe",
        },
    )
    workflow.add_edge("report", END)
    workflow.add_edge("safe", END)
    return workflow


def compile_graph(checkpointer: bool = True, use_rag: bool = True):
    workflow = create_audit_graph(use_rag=use_rag)
    if checkpointer:
        return workflow.compile(checkpointer=MemorySaver())
    return workflow.compile()


def load_dataset_to_vectorstore(dataset_path: str) -> int:
    vectorstore = get_vectorstore()
    if vectorstore is None:
        print("Error: VectorStore not initialized. Check USE_RAG setting.")
        return 0
    return vectorstore.load_from_dataset(dataset_path)
