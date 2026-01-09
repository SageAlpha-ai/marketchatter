"""
VFIS Ingestion Module - Centralized Data Ingestion.

This module provides the SINGLE entrypoint for all market chatter ingestion.
All ingestion MUST go through this module to ensure:
- Consistent schema usage (MarketChatterRecord)
- Single persistence path (chatter_persist.py)
- No hardcoded tickers
- Proper error handling and logging

Canonical Entrypoints:
    - ingest_ticker(): Ingest chatter for a single ticker
    - ingest_tickers(): Ingest chatter for multiple tickers
    - ensure_ticker_ingested(): Ensure ticker has been ingested (on-demand)
    
CRITICAL: Never hardcode ticker symbols. All tickers must be provided dynamically.
"""

from typing import Dict, Any, List, Optional
import logging

logger = logging.getLogger(__name__)


def ingest_ticker(
    ticker: str,
    company_name: Optional[str] = None,
    days: int = 7,
    sources: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Ingest market chatter for a single ticker.
    
    This is the CANONICAL function for single-ticker ingestion.
    
    Args:
        ticker: Stock ticker symbol (e.g., 'AAPL', 'MSFT')
        company_name: Optional company name for broader search
        days: Number of days to look back (default: 7)
        sources: Optional list of sources ['rss', 'alpha_vantage']
    
    Returns:
        Standard result dict:
        {
            "data": {"ticker": str, "fetched": int, "inserted": int, ...},
            "status": "success" | "no_data" | "error",
            "message": Optional[str]
        }
    """
    from vfis.ingestion.scheduler import ingest_for_tickers
    
    ticker = ticker.upper()
    
    try:
        result = ingest_for_tickers([ticker], days=days)
        
        # Get ticker-specific result
        ticker_result = result.get("ticker_results", {}).get(ticker, {})
        
        # Determine status
        if result.get("total_errors", 0) > 0:
            status = "error"
            message = f"Ingestion completed with errors: {result.get('total_errors')} errors"
        elif result.get("total_fetched", 0) == 0:
            status = "no_data"
            message = f"No data found for {ticker} from any source"
        else:
            status = "success"
            message = f"Ingested {result.get('total_inserted', 0)} new records for {ticker}"
        
        return {
            "data": {
                "ticker": ticker,
                "fetched": result.get("total_fetched", 0),
                "inserted": result.get("total_inserted", 0),
                "skipped": result.get("total_skipped", 0),
                "errors": result.get("total_errors", 0),
                "sources_used": result.get("sources_used", []),
                "ticker_results": ticker_result
            },
            "status": status,
            "message": message
        }
        
    except Exception as e:
        logger.error(f"[INGEST] Error ingesting {ticker}: {e}", exc_info=True)
        return {
            "data": {
                "ticker": ticker,
                "fetched": 0,
                "inserted": 0,
                "skipped": 0,
                "errors": 1
            },
            "status": "error",
            "message": str(e)
        }


def ingest_tickers(
    tickers: List[str],
    days: int = 7,
    sources: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Ingest market chatter for multiple tickers.
    
    This is the CANONICAL function for batch ticker ingestion.
    
    Args:
        tickers: List of ticker symbols (dynamic, not hardcoded)
        days: Number of days to look back (default: 7)
        sources: Optional list of sources to use
    
    Returns:
        Standard result dict:
        {
            "data": {"tickers": list, "total_fetched": int, ...},
            "status": "success" | "partial" | "error",
            "message": Optional[str]
        }
    """
    from vfis.ingestion.scheduler import ingest_for_tickers
    
    if not tickers:
        return {
            "data": {"tickers": [], "total_fetched": 0, "total_inserted": 0},
            "status": "no_data",
            "message": "No tickers provided for ingestion"
        }
    
    # Normalize tickers
    tickers = [t.upper() for t in tickers]
    
    try:
        result = ingest_for_tickers(tickers, days=days)
        
        # Determine status
        total_errors = result.get("total_errors", 0)
        total_fetched = result.get("total_fetched", 0)
        total_inserted = result.get("total_inserted", 0)
        
        if total_errors > 0 and total_inserted == 0:
            status = "error"
            message = f"Ingestion failed for all tickers: {total_errors} errors"
        elif total_errors > 0:
            status = "partial"
            message = f"Ingestion partially successful: {total_inserted} inserted, {total_errors} errors"
        elif total_fetched == 0:
            status = "no_data"
            message = f"No data found for any of {len(tickers)} tickers"
        else:
            status = "success"
            message = f"Ingested {total_inserted} new records for {len(tickers)} tickers"
        
        return {
            "data": {
                "tickers": tickers,
                "total_fetched": total_fetched,
                "total_inserted": total_inserted,
                "total_skipped": result.get("total_skipped", 0),
                "total_errors": total_errors,
                "sources_used": result.get("sources_used", []),
                "ticker_results": result.get("ticker_results", {})
            },
            "status": status,
            "message": message
        }
        
    except Exception as e:
        logger.error(f"[INGEST] Error ingesting tickers {tickers}: {e}", exc_info=True)
        return {
            "data": {
                "tickers": tickers,
                "total_fetched": 0,
                "total_inserted": 0,
                "total_errors": 1
            },
            "status": "error",
            "message": str(e)
        }


def ensure_ticker_ingested(ticker: str, days: int = 7) -> Dict[str, Any]:
    """
    Ensure a ticker has been ingested.
    
    Checks if ticker was already ingested this session. If not, runs ingestion.
    Use this for on-demand ingestion before queries.
    
    Args:
        ticker: Ticker symbol to ensure is ingested
        days: Days to look back if ingestion is needed
    
    Returns:
        Standard result dict:
        {
            "data": {"ticker": str, "already_ingested": bool, ...},
            "status": "success" | "error",
            "message": str
        }
    """
    from vfis.ingestion.scheduler import is_ticker_ingested, ingest_ticker_if_missing
    
    ticker = ticker.upper()
    
    try:
        if is_ticker_ingested(ticker):
            return {
                "data": {
                    "ticker": ticker,
                    "already_ingested": True,
                    "inserted": 0
                },
                "status": "success",
                "message": f"Ticker {ticker} already ingested this session"
            }
        
        # Ingest if missing
        result = ingest_ticker_if_missing(ticker, days=days)
        
        if result is None:
            return {
                "data": {
                    "ticker": ticker,
                    "already_ingested": True,
                    "inserted": 0
                },
                "status": "success",
                "message": f"Ticker {ticker} already ingested this session"
            }
        
        return {
            "data": {
                "ticker": ticker,
                "already_ingested": False,
                "fetched": result.get("total_fetched", 0),
                "inserted": result.get("total_inserted", 0),
                "errors": result.get("total_errors", 0)
            },
            "status": "success" if result.get("total_errors", 0) == 0 else "error",
            "message": f"Ingested {result.get('total_inserted', 0)} new records for {ticker}"
        }
        
    except Exception as e:
        logger.error(f"[INGEST] Error ensuring {ticker} is ingested: {e}", exc_info=True)
        return {
            "data": {
                "ticker": ticker,
                "already_ingested": False,
                "errors": 1
            },
            "status": "error",
            "message": str(e)
        }


def get_active_tickers() -> Dict[str, Any]:
    """
    Get list of active tickers for ingestion.
    
    Discovers tickers from:
    1. ACTIVE_TICKERS environment variable
    2. companies table in database
    
    NO hardcoded fallback - returns empty list if no tickers found.
    
    Returns:
        Standard result dict:
        {
            "data": {"tickers": list, "source": str},
            "status": "success" | "no_data",
            "message": str
        }
    """
    from vfis.ingestion.scheduler import get_active_tickers as _get_active_tickers
    
    try:
        tickers = _get_active_tickers()
        
        if not tickers:
            return {
                "data": {"tickers": [], "source": "none"},
                "status": "no_data",
                "message": "No active tickers found. Set ACTIVE_TICKERS env var or add companies to database."
            }
        
        # Determine source using canonical env
        from vfis.core.env import ACTIVE_TICKERS as env_ticker_list
        source = "environment" if env_ticker_list else "database"
        
        return {
            "data": {"tickers": tickers, "source": source, "count": len(tickers)},
            "status": "success",
            "message": f"Found {len(tickers)} active tickers from {source}"
        }
        
    except Exception as e:
        logger.error(f"[INGEST] Error getting active tickers: {e}", exc_info=True)
        return {
            "data": {"tickers": [], "source": "error"},
            "status": "error",
            "message": str(e)
        }


# Export all canonical functions
__all__ = [
    'ingest_ticker',
    'ingest_tickers',
    'ensure_ticker_ingested',
    'get_active_tickers',
]
