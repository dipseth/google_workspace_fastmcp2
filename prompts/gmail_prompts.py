"""
Gmail Prompts with Jinja2 Templates for FastMCP2

This module provides clean Gmail prompts using professional Jinja2 templating
instead of problematic f-strings. Integrates with Template Parameter Middleware
for automatic resource resolution.

Features:
- Clean Jinja2 templates (no f-string CSS parsing errors!)
- Template Parameter Middleware integration 
- Automatic {{resource://uri}} resolution
- Professional email templates
- Proper error handling and fallbacks
"""

import json
import logging
from typing_extensions import Optional, Dict, Any, List
from datetime import datetime, timezone
from pathlib import Path

try:
    from jinja2 import Environment, FileSystemLoader, Template, DictLoader, ChoiceLoader
    JINJA2_AVAILABLE = True
except ImportError:
    JINJA2_AVAILABLE = False
    print("⚠️ Jinja2 not available, falling back to simple templates")

from fastmcp import FastMCP, Context
from fastmcp.prompts.prompt import Message, PromptMessage, TextContent

logger = logging.getLogger(__name__)




class GmailPrompts:
    """Gmail prompts with professional Jinja2 templates and Template Parameter Middleware integration."""
    
    def __init__(self):
        """Initialize with Jinja2 template environment."""
        self.jinja_env = None
        
        if JINJA2_AVAILABLE:
            # Setup template directories (corrected paths)
            template_dirs = [
                "prompts/templates/gmail",  # Primary location after move
                "prompts/templates",
                "templates/gmail",           # Fallback locations
                "templates"
            ]
            
            # Find existing directories
            loaders = []
            for template_dir in template_dirs:
                path = Path(template_dir)
                if path.exists():
                    loaders.append(FileSystemLoader(str(path)))
                    logger.info(f"📁 Found Gmail template directory: {path}")
            
            if loaders:
                loader = ChoiceLoader(loaders)
                logger.info(f"✅ Using {len(loaders)} template directories")
            else:
                # Use built-in templates as fallback
                loader = DictLoader({
                    'quick_demo_simple.txt': self._get_builtin_simple_template()
                })
                logger.info("📄 Using built-in Gmail template (no template directories found)")
            
            self.jinja_env = Environment(
                loader=loader,
                autoescape=False,  # We're generating text/markdown
                trim_blocks=True,
                lstrip_blocks=True
            )
            
            logger.info("✅ Clean Gmail prompts initialized with Jinja2")
    
    def _get_builtin_simple_template(self) -> str:
        """Get the built-in simple template."""
        return """# ⚡ Quick Email Demo (Simple) - With Real Gmail Resources
*Request ID: {{ request_id }} | Generated: {{ current_time }}*

## 🎯 Zero-Configuration Demo with Live Gmail Data

### 📊 **GMAIL RESOURCE INTEGRATION:**
- **Resource Status**: {{ auth_status }}
- **Your Email**: `{{ user_email }}` (from `{{user://current/email}}`)
{% if labels %}
- **Your Labels**: 
{% for label in labels[:3] %}
  - {{ label.name }} ({{ label.id }})
{% endfor %}
{% else %}
- **Labels**: Authentication required
{% endif %}
- **System Labels**: {{ system_count }} available
- **Custom Labels**: {{ user_count }} total

## 📧 Instant Send Example

```xml
<mcp_tool_call>
  <tool>send_gmail_message</tool>
  <params>
    <user_google_email>{{user://current/email}}</user_google_email>
    <to>demo@example.com</to>
    <subject>FastMCP2 Email Demo - {{ current_date }}</subject>
    <body><![CDATA[
Hello!

This is a FastMCP2 email demo with live Gmail integration.

🔥 Real Gmail Data:
{% for label in labels[:5] %}
• {{ label.name }} ({{ label.id }})
{% endfor %}
• Total: {{ user_count + system_count }} labels

Best regards,
FastMCP2 Team
    ]]></body>
  </params>
</mcp_tool_call>
```

## 🚀 Benefits
- **Instant Results**: Works with real Gmail data
- **Professional Look**: Clean design  
- **Zero Config**: No setup required
{% if not authenticated %}

### 🔧 Setup Required
Run: `start_google_auth('your.email@gmail.com')`
{% endif %}

---
*Generated with Jinja2 templates • No CSS errors!*"""
    
    async def quick_email_demo(self, context: Context) -> PromptMessage:
        """
        Clean Gmail Quick Email Demo using Jinja2 templates.
        
        This replaces the broken f-string version with a clean Jinja2 approach
        that doesn't have CSS parsing errors.
        """
        try:
            # Get Gmail resource data
            gmail_data = await self._get_gmail_resources(context)
            
            # Prepare template context
            template_context = {
                'request_id': context.request_id,
                'current_time': datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
                'current_date': datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                'authenticated': gmail_data['authenticated'],
                'auth_status': gmail_data['auth_status'],
                'user_email': gmail_data['user_email'],
                'labels': gmail_data['labels'],
                'system_count': gmail_data['system_count'],
                'user_count': gmail_data['user_count']
            }
            
            # Render with Jinja2
            if JINJA2_AVAILABLE and self.jinja_env:
                try:
                    template = self.jinja_env.get_template('quick_demo_simple.txt')
                    content = template.render(**template_context)
                    logger.info("✅ Rendered with Jinja2 template")
                except Exception as e:
                    logger.warning(f"Template error: {e}, using fallback")
                    content = self._render_fallback(template_context)
            else:
                content = self._render_fallback(template_context)
            
            return PromptMessage(
                role="user",
                content=TextContent(type="text", text=content)
            )
            
        except Exception as e:
            logger.error(f"Error in Gmail prompt: {e}")
            return self._create_error_prompt(str(e))
    
    async def _get_gmail_resources(self, context: Context) -> Dict[str, Any]:
        """Get Gmail resources from context - clean implementation."""
        try:
            # Try to read Gmail resources
            gmail_labels = None
            user_email = "test_example@gmail.com"  # fallback
            
            # Check for resources in context (implementation depends on your context structure)
            if hasattr(context, 'read_resource'):
                try:
                    gmail_labels = await context.read_resource("service://gmail/labels")
                    user_email_result = await context.read_resource("user://current/email")
                    if user_email_result:
                        if isinstance(user_email_result, dict):
                            user_email = user_email_result.get('email', user_email)
                        elif isinstance(user_email_result, str):
                            user_email = user_email_result
                except Exception as e:
                    logger.warning(f"Resource read error: {e}")
            
            # Process Gmail labels - handle both dict and list responses
            if gmail_labels:
                if isinstance(gmail_labels, dict) and not gmail_labels.get('error'):
                    return {
                        'authenticated': True,
                        'auth_status': "✅ Authenticated - Real data loaded",
                        'user_email': user_email,
                        'labels': gmail_labels.get('user_labels', []),
                        'system_count': len(gmail_labels.get('system_labels', [])),
                        'user_count': len(gmail_labels.get('user_labels', []))
                    }
                elif isinstance(gmail_labels, list):
                    # Handle direct list of labels
                    processed_labels = []
                    for label in gmail_labels:
                        if isinstance(label, dict):
                            processed_labels.append({
                                'name': label.get('name', 'Unknown'),
                                'id': label.get('id', 'Unknown'),
                                'type': label.get('type', 'user')
                            })
                    
                    return {
                        'authenticated': True,
                        'auth_status': "✅ Authenticated - List data loaded",
                        'user_email': user_email,
                        'labels': processed_labels[:10],  # Take first 10 for display
                        'system_count': len([l for l in processed_labels if l.get('type') == 'system']),
                        'user_count': len([l for l in processed_labels if l.get('type') != 'system'])
                    }
                else:
                    # Authentication required or error
                    error_msg = "Authentication required"
                    if isinstance(gmail_labels, dict) and gmail_labels.get('error'):
                        error_msg = gmail_labels.get('error', 'Unknown error')
                    else:
                        error_msg = f"Unexpected data format: {type(gmail_labels)}"
            else:
                # No data available
                error_msg = "No Gmail data available"
            
            return {
                'authenticated': False,
                'auth_status': f"❌ {error_msg}",
                'user_email': user_email,
                'labels': [
                    {'name': 'MCP', 'id': 'Label_13'},
                    {'name': 'Tech/Development', 'id': 'Label_21'}
                ],
                'system_count': 15,
                'user_count': 38
            }
                
        except Exception as e:
            logger.error(f"Gmail resource error: {e}")
            return {
                'authenticated': False,
                'auth_status': f"⚠️ Resource error: {str(e)}",
                'user_email': 'test_example@gmail.com',
                'labels': [],
                'system_count': 0,
                'user_count': 0
            }
    
    def _render_fallback(self, context: Dict) -> str:
        """Render fallback content without Jinja2."""
        return f"""# ⚡ Quick Email Demo (Simple) - Fallback
*Request ID: {context['request_id']} | Generated: {context['current_time']}*

## 📊 Gmail Integration Status
- **Status**: {context['auth_status']}
- **Email**: {context['user_email']}
- **Labels**: {context['user_count']} custom + {context['system_count']} system

## 📧 Basic Email Example

```xml
<mcp_tool_call>
  <tool>send_gmail_message</tool>
  <params>
    <user_google_email>{{{{user://current/email}}}}</user_google_email>
    <to>demo@example.com</to>
    <subject>FastMCP2 Demo</subject>
    <body>Hello! This is a FastMCP2 email demo.</body>
  </params>
</mcp_tool_call>
```

*Fallback template - install Jinja2 for better templates*"""
    
    def _create_error_prompt(self, error: str) -> PromptMessage:
        """Create error prompt."""
        return PromptMessage(
            role="user",
            content=TextContent(type="text", text=f"""# ⚡ Gmail Demo (Error)
*Error: {error}*

## 📧 Basic Demo

```xml
<mcp_tool_call>
  <tool>send_gmail_message</tool>
  <params>
    <user_google_email>test_example@gmail.com</user_google_email>
    <to>demo@example.com</to>
    <subject>FastMCP2 Email Demo</subject>
    <body>Hello! This is a basic email demo.</body>
  </params>
</mcp_tool_call>
```""")
        )


