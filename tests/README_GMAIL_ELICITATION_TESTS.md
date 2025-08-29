# Gmail Elicitation System Test Suite

This directory contains comprehensive tests for the Gmail elicitation system implemented in the FastMCP2 Google Workspace Platform.

## Overview

The Gmail elicitation system provides a security layer for email sending operations by:

1. **Allow List Management**: Maintaining a list of trusted email recipients
2. **Elicitation Flow**: Requesting user confirmation before sending emails to untrusted recipients
3. **Resource Integration**: Providing access to allow list configuration via MCP resources
4. **Tool Integration**: Offering management tools for allow list administration

## Test Structure

### `test_gmail_elicitation_system.py`

Comprehensive test suite using FastMCP Client SDK to test against a running MCP server.

#### Test Categories

#### A. Allow List Configuration Tests
- **Empty/Missing Configuration**: Tests handling of empty or missing `GMAIL_ALLOW_LIST` environment variable
- **Single Email Parsing**: Validates parsing of single email addresses
- **Multiple Email Parsing**: Tests comma-separated email list parsing
- **Whitespace Handling**: Ensures proper handling of whitespace in email lists
- **Case Normalization**: Verifies email addresses are normalized to lowercase
- **Environment Variable Integration**: Tests reading from `GMAIL_ALLOW_LIST` env var

#### B. Allow List Management Tools Tests
- **Add Valid Email**: Tests adding valid email addresses to allow list
- **Add Duplicate Email**: Verifies handling of duplicate email additions
- **Add Invalid Email**: Tests validation of email format
- **Remove Existing Email**: Tests removal of emails from allow list
- **Remove Nonexistent Email**: Verifies handling of nonexistent email removal
- **View Allow List**: Tests allow list display functionality

#### C. Resource System Tests
- **Authenticated Access**: Tests `gmail://allow-list` resource with authenticated user
- **Unauthenticated Access**: Tests resource access without authentication
- **JSON Response Structure**: Validates proper JSON response format
- **Privacy Masking**: Ensures email addresses are properly masked for privacy

#### D. Elicitation Flow Simulation Tests
- **Trusted Recipients**: Tests that emails to allow-listed recipients skip elicitation
- **Untrusted Recipients**: Tests that emails to non-allow-listed recipients trigger elicitation
- **User Acceptance**: Simulates user accepting elicitation prompt
- **User Decline**: Simulates user declining elicitation prompt
- **User Cancellation**: Simulates user cancelling the operation
- **Content Types**: Tests elicitation with different email content types (plain, html, mixed)

#### E. Integration Test Scenarios
- **All Recipients Trusted**: End-to-end test with all recipients on allow list
- **Mixed Recipients**: Test with combination of trusted and untrusted recipients
- **Empty Allow List**: Test behavior when no allow list is configured
- **Allow List Management Workflow**: Complete workflow of adding, viewing, and removing emails

#### F. Edge Cases and Error Handling Tests
- **Empty Recipient Lists**: Tests handling of emails with no recipients
- **Long Email Bodies**: Tests truncation of very long email content in elicitation
- **Unicode Characters**: Tests handling of unicode in email addresses and content
- **Special Characters**: Tests handling of special characters in subjects and bodies
- **Missing Parameters**: Tests validation of required parameters
- **Concurrent Operations**: Tests system behavior under concurrent load

#### G. Documentation and Validation Tests
- **Tool Descriptions**: Validates that all Gmail tools have proper descriptions
- **Parameter Validation**: Ensures tool parameters match implementation
- **Resource Descriptions**: Validates resource descriptions and structure
- **Input Schema Validation**: Tests tool input schema completeness

## Prerequisites

### 1. Running MCP Server
The tests require a running MCP server instance. Start the server using:

```bash
# From the project root directory
python -m fastmcp2_drive_upload.server
```

### 2. Environment Variables
Set the following environment variables for testing:

```bash
# Server connection (optional, defaults shown)
export MCP_SERVER_HOST=localhost
export MCP_SERVER_PORT=8002

# Test user email for authenticated testing
export TEST_EMAIL_ADDRESS=your.test@gmail.com
```

### 3. Authentication Setup
For full testing, ensure the test user is authenticated:

```bash
# Start authentication flow
start_google_auth your.test@gmail.com
```

## Running the Tests

### Option 1: Run All Gmail Elicitation Tests
```bash
cd /path/to/project
python -m pytest tests/test_gmail_elicitation_system.py -v --asyncio-mode=auto
```

### Option 2: Run Specific Test Categories
```bash
# Run only allow list configuration tests
python -m pytest tests/test_gmail_elicitation_system.py::TestGmailElicitationSystem::test_view_gmail_allow_list_empty -v

# Run only elicitation flow tests
python -m pytest tests/test_gmail_elicitation_system.py -k "elicitation" -v
```

