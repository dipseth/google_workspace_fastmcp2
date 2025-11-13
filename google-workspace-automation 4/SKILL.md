---
name: google-workspace-automation
description: Master skill for automating Google Workspace with the RiversUnlimited MCP. Use when working with Gmail, Drive, Calendar, Docs, Sheets, Forms, Slides, Chat, or Photos. Includes 96+ tools, Qdrant semantic search, Jinja2 templates with 9+ macros, URI-based fast access, and cross-service workflow automation. Trigger on Google Workspace automation, email workflows, calendar management, document generation, template creation, semantic search, analytics, or multi-service integration tasks.
---

# Google Workspace Automation Skill

## Overview

This skill enables comprehensive automation and integration across all Google Workspace services using the RiversUnlimited MCP framework. It provides access to 96+ specialized tools, semantic search with Qdrant vector database, beautiful template generation with Jinja2 macros, and lightning-fast URI-based resource access.

## Core Capabilities

### 1. Multi-Service Tool Access

**72+ Tools across 9 Services:**
- **Gmail** (22 tools): Email management, search, compose, threading, labels, filters, bulk operations
- **Drive** (8 tools): File storage, sharing, advanced search, batch operations  
- **Calendar** (9 tools): Event management, bulk operations, timezone handling
- **Docs** (4 tools): Document creation with multi-format support (HTML, Markdown, RTF, DOCX, LaTeX)
- **Sheets** (6 tools): Spreadsheet creation, data manipulation, comprehensive formatting
- **Forms** (12 tools): Survey creation, dynamic questions, response analytics
- **Slides** (5 tools): Presentation creation, content updates, multi-format export
- **Chat** (5 tools): Google Chat integration with rich cards, interactive elements
- **Photos** (11 tools): Photo management, album operations, smart search

### 2. Qdrant Semantic Search

**Vector Database Integration** for intelligent context retrieval:
- Natural language search across all tool responses
- Service-specific filtering and analytics
- Historical tool response analysis
- Automated data cleanup with configurable retention

**See:** [references/qdrant-workflows.md](references/qdrant-workflows.md) for complete patterns

### 3. Jinja2 Template System

**9+ Pre-Built Macros** for beautiful, token-efficient output:
- `render_gmail_labels_chips` - Visual Gmail label dashboards
- `generate_report_doc` - Comprehensive report generation
- `generate_meeting_notes_doc` - Meeting notes templates
- `render_calendar_dashboard` - Calendar visualizations
- `render_beautiful_email1` - Styled HTML emails
- `render_gmail_filters_dashboard` - Email organization insights
- **Dynamic macro creation** at runtime with persistent storage

**See:** [references/template-patterns.md](references/template-patterns.md) for complete guide

### 4. URI-Based Fast Access

**30x Faster** than traditional API calls:
- `service://gmail/labels` - Instant label access
- `service://calendar/events` - Quick event retrieval
- `user://current/email` - Current user context
- Cached, session-persistent, automatic refresh

**See:** [references/uri-resources.md](references/uri-resources.md) for all URI patterns

## When to Use This Skill

**Trigger this skill for:**
- Google Workspace automation tasks
- Email workflows and Gmail management
- Calendar event management and scheduling
- Document creation and generation
- Cross-service integrations (Email → Drive → Calendar)
- Template and macro creation
- Semantic search across workspace activities
- Analytics and reporting on tool usage
- Bulk operations across any Google service

## Google Docs HTML Formatting

### HTML Support in Google Docs (2025)

Google Docs has **limited but functional** HTML support. It's fundamentally a word processor, not a web browser, so advanced CSS features are not supported.

#### ✅ What WORKS in Google Docs

- **Basic HTML tags**: `<h1>`-`<h6>`, `<p>`, `<b>`, `<i>`, `<u>`, `<a>`, `<ul>`, `<ol>`, `<li>`
- **HTML tables**: Best method for layout control
- **Inline styles**: More reliable than CSS classes
- **Solid colors**: `background-color`, `color` (text)
- **Basic formatting**: `font-size`, `padding`, `border`
- **Text alignment**: `text-align` (left, center, right)
- **Font families**: Standard web fonts

#### ❌ What DOESN'T WORK in Google Docs

