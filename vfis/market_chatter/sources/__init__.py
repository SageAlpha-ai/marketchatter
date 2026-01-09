"""
Market chatter source implementations.

DEPRECATED: These sources are legacy implementations used by the deprecated
vfis.market_chatter.aggregator module.

The canonical ingestion pipeline is:
    vfis/ingestion/__init__.py -> vfis/ingestion/scheduler.py ->
    tradingagents/dataflows/ingest_chatter.py -> tradingagents/database/chatter_persist.py

These files are kept for backward compatibility only.
"""
import warnings
warnings.warn(
    "vfis.market_chatter.sources is deprecated. Use vfis.ingestion module instead.",
    DeprecationWarning,
    stacklevel=2
)

from vfis.market_chatter.sources.base import MarketChatterSource
from vfis.market_chatter.sources.news import NewsSource
from vfis.market_chatter.sources.twitter import TwitterSource
from vfis.market_chatter.sources.reddit import RedditSource

__all__ = [
    'MarketChatterSource',
    'NewsSource',
    'TwitterSource',
    'RedditSource',
]

