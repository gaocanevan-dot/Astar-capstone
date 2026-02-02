"""
Training Data Schemas - 训练数据格式定义

定义用于微调 LLM 的数据结构，专注于访问控制和权限升级漏洞。
"""

from typing import List, Dict, Optional, Literal
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum


class VulnerabilityType(str, Enum):
    """支持的漏洞类型"""
    ACCESS_CONTROL = "access_control"
    PRIVILEGE_ESCALATION = "privilege_escalation"


class TaskType(str, Enum):
    """任务类型"""
    ANALYZE = "analyze"           # 分析合约识别漏洞
    GENERATE_POC = "generate_poc" # 生成 PoC 代码
    VERIFY = "verify"             # 验证漏洞是否存在


class VulnerabilityLabel(BaseModel):
    """漏洞标注"""
    function_name: str = Field(description="存在漏洞的函数名")
    vulnerability_type: VulnerabilityType = Field(description="漏洞类型")
    severity: Literal["critical", "high", "medium", "low"] = Field(description="严重程度")
    description: str = Field(description="漏洞描述")
    line_numbers: List[int] = Field(default_factory=list, description="相关代码行号")
    missing_check: str = Field(default="", description="缺失的检查 (如 onlyOwner)")


class AnalysisInput(BaseModel):
    """分析任务输入"""
    contract_source: str = Field(description="Solidity 源代码")
    contract_name: str = Field(default="", description="合约名称")


class AnalysisOutput(BaseModel):
    """分析任务输出"""
    is_vulnerable: bool = Field(description="是否存在漏洞")
    vulnerable_functions: List[str] = Field(default_factory=list, description="存在漏洞的函数列表")
    vulnerability_type: Optional[VulnerabilityType] = Field(default=None)
    hypothesis: str = Field(default="", description="漏洞假说")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="置信度")


class PoCInput(BaseModel):
    """PoC 生成任务输入"""
    contract_source: str = Field(description="合约源代码")
    contract_name: str = Field(description="合约名称")
    target_function: str = Field(description="目标函数")
    vulnerability_hypothesis: str = Field(description="漏洞假说")


class PoCOutput(BaseModel):
    """PoC 生成任务输出"""
    poc_code: str = Field(description="Foundry 测试代码")
    attack_steps: List[str] = Field(default_factory=list, description="攻击步骤说明")


class TrainingExample(BaseModel):
    """
    单个训练样本
    
    格式设计便于后续转换为各种 LLM 微调格式:
    - OpenAI fine-tuning format
    - Alpaca format
    - ShareGPT format
    """
    id: str = Field(description="唯一标识符")
    task_type: TaskType = Field(description="任务类型")
    
    # 输入输出
    input_data: Dict = Field(description="输入数据")
    output_data: Dict = Field(description="期望输出")
    
    # 元数据
    metadata: Dict = Field(default_factory=dict, description="附加元数据")
    
    # 来源信息
    source: Literal["manual", "auto", "external"] = Field(default="manual")
    confirmed: bool = Field(default=False, description="是否经过验证")
    created_at: datetime = Field(default_factory=datetime.now)
    
    def to_openai_format(self) -> Dict:
        """转换为 OpenAI fine-tuning 格式"""
        system_prompts = {
            TaskType.ANALYZE: "You are a smart contract security auditor specializing in access control vulnerabilities.",
            TaskType.GENERATE_POC: "You are a security researcher who writes Foundry test cases to verify vulnerabilities.",
            TaskType.VERIFY: "You are a security analyst who verifies if a vulnerability exists based on test results."
        }
        
        return {
            "messages": [
                {"role": "system", "content": system_prompts.get(self.task_type, "")},
                {"role": "user", "content": self._format_input()},
                {"role": "assistant", "content": self._format_output()}
            ]
        }
    
    def to_alpaca_format(self) -> Dict:
        """转换为 Alpaca 格式"""
        instructions = {
            TaskType.ANALYZE: "Analyze the following smart contract for access control vulnerabilities.",
            TaskType.GENERATE_POC: "Generate a Foundry PoC test to verify the access control vulnerability.",
            TaskType.VERIFY: "Determine if the vulnerability exists based on the test execution result."
        }
        
        return {
            "instruction": instructions.get(self.task_type, ""),
            "input": self._format_input(),
            "output": self._format_output()
        }
    
    def _format_input(self) -> str:
        """格式化输入为字符串"""
        if self.task_type == TaskType.ANALYZE:
            return f"```solidity\n{self.input_data.get('contract_source', '')}\n```"
        elif self.task_type == TaskType.GENERATE_POC:
            return (
                f"Contract:\n```solidity\n{self.input_data.get('contract_source', '')}\n```\n"
                f"Target Function: {self.input_data.get('target_function', '')}\n"
                f"Hypothesis: {self.input_data.get('vulnerability_hypothesis', '')}"
            )
        return str(self.input_data)
    
    def _format_output(self) -> str:
        """格式化输出为字符串"""
        import json
        return json.dumps(self.output_data, indent=2)


class TrainingDataset(BaseModel):
    """训练数据集"""
    name: str = Field(description="数据集名称")
    version: str = Field(default="1.0.0")
    description: str = Field(default="")
    
    examples: List[TrainingExample] = Field(default_factory=list)
    
    # 统计信息
    total_examples: int = Field(default=0)
    vulnerability_distribution: Dict[str, int] = Field(default_factory=dict)
    
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    
    def add_example(self, example: TrainingExample):
        """添加样本"""
        self.examples.append(example)
        self.total_examples = len(self.examples)
        self._update_distribution()
        self.updated_at = datetime.now()
    
    def _update_distribution(self):
        """更新漏洞类型分布"""
        self.vulnerability_distribution = {}
        for ex in self.examples:
            vtype = ex.output_data.get("vulnerability_type", "unknown")
            self.vulnerability_distribution[vtype] = self.vulnerability_distribution.get(vtype, 0) + 1
    
    def export_openai_format(self) -> List[Dict]:
        """导出为 OpenAI 格式"""
        return [ex.to_openai_format() for ex in self.examples]
    
    def export_alpaca_format(self) -> List[Dict]:
        """导出为 Alpaca 格式"""
        return [ex.to_alpaca_format() for ex in self.examples]
    
    def save_jsonl(self, filepath: str, format: Literal["openai", "alpaca"] = "openai"):
        """保存为 JSONL 文件"""
        import json
        
        if format == "openai":
            data = self.export_openai_format()
        else:
            data = self.export_alpaca_format()
        
        with open(filepath, 'w', encoding='utf-8') as f:
            for item in data:
                f.write(json.dumps(item, ensure_ascii=False) + '\n')
