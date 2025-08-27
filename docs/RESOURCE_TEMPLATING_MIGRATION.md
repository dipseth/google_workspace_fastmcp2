# Resource Templating Migration Guide

## Overview

This guide shows how to migrate from manual `user_google_email` parameters to automatic resource templating in FastMCP2 Google Workspace Platform.

## 🎯 Benefits of Resource Templating

- **Eliminates repetitive parameters**: No more `user_google_email: str` in every tool
- **Automatic authentication**: User email comes from OAuth session context
- **Cleaner APIs**: Tools focus on their core functionality
- **Better UX**: Users don't need to remember/type their email repeatedly
- **Type safety**: Centralized email validation and error handling

## 📋 Migration Steps

### Before: Manual Email Parameters

```python
@mcp.tool()
async def old_search_drive_files(
    user_google_email: str,  # ← Manual parameter required
    query: str,
    page_size: int = 25
) -> str:
    """Search Drive files - OLD PATTERN"""
    # Manual service creation
    drive_key = request_google_service("drive", ["drive_read"])
    drive_service = get_injected_service(drive_key)
    
    # Use the manually provided email
    # ... rest of implementation
```

### After: Resource Templating

```python
@mcp.tool()
async def new_search_drive_files(
    query: str,              # ← No email parameter needed!
    page_size: int = 25
) -> str:
    """Search Drive files - NEW PATTERN"""
    # Automatic email from resource context
    user_email = get_current_user_email_simple()
    
    # Same service injection pattern
    drive_key = request_google_service("drive", ["drive_read"])
    drive_service = get_injected_service(drive_key)
    
    # Use the automatically retrieved email
    # ... rest of implementation
```

## 🔧 Step-by-Step Migration

### 1. Import the Resource Helper

```python
from resources.user_resources import get_current_user_email_simple
```

### 2. Remove Email Parameter

```python
# Before
async def my_tool(user_google_email: str, other_param: str) -> str:

# After  
async def my_tool(other_param: str) -> str:
```

### 3. Get Email from Context

```python
# Add this at the start of your tool function
try:
    user_email = get_current_user_email_simple()
except ValueError as e:
    return f"❌ Authentication error: {str(e)}"
```

### 4. Use the Email as Before

```python
# The rest of your tool logic remains exactly the same
drive_key = request_google_service("drive", ["drive_read"])
drive_service = get_injected_service(drive_key)
# ... use user_email variable as before
```

## 📚 Complete Migration Example

Here's a complete before/after example:

### Before (Manual Pattern)

```python
@mcp.tool()
async def send_gmail_message(
    user_google_email: str,  # Manual parameter
    to: str,
    subject: str,
    body: str
) -> str:
    """Send Gmail message - OLD PATTERN"""
    try:
        gmail_key = request_google_service("gmail", ["gmail_send"])
        gmail_service = get_injected_service(gmail_key)
        
        # Create message
        message = create_message(to, subject, body)
        
        # Send message
        result = gmail_service.users().messages().send(
            userId='me',
            body={'raw': message}
        ).execute()
        
        return f"✅ Message sent by {user_google_email}: {result['id']}"
        
    except Exception as e:
        return f"❌ Error sending message: {str(e)}"
```

### After (Resource Templating)

```python
@mcp.tool()
async def send_gmail_message(
    to: str,        # No email parameter needed!
    subject: str,
    body: str
) -> str:
    """Send Gmail message - NEW PATTERN"""
    try:
        # Get user email automatically from resource context
        user_email = get_current_user_email_simple()
        
        gmail_key = request_google_service("gmail", ["gmail_send"])
        gmail_service = get_injected_service(gmail_key)
        
        # Create message (same as before)
        message = create_message(to, subject, body)
        
        # Send message (same as before)
        result = gmail_service.users().messages().send(
            userId='me',
            body={'raw': message}
        ).execute()
        
        return f"✅ Message sent by {user_email}: {result['id']}"
        
    except ValueError as e:
        return f"❌ Authentication error: {str(e)}"
    except Exception as e:
        return f"❌ Error sending message: {str(e)}"
```

## 🔄 Gradual Migration Strategy

For backwards compatibility during migration, you can use this helper:

