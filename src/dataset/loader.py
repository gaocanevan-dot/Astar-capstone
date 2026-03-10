"""
Dataset Loader - 数据集加载器

从文件加载用户已有的漏洞数据集，用于:
1. RAG 知识增强 (加载到向量库)
2. Few-Shot 示例选择
3. 评估测试
"""

import json
from pathlib import Path
from typing import List, Dict, Optional, Iterator, Union
from datetime import datetime

from pydantic import BaseModel, Field

from .schemas import (
    TrainingExample,
    TrainingDataset,
    TaskType,
    VulnerabilityType
)


class VulnerabilityCase(BaseModel):
    """
    漏洞案例 - 数据集中的单条记录
    
    这是你手动构建的数据集的标准格式
    """
    id: str = Field(description="唯一标识符")
    
    # 合约信息
    contract_source: str = Field(description="合约源代码")
    contract_name: str = Field(default="", description="合约名称")
    
    # 漏洞信息
    vulnerable_function: str = Field(description="存在漏洞的函数名")
    vulnerability_type: VulnerabilityType = Field(description="漏洞类型")
    severity: str = Field(default="high", description="严重程度")
    
    # 漏洞描述
    description: str = Field(description="漏洞描述")
    missing_check: str = Field(default="", description="缺失的检查，如 onlyOwner")
    
    # PoC 信息
    poc_code: str = Field(default="", description="验证漏洞的 PoC 代码")
    attack_steps: List[str] = Field(default_factory=list, description="攻击步骤")
    
    # 修复建议
    fix_recommendation: str = Field(default="", description="修复建议")
    fixed_code: str = Field(default="", description="修复后的代码")
    
    # 元数据
    source: str = Field(default="manual", description="数据来源")
    tags: List[str] = Field(default_factory=list, description="标签")
    created_at: Optional[datetime] = None
    
    def to_rag_document(self) -> Dict:
        """转换为 RAG 文档格式"""
        # 构建元数据。像 Chroma 这类向量库对部分字段（如 tags）有非空要求，
        # 因此我们只在 tags 非空时才添加该字段，避免空列表导致 upsert 失败。
        metadata = {
            "id": self.id,
            "vulnerability_type": self.vulnerability_type.value,
            "severity": self.severity,
            "function": self.vulnerable_function,
            "missing_check": self.missing_check,
        }
        if self.tags:
            metadata["tags"] = self.tags

        return {
            "id": self.id,
            "content": f"""
Vulnerability Type: {self.vulnerability_type.value}
Severity: {self.severity}
Function: {self.vulnerable_function}

Description:
{self.description}

Vulnerable Code:
```solidity
{self.contract_source}
```

PoC Code:
```solidity
{self.poc_code}
```

Fix Recommendation:
{self.fix_recommendation}
""",
            "metadata": metadata,
        }
    
    def to_training_example(self, task_type: TaskType = TaskType.ANALYZE) -> TrainingExample:
        """转换为训练样本"""
        if task_type == TaskType.ANALYZE:
            input_data = {
                "contract_source": self.contract_source,
                "contract_name": self.contract_name
            }
            output_data = {
                "is_vulnerable": True,
                "vulnerable_functions": [self.vulnerable_function],
                "vulnerability_type": self.vulnerability_type.value,
                "hypothesis": self.description
            }
        elif task_type == TaskType.GENERATE_POC:
            input_data = {
                "contract_source": self.contract_source,
                "contract_name": self.contract_name,
                "target_function": self.vulnerable_function,
                "vulnerability_hypothesis": self.description
            }
            output_data = {
                "poc_code": self.poc_code,
                "attack_steps": self.attack_steps
            }
        else:
            input_data = {"case_id": self.id}
            output_data = {"confirmed": True}
        
        return TrainingExample(
            id=f"{task_type.value}_{self.id}",
            task_type=task_type,
            input_data=input_data,
            output_data=output_data,
            metadata={
                "severity": self.severity,
                "missing_check": self.missing_check,
                "source": self.source
            },
            source="manual",
            confirmed=True  # 手动构建的数据已确认
        )


