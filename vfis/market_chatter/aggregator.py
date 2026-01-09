"""
Aggregation and deduplication logic for market chatter.

DEPRECATED: This module is no longer the canonical ingestion path.

Use instead:
    from vfis.ingestion import ingest_ticker
    result = ingest_ticker("AAPL", days=7)

The canonical ingestion pipeline is:
    vfis/ingestion/__init__.py -> vfis/ingestion/scheduler.py ->
    tradingagents/dataflows/ingest_chatter.py -> tradingagents/database/chatter_persist.py

This file is kept for backward compatibility only.
"""
import warnings
warnings.warn(
    "vfis.market_chatter.aggregator is deprecated. Use vfis.ingestion module instead.",
    DeprecationWarning,
    stacklevel=2
)

import logging
import hashlib
from typing import List, Dict, Set
from datetime import datetime

from vfis.market_chatter.sources import NewsSource, TwitterSource, RedditSource
from vfis.market_chatter.sentiment import analyze_sentiment

logger = logging.getLogger(__name__)


class MarketChatterAggregator:
    """
    Aggregates market chatter from multiple sources and deduplicates.
    """
    
    def __init__(self):
        """Initialize aggregator with sources."""
        self.news_source = NewsSource()
        self.twitter_source = TwitterSource()
        self.reddit_source = RedditSource()
    
    def aggregate(self, ticker: str, company_name: str) -> List[Dict]:
        """
        Aggregate chatter from all sources and deduplicate.
        
        Args:
            ticker: Stock ticker symbol
            company_name: Company name
            
        Returns:
            List of aggregated chatter items with sentiment analysis
        """
        logger.info(f"Aggregating market chatter for {ticker} ({company_name})")
        
        all_chatter = []
        
        # Fetch from all sources
        try:
            news_items = self.news_source.fetch(ticker, company_name)
            all_chatter.extend(news_items)
            logger.info(f"Fetched {len(news_items)} items from news source")
        except Exception as e:
            logger.warning(f"Failed to fetch from news source: {e}")
        
        try:
            twitter_items = self.twitter_source.fetch(ticker, company_name)
            all_chatter.extend(twitter_items)
            logger.info(f"Fetched {len(twitter_items)} items from twitter source")
        except Exception as e:
            logger.warning(f"Failed to fetch from twitter source: {e}")
        
        try:
            reddit_items = self.reddit_source.fetch(ticker, company_name)
            all_chatter.extend(reddit_items)
            logger.info(f"Fetched {len(reddit_items)} items from reddit source")
        except Exception as e:
            logger.warning(f"Failed to fetch from reddit source: {e}")
        
        # Normalize and deduplicate
        normalized = self._normalize_chatter(all_chatter)
        deduplicated = self._deduplicate(normalized)
        
        # Add sentiment analysis
        enriched = []
        for item in deduplicated:
            try:
                sentiment_result = analyze_sentiment(item["content"])
                item["sentiment_score"] = sentiment_result["sentiment_score"]
                item["sentiment_label"] = sentiment_result["sentiment_label"]
                item["confidence"] = sentiment_result["confidence"]
                enriched.append(item)
            except Exception as e:
                logger.warning(f"Sentiment analysis failed for item: {e}")
                # Add item without sentiment
                item["sentiment_score"] = None
                item["sentiment_label"] = None
                item["confidence"] = None
                enriched.append(item)
        
        logger.info(f"Aggregated {len(enriched)} unique chatter items for {ticker}")
        return enriched
    
    def _normalize_chatter(self, chatter: List[Dict]) -> List[Dict]:
        """
        Normalize chatter items (ensure all required fields are present).
        
        Args:
            chatter: List of raw chatter items
            
        Returns:
            List of normalized chatter items
        """
        normalized = []
        for item in chatter:
            # Ensure all required fields
            normalized_item = {
                "source": item.get("source", "unknown"),
                "source_type": item.get("source_type", "social"),
                "content": item.get("content", "").strip(),
                "url": item.get("url"),
                "published_at": item.get("published_at", datetime.utcnow()),
                "raw": item.get("raw", {})
            }
            
            # Skip if no content
            if not normalized_item["content"]:
                continue
            
            normalized.append(normalized_item)
        
        return normalized
    
    def _deduplicate(self, chatter: List[Dict]) -> List[Dict]:
        """
        Deduplicate chatter items using content hash.
        
        Args:
            chatter: List of chatter items
            
        Returns:
            List of deduplicated chatter items
        """
        seen_hashes: Set[str] = set()
        deduplicated = []
        
        for item in chatter:
            # Create content hash for deduplication
            content_hash = self._content_hash(item["content"])
            
            if content_hash not in seen_hashes:
                seen_hashes.add(content_hash)
                deduplicated.append(item)
            else:
                logger.debug(f"Skipping duplicate content: {item['content'][:50]}...")
        
        return deduplicated
    
    def _content_hash(self, content: str) -> str:
        """
        Create normalized hash of content for deduplication.
        
        Args:
            content: Content text
            
        Returns:
            Hash string
        """
        # Normalize: lowercase, remove extra whitespace
        normalized = " ".join(content.lower().split())
        # Create hash
        return hashlib.md5(normalized.encode("utf-8")).hexdigest()

