"""
Schema update for sentiment scoring columns in news table.

This module ensures sentiment columns exist in the news table.
"""

import logging
from tradingagents.database.connection import get_db_connection

logger = logging.getLogger(__name__)


def add_sentiment_columns_to_news():
    """
    Add sentiment scoring columns to news table if they don't exist.
    
    Adds:
    - sentiment_score: NUMERIC(5, 3) - sentiment score (-1 to 1)
    - sentiment_label: VARCHAR(20) - 'positive', 'neutral', or 'negative'
    - confidence_score: NUMERIC(5, 3) - confidence in sentiment (0 to 1)
    """
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            # Check if sentiment_score column exists
            cur.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'news' AND column_name = 'sentiment_score'
            """)
            if not cur.fetchone():
                cur.execute("ALTER TABLE news ADD COLUMN sentiment_score NUMERIC(5, 3);")
                logger.info("Added sentiment_score column to news table")
            
            # Check if sentiment_label column exists
            cur.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'news' AND column_name = 'sentiment_label'
            """)
            if not cur.fetchone():
                cur.execute("""
                    ALTER TABLE news 
                    ADD COLUMN sentiment_label VARCHAR(20) 
                    CHECK (sentiment_label IN ('positive', 'neutral', 'negative'));
                """)
                logger.info("Added sentiment_label column to news table")
            
            # Check if confidence_score column exists
            cur.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'news' AND column_name = 'confidence_score'
            """)
            if not cur.fetchone():
                cur.execute("ALTER TABLE news ADD COLUMN confidence_score NUMERIC(5, 3);")
                logger.info("Added confidence_score column to news table")
            
            conn.commit()
            logger.info("Sentiment columns updated in news table")

