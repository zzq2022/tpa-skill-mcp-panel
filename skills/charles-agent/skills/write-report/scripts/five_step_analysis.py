#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
国泰君安"五步法"分析引擎

功能：按照五步法框架（信息差->逻辑差->预期差->催化剂->结论），
      结合 RAG 财报数据，逐步调用 LLM 生成深度分析。
      每一步的输出作为下一步的输入，形成递进式分析链。

依赖：需要先通过 read-pdf Skill 构建好 FAISS 索引。

用法：
    python five_step_analysis.py --index_dir <索引目录> --stock_name <公司名称> --output_dir <输出目录>
    python five_step_analysis.py --index_dir data/vector_db --stock_name 贵州茅台 --output_dir output/
    python five_step_analysis.py --index_dir data/vector_db --stock_name 贵州茅台 --focus catalyst
"""

import argparse
import json
import os
import pickle
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from runtime.env_loader import load_dotenv_from_root
load_dotenv_from_root()

from langchain_openai import ChatOpenAI
from langchain_community.vectorstores import FAISS

# 添加 common 目录到 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'common'))
from error_handler import SkillError, format_error_message
from logger import SkillLogger, LogLevel
from cli_helper import CLIHelper
from llm_client import message_content
from faiss_compat import load_faiss_local
from embedding_client import OpenAICompatibleEmbeddings

# 初始化日志
logger = SkillLogger("five_step_analysis", level=LogLevel.INFO)

# 导入五步法 Prompt 模板
sys.path.insert(0, os.path.dirname(__file__))
from prompts import FIVE_STEP_CONFIG


STEP_MAX_ATTEMPTS = 2


def load_rag_index(index_dir: str) -> Tuple[FAISS, dict]:
    """加载 FAISS 索引和页码映射"""
    api_key = os.getenv("EMBEDDING_API_KEY") or os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("EMBEDDING_BASE_URL", "https://api.siliconflow.cn/v1")
    model = os.getenv("EMBEDDING_BASE_MODEL", "BAAI/bge-large-zh-v1.5")
    if not api_key:
        raise SkillError(
            operation="初始化 Embedding API",
            reason="未设置 API Key",
            next_action="请在 .env 中设置 EMBEDDING_API_KEY 或 OPENAI_API_KEY"
        )

    embeddings = OpenAICompatibleEmbeddings(
        api_key=api_key,
        base_url=base_url,
        model=model,
        batch_size=100,
    )

    try:
        vectorstore = load_faiss_local(FAISS, index_dir, embeddings)
    except Exception as e:
        raise SkillError(
            operation="加载 FAISS 索引",
            reason=f"索引加载失败: {e}",
            next_action=f"请检查索引目录是否正确: {index_dir}"
        )

    page_info = {}
    page_info_path = os.path.join(index_dir, "page_info.pkl")
    if os.path.exists(page_info_path):
        with open(page_info_path, "rb") as f:
            page_info = pickle.load(f)

    return vectorstore, page_info


def rag_retrieve(
    vectorstore: FAISS,
    query: str,
    page_info: dict,
    top_k: int = 6,
) -> Tuple[str, List[int], List[dict]]:
    """
    从 RAG 索引中检索相关内容。

    Returns:
        context: 拼接后的上下文文本
        source_pages: 来源页码列表
        evidence: 包含元数据的证据列表
    """
    docs = vectorstore.similarity_search(query, k=top_k)

    context_parts = []
    source_pages = []
    evidence = []
    seen_locators = set()

    for doc in docs:
        context_parts.append(doc.page_content)
        metadata = getattr(doc, "metadata", {}) or {}
        page = metadata.get("page") or page_info.get(doc.page_content.strip(), -1)
        if page and page > 0:
            source_pages.append(page)

        src = metadata.get("source")
        period = metadata.get("period")
        if src and page and page > 0:
            locator = f"{src}#page={page}"
            if locator not in seen_locators:
                seen_locators.add(locator)
                evidence.append({
                    "locator": locator,
                    "source_type": "filing",
                    "period": period or None,
                    "as_of": None,
                    "field": None,
                    "formula": None,
                    "confidence": "medium",
                })

    context = "\n\n---\n\n".join(context_parts)
    return context, sorted(set(source_pages)), evidence


def run_single_step(
    step_config: dict,
    stock_name: str,
    vectorstore: FAISS,
    page_info: dict,
    llm,
    index_dir: str,
    previous_analysis: str = "",
) -> dict:
    """
    执行五步法中的单个步骤。

    Args:
        step_config: 该步骤的配置（来自 FIVE_STEP_CONFIG）
        stock_name: 公司名称
        vectorstore: FAISS 索引
        page_info: 页码映射
        llm: LLM 实例
        previous_analysis: 前面步骤的分析结果

    Returns:
        步骤结果字典
    """
    step_num = step_config["step"]
    step_name = step_config["name"]

    logger.info(f"Step {step_num}: {step_name}")

    # RAG 检索相关数据及原生元数据证据
    rag_query = f"{stock_name} {step_config['rag_query']}"
    context, source_pages, evidence = rag_retrieve(vectorstore, rag_query, page_info)
    logger.info(f"RAG 检索到 {len(context)} 字符的相关数据，来源页码: {source_pages}")

    # 构建 Prompt
    prompt = step_config["prompt_template"].format(
        stock_name=stock_name,
        context=context,
        previous_analysis=previous_analysis if previous_analysis else "（这是第一步分析，无前置分析结果）",
    )

    # 调用 LLM
    logger.info("正在分析...")
    analysis = message_content(llm.invoke(prompt))
    logger.info(f"生成 {len(analysis)} 字符的分析结果")

    has_period = any(item.get("period") for item in evidence)
    if not evidence:
        evidence_status = "unavailable"
        limitations = ["RAG 未返回可定位页码"]
    elif step_config["name_en"] == "logic_gap" and has_period:
        evidence_status = "available"
        limitations = []
    elif step_config["name_en"] == "expectation_gap":
        evidence_status = "unavailable"
        limitations = ["财报 RAG 不包含可验证的一致预期"]
    else:
        evidence_status = "partial"
        limitations = ["仅使用财报 RAG，缺少外部交叉验证"]

    return {
        "step": step_num,
        "name": step_name,
        "name_en": step_config["name_en"],
        "analysis": analysis,
        "source_pages": source_pages,
        "rag_query": rag_query,
        "evidence": evidence,
        "evidence_status": evidence_status,
        "limitations": limitations,
    }


def _safe_output_stem(value: str) -> str:
    cleaned = re.sub(r"[^\w\s-]", "_", str(value or ""), flags=re.UNICODE)
    cleaned = re.sub(r"[\s_]+", "_", cleaned).strip("_.-")
    return cleaned[:80] or "research-document"


def _analysis_identity(
    index_dir: str,
    stock_name: str,
    model: str,
    step_configs: list[dict],
) -> dict:
    return {
        "stock_name": stock_name,
        "model": model,
        "index_dir": index_dir,
        "selected_steps": [config["name_en"] for config in step_configs],
    }


def _load_completed_steps(output_file: str, identity: dict) -> list[dict]:
    path = Path(output_file)
    if not path.is_file():
        return []
    try:
        existing = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning(f"忽略不可读取的已有分析结果: {exc}")
        return []
    if any(existing.get(key) != value for key, value in identity.items()):
        return []

    by_name = {
        str(step.get("name_en") or ""): step
        for step in existing.get("steps") or []
        if isinstance(step, dict) and str(step.get("analysis") or "").strip()
    }
    completed = []
    for name_en in identity["selected_steps"]:
        step = by_name.get(name_en)
        if not step:
            break
        completed.append(step)
    return completed


def _build_analysis_result(
    identity: dict,
    results: list[dict],
    failed_step: dict = None,
) -> dict:
    all_pages = sorted({page for item in results for page in item.get("source_pages", [])})
    statuses = [item.get("evidence_status", "unavailable") for item in results]
    incomplete = len(results) < len(identity["selected_steps"])
    if failed_step or incomplete:
        analysis_status = "partial" if results else "unavailable"
    elif statuses and all(status == "available" for status in statuses):
        analysis_status = "success"
    elif any(status in {"available", "partial"} for status in statuses):
        analysis_status = "partial"
    else:
        analysis_status = "unavailable"

    analysis_result = {
        **identity,
        "analysis_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "steps": results,
        "all_source_pages": all_pages,
        "analysis_status": analysis_status,
    }
    if failed_step:
        analysis_result["failed_step"] = failed_step
    return analysis_result


def _save_analysis_result(output_file: str, analysis_result: dict) -> None:
    Path(output_file).write_text(
        json.dumps(analysis_result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info(f"分析结果已保存: {output_file}")


def _print_result_summary(analysis_result: dict, output_file: str) -> None:
    failed_step = analysis_result.get("failed_step") or {}
    warnings = [
        limitation
        for item in analysis_result["steps"]
        for limitation in item.get("limitations") or []
    ]
    if failed_step:
        warnings.append(
            f"Step {failed_step['step']} {failed_step['name']} 失败: "
            f"{failed_step['error_type']}: {failed_step['error_message']}"
        )
    try:
        print(json.dumps({
            "status": analysis_result["analysis_status"],
            "module": "five_step_analysis",
            "stock_name": analysis_result["stock_name"],
            "steps_completed": len(analysis_result["steps"]),
            "output_file": output_file,
            "all_source_pages": analysis_result["all_source_pages"],
            "warnings": warnings,
            "errors": [],
            "next_actions": ["rerun to resume the failed step"] if failed_step else [],
        }, ensure_ascii=False, indent=2))
    except (ValueError, OSError):
        pass


def run_five_step_analysis(
    index_dir: str,
    stock_name: str,
    output_dir: str,
    model: str = "deepseek-v3",
    focus: str = None,
) -> dict:
    """
    执行完整的五步法分析。

    Args:
        index_dir: FAISS 索引目录
        stock_name: 公司名称
        output_dir: 输出目录
        model: LLM 模型名称
        focus: 聚焦某个步骤进行深入分析（可选）

    Returns:
        完整的分析结果
    """
    # 确定要执行的步骤
    if focus:
        step_configs = [s for s in FIVE_STEP_CONFIG if s["name_en"] == focus or s["name"] == focus]
        if not step_configs:
            logger.warning(f"未找到步骤 '{focus}'，将执行全部五步")
            step_configs = FIVE_STEP_CONFIG
    else:
        step_configs = FIVE_STEP_CONFIG

    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, f"{_safe_output_stem(stock_name)}_analysis.json")
    identity = _analysis_identity(
        index_dir,
        stock_name,
        model,
        step_configs,
    )
    results = _load_completed_steps(output_file, identity)
    completed_names = {item["name_en"] for item in results}
    accumulated_analysis = "".join(
        f"\n\n### Step {item['step']}: {item['name']}\n{item['analysis']}"
        for item in results
    )

    if results:
        logger.info(f"复用 {len(results)} 个已完成步骤")

    logger.info(f"加载 RAG 索引: {index_dir}")
    vectorstore, page_info = load_rag_index(index_dir)

    if not os.getenv("OPENAI_API_KEY"):
        raise SkillError(
            operation="初始化 LLM",
            reason="未设置 OPENAI_API_KEY",
            next_action="请在 .env 中设置 OPENAI_API_KEY"
        )

    llm = ChatOpenAI(
        model=model if model not in ("deepseek-v3", "qwen-plus") else os.getenv("OPENAI_MODEL", "kimi-for-coding"),
        api_key=os.getenv("OPENAI_API_KEY"),
        base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
    )

    for config in step_configs:
        if config["name_en"] in completed_names:
            continue

        step_result = None
        for attempt in range(1, STEP_MAX_ATTEMPTS + 1):
            try:
                step_result = run_single_step(
                    config,
                    stock_name,
                    vectorstore,
                    page_info,
                    llm,
                    index_dir,
                    previous_analysis=accumulated_analysis,
                )
                break
            except Exception as exc:
                logger.warning(
                    f"Step {config['step']} 第 {attempt}/{STEP_MAX_ATTEMPTS} 次失败: "
                    f"{type(exc).__name__}: {exc}"
                )
                if attempt == STEP_MAX_ATTEMPTS:
                    failed_step = {
                        "step": config["step"],
                        "name": config["name"],
                        "name_en": config["name_en"],
                        "attempts": attempt,
                        "error_type": type(exc).__name__,
                        "error_message": str(exc),
                    }
                    analysis_result = _build_analysis_result(identity, results, failed_step)
                    _save_analysis_result(output_file, analysis_result)
                    _print_result_summary(analysis_result, output_file)
                    return analysis_result

        assert step_result is not None
        results.append(step_result)

        # 将当前步骤的分析结果累加，供下一步使用
        accumulated_analysis += f"\n\n### Step {config['step']}: {config['name']}\n{step_result['analysis']}"
        analysis_result = _build_analysis_result(identity, results)
        _save_analysis_result(output_file, analysis_result)

    analysis_result = _build_analysis_result(identity, results)
    _print_result_summary(analysis_result, output_file)
    return analysis_result


def main():
    # 创建 CLI 助手
    cli = CLIHelper(
        script_name="five_step_analysis.py",
        description="国泰君安五步法分析引擎 - 基于 RAG 财报数据生成深度投资分析",
        examples=[
            "python five_step_analysis.py --index_dir data/vector_db --stock_name 贵州茅台",
            "python five_step_analysis.py --index_dir data/vector_db --stock_name 贵州茅台 --output_dir output/",
            "python five_step_analysis.py --index_dir data/vector_db --stock_name 贵州茅台 --focus catalyst",
        ]
    )

    parser = argparse.ArgumentParser(
        description=cli.description,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=cli.format_examples()
    )

    parser.add_argument("--index_dir", required=True, help="FAISS 索引目录")
    parser.add_argument("--stock_name", required=True, help="公司名称（如：贵州茅台）")
    parser.add_argument("--output_dir", default="./output", help="输出目录（默认: ./output）")
    parser.add_argument("--model", default="deepseek-v3", help="LLM 模型（默认: deepseek-v3）")
    parser.add_argument(
        "--focus",
        default=None,
        choices=["information_gap", "logic_gap", "expectation_gap", "catalyst", "conclusion",
                 "信息差", "逻辑差", "预期差", "催化剂", "结论"],
        help="聚焦某个步骤深入分析",
    )
    args = parser.parse_args()

    try:
        if not os.path.exists(args.index_dir):
            raise SkillError(
                operation="检查索引目录",
                reason=f"索引目录不存在: {args.index_dir}",
                next_action="请先使用 read-pdf 技能解析财报并构建索引"
            )

        run_five_step_analysis(
            index_dir=args.index_dir,
            stock_name=args.stock_name,
            output_dir=args.output_dir,
            model=args.model,
            focus=args.focus,
        )
        sys.exit(0)

    except SkillError as e:
        print(format_error_message(e), file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        error = SkillError(
            operation="五步法分析",
            reason=f"未预期的错误: {type(e).__name__}: {e}",
            next_action="请检查索引文件、API Key 配置或网络连接"
        )
        print(format_error_message(error), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
