#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
跨公司对比分析工具

功能: 从统一 FAISS 索引中检索不同公司的研报/财报内容，
     由 LLM 横向对比分析指定主题的差异。

用法:
    python cross_company.py --stocks 688981,600519 --topic "经营状况和盈利能力"
    python cross_company.py --stocks 688981,600519 --topic "核心竞争力" --index_dir data/vector_store
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
logger = SkillLogger("cross_company", level=LogLevel.INFO)


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

    chunks_json_path = os.path.join(index_dir, "chunks.json")
    chunks_metadata = {}
    if os.path.exists(chunks_json_path):
        with open(chunks_json_path, "r", encoding="utf-8") as f:
            chunks_data = json.load(f)
        for c in chunks_data:
            chunks_metadata[c["text"]] = c.get("metadata", {})

    return vectorstore, chunks_metadata


def search_for_company(vectorstore, chunks_metadata: dict, stock_code: str, topic: str, top_k: int = 6):
    """检索某公司关于特定主题的内容"""
    stock_name = STOCK_NAMES.get(stock_code, stock_code)
    query = f"{stock_name} {topic}"

    docs = vectorstore.similarity_search(query, k=top_k * 3)

    filtered = []
    for doc in docs:
        meta = chunks_metadata.get(doc.page_content, {})
        if meta.get("stock_code") == stock_code:
            filtered.append({
                "text": doc.page_content,
                "filename": meta.get("filename", ""),
                "report_type": meta.get("report_type", ""),
                "source": meta.get("source", ""),
            })
        if len(filtered) >= top_k:
            break

    return filtered


def cross_company_analysis(
    stock_codes: list, topic: str, vectorstore, chunks_metadata: dict, model: str
):
    """执行跨公司对比分析"""
    company_data = {}

    for code in stock_codes:
        name = STOCK_NAMES.get(code, code)
        results = search_for_company(vectorstore, chunks_metadata, code, topic)

        if results:
            company_data[code] = {
                "name": name,
                "results": results,
            }
            logger.info(f"{name}({code}): 检索到 {len(results)} 条相关内容")
        else:
            logger.warning(f"{name}({code}): 未找到相关内容")

    if len(company_data) < 2:
        logger.warning("至少需要 2 家公司的数据才能对比")
        return None

    # 构建对比上下文
    context_parts = []
    for code, data in company_data.items():
        texts = "\n".join([r["text"] for r in data["results"][:4]])
        sources = list(set(r["filename"] for r in data["results"] if r["filename"]))
        source_str = ", ".join(sources[:3]) if sources else "未知来源"
        context_parts.append(
            f"### {data['name']}({code})\n来源: {source_str}\n\n{texts}"
        )

    context = "\n\n---\n\n".join(context_parts)
    names = [company_data[c]["name"] for c in company_data]

    prompt = f"""你是一位专业的投资分析师。请根据以下从各公司财报/研报中检索到的内容，
对 {' 和 '.join(names)} 进行横向对比分析。

对比主题: {topic}

要求:
1. 按对比维度逐一分析各公司的表现
2. 明确数据差异和相对优劣
3. 分析各自的竞争优势和风险点
4. 给出总体对比结论
5. 如果两家公司行业不同，请从各自行业视角分析

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
        "stocks": {c: d["name"] for c, d in company_data.items()},
        "topic": topic,
        "analysis": answer,
    }


def main():
    # 创建 CLI 助手
    cli = CLIHelper(
        script_name="cross_company.py",
        description="跨公司对比分析工具 - 横向对比不同公司的财报关键指标",
        examples=[
            "python cross_company.py --stocks 688981,600519 --topic '经营状况和盈利能力'",
            "python cross_company.py --stocks 688981,600519 --topic '核心竞争力' --index_dir data/vector_store",
            "python cross_company.py --stocks 002594,300750 --topic '研发投入和技术实力' --model qwen-plus",
        ]
    )

    parser = argparse.ArgumentParser(
        description=cli.description,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=cli.format_examples()
    )

    parser.add_argument("--stocks", required=True, help="股票代码（逗号分隔，如 688981,600519）")
    parser.add_argument("--topic", default="经营状况和盈利能力", help="对比主题（默认: 经营状况和盈利能力）")
    parser.add_argument("--index_dir", default="data/vector_db", help="统一索引目录（默认: data/vector_db）")
    parser.add_argument("--model", default="qwen-plus", help="LLM 模型（默认: qwen-plus）")
    parser.add_argument("--top_k", type=int, default=6, help="每家公司检索的文档数（默认: 6）")
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

        stock_codes = [s.strip() for s in args.stocks.split(",")]
        names = [STOCK_NAMES.get(c, c) for c in stock_codes]

        logger.info(f"跨公司对比: {' vs '.join(names)}")
        logger.info(f"主题: {args.topic}")

        vectorstore, chunks_metadata = load_unified_index(index_dir)

        result = cross_company_analysis(
            stock_codes, args.topic, vectorstore, chunks_metadata, args.model
        )

        if result:
            print(f"\n{'=' * 60}")
            print(f"[跨公司对比] {' vs '.join(result['stocks'].values())}")
            print(f"[主题] {result['topic']}")
            print(f"{'=' * 60}")
            print(f"\n{result['analysis']}\n")
            print(f"{'=' * 60}")

            output = {
                "status": "success",
                "module": "compare",
                "summary": {
                    "stocks": result["stocks"],
                    "topic": args.topic,
                },
                "artifacts": [],
                "sources": [{"type": "vector-index", "path": args.index_dir}],
                "warnings": [],
                "errors": [],
                "next_actions": [],
            }
            print(json.dumps(output, ensure_ascii=False, indent=2))
        else:
            logger.warning("未找到足够的数据进行对比分析（至少需要 2 家公司）")
            output = {
                "status": "unavailable",
                "module": "compare-company",
                "summary": {},
                "artifacts": [],
                "sources": [],
                "warnings": ["fewer than 2 companies found in index"],
                "errors": ["未能完成分析, 请确认索引中包含相关公司的报告"],
                "next_actions": ["build an index for the target companies"],
            }
            print(json.dumps(output, ensure_ascii=False))

        sys.exit(0)

    except SkillError as e:
        print(format_error_message(e), file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        error = SkillError(
            operation="跨公司对比分析",
            reason=f"未预期的错误: {type(e).__name__}: {e}",
            next_action="请检查索引文件、API Key 配置或网络连接"
        )
        print(format_error_message(error), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
