# Approve-only RAG validation (Windows laptop, end-to-end)

Step-by-step guide to validate **FAISS approve-only indexing** on a Windows dev machine:

- Postgres in Docker
- API (`uvicorn`) on the host
- UI (`npm start`) on the host
- Local CSV metrics (`USE_LOCAL_DATA=true`) — no Databricks required

## What you are validating

| Behavior | Expected |
|----------|----------|
| Generate recommendation | **Does not** write to FAISS or Azure AI Search |
| RAG during sizing | **Only** when workspace agent has a **Knowledge search** binding (`faiss` or `ai_search`) |
| Lifecycle → **Approved** | Indexes one document (`config_quality: approved`) |
| FAISS read path | Loads index once per path; reloads after approve (mtime cache) |
| Stored ingest | `job_run_ingest` saved on the recommendation row for richer index text |

---

## 0. Prerequisites

- Git clone of this repo on Windows (example: `C:\Users\<you>\projects\edim-dde-ai-agents`)
- Docker Desktop (for Postgres only)
- Python 3.11+ and Node.js 18+ (for local API + UI)
- **Azure OpenAI** with a chat deployment **and** an embedding deployment (`text-embedding-3-small` or similar)  
  FAISS indexing on approve calls embeddings; `USE_MOCK_LLM=true` is **not** enough for the indexing step.

Pull the latest code that includes approve-only RAG:

```powershell
cd C:\Users\<you>\projects\edim-dde-ai-agents
git pull
```

---

## 1. One-time setup

### 1.1 Python virtual environment

```powershell
cd C:\Users\<you>\projects\edim-dde-ai-agents
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install -r requirements.txt
```

### 1.2 Configure `.env` (host API)

Copy and edit:

```powershell
copy .env.example .env
notepad .env
```

Minimum for this runbook:

```ini
# Local metrics (no Databricks)
USE_LOCAL_DATA=true
LOCAL_DATA_PATH=data/sample_job_metrics.csv

# Postgres in Docker — host connects via localhost
USE_POSTGRES=true
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_DATABASE=ai_agents

# Real LLM + embeddings (required for FAISS indexing on approve)
USE_MOCK_LLM=false
AZURE_OPENAI_ENDPOINT=https://<your-resource>.openai.azure.com
AZURE_OPENAI_API_KEY=<your-key>
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4o
AZURE_OPENAI_EMBEDDING_DEPLOYMENT=text-embedding-3-small

# Optional global default; workspace FAISS connection overrides this
FAISS_INDEX_PATH=C:/Users/<you>/projects/edim-dde-ai-agents/data/faiss_index

ADMIN_USERNAMES=admin
CONFIG_DIR=config
```

Use **forward slashes** in `FAISS_INDEX_PATH` (Python on Windows accepts them).

Do **not** set `VECTOR_RETRIEVAL_BACKEND=azure_search` globally unless you are testing Search; workspace agent bindings control RAG per install.

### 1.3 Create an empty FAISS folder

```powershell
mkdir data\faiss_index -Force
# Folder should be empty before first test
dir data\faiss_index
```

### 1.4 Start Postgres and migrate schema

```powershell
docker compose up -d postgres
$env:PYTHONPATH = (Get-Location).Path
$env:USE_POSTGRES = "true"
python scripts\migrate-db.py
```

Expected: `Database migration completed successfully`

### 1.5 Start API (host)

In a **new** terminal:

```powershell
cd C:\Users\<you>\projects\edim-dde-ai-agents
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH = (Get-Location).Path
$env:USE_POSTGRES = "true"
python -m uvicorn API.src.main:app --host 0.0.0.0 --port 8000 --reload
```

Smoke check:

```powershell
curl http://localhost:8000/api/health/
```

### 1.6 Start UI (host)

In another terminal:

```powershell
cd C:\Users\<you>\projects\edim-dde-ai-agents\UI
npm install
npm start
```

Open http://localhost:4200 — API calls proxy to `http://localhost:8000` via `UI/proxy.conf.json`.

---

## 2. UI wiring (connections + workspace agent)

### 2.1 Login

1. Open http://localhost:4200/login  
2. Sign in as **`admin`** (any password — dev auth is username-only).

### 2.2 Select environment

In the shell header, choose **`Local`** (`environment_id: local`).

### 2.3 Workspace Setup → Connections

Open **Sample Production Workspace** (`workspace_id` `1234567890123456` in sample CSV) → **Setup** → **Connections**.

Create three connections:

| Name | Type | Key fields |
|------|------|------------|
| `local-metrics` | **Local dataset** | Path: `data/sample_job_metrics.csv` |
| `foundry-llm` | **AI Foundry / Azure OpenAI** | Endpoint, deployment name (`gpt-4o`), API key if not using `az login` |
| `local-faiss` | **FAISS (local index)** | Index path: `C:/Users/<you>/projects/edim-dde-ai-agents/data/faiss_index` |

