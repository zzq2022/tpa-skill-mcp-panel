#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LLM 情感分析评分器

功能：使用 LLM 对新闻进行情感分析，输出结构化评分，
      并聚合生成整体情绪指数（类似 CNN Fear & Greed Index）。

输出格式（每条新闻）：
- sentiment: 正面/负面/中性
- strength: 1-5（情感强度）
- entities: 关键实体列表
- summary: 一句话摘要

用法：
    python sentiment_scorer.py --news_file data/002594_news.json --output_dir output/
    python sentiment_scorer.py --news_file data/资产重组_news.json
"""

import argparse
import json
import os
import sys
from typing import List
from pathlib import Path

from openai import OpenAI

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from runtime.env_loader import load_dotenv_from_root
load_dotenv_from_root()

# 添加 common 目录到 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'common'))
from error_handler import SkillError, format_error_message
from logger import SkillLogger, LogLevel
from cli_helper import CLIHelper

# 初始化日志
logger = SkillLogger("sentiment_scorer", level=LogLevel.INFO)

SENTIMENT_PROMPT = """你是一位专业的金融舆情分析师。请对以下金融新闻进行情感分析。

新闻内容：
{news_text}

请以严格的 JSON 格式输出分析结果（不要输出其他内容）：
{{
    "sentiment": "正面/负面/中性",
    "strength": 1到5的整数（1=极弱, 2=较弱, 3=中等, 4=较强, 5=极强）,
    "entities": ["相关公司或人物名称列表"],
    "keywords": ["核心关键词列表，最多5个"],
    "summary": "一句话摘要，不超过50字",
    "market_impact": "对市场可能的影响，一句话描述"
}}

分析要点：
- 区分事实报道与观点评论
- 关注对股价的潜在影响方向
- 识别信息的时效性（已发生/将发生/传闻）
- 注意消息源的可信度"""

AGGREGATE_PROMPT = """你是一位专业的市场情绪分析师。请基于以下一批新闻的情感分析结果，给出整体市场情绪评估。

情感分析结果汇总：
{analysis_summary}

