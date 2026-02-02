#!/usr/bin/env python3
"""
演示脚本 - 展示 Agent 框架的核心功能

运行方式:
    python scripts/demo.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.markdown import Markdown

console = Console()


def print_section(title: str):
    console.print(f"\n[bold cyan]{'='*60}[/bold cyan]")
    console.print(f"[bold cyan]{title}[/bold cyan]")
    console.print(f"[bold cyan]{'='*60}[/bold cyan]\n")


def demo_project_overview():
    """演示1: 项目概述"""
    print_section("1. 项目概述 - Project Overview")
    
    overview = """
## 项目目标
基于 Agent 的 DeFi 智能合约**访问控制漏洞**检测系统

## 核心功能
1. **分析合约** - 识别缺少访问控制的敏感函数
2. **生成 PoC** - 自动生成 Foundry 测试代码
3. **验证漏洞** - 执行测试确认漏洞存在
4. **收集数据** - 为后续模型训练收集标注数据

## 技术栈
- **LangGraph**: 工作流编排
- **LangChain + OpenAI**: LLM 集成
- **Foundry**: 智能合约测试
- **Pydantic**: 数据结构定义
"""
    console.print(Markdown(overview))
    input("\n[按 Enter 继续...]")


def demo_architecture():
    """演示2: 系统架构"""
    print_section("2. 系统架构 - Architecture")
    
    arch = """
```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Analyst   │ ──▶ │   Builder   │ ──▶ │  Verifier   │
│  分析合约    │     │  生成 PoC   │     │  执行验证    │
└─────────────┘     └─────────────┘     └──────┬──────┘
                           ▲                    │
                           │     重试 (≤3次)    │
                           └────────────────────┘
                                   │
                                   ▼
                    ┌──────────────────────────┐
                    │  pass → 漏洞确认，生成报告  │
                    │  fail_revert → 安全      │
                    │  fail_error → 重试       │
                    └──────────────────────────┘
```
"""
    console.print(arch)
    
    # 节点说明表格
    table = Table(title="节点功能说明")
    table.add_column("节点", style="cyan")
    table.add_column("输入", style="green")
    table.add_column("输出", style="yellow")
    table.add_column("技术", style="magenta")
    
    table.add_row("Analyst", "合约源码", "敏感函数列表 + 假说", "GPT-4 + Prompt")
    table.add_row("Builder", "假说 + 目标函数", "Foundry 测试代码", "GPT-4 + Prompt")
    table.add_row("Verifier", "PoC 代码", "执行结果", "Foundry (forge test)")
    
    console.print(table)
    input("\n[按 Enter 继续...]")


def demo_vulnerable_contract():
    """演示3: 展示漏洞合约"""
    print_section("3. 示例漏洞合约 - Vulnerable Contract")
    
    contract_path = Path("data/contracts/VulnerableAccessControl.sol")
    if contract_path.exists():
        source = contract_path.read_text()
        
        # 只显示关键部分
        key_parts = """// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

contract VulnerableAccessControl {
    address public owner;
    uint256 public protocolFee;

    modifier onlyOwner() {
        require(msg.sender == owner, "Not owner");
        _;
    }

    // ⚠️ 漏洞1: 缺少 onlyOwner 修饰符!
    function setProtocolFee(uint256 _fee) external {
        protocolFee = _fee;  // 任何人都能修改!
    }

    // ⚠️ 漏洞2: 缺少 onlyOwner 修饰符!
    function withdraw() external {
        payable(msg.sender).transfer(address(this).balance);
    }

    // ✅ 正确: 有 onlyOwner 保护
    function pause() external onlyOwner {
        paused = true;
    }
}"""
        
        console.print("[bold red]漏洞说明:[/bold red]")
        console.print("• setProtocolFee() - 缺少访问控制，任何人可修改费用")
        console.print("• withdraw() - 缺少访问控制，任何人可提取资金\n")
        
        syntax = Syntax(key_parts, "solidity", theme="monokai", line_numbers=True)
        console.print(syntax)
    else:
        console.print("[yellow]示例合约文件不存在[/yellow]")
    
    input("\n[按 Enter 继续...]")


def demo_state_definition():
    """演示4: 状态定义"""
    print_section("4. 工作流状态定义 - State Schema")
    
    state_code = '''class AuditGraphState(TypedDict):
    """简化版审计状态"""
    
    # 输入
    contract_source: str          # 合约源码
    contract_name: str            # 合约名称
    
    # 分析结果
    sensitive_functions: List[Dict]  # 敏感函数列表
    audit_hypothesis: str            # 审计假说
    current_target_function: str     # 当前目标
    
    # 验证
    verification_poc: str         # PoC 代码
    execution_result: Literal["pass", "fail_revert", "fail_error"]
    
    # 控制流
    retry_count: int
    max_retries: int
    
    # 输出
    finding_confirmed: bool       # 漏洞是否确认
    audit_report: Dict            # 审计报告
    
    # 训练数据收集
    collect_training_data: bool   # 是否收集数据
    training_examples: List[Dict] # 收集的样本'''
    
    console.print("[bold]状态在各节点间传递，实现信息共享:[/bold]\n")
    syntax = Syntax(state_code, "python", theme="monokai", line_numbers=True)
    console.print(syntax)
    
    input("\n[按 Enter 继续...]")


def demo_training_data():
    """演示5: 训练数据格式"""
    print_section("5. 训练数据格式 - Training Data Format")
    
    console.print("[bold]为后续 LLM 微调设计的数据格式:[/bold]\n")
    
    example = '''{
  "task_type": "analyze",
  "input_data": {
    "contract_source": "contract Vault { function setFee()... }",
    "contract_name": "Vault"
  },
  "output_data": {
    "is_vulnerable": true,
    "vulnerable_functions": ["setFee", "withdraw"],
    "vulnerability_type": "access_control",
    "hypothesis": "setFee() lacks onlyOwner modifier"
  },
  "source": "auto",
  "confirmed": true
}'''
    
    syntax = Syntax(example, "json", theme="monokai")
    console.print(syntax)
    
    console.print("\n[bold]支持的导出格式:[/bold]")
    console.print("• OpenAI fine-tuning format (JSONL)")
    console.print("• Alpaca format (for open-source models)")
    
    input("\n[按 Enter 继续...]")


def demo_next_steps():
    """演示6: 后续计划"""
    print_section("6. 后续开发计划 - Next Steps")
    
    plan = """