class DatasetLoader:
    """
    数据集加载器
    
    支持多种数据格式:
    - JSON 文件
    - JSONL 文件 (每行一条记录)
    - 文件夹 (每个文件一条记录)
    """
    
    def __init__(self, dataset_path: Union[str, Path]):
        self.dataset_path = Path(dataset_path)
        self._cases: List[VulnerabilityCase] = []
        self._loaded = False
    
    def load(self) -> "DatasetLoader":
        """加载数据集"""
        if self._loaded:
            return self
        
        if self.dataset_path.is_file():
            if self.dataset_path.suffix == ".jsonl":
                self._load_jsonl()
            elif self.dataset_path.suffix == ".json":
                self._load_json()
            else:
                raise ValueError(f"Unsupported file format: {self.dataset_path.suffix}")
        elif self.dataset_path.is_dir():
            self._load_directory()
        else:
            raise FileNotFoundError(f"Dataset not found: {self.dataset_path}")
        
        self._loaded = True
        print(f"Loaded {len(self._cases)} vulnerability cases from {self.dataset_path}")
        return self
    
    def _load_json(self):
        """从 JSON 文件加载"""
        with open(self.dataset_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 支持两种格式: 列表 或 带 "cases" 键的对象
        cases_data = data if isinstance(data, list) else data.get("cases", [])
        
        for item in cases_data:
            try:
                case = VulnerabilityCase(**item)
                self._cases.append(case)
            except Exception as e:
                print(f"Warning: Failed to parse case: {e}")
    
    def _load_jsonl(self):
        """从 JSONL 文件加载"""
        with open(self.dataset_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                    case = VulnerabilityCase(**item)
                    self._cases.append(case)
                except Exception as e:
                    print(f"Warning: Failed to parse line {line_num}: {e}")
    
    def _load_directory(self):
        """从文件夹加载 (每个 .json 文件一条记录)"""
        for json_file in self.dataset_path.glob("*.json"):
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    item = json.load(f)
                case = VulnerabilityCase(**item)
                self._cases.append(case)
            except Exception as e:
                print(f"Warning: Failed to parse {json_file.name}: {e}")
    
    @property
    def cases(self) -> List[VulnerabilityCase]:
        """获取所有案例"""
        if not self._loaded:
            self.load()
        return self._cases
    
    def __len__(self) -> int:
        return len(self.cases)
    
    def __iter__(self) -> Iterator[VulnerabilityCase]:
        return iter(self.cases)
    
    def filter_by_type(self, vuln_type: VulnerabilityType) -> List[VulnerabilityCase]:
        """按漏洞类型过滤"""
        return [c for c in self.cases if c.vulnerability_type == vuln_type]
    
    def filter_by_severity(self, severity: str) -> List[VulnerabilityCase]:
        """按严重程度过滤"""
        return [c for c in self.cases if c.severity == severity]
    
    def get_rag_documents(self) -> List[Dict]:
        """获取所有案例的 RAG 文档格式"""
        return [case.to_rag_document() for case in self.cases]
    
    def get_training_examples(
        self,
        task_types: List[TaskType] = None
    ) -> List[TrainingExample]:
        """
        获取训练样本
        
        每个案例可以生成多种任务类型的训练样本
        """
        if task_types is None:
            task_types = [TaskType.ANALYZE, TaskType.GENERATE_POC]
        
        examples = []
        for case in self.cases:
            for task_type in task_types:
                examples.append(case.to_training_example(task_type))
        
        return examples
    
    def to_training_dataset(self, name: str = "vulnerability_dataset") -> TrainingDataset:
        """转换为 TrainingDataset 对象"""
        dataset = TrainingDataset(
            name=name,
            description="Access control vulnerability dataset (manually curated)"
        )
        
        for example in self.get_training_examples():
            dataset.add_example(example)
        
        return dataset
    
    def get_few_shot_examples(
        self,
        task_type: TaskType,
        n: int = 3,
        vuln_type: Optional[VulnerabilityType] = None
    ) -> List[VulnerabilityCase]:
        """
        获取 Few-Shot 示例
        
        用于构建 Prompt 时提供示例
        """
        candidates = self.cases
        
        if vuln_type:
            candidates = [c for c in candidates if c.vulnerability_type == vuln_type]
        
        # 优先选择有完整 PoC 的案例
        candidates_with_poc = [c for c in candidates if c.poc_code]
        
        if len(candidates_with_poc) >= n:
            return candidates_with_poc[:n]
        
        return candidates[:n]
    
    def summary(self) -> Dict:
        """数据集统计摘要"""
        if not self._loaded:
            self.load()
        
        type_dist = {}
        severity_dist = {}
        
        for case in self._cases:
            vtype = case.vulnerability_type.value
            type_dist[vtype] = type_dist.get(vtype, 0) + 1
            severity_dist[case.severity] = severity_dist.get(case.severity, 0) + 1
        
        return {
            "total_cases": len(self._cases),
            "vulnerability_types": type_dist,
            "severity_distribution": severity_dist,
            "cases_with_poc": sum(1 for c in self._cases if c.poc_code)
        }


def create_sample_dataset(output_path: str = "data/dataset/sample.json"):
    """
    创建示例数据集文件
    
    展示数据集的预期格式
    """
    sample_cases = [
        {
            "id": "case_001",
            "contract_source": """// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

contract VulnerableVault {
    address public owner;
    uint256 public protocolFee;
    
    constructor() {
        owner = msg.sender;
    }
    
    // VULNERABLE: Missing access control
    function setProtocolFee(uint256 _fee) external {
        protocolFee = _fee;
    }
    
    function withdraw() external {
        // VULNERABLE: Anyone can withdraw
        payable(msg.sender).transfer(address(this).balance);
    }
}""",
            "contract_name": "VulnerableVault",
            "vulnerable_function": "setProtocolFee",
            "vulnerability_type": "access_control",
            "severity": "high",
            "description": "The setProtocolFee function lacks access control, allowing any user to modify the protocol fee.",
            "missing_check": "onlyOwner",
            "poc_code": """function test_unauthorized_setFee() public {
    address attacker = address(0x123);
    vm.prank(attacker);
    vault.setProtocolFee(9999);
    assertEq(vault.protocolFee(), 9999);
}""",
            "attack_steps": [
                "1. Attacker calls setProtocolFee with arbitrary value",
                "2. Protocol fee is changed without authorization",
                "3. Users may pay excessive fees"
            ],
            "fix_recommendation": "Add onlyOwner modifier to setProtocolFee function",
            "tags": ["missing-modifier", "fee-manipulation"]
        },
        {
            "id": "case_002",
            "contract_source": """// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

contract VulnerableToken {
    mapping(address => uint256) public balances;
    address public admin;
    
    constructor() {
        admin = msg.sender;
    }
    
    // VULNERABLE: No access control on mint
    function mint(address to, uint256 amount) external {
        balances[to] += amount;
    }
}""",
            "contract_name": "VulnerableToken",
            "vulnerable_function": "mint",
            "vulnerability_type": "privilege_escalation",
            "severity": "critical",
            "description": "The mint function has no access control, allowing anyone to mint tokens.",
            "missing_check": "onlyAdmin",
            "poc_code": """function test_unauthorized_mint() public {
    address attacker = address(0x456);
    vm.prank(attacker);
    token.mint(attacker, 1000000 ether);
    assertEq(token.balances(attacker), 1000000 ether);
}""",
            "attack_steps": [
                "1. Attacker calls mint function",
                "2. Arbitrary amount of tokens created",
                "3. Token supply inflated, value destroyed"
            ],
            "fix_recommendation": "Add access control: require(msg.sender == admin, 'Not admin')",
            "tags": ["token", "mint", "critical"]
        }
    ]
    
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump({"cases": sample_cases}, f, indent=2, ensure_ascii=False)
    
    print(f"Sample dataset created at: {output_file}")
    return output_file
