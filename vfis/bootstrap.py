"""
VFIS Bootstrap Module - Single Canonical Entrypoint.

This module provides the SINGLE function for initializing the VFIS system:
- Loads and validates environment variables via vfis.core.env
- Initializes database connection pool
- Ensures required tables exist (migrations)
- Starts the background ingestion scheduler

CRITICAL: All entrypoints MUST call bootstrap() before any other operations.

Usage:
    from vfis.bootstrap import bootstrap
    bootstrap()  # Call once at startup
    
    # Now the system is ready for use
"""

import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Track bootstrap state to prevent double initialization
_bootstrap_completed = False
_bootstrap_result: Optional['BootstrapResult'] = None


@dataclass
class BootstrapResult:
    """Result of bootstrap operation."""
    success: bool
    env_loaded: bool
    db_initialized: bool
    tables_created: bool
    scheduler_started: bool
    errors: List[str]
    warnings: List[str]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'success': self.success,
            'env_loaded': self.env_loaded,
            'db_initialized': self.db_initialized,
            'tables_created': self.tables_created,
            'scheduler_started': self.scheduler_started,
            'errors': self.errors,
            'warnings': self.warnings
        }


# Environment variable lists for reference (actual validation in core.env)
REQUIRED_ENV_VARS = [
    "POSTGRES_HOST",
    "POSTGRES_PORT",
    "POSTGRES_DB",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
]

REQUIRED_FOR_LLM = [
    "AZURE_OPENAI_API_KEY",
    "AZURE_OPENAI_ENDPOINT",
    "AZURE_OPENAI_DEPLOYMENT_NAME",
]

OPTIONAL_ENV_VARS = [
    "ALPHA_VANTAGE_API_KEY",
    "ACTIVE_TICKERS",
    "INGESTION_INTERVAL_SECONDS",
    "INGESTION_LOOKBACK_DAYS",
]


def _load_and_validate_env() -> tuple[bool, bool, List[str], List[str]]:
    """
    Load and validate environment variables via vfis.core.env.
    
    The core.env module is the SINGLE SOURCE OF TRUTH for environment loading.
    Importing it triggers:
    1. .env file loading (once)
    2. Required variable validation (fail-fast)
    3. Optional variable defaults
    
    CRITICAL: This does NOT test database connectivity.
    Database connection is tested AFTER init_database() in step 2.
    
    Returns:
        Tuple of (env_loaded, env_valid, errors, warnings)
    """
    errors = []
    warnings = []
    
    logger.info("[BOOTSTRAP] Step 1: Loading and validating environment variables...")
    
    try:
        # Import core.env - this loads and validates at import time
        from vfis.core.env import (
            get_env_status,
            validate_env,
            LLM_AVAILABLE,
            ALPHA_VANTAGE_AVAILABLE,
            ACTIVE_TICKERS,
            POSTGRES_HOST,
            POSTGRES_DB,
        )
        
        env_status = get_env_status()
        logger.info(f"[BOOTSTRAP] Environment loaded from {env_status.get('env_file_path', 'system environment')}")
        logger.info(f"[BOOTSTRAP] Database target: {POSTGRES_HOST}/{POSTGRES_DB}")
        
        # Log key status
        if not LLM_AVAILABLE:
            warnings.append("LLM features disabled (Azure OpenAI not configured)")
        if not ALPHA_VANTAGE_AVAILABLE:
            warnings.append("Alpha Vantage disabled (API key not set)")
        if ACTIVE_TICKERS:
            logger.info(f"[BOOTSTRAP] ACTIVE_TICKERS: {ACTIVE_TICKERS}")
        
        # Run env validation (does NOT test DB connectivity)
        is_valid, val_errors, val_warnings = validate_env()
        errors.extend(val_errors)
        warnings.extend(val_warnings)
        
        if is_valid:
            logger.info("[BOOTSTRAP] Environment variables validated successfully")
        else:
            logger.error(f"[BOOTSTRAP] Environment validation failed: {val_errors}")
        
        return True, is_valid, errors, warnings
        
    except RuntimeError as e:
        # core.env raises RuntimeError for missing required vars
        logger.critical(f"[BOOTSTRAP] FATAL: {e}")
        errors.append(str(e))
        return False, False, errors, warnings
    except Exception as e:
        logger.critical(f"[BOOTSTRAP] FATAL: Environment loading failed: {e}")
        errors.append(f"Environment loading failed: {e}")
        return False, False, errors, warnings


