#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
新闻抓取器

功能：通过 akshare 获取东方财富个股新闻、上市公司公告等，
      支持关键词过滤和时间范围筛选。

用法：
    python news_fetcher.py --stock 002594 --days 7
    python news_fetcher.py --keywords 资产重组 --days 3
    python news_fetcher.py --stock 600519 --keywords 业绩,分红 --days 30
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta
from typing import List, Optional
from pathlib import Path

import pandas as pd

# 避免 pyarrow 字符串引擎与 akshare 正则转义 (\u3000) 冲突导致 ArrowInvalid
try:
    pd.set_option("mode.string_storage", "python")
except Exception:
    pass

# 添加 common 目录到 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'common'))
from error_handler import SkillError, format_error_message
from logger import SkillLogger, LogLevel
from cli_helper import CLIHelper

# 初始化日志
logger = SkillLogger("news_fetcher", level=LogLevel.INFO)


STOCK_ALIASES = {
    "601318": ["中国平安", "平安集团", "平安寿险", "平安产险"],
    "601628": ["中国人寿", "国寿"],
    "600519": ["贵州茅台", "茅台"],
    "688981": ["中芯国际", "中芯"],
}


def filter_stock_relevance(df: pd.DataFrame, stock_code: str) -> pd.DataFrame:
    """Remove list-style articles that only mention a stock code in the body."""
    aliases = STOCK_ALIASES.get(stock_code)
    if df.empty or not aliases:
        return df
    title_cols = [column for column in ["新闻标题", "title", "标题"] if column in df.columns]
    text_cols = title_cols + [
        column for column in ["新闻内容", "content", "内容"] if column in df.columns
    ]
    mask = pd.Series(False, index=df.index)
    for column in text_cols:
        text = df[column].astype(str)
        for alias in aliases:
            mask |= text.str.contains(alias, regex=False, na=False)
    for column in title_cols:
        mask |= df[column].astype(str).str.contains(stock_code, regex=False, na=False)
    filtered = df[mask]
    logger.info(f"{stock_code} 高相关新闻 {len(filtered)}/{len(df)} 条")
    return filtered


def fetch_stock_news(stock_code: str, limit: int = 100) -> pd.DataFrame:
    """
    获取个股新闻（东方财富）。

    Args:
        stock_code: 股票代码（如 002594、600519）
        limit: 获取条数上限

    Returns:
        新闻 DataFrame
    """
    try:
        import akshare as ak
    except ImportError:
        raise SkillError(
            operation="导入 akshare 库",
            reason="akshare 包未安装",
            next_action="运行: pip install akshare"
        )

    try:
        df = ak.stock_news_em(symbol=stock_code)
        if df is not None and not df.empty:
            logger.info(f"个股新闻: {stock_code}，共 {len(df)} 条")
            return df.head(limit)
        else:
            logger.warning(f"未获取到 {stock_code} 的新闻")
            return pd.DataFrame()
    except Exception as e:
        logger.error(f"获取个股新闻失败: {e}")
        return pd.DataFrame()


def fetch_stock_notices(stock_code: str) -> pd.DataFrame:
    """
    获取上市公司公告。

    Args:
        stock_code: 股票代码

    Returns:
        公告 DataFrame
    """
    try:
        import akshare as ak
    except ImportError:
        raise SkillError(
            operation="导入 akshare 库",
            reason="akshare 包未安装",
            next_action="运行: pip install akshare"
        )

    try:
        # 尝试获取个股公告
        df = ak.stock_notice_report(symbol=stock_code)
        if df is not None and not df.empty:
            logger.info(f"公司公告: {stock_code}，共 {len(df)} 条")
            return df
        else:
            logger.info(f"未获取到 {stock_code} 的公告")
            return pd.DataFrame()
    except Exception as e:
        logger.warning(f"获取公司公告接口异常（可能需要登录或接口变更）: {e}")
        return pd.DataFrame()


