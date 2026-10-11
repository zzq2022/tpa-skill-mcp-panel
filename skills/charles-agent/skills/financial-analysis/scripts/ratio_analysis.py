#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
核心财务指标分析工具

功能: 从 akshare 获取的财务摘要 CSV 中提取核心指标，
     分析多年趋势，生成结构化的财务健康状况报告。

用法:
    python ratio_analysis.py --stock 600519
    python ratio_analysis.py --stock 600519 --years 3
    python ratio_analysis.py --stock 688981 --data_dir data/financial_data
"""

import argparse
import json
import os
import sys
from pathlib import Path

import pandas as pd

# 添加 common 目录到 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'common'))
from error_handler import SkillError, format_error_message
from logger import SkillLogger, LogLevel
from cli_helper import CLIHelper

# 初始化日志
logger = SkillLogger("ratio_analysis", level=LogLevel.INFO)

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

# 从 skill 内部 lib 导入
sys.path.insert(0, str(Path(__file__).parent.parent / 'lib'))
from metrics import (
    detect_industry,
    extract_period_metrics,
    select_comparison_columns,
)


# 需要提取的核心指标及其中文名
CORE_METRICS = {
    "营业总收入": {"unit": "亿元", "scale": 1e8, "category": "规模"},
    "归母净利润": {"unit": "亿元", "scale": 1e8, "category": "规模"},
    "毛利率": {"unit": "%", "scale": 1, "category": "盈利"},
    "销售净利率": {"unit": "%", "scale": 1, "category": "盈利"},
    "净资产收益率(ROE)": {"unit": "%", "scale": 1, "category": "盈利"},
    "总资产报酬率(ROA)": {"unit": "%", "scale": 1, "category": "盈利"},
    "资产负债率": {"unit": "%", "scale": 1, "category": "风险"},
    "基本每股收益": {"unit": "元", "scale": 1, "category": "每股"},
    "每股净资产": {"unit": "元", "scale": 1, "category": "每股"},
    "每股经营现金流": {"unit": "元", "scale": 1, "category": "每股"},
    "经营现金流量净额": {"unit": "亿元", "scale": 1e8, "category": "现金流"},
    "期间费用率": {"unit": "%", "scale": 1, "category": "效率"},
}

INSURER_METRICS = {
    "新业务价值": {"unit": "亿元", "scale": 1e8, "category": "保险业务"},
    "合同服务边际": {"unit": "亿元", "scale": 1e8, "category": "保险业务"},
    "综合成本率": {"unit": "%", "scale": 1, "category": "保险业务"},
    "总投资收益率": {"unit": "%", "scale": 1, "category": "投资"},
    "净投资收益率": {"unit": "%", "scale": 1, "category": "投资"},
    "综合偿付能力充足率": {"unit": "%", "scale": 1, "category": "偿付"},
    "核心偿付能力充足率": {"unit": "%", "scale": 1, "category": "偿付"},
}


def load_financial_abstract(stock_code: str, data_dir: str) -> pd.DataFrame:
    """加载财务摘要 CSV"""
    csv_path = os.path.join(data_dir, f"{stock_code}_financial_abstract.csv")
    if not os.path.exists(csv_path):
        raise SkillError(
            operation="加载财务摘要文件",
            reason=f"文件不存在: {csv_path}",
            next_action=f"请先执行: python skills/read-pdf/scripts/fetch_financial_data.py --stock {stock_code} --type financial"
        )

    df = pd.read_csv(csv_path, encoding="utf-8-sig")
    return df


def extract_annual_metrics(
    df: pd.DataFrame,
    years: int = 5,
    metrics_config: dict = None,
    requested_years: list[str] | None = None,
) -> dict:
    """
    从财务摘要中提取年度核心指标

    财务摘要 CSV 格式: 行为指标，列为日期(如 20241231, 20231231...)
    """
    # 获取所有日期列(格式为 YYYYMMDD 的数字列)
    date_cols = [c for c in df.columns if c not in ("选项", "指标") and str(c).isdigit()]

    # 筛选年报数据(12月31日结尾)
    annual_cols = [c for c in date_cols if str(c).endswith("1231")]
    requested = {str(year) for year in requested_years or []}
    if requested:
        annual_cols = [c for c in annual_cols if str(c)[:4] in requested]
        annual_cols = sorted(annual_cols, reverse=True)
    else:
        annual_cols = sorted(annual_cols, reverse=True)[:years]

    if not annual_cols and not requested:
        logger.warning("未找到年度数据，尝试使用最近的季度数据")
        annual_cols = sorted(date_cols, reverse=True)[:years]

    result = {}
    metrics_config = metrics_config or CORE_METRICS
    for metric_name, config in metrics_config.items():
        row = df[df["指标"] == metric_name]
        if row.empty:
            continue

        values = {}
        for col in annual_cols:
            val = row[col].values[0] if col in row.columns else None
            if pd.notna(val) and val != "":
                try:
                    num = float(val)
                    values[str(col)] = round(num / config["scale"], 2) if config["scale"] != 1 else round(num, 2)
                except (ValueError, TypeError):
                    pass

        if values:
            sorted_dates = sorted(values.keys(), reverse=True)
            vals_list = [values[d] for d in sorted_dates]

            # 计算同比增长率
            yoy_growth = None
            if len(vals_list) >= 2 and vals_list[1] != 0:
                yoy_growth = round((vals_list[0] - vals_list[1]) / abs(vals_list[1]) * 100, 2)

            # 计算趋势方向
            trend = "stable"
            if len(vals_list) >= 3:
                increases = sum(1 for i in range(len(vals_list) - 1) if vals_list[i] > vals_list[i + 1])
                if increases >= len(vals_list) - 1:
                    trend = "up"
                elif increases <= 0:
                    trend = "down"

            result[metric_name] = {
                "category": config["category"],
                "unit": config["unit"],
                "values": {d: values[d] for d in sorted_dates},
                "latest": vals_list[0] if vals_list else None,
                "yoy_growth": yoy_growth,
                "trend": trend,
            }

    return result


def generate_analysis(stock_code: str, metrics: dict, industry: str = "general") -> str:
    """生成财务分析报告文本"""
    lines = []
    lines.append(f"{'=' * 60}")
    lines.append(f"  {stock_code} 核心财务指标分析")
    lines.append(f"{'=' * 60}")

    categories = {
        "规模": [], "盈利": [], "风险": [], "每股": [], "现金流": [], "效率": [],
        "保险业务": [], "投资": [], "偿付": [],
    }
    excluded = {"毛利率", "销售净利率", "资产负债率", "期间费用率"} if industry == "insurer" else set()
    for name, data in metrics.items():
        if name in excluded:
            continue
        config = {**CORE_METRICS, **INSURER_METRICS}
        cat = data.get("category", config.get(name, {}).get("category", ""))
        if cat in categories:
            categories[cat].append((name, data))

    for cat_name, items in categories.items():
        if not items:
            continue
        lines.append(f"\n--- {cat_name}指标 ---")
        for name, data in items:
            latest = data["latest"]
            unit = data["unit"]
            yoy = data["yoy_growth"]
            trend = {"up": "上升", "down": "下降", "stable": "平稳"}.get(data["trend"], "")

            yoy_str = f" (同比 {'+' if yoy > 0 else ''}{yoy}%)" if yoy is not None else ""
            trend_str = f" [{trend}]" if trend else ""

            lines.append(f"  {name}: {latest} {unit}{yoy_str}{trend_str}")

            # 显示历史数据
            vals = data["values"]
            if len(vals) > 1:
                hist = " | ".join(f"{d[:4]}: {v}" for d, v in vals.items())
                lines.append(f"    历史: {hist}")

    # 综合评价
    lines.append(f"\n--- 综合评价 ---")

    roe = metrics.get("净资产收益率(ROE)", {})
    margin = metrics.get("毛利率", {})
    debt = metrics.get("资产负债率", {})
    revenue = metrics.get("营业总收入", {})

    if industry != "insurer" and roe.get("latest"):
        roe_val = roe["latest"]
        if roe_val > 20:
            lines.append(f"  盈利能力: 优秀 (ROE {roe_val}% > 20%)")
        elif roe_val > 10:
            lines.append(f"  盈利能力: 良好 (ROE {roe_val}%)")
        else:
            lines.append(f"  盈利能力: 一般 (ROE {roe_val}%)")

    if industry != "insurer" and margin.get("latest"):
        trend_map = {"up": "改善", "down": "承压", "stable": "稳定"}
        trend_label = trend_map.get(margin.get("trend", ""), "")
        lines.append(f"  毛利水平: {margin['latest']}%，趋势{trend_label}")

    if industry == "insurer":
        lines.append("  行业口径: 保险公司；不使用普通企业负债率阈值评价偿付安全")
        lines.append("  重点补充: 新业务价值、合同服务边际、综合成本率、投资收益率及偿付能力")
    elif debt.get("latest"):
        debt_val = debt["latest"]
        if debt_val < 30:
            lines.append(f"  财务安全: 稳健 (负债率 {debt_val}%)")
        elif debt_val < 60:
            lines.append(f"  财务安全: 适中 (负债率 {debt_val}%)")
        else:
            lines.append(f"  财务安全: 偏高 (负债率 {debt_val}%)")

    if revenue.get("yoy_growth") is not None:
        growth = revenue["yoy_growth"]
        if growth > 20:
            lines.append(f"  成长性: 高增长 (营收同比 +{growth}%)")
        elif growth > 0:
            lines.append(f"  成长性: 稳定增长 (营收同比 +{growth}%)")
        else:
            lines.append(f"  成长性: 增速放缓 (营收同比 {growth}%)")

    lines.append(f"{'=' * 60}")
    return "\n".join(lines)


def main():
    # 创建 CLI 助手
    cli = CLIHelper(
        script_name="ratio_analysis.py",
        description="核心财务指标分析工具 - 从财务摘要中提取核心指标并生成趋势分析",
        examples=[
            "python ratio_analysis.py --stock 600519",
            "python ratio_analysis.py --stock 600519 --years 3",
            "python ratio_analysis.py --stock 688981 --data_dir data/financial_data --output output/analysis.json",
        ]
    )

    parser = argparse.ArgumentParser(
        description=cli.description,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=cli.format_examples()
    )

    parser.add_argument("--stock", required=True, help="股票代码(如 600519)")
    parser.add_argument("--years", type=int, default=5, help="分析年数(默认: 5)")
    parser.add_argument(
        "--period",
        default="annual",
        help="报告期: annual、latest 或 YYYYMMDD（默认: annual）",
    )
    parser.add_argument(
        "--periods",
        default="",
        help="逗号分隔的明确年度（如 2024,2025）；提供后仅分析这些年报期",
    )
    parser.add_argument(
        "--industry",
        choices=["auto", "general", "insurer"],
        default="auto",
        help="行业分析口径（默认: auto - 自动识别）",
    )
    parser.add_argument("--data_dir", default="data/financial_data", help="财务数据目录（默认: data/financial_data）")
    parser.add_argument("--output", default=None, help="JSON 结果保存路径(可选)")
    args = parser.parse_args()

    try:
        logger.info(f"分析 {args.stock} 近 {args.years} 年财务指标")

        df = load_financial_abstract(args.stock, args.data_dir)
        logger.info(f"财务摘要共 {len(df)} 行指标")

        industry = detect_industry(args.stock) if args.industry == "auto" else args.industry
        requested_years = sorted({
            item.strip() for item in args.periods.split(",")
            if item.strip().isdigit() and len(item.strip()) == 4
        })
        metrics_config = {**CORE_METRICS, **INSURER_METRICS} if industry == "insurer" else CORE_METRICS
        if args.period == "annual" or requested_years:
            metrics = extract_annual_metrics(
                df,
                args.years,
                metrics_config=metrics_config,
                requested_years=requested_years,
            )
        else:
            latest, comparison = select_comparison_columns(df, args.period)
            period_metrics = extract_period_metrics(df, latest, comparison, metrics_config)
            metrics = {}
            for name, item in period_metrics.items():
                config = metrics_config[name]
                scale = config["scale"]
                current = round(item["current"] / scale, 2)
                previous = None if item["previous"] is None else round(item["previous"] / scale, 2)
                metrics[name] = {
                    "category": config["category"],
                    "unit": config["unit"],
                    "values": {latest: current, comparison: previous},
                    "latest": current,
                    "yoy_growth": item["yoy"],
                    "trend": "up" if item["yoy"] and item["yoy"] > 0 else ("down" if item["yoy"] and item["yoy"] < 0 else "stable"),
                }
                logger.info(f"期间对比: {latest} vs {comparison}")
        logger.info(f"提取到 {len(metrics)} 个核心指标")

        report = generate_analysis(args.stock, metrics, industry=industry)
        print(report)

        if args.output:
            os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump({
                    "stock": args.stock,
                    "industry": industry,
                    "years": args.years,
                    "requested_years": requested_years,
                    "metrics": metrics,
                }, f, ensure_ascii=False, indent=2, allow_nan=False)
            logger.info(f"JSON 已保存: {args.output}")

        missing_insurer_metrics = sorted(set(INSURER_METRICS) - set(metrics)) if industry == "insurer" else []
        available_years = sorted({
            str(period)[:4]
            for metric in metrics.values()
            for period in metric.get("values", {})
        })
        missing_requested_years = [year for year in requested_years if year not in available_years]
        warnings = []
        if missing_insurer_metrics:
            warnings.append("保险专用指标需从年报或公司披露补充: " + ", ".join(missing_insurer_metrics))
        if missing_requested_years:
            warnings.append("结构化财务数据缺少请求年份: " + ", ".join(missing_requested_years))
        result = {
            "status": "partial" if missing_requested_years else "success",
            "module": "financial-analysis",
            "summary": {
                "stock": args.stock, "metrics_count": len(metrics), "industry": industry,
                "requested_years": requested_years, "available_years": available_years,
                "missing_insurer_metrics": missing_insurer_metrics,
            },
            "artifacts": ([{"role": "metrics-json", "module": "financial-analysis", "path": args.output}] if args.output else []),
            "sources": [{"type": "financial-abstract-csv", "stock": args.stock}],
            "warnings": warnings,
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
            operation="分析财务指标",
            reason=f"未预期的错误: {type(e).__name__}: {e}",
            next_action="请检查股票代码、数据文件或参数配置"
        )
        print(format_error_message(error), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
