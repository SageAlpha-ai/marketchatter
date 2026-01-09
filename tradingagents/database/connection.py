"""PostgreSQL database connection and initialization."""
import os
from pathlib import Path
from typing import Optional
import psycopg2
from psycopg2 import pool
from psycopg2.extensions import connection
from contextlib import contextmanager
import logging

logger = logging.getLogger(__name__)

# Connection pool (thread-safe)
_connection_pool: Optional[pool.ThreadedConnectionPool] = None


def init_database(config: dict = None):
    """
    Initialize database connection pool.
    
    This function is idempotent - safe to call multiple times.
    If the pool is already initialized, it will be reused.
    
    Args:
        config: Optional dict with database config (keys: db_host, db_port, db_name, db_user, db_password).
                If None, uses empty dict (environment variables take precedence).
                
    Environment Variables (standardized to POSTGRES_*):
        POSTGRES_HOST: Database host (default: localhost)
        POSTGRES_PORT: Database port (default: 5432)
        POSTGRES_DB: Database name (default: vfis_db)
        POSTGRES_USER: Database user (default: postgres)
        POSTGRES_PASSWORD: Database password (required)
    """
    global _connection_pool
    
    # If pool already initialized, return early (idempotent)
    if _connection_pool is not None:
        logger.debug("Database connection pool already initialized, reusing existing pool")
        return
    
    # Default to empty dict if config not provided
    if config is None:
        config = {}
    
    # Get database configuration from environment variables (POSTGRES_*) or config dict
    # Environment variables take precedence over config dict
    db_host = os.getenv('POSTGRES_HOST') or os.getenv('DB_HOST') or config.get('db_host', 'localhost')
    db_port = int(os.getenv('POSTGRES_PORT') or os.getenv('DB_PORT') or config.get('db_port', 5432))
    db_name = os.getenv('POSTGRES_DB') or os.getenv('DB_NAME') or config.get('db_name', 'vfis_db')
    db_user = os.getenv('POSTGRES_USER') or os.getenv('DB_USER') or config.get('db_user', 'postgres')
    db_password = os.getenv('POSTGRES_PASSWORD') or os.getenv('DB_PASSWORD') or config.get('db_password', '')
    
    # Validate required password (fail fast)
    if not db_password:
        raise ValueError(
            "Database password is required. Set POSTGRES_PASSWORD environment variable. "
            "For security, never use empty password."
        )
    
    db_config = {
        'host': db_host,
        'port': db_port,
        'database': db_name,
        'user': db_user,
        'password': db_password,
    }
    
    # Log configuration (without password) for debugging
    logger.info(
        f"Initializing database connection pool: "
        f"host={db_host}, port={db_port}, database={db_name}, user={db_user}"
    )
    
    try:
        # Create connection pool (min 1, max 10 connections)
        _connection_pool = pool.ThreadedConnectionPool(
            minconn=1,
            maxconn=10,
            **db_config
        )
        logger.info(f"Database connection pool initialized for {db_config['database']}")
        
        # Test connection
        test_conn = _connection_pool.getconn()
        try:
            with test_conn.cursor() as cur:
                cur.execute("SELECT version();")
                version = cur.fetchone()
                logger.info(f"Connected to PostgreSQL: {version[0]}")
            test_conn.commit()
        finally:
            _connection_pool.putconn(test_conn)
        
        # Create tables if they don't exist
        from .schema import create_tables
        create_tables()
        
    except Exception as e:
        logger.error(f"Failed to initialize database connection pool: {e}")
        raise


@contextmanager
def get_db_connection():
    """Get a database connection from the pool."""
    if _connection_pool is None:
        raise RuntimeError("Database connection pool not initialized. Call init_database() first.")
    
    conn = _connection_pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"Database transaction failed: {e}")
        raise
    finally:
        _connection_pool.putconn(conn)


def close_pool():
    """Close all database connections in the pool."""
    global _connection_pool
    if _connection_pool:
        _connection_pool.closeall()
        _connection_pool = None
        logger.info("Database connection pool closed")

