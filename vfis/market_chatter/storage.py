"""
Database storage layer for market chatter.

This module provides safe, production-grade storage with:
- Automatic table creation if missing
- Idempotent inserts (ON CONFLICT DO NOTHING)
- Consistent return types
- Structured logging for observability
"""

import logging
import json
from typing import List, Dict, Optional, Any, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)


def _ensure_db_initialized():
    """
    Ensure database is initialized. Safe to call multiple times.
    
    NOTE: This assumes bootstrap() has already been called.
    Environment should already be loaded by vfis.bootstrap.
    """
    try:
        from tradingagents.database.connection import init_database
        # Don't call load_dotenv here - env should already be loaded by bootstrap
        init_database(config={})
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise


def _ensure_table_exists() -> bool:
    """Ensure market_chatter table exists. Returns True if successful."""
    try:
        from tradingagents.database.chatter_dal import ensure_market_chatter_table
        return ensure_market_chatter_table()
    except Exception as e:
        logger.error(f"Failed to ensure market_chatter table: {e}")
        return False


class MarketChatterStorage:
    """
    Storage layer for market chatter data.
    
    Provides safe, idempotent operations with automatic table creation
    and consistent error handling.
    """
    
    def __init__(self):
        """Initialize storage with database connection."""
        _ensure_db_initialized()
    
    def store_chatter(
        self,
        ticker: str,
        company_name: str,
        chatter_items: List[Dict]
    ) -> Dict[str, int]:
        """
        Store market chatter items in database.
        
        Uses persist_market_chatter for idempotent storage via (source, source_id).
        
        Args:
            ticker: Stock ticker symbol
            company_name: Company name
            chatter_items: List of chatter items with sentiment analysis
            
        Returns:
            Dictionary with counts: {"inserted": int, "skipped": int, "errors": int}
        """
        logger.info(f"[STORAGE] Storing {len(chatter_items)} chatter items for {ticker}")
        
        if not chatter_items:
            logger.info(f"[STORAGE] No items to store for {ticker}")
            return {"inserted": 0, "skipped": 0, "errors": 0, "total": 0}
        
        try:
            from tradingagents.dataflows.chatter_schema import MarketChatterRecord, normalize_chatter_item
            from tradingagents.database.chatter_persist import persist_market_chatter
            import hashlib
            
            # Convert items to MarketChatterRecord
            records = []
            for item in chatter_items:
                # Ensure required fields
                source = item.get("source", "unknown")
                url = item.get("url", "")
                content = item.get("content", item.get("summary", ""))
                
                # Generate source_id from URL or content
                if url:
                    source_id = hashlib.sha256(url.encode()).hexdigest()[:32]
                else:
                    hash_input = f"{ticker}:{source}:{content[:100]}"
                    source_id = hashlib.sha256(hash_input.encode()).hexdigest()[:32]
                
                record = MarketChatterRecord(
                    ticker=ticker,
                    source=source,
                    source_id=source_id,
                    title=item.get("title"),
                    summary=content,
                    url=url,
                    published_at=item.get("published_at"),
                    sentiment_score=item.get("sentiment_score"),
                    sentiment_label=item.get("sentiment_label"),
                    confidence=item.get("confidence"),
                    source_type=item.get("source_type", "news"),
                    company_name=company_name,
                    raw_payload=item.get("raw", item.get("raw_payload"))
                )
                records.append(record)
            
            # Persist using centralized function
            counts = persist_market_chatter(records)
            
            logger.info(
                f"[STORAGE] Complete for {ticker}: "
                f"inserted={counts['inserted']}, skipped={counts['skipped']}, errors={counts['errors']}"
            )
            
            return counts
            
        except Exception as e:
            logger.error(f"[STORAGE] Database error: {e}", exc_info=True)
            return {"inserted": 0, "skipped": 0, "errors": len(chatter_items), "total": len(chatter_items)}
    
    def get_recent_chatter(
        self,
        ticker: str,
        days: int = 7,
        limit: int = 100
    ) -> Dict[str, Any]:
        """
        Retrieve recent market chatter for a ticker.
        
        SAFE: Never throws. Returns dictionary with items/count/sources even if empty.
        
        Args:
            ticker: Stock ticker symbol
            days: Number of days to look back
            limit: Maximum number of records to return
            
        Returns:
            Dictionary with consistent shape:
            {
                "items": List[dict],
                "count": int,
                "sources": Dict[str, int],
                "window_days": int,
                "status": str,
                "message": str
            }
        """
        try:
            from tradingagents.database.chatter_dal import get_recent_chatter
            return get_recent_chatter(ticker, days=days, limit=limit)
        except Exception as e:
            logger.error(f"[STORAGE] Error retrieving chatter: {e}")
            return {
                "items": [],
                "count": 0,
                "sources": {},
                "window_days": days,
                "status": "error",
                "message": str(e)
            }
    
    def get_chatter_summary(
        self,
        ticker: str,
        days: int = 7
    ) -> Dict[str, Any]:
        """
        Get a summary of market chatter for a ticker.
        
        SAFE: Never throws. Returns empty summary if no data.
        
        Returns:
            Summary dictionary with counts, sources, sentiment distribution
        """
        try:
            from tradingagents.database.chatter_dal import get_chatter_summary
            return get_chatter_summary(ticker, days=days)
        except Exception as e:
            logger.error(f"[STORAGE] Error getting summary: {e}")
            return {
                "ticker": ticker,
                "status": "error",
                "message": str(e),
                "has_data": False,
                "total_count": 0,
                "sources": [],
                "items": []
            }


# Convenience function for backward compatibility
def store_chatter(ticker: str, company_name: str, items: List[Dict]) -> Dict[str, int]:
    """Store chatter items. Convenience wrapper around MarketChatterStorage."""
    storage = MarketChatterStorage()
    return storage.store_chatter(ticker, company_name, items)


def get_recent_chatter(ticker: str, days: int = 7, limit: int = 100) -> Dict[str, Any]:
    """Get recent chatter. Convenience wrapper around MarketChatterStorage."""
    storage = MarketChatterStorage()
    return storage.get_recent_chatter(ticker, days, limit)
