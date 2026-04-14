# Release v2.0.0 — Google Workspace MCP Server

**Date:** 2026-04-14
**Branch:** `reaserch_trm_mw` -> `feat/chat-space-admin-and-payment-402`
**Commits:** 46

---

## Highlights

This is a major release marking the maturation of the **Universal Module Wrapper** framework, **TRM learned scoring**, and **production hardening** across the full 96-tool surface. The jump from v1.11.0 to v2.0.0 reflects the scope of architectural change: graceful degradation, a new mixin-based wrapper architecture, and a deployed neural scorer.

---

## What's New

### Graceful Degradation
- Server starts and registers all **96 tools** even when Qdrant or embedding services are unavailable
- `ModuleWrapper` enters degraded mode: in-memory introspection works, vector search returns empty results
- Lazy reconnection automatically recovers when services come back online

### TRM Learned Scorer (UnifiedTRN)
- 28.7K-parameter network with 4 task heads (form, content, pool, halt) deployed in card builder slot assignment
- V5 features: 17D structural + 384D content vectors
- 100% validation accuracy on the Module Wrapper domain
- Domain onboarding pipeline for expanding to new wrapped modules

### Module Wrapper Expansion
- 13 composable mixins with explicit dependency contracts (`_MIXIN_PROVIDES` / `_MIXIN_REQUIRES`)
- 3 production domains: Google Chat cards, Gmail MJML email, Qdrant models
- RIC 3-vector schema (ColBERT 128D + MiniLM 384D) with Reciprocal Rank Fusion search
- Auto-generated skills and DSL documentation per wrapped domain

### Langfuse Observability
- OTel-based tracing for both LiteLLM and Anthropic sampling paths
- `ContextVar`-based trace context propagating tool name, template, phase, enhancement level
- Generation naming: `mcp::{tool_name}::{phase}::step{n}`

### Model Artifact Management
- GCS-backed model artifact storage with local caching
- Monthly budget enforcement for cloud operations

---

## Bug Fixes

### Stale Sandbox Argument Leakage (Critical)
- **File:** `middleware/sampling_middleware.py`
- Argument recovery middleware was mutating `context.message.arguments` in-place (`.clear()/.update()`), causing args from prior tool calls to leak into subsequent calls within the same sandbox session
- **Fix:** Changed to dict reassignment — no more cross-call contamination

### Forms Resource List Tool
- `list_tool` for `forms/form_responses` resource set to `None` (requires `form_id`, cannot list generically)

### Dashboard Tool Tracker
- Cleared stale dashboard tool tracker before execution to prevent data leakage between calls

### Gmail Body Extraction
- Added fallback for extracting HTML body to plain text when structured extraction fails

---

## Developer Experience

### Tool Documentation Alignment
- `send_dynamic_card` now uses `UserGoogleEmail = None` (middleware auto-injects)
- All hardcoded Unicode symbols in skill templates converted to dynamic `wrapper.symbol_mapping` lookups
- Parameter tables updated with `user_google_email` guidance

### FastMCP 3.2.4 Upgrade
- Security fixes: FileUpload validation, header forwarding
- Task auth scoping improvements
- Gemini compatibility

### Code Quality
- All E741/E731 lint errors fixed across research and diagnostic-ui code
- Entire codebase formatted with `ruff format`
- Import sorting standardized with `ruff check --select I`

---

## Test Results

| Suite | Result |
|-------|--------|
| Module unit tests | 480 passed, 28 skipped, 0 failed |
| Client tests | 21 passed, 1 pre-existing failure |
| Live server validation | `send_dynamic_card` and `compose_dynamic_email` succeed |
| Degraded mode | Server starts and 96 tools register with Qdrant down |
| Lint | `ruff check` passes clean |
| Format | `ruff format --check` passes clean |

---

## Breaking Changes

None. `UserGoogleEmail` parameter change is backwards-compatible (`Optional` with `default=None`).

---

## Upgrade Notes

```bash
# Pull the latest
git pull origin feat/chat-space-admin-and-payment-402

# Sync dependencies (FastMCP 3.2.4)
uv sync

# Verify
uv run ruff check .
uv run ruff format --check .
uv run pytest tests/module/
```