def fetch_cctv_news(date_str: str = None) -> pd.DataFrame:
    """
    获取央视新闻（政策面参考）。

    Args:
        date_str: 日期字符串（格式 YYYYMMDD），默认今天

    Returns:
        新闻 DataFrame
    """
    try:
        import akshare as ak
    except ImportError:
        raise SkillError(
            operation="导入 akshare 库",
            reason="akshare 包未安装",
            next_action="运行: pip install akshare"
        )

    if date_str is None:
        date_str = datetime.now().strftime("%Y%m%d")

    try:
        df = ak.news_cctv(date=date_str)
        if df is not None and not df.empty:
            logger.info(f"央视新闻({date_str}): 共 {len(df)} 条")
            return df
        else:
            logger.info(f"未获取到 {date_str} 的央视新闻")
            return pd.DataFrame()
    except Exception as e:
        logger.warning(f"获取央视新闻异常: {e}")
        return pd.DataFrame()


def filter_by_keywords(df: pd.DataFrame, keywords: List[str], text_columns: List[str] = None) -> pd.DataFrame:
    """
    按关键词过滤新闻。

    Args:
        df: 新闻 DataFrame
        keywords: 关键词列表
        text_columns: 搜索的列名列表（自动检测）

    Returns:
        过滤后的 DataFrame
    """
    if df.empty or not keywords:
        return df

    # 自动检测文本列
    if text_columns is None:
        possible_cols = ["title", "content", "新闻标题", "新闻内容", "标题", "内容"]
        text_columns = [c for c in possible_cols if c in df.columns]
        if not text_columns:
            text_columns = df.columns.tolist()

    # 构建过滤条件
    mask = pd.Series([False] * len(df), index=df.index)
    for col in text_columns:
        for kw in keywords:
            mask = mask | df[col].astype(str).str.contains(kw, na=False)

    filtered = df[mask]
    logger.info(f"关键词 {keywords}，匹配 {len(filtered)}/{len(df)} 条")
    return filtered


def filter_by_date(df: pd.DataFrame, days: int, date_column: str = None) -> pd.DataFrame:
    """
    按时间范围过滤新闻。

    Args:
        df: 新闻 DataFrame
        days: 最近 N 天
        date_column: 日期列名（自动检测）

    Returns:
        过滤后的 DataFrame
    """
    if df.empty:
        return df

    # 自动检测日期列
    if date_column is None:
        possible_cols = ["发布时间", "日期", "date", "publish_date", "公告日期", "发布日期"]
        for col in possible_cols:
            if col in df.columns:
                date_column = col
                break

    if date_column is None:
        logger.info("未找到日期列，跳过时间过滤")
        return df

    try:
        df[date_column] = pd.to_datetime(df[date_column], errors="coerce")
        cutoff = datetime.now() - timedelta(days=days)
        filtered = df[df[date_column] >= cutoff]
        logger.info(f"最近 {days} 天，筛选 {len(filtered)}/{len(df)} 条")
        return filtered
    except Exception as e:
        logger.warning(f"时间过滤异常: {e}")
        return df


def deduplicate(df: pd.DataFrame) -> pd.DataFrame:
    """Remove repeated articles by normalized content, falling back to titles."""
    if df.empty:
        return df

    title_cols = [c for c in df.columns if "标题" in c or "title" in c.lower()]
    content_cols = [c for c in df.columns if c in {"新闻内容", "content", "内容"}]
    key_cols = content_cols or title_cols
    if key_cols:
        before = len(df)
        normalized = df[key_cols].fillna("").astype(str).agg(" ".join, axis=1)
        df = df.assign(
            _dedup_key=normalized.map(lambda text: re.sub(r"\W+", "", text).lower())
        )
        df = df.drop_duplicates(subset=["_dedup_key"], keep="first").drop(columns=["_dedup_key"])
        logger.info(f"去重: {before} -> {len(df)} 条")
    return df


def save_news(df: pd.DataFrame, output_file: str) -> str:
    """将新闻保存为 JSON 文件"""
    os.makedirs(os.path.dirname(output_file) or ".", exist_ok=True)

    # 将 DataFrame 转为可序列化的字典列表
    records = df.to_dict(orient="records")
    for record in records:
        for k, v in record.items():
            if isinstance(v, pd.Timestamp):
                record[k] = v.strftime("%Y-%m-%d %H:%M:%S")
            elif pd.isna(v):
                record[k] = None

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2, default=str)

    return output_file


