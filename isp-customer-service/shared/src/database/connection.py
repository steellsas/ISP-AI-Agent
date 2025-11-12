"""
Database Connection Manager
Provides thread-safe SQLite connections with connection pooling
"""

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Optional
import logging

logger = logging.getLogger(__name__)


class DatabaseConnection:
    """
    Thread-safe SQLite database connection manager.
    
    Uses thread-local storage to ensure each thread gets its own connection.
    Implements connection pooling and automatic cleanup.
    """
    
    _instance: Optional["DatabaseConnection"] = None
    _lock = threading.Lock()
    
    def __init__(self, db_path: str | Path) -> None:
        """
        Initialize database connection manager.
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        self._local = threading.local()
        
        if not self.db_path.exists():
            raise FileNotFoundError(f"Database not found: {self.db_path}")
        
        logger.info(f"DatabaseConnection initialized: {self.db_path}")
    
    def __new__(cls, db_path: str | Path) -> "DatabaseConnection":
        """Singleton pattern to ensure only one instance exists."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def get_connection(self) -> sqlite3.Connection:
        """
        Get thread-local database connection.
        
        Returns:
            SQLite connection object for current thread
        """
        if not hasattr(self._local, "connection") or self._local.connection is None:
            self._local.connection = sqlite3.connect(
                str(self.db_path),
                check_same_thread=False,
                timeout=30.0
            )
            # Enable foreign keys
            self._local.connection.execute("PRAGMA foreign_keys = ON")
            # Use Row factory for dict-like access
            self._local.connection.row_factory = sqlite3.Row
            
            logger.debug(f"Created new connection for thread {threading.current_thread().name}")
        
        return self._local.connection
    
    def close(self) -> None:
        """Close current thread's database connection."""
        if hasattr(self._local, "connection") and self._local.connection is not None:
            self._local.connection.close()
            self._local.connection = None
            logger.debug(f"Closed connection for thread {threading.current_thread().name}")
    
    @contextmanager
    def transaction(self) -> Generator[sqlite3.Connection, None, None]:
        """
        Context manager for database transactions.
        
        Automatically commits on success, rolls back on exception.
        
        Usage:
            with db.transaction() as conn:
                conn.execute("INSERT INTO ...")
        
        Yields:
            SQLite connection object
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
    def cursor(self) -> Generator[sqlite3.Cursor, None, None]:
        """
        Context manager for database cursor.
        
        Automatically commits on success, rolls back on exception.
        
        Usage:
            with db.cursor() as cur:
                cur.execute("SELECT * FROM customers")
                results = cur.fetchall()
        
        Yields:
            SQLite cursor object
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            yield cursor
            conn.commit()
            logger.debug("Cursor operation committed")
        except Exception as e:
            conn.rollback()
            logger.error(f"Cursor operation rolled back: {e}")
            raise
        finally:
            cursor.close()


# Global database connection instance
_db_connection: Optional[DatabaseConnection] = None


def get_db_connection(db_path: Optional[str | Path] = None) -> DatabaseConnection:
    """
    Get global database connection instance.
    
    Args:
        db_path: Path to database file (only needed on first call)
    
    Returns:
        DatabaseConnection instance
    
    Raises:
        ValueError: If db_path not provided on first call
    """
    global _db_connection
    
    if _db_connection is None:
        if db_path is None:
            raise ValueError("db_path must be provided on first call to get_db_connection")
        _db_connection = DatabaseConnection(db_path)
    
    return _db_connection


def init_database(db_path: str | Path) -> DatabaseConnection:
    """
    Initialize global database connection.
    
    Args:
        db_path: Path to SQLite database file
    
    Returns:
        DatabaseConnection instance
    """
    global _db_connection
    _db_connection = DatabaseConnection(db_path)
    return _db_connection