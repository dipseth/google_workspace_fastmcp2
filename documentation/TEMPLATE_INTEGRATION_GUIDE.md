# Template Parameter Middleware Integration Guide

## Quick Integration into Existing FastMCP2 Server

This guide shows how to add the Template Parameter Middleware to your existing FastMCP2 Google Workspace Platf## 🔧 Creating Your Own Template-Enabled Tools

### Basic Template Tool

```python
@mcp.tool()
async def my_template_tool(
    recipient: str,
    sender: str = "{{template://user_email}}",           # Simple template
    file_count: int = "{{workspace://content/recent}}['content_summary']['total_files']",  # JSON path
    domain: str = "{{user://current/profile}}['email'].split('@')[1]"  # Complex extraction
) -> str:
    """My tool with automatic template resolution."""
    
    # All template parameters are automatically resolved before execution
    return f"Email from {sender}@{domain} to {recipient} about {file_count} files"
```

### Gmail Service Integration (Real Data)

```python
@mcp.tool()
async def smart_gmail_assistant(
    recipient: str,
    
    # User context (automatically resolved)
    user_email: str = "{{template://user_email}}",
    
    # Real Gmail data from our validated tests
    inbox_label: str = "{{service://gmail/labels}}[\"system_labels\"][2][\"id\"]",  # INBOX
    sent_label: str = "{{service://gmail/labels}}[\"system_labels\"][1][\"id\"]",   # SENT
    work_label: str = "{{service://gmail/labels}}[\"user_labels\"][0][\"id\"]",    # First user label (e.g., CHAT)
    total_labels: int = "{{service://gmail/labels}}[\"count\"]",
    filter_count: int = "{{service://gmail/filters}}[\"count\"]"
) -> str:
    """Gmail assistant with real label data from client tests."""
    
    # Template resolution gives us real data:
    # user_email: "srivers@groupon.com" 
    # inbox_label: "INBOX"
    # sent_label: "SENT"
    # work_label: "CHAT" (or other real user label)
    # total_labels: 33 (from our test results)
    # filter_count: 3
    
    return f"""
    Gmail Assistant for {user_email}:
    
    � Labels Available: {total_labels}
    📂 Inbox: {inbox_label}
    📤 Sent: {sent_label} 
    🏷️ Work: {work_label}
    🔧 Filters: {filter_count}
    
    Ready to help with email management!
    """

@mcp.tool() 
async def create_gmail_filter(
    description: str,
    
    # Auto-resolved user context
    user_email: str = "{{template://user_email}}",
    
    # Real label IDs from service (validated in our tests)
    target_label: str = "{{service://gmail/labels}}[\"user_labels\"][0][\"id\"]",  # First user label
    inbox_label: str = "{{service://gmail/labels}}[\"system_labels\"][2][\"id\"]",  # INBOX
    
    # Filter configuration
    existing_filters: str = "{{service://gmail/filters}}"
) -> str:
    """Create Gmail filter with real label IDs."""
    
    import json
    filters = json.loads(existing_filters) if isinstance(existing_filters, str) else existing_filters
    
    return f"""
    Creating Gmail filter for {user_email}:
    
    Description: {description}
    Target Label: {target_label}
    Source: {inbox_label}
    Existing Filters: {len(filters.get('filters', []))}
    
    Filter would move messages matching criteria to {target_label} label.
    """
```🚀 Quick Setup (3 Steps)

### Step 1: Import the Middleware

Add to your `server.py`:

```python
# Add these imports at the top
from middleware.template_middleware import setup_template_middleware
from tools.enhanced_template_tools import setup_enhanced_template_tools
```

### Step 2: Add Middleware After Resources

In your server setup, after setting up resources but before running:

