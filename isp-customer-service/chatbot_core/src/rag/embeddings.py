"""
Embedding Manager
Generates embeddings using sentence-transformers for multilingual support
"""

import sys
from pathlib import Path
from typing import List, Union, Optional
import numpy as np

# # Add shared to path
# shared_path = Path(__file__).parent.parent.parent.parent / "shared" / "src"
# if str(shared_path) not in sys.path:
#     sys.path.insert(0, str(shared_path))

# from utils import get_logger

# logger = get_logger(__name__)


try:
    from isp_shared.utils import get_logger
except ImportError:
    # Fallback for development
    import logging
    def get_logger(name):
        return logging.getLogger(name)

logger = get_logger(__name__)



class EmbeddingManager:
    """
    Manages text embeddings using sentence-transformers.
    
    Features:
    - Multilingual support (Lithuanian + English)
    - Batch processing
    - Caching
    - Efficient memory usage
    """
    
    def __init__(
        self,
        model_name: str = "sentence-transformers/paraphrase-multilingual-mpnet-base-v2",
        device: str = "cpu",
        cache_dir: Optional[str] = None
    ):
        """
        Initialize embedding manager.
        
        Args:
            model_name: HuggingFace model name
            device: Device to use ('cpu' or 'cuda')
            cache_dir: Directory to cache model files
        """
        self.model_name = model_name
        self.device = device
        self.cache_dir = cache_dir
        
        # Initialize model
        self.model = None
        self._load_model()
        
        # Embedding dimension
        self.embedding_dim = self._get_embedding_dim()
        
        logger.info(f"EmbeddingManager initialized: {model_name} ({self.embedding_dim}d)")
    
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
        try:
            # Ensure texts is a list
            if isinstance(texts, str):
                texts = [texts]
            
            logger.info(f"Encoding {len(texts)} texts")
            
            # Encode
            embeddings = self.model.encode(
                texts,
                batch_size=batch_size,
                show_progress_bar=show_progress,
                convert_to_numpy=True,
                normalize_embeddings=normalize
            )
            
            logger.info(f"Encoded {len(texts)} texts -> shape {embeddings.shape}")
            
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
    
    def encode_query(self, query: str, normalize: bool = True) -> np.ndarray:
        """
        Encode a query (alias for encode_single).
        
        Args:
            query: Query text
            normalize: Normalize embedding
            
        Returns:
            1D numpy array of embedding
        """
        return self.encode_single(query, normalize=normalize)
    
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
        # Cosine similarity
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
        """
        Get model information.
        
        Returns:
            Dictionary with model info
        """
        return {
            "model_name": self.model_name,
            "embedding_dim": self.embedding_dim,
            "device": self.device,
            "max_seq_length": self.model.max_seq_length if self.model else None
        }


# Singleton instance
_embedding_manager: Optional[EmbeddingManager] = None


def get_embedding_manager(
    model_name: str = "sentence-transformers/paraphrase-multilingual-mpnet-base-v2",
    device: str = "cpu",
    cache_dir: Optional[str] = None
) -> EmbeddingManager:
    """
    Get or create EmbeddingManager singleton instance.
    
    Args:
        model_name: Model name (only used on first call)
        device: Device (only used on first call)
        cache_dir: Cache directory (only used on first call)
        
    Returns:
        EmbeddingManager instance
    """
    global _embedding_manager
    
    if _embedding_manager is None:
        _embedding_manager = EmbeddingManager(
            model_name=model_name,
            device=device,
            cache_dir=cache_dir
        )
    
    return _embedding_manager


# Example usage
if __name__ == "__main__":
    # Test embedding manager
    manager = EmbeddingManager()
    
    # Test single text
    print("Testing single text encoding...")
    text = "Internetas neveikia"
    embedding = manager.encode_single(text)
    print(f"Text: {text}")
    print(f"Embedding shape: {embedding.shape}")
    print(f"Embedding (first 5): {embedding[:5]}")
    
    # Test multiple texts
    print("\nTesting batch encoding...")
    texts = [
        "Internetas neveikia",
        "Lėtas internetas",
        "TV neveikia",
        "Internet not working"
    ]
    embeddings = manager.encode(texts)
    print(f"Encoded {len(texts)} texts")
    print(f"Embeddings shape: {embeddings.shape}")
    
    # Test similarity
    print("\nTesting similarity...")
    text1 = "Internetas neveikia"
    text2 = "Internet not working"
    text3 = "TV neveikia"
    
    emb1 = manager.encode_single(text1)
    emb2 = manager.encode_single(text2)
    emb3 = manager.encode_single(text3)
    
    sim_12 = manager.similarity(emb1, emb2)
    sim_13 = manager.similarity(emb1, emb3)
    
    print(f"Similarity '{text1}' <-> '{text2}': {sim_12:.3f}")
    print(f"Similarity '{text1}' <-> '{text3}': {sim_13:.3f}")
    
    # Model info
    print("\nModel info:")
    info = manager.get_model_info()
    for key, value in info.items():
        print(f"  {key}: {value}")
