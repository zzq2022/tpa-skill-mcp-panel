# 投研方案规划模板 (Plan Template)

在 Phase 2 Planning 阶段，Agent 必须在 `workspaces/<task_id>/plan/plan.md` 产出单一结构化规划文件（四段合一：Brief / Scope / Outline / Artifacts）。

---

## `plan/plan.md` 模板内容

```markdown
# 投研任务规划: [公司名称/研究标的]

## 1. Brief (研究摘要)
- **研究目标**：[如：评估中国电信基本面、股息率可持续性与投资价值]
- **研究对象**：[公司名称 / 标的]
- **标的代码**：[标准化证券代码，如 601728.SH / 0728.HK]
- **研究类型**：[公司研究 company | 文档研究 document]
- **核心关注点**：[如：现金流与分红能力、算力业务弹性、估值分位]

## 2. Scope (范围与口径界定)
- **分析周期**：[如：2022FY ~ 2024FY 近三年年报 + 2025Q3 季报]
- **同业对标池**：[如：中国移动(600941.SH)、中国联通(600050.SH)]
- **行业分析口径**：[general | insurer 等]
- **一致预期基准**：[卖方券商 Consensus / Wind / 自研基准]

## 3. Outline (五步法交付大纲)
- **Step 1: 信息差**：三大报表底层异动、现金流质量、财报附注与 RAG 证据挖掘。
- **Step 2: 逻辑差**：市场主流叙事 vs 客观事实的因果链偏差定位。
- **Step 3: 预期差**：实际财务弹性与一致预期偏离幅度对标。
- **Step 4: 催化剂与情绪**：重估时间窗口、关键事件与正反向触发条件。
- **Step 5: 投资结论与风险闭环**：确定性评级、安全边际与核心假设失效条件。

## 4. Artifacts (产物与文件规划)
- `data/financial_data/`：结构化财务数据 CSV
- `data/vector_db/`：财报 PDF 向量索引
- `analysis/`：财务比率、同业对比、因果链分析文件
- `review/final-review.md`：终审质检记录
- `output/reports/`：最终 Markdown / HTML 格式研报
```
