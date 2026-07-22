# Backlog — action items

Captured from product and engineering discussions. Not committed to priority or sprint; adjust as needed.

**Platform data model (connections → datasets):** see [BACKLOG_CONNECTIONS_AND_DATASETS.md](./BACKLOG_CONNECTIONS_AND_DATASETS.md) for phased design, flows, and checkboxes (Phases 0–5 done; Phase 6 pending). **Manage environments admin UX** (hide Source/Readiness, setup summary) tracked in §6.4.

**AI Foundry / LangChain upgrade:** see [BACKLOG_AI_FOUNDRY_UPGRADE.md](./BACKLOG_AI_FOUNDRY_UPGRADE.md) for phased design, diagrams, and progress (Phases 0–7 not started).

---

## AI platform & data (Postgres-first)

- [ ] **Persisted session / agent state** — Today `RecommendationState` lives only for one `ainvoke`; add optional checkpoints (e.g. Postgres `JSONB`) if multi-step or resume flows are needed.
- [ ] **Conversation memory** — No LangChain chat memory today; define if chat or recommendations need multi-turn threads and where to store (`JSONB` sessions vs external store).
- [ ] **RAG provenance** — Log or store retrieval metadata: source doc id, version, chunk id, and search scores (today vector results are not persisted in Postgres).
- [ ] **Human feedback** — Wire `update_recommendation_quality` (and/or Postgres) to APIs + UI: thumbs, quality labels, optional `feedback_data` (savings, performance).
- [ ] **Evaluation runs** — Datasets, regression runs, judge/LLM-as-judge scores, A/B flags; schema and pipeline TBD.
- [ ] **Cosmos DB revisit** — Stay on Postgres + Search until triggers (global scale, Mongo API mandate, write patterns) are explicit; document the decision.

---

## Azure & Foundry alignment

- [x] **AI Foundry LLM upgrade (v1 API)** — Done. See [BACKLOG_AI_FOUNDRY_UPGRADE.md](./BACKLOG_AI_FOUNDRY_UPGRADE.md).
- [ ] **Azure AI Search endpoint** — Confirm `AZURE_SEARCH_ENDPOINT` uses the Search resource hostname (`*.search.windows.net`); do not use `cognitiveservices.azure.com` as a drop-in for `SearchClient`.
- [ ] **Foundry project API** — If required, design a separate integration for `services.ai.azure.com/.../projects/...` via `langchain-azure-ai` (deferred; see upgrade backlog §7).

---

## Product / UX

**UI/UX modernization (Options A → B → C):** see [BACKLOG_UI_UX_MODERNIZATION.md](./BACKLOG_UI_UX_MODERNIZATION.md) — **Option A complete (Phases 1–4)**; evaluation recommends staying on Bootstrap + shared components ([UI_COMPONENT_LIBRARY_EVALUATION.md](./UI_COMPONENT_LIBRARY_EVALUATION.md)); Option B/C deferred/skipped.

Tracked in detail in [BACKLOG_REFACTOR.md](./BACKLOG_REFACTOR.md) **Phase 5**.

- [x] **Phase 5.0–5.1** — Run-centric UI, structured recommend response
- [x] **Phase 5.2** — Agents catalog + workspace agent install
- [x] **Phase 5.2b** — Agent prompts/skills store + admin UI — see [BACKLOG_AGENT_PROMPTS.md](./BACKLOG_AGENT_PROMPTS.md) (Phases 1–3 done)
- [x] **Phase 5.3** — History with comparison, cost, lifecycle
- [x] **Phase 5.4** — Adoption lifecycle
- [x] **Phase 5.5 (backend)** — RAG index includes `job_run_id`
- [x] **Phase 5.6** — Ops docs ([ops-batch-metrics-vs-llm.md](./ops-batch-metrics-vs-llm.md), [VALIDATION_RUNBOOK.md](./VALIDATION_RUNBOOK.md))
- [x] **Phase 10.8–10.9** — Workspace connections + agents UI; job detail uses `workspace_agent_id`
- [ ] **Phase 5.5.2** — RAG provenance in UI (optional)
- [ ] **Phase 5.7.1** — Chat scope polish
- [x] **Pipeline / architecture / config / profiles API** — Phases 6–9 backend
- [ ] **Enable cost retry in prod** — after measuring guardrail adjustment rate

