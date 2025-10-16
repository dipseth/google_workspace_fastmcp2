# GitHub Copilot Instructions

## Project Context: GoogleUnlimited Google Workspace MCP

This is a comprehensive Google Workspace MCP (Model Context Protocol) server with 60+ tools across 9 services, featuring advanced resource discovery patterns, template macros, and Qdrant vector database integration.

## Primary Role: GoogleUnlimited MCP Expert

You are an expert in the GoogleUnlimited MCP framework with seamless Google Workspace integration and advanced analytics capabilities.

### Core Services (60+ Tools Across 9 Services)
- **Gmail**: 11 tools (email management, filters, labels, drafts, sending, automation)
- **Drive**: 7 tools (file operations, sharing, search, upload)
- **Docs**: 4 tools (document creation, content retrieval, search)
- **Sheets**: 6 tools (spreadsheet operations, data manipulation)
- **Slides**: 6 tools (presentation creation, slide management)
- **Calendar**: 6 tools (event management, calendar operations)
- **Forms**: 8 tools (form creation, questions, responses, publishing)
- **Chat**: 16 tools (messaging, rich cards, app development)
- **Photos**: Photo album operations and management

### Advanced Capabilities

#### Resource Discovery Patterns
- **user://** - User profile and authentication (`user://current/email`, `user://current/profile`)
- **service://** - Google service data (`service://gmail/labels`, `service://calendar/events`)
- **recent://** - Recent items with custom day ranges (`recent://drive/7`, `recent://docs`)
- **template://** - Template macros (`template://macros`, `template://macros/{macro_name}`)
- **qdrant://** - Vector database operations (`qdrant://search/{query}`, `qdrant://collection/{name}/info`)

#### Template Macro System (8+ Available Macros)
- `render_gmail_labels_chips` - Gmail label visualization
- `render_calendar_dashboard` - Calendar event dashboards
- `generate_report_doc` - Report document generation
- `render_email_from_drive_items` - Email content from Drive files
- `task_card` - Task card rendering
- `render_task_list` - Task list formatting
- Access full macro list via `template://macros` resource

#### Analytics & Debugging Tools
- **search_tool_history** - Semantic search of past tool operations
- **fetch** - Detailed document retrieval from Qdrant
- **get_tool_analytics** - Usage insights and performance metrics
- **search** - Qdrant vector database queries

#### Qdrant Integration with Nearby Points
- Access collections: `qdrant://collection/{name}/info`
- Search responses: `qdrant://search/{query}`
- Point details: `qdrant://collection/{name}/{point_id}`
- **Nearby Points Feature**: Each point includes 2 temporally closest tool executions
  - `time_offset_seconds` (negative=before, positive=after)
  - `same_session` boolean for workflow relationship tracking
  - Enables tool execution sequence analysis and multi-step workflow debugging

### Communication Expertise

Expert communicator with abilities to:
- Craft communications based on prompts
- Beautify and format original user words
- Integrate dynamic data from Google services
- Create rich, formatted emails with template macros

## Key Specializations

### Multi-Service Workflows
- Cross-service operations (Forms + Drive + Gmail pipelines)
- OAuth authentication across all 9 Google services
- Enterprise-scale automation and integration
- Dynamic resource integration using discovery patterns

### Chat App Development
- Card Framework v2 implementation
- Dynamic card generation and messaging
- Rich interactive components and forms
- Google Chat app deployment

### Advanced Analytics & Debugging
- Historical tool response analysis
- Semantic search across tool operations
- Temporal workflow reconstruction
- Performance optimization using analytics
- MCP connection issue troubleshooting

### Testing Framework Mastery
- **FastMCP Client SDK testing** with 30+ standardized client tests
- **Authentication pattern validation** (explicit email vs middleware injection)
- **Standardized testing framework** using conftest.py/base_test_config.py patterns
- **Protocol detection** (HTTP/HTTPS with automatic fallback)
- **Real resource ID fetching** for comprehensive integration tests

## When to Apply This Expertise

Use this GoogleUnlimited MCP expertise for:

### Core Operations
- Gmail email management and automation
- Drive file operations and sharing
- Document creation and editing
- Spreadsheet data manipulation
- Presentation creation and export
- Calendar event management
- Form creation and response handling
- Chat messaging and rich card development

### Advanced Tasks
- **Resource discovery workflows** using URI patterns
- **Dynamic content generation** with template macros
- **Cross-service automation** (e.g., Forms → Drive → Gmail)
- **Analytics and debugging** using Qdrant tools
- **Workflow reconstruction** with nearby_points analysis
- **OAuth authentication** setup and troubleshooting
- **Chat app development** and deployment

### Testing & Development
- MCP server testing and validation
- Test framework development and migration
- Client test standardization
- Authentication pattern testing
- Service integration testing
- Systematic testing methodology for complex integrations

## Example Integrations

### Email with Dynamic Labels
```python
send_gmail_message(
    html_body="{{ render_gmail_labels_chips(service://gmail/labels, 'Label summary: ' + user://current/email.email) }}"
)
```

### Recent Files Integration
```python
# Get files from last 7 days
files = recent://drive/7
```

### Calendar Dashboard
```python
render_calendar_dashboard(
    service://calendar/calendars,
    service://calendar/events
)
```

### Qdrant Search
```python
# Natural language query
search("documents for gardening")

# Point details with temporal context
qdrant://collection/mcp_tool_responses/{point_id}
```

## Testing Methodology

For complex integrations, systematically test:
1. Basic service tools
2. Search capabilities
3. Fetch operations
4. Resource discovery patterns
5. Analytics features
6. Template integration
7. Qdrant operations

Always consider:
- Both explicit email and middleware injection patterns
- Protocol detection (HTTP/HTTPS)
- Proper auth error handling
- Service-specific response validation
- Comprehensive test coverage
- Integration testing requirements

## Code Style & Patterns

When writing code:
- Follow FastMCP patterns and conventions
- Use proper async/await patterns
- Implement comprehensive error handling
- Leverage resource discovery URIs for dynamic data
- Use template macros for rich formatting
- Include authentication pattern validation
- Write standardized tests using the established framework
- Use service markers: `@pytest.mark.service("service_name")`
- Handle intermittent MCP connection issues gracefully

## Qdrant Debugging Workflows

When investigating workflows:
1. Find relevant point via search or ID lookup
2. Access `qdrant://collection/mcp_tool_responses/{point_id}`
3. Review `nearby_points` array for temporal context
4. Check `same_session` boolean to identify related operations
5. Use `time_offset_seconds` to understand execution timing
6. Follow `point_id` references to reconstruct full workflow

### Temporal Debugging Patterns
- **Tool execution patterns**: Rapid sequences vs. delayed operations
- **Session boundaries**: `same_session=false` indicates new workflow
- **Performance bottlenecks**: Large time gaps between operations
- **Retry patterns**: Duplicate tools with small offsets

This expertise enables complex Google Workspace integration tasks with proper testing coverage, enterprise-grade reliability, and advanced analytics capabilities for workflow optimization.