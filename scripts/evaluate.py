#!/usr/bin/env python3
"""
Evaluation Script - 评估脚本

用数据集评估 Agent 的效果

Usage:
    # 基本评估
    python scripts/evaluate.py --dataset data/dataset/vulnerabilities.json
    
    # 指定最大案例数
    python scripts/evaluate.py --dataset data/dataset/vulnerabilities.json --max-cases 10
    
    # 输出报告到指定文件
    python scripts/evaluate.py --dataset data/dataset/vulnerabilities.json --output report.json
"""

import argparse
import os
import sys
from pathlib import Path

os.environ.setdefault("PYDANTIC_DISABLE_PLUGINS", "__all__")
sys.path.insert(0, str(Path(__file__).parent.parent))

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn

from src.evaluation.evaluator import AgentEvaluator, run_quick_evaluation
from src.core.config import validate_config


console = Console()


def display_welcome():
    """显示欢迎信息"""
    console.print(Panel.fit(
        "[bold blue]Agent Evaluation Tool[/bold blue]\n"
        "[dim]使用数据集评估 Agent 的检测效果[/dim]",
        border_style="blue"
    ))


def display_dataset_summary(evaluator: AgentEvaluator):
    """显示数据集摘要"""
    summary = evaluator.loader.summary()
    
    console.print(f"\n[bold]📊 Dataset Summary[/bold]")
    console.print(f"Total Cases: {summary['total_cases']}")
    console.print(f"Cases with PoC: {summary['cases_with_poc']}")
    
    table = Table(title="Vulnerability Distribution", show_header=True)
    table.add_column("Type", style="cyan")
    table.add_column("Count", justify="right")
    
    for vtype, count in summary['vulnerability_types'].items():
        table.add_row(vtype, str(count))
    
    console.print(table)


def display_results(report):
    """显示评估结果"""
    console.print("\n" + "=" * 60)
    console.print("[bold]📈 EVALUATION RESULTS[/bold]")
    console.print("=" * 60)
    
    # 性能指标
    metrics_table = Table(title="Performance Metrics", show_header=True)
    metrics_table.add_column("Metric", style="cyan")
    metrics_table.add_column("Value", justify="right")
    
    metrics_table.add_row("Recall", f"{report.recall:.2%}")
    metrics_table.add_row("Detection Rate (Analyst)", f"{report.detection_rate:.2%}")
    metrics_table.add_row("PoC Success Rate", f"{report.poc_success_rate:.2%}")
    
    console.print(metrics_table)
    
    # 结果统计
    results_table = Table(title="Results Summary", show_header=True)
    results_table.add_column("Result Type", style="cyan")
    results_table.add_column("Count", justify="right")
    
    results_table.add_row("True Positives", str(report.true_positives))
    results_table.add_row("False Negatives", str(report.false_negatives))
    results_table.add_row("PoC Failures", str(report.poc_failures))
    
    console.print(results_table)
    
    # 错题分析
    analysis = report.get_failure_analysis()
    
    console.print("\n[bold]🔍 Failure Analysis[/bold]")
    
    failure_table = Table(show_header=True)
    failure_table.add_column("Failure Type", style="yellow")
    failure_table.add_column("Count", justify="right")
    failure_table.add_column("Case IDs", max_width=40)
    
    failure_table.add_row(
        "Analyst Missed",
        str(len(analysis['analyst_missed'])),
        ", ".join(analysis['analyst_missed'][:3]) + ("..." if len(analysis['analyst_missed']) > 3 else "")
    )
    failure_table.add_row(
        "Builder Failed",
        str(len(analysis['builder_failed'])),
        ", ".join(analysis['builder_failed'][:3]) + ("..." if len(analysis['builder_failed']) > 3 else "")
    )
    failure_table.add_row(
        "PoC Syntax Error",
        str(len(analysis['poc_syntax_error'])),
        ", ".join(analysis['poc_syntax_error'][:3]) + ("..." if len(analysis['poc_syntax_error']) > 3 else "")
    )
    failure_table.add_row(
        "PoC Wrong Logic",
        str(len(analysis['poc_wrong_logic'])),
        ", ".join(analysis['poc_wrong_logic'][:3]) + ("..." if len(analysis['poc_wrong_logic']) > 3 else "")
    )
    
    console.print(failure_table)
    console.print("\n" + "=" * 60)


def run_evaluation(dataset_path: str, max_cases: int = None, output_path: str = None):
    """运行评估"""
    
    # 检查 API Key
    if not validate_config():
        console.print("[yellow]⚠️ OPENAI_API_KEY not set. Evaluation requires API access.[/yellow]")
        return
    
    # 创建评估器
    console.print(f"\n[cyan]📂 Loading dataset: {dataset_path}[/cyan]")
    evaluator = AgentEvaluator(dataset_path)
    
    display_dataset_summary(evaluator)
    
    # 定义 Agent 运行函数
    from src.core.state_schema import create_initial_state
    from src.core.graph_light import compile_graph
    
    def run_agent(contract_source: str, contract_name: str) -> dict:
        state = create_initial_state(contract_source, contract_name)
        graph = compile_graph(checkpointer=False, use_rag=True)
        return graph.invoke(state)
    
    # 运行评估
    console.print(f"\n[cyan]🔄 Running evaluation...[/cyan]")
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console
    ) as progress:
        task = progress.add_task("Evaluating...", total=None)
        report = evaluator.evaluate(run_agent, max_cases=max_cases, verbose=False)
        progress.update(task, completed=True)
    
    # 显示结果
    display_results(report)
    
    # 保存报告
    if output_path:
        report.save(output_path)
        console.print(f"\n[green]✅ Report saved to: {output_path}[/green]")
    else:
        default_output = "data/evaluation/report.json"
        report.save(default_output)
        console.print(f"\n[green]✅ Report saved to: {default_output}[/green]")


def main():
    """主入口"""
    parser = argparse.ArgumentParser(
        description="Agent Evaluation Tool"
    )
    parser.add_argument(
        "--dataset", "-d",
        required=True,
        help="Path to the vulnerability dataset (JSON/JSONL)"
    )
    parser.add_argument(
        "--max-cases", "-m",
        type=int,
        default=None,
        help="Maximum number of cases to evaluate"
    )
    parser.add_argument(
        "--output", "-o",
        help="Output path for the evaluation report"
    )
    
    args = parser.parse_args()
    
    display_welcome()
    
    run_evaluation(
        dataset_path=args.dataset,
        max_cases=args.max_cases,
        output_path=args.output
    )


if __name__ == "__main__":
    main()
