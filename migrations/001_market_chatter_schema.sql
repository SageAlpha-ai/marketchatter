-- ============================================================================
-- VFIS Market Chatter Schema Migration
-- Version: 001
-- Date: January 2026
-- ============================================================================

-- This migration ensures the market_chatter table has the correct canonical schema
-- with all required columns and constraints.

-- Create table if not exists
CREATE TABLE IF NOT EXISTS market_chatter (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(20) NOT NULL,
    source VARCHAR(50) NOT NULL,
    source_id VARCHAR(500) NOT NULL,
    title TEXT,
    summary TEXT,
    url TEXT,
    published_at TIMESTAMP WITH TIME ZONE,
    sentiment_score FLOAT,
    raw_payload JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Add unique constraint on (source, source_id) for idempotent inserts
-- This prevents duplicate entries when re-ingesting the same content
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes 
        WHERE tablename = 'market_chatter' 
        AND indexname = 'idx_market_chatter_source_source_id'
    ) THEN
        CREATE UNIQUE INDEX idx_market_chatter_source_source_id 
        ON market_chatter (source, source_id);
    END IF;
END $$;

-- Add index on ticker for efficient queries
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes 
        WHERE tablename = 'market_chatter' 
        AND indexname = 'idx_market_chatter_ticker'
    ) THEN
        CREATE INDEX idx_market_chatter_ticker ON market_chatter (ticker);
    END IF;
END $$;

-- Add index on published_at for time-based queries
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes 
        WHERE tablename = 'market_chatter' 
        AND indexname = 'idx_market_chatter_published_at'
    ) THEN
        CREATE INDEX idx_market_chatter_published_at ON market_chatter (published_at DESC);
    END IF;
END $$;

-- Add index on created_at for recent data queries
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes 
        WHERE tablename = 'market_chatter' 
        AND indexname = 'idx_market_chatter_created_at'
    ) THEN
        CREATE INDEX idx_market_chatter_created_at ON market_chatter (created_at DESC);
    END IF;
END $$;

-- Add composite index for common queries (ticker + published_at)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes 
        WHERE tablename = 'market_chatter' 
        AND indexname = 'idx_market_chatter_ticker_published'
    ) THEN
        CREATE INDEX idx_market_chatter_ticker_published 
        ON market_chatter (ticker, published_at DESC);
    END IF;
END $$;

-- Verify schema
-- Run this to confirm migration applied correctly:
-- SELECT column_name, data_type, is_nullable
-- FROM information_schema.columns
-- WHERE table_name = 'market_chatter'
-- ORDER BY ordinal_position;

-- Verify unique constraint:
-- SELECT indexdef FROM pg_indexes 
-- WHERE tablename = 'market_chatter' 
-- AND indexdef LIKE '%source%source_id%';

-- ============================================================================
-- CANONICAL SCHEMA REFERENCE
-- ============================================================================
-- Column         | Type                     | Constraint
-- ---------------+--------------------------+------------------------
-- id             | SERIAL                   | PRIMARY KEY
-- ticker         | VARCHAR(20)              | NOT NULL
-- source         | VARCHAR(50)              | NOT NULL
-- source_id      | VARCHAR(500)             | NOT NULL
-- title          | TEXT                     | 
-- summary        | TEXT                     | 
-- url            | TEXT                     | 
-- published_at   | TIMESTAMP WITH TIME ZONE |
-- sentiment_score| FLOAT                    |
-- raw_payload    | JSONB                    |
-- created_at     | TIMESTAMP WITH TIME ZONE | DEFAULT CURRENT_TIMESTAMP
--
-- UNIQUE INDEX: (source, source_id) - prevents duplicate ingestion
-- ============================================================================

