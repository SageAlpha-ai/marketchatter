# Azure App Service Deployment Guide for VFIS

## Overview

This guide covers deployment of the Verified Financial Intelligence System (VFIS) to Azure App Service.

## Architecture

- **Azure App Service** (Python): FastAPI application
- **Azure PostgreSQL Flexible Server**: Database
- **Azure Blob Storage**: Document and image storage
- **Azure Monitor**: Logging and monitoring

## Prerequisites

1. Azure subscription
2. Azure CLI installed and configured
3. Python 3.10+ environment locally
4. VFIS codebase ready for deployment

## Step 1: Create Azure Resources

### 1.1 Create Resource Group

```bash
az group create \
  --name vfis-rg \
  --location eastus
```

### 1.2 Create PostgreSQL Flexible Server

```bash
az postgres flexible-server create \
  --resource-group vfis-rg \
  --name vfis-postgres \
  --location eastus \
  --admin-user vfisadmin \
  --admin-password <STRONG_PASSWORD> \
  --sku-name Standard_B1ms \
  --tier Burstable \
  --version 14 \
  --storage-size 32 \
  --public-access 0.0.0.0
```

**Note**: Restrict public access after deployment using firewall rules.

### 1.3 Create Azure Blob Storage Account

```bash
az storage account create \
  --resource-group vfis-rg \
  --name vfisstorage \
  --location eastus \
  --sku Standard_LRS \
  --kind StorageV2
```

### 1.4 Create Storage Container

```bash
az storage container create \
  --account-name vfisstorage \
  --name vfis-documents \
  --auth-mode login
```

### 1.5 Create App Service Plan

```bash
az appservice plan create \
  --resource-group vfis-rg \
  --name vfis-plan \
  --location eastus \
  --sku B1 \
  --is-linux
```

### 1.6 Create Web App

```bash
az webapp create \
  --resource-group vfis-rg \
  --plan vfis-plan \
  --name vfis-api \
  --runtime "PYTHON:3.10"
```

## Step 2: Configure Environment Variables

### 2.1 Get Database Connection String

```bash
DB_HOST=$(az postgres flexible-server show \
  --resource-group vfis-rg \
  --name vfis-postgres \
  --query fullyQualifiedDomainName -o tsv)

DB_CONNECTION_STRING="postgresql://vfisadmin:<PASSWORD>@${DB_HOST}:5432/postgres"
```

### 2.2 Get Blob Storage Connection String

```bash
BLOB_CONNECTION_STRING=$(az storage account show-connection-string \
  --resource-group vfis-rg \
  --name vfisstorage \
  --query connectionString -o tsv)
```

### 2.3 Set App Service Configuration

```bash
az webapp config appsettings set \
  --resource-group vfis-rg \
  --name vfis-api \
  --settings \
    DATABASE_URL="${DB_CONNECTION_STRING}" \
    AZURE_STORAGE_CONNECTION_STRING="${BLOB_CONNECTION_STRING}" \
    OPENAI_API_KEY="<YOUR_OPENAI_API_KEY>" \
    PORT=8000 \
    HOST=0.0.0.0 \
    CORS_ORIGINS="*" \
    PYTHON_ENABLE_WORKER_COUNT=1 \
    SCM_DO_BUILD_DURING_DEPLOYMENT=true
```

## Step 3: Deploy Application

### 3.1 Local Deployment (Azure CLI)

```bash
cd TradingAgents
az webapp up \
  --resource-group vfis-rg \
  --name vfis-api \
  --runtime "PYTHON:3.10" \
  --sku B1
```

### 3.2 Using GitHub Actions (Recommended)

Create `.github/workflows/azure-deploy.yml`:

```yaml
name: Deploy to Azure App Service

on:
  push:
    branches: [ main ]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v2
    
    - name: Set up Python
      uses: actions/setup-python@v2
      with:
        python-version: '3.10'
    
    - name: Install dependencies
      run: |
        pip install -r requirements.txt
    
    - name: Deploy to Azure
      uses: azure/webapps-deploy@v2
      with:
        app-name: vfis-api
        publish-profile: ${{ secrets.AZURE_WEBAPP_PUBLISH_PROFILE }}
        package: .
```

## Step 4: Configure Startup Command

Set the startup command in Azure Portal or via CLI:

```bash
az webapp config set \
  --resource-group vfis-rg \
  --name vfis-api \
  --startup-file "python -m vfis.api.app"
```

Or use `gunicorn` for production:

```bash
az webapp config set \
  --resource-group vfis-rg \
  --name vfis-api \
  --startup-file "gunicorn --bind 0.0.0.0:8000 --workers 2 --timeout 120 vfis.api.app:app"
```

## Step 5: Database Initialization

### 5.1 Initialize Database Schema

SSH into the App Service or run locally with database connection:

```bash
python -m vfis.scripts.init_database
```

### 5.2 Verify Database Connection

Test connectivity from App Service:

```bash
az webapp ssh --resource-group vfis-rg --name vfis-api
```

Then test database:

```python
from tradingagents.database.connection import get_db_connection
with get_db_connection() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT 1")
        print(cur.fetchone())
```

## Step 6: Health Checks

### 6.1 Configure Health Check Path

