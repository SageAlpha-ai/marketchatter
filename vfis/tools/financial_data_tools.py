"""
Financial Data Tools for Verified Financial Intelligence System.

CRITICAL: These tools retrieve data ONLY from PostgreSQL database.
LLMs MUST use these tools to access financial data - they MUST NEVER
generate, calculate, or estimate financial numbers.

This module uses the VFIS Data Access Layer (postgres_dal.py) which provides:
- Safe parameterized queries
- Source validation (NSE, BSE, SEBI only)
- Staleness detection
- Explicit status reporting (SUCCESS, NO_DATA, STALE_DATA, ERROR)
- Comprehensive audit logging
"""

from langchain_core.tools import tool
from typing import Annotated, Optional
import json

# Import VFIS Data Access Layer
from vfis.tools.postgres_dal import (
    VFISDataAccess,
    DataStatus
)


def _format_financial_data_for_llm(data: dict, status: DataStatus, statement_type: str = '') -> str:
    """
    Format financial data for LLM consumption with explicit status reporting.
    
    CRITICAL: This function ONLY formats data from the database.
    It does NOT generate, calculate, or estimate any financial numbers.
    
    Args:
        data: Dictionary containing financial data from database
        status: DataStatus indicating data quality
        statement_type: Type of statement (balance_sheet, income_statement, cashflow_statement)
        
    Returns:
        Formatted string for LLM consumption
    """
    if not data or status == DataStatus.NO_DATA:
        return f"STATUS: NO_DATA - No {statement_type or 'financial'} data available for {data.get('ticker', 'company')} in the database."
    
    lines = [
        f"# {statement_type.replace('_', ' ').title() if statement_type else 'Financial Data'} Report",
        f"**Company:** {data.get('company', 'Unknown')} ({data.get('ticker', 'N/A')})",
        "",
        f"**Status:** {status.value}",
        f"**Data Source:** {data.get('data_source', 'UNKNOWN')}",
        f"**Report Type:** {data.get('report_type', 'N/A').title()}",
        f"**Fiscal Year:** {data.get('fiscal_year', 'N/A')}",
    ]
    
    if data.get('quarter'):
        lines.append(f"**Quarter:** Q{data.get('quarter')}")
    
    lines.extend([
        f"**Report Date:** {data.get('report_date', 'N/A')}",
        f"**Filing Date:** {data.get('filing_date', 'N/A')}",
        f"**As-of Date:** {data.get('as_of_date', 'N/A')}",
    ])
    
    if data.get('days_old'):
        days_old = data.get('days_old')
        if status == DataStatus.STALE_DATA:
            lines.append(f"\n⚠️ **WARNING: DATA IS STALE** - Data is {days_old} days old (threshold: {120 if data.get('report_type') == 'quarterly' else 400} days)")
        else:
            lines.append(f"**Data Age:** {days_old} days")
    
    if data.get('source_url'):
        lines.append(f"**Source URL:** {data.get('source_url')}")
    
    lines.append("\n## Financial Metrics\n")
    
    # Format metrics as a table
    if data.get('metrics'):
        lines.append("| Metric | Value | Currency | As-of Date | Source |")
        lines.append("|--------|-------|----------|------------|--------|")
        for metric in data['metrics']:
            value_str = f"{metric['metric_value']:,.2f}" if metric.get('metric_value') is not None else "N/A"
            lines.append(
                f"| {metric['metric_name']} | {value_str} | "
                f"{metric.get('currency', 'INR')} | "
                f"{metric.get('as_of_date', 'N/A')} | "
                f"{metric.get('data_source', 'UNKNOWN')} |"
            )
    else:
        lines.append("No metrics available for this report.")
    
    return "\n".join(lines)


