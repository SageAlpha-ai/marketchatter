"""
Environment Variable Initialization Module.

DEPRECATED: Use vfis.bootstrap.bootstrap() instead for full system initialization.

This module remains for backward compatibility. It loads and validates environment
variables but does NOT initialize the database or scheduler.

For full system initialization, use:
    from vfis.bootstrap import bootstrap
    bootstrap()

Usage (legacy):
    import scripts.init_env  # Loads and validates env vars only
"""

import os
import sys
import warnings
from pathlib import Path

# Issue deprecation warning
warnings.warn(
    "scripts.init_env is deprecated. Use vfis.bootstrap.bootstrap() for full initialization.",
    DeprecationWarning,
    stacklevel=2
)

# =============================================================================
# Environment Loading (kept for backward compatibility)
# =============================================================================

def _find_env_file() -> Path:
    """Find .env file by searching up the directory tree."""
    # Try multiple locations
    candidates = [
        Path(__file__).resolve().parents[1] / ".env",  # agent/.env
        Path(__file__).resolve().parents[2] / ".env",  # project root/.env
        Path.cwd() / ".env",  # current directory
    ]
    
    for candidate in candidates:
        if candidate.exists():
            return candidate
    
    raise RuntimeError(
        f".env file not found. Searched:\n" + 
        "\n".join(f"  - {c}" for c in candidates)
    )


def load_and_validate():
    """Load and validate environment variables."""
    from dotenv import load_dotenv
    
    env_path = _find_env_file()
    
    # Load with override=True for Windows + PowerShell compatibility
    load_dotenv(dotenv_path=env_path, override=True)
    
    # Required variables
    REQUIRED_VARS = [
        "POSTGRES_HOST",
        "POSTGRES_PORT",
        "POSTGRES_DB",
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
    ]
    
    # Check required vars
    missing = [v for v in REQUIRED_VARS if not os.getenv(v)]
    if missing:
        raise RuntimeError(f"Missing required env vars: {missing}")
    
    # Set defaults for optional variables
    if not os.getenv("AZURE_OPENAI_API_VERSION"):
        os.environ["AZURE_OPENAI_API_VERSION"] = "2024-02-15-preview"
    
    # Log success
    print(f"✓ Environment loaded from {env_path}")
    
    # Log Alpha Vantage status
    av_key = os.getenv("ALPHA_VANTAGE_API_KEY", "").strip()
    if av_key:
        masked = av_key[:4] + "****" + av_key[-4:] if len(av_key) > 8 else "****"
        print(f"✓ ALPHA_VANTAGE_API_KEY: Present ({masked})")
    else:
        print("⚠ ALPHA_VANTAGE_API_KEY: Not set (Alpha Vantage ingestion disabled)")
    
    return env_path


# Auto-load on import (for backward compatibility)
try:
    _env_path = load_and_validate()
except Exception as e:
    print(f"⚠ Environment loading failed: {e}")
    # Don't raise - let the new bootstrap handle failures properly
    _env_path = None


# Export for compatibility
PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = _env_path


def bootstrap():
    """
    Convenience wrapper around vfis.bootstrap.bootstrap().
    
    Use this if you were using scripts.init_env and want to upgrade
    to full system initialization.
    """
    from vfis.bootstrap import bootstrap as _bootstrap
    return _bootstrap()


__all__ = ['load_and_validate', 'bootstrap', 'PROJECT_ROOT', 'ENV_PATH']
