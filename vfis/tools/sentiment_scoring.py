"""
Deterministic sentiment scoring for VFIS.

STRICT RULES:
- No LLM usage
- No probabilistic guessing
- Sentiment must be reproducible
- Use rule-based NLP or classical ML (e.g., VADER, TextBlob)
- Store sentiment_score (numeric), sentiment_label (positive/neutral/negative),
  confidence_score, published_at timestamp
"""

import logging
from typing import Dict, Any, Optional, Tuple
from datetime import datetime

try:
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    VADER_AVAILABLE = True
except ImportError:
    VADER_AVAILABLE = False
    logging.warning("vaderSentiment not available. Install with: pip install vaderSentiment")

try:
    from textblob import TextBlob
    TEXTBLOB_AVAILABLE = True
except ImportError:
    TEXTBLOB_AVAILABLE = False
    logging.warning("textblob not available. Install with: pip install textblob")

logger = logging.getLogger(__name__)


class SentimentScorer:
    """
    Deterministic sentiment scoring using rule-based NLP.
    
    CRITICAL: All scoring is deterministic and reproducible.
    No LLM usage, no probabilistic guessing.
    """
    
    def __init__(self):
        """Initialize sentiment scorer with VADER (preferred) or TextBlob fallback."""
        if VADER_AVAILABLE:
            self.analyzer = SentimentIntensityAnalyzer()
            self.method = 'vader'
        elif TEXTBLOB_AVAILABLE:
            self.analyzer = None
            self.method = 'textblob'
        else:
            raise ImportError(
                "No sentiment analysis library available. "
                "Install with: pip install vaderSentiment textblob"
            )
    
    def score_text(self, text: str) -> Dict[str, Any]:
        """
        Score sentiment of text deterministically.
        
        Args:
            text: Text to analyze
            
        Returns:
            Dictionary with:
            - sentiment_score: numeric score (-1 to 1 or similar)
            - sentiment_label: 'positive', 'neutral', or 'negative'
            - confidence_score: confidence in the score (0 to 1)
        """
        if not text or not text.strip():
            return {
                'sentiment_score': 0.0,
                'sentiment_label': 'neutral',
                'confidence_score': 0.0
            }
        
        if self.method == 'vader':
            return self._score_with_vader(text)
        elif self.method == 'textblob':
            return self._score_with_textblob(text)
        else:
            raise ValueError(f"Unknown sentiment scoring method: {self.method}")
    
    def _score_with_vader(self, text: str) -> Dict[str, Any]:
        """
        Score sentiment using VADER.
        
        VADER scores:
        - compound: -1 (most negative) to +1 (most positive)
        - pos, neu, neg: proportions (0 to 1)
        """
        scores = self.analyzer.polarity_scores(text)
        
        compound = scores['compound']
        
        # Determine label based on compound score
        if compound >= 0.05:
            label = 'positive'
            confidence = scores['pos']
        elif compound <= -0.05:
            label = 'negative'
            confidence = scores['neg']
        else:
            label = 'neutral'
            confidence = scores['neu']
        
        return {
            'sentiment_score': compound,  # -1 to 1
            'sentiment_label': label,
            'confidence_score': confidence  # 0 to 1
        }
    
    def _score_with_textblob(self, text: str) -> Dict[str, Any]:
        """
        Score sentiment using TextBlob.
        
        TextBlob polarity: -1 (negative) to +1 (positive)
        TextBlob subjectivity: 0 (objective) to 1 (subjective)
        """
        blob = TextBlob(text)
        polarity = blob.sentiment.polarity
        subjectivity = blob.sentiment.subjectivity
        
        # Determine label
        if polarity > 0.1:
            label = 'positive'
        elif polarity < -0.1:
            label = 'negative'
        else:
            label = 'neutral'
        
        # Use subjectivity as confidence (higher subjectivity = higher confidence in sentiment)
        confidence = abs(polarity) * (0.5 + subjectivity * 0.5)  # Weighted by subjectivity
        
        return {
            'sentiment_score': polarity,  # -1 to 1
            'sentiment_label': label,
            'confidence_score': min(confidence, 1.0)  # Cap at 1.0
        }


