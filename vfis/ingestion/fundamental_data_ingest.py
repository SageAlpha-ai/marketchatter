"""
Fundamental data ingestion from yfinance or alpha_vantage.

Fetches balance sheet, income statement, and cash flow data
and stores them in the database with proper tagging.
"""

import scripts.init_env
import logging
from typing import Dict, Any, Optional, List, Tuple
from datetime import date, datetime
import pandas as pd
import sys
from pathlib import Path

_project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_project_root))

from tradingagents.database.connection import get_db_connection, init_database
from tradingagents.database.audit import log_data_access
from vfis.tools.postgres_dal import VFISDataAccess

logger = logging.getLogger(__name__)

init_database(config={})


class FundamentalDataIngester:
    """
    Ingester for fundamental financial data from yfinance or alpha_vantage.
    
    Stores balance sheet, income statement, and cash flow data
    in quarterly_reports, balance_sheet, income_statement, cashflow_statement tables.
    """
    
    def __init__(self, source: str = "YFINANCE"):
        """
        Initialize fundamental data ingester.
        
        Args:
            source: Data source name (YFINANCE or ALPHA_VANTAGE)
        """
        self.source = source.upper()
    
    def ingest_for_ticker(
        self,
        ticker: str,
        use_yfinance: bool = True
    ) -> Dict[str, Any]:
        """
        Ingest fundamental data for a ticker.
        
        Args:
            ticker: Company ticker symbol
            use_yfinance: If True, use yfinance; if False, use alpha_vantage
            
        Returns:
            Dictionary with ingestion results
        """
        results = {
            'ticker': ticker.upper(),
            'source': self.source,
            'success': False,
            'quarterly_reports_created': 0,
            'balance_sheet_metrics': 0,
            'income_statement_metrics': 0,
            'cashflow_metrics': 0,
            'errors': []
        }
        
        try:
            # Get or create company
            company = VFISDataAccess.get_company_by_ticker(ticker)
            if not company:
                # Create company if doesn't exist
                company_id = self._get_or_create_company(ticker)
                if not company_id:
                    results['errors'].append(f"Failed to create company {ticker}")
                    return results
            else:
                company_id = company['id']
            
            # Get or create data source
            data_source_id = self._get_or_create_data_source(company_id)
            if not data_source_id:
                results['errors'].append(f"Failed to create data source {self.source}")
                return results
            
            # Fetch financial data
            if use_yfinance:
                balance_df, income_df, cashflow_df = self._fetch_yfinance_data(ticker)
            else:
                balance_df, income_df, cashflow_df = self._fetch_alpha_vantage_data(ticker)
            
            if balance_df is None and income_df is None and cashflow_df is None:
                results['errors'].append("No financial data available from source")
                return results
            
            # Process each DataFrame
            if balance_df is not None:
                balance_result = self._process_statement(
                    ticker, company_id, data_source_id, balance_df, 'balance_sheet'
                )
                results['quarterly_reports_created'] = max(results['quarterly_reports_created'], balance_result['reports_created'])
                results['balance_sheet_metrics'] = balance_result['metrics_inserted']
                results['errors'].extend(balance_result['errors'])
            
            if income_df is not None:
                income_result = self._process_statement(
                    ticker, company_id, data_source_id, income_df, 'income_statement'
                )
                results['quarterly_reports_created'] = max(results['quarterly_reports_created'], income_result['reports_created'])
                results['income_statement_metrics'] = income_result['metrics_inserted']
                results['errors'].extend(income_result['errors'])
            
            if cashflow_df is not None:
                cashflow_result = self._process_statement(
                    ticker, company_id, data_source_id, cashflow_df, 'cashflow_statement'
                )
                results['quarterly_reports_created'] = max(results['quarterly_reports_created'], cashflow_result['reports_created'])
                results['cashflow_metrics'] = cashflow_result['metrics_inserted']
                results['errors'].extend(cashflow_result['errors'])
            
            results['success'] = True
            
            # Log audit
            log_data_access(
                event_type='fundamental_data_ingestion',
                entity_type='quarterly_reports',
                entity_id=None,
                details={
                    'ticker': ticker,
                    'source': self.source,
                    'reports_created': results['quarterly_reports_created'],
                    'metrics_inserted': results['balance_sheet_metrics'] + results['income_statement_metrics'] + results['cashflow_metrics']
                },
                user_id='FundamentalDataIngester'
            )
            
        except Exception as e:
            error_msg = f"Failed to ingest fundamental data for {ticker}: {str(e)}"
            logger.error(error_msg, exc_info=True)
            results['errors'].append(error_msg)
        
        return results
    
    def _fetch_yfinance_data(
        self,
        ticker: str
    ) -> Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame], Optional[pd.DataFrame]]:
        """Fetch data from yfinance."""
        try:
            import yfinance as yf
            
            ticker_obj = yf.Ticker(ticker.upper())
            
            balance_df = ticker_obj.quarterly_balance_sheet
            income_df = ticker_obj.quarterly_financials
            cashflow_df = ticker_obj.quarterly_cashflow
            
            # Convert to DataFrame if needed and check if empty
            if not isinstance(balance_df, pd.DataFrame) or balance_df.empty:
                balance_df = None
            if not isinstance(income_df, pd.DataFrame) or income_df.empty:
                income_df = None
            if not isinstance(cashflow_df, pd.DataFrame) or cashflow_df.empty:
                cashflow_df = None
            
            return balance_df, income_df, cashflow_df
            
        except Exception as e:
            logger.warning(f"Failed to fetch yfinance data for {ticker}: {e}")
            return None, None, None
    
    def _fetch_alpha_vantage_data(
        self,
        ticker: str
    ) -> Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame], Optional[pd.DataFrame]]:
        """Fetch data from alpha_vantage (returns strings, would need parsing)."""
        # Alpha Vantage returns JSON strings, would need additional parsing logic
        # For now, return None to use yfinance
        logger.warning("Alpha Vantage ingestion not yet implemented, using yfinance")
        return None, None, None
    
    def _get_or_create_company(self, ticker: str) -> Optional[int]:
        """Get or create company record."""
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO companies (company_name, ticker_symbol, legal_name, exchange, is_active)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (ticker_symbol) DO UPDATE
                        SET updated_at = CURRENT_TIMESTAMP
                        RETURNING id
                    """, (
                        ticker.upper(),
                        ticker.upper(),
                        ticker.upper(),
                        'NYSE',  # Default exchange, can be updated
                        True
                    ))
                    result = cur.fetchone()
                    conn.commit()
                    return result[0] if result else None
        except Exception as e:
            logger.error(f"Failed to create company {ticker}: {e}")
            return None
    
    def _get_or_create_data_source(self, company_id: int) -> Optional[int]:
        """
        Get or create data source record.
        
        Note: Database schema only allows 'NSE', 'BSE', 'SEBI' as source names.
        For external APIs like YFINANCE, we use 'NSE' as the source_name
        but store the actual source in the source_url field.
        """
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    # Use 'NSE' as the source_name (required by schema constraint)
                    # Store actual source in source_url
                    source_name = 'NSE'  # Schema constraint requires NSE/BSE/SEBI
                    source_url = f"{self.source}:https://finance.yahoo.com/quote/" if self.source == "YFINANCE" else self.source
                    
                    cur.execute("""
                        INSERT INTO data_sources (company_id, source_name, source_url, is_active)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (company_id, source_name) DO UPDATE
                        SET source_url = EXCLUDED.source_url,
                            updated_at = CURRENT_TIMESTAMP
                        RETURNING id
                    """, (company_id, source_name, source_url, True))
                    
                    result = cur.fetchone()
                    conn.commit()
                    return result[0] if result else None
        except Exception as e:
            logger.error(f"Failed to create data source: {e}")
            return None
    
    def _process_statement(
        self,
        ticker: str,
        company_id: int,
        data_source_id: int,
        df: pd.DataFrame,
        statement_type: str
    ) -> Dict[str, Any]:
        """
        Process a financial statement DataFrame and store in database.
        
        Args:
            ticker: Ticker symbol
            company_id: Company ID
            data_source_id: Data source ID
            df: DataFrame with dates as columns, metrics as rows
            statement_type: 'balance_sheet', 'income_statement', or 'cashflow_statement'
        """
        result = {
            'reports_created': 0,
            'metrics_inserted': 0,
            'errors': []
        }
        
        if df.empty:
            return result
        
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    # Process each column (each is a quarterly period)
                    for col_date in df.columns:
                        try:
                            # Parse date (yfinance uses Timestamp)
                            if isinstance(col_date, pd.Timestamp):
                                report_date = col_date.date()
                            elif isinstance(col_date, datetime):
                                report_date = col_date.date()
                            else:
                                report_date = pd.to_datetime(col_date).date()
                            
                            # Determine fiscal year and quarter
                            fiscal_year = report_date.year
                            quarter = (report_date.month - 1) // 3 + 1
                            
                            # Get or create quarterly report
                            quarterly_report_id = self._get_or_create_quarterly_report(
                                cur, company_id, data_source_id, fiscal_year, quarter, report_date
                            )
                            
                            if quarterly_report_id:
                                if result['reports_created'] == 0:
                                    result['reports_created'] = 1
                                
                                # Insert metrics for this period
                                metrics_inserted = self._insert_metrics(
                                    cur, quarterly_report_id, data_source_id, df, col_date, report_date, statement_type
                                )
                                result['metrics_inserted'] += metrics_inserted
                            
                        except Exception as e:
                            error_msg = f"Failed to process period {col_date}: {str(e)}"
                            logger.warning(error_msg)
                            result['errors'].append(error_msg)
                            continue
                    
                    conn.commit()
                    
        except Exception as e:
            error_msg = f"Failed to process {statement_type}: {str(e)}"
            logger.error(error_msg, exc_info=True)
            result['errors'].append(error_msg)
        
        return result
    
    def _get_or_create_quarterly_report(
        self,
        cur,
        company_id: int,
        data_source_id: int,
        fiscal_year: int,
        quarter: int,
        report_date: date
    ) -> Optional[int]:
        """Get or create quarterly report record."""
        try:
            cur.execute("""
                INSERT INTO quarterly_reports (company_id, fiscal_year, quarter, report_date, data_source_id)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (company_id, fiscal_year, quarter) DO UPDATE
                SET report_date = EXCLUDED.report_date,
                    data_source_id = EXCLUDED.data_source_id,
                    updated_at = CURRENT_TIMESTAMP
                RETURNING id
            """, (company_id, fiscal_year, quarter, report_date, data_source_id))
            
            result = cur.fetchone()
            return result[0] if result else None
            
        except Exception as e:
            logger.warning(f"Failed to create quarterly report: {e}")
            return None
    
    def _insert_metrics(
        self,
        cur,
        quarterly_report_id: int,
        data_source_id: int,
        df: pd.DataFrame,
        col_date: Any,
        report_date: date,
        statement_type: str
    ) -> int:
        """Insert metrics for a specific period."""
        table_name = statement_type
        metrics_inserted = 0
        
        # Delete existing metrics for this report and statement type
        cur.execute(f"""
            DELETE FROM {table_name}
            WHERE quarterly_report_id = %s AND report_type = 'quarterly'
        """, (quarterly_report_id,))
        
        # Insert metrics
        for metric_name, row_data in df.iterrows():
            try:
                value = row_data[col_date]
                
                # Skip NaN or None values
                if pd.isna(value):
                    continue
                
                # Convert to float
                try:
                    metric_value = float(value)
                except (ValueError, TypeError):
                    continue
                
                # Insert metric
                cur.execute(f"""
                    INSERT INTO {table_name}
                    (quarterly_report_id, report_type, metric_name, metric_value, currency, as_of_date, data_source_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (
                    quarterly_report_id,
                    'quarterly',
                    str(metric_name),
                    metric_value,
                    'USD',  # yfinance typically uses USD
                    report_date,
                    data_source_id
                ))
                
                metrics_inserted += 1
                
            except Exception as e:
                logger.warning(f"Failed to insert metric {metric_name}: {e}")
                continue
        
        return metrics_inserted


