"""
Migration Script: Upgrade Template Middleware to Jinja2

This script demonstrates how to migrate from the basic template middleware
to the enhanced Jinja2 template middleware.
"""

from pathlib import Path
import shutil
import logging

logger = logging.getLogger(__name__)


def migrate_to_jinja2_middleware():
    """
    Migrate existing FastMCP2 project to use Jinja2 template middleware.
    
    This function:
    1. Creates template directory structure
    2. Updates server.py to use Jinja2 middleware
    3. Provides example template files
    4. Shows before/after comparison
    """
    
    print("🚀 Starting migration to Jinja2 Template Middleware...")
    
    # Step 1: Create template directory structure
    create_template_directories()
    
    # Step 2: Create example template files
    create_example_templates()
    
    # Step 3: Update requirements.txt
    update_requirements()
    
    # Step 4: Show server.py integration example
    show_server_integration()
    
    print("✅ Migration complete! See the examples above for integration steps.")


def create_template_directories():
    """Create the recommended template directory structure."""
    
    directories = [
        "templates",
        "templates/prompts",
        "templates/tools", 
        "templates/gmail",
        "templates/gchat",
        "templates/gsheets",
        "templates/base"
    ]
    
    for directory in directories:
        path = Path(directory)
        path.mkdir(parents=True, exist_ok=True)
        print(f"📁 Created directory: {directory}")


def create_example_templates():
    """Create example Jinja2 template files."""
    
    # Base template for inheritance
    base_template = """<!DOCTYPE html>
<html>
<head>
    <title>{% block title %}FastMCP2 Template{% endblock %}</title>
    <style>
        /* NO MORE F-STRING CSS ERRORS! */
        .fastmcp-container {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            border-radius: 10px;
        }
        
        .resource-info {
            background: rgba(255,255,255,0.1);
            padding: 15px;
            border-radius: 8px;
            margin: 10px 0;
        }
    </style>
</head>
<body>
    <div class="fastmcp-container">
        {% block content %}{% endblock %}
    </div>
</body>
</html>"""
    
    # Gmail template example
    gmail_template = """{% extends "base/layout.html" %}

{% block title %}Gmail Quick Demo - {{ user_email }}{% endblock %}

{% block content %}
<h1>⚡ Gmail Quick Demo</h1>
<p><em>Generated: {{ utc_now().strftime("%Y-%m-%d %H:%M:%S UTC") }}</em></p>

<div class="resource-info">
    <h3>📊 Gmail Resource Integration</h3>
    
    {% if resources.user_current_email %}
        <p><strong>Your Email:</strong> {{ resources.user_current_email }}</p>
    {% else %}
        <p><strong>Status:</strong> ❌ Authentication required</p>
    {% endif %}
    
    {% if resources.service_gmail_labels %}
        <h4>Your Labels:</h4>
        <ul>
        {% for label in resources.service_gmail_labels.user_labels[:5] %}
            <li><code>{{ label.name }}</code> ({{ label.id }})</li>
        {% endfor %}
        </ul>
        
        <p><strong>System Labels:</strong> {{ resources.service_gmail_labels.system_labels | length }}</p>
        <p><strong>Custom Labels:</strong> {{ resources.service_gmail_labels.user_labels | length }}</p>
    {% else %}
        <p><em>Gmail labels not available - check authentication</em></p>
    {% endif %}
</div>

<h3>📧 Ready to Send Email</h3>
<pre><code>&lt;mcp_tool_call&gt;
  &lt;tool&gt;send_gmail_message&lt;/tool&gt;
  &lt;params&gt;
    &lt;user_google_email&gt;{{ resources.user_current_email or 'sethrivers@gmail.com' }}&lt;/user_google_email&gt;
    &lt;to&gt;demo@example.com&lt;/to&gt;
    &lt;subject&gt;FastMCP2 Jinja2 Demo - {{ utc_now().strftime("%Y-%m-%d") }}&lt;/subject&gt;
    &lt;body&gt;&lt;![CDATA[
Hello!

This email was generated using Jinja2 templating with live Gmail data:

{% if resources.service_gmail_labels %}
🏷️ Your Labels:
{% for label in resources.service_gmail_labels.user_labels[:3] %}
• {{ label.name }}
{% endfor %}
{% endif %}

🚀 Powered by FastMCP2 + Jinja2
Generated at: {{ utc_now().isoformat() }}
    ]]&gt;&lt;/body&gt;
  &lt;/params&gt;
&lt;/mcp_tool_call&gt;</code></pre>

{% if not resources.user_current_email %}
<div style="background: rgba(255,0,0,0.1); padding: 10px; border-radius: 5px; margin-top: 20px;">
    <p><strong>⚠️ Authentication Required</strong></p>
    <p>Run: <code>start_google_auth('your.email@gmail.com')</code></p>
</div>
{% endif %}
{% endblock %}"""
    
    # Simple parameter template
    simple_template = """# Quick Email: {{ tool_name }}

**User:** {{ resources.user_current_email or 'Not authenticated' }}
**Time:** {{ utc_now().strftime("%Y-%m-%d %H:%M:%S UTC") }}

{% if resources.service_gmail_labels %}
**Available Labels:** {{ resources.service_gmail_labels.user_labels | length }} custom labels
{% endif %}

This is a simple template that resolves {{resource://user/current/email}} automatically."""
    
    # Write template files
    templates = {
        "templates/base/layout.html": base_template,
        "templates/gmail/quick_demo.html": gmail_template,
        "templates/prompts/simple_email.txt": simple_template
    }
    
    for filepath, content in templates.items():
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        print(f"📄 Created template: {filepath}")


def update_requirements():
    """Show how to update requirements.txt for Jinja2."""
    
    requirements_addition = """
# Add this to your requirements.txt:
jinja2>=3.1.0
"""
    
    print(f"📋 Requirements.txt update needed:")
    print(requirements_addition)


def show_server_integration():
    """Show how to integrate Jinja2 middleware in server.py"""
    
    integration_example = '''
# In your server.py file:

from middleware.jinja2_template_middleware import setup_jinja2_template_middleware

# Replace your current template middleware setup with:
def setup_template_middleware(mcp: FastMCP):
    """Setup Jinja2 template middleware instead of basic template middleware."""
    
    template_dirs = [
        "templates",
        "templates/prompts",
        "templates/gmail",
        "templates/gchat", 
        "templates/gsheets"
    ]
    
    middleware = setup_jinja2_template_middleware(
        mcp=mcp,
        template_dirs=template_dirs,
        enable_debug=True,  # Enable for development
        enable_caching=True,
        cache_ttl_seconds=300,
        sandbox_mode=True  # Security best practice
    )
    
    # Add custom filters if needed
    middleware.add_custom_filter('my_filter', lambda x: x.upper())
    
    return middleware

# In your main setup:
async def main():
    mcp = FastMCP(name="fastmcp2-with-jinja2")
    
    # Set up Jinja2 middleware (replaces old template middleware)
    setup_template_middleware(mcp)
    
    # ... rest of your setup
    
    # Your prompts can now use Jinja2 templates!
'''
    
    print("🔧 Server.py Integration Example:")
    print(integration_example)


if __name__ == "__main__":
    migrate_to_jinja2_middleware()