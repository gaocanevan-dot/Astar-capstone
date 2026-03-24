# Smart Contract Access Control Vulnerability Agent

一个面向智能合约访问控制 / 权限升级漏洞的轻量研究原型，当前流程为：

`静态分析 -> RAG 检索 -> AI 分析 -> PoC 生成 -> Foundry 验证`

当前项目重点不是做“纯检测”，而是尽量把漏洞分析和可利用性验证串成一个完整闭环。

## 当前能力

- 聚焦两类漏洞：
  - `access_control`
  - `privilege_escalation`
- 支持轻量静态分析预处理
- 支持 RAG 检索相似漏洞案例
- 支持 AI analyst 生成漏洞 hypothesis
- 支持 Builder 生成 Foundry PoC
- 支持 Verifier 运行 Foundry 测试确认漏洞
- 支持基础消融实验：
  - `full`
  - `no-static`
  - `no-rag`

## 当前项目结构

```text
agent/
├── src/
│   ├── core/
│   │   ├── config.py
│   │   ├── graph_light.py
│   │   └── state_schema.py
│   ├── nodes/
│   │   ├── preprocess_static.py
│   │   ├── analyst.py
│   │   ├── builder.py
│   │   └── verifier.py
│   ├── rag/
│   │   ├── embeddings.py
│   │   ├── retriever.py
│   │   └── vectorstore.py
│   ├── tools/
│   │   ├── static_adapter.py
│   │   ├── slither.py
│   │   ├── foundry.py
│   │   └── aderyn.py
│   ├── dataset/
│   └── evaluation/
├── scripts/
│   ├── run_audit.py
│   ├── demo_light.py
│   ├── run_ablation.py
│   ├── evaluate.py
│   ├── debug_analyst.py
│   └── debug_builder_verifier.py
├── data/
│   ├── contracts/
│   ├── dataset/
│   ├── evaluation/
│   └── vectorstore/
└── README.md
```

## 环境要求

- Python `3.10+`
- Windows PowerShell 或其他常见终端
- OpenAI API Key
- Foundry
- 可选：
  - Slither
  - Hugging Face 访问能力（本地 embedding 首次下载模型时需要）

## 安装方式

推荐直接使用当前项目目录下的 `venv`。

如果你要新建环境：

```powershell
python -m venv venv
venv\Scripts\python.exe -m pip install -U pip
venv\Scripts\python.exe -m pip install -e .
venv\Scripts\python.exe -m pip install sentence-transformers langchain-huggingface chromadb slither-analyzer
```

## 环境变量配置

复制模板：

```powershell
Copy-Item .env.example .env
```

至少需要配置：

- `OPENAI_API_KEY`
- `FOUNDRY_PATH`（如果 `forge` 不在 PATH 中）

`.env.example` 中当前相关字段如下：

```env
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_MODEL=gpt-4-turbo-preview
MAX_RETRIES=3
DATASET_PATH=data/dataset/vulnerabilities.json
VECTORSTORE_PATH=data/vectorstore
FOUNDRY_PATH=
USE_LOCAL_EMBEDDINGS=true
RAG_TOP_K=5
```

## Windows 运行说明

当前项目已经处理了几个常见 Windows 问题：

- `scripts/run_audit.py` 和 `scripts/evaluate.py` 会自动禁用 Pydantic 插件扫描，避免当前 `venv` 下的启动卡顿问题
- `scripts/run_audit.py` 会自动将 stdout/stderr 配置为 UTF-8，避免 Rich 输出导致编码报错
- Verifier 会按以下顺序寻找 `forge`：
  - `.env` 中的 `FOUNDRY_PATH`
  - 系统 `PATH`
  - 默认 Foundry 安装路径 `~/.foundry/bin/forge(.exe)`
- Slither 工具现在优先使用项目内的：
  - `venv\Scripts\slither.exe`

## 数据说明

### 1. 当前 RAG 数据集

默认使用：

- `data/dataset/vulnerabilities.json`

它用于：

- 加载到 Chroma 向量库
- 为 analyst 提供相似漏洞案例检索结果

### 2. 当前演示合约

默认演示合约：

- `data/contracts/VulnerableAccessControl.sol`

