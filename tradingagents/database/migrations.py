"""
Database migrations runner for VFIS.

This module provides idempotent migrations that can safely run multiple times.
Migrations are applied BEFORE table validation in bootstrap to handle
legacy database schemas.

CRITICAL: All migrations must be idempotent - safe to run multiple times.
"""

import logging
from typing import Tuple, List

from .connection import get_db_connection

logger = logging.getLogger(__name__)


def run_migrations() -> Tuple[bool, List[str]]:
    """
    Run all database migrations in order.
    
    Migrations are idempotent - safe to run multiple times.
    Each migration checks if it needs to apply changes before making them.
    
    Returns:
        Tuple of (success, errors)
    """
    errors = []
    
    logger.info("[MIGRATIONS] Running database migrations...")
    
    try:
        # Migration 1: Ensure market_chatter has source_id column
        success, error = _migrate_market_chatter_source_id()
        if not success:
            errors.append(error)
            return False, errors
        
        logger.info("[MIGRATIONS] All migrations completed successfully")
        return True, errors
        
    except Exception as e:
        error_msg = f"Migration failed: {e}"
        logger.error(f"[MIGRATIONS] {error_msg}")
        errors.append(error_msg)
        return False, errors


def _migrate_market_chatter_source_id() -> Tuple[bool, str]:
    """
    Migration: Add source_id column to market_chatter if missing.
    
    This handles legacy databases that have market_chatter without source_id.
    
    Steps:
    1. Check if table exists (skip if not - will be created later)
    2. Check if source_id column exists
    3. If missing: add column, backfill data, add constraint
    4. If exists: verify constraint exists
    
    Returns:
        Tuple of (success, error_message)
    """
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Step 1: Check if market_chatter table exists
                cur.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_schema = 'public' 
                        AND table_name = 'market_chatter'
                    );
                """)
                table_exists = cur.fetchone()[0]
                
                if not table_exists:
                    logger.info("[MIGRATIONS] market_chatter table does not exist yet - skipping migration")
                    return True, ""
                
                # Step 2: Check if source_id column exists
                cur.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.columns 
                        WHERE table_schema = 'public'
                        AND table_name = 'market_chatter' 
                        AND column_name = 'source_id'
                    );
                """)
                source_id_exists = cur.fetchone()[0]
                
                if not source_id_exists:
                    logger.info("[MIGRATIONS] Adding source_id column to market_chatter...")
                    
                    # Step 3a: Add source_id column (nullable initially)
                    cur.execute("""
                        ALTER TABLE market_chatter 
                        ADD COLUMN source_id TEXT;
                    """)
                    logger.info("[MIGRATIONS] source_id column added")
                    
                    # Step 3b: Backfill source_id for existing rows
                    # Use deterministic hash: MD5 of (url OR ticker:source:content_prefix)
                    cur.execute("""
                        UPDATE market_chatter 
                        SET source_id = MD5(
                            COALESCE(
                                url,
                                ticker || ':' || source || ':' || COALESCE(LEFT(content, 100), '')
                            )
                        )
                        WHERE source_id IS NULL;
                    """)
                    backfilled = cur.rowcount
                    logger.info(f"[MIGRATIONS] Backfilled source_id for {backfilled} existing rows")
                    
                    # Step 3c: Set default for future NULLs (in case INSERT misses it)
                    cur.execute("""
                        UPDATE market_chatter 
                        SET source_id = MD5(RANDOM()::TEXT || CLOCK_TIMESTAMP()::TEXT)
                        WHERE source_id IS NULL;
                    """)
                    
                    # Step 3d: Make source_id NOT NULL
                    cur.execute("""
                        ALTER TABLE market_chatter 
                        ALTER COLUMN source_id SET NOT NULL;
                    """)
                    logger.info("[MIGRATIONS] source_id column set to NOT NULL")
                else:
                    logger.info("[MIGRATIONS] source_id column already exists")
                
                # Step 4: Check if summary column exists (add if missing)
                cur.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.columns 
                        WHERE table_schema = 'public'
                        AND table_name = 'market_chatter' 
                        AND column_name = 'summary'
                    );
                """)
                summary_exists = cur.fetchone()[0]
                
                if not summary_exists:
                    logger.info("[MIGRATIONS] Adding summary column to market_chatter...")
                    cur.execute("""
                        ALTER TABLE market_chatter 
                        ADD COLUMN summary TEXT;
                    """)
                    # Copy content to summary for existing rows
                    cur.execute("""
                        UPDATE market_chatter 
                        SET summary = content 
                        WHERE summary IS NULL AND content IS NOT NULL;
                    """)
                    logger.info("[MIGRATIONS] summary column added and backfilled")
                
                # Step 5: Ensure unique constraint on (source, source_id) exists
                cur.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.table_constraints 
                        WHERE table_schema = 'public'
                        AND table_name = 'market_chatter' 
                        AND constraint_name = 'unique_source_source_id'
                    );
                """)
                constraint_exists = cur.fetchone()[0]
                
                if not constraint_exists:
                    logger.info("[MIGRATIONS] Adding UNIQUE constraint on (source, source_id)...")
                    
                    # First, handle potential duplicates by keeping only the first (lowest id)
                    cur.execute("""
                        DELETE FROM market_chatter a
                        USING market_chatter b
                        WHERE a.id > b.id 
                        AND a.source = b.source 
                        AND a.source_id = b.source_id;
                    """)
                    deleted = cur.rowcount
                    if deleted > 0:
                        logger.info(f"[MIGRATIONS] Removed {deleted} duplicate rows before adding constraint")
                    
                    # Now add the constraint
                    cur.execute("""
                        ALTER TABLE market_chatter 
                        ADD CONSTRAINT unique_source_source_id 
                        UNIQUE (source, source_id);
                    """)
                    logger.info("[MIGRATIONS] UNIQUE constraint added")
                else:
                    logger.info("[MIGRATIONS] UNIQUE constraint already exists")
                
                # Step 6: Ensure index exists for (source, source_id)
                cur.execute("""
                    SELECT EXISTS (
                        SELECT FROM pg_indexes 
                        WHERE tablename = 'market_chatter' 
                        AND indexname = 'idx_mc_source_source_id'
                    );
                """)
                index_exists = cur.fetchone()[0]
                
                if not index_exists:
                    cur.execute("""
                        CREATE INDEX IF NOT EXISTS idx_mc_source_source_id 
                        ON market_chatter(source, source_id);
                    """)
                    logger.info("[MIGRATIONS] Index idx_mc_source_source_id created")
                
                conn.commit()
                logger.info("[MIGRATIONS] market_chatter migration completed successfully")
                return True, ""
                
    except Exception as e:
        error_msg = f"market_chatter migration failed: {e}"
        logger.error(f"[MIGRATIONS] {error_msg}")
        return False, error_msg


