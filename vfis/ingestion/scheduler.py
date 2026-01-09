"""
Background ingestion scheduler for VFIS.

Implements Option A: Scheduled Background Ingestion

- Runs automatically every 5 minutes (configurable)
- RSS ingestion by DEFAULT (no API key needed)
- Alpha Vantage only if API key exists
- Populates market_chatter table before API reads
- Safe to run repeatedly (idempotent)
- Never silently succeeds with zero inserts
- Tickers discovered dynamically from database or env vars (NO HARDCODING)
"""

import logging
import threading
import time
from datetime import datetime
from typing import List, Optional, Dict, Any, Set

# Import configuration from canonical source
from vfis.core.env import (
    INGESTION_INTERVAL_SECONDS,
    INGESTION_LOOKBACK_DAYS,
    ACTIVE_TICKERS as ENV_ACTIVE_TICKERS,
    ALPHA_VANTAGE_AVAILABLE,
)

logger = logging.getLogger(__name__)

# Track tickers that have been ingested this session (for on-demand ingestion)
_ingested_tickers: Set[str] = set()
_ingested_tickers_lock = threading.Lock()


class IngestionScheduler:
    """
    Background scheduler for market chatter ingestion.
    
    Thread-safe, singleton pattern to prevent duplicate schedulers.
    Discovers tickers dynamically from:
    1. ACTIVE_TICKERS env var (comma-separated)
    2. companies table (is_active=TRUE)
    3. No fallback hardcoded list - if no tickers found, logs warning
    """
    
    _instance: Optional["IngestionScheduler"] = None
    _lock = threading.Lock()
    
    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._initialized = True
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._last_run: Optional[datetime] = None
        self._run_count = 0
        self._error_count = 0
        self._total_inserted = 0
        self._last_result: Optional[Dict[str, Any]] = None
    
    def start(self):
        """Start the background ingestion scheduler."""
        with self._lock:
            if self._running:
                logger.warning("[SCHEDULER] Already running, skipping start")
                return
            
            self._running = True
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._run_loop,
                name="IngestionScheduler",
                daemon=True
            )
            self._thread.start()
            
            # Log configuration (using canonical env)
            logger.info(
                f"[SCHEDULER] Started (interval={INGESTION_INTERVAL_SECONDS}s, "
                f"lookback={INGESTION_LOOKBACK_DAYS}d, "
                f"alpha_vantage={'enabled' if ALPHA_VANTAGE_AVAILABLE else 'disabled'})"
            )
    
    def stop(self):
        """Stop the background ingestion scheduler."""
        with self._lock:
            if not self._running:
                return
            
            logger.info("[SCHEDULER] Stopping...")
            self._stop_event.set()
            self._running = False
            
            if self._thread and self._thread.is_alive():
                self._thread.join(timeout=10)
            
            logger.info("[SCHEDULER] Stopped")
    
    def is_running(self) -> bool:
        """Check if scheduler is running."""
        return self._running
    
    def get_status(self) -> Dict[str, Any]:
        """Get scheduler status."""
        return {
            "running": self._running,
            "last_run": self._last_run.isoformat() if self._last_run else None,
            "run_count": self._run_count,
            "error_count": self._error_count,
            "total_inserted": self._total_inserted,
            "interval_seconds": INGESTION_INTERVAL_SECONDS,
            "alpha_vantage_enabled": ALPHA_VANTAGE_AVAILABLE,
            "last_result": self._last_result
        }
    
    def _run_loop(self):
        """Main scheduler loop."""
        logger.info("[SCHEDULER] Loop started")
        
        # Run immediately on startup
        self._run_ingestion()
        
        while not self._stop_event.is_set():
            if self._stop_event.wait(timeout=INGESTION_INTERVAL_SECONDS):
                break
            self._run_ingestion()
        
        logger.info("[SCHEDULER] Loop ended")
    
    def _run_ingestion(self):
        """Execute one ingestion cycle."""
        self._run_count += 1
        self._last_run = datetime.utcnow()
        
        logger.info(f"[SCHEDULER] Starting cycle #{self._run_count}")
        
        try:
            # Get tickers dynamically - NO HARDCODED FALLBACK
            tickers = get_active_tickers()
            
            if not tickers:
                logger.warning("[SCHEDULER] No active tickers found - nothing to ingest")
                logger.warning("[SCHEDULER] Set ACTIVE_TICKERS env var or add companies to database")
                return
            
            logger.info(f"[SCHEDULER] Ingesting for {len(tickers)} tickers: {tickers[:5]}{'...' if len(tickers) > 5 else ''}")
            
            # Run ingestion
            result = ingest_for_tickers(tickers, days=INGESTION_LOOKBACK_DAYS)
            
            self._last_result = result
            self._total_inserted += result.get("total_inserted", 0)
            
            # Track ingested tickers
            with _ingested_tickers_lock:
                _ingested_tickers.update(tickers)
            
            # Warn if nothing inserted
            if result.get("total_inserted", 0) == 0 and result.get("total_fetched", 0) > 0:
                logger.warning(
                    f"[SCHEDULER] Zero new records from {result.get('total_fetched', 0)} fetched items"
                )
            elif result.get("total_fetched", 0) == 0:
                logger.warning("[SCHEDULER] Zero items fetched - check data sources")
            
            logger.info(
                f"[SCHEDULER] Cycle #{self._run_count} complete: "
                f"fetched={result.get('total_fetched', 0)}, "
                f"inserted={result.get('total_inserted', 0)}, "
                f"errors={result.get('total_errors', 0)}"
            )
            
        except Exception as e:
            self._error_count += 1
            logger.error(f"[SCHEDULER] Cycle failed: {e}", exc_info=True)


