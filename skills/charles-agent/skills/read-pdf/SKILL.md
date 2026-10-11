---
name: read-pdf
description: "Use when retrieving evidence from financial PDFs or fetching structured financial CSV data."
---

# read-pdf

## Goal

从财报、公告或研究报告中生成可定位到文件、页码和原文摘录的 evidence，并按需生成可查询索引或结构化数据。

## Input

- 本地 PDF；或可下载报告的股票代码、类别和报告期。
- 可选：已有分页文本或 FAISS 索引。
- 查询时提供明确问题；统一索引查询还需股票代码。
- 输出目录使用宿主可读取的任务工作区路径。

## Runtime boundary

Skill 目录视为只读。所有 artifacts、中间数据与日志必须写入任务工作区（如 `workspaces/<task_id>/`）。

- **CLI 范围**：只能执行已登记的 CLI；不得创建、修改或复制脚本，不得创建临时 Python、PowerShell、批处理、编码转换或页面搜索脚本。处理多个证券时逐个调用现有 `fetch_financial_data.py`，不得生成批处理或证券专用脚本。
- **状态与隔离**：能力或依赖缺失时返回 `unavailable`、`partial` 或 `failed`。CLI 自行加载 Skill 根目录 `.env`。

## Workflow selection

### PDF 证据流程

读取、引用、比较年报或回答报告问题时，默认运行 `fetch_financial_data.py --type pdf`，再执行解析 -> 建索引 -> `query_report.py` -> 原始页复核。该流程不得隐式获取 CSV；PDF、页码和摘录是最终 evidence。

### 结构化财务流程

只有上层明确需要三大表、比率计算或批量数据时，才运行 `fetch_financial_data.py --type financial`。该流程输出外部结构化 CSV 并交给 `financial-analysis`，不解析或建立 PDF 索引；关键结论需要页码证据时，另行执行 PDF 证据流程。

## Internal workflow

### 1. 路由选择

| 任务条件 | 必须执行的路径 |
|---|---|
| 五步法、完整研报、跨章节分析 | 复用兼容索引并运行 `query_report.py`；没有索引时执行 `preprocess.py --workspace <dir>` -> `query_report.py` |
| 精确页码、精确字段或精确原文 | 允许直接读取对应 PDF、分页文本或页码映射 |
| 只需给 `financial-analysis` 提供 CSV | 显式运行 `fetch_financial_data.py --type financial` 后结束，不额外解析或建索引 |

### 2. 执行流水线与完成准则

1. **获取（Fetch）**：
   - **操作**：PDF 证据流程运行 `fetch_financial_data.py --type all`。用户指定年度时必须传递 `--periods`（例如 `--periods 2024,2025`）。报告期优先于披露日期，不使用 `start_date/end_date` 过滤。
   - **完成准则**：`report_periods` 覆盖用户请求。若 `missing_periods` 非空，保留已取得报告并标记为 `partial`，不得用其他年度报告替代。
2. **预处理与建库（Preprocess & Index）**：
   - **操作**：运行 `preprocess.py --workspace <dir>` 进行 PyMuPDF 基础解析、元数据提取、切片注入与统一 FAISS 向量库构建（自动生成 `data/documents.db`、`data/parsed/`、`data/chunks.json` 与 `data/vector_db/`）。构建前从 `.env` 读取完整的 `EMBEDDING_API_KEY`、`EMBEDDING_BASE_URL` 和 `EMBEDDING_BASE_MODEL`（不能回退到 `OPENAI_API_KEY`，`OPENAI_API_KEY` 仅供 LLM 问答使用）。
   - **完成准则**：`index_meta.json` 准确记录实际生效的嵌入模型配置与 `chunk_size`、`chunk_overlap`；`chunks.json` 包含 `source`、`page`、`period`、`stock_code` 等原生元数据。元数据缺失、损坏或不兼容时重新构建。
3. **检索（Query）**：
   - **操作**：运行 `query_report.py`，使用有限候选池进行混合检索。
   - **完成准则**：输出包含 `evidence` 列表，每条 evidence 包含 `evidence_id`、PDF 实体 `page`、原文 `excerpt` 和 `scores`。
4. **降级与复核（Verify）**：
   - **操作**：直接读取候选原始页复核 evidence，不得用全文文本搜索替代 RAG 检索与原始页复核。
   - **完成准则**：回答中的数字与结论必须严格对应 verified evidence，不得自行推断字段名称或页码。索引不可用或检索失败时，记录 `retrieval_mode=direct-fallback` 并直接读取原文，状态最多为 `partial`。

## Output

返回标准结果信封，并登记实际生成的 `data`、`index` 或 `evidence` artifacts：

- `summary` 按公共契约登记 `retrieval_mode`、`index_artifact` 和 `queries_executed`。
- 关键 evidence 必须包含文档名、页码或 URL、匹配摘录、期间和置信度。
- RAG 查询的 `evidence` 字段必须保留 `evidence_id`、`excerpt` 和 `scores`。
- 可将财务 CSV 交给 `financial-analysis`，将统一索引交给 `compare-reports`，将页码 evidence 交回根 Skill。

## Failure handling

- **`unavailable`**：没有 PDF、股票代码、解析文本或兼容索引，且无法执行降级。
- **`partial`**：基础解析质量不足/乱码待 OCR、用户指定报告期部分缺失、或触发 `direct-fallback` 直接原文复核。
- **`failed`**：执行抛出异常或外部依赖致命错误。
- 约束：无页码模型摘要不能作为原文 evidence；综合分析缺少索引 artifact 或 RAG evidence 时不得返回 `success`。

## CLI

参数、示例和 PowerShell UTF-8 调用方式见 [CLI 参数参考](../../docs/CLI_REFERENCE.md#read-pdf)。执行前也可运行目标脚本的 `--help`。
