# Verified Financial Data AI System (VFIS)

## Overview

This system has been refactored from TradingAgents into a production-grade Verified Financial Data AI System. The system ensures that:

- **LLM NEVER generates financial numbers** - it only routes to data tools and summarizes results
- **All financial data comes from PostgreSQL** - no external API calls for financial data
- **Only verified sources** - NSE, BSE, and SEBI are the only valid data sources
- **Full audit logging** - all data access and LLM operations are logged
- **Source attribution** - every financial metric includes data source and as-of date
- **Staleness detection** - system explicitly reports when data is stale or unavailable

## Key Requirements

1. **Data Sources**: Only NSE, BSE, and SEBI are valid sources
2. **Company Support**: Zomato (Eternal Limited) with ticker symbol 'ZOMATO'
3. **Data Coverage**:
   - Quarterly reports: 2022 to Q2 FY 2026
   - Annual reports: 2021-2024
4. **LLM Restrictions**: LLM can only route to tools and summarize - never generate or calculate financial numbers

## Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure PostgreSQL Database

Create a `.env` file in the project root:

```env
DB_HOST=localhost
DB_PORT=5432
DB_NAME=vfis_db
DB_USER=postgres
DB_PASSWORD=your_password
OPENAI_API_KEY=your_openai_key
```

### 3. Initialize Database

```bash
python scripts/init_database.py
```

This will:
- Create the database schema
- Set up Zomato company entry
- Configure data source references (NSE, BSE, SEBI)

### 4. Populate Financial Data

You need to populate the database with financial data from NSE, BSE, or SEBI. Data should include:

- **Quarterly Reports**: Q1 2022 through Q2 FY 2026
- **Annual Reports**: 2021, 2022, 2023, 2024

The data should be inserted into:
- `annual_reports` and `quarterly_reports` tables
- `balance_sheet`, `income_statement`, and `cashflow_statement` tables
- All data must reference valid `data_sources` (NSE, BSE, or SEBI)

## Usage

### Basic Usage

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG
from dotenv import load_dotenv

load_dotenv()

# Initialize the system
config = DEFAULT_CONFIG.copy()
ta = TradingAgentsGraph(debug=True, config=config)

# Analyze a company (Zomato)
_, decision = ta.propagate("ZOMATO", "2024-05-10")
print(decision)
```

## Architecture

### Database Schema

- **companies**: Company master data
- **data_sources**: Valid data sources (NSE, BSE, SEBI) per company
- **annual_reports**: Annual report metadata
- **quarterly_reports**: Quarterly report metadata
- **balance_sheet**: Balance sheet metrics
- **income_statement**: Income statement metrics
- **cashflow_statement**: Cash flow metrics
- **audit_log**: Complete audit trail of all operations

### Data Access Layer

All financial data access goes through `tradingagents.database.dal.FinancialDataAccess`:

- Validates data sources
- Tracks as-of dates
- Detects stale data
- Logs all access for audit

### Agent Restrictions

All agents, especially the fundamentals analyst, have explicit prompts that:

1. Prohibit financial number generation
2. Require source attribution
3. Require as-of date reporting
4. Explicitly state data staleness/unavailability

## Windows Compatibility

The system uses `pathlib.Path` for all file operations to ensure Windows compatibility.

## Audit Logging

All operations are logged to the `audit_log` table:

- Data retrieval events
- LLM interactions
- Errors
- Source tracking

## Data Staleness

The system detects stale data based on a configurable threshold (default: 90 days). When data is stale, the system explicitly warns users with a message like:

```
WARNING: Data is 120 days old (as of 2024-01-15).
```

## Important Notes

- **Never use external APIs for financial data** - all data must come from PostgreSQL
- **Always include data source and as-of date** in summaries
- **Explicitly state unavailability** - never infer or estimate missing data
- **Quote numbers exactly** as provided by the database tools

