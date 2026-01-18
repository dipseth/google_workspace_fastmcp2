"""
Structured Response Demo Prompts for FastMCP2

This module provides dynamic MCP prompts that showcase tools and their structured responses.
It randomly selects tools from the server and demonstrates both original string responses
and their structured counterparts using the structured response middleware.

Features:
- Dynamic tool discovery and demonstration
- Random tool selection for varied examples
- Before/after response comparison (string vs structured)
- Interactive demonstration prompts
- Integration with Template Parameter Middleware
- Professional Jinja2 templating
"""

import json
import random
from datetime import datetime, timezone
from typing import Any, Dict, Optional

try:
    from jinja2 import DictLoader, Environment, Template

    JINJA2_AVAILABLE = True
except ImportError:
    JINJA2_AVAILABLE = False
    print("⚠️ Jinja2 not available, falling back to simple templates")

from fastmcp import Context, FastMCP
from fastmcp.prompts.prompt import PromptMessage, TextContent

from config.enhanced_logging import setup_logger
from prompts.tool_optimization_helper import ToolOptimizationHelper

logger = setup_logger()


class StructuredResponseDemoPrompts:
    """Demo prompts showcasing structured response capabilities with tool examples."""

    def __init__(self):
        """Initialize with Jinja2 template environment and tool mappings."""
        self.jinja_env = None
        self.structured_tools_map = self._get_structured_tools_mapping()

        # Pre-generate tool optimization content for different demo types
        self.multi_service_optimization = ToolOptimizationHelper.generate_multi_service_section()

        if JINJA2_AVAILABLE:
            # Built-in templates for structured response demos
            templates = {
                "tool_showcase.txt": self._get_tool_showcase_template(),
                "comparison_demo.txt": self._get_comparison_demo_template(),
                "interactive_demo.txt": self._get_interactive_demo_template(),
                "structured_benefits.txt": self._get_benefits_template(),
            }

            loader = DictLoader(templates)
            self.jinja_env = Environment(
                loader=loader, autoescape=False, trim_blocks=True, lstrip_blocks=True
            )

            logger.info("✅ Structured Response Demo prompts initialized with Jinja2")

    def _get_structured_tools_mapping(self) -> Dict[str, Dict[str, Any]]:
        """Get mapping of structured tools with example data and descriptions."""
        return {
            "send_gmail_message": {
                "category": "Gmail",
                "description": "Send an email via Gmail",
                "example_params": {
                    "user_google_email": "{{user://current/email}}",
                    "to": "demo@example.com",
                    "subject": "FastMCP2 Demo Email",
                    "body": "This is a test email from FastMCP2!",
                },
                "original_response_example": "Message sent successfully! Message ID: msg_abc123xyz",
                "structured_response_example": {
                    "success": True,
                    "userEmail": "user@example.com",
                    "messageId": "msg_abc123xyz",
                    "message": "Email sent successfully",
                    "error": None,
                },
            },
            "upload_file_to_drive": {
                "category": "Drive",
                "description": "Upload a file to Google Drive",
                "example_params": {
                    "user_google_email": "{{user://current/email}}",
                    "filepath": "/path/to/document.pdf",
                    "filename": "Important Document.pdf",
                    "folder_id": "root",
                },
                "original_response_example": "File uploaded successfully to Google Drive! File ID: 1abc123xyz_def456",
                "structured_response_example": {
                    "success": True,
                    "userEmail": "user@example.com",
                    "fileId": "1abc123xyz_def456",
                    "fileName": "Important Document.pdf",
                    "message": "File uploaded successfully to Google Drive",
                    "error": None,
                },
            },
            "create_event": {
                "category": "Calendar",
                "description": "Create a Google Calendar event",
                "example_params": {
                    "user_google_email": "{{user://current/email}}",
                    "summary": "Team Meeting",
                    "start_time": "2025-09-04T14:00:00Z",
                    "end_time": "2025-09-04T15:00:00Z",
                    "description": "Weekly team sync meeting",
                },
                "original_response_example": "Event created successfully! Event ID: evt_789xyz123",
                "structured_response_example": {
                    "success": True,
                    "userEmail": "user@example.com",
                    "eventId": "evt_789xyz123",
                    "calendarId": "primary",
                    "message": "Event created successfully",
                    "error": None,
                },
            },
            "create_form": {
                "category": "Forms",
                "description": "Create a Google Form",
                "example_params": {
                    "user_google_email": "{{user://current/email}}",
                    "title": "Customer Feedback Survey",
                    "description": "Please share your thoughts about our service",
                },
                "original_response_example": "Form created successfully! Form ID: form_survey_456",
                "structured_response_example": {
                    "success": True,
                    "userEmail": "user@example.com",
                    "formId": "form_survey_456",
                    "message": "Form created successfully",
                    "error": None,
                },
            },
            "create_presentation": {
                "category": "Slides",
                "description": "Create a Google Slides presentation",
                "example_params": {
                    "user_google_email": "{{user://current/email}}",
                    "title": "Q4 Business Review",
                },
                "original_response_example": "Presentation created! ID: pres_q4_review_789",
                "structured_response_example": {
                    "success": True,
                    "userEmail": "user@example.com",
                    "presentationId": "pres_q4_review_789",
                    "message": "Presentation created successfully",
                    "error": None,
                },
            },
            "send_dynamic_card": {
                "category": "Chat",
                "description": "Send a dynamic card to Google Chat",
                "example_params": {
                    "user_google_email": "{{user://current/email}}",
                    "space_id": "spaces/AAAAxxxx",
                    "card_description": "Create a status update card with action buttons",
                },
                "original_response_example": "Card sent successfully to Google Chat space!",
                "structured_response_example": {
                    "success": True,
                    "userEmail": "user@example.com",
                    "messageId": "msg_card_123",
                    "spaceId": "spaces/AAAAxxxx",
                    "message": "Dynamic card sent successfully",
                    "error": None,
                },
            },
        }

    def _get_tool_showcase_template(self) -> str:
        """Template for showcasing a random tool with structured responses."""
        return """# 🛠️ FastMCP2 Tool Showcase: {{ tool_name }}
*Request ID: {{ request_id }} | Generated: {{ current_time }}*

{{ tool_optimization }}

## 🎯 Featured Tool: **{{ tool_info.category }}** → `{{ tool_name }}`

**Description:** {{ tool_info.description }}

### 📊 **STRUCTURED RESPONSE DEMONSTRATION**

#### 🔧 Tool Parameters:
```json
{{ tool_params | tojson(indent=2) }}
```

#### 📤 **ORIGINAL STRING RESPONSE:**
```
{{ original_response }}
```

#### 🎁 **NEW STRUCTURED RESPONSE:**
```json
{{ structured_response | tojson(indent=2) }}
```

### ⚡ **Try It Yourself!**

```xml
<mcp_tool_call>
  <tool>{{ tool_name }}_structured</tool>
  <params>
{% for key, value in tool_params.items() %}
    <{{ key }}>{{ value }}</{{ key }}>
{% endfor %}
  </params>
</mcp_tool_call>
```

### 🚀 **Benefits of Structured Responses:**
- **Consistent Format**: Always get standardized response structure
- **Error Handling**: Clear success/error states with detailed messages
- **ID Extraction**: Automatic extraction of important IDs (messageId, fileId, etc.)
- **Type Safety**: Structured data instead of parsing strings
- **Integration Ready**: Perfect for downstream processing and automation

---
*Powered by FastMCP2 Structured Response Middleware • Generated with Jinja2*"""

    def _get_comparison_demo_template(self) -> str:
        """Template for comparing multiple tools side-by-side."""
        return """# 🔄 FastMCP2 Response Comparison Demo
*Request ID: {{ request_id }} | Generated: {{ current_time }}*

{{ tool_optimization }}

## 📊 **BEFORE vs AFTER: String Responses → Structured Data**

{% for tool_name, tool_info in tools_comparison.items() %}
### 🛠️ {{ loop.index }}. **{{ tool_info.category }}** → `{{ tool_name }}`
{{ tool_info.description }}

**Original Response:**
```
{{ tool_info.original_response_example }}
```

**Structured Response:**
```json
{{ tool_info.structured_response_example | tojson(indent=2) }}
```

---
{% endfor %}

## 🎯 **Key Improvements**

| Feature | Original Response | Structured Response |
|---------|-------------------|-------------------|
| **Format** | Unstructured text | Consistent JSON schema |
| **Success Detection** | String parsing required | Boolean `success` field |
| **ID Extraction** | Regex/manual parsing | Dedicated ID fields |
| **Error Handling** | Mixed with success text | Separate `error` field |
| **Machine Readable** | ❌ Requires parsing | ✅ Direct JSON access |
| **Type Safety** | ❌ All strings | ✅ Proper types |

## 🚀 **Try These Tools:**

{% for tool_name, tool_info in tools_comparison.items() %}
```xml
<!-- {{ tool_info.category }} Tool -->
<mcp_tool_call>
  <tool>{{ tool_name }}_structured</tool>
  <params>
{% for key, value in tool_info.example_params.items() %}
    <{{ key }}>{{ value }}</{{ key }}>
{% endfor %}
  </params>
</mcp_tool_call>
```

{% endfor %}

---
*FastMCP2 Structured Response System • {{ tools_comparison | length }} tools demonstrated*"""

    def _get_interactive_demo_template(self) -> str:
        """Template for interactive demonstration prompt."""
        return """# 🎮 Interactive FastMCP2 Structured Response Demo
*Request ID: {{ request_id }} | Generated: {{ current_time }}*

{{ tool_optimization }}

## 🎲 **Random Tool Challenge!**

Today's featured tool: **{{ featured_tool.category }}** → `{{ featured_tool.name }}`

### 🎯 **Your Mission:**
{{ featured_tool.description }} and observe how the structured response provides clean, machine-readable output!

### 🔧 **Tool Setup:**
```xml
<mcp_tool_call>
  <tool>{{ featured_tool.name }}_structured</tool>
  <params>
{% for key, value in featured_tool.example_params.items() %}
    <{{ key }}>{{ value }}</{{ key }}>
{% endfor %}
  </params>
</mcp_tool_call>
```

### 📊 **Expected Structured Output:**
```json
{{ featured_tool.structured_response_example | tojson(indent=2) }}
```

## 🎖️ **Challenge Levels:**

### 🥉 **Bronze**: Run the tool as shown above
- Get familiar with structured responses
- See the consistent JSON format

### 🥈 **Silver**: Modify parameters and try variations
- Change the email address, file names, or other parameters
- Notice how the structure remains consistent

### 🥇 **Gold**: Compare with original tool (remove `_structured` suffix)
- Run both versions side-by-side
- Appreciate the improvement in data structure

### 💎 **Platinum**: Chain multiple structured tools together
- Use the output from one structured tool as input to another
- Build complex workflows with reliable data flow

## 📚 **Available Structured Tools:**
{% for category, tools in structured_categories.items() %}
**{{ category }}:**
{% for tool in tools %}
- `{{ tool }}_structured`
{% endfor %}

{% endfor %}

## 💡 **Pro Tips:**
- All structured tools end with `_structured` suffix
- Original tools remain available for backward compatibility
- Use structured responses for automation and integration
- Error handling is much cleaner with structured format

---
*Ready to level up your MCP game? Try the challenge above! 🚀*"""

    def _get_benefits_template(self) -> str:
        """Template explaining the benefits of structured responses."""
        return """# ✨ FastMCP2 Structured Response Benefits
*Request ID: {{ request_id }} | Generated: {{ current_time }}*

{{ tool_optimization }}

## 🎯 **Why Structured Responses Matter**

### 🔄 **The Problem with String Responses**
Traditional MCP tools return unstructured text:
```
"Message sent successfully! Message ID: msg_abc123xyz"
"File uploaded to Google Drive! File ID: 1xyz789abc"  
"Error: Invalid email address provided"
```

**Issues:**
- 🚫 Inconsistent formats across different tools
- 🚫 Difficult to parse programmatically  
- 🚫 Error handling mixed with success messages
- 🚫 No type safety or validation
- 🚫 Hard to extract important data (IDs, status, etc.)

### ✅ **The Structured Response Solution**
Our middleware transforms responses to consistent JSON:
```json
{
  "success": true,
  "userEmail": "user@example.com",
  "messageId": "msg_abc123xyz", 
  "message": "Message sent successfully",
  "error": null
}
```

**Benefits:**
- ✅ **Consistent Schema**: All tools follow same response structure
- ✅ **Type Safety**: Proper types (boolean, string, null) instead of all strings
- ✅ **Easy Parsing**: Direct JSON access, no regex needed
- ✅ **Clear Error Handling**: Separate success flag and error field
- ✅ **ID Extraction**: Automatic extraction of important identifiers
- ✅ **Integration Ready**: Perfect for chaining tools and automation

## 🛠️ **Implementation Details**

### 📈 **Coverage Statistics**
- **{{ coverage_stats.total_tools }}** total tools in server
- **{{ coverage_stats.structured_tools }}** tools with structured variants  
- **{{ coverage_stats.coverage_percentage }}%** coverage achieved
- **{{ coverage_stats.categories | length }}** service categories covered

### 🔧 **Response Schema Types**
{% for schema_name, schema_desc in response_schemas.items() %}
**{{ schema_name }}:**
- {{ schema_desc.description }}
- Fields: {{ schema_desc.fields | join(', ') }}

{% endfor %}

### 🎯 **Tool Categories Covered**
{% for category, count in coverage_stats.categories.items() %}
- **{{ category }}**: {{ count }} tools
{% endfor %}

## 🚀 **Get Started**

### 1️⃣ **Try a Basic Structured Tool**
```xml
<mcp_tool_call>
  <tool>send_gmail_message_structured</tool>
  <params>
    <user_google_email>{{ "{{" }}user://current/email{{ "}}" }}</user_google_email>
    <to>test@example.com</to>
    <subject>Structured Response Test</subject>
    <body>Testing the new structured response system!</body>
  </params>
</mcp_tool_call>
```

### 2️⃣ **Compare with Original**
```xml
<mcp_tool_call>
  <tool>send_gmail_message</tool>
  <params>
    <user_google_email>{{ "{{" }}user://current/email{{ "}}" }}</user_google_email>
    <to>test@example.com</to>
    <subject>Original Response Test</subject>
    <body>Testing the original response format.</body>
  </params>
</mcp_tool_call>
```

### 3️⃣ **Build Advanced Workflows**
Chain structured tools together using their consistent response format for complex automation tasks!

---
*FastMCP2 Structured Response System • Making MCP tools more powerful and developer-friendly! 🎉*"""

    async def tool_showcase(
        self, context: Context, tool_name: Optional[str] = None
    ) -> PromptMessage:
        """
        Showcase a specific tool (or random if not specified) with structured responses.
        """
        try:
            # Select tool to showcase
            if tool_name and tool_name in self.structured_tools_map:
                selected_tool = tool_name
                tool_info = self.structured_tools_map[tool_name]
            else:
                # Random selection
                selected_tool = random.choice(list(self.structured_tools_map.keys()))
                tool_info = self.structured_tools_map[selected_tool]

            # Prepare template context
            template_context = {
                "request_id": context.request_id,
                "current_time": datetime.now(timezone.utc).strftime(
                    "%Y-%m-%d %H:%M:%S UTC"
                ),
                "tool_name": selected_tool,
                "tool_info": tool_info,
                "tool_params": tool_info["example_params"],
                "original_response": tool_info["original_response_example"],
                "structured_response": tool_info["structured_response_example"],
                "tool_optimization": self.multi_service_optimization,
            }

            # Render with Jinja2
            if JINJA2_AVAILABLE and self.jinja_env:
                template = self.jinja_env.get_template("tool_showcase.txt")
                content = template.render(**template_context)
                logger.info(f"✅ Rendered tool showcase for: {selected_tool}")
            else:
                content = self._render_fallback_showcase(template_context)

            return PromptMessage(
                role="user", content=TextContent(type="text", text=content)
            )

        except Exception as e:
            logger.error(f"Error in tool showcase prompt: {e}")
            return self._create_error_prompt(str(e))

    async def comparison_demo(
        self, context: Context, num_tools: int = 3
    ) -> PromptMessage:
        """
        Show side-by-side comparison of multiple tools and their response formats.
        """
        try:
            # Select random tools for comparison
            available_tools = list(self.structured_tools_map.keys())
            selected_tools = random.sample(
                available_tools, min(num_tools, len(available_tools))
            )

            tools_comparison = {
                tool: self.structured_tools_map[tool] for tool in selected_tools
            }

            # Prepare template context
            template_context = {
                "request_id": context.request_id,
                "current_time": datetime.now(timezone.utc).strftime(
                    "%Y-%m-%d %H:%M:%S UTC"
                ),
                "tools_comparison": tools_comparison,
                "tool_optimization": self.multi_service_optimization,
            }

            # Render with Jinja2
            if JINJA2_AVAILABLE and self.jinja_env:
                template = self.jinja_env.get_template("comparison_demo.txt")
                content = template.render(**template_context)
                logger.info(
                    f"✅ Rendered comparison demo for {len(selected_tools)} tools"
                )
            else:
                content = self._render_fallback_comparison(template_context)

            return PromptMessage(
                role="user", content=TextContent(type="text", text=content)
            )

        except Exception as e:
            logger.error(f"Error in comparison demo prompt: {e}")
            return self._create_error_prompt(str(e))

    async def interactive_demo(self, context: Context) -> PromptMessage:
        """
        Create an interactive challenge with a randomly selected tool.
        """
        try:
            # Select random tool for the challenge
            selected_tool_name = random.choice(list(self.structured_tools_map.keys()))
            tool_info = self.structured_tools_map[selected_tool_name]

            # Organize tools by category for the reference section
            structured_categories = {}
            for tool_name, info in self.structured_tools_map.items():
                category = info["category"]
                if category not in structured_categories:
                    structured_categories[category] = []
                structured_categories[category].append(tool_name)

            # Prepare featured tool info
            featured_tool = {
                "name": selected_tool_name,
                "category": tool_info["category"],
                "description": tool_info["description"],
                "example_params": tool_info["example_params"],
                "structured_response_example": tool_info["structured_response_example"],
            }

            # Prepare template context
            template_context = {
                "request_id": context.request_id,
                "current_time": datetime.now(timezone.utc).strftime(
                    "%Y-%m-%d %H:%M:%S UTC"
                ),
                "featured_tool": featured_tool,
                "structured_categories": structured_categories,
                "tool_optimization": self.multi_service_optimization,
            }

            # Render with Jinja2
            if JINJA2_AVAILABLE and self.jinja_env:
                template = self.jinja_env.get_template("interactive_demo.txt")
                content = template.render(**template_context)
                logger.info(
                    f"✅ Rendered interactive demo featuring: {selected_tool_name}"
                )
            else:
                content = self._render_fallback_interactive(template_context)

            return PromptMessage(
                role="user", content=TextContent(type="text", text=content)
            )

        except Exception as e:
            logger.error(f"Error in interactive demo prompt: {e}")
            return self._create_error_prompt(str(e))

    async def benefits_overview(self, context: Context) -> PromptMessage:
        """
        Comprehensive overview of structured response benefits and implementation.
        """
        try:
            # Calculate coverage statistics
            total_structured = len(self.structured_tools_map)
            categories = {}
            for tool_info in self.structured_tools_map.values():
                category = tool_info["category"]
                categories[category] = categories.get(category, 0) + 1

            coverage_stats = {
                "total_tools": 150,  # Approximate total tools in server
                "structured_tools": total_structured,
                "coverage_percentage": round((total_structured / 150) * 100, 1),
                "categories": categories,
            }

            # Response schema descriptions
            response_schemas = {
                "GmailOperationResponse": {
                    "description": "For Gmail operations (send, draft, search, etc.)",
                    "fields": [
                        "success",
                        "userEmail",
                        "messageId",
                        "labelId",
                        "message",
                        "error",
                    ],
                },
                "DriveOperationResponse": {
                    "description": "For Google Drive file operations",
                    "fields": [
                        "success",
                        "userEmail",
                        "fileId",
                        "fileName",
                        "message",
                        "error",
                    ],
                },
                "CalendarOperationResponse": {
                    "description": "For Google Calendar event operations",
                    "fields": [
                        "success",
                        "userEmail",
                        "eventId",
                        "calendarId",
                        "message",
                        "error",
                    ],
                },
                "FormOperationResponse": {
                    "description": "For Google Forms operations",
                    "fields": [
                        "success",
                        "userEmail",
                        "formId",
                        "responseId",
                        "message",
                        "error",
                    ],
                },
            }

            # Prepare template context
            template_context = {
                "request_id": context.request_id,
                "current_time": datetime.now(timezone.utc).strftime(
                    "%Y-%m-%d %H:%M:%S UTC"
                ),
                "coverage_stats": coverage_stats,
                "response_schemas": response_schemas,
                "tool_optimization": self.multi_service_optimization,
            }

            # Render with Jinja2
            if JINJA2_AVAILABLE and self.jinja_env:
                template = self.jinja_env.get_template("structured_benefits.txt")
                content = template.render(**template_context)
                logger.info("✅ Rendered benefits overview")
            else:
                content = self._render_fallback_benefits(template_context)

            return PromptMessage(
                role="user", content=TextContent(type="text", text=content)
            )

        except Exception as e:
            logger.error(f"Error in benefits overview prompt: {e}")
            return self._create_error_prompt(str(e))

    def _render_fallback_showcase(self, context: Dict) -> str:
        """Fallback rendering for tool showcase."""
        return f"""# 🛠️ Tool Showcase: {context['tool_name']}
*Request ID: {context['request_id']}*

**Category:** {context['tool_info']['category']}
**Description:** {context['tool_info']['description']}

**Original Response:**
{context['original_response']}

**Structured Response:**
{json.dumps(context['structured_response'], indent=2)}

*Fallback template - install Jinja2 for better formatting*"""

    def _render_fallback_comparison(self, context: Dict) -> str:
        """Fallback rendering for comparison demo."""
        tools = context["tools_comparison"]
        content = (
            f"# 🔄 Response Comparison Demo\n*Request ID: {context['request_id']}*\n\n"
        )

        for i, (tool_name, tool_info) in enumerate(tools.items(), 1):
            content += f"## {i}. {tool_info['category']} → {tool_name}\n"
            content += f"{tool_info['description']}\n\n"
            content += f"**Original:** {tool_info['original_response_example']}\n"
            content += f"**Structured:** {json.dumps(tool_info['structured_response_example'], indent=2)}\n\n"

        return content

    def _render_fallback_interactive(self, context: Dict) -> str:
        """Fallback rendering for interactive demo."""
        tool = context["featured_tool"]
        return f"""# 🎮 Interactive Demo
*Request ID: {context['request_id']}*

**Featured Tool:** {tool['category']} → {tool['name']}
**Description:** {tool['description']}

**Try This:**
```xml
<mcp_tool_call>
  <tool>{tool['name']}_structured</tool>
  <params>
    {json.dumps(tool['example_params'], indent=4)}
  </params>
</mcp_tool_call>
```

*Fallback template - install Jinja2 for full interactive experience*"""

    def _render_fallback_benefits(self, context: Dict) -> str:
        """Fallback rendering for benefits overview."""
        stats = context["coverage_stats"]
        return f"""# ✨ Structured Response Benefits
*Request ID: {context['request_id']}*

**Coverage:** {stats['structured_tools']} structured tools ({stats['coverage_percentage']}% coverage)

**Key Benefits:**
- Consistent JSON schema across all tools
- Automatic ID extraction and type safety
- Clear success/error handling
- Integration-ready responses

*Fallback template - install Jinja2 for detailed overview*"""

    def _create_error_prompt(self, error: str) -> PromptMessage:
        """Create error prompt."""
        return PromptMessage(
            role="user",
            content=TextContent(
                type="text",
                text=f"""# ⚠️ Structured Response Demo Error
*Error: {error}*

The structured response demonstration encountered an issue. Please try again or check the logs for more details.

**Available Demo Types:**
- Tool Showcase: Random tool demonstration
- Comparison Demo: Side-by-side format comparison
- Interactive Demo: Challenge-based exploration
- Benefits Overview: Comprehensive system explanation""",
            ),
        )


