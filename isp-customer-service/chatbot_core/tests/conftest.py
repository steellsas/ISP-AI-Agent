"""
Pytest configuration and shared fixtures.

Run tests:
    cd chatbot_core
    pytest tests/ -v
    pytest tests/ -v --tb=short  # shorter traceback
    pytest tests/test_rag.py -v  # specific file
"""

import os
import sqlite3
import sys
from pathlib import Path

import pytest

# Add src to path
src_path = Path(__file__).parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

# Unit tests run DETERMINISTICALLY: the LLM classifier (Phase 3.8 perceive node) is
# off by default here, so the walker falls back to the keyword detectors the unit
# tests actually assert on — no live LLM call per yes/no confirm. The classifier's
# ON behaviour is covered by the behavioural eval harness (agent/eval), not units.
# `setdefault` lets a dev opt in with CLASSIFIER=on when specifically testing it.
os.environ.setdefault("CLASSIFIER", "off")
# Persona: narrator-worded evidence questions go through the LLM — unit tests
# assert the SCRIPTED wording, so the deterministic mode keeps scripts on.
os.environ.setdefault("NARRATOR_QUESTIONS", "off")
# VOICE_PLAN V1: unit tests feed tiny fake audio bytes (b"x") — the too-short
# guard would drop them all. Off here; the guard's own tests set it explicitly.
os.environ.setdefault("ASR_MIN_AUDIO_S", "0")


# =============================================================================
# TEST DATA ARTIFACTS (built, not versioned)
# =============================================================================
# The SQLite DB and FAISS index are build artifacts (gitignored), so a fresh
# checkout or CI runner has neither. We rebuild the DB deterministically from
# the versioned schema + seed SQL so the regression suite needs zero manual
# setup. The RAG index is heavier (pulls a ~1GB embedding model), so RAG tests
# skip cleanly when it is absent instead of forcing every run to build it.

_TESTS_DIR = Path(__file__).parent
_CHATBOT_CORE = _TESTS_DIR.parent
_PROJECT_ROOT = _CHATBOT_CORE.parent  # isp-customer-service
_DB_PATH = _PROJECT_ROOT / "database" / "isp_database.db"
_PROD_INDEX = _CHATBOT_CORE / "src" / "rag" / "vector_store_data" / "production_index.faiss"

# Order matters: schemas first (DDL), then seeds (DML). demo_internet last —
# it references rows from the base seeds (SW001, OUT001).
_SCHEMA_FILES = ("crm_schema", "network_schema")
_SEED_FILES = ("customers", "addresses", "service_plans", "equipment", "network", "demo_internet")


def _build_test_database() -> None:
    """Build & seed the SQLite test DB from versioned schema + seed SQL.

    Pure sqlite3: no network, no heavy deps, runs in well under a second. This
    mirrors scripts/setup_db.py + scripts/seed_data.py but without the emoji
    console output that crashes on non-UTF-8 Windows terminals.

    The DB is rebuilt from scratch on every session (the previous file is
    removed first) because several seed rows are written relative to
    ``datetime('now')`` — e.g. CUST008's ping_tests / bandwidth_logs sit inside
    a ``-24 hours`` detection window. A cached DB from a prior day would let
    that data age out of the window and make time-windowed tools (packet-loss
    /bandwidth diagnostics) non-deterministic. Rebuilding keeps the window
    fresh for zero practical cost.
    """
    schema_dir = _PROJECT_ROOT / "database" / "schema"
    seeds_dir = _PROJECT_ROOT / "database" / "seeds"
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    _DB_PATH.unlink(missing_ok=True)

    conn = sqlite3.connect(_DB_PATH)
    try:
        for name in _SCHEMA_FILES:
            conn.executescript((schema_dir / f"{name}.sql").read_text(encoding="utf-8"))
        for name in _SEED_FILES:
            conn.executescript((seeds_dir / f"{name}.sql").read_text(encoding="utf-8"))
        conn.commit()
    finally:
        conn.close()


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture(scope="session", autouse=True)
def ensure_test_database():
    """Guarantee a freshly seeded SQLite DB before any DB-backed test runs.

    Rebuilt every session (not just when missing) so that ``datetime('now')``
    -relative seed data — e.g. CUST008's packet-loss / bandwidth rows inside a
    24-hour detection window — never goes stale and silently breaks the
    time-windowed diagnostic tools.
    """
    _build_test_database()
    yield


@pytest.fixture(scope="session")
def kb_available() -> bool:
    """True when the production RAG/FAISS index has been built."""
    return _PROD_INDEX.exists()


@pytest.fixture
def require_kb(kb_available):
    """Skip a test cleanly when the RAG knowledge base has not been built.

    RAG correctness is covered in Phase 1; the regression net only needs the
    DB-backed tool behaviour to be deterministic.
    """
    if not kb_available:
        pytest.skip("RAG knowledge base not built (run build_kb.py) — covered in Phase 1")


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
