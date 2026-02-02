"""
Foundry (Anvil/Forge) Integration Tool.

Provides functionality to:
- Run Anvil local fork
- Execute Forge tests
- Interact with deployed contracts
"""

import subprocess
import json
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass


@dataclass
class ForgeTestResult:
    """Forge 测试结果"""
    success: bool
    test_name: str
    gas_used: int
    logs: List[str]
    traces: List[str]
    error: Optional[str] = None


class FoundryTool:
    """Foundry 工具集成类"""
    
    def __init__(self, rpc_url: str = "http://127.0.0.1:8545"):
        self.rpc_url = rpc_url
        self.anvil_process = None
    
    def start_anvil(
        self,
        fork_url: Optional[str] = None,
        fork_block: Optional[int] = None,
        port: int = 8545
    ) -> bool:
        """启动 Anvil 本地节点"""
        cmd = ["anvil", "--port", str(port)]
        
        if fork_url:
            cmd.extend(["--fork-url", fork_url])
        if fork_block:
            cmd.extend(["--fork-block-number", str(fork_block)])
        
        try:
            self.anvil_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            return True
        except Exception as e:
            print(f"Failed to start Anvil: {e}")
            return False
    
    def stop_anvil(self):
        """停止 Anvil 节点"""
        if self.anvil_process:
            self.anvil_process.terminate()
            self.anvil_process = None
    
    def run_forge_test(
        self,
        project_path: str,
        test_contract: Optional[str] = None,
        test_function: Optional[str] = None,
        verbosity: int = 3,
        fork_url: Optional[str] = None,
        fork_block: Optional[int] = None
    ) -> Tuple[bool, str, str]:
        """
        运行 Forge 测试。
        
        Args:
            project_path: Foundry 项目路径
            test_contract: 指定测试合约名
            test_function: 指定测试函数名
            verbosity: 日志详细程度 (1-5)
            fork_url: Fork RPC URL
            fork_block: Fork 区块高度
            
        Returns:
            (success, stdout, stderr)
        """
        cmd = ["forge", "test", f"-{'v' * verbosity}"]
        
        if test_contract:
            cmd.extend(["--match-contract", test_contract])
        if test_function:
            cmd.extend(["--match-test", test_function])
        if fork_url:
            cmd.extend(["--fork-url", fork_url])
        if fork_block:
            cmd.extend(["--fork-block-number", str(fork_block)])
        
        try:
            result = subprocess.run(
                cmd,
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=300
            )
            return result.returncode == 0, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return False, "", "Test execution timed out"
        except Exception as e:
            return False, "", str(e)
    
    def forge_build(self, project_path: str) -> Tuple[bool, str, str]:
        """编译 Foundry 项目"""
        try:
            result = subprocess.run(
                ["forge", "build"],
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=120
            )
            return result.returncode == 0, result.stdout, result.stderr
        except Exception as e:
            return False, "", str(e)
    
    def cast_call(
        self,
        contract_address: str,
        function_sig: str,
        args: List[str] = None,
        rpc_url: Optional[str] = None
    ) -> Tuple[bool, str]:
        """
        使用 Cast 调用合约函数（只读）。
        
        Args:
            contract_address: 合约地址
            function_sig: 函数签名 (如 "balanceOf(address)")
            args: 函数参数
            rpc_url: RPC URL
        """
        cmd = ["cast", "call", contract_address, function_sig]
        
        if args:
            cmd.extend(args)
        
        cmd.extend(["--rpc-url", rpc_url or self.rpc_url])
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )
            return result.returncode == 0, result.stdout.strip()
        except Exception as e:
            return False, str(e)
    
    def cast_send(
        self,
        contract_address: str,
        function_sig: str,
        args: List[str] = None,
        private_key: str = None,
        value: str = None,
        rpc_url: Optional[str] = None
    ) -> Tuple[bool, str]:
        """
        使用 Cast 发送交易（写操作）。
        """
        cmd = ["cast", "send", contract_address, function_sig]
        
        if args:
            cmd.extend(args)
        if private_key:
            cmd.extend(["--private-key", private_key])
        if value:
            cmd.extend(["--value", value])
        
        cmd.extend(["--rpc-url", rpc_url or self.rpc_url])
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60
            )
            return result.returncode == 0, result.stdout.strip()
        except Exception as e:
            return False, str(e)


def check_foundry_installed() -> bool:
    """检查 Foundry 是否已安装"""
    try:
        result = subprocess.run(
            ["forge", "--version"],
            capture_output=True,
            text=True,
            timeout=10
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False