## 阶段一: 数据收集 (当前)
- [x] 搭建基础框架
- [x] 定义训练数据格式
- [ ] 收集 100+ 漏洞合约样本
- [ ] 人工标注和验证

## 阶段二: 模型训练
- [ ] 使用 OpenAI fine-tuning 或开源模型
- [ ] 针对访问控制漏洞专项优化
- [ ] 评估模型效果

## 阶段三: Agent 优化
- [ ] 用微调模型替换通用 GPT-4
- [ ] 添加更多漏洞类型支持
- [ ] 优化 PoC 生成质量

## 阶段四: 扩展
- [ ] 支持闪电贷攻击向量
- [ ] 支持链上数据分析
- [ ] 多 Agent 协作
"""
    console.print(Markdown(plan))
    input("\n[按 Enter 继续...]")


def demo_run_audit():
    """演示7: 实际运行"""
    print_section("7. 运行演示 - Live Demo")
    
    console.print("[bold]运行命令:[/bold]")
    console.print("```")
    console.print("python scripts/run_audit.py --contract data/contracts/VulnerableAccessControl.sol")
    console.print("```\n")
    
    console.print("[bold yellow]注意:[/bold yellow] 实际运行需要:")
    console.print("1. 设置 OPENAI_API_KEY 环境变量")
    console.print("2. 安装 Foundry (forge)")
    console.print("3. 网络连接正常")
    
    run_now = input("\n是否现在运行? (y/n): ").lower()
    
    if run_now == 'y':
        console.print("\n[cyan]正在运行审计...[/cyan]\n")
        import subprocess
        try:
            result = subprocess.run(
                ["python", "scripts/run_audit.py", 
                 "--contract", "data/contracts/VulnerableAccessControl.sol"],
                capture_output=False,
                timeout=120
            )
        except Exception as e:
            console.print(f"[red]运行出错: {e}[/red]")
    else:
        console.print("\n[dim]跳过实际运行[/dim]")


def main():
    console.print(Panel.fit(
        "[bold blue]访问控制漏洞检测 Agent 演示[/bold blue]\n"
        "[dim]Smart Contract Access Control Vulnerability Detection[/dim]",
        border_style="blue"
    ))
    
    demos = [
        ("项目概述", demo_project_overview),
        ("系统架构", demo_architecture),
        ("漏洞合约示例", demo_vulnerable_contract),
        ("状态定义", demo_state_definition),
        ("训练数据格式", demo_training_data),
        ("后续计划", demo_next_steps),
        ("运行演示", demo_run_audit),
    ]
    
    console.print("\n[bold]演示内容:[/bold]")
    for i, (name, _) in enumerate(demos, 1):
        console.print(f"  {i}. {name}")
    
    console.print("\n" + "="*60)
    input("按 Enter 开始演示...")
    
    for name, demo_func in demos:
        demo_func()
    
    print_section("演示结束 - Demo Complete")
    console.print("[bold green]感谢观看！[/bold green]\n")


if __name__ == "__main__":
    main()
