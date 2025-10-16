"""
Test sampling tools using standardized client testing framework.

This test suite validates the 4 enhanced sampling demo tools:
1. intelligent_email_composer - Email composition with macro suggestions
2. smart_workflow_assistant - Workflow suggestions with historical patterns
3. template_rendering_demo - Template rendering demonstrations
4. resource_discovery_assistant - Resource discovery and usage examples

Tests implement proper sampling handler as per FastMCP client2 documentation.
"""

import pytest
import pytest_asyncio
import json
from typing import List, Optional
from dataclasses import dataclass

# Import standardized test framework components
from .base_test_config import TEST_EMAIL, create_test_client
from .test_helpers import ToolTestRunner, TestResponseValidator

# Import FastMCP client sampling types
from fastmcp.client.sampling import (
    SamplingMessage,
    SamplingParams,
    RequestContext,
)


# ============================================================================
# SAMPLING HANDLER IMPLEMENTATION
# ============================================================================

@dataclass
class MockSamplingResponse:
    """Mock response that simulates LLM sampling output."""
    text: str


class SamplingHandler:
    """
    Sample implementation of a sampling handler for testing.
    
    This handler simulates LLM responses based on the sampling request,
    providing contextually appropriate responses for each tool test case.
    """
    
    def __init__(self, enable_debug: bool = False):
        self.enable_debug = enable_debug
        self.call_count = 0
        self.last_request = None
        
    async def handle_sampling(
        self,
        messages: List[SamplingMessage],
        params: SamplingParams,
        context: RequestContext
    ) -> str:
        """
        Handle sampling requests from the server.
        
        Args:
            messages: List of sampling messages
            params: Sampling parameters including temperature, max_tokens, etc.
            context: Request context with request ID
            
        Returns:
            Generated text response simulating LLM output
        """
        self.call_count += 1
        self.last_request = {
            "messages": messages,
            "params": params,
            "context": context
        }
        
        # Extract the conversation content
        conversation = []
        for message in messages:
            content = message.content.text if hasattr(message.content, 'text') else str(message.content)
            conversation.append(f"{message.role}: {content}")
        
        conversation_text = "\n".join(conversation)
        
        if self.enable_debug:
            print(f"\n{'='*80}")
            print(f"🎯 SAMPLING REQUEST #{self.call_count}")
            print(f"{'='*80}")
            print(f"\n📨 Messages Received ({len(messages)} message(s)):")
            for i, msg in enumerate(messages, 1):
                content = msg.content.text if hasattr(msg.content, 'text') else str(msg.content)
                print(f"\n  Message {i}:")
                print(f"    Role: {msg.role}")
                print(f"    Content: {content[:200]}{'...' if len(content) > 200 else ''}")
            
            print(f"\n⚙️  Sampling Parameters:")
            print(f"    Request ID: {context.request_id}")
            print(f"    Temperature: {params.temperature}")
            print(f"    Max Tokens: {params.maxTokens}")
            print(f"    Stop Sequences: {params.stopSequences if hasattr(params, 'stopSequences') else 'None'}")
            
            if params.systemPrompt:
                print(f"\n📋 System Prompt:")
                print(f"    {params.systemPrompt[:300]}...")
            
            if hasattr(params, 'modelPreferences') and params.modelPreferences:
                print(f"\n🤖 Model Preferences: {params.modelPreferences}")
        
        # Generate contextually appropriate responses based on the request
        response_text = self._generate_contextual_response(conversation_text, params)
        
        if self.enable_debug:
            print(f"\n💬 Generated Response:")
            print(f"    {response_text[:300]}...")
            print(f"\n{'='*80}\n")
        
        return response_text
    
    def _generate_contextual_response(self, conversation: str, params: SamplingParams) -> str:
        """Generate contextually appropriate response based on conversation content."""
        
        conversation_lower = conversation.lower()
        
        # Email composition responses
        if "compose" in conversation_lower and "email" in conversation_lower:
            return """Here's a professional email composition using the beautiful_email macro:

{{ render_beautiful_email(
    title="Professional Update",
    content_sections=[{
        'type': 'text',
        'content': 'Dear recipient, I wanted to reach out regarding our recent discussion...'
    }],
    user_name="{{user://current/email.name}}",
    user_email="{{user://current/email.email}}",
    signature_style="professional"
) }}

This email uses your actual user profile data from the resource system and applies professional styling with gradient backgrounds. You can also add Gmail label chips using:

{{ render_gmail_labels_chips(service://gmail/labels, 'Label context') }}
"""
        
        # Workflow assistance responses
        elif "workflow" in conversation_lower or "task" in conversation_lower:
            return """Based on your workspace context, here's a recommended workflow:

**Step-by-Step Workflow:**

1. **Data Collection**
   - Use `service://gmail/labels` to understand email organization
   - Use `recent://drive/7` to access files from the last week
   - Use `tools://enhanced/list` to see available automation tools

2. **Processing**
   - Leverage the search_drive_files tool with mime_type filters
   - Use Gmail filters for automated email organization
   - Apply Calendar event creation for scheduling

3. **Integration**
   - Combine Drive file operations with email notifications
   - Use template macros for professional formatting
   - Track patterns with Qdrant historical analysis

**Recommended Tools:**
- search_drive_files (for file discovery)
- create_gmail_filter (for automation)
- create_event (for scheduling)

This workflow leverages your current workspace setup and available resources.
"""
        
        # Template rendering responses
        elif "template" in conversation_lower or "rendering" in conversation_lower:
            return """**Template Rendering Demonstration**

Available template macros with examples:

1. **Beautiful Email Template:**
```jinja2
{{ render_beautiful_email(
    title="Status Update",
    content_sections=[{'type': 'text', 'content': 'Content here'}],
    user_name="{{user://current/email.name}}",
    signature_style="professional"
) }}
```

2. **Gmail Labels Visualization:**
```jinja2
{{ render_gmail_labels_chips(
    service://gmail/labels,
    'Organization Summary'
) }}
```

3. **Calendar Dashboard:**
```jinja2
{{ render_calendar_dashboard(
    service://calendar/calendars,
    service://calendar/events
) }}
```

**Usage Tips:**
- Use {{ }} for variable interpolation
- Access resources via URI patterns like service://gmail/labels
- Combine macros for complex templates
- All macros handle real user data from the resource system
"""
        
        # Resource discovery responses
        elif "resource" in conversation_lower or "discover" in conversation_lower:
            return """**Resource Discovery Guide**

**Available Resource Patterns:**

1. **User Context Resources:**
   - `user://current/email` - Current user email and name
   - `user://current/profile` - Complete user profile

2. **Service Resources:**
   - `service://gmail/labels` - Gmail labels and organization
   - `service://drive/items` - Drive files and folders
   - `service://calendar/events` - Calendar events
   - `service://gmail/filters` - Gmail filter rules

3. **Recent Activity Resources:**
   - `recent://drive/7` - Files from last 7 days
   - `recent://all` - Recent items across all services

4. **Template Resources:**
   - `template://macros` - Available Jinja2 macros
   - `template://user_email` - Simple email template

5. **Analytics Resources:**
   - `qdrant://search/{query}` - Vector database search
   - `qdrant://collection/mcp_tool_responses/info` - Collection info

**Integration Example:**
```python
# Send email with dynamic labels
send_gmail_message(
    html_body="{{ render_gmail_labels_chips(service://gmail/labels) }}"
)
```

These resources provide dynamic access to your workspace data and enable sophisticated integrations.
"""
        
        # Default response for other cases
        else:
            return f"""Based on your request, I've analyzed the available context and resources.

**Key Insights:**
- User profile and authentication status: Available via user://current/email
- Workspace activity: Accessible via recent://all
- Available tools: Listed in tools://enhanced/list
- Historical patterns: Searchable via Qdrant

**Recommendations:**
1. Leverage resource URIs for dynamic data access
2. Use template macros for professional formatting
3. Apply historical patterns for personalized workflows
4. Integrate multiple services for comprehensive solutions

Temperature setting ({params.temperature}) indicates a {'creative' if params.temperature > 0.5 else 'precise'} response style.
System prompt context: {params.systemPrompt[:100] if params.systemPrompt else 'Standard'}...
"""


