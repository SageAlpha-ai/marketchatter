"""
PostgreSQL database connection and initialization.

CLOUD-PRODUCTION READY:
- No localhost assumptions - fails fast if POSTGRES_HOST not set
- SSL support for cloud databases (Render, Supabase, Neon)
- Set DATABASE_SSL=true for SSL-required environments
"""
import os
from typing import Optional
import psycopg2
from psycopg2 import pool
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
    
    CLOUD-PRODUCTION NOTES:
    - POSTGRES_HOST is REQUIRED (no localhost default)
    - Set DATABASE_SSL=true for SSL-required cloud databases
    - All credentials must come from environment variables
    
    Environment Variables (REQUIRED):
        POSTGRES_HOST: Database host (REQUIRED - no default)
        POSTGRES_PORT: Database port (default: 5432)
        POSTGRES_DB: Database name (REQUIRED - no default)
        POSTGRES_USER: Database user (REQUIRED - no default)
        POSTGRES_PASSWORD: Database password (REQUIRED)
        DATABASE_SSL: Set to 'true' for SSL connections (default: false)
    """
    global _connection_pool
    
    # If pool already initialized, return early (idempotent)
    if _connection_pool is not None:
        logger.debug("Database connection pool already initialized, reusing existing pool")
        return
    
    # Default to empty dict if config not provided
    if config is None:
        config = {}
    
    # Get database configuration from environment variables
    # NO LOCALHOST DEFAULT - must be explicitly set for cloud deployment
    db_host = os.getenv('POSTGRES_HOST') or os.getenv('DB_HOST') or config.get('db_host')
    db_port = int(os.getenv('POSTGRES_PORT') or os.getenv('DB_PORT') or config.get('db_port', 5432))
    db_name = os.getenv('POSTGRES_DB') or os.getenv('DB_NAME') or config.get('db_name')
    db_user = os.getenv('POSTGRES_USER') or os.getenv('DB_USER') or config.get('db_user')
    db_password = os.getenv('POSTGRES_PASSWORD') or os.getenv('DB_PASSWORD') or config.get('db_password', '')
    
    # SSL configuration for cloud databases (Render, Supabase, Neon, etc.)
    ssl_enabled = os.getenv('DATABASE_SSL', 'false').lower() in ('true', '1', 'yes')
    
    # FAIL FAST: Validate all required parameters
    missing = []
    if not db_host:
        missing.append('POSTGRES_HOST')
    if not db_name:
        missing.append('POSTGRES_DB')
    if not db_user:
        missing.append('POSTGRES_USER')
    if not db_password:
        missing.append('POSTGRES_PASSWORD')
    
    if missing:
        error_msg = (
            f"FATAL: Missing required database environment variables: {', '.join(missing)}. "
            f"Set these in your environment (not .env for production)."
        )
        logger.critical(f"[DB] {error_msg}")
        raise ValueError(error_msg)
    
    # Build connection config
    db_config = {
        'host': db_host,
        'port': db_port,
        'database': db_name,
        'user': db_user,
        'password': db_password,
    }
    
    # Add SSL mode for cloud databases
    if ssl_enabled:
        db_config['sslmode'] = 'require'
        logger.info(f"[DB] SSL mode enabled (sslmode=require)")
    
    # Log configuration (without password) for debugging
    logger.info(
        f"[DB] Initializing connection pool: "
        f"host={db_host}, port={db_port}, database={db_name}, user={db_user}, ssl={ssl_enabled}"
    )
    
    try:
        # Create connection pool (min 1, max 10 connections)
        _connection_pool = pool.ThreadedConnectionPool(
            minconn=1,
            maxconn=10,
            **db_config
        )
        logger.info(f"[DB] Connection pool initialized for {db_name}@{db_host}")
        
        # Test connection
        test_conn = _connection_pool.getconn()
        try:
            with test_conn.cursor() as cur:
                cur.execute("SELECT version();")
                version = cur.fetchone()
                logger.info(f"[DB] Connected to PostgreSQL: {version[0][:60]}...")
            test_conn.commit()
        finally:
            _connection_pool.putconn(test_conn)
        
        # Create tables if they don't exist
        from .schema import create_tables
        create_tables()
        
    except psycopg2.OperationalError as e:
        error_msg = f"Database connection failed: {e}"
        logger.critical(f"[DB] FATAL: {error_msg}")
        logger.critical(f"[DB] Check: host={db_host}, port={db_port}, ssl={ssl_enabled}")
        raise RuntimeError(error_msg) from e
    except Exception as e:
        logger.critical(f"[DB] FATAL: Failed to initialize database: {e}")
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

