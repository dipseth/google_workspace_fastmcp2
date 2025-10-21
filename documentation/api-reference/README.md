# FastMCP Google MCP Server - API Reference

This comprehensive API reference provides detailed documentation for all 60+ tools available in the FastMCP Google MCP Server, organized by service category.

## Quick Navigation

### Core Google Services
- [Google Drive](./drive/README.md) - 9 tools for file management, upload, search, and sharing
- [Gmail](./gmail/README.md) - 15 tools for email operations, labels, filters, and threading  
- [Google Calendar](./calendar/README.md) - 6 tools for event management and calendar operations
- [Google Docs](./google_docs/README.md) - 4 tools for document creation and content management
- [Google Forms](./forms/README.md) - 8 tools for form creation, questions, and response handling
- [Google Sheets](./sheets/README.md) - 6 tools for spreadsheet operations and data manipulation
- [Google Slides](./slides/README.md) - 6 tools for presentation creation and management
- [Google Chat](./chat/README.md) - 16 tools for messaging, spaces, and card framework

### Platform Services
- [Authentication](./auth/README.md) - 3 tools for OAuth, credentials, and session management
- [Enhanced Tools](./enhanced/README.md) - 4 tools with resource templating (no email param needed)
- [Qdrant Integration](./qdrant/README.md) - 3 tools for semantic search and analytics
- [Tunnel Services](./tunnel/README.md) - 3 tools for Cloudflare tunnel management
- [Module Wrapper](./adapters/README.md) - 5 tools for Python module introspection

## Tool Categories

### 🆕 Enhanced Tools (Resource Templating)
Tools that automatically use the authenticated user's context without requiring email parameters:
- `list_my_drive_files` - List Drive files with automatic authentication
- `search_my_gmail` - Search Gmail messages seamlessly
- `create_my_calendar_event` - Create calendar events without email parameter

### 📁 Drive Tools (9 tools)
File management, upload, search, content retrieval, and sharing capabilities.

### 📧 Gmail Tools (15 tools)  
Email operations including search, send, draft, reply, labels, filters, and batch operations.

### 📅 Calendar Tools (6 tools)
Event creation, modification, calendar management with RFC3339 compliance.

### 📄 Docs Tools (4 tools)
Document creation, content retrieval, and folder organization.

### 📋 Forms Tools (8 tools)
Form creation, question management, response handling, and publishing.

### 📊 Sheets Tools (6 tools)
Spreadsheet operations, range handling, and batch updates.

### 🎯 Slides Tools (6 tools)
Presentation creation, slide management, and export functionality.

### 💬 Chat Tools (16 tools)
Messaging, space management, rich cards, and webhook integration.

### 🔐 Authentication Tools (3 tools)
OAuth flow, credential management, and security operations.

### 🔍 Qdrant Tools (3 tools)
Semantic search, tool history, and analytics.

## API Standards

All tools in this platform follow consistent patterns:

### Common Parameters

Most tools accept these standard parameters:

| Parameter | Type | Description | Required |
|-----------|------|-------------|----------|
| `user_google_email` | string | User's Google email for authentication | Yes (except enhanced tools) |
| `page_size` | integer | Number of results to return (usually 10-100) | No |
| `page_token` | string | Token for pagination | No |

### Response Format

All tools return JSON responses with consistent structure:

```json
{
  "success": true,
  "data": {...},
  "metadata": {
    "timestamp": "ISO-8601",
    "tool": "tool_name",
    "user": "user_email"
  },
  "error": null
}
```

### Error Handling

Tools use standardized error responses:

```json
{
  "success": false,
  "data": null,
  "error": {
    "code": "ERROR_CODE",
    "message": "Human-readable error message",
    "details": {...}
  }
}
```

Common error codes:
- `AUTH_REQUIRED` - User needs to authenticate
- `PERMISSION_DENIED` - Insufficient permissions
- `NOT_FOUND` - Resource not found
- `RATE_LIMITED` - API rate limit exceeded
- `INVALID_PARAMETER` - Parameter validation failed

### Authentication Flow

1. Use `start_google_auth` with user's email
2. Complete OAuth flow in browser
3. Tools automatically use stored credentials
4. Tokens refresh automatically when needed

### Rate Limiting

Google APIs have quotas. Tools handle rate limiting gracefully with:
- Automatic retry with exponential backoff
- Clear error messages when quotas exceeded
- Batch operations where supported

## Tool Annotations

Tools use standardized annotations for behavior hints:

| Annotation | Description |
|------------|-------------|
| `readOnlyHint` | Tool only reads data, no modifications |
| `destructiveHint` | Tool can delete or modify data |
| `idempotentHint` | Safe to call multiple times |
| `openWorldHint` | Interacts with external services |

## Version History

- **v1.0.0** (Current) - Complete Google Workspace integration with 60+ tools
- Revolutionary middleware architecture
- Resource templating for enhanced tools
- Qdrant semantic search integration

## Testing Framework

The platform includes a comprehensive testing framework with 100% reliability:

- **✅ 45 passed, 0 failed**: Complete test suite validation across all Google services
- **🔧 Standardized Framework**: Consistent patterns for testing all 60+ tools
- **🌐 Environment Configuration**: Configurable test resources via `.env` variables
- **📋 Full Documentation**: See [`../tests/client/TESTING_FRAMEWORK.md`](../tests/client/TESTING_FRAMEWORK.md)

### Test Environment Configuration

Add these to your `.env` file for complete testing:

```env
# Test Resources (prevents resource creation during tests)
TEST_EMAIL_ADDRESS=your.test@gmail.com
GOOGLE_SLIDE_PRESENTATION_ID=1RGLViw2eUBJfl84jsVlFuuLbauGvcxyfs1YWmpmFCSw
TEST_CHAT_WEBHOOK=https://chat.googleapis.com/v1/spaces/YOUR_SPACE/messages
PHOTO_TEST_EMAIL_ADDRESS=your-photo-test@example.com
```

## Getting Started

1. Review the [Authentication Guide](./auth/README.md) to set up OAuth
2. Explore service-specific documentation for your use case
3. Check [Enhanced Tools](./enhanced/README.md) for simplified authentication
4. See [Examples](./examples/README.md) for common workflows
5. Review [Testing Framework](../tests/client/TESTING_FRAMEWORK.md) for validation

---

For implementation details and architecture documentation, see the [main documentation](../).