@tool
def get_fundamentals(
    ticker: Annotated[str, "ticker symbol"],
    curr_date: Annotated[str, "current date you are analyzing at, yyyy-mm-dd"],
) -> str:
    """
    Retrieve comprehensive fundamental data for a given ticker symbol from PostgreSQL database.
    
    CRITICAL RESTRICTIONS:
    - Data is sourced ONLY from verified sources: NSE, BSE, or SEBI
    - All financial numbers come directly from the database
    - LLM MUST NEVER generate, calculate, or estimate any financial values
    - LLM MUST only summarize the data returned by this tool
    
    Args:
        ticker (str): Ticker symbol of the company (dynamically provided)
        curr_date (str): Current date you are analyzing at, yyyy-mm-dd
        
    Returns:
        str: A formatted report containing comprehensive fundamental data with:
            - Status: SUCCESS, NO_DATA, STALE_DATA, or ERROR
            - Source attribution (NSE, BSE, or SEBI)
            - As-of dates for all metrics
            - Warnings if data is stale or unavailable
    """
    # Get balance sheet, income statement, and cash flow data
    balance_data, balance_status = VFISDataAccess.get_quarterly_financials(
        ticker=ticker,
        statement_type='balance_sheet',
        agent_name='VerifiedDataAgent',
        user_query=f"Get fundamentals for {ticker}"
    )
    
    income_data, income_status = VFISDataAccess.get_quarterly_financials(
        ticker=ticker,
        statement_type='income_statement',
        agent_name='VerifiedDataAgent',
        user_query=f"Get fundamentals for {ticker}"
    )
    
    cashflow_data, cashflow_status = VFISDataAccess.get_quarterly_financials(
        ticker=ticker,
        statement_type='cashflow_statement',
        agent_name='VerifiedDataAgent',
        user_query=f"Get fundamentals for {ticker}"
    )
    
    # Combine results
    lines = [
        "# Comprehensive Fundamental Data Report",
        f"**Company:** {ticker.upper()}",
        f"**Analysis Date:** {curr_date}",
        "",
    ]
    
    # Add balance sheet
    lines.append("\n## Balance Sheet\n")
    lines.append(_format_financial_data_for_llm(balance_data, balance_status, 'balance_sheet'))
    
    lines.append("\n---\n")
    
    # Add income statement
    lines.append("\n## Income Statement\n")
    lines.append(_format_financial_data_for_llm(income_data, income_status, 'income_statement'))
    
    lines.append("\n---\n")
    
    # Add cash flow
    lines.append("\n## Cash Flow Statement\n")
    lines.append(_format_financial_data_for_llm(cashflow_data, cashflow_status, 'cashflow_statement'))
    
    # Overall status
    overall_status = DataStatus.SUCCESS
    if balance_status == DataStatus.NO_DATA and income_status == DataStatus.NO_DATA and cashflow_status == DataStatus.NO_DATA:
        overall_status = DataStatus.NO_DATA
    elif balance_status == DataStatus.STALE_DATA or income_status == DataStatus.STALE_DATA or cashflow_status == DataStatus.STALE_DATA:
        overall_status = DataStatus.STALE_DATA
    
    lines.insert(2, f"**Overall Status:** {overall_status.value}\n")
    
    return "\n".join(lines)


@tool
def get_balance_sheet(
    ticker: Annotated[str, "ticker symbol"],
    freq: Annotated[str, "reporting frequency: annual/quarterly"] = "quarterly",
    curr_date: Annotated[Optional[str], "current date you are analyzing at, yyyy-mm-dd"] = None,
) -> str:
    """
    Retrieve balance sheet data for a given ticker symbol from PostgreSQL database.
    
    CRITICAL RESTRICTIONS:
    - Data is sourced ONLY from verified sources: NSE, BSE, or SEBI
    - All financial numbers come directly from the database
    - LLM MUST NEVER generate, calculate, or estimate any financial values
    - LLM MUST only summarize the data returned by this tool
    
    Args:
        ticker (str): Ticker symbol of the company (dynamically provided)
        freq (str): Reporting frequency: annual/quarterly (default quarterly)
        curr_date (str): Current date you are analyzing at, yyyy-mm-dd (optional)
        
    Returns:
        str: A formatted report containing balance sheet data with:
            - Status: SUCCESS, NO_DATA, STALE_DATA, or ERROR
            - Source attribution (NSE, BSE, or SEBI)
            - As-of dates for all metrics
            - Warnings if data is stale or unavailable
    """
    if freq == 'annual':
        data, status = VFISDataAccess.get_annual_financials(
            ticker=ticker,
            statement_type='balance_sheet',
            agent_name='VerifiedDataAgent',
            user_query=f"Get {freq} balance sheet for {ticker}"
        )
    else:
        data, status = VFISDataAccess.get_quarterly_financials(
            ticker=ticker,
            statement_type='balance_sheet',
            agent_name='VerifiedDataAgent',
            user_query=f"Get {freq} balance sheet for {ticker}"
        )
    
    return _format_financial_data_for_llm(data, status, 'balance_sheet')


