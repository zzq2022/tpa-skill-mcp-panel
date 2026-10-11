#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
研报生成器

功能：将五步法分析结果组装为完整的 Markdown 格式深度研报。
包含封面信息、目录、五步分析内容、风险提示和免责声明。

用法：
    python report_generator.py --analysis_file <分析结果JSON> --output_dir <输出目录>
    python report_generator.py --analysis_file output/贵州茅台_analysis.json --output_dir output/reports/
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

# 从 skill 内部 lib 导入
sys.path.insert(0, str(Path(__file__).parent.parent / 'lib'))
from formatters import write_report_bundle

# 添加 common 目录到 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'common'))
from error_handler import SkillError, format_error_message
from logger import SkillLogger, LogLevel
from cli_helper import CLIHelper

# 初始化日志
logger = SkillLogger("report_generator", level=LogLevel.INFO)


# 研报 Markdown 模板
REPORT_TEMPLATE = """# {stock_name} - 深度分析报告

> **分析框架**: 国泰君安"五步法"  
> **生成时间**: {analysis_date}  
> **分析模型**: {model}  
> **数据来源**: 公司财报 (来源页码: {source_pages})

---

## 章节证据状态

| 五步 | 证据状态 | 已用证据 | 缺口及影响 |
|---|---|---|---|
{evidence_matrix}

---

## 目录

1. [信息差分析](#1-信息差分析)
2. [逻辑差分析](#2-逻辑差分析)
3. [预期差分析](#3-预期差分析)
4. [催化剂识别](#4-催化剂识别)
5. [投资结论](#5-投资结论)
6. [风险提示](#6-风险提示)
7. [免责声明](#7-免责声明)

---

{steps_content}

---

## 6. 风险提示

- 本报告基于公开财报数据和 AI 分析生成，分析结论可能存在偏差
- 财报数据具有滞后性，不代表公司当前经营状况
- 市场环境变化可能导致分析假设不再成立
- 行业政策调整可能对公司经营产生重大影响
- AI 模型的分析能力有限，无法完全替代专业分析师的判断

---

## 7. 免责声明

本报告由 AI 投研助手 Charles 自动生成，仅供学习和研究参考，**不构成任何投资建议**。

- 报告内容基于公开信息和 AI 分析，不保证信息的准确性和完整性
- 投资者据此操作，风险自担
- 报告作者不对任何投资损失承担责任
- 在做出投资决策前，建议咨询专业投资顾问

---

*报告生成于 {generation_time}*
"""

# 每个步骤的章节模板
STEP_SECTION_TEMPLATE = """## {step_num}. {step_title}

> 数据来源页码: {source_pages}

{analysis}

"""

# 步骤名称到章节标题的映射
STEP_TITLES = {
    "信息差": "信息差分析",
    "逻辑差": "逻辑差分析",
    "预期差": "预期差分析",
    "催化剂": "催化剂识别",
    "结论": "投资结论",
}

VALID_EVIDENCE_STATUSES = {"available", "partial", "unavailable"}
CONSENSUS_SOURCE_TYPES = {"consensus", "guidance"}
ALLOWED_SOURCE_TYPES = {"filing", "market", "consensus", "guidance", "news"}
CHAPTER_DEFS = [
    (1, "信息差", "information_gap"),
    (2, "逻辑差", "logic_gap"),
    (3, "预期差", "expectation_gap"),
    (4, "催化剂", "catalyst"),
    (5, "结论", "conclusion"),
]
STATUS_RANK = {"unavailable": 0, "partial": 1, "available": 2}
OPERATIONAL_PHRASES = ("买入", "买点", "安全边际", "适合配置")
VALUATION_EVIDENCE_FIELDS = (
    "target_price",
    "historical_valuation_percentile",
    "risk_reward_ratio",
)


def _valid_evidence(records: list) -> list[dict]:
    return [
        record for record in records
        if (
            isinstance(record, dict)
            and str(record.get("locator") or "").strip()
            and str(record.get("source_type") or "").lower() in ALLOWED_SOURCE_TYPES
            and str(record.get("confidence") or "").lower() in {"high", "medium", "low"}
            and (
                str(record.get("source_type") or "").lower() not in {"filing", "consensus", "guidance"}
                or str(record.get("period") or "").strip()
            )
            and (
                str(record.get("source_type") or "").lower() not in {"market", "consensus", "guidance", "news"}
                or str(record.get("as_of") or "").strip()
            )
        )
    ]


