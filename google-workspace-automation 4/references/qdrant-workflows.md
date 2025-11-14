# Qdrant Workflows

## Overview

The RiversUnlimited MCP stores all tool responses in a Qdrant vector database with semantic search capabilities. This enables natural language queries, analytics, and intelligent context retrieval.

## Semantic Search Patterns

### Basic Search

Search across all stored tool responses using natural language:

```python
riversunlimited:search(
    query="emails about project deadlines",
    limit=10,
    user_google_email="me"
)
```

### Service-Specific Search

Filter by specific Google services:

```python
# Gmail-related searches
riversunlimited:search(query="gmail messages from managers")

# Drive-related searches
riversunlimited:search(query="drive spreadsheets about budget")

# Calendar-related searches
riversunlimited:search(query="calendar meetings next week")
```

### Advanced Filtering

Use special syntax for precise searches:

```python
# By point ID (exact lookup)
riversunlimited:search(query="id:abc123-def456-ghi789")

# By user email
riversunlimited:search(query="user_email:manager@company.com")

# Combined filters with semantic search
riversunlimited:search(query="user_email:manager@company.com project updates")
```

## Tool History Search

### Basic Tool History Query

Search through historical tool responses with filters:

```python
riversunlimited:search_tool_history(
    query="calendar events",
    limit=10,
    tool_name="list_events",  # Optional: filter by tool
    user_email="user@company.com"  # Optional: filter by user
)
```

### ID-Based Lookup

Retrieve specific tool responses by ID:

```python
riversunlimited:search_tool_history(query="id:point-id-here")
```

### Pattern Matching

Find responses matching patterns:

```python
# Temporal searches
riversunlimited:search_tool_history(query="emails sent today")

# Content searches
riversunlimited:search_tool_history(query="spreadsheets with financial data")

# Action searches
riversunlimited:search_tool_history(query="created presentations")
```

## Fetch Tool Responses

### Direct Retrieval

Fetch complete document content by point ID:

```python
riversunlimited:fetch(
    point_id="abc123-def456-ghi789",
    user_google_email="me"
)
```

Returns structured data with:
- Full tool response content
- Metadata (tool name, timestamp, user, session)
- Service context
- Formatted output

### Use Case: Following Up

1. Search for relevant context
2. Extract point IDs from results
3. Fetch full details as needed

```python
# Step 1: Search
results = riversunlimited:search(query="recent Gmail filters")

# Step 2: Get point IDs from results
point_id = results["results"][0]["id"]

# Step 3: Fetch full details
full_data = riversunlimited:fetch(point_id=point_id)
```

## Analytics and Monitoring

### Tool Usage Analytics

Get comprehensive usage statistics:

```python
riversunlimited:get_tool_analytics(
    summary_only=true,  # Quick overview
    start_date="2025-10-01",  # Optional date filter
    end_date="2025-10-31",  # Optional date filter
    group_by="tool_name"  # Group by tool, user, or session
)
```

Returns:
- Total response count
- Tool usage distribution
- Error rates
- Compression statistics
- Recent activity patterns
- Sample point IDs for exploration

### Detailed Analytics

Set `summary_only=false` for comprehensive data:

```python
riversunlimited:get_tool_analytics(
    summary_only=false,
    group_by="tool_name"
)
```

Includes:
- All point IDs per tool
- Timestamps for each operation
- User activity patterns
- Session tracking
- Response sizes
- Error analysis

### Response Details (Legacy)

Get specific response metadata:

```python
riversunlimited:get_response_details(
    point_id="abc123",
    user_google_email="me"
)
```

**Note:** Prefer `riversunlimited:fetch` for better formatting and structured output.

## Data Management

### Automatic Cleanup

Qdrant automatically removes old data based on retention policy (default: 14 days).

Configured via: `MCP_TOOL_RESPONSES_COLLECTION_CACHE_DAYS` environment variable

### Manual Cleanup

Trigger cleanup manually:

```python
riversunlimited:cleanup_qdrant_data(user_google_email="me")
```

This removes all tool responses older than the configured retention period.

### Monitoring Collection Health

Check analytics to monitor:
- Total responses stored
- Storage growth rate
- Error patterns
- Compression efficiency

## Advanced Patterns

### Cross-Service Context Building

1. Search for related activities across services:

```python
# Find all project-related activity
search(query="project Alpha across all services")
```

2. Fetch details for each result
3. Build comprehensive context
4. Use for decision-making or reporting

### Trend Analysis

Query analytics over time periods:

```python
# Last 7 days
get_tool_analytics(start_date="2025-10-12", end_date="2025-10-19")

# Last 30 days
get_tool_analytics(start_date="2025-09-19", end_date="2025-10-19")

# Compare periods
```

### Audit Trail

Use Qdrant as an audit system:

1. All tool operations are automatically logged
2. Search by user, tool, or timeframe
3. Fetch complete operation details
4. Build compliance reports

```python
# Find all operations by specific user
search_tool_history(query="user_email:audited@company.com")

# Find specific action types
search_tool_history(query="email sent")
search_tool_history(query="file deleted")
```

## Performance Optimization

### Search Optimization

- Use specific queries (better than broad queries)
- Leverage filters (user_email, tool_name) when possible
- Set appropriate limits (default: 10, max: 100)
- Use score thresholds to filter irrelevant results

### Fetch Optimization

- Batch related fetches together in workflow
- Cache fetched data in session context
- Only fetch when full details needed (search provides summaries)

### Analytics Optimization

- Use `summary_only=true` for quick checks
- Set date ranges to limit data scanned
- Group by relevant dimension (tool, user, session)

## Collection Information

**Collection Name:** `mcp_tool_responses`

**Indexed Data:**
- Tool name and arguments
- Full tool responses
- User email and session ID
- Timestamps (ISO format)
- Service metadata
- Compression information

**Vector Embeddings:**
- Automatically generated for semantic search
- Based on tool name, arguments, and response content
- Optimized for natural language queries

**Retention Policy:**
- Default: 14 days
- Configurable via environment variable
- Automatic cleanup on server schedule
- Manual cleanup available via tool
