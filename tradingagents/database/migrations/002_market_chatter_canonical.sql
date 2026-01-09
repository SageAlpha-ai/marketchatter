-- Migration: 002_market_chatter_canonical
-- Description: Create canonical market_chatter table for multi-source chatter ingestion
-- Supports: Alpha Vantage, Reddit, Twitter, StockTwits, and future sources
-- Date: 2025-01-07
-- 
-- This migration is IDEMPOTENT - safe to run multiple times

-- Drop old table if exists (from previous migrations)
-- This handles schema drift cleanly
DROP TABLE IF EXISTS market_chatter CASCADE;

-- Create canonical market_chatter table
CREATE TABLE IF NOT EXISTS market_chatter (
    id SERIAL PRIMARY KEY,
    
    -- Core identification
    ticker TEXT NOT NULL,
    company_name TEXT,
    
    -- Source tracking
    source TEXT NOT NULL,              -- alpha_vantage / reddit / twitter / stocktwits / news
    source_type TEXT NOT NULL DEFAULT 'news',  -- news / social
    
    -- Content fields
    title TEXT,                         -- Article/post title (may be NULL for tweets)
    content TEXT NOT NULL,              -- Main content/description
    url TEXT,                           -- Original URL
    
    -- Sentiment analysis
    sentiment_score NUMERIC(4,3),       -- Range: -1.000 to +1.000
    sentiment_label TEXT,               -- positive / neutral / negative
    confidence NUMERIC(4,3),            -- Confidence: 0.000 to 1.000
    
    -- Timestamps
    published_at TIMESTAMP WITH TIME ZONE,
    ingested_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    -- Raw payload for debugging/reprocessing
    raw_payload JSONB,
    
    -- Prevent duplicate ingestion per (ticker, source, url)
    CONSTRAINT unique_chatter_per_source UNIQUE (ticker, source, url)
);

-- Performance indexes
CREATE INDEX IF NOT EXISTS idx_market_chatter_ticker ON market_chatter(ticker);
CREATE INDEX IF NOT EXISTS idx_market_chatter_source ON market_chatter(source);
CREATE INDEX IF NOT EXISTS idx_market_chatter_published_at ON market_chatter(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_market_chatter_ticker_published ON market_chatter(ticker, published_at DESC);
CREATE INDEX IF NOT EXISTS idx_market_chatter_source_type ON market_chatter(source_type);
CREATE INDEX IF NOT EXISTS idx_market_chatter_sentiment_label ON market_chatter(sentiment_label);
CREATE INDEX IF NOT EXISTS idx_market_chatter_ingested_at ON market_chatter(ingested_at DESC);

-- Table documentation
COMMENT ON TABLE market_chatter IS 'Canonical table for market chatter from multiple sources (news, social)';
COMMENT ON COLUMN market_chatter.source IS 'Source identifier: alpha_vantage, reddit, twitter, stocktwits, etc.';
COMMENT ON COLUMN market_chatter.source_type IS 'Source category: news or social';
COMMENT ON COLUMN market_chatter.sentiment_score IS 'Sentiment score ranging from -1.0 (negative) to +1.0 (positive)';
COMMENT ON COLUMN market_chatter.confidence IS 'Confidence score for sentiment analysis (0.0 to 1.0)';
COMMENT ON COLUMN market_chatter.ingested_at IS 'When this record was ingested into our system';
COMMENT ON COLUMN market_chatter.published_at IS 'When the original content was published';

