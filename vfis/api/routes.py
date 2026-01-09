"""
API Routes for Verified Financial Intelligence System (VFIS).

STRICT RULES:
- No direct DB access from routes
- API calls VFIS system only
- Proper error handling
- Request/response logging
- Ingestion runs BEFORE any query reads

ALL responses follow DAL contract:
{
    "data": Any,
    "status": "success" | "no_data" | "error",
    "message": Optional[str]
}
"""

import logging
from typing import Optional, Dict, Any, List
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from vfis.agents.final_output_assembly import FinalOutputAssembly
from vfis.tools.subscriber_matching import SubscriberRiskTolerance
from tradingagents.database.audit import log_data_access

logger = logging.getLogger(__name__)

# Create router
router = APIRouter()


# =============================================================================
# Request/Response models
# =============================================================================

class QueryRequest(BaseModel):
    """Request model for /query endpoint."""
    ticker: str = Field(
        ..., 
        description="Company ticker symbol - dynamically provided, not hardcoded", 
        min_length=1, 
        max_length=20
    )
    subscriber_risk_profile: str = Field(
        ..., 
        description="Subscriber risk profile: LOW, MODERATE, or HIGH"
    )
    query_intent: Optional[str] = Field(
        None, 
        description="Optional query intent or description"
    )
    
    @field_validator('ticker')
    @classmethod
    def ticker_uppercase(cls, v):
        """Convert ticker to uppercase."""
        return v.upper()
    
    @field_validator('subscriber_risk_profile')
    @classmethod
    def validate_risk_profile(cls, v):
        """Validate risk profile."""
        valid_profiles = ['LOW', 'MODERATE', 'HIGH', 'Low Risk', 'Moderate Risk', 'High Risk']
        if v not in valid_profiles:
            raise ValueError(f"subscriber_risk_profile must be one of: {', '.join(valid_profiles)}")
        return v
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "ticker": "TICKER_SYMBOL",
                "subscriber_risk_profile": "MODERATE",
                "query_intent": "Analyze company for moderate risk investor"
            }
        }
    }


class RiskAssessment(BaseModel):
    """Risk assessment model."""
    overall_risk: str
    low_risk_subscriber_view: Dict[str, Any]
    moderate_risk_subscriber_view: Dict[str, Any]
    high_risk_subscriber_view: Dict[str, Any]


class QueryResponseData(BaseModel):
    """Data portion of query response."""
    ticker: str
    analysis_date: str
    latest_financial_metrics: Dict[str, Any]
    market_chatter_summary: str
    sentiment_score: float
    sentiment_label: str
    bull_case: str
    bear_case: str
    risk_assessment: RiskAssessment
    processing_time_ms: Optional[float] = None
    ingestion_triggered: bool = False


class QueryResponse(BaseModel):
    """Response model for /query endpoint - follows DAL contract."""
    data: Optional[QueryResponseData]
    status: str  # "success" | "no_data" | "error"
    message: Optional[str]


class IngestionRequest(BaseModel):
    """Request model for manual ingestion."""
    tickers: Optional[List[str]] = Field(
        None, 
        description="List of ticker symbols to ingest. If null, uses active tickers from DB/env."
    )
    days: Optional[int] = Field(
        7, 
        description="Number of days to look back", 
        ge=1, 
        le=30
    )
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "tickers": ["TICKER1", "TICKER2"],
                "days": 7
            }
        }
    }


class IngestionResponse(BaseModel):
    """Response model for ingestion - follows DAL contract."""
    data: Optional[Dict[str, Any]]
    status: str  # "success" | "partial" | "no_data" | "error"
    message: Optional[str]


class SchedulerStatusResponse(BaseModel):
    """Response model for scheduler status - follows DAL contract."""
    data: Optional[Dict[str, Any]]
    status: str
    message: Optional[str]


# =============================================================================
# Routes
# =============================================================================

