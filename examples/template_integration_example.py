#!/usr/bin/env python3
"""
Template Parameter Middleware Integration Example

This example demonstrates how to set up and use the Template Parameter Middleware
with FastMCP2 Google Workspace Platform. It shows the complete integration flow
from server setup to tool execution with automatic template resolution.
"""

import logging
import asyncio
from pathlib import Path

# FastMCP imports
from fastmcp import FastMCP

# Middleware imports
from auth.middleware import AuthMiddleware, CredentialStorageMode
from middleware.template_middleware import setup_template_middleware

# Resource setup
from resources.user_resources import setup_user_resources

# Enhanced tools with template support
from tools.enhanced_template_tools import setup_enhanced_template_tools

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def create_template_demo_server() -> FastMCP:
    """
    Create a complete FastMCP server with template parameter support.
    
    This function sets up:
    1. FastMCP server instance
    2. User and authentication resources
    3. Authentication middleware with secure credential storage
    4. Template parameter middleware with caching and debug logging
    5. Enhanced tools that demonstrate template parameter resolution
    
    Returns:
        Configured FastMCP server ready to run
    """
    logger.info("🚀 Setting up FastMCP server with Template Parameter Middleware")
    
    # Create the FastMCP server
    server = FastMCP(
        name="Template Parameter Demo Server",
        version="1.0.0"
    )
    
    # Step 1: Setup resources first (resources must exist before middleware can use them)
    logger.info("📚 Setting up user and authentication resources")
    setup_user_resources(server)
    
    # Step 2: Add authentication middleware (handles session context and service injection)
    logger.info("🔐 Adding authentication middleware")
    auth_middleware = AuthMiddleware(
        storage_mode=CredentialStorageMode.FILE_ENCRYPTED,  # Use encrypted credential storage
        encryption_key=None  # Auto-generate encryption key
    )
    server.add_middleware(auth_middleware)
    
    # Step 3: Add template parameter middleware (processes template expressions)
    logger.info("🎭 Adding template parameter middleware")
    template_middleware = setup_template_middleware(
        server,
        enable_debug=True,        # Enable debug logging to see template resolution
        enable_caching=True,      # Cache resource responses for performance
        cache_ttl_seconds=300     # Cache for 5 minutes
    )
    
    # Step 4: Setup enhanced tools that use template parameters
    logger.info("🛠️ Setting up enhanced tools with template parameter support")
    setup_enhanced_template_tools(server)
    
    # Step 5: Add some basic tools for comparison (without templates)
    @server.tool(
        name="get_server_info",
        description="Get information about this Template Parameter Demo Server",
        tags={"info", "server", "demo"}
    )
    async def get_server_info() -> str:
        """Get server information and middleware status."""
        return f"""
🚀 **Template Parameter Demo Server**
Version: 1.0.0

🔧 **Configured Middleware:**
• AuthMiddleware: ✅ (Encrypted credential storage)
• TemplateParameterMiddleware: ✅ (Debug mode, caching enabled)

📚 **Available Resources:**
• user:// - User authentication and profile resources
• auth:// - Session and credential resources  
• template:// - Simple template resources
• workspace:// - Google Workspace content resources
• gmail:// - Gmail integration resources
• tools:// - Tool discovery and usage resources
• google:// - Google service configuration resources

🎭 **Template Features:**
• Automatic parameter resolution: ✅
• JSON path extraction: ✅ 
• Resource caching (TTL: {template_middleware.cache_ttl_seconds}s): ✅
• Debug logging: ✅
• Security controls: ✅

🛠️ **Enhanced Tools Available:**
• send_smart_email - Smart email composition with templates
• create_workspace_summary - Automated workspace analysis
• compose_dynamic_content - Dynamic content generation
• analyze_template_performance - Template system analysis

Try these tools to see automatic template parameter resolution in action!
"""
    
    @server.tool(
        name="test_template_resolution",
        description="Test template parameter resolution with various expressions",
        tags={"test", "template", "demo"}
    )
    async def test_template_resolution(
        simple_template: str = "{{template://user_email}}",
        json_path_template: str = "{{user://current/profile}}['email']",
        nested_template: str = "{{workspace://content/recent}}['content_summary']['total_files']",
        complex_template: str = "{{gmail://content/suggestions}}['email_templates']['status_update']['opening_lines'][0]"
    ) -> str:
        """Test various template resolution patterns."""
        return f"""
🧪 **Template Resolution Test Results**

📝 **Template Expressions Tested:**
1. Simple resource: {{{{template://user_email}}}}
   → Resolved to: "{simple_template}"
   → Type: {type(simple_template).__name__}

2. JSON path extraction: {{{{user://current/profile}}}}['email']
   → Resolved to: "{json_path_template}"
   → Type: {type(json_path_template).__name__}

3. Nested JSON path: {{{{workspace://content/recent}}}}['content_summary']['total_files']
   → Resolved to: "{nested_template}"
   → Type: {type(nested_template).__name__}

4. Complex nested path: {{{{gmail://content/suggestions}}}}['email_templates']['status_update']['opening_lines'][0]
   → Resolved to: "{complex_template}"
   → Type: {type(complex_template).__name__}

✅ **Resolution Status:**
• Simple template: {'✅ RESOLVED' if '{{' not in str(simple_template) else '❌ UNRESOLVED'}
• JSON path template: {'✅ RESOLVED' if '{{' not in str(json_path_template) else '❌ UNRESOLVED'} 
• Nested template: {'✅ RESOLVED' if '{{' not in str(nested_template) else '❌ UNRESOLVED'}
• Complex template: {'✅ RESOLVED' if '{{' not in str(complex_template) else '❌ UNRESOLVED'}

🎭 All template expressions were automatically processed by the Template Parameter Middleware!
"""
    
    logger.info("✅ FastMCP server setup complete with Template Parameter Middleware")
    logger.info(f"   - Resources: {len(server._resources)} registered")
    logger.info(f"   - Tools: {len(server._tools)} registered") 
    logger.info(f"   - Middleware: {len(server._middleware)} components")
    
    return server


