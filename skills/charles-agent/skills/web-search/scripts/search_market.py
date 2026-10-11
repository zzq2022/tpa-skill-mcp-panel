#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
联网搜索工具 - 通过 qwen enable_search 获取实时市场信息

利用通义千问的联网搜索能力，获取最新的股票行情、行业新闻、
政策动态、分析师观点等投研所需的实时数据。

用法:
    python search_market.py --query "贵州茅台最新股价" --type stock
    python search_market.py --query "半导体行业政策" --type policy
    python search_market.py --query "中芯国际分析师评级" --type general
"""

import argparse
import io
import json
import os
import re
import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# 加载根目录 .env
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "runtime"))
from env_loader import load_dotenv_from_root
load_dotenv_from_root()

# 添加 common 目录到 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'common'))
from error_handler import SkillError, format_error_message
from logger import SkillLogger, LogLevel
from cli_helper import CLIHelper

# 初始化日志
logger = SkillLogger("search_market", level=LogLevel.INFO)

from openai import OpenAI


OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "kimi-for-coding")


def classify_search_answer(content: str) -> str:
    if not content or content.startswith("[搜索失败]"):
        return "failed"
    return "success" if "http://" in content or "https://" in content else "partial"


def extract_source_urls(content: str) -> list[str]:
    """Extract unique, directly verifiable URLs in first-seen order."""
    urls = re.findall(r'https?://[^\s<>"\]\)）}，。；、]+', str(content or ""))
    return list(dict.fromkeys(urls))

# 不同搜索类型对应的系统提示词
SEARCH_PROMPTS = {
    "stock": (
        "你是一位专业的股票分析助手。请根据搜索结果，提供以下信息(如果能找到):\n"
        "1. 最新股价/涨跌幅\n"
        "2. 成交量/换手率等交易数据\n"
        "3. 近期重要事件或公告\n"
        "4. 市场关注的核心逻辑\n"
        "请用简洁专业的语言回答，数据要准确，注明数据来源和时间。"
    ),
    "news": (
        "你是一位专业的财经新闻分析师。请根据搜索结果:\n"
        "1. 整理最相关的新闻要点(按时间倒序)\n"
        "2. 分析新闻对相关股票/行业的潜在影响\n"
        "3. 标注新闻来源和发布时间\n"
        "请客观中立地总结，区分事实和观点。"
    ),
    "policy": (
        "你是一位政策研究专家。请根据搜索结果:\n"
        "1. 列出最新的相关政策/法规/指导意见\n"
        "2. 分析政策要点和影响范围\n"
        "3. 评估对相关行业和公司的影响\n"
        "请引用政策原文或官方来源。"
    ),
    "general": (
        "你是一位专业的投资研究助手。请根据搜索到的最新信息，"
        "全面准确地回答用户的问题。"
        "请注明关键数据的来源和时间，确保信息的时效性和准确性。"
    ),
}


def search_with_qwen(query: str, search_type: str = "general", model: str = None) -> str:
    """
    使用 LLM 联网搜索能力获取实时信息，内置超时控频与优雅降级
    """
    if not OPENAI_API_KEY:
        raise SkillError(
            operation="初始化搜索 API",
            reason="未设置 OPENAI_API_KEY",
            next_action="请在 .env 中设置 OPENAI_API_KEY"
        )

    client = OpenAI(
        api_key=OPENAI_API_KEY,
        base_url=OPENAI_BASE_URL,
    )
    model_name = model or OPENAI_MODEL
    logger.info(f"搜索类型={search_type}, 查询: {query}")

    try:
        request = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": SEARCH_PROMPTS.get(search_type, SEARCH_PROMPTS["general"])},
                {"role": "user", "content": f"请简要回答以下搜索需求：{query}"},
            ],
            "timeout": 15,
        }
        if "qwen" in model_name.lower():
            request["extra_body"] = {"enable_search": True}
        response = client.chat.completions.create(
            **request,
        )
        content = response.choices[0].message.content
        if content and content.strip():
            return content
    except Exception as e:
        logger.warning(f"搜索接口请求超时或不可用: {e}")

    return f"[搜索失败] 针对查询 '{query}' 未获得可验证的网页结果。"


def main():
    # 创建 CLI 助手
    cli = CLIHelper(
        script_name="search_market.py",
        description="联网搜索工具 - 通过 qwen enable_search 获取实时市场信息",
        examples=[
            "python search_market.py --query '贵州茅台最新股价' --type stock",
            "python search_market.py --query '半导体行业政策' --type policy",
            "python search_market.py --query '中芯国际分析师评级' --type general --output output/search_result.json",
        ]
    )

    parser = argparse.ArgumentParser(
        description=cli.description,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=cli.format_examples()
    )

    parser.add_argument("--query", required=True, help="搜索查询")
    parser.add_argument(
        "--type",
        choices=["stock", "news", "policy", "general"],
        default="general",
        help="搜索类型（默认: general）- stock=个股行情, news=财经新闻, policy=政策法规, general=通用搜索",
    )
    parser.add_argument("--model", default="qwen-plus", help="模型（默认: qwen-plus）")
    parser.add_argument("--output", default=None, help="结果保存路径（可选）")
    args = parser.parse_args()

    try:
        result = search_with_qwen(args.query, args.type, args.model)
        status = classify_search_answer(result)
        source_urls = extract_source_urls(result)

        print(f"\n{'=' * 60}")
        print(f"[搜索结果]\n{result}")
        print(f"{'=' * 60}")

        if args.output:
            os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
            output_data = {
                "status": status,
                "query": args.query,
                "type": args.type,
                "result": result,
                "sources": source_urls,
            }
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(output_data, f, ensure_ascii=False, indent=2)
            logger.info(f"结果已保存: {args.output}")

        result_json = {
            "status": status,
            "module": "web-search",
            "summary": {"query": args.query, "type": args.type, "answer": result},
            "artifacts": [],
            "sources": [{"type": "web", "url": url} for url in source_urls],
            "warnings": [] if status == "success" else ["结果缺少可验证来源 URL"],
            "errors": [],
            "next_actions": [] if status == "success" else ["verify OPENAI_API_KEY and model enable_search support"],
        }
        print(json.dumps(result_json, ensure_ascii=False, indent=2))
        sys.exit(0)

    except SkillError as e:
        print(format_error_message(e), file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        error = SkillError(
            operation="联网搜索",
            reason=f"未预期的错误: {type(e).__name__}: {e}",
            next_action="请检查 API Key 配置或网络连接"
        )
        print(format_error_message(error), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
