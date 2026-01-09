"""
Reddit source implementation using Reddit JSON API (no auth required).
"""

import logging
from typing import List, Dict, Optional
from datetime import datetime, timedelta
import requests

from vfis.market_chatter.sources.base import MarketChatterSource

logger = logging.getLogger(__name__)


class RedditSource(MarketChatterSource):
    """
    Reddit source using JSON API (no authentication required).
    
    Searches in relevant subreddits for ticker/company mentions.
    """
    
    # Relevant subreddits for stock discussions
    SUBREDDITS = ['stocks', 'investing', 'wallstreetbets']
    
    def __init__(self):
        super().__init__(source_name="reddit", source_type="social")
        self.base_url = "https://www.reddit.com/r/{subreddit}/search.json"
    
    def fetch(self, ticker: str, company_name: str) -> List[Dict]:
        """
        Fetch Reddit posts for the given ticker and company.
        
        Args:
            ticker: Stock ticker symbol
            company_name: Company name
            
        Returns:
            List of Reddit post dictionaries
        """
        try:
            all_posts = []
            
            # Search in each subreddit
            for subreddit in self.SUBREDDITS:
                try:
                    posts = self._fetch_from_subreddit(subreddit, ticker, company_name)
                    all_posts.extend(posts)
                except Exception as e:
                    logger.warning(f"Error fetching from r/{subreddit}: {e}")
                    continue
            
            logger.info(f"Fetched {len(all_posts)} Reddit posts for {ticker}")
            return all_posts
            
        except Exception as e:
            logger.error(f"Error fetching Reddit posts for {ticker}: {e}", exc_info=True)
            return self._get_mock_data(ticker, company_name)
    
    def _fetch_from_subreddit(self, subreddit: str, ticker: str, company_name: str) -> List[Dict]:
        """
        Fetch posts from a specific subreddit.
        
        Args:
            subreddit: Subreddit name
            ticker: Stock ticker symbol
            company_name: Company name
            
        Returns:
            List of post dictionaries
        """
        # Reddit JSON API search
        url = f"https://www.reddit.com/r/{subreddit}/search.json"
        params = {
            "q": f"{ticker} OR {company_name}",
            "restrict_sr": "true",  # Restrict to subreddit
            "sort": "new",
            "limit": 25  # Reddit API limit
        }
        
        headers = {
            "User-Agent": "VFIS-MarketChatter/1.0 (Market Intelligence Bot)"
        }
        
        response = requests.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        posts_data = data.get("data", {}).get("children", [])
        
        results = []
        for post_wrapper in posts_data:
            post_data = post_wrapper.get("data", {})
            
            # Combine title and selftext
            title = post_data.get("title", "")
            selftext = post_data.get("selftext", "")
            content = f"{title}. {selftext}".strip()
            
            if not content:
                continue
            
            # Parse timestamp (Unix timestamp)
            created_utc = post_data.get("created_utc")
            published_at = datetime.utcnow()
            if created_utc:
                try:
                    published_at = datetime.utcfromtimestamp(created_utc)
                except (ValueError, TypeError):
                    pass
            
            normalized_content = self.normalize_content(content)
            if not normalized_content:
                continue
            
            # Build Reddit URL
            permalink = post_data.get("permalink", "")
            url = f"https://www.reddit.com{permalink}" if permalink else None
            
            results.append({
                "source": self.source_name,
                "source_type": self.source_type,
                "content": normalized_content[:1000],  # Limit content length
                "url": url,
                "published_at": published_at,
                "raw": post_data
            })
        
        return results
    
    def _get_mock_data(self, ticker: str, company_name: str) -> List[Dict]:
        """
        Generate mock Reddit post data for testing/fallback.
        
        Args:
            ticker: Stock ticker symbol
            company_name: Company name
            
        Returns:
            List of mock Reddit post dictionaries
        """
        logger.info(f"Generating mock Reddit data for {ticker}")
        now = datetime.utcnow()
        
        mock_posts = [
            {
                "source": self.source_name,
                "source_type": self.source_type,
                "content": f"DD: Why I'm bullish on {ticker}. Strong fundamentals and growing market share.",
                "url": f"https://www.reddit.com/r/stocks/comments/mock_{ticker.lower()}_1",
                "published_at": now - timedelta(days=1),
                "raw": {"id": f"mock_{ticker.lower()}_1", "mock": True}
            },
            {
                "source": self.source_name,
                "source_type": self.source_type,
                "content": f"Anyone else tracking {company_name}? Their latest earnings report was impressive.",
                "url": f"https://www.reddit.com/r/investing/comments/mock_{ticker.lower()}_2",
                "published_at": now - timedelta(days=2),
                "raw": {"id": f"mock_{ticker.lower()}_2", "mock": True}
            }
        ]
        
        return mock_posts

