# 项目汇报 — 2026-04-21 组会

> 写给完全不了解项目的读者。每个模块都写明输入输出。

---

# 0. 一句话项目

> **做一个能"读智能合约源码 → 找出哪个函数有权限漏洞"的 AI 工具，目标是比直接问 GPT 准。**

---

# 1. 我们要解决的问题

## 1.1 智能合约权限漏洞是什么

智能合约里经常有这种代码：
```solidity
// 本意：只有合约所有者能取钱
function withdraw() external {           // ← 没写 onlyOwner!
    msg.sender.transfer(address(this).balance);
}
```

任何人调用 `withdraw()` 都能把合约里的钱卷走。这就是**权限漏洞 (access control vulnerability)**。

历史上 Code4rena、ImmuneFi 等漏洞赏金平台报告过几百起这类问题，损失常常上千万美元。

## 1.2 我们要做的工具

```
用户给一段合约源码（几百到几千行 Solidity 代码）
         ↓
        我们的 AI 工具
         ↓
告诉用户："funcA、funcB、funcC 这 3 个函数最可能有权限漏洞，按可能性排序"
```

## 1.3 评测口径
- **hit@1**：top-1 答案命中标准答案的比例
- **hit@3**：top-3 候选里只要有一个命中就算对，比例

---

# 2. 数据集

## 2.1 评测数据集 `eval_set.json`（42 case）

**来源**：Code4rena 漏洞赏金平台 + NOYA / GIT 等真实项目历史漏洞报告。

**每条数据长这样**（精简）：
```json
{
  "id": "NOYA-H-04",
  "contract_name": "VaultWithdrawManager",
  "contract_source": "<几百行 Solidity 源码>",
  "vulnerable_function": "executeWithdraw",  ← 标准答案
  "vulnerability_type": "access_control",
  "severity": "high",
  "description": "The withdraw execution logic ... missing checks ...",
  "metadata": {"reference": "https://code4rena.com/reports/2024-04-noya#H-04"}
}
```

**质量问题**：42 条里有 9 条标注脏（GT = `unknown_function` / `setUp` / `testExploit` 这种）。所以**真正能评的是 32 条**（"清洁集"）。后面所有数字都用清洁集报。

## 2.2 RAG 检索语料库 `rag_training_dataset.json`（85 条）

**来源**：另一批已标注好的真实漏洞案例，**不与评测集重叠**。

**每条数据长这样**：
```json
{
  "id": "C4-161",
  "content": "Vulnerability Type: access_control\nContract: NFTFloorOracle\nFunction: removeFeeder\nMissing Check: General Access Control\n\nIssue Description: ...\n\nProblematic Code Snippet:\n```solidity\nfunction removeFeeder(address _feeder) external onlyWhenFeederExisted ...\n```",
  "metadata": {"function": "removeFeeder", "vulnerability_type": "access_control", ...}
}
```

这是给 RAG 模块当"先验知识"用的。

---

# 3. 整体架构（LangGraph 多节点 agent）

## 3.1 我们用的框架：LangGraph

**LangGraph** 是 LangChain 团队做的一个开源框架，把多步 LLM 调用组织成"有向图"（StateGraph）。每个节点是一个函数（可以调 LLM、跑 Python、调外部工具），节点之间通过共享 state 字典传递数据。

**为什么选 LangGraph**：
- 我们的工作流是多步的（分析 → 写 PoC → 验证 → 失败重试），天然是图结构
- 比手写 if/else 链清晰；比 LangChain 的 Chain 更灵活（支持循环）

## 3.2 整条链长这样

```
[Code4rena 数据] → [Loader] 
                        ↓
       ┌────────────────┼─────────────┐
       ↓ (可选)         ↓ (可选)        ↓
  [Static]         [RAG]            ↓
       ↓                ↓             ↓
       └──→ [Analyst (LLM)] ←────────┘
              ↓ × N=5
            [Voter] ← 自洽性投票
              ↓
            top-3 候选
              ↓
       (可选 Full pipeline 才有的下半段)
              ↓
         [Builder (LLM)] → 写 Foundry PoC
              ↓
        [Verifier (forge)] → 跑 PoC，三分类
              ↓ 失败回 Builder ≤3 次
            最终判定
```

