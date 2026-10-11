---
name: web-search
description: "Use when searching current market facts, policy, sell-side consensus, or events with traceable source URLs."
---

# web-search

## Goal

通过联网搜索获取与研究问题直接相关、带权威 URL、发布时间与检索时间戳的外部 evidence artifact。

## Input

- **查询条件**：明确查询词与搜索类型（`stock|news|policy|general`）。
- **投研场景路由**：

| 投研阶段与目标 | 推荐 `--type` | 核心查询内容与产物定位 |
|---|---|---|
| **Step 1: 信息差** | `news` / `policy` | 市场主流公开认知与行业动态，用于对比财报底层客观事实 |
| **Step 3: 预期差** | `general` | 卖方券商一致预期（Consensus）、分析师盈利预测、目标价与评级 |
| **Step 4: 催化剂** | `policy` / `news` | 近期关键产业政策、监管文件原文、重大会议与事件窗口 |
| **Step 5: 行情补充** | `stock` | 公开市场行情、板块资金流向（作为辅助外部佐证） |

- **环境依赖**：已配置的联网搜索 API Key 与模型配置。

## Runtime boundary

Skill 目录视为只读。所有 artifacts 与日志必须写入任务工作区（如 `workspaces/<task_id>/`）。

- **CLI 范围**：只能执行已登记的 CLI；不得创建、修改或复制脚本，不得临时接入未登记能力。已登记能力不可用时返回 `unavailable`、`partial` 或 `failed`。
- **环境隔离**：CLI 自行加载 Skill 根目录 `.env`。

## Internal workflow

### 1. 查询词构造与执行（Construct & Search）
- **操作**：按场景选择 `--type`，构造包含“研究标的 + 报告期/年份 + 主题”的查询词，运行 `search_market.py`（传递 `--output` 至任务工作区）。
- **完成准则**：获得包含网页标题、正文摘要与原始 URL 的搜索结果。若 API 不可用或未返回有效内容，返回 `unavailable`。

### 2. 相关性过滤与证据审计（Filter & Audit）
- **操作**：过滤与研究标的不符、时效过期、无明确来源或重复的内容。
- **完成准则**：
  - **`evidence` 判定**：包含真实有效 URL 与发布时间的记录作为可审计 evidence。
  - **待验证线索**：无明确 URL 的内容仅能作为待验证线索，不得冒充确定性事实。

## Output

标准结果信封中登记外部 `evidence` artifact，关键字段包含：
- 来源 URL、标题、发布时间与检索时间戳。
- 关键内容摘录、置信度与适用章节（信息差外部佐证/预期差卖方基准/催化剂原文）。

## Failure handling

- **`unavailable`**：搜索 API 故障或未检索到任何带有效 URL 的结果。
- **`partial`**：结果数量不足、时效性弱、或缺乏权威来源 URL。
- **`failed`**：网络超时或搜索服务解析崩溃。
- **约束**：无权威来源 URL 的模型回答不能作为确定性 evidence；搜索摘要不能替代公告、财报或行情原始数据。

## CLI

参数和示例见 [CLI 参数参考](../../docs/CLI_REFERENCE.md#web-search)，也可运行 `search_market.py --help`。