```python
# Your existing server setup
mcp = FastMCP("FastMCP2 Google Workspace Platform")

# Your existing resource setup
setup_user_resources(mcp)
# ... other resource setups

# Your existing auth middleware
mcp.add_middleware(AuthMiddleware())

# ADD THIS: Template parameter middleware
template_middleware = setup_template_middleware(
    mcp,
    enable_debug=False,      # Set to True for development
    enable_caching=True,     # Enable for performance
    cache_ttl_seconds=300    # 5 minutes cache
)

# ADD THIS: Enhanced tools with template support
setup_enhanced_template_tools(mcp)

# Your existing tools setup continues...
```

### Step 3: Test the Integration

Start your server and test:

```bash
# Start server
uv run server.py

# In MCP inspector or client, try:
test_template_resolution()
send_smart_email(recipient="test@example.com")
```

## 📋 Complete Integration Example

Here's how to modify your existing `server.py`:

```python
#!/usr/bin/env python3
"""
FastMCP2 Google Workspace Platform with Template Parameter Support
"""

import logging
from fastmcp import FastMCP

# Your existing imports
from auth.middleware import AuthMiddleware, CredentialStorageMode
from resources.user_resources import setup_user_resources
# ... other existing imports

# ADD THESE NEW IMPORTS
from middleware.template_middleware import setup_template_middleware
from tools.enhanced_template_tools import setup_enhanced_template_tools

logger = logging.getLogger(__name__)

def main():
    # Your existing server setup
    mcp = FastMCP("FastMCP2 Google Workspace Platform")
    
    # Your existing resources
    setup_user_resources(mcp)
    # ... other resource setups
    
    # Your existing middleware (keep this!)
    auth_middleware = AuthMiddleware(
        storage_mode=CredentialStorageMode.FILE_ENCRYPTED
    )
    mcp.add_middleware(auth_middleware)
    
    # ADD THIS: Template parameter middleware
    template_middleware = setup_template_middleware(
        mcp,
        enable_debug=True,       # Enable for testing
        enable_caching=True,     # Cache resources
        cache_ttl_seconds=300    # 5 minute cache
    )
    
    # Your existing tools (keep these!)
    setup_drive_tools(mcp)
    setup_gmail_tools(mcp)
    # ... other tool setups
    
    # ADD THIS: Enhanced template tools
    setup_enhanced_template_tools(mcp)
    
    # Your existing server run
    mcp.run()

if __name__ == "__main__":
    main()
```

## 🔧 Configuration Options

### Template Middleware Settings

```python
template_middleware = setup_template_middleware(
    mcp,
    enable_debug=False,           # Debug logging on/off
    enable_caching=True,          # Resource caching
    cache_ttl_seconds=300,        # Cache timeout (seconds)
)

# Or create manually for advanced config:
from middleware.template_middleware import TemplateParameterMiddleware

middleware = TemplateParameterMiddleware(
    template_pattern=r'\{\{([^}]+)\}\}',  # Template syntax
    enable_caching=True,                   # Cache resources
    cache_ttl_seconds=300,                 # 5 minutes
    enable_debug_logging=True,             # Debug mode
    allowed_resource_schemes=[             # Security control
        "user", "auth", "template", 
        "workspace", "gmail", "tools", "google"
    ],
    max_recursion_depth=3                  # Nested template limit
)
mcp.add_middleware(middleware)
```

### Production vs Development

**Development Settings:**
```python
template_middleware = setup_template_middleware(
    mcp,
    enable_debug=True,        # See template resolution
    enable_caching=False,     # Disable cache for testing
    cache_ttl_seconds=60      # Short cache for rapid changes
)
```

**Production Settings:**
```python
template_middleware = setup_template_middleware(
    mcp,
    enable_debug=False,       # No debug logging
    enable_caching=True,      # Cache for performance
    cache_ttl_seconds=600     # 10 minute cache
)
```

## 🎯 Testing Your Integration

### 1. Basic Template Resolution Test

```python
# Call this tool after server starts
test_template_resolution()
```

Expected output shows resolved templates:
```
Simple resource: {{template://user_email}}
→ Resolved to: "user@example.com"

JSON path extraction: {{user://current/profile}}['email'] 
→ Resolved to: "user@example.com"
```

