"""
Node 3: Dynamic Verifier (验证节点)

简化版 - 执行 Foundry 测试验证漏洞
"""

import subprocess
import tempfile
from pathlib import Path
from typing import Tuple, Literal

from ..core.state import AuditGraphState
from ..core.config import get_settings


def verify_poc(state: AuditGraphState) -> AuditGraphState:
    """
    执行 PoC 并验证结果
    
    结果:
    - pass: 漏洞确认 (攻击成功)
    - fail_revert: 安全 (被权限拦截)
    - fail_error: 代码错误 (需重试)
    """
    settings = get_settings()
    
    poc_code = state.get("verification_poc", "")
    contract_source = state.get("contract_source", "")
    contract_name = state.get("contract_name", "Contract")
    
    if not poc_code:
        return {
            **state,
            "execution_result": "fail_error",
            "error_message": "No PoC code"
        }
    
    try:
        result, trace, error = run_foundry_test(
            contract_source=contract_source,
            contract_name=contract_name,
            poc_code=poc_code
        )
        
        # 收集训练数据
        training_examples = state.get("training_examples", [])
        if state.get("collect_training_data"):
            training_examples.append({
                "task": "verify",
                "input": {
                    "poc_code": poc_code,
                    "execution_trace": trace
                },
                "output": {
                    "result": result,
                    "confirmed": result == "pass"
                }
            })
        
        return {
            **state,
            "execution_result": result,
            "error_message": error,
            "finding_confirmed": result == "pass",
            "training_examples": training_examples
        }
        
    except Exception as e:
        return {
            **state,
            "execution_result": "fail_error",
            "error_message": f"Verification failed: {str(e)}"
        }


def run_foundry_test(
    contract_source: str,
    contract_name: str,
    poc_code: str
) -> Tuple[Literal["pass", "fail_revert", "fail_error"], str, str]:
    """
    运行 Foundry 测试
    
    Returns: (result, trace, error)
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)
        
        # 创建目录结构
        src_dir = project_dir / "src"
        test_dir = project_dir / "test"
        src_dir.mkdir()
        test_dir.mkdir()
        
        # 写入文件
        (src_dir / f"{contract_name}.sol").write_text(contract_source)
        (test_dir / f"{contract_name}.t.sol").write_text(poc_code)
        
        # foundry.toml
        (project_dir / "foundry.toml").write_text("""[profile.default]
src = "src"
out = "out"
libs = ["lib"]
solc = "0.8.20"
""")
        
        # 安装 forge-std
        try:
            subprocess.run(
                ["forge", "install", "foundry-rs/forge-std", "--no-git"],
                cwd=project_dir,
                capture_output=True,
                timeout=60
            )
        except Exception as e:
            return "fail_error", "", f"Forge init failed: {str(e)}"
        
        # 运行测试
        try:
            result = subprocess.run(
                ["forge", "test", "-vvv"],
                cwd=project_dir,
                capture_output=True,
                text=True,
                timeout=120
            )
            
            return parse_forge_output(result.stdout, result.stderr, result.returncode)
            
        except subprocess.TimeoutExpired:
            return "fail_error", "", "Test timed out"
        except FileNotFoundError:
            return "fail_error", "", "Foundry not installed"


def parse_forge_output(
    stdout: str, 
    stderr: str, 
    return_code: int
) -> Tuple[Literal["pass", "fail_revert", "fail_error"], str, str]:
    """
    解析 forge test 输出
    
    - return_code=0: 测试通过 = 漏洞存在
    - Revert: 权限拦截 = 安全
    - 其他: 代码错误
    """
    trace = stdout + "\n" + stderr
    
    # 编译错误
    if any(kw in stderr for kw in ["Compiler run failed", "Error", "ParserError"]):
        return "fail_error", trace, extract_error_message(stderr)
    
    # 测试通过 = 漏洞确认
    if return_code == 0:
        return "pass", trace, ""
    
    # 权限拦截检查
    revert_keywords = [
        "caller is not the owner", "Ownable:", "AccessControl:",
        "onlyOwner", "unauthorized", "not authorized", "access denied"
    ]
    
    if any(kw.lower() in trace.lower() for kw in revert_keywords):
        return "fail_revert", trace, "Access control working"
    
    return "fail_error", trace, extract_error_message(trace) or "Unknown error"


def extract_error_message(output: str) -> str:
    """提取错误信息"""
    lines = output.split('\n')
    error_lines = [l for l in lines if 'error' in l.lower()][:5]
    return '\n'.join(error_lines) if error_lines else output[:300]