@router.post("/query", response_model=QueryResponse)
async def query_intelligence(
    request: QueryRequest,
    http_request: Request
) -> QueryResponse:
    """
    Main query endpoint for financial intelligence.
    
    CRITICAL: Ensures ingestion runs BEFORE query reads.
    
    Input:
    - ticker: Company ticker symbol (dynamically provided)
    - subscriber_risk_profile: Risk tolerance (LOW/MODERATE/HIGH)
    - query_intent: Optional query description
    
    Output:
    - DAL contract response with analysis data
    
    NOTE: If ticker hasn't been ingested yet, triggers ingestion synchronously.
    """
    start_time = datetime.now()
    ingestion_triggered = False
    
    try:
        # Convert risk profile to SubscriberRiskTolerance enum
        risk_profile_map = {
            'LOW': SubscriberRiskTolerance.LOW_RISK,
            'Low Risk': SubscriberRiskTolerance.LOW_RISK,
            'MODERATE': SubscriberRiskTolerance.MODERATE_RISK,
            'Moderate Risk': SubscriberRiskTolerance.MODERATE_RISK,
            'HIGH': SubscriberRiskTolerance.HIGH_RISK,
            'High Risk': SubscriberRiskTolerance.HIGH_RISK
        }
        
        subscriber_risk = risk_profile_map.get(
            request.subscriber_risk_profile,
            SubscriberRiskTolerance.MODERATE_RISK  # Default
        )
        
        # Log request
        logger.info(
            f"Query request received: ticker={request.ticker}, "
            f"risk_profile={request.subscriber_risk_profile}, "
            f"intent={request.query_intent}"
        )
        
        # CRITICAL: Ensure ingestion BEFORE query reads
        # Use centralized ingestion module
        from vfis.ingestion import ensure_ticker_ingested
        
        ingest_result = ensure_ticker_ingested(request.ticker, days=7)
        
        if ingest_result["status"] == "success" and not ingest_result["data"].get("already_ingested"):
            ingestion_triggered = True
            logger.info(
                f"On-demand ingestion for {request.ticker}: "
                f"fetched={ingest_result['data'].get('fetched', 0)}, "
                f"inserted={ingest_result['data'].get('inserted', 0)}"
            )
        elif ingest_result["status"] == "error":
            # Log warning but continue - don't fail the request
            logger.warning(f"Ingestion warning for {request.ticker}: {ingest_result['message']}")
        
        # Assemble final output using VFIS system
        assembly = FinalOutputAssembly()
        output = assembly.assemble_final_output(
            ticker=request.ticker,
            subscriber_risk_tolerance=subscriber_risk,
            user_query=request.query_intent or f"Query for {request.ticker}"
        )
        
        # Calculate processing time
        processing_time = (datetime.now() - start_time).total_seconds() * 1000
        
        # Log response
        logger.info(
            f"Query completed: ticker={request.ticker}, "
            f"processing_time_ms={processing_time:.2f}, "
            f"success={not output.get('error')}"
        )
        
        # Log audit
        log_data_access(
            event_type='api_query',
            entity_type='ticker_analysis',
            entity_id=None,
            details={
                'ticker': request.ticker,
                'subscriber_risk_profile': request.subscriber_risk_profile,
                'query_intent': request.query_intent,
                'processing_time_ms': processing_time,
                'success': not output.get('error'),
                'ingestion_triggered': ingestion_triggered
            },
            user_id=getattr(http_request.state, 'user_id', 'FastAPI')
        )
        
        # Build response from output
        if output.get('error'):
            return QueryResponse(
                data=None,
                status="error",
                message=f"Analysis failed: {output.get('error')}"
            )
        
        # Extract risk assessment
        risk_assessment_data = output.get('risk_assessment', {})
        
        # Build response data
        response_data = QueryResponseData(
            ticker=output.get('ticker', request.ticker),
            analysis_date=output.get('analysis_date', datetime.now().date().isoformat()),
            latest_financial_metrics=output.get('latest_financial_metrics', {
                'available': False,
                'reason': 'Data retrieval failed',
                'details': 'Unable to retrieve financial metrics',
                'suggestions': ['Check system logs', 'Verify ticker symbol']
            }),
            market_chatter_summary=output.get('market_chatter_summary', 'No market chatter available'),
            sentiment_score=output.get('sentiment_score', 0.0),
            sentiment_label=output.get('sentiment_label', 'neutral'),
            bull_case=output.get('bull_case', ''),
            bear_case=output.get('bear_case', ''),
            risk_assessment=RiskAssessment(
                overall_risk=risk_assessment_data.get('overall_risk', 'UNKNOWN'),
                low_risk_subscriber_view=risk_assessment_data.get('low_risk_subscriber_view', {}),
                moderate_risk_subscriber_view=risk_assessment_data.get('moderate_risk_subscriber_view', {}),
                high_risk_subscriber_view=risk_assessment_data.get('high_risk_subscriber_view', {})
            ),
            processing_time_ms=processing_time,
            ingestion_triggered=ingestion_triggered
        )
        
        return QueryResponse(
            data=response_data,
            status="success",
            message=f"Analysis complete for {request.ticker}"
        )
    
    except ValueError as e:
        # Validation error
        logger.warning(f"Validation error in query: {e}")
        return QueryResponse(
            data=None,
            status="error",
            message=str(e)
        )
    
    except Exception as e:
        # Unexpected error
        logger.error(f"Error processing query: {e}", exc_info=True)
        
        # Log audit for error
        log_data_access(
            event_type='api_query_error',
            entity_type='ticker_analysis',
            entity_id=None,
            details={
                'ticker': request.ticker,
                'error': str(e)
            },
            user_id='FastAPI'
        )
        
        return QueryResponse(
            data=None,
            status="error",
            message=f"Internal server error: {str(e)}"
        )


