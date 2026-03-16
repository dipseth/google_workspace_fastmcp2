---
name: google-workspace-mcp
description: Guide for using the Google Workspace MCP server — DSL notation, code mode, macros, and tools across 11+ Google services
triggers:
  - Google Workspace
  - MCP server
  - send card
  - compose email
  - DSL notation
  - code mode
  - execute tool
  - macro
  - manage tools
---

# Google Workspace MCP Server

FastMCP-based Google Workspace server with DSL-driven composition for emails and chat cards, sandboxed code execution, Jinja2 macros, privacy middleware, and Qdrant-backed response history. Not all tools are active at any given time — use `manage_tools(action="list")` to see what's currently enabled.

## Core Wrapped Tools

### `compose_dynamic_email` — MJML Email Composer

Composes responsive HTML emails via DSL notation, then sends or saves as draft.

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `email_description` | str | required | DSL structure string (e.g., `ε[ħ, τ×2, Ƀ]`) |
| `email_params` | dict/str | None | Block content keyed by symbol. Supports `_shared`/`_items` merging |
| `to` | str | "myself" | Recipients (comma-separated emails or "myself") |
| `action` | "send"/"draft" | "draft" | Draft is safe default; "send" delivers immediately |
| `cc` / `bcc` | str | None | Optional CC/BCC recipients |

**Email DSL Symbols:**

| Symbol | Block |
|--------|-------|
| `ε` | EmailSpec (root container) |
| `ħ` | HeroBlock |
| `τ` | TextBlock |
| `Ƀ` | ButtonBlock |
| `ɨ` | ImageBlock |
| `¢` | ColumnsBlock |
| `©` | Column |
| `Ħ` | HeaderBlock |
| `ƒ` | FooterBlock |
| `đ` | DividerBlock |
| `ş` | SpacerBlock |
| `ą` | AccordionBlock |
| `ȼ` | CarouselBlock |
| `ʂ` | SocialBlock |
| `ƭ` | TableBlock |

**DSL Syntax:**
- `ε[ħ, τ]` — EmailSpec with HeroBlock and TextBlock
- `ε[Ħ, ħ, τ×3, Ƀ]` — Header, hero, 3 text blocks, button
- `ε[ħ, ¢[©×2], Ƀ]` — Hero, 2-column layout, button
- `ε[Ħ, τ, đ, ƒ]` — Header, text, divider, footer

**Params Structure (`_shared`/`_items` merging):**
```json
{
  "subject": "Weekly Report",
  "τ": {
    "_shared": {"padding": "10px 25px"},
    "_items": [
      {"text": "Hello {{user://current/email.email}}"},
      {"text": "Here is your report."}
    ]
  },
  "Ƀ": {
    "_items": [
      {"text": "View Report", "href": "https://example.com/report"}
    ]
  }
}
```

**Example — Simple email:**
```
email_description: ε[Ħ, ħ, τ, Ƀ]
email_params: {
  "subject": "Meeting Reminder",
  "Ħ": {"_items": [{"title": "Acme Corp"}]},
  "ħ": {"_items": [{"title": "Team Standup", "subtitle": "Tomorrow at 10am"}]},
  "τ": {"_items": [{"text": "Don't forget the standup meeting."}]},
  "Ƀ": {"_items": [{"text": "Add to Calendar", "href": "https://calendar.google.com"}]}
}
```

**For detailed component field reference:** Use `skill://mjml-email/` resources (15 component docs, symbols, containment rules).

---

### `send_dynamic_card` — Google Chat Card Builder

Sends a card to Google Chat using DSL notation for structure control.

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `card_description` | str | required | DSL structure string (e.g., `§[δ×3, Ƀ[ᵬ×2]]`) |
| `card_params` | dict/str | None | Widget content keyed by symbol. Supports `_shared`/`_items` merging |
| `space_id` | str | None | Chat space ID. Required only for API mode (no webhook) |
| `webhook_url` | str | None | Webhook URL. Defaults to `MCP_CHAT_WEBHOOK` env var |
| `thread_key` | str | None | Thread key for replies |

**Card DSL Symbols (primary building blocks):**

