"""
Embedding generation for vulnerability knowledge base.
"""

from typing import List
from langchain_openai import OpenAIEmbeddings
from langchain_community.embeddings import HuggingFaceEmbeddings

from ..core.config import get_settings


def get_openai_embeddings() -> OpenAIEmbeddings:
    """获取 OpenAI 嵌入模型"""
    settings = get_settings()
    return OpenAIEmbeddings(
        api_key=settings.openai_api_key,
        model="text-embedding-3-small"
    )


def get_local_embeddings() -> HuggingFaceEmbeddings:
    """获取本地 HuggingFace 嵌入模型"""
    return HuggingFaceEmbeddings(
        model_name="sentence-transformers/all-MiniLM-L6-v2",
        model_kwargs={'device': 'cpu'},
        encode_kwargs={'normalize_embeddings': True}
    )


class CodeEmbeddings:
    """
    专门用于代码的嵌入生成器。
    
    可以处理:
    - Solidity 源码
    - 漏洞描述
    - PoC 代码
    """
    
    def __init__(self, use_openai: bool = True):
        self.use_openai = use_openai
        if use_openai:
            self.embeddings = get_openai_embeddings()
        else:
            self.embeddings = get_local_embeddings()
    
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """嵌入多个文档"""
        return self.embeddings.embed_documents(texts)
    
    def embed_query(self, text: str) -> List[float]:
        """嵌入单个查询"""
        return self.embeddings.embed_query(text)
    
    def embed_contract(self, source_code: str) -> List[float]:
        """
        嵌入合约源码。
        
        预处理步骤:
        1. 移除注释
        2. 标准化空白字符
        3. 提取关键结构
        """
        processed = self._preprocess_solidity(source_code)
        return self.embed_query(processed)
    
    def _preprocess_solidity(self, code: str) -> str:
        """预处理 Solidity 代码"""
        import re
        
        # 移除单行注释
        code = re.sub(r'//.*', '', code)
        # 移除多行注释
        code = re.sub(r'/\*.*?\*/', '', code, flags=re.DOTALL)
        # 标准化空白
        code = ' '.join(code.split())
        
        return code
