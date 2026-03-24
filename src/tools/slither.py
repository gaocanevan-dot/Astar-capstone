"""
Slither Static Analysis Tool Integration.

Slither is a Solidity static analysis framework that detects vulnerabilities,
prints visual information about contract details, and provides an API for custom analyses.
"""

import subprocess
import json
import sys
from pathlib import Path
from shutil import which
from typing import Optional, List, Dict, Tuple
from dataclasses import dataclass, field


@dataclass
class SlitherFinding:
    """Slither 发现的问题"""
    check: str
    impact: str  # High, Medium, Low, Informational
    confidence: str  # High, Medium, Low
    description: str
    elements: List[Dict] = field(default_factory=list)


class SlitherTool:
    """Slither 静态分析工具"""
    
    def __init__(self, solc_version: str = "0.8.20"):
        self.solc_version = solc_version
        self.slither_cmd = resolve_slither_command()
    
    def analyze(
        self,
        target: str,
        detectors: Optional[List[str]] = None,
        exclude_detectors: Optional[List[str]] = None,
        exclude_informational: bool = True,
        exclude_low: bool = False
    ) -> Tuple[bool, List[SlitherFinding], str]:
        """
        运行 Slither 分析。
        
        Args:
            target: 要分析的合约文件或项目目录
            detectors: 要运行的检测器列表
            exclude_detectors: 要排除的检测器列表
            exclude_informational: 是否排除信息级别的发现
            exclude_low: 是否排除低级别的发现
            
        Returns:
            (success, findings, raw_output)
        """
        cmd = [self.slither_cmd, target, "--json", "-"]
        
        if detectors:
            cmd.extend(["--detect", ",".join(detectors)])
        if exclude_detectors:
            cmd.extend(["--exclude", ",".join(exclude_detectors)])
        if exclude_informational:
            cmd.append("--exclude-informational")
        if exclude_low:
            cmd.append("--exclude-low")
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300
            )
            
            # 解析 JSON 输出
            try:
                output = json.loads(result.stdout)
                findings = self._parse_findings(output)
                return True, findings, result.stdout
            except json.JSONDecodeError:
                return False, [], result.stderr
                
        except subprocess.TimeoutExpired:
            return False, [], "Slither analysis timed out"
        except FileNotFoundError:
            return False, [], "Slither not found. Please install: pip install slither-analyzer"
        except Exception as e:
            return False, [], str(e)
    
    def _parse_findings(self, output: Dict) -> List[SlitherFinding]:
        """解析 Slither JSON 输出"""
        findings = []
        
        detectors = output.get("results", {}).get("detectors", [])
        
        for detector in detectors:
            finding = SlitherFinding(
                check=detector.get("check", ""),
                impact=detector.get("impact", ""),
                confidence=detector.get("confidence", ""),
                description=detector.get("description", ""),
                elements=detector.get("elements", [])
            )
            findings.append(finding)
        
        return findings
    
    def get_access_control_findings(
        self,
        target: str
    ) -> Tuple[bool, List[SlitherFinding], str]:
        """
        运行与访问控制相关的检测器。
        """
        access_control_detectors = [
            "arbitrary-send-eth",
            "arbitrary-send-erc20",
            "suicidal",
            "unprotected-upgrade",
            "missing-zero-check",
            "tx-origin",
            "controlled-delegatecall"
        ]
        
        return self.analyze(
            target=target,
            detectors=access_control_detectors,
            exclude_informational=True
        )
    
    def get_function_summary(self, target: str) -> Tuple[bool, str]:
        """获取合约函数摘要"""
        cmd = [self.slither_cmd, target, "--print", "function-summary"]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120
            )
            return result.returncode == 0, result.stdout
        except Exception as e:
            return False, str(e)
    
    def get_modifiers(self, target: str) -> Tuple[bool, str]:
        """获取合约修饰符信息"""
        cmd = [self.slither_cmd, target, "--print", "modifiers"]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120
            )
            return result.returncode == 0, result.stdout
        except Exception as e:
            return False, str(e)


def check_slither_installed() -> bool:
    """检查 Slither 是否已安装"""
    try:
        result = subprocess.run(
            [resolve_slither_command(), "--version"],
            capture_output=True,
            text=True,
            timeout=10
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def resolve_slither_command() -> str:
    """Prefer the project's slither executable over the global PATH."""
    candidates = [
        Path.cwd() / "venv" / "Scripts" / "slither.exe",
        Path(sys.executable).resolve().parent / "slither.exe",
        Path.cwd() / "venv" / "bin" / "slither",
        Path(sys.executable).resolve().parent / "slither",
    ]

    for candidate in candidates:
        if candidate.exists():
            return str(candidate)

    slither_on_path = which("slither")
    if slither_on_path:
        return slither_on_path

    return "slither"
