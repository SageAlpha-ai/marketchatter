"""
RSS-based news ingestion for VFIS.

STRICT RULES:
- Ingest from free, legitimate RSS sources only
- Headline + short summary only (no paid content scraping)
- Associate news items with ticker where possible
- Store in news table with published timestamp and source
- No LLM usage
- Windows-compatible only

NOTE: Environment variables are loaded by scripts.init_env (single source of truth).
All entrypoints must import scripts.init_env as their FIRST import line.
"""
import scripts.init_env  # Loads and validates environment variables

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, date
import feedparser
import requests
from pathlib import Path

from tradingagents.database.connection import get_db_connection, init_database
from tradingagents.database.dal import FinancialDataAccess
from tradingagents.database.audit import log_data_access

logger = logging.getLogger(__name__)

# Initialize database connection pool on module import
# Environment variables are already loaded by scripts.init_env import above
# This is idempotent - safe to call multiple times
init_database(config={})  # Uses environment variables

# Valid RSS sources (free and legitimate only)
RSS_SOURCES = {
    'CNBC TV18': 'https://www.cnbctv18.com/rss/',
    'Moneycontrol': 'https://www.moneycontrol.com/rss/',
    'Reuters India': 'https://www.reutersagency.com/feed/?best-topics=business-finance&post_type=best',
    'Economic Times': 'https://economictimes.indiatimes.com/rssfeedsdefault.cms'
}

# Map source names to our source codes (NSE, BSE, SEBI for regulatory, 'news' for general)
SOURCE_MAPPING = {
    'CNBC TV18': 'news',
    'Moneycontrol': 'news',
    'Reuters India': 'news',
    'Economic Times': 'news'
}


