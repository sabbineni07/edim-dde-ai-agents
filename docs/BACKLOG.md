# Backlog — action items

Captured from product and engineering discussions. Not committed to priority or sprint; adjust as needed.

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

- [ ] **Azure AI Search endpoint** — Confirm `AZURE_SEARCH_ENDPOINT` uses the Search resource hostname (`*.search.windows.net`); do not use `cognitiveservices.azure.com` as a drop-in for `SearchClient`.
- [ ] **Foundry project API** — If required, design a separate integration for `services.ai.azure.com/.../projects/...` (not the same as raw `openai.azure.com` chat path used by LangChain today).

---

## Product / UX

Tracked in detail in [BACKLOG_REFACTOR.md](./BACKLOG_REFACTOR.md) **Phase 5**.

- [x] **Phase 5.0–5.1** — Run-centric UI, structured recommend response
- [x] **Phase 5.2** — Agents screen + profile CRUD
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

---

## Optional / nice-to-have

- [ ] **LangSmith / callbacks** — Structured tracing for chains and graph nodes (today token tracking is estimate-based).
- [ ] **Tests** — Extend coverage for inclusive `end_date` in local collector vs listing APIs.

---

*Last updated: Phase 5.2–5.6 and UI polish implemented.*
