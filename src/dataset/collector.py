"""
Data Collector - 数据收集器

从 Agent 运行过程中收集训练数据。
"""

import json
import uuid
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime

from .schemas import (
    TrainingExample, 
    TrainingDataset, 
    TaskType, 
    VulnerabilityType,
    VulnerabilityLabel
)


class DataCollector:
    """
    数据收集器
    
    用于从 Agent 审计过程中收集训练数据，
    也支持手动添加标注数据。
    """
    
    def __init__(self, output_dir: str = "data/training"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.dataset = TrainingDataset(
            name="access_control_vulnerabilities",
            description="Access control and privilege escalation vulnerability dataset"
        )
        
        # 临时存储当前审计会话的数据
        self._current_session: Dict = {}
    
    def start_session(self, contract_source: str, contract_name: str):
        """开始一个新的数据收集会话"""
        self._current_session = {
            "session_id": str(uuid.uuid4())[:8],
            "contract_source": contract_source,
            "contract_name": contract_name,
            "started_at": datetime.now(),
            "analysis_result": None,
            "poc_code": None,
            "verification_result": None
        }
    
    def record_analysis(
        self,
        vulnerable_functions: List[str],
        vulnerability_type: Optional[VulnerabilityType],
        hypothesis: str,
        is_vulnerable: bool
    ):
        """记录分析结果"""
        self._current_session["analysis_result"] = {
            "vulnerable_functions": vulnerable_functions,
            "vulnerability_type": vulnerability_type.value if vulnerability_type else None,
            "hypothesis": hypothesis,
            "is_vulnerable": is_vulnerable
        }
    
    def record_poc(self, poc_code: str, target_function: str):
        """记录生成的 PoC"""
        self._current_session["poc_code"] = poc_code
        self._current_session["target_function"] = target_function
    
    def record_verification(self, execution_result: str, confirmed: bool):
        """记录验证结果"""
        self._current_session["verification_result"] = {
            "execution_result": execution_result,
            "confirmed": confirmed
        }
    
    def end_session(self, save_examples: bool = True) -> List[TrainingExample]:
        """
        结束会话并生成训练样本
        
        如果 verified 为 True，则标记样本为已确认
        """
        examples = []
        session = self._current_session
        
        if not session:
            return examples
        
        confirmed = session.get("verification_result", {}).get("confirmed", False)
        
        # 1. 分析任务样本
        if session.get("analysis_result"):
            analysis_example = TrainingExample(
                id=f"analyze_{session['session_id']}",
                task_type=TaskType.ANALYZE,
                input_data={
                    "contract_source": session["contract_source"],
                    "contract_name": session["contract_name"]
                },
                output_data=session["analysis_result"],
                source="auto",
                confirmed=confirmed,
                metadata={
                    "session_id": session["session_id"]
                }
            )
            examples.append(analysis_example)
        
        # 2. PoC 生成样本 (仅当有漏洞时)
        if session.get("poc_code") and session.get("analysis_result", {}).get("is_vulnerable"):
            poc_example = TrainingExample(
                id=f"poc_{session['session_id']}",
                task_type=TaskType.GENERATE_POC,
                input_data={
                    "contract_source": session["contract_source"],
                    "contract_name": session["contract_name"],
                    "target_function": session.get("target_function", ""),
                    "vulnerability_hypothesis": session.get("analysis_result", {}).get("hypothesis", "")
                },
                output_data={
                    "poc_code": session["poc_code"]
                },
                source="auto",
                confirmed=confirmed,
                metadata={
                    "session_id": session["session_id"]
                }
            )
            examples.append(poc_example)
        
        # 添加到数据集
        if save_examples:
            for ex in examples:
                self.dataset.add_example(ex)
        
        # 清空会话
        self._current_session = {}
        
        return examples
    
    def add_manual_example(
        self,
        task_type: TaskType,
        input_data: Dict,
        output_data: Dict,
        labels: Optional[List[VulnerabilityLabel]] = None
    ) -> TrainingExample:
        """
        手动添加标注样本
        
        用于人工标注的高质量数据
        """
        example = TrainingExample(
            id=f"manual_{str(uuid.uuid4())[:8]}",
            task_type=task_type,
            input_data=input_data,
            output_data=output_data,
            source="manual",
            confirmed=True,  # 手动标注默认已确认
            metadata={
                "labels": [l.model_dump() for l in labels] if labels else []
            }
        )
        
        self.dataset.add_example(example)
        return example
    
    def save_dataset(self, filename: Optional[str] = None):
        """保存数据集"""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"dataset_{timestamp}.json"
        
        filepath = self.output_dir / filename
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(self.dataset.model_dump(), f, indent=2, ensure_ascii=False, default=str)
        
        print(f"Dataset saved to: {filepath}")
        return filepath
    
    def export_for_training(
        self, 
        format: str = "openai",
        filename: Optional[str] = None
    ) -> Path:
        """
        导出为训练格式
        
        Args:
            format: "openai" 或 "alpaca"
            filename: 输出文件名
        """
        if filename is None:
            filename = f"training_data_{format}.jsonl"
        
        filepath = self.output_dir / filename
        self.dataset.save_jsonl(str(filepath), format=format)
        
        print(f"Training data exported to: {filepath}")
        print(f"Total examples: {self.dataset.total_examples}")
        print(f"Distribution: {self.dataset.vulnerability_distribution}")
        
        return filepath
    
    def load_dataset(self, filepath: str):
        """加载已有数据集"""
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        self.dataset = TrainingDataset(**data)
        print(f"Loaded dataset with {self.dataset.total_examples} examples")
    
    def get_statistics(self) -> Dict:
        """获取数据集统计信息"""
        return {
            "total_examples": self.dataset.total_examples,
            "vulnerability_distribution": self.dataset.vulnerability_distribution,
            "confirmed_count": sum(1 for ex in self.dataset.examples if ex.confirmed),
            "task_distribution": self._count_by_task_type()
        }
    
    def _count_by_task_type(self) -> Dict[str, int]:
        """按任务类型统计"""
        counts = {}
        for ex in self.dataset.examples:
            task = ex.task_type.value
            counts[task] = counts.get(task, 0) + 1
        return counts
