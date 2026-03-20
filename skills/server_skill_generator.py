"""Server-level SKILL.md generator for the Google Workspace MCP server.

Generates the google-workspace-mcp skill document that describes all
cross-module capabilities: email composition (MJML), card sending (GChat),
code mode, Jinja2 macros, resource URIs, and tool management.

Unlike per-wrapper SkillsMixin (which documents a single module), this
generator synthesises information from both wrappers into one cohesive
reference guide.

Usage:
    from skills.server_skill_generator import generate_server_skill, write_server_skill

    doc = generate_server_skill(
        card_symbols=card_wrapper.symbol_mapping,
        email_symbols=email_wrapper.symbol_mapping,
    )
    write_server_skill(Path("~/.claude/skills"), card_wrapper, email_wrapper)
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Dict

from config.enhanced_logging import setup_logger

if TYPE_CHECKING:
    from adapters.module_wrapper import ModuleWrapper

from adapters.module_wrapper.skill_types import SkillDocument

logger = setup_logger()

# U+00D7 MULTIPLICATION SIGN — DSL repeat multiplier (e.g., block*3 notation).
# Stored via named unicode escape so the source file stays symbol-free.
_MULT = "\N{MULTIPLICATION SIGN}"

# Building blocks shown in the server skill — most useful ~20 card components
CARD_BUILDING_BLOCKS: list[str] = [
    "Section",
    "DecoratedText",
    "Divider",
    "Button",
    "ButtonList",
    "Grid",
    "GridItem",
    "Carousel",
    "CarouselCard",
    "ChipList",
    "Chip",
    "TextParagraph",
    "TextInput",
    "Image",
    "Icon",
    "SelectionInput",
    "DateTimePicker",
    "CardHeader",
    "Columns",
    "Column",
]

# Building blocks shown in the server skill — ~15 email blocks
EMAIL_BUILDING_BLOCKS: list[str] = [
    "EmailSpec",
    "HeroBlock",
    "TextBlock",
    "ButtonBlock",
    "ImageBlock",
    "ColumnsBlock",
    "Column",
    "HeaderBlock",
    "FooterBlock",
    "DividerBlock",
    "SpacerBlock",
    "AccordionBlock",
    "CarouselBlock",
    "SocialBlock",
    "TableBlock",
]

# =============================================================================
# Static sections — no DSL symbols; safe as plain string constants
# =============================================================================

_FRONTMATTER = """\
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
---"""

_OVERVIEW = """\
# Google Workspace MCP Server

FastMCP-based Google Workspace server with DSL-driven composition for emails and \
chat cards, sandboxed code execution, Jinja2 macros, privacy middleware, and \
Qdrant-backed response history. Not all tools are active at any given time — use \
`manage_tools(action="list")` to see what's currently enabled."""

_EMAIL_PARAMS_TABLE = """\
**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `email_description` | str | required | DSL structure string — see Email DSL Symbols table |
| `email_params` | dict/str | None | Block content keyed by symbol. Supports `_shared`/`_items` merging |
| `to` | str/list | "myself" | Recipients: "myself", comma-separated string, or list of emails |
| `action` | "send"/"draft" | "draft" | Draft is safe default; "send" delivers immediately |
| `cc` / `bcc` | str | None | Optional CC/BCC recipients |"""

_CARD_PARAMS_TABLE = """\
**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `card_description` | str | required | DSL structure string — see Card DSL Symbols table |
| `card_params` | dict/str | None | Widget content keyed by symbol. Supports `_shared`/`_items` merging |
| `space_id` | str | None | Chat space ID. Required only for API mode (no webhook) |
| `webhook_url` | str | None | Webhook URL. Defaults to `MCP_CHAT_WEBHOOK` env var |
| `thread_key` | str | None | Thread key for replies |"""

_QDRANT_SECTION = """\
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
- `mcp_gchat_cards_v8` — Card templates and feedback patterns"""

_CODE_MODE_HEADER = """\
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
| `semantic_search` | Full Qdrant vector search — semantic, DSL filters (`filter_dsl`), recommendation (`positive/negative_point_ids`), advanced queries (`query_dsl`, `prefetch_dsl`), and `dry_run` validation |
| `fetch_document` | Peek at a stored response by point ID (truncated preview) |
| `tool_activity` | Dashboard of tool usage — counts, error rates, sample IDs |
| `execute` | Run sandboxed Python code |"""

