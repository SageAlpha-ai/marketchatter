"""
Database Inspector Utility

Read-only utility for inspecting database tables.
No side effects. Safe for diagnostic use.

NOTE: Environment variables must be loaded by scripts.init_env before using this module.
All entrypoints must import scripts.init_env as their FIRST import line.
"""

import os
import psycopg2
from psycopg2 import sql


def count_rows(table_name: str) -> int:
    """
    Count rows in a database table.
    
    Args:
        table_name: Name of the table to count rows in
        
    Returns:
        Integer count of rows in the table
        
    Raises:
        ValueError: If required environment variables are missing
        psycopg2.Error: If database connection or query fails
        Exception: If table does not exist or other database error occurs
    """
    # Load database settings from environment variables
    # CLOUD-PRODUCTION: No localhost default - must be explicitly set
    db_name = os.getenv('POSTGRES_DB')
    db_user = os.getenv('POSTGRES_USER')
    db_password = os.getenv('POSTGRES_PASSWORD')
    db_host = os.getenv('POSTGRES_HOST')  # REQUIRED - no default
    db_port = os.getenv('POSTGRES_PORT', '5432')
    db_ssl = os.getenv('DATABASE_SSL', 'false').lower() in ('true', '1', 'yes')
    
    # Validate required environment variables
    if not db_host:
        raise ValueError("POSTGRES_HOST environment variable is required")
    if not db_name:
        raise ValueError("POSTGRES_DB environment variable is required")
    if not db_user:
        raise ValueError("POSTGRES_USER environment variable is required")
    if not db_password:
        raise ValueError("POSTGRES_PASSWORD environment variable is required")
    
    conn = None
    cur = None
    
    try:
        # Build connection parameters
        conn_params = {
            'dbname': db_name,
            'user': db_user,
            'password': db_password,
            'host': db_host,
            'port': db_port
        }
        
        # Add SSL mode for cloud databases
        if db_ssl:
            conn_params['sslmode'] = 'require'
        
        # Open a new psycopg2 connection
        conn = psycopg2.connect(**conn_params)
        
        # Create cursor
        cur = conn.cursor()
        
        # Execute COUNT query using parameterized query to prevent SQL injection
        # Note: table names cannot be parameterized in psycopg2, so we use sql.Identifier
        query = sql.SQL("SELECT COUNT(*) FROM {}").format(
            sql.Identifier(table_name)
        )
        
        cur.execute(query)
        
        # Fetch the result
        result = cur.fetchone()
        count = result[0] if result else 0
        
        return int(count)
        
    except psycopg2.errors.UndefinedTable:
        # Table does not exist
        raise ValueError(f"Table '{table_name}' does not exist in the database")
    except psycopg2.Error as e:
        # Other database errors
        raise Exception(f"Database error while counting rows in '{table_name}': {e}")
    except Exception as e:
        # Any other unexpected errors
        raise Exception(f"Error counting rows in '{table_name}': {e}")
    finally:
        # Close cursor and connection safely
        if cur:
            cur.close()
        if conn:
            conn.close()

