#!/usr/bin/env python3
"""
Smart Contract Access Control Audit Agent

支持 RAG 增强的审计入口脚本

Usage:
    # 1. 先加载数据集到向量库
    python scripts/run_audit.py --load-dataset data/dataset/vulnerabilities.json
    
    # 2. 运行审计 (自动使用 RAG)
    python scripts/run_audit.py --contract path/to/contract.sol
    
    # 3. 不使用 RAG 运行 (对比用)
    python scripts/run_audit.py --contract path/to/contract.sol --no-rag
"""

import argparse
import os
import sys
from pathlib import Path

os.environ.setdefault("PYDANTIC_DISABLE_PLUGINS", "__all__")
sys.path.insert(0, str(Path(__file__).parent.parent))

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from src.core.state_schema import create_initial_state
from src.core.graph_light import compile_graph, load_dataset_to_vectorstore
from src.core.config import validate_config, get_settings


def configure_utf8_output() -> None:
    """Make Rich output safe on fresh Windows PowerShell sessions."""
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is not None and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except ValueError:
                pass


configure_utf8_output()
console = Console()


def load_contract(contract_path: str) -> tuple[str, str]:
    """加载合约"""
    path = Path(contract_path)
    
    if not path.exists():
        raise FileNotFoundError(f"Contract not found: {contract_path}")
    
    if path.suffix != '.sol':
        raise ValueError(f"Expected .sol file, got: {path.suffix}")
    
    return path.read_text(encoding='utf-8'), path.stem


def display_welcome():
    """显示欢迎信息"""
    console.print(Panel.fit(
        "[bold blue]Access Control Vulnerability Agent[/bold blue]\n"
        "[dim]RAG 增强版 - 从数据集学习漏洞模式[/dim]",
        border_style="blue"
    ))


def display_contract(source: str, name: str):
    """显示合约预览"""
    console.print(f"\n[bold]📄 Contract:[/bold] {name}.sol\n")
    
    lines = source.split('\n')[:25]
    preview = '\n'.join(lines)
    if len(source.split('\n')) > 25:
        preview += '\n// ... (truncated)'
    
    console.print(Syntax(preview, "solidity", theme="monokai", line_numbers=True))


def display_static_info(state: dict):
    """Display a compact static-analysis summary."""
    if not state.get("use_static_analysis", True):
        console.print("\n[dim]Static analysis disabled[/dim]")
        return

    candidates = state.get("sensitive_candidates", [])
    if not candidates:
        console.print("\n[dim]No static-analysis candidates collected[/dim]")
        return

    console.print(f"\n[cyan]Static analysis identified {len(candidates)} sensitive candidates:[/cyan]")
    table = Table(show_header=True, header_style="bold")
    table.add_column("Function", width=24)
    table.add_column("Modifiers", width=20)
    table.add_column("Writes", width=20)

    for item in candidates[:4]:
        table.add_row(
            item.get("name", "")[:24],
            ", ".join(item.get("modifiers", []))[:20] or "-",
            ", ".join(item.get("writes", []))[:20] or "-",
        )

    console.print(table)


def display_rag_info(similar_cases: list):
    """显示 RAG 检索到的相似案例"""
    if not similar_cases:
        console.print("\n[yellow]⚠️ No similar cases found in knowledge base[/yellow]")
        return
    
    console.print(f"\n[cyan]🔍 Found {len(similar_cases)} similar cases in knowledge base:[/cyan]")
    
    table = Table(show_header=True, header_style="bold")
    table.add_column("ID", width=15)
    table.add_column("Type", width=20)
    table.add_column("Function", width=20)
    
    for case in similar_cases[:3]:
        table.add_row(
            case.get("id", "")[:15],
            case.get("vulnerability_type", "")[:20],
            case.get("function", "")[:20]
        )
    
    console.print(table)


def display_results(report: dict, final_state: dict = None):
    """显示审计结果"""
    console.print("\n" + "=" * 50)
    console.print("[bold]📊 AUDIT RESULT[/bold]")
    console.print("=" * 50)
    
    status = report.get("status", "unknown")
    rag_enhanced = report.get("rag_enhanced", False)
    static_used = report.get("static_analysis_used", False)
    
    if rag_enhanced:
        console.print("[cyan]✨ RAG Enhanced Analysis[/cyan]")
    if static_used:
        console.print("[cyan]Static Analysis Enhanced[/cyan]")

    if status == "vulnerabilities_found":
        console.print(f"\n[bold red]🚨 VULNERABILITIES FOUND[/bold red]")
        console.print(f"Findings: {report.get('total_findings', 0)}")
        
        for i, finding in enumerate(report.get("findings", []), 1):
            console.print(f"\n[yellow]Finding #{i}[/yellow]")
            console.print(f"  Function: {finding.get('function', 'N/A')}")
            console.print(f"  Issue: {finding.get('hypothesis', 'N/A')}")
            if finding.get('similar_cases_used', 0) > 0:
                console.print(f"  [dim]Referenced {finding.get('similar_cases_used')} similar cases[/dim]")
            if finding.get('static_candidates_used', 0) > 0:
                console.print(f"  [dim]Referenced {finding.get('static_candidates_used')} static candidates[/dim]")
    else:
        console.print(f"\n[green]✅ NO VULNERABILITIES FOUND[/green]")
    
    console.print("\n" + "=" * 50)


