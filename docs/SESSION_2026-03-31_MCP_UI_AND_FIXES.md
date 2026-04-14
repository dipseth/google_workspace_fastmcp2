# Session Notes: MCP UI Features & Bug Fixes (2026-03-31)

## Issues Investigated & Fixed

### 1. Only 4 Tools Visible When `ENABLE_CODE_MODE=false`

**Symptom:** VS Code Copilot showed only `search`, `get_schema`, `tags`, `execute` (CodeMode tools) even with code mode disabled.

**Root Causes:**
- **Stale client cache** — VS Code cached the old CodeMode tool list from a previous session. Fix: restart MCP connection in VS Code after server config changes.
- **Pagination cutting off tools** — `LIST_PAGE_SIZE=28` in `.env` meant only 28 of 99 tools returned on page 1. VS Code Copilot doesn't follow MCP pagination cursors.

**Fix:** Set `LIST_PAGE_SIZE=0` in `.env` to disable pagination. All 99 tools now returned in a single response.

**File changed:** `.env`

---

### 2. `PrefabApp` Return Type Error on Resource Read

**Symptom:** `Error loading MCP App: MPC 0: Error reading resource 'ui://data-dashboard/list_events': contents must be str, bytes, or list[ResourceContent], got PrefabApp`

**Root Cause:** The `data_dashboard` resource handler in `tools/ui_apps.py` tried to return a `PrefabApp` object, but MCP resource handlers must return `str` or `bytes`. `PrefabApp` is only valid as a return type from `FastMCPApp` providers.

**Fix:** Removed the Prefab UI code path from the resource handler. Resources always return self-contained HTML. Prefab dashboards are served via `FastMCPApp` providers instead.

**File changed:** `tools/ui_apps.py` (lines ~434-450)

---

### 3. Dashboard Cache Not Populating (Empty Data in HTML)

**Symptom:** Gmail Labels dashboard rendered the UI (table headers, search, toggle) but showed "0 / 0 items" even after calling `list_gmail_labels` multiple times.

**Root Cause:** The `ResponseCachingMiddleware` (Redis, registered as step 14/outermost) was caching resource read responses. The first time `ui://data-dashboard/list_gmail_labels` was read (before any tool call populated the in-memory dashboard cache), Redis cached the empty HTML response. All subsequent reads returned the stale cached empty HTML, bypassing the resource handler entirely.

**Evidence:**
- Server logs confirmed `Dashboard cache updated for list_gmail_labels (28466 chars)` — in-memory cache was populated
- But `get_cached_result()` was never called on subsequent reads — Redis intercepted first
- 5 stale `gw-mcp__resources/read::*` keys found in Redis

**Fix:**
1. Added `read_resource_settings={"enabled": False}` to `ResponseCachingMiddleware` config — dynamic resources need live data
2. Flushed 5 stale Redis cache entries

**File changed:** `middleware/server_middleware_setup.py` (line ~450-453)

---

## New Features Verified Working

### Data Dashboards (Phase 1 — HTML)

Self-contained HTML dashboards served via `ui://data-dashboard/{tool_name}` resources. Features:
- **Table & Cards view** toggle
- **Search/filter** with real-time filtering
- **Sortable columns** (click headers)
- **Stats chips** (total_count, system_count, user_count)
- **Typed cell rendering**: primary, badge, numeric, timestamp, link, color swatch, nested, boolean
- **Dark theme** (Tokyo Night palette)

Configured for 12 list tools in `_DASHBOARD_CONFIGS`:
`list_gmail_labels`, `list_gmail_filters`, `list_spaces`, `list_messages`, `list_calendars`, `list_events`, `list_drive_items`, `list_docs_in_folder`, `list_spreadsheets`, `list_photos_albums`, `list_form_responses`, `list_people_contact_labels`

Auto-detect mode: tools not in `_DASHBOARD_CONFIGS` get auto-detected columns from response data.

### App Providers (Phase 2 — FastMCP 3.2+)

Registered when `ENABLE_APP_PROVIDERS=true`:

| Provider | Tool | Purpose |
|----------|------|---------|
| `Approval` | `request_approval` | Approve/cancel dialog for destructive actions |
| `Choice` | `choose` | Selection UI for picking from options |
| `ToolManager` (FastMCPApp) | `toggle_tool_state` + `@app.ui()` | Interactive tool management with toggle switches |

**Note:** These require the client to advertise `io.modelcontextprotocol/ui` support during the MCP handshake. VS Code Copilot does **not** currently support this extension, so these tools won't appear in that client. They work with clients that do support the UI extension (e.g., Claude Desktop, MCP Inspector).

### Prefab UI Components (Available but Client-Gated)

`_build_prefab_data_dashboard()` in `tools/ui_apps.py` builds `PrefabApp` with `DataTable` components (searchable, sortable, paginated). Currently only usable via `FastMCPApp` providers, not resource handlers.

`create_tool_management_app()` builds an interactive tool management app with:
- Accordion groups by Google Workspace service
- Toggle switches per tool
- Protected tool badges
- Tool descriptions

---

## Configuration Summary

```env
# Key .env settings after this session
LIST_PAGE_SIZE=0              # No pagination — all tools in one response
ENABLE_CODE_MODE=false        # Direct tool exposure (no CodeMode proxy)
ENABLE_APP_PROVIDERS=true     # Approval, Choice, ToolManager apps
ENABLE_SKILLS_PROVIDER=true   # Skill generation
```

## Files Modified

| File | Change |
|------|--------|
| `.env` | `LIST_PAGE_SIZE=0`, `ENABLE_APP_PROVIDERS=true` |
| `tools/ui_apps.py` | Removed PrefabApp return from resource handler; kept for FastMCPApp provider path |
| `middleware/server_middleware_setup.py` | Disabled Redis caching for resource reads |
| `middleware/dashboard_cache_middleware.py` | Cleaned up debug logging (added/removed during investigation) |

## Architecture Notes

### Dashboard Data Flow
```
1. Client calls list tool (e.g., list_gmail_labels)
2. DashboardCacheMiddleware.on_call_tool() intercepts → stores result in _result_cache
3. Client reads ui://data-dashboard/list_gmail_labels resource
4. data_dashboard() handler reads from _result_cache via get_cached_result()
5. HTML template returned with data injected at /*__DASHBOARD_DATA__*/ placeholder
```

### Middleware Order (relevant to this session)
```
(outermost — runs first on requests, last on responses)
14. Redis ResponseCachingMiddleware  ← was caching stale empty dashboards
13. DashboardCacheMiddleware         ← populates _result_cache on tool calls
...
5.  TemplatMiddleware                ← injects Jinja2 tracking
...
(innermost — tool handler)
```

The key insight: Redis caching (step 14) intercepted resource reads before DashboardCacheMiddleware (step 13) could serve fresh data. Disabling `read_resource_settings` fixed this.
