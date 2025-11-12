"""
Base Repository Class
Provides common database operations for all repositories
"""

import sqlite3
from typing import Any, Dict, List, Optional, Type, TypeVar
from abc import ABC, abstractmethod
import logging

from .connection import DatabaseConnection

logger = logging.getLogger(__name__)

T = TypeVar("T")


class BaseRepository(ABC):
    """
    Base repository class with common CRUD operations.
    
    All service-specific repositories should inherit from this class.
    """
    
    def __init__(self, db: DatabaseConnection) -> None:
        """
        Initialize repository with database connection.
        
        Args:
            db: DatabaseConnection instance
        """
        self.db = db
    
    def _row_to_dict(self, row: sqlite3.Row) -> Dict[str, Any]:
        """
        Convert SQLite Row to dictionary.
        
        Args:
            row: SQLite Row object
        
        Returns:
            Dictionary representation of row
        """
        return dict(row)
    
    def _rows_to_dicts(self, rows: List[sqlite3.Row]) -> List[Dict[str, Any]]:
        """
        Convert list of SQLite Rows to list of dictionaries.
        
        Args:
            rows: List of SQLite Row objects
        
        Returns:
            List of dictionaries
        """
        return [self._row_to_dict(row) for row in rows]
    
    def execute_query(
        self,
        query: str,
        params: Optional[tuple | Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Execute SELECT query and return results as list of dicts.
        
        Args:
            query: SQL query string
            params: Query parameters (tuple or dict)
        
        Returns:
            List of dictionaries representing rows
        """
        with self.db.cursor() as cursor:
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            
            rows = cursor.fetchall()
            return self._rows_to_dicts(rows)
    
    def execute_one(
        self,
        query: str,
        params: Optional[tuple | Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Execute SELECT query and return single result.
        
        Args:
            query: SQL query string
            params: Query parameters (tuple or dict)
        
        Returns:
            Dictionary representing row, or None if not found
        """
        with self.db.cursor() as cursor:
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            
            row = cursor.fetchone()
            return self._row_to_dict(row) if row else None
    
    def execute_write(
        self,
        query: str,
        params: Optional[tuple | Dict[str, Any]] = None
    ) -> int:
        """
        Execute INSERT, UPDATE, or DELETE query.
        
        Args:
            query: SQL query string
            params: Query parameters (tuple or dict)
        
        Returns:
            Number of affected rows
        """
        with self.db.cursor() as cursor:
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            
            return cursor.rowcount
    
    def execute_many(
        self,
        query: str,
        params_list: List[tuple | Dict[str, Any]]
    ) -> int:
        """
        Execute query multiple times with different parameters.
        
        Args:
            query: SQL query string
            params_list: List of parameter tuples/dicts
        
        Returns:
            Total number of affected rows
        """
        with self.db.cursor() as cursor:
            cursor.executemany(query, params_list)
            return cursor.rowcount
    
    def get_last_insert_id(self) -> int:
        """
        Get ID of last inserted row.
        
        Returns:
            Last insert rowid
        """
        conn = self.db.get_connection()
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