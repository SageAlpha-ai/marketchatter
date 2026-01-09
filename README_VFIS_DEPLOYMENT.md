# VFIS Production Deployment Guide

## Overview

This guide provides instructions for deploying the Verified Financial Intelligence System (VFIS) to production.

## Quick Start

1. **Review Deployment Documentation**: See [deployment/azure_app_service.md](./deployment/azure_app_service.md)
2. **Set Up n8n Workflows**: Import workflows from `vfis/n8n/workflows/`
3. **Configure Environment Variables**: Set up via Azure App Service Configuration
4. **Deploy**: Follow Azure deployment guide

## Architecture

```
┌─────────────────┐
│   n8n Workflows │ (Orchestration)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  FastAPI API    │ (Azure App Service)
│  /api/v1/query  │
└────────┬────────┘
         │
    ┌────┴────┐
    ▼         ▼
┌────────┐  ┌──────────────┐
│PostgreSQL│  │ Azure Blob   │
│ Flexible │  │  Storage     │
│  Server  │  └──────────────┘
└─────────┘
```

## API Endpoints

### POST /api/v1/query

Main intelligence query endpoint.

**Request:**
```json
{
  "ticker": "ZOMATO",
  "subscriber_risk_profile": "MODERATE",
  "query_intent": "Analyze Zomato for moderate risk investor"
}
```

**Response:**
```json
{
  "success": true,
  "ticker": "ZOMATO",
  "analysis_date": "2024-01-15",
  "output": {
    "components": {
      "bull_vs_bear_debate": {...},
      "risk_classification": {...},
      "subscriber_suitability": {...}
    }
  },
  "data_quality": {
    "warnings": [],
    "limitations": []
  },
  "processing_time_ms": 1234.5
}
```

### GET /health

Health check endpoint for Azure App Service.

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2024-01-15T00:00:00",
  "checks": {
    "database": {
      "status": "healthy",
      "message": "Database connection successful"
    },
    "environment": {
      "status": "healthy",
      "message": "All required environment variables present"
    }
  }
}
```

## Environment Variables

### Required

- `DATABASE_URL`: PostgreSQL connection string
- `OPENAI_API_KEY`: OpenAI API key for LLM operations

### Optional

- `AZURE_STORAGE_CONNECTION_STRING`: Azure Blob Storage connection string
- `PORT`: Server port (default: 8000)
- `HOST`: Server host (default: 0.0.0.0)
- `CORS_ORIGINS`: Comma-separated list of allowed origins (default: "*")

## n8n Workflows

### Daily Ingestion Workflow

- **Schedule**: Daily at 2 AM UTC
- **Tasks**: 
  - Quarterly PDF ingestion
  - Annual report ingestion
  - News RSS ingestion
  - Technical indicators computation

### On-Demand Intelligence Workflow

- **Trigger**: Webhook
- **Task**: Calls FastAPI /query endpoint
- **Input**: ticker, subscriber_risk_profile, query_intent

Import workflows from `vfis/n8n/workflows/` into your n8n instance.

## Local Development

### Start API Server

```bash
cd TradingAgents
python -m vfis.api.app
```

Or with uvicorn:

```bash
uvicorn vfis.api.app:app --host 0.0.0.0 --port 8000 --reload
```

### Test Endpoints

```bash
# Health check
curl http://localhost:8000/health

# Query endpoint
curl -X POST http://localhost:8000/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{
    "ticker": "ZOMATO",
    "subscriber_risk_profile": "MODERATE",
    "query_intent": "Test query"
  }'
```

## Production Deployment

See detailed guide in [deployment/azure_app_service.md](./deployment/azure_app_service.md).

Key steps:
1. Create Azure resources (App Service, PostgreSQL, Blob Storage)
2. Configure environment variables
3. Deploy application
4. Initialize database
5. Configure monitoring
6. Set up n8n workflows

## Monitoring

- **Health Checks**: `/health` endpoint
- **Application Logs**: Azure App Service logs
- **Application Insights**: Configured via Azure Portal
- **Database Metrics**: Azure PostgreSQL monitoring

## Security

- HTTPS only in production
- Database firewall rules
- Environment variables for secrets (use Azure Key Vault)
- CORS configuration
- Input validation on all endpoints

## Support

For deployment issues:
1. Check application logs
2. Verify health endpoint
3. Review environment variable configuration
4. Check database connectivity
5. Review Azure deployment guide

