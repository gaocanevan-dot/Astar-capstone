"""
Shared State Schema for the Audit Agent.

专注于访问控制和权限升级漏洞检测。
支持 RAG 增强 (从数据集检索相似案例)。
"""

from typing import TypedDict, List, Dict, Optional, Literal
from pydantic import BaseModel, Field
from enum import Enum


class VulnerabilityType(str, Enum):
    """漏洞类型枚举 - 仅支持访问控制相关"""
    ACCESS_CONTROL = "access_control"
    PRIVILEGE_ESCALATION = "privilege_escalation"


class SensitiveFunction(BaseModel):
    """敏感函数的结构化定义"""
    name: str = Field(description="函数名称")
    signature: str = Field(description="函数签名")
    has_access_control: bool = Field(default=False, description="是否有访问控制")
    modifiers: List[str] = Field(default_factory=list, description="函数修饰符列表")
    risk_level: Literal["high", "medium", "low"] = Field(default="medium")


class VulnerabilityFinding(BaseModel):
    """漏洞发现 - 简化版"""
    function_name: str
    vulnerability_type: VulnerabilityType
    severity: Literal["critical", "high", "medium", "low"]
    description: str
    poc_code: str = ""


class RetrievedCase(BaseModel):
    """从数据集检索到的相似案例"""
    id: str = Field(description="案例ID")
    vulnerability_type: str = Field(description="漏洞类型")
    description: str = Field(description="漏洞描述")
    affected_code: str = Field(description="漏洞代码片段")
    poc_code: str = Field(default="", description="PoC 代码")
    similarity_score: float = Field(default=0.0, description="相似度分数")


# ===== Agent 状态定义 =====

class AuditGraphState(TypedDict):
    """
    审计状态 Schema
    
    支持 RAG 增强的访问控制漏洞检测
    """
    
    # --- 输入 ---
    contract_source: str                    # 合约源码
    contract_name: str                      # 合约名称
    
    # --- RAG 检索结果 (核心新增!) ---
    similar_cases: List[Dict]               # 检索到的相似漏洞案例
    few_shot_examples: List[Dict]           # Few-Shot 示例
    
    # --- 分析结果 ---
    sensitive_functions: List[Dict]         # 敏感函数列表
    audit_hypothesis: str                   # 审计假说
    current_target_function: str            # 当前目标函数
    
    # --- 验证 ---
    verification_poc: str                   # PoC 代码
    execution_result: Literal["pass", "fail_revert", "fail_error", "pending"]
    error_message: str
    
    # --- 控制流 ---
    retry_count: int
    max_retries: int
    
    # --- 输出 ---
    finding_confirmed: bool
    findings: List[Dict]
    audit_report: Dict


def create_initial_state(
    contract_source: str,
    contract_name: str = "TargetContract",
    max_retries: int = 3
) -> AuditGraphState:
    """创建初始状态"""
    return AuditGraphState(
        # 输入
        contract_source=contract_source,
        contract_name=contract_name,
        
        # RAG 检索结果
        similar_cases=[],
        few_shot_examples=[],
        
        # 分析结果
        sensitive_functions=[],
        audit_hypothesis="",
        current_target_function="",
        
        # 验证
        verification_poc="",
        execution_result="pending",
        error_message="",
        
        # 控制流
        retry_count=0,
        max_retries=max_retries,
        
        # 输出
        finding_confirmed=False,
        findings=[],
        audit_report={}
    )
