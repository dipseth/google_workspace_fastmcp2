# Centralized Configuration Guide

## Overview

This guide provides comprehensive documentation of all configuration options for the FastMCP Google MCP Server. Configuration is primarily managed through environment variables, with sensible defaults for development and production environments.

## Table of Contents

1. [Quick Start Configuration](#quick-start-configuration)
2. [Environment Variables Reference](#environment-variables-reference)
3. [Service-Specific Configuration](#service-specific-configuration)
4. [Security Configuration](#security-configuration)
5. [Performance Tuning](#performance-tuning)
6. [Development vs Production](#development-vs-production)
7. [Troubleshooting](#troubleshooting)

## Quick Start Configuration

### Minimal Configuration (.env file)

```bash
# Required for Google OAuth
GOOGLE_CLIENT_ID=your-client-id-here
GOOGLE_CLIENT_SECRET=your-client-secret-here

# Server Configuration
SERVER_HOST=localhost
SERVER_PORT=6339

# Security (Production)
CREDENTIAL_STORAGE_MODE=FILE_ENCRYPTED
```

### Complete Example Configuration

```bash
# ============================================
# CORE SERVER CONFIGURATION
# ============================================
SERVER_NAME=FastMCP Google MCP Server
SERVER_HOST=0.0.0.0
SERVER_PORT=6339
BASE_URL=https://google-mcp.FastMCP.internal:6339
LOG_LEVEL=INFO

# ============================================
# GOOGLE OAUTH CONFIGURATION
# ============================================
GOOGLE_CLIENT_ID=123456789012-abcdefghijklmnop.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=GOCSPX-1234567890abcdef
OAUTH_REDIRECT_URI=https://google-mcp.FastMCP.internal:6339/oauth/callback
USE_GOOGLE_OAUTH=true
ENABLE_JWT_AUTH=false

# OAuth Scopes (space-separated)
OAUTH_SCOPES="https://www.googleapis.com/auth/drive.file https://www.googleapis.com/auth/gmail.send https://www.googleapis.com/auth/calendar https://www.googleapis.com/auth/documents https://www.googleapis.com/auth/spreadsheets https://www.googleapis.com/auth/presentations https://www.googleapis.com/auth/forms https://www.googleapis.com/auth/chat.messages"

# ============================================
# SECURITY CONFIGURATION
# ============================================
CREDENTIAL_STORAGE_MODE=FILE_ENCRYPTED
SESSION_TIMEOUT_MINUTES=60
MAX_SESSION_LIFETIME_HOURS=24
AUTH_ENCRYPTION_KEY_FILE=.auth_encryption_key

# SSL/HTTPS Configuration
ENABLE_HTTPS=false
SSL_CERT_FILE=/path/to/cert.pem
SSL_KEY_FILE=/path/to/key.pem
SSL_CA_FILE=/path/to/ca.pem

# ============================================
# STORAGE AND PATHS
# ============================================
CREDENTIALS_DIR=.credentials
CACHE_DIR=.cache
TEMP_DIR=/tmp/fastmcp2

# ============================================
# QDRANT VECTOR DATABASE
# ============================================
QDRANT_HOST=localhost
QDRANT_PORT=6333
QDRANT_COLLECTION_NAME=tool_responses
QDRANT_API_KEY=
QDRANT_HTTPS=false
QDRANT_GRPC_PORT=6334
QDRANT_PREFER_GRPC=false

# ============================================
# PERFORMANCE CONFIGURATION
# ============================================
MAX_CONCURRENT_REQUESTS=10
REQUEST_TIMEOUT_SECONDS=30
CACHE_TTL_SECONDS=3600
MAX_CACHE_SIZE_MB=100

# ============================================
# GOOGLE API CONFIGURATION
# ============================================
# Drive API
DRIVE_API_VERSION=v3
DRIVE_DEFAULT_PAGE_SIZE=100
DRIVE_MAX_PAGE_SIZE=1000
DRIVE_UPLOAD_CHUNK_SIZE=5242880  # 5MB

# Gmail API
GMAIL_API_VERSION=v1
GMAIL_DEFAULT_PAGE_SIZE=50
GMAIL_MAX_RESULTS=500
GMAIL_BATCH_SIZE=50

# Calendar API
CALENDAR_API_VERSION=v3
CALENDAR_DEFAULT_MAX_RESULTS=250
CALENDAR_DEFAULT_TIME_ZONE=America/Chicago

# Docs API
DOCS_API_VERSION=v1
DOCS_DEFAULT_PAGE_SIZE=100

# Forms API
FORMS_API_VERSION=v1
FORMS_DEFAULT_PAGE_SIZE=100

# Sheets API
SHEETS_API_VERSION=v4
SHEETS_DEFAULT_RANGE=A1:Z1000
SHEETS_VALUE_INPUT_OPTION=USER_ENTERED

# Slides API
SLIDES_API_VERSION=v1
SLIDES_DEFAULT_PAGE_SIZE=100

# Chat API
CHAT_API_VERSION=v1
CHAT_DEFAULT_PAGE_SIZE=100
CHAT_USE_SERVICE_ACCOUNT=false
CHAT_SERVICE_ACCOUNT_FILE=

# ============================================
# MIDDLEWARE CONFIGURATION
# ============================================
# Authentication Middleware
AUTH_MIDDLEWARE_ENABLED=true
AUTH_MIDDLEWARE_LOG_LEVEL=INFO

# MCP Auth Middleware
MCP_AUTH_ENABLED=true
MCP_AUTH_REALM=FastMCP2

# Qdrant Middleware
QDRANT_MIDDLEWARE_ENABLED=true
QDRANT_MIDDLEWARE_BATCH_SIZE=100
QDRANT_MIDDLEWARE_FLUSH_INTERVAL=60

# ============================================
# RATE LIMITING
# ============================================
RATE_LIMIT_ENABLED=true
RATE_LIMIT_REQUESTS_PER_MINUTE=60
RATE_LIMIT_REQUESTS_PER_HOUR=1000
RATE_LIMIT_BURST_SIZE=10

# ============================================
# LOGGING AND MONITORING
# ============================================
LOG_FORMAT=json
LOG_FILE=/var/log/fastmcp2/server.log
LOG_MAX_SIZE_MB=100
LOG_BACKUP_COUNT=5
LOG_INCLUDE_TIMESTAMP=true

# Metrics
ENABLE_METRICS=false
METRICS_PORT=9090
METRICS_PATH=/metrics

# ============================================
# DEVELOPMENT OPTIONS
# ============================================
DEBUG_MODE=false
VERBOSE_ERRORS=false
SHOW_STACK_TRACES=false
MOCK_GOOGLE_APIS=false
DISABLE_AUTH_CHECK=false

# ============================================
# CLOUDFLARE TUNNEL
# ============================================
TUNNEL_ENABLED=false
TUNNEL_HOST=localhost
TUNNEL_PORT=8002
TUNNEL_PATH=/mcp

# ============================================
# FEATURE FLAGS
# ============================================
ENABLE_ENHANCED_TOOLS=true
ENABLE_SMART_CARDS=true
ENABLE_MODULE_WRAPPER=true
ENABLE_CHAT_APPS=true
ENABLE_RESOURCE_TEMPLATING=true
```

## Environment Variables Reference

### Core Server Settings

| Variable | Type | Default | Description | Required |
|----------|------|---------|-------------|----------|
| `SERVER_NAME` | string | "FastMCP Google MCP Server" | Server display name | No |
| `SERVER_HOST` | string | "localhost" | Server bind address | No |
| `SERVER_PORT` | integer | 6339 | Server port | No |
| `BASE_URL` | string | "https://google-mcp.FastMCP.internal:6339" | Base URL for callbacks | Yes |
| `LOG_LEVEL` | string | "INFO" | Logging level (DEBUG, INFO, WARNING, ERROR) | No |

### Google OAuth Settings

| Variable | Type | Default | Description | Required |
|----------|------|---------|-------------|----------|
| `GOOGLE_CLIENT_ID` | string | - | OAuth 2.0 client ID | Yes |
| `GOOGLE_CLIENT_SECRET` | string | - | OAuth 2.0 client secret | Yes |
| `OAUTH_REDIRECT_URI` | string | Auto-generated | OAuth callback URI | No |
| `USE_GOOGLE_OAUTH` | boolean | true | Enable Google OAuth | No |
| `ENABLE_JWT_AUTH` | boolean | false | Enable JWT authentication | No |
| `OAUTH_SCOPES` | string | See defaults | Space-separated OAuth scopes | No |

### Security Settings

| Variable | Type | Default | Description | Required |
|----------|------|---------|-------------|----------|
| `CREDENTIAL_STORAGE_MODE` | enum | "FILE_PLAINTEXT" | Storage mode: FILE_PLAINTEXT, FILE_ENCRYPTED, MEMORY_ONLY, MEMORY_WITH_BACKUP | No |
| `SESSION_TIMEOUT_MINUTES` | integer | 60 | Session idle timeout | No |
| `MAX_SESSION_LIFETIME_HOURS` | integer | 24 | Maximum session lifetime | No |
| `AUTH_ENCRYPTION_KEY_FILE` | string | ".auth_encryption_key" | Path to encryption key file | No |

### SSL/TLS Settings

| Variable | Type | Default | Description | Required |
|----------|------|---------|-------------|----------|
| `ENABLE_HTTPS` | boolean | false | Enable HTTPS/SSL | No |
| `SSL_CERT_FILE` | string | - | Path to SSL certificate | If HTTPS enabled |
| `SSL_KEY_FILE` | string | - | Path to SSL private key | If HTTPS enabled |
| `SSL_CA_FILE` | string | - | Path to CA certificate | No |

### Storage Paths

| Variable | Type | Default | Description | Required |
|----------|------|---------|-------------|----------|
| `CREDENTIALS_DIR` | string | ".credentials" | Directory for stored credentials | No |
| `CACHE_DIR` | string | ".cache" | Directory for cache files | No |
| `TEMP_DIR` | string | "/tmp/fastmcp2" | Directory for temporary files | No |

### Qdrant Configuration

| Variable | Type | Default | Description | Required |
|----------|------|---------|-------------|----------|
| `QDRANT_HOST` | string | "localhost" | Qdrant server host | No |
| `QDRANT_PORT` | integer | 6333 | Qdrant HTTP port | No |
| `QDRANT_COLLECTION_NAME` | string | "tool_responses" | Collection name | No |
| `QDRANT_API_KEY` | string | - | Qdrant API key | No |
| `QDRANT_HTTPS` | boolean | false | Use HTTPS for Qdrant | No |
| `QDRANT_GRPC_PORT` | integer | 6334 | Qdrant gRPC port | No |
| `QDRANT_PREFER_GRPC` | boolean | false | Prefer gRPC over HTTP | No |

## Service-Specific Configuration

### Google Drive

```bash
# Drive-specific settings
DRIVE_API_VERSION=v3                    # API version
DRIVE_DEFAULT_PAGE_SIZE=100            # Default results per page
DRIVE_MAX_PAGE_SIZE=1000              # Maximum results per page
DRIVE_UPLOAD_CHUNK_SIZE=5242880       # Upload chunk size (5MB)
DRIVE_ENABLE_SHARED_DRIVES=true       # Enable shared drive support
DRIVE_DEFAULT_FIELDS=*                # Default fields to return
```

### Gmail

```bash
# Gmail-specific settings
GMAIL_API_VERSION=v1                   # API version
GMAIL_DEFAULT_PAGE_SIZE=50            # Default messages per page
GMAIL_MAX_RESULTS=500                 # Maximum results
GMAIL_BATCH_SIZE=50                   # Batch operation size
GMAIL_INCLUDE_SPAM_TRASH=false        # Include spam/trash in search
GMAIL_DEFAULT_FORMAT=full             # Default message format
```

### Google Calendar

```bash
# Calendar-specific settings
CALENDAR_API_VERSION=v3                # API version
CALENDAR_DEFAULT_MAX_RESULTS=250      # Default events per request
CALENDAR_DEFAULT_TIME_ZONE=UTC        # Default timezone
CALENDAR_EXPAND_RECURRING=true        # Expand recurring events
CALENDAR_SHOW_DELETED=false           # Show deleted events
```

### Google Chat

```bash
# Chat-specific settings
CHAT_API_VERSION=v1                    # API version
CHAT_DEFAULT_PAGE_SIZE=100            # Default messages per page
CHAT_USE_SERVICE_ACCOUNT=false        # Use service account auth
CHAT_SERVICE_ACCOUNT_FILE=            # Service account JSON file
CHAT_ENABLE_WEBHOOKS=true             # Enable webhook support
CHAT_WEBHOOK_TIMEOUT=10               # Webhook timeout seconds
```

## Security Configuration

### Production Security Settings

```bash
# Recommended production settings
CREDENTIAL_STORAGE_MODE=FILE_ENCRYPTED
ENABLE_HTTPS=true
SSL_CERT_FILE=/etc/ssl/certs/server.crt
SSL_KEY_FILE=/etc/ssl/private/server.key
SESSION_TIMEOUT_MINUTES=30
MAX_SESSION_LIFETIME_HOURS=8
RATE_LIMIT_ENABLED=true
DEBUG_MODE=false
VERBOSE_ERRORS=false
```

### Development Security Settings

```bash
# Development/testing settings
CREDENTIAL_STORAGE_MODE=FILE_PLAINTEXT
ENABLE_HTTPS=false
SESSION_TIMEOUT_MINUTES=120
DEBUG_MODE=true
VERBOSE_ERRORS=true
MOCK_GOOGLE_APIS=true
```

## Performance Tuning

### High-Load Configuration

```bash
# Performance optimizations for high load
MAX_CONCURRENT_REQUESTS=50
REQUEST_TIMEOUT_SECONDS=60
CACHE_TTL_SECONDS=7200
MAX_CACHE_SIZE_MB=500

# Connection pooling
CONNECTION_POOL_SIZE=20
CONNECTION_TIMEOUT=10
CONNECTION_RETRY_COUNT=3

# Qdrant optimizations
QDRANT_MIDDLEWARE_BATCH_SIZE=500
QDRANT_MIDDLEWARE_FLUSH_INTERVAL=30
QDRANT_PREFER_GRPC=true
```

### Memory-Optimized Configuration

```bash
# Memory-constrained environments
CREDENTIAL_STORAGE_MODE=MEMORY_ONLY
MAX_CACHE_SIZE_MB=50
CACHE_TTL_SECONDS=1800
MAX_CONCURRENT_REQUESTS=5
CONNECTION_POOL_SIZE=5
```

## Development vs Production

### Development Environment

```bash
# .env.development
SERVER_HOST=localhost
SERVER_PORT=6339
LOG_LEVEL=DEBUG
CREDENTIAL_STORAGE_MODE=FILE_PLAINTEXT
ENABLE_HTTPS=false
DEBUG_MODE=true
VERBOSE_ERRORS=true
MOCK_GOOGLE_APIS=false
RATE_LIMIT_ENABLED=false
```

### Production Environment

```bash
# .env.production
SERVER_HOST=0.0.0.0
SERVER_PORT=443
LOG_LEVEL=WARNING
CREDENTIAL_STORAGE_MODE=FILE_ENCRYPTED
ENABLE_HTTPS=true
DEBUG_MODE=false
VERBOSE_ERRORS=false
MOCK_GOOGLE_APIS=false
RATE_LIMIT_ENABLED=true
ENABLE_METRICS=true
```

### Staging Environment

```bash
# .env.staging
SERVER_HOST=staging.example.com
SERVER_PORT=6339
LOG_LEVEL=INFO
CREDENTIAL_STORAGE_MODE=FILE_ENCRYPTED
ENABLE_HTTPS=true
DEBUG_MODE=false
VERBOSE_ERRORS=true
MOCK_GOOGLE_APIS=false
RATE_LIMIT_ENABLED=true
```

## Configuration Validation

### Required Settings Checker

```python
# config/validator.py
def validate_config():
    """Validate required configuration"""
    required = {
        'GOOGLE_CLIENT_ID': 'OAuth client ID',
        'GOOGLE_CLIENT_SECRET': 'OAuth client secret',
        'BASE_URL': 'Base URL for callbacks'
    }
    
    missing = []
    for key, desc in required.items():
        if not os.getenv(key):
            missing.append(f"{key} ({desc})")
    
    if missing:
        raise ValueError(f"Missing required config: {', '.join(missing)}")
```

### Configuration Health Check

```bash
# Check configuration
python -c "from config.settings import settings; settings.validate()"

# Test OAuth configuration
curl https://google-mcp.FastMCP.internal:6339/health_check

# Verify SSL configuration
openssl s_client -connect localhost:6339 -showcerts
```

## Troubleshooting

### Common Configuration Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| "OAuth client ID not set" | Missing GOOGLE_CLIENT_ID | Add to .env file |
| "SSL certificate not found" | Invalid SSL_CERT_FILE path | Check file path and permissions |
| "Cannot connect to Qdrant" | Wrong QDRANT_HOST/PORT | Verify Qdrant is running |
| "Session timeout too short" | Low SESSION_TIMEOUT_MINUTES | Increase timeout value |
| "Rate limit exceeded" | Low rate limit settings | Adjust RATE_LIMIT_* values |

### Environment Variable Debugging

```bash
# Print all FastMCP Google MCP environment variables
env | grep -E '^(SERVER_|GOOGLE_|OAUTH_|CREDENTIAL_|SSL_|QDRANT_)'

# Validate .env file
python -m dotenv list

# Test with specific config
SERVER_PORT=8080 python server.py
```

### Configuration Precedence

1. **Command-line arguments** (highest priority)
2. **Environment variables**
3. **.env file**
4. **config/settings.py defaults** (lowest priority)

Example:
```bash
# Command-line overrides everything
SERVER_PORT=8080 python server.py

# Environment variable overrides .env
export SERVER_PORT=7000
python server.py

# .env file used if no env var
# SERVER_PORT=6339 in .env
python server.py
```

## Best Practices

1. **Use .env files**: Keep configuration out of code
2. **Separate environments**: Use .env.development, .env.production
3. **Secure secrets**: Never commit secrets to version control
4. **Validate early**: Check configuration at startup
5. **Document changes**: Update this guide when adding config
6. **Use defaults**: Provide sensible defaults for optional settings
7. **Type safety**: Validate and cast environment variables
8. **Logging**: Log configuration (except secrets) at startup

## Configuration Templates

### Minimal Production Setup

```bash
# .env.prod.minimal
GOOGLE_CLIENT_ID=your-client-id
GOOGLE_CLIENT_SECRET=your-client-secret
CREDENTIAL_STORAGE_MODE=FILE_ENCRYPTED
ENABLE_HTTPS=true
SSL_CERT_FILE=/etc/ssl/cert.pem
SSL_KEY_FILE=/etc/ssl/key.pem
```

### Full-Featured Setup

```bash
# .env.full
# [Include all variables from Complete Example Configuration above]
```

### Docker Configuration

```dockerfile
# Dockerfile environment
ENV SERVER_HOST=0.0.0.0
ENV SERVER_PORT=8080
ENV CREDENTIAL_STORAGE_MODE=MEMORY_ONLY
ENV LOG_LEVEL=INFO
```

### Kubernetes ConfigMap

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: fastmcp2-config
data:
  SERVER_HOST: "0.0.0.0"
  SERVER_PORT: "8080"
  LOG_LEVEL: "INFO"
  CREDENTIAL_STORAGE_MODE: "MEMORY_WITH_BACKUP"
```

## Migration Guide

### From v0.x to v1.0

```bash
# Old configuration (v0.x)
DRIVE_EMAIL=user@gmail.com  # DEPRECATED
USE_SERVICE_ACCOUNT=true    # DEPRECATED

# New configuration (v1.0)
# Email now passed per request
# Authentication via OAuth only
USE_GOOGLE_OAUTH=true
```

---

**Document Version**: 1.0.0  
**Last Updated**: 2024-01-15  
**Next Review**: 2024-04-15

For additional support, see [Security Implementation](./SECURITY_IMPLEMENTATION.md) and [API Reference](./api-reference/README.md).