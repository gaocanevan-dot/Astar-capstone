"""
Vector store for vulnerability knowledge base.

Supports:
- Pinecone (cloud)
- Milvus (self-hosted)
- Chroma (local development)

核心改动: 支持从用户数据集加载漏洞案例
"""

from typing import List, Dict, Optional, Any
from dataclasses import dataclass
from pathlib import Path

from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document

from .embeddings import get_openai_embeddings, get_local_embeddings
from ..core.config import get_settings


@dataclass
class VulnerabilityRecord:
    """漏洞记录"""
    id: str
    title: str
    description: str
    vulnerability_type: str  # e.g., "Access Control", "Reentrancy"
    severity: str  # Critical, High, Medium, Low
    affected_code: str  # 漏洞代码片段
    poc_code: str  # PoC 代码
    fix_recommendation: str
    cve_id: Optional[str] = None
    cwe_id: Optional[str] = None
    metadata: Dict[str, Any] = None


class VulnerabilityVectorStore:
    """
    漏洞知识向量库。
    
    用于存储和检索历史漏洞案例，
    支持 RAG 增强审计分析。
    """
    
    def __init__(
        self,
        collection_name: str = "vulnerabilities",
        persist_directory: str = "./data/vectorstore",
        use_openai_embeddings: bool = True
    ):
        self.collection_name = collection_name
        self.persist_directory = persist_directory
        
        # 选择嵌入模型
        if use_openai_embeddings:
            self.embeddings = get_openai_embeddings()
        else:
            self.embeddings = get_local_embeddings()
        
        # 初始化 Chroma (本地开发用)
        self.vectorstore = Chroma(
            collection_name=collection_name,
            embedding_function=self.embeddings,
            persist_directory=persist_directory
        )
    
    def add_vulnerability(self, record: VulnerabilityRecord) -> str:
        """添加单个漏洞记录"""
        # 构建文档内容
        content = f"""
Vulnerability: {record.title}
Type: {record.vulnerability_type}
Severity: {record.severity}

Description:
{record.description}

Affected Code:
```solidity
{record.affected_code}
```

PoC Code:
```solidity
{record.poc_code}
```

Fix Recommendation:
{record.fix_recommendation}
"""
        
        metadata = {
            "id": record.id,
            "title": record.title,
            "vulnerability_type": record.vulnerability_type,
            "severity": record.severity,
            "cve_id": record.cve_id or "",
            "cwe_id": record.cwe_id or ""
        }
        if record.metadata:
            metadata.update(record.metadata)
        
        doc = Document(page_content=content, metadata=metadata)
        
        self.vectorstore.add_documents([doc])
        
        return record.id
    
    def add_vulnerabilities(self, records: List[VulnerabilityRecord]) -> List[str]:
        """批量添加漏洞记录"""
        ids = []
        for record in records:
            id = self.add_vulnerability(record)
            ids.append(id)
        return ids
    
    def search_similar(
        self,
        query: str,
        k: int = 5,
        filter_type: Optional[str] = None,
        filter_severity: Optional[str] = None
    ) -> List[Document]:
        """
        搜索相似漏洞。
        
        Args:
            query: 查询文本 (可以是代码或描述)
            k: 返回结果数量
            filter_type: 过滤特定漏洞类型
            filter_severity: 过滤特定严重程度
        """
        # 构建过滤条件
        filter_dict = {}
        if filter_type:
            filter_dict["vulnerability_type"] = filter_type
        if filter_severity:
            filter_dict["severity"] = filter_severity
        
        if filter_dict:
            results = self.vectorstore.similarity_search(
                query,
                k=k,
                filter=filter_dict
            )
        else:
            results = self.vectorstore.similarity_search(query, k=k)
        
        return results
    
    def search_by_code(
        self,
        code_snippet: str,
        k: int = 5
    ) -> List[Document]:
        """
        根据代码片段搜索相似漏洞。
        
        专门用于分析待审计代码与历史漏洞的相似性。
        """
        return self.search_similar(query=code_snippet, k=k)
    
    def delete_vulnerability(self, id: str) -> bool:
        """删除漏洞记录"""
        try:
            self.vectorstore.delete([id])
            return True
        except Exception:
            return False
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取向量库统计信息"""
        collection = self.vectorstore._collection
        return {
            "total_documents": collection.count(),
            "collection_name": self.collection_name
        }
    
    def load_from_dataset(self, dataset_path: str) -> int:
        """
        从用户数据集加载漏洞案例到向量库
        
        这是核心功能: 将你手动构建的数据集加载到 RAG 系统
        
        Args:
            dataset_path: 数据集文件路径 (JSON/JSONL)
        
        Returns:
            加载的文档数量
        """
        from ..dataset.loader import DatasetLoader
        
        loader = DatasetLoader(dataset_path)
        loader.load()
        
        # 获取 RAG 文档格式
        rag_docs = loader.get_rag_documents()
        
        # 转换为 LangChain Document
        documents = []
        for doc in rag_docs:
            documents.append(Document(
                page_content=doc["content"],
                metadata=doc["metadata"]
            ))
        
        # 添加到向量库
        if documents:
            self.vectorstore.add_documents(documents)
            print(f"Loaded {len(documents)} vulnerability cases into vector store")
        
        return len(documents)
    
    def clear(self):
        """清空向量库"""
        try:
            # 获取所有文档的ID并删除
            collection = self.vectorstore._collection
            all_ids = collection.get()["ids"]
            if all_ids:
                self.vectorstore.delete(all_ids)
            print("Vector store cleared")
        except Exception as e:
            print(f"Warning: Could not clear vector store: {e}")

