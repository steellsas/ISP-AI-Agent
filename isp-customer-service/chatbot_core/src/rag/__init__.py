# """RAG system for ISP customer service chatbot."""

# from .embeddings import EmbeddingManager, get_embedding_manager
# from .vector_store import VectorStore, get_vector_store
# from .retriever import Retriever, get_retriever

# __all__ = [
#     "EmbeddingManager",
#     "get_embedding_manager",
#     "VectorStore",
#     "get_vector_store",
#     "Retriever",
#     "get_retriever",
# ]

"""
RAG Module - Retrieval Augmented Generation

Components:
- EmbeddingManager: Text embeddings with caching
- VectorStore: FAISS-based vector storage
- Retriever: Base semantic retriever
- HybridRetriever: Semantic + keyword search
- DocumentProcessor: Smart document chunking
- ScenarioLoader: YAML scenario loading
"""

import threading
from typing import Optional

# from .scenario_loader import ScenarioLoader, get_scenario_loader, TroubleshootingScenario
# Enhanced components
from .document_processor import DocumentProcessor

# Core components
from .embeddings import EmbeddingManager, get_embedding_manager, preload_embedding_model
from .hybrid_retriever import HybridRetriever
from .retriever import Retriever, get_retriever
from .vector_store import VectorStore, get_vector_store

# =============================================================================
# HYBRID RETRIEVER SINGLETON
# =============================================================================

_hybrid_retriever: HybridRetriever | None = None
_hybrid_lock = threading.Lock()


def get_hybrid_retriever(
    keyword_weight: float | None = None,
    top_k: int | None = None,
    similarity_threshold: float | None = None,
) -> HybridRetriever:
    """
    Get or create HybridRetriever singleton.

    Args are resolved from config (``rag_keyword_weight`` / ``rag_top_k`` /
    ``rag_threshold``) when left as ``None``, so the production retrieval knobs
    live in one place (Config/env) instead of being hardcoded here. Explicit
    values still win (used by the eval harness to sweep knobs). Note the
    threshold gates the *semantic cosine* pre-filter inside HybridRetriever
    (applied before the keyword blend), so it stays a real cosine floor.

    Args:
        keyword_weight: Weight for keyword matching (0-1); None -> config
        top_k: Default number of results; None -> config
        similarity_threshold: Minimum cosine similarity; None -> config

    Returns:
        HybridRetriever instance
    """
    global _hybrid_retriever

    if _hybrid_retriever is None:
        with _hybrid_lock:
            if _hybrid_retriever is None:
                # Centralized defaults from config (fall back to prior literals
                # if config is unavailable, e.g. running rag/ in isolation).
                try:
                    from utils import get_config

                    cfg = get_config()
                    if keyword_weight is None:
                        keyword_weight = cfg.rag_keyword_weight
                    if top_k is None:
                        top_k = cfg.rag_top_k
                    if similarity_threshold is None:
                        similarity_threshold = cfg.rag_threshold
                except Exception:
                    keyword_weight = 0.3 if keyword_weight is None else keyword_weight
                    top_k = 5 if top_k is None else top_k
                    similarity_threshold = (
                        0.5 if similarity_threshold is None else similarity_threshold
                    )

                # Get base retriever
                base_retriever = get_retriever(
                    top_k=top_k, similarity_threshold=similarity_threshold
                )

                # Create hybrid wrapper
                _hybrid_retriever = HybridRetriever(
                    retriever=base_retriever, keyword_weight=keyword_weight
                )

    return _hybrid_retriever


# =============================================================================
# INITIALIZATION HELPERS
# =============================================================================

_rag_initialized = False
_init_lock = threading.Lock()


def init_rag(
    kb_name: str = "production", preload_model: bool = True, use_hybrid: bool = True
) -> bool:
    """
    Initialize RAG system.

    Args:
        kb_name: Knowledge base name to load
        preload_model: Preload embedding model in background
        use_hybrid: Use hybrid retriever

    Returns:
        True if initialized successfully
    """
    global _rag_initialized

    with _init_lock:
        if _rag_initialized:
            return True

        try:
            # Preload embedding model in background
            if preload_model:
                preload_embedding_model()

            # Get appropriate retriever
            if use_hybrid:
                retriever = get_hybrid_retriever()
            else:
                retriever = get_retriever()

            # Load knowledge base
            success = retriever.load(kb_name)

            if success:
                _rag_initialized = True

            return success

        except Exception as e:
            import logging

            logging.getLogger(__name__).error(f"RAG init failed: {e}")
            return False


def is_rag_initialized() -> bool:
    """Check if RAG is initialized."""
    return _rag_initialized


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    # Core
    "EmbeddingManager",
    "get_embedding_manager",
    "preload_embedding_model",
    "VectorStore",
    "get_vector_store",
    "Retriever",
    "get_retriever",
    # Enhanced
    "HybridRetriever",
    "get_hybrid_retriever",
    "DocumentProcessor",
    # # Scenarios
    # "ScenarioLoader",
    # "get_scenario_loader",
    # "TroubleshootingScenario",
    # Initialization
    "init_rag",
    "is_rag_initialized",
]
