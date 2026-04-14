# Google Workspace MCP Server — Agent Guide

## Overview

`google-workspace-unlimited` v2.0.0 is a FastMCP server exposing **96+ tools** across **10 Google Workspace services**: Gmail, Drive, Docs, Sheets, Slides, Calendar, Forms, Chat, Photos, and People API.

Agents interact through **7 Code Mode tools** that discover, compose, and execute the full tool surface from sandboxed Python.

---

## Architecture: Code Mode + Service Tools

```
Agent / LLM
    │
    ├─ 7 Code Mode Tools (discovery, orchestration, execution)
    │       │
    │       └─ execute ─► call_tool("send_gmail_message", {...})
    │                     call_tool("create_event", {...})
    │                     call_tool("format_sheet_range", {...})
    │
    └─ 96+ Service Tools (direct MCP tool calls)
            │
            ├─ Gmail (13 tools)
            ├─ Drive (10 tools)
            ├─ Docs (4 tools)
            ├─ Sheets (7 tools)
            ├─ Slides (5 tools)
            ├─ Calendar (9 tools)
            ├─ Forms (8 tools)
            ├─ Chat (8+ tools)
            ├─ Photos (8 tools)
            ├─ People (3 tools)
            ├─ Qdrant / Search (6 tools)
            ├─ Email Templates (5 tools)
            ├─ Module Wrappers (5 tools)
            └─ Server Management (4 tools)
```

---

## Code Mode Tools

These 7 tools are always available (protected from disable) and form the agent's control plane:

| Tool | Purpose |
|------|---------|
| `execute` | Run sandboxed Python with `await call_tool()` for chaining MCP calls |
| `search` | BM25 keyword search across tool names and descriptions |
| `get_schema` | Retrieve full JSON schema for any tool before calling it |
| `tags` | List all tool tags for filtering by service or capability |
| `semantic_search` | Qdrant vector search — semantic queries, DSL filters, recommendations |
| `fetch_document` | Peek at a stored response by point ID (truncated preview) |
| `tool_activity` | Dashboard of tool usage — call counts, error rates, sample IDs |

### Execute Tool — Sandboxed Python

The `execute` tool runs Python code in a sandbox with `call_tool()` available for chaining:

```python
# Multi-step workflow: search Gmail, then create a calendar event
messages = await call_tool("search_gmail_messages", {
    "query": "from:boss@company.com subject:meeting",
    "max_results": 5
})
event = await call_tool("create_event", {
    "summary": "Follow-up meeting",
    "start_time": "2026-04-15T10:00:00-05:00",
    "end_time": "2026-04-15T11:00:00-05:00"
})
return {"messages_found": len(messages), "event_created": event}
```

**Built-in helpers** (no `import` needed):

| Category | Functions |
|----------|-----------|
| Datetime | `now(tz_offset)`, `today()`, `days_ago(n)`, `hours_ago(n)`, `format_date()`, `parse_date()` |
| JSON | `to_json(obj)`, `from_json(s)` |
| URL | `url_encode(s)`, `url_decode(s)`, `url_join()`, `query_string()` |
| Regex | `re_find()`, `re_match()`, `re_sub()` |
| Text | `truncate()`, `join()`, `html_escape()`, `dedent()`, `wrap_text()` |
| Math | `sqrt()`, `ceil()`, `floor()`, `round_()`, `abs_()`, `min_()`, `max_()`, `sum_()` |
| Collections | `sorted_()`, `unique()`, `flatten()`, `counter()`, `chunk()`, `zip_()`, `dict_get(d, 'a.b.c')` |
| Hashing | `md5(s)`, `sha256(s)` |
| Async | `gather(*coros)`, `sleep(seconds)` |

---

## Service Tools by Google Service

### Gmail
| Tool | Description |
|------|-------------|
| `search_gmail_messages` | Search messages with Gmail query syntax |
| `get_gmail_message` | Get full message by ID |
| `send_gmail_message` | Send a new email |
| `reply_to_gmail` | Reply to an existing thread |
| `forward_gmail_message` | Forward a message |
| `modify_gmail_labels` | Add/remove labels on messages |
| `list_gmail_labels` | List all labels |
| `create_gmail_label` | Create a new label |
| `trash_gmail_message` | Move message to trash |
| `get_gmail_attachment` | Download an attachment |
| `compose_dynamic_email` | Compose email using DSL notation with MJML templates |
| `intelligent_email_composer` | AI-assisted email composition |
| `send_smart_email` | Send with template rendering |

### Drive
| Tool | Description |
|------|-------------|
| `search_drive` | Search files across Drive |
| `get_drive_file_content` | Read file content |
| `list_drive_files` | List files in a folder |
| `upload_to_drive` | Upload a file |
| `create_drive_folder` | Create a folder |
| `move_drive_file` | Move file to another folder |
| `copy_drive_file` | Copy a file |
| `delete_drive_file` | Delete a file |
| `share_drive_file` | Set sharing permissions |
| `export_drive_file` | Export to different format |

### Calendar
| Tool | Description |
|------|-------------|
| `list_calendars` | List all calendars |
| `list_events` | List events with date range |
| `get_event` | Get event details |
| `create_event` | Create a new event |
| `modify_event` | Update an existing event |
| `delete_event` | Delete an event |
| `create_calendar` | Create a new calendar |
| `bulk_calendar_operations` | Batch create/modify/delete events |
| `move_events_between_calendars` | Move events across calendars |