_JINJA_SECTION = """\
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

The `email_symbols` object is available as a Jinja2 global, providing \
symbol-to-class mappings for constructing DSL strings dynamically in macros."""

_RESOURCE_URIS_SECTION = """\
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
| `tools://list/all` | All available tools |"""

_SKILL_RESOURCES_SECTION = """\
## Skill Resources

| Resource | Content | When to Use |
|----------|---------|-------------|
| `skill://gchat-cards/` | 100+ component docs, symbols, containment rules, DSL syntax | Detailed card component field reference |
| `skill://mjml-email/` | Email block symbols, DSL syntax, per-component docs | Detailed email block field reference |"""

_MANAGE_TOOLS_SECTION = """\
## Tool Management

### `manage_tools`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `action` | str | required | `list`, `enable`, `disable`, `disable_all_except`, `enable_all` |
| `tool_names` | str/list | None | Tool name(s) — string, list, comma-separated, or JSON array |
| `scope` | str | "global" | `global` (all clients) or `session` (current client only) |
| `service_filter` | str | None | Filter by service: `gmail`, `chat`, `drive`, etc. |

**Protected tools** (cannot be disabled): `manage_tools`, `qdrant_search`, `health_check`, \
`start_google_auth`, `check_drive_auth`, and Code Mode meta-tools \
(`tags`, `search`, `get_schema`, `semantic_search`, `fetch_document`, `tool_activity`, `execute`)."""

_SERVICES_SECTION = """\
## All Services Quick Reference

Use `manage_tools(action="list")` or `manage_tools(action="list", service_filter="gmail")` \
to see currently active tools.

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
| **Code Mode** | `tags`, `search`, `get_schema`, `semantic_search`, `fetch_document`, `tool_activity`, `execute` |"""

_CROSS_CUTTING_SECTION = """\
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
- Collections: `mcp_tool_responses` (all responses), `mcp_gchat_cards_v8` (card templates + feedback)"""


# =============================================================================
# Dynamic sections — all DSL symbols come from the passed dicts at call time
# =============================================================================


def _email_symbol_table(email_symbols: Dict[str, str]) -> str:
    lines = [
        "**Email DSL Symbols:**\n",
        "| Symbol | Block |",
        "|--------|-------|",
    ]
    for name in EMAIL_BUILDING_BLOCKS:
        sym = email_symbols.get(name)
        if sym:
            lines.append(f"| `{sym}` | {name} |")
    return "\n".join(lines)


def _email_dsl_examples(email_symbols: Dict[str, str]) -> str:
    s = email_symbols
    spec = s.get("EmailSpec", "?")
    hero = s.get("HeroBlock", "?")
    text = s.get("TextBlock", "?")
    btn = s.get("ButtonBlock", "?")
    hdr = s.get("HeaderBlock", "?")
    cols = s.get("ColumnsBlock", "?")
    col = s.get("Column", "?")
    div = s.get("DividerBlock", "?")
    ftr = s.get("FooterBlock", "?")
    m = _MULT
    return "\n".join(
        [
            "**DSL Syntax:**",
            f"- `{spec}[{hero}, {text}]` — EmailSpec with HeroBlock and TextBlock",
            f"- `{spec}[{hdr}, {hero}, {text}{m}3, {btn}]` — Header, hero, 3 text blocks, button",
            f"- `{spec}[{hero}, {cols}[{col}{m}2], {btn}]` — Hero, 2-column layout, button",
            f"- `{spec}[{hdr}, {text}, {div}, {ftr}]` — Header, text, divider, footer",
        ]
    )


def _email_params_example(email_symbols: Dict[str, str]) -> str:
    s = email_symbols
    text = s.get("TextBlock", "?")
    btn = s.get("ButtonBlock", "?")
    lines = [
        "**Params Structure (`_shared`/`_items` merging):**",
        "```json",
        "{",
        '  "subject": "Weekly Report",',
        f'  "{text}": {{',
        '    "_shared": {"padding": "10px 25px"},',
        '    "_items": [',
        '      {"text": "Hello {{user://current/email.email}}"},',
        '      {"text": "Here is your report."}',
        "    ]",
        "  },",
        f'  "{btn}": {{',
        '    "_items": [',
        '      {"text": "View Report", "url": "https://example.com/report"}',
        "    ]",
        "  }",
        "}",
        "```",
    ]
    return "\n".join(lines)


