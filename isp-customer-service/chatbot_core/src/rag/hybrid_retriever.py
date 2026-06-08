"""
Hybrid Retriever — BM25 (keyword) + semantic, fused with Reciprocal Rank Fusion.

Why this design (vs the previous weighted-overlap blend):

- BM25 runs over the FULL corpus, independently of the semantic arm, so exact
  technical matches the embedding model misses (model numbers, "WAN", "5GHz")
  can still surface. The old approach only re-scored the semantic top-k, so a
  doc semantic search dropped could never come back — it was a re-ranker, not a
  real hybrid retriever.

- BM25 is a proper keyword ranking function: IDF (rare words weigh more) + term
  frequency saturation + document-length normalization. The old `overlap * 0.1 +
  technical * 0.2` had none of these.

- Fusion is by RANK (RRF), not by mixing raw scores. Cosine (~0.4–0.8) and BM25
  (unbounded) live on different scales; adding them linearly needs an arbitrary
  weight. RRF only looks at each doc's POSITION in each list, so the scales never
  meet:  score = Σ  wᵢ / (rrf_k + rankᵢ).

Drop-in replacement for the base Retriever (same `retrieve()` signature).
"""

from __future__ import annotations

import logging
import re
from typing import Any

from rank_bm25 import BM25Okapi

try:
    from utils import get_logger
except ImportError:

    def get_logger(name):
        return logging.getLogger(name)


logger = get_logger(__name__)

# RRF dampening constant. 60 is the value from the original RRF paper (Cormack
# et al. 2009) and the default in Elasticsearch / Weaviate. Larger -> rank
# differences matter less (flatter); smaller -> the top ranks dominate. 60 is a
# well-tested, conservative default.
_RRF_K = 60