它是一个故意设计的访问控制漏洞样例，用于验证完整流程和演示效果。

## 快速开始

### 1. 加载 RAG 数据集

```powershell
venv\Scripts\python.exe scripts\run_audit.py --load-dataset data/dataset/vulnerabilities.json
```

### 2. 运行完整主流程

```powershell
venv\Scripts\python.exe scripts\run_audit.py --contract data/contracts/VulnerableAccessControl.sol --max-retries 2
```

### 3. 运行轻量 demo

这是当前最推荐的演示命令：

```powershell
venv\Scripts\python.exe scripts\demo_light.py
```

### 4. 在 demo 中附带消融实验结果

```powershell
venv\Scripts\python.exe scripts\demo_light.py --with-ablation
```

### 5. 单独运行轻量消融实验

```powershell
venv\Scripts\python.exe scripts\run_ablation.py --contract data/contracts/VulnerableAccessControl.sol --max-retries 2
```

## 主流程入口说明

### `scripts/run_audit.py`

完整审计入口，支持：

- 静态分析
- RAG
- AI 分析
- Foundry 验证

示例：

```powershell
venv\Scripts\python.exe scripts\run_audit.py --contract data/contracts/VulnerableAccessControl.sol --max-retries 2
```

支持的基础消融开关：

```powershell
venv\Scripts\python.exe scripts\run_audit.py --contract data/contracts/VulnerableAccessControl.sol --max-retries 2 --no-static
venv\Scripts\python.exe scripts\run_audit.py --contract data/contracts/VulnerableAccessControl.sol --max-retries 2 --no-rag
```

### `scripts/demo_light.py`

当前用于答辩 / 汇报的轻量 demo，展示：

- Step 1：静态分析结果
- Step 2：RAG 检索结果
- Step 3：最终漏洞结果
- Step 4：消融实验结果（仅在 `--with-ablation` 时显示）

### `scripts/run_ablation.py`

当前的轻量消融实验脚本，比较：

- `full`
- `no-static`
- `no-rag`

它目前是“单合约展示版”，更适合老师汇报，不是最终的数据集级实验脚本。

### `scripts/evaluate.py`

当前保留为评估入口，但后续还需要继续扩展成更正式的数据集批量实验脚本。

## 当前 demo 展示的含义

在 `demo_light.py` 中，最终输出通常包含：

- `status`
- `findings`
- `vulnerability_type`
- `target`
- `hypothesis`
- `confirmed`

其中：

- `vulnerability_type`
  - 表示当前识别出的主要漏洞类型
- `target`
  - 表示当前这轮验证流程优先选中的目标函数
  - 不是“唯一存在问题的函数”，而是当前主验证目标

## 当前项目做到哪一步

目前已经完成：

- 完整轻量闭环打通
- 静态分析接入主流程
- RAG 接入主流程
- AI 分析 + Foundry 验证串联完成
- 轻量 demo 可直接运行
- 基础消融实验脚本已完成

目前还需要继续完善：

- 面向数据集的正式消融实验
- 真实合约的大规模批量测试
- 与 `Slither` / `Aderyn` 的正式基线对比
- 更规范的实验输出与论文级评估指标

## 当前推荐的老师演示命令

如果你要快速展示当前成果，推荐直接运行：

```powershell
venv\Scripts\python.exe scripts\demo_light.py --with-ablation
```

这条命令会一起展示：

- 静态分析结果
- RAG 检索结果
- 最终漏洞确认结果
- 消融实验对比表

## 常见问题

### 1. 为什么轻量 demo 和主流程输出不完全一样？

因为：

- `run_audit.py` 更偏向完整结果展示
- `demo_light.py` 更偏向老师汇报时的简洁展示

### 2. 当前消融实验能证明模块贡献率吗？

目前只能初步说明：

- 系统框架已跑通
- 模块开关可独立控制

如果要正式证明 static analysis / RAG 的贡献率，还需要在更多真实合约上做批量实验。

### 3. 当前静态分析工具到底是什么？

当前采用：

- 轻量源码静态分析为主
- `Slither` 作为优先调用的外部静态分析工具增强

## License

MIT
