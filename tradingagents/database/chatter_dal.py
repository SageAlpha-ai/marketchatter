"""
Data Access Layer for Market Chatter.

ALL DAL methods return the standard contract:
{
    "data": Any,
    "status": "success" | "no_data" | "error",
    "message": Optional[str]
}

NEVER throws exceptions to callers. Always returns dict.
"""

import logging
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any

from .connection import get_db_connection
from .chatter_persist import ensure_market_chatter_table, persist_market_chatter

logger = logging.getLogger(__name__)


def _make_response(
    data: Any,
    status: str,
    message: Optional[str] = None
) -> Dict[str, Any]:
    """Create standard DAL response dict."""
    return {
        "data": data,
        "status": status,
        "message": message
    }


def _table_exists(cursor, table_name: str) -> bool:
    """Check if a table exists in the database."""
    try:
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = %s
            );
        """, (table_name,))
        result = cursor.fetchone()
        return result[0] if result else False
    except Exception as e:
        logger.warning(f"Error checking table existence: {e}")
        return False


def get_recent_chatter(
    ticker: str,
    days: int = 7,
    limit: int = 100,
    source: Optional[str] = None
) -> Dict[str, Any]:
    """
    Retrieve recent market chatter for a ticker.
    
    SAFE: Never throws. Returns standard dict contract.
    
    Args:
        ticker: Stock ticker symbol (e.g., 'AAPL', 'MSFT')
        days: Number of days to look back (default: 7)
        limit: Maximum number of records (default: 100)
        source: Optional filter by source (e.g., 'alpha_vantage', 'rss')
    
    Returns:
        Standard DAL response:
        {
            "data": {
                "items": List[dict],
                "count": int,
                "sources": Dict[str, int],
                "window_days": int
            },
            "status": "success" | "no_data" | "error",
            "message": str
        }
    """
    ticker = ticker.upper()
    
    # Default data structure
    default_data = {
        "items": [],
        "count": 0,
        "sources": {},
        "window_days": days,
        "ticker": ticker
    }
    
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Check/create table
                if not _table_exists(cur, 'market_chatter'):
                    logger.info("market_chatter table missing, creating...")
                    ensure_market_chatter_table()
                    return _make_response(
                        default_data,
                        "no_data",
                        f"No market chatter data for {ticker} (table just created)"
                    )
                
                # Build query
                query = """
                    SELECT 
                        id, ticker, source, source_id, title,
                        COALESCE(summary, content) as summary, url,
                        published_at, sentiment_score, sentiment_label,
                        confidence, source_type, company_name,
                        created_at, raw_payload
                    FROM market_chatter
                    WHERE ticker = %s 
                      AND published_at >= NOW() - INTERVAL '%s days'
                """
                params: List[Any] = [ticker, days]
                
                if source:
                    query += " AND source = %s"
                    params.append(source)
                
                query += " ORDER BY published_at DESC LIMIT %s"
                params.append(limit)
                
                cur.execute(query, params)
                rows = cur.fetchall()
                
                if not rows:
                    return _make_response(
                        default_data,
                        "no_data",
                        f"No market chatter found for {ticker} in last {days} days"
                    )
                
                # Parse results
                items = []
                sources_count: Dict[str, int] = {}
                
                for row in rows:
                    try:
                        item = {
                            "id": row[0],
                            "ticker": row[1],
                            "source": row[2],
                            "source_id": row[3],
                            "title": row[4],
                            "summary": row[5],
                            "url": row[6],
                            "published_at": row[7].isoformat() if row[7] else None,
                            "sentiment_score": float(row[8]) if row[8] is not None else None,
                            "sentiment_label": row[9],
                            "confidence": float(row[10]) if row[10] is not None else None,
                            "source_type": row[11],
                            "company_name": row[12],
                            "created_at": row[13].isoformat() if row[13] else None,
                            "raw_payload": json.loads(row[14]) if row[14] else None
                        }
                        items.append(item)
                        
                        # Count by source
                        src = row[2] or "unknown"
                        sources_count[src] = sources_count.get(src, 0) + 1
                        
                    except Exception as parse_error:
                        logger.warning(f"Error parsing row {row[0]}: {parse_error}")
                        continue
                
                result_data = {
                    "items": items,
                    "count": len(items),
                    "sources": sources_count,
                    "window_days": days,
                    "ticker": ticker
                }
                
                return _make_response(
                    result_data,
                    "success",
                    f"Found {len(items)} chatter items for {ticker}"
                )
                
    except Exception as e:
        logger.error(f"Error retrieving market chatter for {ticker}: {e}", exc_info=True)
        return _make_response(
            default_data,
            "error",
            f"Error retrieving chatter: {str(e)}"
        )


def get_chatter_summary(ticker: str, days: int = 7) -> Dict[str, Any]:
    """
    Get a summary of market chatter suitable for agent consumption.
    
    SAFE: Never throws. Returns standard dict contract.
    
    Returns:
        Standard DAL response with summary data
    """
    ticker = ticker.upper()
    
    # Default summary
    default_summary = {
        "ticker": ticker,
        "total_count": 0,
        "window_days": days,
        "sources": {},
        "sentiment_distribution": {},
        "average_sentiment": None,
        "newest_item_date": None,
        "oldest_item_date": None,
        "items": [],
        "has_data": False
    }
    
    try:
        # Get recent chatter
        chatter_response = get_recent_chatter(ticker, days=days, limit=200)
        
        if chatter_response["status"] != "success":
            return _make_response(
                default_summary,
                chatter_response["status"],
                chatter_response["message"]
            )
        
        chatter_data = chatter_response["data"]
        items = chatter_data.get("items", [])
        
        if not items:
            return _make_response(
                default_summary,
                "no_data",
                f"No market chatter for {ticker} in last {days} days"
            )
        
        # Calculate sentiment distribution and average
        sentiment_dist: Dict[str, int] = {}
        sentiment_scores = []
        
        for item in items:
            label = item.get("sentiment_label")
            if label:
                sentiment_dist[label] = sentiment_dist.get(label, 0) + 1
            
            score = item.get("sentiment_score")
            if score is not None:
                sentiment_scores.append(score)
        
        avg_sentiment = sum(sentiment_scores) / len(sentiment_scores) if sentiment_scores else None
        
        # Get date range
        dates = [item.get("published_at") for item in items if item.get("published_at")]
        newest = max(dates) if dates else None
        oldest = min(dates) if dates else None
        
        summary = {
            "ticker": ticker,
            "total_count": len(items),
            "window_days": days,
            "sources": chatter_data.get("sources", {}),
            "sentiment_distribution": sentiment_dist,
            "average_sentiment": round(avg_sentiment, 4) if avg_sentiment else None,
            "newest_item_date": newest,
            "oldest_item_date": oldest,
            "items": items[:20],  # Top 20 items for agents
            "has_data": True
        }
        
        return _make_response(
            summary,
            "success",
            f"Found {len(items)} chatter items for {ticker}"
        )
        
    except Exception as e:
        logger.error(f"Error getting chatter summary for {ticker}: {e}", exc_info=True)
        return _make_response(
            default_summary,
            "error",
            str(e)
        )


def get_chatter_metadata(ticker: str, days: int = 30) -> Dict[str, Any]:
    """
    Get metadata about available chatter for a ticker.
    
    SAFE: Never throws. Returns standard dict contract.
    """
    ticker = ticker.upper()
    
    default_metadata = {
        "ticker": ticker,
        "total_count": 0,
        "sources": [],
        "oldest_date": None,
        "newest_date": None,
        "sentiment_distribution": {}
    }
    
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                if not _table_exists(cur, 'market_chatter'):
                    return _make_response(default_metadata, "no_data", "Table does not exist")
                
                # Get counts and date range
                cur.execute("""
                    SELECT 
                        COUNT(*),
                        ARRAY_AGG(DISTINCT source),
                        MIN(published_at),
                        MAX(published_at)
                    FROM market_chatter
                    WHERE ticker = %s 
                      AND published_at >= NOW() - INTERVAL '%s days'
                """, (ticker, days))
                
                row = cur.fetchone()
                if row and row[0]:
                    default_metadata["total_count"] = row[0]
                    default_metadata["sources"] = [s for s in (row[1] or []) if s]
                    default_metadata["oldest_date"] = row[2].isoformat() if row[2] else None
                    default_metadata["newest_date"] = row[3].isoformat() if row[3] else None
                
                # Get sentiment distribution
                cur.execute("""
                    SELECT sentiment_label, COUNT(*)
                    FROM market_chatter
                    WHERE ticker = %s 
                      AND published_at >= NOW() - INTERVAL '%s days'
                      AND sentiment_label IS NOT NULL
                    GROUP BY sentiment_label
                """, (ticker, days))
                
                for row in cur.fetchall():
                    if row[0]:
                        default_metadata["sentiment_distribution"][row[0]] = row[1]
                
                status = "success" if default_metadata["total_count"] > 0 else "no_data"
                return _make_response(default_metadata, status, None)
                
    except Exception as e:
        logger.error(f"Error getting chatter metadata for {ticker}: {e}")
        return _make_response(default_metadata, "error", str(e))


def insert_chatter(
    ticker: str,
    source: str,
    source_id: str,
    summary: str,
    **kwargs
) -> Dict[str, Any]:
    """
    Insert a single chatter item.
    
    Uses persist_single_record from chatter_persist.
    
    Returns:
        Standard DAL response
    """
    from .chatter_persist import persist_single_record
    
    try:
        result = persist_single_record(
            ticker=ticker,
            source=source,
            source_id=source_id,
            summary=summary,
            **kwargs
        )
        
        status = "success" if result["success"] else "error"
        return _make_response(result, status, result.get("message"))
        
    except Exception as e:
        logger.error(f"Error inserting chatter for {ticker}: {e}")
        return _make_response(
            {"success": False, "inserted": False},
            "error",
            str(e)
        )


def bulk_insert_chatter(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Bulk insert multiple chatter items.
    
    Converts dicts to MarketChatterRecord and uses persist_market_chatter.
    
    Returns:
        Standard DAL response with counts
    """
    from tradingagents.dataflows.chatter_schema import MarketChatterRecord
    
    if not items:
        return _make_response(
            {"inserted": 0, "skipped": 0, "errors": 0, "total": 0},
            "success",
            "No items to insert"
        )
    
    try:
        # Convert dicts to records
        records = []
        for item in items:
            try:
                record = MarketChatterRecord.from_dict(item)
                records.append(record)
            except Exception as e:
                logger.warning(f"Error converting item to record: {e}")
                continue
        
        counts = persist_market_chatter(records)
        
        status = "success" if counts["errors"] == 0 else "error"
        message = f"Inserted {counts['inserted']}, skipped {counts['skipped']}, errors {counts['errors']}"
        
        return _make_response(counts, status, message)
        
    except Exception as e:
        logger.error(f"Error in bulk insert: {e}")
        return _make_response(
            {"inserted": 0, "skipped": 0, "errors": len(items), "total": len(items)},
            "error",
            str(e)
        )


# Re-export ensure_market_chatter_table for backward compatibility
__all__ = [
    'get_recent_chatter',
    'get_chatter_summary',
    'get_chatter_metadata',
    'insert_chatter',
    'bulk_insert_chatter',
    'ensure_market_chatter_table'
]
