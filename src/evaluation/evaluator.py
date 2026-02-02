"""
Evaluation Module - 评估模块

用数据集评估 Agent 的效果:
1. Recall - 找出了多少漏洞？
2. PoC Quality - 生成的攻击代码能跑通吗？
3. 错题分析 - 是 Node 1 没找到，还是 Node 2 写错了？
"""

import json
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum

from ..dataset.loader import DatasetLoader, VulnerabilityCase


class EvaluationResult(Enum):
    """单个案例的评估结果"""
    TRUE_POSITIVE = "true_positive"       # 正确检出漏洞
    FALSE_NEGATIVE = "false_negative"     # 漏报 (应该检出但没有)
    POC_FAILED = "poc_failed"             # 检出但 PoC 生成失败
    POC_WRONG = "poc_wrong"               # PoC 语法错误
    POC_PASSED = "poc_passed"             # PoC 执行成功，漏洞确认


@dataclass
class CaseEvaluation:
    """单个案例的评估详情"""
    case_id: str
    case: VulnerabilityCase
    
    # 结果
    result: EvaluationResult
    
    # Analyst 节点输出
    detected: bool = False
    detected_function: str = ""
    hypothesis: str = ""
    
    # Builder 节点输出
    poc_generated: bool = False
    poc_code: str = ""
    
    # Verifier 节点输出
    poc_executed: bool = False
    execution_result: str = ""  # pass, fail_revert, fail_error
    error_message: str = ""
    
    # 分析
    failure_reason: str = ""
    
    def to_dict(self) -> Dict:
        return {
            "case_id": self.case_id,
            "result": self.result.value,
            "detected": self.detected,
            "detected_function": self.detected_function,
            "poc_generated": self.poc_generated,
            "poc_executed": self.poc_executed,
            "execution_result": self.execution_result,
            "failure_reason": self.failure_reason
        }


@dataclass
class EvaluationReport:
    """评估报告"""
    # 基本信息
    dataset_name: str
    total_cases: int
    evaluated_at: datetime = field(default_factory=datetime.now)
    
    # 结果统计
    true_positives: int = 0
    false_negatives: int = 0
    poc_failures: int = 0
    
    # 详细结果
    case_results: List[CaseEvaluation] = field(default_factory=list)
    
    @property
    def recall(self) -> float:
        """召回率: 检出的漏洞数 / 总漏洞数"""
        if self.total_cases == 0:
            return 0.0
        return self.true_positives / self.total_cases
    
    @property
    def detection_rate(self) -> float:
        """检测率: Analyst 节点检出的比例"""
        if self.total_cases == 0:
            return 0.0
        detected = sum(1 for r in self.case_results if r.detected)
        return detected / self.total_cases
    
    @property
    def poc_success_rate(self) -> float:
        """PoC 成功率: PoC 执行成功 / PoC 生成数"""
        generated = sum(1 for r in self.case_results if r.poc_generated)
        if generated == 0:
            return 0.0
        passed = sum(1 for r in self.case_results if r.execution_result == "pass")
        return passed / generated
    
    def get_failure_analysis(self) -> Dict[str, List[str]]:
        """
        错题分析: 分析失败原因
        
        返回: {失败类型: [案例ID列表]}
        """
        analysis = {
            "analyst_missed": [],     # Node 1 没检出
            "builder_failed": [],     # Node 2 没生成 PoC
            "poc_syntax_error": [],   # PoC 语法错误
            "poc_wrong_logic": [],    # PoC 逻辑错误 (被正确 Revert)
        }
        
        for case_eval in self.case_results:
            if not case_eval.detected:
                analysis["analyst_missed"].append(case_eval.case_id)
            elif not case_eval.poc_generated:
                analysis["builder_failed"].append(case_eval.case_id)
            elif case_eval.execution_result == "fail_error":
                analysis["poc_syntax_error"].append(case_eval.case_id)
            elif case_eval.execution_result == "fail_revert":
                analysis["poc_wrong_logic"].append(case_eval.case_id)
        
        return analysis
    
    def summary(self) -> str:
        """生成摘要报告"""
        analysis = self.get_failure_analysis()
        
        return f"""
========== Evaluation Report ==========
Dataset: {self.dataset_name}
Total Cases: {self.total_cases}
Evaluated At: {self.evaluated_at.strftime('%Y-%m-%d %H:%M:%S')}

--- Performance Metrics ---
Recall: {self.recall:.2%}
Detection Rate (Analyst): {self.detection_rate:.2%}
PoC Success Rate (Builder): {self.poc_success_rate:.2%}

--- Results ---
True Positives: {self.true_positives}
False Negatives: {self.false_negatives}
PoC Failures: {self.poc_failures}

--- Failure Analysis ---
Analyst Missed: {len(analysis['analyst_missed'])} cases
  - {', '.join(analysis['analyst_missed'][:5])}{'...' if len(analysis['analyst_missed']) > 5 else ''}
Builder Failed: {len(analysis['builder_failed'])} cases
PoC Syntax Errors: {len(analysis['poc_syntax_error'])} cases
PoC Wrong Logic: {len(analysis['poc_wrong_logic'])} cases
==========================================
"""
    
    def save(self, filepath: str):
        """保存报告到文件"""
        output = {
            "dataset_name": self.dataset_name,
            "total_cases": self.total_cases,
            "evaluated_at": self.evaluated_at.isoformat(),
            "metrics": {
                "recall": self.recall,
                "detection_rate": self.detection_rate,
                "poc_success_rate": self.poc_success_rate
            },
            "results": {
                "true_positives": self.true_positives,
                "false_negatives": self.false_negatives,
                "poc_failures": self.poc_failures
            },
            "failure_analysis": self.get_failure_analysis(),
            "case_details": [r.to_dict() for r in self.case_results]
        }
        
        Path(filepath).parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
        
        print(f"Report saved to: {filepath}")


