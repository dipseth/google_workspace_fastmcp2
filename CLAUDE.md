# Google Workspace MCP Server

@AGENTS.md

## Project Identity

FastMCP server (`google-workspace-unlimited` v1.11.0) providing 72+ tools across 9 Google Workspace services: Gmail, Drive, Docs, Sheets, Slides, Calendar, Forms, Chat, Photos (+ People API).

This server is the proving ground for **universal module wrapping** — the Module Wrapper framework and TRM learning layer described in AGENTS.md are built here, tested against real Google APIs, and iterated on in production. The Google Workspace tools are both the product and the test bed.

**Stack:** Python 3.11-3.12, FastMCP 3.1+, Pydantic v2, Qdrant (vector search), LiteLLM (multi-provider LLM), Langfuse (observability), x402 (stablecoin payments), Jinja2 (templates).

## Quick Start

```bash
# Install dependencies
uv sync

# Copy and configure environment
cp .env.example .env  # then edit with your Google OAuth credentials

# Run in development mode (hot reload)
uv run fastmcp dev

# Run the server directly
uv run python server.py

# Run tests (requires MCP server running)
uv run pytest tests/client/
```

## Development Commands

```bash
# Lint
uv run ruff check .

# Format
uv run black .

# Test (all)
uv run pytest

# Test (specific service)
uv run pytest tests/client/ -m "service('gmail')"

# Test (specific pattern)
uv run pytest -k "gmail and send"

# Test (auth-required only)
uv run pytest tests/client/ -m "auth_required"

# Auth testing
uv run python scripts/auth_test.py <service_name>
```

## Architecture

```
server.py                  # Entry point — FastMCP app, middleware registration, tool setup
config/settings.py         # Pydantic Settings (all env vars)
auth/                      # OAuth 2.1 + PKCE, API key auth, JWT, credential storage
middleware/                 # Middleware stack (see below)
adapters/module_wrapper/   # MW framework — see AGENTS.md for full architecture
research/trm/              # TRM research — see AGENTS.md for vision + status
gmail/ drive/ docs/ sheets/ slides/ gcalendar/ gchat/ forms/ photos/ people/
                           # Service modules — each has *_tools.py entry point
resources/                 # MCP resource providers
prompts/                   # MCP prompt templates
tools/                     # Cross-cutting tools (server info, template macros, UI apps)
templates/                 # Jinja2 email/card templates
lifespans/                 # Server lifecycle management (startup/shutdown hooks)
skills/                    # FastMCP SkillsDirectoryProvider
tests/client/              # Integration tests (requires running server)
tests/module/              # Module wrapper unit tests
```

### Entry Point: `server.py`

Creates `FastMCP` app, registers all service tools via `setup_*_tools(mcp)` functions, wires middleware, and starts the server. Key sections:
- **Lines 1-100:** Imports, logging, SSL fix
- **Lines 100-160:** Feature flags, credential storage config
- **Lines 160-300:** SSOGoogleProvider (OAuth 2.1 for Claude.ai/Desktop)
- **Lines 300+:** FastMCP app creation, tool registration, middleware wiring, `main()`

### Middleware Stack (registration order in server.py)

1. **Auth** — OAuth 2.1 + API key authentication, session credential storage
2. **Session Tool Filter** — Per-session tool enable/disable, minimal startup mode
3. **Template** — Jinja2 rendering, macro system (must be before tool registration)
4. **Qdrant** — Vector search, historical context retrieval, payload tracking
5. **Sampling** — Resource-aware context injection, validation agents, DSL recovery
6. **Profile Enrichment** — User profile caching via Qdrant
7. **Tag-Based Resource** — Tag-based resource filtering, capability discovery
8. **Privacy** — PII redaction, privacy mode enforcement
9. **x402 Payment** — Stablecoin payment gating, verification, settlement (if enabled)
10. **Response Limiting** — Response size/token limiting (if configured)
11. **Dashboard Cache** — Caches dashboard/list tool responses

## Key Systems (Operational)

### Langfuse Integration (`middleware/langfuse_integration.py`)

**Status: Tracing operational. Evaluations/experiments are the next priority.**

Tracing uses Langfuse v4 OTel-based callbacks:
- **LiteLLM path:** `litellm.callbacks = ["langfuse_otel"]` — auto-reads `LANGFUSE_*` env vars
- **Anthropic path:** `@observe()` decorator with `propagate_attributes()` for context
- **Trace context:** `ContextVar`-based `_SamplingTraceContext` carries tool name, template, result type, step index, enhancement level

**Metadata propagated:** source, mcp_tool, template, result_type, step_index, phase, enhancement_level, has_tools, input_char_count

**Roadmap — Evaluations & Experiments:**
- Add Langfuse evaluation functions for scoring sampling quality (correctness, latency, cost)
- Use Langfuse experiments to A/B test prompt templates and model configurations
- Feed evaluation results back into fine-tuning pipelines
- Track validation agent effectiveness (pre vs. parallel mode, DSL recovery success rates)

