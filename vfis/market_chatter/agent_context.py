"""
Agent context and prompt templates for market chatter analysis.

These templates are LLM-agnostic and reference structured chatter data
to avoid hallucination.
"""

from typing import List, Dict, Optional
from datetime import datetime, timedelta


def market_chatter_summary_template(ticker: str, chatter_items: List[Dict]) -> str:
    """
    Generate prompt template for market chatter summary.
    
    Args:
        ticker: Stock ticker symbol
        chatter_items: List of chatter items with sentiment
        
    Returns:
        Prompt template string
    """
    if not chatter_items:
        return f"No market chatter found for {ticker} in the specified time period."
    
    # Group by source
    by_source = {}
    for item in chatter_items:
        source = item.get("source", "unknown")
        if source not in by_source:
            by_source[source] = []
        by_source[source].append(item)
    
    template = f"Market Chatter Summary for {ticker}\n\n"
    template += "Sources and counts:\n"
    for source, items in by_source.items():
        template += f"- {source}: {len(items)} items\n"
    
    template += "\nStructured chatter data (use ONLY this data, do not infer or hallucinate):\n\n"
    
    for idx, item in enumerate(chatter_items[:50], 1):  # Limit to 50 items
        template += f"{idx}. Source: {item.get('source')} | Type: {item.get('source_type')}\n"
        template += f"   Content: {item.get('content', '')[:200]}...\n"
        template += f"   Sentiment: {item.get('sentiment_label', 'neutral')} "
        template += f"(score: {item.get('sentiment_score', 0.0)}, "
        template += f"confidence: {item.get('confidence', 0.0)})\n"
        template += f"   Published: {item.get('published_at')}\n"
        template += f"   URL: {item.get('url', 'N/A')}\n\n"
    
    template += "\nInstructions:\n"
    template += "- Summarize the key themes and sentiment trends\n"
    template += "- Cite specific sources and timestamps\n"
    template += "- DO NOT generate or infer financial numbers\n"
    template += "- DO NOT make trading recommendations\n"
    template += "- Base analysis ONLY on the structured data provided above\n"
    
    return template


def bullish_vs_bearish_view_template(ticker: str, chatter_items: List[Dict]) -> str:
    """
    Generate prompt template for bullish vs bearish analysis.
    
    Args:
        ticker: Stock ticker symbol
        chatter_items: List of chatter items with sentiment
        
    Returns:
        Prompt template string
    """
    if not chatter_items:
        return f"No market chatter found for {ticker}."
    
    # Separate by sentiment
    positive_items = [item for item in chatter_items if item.get("sentiment_label") == "positive"]
    negative_items = [item for item in chatter_items if item.get("sentiment_label") == "negative"]
    neutral_items = [item for item in chatter_items if item.get("sentiment_label") == "neutral"]
    
    template = f"Bullish vs Bearish Analysis for {ticker}\n\n"
    template += f"Total items: {len(chatter_items)}\n"
    template += f"Positive: {len(positive_items)} | Negative: {len(negative_items)} | Neutral: {len(neutral_items)}\n\n"
    
    template += "BULLISH SIGNALS (positive sentiment items):\n"
    for idx, item in enumerate(positive_items[:10], 1):
        template += f"{idx}. [{item.get('source')}] {item.get('content', '')[:150]}...\n"
        template += f"   Score: {item.get('sentiment_score', 0.0)} | Published: {item.get('published_at')}\n\n"
    
    template += "\nBEARISH SIGNALS (negative sentiment items):\n"
    for idx, item in enumerate(negative_items[:10], 1):
        template += f"{idx}. [{item.get('source')}] {item.get('content', '')[:150]}...\n"
        template += f"   Score: {item.get('sentiment_score', 0.0)} | Published: {item.get('published_at')}\n\n"
    
    template += "\nInstructions:\n"
    template += "- Compare bullish vs bearish signals from the structured data above\n"
    template += "- Identify key themes in each camp\n"
    template += "- DO NOT generate financial projections or price targets\n"
    template += "- Cite specific sources and timestamps for each claim\n"
    template += "- Base analysis ONLY on the structured data provided\n"
    
    return template


