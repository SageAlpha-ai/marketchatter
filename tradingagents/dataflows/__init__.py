"""
Trading Agents Dataflows Module.

Provides data retrieval and ingestion from various sources.
"""

# Market chatter ingestion
from .chatter_interface import ChatterSource, ChatterItem, IngestionResult
from .alpha_vantage_chatter import AlphaVantageChatterSource, ingest_alpha_vantage_news
from .ingest_chatter import ingest_chatter, ingest_universe

__all__ = [
    # Chatter interface
    'ChatterSource',
    'ChatterItem',
    'IngestionResult',
    # Alpha Vantage chatter
    'AlphaVantageChatterSource',
    'ingest_alpha_vantage_news',
    # Ingestion functions
    'ingest_chatter',
    'ingest_universe',
]

