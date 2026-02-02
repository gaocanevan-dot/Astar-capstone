# 项目汇报 - 访问控制漏洞检测 Agent (RAG 增强版)

## 汇报大纲 (5-10分钟)

---

### 1. 项目背景 (1分钟)

**问题**：
- DeFi 合约漏洞检测依赖人工专家，耗时且昂贵
- 访问控制漏洞是最常见的安全问题之一
- 通用 LLM 缺乏智能合约安全的专业知识

**解决方案**：
- 开发基于 **RAG 增强** 的 Agent 自动检测访问控制漏洞
- 利用**已有数据集**作为知识库，提升检测效果
- 支持效果评估，持续优化

---

### 2. 系统架构 (2分钟)

```
你的数据集 ──→ [向量库] ──→ 相似案例
                              │
                              ▼
输入合约 → [RAG检索] → [Analyst 分析] → [Builder 生成PoC] → [Verifier 验证] → 输出报告
                                              ↑                    |
                                              └──── 重试 ──────────┘
```

**四个核心节点**：

| 节点              | 职责                         | 技术                  |
| ----------------- | ---------------------------- | --------------------- |
| **RAG Retrieval** | 检索相似漏洞案例             | ChromaDB + Embeddings |
| **Analyst**       | 识别敏感函数 (Few-Shot 增强) | GPT-4 + RAG Context   |
| **Builder**       | 生成 Foundry 测试代码        | GPT-4 + Prompt        |
| **Verifier**      | 执行测试，验证漏洞           | Foundry               |

**技术栈**：
- LangGraph (工作流编排)
- LangChain + OpenAI (LLM 集成)
- ChromaDB (向量数据库)
- Foundry (智能合约测试)

---

### 3. 核心创新点 (2分钟)

#### 3.1 RAG 知识增强 (核心创新!)
- 将**已有漏洞数据集**加载到向量库
- 分析前检索**相似漏洞案例**作为 Few-Shot 上下文
- 让 LLM "学习" 历史漏洞模式

#### 3.2 假说-验证-修正闭环
- 不是简单的静态分析
- Agent 生成假说 → 生成 PoC → 执行验证 → 根据结果修正
- 最多重试 3 次

#### 3.3 自动化评估系统
- 用数据集测试 Agent 的 **Recall** (召回率)
- 评估 **PoC 成功率**
- **错题分析**：定位是 Analyst 没检出，还是 Builder 写错了

#### 3.4 专注访问控制漏洞
- 缺少 `onlyOwner` 修饰符
- 不正确的角色检查
- 权限升级漏洞

---

### 4. 演示 (3分钟)

#### 示例漏洞合约
```solidity
contract Vulnerable {
    address public owner;
    
    // ⚠️ 漏洞: 缺少 onlyOwner!
    function setFee(uint256 _fee) external {
        protocolFee = _fee;
    }
}
```

#### 运行命令
```bash
# 1. 创建示例数据集
python scripts/run_audit.py --create-sample

# 2. 加载数据集到向量库
python scripts/run_audit.py --load-dataset data/dataset/sample.json

# 3. 运行审计 (自动使用 RAG)
python scripts/run_audit.py --contract data/contracts/VulnerableAccessControl.sol

# 4. 评估 Agent 效果
python scripts/evaluate.py --dataset data/dataset/sample.json
```

#### 预期输出
1. 检索到相似漏洞案例 (RAG)
2. 识别 `setFee` 为高风险函数
3. 生成 PoC 测试代码
4. 验证漏洞存在
5. 输出审计报告

---

### 5. 当前进度 & 后续计划 (1分钟)

**已完成**：
- ✅ RAG 增强的四节点工作流
- ✅ 数据集加载模块 (DatasetLoader)
- ✅ 向量库集成 (ChromaDB)
- ✅ 评估模块 (Recall/PoC成功率)
- ✅ 错题分析功能

**后续计划**：
- 导入更多真实漏洞案例到数据集
- 对比 RAG vs 无 RAG 的效果差异
- 根据评估结果优化 Prompt
- 尝试用数据集微调开源 LLM

