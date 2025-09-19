# 🚀 RiversUnlimited Google Workspace Platform

**RiversUnlimited** is a comprehensive MCP framework that provides seamless Google Workspace integration through an advanced middleware architecture. It enables AI assistants and MCP clients to interact with Gmail, Google Drive, Docs, Sheets, Slides, Calendar, Forms, Chat, and Photos services using a unified, secure API.

## 📋 Table of Contents

- [Quick Installation Instructions](#-quick-installation-instructions)
- [Service Capabilities](#-service-capabilities)
- [Middleware Architecture](#-middleware-architecture)
- [Template System](#-template-system)
- [Resource Discovery](#-resource-discovery)
- [Testing Framework](#-testing-framework)
- [Security & Authentication](#-security--authentication)

## ⚡ Quick Installation Instructions

### What is RiversUnlimited?

RiversUnlimited provides AI assistants with access to Google Workspace services through the Model Context Protocol (MCP). It supports **71+ tools** across **9 Google services**, enabling seamless integration between AI workflows and Google Workspace applications with revolutionary performance improvements.

```mermaid
graph TB
    subgraph "🤖 AI Assistant"
        A[Claude/GPT/Other]
    end
    
    subgraph "🌉 RiversUnlimited MCP Framework"
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

## 🎯 Service Capabilities

RiversUnlimited supports **9 Google Workspace services** with **71+ specialized tools**:

| Service | Icon | Tools | Key Features | Documentation |
|---------|------|-------|--------------|---------------|
| **Gmail** | 📧 | 11 | Send, reply, labels, filters, search | [`api-reference/gmail/`](documentation/api-reference/gmail/) |
| **Drive** | 📁 | 7 | Upload, download, sharing, Office docs | [`api-reference/drive/`](documentation/api-reference/drive/) |
| **Docs** | 📄 | 4 | Create, edit, format, batch operations | [`api-reference/docs/`](documentation/api-reference/docs/) |
| **Sheets** | 📊 | 6 | Read, write, formulas, formatting | [`api-reference/sheets/`](documentation/api-reference/sheets/) |
| **Slides** | 🎯 | 5 | Presentations, templates, export | [`api-reference/slides/`](documentation/api-reference/slides/) |
| **Calendar** | 📅 | 6 | Events, scheduling, attendees, timezones | [`api-reference/calendar/`](documentation/api-reference/calendar/) |
| **Forms** | 📝 | 8 | Creation, responses, validation, publishing | [`api-reference/forms/`](documentation/api-reference/forms/) |
| **Chat** | 💬 | 12 | Messaging, cards, spaces, webhooks | [`api-reference/chat/`](documentation/api-reference/chat/) |
| **Photos** | 📷 | 12 | Albums, upload, search, metadata | [`api-reference/photos/`](documentation/api-reference/photos/) |

> 📚 **API Documentation Resources:**
> - 🔗 **[Complete API Reference](documentation/api-reference/)** - Comprehensive documentation for all 71+ tools across 9 services
> - 📧 **[Gmail API Guide](documentation/api-reference/gmail/)** - Email management, labels, filters, and search operations
> - 📁 **[Drive API Guide](documentation/api-reference/drive/)** - File operations, sharing, and Office document handling
> - 📊 **[Sheets API Guide](documentation/api-reference/sheets/)** - Spreadsheet data manipulation and formatting
> - 📅 **[Calendar API Guide](documentation/api-reference/calendar/)** - Event scheduling and timezone management

## 🧠 Middleware Architecture

RiversUnlimited uses a middleware architecture that provides seamless service integration, intelligent resource management, and powerful templating capabilities.

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

RiversUnlimited features powerful **Jinja2 template macros** that transform raw Google Workspace data into visually stunning, AI-optimized formats.

### 🎯 Available Templates

| Template | Purpose | Features |
|----------|---------|----------|
| **`beautiful_email.j2`** | Rich HTML emails | CSS styling, themes, signatures |
| **`email_card.j2`** | Gmail label visualization | Interactive chips, unread counts |
| **`calendar_dashboard.j2`** | Event visualization | Timeline views, scheduling |
| **`document_templates.j2`** | Document formatting | Structure, metadata |
| **`drive_enhanced_email.j2`** | File integration | Drive links in emails |

### 💡 Template Macro Example

**Gmail Labels Visualization** - Transform boring label lists into beautiful interactive chips:

```jinja2
{{ render_gmail_labels_chips( service://gmail/labels , 'Label summary for: ' + user://current/email ) }}
```

This macro produces a beautiful dark-themed interface with:
- 🏷️ **Interactive label chips** with hover effects
- 📊 **Unread message counts**
- 🔗 **Direct Gmail links** for instant access
- 📱 **Mobile-responsive design**

![Gmail Labels Visualization](documentation/Untitled.png)

### 🚀 Real-World Usage

Templates can be directly used in tool calls for beautiful, structured output:

```python
# Send a beautiful email with calendar dashboard using template macros
await send_gmail_message(
    to="manager@company.com",
    subject="Weekly Schedule Update",
    html_body="{{ render_calendar_dashboard( recent://calendar/7 , 'My upcoming events') }}",
    content_type="mixed"
)

# Or use the beautiful email template with dynamic data
await send_gmail_message(
    to="team@company.com",
    subject="Gmail Labels Summary",
    html_body="{{ render_gmail_labels_chips( service://gmail/labels , 'Current label status: ' + user://current/email ) }}",
    content_type="html"
)
# Returns professionally styled emails with interactive elements
```

> 📚 **Template System Resources:**
> - 🎨 **[Template Directory](middleware/templates/)** - Complete collection of Jinja2 templates and macros
> - 💌 **[Beautiful Email Templates](middleware/templates/beautiful_email.j2)** - Rich HTML email styling and themes
> - 🏷️ **[Gmail Label Cards](middleware/templates/email_card.j2)** - Interactive label visualization with chips
> - 📅 **[Calendar Dashboard](middleware/templates/calendar_dashboard.j2)** - Event timeline and scheduling views
> - 📄 **[Document Templates](middleware/templates/document_templates.j2)** - Structured document formatting

## 🗂️ Resource Discovery

RiversUnlimited provides a powerful **MCP resource system** that enables lightning-fast data access without API calls through intelligent URI patterns.

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

RiversUnlimited features an enterprise-grade testing framework with **real resource integration** and comprehensive validation.

### 🎯 Framework Features

```mermaid
pie title Testing Coverage Distribution
    "Service Integration Tests" : 35
    "Authentication Tests" : 25
    "Real Resource Tests" : 20
    "Performance Tests" : 20
```

- **🔧 Standardized Patterns**: Consistent testing across all **71+ tools**
- **🌐 Real Resource Integration**: Tests against actual user data when available
- **🔐 Authentication Validation**: Explicit email vs middleware injection patterns
- **📊 Service Coverage**: Complete validation across all 9 Google services
- **🎯 Real ID Fixtures**: Dynamic fetching from `service://` resources

### 🚀 Quick Test Commands

```bash
# 🧪 Run all client tests
uv run pytest tests/client/ -v

# 📧 Test specific service
uv run pytest tests/client/ -k "gmail" -v

# 🔐 Authentication required tests
uv run pytest tests/client/ -m "auth_required" -v

# ⚡ Performance benchmarks
uv run pytest tests/client/ -m "performance" -v
```

> 📚 **Testing Framework Resources:**
> - 📋 **[Complete Testing Guide](tests/client/TESTING_FRAMEWORK.md)** - Enterprise-grade testing framework documentation
> - 🧪 **[Client Tests Directory](tests/client/)** - Real resource integration tests for all 71+ tools
> - 🔐 **[Authentication Test Patterns](tests/client/)** - Email vs middleware injection validation
> - ⚡ **[Performance Benchmarks](tests/client/)** - Speed and efficiency testing across all services
> - 🎯 **[Service Coverage Tests](tests/client/)** - Complete validation across 9 Google Workspace services

## 🔒 Security & Authentication

RiversUnlimited implements **enterprise-grade security** with OAuth 2.1 + PKCE, advanced session management, and comprehensive audit capabilities.

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

### ✨ Security Features

- **🔐 OAuth 2.1 + PKCE**: Modern authentication with proof-of-key exchange
- **🔒 Session Isolation**: Multi-tenant support preventing data leaks
- **🏷️ 27+ API Scopes**: Granular permission management across all services
- **📊 Audit Logging**: Complete security event tracking
- **🔐 AES-256 Encryption**: Machine-specific keys for credential storage

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