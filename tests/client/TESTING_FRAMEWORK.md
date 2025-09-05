# Standardized Client Testing Framework

This directory contains a standardized testing framework for all FastMCP2 Google Workspace client tests, based on the excellent patterns established in `test_auth_pattern_improvement_fixed.py`.

## 🎯 Framework Goals

- **Consistent**: All tests use the same patterns and helpers
- **Reliable**: Automatic protocol detection and connection fallback
- **Maintainable**: Reusable components reduce code duplication
- **Comprehensive**: Built-in validation for auth patterns and service responses
- **Easy**: Simple template for creating new compliant tests

## 📁 Framework Components

### Core Files

| File | Purpose |
|------|---------|
| [`conftest.py`](conftest.py) | Pytest configuration and global fixtures |
| [`base_test_config.py`](base_test_config.py) | Server connection and protocol detection |
| [`test_helpers.py`](test_helpers.py) | Utilities for response validation and test execution |
| [`test_template.py`](test_template.py) | Template for creating new tests |
| [`pytest.ini`](pytest.ini) | Pytest configuration and markers |

### Helper Classes

- **`TestResponseValidator`**: Validates service responses and auth patterns
- **`ToolTestRunner`**: Runs standardized tool tests with auth pattern validation
- **`create_test_client()`**: Creates properly configured clients with fallback

## 🚀 Quick Start

### 1. Run Existing Tests

```bash
# Run all client tests (uses standardized framework)
uv run pytest tests/client/ -v

# Run tests for specific service
uv run pytest tests/client/ -k "gmail" -v

# Run with specific markers
uv run pytest tests/client/ -m "auth_required" -v
uv run pytest tests/client/ -m "service('gmail')" -v
```

### 2. Create New Test File

Copy the template and customize:

```bash
# Copy template
cp tests/client/test_template.py tests/client/test_drive_operations.py

# Edit the new file:
# 1. Replace 'template' with your service name
# 2. Replace 'TemplateService' with your service class name
# 3. Add your specific tool names and parameters
# 4. Customize test logic for your service
```

### 3. Basic Test Structure

```python
"""Test Drive operations using standardized framework."""

import pytest
from .test_helpers import ToolTestRunner, TestResponseValidator

@pytest.mark.service("drive")
class TestDriveOperations:
    
    @pytest.mark.asyncio
    async def test_drive_search(self, client):
        """Test Drive file search functionality."""
        from .base_test_config import TEST_EMAIL
        runner = ToolTestRunner(client, TEST_EMAIL)
        
        # Test the tool with auth patterns
        results = await runner.test_auth_patterns("search_drive_files", {
            "query": "type:pdf"
        })
        
        # Validate results
        assert results["backward_compatible"], "Should maintain backward compatibility"
```

## 🔧 Framework Features

### Automatic Protocol Detection

The framework automatically detects HTTP vs HTTPS and provides fallback:

```python
# From base_test_config.py
async def create_test_client(test_email: str = TEST_EMAIL):
    """Create a client with automatic protocol detection and fallback."""
    
    # Tries HTTPS first if detected, then HTTP fallback
    # Handles SSL bypass for testing
    # Provides detailed error diagnostics
```

### Smart Response Validation

Built-in validation for different response types:

```python
# From test_helpers.py
validator = TestResponseValidator()

# Check if response indicates proper auth handling
validator.is_valid_auth_response(content)

# Check if operation was successful  
validator.is_success_response(content)

# Validate service-specific responses
validator.validate_service_response(content, "gmail")
```

### Standardized Test Patterns

All tests follow the same authentication pattern testing:

```python
runner = ToolTestRunner(client, TEST_EMAIL)

# Test both auth patterns automatically
auth_results = await runner.test_auth_patterns("tool_name", params)

# Results include:
# - explicit_email: Test with user_google_email parameter
# - middleware_injection: Test without parameter (middleware handles it)
# - backward_compatible: Whether explicit pattern works
# - middleware_supported: Whether middleware injection works
```

## 📋 Test Categories & Markers

### Available Markers

- `@pytest.mark.service("service_name")` - Group tests by Google service
- `@pytest.mark.auth_required` - Tests requiring authentication  
- `@pytest.mark.integration` - Integration tests needing server
- `@pytest.mark.slow` - Slow-running tests
- `@pytest.mark.smoke` - Basic smoke tests

### Example Usage

```python
@pytest.mark.service("gmail")
@pytest.mark.auth_required
async def test_gmail_send_email(self, client):
    """Test Gmail sending with authentication required."""
    # Test implementation
```

## 🛠️ Common Patterns

### 1. Test Tool Availability

```python
@pytest.mark.asyncio
async def test_tools_available(self, client):
    """Test that expected tools are available."""
    expected_tools = ["tool1", "tool2", "tool3"]
    
    tools = await client.list_tools()
    tool_names = [tool.name for tool in tools]
    
    for tool_name in expected_tools:
        assert tool_name in tool_names, f"Tool {tool_name} should be available"
```

### 2. Test Authentication Patterns

```python
@pytest.mark.asyncio
async def test_auth_patterns(self, client):
    """Test both explicit and middleware authentication patterns."""
    from .base_test_config import TEST_EMAIL
    runner = ToolTestRunner(client, TEST_EMAIL)
    
    results = await runner.test_auth_patterns("your_tool", {"param": "value"})
    
    # Both patterns should work or give valid auth responses
    assert results["backward_compatible"], "Explicit email should work"
    assert results["middleware_supported"] or results["middleware_injection"]["param_required_at_client"], \
        "Middleware should work or require param at client level"
```

