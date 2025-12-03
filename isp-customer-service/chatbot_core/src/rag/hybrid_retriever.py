"""
Hybrid Retriever
Combines semantic search with BM25-style keyword matching

Benefits:
- Semantic: Understands meaning ("neveikia" ≈ "not working")
- Keywords: Exact matches for technical terms ("WAN", "DNS", "5GHz")
- Proxy methods: Works as drop-in replacement for base Retriever
"""

from typing import List, Dict, Any, Optional
import re
import logging

try:
    from isp_shared.utils import get_logger
except ImportError:
    def get_logger(name):
        return logging.getLogger(name)

logger = get_logger(__name__)


class HybridRetriever:
    """
    Combines semantic search with BM25-style keyword matching.
    
    Can be used as drop-in replacement for base Retriever.
    """
    
    def __init__(self, retriever, keyword_weight: float = 0.3):
        """
        Initialize hybrid retriever.
        
        Args:
            retriever: Base Retriever instance
            keyword_weight: Weight for keyword matching (0.0-1.0)
                           0.0 = pure semantic, 1.0 = pure keyword
        """
        self.retriever = retriever
        self.keyword_weight = keyword_weight
        
        # Important technical keywords that should match exactly
        self.technical_keywords = {
            # Network
            "wan", "lan", "dns", "dhcp", "ip", "nat", "gateway",
            "wifi", "5ghz", "2.4ghz", "ssid", "wpa", "wpa2",
            # Hardware
            "router", "modem", "ont", "switch", "hub",
            "fiber", "dsl", "ethernet", "cable", "rj45",
            "port", "power", "led", "lemputė", "lempute",
            # Actions
            "reset", "restart", "reboot", "perkrauti", "perkrovimas",
            # Diagnostics
            "mcp", "ping", "packet", "latency", "bandwidth", "speedtest",
            "traceroute", "nslookup",
            # Status
            "up", "down", "flapping", "timeout", "connected", "disconnected",
            # Lithuanian technical
            "maršrutizatorius", "marsrutizatorius", "modemas",
            "prievadas", "kabelis", "maitinimas"
        }
        
        # Stop words to ignore (Lithuanian + English)
        self.stop_words = {
            # Lithuanian
            "ir", "ar", "su", "be", "per", "nuo", "iki", "apie", "pas",
            "tai", "kas", "kaip", "kur", "kada", "kodėl", "kodel",
            "yra", "buvo", "bus", "būti", "buti", "turi", "gali",
            "labai", "dabar", "jau", "dar", "tik", "net", "vis",
            "man", "mano", "jums", "jūsų", "jusu",
            # English
            "the", "a", "an", "is", "are", "was", "were", "be", "been",
            "have", "has", "had", "do", "does", "did", "will", "would",
            "can", "could", "may", "might", "must", "shall", "should",
            "and", "or", "but", "if", "then", "else", "when", "where",
            "what", "which", "who", "how", "why",
            "this", "that", "these", "those",
            "my", "your", "his", "her", "its", "our", "their",
            "not", "no", "yes", "very", "just", "only", "also"
        }
        
        logger.info(f"HybridRetriever initialized (keyword_weight={keyword_weight})")
    
    # =========================================================================
    # MAIN RETRIEVE METHOD
    # =========================================================================
    
    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        threshold: Optional[float] = None,
        filter_metadata: Optional[Dict] = None
    ) -> List[Dict[str, Any]]:
        """
        Hybrid retrieval combining semantic and keyword search.
        
        Args:
            query: Search query
            top_k: Number of results to return
            threshold: Minimum similarity threshold
            filter_metadata: Metadata filter
            
        Returns:
            List of results sorted by hybrid score
        """
        # 1. Semantic search (get more for re-ranking)
        semantic_results = self.retriever.retrieve(
            query=query,
            top_k=top_k * 3,  # Get 3x for better re-ranking
            threshold=threshold,
            filter_metadata=filter_metadata
        )
        
        if not semantic_results:
            logger.debug(f"No semantic results for: {query[:50]}")
            return []
        
        # 2. Extract query keywords
        query_keywords = self._extract_keywords(query)
        query_technical = query_keywords & self.technical_keywords
        
        logger.debug(f"Query keywords: {query_keywords}, technical: {query_technical}")
        
        # 3. Score each result
        for result in semantic_results:
            doc_text = result.get("document", "")
            doc_keywords = self._extract_keywords(doc_text)
            
            # Calculate keyword overlap
            common_keywords = query_keywords & doc_keywords
            overlap_count = len(common_keywords)
            
            # Calculate technical keyword overlap (weighted more)
            technical_overlap = query_technical & doc_keywords
            technical_count = len(technical_overlap)
            
            # Keyword score: normalize to 0-1 range
            max_possible = len(query_keywords) if query_keywords else 1
            keyword_score = min(1.0, (overlap_count * 0.1 + technical_count * 0.2))
            
            # Hybrid score
            semantic_score = result.get("score", 0)
            hybrid_score = (
                semantic_score * (1 - self.keyword_weight) +
                keyword_score * self.keyword_weight
            )
            
            # Store scores
            result["semantic_score"] = semantic_score
            result["keyword_score"] = keyword_score
            result["keyword_matches"] = list(common_keywords)[:5]  # Top 5 for debug
            result["technical_matches"] = list(technical_overlap)
            result["hybrid_score"] = hybrid_score
            result["score"] = hybrid_score  # Override score for compatibility
        
        # 4. Re-rank by hybrid score
        semantic_results.sort(key=lambda x: x.get("hybrid_score", 0), reverse=True)
        
        # 5. Return top_k
        results = semantic_results[:top_k]
        
        logger.debug(f"Hybrid retrieval: {len(results)} results for '{query[:30]}...'")
        
        return results
    
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
        results = self.retrieve(query, top_k=top_k or 3, threshold=threshold)
        
        if not results:
            return "No relevant information found."
        
        context_parts = []
        
        for i, result in enumerate(results, 1):
            doc_text = result["document"]
            score = result.get("hybrid_score", result.get("score", 0))
            
            if include_scores:
                context_parts.append(
                    f"[Document {i}] (Relevance: {score:.2f})\n{doc_text}"
                )
            else:
                context_parts.append(
                    f"[Document {i}]\n{doc_text}"
                )
        
        return "\n\n---\n\n".join(context_parts)
    
    # =========================================================================
    # KEYWORD EXTRACTION
    # =========================================================================
    
    def _extract_keywords(self, text: str) -> set:
        """
        Extract meaningful keywords from text.
        
        Args:
            text: Input text
            
        Returns:
            Set of keywords
        """
        if not text:
            return set()
        
        # Tokenize: extract words
        words = re.findall(r'\b\w+\b', text.lower())
        
        # Filter: remove short words and stop words
        keywords = {
            w for w in words 
            if len(w) > 2 and w not in self.stop_words
        }
        
        return keywords
    
    # =========================================================================
    # PROXY METHODS (delegate to base retriever)
    # =========================================================================
    
    def load(self, name: str = "default") -> bool:
        """Load knowledge base (proxy to base retriever)."""
        success = self.retriever.load(name)
        if success:
            logger.info(f"HybridRetriever loaded KB: {name}")
        return success
    
    def save(self, name: str = "default"):
        """Save knowledge base (proxy to base retriever)."""
        self.retriever.save(name)
        logger.info(f"HybridRetriever saved KB: {name}")
    
    def add_documents(
        self,
        documents: List[str],
        metadata: Optional[List[Dict[str, Any]]] = None,
        ids: Optional[List[str]] = None,
        batch_size: int = 32
    ):
        """Add documents (proxy to base retriever)."""
        self.retriever.add_documents(
            documents=documents,
            metadata=metadata,
            ids=ids,
            batch_size=batch_size
        )
    
    def load_documents_from_directory(
        self,
        directory,
        file_extension: str = ".md",
        recursive: bool = True
    ):
        """Load documents from directory (proxy to base retriever)."""
        self.retriever.load_documents_from_directory(
            directory=directory,
            file_extension=file_extension,
            recursive=recursive
        )
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get statistics (proxy + hybrid info)."""
        stats = self.retriever.get_statistics()
        stats["hybrid_enabled"] = True
        stats["keyword_weight"] = self.keyword_weight
        stats["technical_keywords_count"] = len(self.technical_keywords)
        return stats
    
    def clear(self):
        """Clear all data (proxy to base retriever)."""
        if hasattr(self.retriever, 'vector_store'):
            self.retriever.vector_store.clear()
        logger.info("HybridRetriever cleared")
    
    # =========================================================================
    # CONFIGURATION
    # =========================================================================
    
    def set_keyword_weight(self, weight: float):
        """
        Update keyword weight.
        
        Args:
            weight: New weight (0.0-1.0)
        """
        self.keyword_weight = max(0.0, min(1.0, weight))
        logger.info(f"Keyword weight updated to: {self.keyword_weight}")
    
    def add_technical_keywords(self, keywords: List[str]):
        """
        Add custom technical keywords.
        
        Args:
            keywords: List of keywords to add
        """
        for kw in keywords:
            self.technical_keywords.add(kw.lower())
        logger.info(f"Added {len(keywords)} technical keywords")


# =============================================================================
# EXAMPLE / TEST
# =============================================================================

if __name__ == "__main__":
    # Test hybrid retriever
    print("=" * 60)
    print("Testing HybridRetriever")
    print("=" * 60)
    
    # Mock retriever for testing
    class MockRetriever:
        def retrieve(self, query, top_k=5, threshold=None, filter_metadata=None):
            return [
                {
                    "document": "Internetas neveikia. Patikrinkite WAN kabelį ir router lemputės.",
                    "score": 0.85,
                    "metadata": {"source": "test.md"}
                },
                {
                    "document": "Lėtas internetas gali būti dėl WiFi trukdžių 2.4GHz dažnyje.",
                    "score": 0.75,
                    "metadata": {"source": "test2.md"}
                },
                {
                    "document": "TV dekoderis neveikia. Perkraukite įrenginį.",
                    "score": 0.65,
                    "metadata": {"source": "test3.md"}
                }
            ]
        
        def load(self, name):
            return True
        
        def save(self, name):
            pass
        
        def get_statistics(self):
            return {"total_documents": 3}
    
    # Create hybrid retriever
    mock = MockRetriever()
    hybrid = HybridRetriever(mock, keyword_weight=0.3)
    
    # Test queries
    test_queries = [
        "neveikia internetas WAN",
        "lėtas WiFi 2.4GHz",
        "TV problema"
    ]
    
    for query in test_queries:
        print(f"\nQuery: '{query}'")
        results = hybrid.retrieve(query, top_k=2)
        
        for r in results:
            print(f"  [{r['hybrid_score']:.3f}] {r['document'][:50]}...")
            print(f"       semantic={r['semantic_score']:.2f}, keyword={r['keyword_score']:.2f}")
            print(f"       matches: {r.get('keyword_matches', [])}")
    
    # Test statistics
    print("\nStatistics:")
    stats = hybrid.get_statistics()
    for k, v in stats.items():
        print(f"  {k}: {v}")
    
    print("\n" + "=" * 60)
    print("✅ Test complete!")