| Symbol | Component |
|--------|-----------|
| `§` | Section |
| `δ` | DecoratedText |
| `Đ` | Divider |
| `ᵬ` | Button |
| `Ƀ` | ButtonList |
| `ℊ` | Grid |
| `ǵ` | GridItem |
| `◦` | Carousel |
| `▼` | CarouselCard |
| `ȼ` | ChipList |
| `ℂ` | Chip |
| `ʈ` | TextParagraph |
| `τ` | TextInput |
| `ǐ` | Image |
| `ɨ` | Icon |
| `▲` | SelectionInput |
| `◙` | DateTimePicker |
| `◇` | CardHeader |
| `¢` | Columns |
| `ç` | Column |

**DSL Syntax:**
- `§[δ]` — Section with one DecoratedText
- `§[δ×3, Ƀ[ᵬ×2]]` — Section with 3 DecoratedTexts and 2 Buttons
- `§[ℊ[ǵ×4]]` — Section with a 4-item Grid
- `§[δ, ǐ, Ƀ[ᵬ]]` — Section with text, image, and button

**Context Consumption Pattern:**
Widget content comes from `card_params` via symbol keys, NOT from inline text in `card_description`. The builder creates structure from DSL; content comes from context consumption.

```json
{
  "δ": {
    "_shared": {"top_label": "Status"},
    "_items": [
      {"text": "Build passed", "icon": "STAR"},
      {"text": "Tests: 142/142"}
    ]
  },
  "ᵬ": {
    "_items": [
      {"text": "View Build", "url": "https://ci.example.com/build/123"}
    ]
  }
}
```

**Session-scope enable required:** This tool often needs session-scope enablement:
```
manage_tools(action="enable", tool_names="send_dynamic_card", scope="session")
```
After session enable, must `/mcp` reconnect for Claude Code to discover the tool.

**For detailed component field reference:** Use `skill://gchat-cards/` resources (symbols, DSL syntax, 100+ component docs).

---

### Qdrant Search Tools

| Tool | Purpose |
|------|---------|
| `qdrant_search` | Search tool response history with semantic or hybrid search |
| `search_tool_history` | Find past tool outputs by tool name, date range, or keywords |
| `get_tool_analytics` | Usage statistics across tools |
| `get_response_details` | Get full details of a specific stored response |
| `fetch` | Fetch a specific Qdrant point by ID |
| `cleanup_qdrant_data` | Clean up old or orphaned Qdrant data |

**Collections:**
- `mcp_tool_responses` — Stores all tool invocation results with embeddings
- `mcp_gchat_cards_v8` — Card templates and feedback patterns

---

## Code Mode (Execute Tool)

The `execute` tool runs sandboxed Python with `call_tool()` available for chaining MCP tool calls.

**Key rules:**
- Use `await call_tool(tool_name, params)` to call any MCP tool
- Use `return` to produce output
- `import` is **NOT available** — use built-in helpers instead
- Prefer returning the final answer from a single block

**Built-in Helpers:**

| Category | Functions |
|----------|-----------|
| **Datetime** | `now(tz_offset=-6)`, `today(tz_offset=-6)`, `days_ago(n)`, `hours_ago(n)`, `format_date(iso, fmt)`, `parse_date(iso)`, `timestamp()` |
| **JSON** | `to_json(obj, indent)`, `from_json(s)` |
| **URL** | `url_encode(s)`, `url_decode(s)`, `url_join(base, *parts)`, `query_string(params)` |
| **Regex** | `re_find(pattern, text)`, `re_match(pattern, text)`, `re_sub(pattern, repl, text)` |
| **Text** | `truncate(text, n=80)`, `join(items, sep)`, `html_escape(s)`, `dedent(text)`, `wrap_text(text, width)`, `pad_left(s, width)`, `pad_right(s, width)` |
| **Math** | `sqrt(n)`, `ceil(n)`, `floor(n)`, `round_(n, digits)`, `abs_()`, `min_()`, `max_()`, `sum_()` |
| **Collections** | `sorted_(items, key, reverse)`, `unique(items)`, `flatten(lists)`, `counter(items)`, `chunk(items, size)`, `zip_(*iterables)`, `dict_get(d, 'a.b.c', default)` |
| **Hashing** | `md5(s)`, `sha256(s)` |
| **Async** | `gather(*coros)`, `sleep(seconds)` |

**Code Mode Discovery Tools:**

| Tool | Purpose |
|------|---------|
| `tags` | List all tool tags for filtering |
| `search` | BM25 keyword search across tool names/descriptions |
| `get_schema` | Get full JSON schema for a tool before calling it |
| `execute` | Run sandboxed Python code |

