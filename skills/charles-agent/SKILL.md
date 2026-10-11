---
name: charles-agent
description: "Use when analyzing a named company, security, industry, financial report, market event, or multi-source investment question and producing an evidence-backed five-step research deliverable."
metadata:
  version: "2.1.1"
---

# Charles 五步法投研 Skill

## Goal

将自然语言投研问题拆解为连续的 8 个执行阶段（Phase 0 ~ Phase 8）。由宿主 Agent 自主调度子 Skill 的原子 CLI 获取客观证据，状态物理落盘至工作区，并在关键决策点（Checkpoint 1）与用户对齐，输出包含确定性评级、核心假设与失效条件的闭环研报。

根 Skill 是跨模块流程的唯一编排者；子 Skill 仅负责自身内部执行。

## Trigger boundary

- **适用场景**：公司、证券、行业、财报、研究报告、事件、政策、舆情、估值与综合投资研究。
- **对象判定**：
  - **公司研究**：必须提供证券代码与市场后缀（如 `600519.SH`）。
  - **文档研究**：必须提供本地文件路径或 URL。
  - 语义不明确时向用户确认，不自行假定研究类型。不用于代码调试、系统运维、翻译或无明确对象的泛问答。

## Setup

本项目只以 Skill 模式运行。宿主读取本文件，根据下方步骤加载 `references/` 与 `skills/*/SKILL.md`，再用当前 Python 环境执行已登记的子 Skill CLI：

```powershell
pip install -r requirements-tpa-skill.txt
python runtime/preflight.py --skip-api
```

需要确认脚本参数或 PowerShell 调用方式时，读取 [CLI 参数参考](docs/CLI_REFERENCE.md)。路径含空格时必须使用 PowerShell 调用运算符 `&`，并按参考文档设置 UTF-8。

## Runtime boundary

Skill 目录视为只读。所有 artifacts、中间数据与日志必须写入任务工作区（默认 `workspaces/<task_id>/`）。

- **只读基线**：只能读取根与子 `SKILL.md`、执行当前发布包和 `CLI_REFERENCE.md` 已登记的 CLI；不得在 Skill 目录内创建、修改、复制或删除文件，不得创建临时脚本、证券专用脚本或批处理脚本，也不得用 `python -c`、内联代码或自制接口替代缺失能力。
- **状态契约**：已登记的 CLI 缺少输入、依赖或数据源时，按结果信封返回 `partial`、`unavailable` 或 `failed`，能力缺口不是开发触发器，不得通过现场改代码把结果包装成成功。

## Research brief

执行前确认并提取结构化研究参数：

| 字段 | 含义与约束 | 回退与缺省规则 |
|---|---|---|
| `subject` / `symbol` | 研究对象名称及标准化证券代码（如 `600941.SH`） | 文档研究时提供 `document` 路径 |
| `scope.period` | 用户明确指定的年份或报告期（如 `2024FY`） | 必须原样逐期核验，旧报告不能替代缺失期间，缺失只能标为 `partial` 或 `unavailable` |
| `scope.industry` | 结构化 `scope.industry` 显式行业配置（`general|insurer`） | 自由文本中的公司名称或代码不算显式配置。没有显式字段时使用已验证公司元数据，无法验证则使用 `general` 并披露限制 |
| `scope.peers` | 用户指定或证据支持的同业对比对象 | 无指定时仅执行单公司分析 |
| `output` | 目标格式（Markdown / HTML）与工作区路径 | 默认写入指定的 `workspaces/<task_id>/` |

---

## 各阶段文件读取指南（渐进加载，别一次全读）

| 阶段 | 必读文档 | 按需读取 | 产出与动作 |
|---|---|---|---|
| **Phase 0 (Intake)** | [references/harness.md](references/harness.md) | —— | 判定研究对象类型，初始化会话上下文 |
| **Phase 1 (Source)** | —— | [skills/read-pdf/SKILL.md](skills/read-pdf/SKILL.md) | 初始化 `workspaces/<task_id>/`，生成 `source/source.md` |
| **Phase 2 (Planning)** | [references/plan-template.md](references/plan-template.md) | —— | 生成 `plan/plan.md`，主 Agent 内联 5 条清单自查 |
| **Phase 3 (Checkpoint 1)** | [references/checkpoint-rules.md](references/checkpoint-rules.md) | —— | **★硬停**：逐项确认 5 项核心决策 |
| **Phase 4 (Step 1 信息差)** | [skills/read-pdf/SKILL.md](skills/read-pdf/SKILL.md) | [skills/web-search/SKILL.md](skills/web-search/SKILL.md) | 抓取财报/RAG/搜索，落盘 `data/` |
| **Phase 5 (Step 2 逻辑差)** | —— | [skills/compare-reports/SKILL.md](skills/compare-reports/SKILL.md) | 因果链推导，落盘 `analysis/logic_chain.md` |
| **Phase 6 (Step 3 预期差)** | [skills/financial-analysis/SKILL.md](skills/financial-analysis/SKILL.md) | [skills/web-search/SKILL.md](skills/web-search/SKILL.md) | 比率分析与对标，落盘 `analysis/` |
| **Phase 7 (Step 4 催化剂)** | [skills/sentiment-analysis/SKILL.md](skills/sentiment-analysis/SKILL.md) | [skills/web-search/SKILL.md](skills/web-search/SKILL.md) | 情绪与事件分析，落盘 `analysis/` |
| **Phase 8 (Step 5 终审交付)** | [references/review-checklist.md](references/review-checklist.md) | [skills/write-report/SKILL.md](skills/write-report/SKILL.md) · [skills/stock-price/SKILL.md](skills/stock-price/SKILL.md) | 终审写 `review/final-review.md`，定稿输出 `output/reports/*.md` |