def _email_full_example(email_symbols: Dict[str, str]) -> str:
    s = email_symbols
    spec = s.get("EmailSpec", "?")
    hdr = s.get("HeaderBlock", "?")
    hero = s.get("HeroBlock", "?")
    text = s.get("TextBlock", "?")
    btn = s.get("ButtonBlock", "?")
    lines = [
        "**Example — Simple email:**",
        "```",
        f"email_description: {spec}[{hdr}, {hero}, {text}, {btn}]",
        "email_params: {",
        '  "subject": "Meeting Reminder",',
        f'  "{hdr}": {{"_items": [{{"title": "Acme Corp"}}]}},',
        f'  "{hero}": {{"_items": [{{"title": "Team Standup", "subtitle": "Tomorrow at 10am"}}]}},',
        f'  "{text}": {{"_items": [{{"text": "Don\'t forget the standup meeting."}}]}},',
        f'  "{btn}": {{"_items": [{{"text": "Add to Calendar", "url": "https://calendar.google.com"}}]}}',
        "}",
        "```",
    ]
    return "\n".join(lines)


def _card_symbol_table(card_symbols: Dict[str, str]) -> str:
    lines = [
        "**Card DSL Symbols (primary building blocks):**\n",
        "| Symbol | Component |",
        "|--------|-----------|",
    ]
    for name in CARD_BUILDING_BLOCKS:
        sym = card_symbols.get(name)
        if sym:
            lines.append(f"| `{sym}` | {name} |")
    return "\n".join(lines)


def _card_dsl_examples(card_symbols: Dict[str, str]) -> str:
    s = card_symbols
    sec = s.get("Section", "?")
    dt = s.get("DecoratedText", "?")
    bl = s.get("ButtonList", "?")
    btn = s.get("Button", "?")
    grid = s.get("Grid", "?")
    gi = s.get("GridItem", "?")
    img = s.get("Image", "?")
    m = _MULT
    return "\n".join(
        [
            "**DSL Syntax:**",
            f"- `{sec}[{dt}]` — Section with one DecoratedText",
            f"- `{sec}[{dt}{m}3, {bl}[{btn}{m}2]]` — Section with 3 DecoratedTexts and 2 Buttons",
            f"- `{sec}[{grid}[{gi}{m}4]]` — Section with a 4-item Grid",
            f"- `{sec}[{dt}, {img}, {bl}[{btn}]]` — Section with text, image, and button",
        ]
    )


def _card_params_example(card_symbols: Dict[str, str]) -> str:
    s = card_symbols
    dt = s.get("DecoratedText", "?")
    btn = s.get("Button", "?")
    lines = [
        "**Context Consumption Pattern:**",
        "Widget content comes from `card_params` via symbol keys, NOT from inline text in "
        "`card_description`. The builder creates structure from DSL; content comes from "
        "context consumption.",
        "",
        "```json",
        "{",
        f'  "{dt}": {{',
        '    "_shared": {"top_label": "Status"},',
        '    "_items": [',
        '      {"text": "Build passed", "icon": "STAR"},',
        '      {"text": "Tests: 142/142"}',
        "    ]",
        "  },",
        f'  "{btn}": {{',
        '    "_items": [',
        '      {"text": "View Build", "url": "https://ci.example.com/build/123"}',
        "    ]",
        "  }",
        "}",
        "```",
    ]
    return "\n".join(lines)


def _code_mode_example(email_symbols: Dict[str, str]) -> str:
    s = email_symbols
    spec = s.get("EmailSpec", "?")
    hdr = s.get("HeaderBlock", "?")
    text = s.get("TextBlock", "?")
    div = s.get("DividerBlock", "?")
    ftr = s.get("FooterBlock", "?")
    dsl = f"{spec}[{hdr}, {text}, {div}, {ftr}]"
    lines = [
        "**Example — Chain tool calls:**",
        "```python",
        "# Fetch labels, then compose a report email",
        'labels = await call_tool("list_gmail_labels", {"user_google_email": "me@example.com"})',
        'label_count = len(labels.get("labels", []))',
        "",
        'await call_tool("compose_dynamic_email", {',
        f'    "email_description": "{dsl}",',
        '    "email_params": to_json({',
        '        "subject": f"Label Report - {today()}",',
        f'        "{hdr}": {{"_items": [{{"title": "Gmail Labels"}}]}},',
        f'        "{text}": {{"_items": [{{"text": f"You have {{label_count}} labels."}}]}},',
        f'        "{ftr}": {{"_items": [{{"text": f"Generated {{now()}}"}}]}}',
        "    }),",
        '    "action": "draft"',
        "})",
        'return f"Draft created with {label_count} labels"',
        "```",
    ]
    return "\n".join(lines)


