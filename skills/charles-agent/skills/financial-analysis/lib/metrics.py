# -*- coding: utf-8 -*-
"""
财务分析核心辅助模块（最小实现）
为 financial-analysis/scripts/ratio_analysis.py 提供缺失的依赖。
"""

import re
from typing import Dict, List, Optional, Tuple

import pandas as pd


def detect_industry(stock_code: str, industry_hint: str | None = None) -> str:
    """Select an analysis profile from verified task or provider metadata.

    A stock code alone does not identify an industry reliably. Callers should
    pass an explicit hint obtained during task recon or from company metadata.
    """
    normalized = str(industry_hint or "").strip().lower()
    if normalized in {"general", "insurer"}:
        return normalized
    return "general"


def select_comparison_columns(df: pd.DataFrame, period: str) -> Tuple[Optional[str], Optional[str]]:
    """
    选择最新列与对比列。
    period 可以是 'latest' 或 'YYYYMMDD'。
    """
    date_cols = [c for c in df.columns if c not in ("选项", "指标") and str(c).isdigit()]
    date_cols = sorted(date_cols, reverse=True)
    if not date_cols:
        return None, None

    if period == "latest":
        latest = str(date_cols[0])
        comparison = str(date_cols[1]) if len(date_cols) > 1 else None
        return latest, comparison

    target = str(period).replace("-", "").replace("/", "")
    if target in date_cols:
        idx = date_cols.index(target)
        latest = target
        comparison = str(date_cols[idx + 1]) if idx + 1 < len(date_cols) else None
        return latest, comparison

    # 默认返回最近两期
    return str(date_cols[0]), str(date_cols[1]) if len(date_cols) > 1 else None


def extract_period_metrics(
    df: pd.DataFrame,
    latest: str,
    comparison: Optional[str],
    metrics_config: Dict,
) -> Dict:
    """提取指定期间的财务指标。"""
    result = {}
    for metric_name, config in metrics_config.items():
        row = df[df["指标"] == metric_name]
        if row.empty:
            continue
        try:
            current = float(row[latest].values[0])
        except (ValueError, TypeError, KeyError):
            current = None
        previous = None
        if comparison:
            try:
                previous = float(row[comparison].values[0])
            except (ValueError, TypeError, KeyError):
                previous = None

        yoy = None
        if current is not None and previous is not None and previous != 0:
            yoy = round((current - previous) / abs(previous) * 100, 2)

        result[metric_name] = {"current": current, "previous": previous, "yoy": yoy}
    return result