class NewsIngester:
    """
    Ingest news from RSS feeds.
    
    CRITICAL: Only free, legitimate RSS sources. No paid content scraping.
    """
    
    def __init__(self, ticker: Optional[str] = None):
        """
        Initialize news ingester.
        
        Args:
            ticker: Optional company ticker to filter news for
        """
        self.ticker = ticker.upper() if ticker else None
        
        # Get company ID if ticker provided
        self.company_id = None
        if self.ticker:
            company = FinancialDataAccess.get_company_by_ticker(self.ticker)
            if company:
                self.company_id = company['id']
    
    def fetch_rss_feed(self, source_name: str, rss_url: str) -> List[Dict[str, Any]]:
        """
        Fetch and parse RSS feed.
        
        Args:
            source_name: Name of news source
            rss_url: URL of RSS feed
            
        Returns:
            List of news articles
        """
        articles = []
        
        try:
            # Parse RSS feed
            feed = feedparser.parse(rss_url)
            
            if feed.bozo:
                logger.warning(f"RSS feed parse warning for {source_name}: {feed.bozo_exception}")
            
            for entry in feed.entries:
                # Extract article information
                headline = entry.get('title', '')
                summary = entry.get('summary', '') or entry.get('description', '')
                link = entry.get('link', '')
                
                # Parse published date
                published_at = None
                if hasattr(entry, 'published_parsed') and entry.published_parsed:
                    try:
                        published_at = datetime(*entry.published_parsed[:6])
                    except Exception as e:
                        logger.warning(f"Failed to parse date for article: {e}")
                
                if not published_at and hasattr(entry, 'published'):
                    try:
                        published_at = datetime.strptime(entry.published, '%a, %d %b %Y %H:%M:%S %Z')
                    except (ValueError, TypeError) as e:
                        logger.warning(f"Failed to parse date string '{entry.published}': {e}")
                        published_at = datetime.now()
                
                if not published_at:
                    published_at = datetime.now()
                
                articles.append({
                    'headline': headline,
                    'content': summary[:500] if summary else '',  # Limit to 500 chars
                    'url': link,
                    'published_at': published_at,
                    'source_name': source_name
                })
        
        except Exception as e:
            logger.error(f"Failed to fetch RSS feed from {source_name} ({rss_url}): {e}")
        
        return articles
    
    def ingest_news_from_source(
        self,
        source_name: str,
        rss_url: str,
        limit: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Ingest news from a specific RSS source.
        
        Args:
            source_name: Name of news source
            rss_url: URL of RSS feed
            limit: Maximum number of articles to ingest (None = all)
            
        Returns:
            Dictionary with ingestion results
        """
        results = {
            'success': False,
            'articles_fetched': 0,
            'articles_inserted': 0,
            'errors': []
        }
        
        try:
            # Fetch articles from RSS
            articles = self.fetch_rss_feed(source_name, rss_url)
            
            if limit:
                articles = articles[:limit]
            
            results['articles_fetched'] = len(articles)
            
            # Insert articles into database
            inserted = 0
            for article in articles:
                try:
                    # Try to associate with ticker if headline/summary contains ticker
                    article_company_id = self.company_id
                    
                    # If ticker not provided, try to detect from content
                    if not article_company_id and self.ticker:
                        content_lower = (article['headline'] + ' ' + article['content']).lower()
                        if self.ticker.lower() in content_lower:
                            article_company_id = self.company_id
                    
                    # Map source to our source code
                    source_code = SOURCE_MAPPING.get(source_name, 'news')
                    
                    # Insert into database
                    with get_db_connection() as conn:
                        with conn.cursor() as cur:
                            # Check if news table exists
                            cur.execute("""
                                SELECT EXISTS (
                                    SELECT FROM information_schema.tables 
                                    WHERE table_name = 'news'
                                );
                            """)
                            if not cur.fetchone()[0]:
                                results['errors'].append("News table does not exist")
                                continue
                            
                            # Insert news article (using headline + url for duplicate detection)
                            # Note: We use ON CONFLICT DO NOTHING - adjust constraint if needed
                            cur.execute("""
                                INSERT INTO news 
                                (company_id, headline, content, source_name, published_at, url, created_at)
                                VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                                ON CONFLICT DO NOTHING
                            """, (
                                article_company_id,
                                article['headline'][:500],  # Ensure within VARCHAR limit
                                article['content'],
                                source_code,
                                article['published_at'],
                                article['url']
                            ))
                            
                            inserted += 1
                    
                    conn.commit()
                
                except Exception as e:
                    error_msg = f"Failed to insert article '{article['headline'][:50]}...': {str(e)}"
                    logger.warning(error_msg)
                    results['errors'].append(error_msg)
                    continue
            
            results['articles_inserted'] = inserted
            results['success'] = True
            
            # Log audit
            log_data_access(
                event_type='news_ingestion',
                entity_type='news',
                entity_id=None,
                details={
                    'ticker': self.ticker,
                    'source': source_name,
                    'articles_fetched': results['articles_fetched'],
                    'articles_inserted': results['articles_inserted']
                },
                user_id='news_ingester'
            )
            
            logger.info(
                f"Ingested {results['articles_inserted']} articles from {source_name} "
                f"for {self.ticker or 'all companies'}"
            )
        
        except Exception as e:
            error_msg = f"Failed to ingest news from {source_name}: {str(e)}"
            logger.error(error_msg, exc_info=True)
            results['errors'].append(error_msg)
        
        return results
    
    def ingest_all_sources(self, limit_per_source: Optional[int] = None) -> Dict[str, Any]:
        """
        Ingest news from all configured RSS sources.
        
        Args:
            limit_per_source: Maximum articles per source (None = all)
            
        Returns:
            Combined results from all sources
        """
        combined_results = {
            'success': False,
            'total_articles_fetched': 0,
            'total_articles_inserted': 0,
            'source_results': {},
            'errors': []
        }
        
        for source_name, rss_url in RSS_SOURCES.items():
            source_results = self.ingest_news_from_source(
                source_name=source_name,
                rss_url=rss_url,
                limit=limit_per_source
            )
            
            combined_results['source_results'][source_name] = source_results
            combined_results['total_articles_fetched'] += source_results['articles_fetched']
            combined_results['total_articles_inserted'] += source_results['articles_inserted']
            combined_results['errors'].extend(source_results['errors'])
        
        combined_results['success'] = all(
            r['success'] for r in combined_results['source_results'].values()
        )
        
        return combined_results


def ingest_news(
    ticker: Optional[str] = None,
    limit_per_source: Optional[int] = None
) -> Dict[str, Any]:
    """
    Convenience function to ingest news.
    
    Args:
        ticker: Optional company ticker to filter news for
        limit_per_source: Maximum articles per source
        
    Returns:
        Dictionary with ingestion results
    """
    ingester = NewsIngester(ticker=ticker)
    return ingester.ingest_all_sources(limit_per_source=limit_per_source)


def main():
    """Main entry point for command-line usage."""
    import argparse
    import sys
    
    parser = argparse.ArgumentParser(
        description='Ingest news from RSS feeds into VFIS database',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m vfis.ingestion.news_ingest
  python -m vfis.ingestion.news_ingest --ticker <TICKER>
  python -m vfis.ingestion.news_ingest --ticker <TICKER> --limit 10
        """
    )
    
    parser.add_argument(
        '--ticker',
        type=str,
        default=None,
        help='Optional company ticker to filter news for (dynamically provided)'
    )
    
    parser.add_argument(
        '--limit',
        type=int,
        default=None,
        help='Maximum articles per source (default: all)'
    )
    
    parser.add_argument(
        '--log-level',
        type=str,
        default='INFO',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        help='Logging level (default: INFO)'
    )
    
    args = parser.parse_args()
    
    # Configure logging
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    try:
        # Ingest news
        results = ingest_news(
            ticker=args.ticker,
            limit_per_source=args.limit
        )
        
        # Print summary
        print(f"\n{'='*60}")
        print(f"News Ingestion Summary")
        print(f"{'='*60}")
        print(f"Ticker: {args.ticker or 'ALL'}")
        print(f"Total articles fetched: {results['total_articles_fetched']}")
        print(f"Total articles inserted: {results['total_articles_inserted']}")
        print(f"Success: {results['success']}")
        print(f"{'='*60}\n")
        
        if results['errors']:
            print("Errors:")
            for error in results['errors']:
                print(f"  - {error}")
            print()
        
        # Exit with error code if unsuccessful
        sys.exit(0 if results['success'] else 1)
    
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        print(f"\nERROR: {e}\n", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