---

### 6. 技术挑战 & 解决方案 (1分钟)

| 挑战                      | 解决方案                |
| ------------------------- | ----------------------- |
| LLM 缺乏专业知识          | **RAG 检索相似案例**    |
| LLM 生成的 PoC 可能有错误 | 重试机制 + 错误反馈修正 |
| 如何判断漏洞真实存在      | Foundry 动态验证        |
| 如何评估系统效果          | **自动化评估模块**      |
| 数据格式统一              | Pydantic Schema 定义    |

---

## 演示命令

```bash
# 1. 创建示例数据集 (查看格式)
python scripts/run_audit.py --create-sample

# 2. 加载数据集到向量库
python scripts/run_audit.py --load-dataset data/dataset/sample.json

# 3. 运行审计 (使用 RAG)
python scripts/run_audit.py --contract data/contracts/VulnerableAccessControl.sol

# 4. 运行审计 (不使用 RAG，对比用)
python scripts/run_audit.py --contract data/contracts/VulnerableAccessControl.sol --no-rag

# 5. 评估 Agent 效果
python scripts/evaluate.py --dataset data/dataset/sample.json
```

---

## Q&A 预备问题

**Q: 为什么只关注访问控制漏洞？**
A: 访问控制是最常见且影响最大的漏洞类型，专注于此可以做深做精。

**Q: RAG 是什么？为什么要用？**
A: RAG (Retrieval-Augmented Generation) 是检索增强生成。通过检索数据集中的相似案例，给 LLM 提供专业上下文，弥补通用模型知识不足的问题。

**Q: 如何评估系统效果？**
A: 通过评估模块计算三个指标：
- **Recall**: 找出了多少漏洞
- **Detection Rate**: Analyst 节点检出率
- **PoC Success Rate**: PoC 执行成功率

**Q: 如何处理 LLM 幻觉问题？**
A: 通过 Foundry 动态执行验证，只有 PoC 真正执行成功才确认漏洞。

**Q: 数据集从哪来？**
A: 我们已经**手动构建**了漏洞数据集，本框架的作用是利用这些数据增强 Agent 的检测能力。

**Q: 后续如何优化？**
A: 
1. 根据评估结果的错题分析，改进 Prompt
2. 扩充数据集
3. 尝试用数据集微调开源 LLM

---

## 文件结构说明

```
agent/
├── src/
│   ├── core/          # 核心模块
│   │   ├── state.py   # 状态定义 (含 RAG 检索结果)
│   │   ├── graph.py   # 工作流 (RAG 增强)
│   │   └── config.py  # 配置
│   │
│   ├── nodes/         # Agent 节点
│   │   ├── analyst.py # 漏洞分析 (含 RAG 检索)
│   │   ├── builder.py # PoC 生成
│   │   └── verifier.py# 验证执行
│   │
│   ├── dataset/       # 数据集模块 (核心!)
│   │   ├── loader.py  # 数据集加载器
│   │   └── schemas.py # 数据格式
│   │
│   ├── rag/           # RAG 模块
│   │   └── vectorstore.py # 向量库
│   │
│   └── evaluation/    # 评估模块
│       └── evaluator.py # 效果评估
│
├── data/
│   ├── dataset/       # 漏洞数据集
│   └── contracts/     # 测试合约
│
└── scripts/
    ├── run_audit.py   # 主入口
    └── evaluate.py    # 评估脚本
```

---

## 数据集格式

```json
{
  "cases": [
    {
      "id": "case_001",
      "contract_source": "// Solidity 源码",
      "contract_name": "VulnerableVault",
      "vulnerable_function": "setProtocolFee",
      "vulnerability_type": "access_control",
      "severity": "high",
      "description": "缺少 onlyOwner 修饰符",
      "poc_code": "function test_exploit() { ... }",
      "fix_recommendation": "添加 onlyOwner"
    }
  ]
}
```
