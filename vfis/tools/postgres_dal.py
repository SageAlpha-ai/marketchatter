"""
PostgreSQL Data Access Layer (DAL) for Verified Financial Intelligence System (VFIS).

STRICT RULES:
- PostgreSQL is the ONLY source of financial data
- No external APIs or live data calls
- Data sources validated: NSE, BSE, SEBI only
- Windows-compatible Python only
- No LLM logic inside the data layer

This module provides a clean interface for accessing verified financial data
from PostgreSQL with explicit source attribution, staleness detection, and
comprehensive audit logging.
"""

import logging
from datetime import datetime, date, timedelta
from typing import Optional, Dict, List, Any, Tuple, Union
from enum import Enum
from decimal import Decimal

# Import database connection from tradingagents package
from tradingagents.database.connection import get_db_connection

logger = logging.getLogger(__name__)

# Import audit logging
try:
    from tradingagents.database.audit import log_data_access
except ImportError:
    # Fallback if audit module not available
    def log_data_access(*args, **kwargs):
        logger.warning("Audit logging not available")

# Valid data sources - enforced at database level
VALID_SOURCES = {'NSE', 'BSE', 'SEBI'}

# Staleness thresholds (in days)
QUARTERLY_STALENESS_DAYS = 120
ANNUAL_STALENESS_DAYS = 400
NEWS_STALENESS_HOURS = 48


class DataStatus(Enum):
    """Explicit status codes for data retrieval."""
    SUCCESS = "SUCCESS"
    NO_DATA = "NO_DATA"
    STALE_DATA = "STALE_DATA"
    ERROR = "ERROR"


