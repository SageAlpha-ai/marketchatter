"""
CLI entrypoint for market chatter ingestion.

DEPRECATED: Use vfis.ingestion module instead.

    from vfis.ingestion import ingest_ticker
    result = ingest_ticker("AAPL", days=7)

Or use the CLI:
    python -m tradingagents.dataflows.ingest_chatter --ticker AAPL

This file is kept for backward compatibility only.

NOTE: Ticker and company name are REQUIRED parameters - no hardcoded values.
"""
import warnings
warnings.warn(
    "vfis.market_chatter.ingest is deprecated. Use vfis.ingestion module instead.",
    DeprecationWarning,
    stacklevel=2
)

import argparse
import logging
import sys
from pathlib import Path

# Add parent directories to path
_project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(_project_root))

from vfis.market_chatter.aggregator import MarketChatterAggregator
from vfis.market_chatter.storage import MarketChatterStorage

logger = logging.getLogger(__name__)


def main():
    """Main CLI entrypoint."""
    parser = argparse.ArgumentParser(
        description="Ingest market chatter from various sources (news, Twitter, Reddit)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m vfis.market_chatter.ingest --ticker AAPL --company "Apple Inc."
  python -m vfis.market_chatter.ingest --ticker MSFT --company "Microsoft Corporation" --log-level DEBUG
        """
    )
    
    parser.add_argument(
        "--ticker",
        type=str,
        required=True,
        help="Stock ticker symbol (e.g., AAPL, MSFT, GOOGL)"
    )
    
    parser.add_argument(
        "--company",
        type=str,
        required=True,
        help="Company name (e.g., 'Apple Inc.')"
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
    
    try:
        # Aggregate chatter from all sources
        aggregator = MarketChatterAggregator()
        chatter_items = aggregator.aggregate(args.ticker, args.company)
        
        if not chatter_items:
            logger.warning(f"No market chatter found for {args.ticker}")
            sys.exit(0)
        
        # Store in database
        storage = MarketChatterStorage()
        counts = storage.store_chatter(args.ticker, args.company, chatter_items)
        
        # Print summary
        logger.info("=" * 60)
        logger.info("Market Chatter Ingestion Summary")
        logger.info("=" * 60)
        logger.info(f"Ticker: {args.ticker}")
        logger.info(f"Company: {args.company}")
        logger.info(f"Total items fetched: {len(chatter_items)}")
        logger.info(f"Inserted: {counts['inserted']}")
        logger.info(f"Skipped (duplicates): {counts['skipped']}")
        logger.info(f"Errors: {counts['errors']}")
        logger.info("=" * 60)
        
        # Exit with error code if there were errors
        sys.exit(1 if counts['errors'] > 0 else 0)
        
    except KeyboardInterrupt:
        logger.info("Ingestion interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error during ingestion: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()

