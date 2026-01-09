"""
Initialize the PostgreSQL database for Verified Financial Intelligence System (VFIS).

This script:
1. Creates all required tables (companies, financial statements, news, technical_indicators)
2. Sets up initial company entry (configurable via env var or argument)
3. Configures data sources (NSE, BSE, SEBI)
4. Creates indexes for performance
5. Validates the schema

Windows-compatible: Uses pathlib for all file operations.

USAGE:
    # Use SEED_TICKER env var
    SEED_TICKER=AAPL python -m vfis.scripts.init_database
    
    # Or run without seeding
    python -m vfis.scripts.init_database --no-seed
"""
import os
import sys
import argparse
from pathlib import Path

# Add parent directories to path for imports
_project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_project_root))

# Use bootstrap for proper initialization
from vfis.bootstrap import bootstrap

from tradingagents.database import init_database, create_tables
from tradingagents.default_config import DEFAULT_CONFIG
from vfis.tools.schema_extension import create_all_vfis_tables, update_audit_log_schema


def create_company(
    ticker: str,
    company_name: str,
    legal_name: str,
    exchange: str = 'NSE'
):
    """
    Create company entry in the database.
    
    Args:
        ticker: Company ticker symbol (dynamically provided, not hardcoded)
        company_name: Company display name
        legal_name: Legal/official company name
        exchange: Stock exchange (default: NSE)
    """
    from tradingagents.database.connection import get_db_connection
    
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            # Insert company
            cur.execute("""
                INSERT INTO companies (company_name, ticker_symbol, legal_name, exchange, is_active)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (ticker_symbol) DO UPDATE
                SET company_name = EXCLUDED.company_name,
                    legal_name = EXCLUDED.legal_name,
                    exchange = EXCLUDED.exchange,
                    updated_at = CURRENT_TIMESTAMP
                RETURNING id
            """, (
                company_name,
                ticker.upper(),
                legal_name,
                exchange,
                True
            ))
            result = cur.fetchone()
            company_id = result[0]
            
            # Insert data sources (NSE, BSE, SEBI only)
            sources = [
                ('NSE', f'https://www.nseindia.com/companies-listing/corporate-filings-{ticker.lower()}'),
                ('BSE', 'https://www.bseindia.com/corporates/List_Scrips.aspx'),
                ('SEBI', 'https://www.sebi.gov.in/sebiweb/other/OtherAction.do?doRecognisedFpi=yes')
            ]
            
            for source_name, source_url in sources:
                cur.execute("""
                    INSERT INTO data_sources (company_id, source_name, source_url, is_active)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (company_id, source_name) DO UPDATE
                    SET source_url = EXCLUDED.source_url,
                        updated_at = CURRENT_TIMESTAMP
                """, (company_id, source_name, source_url, True))
            
            conn.commit()
            print(f"✓ Company {ticker} created/updated with ID: {company_id}")
            print(f"✓ Data sources configured: NSE, BSE, SEBI")


def validate_schema():
    """Validate that all required tables exist."""
    from tradingagents.database.connection import get_db_connection
    
    required_tables = [
        'companies',
        'data_sources',
        'annual_reports',
        'quarterly_reports',
        'balance_sheet',
        'income_statement',
        'cashflow_statement',
        'audit_log',
        'news',
        'technical_indicators',
        'document_assets',
        'parsed_tables'
    ]
    
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
                print(f"✗ Missing tables: {', '.join(missing_tables)}")
                return False
            else:
                print("✓ All required tables exist")
                return True


def main():
    """
    Main function to initialize the VFIS database.
    
    This function:
    1. Initializes database connection pool
    2. Creates base tables
    3. Creates VFIS extension tables (news, technical_indicators)
    4. Updates audit log schema if needed
    5. Creates company entry if SEED_TICKER is set
    6. Validates the schema
    """
    parser = argparse.ArgumentParser(
        description="Initialize VFIS Database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Initialize without seeding
    python -m vfis.scripts.init_database --no-seed
    
    # Initialize and seed a company
    python -m vfis.scripts.init_database --ticker MYCO --company "My Company" --legal-name "My Company Ltd"
    
    # Use environment variable
    SEED_TICKER=AAPL python -m vfis.scripts.init_database
        """
    )
    parser.add_argument("--ticker", type=str, default=None, help="Ticker symbol to seed")
    parser.add_argument("--company", type=str, default=None, help="Company display name")
    parser.add_argument("--legal-name", type=str, default=None, help="Legal company name")
    parser.add_argument("--exchange", type=str, default="NSE", help="Stock exchange (default: NSE)")
    parser.add_argument("--no-seed", action="store_true", help="Skip company seeding")
    
    args = parser.parse_args()
    
    # Determine ticker from args or env
    seed_ticker = args.ticker or os.getenv("SEED_TICKER", "").strip()
    seed_company = args.company or os.getenv("SEED_COMPANY_NAME", seed_ticker)
    seed_legal = args.legal_name or os.getenv("SEED_LEGAL_NAME", f"{seed_company} Ltd")
    
    print("=" * 70)
    print("Verified Financial Intelligence System (VFIS) Database Initialization")
    print("=" * 70)
    print()
    print(f"Database: {DEFAULT_CONFIG.get('db_name', os.getenv('POSTGRES_DB', 'vfis_db'))}")
    print(f"Host: {DEFAULT_CONFIG.get('db_host', os.getenv('POSTGRES_HOST', 'localhost'))}")
    print(f"Port: {DEFAULT_CONFIG.get('db_port', os.getenv('POSTGRES_PORT', 5432))}")
    print()
    
    try:
        # Initialize database connection and create base tables
        print("Step 1: Initializing database connection...")
        init_database(DEFAULT_CONFIG)
        print("✓ Database connection pool established")
        print()
        
        # Create base tables (from tradingagents.database.schema)
        print("Step 2: Creating base tables...")
        create_tables()
        print("✓ Base tables created/verified")
        print()
        
        # Create VFIS extension tables (includes ingestion tables)
        print("Step 3: Creating VFIS extension tables (news, technical_indicators, document_assets, parsed_tables)...")
        create_all_vfis_tables()
        print("✓ VFIS extension tables created/verified")
        print()
        
        # Update audit log schema if needed
        print("Step 4: Updating audit log schema...")
        update_audit_log_schema()
        print("✓ Audit log schema updated")
        print()
        
        # Create company entry if seeding is enabled
        if not args.no_seed and seed_ticker:
            print(f"Step 5: Setting up {seed_ticker} company...")
            create_company(
                ticker=seed_ticker,
                company_name=seed_company,
                legal_name=seed_legal,
                exchange=args.exchange
            )
            print()
        elif not args.no_seed:
            print("Step 5: Skipping company seeding (no ticker provided)")
            print("  Set SEED_TICKER env var or use --ticker argument to seed a company")
            print()
        else:
            print("Step 5: Company seeding disabled (--no-seed)")
            print()
        
        # Validate schema
        print("Step 6: Validating schema...")
        if validate_schema():
            print()
            print("=" * 70)
            print("✓ Database initialization completed successfully!")
            print("=" * 70)
            print()
            print("Next steps:")
            print("1. Populate the database with financial data from NSE, BSE, or SEBI")
            print("2. Set ACTIVE_TICKERS env var with your target tickers")
            print("3. Run the ingestion scheduler or API server")
            print()
        else:
            print()
            print("✗ Schema validation failed. Please check errors above.")
            sys.exit(1)
        
    except Exception as e:
        print(f"✗ Error initializing database: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
