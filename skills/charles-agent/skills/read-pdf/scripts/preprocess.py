#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据预处理引擎 (preprocess.py) - 统一批量解析 PDF、提取结构化元数据与构建 FAISS 向量索引

功能:
  1. 扫描工作区或指定目录下的所有 PDF 财报/研报
  2. 使用 PyMuPDF 高性能解析 PDF 文本并记录精确页码映射
  3. 从文件名和文本内容中提取元数据 (股票代码、公司名称、报告期、报告类型等)
  4. 按 chunk 切分文本，每个 chunk 原生注入完整元数据 (source, page, period, stock_code)
  5. 将文档元数据存入工作区 SQLite documents.db
  6. 构建统一 FAISS 向量索引与 chunks.json，支持下游 query_report 和 five_step_analysis 无感精确溯源

用法:
  python preprocess.py --workspace workspaces/601318_pingan
  python preprocess.py --pdf_dir data/financial_reports --output_dir data/vector_db
  python preprocess.py --workspace workspaces/601318_pingan --rebuild
  python preprocess.py --workspace workspaces/601318_pingan --skip-index
"""

import argparse
import io
import json
import os
import pickle
import re
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

if sys.platform == "win32":
    if hasattr(sys.stdout, "buffer") and not getattr(sys.stdout, "closed", False):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    if hasattr(sys.stderr, "buffer") and not getattr(sys.stderr, "closed", False):
        try:
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

import pymupdf
from langchain_community.vectorstores import FAISS
from langchain_text_splitters import RecursiveCharacterTextSplitter

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from runtime.env_loader import load_dotenv_from_root
load_dotenv_from_root()

# 添加 common 目录到 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "common"))
from error_handler import SkillError, format_error_message
from logger import SkillLogger, LogLevel
from cli_helper import CLIHelper
from faiss_compat import save_faiss_local
from embedding_client import OpenAICompatibleEmbeddings, resolve_embedding_config

# 初始化日志
logger = SkillLogger("preprocess", level=LogLevel.INFO)

# 常见股票名称 -> 代码映射
STOCK_CODE_MAP = {
    "中芯国际": "688981",
    "贵州茅台": "600519",
    "比亚迪": "002594",
    "宁德时代": "300750",
    "隆基绿能": "601012",
    "招商银行": "600036",
    "中国平安": "601318",
    "五粮液": "000858",
    "海天味业": "603288",
    "恒瑞医药": "600276",
    "中国电信": "601728",
    "中国移动": "600941",
    "中国联通": "600050",
    "中信证券": "600030",
    "中国太保": "601601",
    "中国人寿": "601628",
    "新华保险": "601336",
}

# 报告类型识别规则
REPORT_TYPE_PATTERNS = [
    (r"年度报告|年报", "年报"),
    (r"半年度报告|半年报", "半年报"),
    (r"第一季度报告|一季度报告|一季报", "一季报"),
    (r"第三季度报告|三季度报告|三季报", "三季报"),
    (r"季度报告|季报", "季报"),
    (r"业绩点评|业绩快报", "业绩点评"),
    (r"深度研究|深度报告|研究报告", "深度研报"),
    (r"调研纪要", "调研纪要"),
]


# ==================== 元数据解析 ====================

def parse_filename(filename: str, parent_rel_path: str = "") -> Dict:
    """
    从 PDF 文件名中提取元数据
    """
    name = os.path.splitext(filename)[0]

    result = {
        "filename": filename,
        "title": name,
        "stock_code": "",
        "stock_name": "",
        "source": f"{parent_rel_path}/{filename}".lstrip("/") if parent_rel_path else filename,
        "report_type": "",
        "report_period": "",
        "publish_date": "",
    }

    # 1. 提取 6 位股票代码
    code_match = re.search(r"(\d{6})", name)
    if code_match:
        result["stock_code"] = code_match.group(1)

    # 2. 匹配已知股票名称
    for s_name, s_code in STOCK_CODE_MAP.items():
        if s_name in name:
            result["stock_name"] = s_name
            if not result["stock_code"]:
                result["stock_code"] = s_code
            break

    # 3. 提取报告类型与报告期
    for pattern, r_type in REPORT_TYPE_PATTERNS:
        if re.search(pattern, name):
            result["report_type"] = r_type
            break

    year_match = re.search(r"(20\d{2})", name)
    if year_match:
        year = year_match.group(1)
        if "三季度" in name or "三季报" in name or "Q3" in name.upper():
            result["report_period"] = f"{year}Q3"
        elif "半年度" in name or "半年报" in name or "H1" in name.upper():
            result["report_period"] = f"{year}H1"
        elif "一季度" in name or "一季报" in name or "Q1" in name.upper():
            result["report_period"] = f"{year}Q1"
        else:
            result["report_period"] = f"{year}FY"

    date_match = re.search(r"(20\d{2}[-_.]\d{2}[-_.]\d{2})", name)
    if date_match:
        result["publish_date"] = date_match.group(1).replace("_", "-").replace(".", "-")

    return result


def extract_stock_name_from_text(text: str) -> str:
    """从文本前 2000 字符中尝试识别公司名称"""
    prefix = text[:2000]
    for s_name in STOCK_CODE_MAP:
        if s_name in prefix:
            return s_name
    m = re.search(r"([\u4e00-\u9fa5]{2,10}(?:股份有限公司|集团|公司))", prefix)
    if m:
        return m.group(1).strip()
    return ""


# ==================== PDF 文本提取 ====================

def extract_pdf_text(pdf_path: str) -> Tuple[str, List[Dict]]:
    """
    使用 PyMuPDF 提取 PDF 文本与精确页码信息。
    """
    pages = []
    full_text_parts = []

    try:
        doc = pymupdf.open(pdf_path)
        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text() or ""
            pages.append({
                "page": page_num + 1,
                "char_count": len(text),
                "text": text,
            })
            if text.strip():
                full_text_parts.append(text)
        doc.close()
    except Exception as e:
        logger.error(f"解析 PDF 失败: {pdf_path}: {e}")
        return "", []

    full_text = "\n\n".join(full_text_parts)
    return full_text, pages


# ==================== SQLite 数据库管理 ====================

def init_database(db_path: Path) -> sqlite3.Connection:
    """初始化 SQLite 数据库并创建 documents 表"""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT UNIQUE NOT NULL,
            title TEXT,
            stock_name TEXT,
            stock_code TEXT,
            source TEXT,
            report_type TEXT,
            report_period TEXT,
            publish_date TEXT,
            total_pages INTEGER,
            total_chars INTEGER,
            total_chunks INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    return conn


def save_doc_to_db(conn: sqlite3.Connection, meta: Dict) -> int:
    """保存或更新文档元数据到 SQLite"""
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO documents (
            filename, title, stock_name, stock_code, source,
            report_type, report_period, publish_date, total_pages, total_chars, total_chunks
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(filename) DO UPDATE SET
            title=excluded.title,
            stock_name=excluded.stock_name,
            stock_code=excluded.stock_code,
            source=excluded.source,
            report_type=excluded.report_type,
            report_period=excluded.report_period,
            publish_date=excluded.publish_date,
            total_pages=excluded.total_pages,
            total_chars=excluded.total_chars,
            total_chunks=excluded.total_chunks
    """, (
        meta["filename"],
        meta.get("title", ""),
        meta.get("stock_name", ""),
        meta.get("stock_code", ""),
        meta.get("source", ""),
        meta.get("report_type", ""),
        meta.get("report_period", ""),
        meta.get("publish_date", ""),
        meta.get("total_pages", 0),
        meta.get("total_chars", 0),
        meta.get("total_chunks", 0),
    ))
    conn.commit()
    cursor.execute("SELECT id FROM documents WHERE filename = ?", (meta["filename"],))
    row = cursor.fetchone()
    return row[0] if row else -1