def ingest_fundamental_data(
    ticker: str,
    source: str = "YFINANCE",
    use_yfinance: bool = True
) -> Dict[str, Any]:
    """
    Ingest fundamental data for a ticker.
    
    Args:
        ticker: Company ticker symbol
        source: Data source name
        use_yfinance: Use yfinance if True, alpha_vantage if False
        
    Returns:
        Dictionary with ingestion results
    """
    ingester = FundamentalDataIngester(source=source)
    return ingester.ingest_for_ticker(ticker, use_yfinance=use_yfinance)


def main():
    """Main entry point for command-line usage."""
    import argparse
    import sys
    
    parser = argparse.ArgumentParser(
        description='Ingest fundamental data (balance sheet, income statement, cash flow) into VFIS database',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m vfis.ingestion.fundamental_data_ingest --ticker AAPL
  python -m vfis.ingestion.fundamental_data_ingest --ticker AAPL --source YFINANCE
        """
    )
    
    parser.add_argument(
        '--ticker',
        type=str,
        required=True,
        help='Company ticker symbol (dynamically provided)'
    )
    
    parser.add_argument(
        '--source',
        type=str,
        default='YFINANCE',
        help='Data source name (default: YFINANCE)'
    )
    
    parser.add_argument(
        '--use-yfinance',
        action='store_true',
        default=True,
        help='Use yfinance API (default: True)'
    )
    
    parser.add_argument(
        '--use-alpha-vantage',
        action='store_true',
        default=False,
        help='Use Alpha Vantage API instead of yfinance'
    )
    
    parser.add_argument(
        '--log-level',
        type=str,
        default='INFO',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        help='Logging level (default: INFO)'
    )
    
    args = parser.parse_args()
    
    # Configure logging
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    try:
        # Determine data source
        use_yfinance = not args.use_alpha_vantage
        
        # Ingest fundamental data
        results = ingest_fundamental_data(
            ticker=args.ticker,
            source=args.source,
            use_yfinance=use_yfinance
        )
        
        # Print summary
        print(f"\n{'='*60}")
        print(f"Fundamental Data Ingestion Summary")
        print(f"{'='*60}")
        print(f"Ticker: {results['ticker']}")
        print(f"Source: {results['source']}")
        print(f"Quarterly reports created: {results['quarterly_reports_created']}")
        print(f"Balance sheet metrics: {results['balance_sheet_metrics']}")
        print(f"Income statement metrics: {results['income_statement_metrics']}")
        print(f"Cashflow metrics: {results['cashflow_metrics']}")
        print(f"Success: {results['success']}")
        print(f"{'='*60}\n")
        
        if results['errors']:
            print("Errors:")
            for error in results['errors']:
                print(f"  - {error}")
            print()
        
        # Exit with error code if unsuccessful
        sys.exit(0 if results['success'] else 1)
    
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        print(f"\nERROR: {e}\n", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

