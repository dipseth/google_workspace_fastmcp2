# 🚀 GoogleUnlimited Google Workspace Platform

**GoogleUnlimited** is a comprehensive MCP framework that provides seamless Google Workspace integration through an advanced middleware architecture. It enables AI assistants and MCP clients to interact with Gmail, Google Drive, Docs, Sheets, Slides, Calendar, Forms, Chat, and Photos services using a unified, secure API.

## 📋 Table of Contents

- [Quick Installation Instructions](#-quick-installation-instructions)
- [Service Capabilities](#-service-capabilities)
- [Middleware Architecture](#-middleware-architecture)
- [Template System](#-template-system)
- [Resource Discovery](#-resource-discovery)
- [Testing Framework](#-testing-framework)
- [Security & Authentication](#-security--authentication)

## ⚡ Quick Installation Instructions

### What is GoogleUnlimited?

GoogleUnlimited provides AI assistants with access to Google Workspace services through the Model Context Protocol (MCP). It supports **90+ tools** across **9 Google services**, enabling seamless integration between AI workflows and Google Workspace applications with revolutionary performance improvements.

```mermaid
graph TB
    subgraph "🤖 AI Assistant"
        A[Claude/GPT/Other]
    end
    
    subgraph "🌉 GoogleUnlimited MCP Framework"
        B[MCP Protocol]
        C[Unified Middleware]
        D[OAuth 2.1 + PKCE]
    end
    
    subgraph "☁️ Google Workspace"
        E[📧 Gmail]
        F[📁 Drive]
        G[📊 Sheets]
        H[📄 Docs]
        I[🎯 Slides]
        J[📅 Calendar]
        K[📝 Forms]
        L[💬 Chat]
        M[📷 Photos]
    end
    
    A --> B
    B --> C
    C --> D
    D --> E
    D --> F
    D --> G
    D --> H
    D --> I
    D --> J
    D --> K
    D --> L
    D --> M
    
    style A fill:#e1f5fe
    style C fill:#f3e5f5
    style D fill:#e8f5e8
```

### 🛠️ Installation Steps

1. **Clone and setup:**
   ```bash
   git clone https://github.com/dipseth/google_workspace_fastmcp2.git
   cd google_workspace_fastmcp2
   uv sync
   ```

2. **Configure Google OAuth:**
   - Visit [Google Cloud Console](https://console.cloud.google.com/) 🔗
   - Enable APIs: Gmail, Drive, Docs, Sheets, Slides, Calendar, Forms, Chat, Photos
   - Create OAuth 2.0 credentials (Web application type)
   - Download client secrets JSON file

3. **Setup environment:**
   ```bash
   cp .env.example .env
   # Edit .env with your Google OAuth credentials path
   ```

4. **Start the server:**
   ```bash
   uv run python server.py
   ```

> 📚 **Configuration Resources:**
> - 🔧 **[Complete Configuration Guide](documentation/config/CONFIGURATION_GUIDE.md)** - Comprehensive environment variables and settings reference
> - 🤖 **[Claude.ai Integration Guide](documentation/config/claude_ai_integration_guide.md)** - Setup for Claude.ai remote MCP server usage
> - 🔒 **[HTTPS Setup Guide](documentation/config/https_setup_guide.md)** - SSL certificate configuration for secure connections
> - ⚙️ **[MCP JSON Configuration Guide](documentation/config/mcp_config_fastmcp.md)** - Standard MCP configuration for any compatible client

## 🔗 Client Connections

GoogleUnlimited supports multiple connection methods. Here are the two most popular ways to get started:

### 🎯 Quick Setup Options

**Option 1: Cursor IDE** (STDIO - Community Verified ✅):
```json
{
  "mcpServers": {
    "google-workspace": {
      "command": "uv",
      "args": [
        "--directory", "/path/to/google_workspace_fastmcp2",
        "run", "python", "server.py"
      ],
      "env": {
        "GOOGLE_CLIENT_SECRETS_FILE": "/path/to/client_secrets.json",
        "MCP_TRANSPORT": "stdio"
      }
    }
  }
}
```

**Option 2: HTTP Streamable** (VS Code Roo, Claude Desktop, etc.):
```bash
# 1. Start server in HTTP mode
uv run python server.py --transport http --port 8002

# 2. Configure your client with:
```
```json
{
  "rivers_unlimited": {
    "type": "streamable-http",
    "url": "https://localhost:8002/mcp",
    "disabled": false
  }
}
```

### 📚 Complete Connection Guide

For detailed setup instructions, troubleshooting, and configurations for all supported clients including:
- Claude Code CLI (HTTP & STDIO)
- Claude Desktop
- VS Code/GitHub Copilot
- Claude.ai with Cloudflare Tunnel
- And more...

> 🔗 **[Complete Client Connection Guide](documentation/config/MCP_CLIENT_CONNECTIONS.md)** - Comprehensive setup instructions, troubleshooting, and advanced configurations for all supported AI clients and development environments

## 🎯 Service Capabilities

GoogleUnlimited supports **9 Google Workspace services** with **90+ specialized tools**:

| Service | Icon | Tools | Key Features | Documentation |
|---------|------|-------|--------------|---------------|
| **Gmail** | 📧 | 14 | Send, reply, labels, filters, search, allowlist | [`api-reference/gmail/`](documentation/api-reference/gmail/) |
| **Drive** | 📁 | 9 | Upload, download, sharing, Office docs, file management | [`api-reference/drive/`](documentation/api-reference/drive/) |
| **Docs** | 📄 | 4 | Create, edit, format, batch operations | [`api-reference/docs/`](documentation/api-reference/docs/) |
| **Sheets** | 📊 | 7 | Read, write, formulas, formatting | [`api-reference/sheets/`](documentation/api-reference/sheets/) |
| **Slides** | 🎯 | 5 | Presentations, templates, export | [`api-reference/slides/`](documentation/api-reference/slides/) |
| **Calendar** | 📅 | 9 | Events, scheduling, attendees, timezones | [`api-reference/calendar/`](documentation/api-reference/calendar/) |
| **Forms** | 📝 | 8 | Creation, responses, validation, publishing | [`api-reference/forms/`](documentation/api-reference/forms/) |
| **Chat** | 💬 | 24 | Messaging, cards, spaces, webhooks, unified cards | [`api-reference/chat/`](documentation/api-reference/chat/) |
| **Photos** | 📷 | 12 | Albums, upload, search, metadata, smart search | [`api-reference/photos/`](documentation/api-reference/photos/) |

> 📚 **API Documentation Resources:**
> - 🔗 **[Complete API Reference](documentation/api-reference/)** - Comprehensive documentation for all 90+ tools across 9 services
> - 📧 **[Gmail API Guide](documentation/api-reference/gmail/)** - Email management, labels, filters, and search operations
> - 📁 **[Drive API Guide](documentation/api-reference/drive/)** - File operations, sharing, and Office document handling
> - 📊 **[Sheets API Guide](documentation/api-reference/sheets/)** - Spreadsheet data manipulation and formatting
> - 📅 **[Calendar API Guide](documentation/api-reference/calendar/)** - Event scheduling and timezone management

## 🧠 Middleware Architecture

GoogleUnlimited uses a middleware architecture that provides seamless service integration, intelligent resource management, and powerful templating capabilities.

```mermaid
graph TD
    A[🔄 MCP Request] --> B[🏷️ TagBasedResourceMiddleware]
    B --> C[🧠 QdrantUnifiedMiddleware]
    C --> D[🎨 TemplateMiddleware]
    D --> E[⚡ Tool Execution]
    E --> F[📊 Response Processing]
    F --> G[✨ Formatted Output]
    
    B --> H[📋 Resource Discovery<br/>service://gmail/labels<br/>user://current/profile]
    C --> I[🔍 Semantic Search<br/>Vector Embeddings<br/>Natural Language Queries]
    D --> J[🎯 Template Rendering<br/>Gmail Chips<br/>Dashboard Cards]
    
    style B fill:#e3f2fd
    style C fill:#f3e5f5
    style D fill:#e8f5e8
    style E fill:#fff3e0
```

### 🔧 Core Middleware Components

- **🏷️ TagBasedResourceMiddleware**: Intelligent resource discovery using URI patterns (`service://gmail/messages`, `user://current/email`)
- **🧠 QdrantUnifiedMiddleware**: AI-powered semantic search across all tool responses with vector embeddings
- **🎨 TemplateMiddleware**: Advanced Jinja2 template system for beautiful, structured output formatting

### ✨ Architecture Benefits

- **🔄 Unified Resource Access**: URI-based access to service data without API calls
- **🧠 Semantic Intelligence**: Natural language search across all stored responses
- **🎨 Visual Excellence**: Consistent, beautiful output formatting for optimal AI consumption
- **💰 Token Efficiency**: Template macros reduce token usage by 60-80% through structured data rendering
- **⚡ Performance**: 30x faster than traditional approaches through intelligent caching

> 📚 **Middleware Documentation Resources:**
> - 📖 **[Middleware Architecture Guide](documentation/middleware/)** - Complete middleware system documentation and implementation details
> - 🏷️ **[TagBasedResourceMiddleware](documentation/middleware/)** - URI pattern resource discovery and management
> - 🧠 **[QdrantUnifiedMiddleware](documentation/middleware/)** - AI-powered semantic search and vector embeddings
> - 🎨 **[TemplateMiddleware](documentation/middleware/)** - Advanced Jinja2 template system for output formatting

## 🎨 Template System

GoogleUnlimited features powerful **Jinja2 template macros** that transform raw Google Workspace data into visually stunning, AI-optimized formats.

### 🎯 Available Template Macros

| Template File | Macro | Purpose | Key Features |
|---------------|-------|---------|--------------|
| **`email_card.j2`** | `render_gmail_labels_chips()` | Gmail label visualization | Interactive chips, unread counts, direct Gmail links |
| **`calendar_dashboard.j2`** | `render_calendar_dashboard()` | Calendar & events dashboard | Primary/shared calendars, upcoming events, dark theme |
| **`dynamic_macro.j2`** | `render_calendar_events_dashboard()` | Calendar events dashboard | Event cards, time/location details, clickable links, dark theme |
| **`document_templates.j2`** | `generate_report_doc()` | Professional reports | Metrics, tables, charts, company branding |
| **`colorfuL_email.j2`** | `render_beautiful_email3()` | Rich HTML emails | Multiple signatures, gradients, responsive design |

### 💡 Template Macro Examples

**Gmail Labels Visualization** - Transform label lists into beautiful interactive chips:

```jinja2
{{ render_gmail_labels_chips( service://gmail/labels , 'Label summary for: ' + user://current/email ) }}
```

**Calendar Dashboard** - Create comprehensive calendar overviews:

```jinja2
{{ render_calendar_dashboard( service://calendar/calendars, service://calendar/events, 'My Calendar Overview' ) }}
```

**Calendar Events Dashboard** - Transform calendar events into beautiful, interactive event cards:

```jinja2
{{ render_calendar_events_dashboard( service://calendar/events , 'Upcoming Events for: ' + user://current/email.email ) }}
```

![Calendar Events Dashboard Example](prompt_to_dashboard.png)

This macro creates a stunning dark-themed dashboard featuring:
- 📅 **Interactive Event Cards**: Each event is rendered as a clickable card that opens in Google Calendar
- 🕐 **Smart Time Display**: Automatically formats all-day events vs. timed events with timezone support
- 📍 **Location Integration**: Displays meeting locations and virtual meeting links
- 👥 **Attendee Information**: Shows attendee counts and participant details
- ✅ **Status Indicators**: Color-coded status (confirmed, tentative, cancelled) with visual feedback
- 📱 **Responsive Design**: Mobile-optimized layout with touch-friendly interactions
- 🎨 **Dark Theme Styling**: Professional appearance with gradient backgrounds and hover effects

**Professional Documents** - Generate reports with metrics and charts:

```jinja2
{{ generate_report_doc(
    report_title='Q4 Performance Report',
    metrics=[{'value': '$1.2M', 'label': 'Revenue', 'change': 15}],
    company_name='Your Company'
) }}
```

### 🔍 Macro Discovery & Dynamic Creation

Explore all available macros using the template resource system:

```python
# Access the template://macros resource to discover all available macros
macros = await access_resource("template://macros")
# Returns comprehensive macro information with usage examples

# Access specific macro details
macro_details = await access_resource("template://macros/render_gmail_labels_chips")
```

### 🎯 Dynamic Macro Creation

Create custom macros at runtime using the `create_template_macro` tool:

```python
# Create a new macro dynamically
await create_template_macro(
    macro_name="render_task_status_badge",
    macro_content='''
    {% macro render_task_status_badge(status, size='small') %}
    {% if status == 'completed' %}
    <span class="status-badge status-completed {{ size }}">✅ Complete</span>
    {% elif status == 'in_progress' %}
    <span class="status-badge status-in-progress {{ size }}">🔄 In Progress</span>
    {% else %}
    <span class="status-badge status-pending {{ size }}">⏳ {{ status|title }}</span>
    {% endif %}
    {% endmacro %}
    ''',
    description="Renders visual status badges for task states with appropriate icons",
    usage_example="{{ render_task_status_badge('completed', 'large') }}",
    persist_to_file=True
)

# Immediately use the newly created macro
await send_gmail_message(
    html_body="Task Status: {{ render_task_status_badge('completed', 'large') }}"
)
```

**Key Features:**
- ⚡ **Immediate Availability**: Macros are instantly available after creation
- 🎯 **Resource Integration**: Automatically available via `template://macros/macro_name`
- 💾 **Optional Persistence**: Save macros to disk for permanent availability
- 🔄 **Template Processing**: Full Jinja2 syntax validation and error handling

### 🚀 Real-World Usage

Templates can be directly used in tool calls for beautiful, structured output:

```python
# Send a beautiful email with calendar dashboard
await send_gmail_message(
    to="manager@company.com",
    subject="Weekly Schedule Update",
    html_body="{{ render_calendar_events_dashboard( service://calendar/events, 'My upcoming events') }}",
    content_type="mixed"
)

# Generate and send a professional report
await create_doc(
    title="Q4 Performance Report",
    content="{{ generate_report_doc( report_title='Quarterly Results', company_name='GoogleUnlimited' ) }}"
)
```

> 📚 **Template System Resources:**
> - 🎨 **[Template Directory](middleware/templates/)** - Complete collection of Jinja2 templates and macros
> - 💌 **[Beautiful Email Templates](middleware/templates/beautiful_email.j2)** - Rich HTML email styling and themes
> - 🏷️ **[Gmail Label Cards](middleware/templates/email_card.j2)** - Interactive label visualization with chips
> - 📅 **[Calendar Dashboard](middleware/templates/calendar_dashboard.j2)** - Event timeline and scheduling views
> - 📄 **[Document Templates](middleware/templates/document_templates.j2)** - Structured document formatting

## 🗂️ Resource Discovery

GoogleUnlimited provides a powerful **MCP resource system** that enables lightning-fast data access without API calls through intelligent URI patterns.

```mermaid
graph LR
    subgraph "🔍 Resource Types"
        A[👤 user://current/email]
        B[🏷️ service://gmail/labels]
        C[📅 recent://calendar]
        D[🧠 qdrant://search/query]
    end
    
    subgraph "🚀 Resource Engine"
        E[TagBasedResourceMiddleware]
        F[QdrantUnifiedMiddleware]
        G[UserResourceManager]
    end
    
    subgraph "📊 Data Sources"
        H[Google APIs]
        I[Vector Database]
        J[Session Cache]
    end
    
    A --> E --> J
    B --> E --> H
    C --> E --> H
    D --> F --> I
    
    style E fill:#e1f5fe
    style F fill:#f3e5f5
    style G fill:#e8f5e8
```

### 🎯 Resource URI Patterns

| Pattern | Purpose | Example | Returns |
|---------|---------|---------|---------|
| `user://profile/{email}` | User authentication status | `user://profile/john@gmail.com` | Profile + auth state |
| `service://{service}/lists` | Available service lists | `service://gmail/lists` | [filters, labels] |
| `service://{service}/{list_type}` | All items in list | `service://gmail/labels` | All Gmail labels |
| `service://{service}/{list_type}/{id}` | Specific item details | `service://gmail/labels/INBOX` | INBOX label details |
| `recent://{service}` | Recent items | `recent://drive` | Recent Drive files |
| `qdrant://search/{query}` | Semantic search | `qdrant://search/gmail errors` | Relevant responses |

### 🏗️ Key Resource Files

- **[`resources/user_resources.py`](resources/user_resources.py)**: Authentication, profiles, session management (1,812 lines)
- **[`resources/service_list_resources.py`](resources/service_list_resources.py)**: Service discovery through TagBasedResourceMiddleware (446 lines)
- **[`middleware/qdrant_core/resources.py`](middleware/qdrant_core/resources.py)**: AI-powered search and analytics (319 lines)

### ⚡ Lightning-Fast Access

```python
# Instant Gmail labels (no API call needed)
labels = await access_resource("service://gmail/labels")

# Current user info from session
user = await access_resource("user://current/email")

# Semantic search across all tool responses
results = await access_resource("qdrant://search/gmail errors today")

# Recent calendar events
events = await access_resource("recent://calendar")
```

> 📚 **Resource System Documentation:**
> - 🗂️ **[User Resources](resources/user_resources.py)** - Authentication, profiles, and session management (1,812 lines)
> - 🏷️ **[Service List Resources](resources/service_list_resources.py)** - Service discovery through TagBasedResourceMiddleware (446 lines)
> - 🧠 **[Qdrant Core Resources](middleware/qdrant_core/resources.py)** - AI-powered search and analytics (319 lines)
> - 📋 **[Resource Patterns Guide](documentation/middleware/)** - Complete URI pattern reference and usage examples

## 🧪 Testing Framework

GoogleUnlimited includes comprehensive testing with **client tests** that validate MCP usage exactly as an LLM would experience it, plus additional testing suites. **559 tests passing with 100% pass rate**.

### 🎯 Client Testing Focus

```mermaid
flowchart LR
    A[🤖 LLM Client] --> B[📧 Gmail Tests]
    A --> C[📁 Drive Tests]
    A --> D[📊 Sheets Tests]
    A --> E[📅 Calendar Tests]

    B --> F[✅ Real Resource Integration]
    C --> F
    D --> F
    E --> F

    F --> G[🔄 Authentication Patterns]
    F --> H[📊 Service Validation]

    style A fill:#e1f5fe
    style F fill:#e8f5e8
    style G fill:#f3e5f5
```

The **client tests** are the most important component - they provide deterministic testing of MCP operations using real resource integration and standardized patterns across all **90+ tools** and **9 Google services**. These tests validate both explicit email authentication and middleware injection patterns.

### 🚀 Quick Test Commands

```bash
# 🧪 Run all client tests (primary test suite)
uv run pytest tests/client/ -v

# 📧 Test specific service
uv run pytest tests/client/ -k "gmail" -v

# 🔐 Authentication required tests
uv run pytest tests/client/ -m "auth_required" -v
```

### 🔬 Real Resource ID Integration

The testing framework fetches **real IDs** from service resources for realistic testing:

```python
# Available fixtures for real resource testing
real_gmail_message_id      # From service://gmail/messages
real_drive_document_id     # From service://drive/items
real_calendar_event_id     # From service://calendar/events
real_photos_album_id       # From service://photos/albums
real_forms_form_id         # From service://forms/forms
real_chat_space_id         # From service://chat/spaces
```

### 🔄 CI/CD Pipeline

Automated testing and publishing via GitHub Actions:

- **CI Workflow**: Runs on every PR and push to main
  - Python 3.11 & 3.12 matrix testing
  - Linting with `ruff` and formatting with `black`
  - Full test suite execution
- **TestPyPI Publishing**: Automated package publishing for testing

> 📚 **Testing Resources:**
> - 📋 **[Client Testing Framework Guide](tests/client/TESTING_FRAMEWORK.md)** - Complete client testing documentation and patterns
> - 🧪 **[Client Tests Directory](tests/client/)** - Real resource integration tests for deterministic MCP validation
> - 🤖 **[MCP Client Integration](https://gofastmcp.com/clients/client)** - Learn more about MCP client patterns and usage
> - 🔐 **[Authentication Patterns](tests/client/)** - Email vs middleware injection validation testing

## 🔒 Security & Authentication

GoogleUnlimited implements **enterprise-grade security** with OAuth 2.1 + PKCE, advanced session management, and comprehensive audit capabilities.

```mermaid
flowchart TD
    A[🔐 OAuth 2.1 + PKCE] --> B[🔑 Dynamic Client Registration]
    B --> C[🏠 Session Management]
    C --> D[🔐 Encrypted Storage]
    D --> E[📝 Audit Logging]
    
    B --> F[🌐 MCP Inspector OAuth]
    B --> G[🖥️ Direct Server OAuth]
    B --> H[🔧 Development JWT]
    B --> I[📁 File Credentials]
    
    style A fill:#e8f5e8
    style C fill:#e1f5fe
    style D fill:#f3e5f5
```

### 🛡️ Authentication Flows

1. **🌐 MCP Inspector OAuth**: MCP Spec compliant with Dynamic Client Registration
2. **🖥️ Direct Server OAuth**: Web-based authentication for direct access
3. **🔧 Development JWT**: Testing mode with generated tokens
4. **📁 Enhanced File Credentials**: Persistent storage with encryption options
5. **🔑 Custom OAuth Clients**: Bring your own OAuth credentials with automatic fallback

### ✨ Security Features

- **🔐 OAuth 2.1 + PKCE**: Modern authentication with proof-of-key exchange (supports public clients)
- **🔒 Session Isolation**: Multi-tenant support preventing data leaks
- **🏷️ 27+ API Scopes**: Granular permission management across all services
- **📊 Audit Logging**: Complete security event tracking
- **🔐 AES-256 Encryption**: Machine-specific keys for credential storage
- **🔄 Three-Tier Fallback**: Robust credential persistence across server restarts (State Map → UnifiedSession → Context Storage)

### ⚙️ Security Configuration

```env
# 🔒 Security settings in .env
CREDENTIAL_STORAGE_MODE=FILE_ENCRYPTED
SESSION_SECRET_KEY=your-secret-key
SESSION_TIMEOUT_MINUTES=30
ENABLE_AUDIT_LOGGING=true
GMAIL_ALLOW_LIST=trusted@example.com
```

> 📚 **Security Documentation Resources:**
> - 🛡️ **[Unified OAuth Architecture](documentation/security/unified_oauth_architecture_design.md)** - Complete security architecture and authentication design
> - 🔐 **[OAuth 2.1 + PKCE Implementation](documentation/security/)** - Modern authentication with proof-of-key exchange
> - 🏠 **[Session Management Guide](documentation/security/)** - Multi-tenant support and session isolation
> - 🔒 **[Encryption & Storage](documentation/security/)** - AES-256 credential encryption and machine-specific keys
> - 📊 **[Audit Logging System](documentation/security/)** - Complete security event tracking and monitoring

---

<div align="center">

**🚀 Ready to revolutionize your Google Workspace integration?**

[📚 Documentation](documentation/) • [🔧 Configuration](documentation/config/) • [🎯 API Reference](documentation/api-reference/) • [🧪 Testing](tests/client/)

</div>