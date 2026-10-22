"""
Pytest configuration and shared fixtures.

Run tests:
    cd chatbot_core
    pytest tests/ -v
    pytest tests/ -v --tb=short  # shorter traceback
    pytest -m diagnosis tests/  # one area (tests/__init__.py)
"""

import os
import sqlite3
import sys
import tempfile
from pathlib import Path

import pytest

# The suite rebuilds its database from the seeds on every session, so it needs its OWN file:
# the demo one is held open by the server/dashboard, and deleting a held file on Windows is
# `PermissionError [WinError 32]`. Until wave 5 that meant tests and a live voice test could
# not run at the same time.
#
# This MUST stay above the `agent` import below: `agent/__init__` imports `agent.tools`, which
# resolves `DB_PATH` once, at import time. Set it later and the tests would rebuild the demo
# file while the agent under test reads the test one.
os.environ.setdefault("DATABASE_PATH", "database/isp_database.test.db")

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
# The analyst calls an LLM — deterministic tests never want that (opt in with
# ANALYST_MODE=sync when testing it specifically).
os.environ.setdefault("ANALYST_MODE", "off")
# Test sessions write their traces OUTSIDE logs/sessions (review finding L: ~121k test
# traces buried the real calls there). A dev can still point TRACE_DIR elsewhere.
TEST_TRACE_DIR = Path(tempfile.gettempdir()) / "isp_agent_test_traces"
os.environ.setdefault("TRACE_DIR", str(TEST_TRACE_DIR))
# No TTS network in tests: the startup prewarm is off and the TTS disk cache too (a
# cached sentence from an earlier run must not satisfy an adapter test).
os.environ.setdefault("TTS_PREWARM", "off")
os.environ.setdefault("TTS_CACHE_DIR", "off")
# The model the suite assumes, whatever .env picks for the demo (the app imports load
# .env, which never overrides an existing variable): tests patch the transport of an
# OpenAI name and must not be routed to Scaleway or a fallback behind their back.
os.environ.setdefault("LLM_MODEL", "gpt-4o-mini")
os.environ.setdefault("LLM_FALLBACK_MODEL", "")
os.environ.setdefault("LLM_WARMUP", "off")  # no provider request at app start in tests
# Ops log of test runs stays out of logs/ops (same reason as the traces).
os.environ.setdefault("OPS_LOG_DIR", str(Path(tempfile.gettempdir()) / "isp_agent_test_ops"))

# Imported only NOW, after every env default above: this is the first line that pulls in
# `agent`, and `agent/__init__` reads some of those switches at import time.
from agent.db_path import database_path  # noqa: E402, I001


# =============================================================================
# TEST DATA ARTIFACTS (built, not versioned)
# =============================================================================
# The SQLite DB is a build artifact (gitignored), so a fresh checkout or CI runner has
# none. We rebuild it deterministically from the versioned schema + seed SQL, so the
# regression suite needs zero manual setup. (The FAISS index used to live here too, with
# fixtures that skipped RAG tests when it was missing; wave 5 removed the v1 store, and
# the knowledge tests now read the markdown documents straight from disk.)

_TESTS_DIR = Path(__file__).parent
_CHATBOT_CORE = _TESTS_DIR.parent
_PROJECT_ROOT = _CHATBOT_CORE.parent  # isp-customer-service
_DB_PATH = database_path()  # DATABASE_PATH above -> database/isp_database.test.db

# Order matters: schemas first (DDL), then seeds (DML). demo_internet last —
# it references rows from the base seeds (SW001, OUT001).
_SCHEMA_FILES = ("crm_schema", "network_schema")
_SEED_FILES = (
    "customers",
    "addresses",
    "service_plans",
    "equipment",
    "network",
    "demo_internet",
    "invoices",
    "similar_streets",
    "network_faults",
)


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


@pytest.fixture(autouse=True)
def forget_test_tickets(request):
    """Tickets a DB test registers are removed after it: an open ticket left behind turns
    the next test's call about the same problem into a repeat call (D-12)."""
    if "db_connection" not in request.fixturenames:
        yield
        return
    db = request.getfixturevalue("db_connection")
    with db.cursor() as cursor:
        cursor.execute("SELECT ticket_id FROM tickets")
        before = {row[0] for row in cursor.fetchall()}
    yield
    with db.cursor() as cursor:
        cursor.execute("SELECT ticket_id FROM tickets")
        created = [row[0] for row in cursor.fetchall() if row[0] not in before]
        for ticket_id in created:
            cursor.execute("DELETE FROM tickets WHERE ticket_id = ?", (ticket_id,))


@pytest.fixture
def sample_customer_phone():
    """Sample customer phone for testing."""
    return "+37060012345"


@pytest.fixture
def sample_customer_id():
    """Sample customer ID for testing."""
    return "CUST001"


@pytest.fixture(name="make_state")
def make_state_fixture():
    """Factory for a call's GraphState (tests.calls.make_state)."""
    from tests.calls import make_state

    return make_state


@pytest.fixture(name="make_runtime")
def make_runtime_fixture():
    """Factory for a call's AgentRuntime with optional fake tools (tests.calls.make_runtime)."""
    from tests.calls import make_runtime

    return make_runtime


# =============================================================================
# TESTS BY FUNCTION (ROADMAP 3.2)
# =============================================================================
# The function report (Area → Function → ✓/✗) and the area markers (`-m identification`):
# tests/function_report.py. A whole call and calls that start in a given phase:
# tests/phases.py.
from tests.function_report import (  # noqa: E402
    pytest_collection_modifyitems,
    pytest_configure,
    pytest_runtest_logreport,
    pytest_terminal_summary,
)

__all__ = [
    "pytest_collection_modifyitems",
    "pytest_configure",
    "pytest_runtest_logreport",
    "pytest_terminal_summary",
]


@pytest.fixture
def call(db_connection):
    """`call(phone)` → a CallDriver: the real graph, the speaking LLM faked (tests/phases.py)."""
    from tests.phases import CallDriver

    drivers = []

    def _make(phone="unknown", greet=True):
        drivers.append(CallDriver(phone, greet=greet))
        return drivers[-1]

    yield _make
    for d in drivers:
        d.close()


@pytest.fixture
def identified(db_connection):
    """`identified("CUST105")` → a CallDriver that starts after identification (tests/phases.py)."""
    from tests.phases import identified_call

    drivers = []

    def _make(customer_id="CUST105", **kw):
        drivers.append(identified_call(customer_id, **kw))
        return drivers[-1]

    yield _make
    for d in drivers:
        d.close()


@pytest.fixture
def diagnosing(db_connection, monkeypatch):
    """`diagnosing("router_hung")` → a CallDriver that starts after identification, on the
    demo customer whose line shows that card (tests/phases.py CARD_CUSTOMER); its next turn
    hears the findings. The demo's reboot/bridge simulations are on, and the DB is reset
    afterwards: a simulated reboot or a bind changes the seeded line."""
    from app.admin import reset_db

    from tests.phases import CARD_CUSTOMER, identified_call

    monkeypatch.setenv("SIMULATE_REBOOT", "on")
    monkeypatch.setenv("SIMULATE_BRIDGE", "on")
    drivers = []

    def _make(card, **kw):
        drivers.append(identified_call(CARD_CUSTOMER[card], **kw))
        return drivers[-1]

    yield _make
    for d in drivers:
        d.close()
    if drivers:
        reset_db()