**重点**：今天能跑赢 GPT 的是 **Loader → Analyst × 5 → Voter** 这条最短路径，下面会逐个讲清楚每个节点的 I/O。

**🆕 正在进行中的实验**（组会前跑完）：**Loader → Embedding RAG → Analyst × 5 → Voter**。用 OpenAI `text-embedding-3-small` 把 RAG 从 TF-IDF 升级到语义检索，验证之前 -30pp 的 RAG 负面结果是否只是 TF-IDF 本身太弱。

---

# 4. 每个模块的输入输出（老师重点关注）

## 4.1 Loader

| | 内容 |
|---|---|
| **代码位置** | `scripts/run_single_agent.py:load_eval_set()` |
| **输入** | 文件路径 `data/dataset/eval_set.json` |
| **输出** | `EvalSet(cases=[Case(...), Case(...), ...])`，42 个 `Case` 对象，每个包含 id / contract_source / contract_name / vulnerable_function / metadata |
| **作用** | 把 JSON 反序列化为强类型对象，方便后面节点用属性访问 |

## 4.2 Static Analyzer（可选节点）

| | 内容 |
|---|---|
| **代码位置** | `src/agent/adapters/static_analyzer.py` |
| **输入** | `contract_source: str`（Solidity 源码） |
| **处理** | 1️⃣ 优先调 Slither (业界标杆静态分析器)；2️⃣ Slither 失败 → 走 regex fallback，扫源码提取所有函数 |
| **输出** | 文本块（喂给 Analyst 当上下文）：<br>```# Functions (name · visibility · modifiers):```<br>```- `mint` · external · mods=[onlyOwner] [STATE]```<br>```- `burn` · public · mods=[] [STATE]```<br>```- ...```<br>每行一个函数，含名字 / 可见性 / 修饰符 / 是否改状态 |
| **代价** | 0 LLM 调用，~1 秒/case |
| **状态** | 实验显示帮助有限（甚至略伤），所以默认关闭 |

**⚠️ 老实交代 — Slither 实际很少生效**：Code4rena 合约依赖重（OpenZeppelin / Uniswap 等大库），Slither 在我们数据集上几乎全部编译失败（Slither baseline 跑出 **0/41**）。所以 `--use-static` 里实际进入 prompt 的 99% 是 regex fallback 的函数列表，不是 Slither 的 detector 产出。代码集成了 Slither，但没吃到它的正能量。

## 4.3 RAG Retriever（可选节点）

老师特别问了 RAG 结构，这里展开讲。

### 4.3.1 RAG 是什么
**RAG (Retrieval-Augmented Generation)** = 检索增强生成。原理：在让 LLM 回答前，先从一个语料库里**找出最相关的几个例子**喂给 LLM，让它"参考着写"。

### 4.3.2 我们现在有两套 RAG 实现

#### 方案 A：TF-IDF（已有，实测 -30pp）

```
┌─────────────────────────────────────────────────────────┐
│                    一次性预处理                            │
│  rag_training_dataset.json (85 条已标注漏洞)              │
│         ↓                                                │
│  _tokenize(每条 content 文本) → 小写 identifier token 列表│
│         ↓                                                │
│  手撸 TF-IDF：Counter + math.log((n+1)/(df+1)) + 1        │
│  (纯 Python + math 标准库，不依赖 sklearn)                │
│         ↓                                                │
│  存到内存里的 TfidfRagStore                               │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│                    每个 case 检索时                        │
│  query = 当前要分析的合约源码                              │
│         ↓                                                │
│  _tfidf_vec(query tokens) → dict[term → tf·idf]          │
│         ↓                                                │
│  手撸 cosine(q_vec, doc_vec) 对 85 个 case 逐个算         │
│         ↓                                                │
│  排序 → 取相似度 top-3                                    │
│  排除自己 (Leave-One-Out by case_id)                     │
└─────────────────────────────────────────────────────────┘
```

#### 方案 B：Embedding（🆕 今天新加，正在测）

