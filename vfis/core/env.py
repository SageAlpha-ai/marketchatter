"""
VFIS Environment Configuration - SINGLE SOURCE OF TRUTH.

This module is the ONLY place where environment variables are loaded.
All other modules MUST import from here instead of using os.getenv().

Usage:
    from vfis.core.env import (
        POSTGRES_HOST,
        POSTGRES_PORT,
        POSTGRES_DB,
        AZURE_OPENAI_API_KEY,
        ALPHA_VANTAGE_API_KEY,
        ...
    )

CRITICAL:
- This module loads .env ONCE at import time
- All env vars are validated at import time
- Missing required vars cause immediate failure
"""

import os
import sys
import logging
from pathlib import Path
from typing import Optional, List

logger = logging.getLogger(__name__)

# =============================================================================
# LOAD .ENV FILE (ONCE)
# =============================================================================

def _find_env_file() -> Optional[Path]:
    """Find .env file by searching up the directory tree."""
    candidates = [
        Path(__file__).resolve().parents[2] / ".env",  # vfis/../.env (agent/.env)
        Path(__file__).resolve().parents[3] / ".env",  # vfis/../../.env
        Path.cwd() / ".env",
    ]
    
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _load_env():
    """Load environment variables from .env file."""
    from dotenv import load_dotenv
    
    env_path = _find_env_file()
    if env_path:
        load_dotenv(dotenv_path=env_path, override=True)
        logger.info(f"[ENV] Loaded environment from {env_path}")
        return env_path
    else:
        logger.warning("[ENV] No .env file found, using system environment only")
        return None


# Load .env at import time
_ENV_FILE_PATH = _load_env()

# =============================================================================
# REQUIRED ENVIRONMENT VARIABLES (FAIL FAST IF MISSING)
# =============================================================================

def _get_required(name: str) -> str:
    """Get required environment variable or fail fast."""
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(
            f"[ENV] FATAL: Required environment variable '{name}' is not set.\n"
            f"Add it to your .env file or system environment."
        )
    return value


def _get_optional(name: str, default: str = "") -> str:
    """Get optional environment variable with default."""
    return os.getenv(name, default).strip()


# -----------------------------------------------------------------------------
# DATABASE (REQUIRED)
# -----------------------------------------------------------------------------
POSTGRES_HOST: str = _get_required("POSTGRES_HOST")
POSTGRES_PORT: int = int(_get_optional("POSTGRES_PORT", "5432"))
POSTGRES_DB: str = _get_required("POSTGRES_DB")
POSTGRES_USER: str = _get_required("POSTGRES_USER")
POSTGRES_PASSWORD: str = _get_required("POSTGRES_PASSWORD")

# Computed connection string
DATABASE_URL: str = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"

# -----------------------------------------------------------------------------
# AZURE OPENAI (REQUIRED FOR LLM FEATURES)
# -----------------------------------------------------------------------------
AZURE_OPENAI_API_KEY: str = _get_optional("AZURE_OPENAI_API_KEY", "")
AZURE_OPENAI_ENDPOINT: str = _get_optional("AZURE_OPENAI_ENDPOINT", "")
AZURE_OPENAI_DEPLOYMENT_NAME: str = _get_optional("AZURE_OPENAI_DEPLOYMENT_NAME", "")
AZURE_OPENAI_API_VERSION: str = _get_optional("AZURE_OPENAI_API_VERSION", "2024-02-15-preview")

# Flag to indicate if LLM features are available
LLM_AVAILABLE: bool = bool(AZURE_OPENAI_API_KEY and AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_DEPLOYMENT_NAME)

if not LLM_AVAILABLE:
    logger.warning("[ENV] Azure OpenAI credentials not fully configured - LLM features disabled")

# -----------------------------------------------------------------------------
# ALPHA VANTAGE (OPTIONAL - FOR NEWS INGESTION)
# -----------------------------------------------------------------------------
ALPHA_VANTAGE_API_KEY: str = _get_optional("ALPHA_VANTAGE_API_KEY", "")
ALPHA_VANTAGE_AVAILABLE: bool = bool(ALPHA_VANTAGE_API_KEY)

if ALPHA_VANTAGE_AVAILABLE:
    _masked = ALPHA_VANTAGE_API_KEY[:4] + "****" + ALPHA_VANTAGE_API_KEY[-4:] if len(ALPHA_VANTAGE_API_KEY) > 8 else "****"
    logger.info(f"[ENV] Alpha Vantage API key present ({_masked})")
else:
    logger.warning("[ENV] ALPHA_VANTAGE_API_KEY not set - Alpha Vantage ingestion disabled")

# -----------------------------------------------------------------------------
# INGESTION CONFIGURATION
# -----------------------------------------------------------------------------
ACTIVE_TICKERS: List[str] = [
    t.strip().upper() 
    for t in _get_optional("ACTIVE_TICKERS", "").split(",") 
    if t.strip()
]
INGESTION_INTERVAL_SECONDS: int = int(_get_optional("INGESTION_INTERVAL_SECONDS", "300"))
INGESTION_LOOKBACK_DAYS: int = int(_get_optional("INGESTION_LOOKBACK_DAYS", "7"))