class AgentEvaluator:
    """
    Agent 评估器
    
    用数据集测试 Agent 的效果
    """
    
    def __init__(
        self,
        dataset_path: str,
        vectorstore=None
    ):
        self.loader = DatasetLoader(dataset_path)
        self.loader.load()
        self.vectorstore = vectorstore
    
    def evaluate(
        self,
        run_agent_fn,  # 执行 Agent 的函数
        max_cases: Optional[int] = None,
        verbose: bool = True
    ) -> EvaluationReport:
        """
        运行评估
        
        Args:
            run_agent_fn: 执行 Agent 的函数，签名: (contract_source, contract_name) -> Dict
            max_cases: 最大评估案例数 (None 表示全部)
            verbose: 是否打印进度
        
        Returns:
            EvaluationReport
        """
        cases = self.loader.cases[:max_cases] if max_cases else self.loader.cases
        
        report = EvaluationReport(
            dataset_name=str(self.loader.dataset_path),
            total_cases=len(cases)
        )
        
        for i, case in enumerate(cases):
            if verbose:
                print(f"Evaluating [{i+1}/{len(cases)}]: {case.id}")
            
            case_eval = self._evaluate_single_case(case, run_agent_fn)
            report.case_results.append(case_eval)
            
            # 更新统计
            if case_eval.result == EvaluationResult.TRUE_POSITIVE:
                report.true_positives += 1
            elif case_eval.result == EvaluationResult.FALSE_NEGATIVE:
                report.false_negatives += 1
            else:
                report.poc_failures += 1
        
        return report
    
    def _evaluate_single_case(
        self,
        case: VulnerabilityCase,
        run_agent_fn
    ) -> CaseEvaluation:
        """评估单个案例"""
        case_eval = CaseEvaluation(
            case_id=case.id,
            case=case,
            result=EvaluationResult.FALSE_NEGATIVE
        )
        
        try:
            # 运行 Agent
            result = run_agent_fn(case.contract_source, case.contract_name)
            
            # 检查 Analyst 结果
            sensitive_funcs = result.get("sensitive_functions", [])
            detected_names = [f.get("name", "") for f in sensitive_funcs if not f.get("has_access_control", True)]
            
            if case.vulnerable_function in detected_names:
                case_eval.detected = True
                case_eval.detected_function = case.vulnerable_function
                case_eval.hypothesis = result.get("audit_hypothesis", "")
            else:
                case_eval.failure_reason = f"Analyst did not detect {case.vulnerable_function}"
                return case_eval
            
            # 检查 Builder 结果
            poc_code = result.get("verification_poc", "")
            if poc_code:
                case_eval.poc_generated = True
                case_eval.poc_code = poc_code
            else:
                case_eval.result = EvaluationResult.POC_FAILED
                case_eval.failure_reason = "Builder did not generate PoC"
                return case_eval
            
            # 检查 Verifier 结果
            execution_result = result.get("execution_result", "pending")
            case_eval.poc_executed = True
            case_eval.execution_result = execution_result
            case_eval.error_message = result.get("error_message", "")
            
            if execution_result == "pass":
                case_eval.result = EvaluationResult.TRUE_POSITIVE
            elif execution_result == "fail_error":
                case_eval.result = EvaluationResult.POC_WRONG
                case_eval.failure_reason = "PoC has syntax/runtime error"
            else:
                case_eval.result = EvaluationResult.POC_FAILED
                case_eval.failure_reason = "PoC was reverted (access control worked)"
            
        except Exception as e:
            case_eval.failure_reason = f"Agent error: {str(e)}"
        
        return case_eval
    
    def evaluate_detection_only(self, analyze_fn) -> Tuple[float, List[str]]:
        """
        仅评估检测率 (不运行完整 Agent)
        
        用于快速评估 Analyst 节点的效果
        
        Returns:
            (detection_rate, missed_case_ids)
        """
        detected = 0
        missed = []
        
        for case in self.loader.cases:
            result = analyze_fn(case.contract_source, case.contract_name)
            sensitive_funcs = result.get("sensitive_functions", [])
            detected_names = [f.get("name", "") for f in sensitive_funcs]
            
            if case.vulnerable_function in detected_names:
                detected += 1
            else:
                missed.append(case.id)
        
        rate = detected / len(self.loader.cases) if self.loader.cases else 0.0
        return rate, missed


def run_quick_evaluation(
    dataset_path: str,
    output_path: str = "data/evaluation/report.json"
):
    """
    快速运行评估的便捷函数
    
    注意: 需要配置好 API Key
    """
    from ..core.graph import create_audit_graph
    from ..core.state import create_initial_state
    
    def run_agent(contract_source: str, contract_name: str) -> Dict:
        state = create_initial_state(contract_source, contract_name)
        graph = create_audit_graph()
        final_state = graph.invoke(state)
        return final_state
    
    evaluator = AgentEvaluator(dataset_path)
    report = evaluator.evaluate(run_agent, verbose=True)
    
    print(report.summary())
    report.save(output_path)
    
    return report
