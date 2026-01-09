# VFIS Tools - PostgreSQL Data Access Layer

## Overview

This module provides tools for accessing verified financial data from PostgreSQL. All tools enforce strict rules:

- **PostgreSQL is the ONLY source** - no external APIs
- **Source validation** - only NSE, BSE, SEBI allowed
- **Staleness detection** - explicit reporting of data age
- **Status reporting** - SUCCESS, NO_DATA, STALE_DATA, ERROR
- **Audit logging** - all access logged with agent name, query, and tables accessed

## Files

### `postgres_dal.py`

Data Access Layer (DAL) providing:
- `VFISDataAccess` class with methods for retrieving financial data
- `DataStatus` enum for explicit status reporting
- Safe parameterized queries
- Connection pooling (via tradingagents.database.connection)
- Source validation and attribution
- Staleness detection

### `financial_data_tools.py`

LangChain tools that wrap the DAL:
- `get_fundamentals()` - Comprehensive fundamental data
- `get_balance_sheet()` - Balance sheet data
- `get_income_statement()` - Income statement data
- `get_cashflow()` - Cash flow statement data

### `schema_extension.py`

Schema extensions for VFIS:
- `create_vfis_tables()` - Creates news and technical_indicators tables
- `update_audit_log_schema()` - Enhances audit log for VFIS-specific fields

## Staleness Thresholds

- **Quarterly data**: 120 days
- **Annual reports**: 400 days
- **News articles**: 48 hours

## Status Codes

- `SUCCESS` - Data retrieved successfully and is fresh
- `NO_DATA` - No data available in database
- `STALE_DATA` - Data exists but exceeds staleness threshold
- `ERROR` - Error occurred during retrieval

## Usage Example

```python
from vfis.tools.postgres_dal import VFISDataAccess, DataStatus

# Get quarterly balance sheet
data, status = VFISDataAccess.get_quarterly_financials(
    ticker='ZOMATO',
    statement_type='balance_sheet',
    agent_name='MyAgent',
    user_query='Get balance sheet data'
)

if status == DataStatus.SUCCESS:
    print("Data retrieved successfully")
    print(f"Source: {data['data_source']}")
    print(f"As-of date: {data['as_of_date']}")
elif status == DataStatus.NO_DATA:
    print("No data available")
elif status == DataStatus.STALE_DATA:
    print(f"Data is stale: {data.get('days_old')} days old")
```

## Audit Logging

All data access is automatically logged with:
- Agent name
- User query
- Tables accessed
- Status
- Additional details

Logs are stored in the `audit_log` table.