@tool
def get_cashflow(
    ticker: Annotated[str, "ticker symbol"],
    freq: Annotated[str, "reporting frequency: annual/quarterly"] = "quarterly",
    curr_date: Annotated[Optional[str], "current date you are analyzing at, yyyy-mm-dd"] = None,
) -> str:
    """
    Retrieve cash flow statement data for a given ticker symbol from PostgreSQL database.
    
    CRITICAL RESTRICTIONS:
    - Data is sourced ONLY from verified sources: NSE, BSE, or SEBI
    - All financial numbers come directly from the database
    - LLM MUST NEVER generate, calculate, or estimate any financial values
    - LLM MUST only summarize the data returned by this tool
    
    Args:
        ticker (str): Ticker symbol of the company (dynamically provided)
        freq (str): Reporting frequency: annual/quarterly (default quarterly)
        curr_date (str): Current date you are analyzing at, yyyy-mm-dd (optional)
        
    Returns:
        str: A formatted report containing cash flow statement data with:
            - Status: SUCCESS, NO_DATA, STALE_DATA, or ERROR
            - Source attribution (NSE, BSE, or SEBI)
            - As-of dates for all metrics
            - Warnings if data is stale or unavailable
    """
    if freq == 'annual':
        data, status = VFISDataAccess.get_annual_financials(
            ticker=ticker,
            statement_type='cashflow_statement',
            agent_name='VerifiedDataAgent',
            user_query=f"Get {freq} cash flow for {ticker}"
        )
    else:
        data, status = VFISDataAccess.get_quarterly_financials(
            ticker=ticker,
            statement_type='cashflow_statement',
            agent_name='VerifiedDataAgent',
            user_query=f"Get {freq} cash flow for {ticker}"
        )
    
    return _format_financial_data_for_llm(data, status, 'cashflow_statement')


@tool
def get_income_statement(
    ticker: Annotated[str, "ticker symbol"],
    freq: Annotated[str, "reporting frequency: annual/quarterly"] = "quarterly",
    curr_date: Annotated[Optional[str], "current date you are analyzing at, yyyy-mm-dd"] = None,
) -> str:
    """
    Retrieve income statement data for a given ticker symbol from PostgreSQL database.
    
    CRITICAL RESTRICTIONS:
    - Data is sourced ONLY from verified sources: NSE, BSE, or SEBI
    - All financial numbers come directly from the database
    - LLM MUST NEVER generate, calculate, or estimate any financial values
    - LLM MUST only summarize the data returned by this tool
    
    Args:
        ticker (str): Ticker symbol of the company (dynamically provided)
        freq (str): Reporting frequency: annual/quarterly (default quarterly)
        curr_date (str): Current date you are analyzing at, yyyy-mm-dd (optional)
        
    Returns:
        str: A formatted report containing income statement data with:
            - Status: SUCCESS, NO_DATA, STALE_DATA, or ERROR
            - Source attribution (NSE, BSE, or SEBI)
            - As-of dates for all metrics
            - Warnings if data is stale or unavailable
    """
    if freq == 'annual':
        data, status = VFISDataAccess.get_annual_financials(
            ticker=ticker,
            statement_type='income_statement',
            agent_name='VerifiedDataAgent',
            user_query=f"Get {freq} income statement for {ticker}"
        )
    else:
        data, status = VFISDataAccess.get_quarterly_financials(
            ticker=ticker,
            statement_type='income_statement',
            agent_name='VerifiedDataAgent',
            user_query=f"Get {freq} income statement for {ticker}"
        )
    
    return _format_financial_data_for_llm(data, status, 'income_statement')
