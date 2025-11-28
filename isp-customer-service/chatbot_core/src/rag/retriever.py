"""
Retriever
Combines embedding manager and vector store for document retrieval
"""

from pathlib import Path
from typing import List, Dict, Any, Optional

# Import utilities from shared package
try:
    from isp_shared.utils import get_logger
except ImportError:
    # Fallback if shared package not available
    import logging
    logging.basicConfig(level=logging.INFO)
    def get_logger(name):
        return logging.getLogger(name)

# Import RAG components
from .embeddings import EmbeddingManager, get_embedding_manager
from .vector_store import VectorStore, get_vector_store

logger = get_logger(__name__)


class Retriever:
    """
    Document retriever combining embeddings and vector store.
    
    Features:
    - Query encoding
    - Similarity search
    - Result ranking
    - Context formatting
    """
    
    def __init__(
        self,
        embedding_manager: Optional[EmbeddingManager] = None,
        vector_store: Optional[VectorStore] = None,
        top_k: int = 3,
        similarity_threshold: float = 0.7
    ):
        """
        Initialize retriever.
        
        Args:
            embedding_manager: Embedding manager instance
            vector_store: Vector store instance
            top_k: Number of documents to retrieve
            similarity_threshold: Minimum similarity score
        """
        self.embedding_manager = embedding_manager or get_embedding_manager()
        self.vector_store = vector_store or get_vector_store(
            embedding_dim=self.embedding_manager.embedding_dim
        )
        
        self.top_k = top_k
        self.similarity_threshold = similarity_threshold
        
        logger.info(f"Retriever initialized (top_k={top_k}, threshold={similarity_threshold})")
    
    def retrieve(
        self,
        query: str,
        top_k: Optional[int] = None,
        threshold: Optional[float] = None,
        filter_metadata: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieve relevant documents for a query.
        
        Args:
            query: Query text
            top_k: Override default top_k
            threshold: Override default threshold
            filter_metadata: Filter results by metadata
            
        Returns:
            List of relevant documents with scores
        """
        try:
            # Use defaults if not specified
            k = top_k if top_k is not None else self.top_k
            thresh = threshold if threshold is not None else self.similarity_threshold
            
            logger.info(f"Retrieving documents for query: '{query}' (k={k}, threshold={thresh})")
            
            # Encode query
            query_embedding = self.embedding_manager.encode_query(query)
            
            # Search vector store
            results = self.vector_store.search(
                query_embedding,
                k=k * 2,  # Get more results for filtering
                threshold=thresh
            )
            
            # Apply metadata filter if specified
            if filter_metadata:
                results = self._filter_by_metadata(results, filter_metadata)
            
            # Limit to top_k
            results = results[:k]
            
            logger.info(f"Retrieved {len(results)} documents")
            
            return results
            
        except Exception as e:
            logger.error(f"Error retrieving documents: {e}", exc_info=True)
            return []
    
    def retrieve_with_context(
        self,
        query: str,
        top_k: Optional[int] = None,
        threshold: Optional[float] = None,
        include_scores: bool = True
    ) -> str:
        """
        Retrieve documents and format as context string.
        
        Args:
            query: Query text
            top_k: Number of documents
            threshold: Similarity threshold
            include_scores: Include similarity scores in context
            
        Returns:
            Formatted context string
        """
        results = self.retrieve(query, top_k=top_k, threshold=threshold)
        
        if not results:
            return "No relevant information found."
        
        context_parts = []
        
        for i, result in enumerate(results, 1):
            doc_text = result["document"]
            score = result["score"]
            
            if include_scores:
                context_parts.append(
                    f"[Document {i}] (Relevance: {score:.2f})\n{doc_text}"
                )
            else:
                context_parts.append(
                    f"[Document {i}]\n{doc_text}"
                )
        
        context = "\n\n---\n\n".join(context_parts)
        
        return context
    
    def add_documents(
        self,
        documents: List[str],
        metadata: Optional[List[Dict[str, Any]]] = None,
        ids: Optional[List[str]] = None,
        batch_size: int = 32
    ):
        """
        Add documents to the retriever.
        
        Args:
            documents: List of document texts
            metadata: Optional metadata for each document
            ids: Optional IDs for each document
            batch_size: Batch size for encoding
        """
        try:
            logger.info(f"Adding {len(documents)} documents to retriever")
            
            # Encode documents
            embeddings = self.embedding_manager.encode_documents(
                documents,
                batch_size=batch_size,
                show_progress=True
            )
            
            # Add to vector store
            self.vector_store.add(
                embeddings=embeddings,
                documents=documents,
                metadata=metadata,
                ids=ids
            )
            
            logger.info(f"Successfully added {len(documents)} documents")
            
        except Exception as e:
            logger.error(f"Error adding documents: {e}", exc_info=True)
            raise
    
    def load_documents_from_directory(
        self,
        directory: str | Path,
        file_extension: str = ".md",
        recursive: bool = True
    ):
        """
        Load documents from a directory.
        
        Args:
            directory: Directory path
            file_extension: File extension to load
            recursive: Search subdirectories
        """
        try:
            directory = Path(directory)
            
            if not directory.exists():
                logger.error(f"Directory not found: {directory}")
                return
            
            # Find files
            if recursive:
                files = list(directory.rglob(f"*{file_extension}"))
            else:
                files = list(directory.glob(f"*{file_extension}"))
            
            logger.info(f"Found {len(files)} {file_extension} files in {directory}")
            
            # Load documents
            documents = []
            metadata = []
            ids = []
            
            for file_path in files:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                documents.append(content)
                metadata.append({
                    "source": str(file_path),
                    "filename": file_path.name,
                    "category": file_path.parent.name
                })
                ids.append(str(file_path.relative_to(directory)))
            
            # Add to retriever
            self.add_documents(documents, metadata=metadata, ids=ids)
            
            logger.info(f"Loaded {len(documents)} documents from {directory}")
            
        except Exception as e:
            logger.error(f"Error loading documents: {e}", exc_info=True)
            raise
    
    def _filter_by_metadata(
        self,
        results: List[Dict[str, Any]],
        filter_metadata: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Filter results by metadata criteria."""
        filtered = []
        
        for result in results:
            result_metadata = result.get("metadata", {})
            
            # Check if all filter criteria match
            match = True
            for key, value in filter_metadata.items():
                if result_metadata.get(key) != value:
                    match = False
                    break
            
            if match:
                filtered.append(result)
        
        return filtered
    
    def save(self, name: str = "default"):
        """
        Save retriever state.
        
        Args:
            name: Save name
        """
        self.vector_store.save(name)
        logger.info(f"Retriever saved: {name}")
    
    def load(self, name: str = "default") -> bool:
        """
        Load retriever state.
        
        Args:
            name: Save name
            
        Returns:
            True if loaded successfully
        """
        success = self.vector_store.load(name)
        if success:
            logger.info(f"Retriever loaded: {name}")
        return success
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get retriever statistics.
        
        Returns:
            Statistics dictionary
        """
        embedding_info = self.embedding_manager.get_model_info()
        vector_stats = self.vector_store.get_statistics()
        
        return {
            "embedding_model": embedding_info["model_name"],
            "embedding_dim": embedding_info["embedding_dim"],
            "total_documents": vector_stats["total_documents"],
            "top_k": self.top_k,
            "similarity_threshold": self.similarity_threshold
        }


# Singleton instance
_retriever: Optional[Retriever] = None


def get_retriever(
    embedding_manager: Optional[EmbeddingManager] = None,
    vector_store: Optional[VectorStore] = None,
    top_k: int = 3,
    similarity_threshold: float = 0.7
) -> Retriever:
    """
    Get or create Retriever singleton instance.
    
    Args:
        embedding_manager: Embedding manager (only used on first call)
        vector_store: Vector store (only used on first call)
        top_k: Top K (only used on first call)
        similarity_threshold: Threshold (only used on first call)
        
    Returns:
        Retriever instance
    """
    global _retriever
    
    if _retriever is None:
        _retriever = Retriever(
            embedding_manager=embedding_manager,
            vector_store=vector_store,
            top_k=top_k,
            similarity_threshold=similarity_threshold
        )
    
    return _retriever


# Example usage
if __name__ == "__main__":
    # Test retriever
    retriever = Retriever()
    
    # Add test documents
    print("Adding test documents...")
    documents = [
        "Internetas neveikia - patikrinkite maršrutizatorių",
        "Lėtas internetas - uždarykite nereikalingas programas",
        "TV neveikia - perkraukite dekoderių",
        "WiFi signalas silpnas - priartinkite maršrutizatorių",
        "Gedimo pranešimas - skambinkite +370 000 0000"
    ]
    
    metadata = [
        {"category": "internet", "severity": "high"},
        {"category": "internet", "severity": "medium"},
        {"category": "tv", "severity": "high"},
        {"category": "internet", "severity": "low"},
        {"category": "support", "severity": "info"}
    ]
    
    retriever.add_documents(documents, metadata=metadata)
    
    # Test retrieval
    print("\nTesting retrieval...")
    queries = [
        "Internetas neveikia",
        "TV problema",
        "Lėtas ryšys"
    ]
    
    for query in queries:
        print(f"\nQuery: '{query}'")
        results = retriever.retrieve(query, top_k=2)
        
        for result in results:
            print(f"  [{result['score']:.3f}] {result['document']}")
    
    # Test context formatting
    print("\nTesting context formatting...")
    context = retriever.retrieve_with_context("Internetas neveikia", top_k=2)
    print(context)
    
    # Statistics
    print("\nRetriever statistics:")
    stats = retriever.get_statistics()
    for key, value in stats.items():
        print(f"  {key}: {value}")