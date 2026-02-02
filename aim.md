根据图片（Source 14）的内容，这是关于 **Project 2** 的项目说明，主要涉及基于 Agent 的 DeFi 应用攻击向量生成。以下是整理好的 Markdown 格式文档：

***

# Project 2: Agent-based Attacking Vector Generation for DeFi Apps

### Motivation (动机)
*   **依赖人工且耗时**：识别 DeFi 智能合约中的关键漏洞通常需要人类专家的专业知识，且过程非常耗时。
*   **提示工程挑战**：像 ChatGPT 这样的 LLM（大语言模型）的最新进展为这项任务提供了有希望的途径，但如何设计高效的提示词（Prompts）仍然是一个挑战。
*   **主动防御需求**：需要一个更加动态和自主的漏洞发现系统，能够主动识别并测试 DeFi 协议中的弱点。

### Objective (目标)
开发一个多智能体系统（Multi-agent system），其中核心 **Agent** 利用 LLM 和工具来自主生成、模拟和优化针对 DeFi 应用程序的攻击向量。主要目标包括：

*   **a). Analyze DeFi Apps (分析 DeFi 应用)**：摄取并理解代码、文档和链上数据，以识别潜在的漏洞。
*   **b). Synthesize Attack Vectors (合成攻击向量)**：生成攻击，将高层概念（例如：闪电贷 flash loan）转化为交易序列（tx sequences）。
*   **c). Simulate and Evaluate Attacks (模拟与评估攻击)**：在本地的分叉环境（local, forked environment）中执行并评估。
*   **d). Iterate and Refine (迭代与优化)**：利用反馈信息来修正和完善攻击方式。

### Benefit (收益)
1.  有机会熟悉流行的 DeFi Dapps 和智能合约攻击手法。
2.  有机会了解 LLMs（大语言模型）及提示词设计（Prompt Design）。
3.  熟悉流行的智能体系统（Agent Systems）。

### Requirement (要求)
1.  **Understanding of the philosophy of blockchain**：理解区块链的底层哲学/原理。
2.  **Familiar with smart contract**：熟悉智能合约，特别是 **Solidity** 语言。