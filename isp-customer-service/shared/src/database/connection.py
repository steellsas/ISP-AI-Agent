"""
Database Connection Manager
Provides thread-safe connections with connection pooling
Supports both SQLite (local) and PostgreSQL (production/Railway)

Auto-detection:
- If DATABASE_URL is set → PostgreSQL
- Otherwise → SQLite (requires db_path)
"""

import os
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Optional, Any
import logging

logger = logging.getLogger(__name__)

# =============================================================================
# DATABASE TYPE DETECTION
# =============================================================================

DATABASE_URL = os.getenv("DATABASE_URL")


def _is_postgres() -> bool:
    """Check if using PostgreSQL based on DATABASE_URL."""
    return DATABASE_URL is not None and (
        DATABASE_URL.startswith("postgres://") or
        DATABASE_URL.startswith("postgresql://")
    )


USE_POSTGRES = _is_postgres()

# Import appropriate driver
if USE_POSTGRES:
    try:
        import psycopg2
        from psycopg2.extras import RealDictCursor
        logger.info("Database: PostgreSQL (from DATABASE_URL)")
    except ImportError:
        raise ImportError(
            "psycopg2-binary is required for PostgreSQL. "
            "Run: uv add psycopg2-binary"
        )
else:
    import sqlite3
    logger.info("Database: SQLite")


# =============================================================================
# POSTGRES CURSOR WRAPPER
# =============================================================================

class PostgresCursorWrapper:
    """
    Wrapper for PostgreSQL cursor that converts SQLite-style
    parameters (?) to PostgreSQL-style (%s).
    """

    def __init__(self, cursor):
        self._cursor = cursor

    def execute(self, query: str, params: tuple = None):
        """Execute query, converting ? to %s for PostgreSQL."""
        converted_query = query.replace("?", "%s")
        if params:
            self._cursor.execute(converted_query, params)
        else:
            self._cursor.execute(converted_query)

    def executemany(self, query: str, params_list: list):
        """Execute query multiple times with different parameters."""
        converted_query = query.replace("?", "%s")
        self._cursor.executemany(converted_query, params_list)

    def executescript(self, script: str):
        """Execute multiple SQL statements."""
        # Remove SQLite-specific statements
        statements = script.split(";")
        for stmt in statements:
            stmt = stmt.strip()
            if stmt and not stmt.upper().startswith("PRAGMA"):
                try:
                    self._cursor.execute(stmt)
                except Exception as e:
                    logger.debug(f"Statement skipped: {e}")

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()

    def fetchmany(self, size=None):
        return self._cursor.fetchmany(size)

    @property
    def rowcount(self):
        return self._cursor.rowcount

    @property
    def description(self):
        return self._cursor.description

    def close(self):
        self._cursor.close()


# =============================================================================
# DATABASE CONNECTION CLASS
# =============================================================================