# ============================================================================
# PYTEST FIXTURES
# ============================================================================

@pytest_asyncio.fixture
async def client_with_sampling():
    """Create test client with sampling handler."""
    from .base_test_config import SERVER_URL
    from ..test_auth_utils import get_client_auth_config
    
    handler = SamplingHandler(enable_debug=True)
    auth_config = get_client_auth_config(TEST_EMAIL)
    
    # Create client with sampling handler as per FastMCP client2 docs
    from fastmcp import Client
    client = Client(
        SERVER_URL,
        auth=auth_config,
        sampling_handler=handler.handle_sampling,
        timeout=30.0
    )
    
    # Initialize the client connection
    async with client:
        # Attach handler for test access
        client._test_sampling_handler = handler
        
        yield client


# ============================================================================
# TEST CLASS
# ============================================================================

@pytest.mark.service("sampling")
class TestSamplingTools:
    """Tests for enhanced sampling demo tools."""
    
    # ========================================================================
    # TOOL AVAILABILITY TESTS
    # ========================================================================
    
    @pytest.mark.asyncio
    async def test_sampling_tools_available(self, client_with_sampling):
        """Test that all 4 sampling demo tools are available."""
        expected_tools = [
            "intelligent_email_composer",
            "smart_workflow_assistant",
            "template_rendering_demo",
            "resource_discovery_assistant"
        ]
        
        tools = await client_with_sampling.list_tools()
        tool_names = [tool.name for tool in tools]
        
        for tool_name in expected_tools:
            assert tool_name in tool_names, f"Sampling tool {tool_name} should be available"
        
        print(f"✅ All {len(expected_tools)} sampling demo tools are available")
    
    # ========================================================================
    # INTELLIGENT EMAIL COMPOSER TESTS
    # ========================================================================
    
    @pytest.mark.asyncio
    async def test_intelligent_email_composer_basic(self, client_with_sampling):
        """Test intelligent_email_composer with basic parameters."""
        result = await client_with_sampling.call_tool(
            "intelligent_email_composer",
            {
                "recipient": "test@example.com",
                "topic": "Weekly Status Update",
                "style": "professional",
                "user_google_email": TEST_EMAIL
            }
        )
        
        assert result is not None, "Should receive response from email composer"
        
        # Extract content
        content = result.content[0].text if result.content else str(result)
        content_lower = content.lower()
        
        # Validate response structure
        assert "success" in content_lower or "composed" in content_lower or "email" in content_lower, \
            "Response should indicate email composition"
        
        # Verify sampling was called
        handler = client_with_sampling._test_sampling_handler
        assert handler.call_count > 0, "Sampling handler should have been called"
        
        print(f"✅ Email composer called sampling {handler.call_count} time(s)")
    
    @pytest.mark.asyncio
    async def test_intelligent_email_composer_styles(self, client_with_sampling):
        """Test email composer with different styles."""
        styles = ["professional", "friendly", "formal"]
        
        for style in styles:
            result = await client_with_sampling.call_tool(
                "intelligent_email_composer",
                {
                    "recipient": f"test_{style}@example.com",
                    "topic": f"Test {style} email",
                    "style": style,
                    "user_google_email": TEST_EMAIL
                }
            )
            
            assert result is not None, f"Should handle {style} style"
            content = result.content[0].text if result.content else str(result)
            assert "success" in content.lower() or "email" in content.lower(), \
                f"Should compose email with {style} style"
        
        print(f"✅ Tested {len(styles)} different email styles")
    
    # ========================================================================
    # SMART WORKFLOW ASSISTANT TESTS
    # ========================================================================
    
    @pytest.mark.asyncio
    async def test_smart_workflow_assistant_basic(self, client_with_sampling):
        """Test smart_workflow_assistant with basic task."""
        result = await client_with_sampling.call_tool(
            "smart_workflow_assistant",
            {
                "task_description": "Organize my Drive files by project",
                "include_history": True,
                "user_google_email": TEST_EMAIL
            }
        )
        
        assert result is not None, "Should receive workflow suggestions"
        
        content = result.content[0].text if result.content else str(result)
        content_lower = content.lower()
        
        # Validate workflow suggestions
        assert any(keyword in content_lower for keyword in ["workflow", "step", "tool", "recommend"]), \
            "Response should contain workflow suggestions"
        
        # Verify sampling was called
        handler = client_with_sampling._test_sampling_handler
        assert handler.call_count > 0, "Sampling handler should provide workflow assistance"
        
        print("✅ Workflow assistant provided suggestions")
    
    @pytest.mark.asyncio
    async def test_smart_workflow_assistant_with_and_without_history(self, client_with_sampling):
        """Test workflow assistant with and without historical patterns."""
        # Test with history
        result_with_history = await client_with_sampling.call_tool(
            "smart_workflow_assistant",
            {
                "task_description": "Automate email responses",
                "include_history": True,
                "user_google_email": TEST_EMAIL
            }
        )
        
        # Test without history
        result_without_history = await client_with_sampling.call_tool(
            "smart_workflow_assistant",
            {
                "task_description": "Automate email responses",
                "include_history": False,
                "user_google_email": TEST_EMAIL
            }
        )
        
        assert result_with_history is not None, "Should work with history enabled"
        assert result_without_history is not None, "Should work with history disabled"
        
        print("✅ Workflow assistant works with and without historical context")
    
    # ========================================================================
    # TEMPLATE RENDERING DEMO TESTS
    # ========================================================================
    
    @pytest.mark.asyncio
    async def test_template_rendering_demo_email(self, client_with_sampling):
        """Test template rendering demo with email templates."""
        result = await client_with_sampling.call_tool(
            "template_rendering_demo",
            {
                "template_type": "email",
                "render_examples": False,
                "user_google_email": TEST_EMAIL
            }
        )
        
        assert result is not None, "Should provide template examples"
        
        content = result.content[0].text if result.content else str(result)
        content_lower = content.lower()
        
        # Validate template information
        assert any(keyword in content_lower for keyword in ["template", "macro", "email", "example"]), \
            "Response should contain template information"
        
        print("✅ Template demo provided email template examples")
    
    @pytest.mark.asyncio
    async def test_template_rendering_demo_document(self, client_with_sampling):
        """Test template rendering demo with document templates."""
        result = await client_with_sampling.call_tool(
            "template_rendering_demo",
            {
                "template_type": "document",
                "render_examples": True,
                "user_google_email": TEST_EMAIL
            }
        )
        
        assert result is not None, "Should provide document template examples"
        
        content = result.content[0].text if result.content else str(result)
        
        # Should contain document-related template info
        assert "document" in content.lower() or "template" in content.lower(), \
            "Response should contain document template information"
        
        print("✅ Template demo provided document template examples")
    
    # ========================================================================
    # RESOURCE DISCOVERY ASSISTANT TESTS
    # ========================================================================
    
    @pytest.mark.asyncio
    async def test_resource_discovery_assistant_basic(self, client_with_sampling):
        """Test resource discovery assistant with basic use case."""
        result = await client_with_sampling.call_tool(
            "resource_discovery_assistant",
            {
                "use_case": "Send automated weekly reports",
                "user_google_email": TEST_EMAIL
            }
        )
        
        assert result is not None, "Should provide resource discovery information"
        
        content = result.content[0].text if result.content else str(result)
        content_lower = content.lower()
        
        # Validate resource discovery
        assert any(keyword in content_lower for keyword in ["resource", "uri", "service://", "user://"]), \
            "Response should contain resource URIs and patterns"
        
        # Verify sampling was called
        handler = client_with_sampling._test_sampling_handler
        assert handler.call_count > 0, "Sampling handler should provide resource guidance"
        
        print("✅ Resource discovery provided guidance on available resources")
    
    @pytest.mark.asyncio
    async def test_resource_discovery_various_use_cases(self, client_with_sampling):
        """Test resource discovery with various use cases."""
        use_cases = [
            "Email automation workflows",
            "Drive file organization",
            "Calendar event management",
            "Cross-service data integration"
        ]
        
        for use_case in use_cases:
            result = await client_with_sampling.call_tool(
                "resource_discovery_assistant",
                {
                    "use_case": use_case,
                    "user_google_email": TEST_EMAIL
                }
            )
            
            assert result is not None, f"Should handle use case: {use_case}"
            content = result.content[0].text if result.content else str(result)
            assert "resource" in content.lower() or "service://" in content.lower(), \
                f"Should provide resource guidance for: {use_case}"
        
        print(f"✅ Tested {len(use_cases)} different resource discovery use cases")
    
    # ========================================================================
    # SAMPLING HANDLER BEHAVIOR TESTS
    # ========================================================================
    
    @pytest.mark.asyncio
    async def test_sampling_handler_receives_parameters(self, client_with_sampling):
        """Test that sampling handler receives proper parameters."""
        # Call a sampling tool
        await client_with_sampling.call_tool(
            "intelligent_email_composer",
            {
                "recipient": "test@example.com",
                "topic": "Parameter Test",
                "style": "professional",
                "user_google_email": TEST_EMAIL
            }
        )
        
        # Check handler received parameters
        handler = client_with_sampling._test_sampling_handler
        assert handler.last_request is not None, "Handler should have received request"
        
        last_params = handler.last_request["params"]
        assert last_params.maxTokens > 0, "Should receive max_tokens parameter"
        assert last_params.temperature is not None, "Should receive temperature parameter"
        
        print(f"✅ Sampling handler received proper parameters:")
        print(f"   - max_tokens: {last_params.maxTokens}")
        print(f"   - temperature: {last_params.temperature}")
        print(f"   - system_prompt: {'Present' if last_params.systemPrompt else 'None'}")
    
    @pytest.mark.asyncio
    async def test_sampling_handler_call_count(self, client_with_sampling):
        """Test that sampling handler is called for each tool invocation."""
        handler = client_with_sampling._test_sampling_handler
        initial_count = handler.call_count
        
        # Call multiple sampling tools
        await client_with_sampling.call_tool(
            "intelligent_email_composer",
            {
                "recipient": "test1@example.com",
                "topic": "Test 1",
                "style": "professional",
                "user_google_email": TEST_EMAIL
            }
        )
        
        await client_with_sampling.call_tool(
            "smart_workflow_assistant",
            {
                "task_description": "Test workflow",
                "include_history": False,
                "user_google_email": TEST_EMAIL
            }
        )
        
        final_count = handler.call_count
        calls_made = final_count - initial_count
        
        assert calls_made >= 2, f"Should have made at least 2 sampling calls, got {calls_made}"
        print(f"✅ Sampling handler called {calls_made} times for 2 tool invocations")
    
    # ========================================================================
    # ERROR HANDLING TESTS
    # ========================================================================
    
    @pytest.mark.asyncio
    async def test_sampling_tools_without_sampling_handler(self, client):
        """Test sampling tools behavior when client lacks sampling handler."""
        # Note: Using regular client fixture without sampling handler
        
        result = await client.call_tool(
            "intelligent_email_composer",
            {
                "recipient": "test@example.com",
                "topic": "No Handler Test",
                "style": "professional",
                "user_google_email": TEST_EMAIL
            }
        )
        
        # Should still return a response (may indicate sampling not supported)
        assert result is not None, "Should handle missing sampling handler gracefully"
        
        content = result.content[0].text if result.content else str(result)
        # May contain error about sampling not supported or fallback behavior
        print(f"✅ Tool handled missing sampling handler: {content[:100]}...")
    
    @pytest.mark.asyncio
    async def test_sampling_tool_with_missing_parameters(self, client_with_sampling):
        """Test sampling tool error handling with missing parameters."""
        # Try calling tool with missing required parameters
        try:
            result = await client_with_sampling.call_tool(
                "intelligent_email_composer",
                {
                    "user_google_email": TEST_EMAIL
                    # Missing recipient and topic
                }
            )
            
            # If it doesn't raise, check for error in response
            if result:
                content = result.content[0].text if result.content else str(result)
                # Should indicate error or missing parameters
                assert any(keyword in content.lower() for keyword in ["error", "required", "missing"]), \
                    "Should indicate missing parameters"
        except Exception as e:
            # Expected - tool should validate parameters
            assert "required" in str(e).lower() or "missing" in str(e).lower(), \
                "Error should indicate missing required parameters"
            print(f"✅ Tool properly validates required parameters: {str(e)[:100]}")
    
    # ========================================================================
    # INTEGRATION TESTS
    # ========================================================================
    
    @pytest.mark.asyncio
    async def test_sampling_tool_integration_sequence(self, client_with_sampling):
        """Test a realistic sequence of sampling tool calls."""
        # 1. Discover resources for a use case
        discovery_result = await client_with_sampling.call_tool(
            "resource_discovery_assistant",
            {
                "use_case": "Automated weekly team updates",
                "user_google_email": TEST_EMAIL
            }
        )
        assert discovery_result is not None, "Resource discovery should succeed"
        
        # 2. Get workflow suggestions based on the use case
        workflow_result = await client_with_sampling.call_tool(
            "smart_workflow_assistant",
            {
                "task_description": "Create automated weekly team update workflow",
                "include_history": True,
                "user_google_email": TEST_EMAIL
            }
        )
        assert workflow_result is not None, "Workflow suggestions should succeed"
        
        # 3. Get template examples for email formatting
        template_result = await client_with_sampling.call_tool(
            "template_rendering_demo",
            {
                "template_type": "email",
                "render_examples": True,
                "user_google_email": TEST_EMAIL
            }
        )
        assert template_result is not None, "Template demo should succeed"
        
        # 4. Compose the actual email
        compose_result = await client_with_sampling.call_tool(
            "intelligent_email_composer",
            {
                "recipient": "team@example.com",
                "topic": "Weekly Team Update",
                "style": "professional",
                "user_google_email": TEST_EMAIL
            }
        )
        assert compose_result is not None, "Email composition should succeed"
        
        # Verify all steps completed
        handler = client_with_sampling._test_sampling_handler
        print(f"✅ Integration sequence completed with {handler.call_count} sampling calls")
    
    @pytest.mark.asyncio
    async def test_sampling_performance(self, client_with_sampling):
        """Test sampling handler performance with concurrent calls."""
        import asyncio
        
        # Create multiple concurrent sampling tool calls
        tasks = [
            client_with_sampling.call_tool(
                "intelligent_email_composer",
                {
                    "recipient": f"test{i}@example.com",
                    "topic": f"Performance Test {i}",
                    "style": "professional",
                    "user_google_email": TEST_EMAIL
                }
            )
            for i in range(3)
        ]
        
        # Execute concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Verify all succeeded or handled gracefully
        successful = sum(1 for r in results if not isinstance(r, Exception))
        assert successful >= len(tasks) // 2, \
            f"At least half of concurrent calls should succeed, got {successful}/{len(tasks)}"
        
        handler = client_with_sampling._test_sampling_handler
        print(f"✅ Handled {len(tasks)} concurrent sampling requests, {successful} successful")


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def validate_sampling_response_structure(content: str) -> bool:
    """Validate that sampling response has expected structure."""
    content_lower = content.lower()
    
    # Check for key indicators of valid sampling response
    indicators = [
        "success" in content_lower,
        any(keyword in content_lower for keyword in ["email", "workflow", "template", "resource"]),
        len(content) > 50,  # Should have meaningful content
    ]
    
    return sum(indicators) >= 2  # At least 2 indicators should be present


if __name__ == "__main__":
    # Run tests with verbose output
    pytest.main([__file__, "-v", "-s", "--tb=short"])