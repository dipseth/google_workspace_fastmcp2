# FastMCP2 Drive Upload Server Tests

This directory contains integration tests for the FastMCP2 Google Drive Upload Server using the FastMCP Client SDK.

## Testing Philosophy

All tests are designed to run against a **live, running server instance**. This approach ensures:
- Tests validate real server behavior
- Integration between all components is properly tested
- OAuth flows and middleware work as expected
- Qdrant integration functions correctly

## Prerequisites

### 1. Install Dependencies

```bash
# Install test dependencies
uv pip install pytest pytest-asyncio fastmcp
```

### 2. Start the Server

The server must be running before executing tests:

```bash
# In one terminal, start the server
cd fastmcp2_drive_upload
uv run python server.py
```

The server will start on `http://localhost:8002` by default.

### 3. Optional: Start Qdrant

For Qdrant integration tests to fully function:

```bash
# Run Qdrant using Docker
docker run -p 6333:6333 qdrant/qdrant
```

## Running Tests

### Run All Tests

```bash
# From the project root
uv run pytest tests/

# Or with verbose output
uv run pytest tests/ -v
```

### Run Specific Test Files

```bash
# Run only MCP client tests
uv run pytest tests/test_mcp_client.py -v

# Run only Qdrant integration tests
uv run pytest tests/test_qdrant_integration.py -v
```

### Run Specific Test Classes or Methods

```bash
# Run a specific test class
uv run pytest tests/test_mcp_client.py::TestMCPServer -v

# Run a specific test method
uv run pytest tests/test_mcp_client.py::TestMCPServer::test_health_check_tool -v
```

## Test Structure

### test_mcp_client.py
Main integration test suite using the FastMCP Client SDK:
- **TestMCPServer**: Basic server connectivity and tool testing
- **TestQdrantIntegration**: Qdrant-specific tool testing
- **TestGmailTools**: Gmail tool availability testing
- **TestErrorHandling**: Error scenarios and edge cases

### test_qdrant_integration.py
Comprehensive Qdrant integration testing:
- Tests response storage in Qdrant
- Validates semantic search functionality
- Checks analytics and reporting

## Environment Variables

Tests support environment variable configuration:

```bash
# Server configuration
export MCP_SERVER_HOST=localhost
export MCP_SERVER_PORT=8002
export MCP_SERVER_URL=http://localhost:8002/mcp/

# Run tests with custom server location
MCP_SERVER_PORT=8003 uv run pytest tests/
```

## Writing New Tests

All new tests should follow the FastMCP Client SDK pattern:

```python
import pytest
from fastmcp import Client

class TestNewFeature:
    @pytest.fixture
    async def client(self):
        """Create a client connected to the running server."""
        client = Client("http://localhost:8002/mcp/")
        async with client:
            yield client
    
    @pytest.mark.asyncio
    async def test_new_tool(self, client):
        """Test a new tool."""
        # List available tools
        tools = await client.list_tools()
        tool_names = [tool.name for tool in tools]
        assert "new_tool_name" in tool_names
        
        # Call the tool
        result = await client.call_tool("new_tool_name", {
            "param1": "value1",
            "param2": "value2"
        })
        
        # Validate results
        assert len(result) > 0
        content = result[0].text
        assert "expected_content" in content
```

## Common Test Patterns

### 1. Tool Availability Testing
```python
tools = await client.list_tools()
tool_names = [tool.name for tool in tools]
assert "expected_tool" in tool_names
```

### 2. Tool Execution Testing
```python
result = await client.call_tool("tool_name", {"param": "value"})
assert len(result) > 0
assert "expected" in result[0].text
```

### 3. Error Handling Testing
```python
with pytest.raises(ToolError):
    await client.call_tool("invalid_tool", {})
```

### 4. Resource Listing
```python
resources = await client.list_resources()
assert len(resources) > 0
```

## Debugging Failed Tests

### 1. Check Server Logs
The server outputs detailed logs. Check the terminal where the server is running for error messages.

### 2. Verify Server is Running
```bash
# Check if server is responding
curl http://localhost:8002/mcp/
```

### 3. Use Verbose Pytest Output
```bash
uv run pytest tests/ -vvs
```

### 4. Check Environment Variables
```bash
# Ensure .env file exists and is properly configured
cat .env
```

## CI/CD Integration

For CI/CD pipelines:

1. Start the server in the background:
   ```yaml
   - name: Start MCP Server
     run: |
       cd fastmcp2_drive_upload
       uv run python server.py &
       sleep 5  # Wait for server to start
   ```

2. Run tests:
   ```yaml
   - name: Run Tests
     run: |
       cd fastmcp2_drive_upload
       uv run pytest tests/ -v
   ```

3. Optional: Use Docker Compose for Qdrant:
   ```yaml
   services:
     qdrant:
       image: qdrant/qdrant
       ports:
         - "6333:6333"
   ```

## Troubleshooting

### "Session terminated" Errors
- Ensure the server is running
- Check the server URL includes `/mcp/` endpoint
- Verify no firewall is blocking localhost connections

### "Tool not found" Errors
- Confirm the server has fully initialized
- Check server logs for tool registration messages
- Ensure all dependencies are installed

### OAuth/Authentication Errors
- Verify `.env` file contains valid Google OAuth credentials
- Check `GOOGLE_CLIENT_SECRETS_FILE` path is correct
- Ensure OAuth redirect URI matches server configuration

## Best Practices

1. **Always test against a running server** - Never mock the MCP protocol
2. **Use fixtures for client setup** - Ensures proper cleanup
3. **Test both success and error cases** - Validate error handling
4. **Keep tests focused** - One test per behavior
5. **Use descriptive test names** - Should explain what's being tested
6. **Clean up test data** - Don't leave test artifacts in Qdrant

## Future Enhancements

- [ ] Add performance benchmarking tests
- [ ] Implement load testing for concurrent operations
- [ ] Add OAuth flow integration tests
- [ ] Create test data fixtures for Gmail operations
- [ ] Add WebSocket transport testing