### LiteLLM Sampling (`middleware/litellm_sampling_handler.py`)

Routes MCP sampling requests through LiteLLM's `acompletion()` to 100+ LLM providers. Key features:
- Provider routing via `provider/model` naming (e.g., `openai/gpt-4`, `anthropic/claude-sonnet-4-20250514`)
- Cost tracking integration with `payment/cost_tracker.py` (ContextVar-based)
- Semantic caching (disabled for tool-use calls to avoid ID iteration loops)
- Anthropic prompt caching (auto-enables `cache_control_injection_points`)
- Langfuse generation naming: `mcp::{tool_name}::{phase}::step{n}`

### Sampling Middleware (`middleware/sampling_middleware.py`)

`EnhancedSamplingMiddleware` — 2,740 lines handling:
- **Validation agents:** `ValidationAgentConfig` — pre-execution (sync, applies corrections) or parallel (async, advisory). Configurable per-tool with expert system prompts, confidence thresholds, and DSL syntax bypass.
- **DSL error recovery:** On parse failure, triggers recovery sampling with all registered DSL docs as context. Leverages MW symbol documentation — see AGENTS.md DSL Notation section.
- **DSLToolConfig:** Maps tool args to DSL parsers, extractors, result types, and doc providers
- **Enhancement levels:** Control how much context injection occurs per tool call

### Payment / x402 (`middleware/payment/`)

Stablecoin payment gating via the x402 protocol:
- **Flow:** Intercept tool call → check exemptions/cached receipt → verify payment → execute tool → settle on-chain → cache HMAC-signed receipt
- **Networks:** Base (eip155:8453), Ethereum (eip155:1), Sepolia testnet
- **Asset:** USDC
- **Exempt tools:** verify_payment, manage_tools, get_server_info, start_google_auth, MCP proxy tools

### Authentication

Multiple auth modes coexist:
- **OAuth 2.1 + PKCE** via FastMCP `SSOGoogleProvider` — for Claude.ai, Claude Desktop, MCP Inspector
- **API Key** (`MCP_API_KEY`) — bypass for non-OAuth clients (Cursor, Roo Code)
- **Legacy OAuth** — custom proxy for older clients
- **Credential storage modes:** `FILE_PLAINTEXT`, `FILE_ENCRYPTED` (Fernet via HKDF-SHA256 from API key), `MEMORY_ONLY`, `MEMORY_WITH_BACKUP`
- **Scope management:** `auth/scope_registry.py` — centralized Google API scope definitions

## Code Conventions

- **Tool registration:** Each service exposes `setup_*_tools(mcp)` called from `server.py`
- **Async throughout:** All tool handlers are `async def`
- **Settings via env:** All config in `config/settings.py` (Pydantic Settings), loaded from `.env`
- **Logging:** Use `from config.enhanced_logging import setup_logger; logger = setup_logger()`
- **Imports:** First-party packages listed in `pyproject.toml [tool.ruff.lint.isort]`
- **Line length:** 88 (ruff/black)
- **Linter:** ruff with E/F/W/I rules; many rules intentionally suppressed (see pyproject.toml)

## Testing

Tests require a running MCP server. The test framework auto-detects available services and fetches real resource IDs.

**Markers:** `auth_required`, `service(name)`, `integration`, `slow`, `core`, `middleware`, `x402`, `payment`

**Auto-skip:** Tests auto-skip if infrastructure is missing (Qdrant URL, OAuth credentials, credentials dir).

**Key fixtures** (`tests/client/conftest.py`):
- `client` — Async MCP client connected to running server (auto-enables all tools)
- `real_*_id` fixtures — Fetch real resource IDs from live services (gmail_message_id, drive_document_id, etc.)
- `cleanup_tracker` — Session-scoped tracker; auto-deletes created resources unless `SKIP_TEST_CLEANUP=1`

**Pattern:** See `tests/client/TESTING_FRAMEWORK.md` for the standardized template.

## Active Development Areas

1. **Module Wrapper domain expansion** — Framework is mature; priority is wrapping new Python modules beyond cards/email/qdrant. Each new domain validates and stress-tests the mixin architecture.

2. **TRM recursive refinement** — UnifiedTRN (28.7K params) is deployed for card builder slot assignment. Next: integrate recursive multi-cycle search into the production search path. See AGENTS.md for the full TRM roadmap.

3. **Langfuse evaluations & experiments** — Tracing is live; next step is building evaluation functions and experiment workflows to measure sampling quality and iterate on prompts/models.

4. **New domain adapters** — Each wrapped module produces DSL notation, semantic search, and auto-generated skills. Expanding to more Python libraries is the primary growth vector.

## PR & Commit Conventions

- **Title format:** `[<service>] <Title>` (e.g., `[Gmail] Add filter management tools`)
- **Multi-service:** `[Multi] <Title>`
- **Before committing:** Run `uv run black .` and `uv run pytest tests/client/`
- **Test new tools:** Add tests using the framework in `tests/client/TESTING_FRAMEWORK.md`