Save each connection.

### 2.4 Workspace Setup → Agents

1. **Add agent** → `dbx_cluster_tuning_agent`
2. Bind:
   - **Metrics** → `local-metrics`
   - **LLM** → `foundry-llm`
   - **Knowledge search** → `local-faiss`
3. **Install** the agent and note the **workspace agent id** (UUID) from the UI or API.

### 2.5 Negative control (optional)

Install a second agent on the same workspace **without** a Knowledge search binding (metrics + LLM only). Use it in **Test 3** to confirm RAG stays off.

---

## 3. Test 1 — Generate does **not** index

### 3.1 Browse jobs

1. **Workspaces** → **Sample Production Workspace**
2. Date range: **`2026-06-01`** to **`2026-06-03`** (matches `data/sample_job_metrics.csv`)
3. Open **job-001** → select run **`jr-001-001`** (cluster `run-001-001`)

### 3.2 Generate recommendation

1. In the **Workspace agent** dropdown, select the agent **with FAISS** bound.
2. Click **Recommend**.
3. Wait for the recommendation card (status **Recommended**).

### 3.3 Verify — no index files yet

```powershell
dir C:\Users\<you>\projects\edim-dde-ai-agents\data\faiss_index
```

**Pass:** folder still empty (no `index.faiss`, no `index.pkl`).

### 3.4 Verify — API logs

In the API terminal, confirm you **do not** see:

- `indexed_approved_recommendation`
- `approved_indexing_faiss_complete`
- `faiss_index_appended`

You **may** see `rag_context_provider_ready` with `backend=faiss` if the index already existed from a prior run; on a fresh empty folder, FAISS RAG load may log `rag_faiss_load_failed` until the first approved doc exists — that is expected.

### 3.5 Verify — ingest stored in Postgres

```powershell
docker exec -it edim-dde-ai-agents-postgres psql -U postgres -d ai_agents -c ^
  "SELECT request_id, lifecycle_status, (recommendation->'job_run_ingest') IS NOT NULL AS has_ingest FROM recommendations_history ORDER BY created_at DESC LIMIT 3;"
```

**Pass:** latest row has `lifecycle_status = RECOMMENDED` and `has_ingest = t`.

Copy the `request_id` (UUID) — you need it for lifecycle steps.

---

## 4. Test 2 — Lifecycle to **Approved** indexes FAISS

Adoption path (UI enforces allowed transitions):

```text
RECOMMENDED → ACCEPTED → DEPLOYED → MONITORING_AND_VALIDATION → APPROVED
```

### 4.1 Advance in the UI

On the job detail page, under **Adoption lifecycle** for your recommendation:

1. Move to **Accepted** → Update  
2. **Deployed** → Update  
3. **Monitoring and validation** → Update  
4. **Approved** → Update  

You must be signed in (same `admin` session).

### 4.2 Verify — FAISS files created

```powershell
dir C:\Users\<you>\projects\edim-dde-ai-agents\data\faiss_index
```

**Pass:** `index.faiss` and `index.pkl` (and related files) appear **after** the final **Approved** step, not before.

### 4.3 Verify — API logs

After **Approved**, the API terminal should show something like:

```text
approved_indexing_faiss_complete ... path=...
faiss_index_appended ...
recommendation_lifecycle_transition ... to_status=APPROVED
```

### 4.4 Verify — database lifecycle

```powershell
docker exec -it edim-dde-ai-agents-postgres psql -U postgres -d ai_agents -c ^
  "SELECT lifecycle_status, lifecycle_updated_by FROM recommendations_history WHERE request_id = '<your-request-id>';"
```

**Pass:** `lifecycle_status = APPROVED`.

### 4.5 Verify — lifecycle audit API (optional)

```powershell
curl http://localhost:8000/api/recommendations/<your-request-id>/lifecycle/events
```

**Pass:** five events ending with `to_status: "APPROVED"`.

---

## 5. Test 3 — RAG uses approved index on next recommendation

### 5.1 Second generate (same workspace agent with FAISS)

1. Same workspace / job / date range.
2. Pick another run (e.g. **`jr-001-002`**) or re-run on the same run.
3. Generate with the **FAISS-bound** workspace agent.

### 5.2 Verify — RAG loaded from cache

API logs should include:

```text
rag_context_provider_ready ... backend=faiss ...
```

On the second recommend in the same API process, you should **not** see repeated `faiss_cache_loaded` / disk load spam for every request (cache hit after first load).

### 5.3 Verify — second recommendation not indexed until approved