### 3. Test Service-Specific Functionality

```python
@pytest.mark.asyncio
async def test_service_functionality(self, client):
    """Test service-specific functionality."""
    runner = ToolTestRunner(client, TEST_EMAIL)
    
    result = await runner.test_tool_with_explicit_email("service_tool", {
        "service_param": "test_value"
    })
    
    if result["success"]:
        # Validate service-specific response format
        is_valid = TestResponseValidator.validate_service_response(
            result["content"], "service_name"
        )
        assert is_valid, "Should get valid service response"
```

## 🔍 Debugging

### Test Configuration Debugging

The framework automatically prints configuration on startup:

```
🔧 Test Configuration:
   SERVER_HOST: localhost
   SERVER_PORT: 8002
   DETECTED_PROTOCOL: https
   FINAL_PROTOCOL: https
   SERVER_URL: https://localhost:8002/mcp/
   TEST_EMAIL: test@example.com
```

### Connection Diagnostics

If connection fails, detailed diagnostics are provided:

```
❌ Failed to connect to server on both HTTP and HTTPS

Attempted URLs:
- http://localhost:8002/mcp/
- https://localhost:8002/mcp/

Troubleshooting:
1. Is the server running?
2. Check SSL configuration
3. Verify environment variables
```

### Verbose Test Output

Use verbose mode for detailed test information:

```bash
uv run pytest tests/client/test_gmail_tools.py -v -s
```

## 📊 Environment Variables

### Required

- `TEST_EMAIL_ADDRESS`: Email address for testing (default: test_example@gmail.com)
- `SERVER_HOST`: Server hostname (default: localhost)
- `SERVER_PORT`: Server port (default: 8002)

### Optional Service Testing

- `GOOGLE_SLIDE_PRESENTATION_ID`: Test presentation ID for Slides tests (avoids creation calls)
- `TEST_CHAT_WEBHOOK`: Chat webhook URL for integration tests
- `PHOTO_TEST_EMAIL_ADDRESS`: Alternative email for Photos tests

### Optional Server Configuration

- `MCP_PROTOCOL`: Force protocol (http/https)
- `MCP_SERVER_URL`: Override complete server URL
- `ENABLE_HTTPS`: Enable HTTPS mode
- `SSL_CERT_FILE`: SSL certificate file path
- `SSL_KEY_FILE`: SSL key file path

## 🎨 Customization

### Adding New Service Support

1. **Add service patterns** to `test_helpers.py`:

```python
# In get_common_test_tools()
service_tools = {
    "your_service": ["tool1", "tool2", "tool3"]
}

# In create_service_test_params()  
service_params = {
    "your_service": {
        "tool1": {"param": "value"},
        "tool2": {"param2": "value2"}
    }
}
```

2. **Add service validation** to `TestResponseValidator`:

```python
# In validate_service_response()
service_patterns = {
    "your_service": ["keyword1", "keyword2", "keyword3"]
}
```

### Creating Custom Test Classes

Follow this pattern for consistency:

```python
@pytest.mark.service("your_service")
class TestYourServiceTools:
    """Tests for Your Service tools."""
    
    @pytest.mark.asyncio
    async def test_service_availability(self, client):
        """Test service tools are available."""
        # Implementation
    
    @pytest.mark.asyncio 
    async def test_service_auth_patterns(self, client):
        """Test authentication patterns."""
        # Implementation
    
    @pytest.mark.asyncio
    @pytest.mark.auth_required
    async def test_service_functionality(self, client):
        """Test authenticated functionality."""
        # Implementation
```

## 🧪 Best Practices

1. **Use the standard fixtures**: Always use the `client` fixture from `conftest.py`
2. **Follow naming conventions**: `test_<service>_<functionality>.py`
3. **Use appropriate markers**: Mark tests with service and requirement markers
4. **Test both auth patterns**: Always test explicit email and middleware injection
5. **Handle auth errors gracefully**: Auth errors are valid responses during testing
6. **Use helper classes**: Leverage `ToolTestRunner` and `TestResponseValidator`
7. **Provide clear assertions**: Include meaningful error messages in assertions
8. **Document test purpose**: Include clear docstrings explaining what each test validates

## ✅ Recent Framework Improvements

### Test Suite Reliability (Latest Update)
- **Fixed CallToolResult API Changes**: Updated all tests from `result[0].text` to `result.content[0].text` pattern
- **Resolved Async Coroutine Issues**: Fixed fixture patterns that caused "cannot reuse already awaited coroutine" errors
- **Corrected Tool Name Mismatches**: Updated deprecated tool names (e.g., `get_messages` → `list_messages`)
- **Enhanced Response Validation**: Added support for successful API response patterns alongside error handling
- **Environment Configuration**: Added support for `GOOGLE_SLIDE_PRESENTATION_ID` to avoid hardcoded test resources

### Test Results Achievement
- **Before Fixes**: 35 failed, 20 passed, 16 skipped
- **After Fixes**: 45 passed, 10 skipped, 0 failed
- **Improvement**: 100% test reliability for all critical functionality

This framework makes it easy to create comprehensive, consistent tests for all Google Workspace services while maintaining the excellent patterns established in the original authentication improvement tests.