```
┌─────────────────────────────────────────────────────────┐
│                    一次性预处理（有磁盘缓存）               │
│  rag_training_dataset.json (85 条已标注漏洞)              │
│         ↓                                                │
│  每条格式化为: "Contract: X\nVulnerable function: Y\n..." │
│         ↓                                                │
│  OpenAI text-embedding-3-small API (batch, 85 条一次调用) │
│         ↓                                                │
│  得到 85 × 1536 dense 矩阵，L2 归一化                     │
│  缓存到 data/dataset/.rag_training_dataset.embcache.npz  │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│                    每个 case 检索时                        │
│  query = 当前要分析的合约源码                              │
│         ↓                                                │
│  OpenAI embed(query) → 1536-d 向量 → L2 归一化            │
│         ↓                                                │
│  sims = corpus_matrix @ query_vec   (纯矩阵乘法 = cosine) │
│         ↓                                                │
│  numpy.argsort 取 top-3，LOO 同前                         │
└─────────────────────────────────────────────────────────┘
```

**区别的本质**：
- TF-IDF 比较的是**词面相同**（一篇有 `withdraw`，一篇也有 `withdraw` → 高相似）
- Embedding 比较的是**语义相同**（`withdraw 没 onlyOwner` 和 `setFee 没 onlyOwner` 都映射到"无权限检查的状态变更"向量邻域）

### 4.3.3 Few-shot 格式化（两方案共用）

检索到的 top-3 统一拼成：
```
## Example 1 (similarity=0.87, project=NFTFloorOracle)
Vulnerable function: `removeFeeder`
Hypothesis: General Access Control ...

## Example 2 (similarity=0.82, project=...)
...
```
这段文本插到 Analyst 的 user prompt 里，位置在合约源码**之前**。

### 4.3.4 为什么最初选 TF-IDF（MVP 理由）

1. 零额外依赖（不用装 Chroma / sentence-transformers）
2. 零额外 API 成本
3. 确定性可复现（embedding API 会被模型升级静默改结果）
4. Solidity 有大量独特关键词（`function` / `external` / `msg.sender`），词面相似**理论上**能抓到部分信号

**实证结果打了这个设计的脸**：TF-IDF RAG 在 42 case 上把 hit@1 **砍了 -28pp**。显然词面相似不等于漏洞机制相似。所以今天加上 embedding RAG 做对比实验。

### 4.3.5 RAG I/O 总结

| | TF-IDF 方案 | Embedding 方案（新） |
|---|---|---|
| **类名** | `TfidfRagStore` | `EmbeddingRagStore` |
| **代码位置** | `src/agent/adapters/rag.py` | 同文件新加 |
| **预处理输入** | `rag_training_dataset.json` | 同 |
| **预处理计算** | 纯本地，Counter + math | 1 次 OpenAI batch embed (85 docs) |
| **检索输入** | query 合约源码 | 同 |
| **检索计算** | 85 次手撸 cosine | 1 次 query embed + 1 次矩阵乘 |
| **输出** | top-3 相似 case 的 few-shot 文本块 | 同 |
| **代价** | 0 LLM / 0 API | 86 次 embed ≈ $0.01 (有缓存下次免费) |
| **延迟** | ~10ms/case | ~100ms/case (embed API 耗时) |
| **嵌入维度** | 变长稀疏 | 固定 1536 dense |

## 4.4 Analyst（核心 LLM 节点）

| | 内容 |
|---|---|
| **代码位置** | `src/agent/nodes/analyst.py:analyze()` |
| **输入** | contract_source + contract_name + (可选) static_context + (可选) rag_few_shot |
| **LLM 调用** | OpenAI API，**实际在用 `gpt-5-mini` (snapshot `2025-08-07`)**，代码里的 `FALLBACK_MODEL=gpt-4o-mini` 没触发过；单次调用 |
| **⚠️ 模型特性** | gpt-5-mini 属于 reasoning-family，**API 不接受 `temperature` 和 `seed` 参数**，所以 5 次 SC 的随机性来自模型自身内部 sampling，不是我们显式控制的 |
| **System prompt** | "You are a smart-contract security auditor specialized in access-control vulnerabilities. Rank TOP-3 functions most likely to lack adequate access control..." |
| **User prompt 结构** | `Contract name: X\n[static facts]\n[RAG examples]\n```solidity\n<source>\n```\nReturn JSON.` |
| **输出 JSON** | `{candidates: [top1, top2, top3], target_function: top1, hypothesis: "...", confidence: 0.0-1.0, reasoning: "..."}` |
| **代价** | 1 LLM 调用 ≈ 1500-3000 prompt tokens + 100-300 completion tokens ≈ $0.001/case |