# Global instance
_structured_demo_prompts = None


def get_structured_demo_prompts() -> StructuredResponseDemoPrompts:
    """Get the global structured demo prompts instance."""
    global _structured_demo_prompts
    if _structured_demo_prompts is None:
        _structured_demo_prompts = StructuredResponseDemoPrompts()
    return _structured_demo_prompts


# Setup function for server.py integration
def setup_structured_response_demo_prompts(mcp: FastMCP):
    """
    Setup structured response demonstration prompts.

    This function registers interactive prompts that showcase the structured
    response middleware capabilities with real tool examples and comparisons.
    """
    demo_prompts = get_structured_demo_prompts()

    @mcp.prompt(
        name="structured_tool_showcase",
        description="Showcase a specific tool with structured response example (random if tool not specified)",
        tags={"structured", "demo", "tools", "showcase"},
        meta={
            "version": "1.0",
            "author": "FastMCP2-StructuredResponse",
            "category": "demonstration",
            "interactive": True,
        },
    )
    async def structured_tool_showcase(
        context: Context, tool_name: Optional[str] = None
    ) -> PromptMessage:
        """Demo a specific tool with structured response comparison."""
        return await demo_prompts.tool_showcase(context, tool_name)

    @mcp.prompt(
        name="structured_response_comparison",
        description="Compare multiple tools showing original vs structured response formats",
        tags={"structured", "demo", "comparison", "before-after"},
        meta={
            "version": "1.0",
            "author": "FastMCP2-StructuredResponse",
            "category": "demonstration",
        },
    )
    async def structured_response_comparison(
        context: Context, num_tools: int = 3
    ) -> PromptMessage:
        """Side-by-side comparison of original vs structured responses."""
        return await demo_prompts.comparison_demo(context, num_tools)

    @mcp.prompt(
        name="structured_interactive_demo",
        description="Interactive challenge featuring a random tool with structured responses",
        tags={"structured", "demo", "interactive", "challenge", "gamified"},
        meta={
            "version": "1.0",
            "author": "FastMCP2-StructuredResponse",
            "category": "demonstration",
            "interactive": True,
            "gamified": True,
        },
    )
    async def structured_interactive_demo(context: Context) -> PromptMessage:
        """Interactive challenge with random tool and difficulty levels."""
        return await demo_prompts.interactive_demo(context)

    @mcp.prompt(
        name="structured_response_benefits",
        description="Comprehensive overview of structured response system benefits and implementation",
        tags={"structured", "demo", "documentation", "benefits", "overview"},
        meta={
            "version": "1.0",
            "author": "FastMCP2-StructuredResponse",
            "category": "documentation",
            "comprehensive": True,
        },
    )
    async def structured_response_benefits(context: Context) -> PromptMessage:
        """Complete guide to structured response system benefits."""
        return await demo_prompts.benefits_overview(context)

    logger.info("✅ Structured Response Demo prompts registered successfully")
    logger.info("   • structured_tool_showcase: Random/specific tool demonstration")
    logger.info("   • structured_response_comparison: Before/after format comparison")
    logger.info("   • structured_interactive_demo: Gamified challenge experience")
    logger.info("   • structured_response_benefits: Comprehensive system overview")

    return demo_prompts


# Export for server.py
__all__ = ["setup_structured_response_demo_prompts", "get_structured_demo_prompts"]
