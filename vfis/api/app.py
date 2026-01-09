"""
FastAPI Production Application for Verified Financial Intelligence System (VFIS).

STRICT RULES:
- No direct DB access from API routes
- API calls VFIS system only
- Proper error handling
- Request/response logging
- Windows-compatible deployment

Implements Option A: Scheduled Background Ingestion
- Database initialized at startup via bootstrap()
- Background scheduler ingests market chatter every 5 minutes
- Chatter data available before any API reads

CRITICAL: Uses centralized bootstrap() for initialization.
All environment loading and validation happens in bootstrap().
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn

# Import env from canonical source (SINGLE SOURCE OF TRUTH)
from vfis.core.env import API_HOST, API_PORT, CORS_ORIGINS

from vfis.api.routes import router
from vfis.api.health import health_check, startup_validation

# Configure logging BEFORE any other operations
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for startup and shutdown events.
    
    Startup order (CRITICAL - handled by bootstrap()):
    1. Load .env file
    2. Validate required environment variables
    3. Initialize database connection pool
    4. Ensure required tables exist
    5. Start background ingestion scheduler
    6. Run startup validation
    
    CRITICAL: If bootstrap fails, the application MUST crash.
    Azure App Service requires startup failure to crash the process.
    NO degraded mode allowed.
    """
    logger.info("=" * 60)
    logger.info("Starting VFIS API application...")
    logger.info("=" * 60)
    
    # Use centralized bootstrap for initialization
    from vfis.bootstrap import bootstrap
    
    # CRITICAL: Bootstrap with fail_fast=True
    # If bootstrap fails, the exception propagates and crashes the app
    # This is REQUIRED for Azure App Service compatibility
    result = bootstrap(start_scheduler=True, fail_fast=True)
    
    # If we reach here, bootstrap succeeded
    logger.info("[STARTUP] Bootstrap successful")
    logger.info(f"[STARTUP] Database initialized: {result.db_initialized}")
    logger.info(f"[STARTUP] Tables created: {result.tables_created}")
    logger.info(f"[STARTUP] Scheduler started: {result.scheduler_started}")
    
    # Log warnings (non-fatal)
    for warning in result.warnings:
        logger.warning(f"[STARTUP] Warning: {warning}")
    
    # Run additional startup validation (non-fatal)
    try:
        validation_result = startup_validation()
        if validation_result.get('success', False):
            logger.info("[STARTUP] Startup validation passed")
        else:
            # Log validation issues but don't fail (bootstrap already succeeded)
            for error in validation_result.get('errors', []):
                logger.warning(f"[STARTUP] Validation issue: {error}")
    except Exception as e:
        logger.warning(f"[STARTUP] Startup validation skipped: {e}")
    
    logger.info("=" * 60)
    logger.info("[STARTUP] VFIS system initialized successfully")
    logger.info("[STARTUP] VFIS API ready to serve requests")
    logger.info("=" * 60)
    
    try:
        yield
    finally:
        # Shutdown cleanup
        logger.info("=" * 60)
        logger.info("Shutting down VFIS API application...")
        logger.info("=" * 60)
        
        # Stop scheduler gracefully
        try:
            from vfis.ingestion.scheduler import stop_scheduler
            stop_scheduler()
            logger.info("[SHUTDOWN] Scheduler stopped")
        except Exception as e:
            logger.warning(f"[SHUTDOWN] Error stopping scheduler: {e}")
        
        logger.info("Shutdown complete")


# Create FastAPI application
app = FastAPI(
    title="Verified Financial Intelligence System (VFIS) API",
    description="Production API for Verified Financial Intelligence System",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware (using canonical env source)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routes
app.include_router(router, prefix="/api/v1", tags=["vfis"])


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler for unhandled errors."""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "data": None,
            "status": "error",
            "message": str(exc),
            "path": str(request.url)
        }
    )


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint with API information."""
    from vfis.bootstrap import get_bootstrap_status
    
    bootstrap_status = get_bootstrap_status()
    
    return {
        "service": "Verified Financial Intelligence System (VFIS) API",
        "version": "1.0.0",
        "status": "operational" if bootstrap_status and bootstrap_status.success else "degraded",
        "bootstrap": bootstrap_status.to_dict() if bootstrap_status else None,
        "endpoints": {
            "query": "/api/v1/query",
            "health": "/api/v1/health",
            "scheduler_status": "/api/v1/scheduler/status",
            "scheduler_ingest": "/api/v1/scheduler/ingest"
        }
    }


# Health check endpoint (also accessible at root level for Azure)
@app.get("/health")
async def health():
    """Health check endpoint for Azure App Service."""
    return await health_check()


# Bootstrap status endpoint
@app.get("/bootstrap")
async def bootstrap_status():
    """Get bootstrap status for debugging."""
    from vfis.bootstrap import get_bootstrap_status, is_bootstrapped
    
    status = get_bootstrap_status()
    
    return {
        "data": {
            "bootstrapped": is_bootstrapped(),
            "status": status.to_dict() if status else None
        },
        "status": "success" if status and status.success else "error",
        "message": None if status and status.success else "Bootstrap incomplete or failed"
    }


if __name__ == "__main__":
    # Development server (using canonical env source)
    uvicorn.run(
        "vfis.api.app:app",
        host=API_HOST,
        port=API_PORT,
        reload=False,  # Disable reload in production
        log_level="info"
    )