def score_news_sentiment(
    news_id: int,
    headline: str,
    content: str
) -> bool:
    """
    Score sentiment for a news article and update the database.
    
    CRITICAL: Sentiment scoring is deterministic and reproducible.
    
    Args:
        news_id: ID of news article in database
        headline: Article headline
        content: Article content/summary
        
    Returns:
        True if successful, False otherwise
    """
    from tradingagents.database.connection import get_db_connection
    
    try:
        # Combine headline and content for sentiment analysis
        text = f"{headline}. {content}".strip()
        
        # Score sentiment
        scorer = SentimentScorer()
        sentiment = scorer.score_text(text)
        
        # Update news table with sentiment scores
        # Note: This assumes sentiment columns exist in news table
        # If not, you'll need to add them via schema migration
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Check if sentiment columns exist
                cur.execute("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = 'news' AND column_name = 'sentiment_score'
                """)
                if not cur.fetchone():
                    logger.warning("Sentiment columns do not exist in news table. Skipping update.")
                    return False
                
                # Update news record with sentiment
                cur.execute("""
                    UPDATE news
                    SET sentiment_score = %s,
                        sentiment_label = %s,
                        confidence_score = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                """, (
                    sentiment['sentiment_score'],
                    sentiment['sentiment_label'],
                    sentiment['confidence_score'],
                    news_id
                ))
                
                conn.commit()
                
                logger.debug(
                    f"Updated sentiment for news {news_id}: "
                    f"{sentiment['sentiment_label']} ({sentiment['sentiment_score']:.3f})"
                )
                
                return True
    
    except Exception as e:
        logger.error(f"Failed to score sentiment for news {news_id}: {e}")
        return False


def batch_score_news_sentiment(ticker: Optional[str] = None, limit: Optional[int] = None) -> Dict[str, Any]:
    """
    Batch score sentiment for news articles.
    
    Args:
        ticker: Optional ticker to filter news for
        limit: Maximum number of articles to score
        
    Returns:
        Dictionary with scoring results
    """
    from tradingagents.database.connection import get_db_connection
    
    results = {
        'success': False,
        'articles_scored': 0,
        'errors': []
    }
    
    try:
        scorer = SentimentScorer()
        
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Get news articles without sentiment scores
                query = """
                    SELECT id, headline, content, company_id
                    FROM news
                    WHERE sentiment_score IS NULL
                """
                params = []
                
                if ticker:
                    # Get company ID
                    from tradingagents.database.dal import FinancialDataAccess
                    company = FinancialDataAccess.get_company_by_ticker(ticker)
                    if company:
                        query += " AND company_id = %s"
                        params.append(company['id'])
                
                query += " ORDER BY published_at DESC"
                
                if limit:
                    query += " LIMIT %s"
                    params.append(limit)
                
                cur.execute(query, params)
                articles = cur.fetchall()
                
                # Score each article
                for article_id, headline, content, company_id in articles:
                    try:
                        text = f"{headline or ''}. {content or ''}".strip()
                        sentiment = scorer.score_text(text)
                        
                        # Update database
                        cur.execute("""
                            UPDATE news
                            SET sentiment_score = %s,
                                sentiment_label = %s,
                                confidence_score = %s,
                                updated_at = CURRENT_TIMESTAMP
                            WHERE id = %s
                        """, (
                            sentiment['sentiment_score'],
                            sentiment['sentiment_label'],
                            sentiment['confidence_score'],
                            article_id
                        ))
                        
                        results['articles_scored'] += 1
                    
                    except Exception as e:
                        error_msg = f"Failed to score article {article_id}: {str(e)}"
                        logger.warning(error_msg)
                        results['errors'].append(error_msg)
                        continue
                
                conn.commit()
        
        results['success'] = True
        
        logger.info(f"Scored sentiment for {results['articles_scored']} news articles")
        
    except Exception as e:
        error_msg = f"Failed to batch score news sentiment: {str(e)}"
        logger.error(error_msg, exc_info=True)
        results['errors'].append(error_msg)
    
    return results

