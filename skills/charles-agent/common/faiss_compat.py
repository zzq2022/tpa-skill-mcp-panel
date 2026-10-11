"""FAISS persistence helpers for Windows paths containing non-ASCII text."""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import Any


def _needs_bridge(path: Path) -> bool:
    return os.name == "nt" and not str(path).isascii()


def _copy_index_files(source: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    files = list(source.glob("*.faiss")) + list(source.glob("*.pkl"))
    if not files:
        raise RuntimeError(f"FAISS index files not found in {source}")
    for path in files:
        shutil.copy2(path, target / path.name)


def save_faiss_local(vectorstore: Any, index_dir: str | Path) -> None:
    """Save a LangChain FAISS store, bridging native Windows path limits."""
    target = Path(index_dir)
    target.mkdir(parents=True, exist_ok=True)
    if not _needs_bridge(target):
        vectorstore.save_local(str(target))
        return
    with tempfile.TemporaryDirectory(prefix="faiss_save_") as temp_dir:
        temporary = Path(temp_dir)
        vectorstore.save_local(str(temporary))
        _copy_index_files(temporary, target)


def load_faiss_local(
    faiss_class: Any,
    index_dir: str | Path,
    embeddings: Any,
) -> Any:
    """Load a LangChain FAISS store, bridging native Windows path limits."""
    source = Path(index_dir)
    kwargs = {"allow_dangerous_deserialization": True}
    if not _needs_bridge(source):
        return faiss_class.load_local(str(source), embeddings, **kwargs)
    with tempfile.TemporaryDirectory(prefix="faiss_load_") as temp_dir:
        temporary = Path(temp_dir)
        _copy_index_files(source, temporary)
        return faiss_class.load_local(str(temporary), embeddings, **kwargs)
