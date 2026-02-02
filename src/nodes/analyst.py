"""
Node 1: Access Control Analyst (访问控制分析节点)

核心改动: 集成 RAG 检索，分析前先检索数据集中的相似漏洞案例
作为 Few-Shot 上下文增强 LLM 的分析能力
"""

from typing import Dict, List, Optional
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser

from ..core.state import AuditGraphState
from ..core.config import get_settings


def _build_few_shot_context(similar_cases: List[Dict]) -> str:
    """
    从检索到的相似案例构建 Few-Shot 上下文
    """
    if not similar_cases:
        return ""
    
    context_parts = ["Here are similar vulnerability cases from our knowledge base:\n"]
    
    for i, case in enumerate(similar_cases[:3], 1):  # 最多3个示例
        context_parts.append(f"""
--- Example {i} ---
Vulnerability Type: {case.get('vulnerability_type', 'unknown')}
Function: {case.get('function', 'unknown')}
Description: {case.get('description', '')}
Missing Check: {case.get('missing_check', '')}
---
""")
    
    return "\n".join(context_parts)


# 带 RAG 增强的分析提示模板
ANALYST_PROMPT_WITH_RAG = ChatPromptTemplate.from_messages([
    ("system", """You are a smart contract security auditor specializing in access control vulnerabilities.

{few_shot_context}

Analyze the given Solidity contract and identify ONLY:
1. **Access Control Vulnerabilities**: Functions missing proper access control (e.g., missing onlyOwner)
2. **Privilege Escalation**: Vulnerabilities allowing unauthorized role changes

For each sensitive function, check:
- Does it modify critical state (balances, fees, addresses)?
- Does it have appropriate access control modifiers?
- Can an unauthorized user call it?

IMPORTANT: Learn from the similar cases above when analyzing.

Output JSON:
{{
    "sensitive_functions": [
        {{
            "name": "functionName",
            "has_access_control": false,
            "modifiers": [],
            "risk_level": "high|medium|low",
            "concern": "Description of the access control issue"
        }}
    ],
    "is_vulnerable": true/false,
    "vulnerability_type": "access_control" or "privilege_escalation" or null,
    "audit_hypothesis": "Description of the suspected vulnerability"
}}"""),
    ("human", """Analyze this contract for access control vulnerabilities:

```solidity
{contract_source}
```

Contract name: {contract_name}""")
])


# 无 RAG 的基础提示模板 (后备)
ANALYST_PROMPT_BASIC = ChatPromptTemplate.from_messages([
    ("system", """You are a smart contract security auditor specializing in access control vulnerabilities.

Analyze the given Solidity contract and identify ONLY:
1. **Access Control Vulnerabilities**: Functions missing proper access control (e.g., missing onlyOwner)
2. **Privilege Escalation**: Vulnerabilities allowing unauthorized role changes

For each sensitive function, check:
- Does it modify critical state (balances, fees, addresses)?
- Does it have appropriate access control modifiers?
- Can an unauthorized user call it?

Output JSON:
{{
    "sensitive_functions": [
        {{
            "name": "functionName",
            "has_access_control": false,
            "modifiers": [],
            "risk_level": "high|medium|low",
            "concern": "Description of the access control issue"
        }}
    ],
    "is_vulnerable": true/false,
    "vulnerability_type": "access_control" or "privilege_escalation" or null,
    "audit_hypothesis": "Description of the suspected vulnerability"
}}"""),
    ("human", """Analyze this contract for access control vulnerabilities:

```solidity
{contract_source}
```

Contract name: {contract_name}""")
])


def analyze_access_control(state: AuditGraphState) -> AuditGraphState:
    """
    分析合约的访问控制漏洞
    
    核心改动: 使用 RAG 检索到的相似案例作为 Few-Shot 上下文
    
    输入: contract_source, similar_cases (可选)
    输出: sensitive_functions, audit_hypothesis
    """
    settings = get_settings()
    
    llm = ChatOpenAI(
        model=settings.openai_model,
        temperature=0.1,
        api_key=settings.openai_api_key
    )
    
    # 获取 RAG 检索结果
    similar_cases = state.get("similar_cases", [])
    few_shot_context = _build_few_shot_context(similar_cases)
    
    # 选择合适的提示模板
    if few_shot_context:
        prompt = ANALYST_PROMPT_WITH_RAG
        chain = prompt | llm | JsonOutputParser()
        invoke_params = {
            "few_shot_context": few_shot_context,
            "contract_source": state["contract_source"],
            "contract_name": state.get("contract_name", "Contract")
        }
    else:
        prompt = ANALYST_PROMPT_BASIC
        chain = prompt | llm | JsonOutputParser()
        invoke_params = {
            "contract_source": state["contract_source"],
            "contract_name": state.get("contract_name", "Contract")
        }
    
    try:
        result = chain.invoke(invoke_params)
        
        # 找出高风险且无访问控制的函数
        sensitive_funcs = result.get("sensitive_functions", [])
        vulnerable_funcs = [
            f for f in sensitive_funcs 
            if not f.get("has_access_control", True) and f.get("risk_level") == "high"
        ]
        
        target_function = vulnerable_funcs[0]["name"] if vulnerable_funcs else ""
        
        return {
            **state,
            "sensitive_functions": sensitive_funcs,
            "audit_hypothesis": result.get("audit_hypothesis", ""),
            "current_target_function": target_function
        }
        
    except Exception as e:
        return {
            **state,
            "error_message": f"Analysis failed: {str(e)}",
            "sensitive_functions": [],
            "audit_hypothesis": "Analysis failed"
        }


def retrieve_similar_cases(state: AuditGraphState, vectorstore=None) -> AuditGraphState:
    """
    从向量库检索相似的漏洞案例
    
    这是 RAG 的核心: 在分析前先检索数据集
    
    输入: contract_source
    输出: similar_cases, few_shot_examples
    """
    if vectorstore is None:
        # 没有向量库，跳过检索
        return state
    
    try:
        # 检索相似漏洞
        docs = vectorstore.search_by_code(
            code_snippet=state["contract_source"],
            k=5
        )
        
        # 转换为案例格式
        similar_cases = []
        for doc in docs:
            similar_cases.append({
                "id": doc.metadata.get("id", ""),
                "vulnerability_type": doc.metadata.get("vulnerability_type", ""),
                "function": doc.metadata.get("function", ""),
                "description": doc.page_content[:500],  # 截断长文本
                "missing_check": doc.metadata.get("missing_check", ""),
                "severity": doc.metadata.get("severity", "")
            })
        
        return {
            **state,
            "similar_cases": similar_cases,
            "few_shot_examples": similar_cases[:3]  # Few-shot 用前3个
        }
        
    except Exception as e:
        print(f"Warning: RAG retrieval failed: {e}")
        return state


def extract_functions_simple(source_code: str) -> List[Dict]:
    """
    简单的函数提取 (正则方式)
    作为 LLM 分析的补充/后备
    """
    import re
    
    functions = []
    
    # 匹配函数定义
    pattern = r'function\s+(\w+)\s*\([^)]*\)\s*(public|external|internal|private)?[^{]*{'
    matches = re.finditer(pattern, source_code)
    
    for match in matches:
        func_name = match.group(1)
        visibility = match.group(2) or "public"
        
        # 检查是否有修饰符
        func_line = match.group(0)
        has_only_owner = "onlyOwner" in func_line or "onlyAdmin" in func_line
        
        functions.append({
            "name": func_name,
            "visibility": visibility,
            "has_access_control": has_only_owner
        })
    
    return functions