class HybridRetriever:
    """
    Combine BM25 keyword search with semantic search via Reciprocal Rank Fusion.

    Can be used as a drop-in replacement for the base Retriever.
    """

    def __init__(self, retriever, keyword_weight: float = 0.3, rrf_k: int = _RRF_K):
        """
        Initialize hybrid retriever.

        Args:
            retriever: Base Retriever instance (provides the semantic arm and the
                corpus that the BM25 arm indexes).
            keyword_weight: RRF weight on the BM25 (keyword) arm, 0.0-1.0. The
                semantic arm gets ``1 - keyword_weight``. 0.0 = pure semantic,
                1.0 = pure keyword.
            rrf_k: RRF dampening constant (see ``_RRF_K``).
        """
        self.retriever = retriever
        self.keyword_weight = keyword_weight
        self.rrf_k = rrf_k

        # BM25 index is built lazily from the loaded corpus and rebuilt only when
        # the document count changes (after load / add_documents). -1 = unbuilt.
        self._bm25: BM25Okapi | None = None
        self._bm25_doc_count: int = -1

        # Stop words to drop during tokenization (Lithuanian + English). Keeps the
        # BM25 vocabulary to meaningful terms; common glue words carry no signal.
        self.stop_words = {
            # Lithuanian
            "ir",
            "ar",
            "su",
            "be",
            "per",
            "nuo",
            "iki",
            "apie",
            "pas",
            "tai",
            "kas",
            "kaip",
            "kur",
            "kada",
            "kodėl",
            "kodel",
            "yra",
            "buvo",
            "bus",
            "būti",
            "buti",
            "turi",
            "gali",
            "labai",
            "dabar",
            "jau",
            "dar",
            "tik",
            "net",
            "vis",
            "man",
            "mano",
            "jums",
            "jūsų",
            "jusu",
            # English
            "the",
            "a",
            "an",
            "is",
            "are",
            "was",
            "were",
            "been",
            "have",
            "has",
            "had",
            "do",
            "does",
            "did",
            "will",
            "would",
            "can",
            "could",
            "may",
            "might",
            "must",
            "shall",
            "should",
            "and",
            "or",
            "but",
            "if",
            "then",
            "else",
            "when",
            "where",
            "what",
            "which",
            "who",
            "how",
            "why",
            "this",
            "that",
            "these",
            "those",
            "my",
            "your",
            "his",
            "her",
            "its",
            "our",
            "their",
            "not",
            "no",
            "yes",
            "very",
            "just",
            "only",
            "also",
        }

        logger.info(f"HybridRetriever initialized (keyword_weight={keyword_weight}, rrf_k={rrf_k})")

    # =========================================================================
    # MAIN RETRIEVE METHOD
    # =========================================================================

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        threshold: float | None = None,
        filter_metadata: dict | None = None,
    ) -> list[dict[str, Any]]:
        """
        Hybrid retrieval: semantic + BM25 keyword, fused with RRF.

        Args:
            query: Search query.
            top_k: Number of results to return.
            threshold: Minimum cosine similarity. Gates the SEMANTIC arm only
                (it stays a real cosine floor); the BM25 arm is exact-match and
                high-precision, so it is not thresholded.
            filter_metadata: Metadata filter applied to BOTH arms.

        Returns:
            List of results sorted by fused (RRF) score, best first.
        """
        # Candidate pool per arm. Wider than top_k so RRF has room to pull a doc
        # ranked low in one arm up via the other. The corpus is small, so we can
        # afford a generous pool.
        candidate_k = max(top_k * 5, 20)

        # --- Semantic arm (cosine; threshold gates THIS arm only) ---
        semantic_results = self.retriever.retrieve(
            query=query,
            top_k=candidate_k,
            threshold=threshold,
            filter_metadata=filter_metadata,
        )

        # --- Keyword arm: BM25 over the FULL corpus (independent of semantic) ---
        bm25_results = self._bm25_search(query, candidate_k, filter_metadata)

        if not semantic_results and not bm25_results:
            logger.debug(f"No hybrid results for: {query[:50]}")
            return []

        # --- Reciprocal Rank Fusion ---------------------------------------
        # Each arm contributes  weight / (rrf_k + rank)  to a doc's fused score.
        # Only the doc's POSITION in each list matters, so the cosine-vs-BM25
        # scale mismatch never enters the math.
        semantic_weight = 1.0 - self.keyword_weight
        fused: dict[str, dict[str, Any]] = {}

        def _fuse(arm_results: list[dict[str, Any]], weight: float, score_field: str) -> None:
            for rank, r in enumerate(arm_results, start=1):
                doc_id = r.get("id")
                if doc_id is None:
                    continue
                entry = fused.get(doc_id)
                if entry is None:
                    # First arm to see this doc owns the result dict (document +
                    # metadata). The other arm only adds rank + its raw score.
                    entry = {"result": r, "rrf": 0.0, "semantic_score": 0.0, "bm25_score": 0.0}
                    fused[doc_id] = entry
                entry["rrf"] += weight / (self.rrf_k + rank)
                entry[score_field] = float(r.get("score", 0.0))

        _fuse(semantic_results, semantic_weight, "semantic_score")
        _fuse(bm25_results, self.keyword_weight, "bm25_score")

        # Materialize results, attach diagnostic scores, sort by fused score.
        out: list[dict[str, Any]] = []
        for entry in fused.values():
            result = entry["result"]
            result["semantic_score"] = entry["semantic_score"]
            result["bm25_score"] = entry["bm25_score"]
            result["hybrid_score"] = entry["rrf"]
            result["score"] = entry["rrf"]  # downstream sorts/reads on "score"
            out.append(result)

        out.sort(key=lambda x: x["hybrid_score"], reverse=True)

        results = out[:top_k]
        logger.debug(f"Hybrid retrieval: {len(results)} results for '{query[:30]}...'")
        return results

    def retrieve_with_context(
        self,
        query: str,
        top_k: int | None = None,
        threshold: float | None = None,
        include_scores: bool = True,
    ) -> str:
        """
        Retrieve documents and format as a context string.

        Args:
            query: Query text
            top_k: Number of documents
            threshold: Similarity threshold
            include_scores: Include relevance scores in context

        Returns:
            Formatted context string
        """
        results = self.retrieve(query, top_k=top_k or 3, threshold=threshold)

        if not results:
            return "No relevant information found."

        context_parts = []

        for i, result in enumerate(results, 1):
            doc_text = result["document"]
            score = result.get("hybrid_score", result.get("score", 0))

            if include_scores:
                context_parts.append(f"[Document {i}] (Relevance: {score:.2f})\n{doc_text}")
            else:
                context_parts.append(f"[Document {i}]\n{doc_text}")

        return "\n\n---\n\n".join(context_parts)

    # =========================================================================
    # BM25 KEYWORD ARM
    # =========================================================================

    def _tokenize(self, text: str) -> list[str]:
        """
        Tokenize text for BM25.

        Returns a LIST (not a set) because BM25 needs term frequencies — a word
        repeated in a document should count more than once. Lowercased word/number
        tokens, stop words and 1-char tokens removed (2-char terms like "tv"/"ip"
        are kept on purpose).
        """
        if not text:
            return []
        words = re.findall(r"\b\w+\b", text.lower())
        return [w for w in words if len(w) >= 2 and w not in self.stop_words]

    def _ensure_bm25(self) -> bool:
        """
        Build or refresh the BM25 index from the base retriever's corpus.

        Cheap to call on every retrieve(): it only rebuilds when the corpus size
        changed. Returns True if a usable index is available.
        """
        store = getattr(self.retriever, "vector_store", None)
        documents = getattr(store, "documents", None) if store is not None else None
        if not documents:
            return False
        if self._bm25 is not None and self._bm25_doc_count == len(documents):
            return True

        tokenized = [self._tokenize(doc) for doc in documents]
        if not any(tokenized):  # BM25Okapi needs at least one non-empty doc
            return False

        self._bm25 = BM25Okapi(tokenized)
        self._bm25_doc_count = len(documents)
        logger.info(f"BM25 index built over {len(documents)} documents")
        return True

    def _bm25_search(
        self, query: str, top_k: int, filter_metadata: dict | None
    ) -> list[dict[str, Any]]:
        """
        Rank the full corpus by BM25 and return up to top_k results.

        Docs scoring 0 (no query term present) are skipped — they carry no keyword
        signal and would only add rank noise to the fusion.
        """
        if not self._ensure_bm25():
            return []
        tokens = self._tokenize(query)
        if not tokens:
            return []

        scores = self._bm25.get_scores(tokens)  # one score per corpus doc
        store = self.retriever.vector_store

        # Indices of the highest scorers first.
        ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)

        results: list[dict[str, Any]] = []
        for idx in ranked:
            if scores[idx] <= 0:
                break  # sorted desc: once we hit 0, everything after is 0 too
            metadata = store.metadata[idx]
            if filter_metadata and not self._matches_metadata(metadata, filter_metadata):
                continue
            results.append(
                {
                    "document": store.documents[idx],
                    "metadata": metadata,
                    "id": store.ids[idx],
                    "score": float(scores[idx]),
                }
            )
            if len(results) >= top_k:
                break
        return results

    @staticmethod
    def _matches_metadata(metadata: dict, filter_metadata: dict) -> bool:
        """All filter key==value pairs must match (mirrors base retriever)."""
        return all(metadata.get(k) == v for k, v in filter_metadata.items())

    # =========================================================================
    # PROXY METHODS (delegate to base retriever)
    # =========================================================================

    def load(self, name: str = "default") -> bool:
        """Load knowledge base (proxy to base retriever)."""
        success = self.retriever.load(name)
        if success:
            # Force a BM25 rebuild against the newly loaded corpus.
            self._bm25 = None
            self._bm25_doc_count = -1
            logger.info(f"HybridRetriever loaded KB: {name}")
        return success

    def is_loaded(self) -> bool:
        """Check whether a KB is loaded (proxy to base retriever)."""
        return self.retriever.is_loaded()

    def save(self, name: str = "default"):
        """Save knowledge base (proxy to base retriever)."""
        self.retriever.save(name)
        logger.info(f"HybridRetriever saved KB: {name}")

    def add_documents(
        self,
        documents: list[str],
        metadata: list[dict[str, Any]] | None = None,
        ids: list[str] | None = None,
        batch_size: int = 32,
    ):
        """Add documents (proxy to base retriever). Invalidates the BM25 index."""
        self.retriever.add_documents(
            documents=documents, metadata=metadata, ids=ids, batch_size=batch_size
        )
        # Corpus changed -> _ensure_bm25() will rebuild on next retrieve().
        self._bm25 = None
        self._bm25_doc_count = -1

    def load_documents_from_directory(
        self, directory, file_extension: str = ".md", recursive: bool = True
    ):
        """Load documents from directory (proxy to base retriever)."""
        self.retriever.load_documents_from_directory(
            directory=directory, file_extension=file_extension, recursive=recursive
        )
        self._bm25 = None
        self._bm25_doc_count = -1

    def get_statistics(self) -> dict[str, Any]:
        """Get statistics (proxy + hybrid info)."""
        stats = self.retriever.get_statistics()
        stats["hybrid_enabled"] = True
        stats["keyword_weight"] = self.keyword_weight
        stats["rrf_k"] = self.rrf_k
        stats["bm25_indexed"] = self._bm25 is not None
        return stats

    def clear(self):
        """Clear all data (proxy to base retriever)."""
        if hasattr(self.retriever, "vector_store"):
            self.retriever.vector_store.clear()
        self._bm25 = None
        self._bm25_doc_count = -1
        logger.info("HybridRetriever cleared")

    # =========================================================================
    # CONFIGURATION
    # =========================================================================

    def set_keyword_weight(self, weight: float):
        """
        Update the BM25-arm RRF weight.

        Args:
            weight: New weight (0.0-1.0)
        """
        self.keyword_weight = max(0.0, min(1.0, weight))
        logger.info(f"Keyword weight updated to: {self.keyword_weight}")


