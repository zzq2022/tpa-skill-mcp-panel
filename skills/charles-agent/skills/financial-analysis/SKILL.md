---
name: financial-analysis
description: "Use when assessing financial metrics, industry-specific ratios, or peer comparisons for named securities."
---

# financial-analysis

## Goal

基于结构化财务数据生成带报告期、单位、同比/环比、公式明细与行业口径的 analysis artifact。

## Input

- **单公司分析**：目标股票代码及其财务报表 CSV。
- **同业指标分析**：两个及以上对象的同口径财务报表 CSV。
- **期间与口径**：用户指定的年份/报告期；结构化显式 `industry` 或已验证公司元数据。
- **上游依赖**：缺少财务 CSV 时交回根 Skill 调度 `read-pdf` 获取，本 Skill 不自行抓取数据。

## Runtime boundary

Skill 目录视为只读。所有 artifacts 与日志必须写入任务工作区（如 `workspaces/<task_id>/`）。

- **CLI 范围**：只能执行已登记的 CLI；不得创建、修改或复制脚本，不得临时接入未登记能力。已登记能力不可用时返回 `unavailable`、`partial` 或 `failed`。
- **环境隔离**：CLI 独立加载项目根目录 `.env`。

## Internal workflow

### 1. 路由选择

| 任务场景 | 执行脚本 | 产物契约 |
|---|---|---|
| 单公司趋势、比率与成长性分析 | `ratio_analysis.py` | 单公司财务比率 analysis artifact |
| 多公司/同行业横向同口径比对 | `peer_compare.py` | 同业指标对比 analysis artifact |

### 2. 分析执行与完成准则

1. **单公司比率分析**：
   - **操作**：运行 `ratio_analysis.py` 计算盈利能力、偿债能力、营运能力及行业特化指标。
   - **行业口径规则**：保险等特殊行业仅在显式 `industry` 或已验证公司元数据支持时启用专用口径；否则使用 `general` 并在产物中披露限制。禁止根据公司名称或代码自行推断行业类型。
   - **完成准则**：生成包含指标名称、数值、单位、原始字段 `field` 与计算公式 `formula` 的 analysis artifact。
2. **多公司同业对比**：
   - **操作**：运行 `peer_compare.py`，对齐各对象报告期与指标口径。
   - **完成准则**：生成包含所有比对对象在指定期间的核心指标横向对比表格。
3. **期间完整性**：
   - 用户指定期间缺失时如实记录为缺失项，不得用其他历史期间隐式替代。

## Output

标准结果信封中登记 `analysis` artifact，关键字段包含：
- 分析对象、报告期、指标名称、数值与单位。
- 原始字段名（`field`）、计算公式（`formula`）与行业口径（`industry`）。
- 缺失项与数据质量说明，产物交回根 Skill 用于逻辑差与预期差分析。

## Failure handling

- **`unavailable`**：缺少目标代码或财务 CSV，且上游无法提供。
- **`partial`**：部分报告期数据缺失、或特殊行业专用字段不足但仍可输出基础通用指标。
- **`failed`**：数据格式解析异常或计算脚本崩溃。
- **约束**：特殊行业指标不足时仅输出已验证指标，不使用通用企业阈值强行评价。

## CLI

参数和示例见 [CLI 参数参考](../../docs/CLI_REFERENCE.md#financial-analysis)，也可运行 `ratio_analysis.py --help` 或 `peer_compare.py --help`。
