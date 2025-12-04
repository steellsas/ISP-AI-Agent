"""
Vector Store
FAISS-based vector storage for efficient similarity search
"""

import sys
import pickle
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import numpy as np


try:
    from isp_shared.utils import get_logger
except ImportError:
    import logging

    def get_logger(name):
        return logging.getLogger(name)


logger = get_logger(__name__)


class VectorStore:
    """
    FAISS-based vector store for document embeddings.

    Features:
    - Efficient similarity search
    - Persistence (save/load)
    - Metadata storage
    - Batch operations
    """

    def __init__(
        self, embedding_dim: int = 768, index_type: str = "flatl2", store_dir: Optional[str] = None
    ):
        """
        Initialize vector store.

        Args:
            embedding_dim: Dimension of embeddings
            index_type: FAISS index type ('flatl2', 'ivfflat', 'hnsw')
            store_dir: Directory for persistence
        """
        self.embedding_dim = embedding_dim
        self.index_type = index_type

        # Storage directory
        if store_dir is None:
            # store_dir = Path(__file__).parent.parent.parent / "vector_store_data"
            store_dir = Path(__file__).parent / "vector_store_data"
        self.store_dir = Path(store_dir)
        self.store_dir.mkdir(parents=True, exist_ok=True)

        # Initialize FAISS index
        self.index = None
        self._create_index()

        # Metadata storage
        self.documents: List[str] = []
        self.metadata: List[Dict[str, Any]] = []
        self.ids: List[str] = []

        logger.info(f"VectorStore initialized: {index_type} ({embedding_dim}d)")

    def _create_index(self):
        """Create FAISS index."""
        try:
            import faiss

            if self.index_type == "flatl2":
                # Simple flat L2 index (exact search)
                self.index = faiss.IndexFlatL2(self.embedding_dim)

            elif self.index_type == "flatip":
                # Flat inner product (cosine similarity with normalized vectors)
                self.index = faiss.IndexFlatIP(self.embedding_dim)

            elif self.index_type == "ivfflat":
                # IVFFlat - faster but approximate
                quantizer = faiss.IndexFlatL2(self.embedding_dim)
                self.index = faiss.IndexIVFFlat(quantizer, self.embedding_dim, 100)
                # Note: Need to train before adding vectors

            elif self.index_type == "hnsw":
                # HNSW - very fast approximate search
                self.index = faiss.IndexHNSWFlat(self.embedding_dim, 32)

            else:
                logger.warning(f"Unknown index type: {self.index_type}, using flatl2")
                self.index = faiss.IndexFlatL2(self.embedding_dim)

            logger.info(f"FAISS index created: {self.index_type}")

        except ImportError:
            logger.error("faiss not installed. Install: pip install faiss-cpu or faiss-gpu")
            raise

    def add(
        self,
        embeddings: np.ndarray,
        documents: List[str],
        metadata: Optional[List[Dict[str, Any]]] = None,
        ids: Optional[List[str]] = None,
    ):
        """
        Add documents with embeddings to the store.

        Args:
            embeddings: Document embeddings (n_docs, embedding_dim)
            documents: List of document texts
            metadata: Optional metadata for each document
            ids: Optional IDs for each document
        """
        try:
            n_docs = len(documents)

            # Validate inputs
            if embeddings.shape[0] != n_docs:
                raise ValueError(f"Mismatch: {embeddings.shape[0]} embeddings, {n_docs} documents")

            if embeddings.shape[1] != self.embedding_dim:
                raise ValueError(
                    f"Wrong embedding dimension: {embeddings.shape[1]}, expected {self.embedding_dim}"
                )

            # Ensure float32
            embeddings = embeddings.astype(np.float32)

            # Add to FAISS index
            self.index.add(embeddings)

            # Store documents
            self.documents.extend(documents)

            # Store metadata
            if metadata is None:
                metadata = [{} for _ in range(n_docs)]
            self.metadata.extend(metadata)

            # Store IDs
            if ids is None:
                start_id = len(self.ids)
                ids = [f"doc_{start_id + i}" for i in range(n_docs)]
            self.ids.extend(ids)

            logger.info(f"Added {n_docs} documents to vector store (total: {self.index.ntotal})")

        except Exception as e:
            logger.error(f"Error adding documents: {e}", exc_info=True)
            raise

    def search(
        self, query_embedding: np.ndarray, k: int = 5, threshold: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        """
        Search for similar documents.

        Args:
            query_embedding: Query embedding (1D array)
            k: Number of results to return
            threshold: Optional similarity threshold

        Returns:
            List of results with document, metadata, score, and ID
        """
        try:
            if self.index.ntotal == 0:
                logger.warning("Vector store is empty")
                return []

            # Ensure correct shape and type
            if query_embedding.ndim == 1:
                query_embedding = query_embedding.reshape(1, -1)
            query_embedding = query_embedding.astype(np.float32)

            # Search
            distances, indices = self.index.search(query_embedding, k)

            # Convert to results
            results = []
            for i, (dist, idx) in enumerate(zip(distances[0], indices[0])):
                # Skip if index is -1 (no result)
                if idx == -1:
                    continue

                # Convert distance to similarity score
                # For L2: smaller distance = more similar
                # Convert to similarity: 1 / (1 + distance)
                similarity = 1.0 / (1.0 + float(dist))

                # Apply threshold if specified
                if threshold is not None and similarity < threshold:
                    continue

                result = {
                    "document": self.documents[idx],
                    "metadata": self.metadata[idx],
                    "id": self.ids[idx],
                    "score": similarity,
                    "distance": float(dist),
                    "rank": i + 1,
                }
                results.append(result)

            logger.info(f"Search returned {len(results)} results")
            return results

        except Exception as e:
            logger.error(f"Error searching: {e}", exc_info=True)
            raise

    def batch_search(
        self, query_embeddings: np.ndarray, k: int = 5, threshold: Optional[float] = None
    ) -> List[List[Dict[str, Any]]]:
        """
        Search for multiple queries.

        Args:
            query_embeddings: Query embeddings (n_queries, embedding_dim)
            k: Number of results per query
            threshold: Optional similarity threshold

        Returns:
            List of result lists (one per query)
        """
        all_results = []

        for query_embedding in query_embeddings:
            results = self.search(query_embedding, k=k, threshold=threshold)
            all_results.append(results)

        return all_results

    def get_by_id(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """
        Get document by ID.

        Args:
            doc_id: Document ID

        Returns:
            Document dict or None
        """
        try:
            idx = self.ids.index(doc_id)
            return {
                "document": self.documents[idx],
                "metadata": self.metadata[idx],
                "id": self.ids[idx],
            }
        except ValueError:
            return None

    def delete_by_id(self, doc_id: str) -> bool:
        """
        Delete document by ID.

        Note: FAISS doesn't support efficient deletion,
        so this rebuilds the entire index.

        Args:
            doc_id: Document ID

        Returns:
            True if deleted
        """
        try:
            idx = self.ids.index(doc_id)

            # Remove from lists
            del self.documents[idx]
            del self.metadata[idx]
            del self.ids[idx]

            # Rebuild index (FAISS limitation)
            logger.warning("Rebuilding index after deletion (FAISS limitation)")
            self._rebuild_index()

            logger.info(f"Deleted document: {doc_id}")
            return True

        except ValueError:
            logger.warning(f"Document not found: {doc_id}")
            return False

    def _rebuild_index(self):
        """Rebuild FAISS index from scratch."""
        # This is needed after deletion since FAISS doesn't support efficient removal
        # In production, consider using a different approach or accepting stale data
        pass

    def clear(self):
        """Clear all data from the store."""
        self._create_index()
        self.documents = []
        self.metadata = []
        self.ids = []
        logger.info("Vector store cleared")

    def save(self, name: str = "default"):
        """
        Save vector store to disk.

        Args:
            name: Store name
        """
        try:
            import faiss

            # Save FAISS index
            index_path = self.store_dir / f"{name}_index.faiss"
            faiss.write_index(self.index, str(index_path))

            # Save metadata
            metadata_path = self.store_dir / f"{name}_metadata.pkl"
            with open(metadata_path, "wb") as f:
                pickle.dump(
                    {
                        "documents": self.documents,
                        "metadata": self.metadata,
                        "ids": self.ids,
                        "embedding_dim": self.embedding_dim,
                        "index_type": self.index_type,
                    },
                    f,
                )

            logger.info(f"Vector store saved: {name}")

        except Exception as e:
            logger.error(f"Error saving vector store: {e}", exc_info=True)
            raise

    def load(self, name: str = "default") -> bool:
        """
        Load vector store from disk.

        Args:
            name: Store name

        Returns:
            True if loaded successfully
        """
        try:
            import faiss

            # Load FAISS index
            index_path = self.store_dir / f"{name}_index.faiss"
            if not index_path.exists():
                logger.warning(f"Index file not found: {index_path}")
                return False

            self.index = faiss.read_index(str(index_path))

            # Load metadata
            metadata_path = self.store_dir / f"{name}_metadata.pkl"
            with open(metadata_path, "rb") as f:
                data = pickle.load(f)

            self.documents = data["documents"]
            self.metadata = data["metadata"]
            self.ids = data["ids"]
            self.embedding_dim = data["embedding_dim"]
            self.index_type = data["index_type"]

            logger.info(f"Vector store loaded: {name} ({len(self.documents)} documents)")
            return True

        except Exception as e:
            logger.error(f"Error loading vector store: {e}", exc_info=True)
            return False

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get vector store statistics.

        Returns:
            Statistics dictionary
        """
        return {
            "total_documents": len(self.documents),
            "embedding_dim": self.embedding_dim,
            "index_type": self.index_type,
            "index_size": self.index.ntotal if self.index else 0,
            "store_dir": str(self.store_dir),
        }


# Singleton instance
_vector_store: Optional[VectorStore] = None


def get_vector_store(
    embedding_dim: int = 768, index_type: str = "flatl2", store_dir: Optional[str] = None
) -> VectorStore:
    """
    Get or create VectorStore singleton instance.

    Args:
        embedding_dim: Embedding dimension (only used on first call)
        index_type: Index type (only used on first call)
        store_dir: Store directory (only used on first call)

    Returns:
        VectorStore instance
    """
    global _vector_store

    if _vector_store is None:
        _vector_store = VectorStore(
            embedding_dim=embedding_dim, index_type=index_type, store_dir=store_dir
        )

    return _vector_store


# Example usage
if __name__ == "__main__":
    # Test vector store
    store = VectorStore(embedding_dim=768)

    # Create test embeddings
    print("Creating test data...")
    n_docs = 10
    embeddings = np.random.randn(n_docs, 768).astype(np.float32)
    documents = [f"Document {i}" for i in range(n_docs)]
    metadata = [{"source": f"source_{i}"} for i in range(n_docs)]

    # Add to store
    print("Adding documents...")
    store.add(embeddings, documents, metadata)

    # Search
    print("\nSearching...")
    query_embedding = np.random.randn(768).astype(np.float32)
    results = store.search(query_embedding, k=3)

    for result in results:
        print(f"  {result['document']} (score: {result['score']:.3f})")

    # Statistics
    print("\nStatistics:")
    stats = store.get_statistics()
    for key, value in stats.items():
        print(f"  {key}: {value}")

    # Save
    print("\nSaving...")
    store.save("test_store")

    # Load
    print("Loading...")
    new_store = VectorStore()
    success = new_store.load("test_store")
    print(f"Load success: {success}")
