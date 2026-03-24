"""
Vulnerability Retriever for RAG-enhanced audit.

Implements retrieval strategies for:
1. Similar vulnerability patterns
2. Few-shot PoC examples
3. Fix recommendations
"""

from typing import List, Dict, Optional
from langchain_core.documents import Document

from .vectorstore import VulnerabilityVectorStore
from ..core.state_schema import AuditGraphState


class VulnerabilityRetriever:
    """
    漏洞检索器，用于 RAG 增强审计。
    
    检索策略:
    1. 基于代码相似度检索
    2. 基于漏洞类型检索
    3. 混合检索 (代码 + 描述)
    """
    
    def __init__(self, vectorstore: VulnerabilityVectorStore):
        self.vectorstore = vectorstore
    
    def retrieve_similar_vulnerabilities(
        self,
        contract_source: str,
        vulnerability_type: Optional[str] = None,
        k: int = 5
    ) -> List[Dict]:
        """
        检索与目标合约相似的历史漏洞。
        
        用于 Node 1 (Analyst) 的 Few-Shot 上下文增强。
        """
        docs = self.vectorstore.search_similar(
            query=contract_source,
            k=k,
            filter_type=vulnerability_type
        )
        
        return self._docs_to_dict(docs)
    
    def retrieve_poc_examples(
        self,
        audit_hypothesis: str,
        target_function: str,
        k: int = 3
    ) -> List[str]:
        """
        检索相关的 PoC 代码示例。
        
        用于 Node 2 (Builder) 的 Few-Shot 示例。
        """
        # 构建查询
        query = f"""
Access control vulnerability in function: {target_function}
Hypothesis: {audit_hypothesis}
PoC test code for Foundry
"""
        
        docs = self.vectorstore.search_similar(query, k=k)
        
        # 提取 PoC 代码部分
        poc_examples = []
        for doc in docs:
            content = doc.page_content
            # 简单提取 PoC 代码块
            if "PoC Code:" in content:
                poc_part = content.split("PoC Code:")[-1]
                poc_part = poc_part.split("Fix Recommendation:")[0]
                poc_examples.append(poc_part.strip())
        
        return poc_examples
    
    def retrieve_fix_recommendations(
        self,
        vulnerability_type: str,
        k: int = 3
    ) -> List[str]:
        """
        检索修复建议。
        
        用于最终报告生成。
        """
        query = f"Fix recommendation for {vulnerability_type} vulnerability"
        
        docs = self.vectorstore.search_similar(
            query,
            k=k,
            filter_type=vulnerability_type
        )
        
        recommendations = []
        for doc in docs:
            content = doc.page_content
            if "Fix Recommendation:" in content:
                fix_part = content.split("Fix Recommendation:")[-1]
                recommendations.append(fix_part.strip())
        
        return recommendations
    
    def enrich_state_with_rag(self, state: AuditGraphState) -> AuditGraphState:
        """
        使用 RAG 检索结果丰富状态。
        
        在审计流程开始前调用，为各节点提供上下文。
        """
        contract_source = state.get("contract_source", "")
        
        # 检索相似漏洞
        similar_vulns = self.retrieve_similar_vulnerabilities(
            contract_source,
            vulnerability_type="Access Control",
            k=5
        )
        
        # 检索 Few-Shot 示例
        few_shot = self.retrieve_poc_examples(
            audit_hypothesis=state.get("audit_hypothesis", ""),
            target_function=state.get("current_target_function", ""),
            k=3
        )
        
        return {
            **state,
            "similar_vulnerabilities": similar_vulns,
            "few_shot_examples": few_shot
        }
    
    def _docs_to_dict(self, docs: List[Document]) -> List[Dict]:
        """将文档列表转换为字典列表"""
        return [
            {
                "content": doc.page_content,
                "metadata": doc.metadata
            }
            for doc in docs
        ]


def create_retriever(
    persist_directory: str = "./data/vectorstore",
    use_openai: bool = True
) -> VulnerabilityRetriever:
    """创建检索器实例"""
    vectorstore = VulnerabilityVectorStore(
        persist_directory=persist_directory,
        use_openai_embeddings=use_openai
    )
    return VulnerabilityRetriever(vectorstore)
