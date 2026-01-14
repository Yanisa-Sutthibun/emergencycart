# Turso Database Wrapper for libsql-client
# This wrapper makes libsql-client work like sqlite3

import libsql_client
import pandas as pd
import asyncio
import nest_asyncio
from typing import Any, List, Tuple, Optional

# Enable nested event loops (required for Streamlit)
nest_asyncio.apply()

def _validate_turso_config(url: str, auth_token: str) -> tuple[str, str]:
    """Validate and sanitize Turso connection parameters."""
    url = (url or "").strip()
    auth_token = (auth_token or "").strip()

    if url.lower() in ("", ".", "none", "null"):
        raise ValueError(
            "Turso URL is missing (got empty/'.'). "
            "Set EMERGENCY_CART_URL / EQUIPMENT_URL in Streamlit secrets or environment variables."
        )
    if auth_token.lower() in ("", "none", "null"):
        raise ValueError(
            "Turso auth token is missing. "
            "Set EMERGENCY_CART_TOKEN / EQUIPMENT_TOKEN in Streamlit secrets or environment variables."
        )
    return url, auth_token

def normalize_turso_url(url: str) -> str:
    """Convert libsql:// URL to proper format for libsql-client"""
    url = (url or '').strip()
    if url.startswith('libsql://'):
        # Remove libsql:// prefix and add https://
        return 'https://' + url.replace('libsql://', '')
    return url

class TursoConnection:
    """Wrapper class to make libsql-client behave like sqlite3.Connection"""
    
    def __init__(self, url: str, auth_token: str):
        # Validate config (avoid libsql URL_UNDEFINED)
        url, auth_token = _validate_turso_config(url, auth_token)

        # Normalize URL
        normalized_url = normalize_turso_url(url)
        
        # Get or create event loop
        try:
            self.loop = asyncio.get_event_loop()
        except RuntimeError:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
        
        # Create client synchronously using the event loop
        self.client = libsql_client.create_client_sync(
            url=normalized_url,
            auth_token=auth_token
        )
        self.url = url
        self.auth_token = auth_token
        self._closed = False
    
    def execute(self, sql: str, parameters: tuple = None):
        """Execute a single SQL statement"""
        # Check if connection is closed
        if self._closed:
            raise Exception("Connection is closed. Create a new connection.")
        
        try:
            if parameters:
                result = self.client.execute(sql, parameters)
            else:
                result = self.client.execute(sql)
            return TursoCursor(result)
        except Exception as e:
            print(f"Error executing SQL: {sql}")
            print(f"Error: {e}")
            raise
    
    def executemany(self, sql: str, parameters_list: List[tuple]):
        """Execute SQL with multiple parameter sets"""
        results = []
        for params in parameters_list:
            result = self.execute(sql, params)
            results.append(result)
        return results
    
    def commit(self):
        """Commit changes (libsql-client auto-commits, so this is a no-op)"""
        pass
    
    def close(self):
        """Close connection"""
        if not self._closed:
            try:
                self.client.close()
            except:
                pass
            self._closed = True
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        # Don't close on exit - let it be reused
        # self.close()
        return False


class TursoCursor:
    """Wrapper class to make libsql-client results behave like sqlite3.Cursor"""
    
    def __init__(self, result):
        self.result = result
        self._rows = None
        self._columns = None
        
        # Parse result
        if hasattr(result, 'rows'):
            self._rows = result.rows
        if hasattr(result, 'columns'):
            self._columns = result.columns
    
    def fetchall(self) -> List[Tuple]:
        """Fetch all results"""
        if self._rows is None:
            return []
        return [tuple(row) for row in self._rows]
    
    def fetchone(self) -> Optional[Tuple]:
        """Fetch one result"""
        if self._rows is None or len(self._rows) == 0:
            return None
        return tuple(self._rows[0])
    
    @property
    def description(self):
        """Column descriptions"""
        if self._columns is None:
            return None
        return [(col, None, None, None, None, None, None) for col in self._columns]


def turso_read_sql(sql: str, conn: TursoConnection, params: tuple = None) -> pd.DataFrame:
    """
    Execute SQL and return results as pandas DataFrame
    Replacement for pd.read_sql() which doesn't work with libsql-client
    """
    cursor = conn.execute(sql, params)
    
    # Get column names
    columns = cursor._columns if cursor._columns else []
    
    # Get rows
    rows = cursor.fetchall()
    
    # Create DataFrame
    if not rows:
        return pd.DataFrame(columns=columns)
    
    df = pd.DataFrame(rows, columns=columns)
    return df


def turso_to_sql(df: pd.DataFrame, table_name: str, conn: TursoConnection, 
                 if_exists: str = 'replace') -> None:
    """
    Write DataFrame to Turso database
    Replacement for df.to_sql() which doesn't work with libsql-client
    """
    if df.empty:
        return
    
    # Handle if_exists
    if if_exists == 'replace':
        try:
            conn.execute(f"DROP TABLE IF EXISTS {table_name}")
        except:
            pass
    
    # Get column names and types
    columns = df.columns.tolist()
    
    # Infer SQL types from pandas dtypes
    type_mapping = {
        'int64': 'INTEGER',
        'float64': 'REAL',
        'object': 'TEXT',
        'bool': 'INTEGER',
        'datetime64[ns]': 'TEXT'
    }
    
    col_defs = []
    for col in columns:
        dtype = str(df[col].dtype)
        sql_type = type_mapping.get(dtype, 'TEXT')
        col_defs.append(f"{col} {sql_type}")
    
    # Create table
    create_sql = f"CREATE TABLE IF NOT EXISTS {table_name} ({', '.join(col_defs)})"
    conn.execute(create_sql)
    
    # Insert data
    placeholders = ', '.join(['?' for _ in columns])
    insert_sql = f"INSERT INTO {table_name} ({', '.join(columns)}) VALUES ({placeholders})"
    
    for _, row in df.iterrows():
        values = tuple(row[col] for col in columns)
        conn.execute(insert_sql, values)


# Example usage functions
def create_turso_connection(url: str, auth_token: str) -> TursoConnection:
    """Create a Turso connection that works like sqlite3.Connection"""
    return TursoConnection(url, auth_token)


if __name__ == "__main__":
    # Test the wrapper
    print("Turso wrapper loaded successfully!")
    print("Use: conn = create_turso_connection(url, token)")