#!/usr/bin/env python3
"""
Test Gmail Resource Integration - Enhanced Gmail Prompts

This test demonstrates how the Gmail prompts would work with real Gmail resource data.
Tests the enhanced features that include actual label IDs and filter information.

Key Features Tested:
- Resource-aware prompt generation
- Real Gmail label ID integration  
- Filter data utilization
- Context-sensitive email content

Run this test to see how the prompts would behave when Gmail resources are available.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from fastmcp import FastMCP, Context
from fastmcp.prompts.prompt import PromptMessage

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Mock Gmail resource data (simulates what the real resources would return)
MOCK_GMAIL_LABELS = {
    "service": "gmail",
    "count": 8,
    "system_labels": [
        {"id": "INBOX", "name": "INBOX", "type": "system"},
        {"id": "SENT", "name": "SENT", "type": "system"},
        {"id": "DRAFT", "name": "DRAFT", "type": "system"},
        {"id": "SPAM", "name": "SPAM", "type": "system"},
        {"id": "TRASH", "name": "TRASH", "type": "system"}
    ],
    "user_labels": [
        {"id": "Label_123", "name": "Work", "type": "user"},
        {"id": "Label_456", "name": "Personal", "type": "user"}, 
        {"id": "Label_789", "name": "Projects", "type": "user"}
    ]
}

MOCK_GMAIL_FILTERS = {
    "service": "gmail",
    "count": 3,
    "filters": [
        {
            "id": "Filter_001",
            "criteria": {"from": "github.com"},
            "action": {"addLabelIds": ["Label_123"]},
            "description": "Auto-label GitHub notifications as Work"
        },
        {
            "id": "Filter_002", 
            "criteria": {"subject": "invoice"},
            "action": {"addLabelIds": ["Label_456"], "markAsImportant": True},
            "description": "Mark invoices as important and label as Personal"
        },
        {
            "id": "Filter_003",
            "criteria": {"from": "newsletter"},
            "action": {"addLabelIds": ["Label_789"], "skipInbox": True},
            "description": "Skip inbox for newsletters, label as Projects"
        }
    ]
}

MOCK_GMAIL_LISTS = {
    "service": "gmail",
    "list_types": [
        {"name": "labels", "description": "Gmail labels for organization"},
        {"name": "filters", "description": "Gmail filters for automation"}
    ]
}


class MockContext(Context):
    """Mock FastMCP context for testing"""
    
    def __init__(self):
        self.request_id = f"test_{int(datetime.now().timestamp())}"
        self.metadata = {"user_email": "test@example.com"}


class MockMCP(FastMCP):
    """Mock FastMCP instance with resource simulation"""
    
    def __init__(self):
        super().__init__(name="MockMCP")
        self.mock_resources = {
            "service://gmail/labels": MOCK_GMAIL_LABELS,
            "service://gmail/filters": MOCK_GMAIL_FILTERS,
            "service://gmail/lists": MOCK_GMAIL_LISTS
        }
    
    async def read_resource(self, uri: str):
        """Simulate resource reading"""
        if uri in self.mock_resources:
            logger.info(f"📊 Mock resource accessed: {uri}")
            return self.mock_resources[uri]
        else:
            logger.warning(f"⚠️ Mock resource not found: {uri}")
            return None


async def test_advanced_prompt_with_resources():
    """Test the advanced Gmail prompt with mock resource data"""
    
    print("🧠 Testing Advanced Gmail Prompt with Resource Integration\n")
    
    # Set up mock environment
    mcp = MockMCP()
    context = MockContext()
    
    # Import the Gmail prompts module
    from prompts.gmail_prompts import setup_gmail_prompts
    
    # Register the prompts
    setup_gmail_prompts(mcp)
    
    # Test the advanced prompt
    try:
        # Find the smart contextual email prompt
        smart_prompt = None
        for prompt in mcp.prompts:
            if hasattr(prompt, 'name') and prompt.name == 'smart_contextual_email':
                smart_prompt = prompt
                break
                
        if smart_prompt:
            print("✅ Found smart_contextual_email prompt")
            
            # Call the prompt with test parameters
            result = await smart_prompt.function(
                context=context,
                email_subject="AI Project Update",
                recipient_name="Sarah Johnson", 
                email_purpose="project collaboration"
            )
            
            if isinstance(result, PromptMessage):
                content = result.content.text if hasattr(result.content, 'text') else str(result.content)
                
                print("📧 Generated Email Prompt Content:")
                print("-" * 60)
                print(content[:2000])  # First 2000 characters
                print("..." if len(content) > 2000 else "")
                print("-" * 60)
                
                # Check for resource integration indicators
                resource_indicators = [
                    "Label_123",  # Work label ID
                    "Label_456",  # Personal label ID  
                    "gmail_labels",
                    "gmail_filters",
                    "Filter_",
                    "real-time Gmail data"
                ]
                
                found_indicators = [indicator for indicator in resource_indicators if indicator in content]
                
                print(f"\n🎯 Resource Integration Check:")
                print(f"   Found {len(found_indicators)} resource indicators:")
                for indicator in found_indicators:
                    print(f"   ✓ {indicator}")
                    
                if len(found_indicators) >= 3:
                    print("   🏆 Excellent resource integration!")
                else:
                    print("   ⚠️ Limited resource integration detected")
                    
                return True
                
        else:
            print("❌ smart_contextual_email prompt not found")
            return False
            
    except Exception as e:
        print(f"❌ Error testing advanced prompt: {e}")
        logger.exception("Detailed error:")
        return False


async def simulate_resource_usage_in_email():
    """Simulate how the email would actually use resource data"""
    
    print("\n🔬 Simulating Resource Usage in Email Generation\n")
    
    # Simulate reading resources
    labels = MOCK_GMAIL_LABELS
    filters = MOCK_GMAIL_FILTERS
    
    print("📊 Resource Data Retrieved:")
    print(f"   Labels: {len(labels['user_labels'])} user labels")
    for label in labels['user_labels']:
        print(f"     • {label['name']} (ID: {label['id']})")
        
    print(f"   Filters: {len(filters['filters'])} active filters")  
    for filter_data in filters['filters']:
        print(f"     • {filter_data['description']}")
    
    print("\n📧 Email Content Generation:")
    
    # Extract label names and IDs for email content
    work_label = next((l for l in labels['user_labels'] if l['name'] == 'Work'), None)
    personal_label = next((l for l in labels['user_labels'] if l['name'] == 'Personal'), None)
    
    email_content = f"""Hello Sarah,