def evaluate_evidence(analysis: dict) -> dict:
    """Evaluate chapter evidence without upgrading unsupported claims."""
    input_steps = {
        str(step.get("name_en") or ""): step
        for step in analysis.get("steps") or []
        if isinstance(step, dict)
    }
    chapters = []
    for number, default_name, name_en in CHAPTER_DEFS:
        step = input_steps.get(name_en) or {
            "step": number,
            "name": default_name,
            "name_en": name_en,
            "analysis": "",
            "evidence": [],
        }
        name_en = str(step.get("name_en") or "")
        records = _valid_evidence(list(step.get("evidence") or []))
        source_types = {str(record.get("source_type") or "").lower() for record in records}
        declared = str(step.get("evidence_status") or "").lower()
        status = "available" if records else "unavailable"
        limitations = list(step.get("limitations") or [])

        if not records:
            status = "unavailable"
            limitations.append("没有可定位的 evidence record")
        elif name_en == "expectation_gap" and not (source_types & CONSENSUS_SOURCE_TYPES):
            status = "unavailable"
            limitations.append("缺少同期间、同口径的一致预期或公司指引")
        elif name_en == "information_gap" and source_types and source_types <= {"filing"}:
            status = "partial"
            limitations.append("只有公司材料，无法验证市场关注程度")
        elif name_en == "catalyst" and source_types and source_types <= {"filing"}:
            status = "partial"
            limitations.append("缺少外部事件或公告时点交叉验证")

        if declared in VALID_EVIDENCE_STATUSES and STATUS_RANK[declared] < STATUS_RANK[status]:
            status = declared

        chapters.append({
            "step": step.get("step") or number,
            "name": STEP_TITLES.get(str(step.get("name") or ""), str(step.get("name") or name_en)),
            "name_en": name_en,
            "status": status,
            "evidence": records,
            "limitations": list(dict.fromkeys(limitations)),
        })

    critical = [item["status"] for item in chapters if item["name_en"] != "conclusion"]
    conclusion = next((item for item in chapters if item["name_en"] == "conclusion"), None)
    if conclusion and critical and any(status != "available" for status in critical):
        conclusion["status"] = "partial" if any(status != "unavailable" for status in critical) else "unavailable"
        conclusion["limitations"].append("结论强度受前序章节证据缺口限制")

    statuses = [item["status"] for item in chapters]
    if statuses and all(status == "available" for status in statuses):
        overall = "success"
    elif any(status in {"available", "partial"} for status in statuses):
        overall = "partial"
    else:
        overall = "unavailable"
    return {"status": overall, "chapters": chapters}


def _evidence_matrix(evaluation: dict) -> str:
    rows = []
    for chapter in evaluation["chapters"]:
        locators = [str(item["locator"]) for item in chapter["evidence"][:3]]
        evidence = "<br>".join(locators) if locators else "无"
        limitations = "；".join(chapter["limitations"]) if chapter["limitations"] else "无"
        rows.append(f"| {chapter['name']} | {chapter['status']} | {evidence} | {limitations} |")
    return "\n".join(rows)


def _has_operational_basis(evaluation: dict) -> bool:
    critical_chapters = [
        chapter for chapter in evaluation["chapters"]
        if chapter["name_en"] != "conclusion"
    ]
    records = [
        record for chapter in evaluation["chapters"]
        for record in chapter["evidence"]
    ]
    has_market_evidence = any(record.get("source_type") == "market" for record in records)
    has_valuation_evidence = any(
        record.get(field) not in (None, "")
        for record in records
        for field in VALUATION_EVIDENCE_FIELDS
    )
    return (
        all(chapter["status"] == "available" for chapter in critical_chapters)
        and has_market_evidence
        and has_valuation_evidence
    )


def _constrain_conclusion_language(text: str, valuation_evidence_available: bool) -> str:
    if valuation_evidence_available or not any(phrase in text for phrase in OPERATIONAL_PHRASES):
        return text
    return "操作性判断已省略：缺少可验证的最新行情与估值证据。"


