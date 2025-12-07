"""
Pytest configuration and shared fixtures.

Run tests:
    cd chatbot_core
    pytest tests/ -v
    pytest tests/ -v --tb=short  # shorter traceback
    pytest tests/test_rag.py -v  # specific file
"""

import sys
from pathlib import Path
import pytest

# Add src to path
src_path = Path(__file__).parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture(scope="session")
def project_root():
    """Get project root directory."""
    return Path(__file__).parent.parent


@pytest.fixture(scope="session")
def db_connection():
    """Get database connection (shared across all tests)."""
    try:
        from agent.tools import get_db
        return get_db()
    except Exception as e:
        pytest.skip(f"Database not available: {e}")


@pytest.fixture(scope="session")
def retriever():
    """Get RAG retriever with production KB loaded."""
    try:
        from rag import get_retriever
        
        # Create retriever with lower threshold for testing
        r = get_retriever(top_k=5, similarity_threshold=0.3)
        
        # Load production KB
        success = r.load("production")
        if not success:
            pytest.skip("Production KB not found - run build_kb.py first")
        
        # Verify it loaded
        stats = r.get_statistics()
        if stats["total_documents"] == 0:
            pytest.skip("Production KB is empty")
        
        return r
    except Exception as e:
        pytest.skip(f"RAG not available: {e}")


@pytest.fixture
def sample_customer_phone():
    """Sample customer phone for testing."""
    return "+37060012345"


@pytest.fixture
def sample_customer_id():
    """Sample customer ID for testing."""
    return "CUST001"