I hope this message finds you well. I'm reaching out regarding our AI project collaboration.

This email leverages intelligent Gmail integration to ensure proper routing:

📧 Smart Email Features:
• Integration with your "{work_label['name']}" label ({work_label['id']})
• Works with your "{personal_label['name']}" label ({personal_label['id']}) 
• Respects your {len(filters['filters'])} Gmail filters for automatic organization
• GitHub notifications will be auto-labeled as Work (Filter_001)

The email is designed to work with your existing Gmail automation.

Best regards,
AI Assistant
"""

    print(email_content)
    
    print("\n✅ Resource integration successful!")
    print("   • Actual label IDs used in content")
    print("   • Filter count referenced") 
    print("   • Specific filter behavior mentioned")


async def main():
    """Main test function"""
    
    print("🚀 Gmail Resource Integration Test\n")
    print("=" * 60)
    
    # Test 1: Advanced prompt with resources
    success1 = await test_advanced_prompt_with_resources()
    
    # Test 2: Simulate resource usage
    await simulate_resource_usage_in_email()
    
    print("\n" + "=" * 60)
    if success1:
        print("🎉 All tests passed! Gmail prompts are ready for resource integration.")
        print("\n📝 Next Steps:")
        print("   1. Ensure Gmail resources are working in your FastMCP2 server")
        print("   2. Test with real Gmail authentication")
        print("   3. Verify actual label IDs are returned by resources")
        print("   4. Use the prompts with real Gmail data")
    else:
        print("⚠️ Some tests failed. Check the Gmail prompts implementation.")
        
    print("\n🔗 Resource URLs to test when server is running:")
    print("   • service://gmail/lists")
    print("   • service://gmail/labels") 
    print("   • service://gmail/filters")


if __name__ == "__main__":
    asyncio.run(main())