# Service List Resources Testing Documentation

> **📋 Note**: Service list resource testing has been moved to [`tests/client/`](client/) as part of the comprehensive client testing framework. The specific tests are integrated into service-specific test files like [`test_sheets_tools.py`](client/test_sheets_tools.py), [`test_gmail_tools.py`](client/test_gmail_tools.py), etc.

## Overview

The Service List Resources feature provides a hierarchical, dynamic resource system that exposes list-based tools from various Google services through standardized MCP resources. This enables MCP clients to discover and access list data without needing to know the specific tool names or parameters.

## Resource Hierarchy

The system provides three levels of resources:

### Level 1: Service Discovery
**Pattern:** `service://{service}/lists`  
**Purpose:** Returns available list types for a service  
**Example:** `service://gmail/lists` → Returns `["filters", "labels"]`

### Level 2: List Items
**Pattern:** `service://{service}/{list_type}`  
**Purpose:** Returns all items/IDs for that list type  
**Example:** `service://photos/albums` → Returns list of album IDs

### Level 3: Item Details  
**Pattern:** `service://{service}/{list_type}/{item_id}`  
**Purpose:** Returns detailed data for a specific item  
**Example:** `service://photos/albums/abc123` → Returns photos in album abc123

## Supported Services

| Service | List Types | Detail Views | Notes |
|---------|------------|--------------|-------|
| **Gmail** | `filters`, `labels` | `filters` → `get_gmail_filter` | Labels have no detail view |
| **Forms** | `form_responses` | Via `form_id` parameter | Requires form ID to list responses |
| **Photos** | `albums` | `albums` → `list_album_photos` | Detail view shows photos in album |
| **Calendar** | `calendars`, `events` | `events` via `calendar_id` | Events require calendar ID |
| **Sheets** | `spreadsheets` | `spreadsheets` → `get_spreadsheet_info` | Shows spreadsheet details |
| **Drive** | `items` | Via `folder_id` parameter | Lists folder contents |
| **Chat** | `spaces` | `spaces` → `list_messages` | Shows messages in space |
| **Docs** | `documents` | Via `folder_id`, detail via `get_doc_content` | Lists docs in folder |

## Test Files (Now in Client Framework)

> **Moved to Client Tests**: Service list resource testing is now integrated into the comprehensive client testing framework:

### Client Test Integration
- **Service Discovery**: Tested in individual service test files (e.g., [`test_sheets_tools.py`](client/test_sheets_tools.py))
- **Resource Template Registration**: Validated in [`test_service_list_resources.py`](../delete_later/tests/test_enhanced_service_list_resources.py) (moved to delete_later)
- **Tool-Resource Mapping**: Covered by client service integration tests
- **Structured Response Validation**: Built into client test framework assertions

### Original Test Files (Archived)
- `test_service_list_resources.py` → Moved to [`delete_later/tests/`](../delete_later/tests/) (functionality covered by client tests)
- `test_service_list_integration.py` → Integrated into client service tests

## Running Tests (Updated)

Service list resource functionality is now tested through the client testing framework:

```bash
# Run all client tests (includes service list resource validation)
uv run pytest tests/client/ -v

# Test specific services with list resource functionality
uv run pytest tests/client/test_sheets_tools.py -v         # Spreadsheets list resources
uv run pytest tests/client/test_gmail_tools.py -v          # Gmail filters/labels resources
uv run pytest tests/client/test_chat_tools.py -v           # Chat spaces resources

# Run comprehensive service resource testing
uv run pytest tests/client/ -k "list" -v
```

## Test Coverage

The test suite covers:

### Functional Testing
- ✅ All 8 Google services are discoverable
- ✅ Each service returns correct list types
- ✅ Detail views are properly mapped
- ✅ Tools with `id_field` parameters work correctly
- ✅ Structured data responses are handled

### Error Handling
- ✅ Invalid service names return helpful errors
- ✅ Invalid list types return available options
- ✅ Missing authentication is handled gracefully
- ✅ Malformed URIs are rejected appropriately

### Integration Testing
- ✅ Resources correctly invoke underlying tools
- ✅ Tool responses are properly transformed
- ✅ Structured data from tools is preserved
- ✅ Authentication context is passed through

## Expected Behaviors

### Without Authentication
Resources will return error messages indicating authentication is required:
```json
{
  "error": "User email not found in context"
}
```

### With Authentication
Resources return structured data from the underlying tools:
```json
{
  "service": "photos",
  "list_type": "albums",
  "count": 5,
  "items": [
    {"id": "album1", "type": "album"},
    {"id": "album2", "type": "album"}
  ]
}
```

### For Tools with Structured Output
Tools that return TypedDict-based structured data (e.g., `list_calendars`, `list_spaces`) will have their structure preserved:
```json
{
  "service": "calendar",
  "list_type": "calendars",
  "calendars": [
    {
      "id": "primary",
      "summary": "Main Calendar",
      "description": "Primary calendar"
    }
  ],
  "count": 1
}
```

## Common Test Patterns

### Testing Service Discovery
```python
content = await client.read_resource("service://gmail/lists")
data = json.loads(content[0].text)
assert "filters" in [lt["name"] for lt in data["list_types"]]
```

### Testing List Retrieval
```python
content = await client.read_resource("service://photos/albums")
data = json.loads(content[0].text)
# Will have error without auth, or items with auth
assert "error" in data or "items" in data
```

### Testing Detail Views
```python
content = await client.read_resource("service://photos/albums/test_id")
data = json.loads(content[0].text)
assert "item_id" in data or "error" in data
```

## Troubleshooting

### Issue: Tools not discovered
**Symptom:** Resources return empty results or "tool not found" errors  
**Solution:** Ensure tools are properly registered with FastMCP before resource setup

### Issue: Structured data not returned
**Symptom:** Resources return string data instead of structured JSON  
**Solution:** Check that tools have been updated with output schemas (TypedDict return types)

### Issue: Authentication errors
**Symptom:** All resource calls fail with auth errors  
**Solution:** Ensure test client has proper authentication configuration via `get_client_auth_config()`

### Issue: _tools attribute not accessible
**Symptom:** Test output shows "Cannot access _tools attribute"  
**Solution:** The tools need to be accessed through FastMCP's public API, not internal attributes

## Implementation Notes

1. **Tool Discovery:** The system attempts multiple methods to discover tools:
   - Via `mcp.tools` property (FastMCP 2.x)
   - Via `mcp._tools` dict (fallback)
   - Direct callable checking

2. **Response Handling:** Resources handle multiple response types:
   - Structured dict/list responses (preferred)
   - String responses (parsed with regex)
   - Error responses (passed through)

3. **Context Passing:** User email is extracted from `ctx.metadata` and passed to tools

4. **Dynamic Mapping:** The `SERVICE_MAPPINGS` dict defines all service/tool relationships

## Future Enhancements

1. **Pagination Support:** Add support for paginated list results
2. **Filtering Parameters:** Pass through query parameters for filtering
3. **Caching:** Add caching layer for frequently accessed lists
4. **Batch Operations:** Support fetching multiple list types in one call
5. **WebSocket Updates:** Real-time updates for list changes