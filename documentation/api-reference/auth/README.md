# Authentication API Reference

Complete API documentation for all authentication tools in the FastMCP Google MCP Server.

## Overview

The Authentication service provides comprehensive OAuth 2.0 flow management, credential handling, and session management across all Google Workspace services. This service supports multiple authentication flows and enterprise-grade security features.

## Available Tools

| Tool Name | Description |
|-----------|-------------|
| [`start_google_auth`](#start_google_auth) | Initiate OAuth 2.0 authentication flow |
| [`check_drive_auth`](#check_drive_auth) | Check authentication status for all Google services |
| [`get_my_auth_status`](#get_my_auth_status) | Enhanced authentication status with resource templating |

---

## Tool Details

### `start_google_auth`

Initiate the OAuth 2.0 authentication flow for Google Workspace services.

**Parameters:**
- `user_google_email` (string, required): User's Google email for authentication
- `service_name` (string, optional, default: "All Google Services"): Specific service or all services

**Supported Services:**
- Gmail
- Google Drive
- Google Docs
- Google Sheets
- Google Slides
- Google Calendar
- Google Forms
- Google Chat
- All Google Services (default)

**Authentication Flow:**
1. Generates OAuth 2.0 authorization URL
2. Opens browser for user consent
3. Handles OAuth callback
4. Stores encrypted credentials securely
5. Returns authentication confirmation

**Response:**
- Authentication URL for browser opening
- Flow status and next steps
- Service-specific scope information
- Success confirmation upon completion

### `check_drive_auth`

Check authentication status across all Google Workspace services for a user.

**Parameters:**
- `user_google_email` (string, required): User's Google email to check

**Comprehensive Status Check:**
- Gmail authentication status
- Drive authentication status
- Docs authentication status
- Sheets authentication status
- Slides authentication status
- Calendar authentication status
- Forms authentication status
- Chat authentication status

**Response:**
- Per-service authentication status
- Token expiration information
- Required scopes and permissions
- Re-authentication requirements
- Service availability status

### `get_my_auth_status`

Enhanced authentication status check with resource templating support (no email parameter required).

**Parameters:**
- None (uses resource context for email detection)

**Enhanced Features:**
- Automatic email detection from resource context
- Cross-service authentication summary
- Token health and refresh status
- Permission scope analysis
- Service capability matrix

**Resource Templating:**
- Leverages FastMCP Google MCP's resource templating system
- Automatically determines user context
- Provides seamless authentication checking
- Integration with Enhanced Tools ecosystem

---

## Authentication Architecture

### Multi-Flow OAuth System

FastMCP Google MCP supports **four distinct authentication flows**:

#### 1. MCP Inspector OAuth (MCP Spec Compliant)
- **Purpose**: OAuth 2.1 + Dynamic Client Registration for MCP clients
- **Redirect URIs**: `http://127.0.0.1:6274/oauth/callback/debug`, `http://localhost:3000/auth/callback`
- **Flow**: MCP Inspector → Server → Google → Back to MCP Inspector
- **Implementation**: `fastmcp_oauth_endpoints.py`, `dynamic_client_registration.py`

#### 2. Direct Server OAuth (Web Interface)
- **Purpose**: Direct user authentication via web interface
- **Redirect URI**: `http://localhost:8002/oauth2callback`
- **Flow**: User → Server → Google → Back to Server
- **Implementation**: `google_oauth_auth.py`, server authentication tools

#### 3. Development JWT (Testing Mode)
- **Purpose**: Development/testing authentication without Google
- **Flow**: Development tokens for testing environments
- **Implementation**: `jwt_auth.py`

#### 4. Enhanced File-Based Credentials (Persistent)
- **Purpose**: Stored OAuth credentials from previous authentications
- **Security Modes**:
  - **FILE_PLAINTEXT**: Legacy JSON files (backward compatible)
  - **FILE_ENCRYPTED**: AES-256 encrypted files with machine-specific keys
  - **MEMORY_ONLY**: No disk storage, expires with server restart
  - **MEMORY_WITH_BACKUP**: Memory cache + encrypted backup files

### Universal Scope Management

Comprehensive API scope management across all Google services:

**Drive Scopes:**
- `https://www.googleapis.com/auth/drive.file`
- `https://www.googleapis.com/auth/drive.readonly`
- `https://www.googleapis.com/auth/drive.metadata.readonly`

**Gmail Scopes:**
- `https://www.googleapis.com/auth/gmail.send`
- `https://www.googleapis.com/auth/gmail.modify`
- `https://www.googleapis.com/auth/gmail.compose`
- `https://www.googleapis.com/auth/gmail.readonly`

**Calendar Scopes:**
- `https://www.googleapis.com/auth/calendar.events`
- `https://www.googleapis.com/auth/calendar.readonly`

**Forms Scopes:**
- `https://www.googleapis.com/auth/forms.body`
- `https://www.googleapis.com/auth/forms.body.readonly`
- `https://www.googleapis.com/auth/forms.responses.readonly`

**Additional Service Scopes:**
- Docs, Sheets, Slides: Read/write access
- Chat: Message and space management
- Cloud Platform: Service integration scopes

## Security Features

### Enterprise-Grade Security
- ✅ **OAuth 2.0 with PKCE**: Enhanced security flow
- ✅ **Token Encryption**: AES-256 credential protection
- ✅ **Session Isolation**: Multi-user session management
- ✅ **Automatic Refresh**: Seamless token renewal
- ✅ **Scope Validation**: Permission verification
- ✅ **Audit Logging**: Comprehensive authentication logs

### Credential Storage Options

#### FILE_ENCRYPTED (Recommended)
```json
{
  "storage_mode": "FILE_ENCRYPTED",
  "encryption": "AES-256-GCM",
  "key_derivation": "machine_specific",
  "backup_enabled": true
}
```

#### MEMORY_WITH_BACKUP
```json
{
  "storage_mode": "MEMORY_WITH_BACKUP",
  "primary_storage": "memory",
  "backup_storage": "encrypted_file",
  "session_persistence": false
}
```

### Multi-User Support
- Individual credential isolation
- Per-user session management
- Cross-user permission boundaries
- Scalable authentication architecture

## Integration Patterns

### Service Middleware Integration
All Google services integrate with the authentication middleware:

```python
# Automatic service injection with authentication
@mcp.tool()
async def universal_tool(user_google_email: str):
    service_key = request_service("gmail")
    service = get_injected_service(service_key)
    # Service is automatically authenticated
```

### Enhanced Tools Integration
Resource templating eliminates email parameter requirements:

```python
# No email parameter needed
@mcp.tool()
async def enhanced_tool():
    # Email automatically detected from resource context
    # Authentication handled transparently
```

## Best Practices

### Authentication Flow
1. **Initial Setup**: Use `start_google_auth` for first-time setup
2. **Status Monitoring**: Regular `check_drive_auth` calls
3. **Enhanced Tools**: Leverage `get_my_auth_status` for seamless checking
4. **Error Handling**: Implement proper re-authentication flows

### Security Considerations
1. **Credential Storage**: Use FILE_ENCRYPTED in production
2. **Token Rotation**: Implement regular token refresh
3. **Permission Auditing**: Monitor scope usage and requirements
4. **Session Management**: Implement proper session cleanup

### Multi-User Environments
1. **User Isolation**: Ensure proper credential separation
2. **Resource Management**: Monitor authentication resource usage
3. **Scalability**: Implement connection pooling for large deployments
4. **Monitoring**: Track authentication success and failure rates

## Common Use Cases

### Enterprise Single Sign-On
```python
# Authenticate user across all services
auth_result = await start_google_auth(
    user_google_email="employee@company.com",
    service_name="All Google Services"
)

# Check authentication status
status = await check_drive_auth(
    user_google_email="employee@company.com"
)

# Use enhanced tools without re-authentication
my_status = await get_my_auth_status()
```

### Service-Specific Authentication
```python
# Authenticate for specific service
await start_google_auth(
    user_google_email="user@example.com",
    service_name="Gmail"
)

# Check service-specific status
status = await check_drive_auth(user_google_email="user@example.com")
# Returns status for all services, not just Drive despite name
```

### Development and Testing
```python
# Use JWT authentication for testing
# Configured in environment variables
# Automatic fallback for development environments
```

## Error Handling

### Common Authentication Errors

#### Authentication Required
```json
{
  "error": {
    "code": "AUTH_REQUIRED",
    "message": "User needs to complete OAuth flow",
    "details": {
      "auth_url": "https://accounts.google.com/oauth2/auth?...",
      "required_scopes": ["gmail.send", "drive.file"]
    }
  }
}
```

#### Token Expired
```json
{
  "error": {
    "code": "TOKEN_EXPIRED",
    "message": "Authentication tokens have expired",
    "details": {
      "refresh_available": true,
      "re_auth_required": false
    }
  }
}
```

#### Permission Denied
```json
{
  "error": {
    "code": "PERMISSION_DENIED",
    "message": "Insufficient permissions for requested operation",
    "details": {
      "required_scopes": ["forms.body"],
      "current_scopes": ["forms.body.readonly"]
    }
  }
}
```

### Troubleshooting Guide

1. **Clear Credentials**: Remove stored credentials and re-authenticate
2. **Scope Verification**: Ensure OAuth client has all required scopes
3. **Redirect URI**: Verify OAuth redirect URIs in Google Cloud Console
4. **API Enablement**: Confirm all required APIs are enabled
5. **Quota Limits**: Check for OAuth quota limitations

## Configuration

### Environment Variables
```bash
# OAuth Configuration
GOOGLE_CLIENT_SECRETS_FILE=/path/to/client_secret.json
GOOGLE_CLIENT_ID=your_client_id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your_client_secret

# Authentication Settings
CREDENTIALS_DIR=./credentials
CREDENTIAL_STORAGE_MODE=FILE_ENCRYPTED
SESSION_TIMEOUT_MINUTES=60

# Development Settings
DEVELOPMENT_MODE=false
JWT_AUTH_ENABLED=false
```

### OAuth Client Setup
1. **Google Cloud Console**: Create OAuth 2.0 client
2. **Redirect URIs**: Add all supported redirect URIs
3. **API Enablement**: Enable all required Google APIs
4. **Scope Configuration**: Request appropriate OAuth scopes
5. **Domain Verification**: Verify domain for production use

---

For more information, see:
- [OAuth 2.0 Flow Documentation](../../OAuth_Authentication_Explained.md)
- [Multi-Service Integration](../../MULTI_SERVICE_INTEGRATION.md)
- [Security Best Practices](../../SECURITY.md)
- [Main API Reference](../README.md)