@router.get("/health")
async def health():
    """Health check endpoint."""
    from vfis.api.health import health_check
    return await health_check()


@router.get("/scheduler/status", response_model=SchedulerStatusResponse)
async def scheduler_status() -> SchedulerStatusResponse:
    """
    Get background ingestion scheduler status.
    
    Returns:
        DAL contract response with scheduler status
    """
    try:
        from vfis.ingestion.scheduler import get_scheduler_status
        
        status = get_scheduler_status()
        
        return SchedulerStatusResponse(
            data=status,
            status="success",
            message="Scheduler status retrieved"
        )
    except Exception as e:
        logger.error(f"Error getting scheduler status: {e}")
        return SchedulerStatusResponse(
            data=None,
            status="error",
            message=str(e)
        )


@router.post("/scheduler/ingest", response_model=IngestionResponse)
async def trigger_ingestion(request: IngestionRequest) -> IngestionResponse:
    """
    Manually trigger market chatter ingestion.
    
    USES CENTRALIZED INGESTION MODULE - no duplicate logic.
    
    Args:
        request: IngestionRequest with optional tickers list and days
    
    Returns:
        DAL contract response with ingestion results
    """
    try:
        from vfis.ingestion import ingest_tickers, get_active_tickers
        
        tickers = request.tickers
        days = request.days or 7
        
        logger.info(f"Manual ingestion triggered: tickers={tickers}, days={days}")
        
        if tickers:
            # Use provided tickers (normalize to uppercase)
            tickers = [t.upper() for t in tickers]
            result = ingest_tickers(tickers, days=days)
        else:
            # Get active tickers from DB/env
            active_result = get_active_tickers()
            
            if active_result["status"] == "no_data":
                return IngestionResponse(
                    data={"tickers": [], "total_inserted": 0},
                    status="no_data",
                    message=active_result["message"]
                )
            
            tickers = active_result["data"]["tickers"]
            result = ingest_tickers(tickers, days=days)
        
        return IngestionResponse(
            data=result["data"],
            status=result["status"],
            message=result["message"]
        )
        
    except Exception as e:
        logger.error(f"Error running manual ingestion: {e}", exc_info=True)
        return IngestionResponse(
            data=None,
            status="error",
            message=str(e)
        )


@router.get("/tickers/active", response_model=IngestionResponse)
async def list_active_tickers() -> IngestionResponse:
    """
    List active tickers configured for ingestion.
    
    Returns tickers from ACTIVE_TICKERS env var or database.
    NO hardcoded defaults.
    
    Returns:
        DAL contract response with list of active tickers
    """
    try:
        from vfis.ingestion import get_active_tickers
        
        result = get_active_tickers()
        
        return IngestionResponse(
            data=result["data"],
            status=result["status"],
            message=result["message"]
        )
        
    except Exception as e:
        logger.error(f"Error listing active tickers: {e}")
        return IngestionResponse(
            data=None,
            status="error",
            message=str(e)
        )


# =============================================================================
# DEBUG ENDPOINTS (for validation and troubleshooting)
# =============================================================================

class DebugResponse(BaseModel):
    """Response model for debug endpoints - follows DAL contract."""
    data: Optional[Dict[str, Any]]
    status: str
    message: Optional[str]


@router.get("/debug/env", response_model=DebugResponse)
async def debug_env() -> DebugResponse:
    """
    Debug endpoint to verify environment configuration.
    
    Shows:
    - Which env file was loaded
    - Database configuration (passwords masked)
    - LLM availability
    - Alpha Vantage availability
    - Ingestion configuration
    
    Returns:
        DAL contract response with environment status
    """
    try:
        from vfis.core.env import get_env_status, validate_env
        
        env_status = get_env_status()
        is_valid, errors, warnings = validate_env()
        
        env_status["validation"] = {
            "is_valid": is_valid,
            "errors": errors,
            "warnings": warnings
        }
        
        return DebugResponse(
            data=env_status,
            status="success" if is_valid else "error",
            message=f"Environment {'valid' if is_valid else 'has errors'}: {len(errors)} errors, {len(warnings)} warnings"
        )
        
    except Exception as e:
        logger.error(f"Error in debug/env: {e}", exc_info=True)
        return DebugResponse(
            data=None,
            status="error",
            message=str(e)
        )


