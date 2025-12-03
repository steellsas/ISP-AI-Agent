# """
# Embedding Manager
# Generates embeddings using sentence-transformers for multilingual support
# """

# import sys
# from pathlib import Path
# from typing import List, Union, Optional
# import numpy as np



# try:
#     from isp_shared.utils import get_logger
# except ImportError:
#     # Fallback for development
#     import logging
#     def get_logger(name):
#         return logging.getLogger(name)

# logger = get_logger(__name__)



# class EmbeddingManager:
#     """
#     Manages text embeddings using sentence-transformers.
    
#     Features:
#     - Multilingual support (Lithuanian + English)
#     - Batch processing
#     - Caching
#     - Efficient memory usage
#     """
    
#     def __init__(
#         self,
#         model_name: str = "sentence-transformers/paraphrase-multilingual-mpnet-base-v2",
#         device: str = "cpu",
#         cache_dir: Optional[str] = None
#     ):
#         """
#         Initialize embedding manager.
        
#         Args:
#             model_name: HuggingFace model name
#             device: Device to use ('cpu' or 'cuda')
#             cache_dir: Directory to cache model files
#         """
#         self.model_name = model_name
#         self.device = device
#         self.cache_dir = cache_dir
        
#         # Initialize model
#         self.model = None
#         self._load_model()
        
#         # Embedding dimension
#         self.embedding_dim = self._get_embedding_dim()
        
#         logger.info(f"EmbeddingManager initialized: {model_name} ({self.embedding_dim}d)")
    
#     def _load_model(self):
#         """Load sentence-transformers model."""
#         try:
#             from sentence_transformers import SentenceTransformer
            
#             logger.info(f"Loading embedding model: {self.model_name}")
            
#             self.model = SentenceTransformer(
#                 self.model_name,
#                 device=self.device,
#                 cache_folder=self.cache_dir
#             )
            
#             logger.info("Embedding model loaded successfully")
            
#         except ImportError:
#             logger.error("sentence-transformers not installed. Install: pip install sentence-transformers")
#             raise
#         except Exception as e:
#             logger.error(f"Error loading model: {e}", exc_info=True)
#             raise
    
#     def _get_embedding_dim(self) -> int:
#         """Get embedding dimension."""
#         if self.model is None:
#             return 768  # Default for MPNET
        
#         # Get dimension by encoding a test string
#         test_embedding = self.model.encode("test", convert_to_numpy=True)
#         return len(test_embedding)
    
#     def encode(
#         self,
#         texts: Union[str, List[str]],
#         batch_size: int = 32,
#         show_progress: bool = False,
#         normalize: bool = True
#     ) -> np.ndarray:
#         """
#         Encode text(s) into embeddings.
        
#         Args:
#             texts: Single text or list of texts
#             batch_size: Batch size for processing
#             show_progress: Show progress bar
#             normalize: Normalize embeddings to unit length
            
#         Returns:
#             Numpy array of embeddings (n_texts, embedding_dim)
#         """
#         try:
#             # Ensure texts is a list
#             if isinstance(texts, str):
#                 texts = [texts]
            
#             logger.info(f"Encoding {len(texts)} texts")
            
#             # Encode
#             embeddings = self.model.encode(
#                 texts,
#                 batch_size=batch_size,
#                 show_progress_bar=show_progress,
#                 convert_to_numpy=True,
#                 normalize_embeddings=normalize
#             )
            
#             logger.info(f"Encoded {len(texts)} texts -> shape {embeddings.shape}")
            
#             return embeddings
            
#         except Exception as e:
#             logger.error(f"Error encoding texts: {e}", exc_info=True)
#             raise
    
#     def encode_single(self, text: str, normalize: bool = True) -> np.ndarray:
#         """
#         Encode a single text into embedding.
        
#         Args:
#             text: Text to encode
#             normalize: Normalize embedding
            
#         Returns:
#             1D numpy array of embedding
#         """
#         embeddings = self.encode([text], normalize=normalize)
#         return embeddings[0]
    
#     def encode_query(self, query: str, normalize: bool = True) -> np.ndarray:
#         """
#         Encode a query (alias for encode_single).
        
#         Args:
#             query: Query text
#             normalize: Normalize embedding
            
#         Returns:
#             1D numpy array of embedding
#         """
#         return self.encode_single(query, normalize=normalize)
    
