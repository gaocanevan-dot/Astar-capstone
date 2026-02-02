"""
Evaluation module for testing Agent performance.

用数据集评估 Agent 的效果:
1. Recall - 找出了多少漏洞？
2. PoC Quality - 生成的攻击代码能跑通吗？
3. 错题分析 - 是 Node 1 没找到，还是 Node 2 写错了？
"""

from .evaluator import (
    AgentEvaluator,
    EvaluationReport,
    EvaluationResult,
    CaseEvaluation,
    run_quick_evaluation
)

__all__ = [
    "AgentEvaluator",
    "EvaluationReport", 
    "EvaluationResult",
    "CaseEvaluation",
    "run_quick_evaluation"
]