def load_analysis(analysis_file: str) -> dict:
    """加载五步法分析结果"""
    try:
        with open(analysis_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        raise SkillError(
            operation="加载分析文件",
            reason=f"文件读取失败: {e}",
            next_action="请检查文件路径和格式是否正确"
        )


def generate_report(analysis: dict) -> str:
    """
    将分析结果组装为 Markdown 研报。

    Args:
        analysis: 五步法分析结果（来自 five_step_analysis.py 的输出）

    Returns:
        完整的 Markdown 格式研报
    """
    stock_name = analysis["stock_name"]
    analysis_date = analysis["analysis_date"]
    model = analysis["model"]
    all_pages = analysis.get("all_source_pages", [])
    evaluation = evaluate_evidence(analysis)

    # 生成各步骤章节，包括因上游失败而缺失的章节。
    steps_content = ""
    input_steps = {
        str(step.get("name_en") or ""): step
        for step in analysis.get("steps") or []
        if isinstance(step, dict)
    }
    failed_step = analysis.get("failed_step") or {}
    chapter_by_name = {item["name_en"]: item for item in evaluation["chapters"]}
    for step_num, step_name, name_en in CHAPTER_DEFS:
        step_data = input_steps.get(name_en)
        step_title = STEP_TITLES.get(step_name, step_name)
        if step_data:
            step_analysis = step_data.get("analysis") or "本步骤未生成分析内容。"
            if name_en == "conclusion":
                step_analysis = _constrain_conclusion_language(
                    step_analysis,
                    _has_operational_basis(evaluation),
                )
            step_pages = step_data.get("source_pages", [])
        else:
            chapter = chapter_by_name[name_en]
            step_analysis = f"> 证据状态: {chapter['status']}\n\n本步骤未完成。"
            if str(failed_step.get("name_en") or "") == name_en:
                step_analysis += (
                    f"\n\n失败原因: {failed_step.get('error_type', 'Error')}: "
                    f"{failed_step.get('error_message', 'unknown error')}"
                )
            step_pages = []

        section = STEP_SECTION_TEMPLATE.format(
            step_num=step_num,
            step_title=step_title,
            source_pages=", ".join(str(p) for p in step_pages) if step_pages else "未标注",
            analysis=step_analysis,
        )
        steps_content += section

    # 组装完整报告
    report = REPORT_TEMPLATE.format(
        stock_name=stock_name,
        analysis_date=analysis_date,
        model=model,
        source_pages=", ".join(str(p) for p in all_pages) if all_pages else "未标注",
        evidence_matrix=_evidence_matrix(evaluation),
        steps_content=steps_content,
        generation_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )

    return report


def save_report_bundle(report: str, stock_code: str, output_dir: str) -> dict:
    """Save a deterministic ASCII-named Markdown and HTML bundle."""
    return write_report_bundle(Path(output_dir), report, f"{stock_code} 深度分析报告")


def main():
    # 创建 CLI 助手
    cli = CLIHelper(
        script_name="report_generator.py",
        description="研报生成器 - 将五步法分析结果组装为完整的 Markdown/HTML 研报",
        examples=[
            "python report_generator.py --analysis_file output/贵州茅台_analysis.json",
            "python report_generator.py --analysis_file output/贵州茅台_analysis.json --output_dir output/reports/",
        ]
    )

    parser = argparse.ArgumentParser(
        description=cli.description,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=cli.format_examples()
    )

    parser.add_argument("--analysis_file", required=True, help="五步法分析结果 JSON 文件")
    parser.add_argument("--output_dir", default="./output/reports", help="研报输出目录（默认: ./output/reports）")
    args = parser.parse_args()

    try:
        if not os.path.exists(args.analysis_file):
            raise SkillError(
                operation="检查分析文件",
                reason=f"分析文件不存在: {args.analysis_file}",
                next_action="请先运行 five_step_analysis.py 生成分析结果"
            )

        logger.info("生成深度分析研报")

        # 加载分析结果
        analysis = load_analysis(args.analysis_file)
        evaluation = evaluate_evidence(analysis)
        stock_name = analysis["stock_name"]
        logger.info(f"目标公司: {stock_name}")
        logger.info(f"分析步骤: {len(analysis['steps'])} 步")

        # 生成报告
        report = generate_report(analysis)
        logger.info(f"研报生成完成，共 {len(report)} 字符")

        # 保存报告
        artifacts = save_report_bundle(report, str(analysis.get("stock_code", stock_name)), args.output_dir)
        logger.info(f"Markdown: {artifacts['markdown']}")
        logger.info(f"HTML: {artifacts['html']}")

        result = {
            "status": evaluation["status"],
            "module": "report",
            "summary": {
                "stock_name": stock_name,
                "report_length": len(report),
                "steps_included": len(analysis["steps"]),
                "chapter_evidence": evaluation["chapters"],
            },
            "artifacts": [
                {"role": "report-markdown", "module": "report", "path": artifacts["markdown"]},
                {"role": "report-html", "module": "report", "path": artifacts["html"]},
            ],
            "sources": [{"type": "analysis-file", "path": args.analysis_file}],
            "warnings": [
                limitation
                for chapter in evaluation["chapters"]
                for limitation in chapter["limitations"]
            ],
            "errors": [],
            "next_actions": [],
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        sys.exit(0)

    except SkillError as e:
        print(format_error_message(e), file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        error = SkillError(
            operation="生成研报",
            reason=f"未预期的错误: {type(e).__name__}: {e}",
            next_action="请检查分析文件格式或输出目录权限"
        )
        print(format_error_message(error), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