请以 JSON 格式输出（不要输出其他内容）：
{{
    "overall_sentiment": "贪婪/乐观/中性/谨慎/恐慌",
    "fear_greed_index": 0到100的整数（0=极度恐慌, 50=中性, 100=极度贪婪）,
    "positive_count": 正面新闻数量,
    "negative_count": 负面新闻数量,
    "neutral_count": 中性新闻数量,
    "top_themes": ["最主要的3个主题"],
    "risk_alerts": ["需要关注的风险点"],
    "opportunity_hints": ["可能的交易机会"],
    "summary": "整体市场情绪的一段话描述，100字以内"
}}"""


def init_client() -> OpenAI:
    """初始化 API 客户端"""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise SkillError(
            operation="初始化 API 客户端",
            reason="未设置 OPENAI_API_KEY",
            next_action="请在 .env 中设置 OPENAI_API_KEY"
        )

    return OpenAI(
        api_key=api_key,
        base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
    )


def load_news(news_file: str) -> List[dict]:
    """加载新闻数据"""
    if not os.path.exists(news_file):
        raise SkillError(
            operation="加载新闻文件",
            reason=f"文件不存在: {news_file}",
            next_action="请先使用 news_fetcher.py 抓取新闻数据"
        )

    try:
        with open(news_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        raise SkillError(
            operation="读取新闻文件",
            reason=f"文件读取失败: {e}",
            next_action="请检查文件格式是否为有效的 JSON"
        )


def extract_news_text(news_item: dict) -> str:
    """从新闻条目中提取文本"""
    # 尝试不同的字段名
    text_fields = ["新闻内容", "content", "内容", "新闻标题", "title", "标题"]
    parts = []

    for field in text_fields:
        if field in news_item and news_item[field]:
            parts.append(str(news_item[field]))

    return " ".join(parts) if parts else ""


def analyze_single_news(client: OpenAI, news_text: str, model: str = "qwen-turbo") -> dict:
    """
    对单条新闻进行情感分析。

    Returns:
        分析结果字典
    """
    prompt = SENTIMENT_PROMPT.format(news_text=news_text[:2000])

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
        )
        content = response.choices[0].message.content.strip()

        # 尝试解析 JSON
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]

        result = json.loads(content)
        result.setdefault("status", "success")
        return result
    except json.JSONDecodeError:
        return {
            "sentiment": "中性",
            "strength": 1,
            "entities": [],
            "keywords": [],
            "summary": news_text[:50],
            "market_impact": "无法解析",
            "parse_error": True,
        }
    except Exception as e:
        return {
            "sentiment": "中性",
            "strength": 0,
            "entities": [],
            "keywords": [],
            "summary": "",
            "market_impact": "",
            "error": str(e),
        }


def aggregate_sentiment(client: OpenAI, analyses: List[dict], model: str = "qwen-turbo") -> dict:
    """
    聚合所有新闻的情感分析结果，生成整体情绪指数。

    Returns:
        聚合分析结果
    """
    failed_count = sum(1 for item in analyses if item.get("error") or item.get("parse_error"))
    valid_analyses = [
        item for item in analyses if not item.get("error") and not item.get("parse_error")
    ]
    if not valid_analyses:
        return {
            "overall_sentiment": "中性",
            "fear_greed_index": 50,
            "positive_count": 0,
            "negative_count": 0,
            "neutral_count": 0,
            "top_themes": [],
            "risk_alerts": [],
            "opportunity_hints": [],
            "summary": "没有可用的舆情分析样本",
            "status": "failed",
            "fallback": True,
            "error": f"all {len(analyses)} samples failed",
        }

    # 构建摘要
    summary_parts = []
    for i, a in enumerate(valid_analyses[:50]):  # 限制数量避免超长
        summary_parts.append(
            f"[{i+1}] {a.get('sentiment', '中性')}(强度{a.get('strength', 0)}) - {a.get('summary', '')}"
        )
    analysis_summary = "\n".join(summary_parts)

    prompt = AGGREGATE_PROMPT.format(analysis_summary=analysis_summary)

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
        )
        content = response.choices[0].message.content.strip()

        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]

        result = json.loads(content)
        result.setdefault("status", "partial" if failed_count else "success")
        return result
    except Exception as e:
        # 手动计算基础统计
        pos = sum(1 for a in valid_analyses if a.get("sentiment") == "正面")
        neg = sum(1 for a in valid_analyses if a.get("sentiment") == "负面")
        neu = len(valid_analyses) - pos - neg
        total = len(valid_analyses)
        index = int(((pos + 0.5 * neu) / total) * 100) if total > 0 else 50

        return {
            "overall_sentiment": "乐观" if index > 60 else ("恐慌" if index < 40 else "中性"),
            "fear_greed_index": index,
            "positive_count": pos,
            "negative_count": neg,
            "neutral_count": neu,
            "top_themes": [],
            "risk_alerts": [],
            "opportunity_hints": [],
            "summary": f"共分析 {total} 条新闻，正面 {pos} 条，负面 {neg} 条，中性 {neu} 条",
            "status": "failed",
            "fallback": True,
            "error": str(e),
        }


def main():
    # 创建 CLI 助手
    cli = CLIHelper(
        script_name="sentiment_scorer.py",
        description="LLM 情感分析评分器 - 使用 LLM 对新闻进行情感分析并聚合生成情绪指数",
        examples=[
            "python sentiment_scorer.py --news_file data/002594_news.json --output_dir output/",
            "python sentiment_scorer.py --news_file data/资产重组_news.json --max_news 30",
            "python sentiment_scorer.py --news_file data/600519_news.json --model qwen-plus",
        ]
    )

    parser = argparse.ArgumentParser(
        description=cli.description,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=cli.format_examples()
    )

    parser.add_argument("--news_file", required=True, help="新闻 JSON 文件路径")
    parser.add_argument("--output_dir", default="./output", help="输出目录（默认: ./output）")
    parser.add_argument("--model", default="qwen-turbo", help="LLM 模型（默认: qwen-turbo）")
    parser.add_argument("--max_news", type=int, default=50, help="最大分析条数（默认: 50）")
    args = parser.parse_args()

    try:
        logger.info(f"情感分析: {args.news_file}")

        # 加载新闻
        news_list = load_news(args.news_file)
        if not news_list:
            raise SkillError(
                operation="加载新闻数据",
                reason="新闻文件为空",
                next_action="请检查新闻文件内容或重新抓取新闻"
            )

        news_to_analyze = news_list[:args.max_news]
        logger.info(f"共 {len(news_list)} 条新闻，将分析前 {len(news_to_analyze)} 条")

        # 初始化客户端
        client = init_client()

        # 逐条分析
        analyses = []
        for i, news in enumerate(news_to_analyze):
            news_text = extract_news_text(news)
            if not news_text.strip():
                continue

            logger.info(f"分析 ({i+1}/{len(news_to_analyze)}) {news_text[:60]}...")
            result = analyze_single_news(client, news_text, args.model)
            result["original_index"] = i
            result["news_text_preview"] = news_text[:200]
            analyses.append(result)

        if not analyses:
            raise SkillError(
                operation="分析新闻内容",
                reason="没有可分析的新闻内容",
                next_action="请检查新闻文件中是否包含有效的文本字段"
            )

        logger.info(f"完成 {len(analyses)} 条新闻的情感分析")

        # 聚合分析
        logger.info("生成整体情绪指数...")
        aggregate = aggregate_sentiment(client, analyses, args.model)

        # 保存结果
        os.makedirs(args.output_dir, exist_ok=True)
        base_name = os.path.splitext(os.path.basename(args.news_file))[0]

        # 保存逐条分析
        detail_file = os.path.join(args.output_dir, f"{base_name}_sentiment.json")
        with open(detail_file, "w", encoding="utf-8") as f:
            json.dump(analyses, f, ensure_ascii=False, indent=2)
        logger.info(f"详细分析已保存: {detail_file}")

        # 保存聚合结果
        agg_file = os.path.join(args.output_dir, f"{base_name}_mood.json")
        with open(agg_file, "w", encoding="utf-8") as f:
            json.dump(aggregate, f, ensure_ascii=False, indent=2)
        logger.info(f"情绪指数已保存: {agg_file}")

        # 打印摘要
        print(f"\n{'='*60}")
        print(f"[情绪指数] Fear & Greed Index: {aggregate.get('fear_greed_index', 'N/A')}/100")
        print(f"[整体情绪] {aggregate.get('overall_sentiment', 'N/A')}")
        print(f"[正面/负面/中性] {aggregate.get('positive_count', 0)}/{aggregate.get('negative_count', 0)}/{aggregate.get('neutral_count', 0)}")
        if aggregate.get("risk_alerts"):
            print(f"[风险提示] {', '.join(aggregate['risk_alerts'])}")
        if aggregate.get("opportunity_hints"):
            print(f"[机会提示] {', '.join(aggregate['opportunity_hints'])}")
        print(f"{'='*60}")

        result = {
            "status": aggregate.get("status", "success"),
            "module": "sentiment",
            "summary": {
                "news_analyzed": len(analyses),
                "fear_greed_index": aggregate.get("fear_greed_index"),
                "overall_sentiment": aggregate.get("overall_sentiment"),
                "detail_file": detail_file,
                "mood_file": agg_file,
            },
            "artifacts": [
                {"role": "sentiment-detail", "module": "sentiment", "path": detail_file},
                {"role": "sentiment-aggregate", "module": "sentiment", "path": agg_file},
            ],
            "sources": [{"type": "news-file", "path": args.news_file}],
            "warnings": (["aggregate LLM call failed; using fallback stats"] if aggregate.get("fallback") else []),
            "errors": ([aggregate.get("error")] if aggregate.get("error") and aggregate.get("status") == "failed" else []),
            "next_actions": [],
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        sys.exit(0)

    except SkillError as e:
        print(format_error_message(e), file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        error = SkillError(
            operation="情感分析",
            reason=f"未预期的错误: {type(e).__name__}: {e}",
            next_action="请检查新闻文件格式、API Key 配置或网络连接"
        )
        print(format_error_message(error), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