- **CSS gradients**: `linear-gradient`, `radial-gradient` - stripped out
- **Box shadows**: `box-shadow` property ignored
- **Flexbox/Grid**: Modern CSS layout systems not supported
- **Backdrop filters**: blur effects don't work
- **Advanced positioning**: `absolute`, `fixed`, `sticky` ignored
- **CSS animations**: No support for keyframes or transitions
- **External CSS files**: Must use inline styles
- **CSS classes**: Often stripped - inline styles more reliable
- **Complex selectors**: Pseudo-classes, pseudo-elements ignored

### Best Practices for HTML Documents

#### 1. Use HTML Tables for Layout

Tables are the **most reliable** way to control layout in Google Docs:

```html
<!-- ✅ GOOD: Table-based layout -->
<table width="100%" cellpadding="20" style="background-color: #dbeafe; margin: 20px 0;">
  <tr>
    <td>
      <h2 style="color: #1e40af; font-size: 24px;">Section Title</h2>
      <p style="color: #1e40af; font-size: 16px; line-height: 1.8;">
        Your content here...
      </p>
    </td>
  </tr>
</table>

<!-- ❌ BAD: Flexbox layout -->
<div style="display: flex;">
  <div style="flex: 0.3;">Left</div>
  <div style="flex: 0.7;">Right</div>
</div>
```

#### 2. Use Inline Styles, Not CSS Classes

CSS classes are often stripped out. **Always use inline style attributes**:

```html
<!-- ✅ DO THIS -->
<p style="color: #1e40af; font-size: 18px; font-weight: bold;">Text</p>

<!-- ❌ DON'T DO THIS -->
<p class="heading">Text</p>
```

#### 3. Stick to Solid Colors

Gradients, shadows, and fancy effects don't work:

```html
<!-- ✅ Solid colors work -->
<div style="background-color: #dbeafe; padding: 20px;">Content</div>

<!-- ❌ Gradients are stripped -->
<div style="background: linear-gradient(to right, #dbeafe, #1e40af);">Content</div>
```

#### 4. Two-Column Layout Template

```html
<table width="100%" cellpadding="15">
  <tr>
    <td style="width: 50%; vertical-align: top; padding: 15px;">
      <h3>Left Column</h3>
      <p>Content...</p>
    </td>
    <td style="width: 50%; vertical-align: top; padding: 15px; border-left: 2px solid #cbd5e1;">
      <h3>Right Column</h3>
      <p>Content...</p>
    </td>
  </tr>
</table>
```

#### 5. Bordered Info Box Template

```html
<table width="100%" cellpadding="15" style="background-color: #f0fdf4; border: 3px solid #22c55e; margin: 20px 0;">
  <tr>
    <td>
      <h3 style="color: #15803d; font-size: 20px;">✅ Important Info</h3>
      <p style="color: #166534; font-size: 15px; line-height: 1.6;">
        Your important message here...
      </p>
    </td>
  </tr>
</table>
```

### Document Size Limits

- **1.02 million characters** maximum per document
- **50 MB maximum** when converting from text/html to Google Doc format
- Large tables can cause performance issues
- Complex nested tables may slow down rendering

### HTML Tags Support Matrix

| HTML Tag | Support | Notes |
|----------|---------|-------|
| `<h1>` - `<h6>` | ✅ Full | Preserved with appropriate sizing |
| `<p>` | ✅ Full | Paragraph support complete |
| `<b>`, `<strong>` | ✅ Full | Bold text works perfectly |
| `<i>`, `<em>` | ✅ Full | Italic text works perfectly |
| `<u>` | ✅ Full | Underline supported |
| `<a>` | ✅ Full | Links work, retain href attribute |
| `<table>` | ✅ Full | Best layout tool available |
| `<ul>`, `<ol>`, `<li>` | ⚠️ Partial | Works but nested lists can be tricky |
| `<img>` | ⚠️ Partial | Images imported but sizing/alignment may need adjustment |
| `<div>` | ❌ Limited | Converted to paragraphs, no layout control |
| `<span>` | ⚠️ Partial | Some styling retained, inconsistent |

### CSS Properties Support Matrix

