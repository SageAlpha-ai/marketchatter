"""
CLI and function entrypoint for market chatter ingestion.

Supports ingesting from multiple FREE sources (no API keys required):
- Google News RSS (free, no API key)
- Yahoo Finance RSS (free, no API key)
- Reddit public JSON (free, no auth)
- RSS (generic feeds, no API key)
- Alpha Vantage News API (only if ALPHA_VANTAGE_API_KEY env var exists)

All sources flow through the canonical pipeline:
    chatter_schema.py → MarketChatterRecord
    ingest_chatter.py → normalization
    chatter_persist.py → persist_market_chatter()

Usage:
    # CLI - ticker is required, dynamically provided
    python -m tradingagents.dataflows.ingest_chatter --ticker AAPL --days 7
    
    # Function - ticker parameter is required
    from tradingagents.dataflows.ingest_chatter import ingest_chatter
    results = ingest_chatter("<TICKER>", days=7)  # Ticker provided dynamically
    
NOTE: No hardcoded tickers. All ticker values must be provided dynamically.
"""

import argparse
import logging
import sys
import hashlib
import json
import requests
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any

from .chatter_schema import MarketChatterRecord, SOURCE_TYPE_NEWS, SOURCE_TYPE_SOCIAL
from tradingagents.database.chatter_persist import persist_market_chatter

logger = logging.getLogger(__name__)

# =============================================================================
# FREE DATA SOURCE CONFIGURATION (NO API KEYS REQUIRED)
# =============================================================================

# Google News RSS - builds search query from ticker + keywords
GOOGLE_NEWS_RSS_URL = "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"

# Yahoo Finance RSS - ticker-specific headlines
YAHOO_FINANCE_RSS_URL = "https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker}&region=US&lang=en-US"

# Reddit public JSON search - no OAuth required
REDDIT_SEARCH_URL = "https://www.reddit.com/search.json"
REDDIT_USER_AGENT = "vfis-market-intel/1.0"
REDDIT_SUBREDDITS = ["wallstreetbets", "stocks", "investing", "StockMarket"]


