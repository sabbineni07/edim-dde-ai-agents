# Design Optimization Backlog

Design optimizations to consider for scalability, performance, and best practices. Review before major changes.

---

## Scalability

1. **Sync I/O in async handlers** – Async endpoints call sync DB code (e.g. `cost_analytics`), blocking the event loop under load. Options: wrap with `asyncio.to_thread()` / `run_in_executor`, or adopt async SQLAlchemy (`asyncpg`) and async sessions.
2. **Sync chains in LangGraph** – Chains (pattern, cost, explanation) are synchronous. LangGraph runs them in a thread pool, but under heavy load many concurrent requests will saturate threads.
3. **Horizontal scaling** – API is stateless (good). Docker runs a single uvicorn process. Consider `--workers N` or multiple replicas behind a load balancer.
4. **Database session lifecycle** – `get_cost_summary` creates its own session. Prefer DI with request-scoped sessions for consistency and pooling.

---

## Performance

5. **Chain instantiation** – Verify no per-request chain recreation (currently cached via agent; keep that).
6. **Azure Search** – Sync `SearchClient`. For high RAG volume, consider async search or offload to a thread pool.
7. **LLM timeouts** – No explicit timeout on Azure OpenAI calls. Long-running calls can hold resources. Add configurable timeouts.
8. **Response caching** – Same `job_id` + date range can return identical recommendations. Add caching (in-memory, Redis, or DB) with TTL.
9. **Cost analytics DI** – `cost_logger = ObservabilityService()` is module-level. Switch to FastAPI DI for consistency and testability.

---

## Best Practices

10. **CORS** – `allow_origins=["*"]` with `allow_credentials=True` is unsafe for production. Use explicit origins or env-based config.
11. **Health checks** – `/health` and `/ready` are trivial. Add optional dependency checks (DB, Azure OpenAI, Azure Search) with timeouts.
12. **Rate limiting** – No throttling. Add rate limiting (slowapi, nginx, or API gateway) for production.
13. **Input validation** – Add request limits (date range, job_id length, payload size) to avoid unbounded queries.
14. **Circuit breaker** – No circuit breaker for external services. Consider fast-fail when Azure OpenAI or Search are down.
15. **Structured errors** – Some routes catch broad `Exception`. Use domain exceptions and map to consistent error responses with error codes.
16. **OpenTelemetry** – `azure-monitor-opentelemetry` is in requirements. Ensure tracing is configured for production observability (request latency, LLM calls, DB queries).

---

## Priority Summary

| Area | High impact | Medium impact |
|------|-------------|---------------|
| **Scalability** | Wrap sync I/O or adopt async DB | Add workers / horizontal scaling |
| **Performance** | LLM timeouts, response caching | Consistent DB session handling |
| **Best practices** | CORS, rate limiting, readiness checks | Circuit breaker, structured errors, observability |
