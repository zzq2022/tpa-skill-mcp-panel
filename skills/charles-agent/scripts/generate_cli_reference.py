#!/usr/bin/env python3
"""Generate the child-skill CLI reference from argparse source definitions."""

from __future__ import annotations

import argparse
import ast
from pathlib import Path
from typing import Any


SCRIPT_REGISTRY = (
    ("read-pdf", (
        "skills/read-pdf/scripts/fetch_financial_data.py",
        "skills/read-pdf/scripts/preprocess.py",
        "skills/read-pdf/scripts/query_report.py",
    )),
    ("financial-analysis", (
        "skills/financial-analysis/scripts/ratio_analysis.py",
        "skills/financial-analysis/scripts/peer_compare.py",
    )),
    ("sentiment-analysis", (
        "skills/sentiment-analysis/scripts/news_fetcher.py",
        "skills/sentiment-analysis/scripts/sentiment_scorer.py",
        "skills/sentiment-analysis/scripts/event_detector.py",
    )),
    ("compare-reports", (
        "skills/compare-reports/scripts/cross_period.py",
        "skills/compare-reports/scripts/cross_company.py",
    )),
    ("write-report", (
        "skills/write-report/scripts/five_step_analysis.py",
        "skills/write-report/scripts/report_generator.py",
    )),
    ("stock-price", ("skills/stock-price/scripts/get_kline.py",)),
    ("web-search", ("skills/web-search/scripts/search_market.py",)),
)

RUNTIME_ENTRIES = (
    "runtime/preflight.py",
)

GROUP_DESCRIPTIONS = {
    "read-pdf": "财报下载、解析、索引和 RAG 查询",
    "financial-analysis": "财务指标和同业分析",
    "sentiment-analysis": "新闻、情绪和事件分析",
    "compare-reports": "跨期和跨公司报告比较",
    "write-report": "五步法分析和报告生成",
    "stock-price": "MiniQMT 行情和 K 线数据",
    "web-search": "联网市场、新闻和政策搜索",
}


def _literal(node: ast.AST | None) -> Any:
    if node is None:
        return None
    try:
        return ast.literal_eval(node)
    except (ValueError, TypeError, SyntaxError):
        return ast.unparse(node)


def _keyword(call: ast.Call, name: str) -> ast.AST | None:
    for keyword in call.keywords:
        if keyword.arg == name:
            return keyword.value
    return None


def _type_name(node: ast.AST | None) -> str:
    if node is None:
        return "str"
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ast.unparse(node)


class _ParserInspector(ast.NodeVisitor):
    def __init__(self) -> None:
        self.arguments: list[dict[str, Any]] = []
        self.examples: list[str] = []

    def visit_Call(self, node: ast.Call) -> None:
        function = node.func
        if isinstance(function, ast.Attribute) and function.attr == "add_argument":
            values = [
                value
                for value in (_literal(argument) for argument in node.args)
                if isinstance(value, str)
            ]
            flags = [value for value in values if value.startswith("-")]
            if flags or values:
                choices = _literal(_keyword(node, "choices"))
                if isinstance(choices, tuple):
                    choices = list(choices)
                self.arguments.append({
                    "flags": flags or values,
                    "required": bool(_literal(_keyword(node, "required"))),
                    "default": _literal(_keyword(node, "default")),
                    "has_default": _keyword(node, "default") is not None,
                    "type": _type_name(_keyword(node, "type")),
                    "choices": choices if isinstance(choices, list) else None,
                    "action": _literal(_keyword(node, "action")),
                    "help": _literal(_keyword(node, "help")) or "",
                })
        if isinstance(function, ast.Name) and function.id == "CLIHelper":
            examples = _literal(_keyword(node, "examples"))
            if isinstance(examples, list):
                self.examples.extend(value for value in examples if isinstance(value, str))
        self.generic_visit(node)


def inspect_script(path: Path) -> dict[str, Any]:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    inspector = _ParserInspector()
    inspector.visit(tree)
    description = (ast.get_docstring(tree) or "").strip().splitlines()
    return {
        "path": path,
        "name": path.name,
        "description": description[0].strip() if description else path.stem,
        "arguments": inspector.arguments,
        "examples": inspector.examples,
    }


def _display(value: Any) -> str:
    if value is None:
        return "None"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple)):
        return ", ".join(str(item) for item in value)
    return str(value)


