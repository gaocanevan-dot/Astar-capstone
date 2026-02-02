"""
LangGraph Workflow - RAG 增强版

访问控制漏洞检测工作流
支持从数据集检索相似案例作为 Few-Shot 上下文
"""

from typing import Literal, Optional
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from .state import AuditGraphState
from .config import get_settings
from ..nodes.analyst import analyze_access_control, retrieve_similar_cases
from ..nodes.builder import build_verification_poc
from ..nodes.verifier import verify_poc


# 全局向量库实例 (延迟初始化)
_vectorstore = None


def get_vectorstore():
    """获取或初始化向量库"""
    global _vectorstore
    
    if _vectorstore is None:
        settings = get_settings()
        if settings.use_rag:
            try:
                from ..rag.vectorstore import VulnerabilityVectorStore
                _vectorstore = VulnerabilityVectorStore(
                    persist_directory=settings.vectorstore_path,
                    use_openai_embeddings=not settings.use_local_embeddings
                )
                print(f"VectorStore initialized: {settings.vectorstore_path}")
            except Exception as e:
                print(f"Warning: Could not initialize VectorStore: {e}")
                _vectorstore = None
    
    return _vectorstore


def rag_retrieval_node(state: AuditGraphState) -> AuditGraphState:
    """
    RAG 检索节点
    
    在分析前检索数据集中的相似漏洞案例
    """
    vectorstore = get_vectorstore()
    return retrieve_similar_cases(state, vectorstore)


def should_continue(state: AuditGraphState) -> Literal["refine", "report", "safe"]:
    """
    决策函数
    
    - pass: 漏洞确认 → 报告
    - fail_revert: 权限拦截 → 安全
    - fail_error: 代码错误 → 重试
    """
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
    """生成漏洞报告"""
    findings = state.get("findings", [])
    
    findings.append({
        "function": state.get("current_target_function", ""),
        "hypothesis": state.get("audit_hypothesis", ""),
        "poc": state.get("verification_poc", ""),
        "confirmed": True,
        "similar_cases_used": len(state.get("similar_cases", []))  # 记录使用了多少相似案例
    })
    
    return {
        **state,
        "findings": findings,
        "audit_report": {
            "contract_name": state.get("contract_name", ""),
            "total_findings": len(findings),
            "findings": findings,
            "status": "vulnerabilities_found",
            "rag_enhanced": len(state.get("similar_cases", [])) > 0
        },
        "finding_confirmed": True
    }


def mark_safe(state: AuditGraphState) -> AuditGraphState:
    """标记安全"""
    return {
        **state,
        "audit_report": {
            "contract_name": state.get("contract_name", ""),
            "total_findings": 0,
            "findings": [],
            "status": "no_vulnerabilities_found"
        },
        "finding_confirmed": False
    }


def create_audit_graph(use_rag: bool = True) -> StateGraph:
    """
    创建审计工作流
    
    新增 RAG 检索节点:
    [rag_retrieval] → analyst → builder → verifier → [决策]
                                  ↑                     |
                                  └─────── refine ──────┘
    """
    workflow = StateGraph(AuditGraphState)
    
    # 节点
    if use_rag:
        workflow.add_node("rag_retrieval", rag_retrieval_node)
    workflow.add_node("analyst", analyze_access_control)
    workflow.add_node("builder", build_verification_poc)
    workflow.add_node("verifier", verify_poc)
    workflow.add_node("report", generate_report)
    workflow.add_node("safe", mark_safe)
    
    # 边
    if use_rag:
        workflow.set_entry_point("rag_retrieval")
        workflow.add_edge("rag_retrieval", "analyst")
    else:
        workflow.set_entry_point("analyst")
    
    workflow.add_edge("analyst", "builder")
    workflow.add_edge("builder", "verifier")
    
    # 条件边
    workflow.add_conditional_edges(
        "verifier",
        should_continue,
        {
            "refine": "builder",
            "report": "report",
            "safe": "safe"
        }
    )
    
    workflow.add_edge("report", END)
    workflow.add_edge("safe", END)
    
    return workflow


def compile_graph(checkpointer: bool = True, use_rag: bool = True):
    """编译工作流"""
    workflow = create_audit_graph(use_rag=use_rag)
    
    if checkpointer:
        memory = MemorySaver()
        return workflow.compile(checkpointer=memory)
    
    return workflow.compile()


def load_dataset_to_vectorstore(dataset_path: str) -> int:
    """
    加载数据集到向量库
    
    这是使用 RAG 前的必要步骤
    
    Returns:
        加载的文档数量
    """
    vectorstore = get_vectorstore()
    if vectorstore is None:
        print("Error: VectorStore not initialized. Check USE_RAG setting.")
        return 0
    
    return vectorstore.load_from_dataset(dataset_path)
