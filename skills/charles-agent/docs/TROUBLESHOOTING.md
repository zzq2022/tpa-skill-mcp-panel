# Charles Skill 故障排查

## 先运行预检

```powershell
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$python = "<python.exe绝对路径>"
& $python runtime/preflight.py --skip-api
```

需要同时测试 LLM 和 Embedding 连通性时去掉 `--skip-api`。

## PowerShell 路径或中文乱码

症状：可执行文件路径包含空格导致命令无法启动，或 CLI 中文输出乱码。

处理：使用上面的 UTF-8 设置和调用运算符 `&`。命令参数使用独立字符串，不要拼接整条命令，也不要从表格输出复制被截断的路径。

## 缺少 Python 包

```powershell
& $python -m pip install -r requirements-tpa-skill.txt
& $python runtime/preflight.py --skip-api
```

行情脚本的 `xtquant` 由 MiniQMT 提供，不在公共依赖文件中。

## API 或模型不可用

检查 `.env` 中对应服务的 Key、Base URL 和模型名。不要在日志或对话中输出 Key。只有某个子 Skill 依赖的服务不可用时，将该子 Skill 标为 `unavailable`；继续完成不依赖它的步骤。

## PDF 无文本或乱码

1. 先运行 `parse_pdf_basic.py`。
2. 如果返回 `partial`、空文本或乱码占比高，按 `read-pdf` 内部流程运行 `parse_pdf_ocr.py`。
3. 检查输出页码映射和原文摘录后再建索引。

不得把空文本、无页码摘要或 OCR 未核验内容标为完整 evidence。

## CLI 参数错误

```powershell
& $python skills/read-pdf/scripts/parse_pdf_basic.py --help
& $python skills/financial-analysis/scripts/ratio_analysis.py --help
& $python scripts/generate_cli_reference.py --check
```

参数以脚本 `--help` 和 [CLI_REFERENCE.md](CLI_REFERENCE.md) 为准。文档检查失败时重新运行生成器。

## 数据或期间缺失

- 用户指定期间缺失：返回 `partial` 或 `unavailable`，不能用旧期间替代。
- 一致预期缺失：预期差为 `unavailable`，不能用低估猜测替代。
- 行情没有时间戳：不能作为实时 evidence。
- 比较索引未覆盖全部对象：列出不可比项，不使用其他公司补齐。

## 报告不完整

`write-report` 应保留已经验证的章节，将缺失章节标为 `unavailable`，并列出 `warnings`、`errors` 和 `next_actions`。报告不能把子 Skill 的失败包装成成功。