| CSS Property | Support | Notes |
|--------------|---------|-------|
| `color` | ✅ | Hex, RGB, named colors all work |
| `background-color` | ✅ | Solid colors only, no gradients |
| `font-size` | ✅ | px, pt, em all work |
| `font-family` | ✅ | Standard web fonts work |
| `font-weight` | ✅ | bold, normal work well |
| `text-align` | ✅ | left, center, right, justify |
| `padding` | ✅ | Works in tables and cells |
| `border` | ✅ | Basic borders work (solid style best) |
| `width`, `height` | ✅ | px and % work on tables |
| `line-height` | ✅ | Controls text spacing |
| `background` (gradient) | ❌ | linear-gradient, radial-gradient stripped |
| `box-shadow` | ❌ | Not supported, removed entirely |
| `text-shadow` | ❌ | Not supported |
| `display` (flex/grid) | ❌ | Modern layout systems not supported |
| `position` (absolute/fixed) | ❌ | Not supported |
| `transform` | ❌ | rotate, scale, etc. not supported |
| `animation`, `transition` | ❌ | No animation support |
| `opacity` | ❌ | Not reliably supported |

## Google Chat Message Formatting

### Text Formatting in Chat Messages

Google Chat supports basic text formatting using Markdown syntax. Text messages are formatted differently than card messages.

#### Formatting Syntax

