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

Tracked in detail in [BACKLOG_REFACTOR.md](./BACKLOG_REFACTOR.md) **Phase 5** (refined for Phases 6–9).

- [x] **Phase 5.0** — List job runs API; fix recommendation history `workspace_id`
- [x] **Phase 5.1 (core)** — Run-centric UI: agent/profile pickers, Phase 6 response panels, per-run recommend
- [ ] **Phase 5.2** — Agents screen: profile CRUD (Phase 9 backend done)
- [x] **Phase 5.3 (partial)** — History with `job_run_id`; API vs lifecycle badges
- [x] **Phase 5.4** — Adoption lifecycle: RECOMMENDED → … → APPROVED + audit UI/API
- [ ] **Phase 5.5** — RAG by `job_run_id`
- [ ] **Phase 5.6** — Ops docs (batch metrics vs on-demand LLM)
- [x] **Pipeline transparency (Phase 6)** — see [recommendation-pipeline.md](./recommendation-pipeline.md)
- [x] **Multi-agent layout (Phase 7)** — see [architecture.md](./architecture.md)
- [x] **YAML settings (Phase 8)** — see [configuration.md](./configuration.md)
- [x] **Agent profiles API (Phase 9 backend)** — `/api/agent-profiles`, `agent_id` + `profile_id` on recommend
- [ ] **Drop `cluster_config` agent alias** — UI defaults to `job_run_cluster_sizing` (Phase 5.7)
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

*Last updated: Phase 5.4 adoption lifecycle implemented.*
