"""
Aderyn Static Analysis Tool Integration.

Aderyn is a Rust-based Solidity static analyzer that focuses on
security vulnerabilities detection.
"""

import subprocess
import json
from typing import Optional, List, Dict, Tuple
from dataclasses import dataclass, field


@dataclass
class AderynFinding:
    """Aderyn 发现的问题"""
    title: str
    severity: str  # High, Medium, Low
    description: str
    instances: List[Dict] = field(default_factory=list)


class AderynTool:
    """Aderyn 静态分析工具"""
    
    def analyze(
        self,
        target: str,
        output_format: str = "json"
    ) -> Tuple[bool, List[AderynFinding], str]:
        """
        运行 Aderyn 分析。
        
        Args:
            target: 要分析的合约文件或项目目录
            output_format: 输出格式 (json, markdown)
            
        Returns:
            (success, findings, raw_output)
        """
        cmd = ["aderyn", target]
        
        if output_format == "json":
            cmd.extend(["--output", "report.json"])
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300
            )
            
            # 如果是 JSON 输出，读取报告文件
            if output_format == "json":
                try:
                    with open("report.json", "r") as f:
                        output = json.load(f)
                    findings = self._parse_findings(output)
                    return True, findings, json.dumps(output)
                except (FileNotFoundError, json.JSONDecodeError):
                    return False, [], result.stderr
            
            return True, [], result.stdout
            
        except subprocess.TimeoutExpired:
            return False, [], "Aderyn analysis timed out"
        except FileNotFoundError:
            return False, [], "Aderyn not found. Please install from: https://github.com/Cyfrin/aderyn"
        except Exception as e:
            return False, [], str(e)
    
    def _parse_findings(self, output: Dict) -> List[AderynFinding]:
        """解析 Aderyn JSON 输出"""
        findings = []
        
        # 解析高危发现
        high_issues = output.get("high_issues", {}).get("issues", [])
        for issue in high_issues:
            finding = AderynFinding(
                title=issue.get("title", ""),
                severity="High",
                description=issue.get("description", ""),
                instances=issue.get("instances", [])
            )
            findings.append(finding)
        
        # 解析中危发现
        medium_issues = output.get("medium_issues", {}).get("issues", [])
        for issue in medium_issues:
            finding = AderynFinding(
                title=issue.get("title", ""),
                severity="Medium",
                description=issue.get("description", ""),
                instances=issue.get("instances", [])
            )
            findings.append(finding)
        
        # 解析低危发现
        low_issues = output.get("low_issues", {}).get("issues", [])
        for issue in low_issues:
            finding = AderynFinding(
                title=issue.get("title", ""),
                severity="Low",
                description=issue.get("description", ""),
                instances=issue.get("instances", [])
            )
            findings.append(finding)
        
        return findings


def check_aderyn_installed() -> bool:
    """检查 Aderyn 是否已安装"""
    try:
        result = subprocess.run(
            ["aderyn", "--version"],
            capture_output=True,
            text=True,
            timeout=10
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False
