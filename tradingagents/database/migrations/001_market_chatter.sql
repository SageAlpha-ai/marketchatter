-- Migration: Create market_chatter table
-- Description: Stores market chatter from various sources (news, Twitter, Reddit, StockTwits)
-- Date: 2024

CREATE TABLE IF NOT EXISTS market_chatter (
    id SERIAL PRIMARY KEY,
    ticker TEXT NOT NULL,
    company_name TEXT,
    source TEXT NOT NULL,  -- news / twitter / reddit / stocktwits
    source_type TEXT NOT NULL,  -- news / social
    content TEXT NOT NULL,
    url TEXT,
    published_at TIMESTAMP,
    sentiment_score NUMERIC,  -- range -1.0 to +1.0
    sentiment_label TEXT,     -- positive / neutral / negative
    confidence NUMERIC,
    raw_payload JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Prevent exact duplicates
    CONSTRAINT unique_chatter UNIQUE (ticker, source, content)
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_market_chatter_ticker ON market_chatter(ticker);
CREATE INDEX IF NOT EXISTS idx_market_chatter_source ON market_chatter(source);
CREATE INDEX IF NOT EXISTS idx_market_chatter_published_at ON market_chatter(published_at);
CREATE INDEX IF NOT EXISTS idx_market_chatter_source_type ON market_chatter(source_type);
CREATE INDEX IF NOT EXISTS idx_market_chatter_sentiment_label ON market_chatter(sentiment_label);

-- Add comment
COMMENT ON TABLE market_chatter IS 'Market chatter from various sources including news, social media, and forums';
COMMENT ON COLUMN market_chatter.sentiment_score IS 'Sentiment score ranging from -1.0 (negative) to +1.0 (positive)';
COMMENT ON COLUMN market_chatter.confidence IS 'Confidence score for sentiment analysis (0.0 to 1.0)';

