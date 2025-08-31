"""
Example: Gmail Prompts with Jinja2 Templating Engine

This shows how our Gmail prompts would be MUCH cleaner with proper templating.
"""

from jinja2 import Template, Environment, FileSystemLoader
from pathlib import Path
from datetime import datetime, timezone

# Type hints for the example (in real implementation, these would be proper imports)
from typing_extensions import Any
Context = Any  # Real: from your context module
PromptMessage = Any  # Real: from fastmcp.types
TextContent = Any  # Real: from fastmcp.types

# Clean template file (no escaping hell)
SIMPLE_EMAIL_TEMPLATE = """
# ⚡ Quick Email Demo (Simple) - With Real Gmail Resources
*Request ID: {{ request_id }} | Generated: {{ current_time }}*

## 🎯 Zero-Configuration Demo with Live Gmail Data

### Features
- **Level**: Simple - No parameters required
- **Ready**: Instant send capability with real Gmail integration
- **Design**: Clean and professional with live resource data
- **Testing**: Perfect for quick demos using actual Gmail labels and settings

### 📊 **GMAIL RESOURCE INTEGRATION:**
- **Resource Status**: {{ auth_status }}
- **Your Email**: `{{ user_email }}` (from `{{user://current/email}}`)  
- **Your Labels**: `{{ first_label_name }}` ({{ first_label_id }}), `{{ second_label_name }}` ({{ second_label_id }})
- **System Labels**: {{ system_count }} available
- **Custom Labels**: {{ user_label_count }} total

### 🔍 **RESOURCE DATA FROM MCP CONTEXT:**

```xml
<resource_status>{{ auth_status }}</resource_status>

<gmail_data source="context.resources">
  <user_email>{{ user_email }}</user_email>
  
  <system_labels count="{{ system_count }}">
    <!-- INBOX, SENT, DRAFT, TRASH, SPAM, STARRED, IMPORTANT -->
  </system_labels>
  
  <user_labels count="{{ user_label_count }}">
    <label id="{{ first_label_id }}" name="{{ first_label_name }}"/>
    <label id="{{ second_label_id }}" name="{{ second_label_name }}"/>
    <!-- Additional labels available in authenticated session -->
  </user_labels>
</gmail_data>

{% if not authenticated %}
<authentication_help>
  <!-- If you see "Authentication required", run: -->
  <!-- start_google_auth('your.email@gmail.com') -->
</authentication_help>
{% endif %}
```

## 📧 Instant Send Example with Real Resource Integration

```xml
<mcp_tool_call>
  <tool>send_gmail_message</tool>
  <params>
    <user_google_email>{{user://current/email}}</user_google_email>
    <to>demo@example.com</to>
    <subject>FastMCP2 Email Demo - Live Gmail Integration</subject>
    <content_type>mixed</content_type>
    <body><![CDATA[
Hello!

This is a demonstration of FastMCP2's email capabilities with live Gmail resource integration.

🔥 Real Gmail Data Integration:
{% for label in top_labels %}
• Label: {{ label.name }} (ID: {{ label.id }})
{% endfor %}
• System Labels: {{ system_count }} system labels available
• Total Labels: {{ user_label_count }} custom + {{ system_count }} system = {{ total_labels }} total!

Key benefits:
{% for benefit in benefits %}
• {{ benefit }}
{% endfor %}

Best regards,
FastMCP2 Team with Real Gmail Data
    ]]></body>
  </params>
</mcp_tool_call>
```

## 🚀 Simple & Effective with Real Gmail Integration

### Zero Configuration Benefits + Live Data
{% for feature in features %}
- **{{ feature.title }}**: {{ feature.description }}
{% endfor %}

### Real Gmail Resource Integration Features
{% for integration in integrations %}
- **{{ integration.name }}**: {{ integration.description }}
{% endfor %}
"""

# Clean Python code (no f-string hell)
class GmailPromptsWithJinja:
    def __init__(self):
        self.env = Environment(loader=FileSystemLoader('templates'))
        
    async def quick_email_demo(self, context: Context) -> PromptMessage:
        """Clean templating approach - no f-string nightmare!"""
        
        # Get resource data (clean separation)
        gmail_data = await self._get_gmail_resources(context)
        
        # Prepare template context (clean data preparation)
        template_context = {
            'request_id': context.request_id,
            'current_time': datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            'authenticated': gmail_data['authenticated'],
            'auth_status': gmail_data['auth_status'],
            'user_email': gmail_data['user_email'],
            'first_label_name': gmail_data['labels'][0]['name'] if gmail_data['labels'] else 'MCP',
            'first_label_id': gmail_data['labels'][0]['id'] if gmail_data['labels'] else 'Label_13',
            'second_label_name': gmail_data['labels'][1]['name'] if len(gmail_data['labels']) > 1 else 'Tech',
            'second_label_id': gmail_data['labels'][1]['id'] if len(gmail_data['labels']) > 1 else 'Label_21',
            'system_count': gmail_data['system_count'],
            'user_label_count': gmail_data['user_count'],
            'total_labels': gmail_data['system_count'] + gmail_data['user_count'],
            'top_labels': gmail_data['labels'][:5],  # Clean list handling
            'benefits': [
                "Zero setup required but with real Gmail integration",
                "Professional appearance with live label data", 
                "Instant results using actual user email",
                "Cross-platform compatibility with Gmail resources"
            ],
            'features': [
                {'title': 'Instant Results', 'description': 'Works immediately without setup using real Gmail data'},
                {'title': 'Professional Look', 'description': 'Clean design enhanced with actual Gmail information'},
                {'title': 'Perfect Testing', 'description': 'Ideal for verifying Gmail resource integration'}
            ],
            'integrations': [
                {'name': 'Live User Email', 'description': 'Automatically uses user://current/email for sender'},
                {'name': 'Actual Labels', 'description': 'Shows real Gmail labels from service://gmail/labels'},
                {'name': 'System Integration', 'description': 'Displays count of system labels available'}
            ]
        }
        
        # Render template (clean and simple!)
        template = Template(SIMPLE_EMAIL_TEMPLATE)
        content = template.render(**template_context)
        
        return PromptMessage(
            role="user",
            content=TextContent(text=content)
        )
    
    async def _get_gmail_resources(self, context: Context) -> dict:
        """Clean resource reading - separated from presentation"""
        try:
            # Try to read Gmail resources using proper context method
            gmail_labels = await context.read_resource("service://gmail/labels")
            user_email_data = await context.read_resource("user://current/email") 
            
            return {
                'authenticated': True,
                'auth_status': "✅ Authenticated - Real data loaded",
                'user_email': user_email_data.get('email', 'sethrivers@gmail.com'),
                'labels': gmail_labels.get('user_labels', []),
                'system_count': len(gmail_labels.get('system_labels', [])),
                'user_count': len(gmail_labels.get('user_labels', []))
            }
        except Exception as e:
            # Clean error handling
            return {
                'authenticated': False,
                'auth_status': f"❌ Authentication required: {str(e)}",
                'user_email': 'sethrivers@gmail.com',
                'labels': [
                    {'name': 'MCP', 'id': 'Label_13'},
                    {'name': 'Tech/Development', 'id': 'Label_21'}
                ],
                'system_count': 15,
                'user_count': 38
            }


# Benefits Summary:
"""
✅ No f-string escaping hell
✅ Clean separation of logic and templates
✅ Easy to debug template syntax errors
✅ Conditional logic and loops 
✅ Template inheritance and includes
✅ Professional template organization
✅ Better maintainability
✅ Industry standard approach
✅ Rich filter system
✅ Template debugging tools
"""