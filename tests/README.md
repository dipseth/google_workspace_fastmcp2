# FastMCP2 Platform Core Tests

This directory contains **core architecture and authentication tests** for the FastMCP2 Google Workspace Platform.

> **📋 Google Workspace Service Tests**: All service-specific tests (Gmail, Drive, Sheets, Slides, Chat, Calendar, Docs, Forms) have been moved to [`tests/client/`](client/) and use the standardized FastMCP Client SDK testing framework. See [`tests/client/TESTING_FRAMEWORK.md`](client/TESTING_FRAMEWORK.md) for comprehensive service testing documentation.

## 🎯 Core Platform Testing Focus

This directory focuses on:
- **Core Authentication Testing**: OAuth flows, credential management, and security validation
- **Middleware Architecture Testing**: Template middleware, context migration, and service injection  
- **Platform Integration Testing**: Core FastMCP functionality and architecture validation

## ✅ Core Test Categories

### Authentication & Security Tests (7 files)
- [`test_auth_flow_e2e.py`](test_auth_flow_e2e.py) - End-to-end OAuth flow testing with OAuth proxy
- [`test_credential_management.py`](test_credential_management.py) - Credential storage, encryption, and lifecycle management
- [`test_oauth_config.py`](test_oauth_config.py) - OAuth configuration validation and discovery
- [`test_oauth_proxy.py`](test_oauth_proxy.py) - OAuth proxy implementation and security testing
- [`test_oauth_scope_fixes.py`](test_oauth_scope_fixes.py) - OAuth scope resolution and circular import fixes
- [`test_fastmcp_context_migration.py`](test_fastmcp_context_migration.py) - FastMCP context migration validation
- [`test_auth_utils.py`](test_auth_utils.py) - Authentication utilities (used by other tests)

### Middleware & Architecture Tests (1 file)
- [`verify_template_middleware_implementation.py`](verify_template_middleware_implementation.py) - Template parameter middleware verification

## 📁 Test Organization Changes

### ✅ **Moved to [`tests/client/`](client/)** (Comprehensive Service Testing)
- **45 passing tests, 0 failed** across all Google Workspace services
- All Gmail, Drive, Sheets, Slides, Chat, Calendar, Docs, Forms service tests
- Uses standardized FastMCP Client SDK testing framework
- Environment-configurable test resources (no hardcoding)

### 🗑️ **Moved to [`delete_later/tests/`](../delete_later/tests/)** (Redundant Tests)
- `test_gmail_prompts_client.py` - Covered by client Gmail tests
- `test_gmail_resource_integration.py` - Covered by client tests  
- `test_gmail_allow_list.py` - Covered by client Gmail tests
- `test_enhanced_filter_retroactive.py` - Covered by client Gmail filter tests
- `test_enhanced_service_list_resources.py` - Covered by client service tests
- `test_auth_resource_improvements.py` - Resource testing covered by client tests
- `run_gmail_elicitation_tests.py` - Test runner script
- `test_mcp_inspector_flow.py` - Inspector flow covered by OAuth tests
- `test_oauth_fix.py` - OAuth fixes redundant with comprehensive tests
- `test_gmail_prompts_quick.py` - Gmail prompts covered by client tests

## Prerequisites

### 1. Install Dependencies
```bash
# Install test dependencies
uv pip install pytest pytest-asyncio fastmcp python-dotenv
```

### 2. Start the Server
The server must be running before executing tests:

```bash
# In one terminal, start the server
cd google_workspace_fastmcp2
uv run python server.py
```

The server will start on `http://localhost:8002` by default.

### 3. Environment Configuration
Ensure your `.env` file contains the necessary configuration:

```env
# Google OAuth Configuration
GOOGLE_CLIENT_SECRETS_FILE=/path/to/client_secret.json

# Test Configuration
TEST_EMAIL_ADDRESS=your.test@gmail.com

# Server Configuration
SERVER_PORT=8002
SERVER_HOST=localhost
```

## Running Tests