---

## Lifecycle Phases & Workflow

宿主 Agent 执行时复制此清单并在关键阶段流转与汇报中更新进度：

```text
投研执行进度：
- [ ] Phase 0: Intake（需求判定与标的抽取）
- [ ] Phase 1: Source & Workspace（工作区初始化与底座落盘）
- [ ] Phase 2: Planning（方案编制与内联自查）
- [ ] Phase 3: Checkpoint 1（★硬阻断：5 项核心决策用户确认）
- [ ] Phase 4: 信息差（财报数据/RAG/市场事实落盘）
- [ ] Phase 5: 逻辑差（因果链推导与分歧定位）
- [ ] Phase 6: 预期差（财务建模与一致预期对标）
- [ ] Phase 7: 催化剂与情绪（事件识别与触发窗口）
- [ ] Phase 8: 结论闭环（评级/失效条件与三视角终审）
```

### Phase 0 —— Intake (需求判定)
判断用户输入是公司名称、代码、还是 PDF/URL 文档。提取目标语言、研究对象与基础诉求。若关键标的不明确，先向用户提问澄清，不凭空假设。

### Phase 1 —— Source $\rightarrow$ Markdown & Workspace Init (事实底座)
1. 创建工作区 `workspaces/<task_id>/`（含 `source/`, `plan/`, `data/`, `analysis/`, `review/`, `output/` 目录结构）。
2. 文档研究时解析源文件为 `source/source.md`；公司研究时写入基础元数据至 `source/source.md`。

### Phase 2 —— Editorial Planning (方案规划)
生成一份 `plan/plan.md`（包含 Brief / Scope / Outline / Artifacts 四段，模板见 [references/plan-template.md](references/plan-template.md)）。
- **门禁**：主 Agent 就地内联核查，**禁止开 SubAgent，禁止写 review 文件**。

### Phase 3 —— Plan Checkpoint (★ Checkpoint 1，硬阻断，必须停)
**铁律：禁止静默替用户选择。** 停下来，通过 `ask_question` 或编号消息向用户**独立确认 5 项决策**（规范见 [references/checkpoint-rules.md](references/checkpoint-rules.md)）：
1. 研究标的与证券代码
2. 研究时间跨度 (Period Scope)
3. 同业对标池 (Peer Group)
4. 分析侧重点 (Research Focus)
5. 交付格式 (Output Format)
用户未确认前，**严禁进入 Phase 4 取数**。

---

### Phase 4 —— Step 1: 信息差（被忽视的数据）
- **调度子技能**：加载 [read-pdf](skills/read-pdf/SKILL.md) 与 [web-search](skills/web-search/SKILL.md)。
- **核心动作**：
  1. 调度 `read-pdf` 下载三大财务报表与财报原件至 `data/`。五步法、完整研报或跨章节分析必须先取得 `index` artifact，且必须运行 `query_report.py` 生成底层 RAG evidence。
  2. 调度 `web-search` 检索同期公开信息与主流认知，提炼被忽视的客观事实，区分“文档事实”、“市场已知信息”与“待验证线索”。
- **流转门禁**：至少有一条可定位文档事实。五步法、完整研报或跨章节分析还必须同时登记索引 artifact、RAG 查询次数和 RAG evidence；文本搜索只能复核 RAG 返回的候选页，不能替代首次检索。索引构建或 RAG 查询失败时记录 `retrieval_mode=direct-fallback`，Step 1 最多为 `partial`。没有外部佐证时，本步最多为 `partial`，只能称为待验证线索。门禁必须核验：① `data/financial_data/` CSV 存在；② `data/financial_reports/` PDF 存在；③ `data/vector_db/index.faiss` 存在且包含 RAG evidence，信封 `status` 为 `success` 或 `partial`。严禁仅依赖 CSV 而跳过 PDF/RAG 流程。

