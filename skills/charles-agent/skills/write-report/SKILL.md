---
name: write-report
description: "Use when conducting five-step investment reasoning (information/logic/expectation gap, catalyst, conclusion) and assembling audited Markdown/HTML reports from upstream artifacts."
---

# write-report

## Goal

将上游 Skill 取得的 evidence/analysis artifacts 进行五步法链式深度推理，并组装为可审计的五步法 Markdown 研报与 HTML 交付物。

本 Skill 只消费上游 artifacts，不自主搜索、不重新执行信息差、逻辑差、预期差或催化剂阶段的数据采集。

## Gotchas

- **分析前置（Analysis Precedence）**：`report_generator.py` 必须接收已完成推理的 `<stock>_analysis.json`；若分析尚未执行，必须先调用 `five_step_analysis.py` 生成分析文件，严禁直接编译空产物。
- **估值绑定（Valuation Anchor）**：操作性措辞（配置建议、目标价、安全边际）必须严格绑定行情与估值证据；证据缺失时必须输出降级合规说明，严禁主观无据断言。
- **纯粹消费（Consumer-Only）**：只消费上游已验证 artifacts，不自主搜索、不补抓财报或计算比率；输入缺失时如实标记缺口。
- **工作区隔离（Workspace Isolation）**：所有分析中间产物与最终报告统一写入 `--output_dir` 指定的任务工作区，禁止向源码或根目录写入。
- **最弱链路定级（Weakest-Link Status）**：整份研报的置信度与状态严格由最弱关键证据环节决定；若使用了 `direct-fallback` 检索或关键章节缺失，整份报告最高状态为 `partial`。

## Input

- **研报元数据**：研究对象（`stock_name` / `stock_code`）、报告期、数据截至时间及目标格式。
- **上游产物与五步映射**：

| 报告章节 | 消费的上游 Skill 产物 | 核心内容与证据字段 |
|---|---|---|
| **一、信息差** | `read-pdf` (`evidence`)<br>`web-search` (`evidence`) | 财报底层数据、页码摘录、检索记录（`retrieval_mode`、`index_artifact`、`queries_executed`）及外部客观佐证 |
| **二、逻辑差** | `compare-reports` (`comparison`)<br>`financial-analysis` (`analysis`) | 跨期/同业比对、财务因果链（事实 $\rightarrow$ 推断 $\rightarrow$ 假设） |
| **三、预期差** | `financial-analysis` (`analysis`)<br>`web-search` (`consensus`) | 实际财务比率与卖方券商一致预期（Consensus）/公司指引的偏离度 |
| **四、催化剂与情绪** | `sentiment-analysis` (`events`, `sentiment`)<br>`web-search` (`policy`) | 舆情打分分布、催化剂事件类别与触发时间窗口 |
| **五、结论与风险闭环** | `stock-price` (`evidence`) | 最新行情与估值分位、确定性评级、核心假设与失效条件 |

## Runtime boundary

Skill 目录视为只读。所有 artifacts 与报告必须写入任务工作区（如 `workspaces/<task_id>/`）。

- **CLI 范围**：只能按序执行已登记的 CLI（`five_step_analysis.py` $\rightarrow$ `report_generator.py`）；不得创建、修改或复制脚本，不得临时接入未登记能力。只消费上游 artifacts，不补写数据抓取、分析或格式转换脚本。已登记能力不可用时返回 `unavailable`、`partial` 或 `failed`。
- **环境隔离**：CLI 自行加载 Skill 根目录 `.env`。

## Internal workflow

### 1. 证据核验与状态矩阵（Verify & Build Matrix）
- **操作**：校验上游 artifacts 的对象一致性、报告期覆盖度与 evidence 字段完整性。
- **完成准则**：生成覆盖五个章节的证据状态矩阵；若无任何可用 evidence，直接返回 `unavailable` 并终止。

### 2. 五步法递进式分析（Step 1 Reasoning: `five_step_analysis.py`）
- **操作**：基于上游 `read-pdf` 构建的 FAISS 向量索引与结构化证据，调用 `five_step_analysis.py`（指定 `--index_dir`、`--stock_name` 与 `--output_dir` 至任务工作区）执行递进推理。
- **完成准则**：
  - 严格区分事实（Fact）、推断（Inference）与假设（Hypothesis）。
  - 生成包含 5 步推理及对应证据页码的 `<stock_name>_analysis.json`（支持 `--focus` 聚焦单步与断点续跑）。

### 3. 研报组装与格式渲染（Step 2 Rendering: `report_generator.py`）
- **操作**：调用 `report_generator.py`（传入 `--analysis_file <analysis_json>` 与 `--output_dir <workspace>/output/reports`），执行证据矩阵核验与合规文本生成。
- **完成准则**：
  - 报告正文前输出章节证据状态表（信息差行完整保留 `retrieval_mode`、`index_artifact` 与 `queries_executed`）。
  - 操作性措辞严格绑定估值与行情证据，结论章明确标明核心假设与失效条件。
  - 生成最终 Markdown 研报与 HTML 交付物，登记 `report` artifacts。

## Output

标准结果信封中登记 `report` artifacts：
- 结构化研报 JSON（`module: five_step_analysis`）。
- Markdown 研报及 HTML 交付物（`module: report`，包含证据状态矩阵、核心因果链、风险提示与免责声明）。

## Failure handling

- **`unavailable`**：缺失关键上游 artifacts（如无向量索引或无任何基础证据）无法形成分析，禁止主观编造数值。
- **`partial`**：部分章节证据缺失（如无一致预期时预期差标为 `unavailable`），或使用了 `direct-fallback` 检索，整份报告最高为 `partial`。
- **`failed`**：分析推理或报告生成脚本执行异常。

## CLI

参数和示例见 [CLI 参数参考](../../docs/CLI_REFERENCE.md#write-report)。递进推理使用 `five_step_analysis.py`，标准渲染使用 `report_generator.py`。
