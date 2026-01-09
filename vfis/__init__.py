"""
Verified Financial Intelligence System (VFIS)

STRICT RULES:
- LLMs must NEVER generate financial numbers or metrics
- All financial data must come from PostgreSQL via tools
- Agents may only read data, reason, and summarize
- No trading logic, no buy/sell signals

NOTE: Environment variables are loaded by scripts.init_env (single source of truth).
All entrypoints must import scripts.init_env as their FIRST import line.
"""
from vfis.bootstrap import *  # noqa

__version__ = "1.0.0"