### Sheets
| Tool | Description |
|------|-------------|
| `list_spreadsheets` | List spreadsheets |
| `get_spreadsheet_info` | Get spreadsheet metadata |
| `read_sheet_values` | Read cell values |
| `modify_sheet_values` | Write cell values |
| `create_spreadsheet` | Create a new spreadsheet |
| `create_sheet` | Add a sheet tab |
| `format_sheet_range` | Apply formatting to a range |

### Docs
| Tool | Description |
|------|-------------|
| `search_docs` | Search documents |
| `get_doc_content` | Read document content |
| `list_docs_in_folder` | List docs in a Drive folder |
| `create_doc` | Create a new document |

### Slides
| Tool | Description |
|------|-------------|
| `create_presentation` | Create a new presentation |
| `get_presentation_info` | Get presentation metadata |
| `add_slide` | Add a slide |
| `update_slide_content` | Update slide content |
| `export_and_download_presentation` | Export presentation |

### Chat
| Tool | Description |
|------|-------------|
| `send_dynamic_card` | Send rich Card v2 messages using DSL notation |
| `list_chat_spaces` | List available spaces |
| `list_chat_messages` | List messages in a space |
| `get_chat_message` | Get a specific message |
| `create_chat_space` | Create a new space |
| `send_chat_message` | Send a plain text message |
| `add_chat_members` | Add members to a space |
| `manage_chat_space` | Update space settings |

### Forms
| Tool | Description |
|------|-------------|
| `create_form` | Create a new form |
| `get_form` | Get form details |
| `add_questions_to_form` | Add questions |
| `update_form_questions` | Modify existing questions |
| `set_form_publish_state` | Toggle publish state |
| `publish_form_publicly` | Make form publicly accessible |
| `get_form_response` | Get a specific response |
| `list_form_responses` | List all responses |

### Photos
| Tool | Description |
|------|-------------|
| `list_photos_albums` | List albums |
| `search_photos` | Search photos |
| `get_photo_details` | Get photo metadata |
| `upload_photos` | Upload photos |
| `upload_folder_photos` | Upload a folder of photos |
| `photos_smart_search` | AI-powered photo search |
| `photos_batch_details` | Batch get photo details |
| `create_photos_album` | Create an album |

### People
| Tool | Description |
|------|-------------|
| `list_people_contact_labels` | List contact groups |
| `get_people_contact_group_members` | Get group members |
| `manage_people_contact_labels` | Create/update/delete contact groups |

---

## Infrastructure Tools

### Server Management
| Tool | Description |
|------|-------------|
| `manage_tools` | Enable/disable tools at runtime (global or per-session, filterable by service) |
| `health_check` | Server health, OAuth status, memory, active sessions |
| `start_google_auth` | Initiate OAuth 2.1 + PKCE flow for all Google services |
| `check_drive_auth` | Verify authentication status |

### Qdrant / Vector Search
| Tool | Description |
|------|-------------|
| `qdrant_search` | Full semantic search with natural language, filters, and DSL queries |
| `search_tool_history` | Search past tool call results |
| `get_tool_analytics` | Usage analytics and patterns |
| `fetch` | Retrieve stored data by point ID |
| `get_response_details` | Full response details for a stored result |
| `cleanup_qdrant_data` | Remove stale data from collections |

### Module Wrappers
| Tool | Description |
|------|-------------|
| `list_wrapped_modules` | List all wrapped Python modules |
| `wrap_module` | Wrap a new Python module for MCP access |
| `search_module` | Search within a wrapped module's components |
| `list_module_components` | List components in a wrapped module |
| `get_module_component` | Get detailed info about a specific component |

---

## DSL Notation

Tools like `send_dynamic_card` and `compose_dynamic_email` accept a compact DSL for describing rich layouts:

```
§[δ×3, Ƀ[ᵬ×2]]
= Section containing 3 DecoratedTexts and a ButtonList with 2 Buttons
```

**Syntax:** `SYMBOL` (component), `[children]` (nesting), `×N` (multiplicity), `{key=val}` (params).

**Content DSL:** `δ 'Status: Online' success bold` — styled text with modifiers.

Symbols are auto-generated from wrapped modules. Use `search_module` or `get_schema` to discover available symbols for each domain.

---

## Authentication

The server supports multiple auth modes:

| Mode | Use Case |
|------|----------|
| **OAuth 2.1 + PKCE** | Claude.ai, Claude Desktop, MCP Inspector |
| **API Key** (`MCP_API_KEY`) | Cursor, Roo Code, non-OAuth clients |

Call `start_google_auth` with an email to begin the OAuth flow, then `check_drive_auth` to verify.

---

## Graceful Degradation

The server starts and registers all 96+ tools even when Qdrant or embedding services are unavailable. Module wrappers enter degraded mode — in-memory introspection works, vector search returns empty results. Services reconnect automatically when infrastructure comes back online.

---

## Quick Start

```bash
# Install
uv sync

# Configure
cp .env.example .env  # edit with Google OAuth credentials

# Run
uv run python server.py

# Development mode (hot reload)
uv run fastmcp dev
```
