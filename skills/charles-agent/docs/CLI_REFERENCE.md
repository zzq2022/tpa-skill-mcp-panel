# Charles Skill CLI 参数参考

> 本文由 `scripts/generate_cli_reference.py` 根据脚本中的 `argparse` 定义生成。参数、默认值和可选值以源码为准。

## 目录

- [Windows 安全调用](#windows-安全调用)
- [环境配置](#环境配置)
- [环境预检](#环境预检)
- [read-pdf](#read-pdf)
- [financial-analysis](#financial-analysis)
- [sentiment-analysis](#sentiment-analysis)
- [compare-reports](#compare-reports)
- [write-report](#write-report)
- [stock-price](#stock-price)
- [web-search](#web-search)

## Windows 安全调用

可执行文件路径包含空格时，在 PowerShell 中使用调用运算符 `&`，并显式设置 UTF-8：

```powershell
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$python = '<python.exe绝对路径>'
& $python runtime/preflight.py
& $python skills/read-pdf/scripts/parse_pdf_basic.py --pdf '<报告PDF>' --output_dir '<输出目录>'
```

子 Skill 通过明确的 artifact 路径交接；不要从 PowerShell 表格输出猜测或截断路径。

## 环境配置

读取模型或 API 配置的子 Skill CLI 会在独立进程中自行加载 Skill 根目录 `.env`。调用方无需先运行预检来传递变量，也无需生成 PowerShell 或 Python 包装脚本。操作系统中已存在的环境变量优先于 `.env`。

## 环境预检

预检参数由 `runtime/preflight.py` 的 argparse 定义生成：

### `preflight.py`

**路径**：`runtime/preflight.py`<br>
**功能**：环境预检 - 启动前检查所有依赖和配置

| 参数 | 类型 | 必需 | 默认值 | 可选值 | 说明 |
|---|---|---:|---|---|---|
| `--quiet` | `bool` | 否 | `false` | `-` | 静默模式（仅输出错误） |
| `--skip-api` | `bool` | 否 | `false` | `-` | 仅检查本地依赖和配置 |

## read-pdf

财报下载、解析、索引和 RAG 查询

### `fetch_financial_data.py`

**路径**：`skills/read-pdf/scripts/fetch_financial_data.py`<br>
**功能**：财务数据获取工具

| 参数 | 类型 | 必需 | 默认值 | 可选值 | 说明 |
|---|---|---:|---|---|---|
| `--stock` | `str` | 是 | `None` | `-` | 股票代码（如 600519） |
| `--type` | `str` | 否 | `pdf` | `financial, pdf, all` | 获取类型：financial=结构化数据, pdf=PDF年报, all=全部（默认: pdf） |
| `--output_dir` | `str` | 否 | `./data` | `-` | 输出根目录（默认: ./data） |
| `--category` | `str` | 否 | `年度报告` | `年度报告, 半年度报告, 一季度报告, 三季度报告, 业绩预告` | PDF报告类别（默认: 年度报告） |
| `--keyword` | `str` | 否 | `` | `-` | PDF标题过滤关键词 |
| `--max_download` | `int` | 否 | `3` | `-` | 最大PDF下载数量（默认: 3） |
| `--start_date` | `str` | 否 | `` | `-` | 起始日期（如 2024-01-01） |
| `--end_date` | `str` | 否 | `` | `-` | 结束日期（如 2025-12-31） |
| `--periods` | `str` | 否 | `` | `-` | 逗号分隔的报告年度（如 2024,2025） |

**示例**：

```powershell
python fetch_financial_data.py --stock 600519 --type financial
python fetch_financial_data.py --stock 600519 --type pdf --category 年度报告
python fetch_financial_data.py --stock 600519 --type all --max_download 5
```

### `preprocess.py`

**路径**：`skills/read-pdf/scripts/preprocess.py`<br>
**功能**：数据预处理引擎 (preprocess.py) - 统一批量解析 PDF、提取结构化元数据与构建 FAISS 向量索引

| 参数 | 类型 | 必需 | 默认值 | 可选值 | 说明 |
|---|---|---:|---|---|---|
| `--workspace` | `str` | 否 | `None` | `-` | 工作区根目录（如 workspaces/601318_pingan） |
| `--pdf_dir` | `str` | 否 | `None` | `-` | PDF 文件目录（默认: <workspace>/data/financial_reports 或 ./data/financial_reports） |
| `--output_dir` | `str` | 否 | `None` | `-` | 向量库输出目录（默认: <workspace>/data/vector_db 或 ./data/vector_db） |
| `--parsed_dir` | `str` | 否 | `None` | `-` | 解析文本输出目录（默认: <workspace>/data/parsed 或 ./data/parsed） |
| `--db_path` | `str` | 否 | `None` | `-` | SQLite 数据库路径（默认: <workspace>/data/documents.db） |
| `--rebuild` | `bool` | 否 | `false` | `-` | 清空旧记录并全量重新构建 |
| `--skip-index` | `bool` | 否 | `false` | `-` | 仅解析文本并存入 SQLite，不构建 FAISS 索引 |
| `--chunk_size` | `int` | 否 | `int(os.getenv('EMBEDDING_CHUNK_SIZE', '400'))` | `-` | 切片大小 |
| `--chunk_overlap` | `int` | 否 | `int(os.getenv('EMBEDDING_CHUNK_OVERLAP', '80'))` | `-` | 切片重叠 |
| `--embedding_model` | `str` | 否 | `None` | `-` | Embedding 模型名称 |

**示例**：

```powershell
python preprocess.py --workspace workspaces/601318_pingan
python preprocess.py --pdf_dir data/financial_reports --output_dir data/vector_db
python preprocess.py --workspace workspaces/601318_pingan --rebuild
python preprocess.py --workspace workspaces/601318_pingan --skip-index
```

### `query_report.py`

**路径**：`skills/read-pdf/scripts/query_report.py`<br>
**功能**：RAG 问答查询器

| 参数 | 类型 | 必需 | 默认值 | 可选值 | 说明 |
|---|---|---:|---|---|---|
| `--index_dir` | `str` | 是 | `None` | `-` | FAISS 索引目录 |
| `--query` | `str` | 是 | `None` | `-` | 查询问题 |
| `--top_k` | `int` | 否 | `6` | `-` | 返回文档数（默认: 6） |
| `--model` | `str` | 否 | `deepseek-v3` | `-` | LLM 模型（默认: deepseek-v3） |
| `--alpha` | `float` | 否 | `0.5` | `-` | 混合检索中向量权重（默认: 0.5） |
| `--stock` | `str` | 否 | `None` | `-` | 按股票代码过滤（如 688981），仅统一索引有效 |

**示例**：

```powershell
python query_report.py --index_dir data/vector_db --query "营收和净利润是多少"
python query_report.py --index_dir data/vector_store --query "主要风险因素" --top_k 8
python query_report.py --index_dir data/vector_store --query "核心竞争力" --stock 688981
```

## financial-analysis

财务指标和同业分析

### `ratio_analysis.py`

**路径**：`skills/financial-analysis/scripts/ratio_analysis.py`<br>
**功能**：核心财务指标分析工具

| 参数 | 类型 | 必需 | 默认值 | 可选值 | 说明 |
|---|---|---:|---|---|---|
| `--stock` | `str` | 是 | `None` | `-` | 股票代码(如 600519) |
| `--years` | `int` | 否 | `5` | `-` | 分析年数(默认: 5) |
| `--period` | `str` | 否 | `annual` | `-` | 报告期: annual、latest 或 YYYYMMDD（默认: annual） |
| `--periods` | `str` | 否 | `` | `-` | 逗号分隔的明确年度（如 2024,2025）；提供后仅分析这些年报期 |
| `--industry` | `str` | 否 | `auto` | `auto, general, insurer` | 行业分析口径（默认: auto - 自动识别） |
| `--data_dir` | `str` | 否 | `data/financial_data` | `-` | 财务数据目录（默认: data/financial_data） |
| `--output` | `str` | 否 | `None` | `-` | JSON 结果保存路径(可选) |

**示例**：

```powershell
python ratio_analysis.py --stock 600519
python ratio_analysis.py --stock 600519 --years 3
python ratio_analysis.py --stock 688981 --data_dir data/financial_data --output output/analysis.json
```

### `peer_compare.py`

**路径**：`skills/financial-analysis/scripts/peer_compare.py`<br>
**功能**：同行对比分析工具

| 参数 | 类型 | 必需 | 默认值 | 可选值 | 说明 |
|---|---|---:|---|---|---|
| `--stocks` | `str` | 是 | `None` | `-` | 股票代码(逗号分隔, 如 600519,000858) |
| `--data_dir` | `str` | 否 | `data/financial_data` | `-` | 财务数据目录（默认: data/financial_data） |
| `--output` | `str` | 否 | `None` | `-` | JSON 结果保存路径(可选) |

**示例**：

```powershell
python peer_compare.py --stocks 600519,000858
python peer_compare.py --stocks 688981,002049,603501 --data_dir data/financial_data
python peer_compare.py --stocks 600519,000858 --output output/peer_compare.json
```

## sentiment-analysis

新闻、情绪和事件分析

### `news_fetcher.py`

**路径**：`skills/sentiment-analysis/scripts/news_fetcher.py`<br>
**功能**：新闻抓取器

| 参数 | 类型 | 必需 | 默认值 | 可选值 | 说明 |
|---|---|---:|---|---|---|
| `--stock` | `str` | 否 | `None` | `-` | 股票代码（如 002594、600519） |
| `--keywords` | `str` | 否 | `None` | `-` | 关键词，逗号分隔（如 资产重组,回购） |
| `--days` | `int` | 否 | `7` | `-` | 最近 N 天（默认: 7） |
| `--output_dir` | `str` | 否 | `./data` | `-` | 输出目录（默认: ./data） |
| `--include_cctv` | `bool` | 否 | `false` | `-` | 是否包含央视新闻 |

**示例**：

```powershell
python news_fetcher.py --stock 600519 --days 7
python news_fetcher.py --stock 002594 --keywords 资产重组,回购 --days 30
python news_fetcher.py --keywords 白酒 --days 7 --include_cctv
```

### `sentiment_scorer.py`

**路径**：`skills/sentiment-analysis/scripts/sentiment_scorer.py`<br>
**功能**：LLM 情感分析评分器

| 参数 | 类型 | 必需 | 默认值 | 可选值 | 说明 |
|---|---|---:|---|---|---|
| `--news_file` | `str` | 是 | `None` | `-` | 新闻 JSON 文件路径 |
| `--output_dir` | `str` | 否 | `./output` | `-` | 输出目录（默认: ./output） |
| `--model` | `str` | 否 | `qwen-turbo` | `-` | LLM 模型（默认: qwen-turbo） |
| `--max_news` | `int` | 否 | `50` | `-` | 最大分析条数（默认: 50） |

**示例**：

```powershell
python sentiment_scorer.py --news_file data/002594_news.json --output_dir output/
python sentiment_scorer.py --news_file data/资产重组_news.json --max_news 30
python sentiment_scorer.py --news_file data/600519_news.json --model qwen-plus
```

### `event_detector.py`

**路径**：`skills/sentiment-analysis/scripts/event_detector.py`<br>
**功能**：事件识别与交易信号生成器

| 参数 | 类型 | 必需 | 默认值 | 可选值 | 说明 |
|---|---|---:|---|---|---|
| `--news_file` | `str` | 是 | `None` | `-` | 新闻 JSON 文件路径 |
| `--output_dir` | `str` | 否 | `./output` | `-` | 输出目录（默认: ./output） |
| `--model` | `str` | 否 | `qwen-turbo` | `-` | LLM 模型（默认: qwen-turbo） |
| `--use_llm` | `bool` | 否 | `false` | `-` | 使用 LLM 进行精细事件识别（较慢但更准确） |

**示例**：

```powershell
python event_detector.py --news_file data/002594_news.json --output_dir output/
python event_detector.py --news_file data/资产重组_news.json --use_llm
python event_detector.py --news_file data/600519_news.json --model qwen-plus --use_llm
```

## compare-reports

跨期和跨公司报告比较

### `cross_period.py`

**路径**：`skills/compare-reports/scripts/cross_period.py`<br>
**功能**：跨期对比分析工具

| 参数 | 类型 | 必需 | 默认值 | 可选值 | 说明 |
|---|---|---:|---|---|---|
| `--stock` | `str` | 是 | `None` | `-` | 股票代码（如 688981） |
| `--topics` | `str` | 否 | `营收,净利润,毛利率,经营情况` | `-` | 对比维度（逗号分隔，默认: 营收,净利润,毛利率,经营情况） |
| `--index_dir` | `str` | 否 | `data/vector_db` | `-` | 统一索引目录（默认: data/vector_db） |
| `--model` | `str` | 否 | `qwen-plus` | `-` | LLM 模型（默认: qwen-plus） |
| `--top_k` | `int` | 否 | `8` | `-` | 每个维度检索的文档数（默认: 8） |

**示例**：

```powershell
python cross_period.py --stock 688981 --topics '营收,净利润,毛利率'
python cross_period.py --stock 600519 --topics '经营情况' --index_dir data/vector_store
python cross_period.py --stock 002594 --topics '研发投入,毛利率' --model qwen-plus
```

### `cross_company.py`

**路径**：`skills/compare-reports/scripts/cross_company.py`<br>
**功能**：跨公司对比分析工具

| 参数 | 类型 | 必需 | 默认值 | 可选值 | 说明 |
|---|---|---:|---|---|---|
| `--stocks` | `str` | 是 | `None` | `-` | 股票代码（逗号分隔，如 688981,600519） |
| `--topic` | `str` | 否 | `经营状况和盈利能力` | `-` | 对比主题（默认: 经营状况和盈利能力） |
| `--index_dir` | `str` | 否 | `data/vector_db` | `-` | 统一索引目录（默认: data/vector_db） |
| `--model` | `str` | 否 | `qwen-plus` | `-` | LLM 模型（默认: qwen-plus） |
| `--top_k` | `int` | 否 | `6` | `-` | 每家公司检索的文档数（默认: 6） |

**示例**：

```powershell
python cross_company.py --stocks 688981,600519 --topic '经营状况和盈利能力'
python cross_company.py --stocks 688981,600519 --topic '核心竞争力' --index_dir data/vector_store
python cross_company.py --stocks 002594,300750 --topic '研发投入和技术实力' --model qwen-plus
```

## write-report

五步法分析和报告生成

### `five_step_analysis.py`

**路径**：`skills/write-report/scripts/five_step_analysis.py`<br>
**功能**：国泰君安"五步法"分析引擎

| 参数 | 类型 | 必需 | 默认值 | 可选值 | 说明 |
|---|---|---:|---|---|---|
| `--index_dir` | `str` | 是 | `None` | `-` | FAISS 索引目录 |
| `--stock_name` | `str` | 是 | `None` | `-` | 公司名称（如：贵州茅台） |
| `--output_dir` | `str` | 否 | `./output` | `-` | 输出目录（默认: ./output） |
| `--model` | `str` | 否 | `deepseek-v3` | `-` | LLM 模型（默认: deepseek-v3） |
| `--focus` | `str` | 否 | `None` | `information_gap, logic_gap, expectation_gap, catalyst, conclusion, 信息差, 逻辑差, 预期差, 催化剂, 结论` | 聚焦某个步骤深入分析 |

**示例**：

```powershell
python five_step_analysis.py --index_dir data/vector_db --stock_name 贵州茅台
python five_step_analysis.py --index_dir data/vector_db --stock_name 贵州茅台 --output_dir output/
python five_step_analysis.py --index_dir data/vector_db --stock_name 贵州茅台 --focus catalyst
```

### `report_generator.py`

**路径**：`skills/write-report/scripts/report_generator.py`<br>
**功能**：研报生成器

| 参数 | 类型 | 必需 | 默认值 | 可选值 | 说明 |
|---|---|---:|---|---|---|
| `--analysis_file` | `str` | 是 | `None` | `-` | 五步法分析结果 JSON 文件 |
| `--output_dir` | `str` | 否 | `./output/reports` | `-` | 研报输出目录（默认: ./output/reports） |

**示例**：

```powershell
python report_generator.py --analysis_file output/贵州茅台_analysis.json
python report_generator.py --analysis_file output/贵州茅台_analysis.json --output_dir output/reports/
```

## stock-price

MiniQMT 行情和 K 线数据

### `get_kline.py`

**路径**：`skills/stock-price/scripts/get_kline.py`<br>
**功能**：MiniQMT K 线数据获取脚本

| 参数 | 类型 | 必需 | 默认值 | 可选值 | 说明 |
|---|---|---:|---|---|---|
| `--stock` | `str` | 是 | `None` | `-` | 股票代码（如 000001.SZ, 600519.SH） |
| `--period` | `str` | 否 | `1d` | `-` | K 线周期（默认: 1d，支持: 1m,5m,15m,30m,1h,1d,1w,1mon） |
| `--count` | `int` | 否 | `100` | `-` | 获取条数（默认: 100） |

**示例**：

```powershell
python get_kline.py --stock 000001.SZ
python get_kline.py --stock 600519.SH --period 1d --count 200
python get_kline.py --stock 000858.SZ --period 1w --count 52
```

## web-search

联网市场、新闻和政策搜索

### `search_market.py`

**路径**：`skills/web-search/scripts/search_market.py`<br>
**功能**：联网搜索工具 - 通过 qwen enable_search 获取实时市场信息

| 参数 | 类型 | 必需 | 默认值 | 可选值 | 说明 |
|---|---|---:|---|---|---|
| `--query` | `str` | 是 | `None` | `-` | 搜索查询 |
| `--type` | `str` | 否 | `general` | `stock, news, policy, general` | 搜索类型（默认: general）- stock=个股行情, news=财经新闻, policy=政策法规, general=通用搜索 |
| `--model` | `str` | 否 | `qwen-plus` | `-` | 模型（默认: qwen-plus） |
| `--output` | `str` | 否 | `None` | `-` | 结果保存路径（可选） |

**示例**：

```powershell
python search_market.py --query '贵州茅台最新股价' --type stock
python search_market.py --query '半导体行业政策' --type policy
python search_market.py --query '中芯国际分析师评级' --type general --output output/search_result.json
```

## 相关文档

- [README.md](../README.md) - 项目快速开始
- [SKILL.md](../SKILL.md) - Skill 契约和接口规范
- [故障排查](TROUBLESHOOTING.md)
