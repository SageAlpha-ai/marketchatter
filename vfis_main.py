"""
Main entry point for Verified Financial Intelligence System (VFIS).

This script demonstrates how to use VFIS to retrieve and summarize
financial data. NO trading logic is included.

CRITICAL: Ticker is configurable via environment variable or command line argument.
No hardcoded tickers are used.

Usage:
    # Use environment variable
    VFIS_TICKER=AAPL python vfis_main.py
    
    # Use command line argument
    python vfis_main.py --ticker AAPL
    
    # Uses ACTIVE_TICKERS env var if set, otherwise prompts for input
    python vfis_main.py
"""
import argparse
import os
import sys
from datetime import date
from pathlib import Path

# Ensure project root is in path
project_root = Path(__file__).resolve().parent
sys.path.insert(0, str(project_root))


def get_ticker_from_args_or_env() -> str:
    """
    Get ticker symbol from command line args or environment variable.
    
    Priority:
    1. --ticker command line argument
    2. VFIS_TICKER environment variable
    3. First ticker from ACTIVE_TICKERS environment variable
    4. User input (interactive)
    
    Returns:
        Ticker symbol in uppercase
    
    Raises:
        SystemExit if no ticker provided in non-interactive mode
    """
    # Parse command line args
    parser = argparse.ArgumentParser(
        description="VFIS Financial Intelligence System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python vfis_main.py --ticker AAPL
    python vfis_main.py --ticker MSFT --query "Get balance sheet"
    VFIS_TICKER=GOOGL python vfis_main.py
        """
    )
    parser.add_argument(
        "--ticker",
        type=str,
        default=None,
        help="Stock ticker symbol (e.g., AAPL, MSFT, GOOGL)"
    )
    parser.add_argument(
        "--query",
        type=str,
        default=None,
        help="Optional query for analysis"
    )
    
    args = parser.parse_args()
    
    # Priority 1: Command line argument
    if args.ticker:
        return args.ticker.upper(), args.query
    
    # Priority 2: VFIS_TICKER environment variable
    vfis_ticker = os.getenv("VFIS_TICKER", "").strip()
    if vfis_ticker:
        return vfis_ticker.upper(), args.query
    
    # Priority 3: First ticker from ACTIVE_TICKERS
    active_tickers = os.getenv("ACTIVE_TICKERS", "").strip()
    if active_tickers:
        first_ticker = active_tickers.split(",")[0].strip()
        if first_ticker:
            print(f"Using first ticker from ACTIVE_TICKERS: {first_ticker}")
            return first_ticker.upper(), args.query
    
    # Priority 4: Interactive input (if terminal is available)
    if sys.stdin.isatty():
        ticker = input("Enter ticker symbol (e.g., AAPL): ").strip().upper()
        if ticker:
            return ticker, args.query
    
    # No ticker provided
    print("ERROR: No ticker symbol provided.")
    print("Usage: python vfis_main.py --ticker SYMBOL")
    print("   or: VFIS_TICKER=SYMBOL python vfis_main.py")
    print("   or: Set ACTIVE_TICKERS environment variable")
    sys.exit(1)


def main():
    """Main function to demonstrate VFIS usage."""
    # Import bootstrap and initialize system FIRST
    from vfis.bootstrap import bootstrap
    
    print("=" * 60)
    print("Verified Financial Intelligence System (VFIS)")
    print("=" * 60)
    
    # Bootstrap the system (loads env, initializes DB, starts scheduler)
    result = bootstrap(start_scheduler=True, fail_fast=True)
    
    if not result.success:
        print(f"Bootstrap failed: {result.errors}")
        sys.exit(1)
    
    # Get ticker from args/env (no hardcoded default)
    company_ticker, query = get_ticker_from_args_or_env()
    analysis_date = date.today()
    
    print(f"\nAnalyzing financial data for {company_ticker} as of {analysis_date}...")
    print("=" * 60)
    
    # Import VFIS system after bootstrap
    from vfis.vfis_system import create_vfis_system
    from tradingagents.default_config import DEFAULT_CONFIG
    
    # Create configuration
    config = DEFAULT_CONFIG.copy()
    
    # Create VFIS system (uses Azure OpenAI from environment variables)
    vfis = create_vfis_system(
        config=config,
        llm_provider="azure",
        debug=True
    )
    
    # Get summary
    summary = vfis.get_summary(company_ticker, analysis_date)
    
    print("\nFinancial Data Summary:")
    print("=" * 60)
    print(summary)
    print("=" * 60)
    
    # Run custom query if provided
    if query:
        print(f"\n\nCustom Query Analysis: {query}")
        print("=" * 60)
        result = vfis.analyze_company(
            company_ticker=company_ticker,
            analysis_date=analysis_date,
            query=query
        )
        print(result["summary"])
    else:
        # Default query-based analysis
        print("\n\nQuery-based Analysis:")
        print("=" * 60)
        result = vfis.analyze_company(
            company_ticker=company_ticker,
            analysis_date=analysis_date,
            query="Get balance sheet data for the latest quarter"
        )
        print(result["summary"])


if __name__ == "__main__":
    main()
