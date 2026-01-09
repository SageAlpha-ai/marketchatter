"""Audit logging for all system operations."""
import logging
import json
from datetime import datetime
from typing import Optional, Dict, Any
from uuid import uuid4
from .connection import get_db_connection

logger = logging.getLogger(__name__)

# Thread-local storage for request ID (if needed)
_request_context = {'request_id': None}


def set_request_id(request_id: Optional[str] = None):
    """Set the current request ID for audit logging."""
    _request_context['request_id'] = request_id or str(uuid4())


def get_request_id() -> Optional[str]:
    """Get the current request ID."""
    return _request_context.get('request_id')


def log_data_access(
    event_type: str,
    entity_type: str,
    entity_id: Optional[int],
    details: Dict[str, Any],
    user_id: Optional[str] = None,
    ip_address: Optional[str] = None,
    agent_name: Optional[str] = None
):
    """
    Log a data access event to the audit log.
    
    Args:
        event_type: Type of event being logged
        entity_type: Type of entity being accessed
        entity_id: ID of the entity (optional)
        details: Dictionary with additional details
        user_id: User ID performing the action (optional)
        ip_address: IP address of the requester (optional)
        agent_name: Agent name performing the action (optional, used as user_id if user_id not provided)
    """
    # Use agent_name as user_id if user_id is not provided (backward compatibility)
    effective_user_id = user_id if user_id is not None else agent_name
    
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO audit_log 
                    (event_type, entity_type, entity_id, action, user_id, request_id, details, ip_address)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    event_type,
                    entity_type,
                    entity_id,
                    'data_access',
                    effective_user_id,
                    get_request_id(),
                    json.dumps(details),
                    ip_address
                ))
                conn.commit()
                logger.debug(f"Audit log entry created: {event_type}/{entity_type}/{entity_id}")
    except Exception as e:
        logger.error(f"Failed to write audit log: {e}", exc_info=True)


def log_llm_interaction(
    agent_name: str,
    interaction_type: str,
    input_data: Dict[str, Any],
    output_data: Dict[str, Any],
    user_id: Optional[str] = None
):
    """Log an LLM interaction for audit purposes."""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                details = {
                    'agent': agent_name,
                    'interaction_type': interaction_type,
                    'input': input_data,
                    'output': output_data,
                    'timestamp': datetime.utcnow().isoformat()
                }
                
                cur.execute("""
                    INSERT INTO audit_log 
                    (event_type, entity_type, entity_id, action, user_id, request_id, details)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (
                    'llm_interaction',
                    'agent',
                    None,
                    interaction_type,
                    user_id,
                    get_request_id(),
                    json.dumps(details)
                ))
                conn.commit()
                logger.debug(f"LLM interaction logged: {agent_name}/{interaction_type}")
    except Exception as e:
        logger.error(f"Failed to log LLM interaction: {e}", exc_info=True)


def log_error(
    error_type: str,
    error_message: str,
    error_details: Optional[Dict[str, Any]] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None
):
    """Log an error event."""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                details = {
                    'error_type': error_type,
                    'error_message': error_message,
                    'error_details': error_details or {},
                    'timestamp': datetime.utcnow().isoformat()
                }
                
                cur.execute("""
                    INSERT INTO audit_log 
                    (event_type, entity_type, entity_id, action, request_id, details)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (
                    'error',
                    entity_type,
                    entity_id,
                    error_type,
                    get_request_id(),
                    json.dumps(details)
                ))
                conn.commit()
                logger.error(f"Error logged: {error_type} - {error_message}")
    except Exception as e:
        logger.error(f"Failed to log error: {e}", exc_info=True)

