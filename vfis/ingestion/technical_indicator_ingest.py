"""
Technical indicator ingestion pipeline for VFIS.

STRICT RULES:
- All computations use data already stored in PostgreSQL
- No live market APIs
- No LLM-based calculations
- Calculations must be reproducible
- No forecasting

NOTE: Environment variables are loaded by scripts.init_env (single source of truth).
All entrypoints must import scripts.init_env as their FIRST import line.
"""
import scripts.init_env  # Loads and validates environment variables

import logging
from datetime import date, timedelta
from typing import Dict, Any
from vfis.tools.technical_indicators import TechnicalIndicators, store_technical_indicators
from tradingagents.database.connection import init_database
from tradingagents.database.audit import log_data_access

logger = logging.getLogger(__name__)

# Initialize database connection pool on module import
# Environment variables are already loaded by scripts.init_env import above
# This is idempotent - safe to call multiple times
init_database(config={})  # Uses environment variables


class TechnicalIndicatorIngester:
    """
    Ingest computed technical indicators into PostgreSQL.
    
    CRITICAL: All indicators are deterministically computed from stored OHLC data.
    """
    
    def __init__(self, ticker: str):
        """
        Initialize technical indicator ingester.
        
        Args:
            ticker: Company ticker symbol
        """
        self.ticker = ticker.upper()
        self.indicator_computer = TechnicalIndicators(self.ticker)
    
    def ingest_indicators(
        self,
        start_date: date,
        end_date: date,
        source: str = 'computed'
    ) -> Dict[str, Any]:
        """
        Compute and store all technical indicators.
        
        Args:
            start_date: Start date for computation
            end_date: End date for computation
            source: Source identifier (default 'computed')
            
        Returns:
            Dictionary with ingestion results
        """
        results = {
            'success': False,
            'indicators_computed': 0,
            'records_inserted': 0,
            'errors': []
        }
        
        try:
            # Compute all indicators
            indicators_df = self.indicator_computer.compute_all_indicators(
                start_date=start_date,
                end_date=end_date
            )
            
            if indicators_df.empty:
                results['errors'].append(f"No OHLC data available for {self.ticker}")
                logger.warning(f"No indicators computed for {self.ticker}: No OHLC data")
                return results
            
            # Store each indicator
            indicator_names = [
                'sma_20', 'sma_50', 'sma_200',
                'ema_12', 'ema_26',
                'rsi',
                'macd', 'macd_signal', 'macd_histogram',
                'bb_upper', 'bb_middle', 'bb_lower',
                'stoch_k', 'stoch_d'
            ]
            
            total_records = 0
            for indicator_name in indicator_names:
                if indicator_name in indicators_df.columns:
                    try:
                        records = store_technical_indicators(
                            ticker=self.ticker,
                            indicator_name=indicator_name,
                            indicator_values=indicators_df[indicator_name],
                            source=source
                        )
                        total_records += records
                        results['indicators_computed'] += 1
                    except Exception as e:
                        error_msg = f"Failed to store {indicator_name}: {str(e)}"
                        logger.error(error_msg)
                        results['errors'].append(error_msg)
            
            results['records_inserted'] = total_records
            results['success'] = True
            
            # Log audit
            log_data_access(
                event_type='technical_indicator_computation',
                entity_type='technical_indicators',
                entity_id=None,
                details={
                    'ticker': self.ticker,
                    'start_date': start_date.isoformat(),
                    'end_date': end_date.isoformat(),
                    'indicators_computed': results['indicators_computed'],
                    'records_inserted': results['records_inserted'],
                    'source': source
                },
                user_id='technical_indicator_ingester'
            )
            
            logger.info(
                f"Computed and stored {results['indicators_computed']} indicators "
                f"for {self.ticker}: {results['records_inserted']} records"
            )
            
        except Exception as e:
            error_msg = f"Failed to ingest technical indicators for {self.ticker}: {str(e)}"
            logger.error(error_msg, exc_info=True)
            results['errors'].append(error_msg)
        
        return results


def ingest_technical_indicators(
    ticker: str,
    start_date: date,
    end_date: date,
    source: str = 'computed'
) -> Dict[str, Any]:
    """
    Convenience function to ingest technical indicators.
    
    Args:
        ticker: Company ticker symbol
        start_date: Start date for computation
        end_date: End date for computation
        source: Source identifier
        
    Returns:
        Dictionary with ingestion results
    """
    ingester = TechnicalIndicatorIngester(ticker=ticker)
    return ingester.ingest_indicators(
        start_date=start_date,
        end_date=end_date,
        source=source
    )


def main():
    """Main entry point for command-line usage."""
    import argparse
    import sys
    
    parser = argparse.ArgumentParser(
        description='Compute and ingest technical indicators into VFIS database',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m vfis.ingestion.technical_indicator_ingest --ticker <TICKER> --start-date 2024-01-01 --end-date 2024-12-31
  python -m vfis.ingestion.technical_indicator_ingest --ticker <TICKER> --days 30
        """
    )
    
    parser.add_argument(
        '--ticker',
        type=str,
        required=True,
        help='Company ticker symbol (dynamically provided)'
    )
    
    date_group = parser.add_mutually_exclusive_group(required=True)
    date_group.add_argument(
        '--start-date',
        type=str,
        help='Start date for computation (YYYY-MM-DD)'
    )
    date_group.add_argument(
        '--days',
        type=int,
        help='Number of days back from today for computation'
    )
    
    parser.add_argument(
        '--end-date',
        type=str,
        default=None,
        help='End date for computation (YYYY-MM-DD, default: today)'
    )
    
    parser.add_argument(
        '--source',
        type=str,
        default='computed',
        help='Source identifier (default: computed)'
    )
    
    parser.add_argument(
        '--log-level',
        type=str,
        default='INFO',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        help='Logging level (default: INFO)'
    )
    
    args = parser.parse_args()
    
    # Configure logging
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    try:
        # Parse dates
        if args.days:
            end_date = date.today()
            start_date = end_date - timedelta(days=args.days)
        else:
            start_date = date.fromisoformat(args.start_date)
            end_date = date.fromisoformat(args.end_date) if args.end_date else date.today()
        
        # Ingest technical indicators
        results = ingest_technical_indicators(
            ticker=args.ticker,
            start_date=start_date,
            end_date=end_date,
            source=args.source
        )
        
        # Print summary
        print(f"\n{'='*60}")
        print(f"Technical Indicator Ingestion Summary")
        print(f"{'='*60}")
        print(f"Ticker: {args.ticker}")
        print(f"Start date: {start_date.isoformat()}")
        print(f"End date: {end_date.isoformat()}")
        print(f"Indicators computed: {results['indicators_computed']}")
        print(f"Records inserted: {results['records_inserted']}")
        print(f"Success: {results['success']}")
        print(f"{'='*60}\n")
        
        if results['errors']:
            print("Errors:")
            for error in results['errors']:
                print(f"  - {error}")
            print()
        
        # Exit with error code if unsuccessful
        sys.exit(0 if results['success'] else 1)
    
    except ValueError as e:
        logger.error(f"Invalid date format: {e}")
        print(f"\nERROR: Invalid date format: {e}\n", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        print(f"\nERROR: {e}\n", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