```bash
az webapp config set \
  --resource-group vfis-rg \
  --name vfis-api \
  --generic-configurations '{"healthCheckPath": "/health"}'
```

### 6.2 Test Health Endpoint

```bash
curl https://vfis-api.azurewebsites.net/health
```

Expected response:

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

## Step 7: Monitoring and Logging

### 7.1 Enable Application Insights

```bash
az monitor app-insights component create \
  --app vfis-insights \
  --location eastus \
  --resource-group vfis-rg

INSTRUMENTATION_KEY=$(az monitor app-insights component show \
  --app vfis-insights \
  --resource-group vfis-rg \
  --query instrumentationKey -o tsv)

az webapp config appsettings set \
  --resource-group vfis-rg \
  --name vfis-api \
  --settings APPINSIGHTS_INSTRUMENTATIONKEY="${INSTRUMENTATION_KEY}"
```

### 7.2 Enable Logging

```bash
az webapp log config \
  --resource-group vfis-rg \
  --name vfis-api \
  --application-logging filesystem \
  --detailed-error-messages true \
  --failed-request-tracing true \
  --web-server-logging filesystem
```

### 7.3 Stream Logs

```bash
az webapp log tail \
  --resource-group vfis-rg \
  --name vfis-api
```

## Step 8: Security Configuration

### 8.1 Configure HTTPS Only

```bash
az webapp update \
  --resource-group vfis-rg \
  --name vfis-api \
  --https-only true
```

### 8.2 Restrict Database Access

Configure PostgreSQL firewall to allow only App Service outbound IPs:

```bash
# Get App Service outbound IPs
az webapp show \
  --resource-group vfis-rg \
  --name vfis-api \
  --query outboundIpAddresses -o tsv

# Add firewall rule for App Service
az postgres flexible-server firewall-rule create \
  --resource-group vfis-rg \
  --name vfis-postgres \
  --rule-name AllowAppService \
  --start-ip-address <APP_SERVICE_IP> \
  --end-ip-address <APP_SERVICE_IP>
```

### 8.3 Use Azure Key Vault for Secrets (Recommended)

```bash
# Create Key Vault
az keyvault create \
  --resource-group vfis-rg \
  --name vfis-keyvault \
  --location eastus

# Store secrets
az keyvault secret set \
  --vault-name vfis-keyvault \
  --name DatabaseConnectionString \
  --value "${DB_CONNECTION_STRING}"

az keyvault secret set \
  --vault-name vfis-keyvault \
  --name OpenAIApiKey \
  --value "<YOUR_OPENAI_API_KEY>"

# Grant App Service access
az webapp identity assign \
  --resource-group vfis-rg \
  --name vfis-api

PRINCIPAL_ID=$(az webapp identity show \
  --resource-group vfis-rg \
  --name vfis-api \
  --query principalId -o tsv)

az keyvault set-policy \
  --name vfis-keyvault \
  --object-id "${PRINCIPAL_ID}" \
  --secret-permissions get list
```

## Step 9: Scaling Configuration

### 9.1 Configure Auto-scaling

```bash
az monitor autoscale create \
  --resource-group vfis-rg \
  --resource /subscriptions/<SUB_ID>/resourceGroups/vfis-rg/providers/Microsoft.Web/serverfarms/vfis-plan \
  --name vfis-autoscale \
  --min-count 1 \
  --max-count 3 \
  --count 1
```

### 9.2 Configure Scale-out Rules

```bash
az monitor autoscale rule create \
  --resource-group vfis-rg \
  --autoscale-name vfis-autoscale \
  --condition "Percentage CPU > 70 avg 5m" \
  --scale out 1
```

## Step 10: Backup Configuration

### 10.1 Enable Database Backups

```bash
az postgres flexible-server backup create \
  --resource-group vfis-rg \
  --server-name vfis-postgres \
  --backup-name daily-backup \
  --backup-retention 7
```

## Troubleshooting

### Common Issues

1. **Database Connection Failures**
   - Check firewall rules
   - Verify connection string format
   - Check SSL requirements

2. **Startup Errors**
   - Check startup command
   - Verify Python version
   - Review application logs

3. **Import Errors**
   - Verify requirements.txt
   - Check PYTHONPATH
   - Ensure all dependencies are installed

### Useful Commands

```bash
# View application logs
az webapp log tail --resource-group vfis-rg --name vfis-api

# SSH into App Service
az webapp ssh --resource-group vfis-rg --name vfis-api

# Restart App Service
az webapp restart --resource-group vfis-rg --name vfis-api

# View application settings
az webapp config appsettings list --resource-group vfis-rg --name vfis-api
```

## Requirements Verification

Ensure `requirements.txt` includes:

```
fastapi>=0.104.0
uvicorn[standard]>=0.24.0
pydantic>=2.0.0
python-dotenv>=1.0.0
psycopg2-binary>=2.9.0
azure-storage-blob>=12.19.0
langchain-openai>=0.0.2
langchain-core>=0.1.0
pandas>=2.0.0
numpy>=1.24.0
```

For production, also consider:

```
gunicorn>=21.2.0
```

## Next Steps

1. Set up n8n workflows for daily ingestion
2. Configure monitoring alerts
3. Set up automated testing
4. Configure CI/CD pipeline
5. Document API endpoints
6. Set up staging environment

