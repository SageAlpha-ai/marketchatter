"""
Quarterly PDF ingestion script for VFIS.

STRICT RULES:
- Ingest quarterly PDFs (Q1 FY22 → Q2 FY26)
- Insert structured financial tables into parsed_tables
- Insert metadata into document_assets
- All values must be extracted deterministically (no LLM)
- Reject ambiguous or malformed tables
- Windows-compatible paths only
- NO hardcoded file paths - use --input_dir argument
"""
import scripts.init_env
import logging
import argparse
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime, date
import pandas as pd
import sys

# Add parent directories to path
_project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_project_root))

from vfis.ingestion.pdf_parser import PDFParser
from vfis.tools.blob_storage import create_blob_storage_manager
from vfis.tools.document_integrity import compute_file_hash, check_duplicate_document
from tradingagents.database.connection import get_db_connection, init_database
from tradingagents.database.audit import log_data_access

logger = logging.getLogger(__name__)

# Initialize database connection pool on module import
# Environment variables are already loaded by scripts.init_env import above
# This is idempotent - safe to call multiple times
init_database(config={})  # Uses environment variables (POSTGRES_*)

# Valid sources
VALID_SOURCES = {'NSE', 'BSE', 'SEBI'}


class QuarterlyPDFIngester:
    """
    Ingester for quarterly PDF financial reports.
    
    CRITICAL: All parsing is deterministic. No LLM usage.
    """
    
    def __init__(
        self,
        ticker: str,
        source: str,
        blob_storage_manager=None
    ):
        """
        Initialize quarterly PDF ingester.
        
        Args:
            ticker: Company ticker symbol (dynamically provided)
            source: Data source ('NSE', 'BSE', or 'SEBI')
            blob_storage_manager: Optional BlobStorageManager instance
        """
        if source not in VALID_SOURCES:
            raise ValueError(f"Invalid source: {source}. Must be one of {VALID_SOURCES}")
        
        self.ticker = ticker.upper()
        self.source = source
        self.blob_manager = blob_storage_manager
    
    def ingest_pdf(
        self,
        pdf_path: Path,
        fiscal_year: int,
        quarter: int,
        report_date: date,
        filing_date: Optional[date] = None
    ) -> Dict[str, Any]:
        """
        Ingest a single quarterly PDF file.
        
        Args:
            pdf_path: Path to PDF file (Windows-compatible Path object)
            fiscal_year: Fiscal year (e.g., 2024)
            quarter: Quarter number (1, 2, 3, or 4)
            report_date: Report date (as-of date)
            filing_date: Optional filing date
            
        Returns:
            Dictionary with ingestion results
        """
        # Resolve absolute path (Windows-compatible)
        pdf_path = Path(pdf_path).resolve()
        
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")
        
        if not pdf_path.suffix.lower() == '.pdf':
            raise ValueError(f"File is not a PDF: {pdf_path}")
        
        logger.info(f"Ingesting quarterly PDF: {pdf_path.name} for {self.ticker}")
        
        # Compute SHA-256 hash for document integrity
        file_hash = compute_file_hash(pdf_path)
        logger.debug(f"Computed SHA-256 hash for {pdf_path.name}: {file_hash[:16]}...")
        
        # Check for duplicate document
        is_duplicate, existing_asset_id = check_duplicate_document(
            ticker=self.ticker,
            document_type='quarterly',
            file_hash=file_hash
        )
        
        if is_duplicate:
            logger.warning(
                f"Skipping {pdf_path.name} - duplicate document detected "
                f"(existing asset_id={existing_asset_id}, hash: {file_hash[:16]}...)"
            )
            return {
                'success': 'skipped',  # Mark as skipped, not failed
                'ticker': self.ticker,
                'pdf_path': str(pdf_path),
                'reason': 'duplicate_document',
                'existing_asset_id': existing_asset_id,
                'file_hash': file_hash
            }
        
        period = f"Q{quarter} FY{fiscal_year}"
        results = {
            'success': False,
            'document_asset_id': None,
            'tables_parsed': 0,
            'records_inserted': 0,
            'file_hash': file_hash,
            'is_duplicate': False,
            'errors': []
        }
        
        try:
            # Step 1: Upload PDF to blob storage (if available)
            blob_path = None
            if self.blob_manager:
                try:
                    blob_path = self.blob_manager.upload_pdf(
                        file_path=pdf_path,
                        ticker=self.ticker,
                        document_type='quarterly',
                        period=period,
                        source=self.source
                    )
                except Exception as e:
                    logger.warning(f"Failed to upload PDF to blob storage: {e}")
                    results['errors'].append(f"Blob upload failed: {str(e)}")
            
            # Step 2: Record document asset in database with hash
            document_asset_id = self._record_document_asset(
                pdf_path=pdf_path,
                period=period,
                blob_path=blob_path,
                report_date=report_date,
                file_hash=file_hash
            )
            results['document_asset_id'] = document_asset_id
            
            # Step 3: Parse tables from PDF using context manager
            with PDFParser(pdf_path) as parser:
                tables_data = parser.extract_tables(method='lattice')
                results['tables_parsed'] = len(tables_data)
                
                # Step 4: Insert parsed tables into database
                for table_df, page_num in tables_data:
                    try:
                        records = self._insert_parsed_table(
                            table_df=table_df,
                            period=period,
                            table_name=f"table_page_{page_num}",
                            report_date=report_date,
                            document_asset_id=document_asset_id
                        )
                        results['records_inserted'] += records
                    except Exception as e:
                        error_msg = f"Failed to insert table from page {page_num}: {str(e)}"
                        logger.error(error_msg)
                        results['errors'].append(error_msg)
            
            results['success'] = True
            
            # Log audit
            log_data_access(
                event_type='pdf_ingestion',
                entity_type='quarterly_report',
                entity_id=document_asset_id,
                details={
                    'ticker': self.ticker,
                    'period': period,
                    'source': self.source,
                    'tables_parsed': results['tables_parsed'],
                    'records_inserted': results['records_inserted'],
                    'errors': results['errors']
                },
                user_id='quarterly_pdf_ingester'
            )
            
            logger.info(
                f"Ingested quarterly PDF: {period} - "
                f"{results['tables_parsed']} tables, "
                f"{results['records_inserted']} records"
            )
            
        except Exception as e:
            error_msg = f"Failed to ingest PDF {pdf_path}: {str(e)}"
            logger.error(error_msg, exc_info=True)
            results['errors'].append(error_msg)
        
        return results
    
    def _record_document_asset(
        self,
        pdf_path: Path,
        period: str,
        blob_path: Optional[str],
        report_date: date,
        file_hash: str
    ) -> int:
        """
        Record document asset in database with file hash.
        
        CRITICAL: Includes SHA-256 hash for document integrity.
        
        Returns:
            Document asset ID
        """
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                file_size = pdf_path.stat().st_size
                
                cur.execute("""
                    INSERT INTO document_assets 
                    (ticker, document_type, period, asset_type, blob_path, file_name, file_size_bytes, file_hash, source, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                    RETURNING id
                """, (
                    self.ticker,
                    'quarterly',
                    period,
                    'pdf',
                    blob_path or str(pdf_path),  # Use local path if blob not available
                    pdf_path.name,
                    file_size,
                    file_hash,
                    self.source
                ))
                
                asset_id = cur.fetchone()[0]
                conn.commit()
                logger.info(f"Recorded document asset {asset_id} with hash: {file_hash[:16]}...")
                return asset_id
    
    def _insert_parsed_table(
        self,
        table_df: pd.DataFrame,
        period: str,
        table_name: str,
        report_date: date,
        document_asset_id: int
    ) -> int:
        """
        Insert parsed table data into parsed_tables.
        
        CRITICAL: Only inserts numeric values deterministically extracted.
        Rejects ambiguous or non-numeric data.
        
        Returns:
            Number of records inserted
        """
        records_inserted = 0
        
        # Identify metric column and value columns
        # This is a simplified approach - in production you'd have more sophisticated
        # table structure detection
        if len(table_df.columns) < 2:
            logger.warning(f"Table {table_name} has insufficient columns, skipping")
            return 0
        
        # Assume first column is metric name, rest are values
        metric_col = table_df.columns[0]
        value_cols = table_df.columns[1:]
        
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                for idx, row in table_df.iterrows():
                    metric = str(row[metric_col]).strip()
                    
                    # Skip empty metrics
                    if not metric or metric.lower() in {'nan', 'none', ''}:
                        continue
                    
                    # Try each value column
                    for value_col in value_cols:
                        value = row[value_col]
                        
                        # Try to convert to numeric
                        try:
                            numeric_value = pd.to_numeric(value, errors='raise')
                        except (ValueError, TypeError):
                            # Skip non-numeric values
                            continue
                        
                        # Insert record
                        try:
                            cur.execute("""
                                INSERT INTO parsed_tables 
                                (ticker, period, table_name, metric, value, source, as_of, document_asset_id)
                                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                                ON CONFLICT (ticker, period, table_name, metric, as_of) 
                                DO UPDATE SET value = EXCLUDED.value
                            """, (
                                self.ticker,
                                period,
                                table_name,
                                metric,
                                float(numeric_value),
                                self.source,
                                report_date,
                                document_asset_id
                            ))
                            records_inserted += 1
                        except Exception as e:
                            logger.warning(f"Failed to insert record for {metric}: {e}")
                            continue
                
                conn.commit()
        
        return records_inserted


