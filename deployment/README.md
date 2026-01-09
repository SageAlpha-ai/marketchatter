# VFIS Deployment Documentation

This directory contains deployment documentation and configurations for the Verified Financial Intelligence System (VFIS).

## Contents

- `azure_app_service.md`: Complete guide for deploying VFIS to Azure App Service
- `n8n/`: n8n workflow JSON exports for orchestration

## Quick Start

1. **Azure Deployment**: See [azure_app_service.md](./azure_app_service.md)
2. **n8n Setup**: Import workflows from `n8n/workflows/` directory
3. **Environment Variables**: Configure via Azure App Service Configuration

## Architecture

```
┌─────────────┐      ┌──────────────┐      ┌─────────────┐
│   n8n       │──────│  FastAPI API │──────│ PostgreSQL  │
│ Workflows   │      │  (App Service)│     │  Flexible   │
└─────────────┘      └──────────────┘      └─────────────┘
                            │
                            │
                     ┌──────▼──────┐
                     │ Azure Blob  │
                     │  Storage    │
                     └─────────────┘
```

## Deployment Checklist

- [ ] Azure resources created (App Service, PostgreSQL, Blob Storage)
- [ ] Environment variables configured
- [ ] Database initialized
- [ ] Application deployed
- [ ] Health checks passing
- [ ] Monitoring configured
- [ ] n8n workflows imported
- [ ] Security configured (HTTPS, firewall rules)
- [ ] Backups enabled

## Support

For deployment issues, check:
1. Application logs: `az webapp log tail`
2. Health endpoint: `https://your-api.azurewebsites.net/health`
3. Database connectivity tests
4. Environment variable configuration

