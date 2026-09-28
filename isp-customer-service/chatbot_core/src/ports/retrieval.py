"""Retrieval port — a query-in / ranked-chunks-out knowledge backend."""

from __future__ import annotations

from typing import Protocol, TypedDict, runtime_checkable


class ChunkMetadata(TypedDict, total=False):
    """Metadata carried by every KB chunk.

    ``total=False`` — every field is optional, so the schema can grow (e.g. add
    ``lt_keywords`` later) without invalidating already-persisted knowledge bases.
    """

    source: str  # "internet/router_reboot.md"
    topic: str  # "router_reboot" (free tag derived from the filename)
    section: str  # "How to reboot" (the markdown ## header)
    problem_type: str  # "internet" | "tv" | "phone" | ...
    lang: str  # "en"


class RetrievedChunk(TypedDict):
    """One retrieval hit.

    Mirrors the dict the current retrievers already return (keys
    ``document``/``score``/``metadata``/``id``), so this is a *description* of the
    existing contract, not a rewrite. Implementations may add extra keys
    (``distance``, ``hybrid_score``, ``semantic_score``) without breaking it.
    """

    document: str  # the chunk text
    score: float  # similarity; true cosine [0..1] once index_type=flatip
    metadata: ChunkMetadata
    id: str


@runtime_checkable
class RetrieverPort(Protocol):
    """A swappable knowledge-retrieval backend.

    The port earned its keep: it was written against the v1 FAISS retrievers, and when
    wave 5 deleted them the agent core needed no change at all. Today
    ``adapters/retrieval/lexical.py`` (files, the default and the fallback) and
    ``adapters/retrieval/qdrant_store.py::QdrantRetriever`` (sparse + dense, fused in
    Qdrant) satisfy it, and `KB_BACKEND` chooses between them at startup.
    """

    def retrieve(
        self,
        query: str,
        top_k: int | None = None,
        threshold: float | None = None,
        filter_metadata: dict | None = None,
    ) -> list[RetrievedChunk]:
        """Return chunks ranked most- to least-relevant for ``query``."""
        ...

    def is_loaded(self) -> bool:
        """True if a knowledge base is loaded and searchable.

        Replaces the FAISS-specific ``retriever.vector_store.index.ntotal`` peek
        that currently leaks into the agent (``agent/tools.py``).
        """
        ...

    def load(self, name: str = "default") -> bool:
        """Load a persisted KB by name. Returns False if it does not exist."""
        ...

    def save(self, name: str = "default") -> None:
        """Persist the current KB under ``name``."""
        ...
