#!/usr/bin/env python3
"""
Lightweight ablation runner for demo and small-scale comparison.
"""

import argparse
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("PYDANTIC_DISABLE_PLUGINS", "__all__")
sys.path.insert(0, str(Path(__file__).parent.parent))

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from src.core.graph_light import compile_graph
from src.core.state_schema import create_initial_state

console = Console()


ABLATION_MODES = {
    "full": {"use_static": True, "use_rag": True},
    "no-static": {"use_static": False, "use_rag": True},
    "no-rag": {"use_static": True, "use_rag": False},
}


def run_single_mode(contract_path: str, mode_name: str, max_retries: int = 2) -> dict:
    contract = Path(contract_path)
    source = contract.read_text(encoding="utf-8")
    config = ABLATION_MODES[mode_name]

    state = create_initial_state(
        contract_source=source,
        contract_name=contract.stem,
        max_retries=max_retries,
        use_static_analysis=config["use_static"],
        use_rag=config["use_rag"],
    )
    graph = compile_graph(checkpointer=False, use_rag=config["use_rag"])
    final_state = graph.invoke(state)
    report = final_state.get("audit_report", {})
    return {
        "mode": mode_name,
        "status": report.get("status", "unknown"),
        "findings": report.get("total_findings", 0),
        "confirmed": final_state.get("finding_confirmed", False),
        "target": final_state.get("current_target_function", ""),
        "rag": config["use_rag"],
        "static": config["use_static"],
    }


def render_results(results: list[dict]) -> None:
    table = Table(title="Ablation Summary", show_header=True)
    table.add_column("Mode", style="cyan")
    table.add_column("Static")
    table.add_column("RAG")
    table.add_column("Status")
    table.add_column("Findings", justify="right")
    table.add_column("Confirmed")
    table.add_column("Target", overflow="fold")

    for item in results:
        table.add_row(
            item["mode"],
            "on" if item["static"] else "off",
            "on" if item["rag"] else "off",
            item["status"],
            str(item["findings"]),
            str(item["confirmed"]),
            item["target"] or "-",
        )
    console.print(table)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run lightweight ablation experiments")
    parser.add_argument(
        "--contract",
        default="data/contracts/VulnerableAccessControl.sol",
        help="Path to the Solidity contract file",
    )
    parser.add_argument(
        "--modes",
        nargs="+",
        default=["full", "no-static", "no-rag"],
        choices=list(ABLATION_MODES.keys()),
        help="Ablation modes to run",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=2,
        help="Maximum retry attempts",
    )
    parser.add_argument(
        "--output",
        help="Optional JSON output path",
    )
    args = parser.parse_args()

    console.print(
        Panel.fit(
            "[bold blue]Ablation Runner[/bold blue]\n"
            "[dim]Compare full system against simplified variants[/dim]",
            border_style="blue",
        )
    )

    results = [run_single_mode(args.contract, mode, args.max_retries) for mode in args.modes]
    render_results(results)

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
        console.print(f"\nSaved results to {output_path}")


if __name__ == "__main__":
    main()
