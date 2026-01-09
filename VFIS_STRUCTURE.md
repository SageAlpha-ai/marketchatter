# Verified Financial Intelligence System (VFIS) - Structure

## Directory Structure

```
TradingAgents/
├── vfis/                          # Main VFIS package
│   ├── __init__.py                # Package initialization
│   ├── README.md                  # VFIS documentation
│   ├── vfis_system.py             # Main system class
│   │
│   ├── agents/                    # Agent implementations
│   │   ├── __init__.py
│   │   └── verified_data_agent.py # Main data retrieval agent
│   │
│   ├── tools/                     # Data retrieval tools
│   │   ├── __init__.py
│   │   └── financial_data_tools.py # PostgreSQL-based tools
│   │
│   ├── prompts/                   # Prompt templates
│   │   ├── __init__.py
│   │   └── data_agent_prompts.py  # Strict prompts with restrictions
│   │
│   ├── ingestion/                 # Data ingestion (future)
│   │   └── __init__.py
│   │
│   └── api/                       # API endpoints (future)
│       └── __init__.py
│
├── tradingagents/                 # Original package (preserved)
│   ├── database/                  # PostgreSQL database layer
│   │   ├── connection.py
│   │   ├── schema.py
│   │   ├── dal.py
│   │   └── audit.py
│   ├── dataflows/                 # Data retrieval implementations
│   │   └── postgresql_data.py
│   └── ...
│
├── vfis_main.py                   # Main entry point
└── REFACTORING_VFIS.md            # This refactoring summary
```

## Key Files

### Main System
- **`vfis/vfis_system.py`**: Main system class that orchestrates the VFIS
- **`vfis_main.py`**: Entry point script demonstrating usage

### Agents
- **`vfis/agents/verified_data_agent.py`**: 
  - Only retrieves data via tools
  - Only summarizes retrieved data
  - NEVER generates financial numbers
  - NO trading logic

### Tools
- **`vfis/tools/financial_data_tools.py`**:
  - PostgreSQL-based data retrieval
  - Source validation (NSE, BSE, SEBI)
  - Staleness detection
  - Source attribution

### Prompts
- **`vfis/prompts/data_agent_prompts.py`**:
  - Strict system prompts
  - Explicit prohibitions on number generation
  - Guidelines for summarization
  - Source attribution requirements

## Usage Example

```python
from vfis.vfis_system import create_vfis_system
from tradingagents.default_config import DEFAULT_CONFIG

# Initialize system
config = DEFAULT_CONFIG.copy()
vfis = create_vfis_system(config=config, llm_provider="openai")

# Get financial data summary (no trading signals)
summary = vfis.get_summary("ZOMATO", "2024-05-10")
print(summary)
```

## Strict Rules Enforced

1. **NEVER generate financial numbers** - explicit in prompts and code
2. **ONLY use tools** - no direct database access by LLM
3. **ALWAYS attribute sources** - NSE, BSE, SEBI with dates
4. **EXPLICIT unavailability** - clear messaging when data missing
5. **NO trading logic** - no buy/sell/hold recommendations
6. **NO hallucinations** - only report actual data

## Windows Compatibility

All paths use `pathlib.Path`:
- Cross-platform path handling
- No hardcoded separators
- Works on Windows without modification

## Dependencies

- `tradingagents.database` - PostgreSQL database layer
- `tradingagents.dataflows.postgresql_data` - Data retrieval functions
- `langchain` - LLM integration
- `psycopg2-binary` - PostgreSQL driver

