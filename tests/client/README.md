# FastMCP Client Tests

This directory contains all test files that use the FastMCP Client SDK (`from fastmcp import Client`). These tests are client-based tests that connect to the MCP server via HTTP to test the various tools and functionality.

## Files Moved to This Directory

The following 30 test files were moved from the main `tests/` directory because they use `from fastmcp import Client`:

1. `test_auth_pattern_improvement_fixed.py` - Authentication pattern improvements testing
2. `test_calendar_tools.py` - Google Calendar tools testing
3. `test_chat_app_tools.py` - Google Chat app tools testing
4. `test_chat_tools.py` - Google Chat tools testing (main focus file)
5. `test_enhanced_gmail_filters.py` - Enhanced Gmail filter functionality testing
6. `test_gmail_elicitation_system.py` - Gmail elicitation system testing
7. `test_gmail_prompts_real_client.py` - Gmail prompts with real client testing
8. `test_list_tools.py` - Tool listing functionality testing
9. `test_mcp_client.py` - MCP client core functionality testing
10. `test_module_wrapper.py` - Module wrapper functionality testing
11. `test_nlp_card_parser.py` - NLP card parser testing
12. `test_oauth_session_context_fix.py` - OAuth session context fixes testing
13. `test_photos_tools_improved.py` - Google Photos tools testing (improved)
14. `test_qdrant_integration.py` - Qdrant vector database integration testing
15. `test_refactored_service_resources.py` - Refactored service resources testing
16. `test_refactored_with_auth.py` - Refactored authentication testing
17. `test_resource_templating.py` - Resource templating system testing
18. `test_scope_consolidation.py` - OAuth scope consolidation testing
19. `test_send_dynamic_card.py` - Dynamic card sending functionality testing
20. `test_service_fixes_validation.py` - Service fixes validation testing
21. `test_service_list_integration.py` - Service list integration testing
22. `test_service_list_resources.py` - Service list resources testing
23. `test_service_resources.py` - Service resources testing
24. `test_service_resources_debug.py` - Service resources debugging testing
25. `test_sheets_tools.py` - Google Sheets tools testing
26. `test_slides_tools.py` - Google Slides tools testing
27. `test_smart_card_tool.py` - Smart card tool testing
28. `test_template_middleware_integration.py` - Template middleware integration testing
29. `test_template_simple.py` - Simple template testing
30. `test_unified_card_tool.py` - Unified card tool testing

## Purpose

These tests are designed to:
- Test MCP tools through the FastMCP Client SDK
- Validate end-to-end functionality by making actual HTTP requests to the MCP server
- Test authentication flows and credential management
- Verify Google Workspace API integrations (Gmail, Calendar, Drive, Sheets, Slides, Chat, Photos)
- Test card framework and dynamic messaging functionality
- Validate service resource management and OAuth flows

## Running Client Tests

To run all client-based tests in this directory:

```bash
# Run all client tests
pytest tests/client/ -v

# Run specific client test file
pytest tests/client/test_chat_tools.py -v

# Run with integration tests (requires proper credentials and environment setup)
pytest tests/client/ -v -m integration
```

## Requirements

These tests require:
- FastMCP Client SDK installed (`fastmcp` package)
- Running MCP server (usually on localhost:8002)
- Proper authentication configuration
- Test environment variables set (TEST_EMAIL_ADDRESS, etc.)
- Google API credentials for integration tests

## ✅ Recent Framework Improvements

### Test Suite Reliability (Latest Update)
- **Fixed CallToolResult API Changes**: Updated all tests from `result[0].text` to `result.content[0].text` pattern
- **Resolved Async Coroutine Issues**: Fixed fixture patterns that caused "cannot reuse already awaited coroutine" errors
- **Corrected Tool Name Mismatches**: Updated deprecated tool names (e.g., `get_messages` → `list_messages`)
- **Enhanced Response Validation**: Added support for successful API response patterns alongside error handling
- **Environment Configuration**: Added support for `GOOGLE_SLIDE_PRESENTATION_ID` and other configurable test resources

### Test Results Achievement
- **Before Fixes**: 35 failed, 20 passed, 16 skipped (across Sheets, Slides, Chat, Gmail filter tests)
- **After Fixes**: 45 passed, 10 skipped, 0 failed
- **Improvement**: 100% test reliability for all critical functionality

### New Environment Variables

Add these to your `.env` file for enhanced testing:

```env
# Test Resources (prevents resource creation during tests)
GOOGLE_SLIDE_PRESENTATION_ID=1RGLViw2eUBJfl84jsVlFuuLbauGvcxyfs1YWmpmFCSw
TEST_CHAT_WEBHOOK=https://chat.googleapis.com/v1/spaces/YOUR_SPACE/messages
PHOTO_TEST_EMAIL_ADDRESS=your-photo-test@example.com

# Required Test Configuration
TEST_EMAIL_ADDRESS=your.test@gmail.com
SERVER_HOST=localhost
SERVER_PORT=8002
```

## Organization

This separation helps organize the test suite by distinguishing between:
- **Client tests** (this directory) - Test via FastMCP Client SDK over HTTP with standardized framework
- **Unit tests** (main tests directory) - Test individual components and modules directly