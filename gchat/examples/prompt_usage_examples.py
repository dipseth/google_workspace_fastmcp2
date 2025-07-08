"""
Google Chat App Prompts Usage Examples

This file demonstrates how to use the new FastMCP prompts for Google Chat app development.
These prompts serve as reusable templates that help LLMs generate structured responses.
"""

def demonstrate_prompt_usage():
    """
    Examples showing how the new FastMCP prompts can be used.
    
    Note: These are conceptual examples showing the prompt patterns.
    In actual usage, the MCP client would call these prompts.
    """
    
    print("=== Google Chat App FastMCP Prompts Usage Examples ===\n")
    
    # Example 1: Complex Card Creation
    print("1. COMPLEX CARD CREATION")
    print("   Prompt Name: google_chat_complex_card")
    print("   Parameters:")
    print("   - card_type: 'approval_workflow'")  
    print("   - integration_service: 'drive'")
    print("   - widget_types: 'buttons,forms,text'")
    print("   → Returns: Comprehensive guidance for creating sophisticated multi-section cards\n")
    
    # Example 2: App Setup and Development
    print("2. APP SETUP & DEVELOPMENT")
    print("   Prompt Name: google_chat_app_setup")
    print("   Parameters:")
    print("   - deployment_target: 'cloud_run'")
    print("   - auth_type: 'service_account'")
    print("   - integration_level: 'advanced'")
    print("   → Returns: Step-by-step setup and development guidance\n")
    
    # Example 3: Cross-Service Integration
    print("3. CROSS-SERVICE INTEGRATION")
    print("   Prompt Name: google_chat_integration")
    print("   Parameters:")
    print("   - primary_service: 'calendar'")
    print("   - workflow_type: 'collaborative'")
    print("   - automation_level: 'intermediate'")
    print("   → Returns: Integration patterns and workflow guidance\n")
    
    # Example 4: Deployment and Production
    print("4. DEPLOYMENT & PRODUCTION")
    print("   Prompt Name: google_chat_deployment")
    print("   Parameters:")
    print("   - platform: 'cloud_run'")
    print("   - environment: 'production'")
    print("   - monitoring_level: 'comprehensive'")
    print("   → Returns: Production deployment and monitoring guidance\n")
    
    # Example 5: Examples and Templates
    print("5. EXAMPLES & TEMPLATES")
    print("   Prompt Name: google_chat_examples")
    print("   Parameters:")
    print("   - example_category: 'workflows'")
    print("   - complexity_level: 'advanced'")
    print("   - use_case: 'business_workflow'")
    print("   → Returns: Showcases and template examples with implementation guidance\n")

def show_prompt_benefits():
    """Show the benefits of using FastMCP prompts vs the old tool approach."""
    
    print("=== Benefits of FastMCP Prompts vs Tools ===\n")
    
    print("✅ PROMPTS (New Implementation):")
    print("   • Reusable message templates for consistent LLM responses")
    print("   • Proper FastMCP @mcp.prompt decorator usage")
    print("   • Parameterized for customization and flexibility")
    print("   • Return structured string templates for LLM processing")
    print("   • Focused on generating prompt guidance, not direct responses")
    print("   • Better separation of concerns - prompts guide, tools execute\n")
    
    print("❌ TOOLS (Old Implementation):")
    print("   • Incorrectly implemented as @mcp.tool")
    print("   • Generated static responses instead of prompt templates")
    print("   • Mixed guidance generation with tool functionality")
    print("   • Less flexible and harder to customize")
    print("   • Not following FastMCP prompt patterns\n")

def show_integration_examples():
    """Show how prompts integrate with existing MCP tools."""
    
    print("=== Integration with Existing MCP Tools ===\n")
    
    print("WORKFLOW EXAMPLE:")
    print("1. Use google_chat_complex_card prompt → Get guidance for card design")
    print("2. Use send_rich_card tool → Actually create and send the card")
    print("3. Use google_chat_integration prompt → Get integration guidance")
    print("4. Use drive/calendar/gmail tools → Implement the integrations")
    print("5. Use google_chat_deployment prompt → Get deployment guidance")
    print("6. Use deployment tools/scripts → Actually deploy the application\n")
    
    print("PROMPT → TOOL MAPPING:")
    print("• google_chat_complex_card → send_rich_card, send_interactive_card")
    print("• google_chat_app_setup → initialize_chat_app_manager, create_chat_app_manifest")
    print("• google_chat_integration → drive_tools, calendar_tools, gmail_tools")
    print("• google_chat_deployment → Cloud deployment tools")
    print("• google_chat_examples → All existing card and app tools\n")

if __name__ == "__main__":
    demonstrate_prompt_usage()
    show_prompt_benefits()
    show_integration_examples()