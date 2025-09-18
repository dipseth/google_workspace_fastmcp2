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
        Gmail Quick Email Demo that returns template content with {{resource://uri}} variables.
        
        The Template Parameter Middleware will automatically resolve these variables
        in the on_get_prompt hook after this function returns.
        """
        try:
            # Return template content with resource variables - middleware will resolve them!
            if JINJA2_AVAILABLE and self.jinja_env:
                try:
                    template = self.jinja_env.get_template('quick_demo_simple.txt')
                    # Return raw template content with resource variables
                    template_content = template.source
                except Exception:
                    template_content = self._get_template_content_with_resources()
            else:
                template_content = self._get_template_content_with_resources()
            
            # Basic template context that doesn't require resource resolution
            basic_context = {
                'request_id': context.request_id,
                'current_time': datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
                'current_date': datetime.now(timezone.utc).strftime("%Y-%m-%d")
            }
            
            # Do basic Jinja2 rendering for non-resource variables only
            if JINJA2_AVAILABLE and self.jinja_env:
                template_obj = self.jinja_env.from_string(template_content)
                content = template_obj.render(**basic_context)
            else:
                # Simple string replacement for basic variables
                content = template_content
                for key, value in basic_context.items():
                    content = content.replace(f"{{{{ {key} }}}}", str(value))
            
            return PromptMessage(
                role="user",
                content=TextContent(type="text", text=content)
            )
            
        except Exception as e:
            logger.error(f"Error in Gmail prompt: {e}")
            return self._create_error_prompt(str(e))
    
    def _get_template_content_with_resources(self) -> str:
        """Get template content with resource variables that middleware will resolve."""
        return """# ⚡ Template Middleware Resource Resolution Demo
*Request ID: {{ request_id }} | Generated: {{ current_time }}*

## 🎯 Template Parameter Middleware Integration Demo

### 📊 **MIDDLEWARE RESOURCE RESOLUTION:**
- **Your Email**: `{{user://current/email}}` (resolved by middleware)
- **Gmail Labels**: `{{service://gmail/labels}}` (resolved by middleware)
- **System Status**: Template Parameter Middleware processing

### 🔧 **How This Works:**
1. **Prompt Function**: Returns content with `{{resource://uri}}` variables
2. **Middleware Hook**: `on_get_prompt` processes the result
3. **Resource Resolution**: Same system as tool parameters
4. **Final Result**: Variables resolved automatically

## 📧 **Template Middleware Tool Call Demo**

This tool call will also have its `{{resource://uri}}` resolved by the same middleware:

```xml
<mcp_tool_call>
  <tool>send_gmail_message</tool>
  <params>
    <user_google_email>{{user://current/email}}</user_google_email>
    <to>demo@example.com</to>
    <subject>Template Middleware Demo - {{ current_date }}</subject>
    <body><![CDATA[
Hello!

This demonstrates Template Parameter Middleware working for BOTH:
1. PROMPT content (this message you're reading)
2. TOOL parameters (the user_google_email field above)

Resource Variables Resolved:
- Email: {{user://current/email}}
- Labels: {{service://gmail/labels}}

Same middleware, same resolution system!

Best regards,
Template Parameter Middleware Demo
    ]]></body>
  </params>
</mcp_tool_call>
```

## ✅ **Unified Resource Resolution**
- **Prompts**: Resource variables resolved via `on_get_prompt` hook
- **Tools**: Resource variables resolved via `on_call_tool` hook
- **Same System**: Both use Template Parameter Middleware
- **Consistent**: `{{resource://uri}}` syntax works everywhere

---
*Template Parameter Middleware • Same system for tools AND prompts!*"""
    
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