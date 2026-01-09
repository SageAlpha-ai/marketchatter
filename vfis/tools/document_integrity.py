"""
Document integrity utilities for VFIS.

STRICT RULES:
- Compute SHA-256 hash for every PDF file before ingestion
- Hash must be computed from raw file bytes
- Reject ingestion if same hash exists for same ticker and document_type
- Log hash mismatches or duplicate detection explicitly
- Use Python hashlib only (no third-party libraries)
"""

import hashlib
import logging
from pathlib import Path
from typing import Optional, Tuple
from tradingagents.database.connection import get_db_connection

logger = logging.getLogger(__name__)


def compute_file_hash(file_path: Path) -> str:
    """
    Compute SHA-256 hash of a file.
    
    CRITICAL: Hash is computed from raw file bytes.
    This ensures document integrity and prevents duplicate ingestion.
    
    Args:
        file_path: Path to file (Windows-compatible Path object)
        
    Returns:
        SHA-256 hash as hexadecimal string
    """
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    
    sha256_hash = hashlib.sha256()
    
    # Read file in chunks to handle large files efficiently
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b""):
            sha256_hash.update(chunk)
    
    hash_value = sha256_hash.hexdigest()
    logger.debug(f"Computed SHA-256 hash for {file_path.name}: {hash_value[:16]}...")
    
    return hash_value


def check_duplicate_document(
    ticker: str,
    document_type: str,
    file_hash: str
) -> Tuple[bool, Optional[int]]:
    """
    Check if a document with the same hash already exists for the ticker and document_type.
    
    This prevents duplicate ingestion of the same document.
    
    Args:
        ticker: Company ticker symbol
        document_type: 'quarterly' or 'annual'
        file_hash: SHA-256 hash of the file
        
    Returns:
        Tuple of (is_duplicate: bool, existing_asset_id: int or None)
    """
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, file_name, period, created_at
                FROM document_assets
                WHERE ticker = %s 
                AND document_type = %s 
                AND file_hash = %s
            """, (ticker.upper(), document_type, file_hash))
            
            result = cur.fetchone()
            
            if result:
                asset_id, file_name, period, created_at = result
                logger.warning(
                    f"Duplicate document detected: ticker={ticker}, "
                    f"type={document_type}, hash={file_hash[:16]}... "
                    f"(existing asset_id={asset_id}, file={file_name}, period={period})"
                )
                return True, asset_id
            else:
                return False, None


def record_document_hash(
    asset_id: int,
    file_hash: str
) -> bool:
    """
    Update an existing document_asset record with file_hash.
    
    Args:
        asset_id: Document asset ID
        file_hash: SHA-256 hash of the file
        
    Returns:
        True if successful, False otherwise
    """
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE document_assets
                    SET file_hash = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                """, (file_hash, asset_id))
                
                conn.commit()
                logger.debug(f"Updated document_asset {asset_id} with hash: {file_hash[:16]}...")
                return True
    except Exception as e:
        logger.error(f"Failed to record document hash for asset {asset_id}: {e}")
        return False

