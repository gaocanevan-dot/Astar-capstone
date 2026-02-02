# 访问控制漏洞检测 Agent - 简化版文档

## 1. 项目目标

本项目是一个**简化的基础框架**，专注于：

1. **访问控制漏洞检测** - 检测缺失的权限控制
2. **权限升级漏洞检测** - 检测未保护的权限转移
3. **训练数据收集** - 为后续 LLM 模型训练提供数据基础

> 注意：这不是一个完整的审计系统，而是为模型训练做准备的基础框架。

## 2. 核心架构

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Analyst   │ ──▶ │   Builder   │ ──▶ │  Verifier   │
│  分析合约    │     │  生成 PoC   │     │  执行验证    │
└─────────────┘     └─────────────┘     └──────┬──────┘
                           ▲                    │
                           │     重试           │
                           └────────────────────┘
```

### 节点说明

| 节点     | 功能                  | 输入           | 输出                        |
| -------- | --------------------- | -------------- | --------------------------- |
| Analyst  | 分析合约识别敏感函数  | 合约源码       | 敏感函数列表、假说          |
| Builder  | 生成 Foundry 测试代码 | 假说、目标函数 | PoC 代码                    |
| Verifier | 执行测试验证漏洞      | PoC 代码       | pass/fail_revert/fail_error |

## 3. 目录结构

```
agent/
├── src/
│   ├── core/
│   │   ├── state.py      # 状态定义 (简化版)
│   │   ├── config.py     # 配置管理 (简化版)
│   │   └── graph.py      # LangGraph 工作流
│   │
│   ├── nodes/
│   │   ├── analyst.py    # 访问控制分析
│   │   ├── builder.py    # PoC 生成
│   │   └── verifier.py   # 动态验证
│   │
│   └── dataset/          # 【新增】训练数据模块
│       ├── schemas.py    # 数据格式定义
│       ├── collector.py  # 数据收集器
│       └── formatter.py  # 格式转换器
│
├── scripts/
│   ├── run_audit.py      # 运行审计
│   └── collect_data.py   # 收集训练数据
│
└── data/
    ├── contracts/        # 测试合约
    └── training/         # 训练数据输出
```

## 4. 训练数据格式

### 4.1 分析任务数据

```json
{
  "task_type": "analyze",
  "input_data": {
    "contract_source": "pragma solidity ^0.8.0; ...",
    "contract_name": "VulnerableVault"
  },
  "output_data": {
    "is_vulnerable": true,
    "vulnerable_functions": ["setFee", "withdraw"],
    "vulnerability_type": "access_control",
    "hypothesis": "setFee lacks onlyOwner modifier"
  }
}
```

### 4.2 PoC 生成任务数据

```json
{
  "task_type": "generate_poc",
  "input_data": {
    "contract_source": "...",
    "target_function": "setFee",
    "vulnerability_hypothesis": "Missing access control"
  },
  "output_data": {
    "poc_code": "function test_UnauthorizedSetFee() public { ... }"
  }
}
```

### 4.3 导出格式

支持导出为：
- **OpenAI 格式** - 用于 OpenAI fine-tuning
- **Alpaca 格式** - 用于开源模型微调

## 5. 快速开始

### 5.1 安装

```bash
cd "e:\Studying Material\Capstone\agent"
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -e .
```

### 5.2 配置

```bash
cp .env.example .env
# 编辑 .env，设置 OPENAI_API_KEY
```

### 5.3 运行审计

```bash
# 基本审计
python scripts/run_audit.py --contract data/contracts/example.sol

# 同时收集训练数据
python scripts/run_audit.py --contract data/contracts/example.sol --collect-data
```

### 5.4 收集训练数据

```bash
# 从目录批量收集
python scripts/collect_data.py collect --input data/contracts/ --output data/training/

# 导出为 OpenAI 格式
python scripts/collect_data.py export --dataset data/training/dataset.json --format openai

# 查看统计
python scripts/collect_data.py stats --dataset data/training/dataset.json
```

## 6. 下一步计划

这个简化框架为后续工作提供基础：

1. **收集更多训练数据**
   - 从公开审计报告收集
   - 人工标注漏洞合约
   - 使用当前 Agent 自动生成

2. **微调 LLM 模型**
   - 使用收集的数据微调模型
   - 专门针对访问控制漏洞优化

3. **替换节点中的 LLM**
   - 用微调后的模型替换 OpenAI API
   - 形成自己的专属 Agent

## 7. 文件说明

| 文件                       | 作用                                 |
| -------------------------- | ------------------------------------ |
| `src/core/state.py`        | 定义工作流状态，包含训练数据收集字段 |
| `src/core/graph.py`        | LangGraph 工作流定义                 |
| `src/nodes/analyst.py`     | 分析节点，识别缺少访问控制的函数     |
| `src/nodes/builder.py`     | 生成 Foundry 测试代码                |
| `src/nodes/verifier.py`    | 执行测试验证漏洞                     |
| `src/dataset/schemas.py`   | 训练数据格式定义                     |
| `src/dataset/collector.py` | 数据收集器                           |
| `src/dataset/formatter.py` | 格式转换工具                         |

---

*版本: v0.2.0 (简化版)*  
*专注于: 访问控制 & 权限升级漏洞*
