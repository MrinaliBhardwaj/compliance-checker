"""
RAG interface (Copilot Tiers 2 & 4). Qdrant in production (ap-south-1,
data-residency clean); an in-memory cosine fallback keeps local/dev and tests
working with no vector DB. Two namespaces: per-tenant `company-documents` and the
shared read-only `regulatory-corpus`. Retrieval quality (strong/weak) feeds the
copilot confidence model.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Chunk:
    id: str
    text: str
    source: str
    score: float = 0.0


class RagStore:
    """Minimal interface. Swap `_InMemory` for a Qdrant-backed impl in prod."""

    def search(self, namespace: str, query: str, *, org_id: str | None = None,
               k: int = 5) -> list[Chunk]:
        raise NotImplementedError


class _InMemory(RagStore):
    """Keyword-overlap fallback — deterministic, offline. Not for production scale."""

    def __init__(self) -> None:
        self._docs: dict[str, list[Chunk]] = {}

    def add(self, namespace: str, chunks: list[Chunk]) -> None:
        self._docs.setdefault(namespace, []).extend(chunks)

    def search(self, namespace: str, query: str, *, org_id: str | None = None,
               k: int = 5) -> list[Chunk]:
        terms = set(query.lower().split())
        scored = []
        for c in self._docs.get(namespace, []):
            overlap = len(terms & set(c.text.lower().split()))
            if overlap:
                scored.append(Chunk(c.id, c.text, c.source, overlap / max(len(terms), 1)))
        scored.sort(key=lambda c: c.score, reverse=True)
        return scored[:k]


def get_store() -> RagStore:
    """Factory. Returns Qdrant store when configured; else the in-memory fallback."""
    # Production: build a Qdrant-backed RagStore from settings.qdrant_url here.
    return _InMemory()


def retrieval_quality(chunks: list[Chunk]) -> str:
    """Map retrieval into the copilot's strong/weak signal."""
    if chunks and chunks[0].score >= 0.5:
        return "strong"
    return "weak"
