"""Database schema for Verified Financial Data AI System."""
import logging
from datetime import datetime
from typing import Optional
from .connection import get_db_connection

logger = logging.getLogger(__name__)

# Valid data sources as per requirements
VALID_SOURCES = {'NSE', 'BSE', 'SEBI'}

# Valid chatter sources
VALID_CHATTER_SOURCES = {'alpha_vantage', 'reddit', 'twitter', 'stocktwits', 'news', 'rss'}


def create_tables():
    """Create all database tables if they don't exist."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            # Companies table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS companies (
                    id SERIAL PRIMARY KEY,
                    company_name VARCHAR(255) NOT NULL,
                    ticker_symbol VARCHAR(50) NOT NULL UNIQUE,
                    legal_name VARCHAR(255),
                    exchange VARCHAR(50),
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            
            # Financial data sources table (tracks where data came from)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS data_sources (
                    id SERIAL PRIMARY KEY,
                    company_id INTEGER REFERENCES companies(id),
                    source_name VARCHAR(50) NOT NULL CHECK (source_name IN ('NSE', 'BSE', 'SEBI')),
                    source_url TEXT,
                    last_updated TIMESTAMP,
                    data_period_start DATE,
                    data_period_end DATE,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(company_id, source_name)
                );
            """)
            
            # Annual reports table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS annual_reports (
                    id SERIAL PRIMARY KEY,
                    company_id INTEGER REFERENCES companies(id),
                    fiscal_year INTEGER NOT NULL,
                    report_date DATE NOT NULL,
                    data_source_id INTEGER REFERENCES data_sources(id),
                    filing_date DATE,
                    document_url TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(company_id, fiscal_year)
                );
            """)
            
            # Quarterly reports table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS quarterly_reports (
                    id SERIAL PRIMARY KEY,
                    company_id INTEGER REFERENCES companies(id),
                    fiscal_year INTEGER NOT NULL,
                    quarter INTEGER NOT NULL CHECK (quarter IN (1, 2, 3, 4)),
                    report_date DATE NOT NULL,
                    data_source_id INTEGER REFERENCES data_sources(id),
                    filing_date DATE,
                    document_url TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(company_id, fiscal_year, quarter)
                );
            """)
            
            # Balance sheet data
            cur.execute("""
                CREATE TABLE IF NOT EXISTS balance_sheet (
                    id SERIAL PRIMARY KEY,
                    annual_report_id INTEGER REFERENCES annual_reports(id),
                    quarterly_report_id INTEGER REFERENCES quarterly_reports(id),
                    report_type VARCHAR(20) NOT NULL CHECK (report_type IN ('annual', 'quarterly')),
                    metric_name VARCHAR(255) NOT NULL,
                    metric_value NUMERIC(20, 2) NOT NULL,
                    currency VARCHAR(10) DEFAULT 'INR',
                    as_of_date DATE NOT NULL,
                    data_source_id INTEGER REFERENCES data_sources(id),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    CHECK ((annual_report_id IS NOT NULL AND quarterly_report_id IS NULL) OR 
                           (annual_report_id IS NULL AND quarterly_report_id IS NOT NULL))
                );
            """)
            
            # Income statement data
            cur.execute("""
                CREATE TABLE IF NOT EXISTS income_statement (
                    id SERIAL PRIMARY KEY,
                    annual_report_id INTEGER REFERENCES annual_reports(id),
                    quarterly_report_id INTEGER REFERENCES quarterly_reports(id),
                    report_type VARCHAR(20) NOT NULL CHECK (report_type IN ('annual', 'quarterly')),
                    metric_name VARCHAR(255) NOT NULL,
                    metric_value NUMERIC(20, 2) NOT NULL,
                    currency VARCHAR(10) DEFAULT 'INR',
                    as_of_date DATE NOT NULL,
                    data_source_id INTEGER REFERENCES data_sources(id),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    CHECK ((annual_report_id IS NOT NULL AND quarterly_report_id IS NULL) OR 
                           (annual_report_id IS NULL AND quarterly_report_id IS NOT NULL))
                );
            """)
            
            # Cash flow statement data
            cur.execute("""
                CREATE TABLE IF NOT EXISTS cashflow_statement (
                    id SERIAL PRIMARY KEY,
                    annual_report_id INTEGER REFERENCES annual_reports(id),
                    quarterly_report_id INTEGER REFERENCES quarterly_reports(id),
                    report_type VARCHAR(20) NOT NULL CHECK (report_type IN ('annual', 'quarterly')),
                    metric_name VARCHAR(255) NOT NULL,
                    metric_value NUMERIC(20, 2) NOT NULL,
                    currency VARCHAR(10) DEFAULT 'INR',
                    as_of_date DATE NOT NULL,
                    data_source_id INTEGER REFERENCES data_sources(id),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    CHECK ((annual_report_id IS NOT NULL AND quarterly_report_id IS NULL) OR 
                           (annual_report_id IS NULL AND quarterly_report_id IS NOT NULL))
                );
            """)
            
            # Audit log table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS audit_log (
                    id SERIAL PRIMARY KEY,
                    event_type VARCHAR(50) NOT NULL,
                    entity_type VARCHAR(50),
                    entity_id INTEGER,
                    action VARCHAR(100) NOT NULL,
                    user_id VARCHAR(100),
                    request_id VARCHAR(100),
                    details JSONB,
                    ip_address VARCHAR(50),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            
            # Market chatter table - canonical schema for multi-source ingestion
            cur.execute("""
                CREATE TABLE IF NOT EXISTS market_chatter (
                    id SERIAL PRIMARY KEY,
                    ticker TEXT NOT NULL,
                    company_name TEXT,
                    source TEXT NOT NULL,
                    source_type TEXT NOT NULL DEFAULT 'news',
                    title TEXT,
                    content TEXT NOT NULL,
                    url TEXT,
                    sentiment_score NUMERIC(4,3),
                    sentiment_label TEXT,
                    confidence NUMERIC(4,3),
                    published_at TIMESTAMP WITH TIME ZONE,
                    ingested_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    raw_payload JSONB,
                    CONSTRAINT unique_chatter_per_source UNIQUE (ticker, source, url)
                );
            """)
            
            # Create indexes for performance
            cur.execute("CREATE INDEX IF NOT EXISTS idx_companies_ticker ON companies(ticker_symbol);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_data_sources_company ON data_sources(company_id);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_annual_reports_company_year ON annual_reports(company_id, fiscal_year);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_quarterly_reports_company_year_quarter ON quarterly_reports(company_id, fiscal_year, quarter);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_balance_sheet_annual ON balance_sheet(annual_report_id);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_balance_sheet_quarterly ON balance_sheet(quarterly_report_id);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_income_statement_annual ON income_statement(annual_report_id);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_income_statement_quarterly ON income_statement(quarterly_report_id);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_cashflow_statement_annual ON cashflow_statement(annual_report_id);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_cashflow_statement_quarterly ON cashflow_statement(quarterly_report_id);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_audit_log_created_at ON audit_log(created_at);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_audit_log_event_type ON audit_log(event_type);")
            
            # Market chatter indexes
            cur.execute("CREATE INDEX IF NOT EXISTS idx_market_chatter_ticker ON market_chatter(ticker);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_market_chatter_source ON market_chatter(source);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_market_chatter_published_at ON market_chatter(published_at DESC);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_market_chatter_ticker_published ON market_chatter(ticker, published_at DESC);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_market_chatter_source_type ON market_chatter(source_type);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_market_chatter_sentiment_label ON market_chatter(sentiment_label);")
            
            conn.commit()
            logger.info("Database tables created successfully (including market_chatter)")


def validate_source(source: str) -> bool:
    """Validate that the source is one of the allowed sources."""
    return source in VALID_SOURCES


def get_latest_as_of_date(company_id: int, report_type: str = 'quarterly') -> Optional[datetime]:
    """Get the latest as-of date for a company's reports."""
    table = 'quarterly_reports' if report_type == 'quarterly' else 'annual_reports'
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT MAX(report_date) 
                FROM {table} 
                WHERE company_id = %s
            """, (company_id,))
            result = cur.fetchone()
            return result[0] if result and result[0] else None