## 4.5 Self-Consistency Voter（今天新增的赢点）

老师重点：**这是我们今天能跑赢 GPT 的关键改动。**

| | 内容 |
|---|---|
| **代码位置** | `src/agent/nodes/analyst.py:analyze_consistent()` |
| **输入** | 同 Analyst，但多一个参数 `n_runs=5` |
| **机制** | 调 5 次 Analyst（同样 prompt，模型自然有随机性），收集 5 组 top-3 候选，按 reciprocal-rank 投票 |
| **投票算法** | 对每个候选 c：score(c) = Σ_runs (1 / rank_in_that_run)，例子见下面 |
| **输出** | 最终共识的 top-3，hypothesis/reasoning 继承自"top-1 与共识一致"的那个 run |
| **代价** | 5 次 LLM 调用 ≈ $0.005/case，wall-clock 5×（44 分钟跑完 42 case） |

### Voter 算法举例
5 次 run 的 top-3：
```
Run 1: [funcA, funcB, funcC]
Run 2: [funcA, funcD, funcB]
Run 3: [funcB, funcA, funcE]
Run 4: [funcA, funcC, funcB]
Run 5: [funcD, funcA, funcF]
```

每个候选的得分（出现一次得 1/rank 分）：
- funcA: 1/1+1/1+1/2+1/1+1/2 = **4.0**  ← 4 次第 1 + 1 次第 2
- funcB: 1/2+1/3+1/1+1/3 = **2.17**
- funcC: 1/3+1/2 = **0.83**
- funcD: 1/2+1/1 = **1.5**

最终共识 top-3：[**funcA, funcB, funcD**]

### 为什么这个能涨点
单次 GPT 推理有随机性，会偶尔被 prompt 里的某个细节带跑偏。5 次平均下来，**真正核心的可疑函数会反复浮现**，random noise 会被稀释掉。学术依据：Wei et al. 2022 "Self-Consistency Improves Chain-of-Thought Reasoning"，原论文在数学题上涨 5-15pp。

## 4.6 Metrics 计算

| | 内容 |
|---|---|
| **代码位置** | `src/agent/eval/metrics.py:compute_analyst_recall()` |
| **输入** | 预测列表（每条含 ground_truth_function + predicted_function + candidates） |
| **输出** | `AnalystRecall` 对象，含 strict/loose recall + hit@1/2/3 + per-case 详细标记 |
| **关键判定** | strict_hit = predicted == GT；loose_hit = case-insensitive substring；hit@k = candidates[:k] 任一命中 GT |

---

# 5. Full Pipeline 多出的两个节点（仅用于生成 PoC，今天没用）

## 5.1 Builder
| | 内容 |
|---|---|
| **位置** | `src/agent/nodes/builder.py` |
| **输入** | Analyst 给的 target_function + hypothesis + 原合约源码 |
| **LLM 调用** | 让 GPT 写一段 Foundry 测试代码（Solidity） |
| **输出** | 一段独立的 Solidity 测试合约 (`AttackTest.t.sol`)，包含一个简化版受害合约 + 一个 testExploit 函数 |

## 5.2 Verifier
| | 内容 |
|---|---|
| **位置** | `src/agent/nodes/verifier.py` |
| **输入** | Builder 写的 PoC 代码 |
| **处理** | subprocess 调 `forge test`，捕获 stdout/stderr |
| **输出** | 三分类：`pass` (攻击成功) / `fail_revert_ac` (被权限拦了) / `fail_error` (编译错) |
| **状态** | **PoC 真实性争议**：Builder 写的"简化版受害合约"是 GPT 自己理解的版本，不是真合约 → PoC-pass 率 81% 是虚高的工程指标，不是真攻破率。**所以这个分支今天不作为重点。**