def _init_database() -> tuple[bool, List[str]]:
    """
    Initialize database connection pool.
    
    CRITICAL: This MUST be called BEFORE any database operations.
    The connection pool is a singleton - safe to call multiple times.
    
    Returns:
        Tuple of (success, errors)
    """
    errors = []
    
    try:
        from tradingagents.database.connection import init_database, get_db_connection
        
        logger.info("[BOOTSTRAP] Step 2: Initializing database connection pool...")
        init_database(config={})
        logger.info("[BOOTSTRAP] Database connection pool initialized")
        
        # Verify connectivity with a test query
        logger.info("[BOOTSTRAP] Testing database connectivity...")
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                result = cur.fetchone()
                if result and result[0] == 1:
                    logger.info("[BOOTSTRAP] Database connectivity verified")
                else:
                    raise RuntimeError("Database test query returned unexpected result")
        
        return True, errors
        
    except Exception as e:
        errors.append(f"Database initialization failed: {e}")
        logger.critical(f"[BOOTSTRAP] FATAL: Database initialization failed: {e}")
        return False, errors


def _ensure_tables() -> tuple[bool, List[str]]:
    """
    Ensure required database tables exist.
    
    CRITICAL: Must be called AFTER _init_database().
    
    Returns:
        Tuple of (success, errors)
    """
    errors = []
    
    try:
        from tradingagents.database.chatter_persist import ensure_market_chatter_table
        
        logger.info("[BOOTSTRAP] Step 3: Ensuring database tables exist...")
        if ensure_market_chatter_table():
            logger.info("[BOOTSTRAP] market_chatter table ready")
        else:
            errors.append("Failed to create/verify market_chatter table")
            logger.error("[BOOTSTRAP] Failed to create/verify market_chatter table")
        
        return len(errors) == 0, errors
        
    except Exception as e:
        errors.append(f"Table creation failed: {e}")
        logger.critical(f"[BOOTSTRAP] FATAL: Table creation failed: {e}")
        return False, errors


def _start_scheduler() -> tuple[bool, List[str]]:
    """
    Start the background ingestion scheduler.
    
    CRITICAL: Must be called AFTER _ensure_tables().
    
    Returns:
        Tuple of (success, errors)
    """
    errors = []
    
    try:
        from vfis.ingestion.scheduler import start_scheduler, get_scheduler_status
        
        logger.info("[BOOTSTRAP] Step 4: Starting background ingestion scheduler...")
        start_scheduler()
        
        status = get_scheduler_status()
        if status.get('running'):
            logger.info(f"[BOOTSTRAP] Scheduler started successfully (running={status.get('running')})")
        else:
            errors.append("Scheduler failed to start")
            logger.error("[BOOTSTRAP] Scheduler failed to start")
        
        return status.get('running', False), errors
        
    except Exception as e:
        errors.append(f"Scheduler startup failed: {e}")
        logger.error(f"[BOOTSTRAP] Scheduler startup failed: {e}")
        return False, errors