### Phase 5 —— Step 2: 逻辑差（市场的错误推理）
- **调度子技能**：Agent 自主因果链推理，按需配合 [compare-reports](skills/compare-reports/SKILL.md)。
- **核心动作**：
  1. 基于 Step 1 客观事实，构建“事实 $\rightarrow$ 推断 $\rightarrow$ 假设”完整因果链，落盘至 `analysis/logic_chain.md`。
  2. 定位市场在因果归因中的盲区、过度线性外推或错误假设。
  3. 按需调度 `compare-reports` 完成跨期或同业比较，印证逻辑分歧点。
- **流转门禁**：因果链每个关键环节均能回溯到 evidence 或 analysis artifact；缺少关键环节时标为 `partial`。检查 `analysis/logic_chain.md` 是否已落盘，推论均有 Phase 4 事实锚定。

### Phase 6 —— Step 3: 预期差（偏离幅度与持续性）
- **调度子技能**：加载 [financial-analysis](skills/financial-analysis/SKILL.md) 与 [web-search](skills/web-search/SKILL.md)。
- **核心动作**：
  1. 调度 `web-search` 获取同期同口径的卖方券商一致预期（Consensus）、业绩指引与估值基准。
  2. 调度 `financial-analysis` 计算目标期间财务指标、趋势与行业口径真实盈利弹性，落盘至 `analysis/`。
  3. 对标实际模型与一致预期，量化偏离幅度并论证持续性。
- **流转门禁**：没有可比的一致预期、公司指引或明确基准时，本步为 `unavailable`；不得用“市场可能低估”代替预期差量化。检查 `analysis/` 财务比率数据是否生成；无对比基准时信封如实标为 `partial/unavailable`。

### Phase 7 —— Step 4: 催化剂与情绪（触发重估的时间节点）
- **调度子技能**：加载 [sentiment-analysis](skills/sentiment-analysis/SKILL.md) 与 [web-search](skills/web-search/SKILL.md)。
- **核心动作**：
  1. 调度 `sentiment-analysis` 抓取新闻并完成相关性过滤、情绪打分与事件识别，落盘至 `analysis/`。
  2. 调度 `web-search` 补充近期关键事件、行业动态或政策原文。
  3. 锁定触发市场认知重估的核心时间节点或催化窗口，明确正反向触发条件。
- **流转门禁**：只有泛行业叙事而没有事件来源和时间窗口时，本步最多为 `partial`。检查情绪/事件分析文件是否落盘，关键催化剂是否具备明确时间节点。

### Phase 8 —— Step 5: 结论与风险闭环（投资评级 + 失效条件）
- **调度子技能**：加载 [stock-price](skills/stock-price/SKILL.md) 与 [write-report](skills/write-report/SKILL.md)。
- **核心动作**：
  1. 调度 `stock-price` 获取带时间戳（`as_of`）的行情与历史估值分位，验证价格是否已 Price-in 前述预期。
  2. Agent 综合五步证据，输出确定性评级、安全边际、风险收益比与投资结论。
  3. 将前序有效 artifacts 交给 `write-report`，明确输出核心假设的**失效条件**（如关键指标低于阈值即证伪）与跟踪指标，执行五步法分析与报告生成至 `output/reports/`。
  4. 按照 [references/review-checklist.md](references/review-checklist.md) 执行三视角终审（数据真实性、逻辑闭环度、失效条件完整性），质检记录写入 `review/final-review.md`。
- **流转门禁**：结论强度不得高于最弱关键证据。没有目标价、历史估值分位或风险收益比时，不得使用“买点”“安全边际”“适合配置”等操作性措辞。未能明确列出失效条件时，本步最多为 `partial`。研报必须包含正文《章节证据状态表》与核心假设**失效条件**。

---

## Evidence & Delivery Contract

每个关键数值、比较和事件至少关联一条包含 `locator`、`as_of`、`period`、`field`、`formula` 的 evidence record，详细信封格式见 [子 Skill 交接契约](skills/_common/SKILL_CONTRACT.md)。

报告正文前输出章节证据状态表；信息差同时披露 `retrieval_mode`：

| 五步 | 证据状态 | 检索方式 | 已用证据 | 缺口及影响 |
|---|---|---|---|---|
| 信息差 | available/partial/unavailable | rag/direct/direct-fallback | 文件、页码或 URL | 对信息差判断的影响 |
| 逻辑差 | available/partial/unavailable | - | 财务和比较 artifacts | 因果链缺口 |
| 预期差 | available/partial/unavailable | - | 一致预期、指引或估值基准 | 无可比预期时不可下结论 |
| 催化剂 | available/partial/unavailable | - | 事件来源和日期 | 时间或方向不确定性 |
| 结论 | available/partial/unavailable | - | 关键证据汇总 | 总体置信度和失效条件 |

只报告实际完成内容，显式列出 `warnings`、`errors`、证据缺口与 `next_actions`。输出必须包含研究对象、期间、数据截至时间、来源、限制和“仅供研究参考，不构成投资建议”的免责声明。
