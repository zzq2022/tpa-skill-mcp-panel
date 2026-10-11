#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
同行对比分析工具

功能: 横向对比多家公司的核心财务指标，
     帮助投资者快速识别各公司在盈利、成长、风险等维度的相对优劣。

用法:
    python peer_compare.py --stocks 600519,000858
    python peer_compare.py --stocks 688981,002049,603501 --data_dir data/financial_data
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
logger = SkillLogger("peer_compare", level=LogLevel.INFO)


# 用于对比的核心指标
COMPARE_METRICS = [
    {"name": "营业总收入", "unit": "亿元", "scale": 1e8, "higher_better": True},
    {"name": "归母净利润", "unit": "亿元", "scale": 1e8, "higher_better": True},
    {"name": "毛利率", "unit": "%", "scale": 1, "higher_better": True},
    {"name": "销售净利率", "unit": "%", "scale": 1, "higher_better": True},
    {"name": "净资产收益率(ROE)", "unit": "%", "scale": 1, "higher_better": True},
    {"name": "总资产报酬率(ROA)", "unit": "%", "scale": 1, "higher_better": True},
    {"name": "资产负债率", "unit": "%", "scale": 1, "higher_better": False},
    {"name": "基本每股收益", "unit": "元", "scale": 1, "higher_better": True},
    {"name": "每股经营现金流", "unit": "元", "scale": 1, "higher_better": True},
    {"name": "期间费用率", "unit": "%", "scale": 1, "higher_better": False},
]

# 已知股票名称映射
STOCK_NAMES = {
    "600519": "贵州茅台",
    "000858": "五粮液",
    "688981": "中芯国际",
    "002594": "比亚迪",
    "300750": "宁德时代",
    "601012": "隆基绿能",
    "600036": "招商银行",
    "601318": "中国平安",
    "603288": "海天味业",
    "600276": "恒瑞医药",
}


def load_latest_annual(stock_code: str, data_dir: str) -> dict:
    """加载某只股票最新年报数据"""
    csv_path = os.path.join(data_dir, f"{stock_code}_financial_abstract.csv")
    if not os.path.exists(csv_path):
        return None

    df = pd.read_csv(csv_path, encoding="utf-8-sig")

    # 找最新的年度列(1231结尾)
    date_cols = [c for c in df.columns if c not in ("选项", "指标") and str(c).isdigit()]
    annual_cols = sorted([c for c in date_cols if str(c).endswith("1231")], reverse=True)

    if not annual_cols:
        return None

    latest_col = annual_cols[0]
    prev_col = annual_cols[1] if len(annual_cols) > 1 else None

    result = {"period": str(latest_col), "stock_name": STOCK_NAMES.get(stock_code, stock_code)}

    for metric in COMPARE_METRICS:
        row = df[df["指标"] == metric["name"]]
        if row.empty:
            continue

        val = row[latest_col].values[0] if latest_col in row.columns else None
        if pd.notna(val) and val != "":
            try:
                num = float(val)
                scaled = round(num / metric["scale"], 2) if metric["scale"] != 1 else round(num, 2)
                entry = {"value": scaled, "unit": metric["unit"]}

                # 计算同比
                if prev_col and prev_col in row.columns:
                    prev_val = row[prev_col].values[0]
                    if pd.notna(prev_val) and prev_val != "" and float(prev_val) != 0:
                        yoy = round((num - float(prev_val)) / abs(float(prev_val)) * 100, 2)
                        entry["yoy"] = yoy

                result[metric["name"]] = entry
            except (ValueError, TypeError):
                pass

    return result