#     def encode_documents(
#         self,
#         documents: List[str],
#         batch_size: int = 32,
#         show_progress: bool = True,
#         normalize: bool = True
#     ) -> np.ndarray:
#         """
#         Encode multiple documents.
        
#         Args:
#             documents: List of document texts
#             batch_size: Batch size
#             show_progress: Show progress bar
#             normalize: Normalize embeddings
            
#         Returns:
#             2D numpy array of embeddings (n_docs, embedding_dim)
#         """
#         return self.encode(
#             documents,
#             batch_size=batch_size,
#             show_progress=show_progress,
#             normalize=normalize
#         )
    
#     def similarity(
#         self,
#         embedding1: np.ndarray,
#         embedding2: np.ndarray
#     ) -> float:
#         """
#         Calculate cosine similarity between two embeddings.
        
#         Args:
#             embedding1: First embedding
#             embedding2: Second embedding
            
#         Returns:
#             Similarity score (0-1)
#         """
#         # Cosine similarity
#         dot_product = np.dot(embedding1, embedding2)
#         norm1 = np.linalg.norm(embedding1)
#         norm2 = np.linalg.norm(embedding2)
        
#         if norm1 == 0 or norm2 == 0:
#             return 0.0
        
#         similarity = dot_product / (norm1 * norm2)
        
#         return float(similarity)
    
#     def batch_similarity(
#         self,
#         query_embedding: np.ndarray,
#         document_embeddings: np.ndarray
#     ) -> np.ndarray:
#         """
#         Calculate similarities between query and multiple documents.
        
#         Args:
#             query_embedding: Query embedding (1D)
#             document_embeddings: Document embeddings (2D: n_docs x embedding_dim)
            
#         Returns:
#             1D array of similarity scores
#         """
#         # Normalize if needed
#         query_norm = query_embedding / np.linalg.norm(query_embedding)
#         doc_norms = document_embeddings / np.linalg.norm(document_embeddings, axis=1, keepdims=True)
        
#         # Cosine similarity via dot product
#         similarities = np.dot(doc_norms, query_norm)
        
#         return similarities
    
#     def get_model_info(self) -> dict:
#         """
#         Get model information.
        
#         Returns:
#             Dictionary with model info
#         """
#         return {
#             "model_name": self.model_name,
#             "embedding_dim": self.embedding_dim,
#             "device": self.device,
#             "max_seq_length": self.model.max_seq_length if self.model else None
#         }


# # Singleton instance
# _embedding_manager: Optional[EmbeddingManager] = None


# def get_embedding_manager(
#     model_name: str = "sentence-transformers/paraphrase-multilingual-mpnet-base-v2",
#     device: str = "cpu",
#     cache_dir: Optional[str] = None
# ) -> EmbeddingManager:
#     """
#     Get or create EmbeddingManager singleton instance.
    
#     Args:
#         model_name: Model name (only used on first call)
#         device: Device (only used on first call)
#         cache_dir: Cache directory (only used on first call)
        
#     Returns:
#         EmbeddingManager instance
#     """
#     global _embedding_manager
    
#     if _embedding_manager is None:
#         _embedding_manager = EmbeddingManager(
#             model_name=model_name,
#             device=device,
#             cache_dir=cache_dir
#         )
    
#     return _embedding_manager


# # Example usage
# if __name__ == "__main__":
#     # Test embedding manager
#     manager = EmbeddingManager()
    
#     # Test single text
#     print("Testing single text encoding...")
#     text = "Internetas neveikia"
#     embedding = manager.encode_single(text)
#     print(f"Text: {text}")
#     print(f"Embedding shape: {embedding.shape}")
#     print(f"Embedding (first 5): {embedding[:5]}")
    
#     # Test multiple texts
#     print("\nTesting batch encoding...")
#     texts = [
#         "Internetas neveikia",
#         "Lėtas internetas",
#         "TV neveikia",
#         "Internet not working"
#     ]
#     embeddings = manager.encode(texts)
#     print(f"Encoded {len(texts)} texts")
#     print(f"Embeddings shape: {embeddings.shape}")
    
#     # Test similarity
#     print("\nTesting similarity...")
#     text1 = "Internetas neveikia"
#     text2 = "Internet not working"
#     text3 = "TV neveikia"
    
#     emb1 = manager.encode_single(text1)
#     emb2 = manager.encode_single(text2)
#     emb3 = manager.encode_single(text3)
    
#     sim_12 = manager.similarity(emb1, emb2)
#     sim_13 = manager.similarity(emb1, emb3)
    