def _render_script(project_root: Path, path: Path) -> str:
    info = inspect_script(path)
    relative = path.relative_to(project_root).as_posix()
    lines = [
        f"### `{info['name']}`",
        "",
        f"**路径**：`{relative}`<br>",
        f"**功能**：{info['description']}",
        "",
        "| 参数 | 类型 | 必需 | 默认值 | 可选值 | 说明 |",
        "|---|---|---:|---|---|---|",
    ]
    for argument in info["arguments"]:
        flags = ", ".join(f"`{flag}`" for flag in argument["flags"])
        required = "是" if argument["required"] else "否"
        default = _display(argument["default"]) if argument["has_default"] else "None"
        choices = _display(argument["choices"]) if argument["choices"] else "-"
        help_text = str(argument["help"]).replace("|", "\\|").replace("\n", " ")
        if argument["action"] == "store_true" or str(argument["action"]).endswith("BooleanOptionalAction"):
            type_name = "bool"
            if argument["action"] == "store_true":
                default = "false"
        else:
            type_name = argument["type"]
        lines.append(f"| {flags} | `{type_name}` | {required} | `{default}` | `{choices}` | {help_text} |")
    if info["examples"]:
        lines.extend(["", "**示例**：", "", "```powershell"])
        lines.extend(info["examples"])
        lines.extend(["```"])
    lines.append("")
    return "\n".join(lines)


def _render_runtime(project_root: Path) -> str:
    lines = ["## 环境预检", "", "预检参数由 `runtime/preflight.py` 的 argparse 定义生成：", ""]
    for relative in RUNTIME_ENTRIES:
        path = project_root / relative
        if not path.is_file():
            continue
        lines.append(_render_script(project_root, path))
    return "\n".join(lines)


def _render_windows_execution() -> str:
    return "\n".join([
        "## Windows 安全调用",
        "",
        "可执行文件路径包含空格时，在 PowerShell 中使用调用运算符 `&`，并显式设置 UTF-8：",
        "",
        "```powershell",
        "$env:PYTHONUTF8 = \"1\"",
        "$env:PYTHONIOENCODING = \"utf-8\"",
        "[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)",
        "$python = '<python.exe绝对路径>'",
        "& $python runtime/preflight.py",
        "& $python skills/read-pdf/scripts/parse_pdf_basic.py --pdf '<报告PDF>' --output_dir '<输出目录>'",
        "```",
        "",
        "子 Skill 通过明确的 artifact 路径交接；不要从 PowerShell 表格输出猜测或截断路径。",
        "",
    ])


def _render_environment_loading() -> str:
    return "\n".join([
        "## 环境配置",
        "",
        "读取模型或 API 配置的子 Skill CLI 会在独立进程中自行加载 Skill 根目录 `.env`。调用方无需先运行预检来传递变量，也无需生成 PowerShell 或 Python 包装脚本。操作系统中已存在的环境变量优先于 `.env`。",
        "",
    ])


def render_reference(project_root: Path) -> str:
    root = project_root.resolve()
    lines = [
        "# Charles Skill CLI 参数参考",
        "",
        "> 本文由 `scripts/generate_cli_reference.py` 根据脚本中的 `argparse` 定义生成。参数、默认值和可选值以源码为准。",
        "",
        "## 目录",
        "",
        "- [Windows 安全调用](#windows-安全调用)",
        "- [环境配置](#环境配置)",
        "- [环境预检](#环境预检)",
    ]
    for group, _ in SCRIPT_REGISTRY:
        lines.append(f"- [{group}](#{group})")
    lines.extend([
        "",
        _render_windows_execution(),
        _render_environment_loading(),
        _render_runtime(root),
    ])
    for group, scripts in SCRIPT_REGISTRY:
        lines.extend([f"## {group}", "", GROUP_DESCRIPTIONS[group], ""])
        for relative in scripts:
            lines.append(_render_script(root, root / relative))
    lines.extend([
        "## 相关文档",
        "",
        "- [README.md](../README.md) - 项目快速开始",
        "- [SKILL.md](../SKILL.md) - Skill 契约和接口规范",
        "- [故障排查](TROUBLESHOOTING.md)",
        "",
    ])
    return "\n".join(lines)


def generate_reference(project_root: Path, output: Path) -> str:
    content = render_reference(project_root)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content, encoding="utf-8", newline="\n")
    return content


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("docs/CLI_REFERENCE.md"))
    parser.add_argument("--check", action="store_true", help="检查文档是否与当前 parser 定义一致")
    args = parser.parse_args(argv)
    project_root = Path(__file__).resolve().parents[1]
    output = args.output if args.output.is_absolute() else project_root / args.output
    content = render_reference(project_root)
    if args.check:
        if not output.is_file() or output.read_text(encoding="utf-8") != content:
            print(f"CLI reference is stale: {output}")
            return 1
        print(f"CLI reference is up to date: {output}")
        return 0
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content, encoding="utf-8", newline="\n")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