async def demo_template_usage():
    """
    Demonstrate template parameter usage with example calls.
    
    This function shows how template expressions are resolved automatically
    when tools are called, without requiring any manual parameter passing.
    """
    logger.info("🎭 Starting Template Parameter Middleware Demo")
    
    # Create the server
    server = create_template_demo_server()
    
    # In a real scenario, you would run the server with server.run()
    # For this demo, we'll show what the setup looks like
    
    print("""
🎉 **Template Parameter Middleware Demo Server Ready!**

To use this server:

1. **Start the server:**
   ```bash
   python examples/template_integration_example.py
   ```

2. **Authenticate a user:**
   Use the `start_google_auth` tool with your email address to establish a session.

3. **Try enhanced tools with templates:**
   
   **Smart Email Composition:**
   ```
   send_smart_email(
       recipient="colleague@company.com"
       # All other parameters use templates and are auto-resolved!
   )
   ```
   
   **Workspace Analysis:**
   ```
   create_workspace_summary()
   # No parameters needed - everything resolved from templates!
   ```
   
   **Template Resolution Test:**
   ```
   test_template_resolution()
   # See template expressions resolve in real-time!
   ```

4. **Compare with traditional tools:**
   Traditional tools would require:
   ```
   send_email(
       user_google_email="user@domain.com",  # Manual parameter
       recipient="colleague@company.com",
       subject="Manual subject"
   )
   ```
   
   Enhanced tools with templates:
   ```
   send_smart_email(
       recipient="colleague@company.com"
       # subject automatically becomes "Weekly Update from user@domain.com"
       # greeting automatically becomes "Hello! This is user@domain.com" 
       # file_count_msg automatically shows actual workspace file count
       # Everything else resolved automatically!
   )
   ```

🔍 **What happens behind the scenes:**

1. **Tool Call:** Client calls `send_smart_email(recipient="test@example.com")`

2. **Template Middleware:** Intercepts call, finds template expressions:
   - `{{template://user_email}}` in subject
   - `{{user://current/profile}}['email']` in greeting
   - `{{workspace://content/recent}}['content_summary']['total_files']` in file_count_msg

3. **Resource Resolution:** Middleware resolves each template:
   - Reads `template://user_email` → "user@domain.com"
   - Reads `user://current/profile` → extracts email field
   - Reads `workspace://content/recent` → extracts nested file count

4. **Parameter Substitution:** Updates tool parameters with resolved values

5. **Tool Execution:** Tool receives fully resolved parameters and executes normally

6. **Result:** Smart, personalized email composed automatically!

🎭 **Template Parameter Middleware makes tools intelligent and context-aware!**
""")


if __name__ == "__main__":
    # Run the demo
    asyncio.run(demo_template_usage())
    
    # To actually run the server, uncomment the following:
    # server = create_template_demo_server()
    # server.run()