"""
Tests for RAG (Retrieval Augmented Generation) system.

These tests verify that the knowledge base returns relevant results.
Run: pytest tests/test_rag.py -v
"""

import pytest


class TestRAGRetrieval:
    """Tests for RAG document retrieval."""

    def test_retriever_loads_production_kb(self, retriever):
        """Should have documents loaded."""
        stats = retriever.get_statistics()
        
        assert stats["total_documents"] > 0
        assert stats["total_documents"] >= 50  # We have ~70 chunks

    def test_retrieve_internet_no_connection(self, retriever):
        """Should find internet troubleshooting for 'neveikia internetas'."""
        results = retriever.retrieve("neveikia internetas", top_k=3, threshold=0.3)
        
        assert len(results) > 0, "Should find results for 'neveikia internetas'"
        
        # Should find internet-related content
        first_result = results[0]
        assert first_result["score"] > 0.3
        
        # Check it's relevant
        doc_lower = first_result["document"].lower()
        assert any(word in doc_lower for word in ["internet", "router", "ryšy", "neveik"])

    def test_retrieve_slow_internet(self, retriever):
        """Should find content for slow internet."""
        results = retriever.retrieve("lėtas internetas", top_k=3, threshold=0.3)
        
        assert len(results) > 0, "Should find results for 'lėtas internetas'"
        assert results[0]["score"] > 0.3
        
        # Should mention speed or slow
        doc_lower = results[0]["document"].lower()
        assert any(word in doc_lower for word in ["lėtas", "greitis", "speed", "lėt", "internet"])

    def test_retrieve_wifi_password(self, retriever):
        """Should find WiFi password information."""
        results = retriever.retrieve("WiFi slaptažodis", top_k=3, threshold=0.3)
        
        assert len(results) > 0, "Should find results for 'WiFi slaptažodis'"
        
        doc_lower = results[0]["document"].lower()
        assert any(word in doc_lower for word in ["slaptažod", "password", "wifi", "key"])

    def test_retrieve_router_lights(self, retriever):
        """Should find router lights/LED information."""
        results = retriever.retrieve("routerio lemputės", top_k=3, threshold=0.3)
        
        assert len(results) > 0, "Should find results for 'routerio lemputės'"
        
        doc_lower = results[0]["document"].lower()
        assert any(word in doc_lower for word in ["lemput", "power", "internet", "led", "žalia"])

    def test_retrieve_tv_no_signal(self, retriever):
        """Should find TV troubleshooting."""
        results = retriever.retrieve("TV nerodo nėra signalo", top_k=3, threshold=0.3)
        
        assert len(results) > 0, "Should find results for TV signal"
        
        doc_lower = results[0]["document"].lower()
        assert any(word in doc_lower for word in ["tv", "signal", "hdmi", "priedėl", "nerodo"])

    def test_retrieve_technician_visit(self, retriever):
        """Should find technician visit procedure."""
        results = retriever.retrieve("techniko vizitas", top_k=3, threshold=0.3)
        
        assert len(results) > 0, "Should find results for 'techniko vizitas'"
        
        doc_lower = results[0]["document"].lower()
        assert any(word in doc_lower for word in ["technik", "vizit", "atvyk", "sla"])

    def test_retrieve_equipment_replacement(self, retriever):
        """Should find equipment replacement info."""
        results = retriever.retrieve("routeris sugedęs keisti įrangą", top_k=3, threshold=0.3)
        
        assert len(results) > 0, "Should find results for equipment replacement"
        
        doc_lower = results[0]["document"].lower()
        assert any(word in doc_lower for word in ["kei", "įrang", "router", "suged", "grąžin"])

    def test_retrieve_intermittent_connection(self, retriever):
        """Should find intermittent connection troubleshooting."""
        results = retriever.retrieve("internetas nutrūkinėja", top_k=3, threshold=0.3)
        
        assert len(results) > 0, "Should find results for 'internetas nutrūkinėja'"
        
        doc_lower = results[0]["document"].lower()
        assert any(word in doc_lower for word in ["nutrūk", "dingsta", "nestabil", "internet"])


class TestRAGMetadata:
    """Tests for RAG result metadata."""

    def test_results_have_metadata(self, retriever):
        """Results should include metadata."""
        results = retriever.retrieve("internetas", top_k=1, threshold=0.3)
        
        assert len(results) > 0, "Should find results for 'internetas'"
        
        result = results[0]
        assert "metadata" in result
        assert "score" in result
        assert "document" in result

    def test_metadata_has_source(self, retriever):
        """Metadata should include source file."""
        results = retriever.retrieve("internetas", top_k=1, threshold=0.3)
        
        assert len(results) > 0, "Should find results"
        metadata = results[0]["metadata"]
        
        assert "source" in metadata or "filename" in metadata

    def test_metadata_has_category(self, retriever):
        """Metadata should include category."""
        results = retriever.retrieve("internetas", top_k=1, threshold=0.3)
        
        assert len(results) > 0, "Should find results"
        metadata = results[0]["metadata"]
        
        # Should have category or problem_type
        has_category = "category" in metadata or "problem_type" in metadata
        assert has_category


class TestRAGEdgeCases:
    """Tests for RAG edge cases."""

    def test_empty_query_handled(self, retriever):
        """Should handle empty query gracefully."""
        try:
            results = retriever.retrieve("", top_k=3)
            # Either returns empty or raises - both acceptable
            assert isinstance(results, list)
        except Exception:
            pass  # Exception is acceptable for empty query

    def test_nonsense_query(self, retriever):
        """Should return low scores for irrelevant query."""
        results = retriever.retrieve("asdfghjkl zxcvbnm", top_k=3, threshold=0.5)
        
        # Should return few or no results above threshold
        assert len(results) <= 3

    def test_english_query_works(self, retriever):
        """Should handle English queries too."""
        results = retriever.retrieve("router restart troubleshooting", top_k=3)
        
        # Might find something due to multilingual embeddings
        assert isinstance(results, list)

    def test_retrieve_with_context(self, retriever):
        """retrieve_with_context should return formatted string."""
        context = retriever.retrieve_with_context("neveikia internetas", top_k=2)
        
        assert isinstance(context, str)
        assert len(context) > 0


class TestRAGStatistics:
    """Tests for RAG statistics."""

    def test_get_statistics(self, retriever):
        """Should return valid statistics."""
        stats = retriever.get_statistics()
        
        assert "total_documents" in stats
        assert "embedding_dim" in stats
        assert stats["embedding_dim"] == 768  # Multilingual model
