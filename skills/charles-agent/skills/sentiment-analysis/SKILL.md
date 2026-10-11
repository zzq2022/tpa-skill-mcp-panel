---
name: sentiment-analysis
description: "Use when analyzing news sentiment, market signals, or event catalysts for a named security."
---

# sentiment-analysis

## Goal

生成相关新闻集、逐条与聚合情绪分布、催化剂事件类型及时间窗口的 analysis artifacts。

## Input

- 本地规范新闻 JSON（包含 `title`、`content`、`publish_time`、`url`）；或用于抓取的股票代码、关键词与回溯天数。
- 明确的研究对象与事件时间范围。
- 情绪评分与事件检测所需的模型配置。
- 政策或行业宏观背景由根 Skill 调度 `web-search` 提供，不直接作为新闻数据源。

## Runtime boundary

Skill 目录视为只读。所有 artifacts 与日志必须写入任务工作区（如 `workspaces/<task_id>/`）。

- **CLI 范围**：只能执行已登记的 CLI；不得创建、修改或复制脚本，不得临时接入未登记能力。已登记能力不可用时返回 `unavailable`、`partial` 或 `failed`。
- **环境隔离**：CLI 自行加载 Skill 根目录 `.env`。

## Internal workflow

### 1. 抓取与清洗（Fetch & Clean）
- **操作**：无外部新闻输入时，运行 `news_fetcher.py` 抓取并按研究对象与时间范围过滤去重。
- **完成准则**：生成包含有效新闻条目的 `news` data artifact。若抓取完全失败且无历史输入，返回 `unavailable` 或 `failed`。

### 2. 并行分析（Parallel Analysis）
读取同一 `news` 数据产物，可并行或独立执行：
- **情绪评分（Sentiment Scoring）**：
  - **操作**：运行 `sentiment_scorer.py` 对每条新闻打分并统计聚合分布。
  - **完成准则**：生成包含单条分值、加权情绪指数与正/负/中性分布的 `sentiment` analysis artifact。客观保留原始中性分布，无需强行拟合多空方向。
- **事件检测（Event Detection）**：
  - **操作**：运行 `event_detector.py` 提取催化剂事件类别、关键词匹配与时间窗口。
  - **完成准则**：生成包含事件类型、关键摘录与置信度的 `events` analysis artifact。

### 3. 汇总与交付（Synthesis）
- **操作**：汇总有效样本数、失败数、情绪分布、事件类型与时间窗口。
- **完成准则**：将 `news`、`sentiment` 和 `events` artifacts 交回根 Skill，供催化剂与情绪分析步骤消费。

## Output

标准结果信封中登记生成的 artifacts：
- **`news` (data)**：清洗去重后的新闻列表及来源。
- **`sentiment` (analysis)**：逐条评分、有效样本量及聚合情绪倾向。
- **`events` (analysis)**：检测到的事件分类、关键时间窗口与置信度。

## Failure handling

- **`unavailable`**：缺少股票代码且无已有新闻输入，或抓取源完全不可用。
- **`partial`**：新闻样本量偏少、部分文本评分失败、或事件检测置信度较低。
- **`failed`**：模型调用异常或脚本执行崩溃。
- **分析准则**：事件信号作为待验证催化剂证据，不直接推断投资结论；全中性信号如实记录。

## CLI

参数和示例见 [CLI 参数参考](../../docs/CLI_REFERENCE.md#sentiment-analysis)，也可运行脚本的 `--help`。
