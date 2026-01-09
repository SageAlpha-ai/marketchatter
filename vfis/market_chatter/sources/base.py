"""
Base abstract class for market chatter sources.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Optional
from datetime import datetime


class MarketChatterSource(ABC):
    """
    Abstract base class for market chatter sources.
    
    All source implementations must inherit from this class and
    implement the fetch() method.
    """
    
    def __init__(self, source_name: str, source_type: str):
        """
        Initialize the source.
        
        Args:
            source_name: Name of the source (e.g., 'news', 'twitter', 'reddit')
            source_type: Type of source ('news' or 'social')
        """
        self.source_name = source_name
        self.source_type = source_type
    
    @abstractmethod
    def fetch(self, ticker: str, company_name: str) -> List[Dict]:
        """
        Fetch market chatter for a given ticker and company.
        
        Args:
            ticker: Stock ticker symbol (dynamically provided)
            company_name: Company name (e.g., 'Zomato Ltd')
            
        Returns:
            List of dictionaries with the following schema:
            {
                "source": str,                    # Source identifier
                "source_type": str,               # "news" | "social"
                "content": str,                   # Main content text
                "url": str | None,                # URL to original content
                "published_at": datetime,         # Publication timestamp
                "raw": dict                       # Raw API response
            }
            
        Raises:
            Exception: If fetch fails (should be caught and handled by caller)
        """
        pass
    
    def normalize_content(self, content: str) -> str:
        """
        Normalize content text (strip whitespace, normalize newlines).
        
        Args:
            content: Raw content text
            
        Returns:
            Normalized content string
        """
        if not content:
            return ""
        # Remove extra whitespace and normalize newlines
        normalized = " ".join(content.split())
        return normalized.strip()