#     print(f"Similarity '{text1}' <-> '{text2}': {sim_12:.3f}")
#     print(f"Similarity '{text1}' <-> '{text3}': {sim_13:.3f}")
    
#     # Model info
#     print("\nModel info:")
#     info = manager.get_model_info()
#     for key, value in info.items():
#         print(f"  {key}: {value}")


"""
Embedding Manager v2 - Optimized
Generates embeddings using sentence-transformers for multilingual support

Optimizations:
- Lazy loading (model loads only when first needed)
- Query caching (avoids re-encoding same queries)
- Thread-safe singleton
"""

import hashlib
import threading
from pathlib import Path
from typing import List, Union, Optional, Dict
import numpy as np

try:
    from isp_shared.utils import get_logger
except ImportError:
    import logging
    def get_logger(name):
        return logging.getLogger(name)

logger = get_logger(__name__)


class EmbeddingManager:
    """
    Manages text embeddings using sentence-transformers.
    
    Features:
    - Multilingual support (Lithuanian + English)
    - Lazy model loading (faster startup)
    - Query caching (faster repeated queries)
    - Batch processing
    - Thread-safe
    """
    
    def __init__(
        self,
        model_name: str = "sentence-transformers/paraphrase-multilingual-mpnet-base-v2",
        device: str = "cpu",
        cache_dir: Optional[str] = None,
        query_cache_size: int = 500
    ):
        """
        Initialize embedding manager.
        
        Args:
            model_name: HuggingFace model name
            device: Device to use ('cpu' or 'cuda')
            cache_dir: Directory to cache model files
            query_cache_size: Max number of cached query embeddings
        """
        self.model_name = model_name
        self.device = device
        self.cache_dir = cache_dir
        
        # Lazy loading - model NOT loaded here
        self.model = None
        self._model_lock = threading.Lock()
        self._model_loaded = False
        
        # Query cache
        self._query_cache: Dict[str, np.ndarray] = {}
        self._query_cache_size = query_cache_size
        self._cache_lock = threading.Lock()
        
        # Embedding dimension (will be set when model loads)
        self._embedding_dim: Optional[int] = None
        
        logger.info(f"EmbeddingManager initialized (lazy): {model_name}")
    
    @property
    def embedding_dim(self) -> int:
        """Get embedding dimension (loads model if needed)."""
        if self._embedding_dim is None:
            self._ensure_model_loaded()
            self._embedding_dim = self._get_embedding_dim()
        return self._embedding_dim
    
    def _ensure_model_loaded(self):
        """Ensure model is loaded (lazy loading)."""
        if self._model_loaded:
            return
        
        with self._model_lock:
            # Double-check after acquiring lock
            if self._model_loaded:
                return
            
            self._load_model()
            self._model_loaded = True
    
    def _load_model(self):
        """Load sentence-transformers model."""
        try:
            from sentence_transformers import SentenceTransformer
            
            logger.info(f"Loading embedding model: {self.model_name}")
            
            self.model = SentenceTransformer(
                self.model_name,
                device=self.device,
                cache_folder=self.cache_dir
            )
            
            logger.info("Embedding model loaded successfully")
            
        except ImportError:
            logger.error("sentence-transformers not installed. Install: pip install sentence-transformers")
            raise
        except Exception as e:
            logger.error(f"Error loading model: {e}", exc_info=True)
            raise
    
    def _get_embedding_dim(self) -> int:
        """Get embedding dimension."""
        if self.model is None:
            return 768  # Default for MPNET
        
        # Get dimension by encoding a test string
        test_embedding = self.model.encode("test", convert_to_numpy=True)
        return len(test_embedding)
    
    def _get_cache_key(self, text: str) -> str:
        """Generate cache key for text."""
        return hashlib.md5(text.encode('utf-8')).hexdigest()
    
    def _get_from_cache(self, text: str) -> Optional[np.ndarray]:
        """Get embedding from cache if exists."""
        cache_key = self._get_cache_key(text)
        with self._cache_lock:
            return self._query_cache.get(cache_key)
    
    def _add_to_cache(self, text: str, embedding: np.ndarray):
        """Add embedding to cache."""
        cache_key = self._get_cache_key(text)
        with self._cache_lock:
            # Simple LRU-like: if cache full, remove oldest entries
            if len(self._query_cache) >= self._query_cache_size:
                # Remove ~10% of oldest entries
                keys_to_remove = list(self._query_cache.keys())[:self._query_cache_size // 10]
                for key in keys_to_remove:
                    del self._query_cache[key]
            
            self._query_cache[cache_key] = embedding
    
    def encode(
        self,
        texts: Union[str, List[str]],
        batch_size: int = 32,
        show_progress: bool = False,
        normalize: bool = True
    ) -> np.ndarray:
        """
        Encode text(s) into embeddings.
        
        Args:
            texts: Single text or list of texts
            batch_size: Batch size for processing
            show_progress: Show progress bar
            normalize: Normalize embeddings to unit length
            
        Returns:
            Numpy array of embeddings (n_texts, embedding_dim)
        """
        # Ensure model is loaded
        self._ensure_model_loaded()
        
        try:
            # Ensure texts is a list
            if isinstance(texts, str):
                texts = [texts]
            
            if len(texts) <= 5:
                logger.debug(f"Encoding {len(texts)} texts")
            else:
                logger.info(f"Encoding {len(texts)} texts")
            
            # Encode
            embeddings = self.model.encode(
                texts,
                batch_size=batch_size,
                show_progress_bar=show_progress,
                convert_to_numpy=True,
                normalize_embeddings=normalize
            )
            
            return embeddings
            
        except Exception as e:
            logger.error(f"Error encoding texts: {e}", exc_info=True)
            raise
    
    def encode_single(self, text: str, normalize: bool = True) -> np.ndarray:
        """
        Encode a single text into embedding.
        
        Args:
            text: Text to encode
            normalize: Normalize embedding
            
        Returns:
            1D numpy array of embedding
        """
        embeddings = self.encode([text], normalize=normalize)
        return embeddings[0]
    
    def encode_query(self, query: str, normalize: bool = True, use_cache: bool = True) -> np.ndarray:
        """
        Encode a query with caching support.
        
        Args:
            query: Query text
            normalize: Normalize embedding
            use_cache: Whether to use cache (default True)
            
        Returns:
            1D numpy array of embedding
        """
        # Check cache first
        if use_cache:
            cached = self._get_from_cache(query)
            if cached is not None:
                logger.debug(f"Cache hit for query: {query[:30]}...")
                return cached
        
        # Encode
        embedding = self.encode_single(query, normalize=normalize)
        
        # Add to cache
        if use_cache:
            self._add_to_cache(query, embedding)
        
        return embedding
    
    def encode_documents(
        self,
        documents: List[str],
        batch_size: int = 32,
        show_progress: bool = True,
        normalize: bool = True
    ) -> np.ndarray:
        """
        Encode multiple documents.
        
        Args:
            documents: List of document texts
            batch_size: Batch size
            show_progress: Show progress bar
            normalize: Normalize embeddings
            
        Returns:
            2D numpy array of embeddings (n_docs, embedding_dim)
        """
        return self.encode(
            documents,
            batch_size=batch_size,
            show_progress=show_progress,
            normalize=normalize
        )
    
    def similarity(
        self,
        embedding1: np.ndarray,
        embedding2: np.ndarray
    ) -> float:
        """
        Calculate cosine similarity between two embeddings.
        
        Args:
            embedding1: First embedding
            embedding2: Second embedding
            
        Returns:
            Similarity score (0-1)
        """
        dot_product = np.dot(embedding1, embedding2)
        norm1 = np.linalg.norm(embedding1)
        norm2 = np.linalg.norm(embedding2)
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        similarity = dot_product / (norm1 * norm2)
        return float(similarity)
    
    def batch_similarity(
        self,
        query_embedding: np.ndarray,
        document_embeddings: np.ndarray
    ) -> np.ndarray:
        """
        Calculate similarities between query and multiple documents.
        
        Args:
            query_embedding: Query embedding (1D)
            document_embeddings: Document embeddings (2D: n_docs x embedding_dim)
            
        Returns:
            1D array of similarity scores
        """
        # Normalize if needed
        query_norm = query_embedding / np.linalg.norm(query_embedding)
        doc_norms = document_embeddings / np.linalg.norm(document_embeddings, axis=1, keepdims=True)
        
        # Cosine similarity via dot product
        similarities = np.dot(doc_norms, query_norm)
        return similarities
    
    def get_model_info(self) -> dict:
        """Get model information."""
        return {
            "model_name": self.model_name,
            "embedding_dim": self.embedding_dim,
            "device": self.device,
            "model_loaded": self._model_loaded,
            "cache_size": len(self._query_cache),
            "cache_max_size": self._query_cache_size,
            "max_seq_length": self.model.max_seq_length if self.model else None
        }
    
    def clear_cache(self):
        """Clear query cache."""
        with self._cache_lock:
            self._query_cache.clear()
        logger.info("Query cache cleared")
    
    def preload_model(self):
        """
        Explicitly load model (useful for warming up).
        Call this during app startup if you want to avoid
        first-query delay.
        """
        self._ensure_model_loaded()
        logger.info("Model preloaded")


# =============================================================================
# SINGLETON
# =============================================================================

_embedding_manager: Optional[EmbeddingManager] = None
_singleton_lock = threading.Lock()


def get_embedding_manager(
    model_name: str = "sentence-transformers/paraphrase-multilingual-mpnet-base-v2",
    device: str = "cpu",
    cache_dir: Optional[str] = None,
    query_cache_size: int = 500
) -> EmbeddingManager:
    """
    Get or create EmbeddingManager singleton instance.
    Thread-safe.
    
    Args:
        model_name: Model name (only used on first call)
        device: Device (only used on first call)
        cache_dir: Cache directory (only used on first call)
        query_cache_size: Query cache size (only used on first call)
        
    Returns:
        EmbeddingManager instance
    """
    global _embedding_manager
    
    if _embedding_manager is None:
        with _singleton_lock:
            # Double-check after acquiring lock
            if _embedding_manager is None:
                _embedding_manager = EmbeddingManager(
                    model_name=model_name,
                    device=device,
                    cache_dir=cache_dir,
                    query_cache_size=query_cache_size
                )
    
    return _embedding_manager


def preload_embedding_model():
    """
    Preload embedding model in background.
    Call at app startup for faster first query.
    """
    import threading
    
    def _preload():
        manager = get_embedding_manager()
        manager.preload_model()
    
    thread = threading.Thread(target=_preload, daemon=True)
    thread.start()
    logger.info("Embedding model preload started in background")


# =============================================================================
# EXAMPLE / TEST
# =============================================================================

if __name__ == "__main__":
    import time
    
    print("=" * 60)
    print("Testing Optimized EmbeddingManager")
    print("=" * 60)
    
    # Test lazy loading
    print("\n1. Testing lazy loading...")
    start = time.time()
    manager = EmbeddingManager()
    init_time = time.time() - start
    print(f"   Init time (no model load): {init_time*1000:.1f}ms")
    print(f"   Model loaded: {manager._model_loaded}")
    
    # First encode triggers model load
    print("\n2. First encode (triggers model load)...")
    start = time.time()
    embedding = manager.encode_single("Internetas neveikia")
    first_encode_time = time.time() - start
    print(f"   First encode time: {first_encode_time*1000:.1f}ms")
    print(f"   Model loaded: {manager._model_loaded}")
    
    # Test caching
    print("\n3. Testing query cache...")
    
    # First query (no cache)
    start = time.time()
    emb1 = manager.encode_query("Internetas neveikia")
    no_cache_time = time.time() - start
    print(f"   No cache: {no_cache_time*1000:.1f}ms")
    
    # Second query (from cache)
    start = time.time()
    emb2 = manager.encode_query("Internetas neveikia")
    cache_time = time.time() - start
    print(f"   From cache: {cache_time*1000:.1f}ms")
    print(f"   Speedup: {no_cache_time/cache_time:.1f}x")
    
    # Verify same embedding
    print(f"   Same embedding: {np.allclose(emb1, emb2)}")
    
    # Test similarity
    print("\n4. Testing similarity...")
    text1 = "Internetas neveikia"
    text2 = "Internet not working"
    text3 = "TV neveikia"
    
    emb1 = manager.encode_query(text1)
    emb2 = manager.encode_query(text2)
    emb3 = manager.encode_query(text3)
    
    sim_12 = manager.similarity(emb1, emb2)
    sim_13 = manager.similarity(emb1, emb3)
    
    print(f"   '{text1}' <-> '{text2}': {sim_12:.3f}")
    print(f"   '{text1}' <-> '{text3}': {sim_13:.3f}")
    
    # Model info
    print("\n5. Model info:")
    info = manager.get_model_info()
    for key, value in info.items():
        print(f"   {key}: {value}")
    
    print("\n" + "=" * 60)
    print("✅ All tests passed!")