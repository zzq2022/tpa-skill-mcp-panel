# Charles 五步法投研 Skill

Charles 是一组面向宿主 Agent 的投研 Skills。根 `SKILL.md` 定义五步法顺序，各子 `SKILL.md` 定义自身输入、内部 CLI 流程、输出和降级规则。

项目不提供独立 Agent 或 Python 固化 pipeline。TPA CoWork 等宿主读取 Skill 文档后，直接调用现有业务脚本。

## 安装

```powershell
pip install -r requirements-tpa-skill.txt
Copy-Item .env.example .env
python runtime/preflight.py --skip-api
```

`.env` 配置 LLM、Embedding 和搜索服务。发布包不包含 `.env`，升级安装时必须保留用户已有配置。

基础 PDF 使用 PyMuPDF 文本提取；复杂扫描件可按 `read-pdf` 内部流程改用 OCR。MiniQMT 行情需要额外安装供应商提供的 `xtquant` 并保持客户端登录。

## 使用方式

1. 宿主读取根 [SKILL.md](SKILL.md)，确认研究对象、代码、期间和输出要求。
2. 根 Skill 按五步法加载对应子 Skill。
3. 子 Skill 根据内部流程选择脚本，并从 [CLI 参数参考](docs/CLI_REFERENCE.md) 确认参数。
4. 宿主直接执行 CLI，把结果信封和 artifact 路径交回根 Skill。
5. `write-report` 只消费前四步产物，生成 Markdown 和按需生成 HTML。

| 步骤 | 子 Skill | 主要产物 |
|---|---|---|
| 信息差 | `read-pdf`、`web-search` | 页码 evidence、外部 URL evidence |
| 逻辑差 | `financial-analysis`、`compare-reports` | 财务 analysis、跨期/同业 comparison |
| 预期差 | `stock-price`、`web-search` | 带时间戳行情、一致预期或指引 |
| 催化剂与情绪 | `sentiment-analysis`，按需补充 `web-search` | 新闻、情绪、事件 analysis |
| 结论与风险 | `write-report` | Markdown、HTML、结构化报告 |

## PowerShell CLI

路径包含空格时使用调用运算符 `&`，并显式设置 UTF-8：

```powershell
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$python = "D:\apps\TPA CoWork\agent-venv\Scripts\python.exe"

& $python runtime/preflight.py --skip-api
& $python skills/read-pdf/scripts/parse_pdf_basic.py --pdf "D:\reports\annual.pdf" --output_dir "D:\research\data"
& $python skills/financial-analysis/scripts/ratio_analysis.py --stock 600036 --years 5 --data_dir "D:\research\data\financial_data"
```

所有脚本都支持 `--help`。不要从 PowerShell 表格输出复制可能被截断的路径；使用脚本返回的明确 artifact 路径。

## 子 Skill

| Skill | 内部能力 |
|---|---|
| [read-pdf](skills/read-pdf/SKILL.md) | 下载财务数据、解析 PDF、建索引、RAG 查询 |
| [financial-analysis](skills/financial-analysis/SKILL.md) | 财务指标和同口径同业指标 |
| [compare-reports](skills/compare-reports/SKILL.md) | 跨期和跨公司报告比较 |
| [stock-price](skills/stock-price/SKILL.md) | MiniQMT K 线和行情 |
| [web-search](skills/web-search/SKILL.md) | 市场、新闻、政策和一致预期搜索 |
| [sentiment-analysis](skills/sentiment-analysis/SKILL.md) | 新闻抓取、情绪评分和事件检测 |
| [write-report](skills/write-report/SKILL.md) | 验证上游证据并生成五步法报告 |

公共 artifact 与 evidence 字段见 [子 Skill 交接契约](skills/_common/SKILL_CONTRACT.md)。

## CLI 文档

`docs/CLI_REFERENCE.md` 由每个脚本的 `argparse` 定义生成：

```powershell
python scripts/generate_cli_reference.py
python scripts/generate_cli_reference.py --check
```

脚本参数变更后必须重新生成并执行 `--check`。详细排查步骤见 [TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)。

## 目录

```text
charles-agent/
├── SKILL.md
├── requirements-tpa-skill.txt
├── runtime/
│   ├── env_loader.py
│   └── preflight.py
├── common/
├── skills/
│   ├── _common/SKILL_CONTRACT.md
│   └── <child-skill>/
│       ├── SKILL.md
│       └── scripts/
├── docs/CLI_REFERENCE.md
└── scripts/
    ├── build_release.py
    └── generate_cli_reference.py
```