# Global instance
_gmail_prompts = None


def get_gmail_prompts() -> GmailPrompts:
    """Get the global Gmail prompts instance."""
    global _gmail_prompts
    if _gmail_prompts is None:
        _gmail_prompts = GmailPrompts()
    return _gmail_prompts


# Setup function for server.py integration
def setup_gmail_prompts(mcp: FastMCP):
    """
    Setup Gmail prompts with Jinja2 templates and Template Parameter Middleware integration.
    
    This function registers the clean Gmail prompts that work with both:
    1. Jinja2 templates for presentation
    2. Template Parameter Middleware for {{resource://uri}} resolution
    """
    gmail_prompts = get_gmail_prompts()
    
    @mcp.prompt(
        name="quick_email_demo",
        description="Simple: Zero-config Gmail demo with Jinja2 templates and resource integration",
        tags={"gmail", "simple", "demo", "jinja2", "resources"},
        meta={
            "version": "4.0",
            "author": "FastMCP2-Jinja2",
            "uses_jinja2": True,
            "uses_template_middleware": True,
            "resource_dependencies": ["service://gmail/labels", "user://current/email"]
        }
    )
    async def quick_email_demo_prompt(context: Context) -> PromptMessage:
        """Gmail Quick Email Demo - Clean Jinja2 version with Template Parameter Middleware support."""
        return await gmail_prompts.quick_email_demo(context)
    
    logger.info("✅ Gmail prompts with Jinja2 templates registered successfully")
    logger.info("   • quick_email_demo: Simple zero-config demo with resource integration")
    logger.info("   • Template Parameter Middleware: {{resource://uri}} expressions supported")
    logger.info("   • Jinja2 Templates: Professional presentation layer")
    
    return gmail_prompts


# Export for server.py
__all__ = ['setup_gmail_prompts', 'get_gmail_prompts']