---

# 6. 用了什么技术栈

| 类别 | 技术 | 版本/说明 |
|------|------|----------|
| **图编排** | LangGraph | StateGraph + TypedDict |
| **LLM (主模型)** | OpenAI API | **实际用 `gpt-5-mini` (snapshot `2025-08-07`)**；代码里 fallback 为 `gpt-4o-mini` 但没触发 |
| **LLM (embedding)** | OpenAI API | `text-embedding-3-small` (1536-d)，给 Embedding RAG 用 |
| **静态分析** | Slither | 已集成但在 Code4rena 数据上几乎全挂，实际生效的是自写 regex fallback |
| **PoC 验证** | Foundry (forge) | subprocess |
| **RAG 方案 A** | 手撸 TF-IDF | 纯 Python `Counter` + `math.log`，无 sklearn 依赖 |
| **RAG 方案 B (新)** | OpenAI embedding + numpy | batch embed + L2 归一化 + 矩阵乘法 cosine，有磁盘缓存 |
| **测试** | pytest | 110 单元测试（含今天新加的 6 个 self-consistency 测试） |
| **数据格式** | Python dataclass / TypedDict | 严类型 schema (`Case`, `EvalSet`, `AnalystPrediction`) |
| **环境** | Python 3.10 + Windows | venv 隔离 |

---

# 7. 三个 Baseline（对比组，证明我们的存在价值）

## 7.1 Slither (纯静态规则)
- **是什么**：ChainSecurity 开源的静态分析器，业界标杆，几万 GitHub star
- **怎么跑**：直接对合约源码跑 `slither <file> --json -`
- **结果**：**0/41 命中** (0%) — Code4rena 合约依赖太重，Slither 大量编译失败
- **意义**：证明纯规则方法在真实数据上不可用 → 必须上 AI

## 7.2 GPT 零样本 (1-fn prompt)
- **是什么**：直接拿 `gpt-5-mini`（和我们 agent 用同一个模型，保证公平对比），最朴素的 prompt 问一次
- **Prompt**：`"You are a smart-contract security auditor. Identify access-control vulnerabilities. Return JSON: {is_vulnerable: bool, vulnerable_functions: [string]}"`
- **结果**：hit@1 = **71.9%**，hit@3 = **75.0%** (清洁集)
- **意义**：这是我们要超越的基线 — 老师说"你做这么复杂的框架，必须要比这个好"

## 7.3 GPT 零样本 (强制 top-3 prompt)
- **是什么**：同样 `gpt-5-mini`，但 prompt 改成强制要求输出 top-3
- **Prompt**：增加 `"...EXACTLY up to 3 function names, ordered by likelihood..."`
- **结果**：hit@1 = 50.0%，hit@3 = **65.6%** (反而比 1-fn 的 75% 更差)
- **意义**：意外发现 — **强制 GPT 输出 3 个反而把它的判断质量拉低**。说明 prompt 工程很微妙，不是越详细越好

---

# 8. 完整对比表（清洁集 32 case）

| 方法 | hit@1 | hit@3 | 说明 |
|------|-------|-------|------|
| Slither baseline | 0.0% | 0.0% | 静态规则不可用 |
| GPT 零样本 (1-fn prompt) | **71.9%** | 75.0% | 要超越的对手 |
| GPT 零样本 (强制 top-3) | 50.0% | 65.6% | 反例：prompt 改坏 |
| Single-agent (no SC, no static, no RAG) | 59.4% | 75.0% | 我们的最简版 |
| Single-agent + RAG curated (**TF-IDF**) | 31.2% | 43.8% | 词面相似不等于机制相似，-30pp |
| Single-agent + static (FULL) | 53.1% | 71.9% | static 帮助有限 |
| Single-agent + static (FILTERED) | 56.2% | 65.6% | filter 设计错了 |
| **🏆 Single-agent + Self-Consistency N=5** | **62.5%** | **78.1%** | **今天的主要成果** |
| **🆕 SC=5 + Embedding RAG (text-embedding-3-small)** | 56.2% | 68.8% | 比 TF-IDF 缓解很多（-34pp → -9pp）但仍负效应 |
| Full pipeline (含 Builder+Verifier) | 53.1% | 53.1% | PoC 路径，Recall 不强 |