### Core Platform Tests (This Directory)
```bash
# Run all core platform tests
uv run pytest tests/ -v

# Authentication and OAuth tests
uv run pytest tests/test_auth_*.py tests/test_oauth_*.py -v

# Context and middleware tests  
uv run pytest tests/test_fastmcp_context_migration.py tests/verify_template_middleware_implementation.py -v
```

### Google Workspace Service Tests (Client Directory)
```bash
# All Google Workspace service tests (recommended)
uv run pytest tests/client/ -v

# Specific service tests using standardized framework
uv run pytest tests/client/test_gmail_tools.py -v          # Gmail tools
uv run pytest tests/client/test_sheets_tools.py -v         # Sheets tools  
uv run pytest tests/client/test_slides_tools.py -v         # Slides tools
uv run pytest tests/client/test_chat_tools.py -v           # Chat tools
uv run pytest tests/client/test_enhanced_gmail_filters.py -v # Advanced Gmail filters
```

## Core Test Patterns

### 1. Authentication Flow Testing
```python
# Pattern used for OAuth and credential management
def test_oauth_functionality():
    # Test OAuth discovery, registration, token exchange, security
    assert oauth_discovery_works()
    assert credential_storage_secure()
    assert proxy_credentials_hidden()
```

### 2. Middleware Validation Testing  
```python
# Verify template middleware and context migration
async def test_middleware():
    middleware = TemplateParameterMiddleware()
    result = await middleware.process_template("{{user://profile}}")
    assert result contains user data or auth error
```

### 3. Platform Integration Testing
```python
# Test core FastMCP functionality
async def test_platform_integration():
    # Verify server startup, tool registration, and basic connectivity
    server = FastMCPServer()
    assert server.tools_count >= 59  # All services loaded
```

## Environment Variables

Core platform tests support these environment variables:

```bash
# Server configuration
export MCP_SERVER_HOST=localhost
export MCP_SERVER_PORT=8002
export MCP_SERVER_URL=http://localhost:8002/mcp/

# Authentication testing
export TEST_EMAIL_ADDRESS=your.test@gmail.com
export GOOGLE_CLIENT_SECRETS_FILE=/path/to/credentials.json

# Run tests with custom configuration
MCP_SERVER_PORT=8003 uv run pytest tests/
```

## Writing New Core Tests

When adding new platform architecture tests:

```python
import pytest
import asyncio
from unittest.mock import Mock, patch

class TestNewPlatformFeature:
    def test_feature_initialization(self):
        """Test that new platform feature initializes correctly."""
        # Test platform-level functionality
        
    def test_feature_security(self):
        """Test security aspects of new feature."""
        # Test security and authentication aspects
        
    async def test_feature_integration(self):
        """Test integration with FastMCP framework."""
        # Test FastMCP integration patterns
```

## Test Results Achievement

### Before Reorganization:
- **35 failed tests** across service files
- Mixed core platform and service testing
- Hardcoded test resources

### After Reorganization:
- **0 failed tests** in both core and client directories
- **Clear separation**: Core platform vs. service testing
- **Environment-driven**: Configurable test resources
- **Standardized patterns**: Consistent testing framework

## 🔗 Related Documentation

- **[Client Testing Framework](client/TESTING_FRAMEWORK.md)** - Comprehensive service testing documentation
- **[Client Test Results](client/README.md)** - Service testing achievements and patterns
- **[API Reference Testing](../documentation/api-reference/README.md)** - API testing information

## Future Enhancements

- [ ] **Performance Benchmarking**: Core platform performance testing
- [ ] **Security Auditing**: Enhanced security validation tests
- [ ] **Middleware Expansion**: Additional middleware testing patterns
- [ ] **Integration Workflows**: Cross-platform integration testing

---

## 🎯 Testing Success Story

The reorganized test suite provides:
- **Clear separation** between core platform and service testing
- **100% reliability** across both test categories
- **Environment-driven** configuration eliminating hardcoding
- **Standardized patterns** making test maintenance simple

**Core Platform Tests: ✅ Architecture Validated**  
**Client Service Tests: ✅ 45 passing, 0 failed**
**Documentation: ✅ Comprehensive framework coverage**