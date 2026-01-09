import os
from pathlib import Path

# Windows-compatible path handling
_project_dir = Path(__file__).parent.parent
_data_cache_dir = _project_dir / "dataflows" / "data_cache"
_results_dir = Path(os.getenv("TRADINGAGENTS_RESULTS_DIR", "./results"))

DEFAULT_CONFIG = {
    "project_dir": str(_project_dir.resolve()),
    "results_dir": str(_results_dir.resolve()),
    "data_cache_dir": str(_data_cache_dir.resolve()),
    # LLM settings
    "llm_provider": "openai",
    "deep_think_llm": "o4-mini",
    "quick_think_llm": "gpt-4o",
    "backend_url": "https://api.openai.com/v1",
    # Debate and discussion settings
    "max_debate_rounds": 1,
    "max_risk_discuss_rounds": 1,
    "max_recur_limit": 100,
    # Database configuration (PostgreSQL)
    # Standardized to POSTGRES_* environment variables (with DB_* fallback for backward compatibility)
    "db_host": os.getenv("POSTGRES_HOST") or os.getenv("DB_HOST", "localhost"),
    "db_port": int(os.getenv("POSTGRES_PORT") or os.getenv("DB_PORT", "5432")),
    "db_name": os.getenv("POSTGRES_DB") or os.getenv("DB_NAME", "vfis_db"),
    "db_user": os.getenv("POSTGRES_USER") or os.getenv("DB_USER", "postgres"),
    "db_password": os.getenv("POSTGRES_PASSWORD") or os.getenv("DB_PASSWORD", ""),
    # Data staleness threshold (in days)
    "data_staleness_threshold_days": 90,
}