# =============================================================================
# EXAMPLE / TEST
# =============================================================================

if __name__ == "__main__":
    # Minimal stand-in for a loaded base retriever: a semantic arm plus a
    # vector_store exposing the parallel documents/metadata/ids lists the BM25
    # arm indexes.
    print("=" * 60)
    print("Testing HybridRetriever (BM25 + semantic, RRF)")
    print("=" * 60)

    _DOCS = [
        "Internetas neveikia. Patikrinkite WAN kabelį ir router lemputės.",
        "Lėtas internetas gali būti dėl WiFi trukdžių 2.4GHz dažnyje.",
        "TV dekoderis neveikia. Perkraukite įrenginį.",
    ]
    _META = [{"source": "test.md"}, {"source": "test2.md"}, {"source": "test3.md"}]
    _IDS = ["test.md_0", "test2.md_1", "test3.md_2"]

    class MockVectorStore:
        documents = _DOCS
        metadata = _META
        ids = _IDS

    class MockRetriever:
        vector_store = MockVectorStore()

        def retrieve(self, query, top_k=5, threshold=None, filter_metadata=None):
            # Pretend semantic search returns all docs with descending cosine.
            scored = [
                {"document": d, "score": s, "metadata": m, "id": i}
                for d, m, i, s in zip(_DOCS, _META, _IDS, [0.85, 0.75, 0.65])
            ]
            return scored[:top_k]

        def load(self, name):
            return True

        def save(self, name):
            pass

        def get_statistics(self):
            return {"total_documents": len(_DOCS)}

    hybrid = HybridRetriever(MockRetriever(), keyword_weight=0.3)

    for query in ["neveikia internetas WAN", "lėtas WiFi 2.4GHz", "TV dekoderis"]:
        print(f"\nQuery: '{query}'")
        for r in hybrid.retrieve(query, top_k=2):
            print(f"  [rrf={r['hybrid_score']:.4f}] {r['document'][:50]}...")
            print(f"       semantic={r['semantic_score']:.2f}, bm25={r['bm25_score']:.2f}")

    print("\nStatistics:")
    for k, v in hybrid.get_statistics().items():
        print(f"  {k}: {v}")

    print("\n" + "=" * 60)
    print("Test complete.")