class DatabaseConnection:
    """
    Thread-safe database connection manager.
    Supports both SQLite and PostgreSQL.
    """

    _instance: Optional["DatabaseConnection"] = None
    _lock = threading.Lock()

    def __init__(self, db_path: Optional[str | Path] = None) -> None:
        """
        Initialize database connection manager.

        Args:
            db_path: Path to SQLite database file (ignored for PostgreSQL)
        """
        self._local = threading.local()
        self.use_postgres = USE_POSTGRES

        if self.use_postgres:
            self.database_url = DATABASE_URL
            # Fix Railway URL format (postgres:// -> postgresql://)
            if self.database_url and self.database_url.startswith("postgres://"):
                self.database_url = self.database_url.replace(
                    "postgres://", "postgresql://", 1
                )
            logger.info("PostgreSQL connection configured")
        else:
            if db_path is None:
                raise ValueError(
                    "db_path required for SQLite (DATABASE_URL not set)"
                )
            self.db_path = Path(db_path)
            if not self.db_path.exists():
                raise FileNotFoundError(f"Database not found: {self.db_path}")
            logger.info(f"SQLite connection configured: {self.db_path}")

    @classmethod
    def reset_instance(cls):
        """Reset singleton instance (useful for testing)."""
        with cls._lock:
            cls._instance = None

    def __new__(cls, db_path: Optional[str | Path] = None) -> "DatabaseConnection":
        """Singleton pattern to ensure only one instance exists."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def get_connection(self) -> Any:
        """
        Get thread-local database connection.

        Returns:
            Database connection object for current thread
        """
        if not hasattr(self._local, "connection") or self._local.connection is None:
            if self.use_postgres:
                self._local.connection = psycopg2.connect(self.database_url)
                self._local.connection.autocommit = False
                logger.debug(
                    f"Created PostgreSQL connection for thread "
                    f"{threading.current_thread().name}"
                )
            else:
                self._local.connection = sqlite3.connect(
                    str(self.db_path), check_same_thread=False, timeout=30.0
                )
                # Enable foreign keys
                self._local.connection.execute("PRAGMA foreign_keys = ON")
                # Use Row factory for dict-like access
                self._local.connection.row_factory = sqlite3.Row
                logger.debug(
                    f"Created SQLite connection for thread "
                    f"{threading.current_thread().name}"
                )

        return self._local.connection

    def close(self) -> None:
        """Close current thread's database connection."""
        if hasattr(self._local, "connection") and self._local.connection is not None:
            self._local.connection.close()
            self._local.connection = None
            logger.debug(
                f"Closed connection for thread {threading.current_thread().name}"
            )

    @contextmanager
    def transaction(self) -> Generator[Any, None, None]:
        """
        Context manager for database transactions.

        Automatically commits on success, rolls back on exception.
        """
        conn = self.get_connection()
        try:
            yield conn
            conn.commit()
            logger.debug("Transaction committed")
        except Exception as e:
            conn.rollback()
            logger.error(f"Transaction rolled back: {e}")
            raise

    @contextmanager
    def cursor(self) -> Generator[Any, None, None]:
        """
        Context manager for database cursor.

        Automatically commits on success, rolls back on exception.
        Returns dict-like rows for both SQLite and PostgreSQL.
        """
        conn = self.get_connection()

        if self.use_postgres:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            wrapped_cursor = PostgresCursorWrapper(cursor)
        else:
            cursor = conn.cursor()
            wrapped_cursor = cursor  # SQLite cursor works directly

        try:
            yield wrapped_cursor
            conn.commit()
            logger.debug("Cursor operation committed")
        except Exception as e:
            conn.rollback()
            logger.error(f"Cursor operation rolled back: {e}")
            raise
        finally:
            if self.use_postgres:
                cursor.close()
            else:
                wrapped_cursor.close()

    def is_postgres(self) -> bool:
        """Check if using PostgreSQL."""
        return self.use_postgres


# =============================================================================
# GLOBAL INSTANCE FUNCTIONS
# =============================================================================

_db_connection: Optional[DatabaseConnection] = None


def get_db_connection(db_path: Optional[str | Path] = None) -> DatabaseConnection:
    """
    Get global database connection instance.

    Args:
        db_path: Path to database file (only needed for SQLite on first call)

    Returns:
        DatabaseConnection instance
    """
    global _db_connection

    if _db_connection is None:
        if not USE_POSTGRES and db_path is None:
            raise ValueError(
                "db_path must be provided for SQLite (DATABASE_URL not set)"
            )
        _db_connection = DatabaseConnection(db_path)

    return _db_connection


def init_database(db_path: Optional[str | Path] = None) -> DatabaseConnection:
    """
    Initialize global database connection.

    For PostgreSQL: db_path is ignored, uses DATABASE_URL
    For SQLite: db_path is required

    Args:
        db_path: Path to SQLite database file

    Returns:
        DatabaseConnection instance
    """
    global _db_connection

    # Reset singleton for fresh initialization
    DatabaseConnection.reset_instance()
    _db_connection = None

    _db_connection = DatabaseConnection(db_path)
    return _db_connection


def is_postgres() -> bool:
    """Check if using PostgreSQL."""
    return USE_POSTGRES


def get_database_type() -> str:
    """Get current database type as string."""
    return "PostgreSQL" if USE_POSTGRES else "SQLite"
