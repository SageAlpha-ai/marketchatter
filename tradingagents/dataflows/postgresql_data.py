"""PostgreSQL-based data retrieval for Verified Financial Data AI System."""
import json
from typing import Dict, Any, Optional
from datetime import datetime
from tradingagents.database.dal import FinancialDataAccess
from tradingagents.database.audit import log_data_access

def format_financial_data_for_llm(data: Dict[str, Any], staleness_msg: Optional[str] = None) -> str:
    """Format financial data for LLM consumption with source attribution."""
    if not data:
        return "No financial data available."
    
    lines = [
        f"# Financial Data Report for {data.get('company', 'Unknown')} ({data.get('ticker', 'N/A')})",
        "",
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
    
    if data.get('source_url'):
        lines.append(f"**Source URL:** {data.get('source_url')}")
    
    if staleness_msg:
        lines.append(f"\n⚠️ **{staleness_msg}**\n")
    
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


def get_balance_sheet_postgresql(
    ticker: str,
    freq: str = "quarterly",
    curr_date: Optional[str] = None
) -> str:
    """
    Retrieve balance sheet data from PostgreSQL database.
    Only returns verified data from NSE, BSE, or SEBI sources.
    """
    try:
        fiscal_year = None
        quarter = None
        
        # Parse date if provided to determine fiscal year/quarter
        if curr_date:
            try:
                trade_date = datetime.strptime(curr_date, "%Y-%m-%d")
                # For Indian companies, fiscal year typically runs April to March
                # Q1: Apr-Jun, Q2: Jul-Sep, Q3: Oct-Dec, Q4: Jan-Mar
                if trade_date.month >= 4:
                    fiscal_year = trade_date.year
                else:
                    fiscal_year = trade_date.year - 1
            except ValueError:
                pass  # Use latest if date parsing fails
        
        data, status, staleness_msg = FinancialDataAccess.get_balance_sheet(
            ticker=ticker,
            report_type=freq,
            fiscal_year=fiscal_year,
            quarter=quarter
        )
        
        formatted = format_financial_data_for_llm(data, staleness_msg)
        return formatted
        
    except Exception as e:
        error_msg = f"Error retrieving balance sheet for {ticker}: {str(e)}"
        log_data_access('data_retrieval', 'balance_sheet', None,
                      {'ticker': ticker, 'error': str(e)})
        return f"ERROR: {error_msg}"


def get_income_statement_postgresql(
    ticker: str,
    freq: str = "quarterly",
    curr_date: Optional[str] = None
) -> str:
    """
    Retrieve income statement data from PostgreSQL database.
    Only returns verified data from NSE, BSE, or SEBI sources.
    """
    try:
        fiscal_year = None
        quarter = None
        
        if curr_date:
            try:
                trade_date = datetime.strptime(curr_date, "%Y-%m-%d")
                if trade_date.month >= 4:
                    fiscal_year = trade_date.year
                else:
                    fiscal_year = trade_date.year - 1
            except ValueError:
                pass
        
        data, status, staleness_msg = FinancialDataAccess.get_income_statement(
            ticker=ticker,
            report_type=freq,
            fiscal_year=fiscal_year,
            quarter=quarter
        )
        
        formatted = format_financial_data_for_llm(data, staleness_msg)
        return formatted
        
    except Exception as e:
        error_msg = f"Error retrieving income statement for {ticker}: {str(e)}"
        log_data_access('data_retrieval', 'income_statement', None,
                      {'ticker': ticker, 'error': str(e)})
        return f"ERROR: {error_msg}"


def get_cashflow_postgresql(
    ticker: str,
    freq: str = "quarterly",
    curr_date: Optional[str] = None
) -> str:
    """
    Retrieve cash flow statement data from PostgreSQL database.
    Only returns verified data from NSE, BSE, or SEBI sources.
    """
    try:
        fiscal_year = None
        quarter = None
        
        if curr_date:
            try:
                trade_date = datetime.strptime(curr_date, "%Y-%m-%d")
                if trade_date.month >= 4:
                    fiscal_year = trade_date.year
                else:
                    fiscal_year = trade_date.year - 1
            except ValueError:
                pass
        
        data, status, staleness_msg = FinancialDataAccess.get_cashflow_statement(
            ticker=ticker,
            report_type=freq,
            fiscal_year=fiscal_year,
            quarter=quarter
        )
        
        formatted = format_financial_data_for_llm(data, staleness_msg)
        return formatted
        
    except Exception as e:
        error_msg = f"Error retrieving cash flow statement for {ticker}: {str(e)}"
        log_data_access('data_retrieval', 'cashflow_statement', None,
                      {'ticker': ticker, 'error': str(e)})
        return f"ERROR: {error_msg}"


def get_fundamentals_postgresql(
    ticker: str,
    curr_date: Optional[str] = None
) -> str:
    """
    Retrieve comprehensive fundamental data from PostgreSQL database.
    Combines balance sheet, income statement, and cash flow data.
    Only returns verified data from NSE, BSE, or SEBI sources.
    """
    try:
        # Get available reports
        reports = FinancialDataAccess.get_available_reports(ticker)
        
        # Get latest quarterly data (returns 3-tuple: data, status, stale_msg)
        balance_data, _, balance_stale = FinancialDataAccess.get_balance_sheet(
            ticker=ticker, report_type='quarterly'
        )
        income_data, _, income_stale = FinancialDataAccess.get_income_statement(
            ticker=ticker, report_type='quarterly'
        )
        cashflow_data, _, cashflow_stale = FinancialDataAccess.get_cashflow_statement(
            ticker=ticker, report_type='quarterly'
        )
        
        lines = [
            "# Comprehensive Fundamental Data Report",
            f"**Company:** {balance_data.get('company', 'Unknown')} ({ticker})",
            "",
            "## Available Reports",
        ]
        
        if reports['annual']:
            lines.append("\n### Annual Reports Available:")
            for report in reports['annual'][:5]:  # Show last 5
                lines.append(
                    f"- FY {report['fiscal_year']}: "
                    f"Report Date: {report['report_date']}, "
                    f"Source: {report.get('source', 'UNKNOWN')}"
                )
        
        if reports['quarterly']:
            lines.append("\n### Quarterly Reports Available:")
            for report in reports['quarterly'][:8]:  # Show last 8
                lines.append(
                    f"- FY {report['fiscal_year']} Q{report['quarter']}: "
                    f"Report Date: {report['report_date']}, "
                    f"Source: {report.get('source', 'UNKNOWN')}"
                )
        
        lines.append("\n---\n")
        
        # Add balance sheet summary
        if balance_data:
            lines.append("\n## Balance Sheet Summary")
            staleness_note = f"\n⚠️ {balance_stale}\n" if balance_stale else ""
            lines.append(staleness_note)
            lines.append(format_financial_data_for_llm(balance_data, None))
        
        lines.append("\n---\n")
        
        # Add income statement summary
        if income_data:
            lines.append("\n## Income Statement Summary")
            staleness_note = f"\n⚠️ {income_stale}\n" if income_stale else ""
            lines.append(staleness_note)
            lines.append(format_financial_data_for_llm(income_data, None))
        
        lines.append("\n---\n")
        
        # Add cash flow summary
        if cashflow_data:
            lines.append("\n## Cash Flow Statement Summary")
            staleness_note = f"\n⚠️ {cashflow_stale}\n" if cashflow_stale else ""
            lines.append(staleness_note)
            lines.append(format_financial_data_for_llm(cashflow_data, None))
        
        if not balance_data and not income_data and not cashflow_data:
            return f"ERROR: No fundamental data available for {ticker} in the database."
        
        return "\n".join(lines)
        
    except Exception as e:
        error_msg = f"Error retrieving fundamentals for {ticker}: {str(e)}"
        log_data_access('data_retrieval', 'fundamentals', None,
                      {'ticker': ticker, 'error': str(e)})
        return f"ERROR: {error_msg}"

