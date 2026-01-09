"""
Alpha Vantage News ingestion adapter for market chatter.

Normalizes Alpha Vantage NEWS_SENTIMENT API data into canonical MarketChatterRecord format.
"""

import logging
import json
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any

from .chatter_interface import ChatterSource, IngestionResult
from .chatter_schema import MarketChatterRecord, SOURCE_TYPE_NEWS
from .alpha_vantage_news import get_news

logger = logging.getLogger(__name__)


class AlphaVantageChatterSource(ChatterSource):
    """
    Alpha Vantage News API adapter for market chatter.
    
    Uses the NEWS_SENTIMENT endpoint to fetch news articles with sentiment.
    """
    
    SOURCE_NAME = "alpha_vantage"
    SOURCE_TYPE = SOURCE_TYPE_NEWS
    
    def fetch(
        self,
        ticker: str,
        company_name: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """
        Fetch news from Alpha Vantage NEWS_SENTIMENT API.
        """
        # Default to last 7 days
        if not end_date:
            end_date = datetime.now()
        if not start_date:
            start_date = end_date - timedelta(days=7)
        
        try:
            # Alpha Vantage returns JSON string
            response = get_news(ticker, start_date, end_date)
            
            if isinstance(response, str):
                try:
                    data = json.loads(response)
                except json.JSONDecodeError:
                    logger.warning(f"Invalid JSON response from Alpha Vantage for {ticker}")
                    return []
            else:
                data = response
            
            # Check for API errors
            if "Error Message" in data:
                logger.warning(f"Alpha Vantage API error: {data['Error Message']}")
                return []
            
            if "Information" in data:
                logger.warning(f"Alpha Vantage rate limit: {data['Information']}")
                return []
            
            # Extract feed items
            feed = data.get("feed", [])
            logger.info(f"Alpha Vantage returned {len(feed)} news items for {ticker}")
            return feed
            
        except Exception as e:
            logger.error(f"Error fetching Alpha Vantage news for {ticker}: {e}")
            return []
    
    def normalize(
        self,
        raw_items: List[Dict[str, Any]],
        ticker: str,
        company_name: Optional[str] = None
    ) -> List[MarketChatterRecord]:
        """
        Normalize Alpha Vantage news items to MarketChatterRecord format.
        
        Alpha Vantage news item structure:
        {
            "title": "...",
            "url": "...",
            "time_published": "20231215T120000",
            "summary": "...",
            "source": "...",
            "overall_sentiment_score": 0.123,
            "overall_sentiment_label": "Bullish",
            "ticker_sentiment": [
                {"ticker": "...", "relevance_score": "0.9", "ticker_sentiment_score": "0.1", ...}
            ]
        }
        """
        items = []
        ticker_upper = ticker.upper()
        
        for raw in raw_items:
            try:
                # Parse publication time
                time_str = raw.get("time_published", "")
                published_at = None
                if time_str:
                    try:
                        # Format: YYYYMMDDTHHMMSS
                        published_at = datetime.strptime(time_str[:15], "%Y%m%dT%H%M%S")
                    except (ValueError, TypeError):
                        logger.debug(f"Could not parse time: {time_str}")
                
                # Get sentiment for specific ticker
                sentiment_score = raw.get("overall_sentiment_score")
                sentiment_label = raw.get("overall_sentiment_label", "").lower()
                confidence = None
                
                # Look for ticker-specific sentiment
                ticker_sentiments = raw.get("ticker_sentiment", [])
                for ts in ticker_sentiments:
                    if ts.get("ticker", "").upper() == ticker_upper:
                        try:
                            sentiment_score = float(ts.get("ticker_sentiment_score", 0))
                            confidence = float(ts.get("relevance_score", 0))
                        except (ValueError, TypeError):
                            pass
                        break
                
                # Normalize sentiment label
                if sentiment_label in ("bullish", "somewhat-bullish"):
                    sentiment_label = "positive"
                elif sentiment_label in ("bearish", "somewhat-bearish"):
                    sentiment_label = "negative"
                else:
                    sentiment_label = "neutral"
                
                # Generate source_id from URL
                url = raw.get("url", "")
                source_id = hashlib.sha256(url.encode('utf-8')).hexdigest()[:32] if url else ""
                
                if not source_id:
                    # Skip items without URL (can't deduplicate)
                    logger.debug(f"Skipping item without URL: {raw.get('title', '')[:50]}")
                    continue
                
                # Create canonical record
                record = MarketChatterRecord(
                    ticker=ticker_upper,
                    source=self.SOURCE_NAME,
                    source_id=source_id,
                    title=raw.get("title", "")[:500],
                    summary=raw.get("summary", "")[:2000],
                    url=url,
                    published_at=published_at,
                    sentiment_score=sentiment_score,
                    sentiment_label=sentiment_label,
                    confidence=confidence,
                    source_type=self.SOURCE_TYPE,
                    company_name=company_name,
                    raw_payload=raw
                )
                
                items.append(record)
                
            except Exception as e:
                logger.warning(f"Error normalizing item: {e}")
                continue
        
        return items


def ingest_alpha_vantage_news(
    ticker: str,
    company_name: Optional[str] = None,
    days: int = 7
) -> Dict[str, Any]:
    """
    Convenience function to ingest Alpha Vantage news for a ticker.
    
    Args:
        ticker: Stock ticker symbol
        company_name: Optional company name
        days: Number of days to look back (default: 7)
        
    Returns:
        Ingestion result dictionary
    """
    source = AlphaVantageChatterSource()
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    
    result = source.ingest(ticker, company_name, start_date, end_date)
    return result.to_dict()
