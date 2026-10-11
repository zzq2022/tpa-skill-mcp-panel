---
name: compare-reports
description: "Use when comparing named companies or reporting periods across compatible report indices."
---

# compare-reports

## Goal

基于兼容的统一索引，输出对象、期间与口径明确的跨期或跨公司 comparison artifact，并如实标记差异与不可比项。

## Input

- **跨期对比**：同一对象、两个及以上报告期的兼容统一索引。
- **跨公司对比**：两个及以上对象、同一口径期间的兼容统一索引。
- **上游依赖**：兼容统一索引由 `read-pdf` 生成；缺少覆盖目标对象或期间的索引时，将缺口交回根 Skill，本 Skill 不自行抓取或解析报告。

## Runtime boundary

Skill 目录视为只读。所有 artifacts 与日志必须写入任务工作区（如 `workspaces/<task_id>/`）。

- **CLI 范围**：只能执行已登记的 CLI；不得创建、修改或复制脚本，不得临时接入未登记能力。已登记能力不可用时返回 `unavailable`、`partial` 或 `failed`。
- **环境隔离**：CLI 自行加载 Skill 根目录 `.env`。

## Internal workflow

### 1. 路由选择

| 比较模式 | 执行脚本 | 产物契约 |
|---|---|---|
| 同一对象跨期/跨年度演进分析 | `cross_period.py` | 跨期对比 comparison artifact |
| 多对象同口径期间横向对比 | `cross_company.py` | 跨公司对比 comparison artifact |

### 2. 执行步骤与完成准则

1. **索引核验（Index Verification）**：
   - **操作**：读取索引 `index_meta.json`，验证是否完整覆盖全部请求对象与期间。
   - **完成准则**：目标对象与期间均存在且嵌入配置兼容。若缺失关键对象或期间，返回 `unavailable` 并交回上游。
2. **执行比对（Execute Comparison）**：
   - **操作**：按模式运行 `cross_period.py` 或 `cross_company.py`。
   - **完成准则**：生成包含一致项、差异项与不可比项的结构化对比数据。
3. **对齐与证据追溯（Alignment & Evidence）**：
   - **操作**：明确标注基期（Base Period）与当前期（Current Period），关联对应的来源文档、页码或检索 `locator`。
   - **完成准则**：所有对比论点均附带可追溯的原文位置与不可比说明。

## Output

标准结果信封中登记 `comparison` artifact，关键字段包含：
- 比较对象、主题、基期与当前期。
- 业务/财务核心差异项与一致项。
- 不可比项及具体原因（口径变更、披露缺失等）。
- 来源文档、页码或检索 `locator`，产物交回根 Skill 用于逻辑差分析。

## Failure handling

- **`unavailable`**：缺少必需对象或期间的索引文件，且上游无法提供。
- **`partial`**：部分对比期间或指标覆盖不全，已在产物中明确列出未覆盖范围与不可比项。
- **`failed`**：索引损坏、嵌入维度不匹配或比较脚本崩溃。
- **约束**：统一比较必须严格以请求对象与期间为准，不使用旧期间或非兼容索引静默替代。

## CLI

参数和示例见 [CLI 参数参考](../../docs/CLI_REFERENCE.md#compare-reports)，也可运行对应脚本的 `--help`。