---

## DevOps & quality

- [ ] **Secrets hygiene** — Rotate any credentials that appeared in local `.env` or logs; keep `.env` out of images and VCS.
- [ ] **Docker `env_file`** — After Compose changes, recreate `api` so host `.env` (incl. Search) is loaded; verify `POSTGRES_HOST` override for `postgres` service.
- [ ] **500 troubleshooting** — Use `logger.exception` on recommendation errors and check response `detail`; confirm Azure OpenAI deployment names match the resource.
- [ ] **Remove temporary SQL executor** — Admin-only ad-hoc Postgres console added for debugging. Delete: `API/src/routes/temp_sql_executor.py`, its import/`include_router` in `API/src/main.py`, UI folder `UI/src/app/features/temp-sql-executor/`, route `temp/sql` in `app.routes.ts`, and the shell account-menu link (`openTempSqlExecutor` + CONTEXT_BAR hide).

---

## Optional / nice-to-have

- [ ] **LangSmith / callbacks** — Structured tracing for chains and graph nodes (today token tracking is estimate-based).
- [ ] **Tests** — Extend coverage for inclusive `end_date` in local collector vs listing APIs.

---

## Spark Job Failure RCA — quality improvements (revisit)

Captured 2026-07-21 from post-run review (schema-mismatch failure: rich `summary`, empty `recommended_actions` / `contributing_factors`, category `unknown`, low confidence).

**Context:** Agent receives a bounded evidence pack (filtered Delta `spark_logs` / `spark_metrics` by event type / severity), not full logs. `spark_metrics` can include SQL/plan attributes (`sql_text`, `physical_plan`, etc.). Prompt bias was “cite evidence, don’t invent,” which left action/factor lists empty when uncertain.

### Done (2026-07-21) — prompts + skills refine
- [x] **Prompts** — Diagnostic order; confidence bands; mandatory non-empty `contributing_factors` / `recommended_actions` when summary present; investigatory checks allowed at low confidence (`shared/config/agent_content_seed.py`).
- [x] **Skills** — Added workflow, resource/OOM, skew/shuffle, plan operators, Delta concurrency, thin-evidence (no dedicated schema A−B skill).
- [x] **Runtime** — RCA chain now appends active skills to the system message (`AI/src/core/prompts/loader.py`).
- [x] **Reset** — `reset_to_seed` inserts missing seed skills so new skill keys appear on existing DBs.

**Apply locally:** reset Spark RCA agent content to seed (Agents UI → Reset, or API `POST /api/agents/spark_job_rca_agent/content/reset`), then restart API so the chain reloads prompts.

### Done (2026-07-21) — collector section fetches + pack enrichment
- [x] **Three section fetches** — `fetch_logs` / `fetch_stage_metrics` / `fetch_sql_plans` on Databricks + local collectors; `build_evidence_pack_for_run` assembles one pack.
- [x] **Evidence pack enrichment** — First-class `sections` (`logs` / `stage_metrics` / `sql_plans`); preserve truncated `sql_text` / `physical_plan` / related attrs; spill fields on stage excerpts; human prompt prefers `pack.sections`.

### Still pending
- [ ] **Validation backfill** — If LLM still returns empty actions/factors, derive fallbacks in `validate_rca_llm_output`.
- [ ] **Last-success comparison** — Attach last successful run evidence (or compact success-vs-fail diff) for drift/regression cases.
- [ ] **UI** — Always show Recommended actions / Contributing factors (even if empty/low-confidence); distinguish hypotheses vs findings.
- [ ] **Schema A−B (optional / deferred)** — Explicit expected-vs-actual column set-diff skill; not required for current refine.

**Suggested next pickup:** validation backfill → last-success / UI.

---

*Last updated: 2026-07-21 — RCA collector sections + pack SQL/plan enrichment done; schema A−B deferred.*