def bootstrap(
    start_scheduler: bool = True,
    fail_fast: bool = True
) -> BootstrapResult:
    """
    Bootstrap the VFIS system.
    
    This is the SINGLE canonical entrypoint for system initialization.
    Call this ONCE at application startup before any other operations.
    
    Initialization order (CRITICAL):
    1. Load .env file
    2. Validate required environment variables
    3. Initialize database connection pool
    4. Ensure required tables exist (migrations)
    5. Start background ingestion scheduler (optional)
    
    Args:
        start_scheduler: Whether to start the background scheduler (default: True)
        fail_fast: Whether to raise exceptions on errors (default: True)
    
    Returns:
        BootstrapResult with success status and any errors/warnings
    
    Raises:
        RuntimeError: If fail_fast=True and bootstrap fails
    
    Usage:
        from vfis.bootstrap import bootstrap
        
        # Basic usage (fail on errors)
        bootstrap()
        
        # Don't start scheduler (e.g., for testing)
        bootstrap(start_scheduler=False)
        
        # Continue on errors (for debugging)
        result = bootstrap(fail_fast=False)
        if not result.success:
            print(f"Bootstrap errors: {result.errors}")
    """
    global _bootstrap_completed, _bootstrap_result
    
    # Return cached result if already bootstrapped
    if _bootstrap_completed and _bootstrap_result:
        logger.debug("[BOOTSTRAP] Already completed, returning cached result")
        return _bootstrap_result
    
    logger.info("=" * 60)
    logger.info("[BOOTSTRAP] Starting VFIS system initialization...")
    logger.info("[BOOTSTRAP] Initialization order: ENV -> DB POOL -> TABLES -> SCHEDULER")
    logger.info("=" * 60)
    
    all_errors: List[str] = []
    all_warnings: List[str] = []
    
    # =========================================================================
    # STEP 1: Load and validate environment (NO DB CONNECTION YET)
    # =========================================================================
    env_loaded, env_valid, env_errors, env_warnings = _load_and_validate_env()
    all_errors.extend(env_errors)
    all_warnings.extend(env_warnings)
    
    if not env_loaded:
        error_msg = f"FATAL: Failed to load environment: {env_errors}"
        logger.critical(f"[BOOTSTRAP] {error_msg}")
        if fail_fast:
            raise RuntimeError(error_msg)
    
    if not env_valid:
        error_msg = f"FATAL: Environment validation failed: {env_errors}"
        logger.critical(f"[BOOTSTRAP] {error_msg}")
        if fail_fast:
            raise RuntimeError(error_msg)
    
    # =========================================================================
    # STEP 2: Initialize database connection pool (BEFORE any DB operations)
    # =========================================================================
    db_initialized = False
    if env_valid:
        db_initialized, db_errors = _init_database()
        all_errors.extend(db_errors)
        
        if not db_initialized:
            error_msg = f"FATAL: Database initialization failed: {db_errors}"
            logger.critical(f"[BOOTSTRAP] {error_msg}")
            if fail_fast:
                raise RuntimeError(error_msg)
    
    # =========================================================================
    # STEP 3: Ensure tables exist (REQUIRES DB POOL)
    # =========================================================================
    tables_created = False
    if db_initialized:
        tables_created, table_errors = _ensure_tables()
        all_errors.extend(table_errors)
        
        if not tables_created:
            error_msg = f"FATAL: Table creation failed: {table_errors}"
            logger.critical(f"[BOOTSTRAP] {error_msg}")
            if fail_fast:
                raise RuntimeError(error_msg)
    
    # =========================================================================
    # STEP 4: Start scheduler (REQUIRES TABLES)
    # =========================================================================
    scheduler_started = False
    if start_scheduler and tables_created:
        scheduler_started, scheduler_errors = _start_scheduler()
        all_errors.extend(scheduler_errors)
        # Scheduler failure is non-fatal (system can work without background ingestion)
        if not scheduler_started:
            logger.warning(f"[BOOTSTRAP] Scheduler failed to start (non-fatal): {scheduler_errors}")
    elif not start_scheduler:
        logger.info("[BOOTSTRAP] Scheduler disabled by configuration")
    
    # =========================================================================
    # FINAL: Build result and log status
    # =========================================================================
    success = env_loaded and env_valid and db_initialized and tables_created
    
    _bootstrap_result = BootstrapResult(
        success=success,
        env_loaded=env_loaded,
        db_initialized=db_initialized,
        tables_created=tables_created,
        scheduler_started=scheduler_started,
        errors=all_errors,
        warnings=all_warnings
    )
    
    _bootstrap_completed = True
    
    # Log final status
    logger.info("=" * 60)
    if success:
        logger.info("[BOOTSTRAP] VFIS system initialized successfully")
        logger.info(f"[BOOTSTRAP] DB Pool: ✓ | Tables: ✓ | Scheduler: {'✓' if scheduler_started else '✗'}")
    else:
        logger.critical(f"[BOOTSTRAP] VFIS system initialization FAILED")
        logger.critical(f"[BOOTSTRAP] Errors: {all_errors}")
    logger.info("=" * 60)
    
    return _bootstrap_result


def get_bootstrap_status() -> Optional[BootstrapResult]:
    """Get the current bootstrap status, or None if not bootstrapped."""
    return _bootstrap_result


def is_bootstrapped() -> bool:
    """Check if the system has been bootstrapped."""
    return _bootstrap_completed


def reset_bootstrap():
    """
    Reset bootstrap state (for testing only).
    
    WARNING: Only use in test environments.
    """
    global _bootstrap_completed, _bootstrap_result
    _bootstrap_completed = False
    _bootstrap_result = None


# Module-level convenience - allow importing bootstrap functions directly
__all__ = [
    'bootstrap',
    'get_bootstrap_status',
    'is_bootstrapped',
    'reset_bootstrap',
    'BootstrapResult',
    'REQUIRED_ENV_VARS',
    'REQUIRED_FOR_LLM',
    'OPTIONAL_ENV_VARS',
]