# ==================== 切片与元数据注入 ====================

def chunk_with_metadata(
    full_text: str,
    pages: List[Dict],
    doc_metadata: Dict,
    chunk_size: int = 400,
    chunk_overlap: int = 80,
) -> List[Dict]:
    """
    对文本进行切片，并为每个 chunk 原生注入完整的元数据字典。
    """
    text_splitter = RecursiveCharacterTextSplitter(
        separators=["\n\n", "\n", "。", ".", " ", ""],
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
    )

    chunks = text_splitter.split_text(full_text)

    # 建立页码偏移边界
    page_boundaries = []
    offset = 0
    for p in pages:
        page_boundaries.append({
            "page": p["page"],
            "start": offset,
            "end": offset + p["char_count"],
        })
        offset += p["char_count"]

    result = []
    for chunk in chunks:
        page_num = -1
        chunk_start = full_text.find(chunk[:100])
        if chunk_start >= 0 and page_boundaries:
            for pb in page_boundaries:
                if pb["start"] <= chunk_start < pb["end"]:
                    page_num = pb["page"]
                    break
        if page_num <= 0:
            page_num = 1

        meta = {
            "doc_id": doc_metadata.get("doc_id", -1),
            "source": doc_metadata.get("source", doc_metadata.get("filename", "")),
            "filename": doc_metadata.get("filename", ""),
            "page": page_num,
            "period": doc_metadata.get("report_period", ""),
            "stock_code": doc_metadata.get("stock_code", ""),
            "stock_name": doc_metadata.get("stock_name", ""),
            "report_type": doc_metadata.get("report_type", ""),
        }
        result.append({
            "text": chunk,
            "metadata": meta,
        })

    return result