### 2. Gmail Integration Test with Real Data

```python
# Test with real Gmail service resources
result = await client.call_tool("list_gmail_labels", {
    "user_google_email": "test@example.com"
})

# Extract real label IDs from server response
label_ids = extract_gmail_labels(result)  # ['CHAT', 'SENT', 'INBOX', ...]
```

Expected results from our validated test:
```
✅ Found 33 real Gmail label IDs: ['CHAT', 'SENT', 'INBOX', 'IMPORTANT', 'TRASH', 'DRAFT', 'SPAM'...]
🎉 SUCCESS: Template expressions {{service://gmail/labels}} work with real data!
```

### 3. Client SDK Integration Test

```python
# Full client test against running server (from our validated test)
import pytest
from fastmcp import Client

@pytest.mark.asyncio
async def test_template_middleware_integration():
    """Test template middleware with real server data."""
    
    # Connect to running server
    auth_config = get_client_auth_config("test@example.com")
    client = Client("http://localhost:8002/mcp/", auth=auth_config)
    
    async with client:
        # Test real Gmail tools
        gmail_result = await client.call_tool("list_gmail_labels", {
            "user_google_email": "test@example.com"
        })
        
        # Validate real data extraction
        label_ids = extract_real_gmail_labels(gmail_result)
        assert len(label_ids) >= 10, f"Expected many labels, got {len(label_ids)}"
        assert "INBOX" in label_ids, "Should have INBOX label"
        
        print(f"✅ Found {len(label_ids)} real label IDs: {label_ids[:3]}...")
        print(f"🎉 SUCCESS: Got real Gmail label IDs from server!")

# Run with: uv run pytest tests/test_template_middleware_integration.py -v
```

## 🛠️ Creating Your Own Template-Enabled Tools

### Basic Template Tool

```python
@mcp.tool()
async def my_template_tool(
    recipient: str,
    sender: str = "{{template://user_email}}",           # Simple template
    file_count: int = "{{workspace://content/recent}}['content_summary']['total_files']",  # JSON path
    domain: str = "{{user://current/profile}}['email'].split('@')[1]"  # Complex extraction
) -> str:
    """My tool with automatic template resolution."""
    
    # All template parameters are automatically resolved before execution
    return f"Email from {sender}@{domain} to {recipient} about {file_count} files"
```

### Advanced Template Tool

```python
@mcp.tool()
async def advanced_template_tool(
    # User context templates
    user_info: str = "{{user://current/profile}}",
    session_id: str = "{{auth://session/current}}['session_id']",
    
    # Content templates
    recent_docs: str = "{{workspace://content/recent}}['content_by_type']['documents']",
    suggestions: str = "{{gmail://content/suggestions}}['email_templates']",
    
    # Nested extraction
    first_doc_name: str = "{{workspace://content/recent}}['content_by_type']['documents'][0]['name']",
    user_domain: str = "{{gmail://content/suggestions}}['dynamic_variables']['user_domain']"
) -> str:
    """Advanced tool with complex template resolution."""
    
    import json
    
    # Parse resolved JSON data
    user_data = json.loads(user_info) if isinstance(user_info, str) else user_info
    docs_data = json.loads(recent_docs) if isinstance(recent_docs, str) else recent_docs
    
    # Use resolved data
    email = user_data.get('email', 'unknown')
    doc_count = len(docs_data) if docs_data else 0
    
    return f"""
Advanced Analysis:
- User: {email} ({user_domain})
- Session: {session_id}
- Documents: {doc_count}
- Latest: {first_doc_name}
"""
```

## 🔍 Troubleshooting

### Common Issues

**1. Templates not resolving:**
```
# Check middleware order - template middleware should be AFTER auth middleware
mcp.add_middleware(AuthMiddleware())          # First - sets up context
mcp.add_middleware(TemplateParameterMiddleware())  # Second - uses context
```

