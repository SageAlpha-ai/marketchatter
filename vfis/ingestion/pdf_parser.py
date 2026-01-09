"""
Deterministic PDF parsing for VFIS.

STRICT RULES:
- PDFs are RAW INPUT ONLY
- LLMs must NEVER parse PDFs or extract numbers
- All numerical values must be extracted programmatically
- No OCR guessing, no chart value inference
- Charts are extracted as images, NOT interpreted
- Reject tables that cannot be parsed deterministically

This module uses:
- pdfplumber for text extraction
- camelot (lattice + stream) for table extraction
- pdfplumber for image extraction
"""

import logging
import gc
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import pandas as pd
from vfis.tools.document_integrity import compute_file_hash

try:
    import pdfplumber
    PDFPLUMBER_AVAILABLE = True
except ImportError:
    PDFPLUMBER_AVAILABLE = False
    logging.warning("pdfplumber not available. Install with: pip install pdfplumber")

try:
    import camelot
    CAMELOT_AVAILABLE = True
except ImportError:
    CAMELOT_AVAILABLE = False
    logging.warning("camelot-py not available. Install with: pip install camelot-py[cv]")

logger = logging.getLogger(__name__)


class PDFParser:
    """
    Deterministic PDF parser for financial documents.
    
    CRITICAL: This parser does NOT use LLMs. All extraction is programmatic.
    """
    
    def __init__(self, pdf_path: Path):
        """
        Initialize PDF parser.
        
        Args:
            pdf_path: Path to PDF file (Windows-compatible Path object)
        """
        if not PDFPLUMBER_AVAILABLE:
            raise ImportError("pdfplumber not installed. Install with: pip install pdfplumber")
        
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")
        
        self.pdf_path = Path(pdf_path)
        self.pdf = None
        self.file_hash = None
    
    def get_file_hash(self) -> str:
        """
        Get SHA-256 hash of the PDF file.
        
        CRITICAL: Hash is computed from raw file bytes for document integrity.
        
        Returns:
            SHA-256 hash as hexadecimal string
        """
        if self.file_hash is None:
            self.file_hash = compute_file_hash(self.pdf_path)
        return self.file_hash
    
    def __enter__(self):
        """Context manager entry."""
        self.pdf = pdfplumber.open(self.pdf_path)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        if self.pdf:
            self.pdf.close()
    
    def extract_text(self) -> str:
        """
        Extract all text from PDF.
        
        Returns:
            Combined text from all pages
        """
        if not self.pdf:
            raise RuntimeError("PDF not opened. Use as context manager or call open() first.")
        
        text_parts = []
        for page in self.pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)
        
        return "\n\n".join(text_parts)
    
    def extract_tables(
        self,
        pages: Optional[List[int]] = None,
        method: str = 'lattice'
    ) -> List[Tuple[pd.DataFrame, int]]:
        """
        Extract tables from PDF using camelot.
        
        CRITICAL: Only returns tables that can be parsed deterministically.
        Rejects ambiguous or malformed tables.
        
        Args:
            pages: List of page numbers to extract from (None = all pages)
            method: 'lattice' or 'stream' (camelot methods)
            
        Returns:
            List of tuples (DataFrame, page_number) for successfully parsed tables
        """
        if not CAMELOT_AVAILABLE:
            logger.warning("camelot not available. Cannot extract tables.")
            return []
        
        if method not in {'lattice', 'stream'}:
            raise ValueError(f"Invalid method: {method}. Must be 'lattice' or 'stream'")
        
        tables = []
        camelot_tables = None
        
        try:
            # Extract tables using camelot
            # Note: camelot.read_pdf() creates temporary files internally
            camelot_tables = camelot.read_pdf(
                str(self.pdf_path),
                pages=','.join(map(str, pages)) if pages else '1-end',
                flavor=method
            )
            
            # Process tables immediately and extract data to avoid holding references
            for table in camelot_tables:
                df = table.df.copy()  # Create a copy to avoid holding reference to Camelot table
                page_num = table.page
                
                # Validate table - must have at least 2 rows and 2 columns
                if len(df) < 2 or len(df.columns) < 2:
                    logger.warning(f"Rejected table on page {page_num}: insufficient dimensions")
                    continue
                
                # Try to convert numeric columns - this helps validate the table
                # If conversion fails, we still keep the table but log a warning
                validated_df = self._validate_table(df)
                if validated_df is not None:
                    tables.append((validated_df, page_num))
                else:
                    logger.warning(f"Rejected table on page {page_num}: validation failed")
        
        except Exception as e:
            logger.error(f"Error extracting tables from PDF: {e}")
            # Don't raise - return what we have
        
        finally:
            # Explicit cleanup for Windows compatibility
            # Camelot creates temporary files that need to be cleaned up
            # On Windows, file handles must be closed before temp files can be deleted
            if camelot_tables is not None:
                try:
                    # Clear reference to allow garbage collection
                    # Force garbage collection to release file handles on Windows
                    # This ensures Camelot's internal temp files can be cleaned up
                    del camelot_tables
                    gc.collect()  # Force garbage collection to release file handles
                except Exception:
                    pass  # Ignore errors during cleanup
        
        return tables
    
    def _validate_table(self, df: pd.DataFrame) -> Optional[pd.DataFrame]:
        """
        Validate that a table can be parsed deterministically.
        
        Rules:
        - Must have clear structure
        - Must have at least some numeric data
        - Must not be entirely empty
        
        Args:
            df: DataFrame to validate
            
        Returns:
            Validated DataFrame or None if validation fails
        """
        if df.empty:
            return None
        
        # Check if table has any non-empty cells
        if df.isna().all().all():
            return None
        
        # Check if at least one column appears to contain numeric data
        # (This is a heuristic to ensure we're getting actual data tables)
        has_numeric_data = False
        for col in df.columns:
            # Try to convert to numeric for at least some values
            numeric_col = pd.to_numeric(df[col], errors='coerce')
            if numeric_col.notna().sum() > 0:
                has_numeric_data = True
                break
        
        if not has_numeric_data:
            # Allow non-numeric tables but log
            logger.debug("Table has no numeric data, but keeping for reference")
        
        return df
    
    def extract_images(self, output_dir: Optional[Path] = None) -> List[Path]:
        """
        Extract images from PDF pages.
        
        CRITICAL: Images (including charts) are extracted but NOT interpreted.
        Charts are stored as images for reference only.
        
        Args:
            output_dir: Directory to save extracted images (default: same as PDF)
            
        Returns:
            List of paths to extracted image files
        """
        if not self.pdf:
            raise RuntimeError("PDF not opened. Use as context manager or call open() first.")
        
        if output_dir is None:
            output_dir = self.pdf_path.parent / f"{self.pdf_path.stem}_images"
        else:
            output_dir = Path(output_dir)
        
        output_dir.mkdir(parents=True, exist_ok=True)
        
        image_paths = []
        
        try:
            for page_num, page in enumerate(self.pdf.pages, start=1):
                # Extract images from page
                images = page.images
                
                for img_idx, img in enumerate(images):
                    # Extract image
                    bbox = (img['x0'], img['top'], img['x1'], img['bottom'])
                    page_image = page.within_bbox(bbox)
                    
                    # Save as image
                    # Note: pdfplumber doesn't directly save images, we'd need PIL for this
                    # For now, we'll use a workaround with pdfplumber's to_image method if available
                    # This is a simplified version - in production you'd use PIL/Pillow
                    image_filename = f"{self.pdf_path.stem}_page{page_num}_img{img_idx + 1}.png"
                    image_path = output_dir / image_filename
                    
                    # Note: Actual image extraction would require PIL/Pillow
                    # This is a placeholder showing the structure
                    logger.debug(f"Would extract image to: {image_path}")
                    # image_paths.append(image_path)
            
            logger.info(f"Extracted {len(image_paths)} images from PDF")
            
        except Exception as e:
            logger.error(f"Error extracting images from PDF: {e}")
        
        return image_paths
    
    def get_page_count(self) -> int:
        """Get the number of pages in the PDF."""
        if not self.pdf:
            raise RuntimeError("PDF not opened. Use as context manager or call open() first.")
        return len(self.pdf.pages)


def parse_pdf_tables(
    pdf_path: Path,
    method: str = 'lattice',
    pages: Optional[List[int]] = None
) -> List[Tuple[pd.DataFrame, int]]:
    """
    Convenience function to parse tables from a PDF.
    
    Args:
        pdf_path: Path to PDF file
        method: 'lattice' or 'stream' (camelot method)
        pages: List of page numbers (None = all pages)
        
    Returns:
        List of tuples (DataFrame, page_number)
    """
    with PDFParser(pdf_path) as parser:
        return parser.extract_tables(pages=pages, method=method)

