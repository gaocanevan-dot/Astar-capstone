#!/usr/bin/env python3
"""
Training Data Collection Script

批量收集训练数据用于 LLM 模型微调

Usage:
    # 从目录批量收集
    python scripts/collect_data.py --input data/contracts/ --output data/training/
    
    # 导出为训练格式
    python scripts/collect_data.py --export --format openai --input data/training/dataset.json
"""

import argparse
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from rich.console import Console
from rich.table import Table
from rich.progress import Progress

from src.dataset.collector import DataCollector
from src.dataset.schemas import TaskType, VulnerabilityLabel, VulnerabilityType

console = Console()


def collect_from_directory(input_dir: str, output_dir: str):
    """从目录批量收集训练数据"""
    
    input_path = Path(input_dir)
    if not input_path.exists():
        console.print(f"[red]❌ Directory not found: {input_dir}[/red]")
        return
    
    sol_files = list(input_path.glob("**/*.sol"))
    
    if not sol_files:
        console.print(f"[yellow]No .sol files found in {input_dir}[/yellow]")
        return
    
    console.print(f"\n[cyan]Found {len(sol_files)} Solidity files[/cyan]\n")
    
    collector = DataCollector(output_dir=output_dir)
    
    with Progress() as progress:
        task = progress.add_task("Processing contracts...", total=len(sol_files))
        
        for sol_file in sol_files:
            try:
                source_code = sol_file.read_text(encoding='utf-8')
                contract_name = sol_file.stem
                
                # 开始会话
                collector.start_session(source_code, contract_name)
                
                # 这里可以添加实际的分析逻辑
                # 目前只是记录原始合约
                collector.add_manual_example(
                    task_type=TaskType.ANALYZE,
                    input_data={
                        "contract_source": source_code,
                        "contract_name": contract_name
                    },
                    output_data={
                        "is_vulnerable": None,  # 待标注
                        "vulnerable_functions": [],
                        "vulnerability_type": None,
                        "hypothesis": ""
                    }
                )
                
                progress.advance(task)
                
            except Exception as e:
                console.print(f"[red]Error processing {sol_file}: {e}[/red]")
    
    # 保存数据集
    filepath = collector.save_dataset()
    
    # 显示统计
    stats = collector.get_statistics()
    display_statistics(stats)


def add_manual_label(dataset_path: str, contract_name: str, labels: dict):
    """手动添加标注"""
    
    collector = DataCollector()
    collector.load_dataset(dataset_path)
    
    # 找到对应的样本并更新
    for example in collector.dataset.examples:
        if example.input_data.get("contract_name") == contract_name:
            example.output_data.update(labels)
            example.confirmed = True
            console.print(f"[green]✅ Updated labels for {contract_name}[/green]")
            break
    else:
        console.print(f"[yellow]Contract {contract_name} not found[/yellow]")
        return
    
    collector.save_dataset()


def export_training_data(dataset_path: str, format: str, output_path: str = None):
    """导出为训练格式"""
    
    collector = DataCollector()
    collector.load_dataset(dataset_path)
    
    if output_path is None:
        output_path = f"training_data_{format}.jsonl"
    
    filepath = collector.export_for_training(format=format, filename=output_path)
    console.print(f"\n[green]✅ Exported to: {filepath}[/green]")


def display_statistics(stats: dict):
    """显示数据集统计信息"""
    
    console.print("\n[bold]📊 Dataset Statistics[/bold]\n")
    
    table = Table()
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    
    table.add_row("Total Examples", str(stats.get("total_examples", 0)))
    table.add_row("Confirmed", str(stats.get("confirmed_count", 0)))
    
    console.print(table)
    
    # 任务类型分布
    if stats.get("task_distribution"):
        console.print("\n[bold]Task Distribution:[/bold]")
        for task, count in stats["task_distribution"].items():
            console.print(f"  {task}: {count}")
    
    # 漏洞类型分布
    if stats.get("vulnerability_distribution"):
        console.print("\n[bold]Vulnerability Types:[/bold]")
        for vtype, count in stats["vulnerability_distribution"].items():
            console.print(f"  {vtype}: {count}")


def create_sample_labels():
    """创建示例标注文件"""
    
    sample = {
        "contract_name": "VulnerableVault",
        "labels": {
            "is_vulnerable": True,
            "vulnerable_functions": ["setFee", "withdraw"],
            "vulnerability_type": "access_control",
            "hypothesis": "setFee and withdraw functions lack access control modifiers"
        },
        "severity": "high",
        "poc_code": """
function test_UnauthorizedSetFee() public {
    address attacker = makeAddr("attacker");
    vm.prank(attacker);
    vault.setFee(999);
    assertEq(vault.fee(), 999);
}
"""
    }
    
    output_path = Path("data/labels/sample_label.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(sample, f, indent=2, ensure_ascii=False)
    
    console.print(f"[green]✅ Sample label file created: {output_path}[/green]")
    console.print("\n[dim]Edit this file to add your labels, then use --add-label to import[/dim]")


def main():
    parser = argparse.ArgumentParser(
        description="Training Data Collection Tool"
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Commands")
    
    # collect 命令
    collect_parser = subparsers.add_parser("collect", help="Collect data from contracts")
    collect_parser.add_argument("--input", "-i", required=True, help="Input directory with .sol files")
    collect_parser.add_argument("--output", "-o", default="data/training/", help="Output directory")
    
    # export 命令
    export_parser = subparsers.add_parser("export", help="Export to training format")
    export_parser.add_argument("--dataset", "-d", required=True, help="Dataset JSON file")
    export_parser.add_argument("--format", "-f", choices=["openai", "alpaca"], default="openai")
    export_parser.add_argument("--output", "-o", help="Output file path")
    
    # stats 命令
    stats_parser = subparsers.add_parser("stats", help="Show dataset statistics")
    stats_parser.add_argument("--dataset", "-d", required=True, help="Dataset JSON file")
    
    # sample 命令
    sample_parser = subparsers.add_parser("sample", help="Create sample label file")
    
    args = parser.parse_args()
    
    if args.command == "collect":
        collect_from_directory(args.input, args.output)
    elif args.command == "export":
        export_training_data(args.dataset, args.format, args.output)
    elif args.command == "stats":
        collector = DataCollector()
        collector.load_dataset(args.dataset)
        display_statistics(collector.get_statistics())
    elif args.command == "sample":
        create_sample_labels()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