def run_audit(contract_path: str, max_retries: int = 3, use_rag: bool = True, use_static: bool = True):
    """执行审计"""
    
    # 加载合约
    try:
        source_code, contract_name = load_contract(contract_path)
    except Exception as e:
        console.print(f"[red]❌ {str(e)}[/red]")
        return
    
    display_contract(source_code, contract_name)
    
    # 检查 API Key
    has_api_key = validate_config()
    if not has_api_key:
        console.print("[yellow]⚠️ OPENAI_API_KEY not set. Skipping LLM analysis.[/yellow]")
        console.print("[dim]Set OPENAI_API_KEY in .env to enable full audit.[/dim]")
        return
    
    # 创建状态
    initial_state = create_initial_state(
        contract_source=source_code,
        contract_name=contract_name,
        max_retries=max_retries,
        use_static_analysis=use_static,
        use_rag=use_rag,
    )
    
    mode_parts = []
    mode_parts.append("with static analysis" if use_static else "without static analysis")
    mode_parts.append("with RAG" if use_rag else "without RAG")
    mode = ", ".join(mode_parts)
    console.print(f"\n[cyan]🔍 Starting audit ({mode})...[/cyan]\n")
    
    try:
        graph = compile_graph(checkpointer=True, use_rag=use_rag)
        config = {"configurable": {"thread_id": f"audit_{contract_name}"}}
        
        final_state = None
        for state in graph.stream(initial_state, config):
            for node_name, node_state in state.items():
                final_state = node_state
                
                # 显示 RAG 检索结果
                if node_name == "preprocess_static":
                    display_static_info(node_state)
                if node_name == "rag_retrieval":
                    display_rag_info(node_state.get("similar_cases", []))
                
                console.print(f"  → {node_name}")
        
        if final_state:
            display_results(final_state.get("audit_report", {}), final_state)
        else:
            console.print("[red]❌ Audit failed[/red]")
            
    except Exception as e:
        console.print(f"[red]❌ Error: {str(e)}[/red]")
        import traceback
        traceback.print_exc()


def load_dataset(dataset_path: str):
    """加载数据集到向量库"""
    console.print(f"\n[cyan]📚 Loading dataset: {dataset_path}[/cyan]")
    
    try:
        count = load_dataset_to_vectorstore(dataset_path)
        console.print(f"[green]✅ Loaded {count} vulnerability cases into vector store[/green]")
        console.print("[dim]RAG is now ready for enhanced analysis[/dim]")
    except Exception as e:
        console.print(f"[red]❌ Failed to load dataset: {e}[/red]")


def create_sample_dataset_cmd():
    """创建示例数据集"""
    from src.dataset.loader import create_sample_dataset
    
    output_path = "data/dataset/sample.json"
    create_sample_dataset(output_path)
    console.print(f"[green]✅ Sample dataset created: {output_path}[/green]")
    console.print("[dim]Edit this file to add your own vulnerability cases[/dim]")


def main():
    """主入口"""
    parser = argparse.ArgumentParser(
        description="Access Control Vulnerability Agent (RAG Enhanced)"
    )
    parser.add_argument(
        "--contract", "-c",
        help="Path to the Solidity contract file"
    )
    parser.add_argument(
        "--load-dataset", "-l",
        help="Load dataset into vector store for RAG"
    )
    parser.add_argument(
        "--create-sample",
        action="store_true",
        help="Create a sample dataset file"
    )
    parser.add_argument(
        "--no-rag",
        action="store_true",
        help="Disable RAG enhancement (for comparison)"
    )
    parser.add_argument(
        "--no-static",
        action="store_true",
        help="Disable static-analysis preprocessing (for comparison)"
    )
    parser.add_argument(
        "--max-retries", "-r",
        type=int,
        default=3,
        help="Maximum retry attempts (default: 3)"
    )
    
    args = parser.parse_args()
    
    display_welcome()
    
    if args.create_sample:
        create_sample_dataset_cmd()
        return
    
    if args.load_dataset:
        load_dataset(args.load_dataset)
        return
    
    if args.contract:
        run_audit(
            contract_path=args.contract,
            max_retries=args.max_retries,
            use_rag=not args.no_rag,
            use_static=not args.no_static
        )
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