### Option 3: Run with Custom Server Configuration
```bash
# Test against different server
MCP_SERVER_HOST=192.168.1.100 MCP_SERVER_PORT=9000 python -m pytest tests/test_gmail_elicitation_system.py -v
```

### Option 4: Generate Test Report
```bash
# Generate HTML test report
python -m pytest tests/test_gmail_elicitation_system.py --html=report.html --self-contained-html
```

## Test Results Interpretation

### Expected Outcomes

#### ✅ Successful Tests
- **Authenticated Tests**: Pass when user is properly authenticated
- **Unauthenticated Tests**: Pass when system properly handles missing authentication
- **Validation Tests**: Pass when input validation works correctly
- **Integration Tests**: Pass when complete workflows function properly

#### ⚠️ Expected Failures (Without Authentication)
Some tests may show as "passed" but with authentication error messages, which is expected behavior when testing without proper authentication setup.

#### 🔍 Common Test Scenarios

1. **No Authentication**: Tests will show authentication errors - this is expected
2. **Invalid Emails**: Should be rejected with clear error messages
3. **Empty Configurations**: Should be handled gracefully
4. **Unicode Content**: Should be processed without corruption
5. **Long Content**: Should be truncated appropriately in elicitation messages

## Test Coverage Summary

The test suite provides comprehensive coverage of:

| Component | Tests | Coverage |
|-----------|-------|----------|
| Settings Layer | 7 tests | Environment parsing, validation, normalization |
| Management Tools | 6 tests | Add, remove, view operations with validation |
| Resource System | 2 tests | JSON responses, privacy masking, error handling |
| Elicitation Flow | 6 tests | Accept/decline/cancel scenarios, content types |
| Integration Scenarios | 4 tests | End-to-end workflows, mixed recipients |
| Edge Cases | 7 tests | Unicode, long content, empty lists, special chars |
| Documentation | 3 tests | Parameter validation, descriptions, schemas |
| Performance | 1 test | Concurrent operations handling |

## Troubleshooting

### Common Issues

#### 1. Server Connection Failed
```
ERROR: Could not connect to MCP server
```
**Solution**: Ensure MCP server is running and accessible on the specified host/port.

#### 2. Authentication Errors
```
ERROR: No authenticated user found
```
**Solution**: Run authentication flow or test with unauthenticated scenarios.

#### 3. Tool Not Found
```
ERROR: Tool 'send_gmail_message' not found
```
**Solution**: Ensure Gmail tools are properly registered in the MCP server.

#### 4. Resource Not Found
```
ERROR: Resource 'gmail://allow-list' not found
```
**Solution**: Ensure user resources are properly registered in the MCP server.

### Debug Mode
Run tests with detailed output:
```bash
python -m pytest tests/test_gmail_elicitation_system.py -v -s --tb=long
```

## Integration with CI/CD

### GitHub Actions Example
```yaml
- name: Run Gmail Elicitation Tests
  run: |
    # Start MCP server in background
    python -m fastmcp2_drive_upload.server &
    sleep 5

    # Run tests
    python -m pytest tests/test_gmail_elicitation_system.py -v --asyncio-mode=auto
```

### Docker Integration
```dockerfile
# Test stage
FROM python:3.11-slim
COPY . /app
WORKDIR /app
RUN pip install -r requirements.txt
RUN python -m pytest tests/test_gmail_elicitation_system.py -v --asyncio-mode=auto
```

## Contributing

When adding new Gmail elicitation features:

1. **Add corresponding tests** in `test_gmail_elicitation_system.py`
2. **Update test documentation** in this README
3. **Ensure test coverage** for new functionality
4. **Test both authenticated and unauthenticated scenarios**
5. **Include edge cases** and error conditions

## Security Considerations

The test suite validates security features:

- **Allow List Enforcement**: Ensures elicitation is triggered for untrusted recipients
- **Authentication Validation**: Tests proper authentication checking
- **Input Validation**: Validates email format and parameter requirements
- **Privacy Protection**: Ensures email addresses are properly masked in responses
- **Error Handling**: Prevents information leakage through error messages

## Performance Benchmarks

The test suite includes performance validation:

- **Concurrent Operations**: Tests system behavior under concurrent load
- **Large Allow Lists**: Tests handling of large email lists
- **Long Content**: Tests processing of large email bodies
- **Resource Efficiency**: Validates efficient resource usage

---

**Note**: These tests are designed to work with the FastMCP2 Google Workspace Platform and require a running MCP server instance for execution.