| Format | Symbol | Example Syntax | Result |
|--------|--------|----------------|--------|
| **Bold** | `**` | `**hello**` | **hello** |
| *Italic* | `_` (underscore) | `_hello_` | *hello* |
| ~~Strikethrough~~ | `~~` | `~~hello~~` | ~~hello~~ |
| `Monospace` | `` ` `` (backquote) | `` `hello` `` | `hello` |
| Monospace block | ``` (three backquotes) | ` ```Hello World``` ` | ```Hello World``` |
| Bulleted list | `*` or `-` + space | `* Item 1`<br>`* Item 2` | • Item 1<br>• Item 2 |
| Hyperlink | `<url\|text>` | `<https://example.com\|Link>` | [Link](https://example.com) |
| Mention user | `<users/{id}>` | `<users/123>` | @User |

#### Chat Message Examples

**Simple formatted message:**
```python
riversunlimited:send_message(
    space_id="space_id",
    message_text="Your pizza delivery *has arrived*!\nThank you for using _Cymbal Pizza!_"
)
```

**Message with bullet points:**
```python
riversunlimited:send_message(
    space_id="space_id",
    message_text="""Project Update:
* Design phase completed
* Development in progress
* Testing scheduled for next week"""
)
```

**Message with code block:**
```python
riversunlimited:send_message(
    space_id="space_id",
    message_text="""Here's the API response:
```
{
  "status": "success",
  "data": {...}
}
```"""
)
```

**Message with hyperlinks:**
```python
riversunlimited:send_message(
    space_id="space_id",
    message_text="Check out the <https://docs.google.com|documentation> for more details."
)
```

### Chat Cards Formatting

For rich card messages, use the card-specific tools:

```python
# Simple card with buttons
riversunlimited:send_interactive_card(
    space_id="space_id",
    title="Task Status",
    text="Your task is ready for review.",
    buttons=[
        {"text": "Approve", "url": "https://example.com/approve"},
        {"text": "Reject", "url": "https://example.com/reject"}
    ]
)

# Form card for data collection
riversunlimited:send_form_card(
    space_id="space_id",
    title="Feedback Form",
    fields=[
        {"name": "rating", "label": "Rating", "type": "dropdown"},
        {"name": "comments", "label": "Comments", "type": "textarea"}
    ],
    submit_action={"function": "submit_feedback"}
)
```

### Chat Best Practices

1. **Use text formatting** for emphasis rather than all caps
2. **Keep messages concise** - break long messages into multiple sends or use cards
3. **Use bullet points** for lists - easier to read than numbered lists in chat
4. **Include hyperlinks** for external resources rather than raw URLs
5. **Use monospace** for code snippets or technical terms
6. **Mention users** when you need their attention with `<users/{id}>`
7. **Use cards** for structured data, forms, or interactive elements
8. **Avoid excessive formatting** - too much bold/italic reduces readability

## Quick Start Patterns

### Email Automation

```python
# Search emails
results = riversunlimited:search_gmail_messages(
    query="is:unread newer_than:7d",
    page_size=20
)

# Get full content in batch
content = riversunlimited:get_gmail_messages_content_batch(
    message_ids=message_ids
)

# Apply labels
riversunlimited:modify_gmail_message_labels(
    message_id=msg_id,
    add_label_ids=["processed"]
)
```

### Document Generation with Templates

```python
# Create custom macro
riversunlimited:create_template_macro(
    macro_name="status_report",
    macro_content="""{% macro status_report(data) %}
<table width="100%" cellpadding="20" style="background-color: #dbeafe;">
  <tr>
    <td>
      <h1 style="color: #1e40af;">{{ data.title }}</h1>
      {{ dashboard_card("Tasks", data.tasks_count, data.trend) }}
    </td>
  </tr>
</table>
{% endmacro %}""",
    persist_to_file=true
)

# Use in document
doc = riversunlimited:create_doc(
    title="Weekly Status",
    content="{{ status_report(data) }}",
    content_mime_type="text/html"
)
```

### Semantic Search

```python
# Search historical context
context = riversunlimited:search(
    query="project discussions with deadlines",
    limit=10
)

# Fetch full details
details = riversunlimited:fetch(
    point_id=context.results[0].id
)

# Get analytics
analytics = riversunlimited:get_tool_analytics(
    summary_only=true,
    group_by="tool_name"
)
```

### Calendar Management

```python
# Get upcoming events
events = riversunlimited:list_events(
    calendar_id="primary",
    max_results=10
)

# Create multiple events in batch
riversunlimited:create_event(
    events=[
        {
            "summary": "Meeting 1",
            "start_time": "2025-10-20T10:00:00Z",
            "end_time": "2025-10-20T11:00:00Z"
        },
        {
            "summary": "Meeting 2",
            "start_time": "2025-10-20T14:00:00Z",
            "end_time": "2025-10-20T15:00:00Z"
        }
    ]
)
```

### Chat Automation

```python
# Send formatted status update to Chat
riversunlimited:send_message(
    space_id="space_id",
    message_text="""*Daily Standup Update*
_Status: On Track_

*Completed:*
* Feature A implementation
* Bug fixes for module B

*In Progress:*
* Testing feature C
* Documentation updates

*Blockers:*
* Waiting on API key for service D

Full details: <https://docs.example.com/status|Status Report>"""
)

# Or send as a rich card
riversunlimited:send_simple_card(
    space_id="space_id",
    title="Daily Standup",
    subtitle="Status: On Track",
    text="All tasks progressing as planned. Check the link for full details.",
    image_url="https://example.com/status-icon.png"
)
```

## Cross-Service Workflows

For multi-service automation recipes including:
- Email → Drive (save attachments)
- Calendar → Email (meeting prep)
- Drive → Email (review reminders)
- Forms → Sheets → Email (survey processing)
- Chat → Drive → Email (notification workflows)
- Full workspace dashboards

**See:** [references/cross-service-recipes.md](references/cross-service-recipes.md) for 12+ proven recipes

## Tool Categories

### Authentication & Health
- `start_google_auth` - OAuth2 authentication with PKCE
- `check_drive_auth` - Verify authentication status
- `health_check` - System health and configuration

### Qdrant Search & Analytics
- `search` - Natural language semantic search
- `fetch` - Retrieve complete documents by ID
- `search_tool_history` - Advanced tool response search
- `get_tool_analytics` - Usage statistics and patterns
- `cleanup_qdrant_data` - Manual data cleanup

### Template System
- `create_template_macro` - Dynamic macro creation with persistence
- All pre-built macros accessible via template syntax

### Gmail (22 tools)
Message operations, search, compose, reply, forward, threading, labels, filters, bulk operations, allow-list management

### Drive (8 tools)
Search, upload, list, content retrieval, sharing, permissions, file management

### Calendar (9 tools)
List/create/modify/delete events, bulk operations, cross-calendar migrations

### Docs (4 tools)
- `create_doc` - Create/edit documents with HTML, Markdown, RTF, DOCX, LaTeX support
- `get_doc_content` - Retrieve document content
- `search_docs` - Search for documents by name
- `list_docs_in_folder` - List documents in a folder

**Important:** When creating Docs with HTML content, always follow the HTML best practices above (table-based layouts, inline styles, solid colors only).

### Sheets (6 tools)
Spreadsheet creation, data manipulation, comprehensive formatting

### Forms (12 tools)
Survey creation, dynamic questions, response analytics

### Slides (5 tools)
Presentation creation, content updates, multi-format export

### Chat (5 tools)
- `send_message` - Send formatted text messages
- `send_simple_card` - Simple card with title, text, image
- `send_interactive_card` - Card with interactive buttons
- `send_form_card` - Card with form fields
- `send_rich_card` - Advanced card with multiple sections

### Photos (11 tools)
Album management, smart search, batch operations

## Reference Files

All reference files contain comprehensive workflows, patterns, and examples:

1. **qdrant-workflows.md** - Semantic search patterns, analytics, audit trails
2. **template-patterns.md** - Macro creation, design patterns, styling guides
3. **uri-resources.md** - Fast URI-based access, performance optimization
4. **cross-service-recipes.md** - 12+ multi-service automation workflows

## Best Practices

### 1. Progressive Loading

Read reference files when needed:
- Qdrant operations → Read qdrant-workflows.md
- Template creation → Read template-patterns.md
- Multi-service tasks → Read cross-service-recipes.md
- URI usage → Read uri-resources.md

### 2. Batch Operations

Use batch tools for efficiency:
- `get_gmail_messages_content_batch` instead of loops
- Bulk event creation with `events` parameter
- Batch label modifications

### 3. Leverage URIs

Use URIs in templates for 30x speed improvement:
```jinja2
{{ service://gmail/labels | length }}
```
Instead of calling `list_gmail_labels()` every time.

### 4. Semantic Search

Use Qdrant to build context from historical operations:
```python
# Find relevant past context
context = riversunlimited:search(query="similar project discussions")
# Use to inform current work
```

### 5. Template Reuse

Create macros once, use everywhere:
```python
# Create persistent macro
create_template_macro(..., persist_to_file=true)
# Available in all future sessions
```

### 6. HTML Document Creation

When creating HTML documents in Google Docs:
- Always use table-based layouts, never flexbox or grid
- Use inline styles only, not CSS classes
- Stick to solid colors, avoid gradients
- Keep documents under 50 MB and 1.02M characters
- Test complex layouts before deployment

### 7. Chat Message Formatting

When sending Chat messages:
- Use Markdown for text formatting
- Keep messages concise and scannable
- Use bullet points for lists
- Include hyperlinks for references
- Use cards for structured or interactive content
- Avoid over-formatting

## Performance Tips

- **URI access:** 30x faster than API calls for cached data
- **Batch operations:** Process multiple items in single request
- **Template macros:** 60-80% token reduction vs manual formatting
- **Qdrant search:** Instant retrieval vs sequential API calls
- **Compression:** 37.7% average data compression in storage
- **HTML tables:** More reliable than CSS layouts for Docs
- **Inline styles:** Faster rendering than CSS classes

## Error Handling

All tools automatically log to Qdrant for audit trail. Use semantic search to investigate issues:

```python
# Find errors
riversunlimited:search_tool_history(query="error failed")

# Get details
details = riversunlimited:fetch(point_id=error_point_id)
```

## Security Features

- OAuth 2.1 + PKCE for enterprise-grade authentication
- Email elicitation support with allow-list management
- Complete audit trail via Qdrant
- Configurable data retention policies
- Per-user session isolation

## Production Usage

The system has proven reliability:
- 0.0% error rate in production tracking
- 61+ operations successfully logged
- 20+ tool types in active use
- Multi-session support with 12+ concurrent sessions
- Automatic cleanup maintaining performance

## Known Limitations

### Google Docs
- No CSS gradients or box shadows
- No flexbox or grid layouts
- No advanced positioning (absolute, fixed)
- No CSS animations
- Large tables may impact performance

### Google Chat
- Text formatting limited to Markdown subset
- Card complexity limited by Chat UI
- Interactive elements require webhook configuration
- Message length limits apply

### General
- API rate limits may affect bulk operations
- Large file operations may be slow
- Some formatting may be lost in cross-service operations

## Next Steps

1. Identify automation need
2. Check cross-service-recipes.md for similar pattern
3. Review formatting guidelines for Docs and Chat
4. Use tools directly or compose new workflow
5. Create custom macros for repeated formatting
6. Use Qdrant search to learn from past operations
7. Share patterns back to expand recipe library