@router.get("/debug/ingestion", response_model=DebugResponse)
async def debug_ingestion() -> DebugResponse:
    """
    Debug endpoint to verify ingestion pipeline status.
    
    Shows:
    - Scheduler status (running, last run, counts)
    - Active tickers source
    - Recent ingestion results
    - Database chatter counts
    
    Returns:
        DAL contract response with ingestion status
    """
    try:
        from vfis.ingestion.scheduler import get_scheduler_status
        from vfis.ingestion import get_active_tickers
        from tradingagents.database.connection import get_db_connection
        
        # Get scheduler status
        scheduler_status = get_scheduler_status()
        
        # Get active tickers
        tickers_result = get_active_tickers()
        
        # Get database counts
        db_counts = {}
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    # Total chatter count
                    cur.execute("SELECT COUNT(*) FROM market_chatter")
                    db_counts["total_chatter_rows"] = cur.fetchone()[0]
                    
                    # Count by ticker
                    cur.execute("""
                        SELECT ticker, COUNT(*) as count 
                        FROM market_chatter 
                        GROUP BY ticker 
                        ORDER BY count DESC 
                        LIMIT 10
                    """)
                    db_counts["chatter_by_ticker"] = {
                        row[0]: row[1] for row in cur.fetchall()
                    }
                    
                    # Count by source
                    cur.execute("""
                        SELECT source, COUNT(*) as count 
                        FROM market_chatter 
                        GROUP BY source
                    """)
                    db_counts["chatter_by_source"] = {
                        row[0]: row[1] for row in cur.fetchall()
                    }
                    
                    # Recent insertions
                    cur.execute("""
                        SELECT ticker, source, published_at, created_at 
                        FROM market_chatter 
                        ORDER BY created_at DESC 
                        LIMIT 5
                    """)
                    db_counts["recent_insertions"] = [
                        {
                            "ticker": row[0],
                            "source": row[1],
                            "published_at": row[2].isoformat() if row[2] else None,
                            "created_at": row[3].isoformat() if row[3] else None
                        }
                        for row in cur.fetchall()
                    ]
        except Exception as db_error:
            db_counts["error"] = str(db_error)
        
        ingestion_status = {
            "scheduler": scheduler_status,
            "active_tickers": tickers_result.get("data", {}),
            "database": db_counts
        }
        
        return DebugResponse(
            data=ingestion_status,
            status="success",
            message=f"Scheduler running: {scheduler_status.get('running', False)}, Total chatter: {db_counts.get('total_chatter_rows', 0)}"
        )
        
    except Exception as e:
        logger.error(f"Error in debug/ingestion: {e}", exc_info=True)
        return DebugResponse(
            data=None,
            status="error",
            message=str(e)
        )


@router.get("/debug/agents", response_model=DebugResponse)
async def debug_agents() -> DebugResponse:
    """
    Debug endpoint to verify agent availability.
    
    Shows:
    - Agent classes available
    - LLM configuration status
    - Any initialization errors
    
    Returns:
        DAL contract response with agent status
    """
    try:
        agent_status = {
            "agents": {},
            "llm_available": False
        }
        
        # Check LLM availability
        try:
            from vfis.core.env import LLM_AVAILABLE
            agent_status["llm_available"] = LLM_AVAILABLE
        except Exception as e:
            agent_status["llm_error"] = str(e)
        
        # Check each agent
        agents_to_check = [
            ("BullAgent", "vfis.agents.bull_agent", "BullAgent"),
            ("BearAgent", "vfis.agents.bear_agent", "BearAgent"),
            ("RiskManagementAgent", "vfis.agents.risk_management_agent", "RiskManagementAgent"),
            ("FinalOutputAssembly", "vfis.agents.final_output_assembly", "FinalOutputAssembly"),
            ("DebateOrchestrator", "vfis.agents.debate_orchestrator", "DebateOrchestrator"),
        ]
        
        for name, module_path, class_name in agents_to_check:
            try:
                module = __import__(module_path, fromlist=[class_name])
                agent_class = getattr(module, class_name)
                agent_status["agents"][name] = {
                    "available": True,
                    "module": module_path
                }
            except Exception as e:
                agent_status["agents"][name] = {
                    "available": False,
                    "error": str(e)
                }
        
        all_available = all(a.get("available", False) for a in agent_status["agents"].values())
        
        return DebugResponse(
            data=agent_status,
            status="success" if all_available else "error",
            message=f"Agents: {sum(1 for a in agent_status['agents'].values() if a.get('available'))}/{len(agent_status['agents'])} available"
        )
        
    except Exception as e:
        logger.error(f"Error in debug/agents: {e}", exc_info=True)
        return DebugResponse(
            data=None,
            status="error",
            message=str(e)
        )
