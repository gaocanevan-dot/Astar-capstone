# Smart Contract Access Control Vulnerability Agent

基于 RAG 增强的 DeFi 智能合约**访问控制漏洞**检测系统。

## 项目目标

### 核心目标

1. **加载数据集**：将你手动构建的漏洞数据集加载到向量库
2. **RAG 增强分析**：分析前检索相似漏洞案例，提升检测效果
3. **自动生成 PoC**：生成 Foundry 测试代码验证漏洞
4. **评估效果**：用数据集测试 Agent 的 Recall 和 PoC 成功率

### 漏洞类型范围（仅专注于）

- **访问控制漏洞 (Access Control)**
  - 缺失的 `onlyOwner` 修饰符
  - 不正确的角色检查
  - 公开的敏感函数
  
- **权限升级漏洞 (Privilege Escalation)**
  - 未保护的所有权转移
  - 角色管理漏洞

## 项目架构

```
agent/
├── src/
│   ├── core/              # 核心模块
│   │   ├── state.py       # 共享状态 (含 RAG 检索结果)
│   │   ├── graph.py       # LangGraph 工作流 (RAG 增强)
│   │   └── config.py      # 配置管理
│   │
│   ├── nodes/             # Agent 节点
│   │   ├── analyst.py     # 漏洞分析 (含 RAG 检索)
│   │   ├── builder.py     # PoC 生成
│   │   └── verifier.py    # 验证执行
│   │
│   ├── dataset/           # 数据集模块 (核心!)
│   │   ├── loader.py      # 数据集加载器
│   │   ├── schemas.py     # 数据结构定义
│   │   └── collector.py   # (保留) 数据收集
│   │
│   ├── rag/               # RAG 模块
│   │   ├── vectorstore.py # 向量库 (ChromaDB)
│   │   ├── retriever.py   # 检索器
│   │   └── embeddings.py  # 嵌入模型
│   │
│   └── evaluation/        # 评估模块 (新增!)
│       └── evaluator.py   # 用数据集评估 Agent
│
├── data/
│   ├── dataset/           # 你的漏洞数据集
│   ├── vectorstore/       # 向量库存储
│   ├── contracts/         # 测试合约
│   └── evaluation/        # 评估报告
│
└── scripts/
    ├── run_audit.py       # 主入口 (支持 RAG)
    └── evaluate.py        # 评估脚本
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 设置 OPENAI_API_KEY
```

### 3. 准备数据集

创建示例数据集查看格式：
```bash
python scripts/run_audit.py --create-sample
```

数据集格式 (`data/dataset/vulnerabilities.json`):
```json
{
  "cases": [
    {
      "id": "case_001",
      "contract_source": "// Solidity code...",
      "contract_name": "VulnerableVault",
      "vulnerable_function": "setProtocolFee",
      "vulnerability_type": "access_control",
      "severity": "high",
      "description": "Missing onlyOwner modifier",
      "poc_code": "function test_exploit() { ... }",
      "fix_recommendation": "Add onlyOwner modifier"
    }
  ]
}
```

### 4. 加载数据集到向量库

```bash
python scripts/run_audit.py --load-dataset data/dataset/vulnerabilities.json
```

### 5. 运行审计

```bash
# 使用 RAG 增强 (默认)
python scripts/run_audit.py --contract path/to/contract.sol

# 不使用 RAG (对比用)
python scripts/run_audit.py --contract path/to/contract.sol --no-rag
```

### 6. 评估 Agent 效果

```bash
python scripts/evaluate.py --dataset data/dataset/vulnerabilities.json
```

## 工作流程

```
你的数据集
    │
    ▼
┌─────────────────┐
│  加载到向量库   │  ← VectorStore (ChromaDB)
└────────┬────────┘
         │
         ▼
待审计合约 ─────────────────────────────────────────┐
         │                                          │
         ▼                                          ▼
┌─────────────────┐                        ┌─────────────────┐
│  RAG 检索       │ ───── 相似案例 ─────── │  Analyst 节点   │
│  (Few-Shot)     │                        │  (漏洞分析)     │
└─────────────────┘                        └────────┬────────┘
                                                    │
                                                    ▼
                                           ┌─────────────────┐
                                           │  Builder 节点   │
                                           │  (生成 PoC)     │
                                           └────────┬────────┘
                                                    │
                                                    ▼
                                           ┌─────────────────┐
                                           │  Verifier 节点  │
                                           │  (Foundry 验证) │
                                           └────────┬────────┘
                                                    │
                            ┌───────────────────────┼───────────────────────┐
                            │                       │                       │
                        pass (漏洞确认)      fail_error (重试)      fail_revert (安全)
                            │                       │                       │
                            ▼                       │                       ▼
                      生成报告                  回到 Builder             标记安全
```

## 评估指标

运行 `evaluate.py` 后会生成以下指标：

| 指标                 | 说明                      |
| -------------------- | ------------------------- |
| **Recall**           | 检出的漏洞数 / 总漏洞数   |
| **Detection Rate**   | Analyst 节点检出的比例    |
| **PoC Success Rate** | PoC 执行成功 / PoC 生成数 |

### 错题分析

- **Analyst Missed**: Node 1 没检出
- **Builder Failed**: Node 2 没生成 PoC
- **PoC Syntax Error**: PoC 语法错误
- **PoC Wrong Logic**: PoC 逻辑错误

## 技术栈

- **LangGraph**: 工作流编排
- **LangChain + OpenAI**: LLM 集成
- **ChromaDB**: 向量数据库
- **Foundry**: 智能合约测试
- **Pydantic**: 数据验证

## License

MIT