def rumor_vs_fact_analysis_template(ticker: str, chatter_items: List[Dict]) -> str:
    """
    Generate prompt template for rumor vs fact analysis.
    
    Args:
        ticker: Stock ticker symbol
        chatter_items: List of chatter items with sentiment
        
    Returns:
        Prompt template string
    """
    if not chatter_items:
        return f"No market chatter found for {ticker}."
    
    # Separate by source type
    news_items = [item for item in chatter_items if item.get("source_type") == "news"]
    social_items = [item for item in chatter_items if item.get("source_type") == "social"]
    
    template = f"Rumor vs Fact Analysis for {ticker}\n\n"
    template += f"News sources: {len(news_items)} items\n"
    template += f"Social media: {len(social_items)} items\n\n"
    
    template += "NEWS SOURCES (factual reporting):\n"
    for idx, item in enumerate(news_items[:10], 1):
        template += f"{idx}. [{item.get('source')}] {item.get('content', '')[:150]}...\n"
        template += f"   URL: {item.get('url', 'N/A')} | Published: {item.get('published_at')}\n\n"
    
    template += "\nSOCIAL MEDIA (may contain rumors/opinions):\n"
    for idx, item in enumerate(social_items[:10], 1):
        template += f"{idx}. [{item.get('source')}] {item.get('content', '')[:150]}...\n"
        template += f"   URL: {item.get('url', 'N/A')} | Published: {item.get('published_at')}\n\n"
    
    template += "\nInstructions:\n"
    template += "- Identify claims that appear in news sources vs social media\n"
    template += "- Highlight potential rumors or unverified claims\n"
    template += "- Note if themes are consistent across source types\n"
    template += "- DO NOT generate or infer financial numbers\n"
    template += "- Cite specific sources and URLs for verification\n"
    template += "- Base analysis ONLY on the structured data provided\n"
    
    return template


def sentiment_trend_last_7_days_template(ticker: str, chatter_items: List[Dict]) -> str:
    """
    Generate prompt template for sentiment trend analysis over last 7 days.
    
    Args:
        ticker: Stock ticker symbol
        chatter_items: List of chatter items with sentiment
        
    Returns:
        Prompt template string
    """
    if not chatter_items:
        return f"No market chatter found for {ticker} in the last 7 days."
    
    # Filter items from last 7 days
    seven_days_ago = datetime.utcnow() - timedelta(days=7)
    recent_items = [
        item for item in chatter_items
        if isinstance(item.get("published_at"), datetime) and item.get("published_at") >= seven_days_ago
    ]
    
    if not recent_items:
        return f"No market chatter found for {ticker} in the last 7 days."
    
    # Group by day
    by_day = {}
    for item in recent_items:
        pub_date = item.get("published_at")
        if isinstance(pub_date, datetime):
            day_key = pub_date.date().isoformat()
            if day_key not in by_day:
                by_day[day_key] = {"positive": 0, "negative": 0, "neutral": 0, "items": []}
            sentiment = item.get("sentiment_label", "neutral")
            by_day[day_key][sentiment] += 1
            by_day[day_key]["items"].append(item)
    
    template = f"Sentiment Trend Analysis (Last 7 Days) for {ticker}\n\n"
    template += f"Total items: {len(recent_items)}\n\n"
    
    template += "Daily breakdown:\n"
    for day in sorted(by_day.keys(), reverse=True):
        day_data = by_day[day]
        template += f"{day}: "
        template += f"Positive: {day_data['positive']}, "
        template += f"Negative: {day_data['negative']}, "
        template += f"Neutral: {day_data['neutral']}\n"
    
    template += "\nRecent items (last 7 days):\n"
    for idx, item in enumerate(recent_items[:20], 1):
        template += f"{idx}. [{item.get('published_at')}] [{item.get('source')}] "
        template += f"{item.get('sentiment_label', 'neutral')} (score: {item.get('sentiment_score', 0.0)})\n"
        template += f"   {item.get('content', '')[:100]}...\n\n"
    
    template += "\nInstructions:\n"
    template += "- Identify sentiment trends over the 7-day period\n"
    template += "- Note any significant shifts in sentiment\n"
    template += "- Correlate sentiment changes with key events/dates\n"
    template += "- DO NOT generate financial projections\n"
    template += "- Base analysis ONLY on the structured data provided above\n"
    
    return template


# Export all templates
__all__ = [
    "market_chatter_summary_template",
    "bullish_vs_bearish_view_template",
    "rumor_vs_fact_analysis_template",
    "sentiment_trend_last_7_days_template",
]