# ==================== 统一 FAISS 向量库构建 ====================

def build_unified_index(
    chunks: List[Dict],
    index_dir: str,
    embedding_model: Optional[str] = None,
    chunk_size: int = 400,
    chunk_overlap: int = 80,
) -> FAISS:
    """构建 FAISS 向量库，并落盘 chunks.json、page_info.pkl、chunks.pkl 和 index_meta.json"""
    embedding_config = resolve_embedding_config(embedding_model)
    api_key = embedding_config["api_key"]
    base_url = embedding_config["base_url"]
    model = embedding_config["model"]

    missing_settings = [
        setting for setting, value in (
            ("EMBEDDING_API_KEY", api_key),
            ("EMBEDDING_BASE_URL", base_url),
            ("EMBEDDING_BASE_MODEL", model),
        ) if not value
    ]
    if missing_settings:
        raise SkillError(
            operation="初始化 Embedding API",
            reason=f"未设置嵌入配置: {', '.join(missing_settings)}",
            next_action="请在项目根目录 .env 中设置所需的 EMBEDDING_* 变量",
        )

    embeddings = OpenAICompatibleEmbeddings(
        api_key=api_key,
        base_url=base_url,
        model=model,
        batch_size=10,
        logger=logger,
    )

    texts = [c["text"] for c in chunks]
    metadatas = [c["metadata"] for c in chunks]
    chunk_page_map = {c["text"]: c["metadata"].get("page", 1) for c in chunks}

    logger.info(f"正在使用 {model} 生成向量索引 (共 {len(texts)} 个切片)...")
    try:
        vectorstore = FAISS.from_texts(texts, embeddings, metadatas=metadatas)
        vectorstore.page_info = chunk_page_map
    except Exception as e:
        raise SkillError(
            operation="构建 FAISS 索引",
            reason=f"向量化失败: {e}",
            next_action="请检查 Embedding API 配置和网络连接",
        )

    os.makedirs(index_dir, exist_ok=True)
    try:
        save_faiss_local(vectorstore, index_dir)
        logger.info(f"FAISS 索引已保存: {index_dir}")

        with open(os.path.join(index_dir, "chunks.json"), "w", encoding="utf-8") as f:
            json.dump(chunks, f, ensure_ascii=False, indent=2)

        with open(os.path.join(index_dir, "page_info.pkl"), "wb") as f:
            pickle.dump(chunk_page_map, f)

        with open(os.path.join(index_dir, "chunks.pkl"), "wb") as f:
            pickle.dump(texts, f)

        meta = {
            "total_chunks": len(chunks),
            "embedding_model": model,
            "embedding_base_url": base_url,
            "chunk_size": chunk_size,
            "chunk_overlap": chunk_overlap,
            "pages_mapped": sum(1 for v in chunk_page_map.values() if v > 0),
        }
        with open(os.path.join(index_dir, "index_meta.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
    except Exception as e:
        raise SkillError(
            operation="保存 FAISS 索引",
            reason=f"文件写入失败: {e}",
            next_action="请检查目录权限和磁盘空间",
        )

    return vectorstore


# ==================== 执行流水线 ====================

def run_preprocess(
    workspace_dir: Optional[str] = None,
    pdf_dir: Optional[str] = None,
    parsed_dir: Optional[str] = None,
    index_dir: Optional[str] = None,
    db_path: Optional[str] = None,
    rebuild: bool = False,
    skip_index: bool = False,
    embedding_model: Optional[str] = None,
    chunk_size: int = 400,
    chunk_overlap: int = 80,
) -> Dict:
    """
    执行端到端 PDF 预处理与索引构建流水线。
    """
    if workspace_dir:
        ws = Path(workspace_dir).resolve()
        effective_pdf_dir = Path(pdf_dir) if pdf_dir else ws / "data" / "financial_reports"
        effective_parsed_dir = Path(parsed_dir) if parsed_dir else ws / "data" / "parsed"
        effective_index_dir = Path(index_dir) if index_dir else ws / "data" / "vector_db"
        effective_db_path = Path(db_path) if db_path else ws / "data" / "documents.db"
        parent_rel = "data/financial_reports"
    else:
        effective_pdf_dir = Path(pdf_dir) if pdf_dir else Path("data/financial_reports")
        effective_parsed_dir = Path(parsed_dir) if parsed_dir else Path("data/parsed")
        effective_index_dir = Path(index_dir) if index_dir else Path("data/vector_db")
        effective_db_path = Path(db_path) if db_path else Path("data/documents.db")
        parent_rel = str(effective_pdf_dir).replace("\\", "/")

    effective_parsed_dir.mkdir(parents=True, exist_ok=True)
    conn = init_database(effective_db_path)

    if rebuild:
        logger.info("指定了 --rebuild，清除旧记录并重新处理")
        conn.execute("DELETE FROM documents")
        conn.commit()

    # 扫描 PDF 文件
    if not effective_pdf_dir.is_dir():
        logger.warning(f"PDF 目录不存在: {effective_pdf_dir}")
        pdf_files = []
    else:
        pdf_files = sorted([f for f in os.listdir(effective_pdf_dir) if f.lower().endswith(".pdf")])

    if not pdf_files:
        conn.close()
        return {
            "status": "partial",
            "module": "read-pdf",
            "summary": {"total_pdfs": 0, "processed": 0, "total_chunks": 0},
            "artifacts": [],
            "warnings": [f"在目录 {effective_pdf_dir} 中未找到任何 PDF 文件"],
            "errors": [],
            "next_actions": ["请先使用 fetch_financial_data.py 下载 PDF 报告"],
        }

    logger.info(f"扫描到 {len(pdf_files)} 个 PDF 文件")

    all_chunks = []
    success_count = 0
    warnings = []

    for filename in pdf_files:
        pdf_path = effective_pdf_dir / filename
        logger.info(f"正在解析: {filename}")

        # 1. 提取元数据与文本
        meta = parse_filename(filename, parent_rel_path=parent_rel)
        full_text, pages = extract_pdf_text(str(pdf_path))

        if not full_text.strip():
            logger.warning(f"{filename} 未提取到有效文本，可能为扫描件")
            warnings.append(f"{filename} 文本提取为空")
            continue

        if not meta["stock_name"]:
            meta["stock_name"] = extract_stock_name_from_text(full_text)

        meta["total_pages"] = len(pages)
        meta["total_chars"] = len(full_text)

        # 2. 保存解析文本缓存
        stem = Path(filename).stem
        (effective_parsed_dir / f"{stem}_full.txt").write_text(full_text, encoding="utf-8")
        (effective_parsed_dir / f"{stem}_pages.json").write_text(
            json.dumps(pages, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        # 3. 记录元数据到 SQLite
        doc_id = save_doc_to_db(conn, meta)
        meta["doc_id"] = doc_id

        # 4. 生成带元数据切片
        chunks = chunk_with_metadata(
            full_text, pages, meta, chunk_size=chunk_size, chunk_overlap=chunk_overlap
        )
        if chunks:
            meta["total_chunks"] = len(chunks)
            save_doc_to_db(conn, meta)
            all_chunks.extend(chunks)
            success_count += 1

    conn.close()

    artifacts = [
        {"role": "database", "path": str(effective_db_path)},
        {"role": "parsed_dir", "path": str(effective_parsed_dir)},
    ]

    # 5. 构建 FAISS 索引
    if not skip_index and all_chunks:
        build_unified_index(
            all_chunks,
            str(effective_index_dir),
            embedding_model=embedding_model,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
        artifacts.append({"role": "vector_db", "path": str(effective_index_dir)})
        artifacts.append({"role": "chunks_json", "path": str(effective_index_dir / "chunks.json")})

    return {
        "status": "success" if success_count > 0 else "partial",
        "module": "read-pdf",
        "summary": {
            "total_pdfs": len(pdf_files),
            "processed": success_count,
            "total_chunks": len(all_chunks),
            "index_dir": str(effective_index_dir) if not skip_index else None,
            "database": str(effective_db_path),
        },
        "artifacts": artifacts,
        "warnings": warnings,
        "errors": [],
        "next_actions": [] if success_count > 0 else ["check pdf files and re-run preprocess"],
    }


# ==================== CLI 主入口 ====================

def main():
    cli = CLIHelper(
        script_name="preprocess.py",
        description="统一数据预处理引擎 - 批量解析 PDF 财报并构建携带原生元数据的 FAISS 向量库",
        examples=[
            "python preprocess.py --workspace workspaces/601318_pingan",
            "python preprocess.py --pdf_dir data/financial_reports --output_dir data/vector_db",
            "python preprocess.py --workspace workspaces/601318_pingan --rebuild",
            "python preprocess.py --workspace workspaces/601318_pingan --skip-index",
        ]
    )

    parser = argparse.ArgumentParser(
        description=cli.description,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=cli.format_examples()
    )

    parser.add_argument("--workspace", default=None, help="工作区根目录（如 workspaces/601318_pingan）")
    parser.add_argument("--pdf_dir", default=None, help="PDF 文件目录（默认: <workspace>/data/financial_reports 或 ./data/financial_reports）")
    parser.add_argument("--output_dir", default=None, help="向量库输出目录（默认: <workspace>/data/vector_db 或 ./data/vector_db）")
    parser.add_argument("--parsed_dir", default=None, help="解析文本输出目录（默认: <workspace>/data/parsed 或 ./data/parsed）")
    parser.add_argument("--db_path", default=None, help="SQLite 数据库路径（默认: <workspace>/data/documents.db）")
    parser.add_argument("--rebuild", action="store_true", help="清空旧记录并全量重新构建")
    parser.add_argument("--skip-index", action="store_true", help="仅解析文本并存入 SQLite，不构建 FAISS 索引")
    parser.add_argument("--chunk_size", type=int, default=int(os.getenv("EMBEDDING_CHUNK_SIZE", "400")), help="切片大小")
    parser.add_argument("--chunk_overlap", type=int, default=int(os.getenv("EMBEDDING_CHUNK_OVERLAP", "80")), help="切片重叠")
    parser.add_argument("--embedding_model", default=None, help="Embedding 模型名称")

    args = parser.parse_args()

    try:
        result = run_preprocess(
            workspace_dir=args.workspace,
            pdf_dir=args.pdf_dir,
            parsed_dir=args.parsed_dir,
            index_dir=args.output_dir,
            db_path=args.db_path,
            rebuild=args.rebuild,
            skip_index=args.skip_index,
            embedding_model=args.embedding_model,
            chunk_size=args.chunk_size,
            chunk_overlap=args.chunk_overlap,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        sys.exit(0 if result["status"] == "success" else 1)
    except SkillError as e:
        print(format_error_message(e), file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        error = SkillError(
            operation="执行 PDF 预处理与建库",
            reason=f"未预期的错误: {type(e).__name__}: {e}",
            next_action="请检查 PDF 文件是否损坏、API Key 配置或网络连接",
        )
        print(format_error_message(error), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