# =============================================================================
# Public API
# =============================================================================


def generate_server_skill(
    card_symbols: Dict[str, str],
    email_symbols: Dict[str, str],
) -> SkillDocument:
    """Generate the server-level SKILL.md for google-workspace-mcp.

    Args:
        card_symbols: Component name -> symbol mapping from the card_framework wrapper.
            Keys are component names (e.g. "Section"); values are the assigned symbols.
        email_symbols: Block name -> symbol mapping from the email/mjml_types wrapper.

    Returns:
        SkillDocument with the complete SKILL.md content.
    """
    parts = [
        _FRONTMATTER,
        "",
        _OVERVIEW,
        "",
        "## Core Wrapped Tools",
        "",
        "### `compose_dynamic_email` — MJML Email Composer",
        "",
        "Composes responsive HTML emails via DSL notation, then sends or saves as draft.",
        "",
        _EMAIL_PARAMS_TABLE,
        "",
        _email_symbol_table(email_symbols),
        "",
        _email_dsl_examples(email_symbols),
        "",
        _email_params_example(email_symbols),
        "",
        _email_full_example(email_symbols),
        "",
        "**For detailed component field reference:** Use `skill://mjml-email/` resources "
        "(15 component docs, symbols, containment rules).",
        "",
        "---",
        "",
        "### `send_dynamic_card` — Google Chat Card Builder",
        "",
        "Sends a card to Google Chat using DSL notation for structure control.",
        "",
        _CARD_PARAMS_TABLE,
        "",
        _card_symbol_table(card_symbols),
        "",
        _card_dsl_examples(card_symbols),
        "",
        _card_params_example(card_symbols),
        "",
        "**Session-scope enable required:** This tool often needs session-scope enablement:",
        "```",
        'manage_tools(action="enable", tool_names="send_dynamic_card", scope="session")',
        "```",
        "After session enable, must `/mcp` reconnect for Claude Code to discover the tool.",
        "",
        "**For detailed component field reference:** Use `skill://gchat-cards/` resources "
        "(symbols, DSL syntax, 100+ component docs).",
        "",
        "---",
        "",
        _QDRANT_SECTION,
        "",
        "---",
        "",
        _CODE_MODE_HEADER,
        "",
        _code_mode_example(email_symbols),
        "",
        "---",
        "",
        _JINJA_SECTION,
        "",
        "---",
        "",
        _RESOURCE_URIS_SECTION,
        "",
        "---",
        "",
        _SKILL_RESOURCES_SECTION,
        "",
        "---",
        "",
        _MANAGE_TOOLS_SECTION,
        "",
        "---",
        "",
        _SERVICES_SECTION,
        "",
        "---",
        "",
        _CROSS_CUTTING_SECTION,
        "",
    ]

    content = "\n".join(parts)

    return SkillDocument(
        name="SKILL",
        title="Google Workspace MCP Server",
        description=(
            "Guide for using the Google Workspace MCP server — "
            "DSL notation, code mode, macros, and tools across 11+ Google services"
        ),
        content=content,
        tags={"google-workspace-mcp", "skill"},
    )


def write_server_skill(
    output_dir: Path,
    card_wrapper: "ModuleWrapper",
    email_wrapper: "ModuleWrapper",
) -> Path:
    """Generate and write the server-level SKILL.md.

    Args:
        output_dir: Base skills directory; the skill subdirectory is created inside it.
        card_wrapper: Initialized ModuleWrapper for card_framework.
        email_wrapper: Initialized ModuleWrapper for gmail.mjml_types.

    Returns:
        Path to the google-workspace-mcp skill directory.
    """
    doc = generate_server_skill(
        card_symbols=card_wrapper.symbol_mapping or {},
        email_symbols=email_wrapper.symbol_mapping or {},
    )
    skill_dir = Path(output_dir) / "google-workspace-mcp"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        doc.content, encoding="utf-8"
    )
    logger.info(
        "Generated server skill: %s", skill_dir / "SKILL.md"
    )
    return skill_dir
