#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
跨期对比分析工具

功能: 从统一 FAISS 索引中检索同一公司不同时期的财报内容，
     由 LLM 自动对比分析关键指标和经营变化。

用法:
    python cross_period.py --stock 688981 --topics "营收,净利润,毛利率"
    python cross_period.py --stock 600519 --topics "经营情况" --index_dir data/vector_store
"""

import argparse
import io
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from runtime.env_loader import load_dotenv_from_root
load_dotenv_from_root()

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_community.vectorstores import FAISS

# 从 common 导入共享工具
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'common'))
from llm_client import message_content
from error_handler import SkillError, format_error_message
from logger import SkillLogger, LogLevel
from cli_helper import CLIHelper
from faiss_compat import load_faiss_local

# 初始化日志
logger = SkillLogger("cross_period", level=LogLevel.INFO)


STOCK_NAMES = {
    "688981": "中芯国际",
    "600519": "贵州茅台",
    "002594": "比亚迪",
    "300750": "宁德时代",
    "000858": "五粮液",
}


def load_unified_index(index_dir: str):
    """加载统一 FAISS 索引"""
    api_key = os.getenv("EMBEDDING_API_KEY") or os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("EMBEDDING_BASE_URL", "https://api.siliconflow.cn/v1")
    model = os.getenv("EMBEDDING_BASE_MODEL", "BAAI/bge-large-zh-v1.5")
    if not api_key:
        raise SkillError(
            operation="初始化 Embedding API",
            reason="未设置 API Key",
            next_action="请在 .env 中设置 EMBEDDING_API_KEY 或 OPENAI_API_KEY"
        )

    embeddings = OpenAIEmbeddings(
        model=model,
        api_key=api_key,
        base_url=base_url,
    )

    vectorstore = load_faiss_local(FAISS, index_dir, embeddings)

    # 加载 chunks 元数据
    chunks_json_path = os.path.join(index_dir, "chunks.json")
    chunks_metadata = {}
    if os.path.exists(chunks_json_path):
        with open(chunks_json_path, "r", encoding="utf-8") as f:
            chunks_data = json.load(f)
        for c in chunks_data:
            chunks_metadata[c["text"]] = c.get("metadata", {})

    return vectorstore, chunks_metadata


def search_by_stock_and_topic(
    vectorstore, chunks_metadata: dict, stock_code: str, topic: str, top_k: int = 8
):
    """按股票代码过滤并检索相关内容"""
    docs = vectorstore.similarity_search(topic, k=top_k * 3)

    # 按股票代码过滤
    filtered = []
    for doc in docs:
        meta = chunks_metadata.get(doc.page_content, {})
        if meta.get("stock_code") == stock_code:
            filtered.append({
                "text": doc.page_content,
                "filename": meta.get("filename", ""),
                "report_type": meta.get("report_type", ""),
                "publish_date": meta.get("publish_date", ""),
                "page": meta.get("page", -1),
            })
        if len(filtered) >= top_k:
            break

    return filtered


def cross_period_analysis(
    stock_code: str, topics: list, vectorstore, chunks_metadata: dict, model: str
):
    """执行跨期对比分析"""
    stock_name = STOCK_NAMES.get(stock_code, stock_code)

    # 搜索所有相关内容
    all_results = []
    for topic in topics:
        query = f"{stock_name} {topic}"
        results = search_by_stock_and_topic(vectorstore, chunks_metadata, stock_code, query)
        all_results.extend(results)

    if not all_results:
        logger.warning(f"未找到 {stock_name}({stock_code}) 的相关内容")
        return None

    # 按报告类型/日期分组
    by_report = {}
    for r in all_results:
        key = r["filename"] or r["report_type"] or "unknown"
        if key not in by_report:
            by_report[key] = {
                "filename": r["filename"],
                "report_type": r["report_type"],
                "publish_date": r["publish_date"],
                "texts": [],
            }
        if r["text"] not in [t for t in by_report[key]["texts"]]:
            by_report[key]["texts"].append(r["text"])

    logger.info(f"找到 {len(all_results)} 条相关内容, 来自 {len(by_report)} 份报告")

    # 构建 LLM 分析的上下文
    context_parts = []
    for key, data in by_report.items():
        header = f"[来源: {data['filename']}]"
        if data["publish_date"]:
            header += f" (发布日期: {data['publish_date']})"
        content = "\n".join(data["texts"][:5])
        context_parts.append(f"{header}\n{content}")

    context = "\n\n---\n\n".join(context_parts)
    topics_str = "、".join(topics)

    prompt = f"""你是一位专业的投资分析师。请根据以下从不同时期的财报/研报中检索到的内容，
对 {stock_name}({stock_code}) 进行跨期对比分析。

