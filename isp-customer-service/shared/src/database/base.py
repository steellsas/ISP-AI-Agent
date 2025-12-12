"""
Base Repository Class
Provides common database operations for all repositories
Works with both SQLite and PostgreSQL
"""

from typing import Any, Dict, List, Optional, TypeVar
from abc import ABC, abstractmethod
import logging

from .connection import DatabaseConnection, is_postgres

logger = logging.getLogger(__name__)

T = TypeVar("T")


class BaseRepository(ABC):
    """
    Base repository class with common CRUD operations.

    All service-specific repositories should inherit from this class.
    Works with both SQLite and PostgreSQL.
    """

    def __init__(self, db: DatabaseConnection) -> None:
        """
        Initialize repository with database connection.

        Args:
            db: DatabaseConnection instance
        """
        self.db = db

    def _row_to_dict(self, row: Any) -> Dict[str, Any]:
        """
        Convert database Row to dictionary.
        Works with both SQLite Row and PostgreSQL RealDictRow.

        Args:
            row: Database row object

        Returns:
            Dictionary representation of row
        """
        if row is None:
            return None

        # PostgreSQL RealDictRow is already dict-like
        if isinstance(row, dict):
            return dict(row)

        # SQLite Row - convert using dict()
        try:
            return dict(row)
        except (TypeError, ValueError):
            # Fallback: if row has keys() method
            if hasattr(row, "keys"):
                return {key: row[key] for key in row.keys()}
            raise

    def _rows_to_dicts(self, rows: List[Any]) -> List[Dict[str, Any]]:
        """
        Convert list of database Rows to list of dictionaries.

        Args:
            rows: List of database row objects

        Returns:
            List of dictionaries
        """
        return [self._row_to_dict(row) for row in rows if row is not None]

    def execute_query(
        self, query: str, params: Optional[tuple | Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Execute SELECT query and return results as list of dicts.

        Args:
            query: SQL query string (use ? for parameters)
            params: Query parameters (tuple or dict)

        Returns:
            List of dictionaries representing rows
        """
        with self.db.cursor() as cursor:
            if params:
                # Convert dict params to tuple if needed
                if isinstance(params, dict):
                    params = tuple(params.values())
                cursor.execute(query, params)
            else:
                cursor.execute(query)

            rows = cursor.fetchall()
            return self._rows_to_dicts(rows)

    def execute_one(
        self, query: str, params: Optional[tuple | Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Execute SELECT query and return single result.

        Args:
            query: SQL query string (use ? for parameters)
            params: Query parameters (tuple or dict)

        Returns:
            Dictionary representing row, or None if not found
        """
        with self.db.cursor() as cursor:
            if params:
                if isinstance(params, dict):
                    params = tuple(params.values())
                cursor.execute(query, params)
            else:
                cursor.execute(query)

            row = cursor.fetchone()
            return self._row_to_dict(row) if row else None

    def execute_write(
        self, query: str, params: Optional[tuple | Dict[str, Any]] = None
    ) -> int:
        """
        Execute INSERT, UPDATE, or DELETE query.

        Args:
            query: SQL query string (use ? for parameters)
            params: Query parameters (tuple or dict)

        Returns:
            Number of affected rows
        """
        with self.db.cursor() as cursor:
            if params:
                if isinstance(params, dict):
                    params = tuple(params.values())
                cursor.execute(query, params)
            else:
                cursor.execute(query)

            return cursor.rowcount

    def execute_many(
        self, query: str, params_list: List[tuple | Dict[str, Any]]
    ) -> int:
        """
        Execute query multiple times with different parameters.

        Args:
            query: SQL query string (use ? for parameters)
            params_list: List of parameter tuples/dicts

        Returns:
            Total number of affected rows
        """
        with self.db.cursor() as cursor:
            # Convert dict params to tuples if needed
            converted_params = []
            for params in params_list:
                if isinstance(params, dict):
                    converted_params.append(tuple(params.values()))
                else:
                    converted_params.append(params)

            cursor.executemany(query, converted_params)
            return cursor.rowcount

    def get_last_insert_id(self) -> int:
        """
        Get ID of last inserted row.

        Note: For PostgreSQL, prefer using RETURNING clause in INSERT.

        Returns:
            Last insert rowid
        """
        conn = self.db.get_connection()

        if is_postgres():
            # PostgreSQL - this is less reliable, use RETURNING instead
            cursor = conn.cursor()
            cursor.execute("SELECT lastval()")
            result = cursor.fetchone()[0]
            cursor.close()
            return result
        else:
            # SQLite
            return conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    def count(self, table: str, where: Optional[str] = None) -> int:
        """
        Count rows in table with optional WHERE clause.

        Args:
            table: Table name
            where: Optional WHERE clause (without WHERE keyword)

        Returns:
            Number of rows
        """
        query = f"SELECT COUNT(*) as count FROM {table}"
        if where:
            query += f" WHERE {where}"

        result = self.execute_one(query)
        return result["count"] if result else 0

    def exists(self, table: str, where: str) -> bool:
        """
        Check if row exists in table.

        Args:
            table: Table name
            where: WHERE clause (without WHERE keyword)

        Returns:
            True if row exists, False otherwise
        """
        return self.count(table, where) > 0

    @abstractmethod
    def get_table_name(self) -> str:
        """
        Get primary table name for this repository.

        Returns:
            Table name
        """
        pass