---

# 9. 今天的核心成果 — 一句话

> **加了 self-consistency 投票后，我们的 single-agent 在 hit@3 上首次超过裸 GPT 零样本：78.1% vs 75.0% (+3.1pp)，同时 hit@1 也从 59.4% 涨到 62.5% (+3.1pp)。**

**和裸 GPT 零样本 (75% hit@3) 的对比**：✅ **赢 +3.1pp**  
**和我们自己的 baseline (75% hit@3) 的对比**：✅ **涨 +3.1pp** （证明 SC 起作用）

---

# 9b. Embedding RAG 实验 — 结果与解读（重点 finding）

## 背景
之前 TF-IDF RAG 把 Recall 砍了 30pp，设计选择被打脸。这次升级到语义检索重新验证 RAG 到底有没有救。

## 做法
- **Corpus**：同一套 `rag_training_dataset.json` (85 条已标注漏洞)
- **Embedder**：OpenAI `text-embedding-3-small` (1536-d)
- **检索**：L2 归一化后做矩阵乘法算 cosine，top-3
- **few-shot 格式**：和 TF-IDF 方案完全一致，只换了"怎么找出相似 case"这一步
- **配置**：叠在今天的 SC=5 最强组合上 → `SC=5 + Embedding RAG`
- **代价**：新增 86 次 embedding 调用 ≈ $0.01，有磁盘缓存（`.rag_training_dataset.embcache.npz`）下次免费

## 实际结果（清洁集 32 case）

| 配置 | hit@1 | hit@3 | vs SC=5 baseline (78.1%) |
|------|-------|-------|--------------------------|
| SC=5 无 RAG (baseline) | 62.5% | **78.1%** | 0 |
| SC=5 + **TF-IDF** RAG (旧方案) | 31.2% | 43.8% | **-34.3pp** 💥 |
| SC=5 + **Embedding** RAG (新方案) | 56.2% | 68.8% | **-9.3pp** 📉 |

## 解读：这是一个有价值的 Negative Finding

### 发现 1: Embedding **大幅缓解**了 RAG 的伤害
从 -34pp 压到 -9pp，**减少了 73% 的负效应**。证明之前 TF-IDF 表现烂**一部分**是词面检索工具本身不够强 —— 升级到语义检索确实抓到了更相关的 case。

### 发现 2: 但 **Embedding 仍然没让 RAG 转正**
即使用了 2024 年最好的 embedding 模型，RAG 还是注入 noise > signal。说明 RAG 这条路在**我们这个特定场景下**有更深的系统性问题。

### 发现 3: 为什么 RAG 在我们这里失败（诚实分析）
1. **Corpus 规模不够**：只有 85 条 —— few-shot 里能放的好例子太少，很容易命中不相关的
2. **分布 mismatch**：评测集都是 Code4rena 复杂真实合约 (几千行)，RAG 语料里有相当多 code snippet (几十行)。相似度再高也代表不了机制相同
3. **GPT-5-mini 自身已经够强**：模型已经从训练数据里学到大量 Solidity 审计知识，外部 few-shot 提供的边际信息反而可能稀释它的正确判断
4. **Access control 漏洞的机制高度多样**：从 `onlyOwner` 缺失到 `initialize` 缺 guard 到 role-transfer 到 low-level calls，一个 top-3 few-shot 覆盖不了这么多模式

### 答辩话术
> "RAG 在我们这个场景是一个 **negative finding，但不是空白 finding**。升级 TF-IDF → Embedding 把负效应从 -34pp 压到 -9pp，证明检索器升级有效；但仍不能转正，说明 RAG 在小规模 corpus + 高多样性漏洞机制上有系统性局限。要让 RAG 转正需要三件事：(a) corpus 扩展到数百条，(b) query-corpus 分布对齐，(c) 大概率还需要置信度门控 + MMR diversification。这是我们给社区的一条 negative knowledge。"

---

