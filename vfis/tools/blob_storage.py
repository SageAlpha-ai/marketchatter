"""
Azure Blob Storage integration for VFIS document assets.

STRICT RULES:
- Azure Blob Storage is used ONLY for raw files and extracted images
- No derived or processed data stored in Blob
- PostgreSQL remains the source of truth for structured data
- Returns immutable blob paths for reference
- Windows-compatible operations only
"""

import os
import logging
from pathlib import Path
from typing import Optional, BinaryIO
from datetime import datetime

try:
    from azure.storage.blob import BlobServiceClient, BlobClient, ContentSettings
    AZURE_AVAILABLE = True
except ImportError:
    AZURE_AVAILABLE = False
    logging.warning("Azure Blob Storage SDK not available. Install with: pip install azure-storage-blob")

logger = logging.getLogger(__name__)


class BlobStorageManager:
    """
    Manager for Azure Blob Storage operations.
    
    Responsibilities:
    - Upload raw PDFs
    - Upload extracted images
    - Return immutable blob paths
    - No data processing or parsing
    """
    
    def __init__(
        self,
        connection_string: Optional[str] = None,
        container_name: str = "vfis-documents"
    ):
        """
        Initialize Blob Storage Manager.
        
        Args:
            connection_string: Azure Storage connection string (from env if not provided)
            container_name: Container name for storing documents
        """
        self.connection_string = connection_string or os.getenv('AZURE_STORAGE_CONNECTION_STRING')
        self.container_name = container_name
        
        if not AZURE_AVAILABLE:
            raise ImportError("Azure Blob Storage SDK not installed. Install with: pip install azure-storage-blob")
        
        if not self.connection_string:
            raise ValueError("Azure Storage connection string not provided. Set AZURE_STORAGE_CONNECTION_STRING env var.")
        
        try:
            self.blob_service_client = BlobServiceClient.from_connection_string(self.connection_string)
            self._ensure_container_exists()
        except Exception as e:
            logger.error(f"Failed to initialize Blob Storage client: {e}")
            raise
    
    def _ensure_container_exists(self):
        """Ensure the container exists, create if it doesn't."""
        try:
            container_client = self.blob_service_client.get_container_client(self.container_name)
            if not container_client.exists():
                container_client.create_container()
                logger.info(f"Created container: {self.container_name}")
        except Exception as e:
            logger.error(f"Failed to ensure container exists: {e}")
            raise
    
    def upload_pdf(
        self,
        file_path: Path,
        ticker: str,
        document_type: str,
        period: str,
        source: str
    ) -> str:
        """
        Upload a raw PDF file to Azure Blob Storage.
        
        CRITICAL: This stores the raw PDF only. No parsing or processing.
        
        Args:
            file_path: Path to PDF file (Windows-compatible Path object)
            ticker: Company ticker symbol (dynamically provided)
            document_type: 'quarterly' or 'annual'
            period: Period identifier (e.g., 'Q2 FY26', 'FY2024')
            source: Data source ('NSE', 'BSE', or 'SEBI')
            
        Returns:
            Blob path (immutable reference to stored file)
        """
        # Validate inputs
        if document_type not in {'quarterly', 'annual'}:
            raise ValueError(f"Invalid document_type: {document_type}. Must be 'quarterly' or 'annual'")
        
        if source not in {'NSE', 'BSE', 'SEBI'}:
            raise ValueError(f"Invalid source: {source}. Must be 'NSE', 'BSE', or 'SEBI'")
        
        # Create blob path: ticker/document_type/period/source/filename
        file_name = file_path.name
        blob_path = f"{ticker.upper()}/{document_type}/{period}/{source}/{file_name}"
        
        try:
            # Upload file
            blob_client = self.blob_service_client.get_blob_client(
                container=self.container_name,
                blob=blob_path
            )
            
            # Read file and upload
            with open(file_path, 'rb') as file_data:
                content_settings = ContentSettings(content_type='application/pdf')
                blob_client.upload_blob(
                    file_data,
                    overwrite=True,
                    content_settings=content_settings
                )
            
            logger.info(f"Uploaded PDF to blob: {blob_path}")
            return blob_path
            
        except Exception as e:
            logger.error(f"Failed to upload PDF {file_path} to blob: {e}")
            raise
    
    def upload_image(
        self,
        file_path: Path,
        ticker: str,
        document_type: str,
        period: str,
        source: str,
        image_type: str = 'chart'
    ) -> str:
        """
        Upload an extracted image (chart, diagram, etc.) to Azure Blob Storage.
        
        CRITICAL: This stores the image only. Charts are NOT interpreted or analyzed.
        
        Args:
            file_path: Path to image file (Windows-compatible Path object)
            ticker: Company ticker symbol
            document_type: 'quarterly' or 'annual'
            period: Period identifier
            source: Data source ('NSE', 'BSE', or 'SEBI')
            image_type: Type of image ('chart', 'image', etc.)
            
        Returns:
            Blob path (immutable reference to stored image)
        """
        # Validate inputs
        if document_type not in {'quarterly', 'annual'}:
            raise ValueError(f"Invalid document_type: {document_type}")
        
        if source not in {'NSE', 'BSE', 'SEBI'}:
            raise ValueError(f"Invalid source: {source}")
        
        # Determine content type based on file extension
        ext = file_path.suffix.lower()
        content_type_map = {
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.pdf': 'application/pdf',  # PDFs can contain images
        }
        content_type = content_type_map.get(ext, 'application/octet-stream')
        
        # Create blob path: ticker/document_type/period/source/images/image_type/filename
        file_name = file_path.name
        blob_path = f"{ticker.upper()}/{document_type}/{period}/{source}/images/{image_type}/{file_name}"
        
        try:
            # Upload file
            blob_client = self.blob_service_client.get_blob_client(
                container=self.container_name,
                blob=blob_path
            )
            
            with open(file_path, 'rb') as file_data:
                content_settings = ContentSettings(content_type=content_type)
                blob_client.upload_blob(
                    file_data,
                    overwrite=True,
                    content_settings=content_settings
                )
            
            logger.info(f"Uploaded image to blob: {blob_path}")
            return blob_path
            
        except Exception as e:
            logger.error(f"Failed to upload image {file_path} to blob: {e}")
            raise
    
    def get_blob_url(self, blob_path: str) -> str:
        """
        Get a URL for accessing a blob (if public access is enabled).
        
        Args:
            blob_path: Blob path returned from upload methods
            
        Returns:
            URL to access the blob
        """
        blob_client = self.blob_service_client.get_blob_client(
            container=self.container_name,
            blob=blob_path
        )
        return blob_client.url


def create_blob_storage_manager(
    connection_string: Optional[str] = None,
    container_name: str = "vfis-documents"
) -> Optional[BlobStorageManager]:
    """
    Factory function to create a Blob Storage Manager.
    
    Returns None if Azure SDK is not available or connection string is missing.
    This allows the system to work without Blob Storage if not configured.
    """
    if not AZURE_AVAILABLE:
        logger.warning("Azure Blob Storage SDK not available. Blob storage disabled.")
        return None
    
    if not connection_string and not os.getenv('AZURE_STORAGE_CONNECTION_STRING'):
        logger.warning("Azure Storage connection string not provided. Blob storage disabled.")
        return None
    
    try:
        return BlobStorageManager(
            connection_string=connection_string,
            container_name=container_name
        )
    except Exception as e:
        logger.error(f"Failed to create Blob Storage Manager: {e}")
        return None