def ingest_quarterly_pdf(
    pdf_path: Path,
    ticker: str,
    fiscal_year: int,
    quarter: int,
    report_date: date,
    source: str,
    filing_date: Optional[date] = None,
    blob_storage_manager=None
) -> Dict[str, Any]:
    """
    Ingest a single quarterly PDF file (convenience function).
    
    This function is kept unchanged for compatibility.
    Use ingest_quarterly_pdf_from_dir() for directory-based ingestion.
    """
    ingester = QuarterlyPDFIngester(ticker=ticker, source=source, blob_storage_manager=blob_storage_manager)
    return ingester.ingest_pdf(
        pdf_path=pdf_path,
        fiscal_year=fiscal_year,
        quarter=quarter,
        report_date=report_date,
        filing_date=filing_date
    )


def ingest_quarterly_pdf_from_dir(
    input_dir: Path,
    ticker: str,
    source: str = 'NSE',
    blob_storage_manager=None
) -> List[Dict[str, Any]]:
    """
    Ingest all quarterly PDFs from a directory.
    
    Args:
        input_dir: Directory containing PDF files (Windows-compatible Path)
        ticker: Company ticker symbol (dynamically provided)
        source: Data source ('NSE', 'BSE', or 'SEBI')
        blob_storage_manager: Optional BlobStorageManager instance
        
    Returns:
        List of ingestion results for each PDF
        
    Raises:
        FileNotFoundError: If directory doesn't exist or contains no PDFs
    """
    # Resolve absolute path strictly (Windows-compatible)
    # This ensures we use ONLY the CLI-provided input directory
    absolute_path = Path(input_dir).resolve(strict=True)
    
    logger.info(f"Resolved PDF input directory: {absolute_path}")
    
    # Validate directory exists (should already be checked by resolve(strict=True), but double-check)
    if not absolute_path.exists():
        raise FileNotFoundError(
            f"Input directory does not exist: {absolute_path}\n"
            f"Please provide a valid directory path containing quarterly PDF files."
        )
    
    if not absolute_path.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {absolute_path}")
    
    # Find all PDF files in directory - use ONLY the resolved absolute path
    pdf_files = sorted(list(absolute_path.glob("*.pdf")))
    
    # Validate at least one PDF found
    if not pdf_files:
        raise FileNotFoundError(
            f"No PDF files found in directory: {absolute_path}\n"
            f"Please ensure the directory contains at least one .pdf file."
        )
    
    logger.info(f"Found {len(pdf_files)} PDF file(s) in {absolute_path}")
    
    # Initialize ingester
    ingester = QuarterlyPDFIngester(
        ticker=ticker,
        source=source,
        blob_storage_manager=blob_storage_manager
    )
    
    # Ingest each PDF
    # pdf_path is built ONLY from absolute_path / filename (via glob)
    results = []
    for pdf_path in pdf_files:
        # Ensure pdf_path is absolute and resolved (should already be from glob, but double-check)
        pdf_path = pdf_path.resolve()
        logger.info(f"Processing: {pdf_path.name}")
        
        # Extract fiscal year and quarter from filename if possible
        # Note: This is a best-effort attempt. Filenames should follow a pattern,
        # but we cannot assume a specific format per requirements.
        # Users should ensure proper file naming or provide metadata separately.
        try:
            # Robust quarter and fiscal year extraction from filename
            # Handles: Q1, Q 1, Q-1, Q1 FY22, Q1FY22, Q1 FY2024, etc.
            # Case-insensitive, ignores spaces/underscores
            import re
            
            # Get normalized and original versions for different pattern matching
            filename_upper = pdf_path.stem.upper()
            filename_normalized = re.sub(r'[\s_\-]', '', filename_upper)
            
            quarter = None
            fiscal_year = None
            
            # Extract quarter: Q1, Q2, Q3, Q4 (after normalization, should be Q1, Q2, etc.)
            quarter_match = re.search(r'Q([1-4])', filename_normalized)
            if quarter_match:
                quarter = int(quarter_match.group(1))
            
            # Extract fiscal year using multiple patterns (check original first for ranges)
            # Pattern 1: Year range like 2022-23, 2021-22 (extract start year from original)
            match = re.search(r'(\d{4})-(\d{2})', filename_upper)
            if match:
                fiscal_year = int(match.group(1))
            else:
                # Pattern 2: FY followed by 4-digit year (FY2024)
                match = re.search(r'FY(\d{4})', filename_normalized)
                if match:
                    fiscal_year = int(match.group(1))
                else:
                    # Pattern 3: FY followed by 2-digit year (FY22, FY23) - assume 2000s
                    match = re.search(r'FY(\d{2})', filename_normalized)
                    if match:
                        year_2digit = int(match.group(1))
                        # Convert 2-digit year to 4-digit (assume 2000-2099 range)
                        fiscal_year = 2000 + year_2digit if year_2digit < 100 else year_2digit
                    else:
                        # Pattern 4: 4-digit year standalone (2024, 2023)
                        match = re.search(r'\b(19\d{2}|20\d{2})\b', filename_normalized)
                        if match:
                            fiscal_year = int(match.group(1))
                        else:
                            # Pattern 5: 2-digit year standalone (22, 23) - assume 2000s
                            match = re.search(r'\b(\d{2})\b', filename_normalized)
                            if match and len(match.group(1)) == 2:
                                year_2digit = int(match.group(1))
                                # Only accept reasonable 2-digit years (20-99 for fiscal years)
                                if 20 <= year_2digit <= 99:
                                    fiscal_year = 2000 + year_2digit
            
            # If we couldn't extract, log warning and use defaults
            if quarter is None or fiscal_year is None:
                missing = []
                if quarter is None:
                    missing.append("quarter")
                if fiscal_year is None:
                    missing.append("fiscal year")
                logger.warning(
                    f"Could not extract {', '.join(missing)} from filename: {pdf_path.name}. "
                    f"Using default values (Q{quarter or 1} FY{fiscal_year or 2024}). "
                    f"Document will still be ingested."
                )
                quarter = quarter or 1
                fiscal_year = fiscal_year or 2024
            
            # Use current date as report_date (can be improved)
            report_date = date.today()
            
            result = ingester.ingest_pdf(
                pdf_path=pdf_path,
                fiscal_year=fiscal_year,
                quarter=quarter,
                report_date=report_date
            )
            results.append(result)
        
        except Exception as e:
            logger.error(f"Error processing {pdf_path.name}: {e}", exc_info=True)
            results.append({
                'success': False,
                'ticker': ticker,
                'pdf_path': str(pdf_path),
                'reason': 'processing_error',
                'error': str(e)
            })
    
    successful = sum(1 for r in results if r.get('success') is True)
    skipped = sum(1 for r in results if r.get('success') == 'skipped')
    failed = sum(1 for r in results if r.get('success') is False)
    
    logger.info(
        f"Ingestion complete: {successful} successful, {skipped} skipped (duplicates), "
        f"{failed} failed out of {len(results)} PDF(s)"
    )
    
    return results