```python
from tools.enhanced_tools import get_user_email_from_context_or_param

@mcp.tool()
async def hybrid_tool(
    other_param: str,
    user_google_email: Optional[str] = None  # Optional for backwards compatibility
) -> str:
    """Tool that supports both patterns during migration"""
    try:
        # This helper tries context first, falls back to parameter
        user_email = get_user_email_from_context_or_param(user_google_email)
        
        # Rest of tool logic remains the same
        # ...
        
    except ValueError as e:
        return f"❌ Authentication error: {str(e)}"
```

## 🌟 Available Resources

The FastMCP2 platform now provides these resources:

### Basic User Resources

- `user://current/email` - Current user's email address
- `user://current/profile` - Full user profile with auth status  
- `user://profile/{email}` - Profile for specific user email
- `template://user_email` - Simple string template for email

### Authentication Resources

- `auth://session/current` - Current session information
- `auth://sessions/list` - List all active sessions
- `auth://credentials/{email}/status` - Credential status for user

### Service Resources

- `google://services/scopes/{service}` - Required scopes for Google services

## 🚀 Usage Examples

### Using Resources Directly (Advanced)

```python
from fastmcp import Context

@mcp.tool()
async def advanced_tool(ctx: Context) -> str:
    """Advanced tool using resources directly"""
    # Access resources directly through FastMCP context
    email_resource = await ctx.read_resource("user://current/email")
    profile_resource = await ctx.read_resource("user://current/profile")
    
    # Parse resource content
    user_data = email_resource.contents[0]  # Assuming text content
    
    return f"Advanced processing for user: {user_data}"
```

### Error Handling Best Practices

```python
@mcp.tool()
async def robust_tool(param: str) -> str:
    """Tool with robust error handling"""
    try:
        user_email = get_current_user_email_simple()
    except ValueError as e:
        # User not authenticated
        return (
            f"❌ Authentication required: {str(e)}\n"
            f"💡 Please run `start_google_auth` tool first to authenticate."
        )
    
    try:
        # Your tool logic here
        service_key = request_google_service("drive")
        service = get_injected_service(service_key)
        # ...
        
    except Exception as e:
        return f"❌ Tool error: {str(e)}"
```

## 🔍 Testing Your Migration

### 1. Test Authentication Flow

```bash
# Start authentication
start_google_auth("your.email@gmail.com")

# Test new tools work without email parameter
list_my_drive_files("name contains 'test'")
search_my_gmail("from:example@domain.com")
get_my_auth_status()
```

### 2. Test Resource Access

```bash
# Check resources are available
mcp.list_resources()

# Read specific resources
mcp.read_resource("user://current/email")
mcp.read_resource("user://current/profile") 
```

### 3. Verify Error Handling

```bash
# Test without authentication (should show helpful error)
list_my_drive_files("test query")
# Should return: "❌ Authentication error: No authenticated user found..."
```

## 📝 Migration Checklist

- [ ] Import `get_current_user_email_simple` helper
- [ ] Remove `user_google_email: str` parameters from tool signatures
- [ ] Add email retrieval at start of tool functions
- [ ] Add proper error handling for authentication errors
- [ ] Test tools work with authenticated sessions
- [ ] Test error messages for unauthenticated sessions
- [ ] Update tool documentation to reflect new parameters
- [ ] Consider gradual migration with backwards compatibility

## 🎉 Benefits After Migration

1. **Cleaner Tool APIs**: Focus on core functionality
2. **Better User Experience**: No repetitive email typing
3. **Automatic Authentication**: Seamless OAuth integration
4. **Error Prevention**: Centralized validation
5. **Future-Proof**: Ready for multi-user enhancements

## ⚠️ Common Pitfalls

1. **Forgetting Error Handling**: Always wrap `get_current_user_email_simple()` in try/catch
2. **Testing Without Auth**: Remember to authenticate before testing new tools
3. **Import Errors**: Make sure to import the helper function
4. **Context Clearing**: Middleware clears context between requests (this is normal)

## 🔗 Related Documentation

- [FastMCP Resources Documentation](https://fastmcp.readthedocs.io/en/latest/resources/)
- [OAuth Authentication Guide](./OAUTH_GUIDE.md)
- [Service Injection Patterns](./SERVICE_INJECTION.md)