def get_active_tickers() -> List[str]:
    """
    Get list of active tickers for ingestion.
    
    Priority:
    1. ACTIVE_TICKERS env var (comma-separated)
    2. companies table (is_active=TRUE)
    3. Empty list (no hardcoded fallback)
    
    Returns:
        List of ticker symbols (uppercase)
    """
    # 1. Check environment variable first (using canonical env)
    if ENV_ACTIVE_TICKERS:
        logger.debug(f"[SCHEDULER] Using {len(ENV_ACTIVE_TICKERS)} tickers from ACTIVE_TICKERS env")
        return list(ENV_ACTIVE_TICKERS)  # Return a copy
    
    # 2. Try database
    try:
        from tradingagents.database.connection import get_db_connection
        
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT DISTINCT ticker_symbol 
                    FROM companies 
                    WHERE is_active = TRUE
                    ORDER BY ticker_symbol
                """)
                rows = cur.fetchall()
                if rows:
                    tickers = [row[0].upper() for row in rows if row[0]]
                    logger.debug(f"[SCHEDULER] Found {len(tickers)} active tickers in database")
                    return tickers
    except Exception as e:
        logger.warning(f"[SCHEDULER] Failed to get tickers from DB: {e}")
    
    # 3. No hardcoded fallback - return empty list
    logger.warning("[SCHEDULER] No tickers found from env or database")
    return []


def ingest_for_tickers(
    tickers: List[str],
    days: int = 7
) -> Dict[str, Any]:
    """
    Ingest market chatter for multiple tickers using CANONICAL pipeline.
    
    Delegates to tradingagents.dataflows.ingest_chatter which handles:
    - Google News RSS (free, no API key)
    - Yahoo Finance RSS (free, no API key)  
    - Reddit public JSON (free, no auth)
    - Generic RSS feeds (free)
    - Alpha Vantage (only if ALPHA_VANTAGE_API_KEY exists)
    
    Args:
        tickers: List of ticker symbols (dynamic, not hardcoded)
        days: Days to look back
    
    Returns:
        Aggregated results dict
    """
    # Use CANONICAL ingestion module - no duplicate logic
    from tradingagents.dataflows.ingest_chatter import ingest_universe
    
    logger.info(f"[SCHEDULER] Delegating to canonical ingest_universe for {len(tickers)} tickers")
    
    # Run canonical ingestion
    result = ingest_universe(tickers, days=days)
    
    # Track all tickers as ingested
    with _ingested_tickers_lock:
        _ingested_tickers.update([t.upper() for t in tickers])
    
    # Build results in expected format
    results = {
        "tickers": tickers,
        "days": days,
        "total_fetched": result["summary"]["total_fetched"],
        "total_inserted": result["summary"]["total_inserted"],
        "total_skipped": result["summary"]["total_skipped"],
        "total_errors": result["summary"]["total_errors"],
        "sources_used": _get_available_sources(),
        "ticker_results": {},
        "timestamp": result["timestamp"]
    }
    
    # Convert per-ticker results
    for ticker, ticker_data in result.get("results", {}).items():
        results["ticker_results"][ticker] = {
            "fetched": ticker_data.get("total_fetched", 0),
            "inserted": ticker_data.get("total_inserted", 0),
            "skipped": ticker_data.get("total_skipped", 0),
            "errors": ticker_data.get("total_errors", 0),
            "sources": {
                src: src_data.get("fetched", 0)
                for src, src_data in ticker_data.get("sources", {}).items()
            }
        }
    
    return results


def _get_available_sources() -> List[str]:
    """Get list of available sources."""
    sources = ["google_news", "yahoo_finance", "reddit", "rss"]
    if ALPHA_VANTAGE_AVAILABLE:
        sources.append("alpha_vantage")
    return sources


def is_ticker_ingested(ticker: str) -> bool:
    """Check if a ticker has been ingested this session."""
    with _ingested_tickers_lock:
        return ticker.upper() in _ingested_tickers


def ingest_ticker_if_missing(ticker: str, days: int = 7) -> Optional[Dict[str, Any]]:
    """
    Ingest a ticker if it hasn't been ingested yet.
    
    Called when a user queries a ticker not yet in the ingestion set.
    Runs in background to not block the request.
    
    Args:
        ticker: Ticker symbol to ingest
        days: Days to look back
    
    Returns:
        Ingestion result if run, None if already ingested
    """
    ticker = ticker.upper()
    
    with _ingested_tickers_lock:
        if ticker in _ingested_tickers:
            logger.debug(f"[INGEST] Ticker {ticker} already ingested this session")
            return None
    
    logger.info(f"[INGEST] On-demand ingestion triggered for {ticker}")
    result = ingest_for_tickers([ticker], days=days)
    return result


# Module-level singleton
_scheduler: Optional[IngestionScheduler] = None


def get_scheduler() -> IngestionScheduler:
    """Get or create the singleton scheduler instance."""
    global _scheduler
    if _scheduler is None:
        _scheduler = IngestionScheduler()
    return _scheduler


def start_scheduler():
    """Start the background ingestion scheduler."""
    scheduler = get_scheduler()
    scheduler.start()


def stop_scheduler():
    """Stop the background ingestion scheduler."""
    scheduler = get_scheduler()
    scheduler.stop()


def get_scheduler_status() -> Dict[str, Any]:
    """Get current scheduler status."""
    scheduler = get_scheduler()
    return scheduler.get_status()


def run_ingestion_now(tickers: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Run ingestion immediately (manual trigger).
    
    Args:
        tickers: Optional list of tickers. If None, uses active tickers from DB/env.
    
    Returns:
        Ingestion results summary
    """
    if not tickers:
        tickers = get_active_tickers()
        if not tickers:
            logger.warning("[SCHEDULER] No tickers available for manual ingestion")
            return {
                "error": "No active tickers found",
                "total_fetched": 0,
                "total_inserted": 0,
                "total_errors": 0
            }
    
    logger.info(f"[SCHEDULER] Manual ingestion for {len(tickers)} tickers")
    return ingest_for_tickers(tickers, days=INGESTION_LOOKBACK_DAYS)
