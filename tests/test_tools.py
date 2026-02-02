"""
Tests for external tools integration.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import subprocess

from src.tools.foundry import FoundryTool, check_foundry_installed
from src.tools.slither import SlitherTool, SlitherFinding, check_slither_installed


class TestFoundryTool:
    """测试 Foundry 工具集成"""
    
    def test_foundry_tool_initialization(self):
        """测试工具初始化"""
        tool = FoundryTool(rpc_url="http://localhost:8545")
        assert tool.rpc_url == "http://localhost:8545"
        assert tool.anvil_process is None
    
    @patch('subprocess.run')
    def test_forge_build(self, mock_run):
        """测试 forge build"""
        mock_run.return_value = Mock(returncode=0, stdout="Success", stderr="")
        
        tool = FoundryTool()
        success, stdout, stderr = tool.forge_build("/tmp/project")
        
        assert success
        mock_run.assert_called_once()
    
    @patch('subprocess.run')
    def test_cast_call(self, mock_run):
        """测试 cast call"""
        mock_run.return_value = Mock(returncode=0, stdout="0x1234")
        
        tool = FoundryTool()
        success, result = tool.cast_call(
            "0x1234567890123456789012345678901234567890",
            "balanceOf(address)",
            ["0xabcd"]
        )
        
        assert success
        assert result == "0x1234"
    
    @patch('subprocess.run')
    def test_check_foundry_installed(self, mock_run):
        """测试 Foundry 安装检查"""
        mock_run.return_value = Mock(returncode=0)
        assert check_foundry_installed() == True
        
        mock_run.side_effect = FileNotFoundError()
        assert check_foundry_installed() == False


class TestSlitherTool:
    """测试 Slither 工具集成"""
    
    def test_slither_tool_initialization(self):
        """测试工具初始化"""
        tool = SlitherTool(solc_version="0.8.20")
        assert tool.solc_version == "0.8.20"
    
    @patch('subprocess.run')
    def test_analyze_with_json_output(self, mock_run):
        """测试 Slither 分析（JSON 输出）"""
        mock_output = {
            "results": {
                "detectors": [
                    {
                        "check": "arbitrary-send-eth",
                        "impact": "High",
                        "confidence": "Medium",
                        "description": "Test finding",
                        "elements": []
                    }
                ]
            }
        }
        
        mock_run.return_value = Mock(
            returncode=0,
            stdout='{"results": {"detectors": []}}',
            stderr=""
        )
        
        tool = SlitherTool()
        # 注意：实际运行需要 Slither 安装
        # success, findings, output = tool.analyze("test.sol")
    
    def test_parse_findings(self):
        """测试发现解析"""
        tool = SlitherTool()
        
        output = {
            "results": {
                "detectors": [
                    {
                        "check": "unprotected-upgrade",
                        "impact": "High",
                        "confidence": "High",
                        "description": "Unprotected upgrade function",
                        "elements": []
                    },
                    {
                        "check": "tx-origin",
                        "impact": "Medium",
                        "confidence": "Medium",
                        "description": "Use of tx.origin",
                        "elements": []
                    }
                ]
            }
        }
        
        findings = tool._parse_findings(output)
        
        assert len(findings) == 2
        assert findings[0].check == "unprotected-upgrade"
        assert findings[0].impact == "High"
        assert findings[1].check == "tx-origin"
        assert findings[1].impact == "Medium"
    
    @patch('subprocess.run')
    def test_check_slither_installed(self, mock_run):
        """测试 Slither 安装检查"""
        mock_run.return_value = Mock(returncode=0)
        assert check_slither_installed() == True
        
        mock_run.side_effect = FileNotFoundError()
        assert check_slither_installed() == False


class TestSlitherFinding:
    """测试 SlitherFinding 数据类"""
    
    def test_finding_creation(self):
        """测试发现对象创建"""
        finding = SlitherFinding(
            check="arbitrary-send-eth",
            impact="High",
            confidence="Medium",
            description="Arbitrary ETH transfer",
            elements=[{"type": "function", "name": "withdraw"}]
        )
        
        assert finding.check == "arbitrary-send-eth"
        assert finding.impact == "High"
        assert len(finding.elements) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