def main():
    """Main entry point for command-line usage."""
    parser = argparse.ArgumentParser(
        description='Ingest quarterly PDF financial reports into VFIS database',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python quarterly_pdf_ingest.py --ticker <TICKER> --input_dir /path/to/reports
  python quarterly_pdf_ingest.py --ticker <TICKER> --input_dir /path/to/reports --source NSE
        """
    )
    
    parser.add_argument(
        '--ticker',
        type=str,
        required=True,
        help='Company ticker symbol (dynamically provided)'
    )
    
    parser.add_argument(
        '--input_dir',
        type=str,
        required=True,
        help='Directory containing quarterly PDF files (e.g., vfis/data/zomato/quarterly)'
    )
    
    parser.add_argument(
        '--source',
        type=str,
        default='NSE',
        choices=VALID_SOURCES,
        help=f'Data source (default: NSE). Must be one of: {", ".join(VALID_SOURCES)}'
    )
    
    parser.add_argument(
        '--log-level',
        type=str,
        default='INFO',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        help='Logging level (default: INFO)'
    )
    
    args = parser.parse_args()
    
    # Configure logging
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    try:
        # Resolve input directory strictly at CLI entry point
        # This ensures we use ONLY the CLI-provided input directory
        absolute_input_dir = Path(args.input_dir).resolve(strict=True)
        
        # Ingest PDFs from directory
        results = ingest_quarterly_pdf_from_dir(
            input_dir=absolute_input_dir,
            ticker=args.ticker,
            source=args.source
        )
        
        # Print summary
        successful = sum(1 for r in results if r.get('success') is True)
        skipped = sum(1 for r in results if r.get('success') == 'skipped')
        failed = sum(1 for r in results if r.get('success') is False)
        
        print(f"\n{'='*60}")
        print(f"Ingestion Summary")
        print(f"{'='*60}")
        print(f"Total PDFs processed: {len(results)}")
        print(f"Successful: {successful}")
        print(f"Skipped (duplicates): {skipped}")
        print(f"Failed: {failed}")
        print(f"{'='*60}\n")
        
        if skipped > 0:
            print("Skipped PDFs (duplicates):")
            for result in results:
                if result.get('success') == 'skipped':
                    print(f"  - {Path(result['pdf_path']).name}: {result.get('reason', 'duplicate')}")
            print()
        
        if failed > 0:
            print("Failed PDFs:")
            for result in results:
                if result.get('success') is False:
                    print(f"  - {Path(result['pdf_path']).name}: {result.get('reason', 'unknown')}")
            print()
        
        # Exit with error code only if there are actual failures (not skipped duplicates)
        sys.exit(0 if failed == 0 else 1)
    
    except FileNotFoundError as e:
        logger.error(str(e))
        print(f"\nERROR: {e}\n", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        print(f"\nERROR: {e}\n", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
