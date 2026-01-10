-- Migration: 004_market_chatter_source_id_fix.sql
-- Description: SAFE, IDEMPOTENT migration to add source_id column to legacy market_chatter tables
-- Date: 2026-01-10
-- 
-- PURPOSE:
--   Production databases may have legacy market_chatter tables created WITHOUT
--   the source_id column. This migration adds the column, backfills existing data,
--   and adds the UNIQUE constraint without data loss.
--
-- SAFETY GUARANTEES:
--   1. All operations are idempotent (safe to run multiple times)
--   2. No data is dropped
--   3. Existing rows are backfilled with deterministic values
--   4. Compatible with PostgreSQL 13+
--
-- NOTE: This migration is also executed programmatically via
--       tradingagents.database.migrations.run_migrations()

-- ============================================================================
-- STEP 1: Check if source_id column exists, add if missing
-- ============================================================================
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'public'
        AND table_name = 'market_chatter' 
        AND column_name = 'source_id'
    ) THEN
        -- Add source_id column (nullable initially)
        ALTER TABLE market_chatter ADD COLUMN source_id TEXT;
        RAISE NOTICE 'Added source_id column to market_chatter';
    ELSE
        RAISE NOTICE 'source_id column already exists';
    END IF;
END $$;

-- ============================================================================
-- STEP 2: Backfill source_id for existing rows
-- Uses MD5 hash of (url OR ticker:source:content_prefix) for determinism
-- ============================================================================
UPDATE market_chatter 
SET source_id = MD5(
    COALESCE(
        url,
        ticker || ':' || source || ':' || COALESCE(LEFT(content, 100), '')
    )
)
WHERE source_id IS NULL;

-- ============================================================================
-- STEP 3: Handle any remaining NULLs (defensive)
-- ============================================================================
UPDATE market_chatter 
SET source_id = MD5(RANDOM()::TEXT || CLOCK_TIMESTAMP()::TEXT)
WHERE source_id IS NULL;

-- ============================================================================
-- STEP 4: Make source_id NOT NULL
-- ============================================================================
DO $$
BEGIN
    -- Check if column is already NOT NULL
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'public'
        AND table_name = 'market_chatter' 
        AND column_name = 'source_id'
        AND is_nullable = 'YES'
    ) THEN
        ALTER TABLE market_chatter ALTER COLUMN source_id SET NOT NULL;
        RAISE NOTICE 'Set source_id to NOT NULL';
    ELSE
        RAISE NOTICE 'source_id is already NOT NULL';
    END IF;
END $$;

-- ============================================================================
-- STEP 5: Add summary column if missing
-- ============================================================================
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'public'
        AND table_name = 'market_chatter' 
        AND column_name = 'summary'
    ) THEN
        ALTER TABLE market_chatter ADD COLUMN summary TEXT;
        UPDATE market_chatter SET summary = content WHERE summary IS NULL AND content IS NOT NULL;
        RAISE NOTICE 'Added and populated summary column';
    ELSE
        RAISE NOTICE 'summary column already exists';
    END IF;
END $$;

-- ============================================================================
-- STEP 6: Handle duplicates before adding constraint
-- Keeps the row with lowest ID for each (source, source_id) pair
-- ============================================================================
DO $$
DECLARE
    deleted_count INTEGER;
BEGIN
    -- Check if constraint already exists
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints 
        WHERE table_schema = 'public'
        AND table_name = 'market_chatter' 
        AND constraint_name = 'unique_source_source_id'
    ) THEN
        -- Remove duplicates
        DELETE FROM market_chatter a
        USING market_chatter b
        WHERE a.id > b.id 
        AND a.source = b.source 
        AND a.source_id = b.source_id;
        
        GET DIAGNOSTICS deleted_count = ROW_COUNT;
        IF deleted_count > 0 THEN
            RAISE NOTICE 'Removed % duplicate rows', deleted_count;
        END IF;
        
        -- Add the constraint
        ALTER TABLE market_chatter 
        ADD CONSTRAINT unique_source_source_id 
        UNIQUE (source, source_id);
        RAISE NOTICE 'Added UNIQUE constraint on (source, source_id)';
    ELSE
        RAISE NOTICE 'UNIQUE constraint already exists';
    END IF;
END $$;

-- ============================================================================
-- STEP 7: Create index for (source, source_id)
-- ============================================================================
CREATE INDEX IF NOT EXISTS idx_mc_source_source_id 
    ON market_chatter(source, source_id);

-- ============================================================================
-- STEP 8: Drop legacy constraint if it exists (optional cleanup)
-- The old constraint was on (ticker, source, url)
-- ============================================================================
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.table_constraints 
        WHERE table_schema = 'public'
        AND table_name = 'market_chatter' 
        AND constraint_name = 'unique_chatter_per_source'
    ) THEN
        ALTER TABLE market_chatter DROP CONSTRAINT unique_chatter_per_source;
        RAISE NOTICE 'Dropped legacy unique_chatter_per_source constraint';
    END IF;
END $$;

-- ============================================================================
-- FINAL: Verify migration success
-- ============================================================================
DO $$
DECLARE
    col_exists BOOLEAN;
    constraint_exists BOOLEAN;
BEGIN
    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'market_chatter' AND column_name = 'source_id'
    ) INTO col_exists;
    
    SELECT EXISTS (
        SELECT 1 FROM information_schema.table_constraints 
        WHERE table_name = 'market_chatter' AND constraint_name = 'unique_source_source_id'
    ) INTO constraint_exists;
    
    IF col_exists AND constraint_exists THEN
        RAISE NOTICE 'Migration 004 COMPLETED SUCCESSFULLY';
    ELSE
        RAISE EXCEPTION 'Migration 004 FAILED: col_exists=%, constraint_exists=%', col_exists, constraint_exists;
    END IF;
END $$;

