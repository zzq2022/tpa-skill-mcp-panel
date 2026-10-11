# 人机决策收集规范 (Checkpoint Rules)

本文档定义 Phase 3 (Plan Checkpoint / Checkpoint 1) 的**硬阻断人机确认交互协议与决策标准**。

---

## 1. 核心定位与阻断协议 (Hard Gate Protocol)

- **状态机状态**：`HALT_AND_WAIT`（硬阻断挂起）。
- **交互铁律**：主 Agent 必须在此停下，通过结构化决策卡片向用户独立确认 5 项核心决策。未取得用户确认前，**严禁进入 Phase 4 开始执行取数与分析**。
- **推荐原则 (Recommend with Rationale)**：明确给出推荐项及前置理由（格式：`(Recommended) ...`），赋予用户充分的选择与修改权。

---

## 2. 必须独立确认的 5 项决策矩阵

| # | 决策项 (Dimension) | 推荐依据与标准示例 | 常见备选项 (Alternatives) |
|---|---|---|---|
| **1** | **研究标的与证券代码** | 给出带市场后缀的标准代码（如 `中国电信 601728.SH / 0728.HK`） | A 股 / 港股 / 美股代码切换、自定义标的 |
| **2** | **研究时间跨度 (Period Scope)** | 推荐 `近3年完整数据 (2022-2024FY) + 2025年最新财报期` | 近 5 年长周期复盘 / 仅聚焦最新两期 / 单季度追踪 |
| **3** | **同业对标池 (Peer Group)** | 推荐 2~3 家同赛道核心可比同业（如三大运营商横向对标） | 自定义可比公司池 / 仅单公司分析不引入对标 |
| **4** | **分析侧重点 (Research Focus)** | 结合标的商业模式特征推荐（如 `综合全景研报`） | 红利安全边际与现金流 / 算力与第二增长曲线 / 财务排雷 |
| **5** | **交付格式 (Output Format)** | 推荐 `完整 Markdown + 交互式 HTML 研报（含双向脚注与 Tooltip 气泡预览）` | 纯文本 Markdown 研报 / 高管决策简报 (Executive Briefing) |

---

## 3. 交互执行路径 (Execution Path)

### 路径 A：优先调用 `ask_question` 工具（推荐）
在支持交互工具的环境中，主 Agent 单次调用 `ask_question` 传入 5 个独立题目：
1. 每个 question 表达清晰单一决策；
2. 推荐项排在 `options` 第一项并前缀 `(Recommended)`；
3. 不添加手动枚举编号（UI 自动枚举），不手动添加 "Other"（UI 默认自带 write-in 选项）。

### 路径 B：无 `ask_question` 时的标准文本降级
在纯文本环境中，主 Agent 在消息末尾按 1~5 编号分段列出：
- 写清每个问题的推荐项、推荐理由与备选项；
- 明确声明：“*我已挂起并等待您确认上述 5 项决策，收到答复后将立即启动 Phase 4 执行取数与分析。*”

---

## 4. 完成判据与状态流转 (Completion Criteria)

当用户答复后，主 Agent 执行以下动作完成 Checkpoint 1 闭环：
1. **决策回写 (Sync to Plan)**：将用户最终确认的 5 项决策更新同步至 `workspaces/<task_id>/plan/plan.md` 的 `Scope` 与 `Outline` 章节；
2. **解除阻断 (Unlock Phase 4)**：状态机切换至 `EXECUTION`，正式启动 Phase 4 双轨数据采集。
