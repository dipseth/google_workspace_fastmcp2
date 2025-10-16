# Qdrant Point Details Resource

## Overview
The `qdrant://collection/{collection_name}/{point_id}` resource provides detailed information about a specific point stored in a Qdrant collection, with automatic decompression and structured output.

## URI Pattern
```
qdrant://collection/{collection_name}/{point_id}
```

## Parameters
- `collection_name`: Name of the Qdrant collection (e.g., `mcp_tool_responses`)
- `point_id`: Unique identifier of the point (UUID format, e.g., `88fc2b49-0e61-4617-a9cb-02812375394a`)

## Response Structure (QdrantPointDetailsResponse)

```json
{
  "qdrant_enabled": true,
  "collection_name": "mcp_tool_responses",
  "point_id": "88fc2b49-0e61-4617-a9cb-02812375394a",
  "point_exists": true,
  "payload": {
    // Full raw payload from Qdrant
  },
  "vector_available": false,
  "vector_size": null,
  // Extracted common fields for easy access:
  "tool_name": "search_gmail_messages",
  "user_email": "user@example.com",
  "timestamp": "2025-01-15T10:30:00Z",
  "session_id": "abc123",
  "payload_type": "tool_response",
  "compressed": true,
  // Decompressed data:
  "response_data": {
    // Parsed JSON response from the tool
  },
  "retrieved_at": "2025-01-15T11:00:00Z"
}
```

## Usage Examples

### 1. Basic Access via MCP Client
```
Access resource: qdrant://collection/mcp_tool_responses/88fc2b49-0e61-4617-a9cb-02812375394a
```

### 2. Template Usage (Coming Soon)
Once templates are implemented, you'll be able to use this resource in Jinja2 templates:

```jinja2
{# Get point details #}
{% set point = resource('qdrant://collection/mcp_tool_responses/88fc2b49-0e61-4617-a9cb-02812375394a') %}

{# Access structured fields #}
<div class="point-details">
  <h3>{{ point.tool_name }}</h3>
  <p>User: {{ point.user_email }}</p>
  <p>Timestamp: {{ point.timestamp }}</p>
  
  {# Access decompressed response data #}
  {% if point.response_data %}
    <pre>{{ point.response_data | tojson(indent=2) }}</pre>
  {% endif %}
</div>
```

### 3. Dynamic Point ID from Search
```jinja2
{# First search for relevant points #}
{% set search_results = resource('qdrant://search/gmail messages from john') %}

{# Then get details for the first result #}
{% if search_results.results %}
  {% set point_id = search_results.results[0].id %}
  {% set details = resource('qdrant://collection/mcp_tool_responses/' + point_id) %}
  
  <div>
    <h4>{{ details.tool_name }}</h4>
    <p>{{ details.response_data }}</p>
  </div>
{% endif %}
```

### 4. Build Lists from Cache
```jinja2
{# Get cache organized by tool #}
{% set cache = resource('qdrant://cache') %}

{# Display recent points from a specific tool #}
{% if 'search_gmail_messages' in cache.cache_data %}
  <h3>Recent Gmail Searches</h3>
  <ul>
  {% for point_meta in cache.cache_data.search_gmail_messages[:5] %}
    {% set point = resource('qdrant://collection/mcp_tool_responses/' + point_meta.point_id) %}
    <li>
      <strong>{{ point.timestamp }}</strong> - {{ point.user_email }}
      <br>Response: {{ point.response_data.total_results }} messages found
    </li>
  {% endfor %}
  </ul>
{% endif %}
```

## Features

### Automatic Data Decompression
- Compressed payloads are automatically decompressed
- JSON data is automatically parsed
- Errors are handled gracefully with detailed error messages

### Structured Access
- Common metadata fields are extracted to top-level for easy access
- Raw payload is still available for advanced use cases
- Response data is presented in parsed, usable format

### Error Handling
- Returns `point_exists: false` if point not found
- Provides detailed error messages
- Validates collection existence

## Architecture

The resource follows the established Qdrant middleware pattern:

1. **Client Request** → `qdrant://collection/X/Y`
2. **Middleware Intercepts** → [`QdrantUnifiedMiddleware.on_read_resource`](../middleware/qdrant_middleware.py:295)
3. **Handler Processes** → [`QdrantResourceHandler._handle_point_details`](../middleware/qdrant_core/resource_handler.py)
4. **Returns Pydantic Model** → [`QdrantPointDetailsResponse`](../middleware/qdrant_types.py)
5. **Middleware Converts** → `model.model_dump()` for MCP
6. **Client Receives** → Structured JSON response

## Related Resources

- `qdrant://collections/list` - List all collections
- `qdrant://collection/{name}/info` - Collection metadata
- `qdrant://collection/{name}/responses/recent` - Recent points in collection
- `qdrant://search/{query}` - Semantic search to find point IDs
- `qdrant://cache` - Get all point IDs organized by tool

## Use Cases

1. **Detailed Inspection** - Examine specific tool responses in detail
2. **Search → Details Pattern** - Search for points, then get full details
3. **Cache → Details Pattern** - List cache, then fetch specific points
4. **Template Rendering** - Build rich displays of historical tool responses
5. **Debugging** - Inspect exact payloads and metadata for troubleshooting
6. **Analytics** - Access response data for analysis and reporting

## Implementation Files

- **Type Definition**: [`middleware/qdrant_types.py`](../middleware/qdrant_types.py) - `QdrantPointDetailsResponse`
- **Handler Logic**: [`middleware/qdrant_core/resource_handler.py`](../middleware/qdrant_core/resource_handler.py) - `_handle_point_details()`
- **Resource Registration**: [`middleware/qdrant_core/resources.py`](../middleware/qdrant_core/resources.py) - `get_qdrant_point_details()`
- **Middleware Hook**: [`middleware/qdrant_middleware.py`](../middleware/qdrant_middleware.py) - `on_read_resource()`