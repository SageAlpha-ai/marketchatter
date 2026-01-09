"""
Pluggable ingestion interface for market chatter sources.

This module provides:
- Abstract base class for chatter sources
- Delegates to canonical schema for data normalization
- Pluggable architecture for adding new sources

NOTE: MarketChatterRecord is defined in chatter_schema.py - use that as the canonical schema.
"""

import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional, Dict, List, Any

# Import canonical schema
from .chatter_schema import (
    MarketChatterRecord,
    DALResponse,
    ChatterSummary,
    normalize_chatter_item,
    VALID_SOURCES,
    SOURCE_TYPE_NEWS,
    SOURCE_TYPE_SOCIAL
)

logger = logging.getLogger(__name__)


# Re-export for backward compatibility
ChatterItem = MarketChatterRecord


class IngestionResult:
    """Result of an ingestion operation."""
    
    def __init__(
        self,
        source: str,
        ticker: str,
        fetched: int = 0,
        inserted: int = 0,
        skipped: int = 0,
        errors: int = 0,
        messages: Optional[List[str]] = None
    ):
        self.source = source
        self.ticker = ticker
        self.fetched = fetched
        self.inserted = inserted
        self.skipped = skipped
        self.errors = errors
        self.messages = messages or []
    
    @property
    def success(self) -> bool:
        return self.errors == 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "ticker": self.ticker,
            "fetched": self.fetched,
            "inserted": self.inserted,
            "skipped": self.skipped,
            "errors": self.errors,
            "success": self.success,
            "messages": self.messages
        }


class ChatterSource(ABC):
    """
    Abstract base class for market chatter sources.
    
    All sources must implement:
    - fetch(): Retrieve raw data from source
    - normalize(): Convert raw data to canonical MarketChatterRecord
    
    Optional:
    - analyze_sentiment(): Add sentiment scores
    """
    
    SOURCE_NAME: str = "unknown"
    SOURCE_TYPE: str = SOURCE_TYPE_NEWS
    
    @abstractmethod
    def fetch(
        self,
        ticker: str,
        company_name: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """
        Fetch raw data from source.
        
        Args:
            ticker: Stock ticker symbol
            company_name: Optional company name for broader search
            start_date: Optional start date filter
            end_date: Optional end date filter
            
        Returns:
            List of raw data dictionaries from source
        """
        pass
    
    @abstractmethod
    def normalize(
        self,
        raw_items: List[Dict[str, Any]],
        ticker: str,
        company_name: Optional[str] = None
    ) -> List[MarketChatterRecord]:
        """
        Normalize raw items to canonical MarketChatterRecord format.
        
        Args:
            raw_items: Raw data from fetch()
            ticker: Stock ticker symbol
            company_name: Optional company name
            
        Returns:
            List of normalized MarketChatterRecord objects
        """
        pass
    
    def analyze_sentiment(self, items: List[MarketChatterRecord]) -> List[MarketChatterRecord]:
        """
        Add sentiment analysis to items.
        
        Default implementation does nothing. Override in subclasses.
        """
        return items
    
    def ingest(
        self,
        ticker: str,
        company_name: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> IngestionResult:
        """
        Full ingestion pipeline: fetch, normalize, analyze, store.
        
        Returns:
            IngestionResult with counts and status
        """
        from tradingagents.database.chatter_persist import persist_market_chatter
        
        result = IngestionResult(source=self.SOURCE_NAME, ticker=ticker.upper())
        
        try:
            # Fetch
            logger.info(f"[{self.SOURCE_NAME}] Fetching chatter for {ticker}")
            raw_items = self.fetch(ticker, company_name, start_date, end_date)
            result.fetched = len(raw_items)
            logger.info(f"[{self.SOURCE_NAME}] Fetched {result.fetched} raw items for {ticker}")
            
            if not raw_items:
                result.messages.append("No data returned from source")
                return result
            
            # Normalize
            items = self.normalize(raw_items, ticker, company_name)
            logger.info(f"[{self.SOURCE_NAME}] Normalized {len(items)} items for {ticker}")
            
            # Analyze sentiment
            items = self.analyze_sentiment(items)
            
            # Store using centralized persist function
            counts = persist_market_chatter(items)
            
            result.inserted = counts["inserted"]
            result.skipped = counts["skipped"]
            result.errors = counts["errors"]
            
            logger.info(
                f"[{self.SOURCE_NAME}] Ingestion complete for {ticker}: "
                f"fetched={result.fetched}, inserted={result.inserted}, "
                f"skipped={result.skipped}, errors={result.errors}"
            )
            
        except Exception as e:
            logger.error(f"[{self.SOURCE_NAME}] Ingestion failed for {ticker}: {e}", exc_info=True)
            result.errors = 1
            result.messages.append(f"Ingestion error: {str(e)}")
        
        return result


# Export all
__all__ = [
    'ChatterSource',
    'ChatterItem',
    'MarketChatterRecord',
    'IngestionResult',
    'DALResponse',
    'ChatterSummary',
    'normalize_chatter_item',
    'VALID_SOURCES',
    'SOURCE_TYPE_NEWS',
    'SOURCE_TYPE_SOCIAL'
]