```powershell
# Note file count / last write time before approving second rec
dir C:\Users\<you>\projects\edim-dde-ai-agents\data\faiss_index
```

Generate second recommendation → **Pass:** index mtime unchanged until you approve the second `request_id`.

After approving the second recommendation → **Pass:** index updates again (`faiss_index_appended` in logs).

---

## 6. Test 4 — RAG off without Knowledge search binding

1. Generate using the workspace agent **without** a `rag` binding (or omit `workspace_agent_id` in API calls).
2. **Pass:** API logs show `rag_context_provider_disabled` or `vector_retrieval_backend: none`.
3. Approve that recommendation → **Pass:** no new FAISS files / `approved_indexing_skipped` with `rag_disabled_or_unbound`.

### API-only negative check

```powershell
curl -X POST http://localhost:8000/api/recommendations/generate ^
  -H "Content-Type: application/json" ^
  -H "X-User-Name: admin" ^
  -d "{\"agent_id\":\"dbx_cluster_tuning_agent\",\"environment_id\":\"local\",\"job_id\":\"job-001\",\"cluster_id\":\"run-001-001\",\"job_run_id\":\"jr-001-001\",\"start_date\":\"2026-06-01\",\"end_date\":\"2026-06-03\"}"
```

**Pass:** recommendation succeeds; no indexing until lifecycle approve with a rag-bound agent on the original generate (indexing resolves settings from `request_logs.request_params.workspace_agent_id`).

---

## 7. Backfill script (optional)

Re-index all approved rows into FAISS (e.g. after deleting the index folder):

```powershell
cd C:\Users\<you>\projects\edim-dde-ai-agents
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH = (Get-Location).Path
$env:USE_POSTGRES = "true"
$env:FAISS_INDEX_PATH = "C:/Users/<you>/projects/edim-dde-ai-agents/data/faiss_index"
python scripts\build_faiss_index.py --all-approved
```

**Pass:** prints `indexed <uuid>` for each approved row; `index.faiss` exists.

Single row:

```powershell
python scripts\build_faiss_index.py --request-id <uuid>
```

---

## 8. Lifecycle via API (alternative to UI)

If the UI lifecycle controls are awkward, drive transitions with curl (replace UUID and step through allowed states):

```powershell
curl -X PATCH http://localhost:8000/api/recommendations/<request-id>/lifecycle ^
  -H "Content-Type: application/json" ^
  -H "X-User-Name: admin" ^
  -d "{\"status\":\"ACCEPTED\",\"notes\":\"validation\"}"
```

Repeat for `DEPLOYED`, `MONITORING_AND_VALIDATION`, then `APPROVED`.

---

## 9. Troubleshooting

| Symptom | Likely cause | Fix |
|---------|----------------|-----|
| Workspaces empty | Wrong date range | Use **2026-06-01** – **2026-06-03** for sample CSV |
| `approved_indexing_embeddings_failed` | No embedding deployment / key | Set `AZURE_OPENAI_EMBEDDING_DEPLOYMENT` and credentials |
| `approved_indexing_faiss_missing_path` | Bad path in FAISS connection | Use absolute Windows path with forward slashes |
| `rag_faiss_load_failed` before any approve | Empty index folder | Expected until first **Approved** recommendation |
| Lifecycle update blocked | Skipped a step | Follow RECOMMENDED → … → APPROVED order |
| Index never updates on approve | Agent had no `rag` binding at generate time | Regenerate with FAISS-bound workspace agent, then approve |
| API cannot reach Postgres | Docker not running | `docker compose up -d postgres` |
| UI cannot reach API | Wrong port | API on **8000**, UI proxy in `proxy.conf.json` |

### Reset FAISS index for a clean rerun

```powershell
Remove-Item C:\Users\<you>\projects\edim-dde-ai-agents\data\faiss_index\* -Force
```

Restart the API process to clear the in-memory FAISS cache.

---

## 10. Pass / fail checklist

- [ ] **Generate** does not create `index.faiss` / `index.pkl`
- [ ] `recommendations_history` row has `job_run_ingest` after generate
- [ ] **Approved** creates/updates FAISS index files
- [ ] API logs `approved_indexing_faiss_complete` on approve
- [ ] Second recommendation uses FAISS RAG after at least one approved doc
- [ ] Second generate does **not** append to index until its own **Approved**
- [ ] Agent without Knowledge search binding keeps RAG off
- [ ] `scripts/build_faiss_index.py --all-approved` backfills successfully

---

## Related docs

- [VALIDATION_RUNBOOK.md](./VALIDATION_RUNBOOK.md) — general smoke tests  
- [configuration.md](./configuration.md) — YAML + env precedence  
- [recommendation-pipeline.md](./recommendation-pipeline.md) — agent flow overview