对比维度: {topics_str}

要求:
1. 明确标注各时期的关键数据
2. 分析核心指标的变化趋势和幅度
3. 解读变化背后的原因(如果能从内容中推断)
4. 给出对未来趋势的判断
5. 如果信息不足以做完整对比，请说明

检索内容:
{context}"""

    if not os.getenv("OPENAI_API_KEY"):
        raise SkillError(
            operation="初始化 LLM",
            reason="未设置 OPENAI_API_KEY",
            next_action="请在 .env 中设置 OPENAI_API_KEY"
        )

    llm = ChatOpenAI(
        model=model if model != "qwen-plus" else os.getenv("OPENAI_MODEL", "kimi-for-coding"),
        api_key=os.getenv("OPENAI_API_KEY"),
        base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
    )

    answer = message_content(llm.invoke(prompt))

    return {
        "stock_code": stock_code,
        "stock_name": stock_name,
        "topics": topics,
        "reports_used": list(by_report.keys()),
        "analysis": answer,
    }


def main():
    # 创建 CLI 助手
    cli = CLIHelper(
        script_name="cross_period.py",
        description="跨期对比分析工具 - 对比同一公司不同时期的财报关键指标",
        examples=[
            "python cross_period.py --stock 688981 --topics '营收,净利润,毛利率'",
            "python cross_period.py --stock 600519 --topics '经营情况' --index_dir data/vector_store",
            "python cross_period.py --stock 002594 --topics '研发投入,毛利率' --model qwen-plus",
        ]
    )

    parser = argparse.ArgumentParser(
        description=cli.description,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=cli.format_examples()
    )

    parser.add_argument("--stock", required=True, help="股票代码（如 688981）")
    parser.add_argument("--topics", default="营收,净利润,毛利率,经营情况", help="对比维度（逗号分隔，默认: 营收,净利润,毛利率,经营情况）")
    parser.add_argument("--index_dir", default="data/vector_db", help="统一索引目录（默认: data/vector_db）")
    parser.add_argument("--model", default="qwen-plus", help="LLM 模型（默认: qwen-plus）")
    parser.add_argument("--top_k", type=int, default=8, help="每个维度检索的文档数（默认: 8）")
    args = parser.parse_args()

    try:
        index_dir = args.index_dir
        if not os.path.exists(index_dir) and index_dir == "data/vector_db" and os.path.exists("data/vector_store"):
            index_dir = "data/vector_store"

        if not os.path.exists(index_dir):
            raise SkillError(
                operation="检查索引目录",
                reason=f"索引目录不存在: {index_dir}",
                next_action="请先运行 python preprocess.py 构建统一索引"
            )

        topics = [t.strip() for t in args.topics.split(",")]
        stock_name = STOCK_NAMES.get(args.stock, args.stock)

        logger.info(f"{stock_name}({args.stock}) 跨期对比分析")
        logger.info(f"对比维度: {', '.join(topics)}")

        vectorstore, chunks_metadata = load_unified_index(index_dir)

        result = cross_period_analysis(
            args.stock, topics, vectorstore, chunks_metadata, args.model
        )

        if result:
            print(f"\n{'=' * 60}")
            print(f"[跨期对比分析] {result['stock_name']}")
            print(f"[对比维度] {', '.join(result['topics'])}")
            print(f"[使用报告] {len(result['reports_used'])} 份")
            print(f"{'=' * 60}")
            print(f"\n{result['analysis']}\n")
            print(f"{'=' * 60}")

            output = {
                "status": "success",
                "module": "compare",
                "summary": {
                    "stock_code": result["stock_code"],
                    "stock_name": result["stock_name"],
                    "topics": result["topics"],
                    "reports_used": result["reports_used"],
                },
                "artifacts": [],
                "sources": [{"type": "vector-index", "path": args.index_dir}],
                "warnings": [],
                "errors": [],
                "next_actions": [],
            }
            print(json.dumps(output, ensure_ascii=False, indent=2))
        else:
            logger.warning("未找到相关内容，无法进行对比分析")
            output = {
                "status": "unavailable",
                "module": "compare-period",
                "summary": {},
                "artifacts": [],
                "sources": [],
                "warnings": ["no content found in index for this stock"],
                "errors": ["未能完成分析, 请确认索引中包含该公司的报告"],
                "next_actions": ["build an index for this stock"],
            }
            print(json.dumps(output, ensure_ascii=False))

        sys.exit(0)

    except SkillError as e:
        print(format_error_message(e), file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        error = SkillError(
            operation="跨期对比分析",
            reason=f"未预期的错误: {type(e).__name__}: {e}",
            next_action="请检查索引文件、API Key 配置或网络连接"
        )
        print(format_error_message(error), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
