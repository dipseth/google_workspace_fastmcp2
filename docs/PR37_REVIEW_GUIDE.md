# PR #37 Review Guide

## Overview

This PR brings the `reaserch_trm_mw` branch into `main` via `pr/migrate-to-public`. It spans TRM research, module wrapper improvements, and server hardening work across multiple sessions.

## Key Changes to Review

### 1. Graceful Degradation (High Impact)
**Files:** `adapters/module_wrapper/__init__.py`, `qdrant_mixin.py`, `embedding_mixin.py`, `search_mixin/_base.py`, `lifespans/server_lifespans.py`

Server now starts with all 96 tools even when Qdrant/embeddings are down. ModuleWrapper enters degraded mode — in-memory introspection works, vector search returns empty results, lazy reconnection recovers when services come back.

**Validated:** Server starts with Qdrant unreachable, card/email tools register and work with in-memory fallbacks, normal mode unchanged.

### 2. Stale Sandbox Argument Fix (Bug Fix)
**File:** `middleware/sampling_middleware.py`

The argument recovery middleware was mutating `context.message.arguments` in-place (`.clear()/.update()`), causing args from prior tool calls to leak into subsequent calls within the same sandbox session. Changed to dict reassignment.

**Validated:** Sequential `search_gmail_messages` → `send_dynamic_card` → `compose_dynamic_email` calls in sandbox — no arg leakage.

### 3. Tool Docs Alignment (Developer Experience)
**Files:** `gchat/card_tools.py`, `skills/server_skill_generator.py`, `gchat/wrapper_setup.py`, `gmail/email_wrapper_setup.py`

- `send_dynamic_card` now uses `UserGoogleEmail = None` (middleware auto-injects, LLMs don't need to pass it)
- All hardcoded Unicode symbols in skill templates/examples converted to dynamic functions pulling from `wrapper.symbol_mapping`
- Parameter tables updated with `user_google_email`, email content separation guidance

### 4. FastMCP 3.2.4 Upgrade
**File:** `uv.lock`

Security fixes (FileUpload validation, header forwarding), task auth scoping, Gemini compatibility.

### 5. Supporting Fixes
- `middleware/tag_based_resource_middleware.py` — Forms resource `list_tool` set to `None` (requires `form_id`)
- Lint: all E741/E731 errors fixed across research and diagnostic-ui code
- Format: entire codebase formatted with `ruff format`

## What's NOT Changed

- Google API tool behavior (Gmail, Drive, Docs, Sheets, Calendar, etc.) — unchanged
- Authentication flows — unchanged
- Payment middleware — unchanged
- DSL parser — unchanged

## Test Results

| Suite | Result |
|-------|--------|
| Module unit tests | 480 passed, 28 skipped, 0 failed |
| Client tests | 21 passed, 1 pre-existing failure (`test_list_tools` count assertion in code mode) |
| Live server validation | `send_dynamic_card` and `compose_dynamic_email` both succeed |
| Degraded mode | Server starts and tools register with Qdrant down |
| Lint | `ruff check` passes clean |
| Format | `ruff format --check` passes clean |

## Merge Checklist

- [x] CI passes (lint + format + tests)
- [x] No breaking changes to tool signatures (UserGoogleEmail is Optional with default=None)
- [x] Graceful degradation tested in both degraded and normal modes
- [x] Stale arg fix validated with sequential sandbox calls
- [x] All 96 tools register on server startup
- [x] Live tool calls succeed (card sent to Testing space, email drafted)
