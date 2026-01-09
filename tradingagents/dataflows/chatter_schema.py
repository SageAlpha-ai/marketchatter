"""
Canonical schema for market chatter data.

This module defines the SINGLE source of truth for market chatter records
used across ingestion, storage, DAL, and agents.

ALL code paths MUST use these schemas for consistency.
"""

import hashlib
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional, Dict, List, Any

logger = logging.getLogger(__name__)


# Valid sources for market chatter
VALID_SOURCES = frozenset({
    'alpha_vantage',
    'rss',
    'reddit',
    'twitter',
    'stocktwits',
    'news',
    'benzinga',
    'seeking_alpha',
    'google_news',      # Google News RSS (free, no API key)
    'yahoo_finance',    # Yahoo Finance RSS (free, no API key)
})

# Source types
SOURCE_TYPE_NEWS = 'news'
SOURCE_TYPE_SOCIAL = 'social'


@dataclass
class MarketChatterRecord:
    """
    Canonical market chatter record.
    
    Used everywhere:
    - Ingestion normalization
    - Database storage
    - DAL retrieval
    - Agent consumption
    
    Fields:
        ticker: Stock symbol (always uppercase)
        source: Data source (e.g., 'alpha_vantage', 'rss', 'reddit')
        source_id: Unique ID from source (URL hash, post ID, etc.)
        title: Article/post title (nullable)
        summary: Content summary/body (required)
        url: Source URL (nullable)
        published_at: Original publication time
        sentiment_score: Sentiment score -1.0 to 1.0 (nullable)
        created_at: Record creation time (auto-set)
    """
    ticker: str
    source: str
    source_id: str
    summary: str
    title: Optional[str] = None
    url: Optional[str] = None
    published_at: Optional[datetime] = None
    sentiment_score: Optional[float] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    
    # Optional metadata
    source_type: str = SOURCE_TYPE_NEWS
    sentiment_label: Optional[str] = None
    confidence: Optional[float] = None
    company_name: Optional[str] = None
    raw_payload: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        """Normalize fields after initialization."""
        # Ensure ticker is uppercase
        self.ticker = self.ticker.upper() if self.ticker else ''
        
        # Validate source
        if self.source not in VALID_SOURCES:
            logger.warning(f"Unknown source '{self.source}', using 'news'")
            self.source = 'news'
        
        # Ensure source_id exists
        if not self.source_id:
            self.source_id = self._generate_source_id()
    
    def _generate_source_id(self) -> str:
        """Generate a source_id from content hash if not provided."""
        content = f"{self.ticker}:{self.source}:{self.title or ''}:{self.url or ''}:{self.summary[:100]}"
        return hashlib.sha256(content.encode('utf-8')).hexdigest()[:32]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database operations."""
        return {
            'ticker': self.ticker,
            'source': self.source,
            'source_id': self.source_id,
            'title': self.title,
            'summary': self.summary,
            'url': self.url,
            'published_at': self.published_at,
            'sentiment_score': self.sentiment_score,
            'sentiment_label': self.sentiment_label,
            'created_at': self.created_at,
            'source_type': self.source_type,
            'confidence': self.confidence,
            'company_name': self.company_name,
            'raw_payload': self.raw_payload
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MarketChatterRecord':
        """Create from dictionary (e.g., database row)."""
        return cls(
            ticker=data.get('ticker', ''),
            source=data.get('source', 'news'),
            source_id=data.get('source_id', ''),
            title=data.get('title'),
            summary=data.get('summary', data.get('content', '')),  # Support legacy 'content' field
            url=data.get('url'),
            published_at=data.get('published_at'),
            sentiment_score=data.get('sentiment_score'),
            sentiment_label=data.get('sentiment_label'),
            created_at=data.get('created_at') or datetime.utcnow(),
            source_type=data.get('source_type', SOURCE_TYPE_NEWS),
            confidence=data.get('confidence'),
            company_name=data.get('company_name'),
            raw_payload=data.get('raw_payload')
        )


@dataclass
class DALResponse:
    """
    Standard response contract for all DAL methods.
    
    ALL DAL methods MUST return this shape:
    {
        "data": Any,
        "status": "success" | "no_data" | "error",
        "message": Optional[str]
    }
    """
    data: Any
    status: str  # 'success', 'no_data', 'error'
    message: Optional[str] = None
    
    def __post_init__(self):
        """Validate status."""
        valid_statuses = {'success', 'no_data', 'error'}
        if self.status not in valid_statuses:
            raise ValueError(f"Invalid status '{self.status}'. Must be one of: {valid_statuses}")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'data': self.data,
            'status': self.status,
            'message': self.message
        }
    
    @classmethod
    def success(cls, data: Any, message: Optional[str] = None) -> 'DALResponse':
        """Create a success response."""
        return cls(data=data, status='success', message=message)
    
    @classmethod
    def no_data(cls, message: str) -> 'DALResponse':
        """Create a no_data response."""
        return cls(data=None, status='no_data', message=message)
    
    @classmethod
    def error(cls, message: str) -> 'DALResponse':
        """Create an error response."""
        return cls(data=None, status='error', message=message)


@dataclass 
class ChatterSummary:
    """
    Summary of market chatter for a ticker.
    
    Used by agents for analysis.
    """
    ticker: str
    total_count: int = 0
    window_days: int = 7
    sources: Dict[str, int] = field(default_factory=dict)
    sentiment_distribution: Dict[str, int] = field(default_factory=dict)
    average_sentiment: Optional[float] = None
    newest_item_date: Optional[datetime] = None
    oldest_item_date: Optional[datetime] = None
    items: List[Dict[str, Any]] = field(default_factory=list)
    has_data: bool = False
    status: str = 'no_data'
    message: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'ticker': self.ticker,
            'total_count': self.total_count,
            'window_days': self.window_days,
            'sources': self.sources,
            'sentiment_distribution': self.sentiment_distribution,
            'average_sentiment': self.average_sentiment,
            'newest_item_date': self.newest_item_date.isoformat() if self.newest_item_date else None,
            'oldest_item_date': self.oldest_item_date.isoformat() if self.oldest_item_date else None,
            'items': self.items,
            'has_data': self.has_data,
            'status': self.status,
            'message': self.message
        }


def normalize_chatter_item(raw_item: Dict[str, Any], source: str) -> MarketChatterRecord:
    """
    Normalize a raw chatter item from any source into canonical MarketChatterRecord.
    
    This is the SINGLE normalization function for all sources.
    
    Args:
        raw_item: Raw data from source (Alpha Vantage, RSS, Reddit, etc.)
        source: Source identifier ('alpha_vantage', 'rss', 'reddit', etc.)
    
    Returns:
        MarketChatterRecord with normalized fields
    """
    if source == 'alpha_vantage':
        return _normalize_alpha_vantage(raw_item)
    elif source == 'rss':
        return _normalize_rss(raw_item)
    elif source == 'reddit':
        return _normalize_reddit(raw_item)
    else:
        return _normalize_generic(raw_item, source)


def _normalize_alpha_vantage(raw: Dict[str, Any]) -> MarketChatterRecord:
    """Normalize Alpha Vantage NEWS_SENTIMENT item."""
    # Parse publication time
    time_str = raw.get('time_published', '')
    published_at = None
    if time_str:
        try:
            published_at = datetime.strptime(time_str[:15], '%Y%m%dT%H%M%S')
        except (ValueError, TypeError):
            pass
    
    # Get sentiment
    sentiment_score = raw.get('overall_sentiment_score')
    if isinstance(sentiment_score, str):
        try:
            sentiment_score = float(sentiment_score)
        except ValueError:
            sentiment_score = None
    
    # Normalize sentiment label
    raw_label = (raw.get('overall_sentiment_label') or '').lower()
    if raw_label in ('bullish', 'somewhat-bullish'):
        sentiment_label = 'positive'
    elif raw_label in ('bearish', 'somewhat-bearish'):
        sentiment_label = 'negative'
    else:
        sentiment_label = 'neutral'
    
    # Generate source_id from URL
    url = raw.get('url', '')
    source_id = hashlib.sha256(url.encode('utf-8')).hexdigest()[:32] if url else ''
    
    # Get ticker from raw item or default
    ticker = ''
    ticker_sentiments = raw.get('ticker_sentiment', [])
    if ticker_sentiments:
        ticker = ticker_sentiments[0].get('ticker', '')
    
    return MarketChatterRecord(
        ticker=ticker,
        source='alpha_vantage',
        source_id=source_id,
        title=raw.get('title', '')[:500],
        summary=raw.get('summary', '')[:2000],
        url=url,
        published_at=published_at,
        sentiment_score=sentiment_score,
        sentiment_label=sentiment_label,
        source_type=SOURCE_TYPE_NEWS,
        raw_payload=raw
    )


def _normalize_rss(raw: Dict[str, Any]) -> MarketChatterRecord:
    """Normalize RSS feed item."""
    # Generate source_id from URL or content hash
    url = raw.get('url', raw.get('link', ''))
    source_id = hashlib.sha256(url.encode('utf-8')).hexdigest()[:32] if url else ''
    
    # Parse published date
    published_at = raw.get('published_at')
    if isinstance(published_at, str):
        try:
            published_at = datetime.fromisoformat(published_at.replace('Z', '+00:00'))
        except ValueError:
            published_at = None
    
    return MarketChatterRecord(
        ticker=raw.get('ticker', ''),
        source='rss',
        source_id=source_id,
        title=raw.get('headline', raw.get('title', ''))[:500],
        summary=raw.get('content', raw.get('summary', ''))[:2000],
        url=url,
        published_at=published_at,
        sentiment_score=raw.get('sentiment_score'),
        sentiment_label=raw.get('sentiment_label'),
        source_type=SOURCE_TYPE_NEWS,
        company_name=raw.get('company_name'),
        raw_payload=raw
    )


def _normalize_reddit(raw: Dict[str, Any]) -> MarketChatterRecord:
    """Normalize Reddit post/comment."""
    # Use Reddit post/comment ID as source_id
    source_id = raw.get('id', '')
    if not source_id:
        url = raw.get('url', raw.get('permalink', ''))
        source_id = hashlib.sha256(url.encode('utf-8')).hexdigest()[:32]
    
    # Parse timestamp
    published_at = raw.get('created_utc')
    if isinstance(published_at, (int, float)):
        published_at = datetime.utcfromtimestamp(published_at)
    elif isinstance(published_at, str):
        try:
            published_at = datetime.fromisoformat(published_at)
        except ValueError:
            published_at = None
    
    return MarketChatterRecord(
        ticker=raw.get('ticker', ''),
        source='reddit',
        source_id=source_id,
        title=raw.get('title', '')[:500],
        summary=raw.get('selftext', raw.get('body', ''))[:2000],
        url=raw.get('url', raw.get('permalink', '')),
        published_at=published_at,
        sentiment_score=raw.get('sentiment_score'),
        sentiment_label=raw.get('sentiment_label'),
        source_type=SOURCE_TYPE_SOCIAL,
        raw_payload=raw
    )


def _normalize_generic(raw: Dict[str, Any], source: str) -> MarketChatterRecord:
    """Generic normalization for unknown sources."""
    url = raw.get('url', '')
    content = raw.get('content', raw.get('summary', raw.get('text', '')))
    source_id = raw.get('source_id', raw.get('id', ''))
    
    if not source_id:
        hash_input = f"{url}:{content[:100]}"
        source_id = hashlib.sha256(hash_input.encode('utf-8')).hexdigest()[:32]
    
    return MarketChatterRecord(
        ticker=raw.get('ticker', ''),
        source=source if source in VALID_SOURCES else 'news',
        source_id=source_id,
        title=raw.get('title', raw.get('headline', ''))[:500],
        summary=content[:2000],
        url=url,
        published_at=raw.get('published_at'),
        sentiment_score=raw.get('sentiment_score'),
        sentiment_label=raw.get('sentiment_label'),
        source_type=raw.get('source_type', SOURCE_TYPE_NEWS),
        company_name=raw.get('company_name'),
        raw_payload=raw
    )

