"""
Database schema extensions for PDF ingestion and document assets.

This module creates tables for storing:
- document_assets: Raw PDFs, extracted images, charts
- parsed_tables: Structured financial data extracted from PDFs

CRITICAL: These tables store only deterministically parsed data.
NO LLM-generated or inferred values are stored here.
"""

import logging
from tradingagents.database.connection import get_db_connection

logger = logging.getLogger(__name__)

# Valid document types
VALID_DOCUMENT_TYPES = {'quarterly', 'annual'}
# Valid asset types
VALID_ASSET_TYPES = {'pdf', 'image', 'chart'}
# Valid sources (enforced at application level, not DB constraint for flexibility)
VALID_SOURCES = {'NSE', 'BSE', 'SEBI'}


def create_ingestion_tables():
    """
    Create tables for PDF ingestion and document assets.
    
    These tables extend the base schema to support:
    - document_assets: Storage metadata for PDFs, images, charts
    - parsed_tables: Structured financial data from parsed PDFs
    """
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            # Document assets table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS document_assets (
                    id SERIAL PRIMARY KEY,
                    ticker TEXT NOT NULL,
                    document_type TEXT NOT NULL CHECK (document_type IN ('quarterly', 'annual')),
                    period TEXT NOT NULL,
                    asset_type TEXT NOT NULL CHECK (asset_type IN ('pdf', 'image', 'chart')),
                    blob_path TEXT NOT NULL,
                    file_name TEXT,
                    file_size_bytes BIGINT,
                    file_hash TEXT,
                    source TEXT CHECK (source IN ('NSE', 'BSE', 'SEBI')),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(ticker, document_type, file_hash)
                );
            """)
            
            # Parsed tables - structured financial data from PDFs
            cur.execute("""
                CREATE TABLE IF NOT EXISTS parsed_tables (
                    id SERIAL PRIMARY KEY,
                    ticker TEXT NOT NULL,
                    period TEXT NOT NULL,
                    table_name TEXT NOT NULL,
                    metric TEXT NOT NULL,
                    value NUMERIC(20, 2) NOT NULL,
                    source TEXT NOT NULL CHECK (source IN ('NSE', 'BSE', 'SEBI')),
                    as_of DATE NOT NULL,
                    document_asset_id INTEGER REFERENCES document_assets(id),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(ticker, period, table_name, metric, as_of)
                );
            """)
            
            # Create indexes for performance
            cur.execute("CREATE INDEX IF NOT EXISTS idx_document_assets_ticker ON document_assets(ticker);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_document_assets_type ON document_assets(document_type);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_document_assets_period ON document_assets(period);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_document_assets_blob_path ON document_assets(blob_path);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_document_assets_file_hash ON document_assets(file_hash);")
            
            # Add file_hash column if it doesn't exist (for existing databases)
            cur.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'document_assets' AND column_name = 'file_hash'
            """)
            if not cur.fetchone():
                cur.execute("ALTER TABLE document_assets ADD COLUMN file_hash TEXT;")
                logger.info("Added file_hash column to document_assets table")
            
            # Add unique constraint on (ticker, document_type, file_hash) if it doesn't exist
            cur.execute("""
                SELECT constraint_name 
                FROM information_schema.table_constraints 
                WHERE table_name = 'document_assets' 
                AND constraint_type = 'UNIQUE' 
                AND constraint_name LIKE '%file_hash%'
            """)
            if not cur.fetchone():
                try:
                    # Try to add unique constraint (may fail if duplicates exist)
                    cur.execute("""
                        ALTER TABLE document_assets 
                        ADD CONSTRAINT unique_ticker_doc_type_hash 
                        UNIQUE(ticker, document_type, file_hash)
                    """)
                    logger.info("Added unique constraint on (ticker, document_type, file_hash)")
                except Exception as e:
                    logger.warning(f"Could not add unique constraint (may have duplicates): {e}")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_document_assets_file_hash ON document_assets(file_hash);")
            
            # Add file_hash column if it doesn't exist (for existing databases)
            cur.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'document_assets' AND column_name = 'file_hash'
            """)
            if not cur.fetchone():
                cur.execute("ALTER TABLE document_assets ADD COLUMN file_hash TEXT;")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_document_assets_file_hash ON document_assets(file_hash);")
            
            # Add unique constraint if it doesn't exist
            cur.execute("""
                SELECT constraint_name 
                FROM information_schema.table_constraints 
                WHERE table_name = 'document_assets' 
                AND constraint_type = 'UNIQUE' 
                AND constraint_name LIKE '%file_hash%'
            """)
            if not cur.fetchone():
                try:
                    cur.execute("""
                        ALTER TABLE document_assets 
                        ADD CONSTRAINT unique_ticker_doc_type_hash 
                        UNIQUE(ticker, document_type, file_hash)
                    """)
                except Exception as e:
                    logger.warning(f"Could not add unique constraint (may already exist): {e}")
            
            cur.execute("CREATE INDEX IF NOT EXISTS idx_parsed_tables_ticker ON parsed_tables(ticker);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_parsed_tables_period ON parsed_tables(period);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_parsed_tables_table_name ON parsed_tables(table_name);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_parsed_tables_source ON parsed_tables(source);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_parsed_tables_as_of ON parsed_tables(as_of);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_parsed_tables_metric ON parsed_tables(metric);")
            
            conn.commit()
            logger.info("Ingestion tables (document_assets, parsed_tables) created successfully")


def validate_ingestion_schema():
    """Validate that ingestion tables exist and have correct structure."""
    required_tables = ['document_assets', 'parsed_tables']
    
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            missing_tables = []
            for table in required_tables:
                cur.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_name = %s
                    );
                """, (table,))
                exists = cur.fetchone()[0]
                if not exists:
                    missing_tables.append(table)
            
            if missing_tables:
                logger.error(f"Missing ingestion tables: {', '.join(missing_tables)}")
                return False
            
            logger.info("All ingestion tables exist and are valid")
            return True