# -----------------------------------------------------------------------------
# API CONFIGURATION
# -----------------------------------------------------------------------------
API_HOST: str = _get_optional("HOST", "0.0.0.0")
API_PORT: int = int(_get_optional("PORT", "8000"))
CORS_ORIGINS: List[str] = [o.strip() for o in _get_optional("CORS_ORIGINS", "*").split(",")]

# -----------------------------------------------------------------------------
# DEBUG / DEVELOPMENT
# -----------------------------------------------------------------------------
DEBUG: bool = _get_optional("DEBUG", "false").lower() in ("true", "1", "yes")
LOG_LEVEL: str = _get_optional("LOG_LEVEL", "INFO").upper()

# =============================================================================
# VALIDATION FUNCTION (FOR DEBUG ENDPOINTS)
# =============================================================================

def get_env_status() -> dict:
    """
    Get current environment status for debugging.
    
    Returns:
        Dictionary with environment status (sensitive values masked)
    """
    return {
        "env_file_loaded": _ENV_FILE_PATH is not None,
        "env_file_path": str(_ENV_FILE_PATH) if _ENV_FILE_PATH else None,
        "database": {
            "host": POSTGRES_HOST,
            "port": POSTGRES_PORT,
            "database": POSTGRES_DB,
            "user": POSTGRES_USER,
            "password_set": bool(POSTGRES_PASSWORD),
        },
        "azure_openai": {
            "available": LLM_AVAILABLE,
            "endpoint": AZURE_OPENAI_ENDPOINT[:30] + "..." if AZURE_OPENAI_ENDPOINT else None,
            "deployment": AZURE_OPENAI_DEPLOYMENT_NAME,
            "api_version": AZURE_OPENAI_API_VERSION,
        },
        "alpha_vantage": {
            "available": ALPHA_VANTAGE_AVAILABLE,
        },
        "ingestion": {
            "active_tickers": ACTIVE_TICKERS,
            "interval_seconds": INGESTION_INTERVAL_SECONDS,
            "lookback_days": INGESTION_LOOKBACK_DAYS,
        },
        "api": {
            "host": API_HOST,
            "port": API_PORT,
            "cors_origins": CORS_ORIGINS,
        },
        "debug": DEBUG,
        "log_level": LOG_LEVEL,
    }


def validate_env() -> tuple:
    """
    Validate environment configuration (ENV VARS ONLY - NO DB CONNECTION).
    
    CRITICAL: This function validates environment variables ONLY.
    Database connectivity is tested SEPARATELY after init_database() is called.
    DO NOT add database connection tests here.
    
    Returns:
        Tuple of (is_valid, errors, warnings)
    """
    errors = []
    warnings = []
    
    # Validate required DB vars are set (but do NOT connect)
    if not POSTGRES_HOST:
        errors.append("POSTGRES_HOST not set")
    if not POSTGRES_DB:
        errors.append("POSTGRES_DB not set")
    if not POSTGRES_USER:
        errors.append("POSTGRES_USER not set")
    if not POSTGRES_PASSWORD:
        errors.append("POSTGRES_PASSWORD not set")
    
    # LLM validation
    if not LLM_AVAILABLE:
        warnings.append("Azure OpenAI not configured - LLM features disabled")
    
    # Alpha Vantage validation
    if not ALPHA_VANTAGE_AVAILABLE:
        warnings.append("Alpha Vantage API key not set - news ingestion limited to RSS")
    
    # Active tickers validation
    if not ACTIVE_TICKERS:
        warnings.append("ACTIVE_TICKERS not set - scheduler will use database tickers only")
    
    is_valid = len(errors) == 0
    return is_valid, errors, warnings


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    # Database
    "POSTGRES_HOST",
    "POSTGRES_PORT", 
    "POSTGRES_DB",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "DATABASE_URL",
    
    # Azure OpenAI
    "AZURE_OPENAI_API_KEY",
    "AZURE_OPENAI_ENDPOINT",
    "AZURE_OPENAI_DEPLOYMENT_NAME",
    "AZURE_OPENAI_API_VERSION",
    "LLM_AVAILABLE",
    
    # Alpha Vantage
    "ALPHA_VANTAGE_API_KEY",
    "ALPHA_VANTAGE_AVAILABLE",
    
    # Ingestion
    "ACTIVE_TICKERS",
    "INGESTION_INTERVAL_SECONDS",
    "INGESTION_LOOKBACK_DAYS",
    
    # API
    "API_HOST",
    "API_PORT",
    "CORS_ORIGINS",
    
    # Debug
    "DEBUG",
    "LOG_LEVEL",
    
    # Functions
    "get_env_status",
    "validate_env",
]

# Log successful initialization
logger.info(f"[ENV] Environment initialized: DB={POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}, LLM={LLM_AVAILABLE}, AV={ALPHA_VANTAGE_AVAILABLE}")