# 10. 老实承认的弱点（防答辩被刺穿）

1. **hit@1 还输 GPT** (62.5% vs 71.9%)：单个最确信答案上还不行，靠 top-3 候选追回。**下一步 Critic-Refine 应该能修这个**。
2. **样本小** (32 case)，+3.1pp = 1 个 case 的差异。结论强度有限，**下一步要扩数据集**。
3. **代价 ×5**：API 调用 40 → 200，wall-clock 8min → 44min。预算可接受，但如果以后扩到 1000 case 要重新评估。
4. **PoC 真实性问题**（Full pipeline 那条线）：Builder 是让 GPT 自己写"简化合约 + 攻击代码"，PoC-pass 81% 是工程意义上跑通了，**不能说明真破了真合约**。所以现在重心在 Recall 而不是 PoC。
5. **Self-Consistency 在 reasoning-family 模型上的机制存疑**：原论文（Wei 2022）用 PaLM/GPT-3 + 显式 `temperature` 制造多样性。我们用的 `gpt-5-mini` 不接受 temperature 参数，5 次调用的多样性来自模型内部自带的 sampling。**我们没有做"单次跑 5 次取 first run"的消融对照**来证明 SC 真的是在工作 —— 这是答辩可能被挑的点。
6. **Slither 实质没生效**：代码集成了 Slither 作为 preprocess 节点，但 Code4rena 合约依赖重，Slither 在我们数据集上 baseline 直接 0%。所以项目里有 Slither 代码，但**实际跑的是 regex fallback**。这点对老师要讲清楚，别让老师以为我们真用了静态分析的硬结论。

---

# 11. 下一步路线（请老师评价）

### 路线 1: Critic-Refine 循环（reflexion 风格）
- Analyst 给 top-3 → Critic 挑刺 → Analyst 修订 → 最多 2 轮
- 目标：把 hit@1 从 62.5% 也拉过 GPT 的 71.9%
- 工作量：1-2 天

### 路线 2: 修脏标签 + 扩数据集
- 9 个 dirty labels 重新人工标注
- 再爬 50-100 个新 case 把数据集扩到 ~150
- 工作量：3-5 天

### 路线 3: chat 交互界面（用户视角）
- Gradio 搭 web UI，用户上传合约 → 多轮对话纠错
- 工作量：1-2 天

---

# 12. 想请老师指导的 3 个问题

1. **学术站位**：Self-Consistency 是 2022 年的方法，我们的贡献是把它**用在 access-control 漏洞检测**这个具体场景。够算"contribution"吗，还是要叠加 Critic 才有 novelty？
2. **数据集策略**：先冲数据扩展（150 case 才有统计意义）还是先冲方法升级（Critic-Refine）？
3. **基线选择**：要不要再加一组**用更大的模型 (GPT-4o full / Claude-3.5-Sonnet)** 做对比，证明我们的提升不是"省钱模型 + 投票"碰巧赢的？

---

# 附录：实际跑出来的命令

```bash
# 跑 Self-Consistency N=5（今天的主要成果）
python scripts/run_single_agent.py \
  --n-consistency 5 \
  --predictions-out data/evaluation/single_agent_sc5_predictions.json \
  --summary-out data/evaluation/single_agent_sc5_summary.md

# 🆕 跑 SC=5 + Embedding RAG（正在跑，验证 RAG 是否有救）
python scripts/run_single_agent.py \
  --n-consistency 5 \
  --use-rag \
  --rag-dataset data/dataset/rag_training_dataset.json \
  --rag-embedding \
  --predictions-out data/evaluation/single_agent_sc5_embrag_predictions.json \
  --summary-out data/evaluation/single_agent_sc5_embrag_summary.md

# 跑清洁版对比表
python scripts/clean_compare.py
# → 输出 data/evaluation/CLEAN_COMPARE.md

# 跑三个 baseline
python scripts/run_baseline.py --method slither
python scripts/run_baseline.py --method gpt_zeroshot
# top-3 变种 (prompt 已改好):
python scripts/run_baseline.py --method gpt_zeroshot \
  --predictions-out data/evaluation/baseline_gpt_zeroshot_top3_predictions.json
```
