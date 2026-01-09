# VFIS Production Architecture

## Module Boundary Map

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              VFIS SYSTEM ARCHITECTURE                           │
└─────────────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────────────┐
│ ENTRYPOINTS                                                                      │
├──────────────────────────────────────────────────────────────────────────────────┤
│  vfis/bootstrap.py         - SINGLE system initialization entrypoint             │
│  vfis/api/app.py           - FastAPI application                                 │
│  vfis_main.py              - CLI entrypoint for analysis                         │
└──────────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│ API LAYER                                                                        │
├──────────────────────────────────────────────────────────────────────────────────┤
│  vfis/api/routes.py        - API endpoints (query, ingestion, scheduler)         │
│  vfis/api/health.py        - Health check endpoints                              │
└──────────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│ AGENT LAYER                                                                      │
├──────────────────────────────────────────────────────────────────────────────────┤
│  vfis/agents/final_output_assembly.py  - Final output orchestrator               │
│  vfis/agents/debate_orchestrator.py    - Bull vs Bear debate                     │
│  vfis/agents/bull_agent.py             - Positive signals analysis               │
│  vfis/agents/bear_agent.py             - Risk signals analysis                   │
│  vfis/agents/risk_management_agent.py  - Risk classification                     │
│  vfis/agents/verified_data_agent.py    - Data verification                       │
└──────────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│ INGESTION LAYER (Canonical)                                                      │
├──────────────────────────────────────────────────────────────────────────────────┤
│  vfis/ingestion/__init__.py      - CANONICAL entrypoint (ingest_ticker, etc.)    │
│  vfis/ingestion/scheduler.py     - Background scheduler (5-minute interval)      │
│  tradingagents/dataflows/ingest_chatter.py - Core ingestion logic                │
│  tradingagents/dataflows/chatter_schema.py - MarketChatterRecord schema          │
└──────────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│ DATA ACCESS LAYER                                                                │
├──────────────────────────────────────────────────────────────────────────────────┤
│  tradingagents/database/chatter_dal.py    - Market chatter DAL (dict contract)   │
│  tradingagents/database/chatter_persist.py - SINGLE persistence function         │
│  tradingagents/database/dal.py            - Financial data DAL                   │
│  tradingagents/database/connection.py     - Connection pool management           │
│  vfis/tools/postgres_dal.py               - VFIS-specific DAL                    │
└──────────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│ DATABASE                                                                         │
├──────────────────────────────────────────────────────────────────────────────────┤
│  PostgreSQL                                                                      │
│    - market_chatter (UNIQUE: source, source_id)                                  │
│    - companies                                                                   │
│    - balance_sheet, income_statement, cashflow_statement                         │
│    - news, technical_indicators                                                  │
│    - audit_log                                                                   │
└──────────────────────────────────────────────────────────────────────────────────┘
```

## File Status Reference

### Active (Production)
| File | Purpose |
|------|---------|
| `vfis/bootstrap.py` | Single system initialization |
| `vfis/api/app.py` | FastAPI application |
| `vfis/api/routes.py` | API endpoints |
| `vfis/ingestion/__init__.py` | Canonical ingestion entrypoint |
| `vfis/ingestion/scheduler.py` | Background scheduler |
| `tradingagents/dataflows/ingest_chatter.py` | Core ingestion logic |
| `tradingagents/dataflows/chatter_schema.py` | Canonical schema |
| `tradingagents/database/chatter_persist.py` | Single persistence function |
| `tradingagents/database/chatter_dal.py` | Chatter DAL (dict contract) |

### Deprecated (Backward Compatibility)
| File | Replacement |
|------|-------------|
| `scripts/init_env.py` | `vfis.bootstrap.bootstrap()` |
| `vfis/market_chatter/ingest.py` | `vfis.ingestion.ingest_ticker()` |
| `vfis/market_chatter/aggregator.py` | `vfis.ingestion.ingest_ticker()` |

### Utility (Supporting)
| File | Purpose |
|------|---------|
| `vfis/tools/llm_factory.py` | Azure OpenAI LLM creation |
| `vfis/tools/sentiment_scoring.py` | Sentiment analysis |
| `vfis/market_chatter/storage.py` | Storage wrapper (delegates to persist) |

## DAL Return Contract

All DAL methods return:
```python
{
    "data": Any,        # Payload (dict, list, etc.)
    "status": str,      # "success" | "no_data" | "error"
    "message": str      # Human-readable description
}
```

**Exception**: Legacy methods in `tradingagents/database/dal.py` return tuples for backward compatibility. Use `*_dict` variants for new code.

## Environment Variables

### Required (Fail-fast)
```env
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=vfis_db
POSTGRES_USER=postgres
POSTGRES_PASSWORD=<secret>
```

### Required for LLM (Warning if missing)
```env
AZURE_OPENAI_API_KEY=<secret>
AZURE_OPENAI_ENDPOINT=https://xxx.openai.azure.com/
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4o
```

### Optional
```env
ALPHA_VANTAGE_API_KEY=<key>          # Enables Alpha Vantage ingestion
ACTIVE_TICKERS=AAPL,MSFT,GOOGL       # Tickers for scheduled ingestion
INGESTION_INTERVAL_SECONDS=300       # Scheduler interval (default: 5 min)
INGESTION_LOOKBACK_DAYS=7            # Days to look back (default: 7)
```

## Ingestion Source Priority

1. **RSS Feeds** - Always enabled, no API key required
2. **Alpha Vantage** - Only if `ALPHA_VANTAGE_API_KEY` is set
3. **Reddit** - Future (not implemented)
4. **Twitter/X** - Future (not implemented)

## Ticker Resolution Priority

1. API request body
2. `ACTIVE_TICKERS` environment variable
3. `companies` table (is_active=TRUE)
4. **No hardcoded fallback**

---

*Last updated: January 2026*