**Example — Chain tool calls:**
```python
# Fetch labels, then compose a report email
labels = await call_tool("list_gmail_labels", {"user_google_email": "me@example.com"})
label_count = len(labels.get("labels", []))

await call_tool("compose_dynamic_email", {
    "email_description": "ε[Ħ, τ, đ, ƒ]",
    "email_params": to_json({
        "subject": f"Label Report - {today()}",
        "Ħ": {"_items": [{"title": "Gmail Labels"}]},
        "τ": {"_items": [{"text": f"You have {label_count} labels."}]},
        "ƒ": {"_items": [{"text": f"Generated {now()}"}]}
    }),
    "action": "draft"
})
return f"Draft created with {label_count} labels"
```

---

## Jinja2 Macro System

Macros enable reusable, data-driven templates for emails and cards.

**Location:** `middleware/templates/*.j2` (tracked) and `middleware/templates/dynamic/*.j2` (gitignored, experimental)

### Dual-Mode Pattern

Macros support two modes:
- **`mode='dsl'`** — Returns DSL structure string (used as `email_description` or `card_description`)
- **`mode='params'`** — Returns JSON params (used as `email_params` or `card_params`)

```jinja2
{% macro email_resource_report(label_data, profile_data, session_data, symbols, mode='dsl') %}
  {%- if mode == 'dsl' -%}
    {{ s.EmailSpec }}[{{ s.HeaderBlock }}, {{ s.HeroBlock }}, ...]
  {%- elif mode == 'params' -%}
    {{ result | tojson }}
  {%- endif -%}
{% endmacro %}
```

### Resource URI Templating

Inside macros, `service://` URIs are preprocessed into Jinja2 variables:
- `service://gmail/labels` becomes `service_gmail_labels` (SimpleNamespace with dot access)
- `user://current/email` becomes `user_current_email`
- Access via: `{{ service_gmail_labels.labels[0].name }}`

### `create_template_macro` Tool

Create macros at runtime:

| Parameter | Type | Description |
|-----------|------|-------------|
| `macro_name` | str | Valid Python identifier (1-100 chars) |
| `macro_content` | str | Full `{% macro %}...{% endmacro %}` Jinja2 block (10-50K chars) |
| `description` | str | Optional description |
| `usage_example` | str | Optional usage example |
| `persist_to_file` | bool | Save to `templates/dynamic/` for persistence across restarts |

### `email_symbols` Global

The `email_symbols` object is available as a Jinja2 global, providing symbol-to-class mappings for constructing DSL strings dynamically in macros.

---

## Resource URIs

### User & Auth
| URI | Description |
|-----|-------------|
| `user://current/email` | Authenticated user's email |
| `user://current/profile` | User profile with auth status |
| `user://profile/{email}` | Profile for specific email |
| `auth://session/current` | Current session info |
| `auth://sessions/list` | All active sessions |
| `auth://credentials/{email}/status` | Credential status for email |

### Service Data
| URI | Description |
|-----|-------------|
| `service://{service}/lists` | Available list types for a service |
| `service://{service}/{list_type}` | All items for list type |
| `service://{service}/{list_type}/{item_id}` | Specific item details |

Supported services: `gmail`, `drive`, `calendar`, `docs`, `sheets`, `chat`, `forms`, `slides`, `photos`

### Templates & Macros
| URI | Description |
|-----|-------------|
| `template://macros` | List all available macros |
| `template://macros/{macro_name}` | Specific macro usage example |

### Qdrant
| URI | Description |
|-----|-------------|
| `qdrant://collections/list` | All Qdrant collections |
| `qdrant://collection/{name}/info` | Collection details |
| `qdrant://collection/{name}/responses/recent` | Recent responses |
| `qdrant://search/{query}` | Search across collections |
| `qdrant://collection/{name}/{point_id}` | Specific point |
| `qdrant://status` | Overall Qdrant status |

### Other
| URI | Description |
|-----|-------------|
| `recent://{service}` | Recent items for service |
| `chat://digest` | Chat digest (supports `?hours=N&limit=N`) |
| `gmail://messages/recent` | Recent Gmail messages |
| `tools://list/all` | All available tools |

---

## Skill Resources

| Resource | Content | When to Use |
|----------|---------|-------------|
| `skill://gchat-cards/` | 100+ component docs, symbols, containment rules, DSL syntax | Detailed card component field reference |
| `skill://mjml-email/` | 15 component docs, email DSL syntax, symbols | Detailed email block field reference |

---

## Tool Management