def ingest_chatter(
    ticker: str,
    company_name: Optional[str] = None,
    days: int = 7,
    sources: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Ingest market chatter from configured sources.
    
    FREE sources (always available, no API key):
    1. Google News RSS - search-based financial news
    2. Yahoo Finance RSS - ticker-specific headlines
    3. Reddit public JSON - social sentiment from finance subreddits
    4. Generic RSS feeds - various financial news outlets
    
    PAID sources (only if API key exists):
    5. Alpha Vantage (only if ALPHA_VANTAGE_API_KEY exists)
    
    Args:
        ticker: Stock ticker symbol (dynamically provided, not hardcoded)
        company_name: Optional company name for broader search
        days: Number of days to look back (default: 7)
        sources: Optional list of sources to ingest from. Default: all available.
                 Valid: ['google_news', 'yahoo_finance', 'reddit', 'rss', 'alpha_vantage']
    
    Returns:
        Dictionary with results:
        {
            "ticker": "<TICKER>",  # Dynamic
            "total_fetched": 150,
            "total_inserted": 120,
            "total_skipped": 30,
            "total_errors": 0,
            "sources": {
                "google_news": { ... },
                "yahoo_finance": { ... },
                "reddit": { ... },
                "rss": { ... },
                "alpha_vantage": { ... }  # Only if API key exists
            }
        }
    """
    from tradingagents.database.chatter_persist import ensure_market_chatter_table
    
    ticker = ticker.upper()
    results = {
        "ticker": ticker,
        "company_name": company_name,
        "days": days,
        "total_fetched": 0,
        "total_inserted": 0,
        "total_skipped": 0,
        "total_errors": 0,
        "sources": {},
        "timestamp": datetime.utcnow().isoformat()
    }
    
    # Ensure table exists
    if not ensure_market_chatter_table():
        logger.error("Failed to ensure market_chatter table exists")
        results["error"] = "Failed to create/verify market_chatter table"
        return results
    
    # Import env from canonical source
    try:
        from vfis.core.env import ALPHA_VANTAGE_AVAILABLE
    except ImportError:
        # Fallback if vfis.core.env not available
        import os
        ALPHA_VANTAGE_AVAILABLE = bool(os.getenv("ALPHA_VANTAGE_API_KEY", "").strip())
    
    # Determine available sources - FREE sources are always available
    available_sources = {
        "google_news": _ingest_google_news,      # FREE - no API key
        "yahoo_finance": _ingest_yahoo_finance,  # FREE - no API key
        "reddit": _ingest_reddit,                # FREE - no auth
        "rss": _ingest_rss,                      # FREE - generic RSS feeds
    }
    
    # Add Alpha Vantage only if API key exists
    if ALPHA_VANTAGE_AVAILABLE:
        available_sources["alpha_vantage"] = _ingest_alpha_vantage
        logger.info("[INGEST] Alpha Vantage API key found, adding to sources")
    else:
        logger.info("[INGEST] No Alpha Vantage API key, using free sources only")
    
    # Filter to requested sources if specified
    if sources:
        sources_to_run = {k: v for k, v in available_sources.items() if k in sources}
    else:
        sources_to_run = available_sources
    
    # Run ingestion for each source
    for source_name, ingest_func in sources_to_run.items():
        try:
            logger.info(f"Ingesting from {source_name} for {ticker}...")
            source_result = ingest_func(ticker, company_name, days)
            
            results["sources"][source_name] = source_result
            results["total_fetched"] += source_result.get("fetched", 0)
            results["total_inserted"] += source_result.get("inserted", 0)
            results["total_skipped"] += source_result.get("skipped", 0)
            results["total_errors"] += source_result.get("errors", 0)
            
        except Exception as e:
            logger.error(f"Error ingesting from {source_name}: {e}", exc_info=True)
            results["sources"][source_name] = {
                "error": str(e),
                "fetched": 0,
                "inserted": 0,
                "skipped": 0,
                "errors": 1
            }
            results["total_errors"] += 1
    
    # Warn if nothing was inserted
    if results["total_inserted"] == 0 and results["total_fetched"] > 0:
        logger.warning(
            f"Zero new records inserted from {results['total_fetched']} fetched items for {ticker}"
        )
    elif results["total_fetched"] == 0:
        logger.warning(f"Zero items fetched for {ticker} - check data sources")
    
    logger.info(
        f"Chatter ingestion complete for {ticker}: "
        f"fetched={results['total_fetched']}, "
        f"inserted={results['total_inserted']}, "
        f"skipped={results['total_skipped']}, "
        f"errors={results['total_errors']}"
    )
    
    return results


def _ingest_google_news(ticker: str, company_name: Optional[str], days: int) -> Dict[str, Any]:
    """
    Ingest from Google News RSS - FREE, NO API KEY.
    
    Builds search query from ticker + financial keywords for better relevance.
    
    Args:
        ticker: Stock ticker symbol (uppercase)
        company_name: Optional company name for broader search
        days: Number of days to look back
    
    Returns:
        Dict with fetched, inserted, skipped, errors counts
    """
    import feedparser
    from urllib.parse import quote_plus
    
    result = {"fetched": 0, "inserted": 0, "skipped": 0, "errors": 0, "source": "google_news"}
    records: List[MarketChatterRecord] = []
    cutoff = datetime.utcnow() - timedelta(days=days)
    
    # Build search query with proper URL encoding
    query_parts = [ticker, "stock"]
    if company_name:
        # URL encode company name to handle spaces and special chars
        query_parts.append(quote_plus(company_name))
    query = "+".join(query_parts)
    
    feed_url = GOOGLE_NEWS_RSS_URL.format(query=query)
    
    try:
        logger.info(f"[GOOGLE_NEWS] Fetching for {ticker} with query: {query}")
        feed = feedparser.parse(feed_url)
        
        if feed.bozo and feed.bozo_exception:
            logger.warning(f"[GOOGLE_NEWS] Feed parse error: {feed.bozo_exception}")
        
        for entry in feed.entries[:50]:  # Limit per query
            try:
                title = entry.get('title', '')
                summary = entry.get('summary', entry.get('description', ''))
                
                # Parse date
                published_at = None
                if hasattr(entry, 'published_parsed') and entry.published_parsed:
                    try:
                        published_at = datetime(*entry.published_parsed[:6])
                    except Exception:
                        pass
                
                if not published_at:
                    published_at = datetime.utcnow()
                
                if published_at < cutoff:
                    continue  # Skip old entries
                
                # Generate source_id from URL
                url = entry.get('link', '')
                source_id = hashlib.sha256(f"google_news_{url}".encode()).hexdigest()[:32] if url else ''
                
                if not source_id:
                    continue
                
                record = MarketChatterRecord(
                    ticker=ticker,
                    source='google_news',
                    source_id=source_id,
                    title=title[:500],
                    summary=summary[:2000],
                    url=url,
                    published_at=published_at,
                    source_type=SOURCE_TYPE_NEWS,
                    company_name=company_name,
                    raw_payload={'feed': 'Google News RSS', 'query': query}
                )
                records.append(record)
                result["fetched"] += 1
                
            except Exception as e:
                logger.debug(f"[GOOGLE_NEWS] Error parsing entry: {e}")
                continue
        
        logger.info(f"[GOOGLE_NEWS] Fetched {result['fetched']} items for {ticker}")
        
    except Exception as e:
        logger.warning(f"[GOOGLE_NEWS] Error fetching for {ticker}: {e}")
        result["errors"] += 1
    
    # Persist via canonical path
    if records:
        counts = persist_market_chatter(records)
        result["inserted"] = counts["inserted"]
        result["skipped"] = counts["skipped"]
        result["errors"] += counts["errors"]
    elif result["fetched"] == 0:
        logger.warning(f"[GOOGLE_NEWS] Zero items fetched for {ticker}")
    
    return result


def _ingest_yahoo_finance(ticker: str, company_name: Optional[str], days: int) -> Dict[str, Any]:
    """
    Ingest from Yahoo Finance RSS - FREE, NO API KEY.
    
    Fetches ticker-specific headlines from Yahoo Finance.
    
    Args:
        ticker: Stock ticker symbol (uppercase)
        company_name: Optional company name (not used in query)
        days: Number of days to look back
    
    Returns:
        Dict with fetched, inserted, skipped, errors counts
    """
    import feedparser
    
    result = {"fetched": 0, "inserted": 0, "skipped": 0, "errors": 0, "source": "yahoo_finance"}
    records: List[MarketChatterRecord] = []
    cutoff = datetime.utcnow() - timedelta(days=days)
    
    feed_url = YAHOO_FINANCE_RSS_URL.format(ticker=ticker.upper())
    
    try:
        logger.info(f"[YAHOO] Fetching for {ticker}")
        feed = feedparser.parse(feed_url)
        
        if feed.bozo and feed.bozo_exception:
            logger.warning(f"[YAHOO] Feed parse error: {feed.bozo_exception}")
        
        for entry in feed.entries[:50]:  # Limit
            try:
                title = entry.get('title', '')
                summary = entry.get('summary', entry.get('description', ''))
                
                # Parse date
                published_at = None
                if hasattr(entry, 'published_parsed') and entry.published_parsed:
                    try:
                        published_at = datetime(*entry.published_parsed[:6])
                    except Exception:
                        pass
                
                if not published_at:
                    published_at = datetime.utcnow()
                
                if published_at < cutoff:
                    continue
                
                # Generate source_id
                url = entry.get('link', '')
                source_id = hashlib.sha256(f"yahoo_{url}".encode()).hexdigest()[:32] if url else ''
                
                if not source_id:
                    continue
                
                record = MarketChatterRecord(
                    ticker=ticker,
                    source='yahoo_finance',
                    source_id=source_id,
                    title=title[:500],
                    summary=summary[:2000],
                    url=url,
                    published_at=published_at,
                    source_type=SOURCE_TYPE_NEWS,
                    company_name=company_name,
                    raw_payload={'feed': 'Yahoo Finance RSS'}
                )
                records.append(record)
                result["fetched"] += 1
                
            except Exception as e:
                logger.debug(f"[YAHOO] Error parsing entry: {e}")
                continue
        
        logger.info(f"[YAHOO] Fetched {result['fetched']} items for {ticker}")
        
    except Exception as e:
        logger.warning(f"[YAHOO] Error fetching for {ticker}: {e}")
        result["errors"] += 1
    
    # Persist via canonical path
    if records:
        counts = persist_market_chatter(records)
        result["inserted"] = counts["inserted"]
        result["skipped"] = counts["skipped"]
        result["errors"] += counts["errors"]
    elif result["fetched"] == 0:
        logger.warning(f"[YAHOO] Zero items fetched for {ticker}")
    
    return result


def _ingest_reddit(ticker: str, company_name: Optional[str], days: int) -> Dict[str, Any]:
    """
    Ingest from Reddit public JSON - FREE, NO AUTH REQUIRED.
    
    Uses Reddit's public JSON endpoints (no OAuth needed).
    Respects rate limits with User-Agent header.
    
    Args:
        ticker: Stock ticker symbol (uppercase)
        company_name: Optional company name for broader search
        days: Number of days to look back
    
    Returns:
        Dict with fetched, inserted, skipped, errors counts
    """
    result = {"fetched": 0, "inserted": 0, "skipped": 0, "errors": 0, "source": "reddit"}
    records: List[MarketChatterRecord] = []
    cutoff = datetime.utcnow() - timedelta(days=days)
    
    headers = {
        "User-Agent": REDDIT_USER_AGENT
    }
    
    # Build search query
    query = f"{ticker}"
    if company_name:
        query = f"{ticker} OR {company_name}"
    
    # Search across relevant subreddits
    for subreddit in REDDIT_SUBREDDITS:
        try:
            # Use subreddit-specific search endpoint
            url = f"https://www.reddit.com/r/{subreddit}/search.json"
            params = {
                "q": query,
                "restrict_sr": "on",  # Restrict to this subreddit
                "sort": "new",
                "limit": 25,
                "t": "week"  # Time filter
            }
            
            logger.debug(f"[REDDIT] Searching r/{subreddit} for {ticker}")
            
            response = requests.get(url, params=params, headers=headers, timeout=10)
            
            if response.status_code == 429:
                logger.warning(f"[REDDIT] Rate limited on r/{subreddit}")
                continue
            
            if response.status_code != 200:
                logger.warning(f"[REDDIT] HTTP {response.status_code} from r/{subreddit}")
                continue
            
            data = response.json()
            posts = data.get("data", {}).get("children", [])
            
            for post in posts:
                try:
                    post_data = post.get("data", {})
                    
                    # Parse timestamp
                    created_utc = post_data.get("created_utc", 0)
                    published_at = datetime.utcfromtimestamp(created_utc) if created_utc else datetime.utcnow()
                    
                    if published_at < cutoff:
                        continue
                    
                    # Generate source_id from Reddit post ID
                    reddit_id = post_data.get("id", "")
                    source_id = f"reddit_{reddit_id}" if reddit_id else ""
                    
                    if not source_id:
                        continue
                    
                    title = post_data.get("title", "")[:500]
                    selftext = post_data.get("selftext", "")[:2000]
                    permalink = post_data.get("permalink", "")
                    post_url = f"https://reddit.com{permalink}" if permalink else ""
                    
                    record = MarketChatterRecord(
                        ticker=ticker,
                        source='reddit',
                        source_id=source_id,
                        title=title,
                        summary=selftext if selftext else title,
                        url=post_url,
                        published_at=published_at,
                        source_type=SOURCE_TYPE_SOCIAL,
                        company_name=company_name,
                        raw_payload={
                            "subreddit": subreddit,
                            "score": post_data.get("score", 0),
                            "num_comments": post_data.get("num_comments", 0),
                            "upvote_ratio": post_data.get("upvote_ratio", 0)
                        }
                    )
                    records.append(record)
                    result["fetched"] += 1
                    
                except Exception as e:
                    logger.debug(f"[REDDIT] Error parsing post: {e}")
                    continue
            
        except requests.exceptions.Timeout:
            logger.warning(f"[REDDIT] Timeout on r/{subreddit}")
            result["errors"] += 1
        except requests.exceptions.RequestException as e:
            logger.warning(f"[REDDIT] Request error on r/{subreddit}: {e}")
            result["errors"] += 1
        except Exception as e:
            logger.warning(f"[REDDIT] Error fetching r/{subreddit}: {e}")
            result["errors"] += 1
    
    logger.info(f"[REDDIT] Fetched {result['fetched']} items for {ticker}")
    
    # Persist via canonical path
    if records:
        counts = persist_market_chatter(records)
        result["inserted"] = counts["inserted"]
        result["skipped"] = counts["skipped"]
        result["errors"] += counts["errors"]
    elif result["fetched"] == 0:
        logger.warning(f"[REDDIT] Zero items fetched for {ticker}")
    
    return result


def _ingest_rss(ticker: str, company_name: Optional[str], days: int) -> Dict[str, Any]:
    """
    Ingest from generic RSS feeds - FREE, NO API KEY.
    
    Uses various financial news RSS feeds as fallback/additional source.
    
    Args:
        ticker: Stock ticker symbol (uppercase)
        company_name: Optional company name
        days: Number of days to look back
    
    Returns:
        Dict with fetched, inserted, skipped, errors counts
    """
    import feedparser
    
    RSS_FEEDS = {
        'CNBC TV18': 'https://www.cnbctv18.com/rss/',
        'Moneycontrol': 'https://www.moneycontrol.com/rss/',
        'Economic Times': 'https://economictimes.indiatimes.com/rssfeedsdefault.cms',
        'MarketWatch': 'https://feeds.marketwatch.com/marketwatch/marketpulse/',
        'Investing.com': 'https://www.investing.com/rss/news.rss'
    }
    
    result = {"fetched": 0, "inserted": 0, "skipped": 0, "errors": 0, "source": "rss"}
    records: List[MarketChatterRecord] = []
    cutoff = datetime.utcnow() - timedelta(days=days)
    
    for feed_name, feed_url in RSS_FEEDS.items():
        try:
            feed = feedparser.parse(feed_url)
            
            for entry in feed.entries[:50]:  # Limit per feed
                # Check if entry mentions ticker
                title = entry.get('title', '')
                summary = entry.get('summary', entry.get('description', ''))
                content = f"{title} {summary}".upper()
                
                if ticker not in content:
                    continue  # Skip irrelevant entries
                
                # Parse date
                published_at = None
                if hasattr(entry, 'published_parsed') and entry.published_parsed:
                    try:
                        published_at = datetime(*entry.published_parsed[:6])
                    except Exception:
                        pass
                
                if not published_at:
                    published_at = datetime.utcnow()
                
                if published_at < cutoff:
                    continue  # Skip old entries
                
                # Generate source_id from URL
                url = entry.get('link', '')
                source_id = hashlib.sha256(f"rss_{url}".encode()).hexdigest()[:32] if url else ''
                
                if not source_id:
                    continue
                
                record = MarketChatterRecord(
                    ticker=ticker,
                    source='rss',
                    source_id=source_id,
                    title=title[:500],
                    summary=summary[:2000],
                    url=url,
                    published_at=published_at,
                    source_type=SOURCE_TYPE_NEWS,
                    company_name=company_name,
                    raw_payload={'feed': feed_name}
                )
                records.append(record)
                result["fetched"] += 1
                
        except Exception as e:
            logger.warning(f"[RSS] Error fetching {feed_name}: {e}")
            result["errors"] += 1
    
    logger.info(f"[RSS] Fetched {result['fetched']} items for {ticker}")
    
    # Persist via canonical path
    if records:
        counts = persist_market_chatter(records)
        result["inserted"] = counts["inserted"]
        result["skipped"] = counts["skipped"]
        result["errors"] += counts["errors"]
    elif result["fetched"] == 0:
        logger.warning(f"[RSS] Zero items fetched for {ticker}")
    
    return result


def _ingest_alpha_vantage(ticker: str, company_name: Optional[str], days: int) -> Dict[str, Any]:
    """
    Ingest from Alpha Vantage News API - REQUIRES API KEY.
    
    Only called if ALPHA_VANTAGE_API_KEY env var exists.
    
    Args:
        ticker: Stock ticker symbol
        company_name: Optional company name
        days: Number of days to look back
    
    Returns:
        Dict with fetched, inserted, skipped, errors counts
    """
    from .alpha_vantage_chatter import ingest_alpha_vantage_news
    return ingest_alpha_vantage_news(ticker, company_name, days)


def _ingest_twitter(ticker: str, company_name: Optional[str], days: int) -> Dict[str, Any]:
    """
    Placeholder for Twitter/X ingestion.
    
    NOTE: Twitter API requires paid access. Not implementing to avoid costs.
    """
    logger.warning("[TWITTER] Twitter/X API requires paid access, skipping")
    return {"fetched": 0, "inserted": 0, "skipped": 0, "errors": 0, "source": "twitter", "message": "Requires paid API"}


def ingest_universe(
    tickers: List[str],
    company_names: Optional[Dict[str, str]] = None,
    days: int = 7,
    sources: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Ingest market chatter for multiple tickers.
    
    Args:
        tickers: List of ticker symbols
        company_names: Optional dict mapping ticker -> company_name
        days: Number of days to look back
        sources: Optional list of sources to use
    
    Returns:
        Dictionary with results per ticker
    """
    company_names = company_names or {}
    results = {
        "tickers": tickers,
        "days": days,
        "results": {},
        "summary": {
            "total_fetched": 0,
            "total_inserted": 0,
            "total_skipped": 0,
            "total_errors": 0
        },
        "timestamp": datetime.utcnow().isoformat()
    }
    
    for ticker in tickers:
        company_name = company_names.get(ticker.upper())
        ticker_result = ingest_chatter(ticker, company_name, days, sources)
        results["results"][ticker.upper()] = ticker_result
        
        results["summary"]["total_fetched"] += ticker_result["total_fetched"]
        results["summary"]["total_inserted"] += ticker_result["total_inserted"]
        results["summary"]["total_skipped"] += ticker_result["total_skipped"]
        results["summary"]["total_errors"] += ticker_result["total_errors"]
    
    # Warn if nothing inserted
    if results["summary"]["total_inserted"] == 0 and results["summary"]["total_fetched"] > 0:
        logger.warning(
            f"Zero new records from {results['summary']['total_fetched']} fetched items across {len(tickers)} tickers"
        )
    
    logger.info(
        f"Universe ingestion complete: {len(tickers)} tickers, "
        f"total inserted={results['summary']['total_inserted']}"
    )
    
    return results


def main():
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(
        description="Ingest market chatter from various sources",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Ingest for a single ticker (RSS by default)
    python -m tradingagents.dataflows.ingest_chatter --ticker AAPL
    
    # Ingest with company name for better search
    python -m tradingagents.dataflows.ingest_chatter --ticker MSFT --company "Microsoft Corporation"
    
    # Ingest last 14 days
    python -m tradingagents.dataflows.ingest_chatter --ticker GOOGL --days 14
    
    # Ingest from specific source only
    python -m tradingagents.dataflows.ingest_chatter --ticker NVDA --source rss
        """
    )
    
    parser.add_argument(
        "--ticker",
        type=str,
        required=True,
        help="Stock ticker symbol (e.g., your target ticker)"
    )
    
    parser.add_argument(
        "--company",
        type=str,
        default=None,
        help="Company name for broader search (optional)"
    )
    
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Number of days to look back (default: 7)"
    )
    
    parser.add_argument(
        "--source",
        type=str,
        choices=["google_news", "yahoo_finance", "reddit", "rss", "alpha_vantage", "twitter"],
        default=None,
        help="Specific source to ingest from (default: all free sources). Free sources: google_news, yahoo_finance, reddit, rss"
    )
    
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: INFO)"
    )
    
    args = parser.parse_args()
    
    # Configure logging
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    # Load environment variables
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
    
    # Initialize database
    try:
        from tradingagents.database.connection import init_database
        init_database()
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        sys.exit(1)
    
    # Run ingestion
    sources = [args.source] if args.source else None
    results = ingest_chatter(args.ticker, args.company, args.days, sources)
    
    # Print summary
    print("\n" + "=" * 60)
    print("MARKET CHATTER INGESTION SUMMARY")
    print("=" * 60)
    print(f"Ticker:    {results['ticker']}")
    print(f"Company:   {results.get('company_name') or 'N/A'}")
    print(f"Days:      {results['days']}")
    print("-" * 60)
    print(f"Fetched:   {results['total_fetched']}")
    print(f"Inserted:  {results['total_inserted']}")
    print(f"Skipped:   {results['total_skipped']} (duplicates)")
    print(f"Errors:    {results['total_errors']}")
    print("-" * 60)
    print("Per-source breakdown:")
    for source, source_result in results.get("sources", {}).items():
        print(f"  {source}: fetched={source_result.get('fetched', 0)}, "
              f"inserted={source_result.get('inserted', 0)}, "
              f"errors={source_result.get('errors', 0)}")
    print("=" * 60)
    
    # Exit with appropriate code
    sys.exit(0 if results['total_errors'] == 0 else 1)


if __name__ == "__main__":
    main()
