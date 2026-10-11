#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RAG 问答查询器

功能：基于 FAISS 向量索引，对财报内容进行检索增强生成（RAG）问答。
支持多查询扩展、BM25+向量混合检索、Rerank 精排，并追溯答案来源页码。
支持标准 read-pdf 工作流构建的单文档或多文档索引。
"""

import argparse
import io
import json
import os
import pickle
import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
from typing import List, Set, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from runtime.env_loader import load_dotenv_from_root
load_dotenv_from_root()

import jieba
from rank_bm25 import BM25Okapi
from langchain_openai import ChatOpenAI
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document

# 添加 common 目录到 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'common'))
from error_handler import SkillError, format_error_message
from logger import SkillLogger, LogLevel
from cli_helper import CLIHelper
from llm_client import message_content
from faiss_compat import load_faiss_local
from embedding_client import OpenAICompatibleEmbeddings, resolve_embedding_config

# 初始化日志
logger = SkillLogger("query_report", level=LogLevel.INFO)


def get_embeddings(embedding_config: dict[str, str] | None = None):
    embedding_config = embedding_config or resolve_embedding_config()
    api_key = embedding_config["api_key"]

    missing_settings = [
        setting
        for setting, value in (
            ("EMBEDDING_API_KEY", api_key),
            ("EMBEDDING_BASE_URL", embedding_config["base_url"]),
            ("EMBEDDING_BASE_MODEL", embedding_config["model"]),
        )
        if not value
    ]
    if missing_settings:
        raise SkillError(
            operation="初始化 Embedding API",
            reason=f"未设置嵌入配置: {', '.join(missing_settings)}",
            next_action="请在项目根目录 .env 中设置所需的 EMBEDDING_* 变量",
        )

    return OpenAICompatibleEmbeddings(
        api_key=api_key,
        base_url=embedding_config["base_url"],
        model=embedding_config["model"],
        batch_size=10,
        logger=logger,
    )


def validate_index_embedding_config(
    index_dir: str, embedding_config: dict[str, str]
) -> None:
    """Reject indexes that were not built in the active embedding space."""
    metadata_path = os.path.join(index_dir, "index_meta.json")
    if not os.path.exists(metadata_path):
        raise SkillError(
            operation="验证索引 Embedding 配置",
            reason="索引缺少 index_meta.json，无法确认 Embedding 模型和端点是否兼容",
            next_action="请使用当前环境配置重新运行 build_index.py 构建索引",
        )

    try:
        with open(metadata_path, "r", encoding="utf-8") as file:
            metadata = json.load(file)
    except (OSError, json.JSONDecodeError) as error:
        raise SkillError(
            operation="验证索引 Embedding 配置",
            reason=f"无法读取 index_meta.json: {error}",
            next_action="请删除损坏的索引目录并重新运行 build_index.py",
        ) from error

    expected = {
        "embedding_model": embedding_config["model"],
        "embedding_base_url": embedding_config["base_url"],
    }
    actual = {key: metadata.get(key) for key in expected}
    if actual != expected:
        raise SkillError(
            operation="验证索引 Embedding 配置",
            reason=(
                "索引 Embedding 配置不兼容: "
                f"索引={actual}, 当前={expected}"
            ),
            next_action="请使用当前 EMBEDDING_BASE_MODEL 和 EMBEDDING_BASE_URL 重新运行 build_index.py",
        )


def load_index(index_dir: str, stock_filter: str = None) -> Tuple[FAISS, List[str], dict]:
    """
    加载 FAISS 索引、chunks 和页码映射。
    """
    embedding_config = resolve_embedding_config()
    validate_index_embedding_config(index_dir, embedding_config)
    embeddings = get_embeddings(embedding_config)

    try:
        vectorstore = load_faiss_local(FAISS, index_dir, embeddings)
    except Exception as e:
        raise SkillError(
            operation="加载 FAISS 索引",
            reason=f"索引加载失败: {e}",
            next_action=f"请检查索引目录是否正确: {index_dir}"
        )

    # 检测索引格式: 统一索引有 chunks.json, 旧版索引有 chunks.pkl
    chunks_json_path = os.path.join(index_dir, "chunks.json")
    chunks_pkl_path = os.path.join(index_dir, "chunks.pkl")

    chunks = []
    page_info = {}

    if os.path.exists(chunks_json_path):
        # ---- 多文档索引格式 ----
        with open(chunks_json_path, "r", encoding="utf-8") as f:
            chunks_data = json.load(f)

        # 按股票代码过滤
        if stock_filter:
            chunks_data = [
                c for c in chunks_data
                if c.get("metadata", {}).get("stock_code", "") == stock_filter
            ]
            logger.info(f"股票代码过滤 {stock_filter}: 匹配 {len(chunks_data)} 个 chunks")

        chunks = [c["text"] for c in chunks_data]
        # 从 metadata 中提取页码映射
        for c in chunks_data:
            page = c.get("metadata", {}).get("page", -1)
            if page > 0:
                page_info[c["text"]] = page
        # 将完整 metadata 存到 vectorstore 上供 rag_answer 使用
        vectorstore._chunks_metadata = {
            c["text"]: c.get("metadata", {}) for c in chunks_data
        }

    elif os.path.exists(chunks_pkl_path):
        # ---- 旧版索引格式 (build_index.py 构建) ----
        with open(chunks_pkl_path, "rb") as f:
            chunks = pickle.load(f)

        page_info_path = os.path.join(index_dir, "page_info.pkl")
        if os.path.exists(page_info_path):
            with open(page_info_path, "rb") as f:
                page_info = pickle.load(f)

    else:
        # 无 chunks 文件，仅使用 FAISS 向量检索
        logger.warning("未找到 chunks 文件，将仅使用向量检索（无 BM25 混合）")

    vectorstore.page_info = page_info

    return vectorstore, chunks, page_info


def generate_multi_queries(query: str, llm, num_queries: int = 3) -> List[str]:
    """使用 LLM 生成多个查询变体，从不同角度检索"""
    prompt = f"""你是一个AI助手，负责生成多个不同视角的搜索查询。