**2. Resource not found errors:**
```
# Ensure resources are set up before middleware
setup_user_resources(mcp)                    # First - create resources
mcp.add_middleware(TemplateParameterMiddleware())  # Second - can access resources
```

**3. JSON path errors:**
```
# Check JSON path syntax - use Python subscript notation
"{{resource://uri}}['key']"           # ✅ Correct
"{{resource://uri}}.key"              # ❌ Wrong syntax
"{{resource://uri}}[key]"             # ❌ Missing quotes
```

**4. Gmail service resource issues (from our testing):**
```
# Correct format for Gmail label extraction (validated in our tests)
"{{service://gmail/labels}}[\"system_labels\"][2][\"id\"]"  # Gets "INBOX"
"{{service://gmail/labels}}[\"user_labels\"][0][\"id\"]"    # Gets first user label like "CHAT"
"{{service://gmail/labels}}[\"count\"]"                    # Gets total count like 33

# Wrong formats that won't work:
"{{service://gmail/labels}}.system_labels[2].id"        # ❌ Wrong syntax
"{{gmail://labels}}['system_labels'][2]['id']"          # ❌ Wrong resource URI
```

### Client Testing Debug

```python
# Test client connection to server
import pytest
from fastmcp import Client

@pytest.mark.asyncio
async def test_client_connection():
    """Debug client connection issues."""
    
    # Check server is running on correct port
    auth_config = get_client_auth_config("test@example.com")
    client = Client("http://localhost:8002/mcp/", auth=auth_config)
    
    try:
        async with client:
            # Test basic server info
            info = await client.get_server_info()
            print(f"✅ Connected to server: {info['name']}")
            
            # Test tools availability
            tools = await client.list_tools()
            print(f"✅ Found {len(tools)} tools")
            
            # Test resources availability  
            resources = await client.list_resources()
            print(f"✅ Found {len(resources)} resources")
            
            # Test specific Gmail tools
            result = await client.call_tool("list_gmail_labels", {
                "user_google_email": "test@example.com"
            })
            print(f"✅ Gmail tool working: {type(result)}")
            
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        # Check if server is running: uv run server.py
        # Check port matches client URL
        # Check authentication config
```

### Debug Mode

Enable debug logging to see template resolution:

```python
# Enable debug mode
template_middleware.enable_debug_mode(True)

# Check cache stats
stats = template_middleware.get_cache_stats()
print(f"Cache entries: {stats['entries']}")
```

### Log Output

With debug enabled, you'll see:
```
🎭 Processing tool call: send_smart_email
🎭 Resolving template expression: template://user_email
🎭 Fetching resource: template://user_email
🎭 Successfully fetched resource: template://user_email
🎭 Resolved parameter 'sender' in send_smart_email: '{{template://user_email}}' → 'user@example.com'
```

## 📈 Performance Monitoring

### Cache Statistics

```python
# Get cache performance
stats = template_middleware.get_cache_stats()
print(f"""
Cache Performance:
- Enabled: {stats['enabled']}
- Entries: {stats['entries']}
- TTL: {stats['ttl_seconds']}s
- Resources: {stats['cached_resources']}
""")
```

### Clear Cache

```python
# Clear cache if needed
template_middleware.clear_cache()
```

## 🎉 Benefits After Integration

### For Users
- No more typing email addresses repeatedly
- Automatic context awareness in tools  
- Personalized content generation
- Dynamic data population

### For Developers
- Cleaner tool APIs (fewer parameters)
- Automatic data injection
- Consistent user context handling
- Powerful templating system

### For Performance
- Resource caching reduces API calls
- Intelligent template resolution
- Backwards compatibility with existing tools

## 🔗 Next Steps

1. **Integrate**: Add the middleware to your server
2. **Test**: Verify template resolution works
3. **Enhance**: Convert existing tools to use templates
4. **Monitor**: Watch cache performance and debug logs
5. **Optimize**: Tune cache settings for your usage patterns

The Template Parameter Middleware makes your FastMCP2 platform more intelligent and user-friendly! 🚀