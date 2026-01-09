# PDF Ingestion Module

## Overview

Deterministic PDF parsing and ingestion for VFIS. This module extracts structured financial data from PDF documents without using LLMs.

## STRICT RULES

- **PDFs are RAW INPUT ONLY** - no interpretation or inference
- **LLMs must NEVER parse PDFs or extract numbers** - all extraction is programmatic
- **No OCR guessing** - only deterministic table extraction
- **No chart value inference** - charts extracted as images only, never interpreted
- **PostgreSQL is the ONLY source** - queried by agents, not the PDFs directly
- **Windows-compatible** - all paths use pathlib.Path

## Files

### `pdf_parser.py`

Deterministic PDF parser using:
- `pdfplumber` for text extraction
- `camelot` (lattice + stream) for table extraction
- `pdfplumber` for image extraction

Features:
- Extracts tables as numeric DataFrames
- Rejects tables that cannot be parsed deterministically
- Extracts charts/images but does NOT interpret them

### `quarterly_pdf_ingest.py`

Ingests quarterly PDF reports (Q1 FY22 → Q2 FY26):
- Parses tables deterministically
- Inserts structured data into `parsed_tables`
- Records metadata in `document_assets`
- Uploads PDFs to Azure Blob Storage (optional)

### `annual_report_ingest.py`

Ingests annual report PDFs (2021–2024):
- Parses tables deterministically
- Stores parsed tables in `parsed_tables`
- Stores PDFs and extracted images in Azure Blob
- Records all assets in `document_assets`

## Database Schema

### `document_assets`
Stores metadata for:
- Raw PDFs
- Extracted images/charts
- Blob storage paths

### `parsed_tables`
Stores structured financial data:
- Ticker, period, table_name
- Metric name and value
- Source (NSE, BSE, SEBI)
- As-of date

## Usage

### Ingest Quarterly PDF

```python
from vfis.ingestion import ingest_quarterly_pdf
from pathlib import Path
from datetime import date

results = ingest_quarterly_pdf(
    pdf_path=Path("Q2_FY2026_ZOMATO.pdf"),
    ticker='ZOMATO',
    fiscal_year=2026,
    quarter=2,
    report_date=date(2026, 9, 30),
    source='NSE'
)

print(f"Tables parsed: {results['tables_parsed']}")
print(f"Records inserted: {results['records_inserted']}")
```

### Ingest Annual Report

```python
from vfis.ingestion import ingest_annual_report
from pathlib import Path
from datetime import date

results = ingest_annual_report(
    pdf_path=Path("FY2024_ZOMATO_Annual_Report.pdf"),
    ticker='ZOMATO',
    fiscal_year=2024,
    report_date=date(2024, 3, 31),
    source='NSE'
)

print(f"Tables parsed: {results['tables_parsed']}")
print(f"Images extracted: {results['images_extracted']}")
```

## Validation & Safety

Every parsed record must have:
- ✅ ticker present (e.g., ZOMATO)
- ✅ period explicit (e.g., Q2 FY26, FY2024)
- ✅ source validated (NSE, BSE, or SEBI only)
- ✅ as_of date populated
- ✅ Rejects ambiguous or malformed tables

## Dependencies

Required:
- `pdfplumber` - Text and image extraction
- `camelot-py[cv]` - Table extraction
- `pandas` - Data manipulation
- `azure-storage-blob` - Optional, for blob storage

Install:
```bash
pip install pdfplumber camelot-py[cv] pandas azure-storage-blob
```

## Logging & Audit

All ingestion events are:
- Logged with explicit success/failure
- Audited in `audit_log` table
- Errors are NOT silently skipped
- Failure reasons explicitly recorded