给定一个用户问题，生成{num_queries}个不同但相关的查询，以帮助检索更全面的信息。
每个查询应该从不同角度表达相同的信息需求。

原始问题: {query}

请直接输出{num_queries}个查询，每行一个，不要编号和其他内容:"""

    try:
        response = message_content(llm.invoke(prompt))
        queries = [q.strip() for q in response.split("\n") if q.strip()]
        return [query] + queries[:num_queries]
    except Exception as e:
        logger.warning(f"生成多查询失败，仅使用原始查询: {e}")
        return [query]


class HybridRetriever:
    """混合检索器：BM25 关键词检索 + FAISS 向量语义检索"""

    def __init__(self, chunks: List[str], vectorstore: FAISS, alpha: float = 0.5):
        self.chunks = chunks
        self.vectorstore = vectorstore
        self.alpha = alpha

        tokenized = [list(jieba.cut(c)) for c in chunks]
        self.bm25 = BM25Okapi(tokenized)
        self.chunk_to_idx = {c: i for i, c in enumerate(chunks)}

    def search(self, query: str, k: int = 6) -> List[Document]:
        """执行混合检索"""
        # BM25 检索
        tokenized_query = list(jieba.cut(query))
        bm25_scores = self.bm25.get_scores(tokenized_query)
        max_bm25 = max(bm25_scores) if max(bm25_scores) > 0 else 1
        bm25_normalized = [s / max_bm25 for s in bm25_scores]

        # 向量检索
        candidate_k = min(len(self.chunks), max(k * 4, 20))
        vector_results = self.vectorstore.similarity_search_with_score(
            query, k=candidate_k
        )
        vector_scores = {}
        max_dist = max(s for _, s in vector_results) if vector_results else 1
        for doc, dist in vector_results:
            idx = self.chunk_to_idx.get(doc.page_content)
            if idx is not None:
                vector_scores[idx] = 1 - (dist / max_dist) if max_dist > 0 else 0

        bm25_candidates = sorted(
            range(len(self.chunks)),
            key=lambda index: bm25_normalized[index],
            reverse=True,
        )[:candidate_k]
        candidate_indices = set(bm25_candidates) | set(vector_scores)

        # 仅在词法和向量候选的并集内融合，避免全量向量扫描。
        hybrid = []
        for idx in candidate_indices:
            combined = (
                self.alpha * vector_scores.get(idx, 0)
                + (1 - self.alpha) * bm25_normalized[idx]
            )
            hybrid.append((idx, combined))

        hybrid.sort(key=lambda x: x[1], reverse=True)

        results = []
        for idx, score in hybrid[:k]:
            doc = Document(
                page_content=self.chunks[idx],
                metadata={
                    "page": getattr(self.vectorstore, "page_info", {}).get(
                        self.chunks[idx], -1
                    ),
                    "hybrid_score": score,
                },
            )
            results.append(doc)

        return results


def multi_query_hybrid_search(
    query: str,
    hybrid_retriever: HybridRetriever,
    llm,
    initial_k: int = 8,
) -> List[Document]:
    """多查询 + 混合检索，合并去重"""
    queries = generate_multi_queries(query, llm)
    logger.info(f"生成 {len(queries)} 个查询变体")

    seen = set()
    candidates = []

    for q in queries:
        docs = hybrid_retriever.search(q, k=initial_k)
        for doc in docs:
            if doc.page_content not in seen:
                seen.add(doc.page_content)
                candidates.append(doc)

    logger.info(f"共召回 {len(candidates)} 个候选文档")
    return candidates


def build_evidence_records(
    docs: List[Document], page_info: dict, vectorstore=None
) -> List[dict]:
    """Return page-bound excerpts for every document supplied to the LLM."""
    chunks_metadata = getattr(vectorstore, "_chunks_metadata", {}) if vectorstore else {}
    records = []

    for index, doc in enumerate(docs, start=1):
        text = doc.page_content.strip()
        metadata = dict(chunks_metadata.get(text, {}))
        metadata.update(doc.metadata)
        page = metadata.get("page", page_info.get(text, -1))
        record = {
            "evidence_id": f"evidence-{index}",
            "page": page,
            "excerpt": text,
            "scores": {
                "hybrid": metadata.get("hybrid_score"),
            },
        }
        for key in ("filename", "stock_name", "report_type"):
            if metadata.get(key):
                record[key] = metadata[key]
        records.append(record)

    return records


def rag_answer(
    query: str,
    docs: List[Document],
    page_info: dict,
    llm,
    vectorstore=None,
) -> Tuple[str, Set[int], List[dict]]:
    """
    基于检索到的文档生成回答，并返回页码绑定的 evidence。

    Returns:
        answer: LLM 生成的回答
        source_pages: 来源页码集合
        evidence: 带 evidence_id、页码、摘录和检索分数的证据列表
    """
    evidence = build_evidence_records(docs, page_info, vectorstore)
    context = "\n\n---\n\n".join(
        f"[{record['evidence_id']} | PDF页 {record['page']}]\n{record['excerpt']}"
        for record in evidence
    )

    prompt = f"""你是一位专业的投资分析师。请根据以下从财报中检索到的内容，回答用户的问题。

