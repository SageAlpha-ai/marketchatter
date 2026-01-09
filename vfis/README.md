# Verified Financial Intelligence System (VFIS)

## Overview

VFIS is a production-grade system for retrieving and summarizing verified financial data from PostgreSQL. The system strictly enforces that:

- **LLMs NEVER generate financial numbers** - they only retrieve and summarize
- **All financial data comes from PostgreSQL** via tools
- **Agents only read, reason, and summarize** - no trading logic
- **No buy/sell signals** - no investment recommendations

## Structure

```
vfis/
├── agents/          # Agent implementations
│   └── verified_data_agent.py  # Main agent for data retrieval and summarization
├── tools/           # Data retrieval tools
│   └── financial_data_tools.py # PostgreSQL-based financial data tools
├── prompts/         # Prompt templates
│   └── data_agent_prompts.py   # Prompts with strict restrictions
├── ingestion/       # Data ingestion (future)
├── api/             # API endpoints (future)
└── vfis_system.py   # Main system class
```

## Key Components

### VerifiedDataAgent

The main agent responsible for:
- Retrieving financial data via tools
- Summarizing retrieved data
- **NOT generating financial numbers**
- **NOT providing trading recommendations**

### Financial Data Tools

Tools that retrieve data from PostgreSQL:
- `get_fundamentals()` - Comprehensive fundamental data
- `get_balance_sheet()` - Balance sheet data
- `get_income_statement()` - Income statement data
- `get_cashflow()` - Cash flow statement data

All tools:
- Only access PostgreSQL database
- Only return data from verified sources (NSE, BSE, SEBI)
- Include source attribution and as-of dates
- Report staleness warnings

### Prompts

Strict prompts that enforce:
- No financial number generation
- Only tool-based data access
- Source attribution requirements
- Explicit unavailability reporting
- No trading logic

## Usage

```python
from vfis.vfis_system import create_vfis_system
from tradingagents.default_config import DEFAULT_CONFIG

# Create system
config = DEFAULT_CONFIG.copy()
vfis = create_vfis_system(config=config, llm_provider="openai")

# Analyze company
summary = vfis.get_summary("ZOMATO", "2024-05-10")
print(summary)
```

## Strict Rules

1. **NEVER generate financial numbers** - only retrieve from database
2. **ONLY use tools** - no direct data access
3. **ALWAYS attribute sources** - NSE, BSE, or SEBI with as-of dates
4. **EXPLICIT unavailability** - state clearly when data is missing
5. **NO trading logic** - no buy/sell/hold recommendations
6. **NO hallucinations** - only report what's in the data

## Windows Compatibility

All paths use `pathlib.Path` for Windows compatibility.

