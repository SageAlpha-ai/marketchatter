"""Database module for Verified Financial Data AI System."""
from .connection import get_db_connection, init_database
from .schema import create_tables
from .chatter_dal import (
    get_recent_chatter,
    get_chatter_metadata,
    get_chatter_summary,
    insert_chatter,
    bulk_insert_chatter,
    ensure_market_chatter_table
)

__all__ = [
    'get_db_connection',
    'init_database',
    'create_tables',
    # Market chatter DAL
    'get_recent_chatter',
    'get_chatter_metadata',
    'get_chatter_summary',
    'insert_chatter',
    'bulk_insert_chatter',
    'ensure_market_chatter_table'
]

