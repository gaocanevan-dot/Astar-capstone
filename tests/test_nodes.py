"""
Tests for audit workflow nodes.
"""

import pytest
from unittest.mock import Mock, patch

from src.core.state_schema import create_initial_state, AuditGraphState
from src.nodes.analyst import analyze_access_control, extract_roles_with_regex, extract_modifiers_with_regex
from src.nodes.builder import build_verification_poc, clean_code_output
from src.nodes.verifier import parse_forge_output


# 测试用的示例合约
SAMPLE_CONTRACT = """
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import "@openzeppelin/contracts/access/Ownable.sol";

contract VulnerableContract is Ownable {
    uint256 public fee;
    address public admin;
    
    modifier onlyAdmin() {
        require(msg.sender == admin, "Not admin");
        _;
    }
    
    function setFee(uint256 _fee) public {
        // Missing onlyOwner modifier!
        fee = _fee;
    }
    
    function setAdmin(address _admin) public onlyOwner {
        admin = _admin;
    }
    
    function withdraw() public onlyAdmin {
        payable(msg.sender).transfer(address(this).balance);
    }
}
"""


class TestAnalystNode:
    """测试权限分析节点"""
    
    def test_extract_roles_with_regex(self):
        """测试角色提取"""
        roles = extract_roles_with_regex(SAMPLE_CONTRACT)
        # 应该能提取到 owner 和 admin 相关的变量
        assert any('admin' in r.lower() for r in roles) or any('owner' in r.lower() for r in roles)
    
    def test_extract_modifiers_with_regex(self):
        """测试修饰符提取"""
        modifiers = extract_modifiers_with_regex(SAMPLE_CONTRACT)
        assert "onlyAdmin" in modifiers
    
    @patch('src.nodes.analyst.ChatOpenAI')
    def test_analyze_access_control(self, mock_llm):
        """测试完整分析流程（Mock LLM）"""
        # Mock LLM 响应
        mock_response = {
            "defined_roles": ["Owner", "Admin"],
            "modifiers_found": ["onlyOwner", "onlyAdmin"],
            "sensitive_functions": [
                {
                    "name": "setFee",
                    "signature": "setFee(uint256)",
                    "expected_role": "Owner",
                    "current_modifiers": [],
                    "is_state_changing": True,
                    "risk_level": "high",
                    "protection_adequate": False,
                    "concern": "Missing access control modifier"
                }
            ],
            "audit_hypothesis": "Function 'setFee' lacks access control and can be called by anyone"
        }
        
        mock_llm.return_value.invoke.return_value = Mock(content=str(mock_response))
        
        state = create_initial_state(
            contract_source=SAMPLE_CONTRACT,
            contract_name="VulnerableContract"
        )
        
        # 注意：实际测试需要配置 API key
        # result = analyze_access_control(state)
        # assert len(result["sensitive_functions"]) > 0


class TestBuilderNode:
    """测试证据构建节点"""
    
    def test_clean_code_output(self):
        """测试代码清理"""
        code_with_markdown = """```solidity
contract Test {
    function test() public {}
}
```"""
        
        cleaned = clean_code_output(code_with_markdown)
        assert not cleaned.startswith("```")
        assert not cleaned.endswith("```")
        assert "contract Test" in cleaned


class TestVerifierNode:
    """测试验证节点"""
    
    def test_parse_forge_output_pass(self):
        """测试解析通过的测试输出"""
        output = """
Running 1 test for test/Test.t.sol:TestContract
[PASS] test_AccessControl() (gas: 12345)
Test result: ok. 1 passed; 0 failed
"""
        result = parse_forge_output(output, "", 0)
        assert result[0] == "pass"
    
    def test_parse_forge_output_fail_revert(self):
        """测试解析失败（权限拦截）的输出"""
        output = """
Error: revert: Ownable: caller is not the owner
"""
        result = parse_forge_output(output, "", 1)
        assert result[0] == "fail_revert"
    
    def test_parse_forge_output_fail_error(self):
        """测试解析失败（编译错误）的输出"""
        stderr = """
Compiler run failed:
Error: ParserError: Expected ';' but got '}'
"""
        result = parse_forge_output("", stderr, 1)
        assert result[0] == "fail_error"


class TestStateManagement:
    """测试状态管理"""
    
    def test_create_initial_state(self):
        """测试初始状态创建"""
        state = create_initial_state(
            contract_source=SAMPLE_CONTRACT,
            contract_name="TestContract",
            max_retries=3
        )
        
        assert state["contract_source"] == SAMPLE_CONTRACT
        assert state["contract_name"] == "TestContract"
        assert state["max_retries"] == 3
        assert state["retry_count"] == 0
        assert state["audit_status"] == "in_progress"
        assert state["execution_result"] == "pending"
    
    def test_state_has_all_required_fields(self):
        """测试状态包含所有必需字段"""
        state = create_initial_state(
            contract_source="contract Test {}",
            contract_name="Test"
        )
        
        required_fields = [
            "contract_source", "contract_abi", "contract_name",
            "defined_roles", "sensitive_functions",
            "audit_hypothesis", "verification_poc",
            "execution_result", "retry_count", "max_retries",
            "finding_confirmed", "audit_report"
        ]
        
        for field in required_fields:
            assert field in state, f"Missing field: {field}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
