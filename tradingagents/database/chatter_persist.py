"""
Single persistence layer for market chatter.

ALL market chatter storage MUST go through this module.
This ensures:
- Consistent schema usage
- Idempotent inserts via (source, source_id) constraint
- Proper logging and error handling
"""

import logging
import json
from datetime import datetime
from typing import List, Dict, Any, Optional

from .connection import get_db_connection

logger = logging.getLogger(__name__)


def ensure_market_chatter_table() -> bool:
    """
    Ensure market_chatter table exists with v2 schema.
    
    Returns:
        True if table exists or was created, False on error.
    """
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Create table with v2 schema
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS market_chatter (
                        id SERIAL PRIMARY KEY,
                        ticker TEXT NOT NULL,
                        source TEXT NOT NULL,
                        source_id TEXT NOT NULL,
                        title TEXT,
                        summary TEXT,
                        content TEXT,
                        url TEXT,
                        published_at TIMESTAMP WITH TIME ZONE,
                        sentiment_score NUMERIC(5,4),
                        sentiment_label TEXT,
                        confidence NUMERIC(4,3),
                        source_type TEXT NOT NULL DEFAULT 'news',
                        company_name TEXT,
                        raw_payload JSONB,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        ingested_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        CONSTRAINT unique_source_source_id UNIQUE (source, source_id)
                    );
                """)
                
                # Create indexes
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_mc_ticker 
                        ON market_chatter(ticker);
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_mc_ticker_published 
                        ON market_chatter(ticker, published_at DESC);
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_mc_source_source_id 
                        ON market_chatter(source, source_id);
                """)
                
                conn.commit()
                logger.debug("market_chatter table ensured")
                return True
                
    except Exception as e:
        logger.error(f"Failed to ensure market_chatter table: {e}")
        return False


def persist_market_chatter(records: List['MarketChatterRecord']) -> Dict[str, int]:
    """
    Persist market chatter records to database.
    
    This is the SINGLE function for storing market chatter.
    Uses ON CONFLICT DO NOTHING for idempotency.
    
    Args:
        records: List of MarketChatterRecord objects
    
    Returns:
        Dictionary with counts:
        {
            "inserted": int,
            "skipped": int,
            "errors": int,
            "total": int
        }
    """
    from tradingagents.dataflows.chatter_schema import MarketChatterRecord
    
    counts = {
        "inserted": 0,
        "skipped": 0,
        "errors": 0,
        "total": len(records)
    }
    
    if not records:
        logger.info("[PERSIST] No records to persist")
        return counts
    
    # Ensure table exists
    if not ensure_market_chatter_table():
        logger.error("[PERSIST] Failed to ensure table exists")
        counts["errors"] = len(records)
        return counts
    
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                for record in records:
                    try:
                        # Get dict representation
                        data = record.to_dict() if hasattr(record, 'to_dict') else record
                        
                        # Use summary for both summary and content fields
                        summary = data.get('summary', data.get('content', ''))
                        
                        cur.execute("""
                            INSERT INTO market_chatter (
                                ticker, source, source_id, title, summary, content, url,
                                published_at, sentiment_score, sentiment_label, confidence,
                                source_type, company_name, raw_payload, created_at
                            ) VALUES (
                                %s, %s, %s, %s, %s, %s, %s,
                                %s, %s, %s, %s,
                                %s, %s, %s::jsonb, %s
                            )
                            ON CONFLICT (source, source_id) DO NOTHING
                            RETURNING id
                        """, (
                            data.get('ticker', '').upper(),
                            data.get('source', 'unknown'),
                            data.get('source_id', ''),
                            data.get('title'),
                            summary,
                            summary,  # Also store in content for backward compat
                            data.get('url'),
                            data.get('published_at') or datetime.utcnow(),
                            data.get('sentiment_score'),
                            data.get('sentiment_label'),
                            data.get('confidence'),
                            data.get('source_type', 'news'),
                            data.get('company_name'),
                            json.dumps(data.get('raw_payload')) if data.get('raw_payload') else None,
                            data.get('created_at') or datetime.utcnow()
                        ))
                        
                        result = cur.fetchone()
                        if result:
                            counts["inserted"] += 1
                        else:
                            counts["skipped"] += 1
                            
                    except Exception as e:
                        logger.warning(f"[PERSIST] Error persisting record: {e}")
                        counts["errors"] += 1
                        continue
                
                conn.commit()
                
    except Exception as e:
        logger.error(f"[PERSIST] Database error: {e}", exc_info=True)
        counts["errors"] = len(records)
    
    logger.info(
        f"[PERSIST] Complete: inserted={counts['inserted']}, "
        f"skipped={counts['skipped']}, errors={counts['errors']}, total={counts['total']}"
    )
    
    # Warn if nothing was inserted
    if counts['inserted'] == 0 and counts['total'] > 0:
        logger.warning(f"[PERSIST] Zero new records inserted from {counts['total']} items")
    
    return counts


def persist_single_record(
    ticker: str,
    source: str,
    source_id: str,
    summary: str,
    title: Optional[str] = None,
    url: Optional[str] = None,
    published_at: Optional[datetime] = None,
    sentiment_score: Optional[float] = None,
    sentiment_label: Optional[str] = None,
    **kwargs
) -> Dict[str, Any]:
    """
    Persist a single chatter record.
    
    Convenience function for inserting one record.
    
    Returns:
        {"success": bool, "inserted": bool, "id": Optional[int], "message": str}
    """
    from tradingagents.dataflows.chatter_schema import MarketChatterRecord
    
    record = MarketChatterRecord(
        ticker=ticker,
        source=source,
        source_id=source_id,
        summary=summary,
        title=title,
        url=url,
        published_at=published_at,
        sentiment_score=sentiment_score,
        sentiment_label=sentiment_label,
        **kwargs
    )
    
    counts = persist_market_chatter([record])
    
    return {
        "success": counts["errors"] == 0,
        "inserted": counts["inserted"] > 0,
        "message": "Inserted" if counts["inserted"] > 0 else "Skipped (duplicate)"
    }

