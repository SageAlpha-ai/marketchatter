-- Migration: 003_market_chatter_v2.sql
-- Description: Redesign market_chatter table with proper deduplication keys
-- Date: 2026-01-08
-- 
-- Changes:
--   1. Add source_id column for proper deduplication
--   2. Replace UNIQUE (ticker, source, url) with UNIQUE (source, source_id)
--   3. Add summary column (replaces content for clarity)
--   4. Add proper indexes

-- Step 1: Drop old constraint if exists (safe migration)
ALTER TABLE market_chatter 
    DROP CONSTRAINT IF EXISTS unique_chatter_per_source;

-- Step 2: Add source_id column if not exists
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'market_chatter' AND column_name = 'source_id'
    ) THEN
        ALTER TABLE market_chatter ADD COLUMN source_id TEXT;
    END IF;
END $$;

-- Step 3: Populate source_id for existing rows (from URL hash or content hash)
UPDATE market_chatter 
SET source_id = encode(sha256(
    COALESCE(url, ticker || ':' || source || ':' || LEFT(content, 100))::bytea
), 'hex')::text
WHERE source_id IS NULL;

-- Step 4: Make source_id NOT NULL after population
ALTER TABLE market_chatter ALTER COLUMN source_id SET NOT NULL;

-- Step 5: Add new unique constraint on (source, source_id)
ALTER TABLE market_chatter 
    ADD CONSTRAINT unique_source_source_id UNIQUE (source, source_id);

-- Step 6: Add summary column if not exists (same as content, but clearer name)
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'market_chatter' AND column_name = 'summary'
    ) THEN
        -- Add summary column
        ALTER TABLE market_chatter ADD COLUMN summary TEXT;
        
        -- Copy content to summary
        UPDATE market_chatter SET summary = content WHERE summary IS NULL;
    END IF;
END $$;

-- Step 7: Create indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_market_chatter_source_source_id 
    ON market_chatter(source, source_id);

CREATE INDEX IF NOT EXISTS idx_market_chatter_ticker_published_desc 
    ON market_chatter(ticker, published_at DESC);

CREATE INDEX IF NOT EXISTS idx_market_chatter_ticker_source 
    ON market_chatter(ticker, source);

-- Step 8: Add comment for documentation
COMMENT ON TABLE market_chatter IS 'Market chatter from multiple sources (news, social) with deduplication via (source, source_id)';
COMMENT ON COLUMN market_chatter.source_id IS 'Unique identifier within source (URL hash, post ID, etc.)';
COMMENT ON COLUMN market_chatter.summary IS 'Content summary/body text';

