# PR #37 Merge Comment

## v2.0.0 — Module Wrapper Maturation + Production Hardening

**46 commits** spanning TRM research, module wrapper improvements, and server hardening.

### Summary

- **Graceful degradation** — Server starts with all 96 tools even when Qdrant/embeddings are down. Lazy reconnection recovers automatically.
- **Stale arg fix** — Sandbox argument leakage between sequential tool calls eliminated (dict reassignment instead of in-place mutation).
- **TRM UnifiedTRN deployed** — 28.7K-param learned scorer with 4 task heads, 100% validation accuracy on MW domain.
- **Langfuse tracing** — OTel-based observability for LiteLLM + Anthropic paths with full context propagation.
- **FastMCP 3.2.4** — Security fixes, task auth scoping, Gemini compatibility.
- **Tool docs aligned** — `UserGoogleEmail` default=None, dynamic symbol mappings, updated parameter tables.
- **Code quality** — All lint errors fixed, full codebase formatted with ruff.

### Validation

| Check | Status |
|-------|--------|
| `ruff check .` | Pass |
| `ruff format --check .` | Pass |
| Module tests (480) | Pass |
| Client tests (21) | Pass |
| Live tool calls | Pass |
| Degraded mode startup | Pass |
| 96 tools registered | Pass |

### No Breaking Changes

`UserGoogleEmail` is `Optional` with `default=None` — fully backwards-compatible.

---

Full release notes: [`docs/RELEASE_v2.0.0.md`](docs/RELEASE_v2.0.0.md)