要求：
1. 仅基于提供的上下文回答，如果信息不足请明确说明
2. 涉及数字时保持原始精度
3. 用专业但易懂的语言回答
4. 如果涉及多个方面，请分点阐述
5. 每个数字或可验证结论后必须附上对应的 `[evidence-N]`；不得自行推断字段名称或页码

上下文（来自财报）：
{context}

问题：{query}"""

    answer = message_content(llm.invoke(prompt))

    source_pages = {record["page"] for record in evidence if record["page"] > 0}
    return answer, source_pages, evidence


def main():
    # 创建 CLI 助手
    cli = CLIHelper(
        script_name="query_report.py",
        description="RAG 问答查询器 - 基于 FAISS 索引对财报进行智能问答",
        examples=[
            'python query_report.py --index_dir data/vector_db --query "营收和净利润是多少"',
            'python query_report.py --index_dir data/vector_store --query "主要风险因素" --top_k 8',
            'python query_report.py --index_dir data/vector_store --query "核心竞争力" --stock 688981',
        ]
    )

    parser = argparse.ArgumentParser(
        description=cli.description,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=cli.format_examples()
    )

    parser.add_argument("--index_dir", required=True, help="FAISS 索引目录")
    parser.add_argument("--query", required=True, help="查询问题")
    parser.add_argument("--top_k", type=int, default=6, help="返回文档数（默认: 6）")
    parser.add_argument("--model", default="deepseek-v3", help="LLM 模型（默认: deepseek-v3）")
    parser.add_argument("--alpha", type=float, default=0.5, help="混合检索中向量权重（默认: 0.5）")
    parser.add_argument("--stock", default=None, help="按股票代码过滤（如 688981），仅统一索引有效")
    args = parser.parse_args()

    try:
        # 检查索引目录
        if not os.path.exists(args.index_dir):
            raise SkillError(
                operation="检查索引目录",
                reason=f"索引目录不存在: {args.index_dir}",
                next_action="请先运行 build_index.py 构建索引"
            )

        logger.info("RAG 问答")
        logger.info(f"问题: {args.query}")
        if args.stock:
            logger.info(f"股票代码过滤: {args.stock}")

        # 加载索引
        vectorstore, chunks, page_info = load_index(args.index_dir, stock_filter=args.stock)
        logger.info(f"索引包含 {len(chunks)} 个文本块")

        # 初始化 LLM
        if not os.getenv("OPENAI_API_KEY"):
            raise SkillError(
                operation="初始化 LLM",
                reason="未设置 OPENAI_API_KEY",
                next_action="请在 .env 中设置 OPENAI_API_KEY"
            )

        llm = ChatOpenAI(
            model=args.model if args.model not in ("qwen-plus", "deepseek-v3") else os.getenv("OPENAI_MODEL", "kimi-for-coding"),
            api_key=os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        )

        # 检索
        if chunks:
            hybrid = HybridRetriever(chunks, vectorstore, alpha=args.alpha)
            docs = multi_query_hybrid_search(args.query, hybrid, llm, initial_k=args.top_k)
            docs = docs[: args.top_k]
        else:
            search_kwargs = {"k": args.top_k}
            if args.stock:
                search_kwargs["filter"] = {"stock_code": args.stock}
            docs = vectorstore.similarity_search(args.query, **search_kwargs)

        # 生成回答
        answer, source_pages, evidence = rag_answer(
            args.query, docs, page_info, llm, vectorstore
        )
        source_details = [
            record for record in evidence if record.get("filename")
        ]

        # 输出结果
        print("\n" + "=" * 60)
        print(f"[回答]\n{answer}")
        print(f"\n[来源页码] {sorted(source_pages) if source_pages else '未知'}")

        print("[证据]")
        for record in evidence:
            print(
                f"  - {record['evidence_id']} (PDF页 {record['page']}): "
                f"{record['excerpt']}"
            )

        # 统一索引时显示来源文档详情
        if source_details:
            seen_files = set()
            print("[来源文档]")
            for sd in source_details:
                fn = sd.get("filename", "")
                if fn and fn not in seen_files:
                    seen_files.add(fn)
                    stock = sd.get("stock_name", "")
                    rtype = sd.get("report_type", "")
                    print(f"  - {fn} ({stock} {rtype})")

        print("=" * 60)

        result = {
            "status": "success",
            "query": args.query,
            "answer": answer,
            "source_pages": sorted(source_pages) if source_pages else [],
            "evidence": evidence,
            "source_details": source_details,
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        sys.exit(0)

    except SkillError as e:
        print(format_error_message(e), file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        error = SkillError(
            operation="RAG 问答",
            reason=f"未预期的错误: {type(e).__name__}: {e}",
            next_action="请检查索引文件、API Key 配置或网络连接"
        )
        print(format_error_message(error), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

    result = {
        "status": "success",
        "module": "read-pdf",
        "summary": {"query": args.query, "answer": answer, "docs_used": len(docs)},
        "artifacts": [],
        "sources": [{"type": "pdf-index", "pages": sorted(source_pages)}] + [
            {"type": "pdf-chunk", "filename": sd.get("filename", ""), "stock": sd.get("stock_name", ""), "page": sd.get("page")}
            for sd in source_details if sd.get("filename")
        ],
        "warnings": [],
        "errors": [],
        "next_actions": [],
    }
    if source_details:
        result["summary"]["source_files"] = list({sd.get("filename", "") for sd in source_details if sd.get("filename")})
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
