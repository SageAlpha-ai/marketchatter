"""
Twitter (X) source implementation using X API v2.
"""

import os
import logging
from typing import List, Dict, Optional
from datetime import datetime, timedelta
import requests

from vfis.market_chatter.sources.base import MarketChatterSource

logger = logging.getLogger(__name__)


class TwitterSource(MarketChatterSource):
    """
    Twitter/X source using X API v2.
    
    Falls back to mock data if bearer token is not available.
    """
    
    def __init__(self):
        super().__init__(source_name="twitter", source_type="social")
        self.bearer_token = os.getenv("TWITTER_BEARER_TOKEN")
        self.base_url = "https://api.twitter.com/2/tweets/search/recent"
    
    def fetch(self, ticker: str, company_name: str) -> List[Dict]:
        """
        Fetch recent tweets for the given ticker and company.
        
        Args:
            ticker: Stock ticker symbol
            company_name: Company name
            
        Returns:
            List of tweet dictionaries
        """
        if not self.bearer_token:
            logger.warning("TWITTER_BEARER_TOKEN not found, using mock data")
            return self._get_mock_data(ticker, company_name)
        
        try:
            # Build search query (ticker OR company name, exclude retweets)
            query = f"({ticker} OR {company_name}) -is:retweet lang:en"
            
            headers = {
                "Authorization": f"Bearer {self.bearer_token}"
            }
            
            params = {
                "query": query,
                "max_results": 50,  # API v2 limit
                "tweet.fields": "created_at,author_id,public_metrics",
                "expansions": "author_id"
            }
            
            logger.info(f"Fetching tweets for {ticker} ({company_name}) from X API")
            response = requests.get(self.base_url, headers=headers, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            tweets = data.get("data", [])
            
            results = []
            for tweet in tweets:
                text = tweet.get("text", "")
                if not text:
                    continue
                
                created_str = tweet.get("created_at")
                published_at = None
                if created_str:
                    try:
                        # Parse ISO format: 2024-01-01T12:00:00.000Z
                        published_at = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
                    except (ValueError, AttributeError):
                        published_at = datetime.utcnow()
                
                normalized_content = self.normalize_content(text)
                if not normalized_content:
                    continue
                
                # Build tweet URL
                author_id = tweet.get("author_id", "")
                tweet_id = tweet.get("id", "")
                url = f"https://twitter.com/i/web/status/{tweet_id}" if tweet_id else None
                
                results.append({
                    "source": self.source_name,
                    "source_type": self.source_type,
                    "content": normalized_content,
                    "url": url,
                    "published_at": published_at or datetime.utcnow(),
                    "raw": tweet
                })
            
            logger.info(f"Fetched {len(results)} tweets for {ticker}")
            return results
            
        except requests.RequestException as e:
            logger.warning(f"X API request failed: {e}, using mock data")
            return self._get_mock_data(ticker, company_name)
        except Exception as e:
            logger.error(f"Error fetching tweets for {ticker}: {e}", exc_info=True)
            return self._get_mock_data(ticker, company_name)
    
    def _get_mock_data(self, ticker: str, company_name: str) -> List[Dict]:
        """
        Generate mock tweet data for testing/fallback.
        
        Args:
            ticker: Stock ticker symbol
            company_name: Company name
            
        Returns:
            List of mock tweet dictionaries
        """
        logger.info(f"Generating mock tweet data for {ticker}")
        now = datetime.utcnow()
        
        mock_tweets = [
            {
                "source": self.source_name,
                "source_type": self.source_type,
                "content": f"$${ticker} looking bullish today! Strong fundamentals support the move.",
                "url": f"https://twitter.com/user/status/mock_{ticker.lower()}_1",
                "published_at": now - timedelta(hours=2),
                "raw": {"id": f"mock_{ticker.lower()}_1", "mock": True}
            },
            {
                "source": self.source_name,
                "source_type": self.source_type,
                "content": f"Just read about {company_name} earnings. Very impressive growth numbers!",
                "url": f"https://twitter.com/user/status/mock_{ticker.lower()}_2",
                "published_at": now - timedelta(hours=6),
                "raw": {"id": f"mock_{ticker.lower()}_2", "mock": True}
            },
            {
                "source": self.source_name,
                "source_type": self.source_type,
                "content": f"${ticker} analysts raising price targets. Worth keeping an eye on.",
                "url": f"https://twitter.com/user/status/mock_{ticker.lower()}_3",
                "published_at": now - timedelta(hours=12),
                "raw": {"id": f"mock_{ticker.lower()}_3", "mock": True}
            }
        ]
        
        return mock_tweets

