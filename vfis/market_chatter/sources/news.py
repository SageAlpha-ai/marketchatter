"""
News source implementation using NewsAPI.org.
"""

import os
import logging
from typing import List, Dict, Optional
from datetime import datetime, timedelta
import requests

from vfis.market_chatter.sources.base import MarketChatterSource

logger = logging.getLogger(__name__)


class NewsSource(MarketChatterSource):
    """
    News source using NewsAPI.org.
    
    Falls back to mock data if API key is not available.
    """
    
    def __init__(self):
        super().__init__(source_name="news", source_type="news")
        self.api_key = os.getenv("NEWS_API_KEY")
        self.base_url = "https://newsapi.org/v2/everything"
    
    def fetch(self, ticker: str, company_name: str) -> List[Dict]:
        """
        Fetch news articles for the given ticker and company.
        
        Args:
            ticker: Stock ticker symbol
            company_name: Company name
            
        Returns:
            List of news article dictionaries
        """
        if not self.api_key:
            logger.warning("NEWS_API_KEY not found, using mock data")
            return self._get_mock_data(ticker, company_name)
        
        try:
            # Calculate date range (last 7 days)
            to_date = datetime.utcnow()
            from_date = to_date - timedelta(days=7)
            
            # Build search query (ticker OR company name)
            query = f"{ticker} OR {company_name}"
            
            params = {
                "q": query,
                "apiKey": self.api_key,
                "from": from_date.strftime("%Y-%m-%d"),
                "to": to_date.strftime("%Y-%m-%d"),
                "sortBy": "publishedAt",
                "language": "en",
                "pageSize": 50  # Max 100, but we'll limit to 50 for rate limiting
            }
            
            logger.info(f"Fetching news for {ticker} ({company_name}) from NewsAPI")
            response = requests.get(self.base_url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            articles = data.get("articles", [])
            
            results = []
            for article in articles:
                # Extract relevant fields
                content = article.get("description") or article.get("content", "")[:500]
                if not content:
                    continue
                
                published_str = article.get("publishedAt")
                published_at = None
                if published_str:
                    try:
                        # Parse ISO format: 2024-01-01T12:00:00Z
                        published_at = datetime.fromisoformat(published_str.replace("Z", "+00:00"))
                    except (ValueError, AttributeError):
                        published_at = datetime.utcnow()
                
                normalized_content = self.normalize_content(content)
                if not normalized_content:
                    continue
                
                results.append({
                    "source": self.source_name,
                    "source_type": self.source_type,
                    "content": normalized_content,
                    "url": article.get("url"),
                    "published_at": published_at or datetime.utcnow(),
                    "raw": article
                })
            
            logger.info(f"Fetched {len(results)} news articles for {ticker}")
            return results
            
        except requests.RequestException as e:
            logger.warning(f"NewsAPI request failed: {e}, using mock data")
            return self._get_mock_data(ticker, company_name)
        except Exception as e:
            logger.error(f"Error fetching news for {ticker}: {e}", exc_info=True)
            return self._get_mock_data(ticker, company_name)
    
    def _get_mock_data(self, ticker: str, company_name: str) -> List[Dict]:
        """
        Generate mock news data for testing/fallback.
        
        Args:
            ticker: Stock ticker symbol
            company_name: Company name
            
        Returns:
            List of mock news dictionaries
        """
        logger.info(f"Generating mock news data for {ticker}")
        now = datetime.utcnow()
        
        mock_articles = [
            {
                "source": self.source_name,
                "source_type": self.source_type,
                "content": f"{company_name} ({ticker}) shows strong quarterly performance with increased revenue.",
                "url": f"https://example.com/news/{ticker.lower()}-quarterly-performance",
                "published_at": now - timedelta(days=1),
                "raw": {"title": f"{company_name} Quarterly Results", "mock": True}
            },
            {
                "source": self.source_name,
                "source_type": self.source_type,
                "content": f"Analysts maintain positive outlook on {ticker} stock following recent developments.",
                "url": f"https://example.com/news/{ticker.lower()}-analyst-outlook",
                "published_at": now - timedelta(days=3),
                "raw": {"title": f"{company_name} Analyst Coverage", "mock": True}
            },
            {
                "source": self.source_name,
                "source_type": self.source_type,
                "content": f"{company_name} announces expansion plans in key markets.",
                "url": f"https://example.com/news/{ticker.lower()}-expansion",
                "published_at": now - timedelta(days=5),
                "raw": {"title": f"{company_name} Expansion", "mock": True}
            }
        ]
        
        return mock_articles