def compare_stocks(stocks_data: dict) -> str:
    """生成对比分析报告"""
    codes = list(stocks_data.keys())
    if not codes:
        logger.error("无有效数据")
        return "[错误] 无有效数据"

    lines = []
    lines.append(f"{'=' * 80}")
    names = [stocks_data[c].get("stock_name", c) for c in codes]
    lines.append(f"  同行对比分析: {' vs '.join(names)}")
    lines.append(f"{'=' * 80}")

    # 表头
    header = f"  {'指标':<20}"
    for code in codes:
        name = stocks_data[code].get("stock_name", code)
        header += f" | {name:>12}"
    lines.append(header)
    lines.append("  " + "-" * (20 + 15 * len(codes)))

    # 每个指标的对比
    for metric in COMPARE_METRICS:
        mname = metric["name"]
        row_str = f"  {mname:<20}"

        values_for_rank = []
        for code in codes:
            data = stocks_data[code].get(mname)
            if data:
                val = data["value"]
                unit = data["unit"]
                yoy_str = ""
                if "yoy" in data:
                    yoy = data["yoy"]
                    yoy_str = f"({'+' if yoy > 0 else ''}{yoy}%)"
                row_str += f" | {val:>8}{unit}{yoy_str:>0}"
                values_for_rank.append((code, val))
            else:
                row_str += f" | {'N/A':>12}"

        # 标记最优
        if len(values_for_rank) >= 2:
            if metric["higher_better"]:
                best = max(values_for_rank, key=lambda x: x[1])
            else:
                best = min(values_for_rank, key=lambda x: x[1])
            best_name = stocks_data[best[0]].get("stock_name", best[0])
            row_str += f"  << {best_name}"

        lines.append(row_str)

    # 综合评价
    lines.append(f"\n--- 综合评价 ---")

    for code in codes:
        data = stocks_data[code]
        name = data.get("stock_name", code)
        strengths = []
        weaknesses = []

        roe = data.get("净资产收益率(ROE)", {}).get("value")
        margin = data.get("毛利率", {}).get("value")
        debt = data.get("资产负债率", {}).get("value")
        net_margin = data.get("销售净利率", {}).get("value")

        if roe and roe > 15:
            strengths.append(f"ROE较高({roe}%)")
        if margin and margin > 50:
            strengths.append(f"毛利率突出({margin}%)")
        if debt and debt < 30:
            strengths.append(f"负债率低({debt}%)")
        if net_margin and net_margin > 30:
            strengths.append(f"净利率高({net_margin}%)")

        if roe and roe < 8:
            weaknesses.append(f"ROE偏低({roe}%)")
        if debt and debt > 60:
            weaknesses.append(f"负债率偏高({debt}%)")

        s_str = "、".join(strengths) if strengths else "无明显亮点"
        w_str = "、".join(weaknesses) if weaknesses else "无明显短板"
        lines.append(f"  {name}: 优势: {s_str}; 关注: {w_str}")

    lines.append(f"{'=' * 80}")
    return "\n".join(lines)


def main():
    # 创建 CLI 助手
    cli = CLIHelper(
        script_name="peer_compare.py",
        description="同行对比分析工具 - 横向对比多家公司的核心财务指标",
        examples=[
            "python peer_compare.py --stocks 600519,000858",
            "python peer_compare.py --stocks 688981,002049,603501 --data_dir data/financial_data",
            "python peer_compare.py --stocks 600519,000858 --output output/peer_compare.json",
        ]
    )

    parser = argparse.ArgumentParser(
        description=cli.description,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=cli.format_examples()
    )

    parser.add_argument("--stocks", required=True, help="股票代码(逗号分隔, 如 600519,000858)")
    parser.add_argument("--data_dir", default="data/financial_data", help="财务数据目录（默认: data/financial_data）")
    parser.add_argument("--output", default=None, help="JSON 结果保存路径(可选)")
    args = parser.parse_args()

    try:
        stock_codes = [s.strip() for s in args.stocks.split(",")]
        logger.info(f"对比分析: {', '.join(stock_codes)}")

        stocks_data = {}
        missing = []

        for code in stock_codes:
            data = load_latest_annual(code, args.data_dir)
            if data:
                stocks_data[code] = data
                logger.info(f"{code} ({data.get('stock_name', '?')}): 已加载, 数据期间 {data['period']}")
            else:
                missing.append(code)
                logger.warning(f"{code}: 数据缺失")

        if missing:
            logger.warning(f"以下股票缺少财务数据: {', '.join(missing)}")
            for code in missing:
                logger.info(f"获取数据: python skills/read-pdf/scripts/fetch_financial_data.py --stock {code} --type financial")

        if len(stocks_data) < 2:
            if len(stocks_data) == 1:
                raise SkillError(
                    operation="同行对比分析",
                    reason="只有 1 家公司数据，无法进行对比",
                    next_action="请添加更多股票代码，或使用 ratio_analysis.py 进行单股分析"
                )
            else:
                raise SkillError(
                    operation="同行对比分析",
                    reason="至少需要 2 家公司的数据才能对比",
                    next_action="请检查股票代码或先执行 fetch_financial_data.py 获取数据"
                )

        report = compare_stocks(stocks_data)
        print(report)

        if args.output:
            os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(stocks_data, f, ensure_ascii=False, indent=2)
            logger.info(f"JSON 已保存: {args.output}")

        result = {
            "status": "success",
            "stocks": list(stocks_data.keys()),
            "missing": missing,
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        sys.exit(0)

    except SkillError as e:
        print(format_error_message(e), file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        error = SkillError(
            operation="同行对比分析",
            reason=f"未预期的错误: {type(e).__name__}: {e}",
            next_action="请检查股票代码、数据文件或参数配置"
        )
        print(format_error_message(error), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
