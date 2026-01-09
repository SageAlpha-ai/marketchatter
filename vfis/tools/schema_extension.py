"""
Schema extension for VFIS - adds news and technical_indicators tables.

This extends the base schema in tradingagents.database.schema with additional
tables needed for VFIS: news and technical_indicators.
"""

import logging
from tradingagents.database.connection import get_db_connection

logger = logging.getLogger(__name__)


def create_vfis_tables():
    """
    Create additional tables for VFIS: news and technical_indicators.
    
    These tables extend the base schema to support news articles and
    technical indicators while maintaining the same source validation
    and audit logging principles.
    """
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            # News table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS news (
                    id SERIAL PRIMARY KEY,
                    company_id INTEGER REFERENCES companies(id),
                    headline VARCHAR(500) NOT NULL,
                    content TEXT,
                    source_name VARCHAR(50) NOT NULL,
                    published_at TIMESTAMP NOT NULL,
                    url TEXT,
                    sentiment_score NUMERIC(5, 3),
                    sentiment_label VARCHAR(20) CHECK (sentiment_label IN ('positive', 'neutral', 'negative')),
                    confidence_score NUMERIC(5, 3),
                    data_source_id INTEGER REFERENCES data_sources(id),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            
            # Add sentiment columns if they don't exist (for existing databases)
            cur.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'news' AND column_name = 'sentiment_score'
            """)
            if not cur.fetchone():
                cur.execute("ALTER TABLE news ADD COLUMN sentiment_score NUMERIC(5, 3);")
                cur.execute("ALTER TABLE news ADD COLUMN sentiment_label VARCHAR(20) CHECK (sentiment_label IN ('positive', 'neutral', 'negative'));")
                cur.execute("ALTER TABLE news ADD COLUMN confidence_score NUMERIC(5, 3);")
            
            # Technical indicators table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS technical_indicators (
                    id SERIAL PRIMARY KEY,
                    company_id INTEGER REFERENCES companies(id),
                    indicator_name VARCHAR(100) NOT NULL,
                    indicator_value NUMERIC(20, 6),
                    calculated_date DATE NOT NULL,
                    source VARCHAR(50) DEFAULT 'computed',
                    data_source_id INTEGER REFERENCES data_sources(id),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(company_id, indicator_name, calculated_date)
                );
            """)
            
            # Add source column if it doesn't exist (for existing databases)
            cur.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'technical_indicators' AND column_name = 'source'
            """)
            if not cur.fetchone():
                cur.execute("ALTER TABLE technical_indicators ADD COLUMN source VARCHAR(50) DEFAULT 'computed';")
            
            # Create indexes for performance
            cur.execute("CREATE INDEX IF NOT EXISTS idx_news_company_id ON news(company_id);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_news_published_at ON news(published_at DESC);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_news_source ON news(source_name);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_technical_indicators_company_id ON technical_indicators(company_id);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_technical_indicators_name ON technical_indicators(indicator_name);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_technical_indicators_date ON technical_indicators(calculated_date DESC);")
            
            conn.commit()
            logger.info("VFIS extension tables (news, technical_indicators) created successfully")


def create_all_vfis_tables():
    """
    Create all VFIS extension tables including ingestion tables.
    
    This function creates:
    - news and technical_indicators (from original schema_extension)
    - document_assets and parsed_tables (from schema_ingestion)
    - Updates news table with sentiment columns
    """
    # Create news and technical_indicators tables
    create_vfis_tables()
    
    # Create ingestion tables (document_assets, parsed_tables)
    # Import here to avoid circular dependencies
    try:
        from vfis.tools.schema_ingestion import create_ingestion_tables
        create_ingestion_tables()
    except ImportError:
        # Fallback if import fails
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from vfis.tools.schema_ingestion import create_ingestion_tables
        create_ingestion_tables()
    
    # Add sentiment columns to news table
    try:
        from vfis.tools.schema_sentiment_update import add_sentiment_columns_to_news
        add_sentiment_columns_to_news()
    except ImportError:
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from vfis.tools.schema_sentiment_update import add_sentiment_columns_to_news
        add_sentiment_columns_to_news()


def update_audit_log_schema():
    """
    Enhance audit_log table to support VFIS-specific fields if needed.
    
    The base audit_log table should already have the necessary fields,
    but this function can be used to add VFIS-specific enhancements.
    """
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            # Check if agent_name column exists, add if not
            cur.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'audit_log' AND column_name = 'agent_name'
            """)
            if not cur.fetchone():
                cur.execute("ALTER TABLE audit_log ADD COLUMN agent_name VARCHAR(100);")
            
            # Check if tables_accessed column exists, add if not
            cur.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'audit_log' AND column_name = 'tables_accessed'
            """)
            if not cur.fetchone():
                cur.execute("ALTER TABLE audit_log ADD COLUMN tables_accessed TEXT[];")
            
            conn.commit()
            logger.info("Audit log schema updated for VFIS")

