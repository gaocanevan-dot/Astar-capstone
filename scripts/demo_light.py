#!/usr/bin/env python3


import argparse
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
from scripts.run_ablation import ABLATION_MODES, run_single_mode

console = Console()


def infer_vulnerability_type(final_state: dict) -> str:
    """Infer the main vulnerability type for lightweight display."""
    report = final_state.get("audit_report", {})
    findings = report.get("findings", [])
    if findings:
        hypothesis = (findings[0].get("hypothesis") or "").lower()
    else:
        hypothesis = (final_state.get("audit_hypothesis") or "").lower()

    if "access control" in hypothesis or "onlyowner" in hypothesis or "unauthorized" in hypothesis:
        return "access_control"
    if (
        ("privilege escalation" in hypothesis or "role takeover" in hypothesis)
        and "no privilege escalation" not in hypothesis
        and "no immediate privilege escalation" not in hypothesis
        and "no direct privilege escalation" not in hypothesis
    ):
        return "privilege_escalation"
    return "unknown"


def render_ablation(contract_path: Path, max_retries: int) -> None:
    results = [run_single_mode(str(contract_path), mode, max_retries) for mode in ("full", "no-static", "no-rag")]
    table = Table(title="Ablation Summary", show_header=True)
    table.add_column("Mode", style="cyan")
    table.add_column("Static")
    table.add_column("RAG")
    table.add_column("Status")
    table.add_column("Findings", justify="right")
    table.add_column("Confirmed")
    table.add_column("Target")

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
    console.print("\n[bold]Step 4[/bold] Ablation experiment")
    console.print(table)


def main() -> None:
    parser = argparse.ArgumentParser(description="Lightweight end-to-end demo")
    parser.add_argument(
        "--contract",
        default="data/contracts/VulnerableAccessControl.sol",
        help="Path to the Solidity contract file",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=2,
        help="Maximum retry attempts",
    )
    parser.add_argument(
        "--with-ablation",
        action="store_true",
        help="Also run a lightweight ablation comparison table",
    )
    args = parser.parse_args()

    contract_path = Path(args.contract)
    contract_source = contract_path.read_text(encoding="utf-8")

    state = create_initial_state(
        contract_source=contract_source,
        contract_name=contract_path.stem,
        max_retries=args.max_retries,
        use_static_analysis=True,
        use_rag=True,
    )

    console.print(
        Panel.fit(
            "[bold blue]Lightweight Demo[/bold blue]\n"
            "[dim]Static Analysis + RAG + AI + Foundry[/dim]",
            border_style="blue",
        )
    )

    graph = compile_graph(checkpointer=False, use_rag=True)
    final_state = graph.invoke(state)
    report = final_state.get("audit_report", {})

    console.print("\n[bold]Step 1[/bold] Static analysis")
    for item in final_state.get("sensitive_candidates", [])[:3]:
        console.print(f"- {item.get('name')} | modifiers={item.get('modifiers')} | writes={item.get('writes')}")

    console.print("\n[bold]Step 2[/bold] RAG retrieval")
    for item in final_state.get("similar_cases", [])[:3]:
        console.print(f"- {item.get('id')} | {item.get('function')} | {item.get('vulnerability_type')}")

    console.print("\n[bold]Step 3[/bold] Final result")
    console.print(f"- status: {report.get('status')}")
    console.print(f"- findings: {report.get('total_findings', 0)}")
    console.print(f"- vulnerability_type: {infer_vulnerability_type(final_state)}")
    console.print(f"- target: {final_state.get('current_target_function')}")
    console.print(f"- hypothesis: {final_state.get('audit_hypothesis')}")
    console.print(f"- confirmed: {final_state.get('finding_confirmed')}")


    if args.with_ablation:
        render_ablation(contract_path, args.max_retries)


if __name__ == "__main__":
    main()