def check_migration_status() -> dict:
    """
    Check the current migration status of the database.
    
    Returns:
        Dictionary with migration status information
    """
    status = {
        "market_chatter_exists": False,
        "source_id_exists": False,
        "summary_exists": False,
        "unique_constraint_exists": False,
        "row_count": 0,
        "migrations_needed": []
    }
    
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Check table exists
                cur.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_schema = 'public' 
                        AND table_name = 'market_chatter'
                    );
                """)
                status["market_chatter_exists"] = cur.fetchone()[0]
                
                if status["market_chatter_exists"]:
                    # Check columns
                    cur.execute("""
                        SELECT column_name FROM information_schema.columns 
                        WHERE table_schema = 'public' AND table_name = 'market_chatter';
                    """)
                    columns = [row[0] for row in cur.fetchall()]
                    status["source_id_exists"] = "source_id" in columns
                    status["summary_exists"] = "summary" in columns
                    
                    # Check constraint
                    cur.execute("""
                        SELECT EXISTS (
                            SELECT FROM information_schema.table_constraints 
                            WHERE table_name = 'market_chatter' 
                            AND constraint_name = 'unique_source_source_id'
                        );
                    """)
                    status["unique_constraint_exists"] = cur.fetchone()[0]
                    
                    # Count rows
                    cur.execute("SELECT COUNT(*) FROM market_chatter;")
                    status["row_count"] = cur.fetchone()[0]
                    
                    # Determine what migrations are needed
                    if not status["source_id_exists"]:
                        status["migrations_needed"].append("add_source_id")
                    if not status["summary_exists"]:
                        status["migrations_needed"].append("add_summary")
                    if not status["unique_constraint_exists"]:
                        status["migrations_needed"].append("add_unique_constraint")
                        
    except Exception as e:
        status["error"] = str(e)
        logger.error(f"[MIGRATIONS] Error checking status: {e}")
    
    return status

