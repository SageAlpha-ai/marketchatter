"""Data Access Layer for Verified Financial Data from PostgreSQL.

ALL methods return the standard DAL contract:
{
    "data": Any,        # The actual data (dict, list, etc.)
    "status": str,      # "success" | "no_data" | "error"
    "message": str      # Human-readable status/error message
}

EXCEPTION: get_balance_sheet, get_income_statement, get_cashflow_statement
return (data, status, staleness_message) tuple for BACKWARD COMPATIBILITY
with tradingagents/dataflows/postgresql_data.py consumers.

For new code, use the _dict variants: get_balance_sheet_dict, etc.
"""
import logging
from datetime import datetime, date
from typing import Optional, Dict, List, Any, Tuple
from decimal import Decimal
from .connection import get_db_connection
from .schema import validate_source, VALID_SOURCES
from .audit import log_data_access

logger = logging.getLogger(__name__)

# Data staleness threshold (in days)
STALENESS_THRESHOLD_DAYS = 90


def _make_dal_response(data: Any, status: str, message: Optional[str] = None) -> Dict[str, Any]:
    """Create standard DAL response dict."""
    return {
        "data": data,
        "status": status,
        "message": message
    }


class FinancialDataAccess:
    """Data access layer for financial data with source validation and audit logging."""
    
    @staticmethod
    def get_company_by_ticker(ticker: str) -> Optional[Dict[str, Any]]:
        """Get company information by ticker symbol."""
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, company_name, ticker_symbol, legal_name, exchange, is_active
                    FROM companies
                    WHERE ticker_symbol = %s AND is_active = TRUE
                """, (ticker.upper(),))
                result = cur.fetchone()
                if result:
                    return {
                        'id': result[0],
                        'company_name': result[1],
                        'ticker_symbol': result[2],
                        'legal_name': result[3],
                        'exchange': result[4],
                        'is_active': result[5]
                    }
                return None
    
    @staticmethod
    def get_balance_sheet(
        ticker: str,
        report_type: str = 'quarterly',
        fiscal_year: Optional[int] = None,
        quarter: Optional[int] = None
    ) -> Tuple[Dict[str, Any], str, Optional[str]]:
        """
        Get balance sheet data for a company.
        
        Returns: Tuple of (data_dict, status, staleness_message) - ALWAYS 3 elements
        """
        company = FinancialDataAccess.get_company_by_ticker(ticker)
        if not company:
            log_data_access('data_retrieval', 'balance_sheet', None, 
                          {'ticker': ticker, 'status': 'company_not_found'})
            return {}, "no_data", f"Company with ticker {ticker} not found in database."
        
        company_id = company['id']
        staleness_msg = None
        
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Determine which report to use
                if report_type == 'quarterly' and fiscal_year and quarter:
                    cur.execute("""
                        SELECT id, fiscal_year, quarter, report_date, data_source_id, filing_date
                        FROM quarterly_reports
                        WHERE company_id = %s AND fiscal_year = %s AND quarter = %s
                    """, (company_id, fiscal_year, quarter))
                elif report_type == 'annual' and fiscal_year:
                    cur.execute("""
                        SELECT id, fiscal_year, NULL as quarter, report_date, data_source_id, filing_date
                        FROM annual_reports
                        WHERE company_id = %s AND fiscal_year = %s
                    """, (company_id, fiscal_year))
                else:
                    # Get latest report
                    if report_type == 'quarterly':
                        cur.execute("""
                            SELECT id, fiscal_year, quarter, report_date, data_source_id, filing_date
                            FROM quarterly_reports
                            WHERE company_id = %s
                            ORDER BY fiscal_year DESC, quarter DESC
                            LIMIT 1
                        """, (company_id,))
                    else:
                        cur.execute("""
                            SELECT id, fiscal_year, NULL as quarter, report_date, data_source_id, filing_date
                            FROM annual_reports
                            WHERE company_id = %s
                            ORDER BY fiscal_year DESC
                            LIMIT 1
                        """, (company_id,))
                
                report = cur.fetchone()
                if not report:
                    log_data_access('data_retrieval', 'balance_sheet', company_id,
                                  {'ticker': ticker, 'status': 'no_report_found'})
                    return {}, "no_data", f"No {report_type} report found for {ticker}."
                
                report_id, fy, q, report_date, data_source_id, filing_date = report
                
                # Check staleness
                days_old = (date.today() - report_date).days if report_date else None
                if days_old and days_old > STALENESS_THRESHOLD_DAYS:
                    staleness_msg = f"WARNING: Data is {days_old} days old (as of {report_date})."
                
                # Get data source info
                cur.execute("""
                    SELECT source_name, source_url, last_updated
                    FROM data_sources
                    WHERE id = %s
                """, (data_source_id,))
                source_info = cur.fetchone()
                source_name = source_info[0] if source_info else 'UNKNOWN'
                
                # Get balance sheet data
                if report_type == 'quarterly':
                    cur.execute("""
                        SELECT metric_name, metric_value, currency, as_of_date, data_source_id
                        FROM balance_sheet
                        WHERE quarterly_report_id = %s AND report_type = %s
                        ORDER BY metric_name
                    """, (report_id, report_type))
                else:
                    cur.execute("""
                        SELECT metric_name, metric_value, currency, as_of_date, data_source_id
                        FROM balance_sheet
                        WHERE annual_report_id = %s AND report_type = %s
                        ORDER BY metric_name
                    """, (report_id, report_type))
                
                metrics = []
                for row in cur.fetchall():
                    metrics.append({
                        'metric_name': row[0],
                        'metric_value': float(row[1]) if row[1] else None,
                        'currency': row[2],
                        'as_of_date': row[3].isoformat() if row[3] else None,
                        'data_source': source_name
                    })
                
                result = {
                    'company': company['company_name'],
                    'ticker': ticker,
                    'report_type': report_type,
                    'fiscal_year': fy,
                    'quarter': q,
                    'report_date': report_date.isoformat() if report_date else None,
                    'filing_date': filing_date.isoformat() if filing_date else None,
                    'data_source': source_name,
                    'source_url': source_info[1] if source_info and len(source_info) > 1 else None,
                    'as_of_date': report_date.isoformat() if report_date else None,
                    'metrics': metrics
                }
                
                log_data_access('data_retrieval', 'balance_sheet', company_id,
                              {'ticker': ticker, 'report_type': report_type, 'report_id': report_id})
                
                return result, "success", staleness_msg
    
    @staticmethod
    def get_income_statement(
        ticker: str,
        report_type: str = 'quarterly',
        fiscal_year: Optional[int] = None,
        quarter: Optional[int] = None
    ) -> Tuple[Dict[str, Any], str, Optional[str]]:
        """Get income statement data for a company. Returns: (data_dict, status, staleness_message) - ALWAYS 3 elements"""
        company = FinancialDataAccess.get_company_by_ticker(ticker)
        if not company:
            log_data_access('data_retrieval', 'income_statement', None,
                          {'ticker': ticker, 'status': 'company_not_found'})
            return {}, "no_data", f"Company with ticker {ticker} not found in database."
        
        company_id = company['id']
        
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Similar logic to balance_sheet
                if report_type == 'quarterly' and fiscal_year and quarter:
                    cur.execute("""
                        SELECT id, fiscal_year, quarter, report_date, data_source_id, filing_date
                        FROM quarterly_reports
                        WHERE company_id = %s AND fiscal_year = %s AND quarter = %s
                    """, (company_id, fiscal_year, quarter))
                elif report_type == 'annual' and fiscal_year:
                    cur.execute("""
                        SELECT id, fiscal_year, NULL as quarter, report_date, data_source_id, filing_date
                        FROM annual_reports
                        WHERE company_id = %s AND fiscal_year = %s
                    """, (company_id, fiscal_year))
                else:
                    if report_type == 'quarterly':
                        cur.execute("""
                            SELECT id, fiscal_year, quarter, report_date, data_source_id, filing_date
                            FROM quarterly_reports
                            WHERE company_id = %s
                            ORDER BY fiscal_year DESC, quarter DESC
                            LIMIT 1
                        """, (company_id,))
                    else:
                        cur.execute("""
                            SELECT id, fiscal_year, NULL as quarter, report_date, data_source_id, filing_date
                            FROM annual_reports
                            WHERE company_id = %s
                            ORDER BY fiscal_year DESC
                            LIMIT 1
                        """, (company_id,))
                
                report = cur.fetchone()
                if not report:
                    log_data_access('data_retrieval', 'income_statement', company_id,
                                  {'ticker': ticker, 'status': 'no_report_found'})
                    return {}, "no_data", f"No {report_type} report found for {ticker}."
                
                report_id, fy, q, report_date, data_source_id, filing_date = report
                
                days_old = (date.today() - report_date).days if report_date else None
                staleness_msg = None
                if days_old and days_old > STALENESS_THRESHOLD_DAYS:
                    staleness_msg = f"WARNING: Data is {days_old} days old (as of {report_date})."
                
                cur.execute("""
                    SELECT source_name, source_url, last_updated
                    FROM data_sources
                    WHERE id = %s
                """, (data_source_id,))
                source_info = cur.fetchone()
                source_name = source_info[0] if source_info else 'UNKNOWN'
                
                if report_type == 'quarterly':
                    cur.execute("""
                        SELECT metric_name, metric_value, currency, as_of_date, data_source_id
                        FROM income_statement
                        WHERE quarterly_report_id = %s AND report_type = %s
                        ORDER BY metric_name
                    """, (report_id, report_type))
                else:
                    cur.execute("""
                        SELECT metric_name, metric_value, currency, as_of_date, data_source_id
                        FROM income_statement
                        WHERE annual_report_id = %s AND report_type = %s
                        ORDER BY metric_name
                    """, (report_id, report_type))
                
                metrics = []
                for row in cur.fetchall():
                    metrics.append({
                        'metric_name': row[0],
                        'metric_value': float(row[1]) if row[1] else None,
                        'currency': row[2],
                        'as_of_date': row[3].isoformat() if row[3] else None,
                        'data_source': source_name
                    })
                
                result = {
                    'company': company['company_name'],
                    'ticker': ticker,
                    'report_type': report_type,
                    'fiscal_year': fy,
                    'quarter': q,
                    'report_date': report_date.isoformat() if report_date else None,
                    'filing_date': filing_date.isoformat() if filing_date else None,
                    'data_source': source_name,
                    'source_url': source_info[1] if source_info and len(source_info) > 1 else None,
                    'as_of_date': report_date.isoformat() if report_date else None,
                    'metrics': metrics
                }
                
                log_data_access('data_retrieval', 'income_statement', company_id,
                              {'ticker': ticker, 'report_type': report_type, 'report_id': report_id})
                
                return result, "success", staleness_msg
    
    @staticmethod
    def get_cashflow_statement(
        ticker: str,
        report_type: str = 'quarterly',
        fiscal_year: Optional[int] = None,
        quarter: Optional[int] = None
    ) -> Tuple[Dict[str, Any], str, Optional[str]]:
        """Get cash flow statement data for a company. Returns: (data_dict, status, staleness_message) - ALWAYS 3 elements"""
        company = FinancialDataAccess.get_company_by_ticker(ticker)
        if not company:
            log_data_access('data_retrieval', 'cashflow_statement', None,
                          {'ticker': ticker, 'status': 'company_not_found'})
            return {}, "no_data", f"Company with ticker {ticker} not found in database."
        
        company_id = company['id']
        
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                if report_type == 'quarterly' and fiscal_year and quarter:
                    cur.execute("""
                        SELECT id, fiscal_year, quarter, report_date, data_source_id, filing_date
                        FROM quarterly_reports
                        WHERE company_id = %s AND fiscal_year = %s AND quarter = %s
                    """, (company_id, fiscal_year, quarter))
                elif report_type == 'annual' and fiscal_year:
                    cur.execute("""
                        SELECT id, fiscal_year, NULL as quarter, report_date, data_source_id, filing_date
                        FROM annual_reports
                        WHERE company_id = %s AND fiscal_year = %s
                    """, (company_id, fiscal_year))
                else:
                    if report_type == 'quarterly':
                        cur.execute("""
                            SELECT id, fiscal_year, quarter, report_date, data_source_id, filing_date
                            FROM quarterly_reports
                            WHERE company_id = %s
                            ORDER BY fiscal_year DESC, quarter DESC
                            LIMIT 1
                        """, (company_id,))
                    else:
                        cur.execute("""
                            SELECT id, fiscal_year, NULL as quarter, report_date, data_source_id, filing_date
                            FROM annual_reports
                            WHERE company_id = %s
                            ORDER BY fiscal_year DESC
                            LIMIT 1
                        """, (company_id,))
                
                report = cur.fetchone()
                if not report:
                    log_data_access('data_retrieval', 'cashflow_statement', company_id,
                                  {'ticker': ticker, 'status': 'no_report_found'})
                    return {}, "no_data", f"No {report_type} report found for {ticker}."
                
                report_id, fy, q, report_date, data_source_id, filing_date = report
                
                days_old = (date.today() - report_date).days if report_date else None
                staleness_msg = None
                if days_old and days_old > STALENESS_THRESHOLD_DAYS:
                    staleness_msg = f"WARNING: Data is {days_old} days old (as of {report_date})."
                
                cur.execute("""
                    SELECT source_name, source_url, last_updated
                    FROM data_sources
                    WHERE id = %s
                """, (data_source_id,))
                source_info = cur.fetchone()
                source_name = source_info[0] if source_info else 'UNKNOWN'
                
                if report_type == 'quarterly':
                    cur.execute("""
                        SELECT metric_name, metric_value, currency, as_of_date, data_source_id
                        FROM cashflow_statement
                        WHERE quarterly_report_id = %s AND report_type = %s
                        ORDER BY metric_name
                    """, (report_id, report_type))
                else:
                    cur.execute("""
                        SELECT metric_name, metric_value, currency, as_of_date, data_source_id
                        FROM cashflow_statement
                        WHERE annual_report_id = %s AND report_type = %s
                        ORDER BY metric_name
                    """, (report_id, report_type))
                
                metrics = []
                for row in cur.fetchall():
                    metrics.append({
                        'metric_name': row[0],
                        'metric_value': float(row[1]) if row[1] else None,
                        'currency': row[2],
                        'as_of_date': row[3].isoformat() if row[3] else None,
                        'data_source': source_name
                    })
                
                result = {
                    'company': company['company_name'],
                    'ticker': ticker,
                    'report_type': report_type,
                    'fiscal_year': fy,
                    'quarter': q,
                    'report_date': report_date.isoformat() if report_date else None,
                    'filing_date': filing_date.isoformat() if filing_date else None,
                    'data_source': source_name,
                    'source_url': source_info[1] if source_info and len(source_info) > 1 else None,
                    'as_of_date': report_date.isoformat() if report_date else None,
                    'metrics': metrics
                }
                
                log_data_access('data_retrieval', 'cashflow_statement', company_id,
                              {'ticker': ticker, 'report_type': report_type, 'report_id': report_id})
                
                return result, "success", staleness_msg
    
    @staticmethod
    def get_available_reports(ticker: str) -> Dict[str, List[Dict[str, Any]]]:
        """Get list of available annual and quarterly reports for a company."""
        company = FinancialDataAccess.get_company_by_ticker(ticker)
        if not company:
            return {'annual': [], 'quarterly': []}
        
        company_id = company['id']
        
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Get annual reports
                cur.execute("""
                    SELECT ar.fiscal_year, ar.report_date, ar.filing_date, 
                           ds.source_name, ds.source_url
                    FROM annual_reports ar
                    LEFT JOIN data_sources ds ON ar.data_source_id = ds.id
                    WHERE ar.company_id = %s
                    ORDER BY ar.fiscal_year DESC
                """, (company_id,))
                
                annual = []
                for row in cur.fetchall():
                    annual.append({
                        'fiscal_year': row[0],
                        'report_date': row[1].isoformat() if row[1] else None,
                        'filing_date': row[2].isoformat() if row[2] else None,
                        'source': row[3],
                        'source_url': row[4]
                    })
                
                # Get quarterly reports
                cur.execute("""
                    SELECT qr.fiscal_year, qr.quarter, qr.report_date, qr.filing_date,
                           ds.source_name, ds.source_url
                    FROM quarterly_reports qr
                    LEFT JOIN data_sources ds ON qr.data_source_id = ds.id
                    WHERE qr.company_id = %s
                    ORDER BY qr.fiscal_year DESC, qr.quarter DESC
                """, (company_id,))
                
                quarterly = []
                for row in cur.fetchall():
                    quarterly.append({
                        'fiscal_year': row[0],
                        'quarter': row[1],
                        'report_date': row[2].isoformat() if row[2] else None,
                        'filing_date': row[3].isoformat() if row[3] else None,
                        'source': row[4],
                        'source_url': row[5]
                    })
                
                log_data_access('data_retrieval', 'available_reports', company_id,
                              {'ticker': ticker})
                
                return {'annual': annual, 'quarterly': quarterly}
    
    @staticmethod
    def get_market_chatter(
        ticker: str,
        days: int = 7,
        limit: int = 100,
        source: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get recent market chatter for a ticker.
        
        SAFE: Never throws. Returns standard DAL response dict.
        
        Args:
            ticker: Stock ticker symbol
            days: Number of days to look back
            limit: Maximum records to return
            source: Optional source filter (e.g., 'alpha_vantage', 'rss')
            
        Returns:
            Standard DAL response:
            {
                "data": {"items": [...], "count": int, "sources": {...}, "window_days": int},
                "status": "success" | "no_data" | "error",
                "message": Optional[str]
            }
        """
        from .chatter_dal import get_recent_chatter
        return get_recent_chatter(ticker, days=days, limit=limit, source=source)
    
    @staticmethod
    def get_chatter_summary(ticker: str, days: int = 7) -> Dict[str, Any]:
        """
        Get a summary of market chatter suitable for LLM consumption.
        
        SAFE: Never throws. Returns standard DAL response dict.
        
        Returns:
            Standard DAL response:
            {
                "data": {summary data},
                "status": "success" | "no_data" | "error",
                "message": Optional[str]
            }
        """
        from .chatter_dal import get_chatter_summary
        
        try:
            return get_chatter_summary(ticker, days=days)
        except Exception as e:
            logger.error(f"Error getting chatter summary for {ticker}: {e}")
            return {
                "data": {
                    "ticker": ticker,
                    "total_count": 0,
                    "has_data": False,
                    "items": []
                },
                "status": "error",
                "message": str(e)
            }
    
    # =========================================================================
    # Dict-returning variants (NEW - use these for new code)
    # =========================================================================
    
    @staticmethod
    def get_balance_sheet_dict(
        ticker: str,
        report_type: str = 'quarterly',
        fiscal_year: Optional[int] = None,
        quarter: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Get balance sheet data - returns standard DAL dict contract.
        
        Returns:
            {"data": {...}, "status": "success|no_data|error", "message": str}
        """
        data, status, staleness_msg = FinancialDataAccess.get_balance_sheet(
            ticker, report_type, fiscal_year, quarter
        )
        if staleness_msg and data:
            data['staleness_warning'] = staleness_msg
        return _make_dal_response(data if data else None, status, staleness_msg)
    
    @staticmethod
    def get_income_statement_dict(
        ticker: str,
        report_type: str = 'quarterly',
        fiscal_year: Optional[int] = None,
        quarter: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Get income statement data - returns standard DAL dict contract.
        
        Returns:
            {"data": {...}, "status": "success|no_data|error", "message": str}
        """
        data, status, staleness_msg = FinancialDataAccess.get_income_statement(
            ticker, report_type, fiscal_year, quarter
        )
        if staleness_msg and data:
            data['staleness_warning'] = staleness_msg
        return _make_dal_response(data if data else None, status, staleness_msg)
    
    @staticmethod
    def get_cashflow_statement_dict(
        ticker: str,
        report_type: str = 'quarterly',
        fiscal_year: Optional[int] = None,
        quarter: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Get cash flow statement data - returns standard DAL dict contract.
        
        Returns:
            {"data": {...}, "status": "success|no_data|error", "message": str}
        """
        data, status, staleness_msg = FinancialDataAccess.get_cashflow_statement(
            ticker, report_type, fiscal_year, quarter
        )
        if staleness_msg and data:
            data['staleness_warning'] = staleness_msg
        return _make_dal_response(data if data else None, status, staleness_msg)

