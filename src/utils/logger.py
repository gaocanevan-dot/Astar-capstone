"""
Logging configuration for the Audit Agent.
"""

import logging
import sys
from typing import Optional
from rich.logging import RichHandler
from rich.console import Console

from ..core.config import get_settings


# 全局 console 实例
console = Console()


def setup_logger(
    name: str = "audit_agent",
    level: Optional[str] = None
) -> logging.Logger:
    """
    配置并返回日志记录器。
    
    使用 Rich 提供美观的控制台输出。
    """
    settings = get_settings()
    log_level = level or settings.log_level
    
    # 创建 logger
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, log_level.upper()))
    
    # 清除现有 handlers
    logger.handlers.clear()
    
    # 添加 Rich handler
    rich_handler = RichHandler(
        console=console,
        show_time=True,
        show_path=False,
        markup=True,
        rich_tracebacks=True
    )
    rich_handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(rich_handler)
    
    return logger


def get_logger(name: str = "audit_agent") -> logging.Logger:
    """获取已配置的日志记录器"""
    logger = logging.getLogger(name)
    
    # 如果没有 handler，进行设置
    if not logger.handlers:
        return setup_logger(name)
    
    return logger


class AuditLogger:
    """
    专门用于审计流程的日志记录器。
    
    提供结构化的日志输出，便于追踪审计过程。
    """
    
    def __init__(self, name: str = "audit"):
        self.logger = get_logger(f"audit_agent.{name}")
    
    def node_enter(self, node_name: str, state_summary: str = ""):
        """记录进入节点"""
        self.logger.info(f"[bold blue]→ Entering node:[/bold blue] {node_name}")
        if state_summary:
            self.logger.debug(f"  State: {state_summary}")
    
    def node_exit(self, node_name: str, result_summary: str = ""):
        """记录离开节点"""
        self.logger.info(f"[bold green]← Exiting node:[/bold green] {node_name}")
        if result_summary:
            self.logger.debug(f"  Result: {result_summary}")
    
    def hypothesis(self, hypothesis: str):
        """记录审计假说"""
        self.logger.info(f"[bold yellow]💡 Hypothesis:[/bold yellow] {hypothesis}")
    
    def poc_generated(self, function_name: str):
        """记录 PoC 生成"""
        self.logger.info(f"[bold cyan]📝 PoC generated for:[/bold cyan] {function_name}")
    
    def verification_result(self, result: str, details: str = ""):
        """记录验证结果"""
        emoji = "✅" if result == "pass" else "❌"
        color = "green" if result == "pass" else "red"
        self.logger.info(f"[bold {color}]{emoji} Verification result:[/bold {color}] {result}")
        if details:
            self.logger.debug(f"  Details: {details}")
    
    def finding(self, severity: str, description: str):
        """记录发现的漏洞"""
        color_map = {
            "critical": "red",
            "high": "red",
            "medium": "yellow",
            "low": "blue"
        }
        color = color_map.get(severity.lower(), "white")
        self.logger.warning(f"[bold {color}]🚨 Finding [{severity}]:[/bold {color}] {description}")
    
    def retry(self, count: int, max_retries: int, reason: str):
        """记录重试"""
        self.logger.info(f"[bold orange]🔄 Retry {count}/{max_retries}:[/bold orange] {reason}")
    
    def error(self, message: str, exception: Optional[Exception] = None):
        """记录错误"""
        self.logger.error(f"[bold red]❌ Error:[/bold red] {message}")
        if exception:
            self.logger.exception(exception)