### `manage_tools`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `action` | str | required | `list`, `enable`, `disable`, `disable_all_except`, `enable_all` |
| `tool_names` | str/list | None | Tool name(s) — string, list, comma-separated, or JSON array |
| `scope` | str | "global" | `global` (all clients) or `session` (current client only) |
| `service_filter` | str | None | Filter by service: `gmail`, `chat`, `drive`, etc. |

**Protected tools** (cannot be disabled): `manage_tools`, `qdrant_search`, `health_check`, `start_google_auth`, `check_drive_auth`, and Code Mode meta-tools (`tags`, `search`, `get_schema`, `execute`).

---

## All Services Quick Reference

Use `manage_tools(action="list")` or `manage_tools(action="list", service_filter="gmail")` to see currently active tools.

| Service | Key Tools |
|---------|-----------|
| **Drive** | `upload_to_drive`, `search_drive_files`, `list_drive_items`, `create_drive_file`, `share_drive_files`, `manage_drive_files`, `get_drive_file_content`, `make_drive_files_public` |
| **Gmail** | `compose_dynamic_email`, `search_gmail_messages`, `send_gmail_message`, `draft_gmail_message`, `reply_to_gmail_message`, `list_gmail_labels`, `manage_gmail_label`, `list_gmail_filters`, `create_gmail_filter`, `manage_gmail_allow_list` |
| **Chat** | `send_dynamic_card`, `list_spaces`, `list_messages`, `send_message`, `search_messages` |
| **Chat Cards** | `send_simple_card`, `send_rich_card`, `send_enhanced_card`, `send_interactive_card`, `send_smart_card`, `preview_card_from_description`, `validate_card`, `find_card_templates`, `save_card_template` |
| **Calendar** | `list_calendars`, `list_events`, `create_event`, `modify_event`, `delete_event`, `get_event`, `create_calendar`, `bulk_calendar_operations`, `move_events_between_calendars` |
| **Docs** | `search_docs`, `get_doc_content`, `list_docs_in_folder`, `create_doc` |
| **Sheets** | `list_spreadsheets`, `get_spreadsheet_info`, `read_sheet_values`, `modify_sheet_values`, `create_spreadsheet`, `create_sheet`, `format_sheet_range` |
| **Slides** | `create_presentation`, `get_presentation_info`, `add_slide`, `update_slide_content`, `export_and_download_presentation` |
| **Forms** | `create_form`, `add_questions_to_form`, `get_form`, `set_form_publish_state`, `publish_form_publicly`, `get_form_response`, `list_form_responses`, `update_form_questions` |
| **Photos** | `list_photos_albums`, `search_photos`, `upload_photos`, `upload_folder_photos`, `photos_smart_search`, `photos_batch_details`, `create_photos_album`, `get_photo_details` |
| **People** | `list_people_contact_labels`, `get_people_contact_group_members`, `manage_people_contact_labels` |
| **Qdrant** | `qdrant_search`, `search_tool_history`, `get_tool_analytics`, `fetch`, `get_response_details`, `cleanup_qdrant_data` |
| **Email Templates** | `create_email_template`, `list_email_templates`, `preview_email_template`, `intelligent_email_composer`, `send_smart_email` |
| **Module Wrappers** | `list_wrapped_modules`, `wrap_module`, `search_module`, `list_module_components`, `get_module_component` |
| **Server** | `health_check`, `manage_credentials`, `manage_tools`, `create_template_macro` |
| **Code Mode** | `tags`, `search`, `get_schema`, `execute` |

---

## Cross-Cutting Features

### Privacy Middleware
- Encrypts PII in tool responses using per-session Fernet keys
- LLM sees masked tokens (`[MASKED:token_1]`), wire carries ciphertext
- Modes: `auto` (heuristic PII detection) or `strict` (encrypt all strings)
- Round-trip: `[PRIVATE:token_N]` in tool arguments resolves back to plaintext

### Authentication
1. Call `start_google_auth` with email to begin OAuth flow
2. Complete authentication in browser
3. Call `check_drive_auth` to verify credentials
4. Session-level account linking tracks authed emails across session lifetime

### Response History (Qdrant)
- All tool responses are automatically stored with embeddings
- Searchable via `qdrant_search` (semantic), `search_tool_history` (filtered), or `get_tool_analytics` (stats)
- Collections: `mcp_tool_responses` (all responses), `mcp_gchat_cards_v8` (card templates + feedback)