class VFISDataAccess:
    """
    Data Access Layer for Verified Financial Intelligence System.
    
    Provides safe, parameterized access to PostgreSQL database with:
    - Source validation (NSE, BSE, SEBI only)
    - Staleness detection
    - Explicit status reporting (SUCCESS, NO_DATA, STALE_DATA, ERROR)
    - Comprehensive audit logging
    - Windows-compatible operations
    """
    
    @staticmethod
    def get_company_by_ticker(ticker: str) -> Optional[Dict[str, Any]]:
        """
        Get company information by ticker symbol.
        
        Args:
            ticker: Company ticker symbol (dynamically provided)
            
        Returns:
            Dictionary with company information or None if not found
        """
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    # Safe parameterized query
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
        except Exception as e:
            logger.error(f"Error retrieving company {ticker}: {e}")
            raise
    
    @staticmethod
    def get_quarterly_financials(
        ticker: str,
        fiscal_year: Optional[int] = None,
        quarter: Optional[int] = None,
        statement_type: str = 'balance_sheet',
        agent_name: Optional[str] = None,
        user_query: Optional[str] = None
    ) -> Tuple[Dict[str, Any], DataStatus]:
        """
        Get quarterly financial data (balance sheet, income statement, or cash flow).
        
        Args:
            ticker: Company ticker symbol
            fiscal_year: Fiscal year (optional, uses latest if not provided)
            quarter: Quarter number 1-4 (optional, uses latest if not provided)
            statement_type: 'balance_sheet', 'income_statement', or 'cashflow_statement'
            agent_name: Name of agent making the request (for audit logging)
            user_query: User query text (for audit logging)
            
        Returns:
            Tuple of (data_dict, DataStatus)
            - data_dict contains financial metrics or empty dict if NO_DATA
            - DataStatus is SUCCESS, NO_DATA, STALE_DATA, or ERROR
        """
        try:
            # Get company
            company = VFISDataAccess.get_company_by_ticker(ticker)
            if not company:
                VFISDataAccess._log_audit(
                    agent_name=agent_name,
                    user_query=user_query,
                    tables_accessed=[f'{statement_type}', 'companies'],
                    status='NO_DATA',
                    details={'reason': 'Company not found', 'ticker': ticker}
                )
                return {}, DataStatus.NO_DATA
            
            company_id = company['id']
            
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    # Find quarterly report
                    if fiscal_year and quarter:
                        cur.execute("""
                            SELECT id, fiscal_year, quarter, report_date, data_source_id, filing_date
                            FROM quarterly_reports
                            WHERE company_id = %s AND fiscal_year = %s AND quarter = %s
                        """, (company_id, fiscal_year, quarter))
                    else:
                        # Get latest quarterly report
                        cur.execute("""
                            SELECT id, fiscal_year, quarter, report_date, data_source_id, filing_date
                            FROM quarterly_reports
                            WHERE company_id = %s
                            ORDER BY fiscal_year DESC, quarter DESC
                            LIMIT 1
                        """, (company_id,))
                    
                    report = cur.fetchone()
                    if not report:
                        VFISDataAccess._log_audit(
                            agent_name=agent_name,
                            user_query=user_query,
                            tables_accessed=['quarterly_reports', f'{statement_type}'],
                            status='NO_DATA',
                            details={'reason': 'No quarterly report found', 'ticker': ticker}
                        )
                        return {}, DataStatus.NO_DATA
                    
                    report_id, fy, q, report_date, data_source_id, filing_date = report
                    
                    # Check staleness (120 days for quarterly)
                    days_old = (date.today() - report_date).days if report_date else None
                    status = DataStatus.SUCCESS
                    if days_old and days_old > QUARTERLY_STALENESS_DAYS:
                        status = DataStatus.STALE_DATA
                    
                    # Get data source info
                    cur.execute("""
                        SELECT source_name, source_url, last_updated
                        FROM data_sources
                        WHERE id = %s
                    """, (data_source_id,))
                    source_info = cur.fetchone()
                    source_name = source_info[0] if source_info else 'UNKNOWN'
                    
                    # Get financial statement data
                    table_name = statement_type
                    cur.execute(f"""
                        SELECT metric_name, metric_value, currency, as_of_date, data_source_id
                        FROM {table_name}
                        WHERE quarterly_report_id = %s AND report_type = 'quarterly'
                        ORDER BY metric_name
                    """, (report_id,))
                    
                    metrics = []
                    for row in cur.fetchall():
                        metrics.append({
                            'metric_name': row[0],
                            'metric_value': float(row[1]) if row[1] else None,
                            'currency': row[2] or 'INR',
                            'as_of_date': row[3].isoformat() if row[3] else None,
                            'data_source': source_name
                        })
                    
                    if not metrics:
                        VFISDataAccess._log_audit(
                            agent_name=agent_name,
                            user_query=user_query,
                            tables_accessed=[table_name],
                            status='NO_DATA',
                            details={'reason': 'No metrics found', 'ticker': ticker, 'report_id': report_id}
                        )
                        return {}, DataStatus.NO_DATA
                    
                    result = {
                        'company': company['company_name'],
                        'ticker': ticker,
                        'report_type': 'quarterly',
                        'fiscal_year': fy,
                        'quarter': q,
                        'report_date': report_date.isoformat() if report_date else None,
                        'filing_date': filing_date.isoformat() if filing_date else None,
                        'data_source': source_name,
                        'source_url': source_info[1] if source_info and len(source_info) > 1 else None,
                        'as_of_date': report_date.isoformat() if report_date else None,
                        'days_old': days_old,
                        'metrics': metrics,
                        'statement_type': statement_type
                    }
                    
                    # Log audit
                    VFISDataAccess._log_audit(
                        agent_name=agent_name,
                        user_query=user_query,
                        tables_accessed=[table_name, 'quarterly_reports', 'data_sources'],
                        status=status.value,
                        details={'ticker': ticker, 'report_id': report_id, 'days_old': days_old}
                    )
                    
                    return result, status
                    
        except Exception as e:
            logger.error(f"Error retrieving quarterly financials for {ticker}: {e}")
            VFISDataAccess._log_audit(
                agent_name=agent_name,
                user_query=user_query,
                tables_accessed=[statement_type],
                status='ERROR',
                details={'error': str(e), 'ticker': ticker}
            )
            return {}, DataStatus.ERROR
    
    @staticmethod
    def get_annual_financials(
        ticker: str,
        fiscal_year: Optional[int] = None,
        statement_type: str = 'balance_sheet',
        agent_name: Optional[str] = None,
        user_query: Optional[str] = None
    ) -> Tuple[Dict[str, Any], DataStatus]:
        """
        Get annual financial data (balance sheet, income statement, or cash flow).
        
        Args:
            ticker: Company ticker symbol
            fiscal_year: Fiscal year (optional, uses latest if not provided)
            statement_type: 'balance_sheet', 'income_statement', or 'cashflow_statement'
            agent_name: Name of agent making the request (for audit logging)
            user_query: User query text (for audit logging)
            
        Returns:
            Tuple of (data_dict, DataStatus)
            - data_dict contains financial metrics or empty dict if NO_DATA
            - DataStatus is SUCCESS, NO_DATA, STALE_DATA, or ERROR
        """
        try:
            company = VFISDataAccess.get_company_by_ticker(ticker)
            if not company:
                VFISDataAccess._log_audit(
                    agent_name=agent_name,
                    user_query=user_query,
                    tables_accessed=[f'{statement_type}', 'companies'],
                    status='NO_DATA',
                    details={'reason': 'Company not found', 'ticker': ticker}
                )
                return {}, DataStatus.NO_DATA
            
            company_id = company['id']
            
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    # Find annual report
                    if fiscal_year:
                        cur.execute("""
                            SELECT id, fiscal_year, report_date, data_source_id, filing_date
                            FROM annual_reports
                            WHERE company_id = %s AND fiscal_year = %s
                        """, (company_id, fiscal_year))
                    else:
                        cur.execute("""
                            SELECT id, fiscal_year, report_date, data_source_id, filing_date
                            FROM annual_reports
                            WHERE company_id = %s
                            ORDER BY fiscal_year DESC
                            LIMIT 1
                        """, (company_id,))
                    
                    report = cur.fetchone()
                    if not report:
                        VFISDataAccess._log_audit(
                            agent_name=agent_name,
                            user_query=user_query,
                            tables_accessed=['annual_reports', f'{statement_type}'],
                            status='NO_DATA',
                            details={'reason': 'No annual report found', 'ticker': ticker}
                        )
                        return {}, DataStatus.NO_DATA
                    
                    report_id, fy, report_date, data_source_id, filing_date = report
                    
                    # Check staleness (400 days for annual)
                    days_old = (date.today() - report_date).days if report_date else None
                    status = DataStatus.SUCCESS
                    if days_old and days_old > ANNUAL_STALENESS_DAYS:
                        status = DataStatus.STALE_DATA
                    
                    # Get data source info
                    cur.execute("""
                        SELECT source_name, source_url, last_updated
                        FROM data_sources
                        WHERE id = %s
                    """, (data_source_id,))
                    source_info = cur.fetchone()
                    source_name = source_info[0] if source_info else 'UNKNOWN'
                    
                    # Get financial statement data
                    table_name = statement_type
                    cur.execute(f"""
                        SELECT metric_name, metric_value, currency, as_of_date, data_source_id
                        FROM {table_name}
                        WHERE annual_report_id = %s AND report_type = 'annual'
                        ORDER BY metric_name
                    """, (report_id,))
                    
                    metrics = []
                    for row in cur.fetchall():
                        metrics.append({
                            'metric_name': row[0],
                            'metric_value': float(row[1]) if row[1] else None,
                            'currency': row[2] or 'INR',
                            'as_of_date': row[3].isoformat() if row[3] else None,
                            'data_source': source_name
                        })
                    
                    if not metrics:
                        VFISDataAccess._log_audit(
                            agent_name=agent_name,
                            user_query=user_query,
                            tables_accessed=[table_name],
                            status='NO_DATA',
                            details={'reason': 'No metrics found', 'ticker': ticker, 'report_id': report_id}
                        )
                        return {}, DataStatus.NO_DATA
                    
                    result = {
                        'company': company['company_name'],
                        'ticker': ticker,
                        'report_type': 'annual',
                        'fiscal_year': fy,
                        'report_date': report_date.isoformat() if report_date else None,
                        'filing_date': filing_date.isoformat() if filing_date else None,
                        'data_source': source_name,
                        'source_url': source_info[1] if source_info and len(source_info) > 1 else None,
                        'as_of_date': report_date.isoformat() if report_date else None,
                        'days_old': days_old,
                        'metrics': metrics,
                        'statement_type': statement_type
                    }
                    
                    # Log audit
                    VFISDataAccess._log_audit(
                        agent_name=agent_name,
                        user_query=user_query,
                        tables_accessed=[table_name, 'annual_reports', 'data_sources'],
                        status=status.value,
                        details={'ticker': ticker, 'report_id': report_id, 'days_old': days_old}
                    )
                    
                    return result, status
                    
        except Exception as e:
            logger.error(f"Error retrieving annual financials for {ticker}: {e}")
            VFISDataAccess._log_audit(
                agent_name=agent_name,
                user_query=user_query,
                tables_accessed=[statement_type],
                status='ERROR',
                details={'error': str(e), 'ticker': ticker}
            )
            return {}, DataStatus.ERROR
    
    @staticmethod
    def get_news(
        ticker: str,
        limit: int = 10,
        agent_name: Optional[str] = None,
        user_query: Optional[str] = None
    ) -> Tuple[List[Dict[str, Any]], DataStatus]:
        """
        Get news articles for a company.
        
        Note: news table needs to be added to schema. This is a placeholder implementation.
        
        Args:
            ticker: Company ticker symbol
            limit: Maximum number of articles to return
            agent_name: Name of agent making the request (for audit logging)
            user_query: User query text (for audit logging)
            
        Returns:
            Tuple of (news_list, DataStatus)
        """
        try:
            company = VFISDataAccess.get_company_by_ticker(ticker)
            if not company:
                return [], DataStatus.NO_DATA
            
            company_id = company['id']
            
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    # Check if news table exists (it will be added to schema)
                    cur.execute("""
                        SELECT EXISTS (
                            SELECT FROM information_schema.tables 
                            WHERE table_name = 'news'
                        );
                    """)
                    table_exists = cur.fetchone()[0]
                    
                    if not table_exists:
                        # News table not yet created, return NO_DATA
                        VFISDataAccess._log_audit(
                            agent_name=agent_name,
                            user_query=user_query,
                            tables_accessed=[],
                            status='NO_DATA',
                            details={'reason': 'News table does not exist', 'ticker': ticker}
                        )
                        return [], DataStatus.NO_DATA
                    
                    # Get news articles
                    cur.execute("""
                        SELECT id, headline, content, source_name, published_at, url, company_id
                        FROM news
                        WHERE company_id = %s
                        ORDER BY published_at DESC
                        LIMIT %s
                    """, (company_id, limit))
                    
                    articles = []
                    for row in cur.fetchall():
                        pub_date = row[4]
                        hours_old = None
                        if pub_date:
                            if isinstance(pub_date, date):
                                pub_datetime = datetime.combine(pub_date, datetime.min.time())
                            else:
                                pub_datetime = pub_date
                            hours_old = (datetime.now() - pub_datetime).total_seconds() / 3600
                        
                        articles.append({
                            'id': row[0],
                            'headline': row[1],
                            'content': row[2],
                            'source_name': row[3],
                            'published_at': pub_date.isoformat() if pub_date else None,
                            'url': row[5],
                            'hours_old': hours_old
                        })
                    
                    if not articles:
                        VFISDataAccess._log_audit(
                            agent_name=agent_name,
                            user_query=user_query,
                            tables_accessed=['news'],
                            status='NO_DATA',
                            details={'reason': 'No news articles found', 'ticker': ticker}
                        )
                        return [], DataStatus.NO_DATA
                    
                    # Check staleness (48 hours for news)
                    latest_article_hours_old = articles[0].get('hours_old')
                    status = DataStatus.SUCCESS
                    if latest_article_hours_old and latest_article_hours_old > NEWS_STALENESS_HOURS:
                        status = DataStatus.STALE_DATA
                    
                    VFISDataAccess._log_audit(
                        agent_name=agent_name,
                        user_query=user_query,
                        tables_accessed=['news'],
                        status=status.value,
                        details={'ticker': ticker, 'article_count': len(articles)}
                    )
                    
                    return articles, status
                    
        except Exception as e:
            logger.error(f"Error retrieving news for {ticker}: {e}")
            VFISDataAccess._log_audit(
                agent_name=agent_name,
                user_query=user_query,
                tables_accessed=['news'],
                status='ERROR',
                details={'error': str(e), 'ticker': ticker}
            )
            return [], DataStatus.ERROR
    
    @staticmethod
    def get_technical_indicators(
        ticker: str,
        indicator_name: Optional[str] = None,
        limit: int = 100,
        agent_name: Optional[str] = None,
        user_query: Optional[str] = None
    ) -> Tuple[List[Dict[str, Any]], DataStatus]:
        """
        Get technical indicators for a company.
        
        Note: technical_indicators table needs to be added to schema. This is a placeholder implementation.
        
        Args:
            ticker: Company ticker symbol
            indicator_name: Specific indicator name (optional)
            limit: Maximum number of records to return
            agent_name: Name of agent making the request (for audit logging)
            user_query: User query text (for audit logging)
            
        Returns:
            Tuple of (indicators_list, DataStatus)
        """
        try:
            company = VFISDataAccess.get_company_by_ticker(ticker)
            if not company:
                return [], DataStatus.NO_DATA
            
            company_id = company['id']
            
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    # Check if technical_indicators table exists
                    cur.execute("""
                        SELECT EXISTS (
                            SELECT FROM information_schema.tables 
                            WHERE table_name = 'technical_indicators'
                        );
                    """)
                    table_exists = cur.fetchone()[0]
                    
                    if not table_exists:
                        VFISDataAccess._log_audit(
                            agent_name=agent_name,
                            user_query=user_query,
                            tables_accessed=[],
                            status='NO_DATA',
                            details={'reason': 'Technical indicators table does not exist', 'ticker': ticker}
                        )
                        return [], DataStatus.NO_DATA
                    
                    # Get technical indicators
                    if indicator_name:
                        cur.execute("""
                            SELECT id, indicator_name, indicator_value, calculated_date, data_source_id
                            FROM technical_indicators
                            WHERE company_id = %s AND indicator_name = %s
                            ORDER BY calculated_date DESC
                            LIMIT %s
                        """, (company_id, indicator_name, limit))
                    else:
                        cur.execute("""
                            SELECT id, indicator_name, indicator_value, calculated_date, data_source_id
                            FROM technical_indicators
                            WHERE company_id = %s
                            ORDER BY calculated_date DESC
                            LIMIT %s
                        """, (company_id, limit))
                    
                    indicators = []
                    for row in cur.fetchall():
                        indicators.append({
                            'id': row[0],
                            'indicator_name': row[1],
                            'indicator_value': float(row[2]) if row[2] else None,
                            'calculated_date': row[3].isoformat() if row[3] else None,
                        })
                    
                    if not indicators:
                        VFISDataAccess._log_audit(
                            agent_name=agent_name,
                            user_query=user_query,
                            tables_accessed=['technical_indicators'],
                            status='NO_DATA',
                            details={'reason': 'No technical indicators found', 'ticker': ticker}
                        )
                        return [], DataStatus.NO_DATA
                    
                    VFISDataAccess._log_audit(
                        agent_name=agent_name,
                        user_query=user_query,
                        tables_accessed=['technical_indicators'],
                        status=DataStatus.SUCCESS.value,
                        details={'ticker': ticker, 'indicator_count': len(indicators)}
                    )
                    
                    return indicators, DataStatus.SUCCESS
                    
        except Exception as e:
            logger.error(f"Error retrieving technical indicators for {ticker}: {e}")
            VFISDataAccess._log_audit(
                agent_name=agent_name,
                user_query=user_query,
                tables_accessed=['technical_indicators'],
                status='ERROR',
                details={'error': str(e), 'ticker': ticker}
            )
            return [], DataStatus.ERROR
    
    @staticmethod
    def _log_audit(
        agent_name: Optional[str],
        user_query: Optional[str],
        tables_accessed: List[str],
        status: str,
        details: Dict[str, Any]
    ):
        """
        Log audit information for data access.
        
        Args:
            agent_name: Name of agent making the request
            user_query: User query text
            tables_accessed: List of table names accessed
            status: Status of the operation (SUCCESS, NO_DATA, STALE_DATA, ERROR)
            details: Additional details dictionary
        """
        try:
            log_data_access(
                event_type='data_access',
                entity_type='financial_data',
                entity_id=None,
                details={
                    'agent_name': agent_name,
                    'user_query': user_query,
                    'tables_accessed': tables_accessed,
                    'status': status,
                    **details
                },
                user_id=agent_name
            )
        except Exception as e:
            logger.warning(f"Failed to log audit: {e}")

    def count_rows(self, table_name: str) -> int:
        """
        Safe utility for row count checks.
        Read-only. No side effects.
        """
        if table_name not in {
            "document_assets",
            "parsed_tables",
            "quarterly_financials",
            "annual_reports",
            "news",
            "technical_indicators",
            "audit_logs",
        }:
            raise ValueError(f"Invalid table name: {table_name}")

        query = f"SELECT COUNT(*) FROM {table_name};"

        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query)
                return cur.fetchone()[0]

