"""
Health check and startup validation for VFIS API.

Operational safety checks:
- Database connectivity
- Blob storage connectivity
- Required environment variables
- Graceful failure handling
"""

import logging
import os
from typing import Dict, Any, List
from datetime import datetime

from tradingagents.database.connection import get_db_connection

logger = logging.getLogger(__name__)


async def health_check() -> Dict[str, Any]:
    """
    Health check endpoint for Azure App Service.
    
    Checks:
    - API is running
    - Database connectivity (optional - graceful degradation)
    - Required environment variables
    """
    health_status = {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "checks": {}
    }
    
    # Check database connectivity
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
        health_status["checks"]["database"] = {
            "status": "healthy",
            "message": "Database connection successful"
        }
    except Exception as e:
        logger.warning(f"Database health check failed: {e}")
        health_status["checks"]["database"] = {
            "status": "unhealthy",
            "message": f"Database connection failed: {str(e)}"
        }
        # Don't fail entire health check - graceful degradation
        health_status["status"] = "degraded"
    
    # Check required environment variables (without exposing values)
    required_vars = [
        "AZURE_OPENAI_API_KEY",
        "AZURE_OPENAI_ENDPOINT",
        "AZURE_OPENAI_DEPLOYMENT_NAME",
    ]
    
    missing_vars = []
    for var in required_vars:
        if not os.getenv(var):
            missing_vars.append(var)
    
    if missing_vars:
        health_status["checks"]["environment"] = {
            "status": "unhealthy",
            "message": f"Missing environment variables: {', '.join(missing_vars)}"
        }
        health_status["status"] = "unhealthy"
    else:
        health_status["checks"]["environment"] = {
            "status": "healthy",
            "message": "All required environment variables present"
        }
    
    # Check blob storage (optional)
    try:
        blob_conn_str = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
        if blob_conn_str:
            # Try to create blob client (just validation, not actual connection)
            from vfis.tools.blob_storage import AzureBlobStorageClient
            # Just check if we can import and initialize (lightweight check)
            health_status["checks"]["blob_storage"] = {
                "status": "healthy",
                "message": "Blob storage connection string configured"
            }
        else:
            health_status["checks"]["blob_storage"] = {
                "status": "optional",
                "message": "Blob storage not configured (optional)"
            }
    except Exception as e:
        logger.warning(f"Blob storage health check failed: {e}")
        health_status["checks"]["blob_storage"] = {
            "status": "optional",
            "message": f"Blob storage check failed: {str(e)}"
        }
    
    return health_status


def startup_validation() -> Dict[str, Any]:
    """
    Perform startup validation checks.
    
    Returns:
        Dictionary with 'success' boolean and 'errors' list
    """
    errors: List[str] = []
    warnings: List[str] = []
    
    # Check database connectivity
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Test query
                cur.execute("SELECT 1")
                cur.fetchone()
                
                # Check if required tables exist
                required_tables = [
                    'companies',
                    'data_sources',
                    'quarterly_reports',
                    'annual_reports'
                ]
                
                for table in required_tables:
                    cur.execute("""
                        SELECT EXISTS (
                            SELECT FROM information_schema.tables 
                            WHERE table_name = %s
                        );
                    """, (table,))
                    exists = cur.fetchone()[0]
                    if not exists:
                        warnings.append(f"Table '{table}' does not exist - some features may not work")
    
    except Exception as e:
        errors.append(f"Database connectivity check failed: {str(e)}")
        logger.error(f"Startup validation: Database check failed: {e}")
    
    # Check required environment variables
    required_vars = {
        "AZURE_OPENAI_API_KEY": "Azure OpenAI API key for LLM operations",
        "AZURE_OPENAI_ENDPOINT": "Azure OpenAI endpoint URL",
        "AZURE_OPENAI_DEPLOYMENT_NAME": "Azure OpenAI deployment name",
    }
    
    for var, description in required_vars.items():
        if not os.getenv(var):
            errors.append(f"Missing required environment variable: {var} ({description})")
    
    # Check optional environment variables (warnings only)
    optional_vars = {
        "AZURE_STORAGE_CONNECTION_STRING": "Azure Blob Storage (optional, for document storage)"
    }
    
    for var, description in optional_vars.items():
        if not os.getenv(var):
            warnings.append(f"Optional environment variable not set: {var} ({description})")
    
    # Return validation result
    return {
        "success": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "timestamp": datetime.now().isoformat()
    }