def main():
    # 创建 CLI 助手
    cli = CLIHelper(
        script_name="news_fetcher.py",
        description="新闻抓取器 - 通过 akshare 获取个股新闻、公告和央视新闻",
        examples=[
            "python news_fetcher.py --stock 600519 --days 7",
            "python news_fetcher.py --stock 002594 --keywords 资产重组,回购 --days 30",
            "python news_fetcher.py --keywords 白酒 --days 7 --include_cctv",
        ]
    )

    parser = argparse.ArgumentParser(
        description=cli.description,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=cli.format_examples()
    )

    parser.add_argument("--stock", default=None, help="股票代码（如 002594、600519）")
    parser.add_argument("--keywords", default=None, help="关键词，逗号分隔（如 资产重组,回购）")
    parser.add_argument("--days", type=int, default=7, help="最近 N 天（默认: 7）")
    parser.add_argument("--output_dir", default="./data", help="输出目录（默认: ./data）")
    parser.add_argument("--include_cctv", action="store_true", help="是否包含央视新闻")
    args = parser.parse_args()

    try:
        if not args.stock and not args.keywords:
            raise SkillError(
                operation="检查参数",
                reason="未指定股票代码或关键词",
                next_action="请通过 --stock 或 --keywords 指定搜索条件"
            )

        keywords = []
        if args.keywords:
            keywords = [k.strip() for k in args.keywords.split(",") if k.strip()]

        all_news = pd.DataFrame()

        # 获取个股新闻
        if args.stock:
            logger.info(f"获取 {args.stock} 的新闻（最近 {args.days} 天）")
            stock_news = fetch_stock_news(args.stock)
            if not stock_news.empty:
                stock_news = filter_by_date(stock_news, args.days)
                stock_news = filter_stock_relevance(stock_news, args.stock)
                if keywords:
                    stock_news = filter_by_keywords(stock_news, keywords)
                all_news = pd.concat([all_news, stock_news], ignore_index=True)

            # 获取公司公告
            notices = fetch_stock_notices(args.stock)
            if not notices.empty:
                notices = filter_by_date(notices, args.days)
                if keywords:
                    notices = filter_by_keywords(notices, keywords)
                all_news = pd.concat([all_news, notices], ignore_index=True)

        # 获取央视新闻（如果要求）
        if args.include_cctv:
            for i in range(min(args.days, 3)):
                date = (datetime.now() - timedelta(days=i)).strftime("%Y%m%d")
                cctv = fetch_cctv_news(date)
                if not cctv.empty:
                    if keywords:
                        cctv = filter_by_keywords(cctv, keywords)
                    all_news = pd.concat([all_news, cctv], ignore_index=True)

        # 如果只有关键词没有股票代码，尝试搜索通用新闻
        if not args.stock and keywords:
            logger.info(f"搜索关键词: {keywords}")
            # 使用关键词搜索最近的新闻
            for kw in keywords:
                try:
                    import akshare as ak
                    kw_news = ak.stock_news_em(symbol=kw)
                    if kw_news is not None and not kw_news.empty:
                        kw_news = filter_by_date(kw_news, args.days)
                        all_news = pd.concat([all_news, kw_news], ignore_index=True)
                except Exception:
                    pass

        # 去重
        all_news = deduplicate(all_news)

        if all_news.empty:
            logger.warning("未获取到符合条件的新闻")
            result = {
                "status": "unavailable",
                "module": "news",
                "summary": {"message": "未获取到新闻"},
                "artifacts": [],
                "sources": [],
                "warnings": ["no news matched the filters"],
                "errors": [],
                "next_actions": ["check stock code, broaden keywords, or extend --days"],
            }
            print(json.dumps(result, ensure_ascii=False, indent=2))
            sys.exit(0)

        # 保存结果
        if args.stock:
            output_file = os.path.join(args.output_dir, f"{args.stock}_news.json")
        else:
            kw_tag = "_".join(keywords[:3])
            output_file = os.path.join(args.output_dir, f"{kw_tag}_news.json")

        save_news(all_news, output_file)
        logger.info(f"新闻已保存: {output_file}，共 {len(all_news)} 条")

        result = {
            "status": "success",
            "module": "news",
            "summary": {"total_news": len(all_news), "stock": args.stock, "keywords": keywords, "days": args.days},
            "artifacts": [{"role": "news-data", "module": "news", "path": output_file}],
            "sources": [{"type": "news", "provider": "east-money", "stock": args.stock}],
            "warnings": [],
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
            operation="抓取新闻",
            reason=f"未预期的错误: {type(e).__name__}: {e}",
            next_action="请检查网络连接和 akshare 包是否正确安装"
        )
        print(format_error_message(error), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
