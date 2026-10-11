"""Shared embeddings adapter for OpenAI-compatible APIs."""

from __future__ import annotations

import os
from typing import Any, Iterable

from langchain_core.embeddings import Embeddings
from openai import OpenAI


def resolve_embedding_config(embedding_model: str | None = None) -> dict[str, str]:
    """Resolve the shared OpenAI-compatible embedding configuration."""
    return {
        "api_key": os.getenv("EMBEDDING_API_KEY", ""),
        "base_url": os.getenv("EMBEDDING_BASE_URL", ""),
        "model": embedding_model or os.getenv("EMBEDDING_BASE_MODEL", ""),
    }


class OpenAICompatibleEmbeddings(Embeddings):
    """Normalize and batch text before calling an OpenAI-compatible endpoint."""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        batch_size: int = 10,
        client: Any = None,
        logger: Any = None,
    ) -> None:
        if batch_size < 1:
            raise ValueError("batch_size must be at least 1")
        self.client = client or OpenAI(api_key=api_key, base_url=base_url)
        self.model = model
        self.batch_size = batch_size
        self.logger = logger

    @staticmethod
    def _clean_text(text: str) -> str:
        cleaned = "".join(
            character
            for character in str(text)
            if ord(character) >= 32 or character in "\n\r\t"
        )
        return cleaned if cleaned.strip() else "."

    def _embed(self, texts: Iterable[str]) -> list[list[float]]:
        normalized = [self._clean_text(text) for text in texts]
        results: list[list[float]] = []
        for start in range(0, len(normalized), self.batch_size):
            batch = normalized[start : start + self.batch_size]
            if self.logger is not None:
                batch_number = start // self.batch_size + 1
                self.logger.info(f"embedding batch {batch_number}: {len(batch)} texts")
            response = self.client.embeddings.create(input=batch, model=self.model)
            results.extend(item.embedding for item in response.data)
        return results

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._embed(texts)

    def embed_query(self, text: str) -> list[float]:
        return self._embed([text])[0]
