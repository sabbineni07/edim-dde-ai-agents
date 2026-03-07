# EDIM DDE AI Agents

AI-powered cluster configuration recommendations. Supports local CSV data or Databricks.

## Quick start

```bash
cp .env.example .env   # edit with your values
docker compose up -d
```

API: http://localhost:8000

## Endpoints

- `GET /api/health/` – Health check
- `GET /api/health/ready` – Readiness
- `POST /api/recommendations/generate` – Generate recommendation (body: `job_id`, `start_date`, `end_date`)

## Local mode

Set `USE_LOCAL_DATA=true` and `LOCAL_DATA_PATH=/app/data/sample_job_metrics.csv` (or `sample.csv`). Uses mock LLM if Azure OpenAI is not configured.
