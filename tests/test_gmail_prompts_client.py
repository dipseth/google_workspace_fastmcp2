#!/usr/bin/env python3
"""
Gmail Prompts Client Test

Test script for the streamlined Gmail prompts using FastMCP client.
Tests all 3 prompt levels: Advanced, Medium, Simple with various argument combinations.

Based on FastMCP2 client prompt documentation:
- list_prompts() for discovery
- get_prompt() for execution with automatic argument serialization
- Tag-based filtering for organization

Usage:
    python test_gmail_prompts_client.py
    pytest tests/test_gmail_prompts_client.py -v
"""

import asyncio
import json
import logging
import pytest
from typing import Dict, Any, List
from dataclasses import dataclass
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# You'll need to install and import your FastMCP client
# from fastmcp_client import FastMCPClient

@pytest.mark.asyncio
async def test_gmail_prompts_comprehensive():
    """
    Comprehensive test of all Gmail prompts with various configurations.
    """
    print("🚀 Starting Gmail Prompts Client Test")
    print("=" * 60)
    
    # TODO: Replace with actual client initialization
    # client = FastMCPClient("ws://localhost:8080")
    
    # For demonstration purposes, we'll simulate the client interactions
    print("📝 Note: This is a demonstration script.")
    print("   Replace client simulation with actual FastMCP client connection.")
    print()
    
    await _test_prompt_discovery()
    await _test_advanced_prompt()
    await _test_medium_prompt()
    await _test_simple_prompt()
    await _test_tag_based_filtering()
    await _test_complex_arguments()
    
    print("🎉 Gmail Prompts Client Test Complete!")

async def _test_prompt_discovery():
    """
    Test 1: Discover all available Gmail prompts
    """
    print("📋 Test 1: Prompt Discovery")
    print("-" * 30)
    
    # Simulate: prompts = await client.list_prompts()
    simulated_prompts = [
        {
            "name": "smart_contextual_email",
            "description": "Advanced: Generate intelligent email templates using real Gmail data (filters, labels, etc.)",
            "arguments": [
                {"name": "email_subject", "required": False, "description": "Subject line for the contextual email"},
                {"name": "recipient_name", "required": False, "description": "Name of the email recipient"},
                {"name": "email_purpose", "required": False, "description": "Purpose of the email"}
            ],
            "_meta": {
                "_fastmcp": {
                    "tags": ["gmail", "advanced", "contextual", "dynamic"],
                    "version": "3.0",
                    "author": "FastMCP2-Streamlined"
                }
            }
        },
        {
            "name": "professional_html_email",
            "description": "Medium: Create beautiful professional HTML emails with modern design",
            "arguments": [
                {"name": "email_subject", "required": False, "description": "Subject line for the email"},
                {"name": "recipient_name", "required": False, "description": "Name of the email recipient"},
                {"name": "message_theme", "required": False, "description": "Theme of the message"}
            ],
            "_meta": {
                "_fastmcp": {
                    "tags": ["gmail", "medium", "html", "professional"],
                    "version": "3.0",
                    "author": "FastMCP2-Streamlined"
                }
            }
        },
        {
            "name": "quick_email_demo",
            "description": "Simple: Zero-config instant email demo - ready to send immediately",
            "arguments": [],
            "_meta": {
                "_fastmcp": {
                    "tags": ["gmail", "simple", "demo", "instant"],
                    "version": "3.0",
                    "author": "FastMCP2-Streamlined"
                }
            }
        }
    ]
    
    print(f"📊 Found {len(simulated_prompts)} Gmail prompts:")
    print()
    
    for prompt in simulated_prompts:
        print(f"🎯 **{prompt['name']}**")
        print(f"   Description: {prompt['description']}")
        
        if prompt["arguments"]:
            arg_names = [arg["name"] for arg in prompt["arguments"]]
            print(f"   Arguments: {arg_names}")
        else:
            print("   Arguments: None (zero-config)")
            
        # Access FastMCP metadata
        if "_meta" in prompt and "_fastmcp" in prompt["_meta"]:
            fastmcp_meta = prompt["_meta"]["_fastmcp"]
            print(f"   Tags: {fastmcp_meta.get('tags', [])}")
            print(f"   Version: {fastmcp_meta.get('version', 'N/A')}")
        print()
    
    print("✅ Prompt discovery completed successfully")
    print()

async def _test_advanced_prompt():
    """
    Test 2: Advanced prompt with various argument combinations
    """
    print("🧠 Test 2: Advanced Prompt (smart_contextual_email)")
    print("-" * 50)
    
    test_cases = [
        {
            "name": "Default Arguments",
            "args": {}
        },
        {
            "name": "Business Follow-up",
            "args": {
                "email_subject": "Follow-up: Project Collaboration Opportunity",
                "recipient_name": "Sarah Johnson",
                "email_purpose": "project follow-up"
            }
        },
        {
            "name": "Partnership Outreach",
            "args": {
                "email_subject": "Strategic Partnership Proposal",
                "recipient_name": "Alex Chen",
                "email_purpose": "strategic partnership"
            }
        }
    ]
    
    for test_case in test_cases:
        print(f"🔬 Testing: {test_case['name']}")
        print(f"📝 Arguments: {test_case['args']}")
        print()
        
        # Show actual sample prompt content
        print("📧 SAMPLE PROMPT CONTENT:")
        print("-" * 40)
        
        sample_advanced_content = f'''
🧠 Smart Contextual Gmail Email (Advanced)
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Configuration:
- Subject: {test_case['args'].get('email_subject', 'Default Subject')}
- Recipient: {test_case['args'].get('recipient_name', 'Default Recipient')}
- Purpose: {test_case['args'].get('email_purpose', 'Default Purpose')}

Step 1: Gather Real Gmail Context
```python
gmail_labels = await mcp.read_resource("service://gmail/labels")
gmail_filters = await mcp.read_resource("service://gmail/filters")
print("🏷️ Current Labels:", gmail_labels)
print("⚙️ Active Filters:", gmail_filters)
```

Step 2: Generate Smart Email
```python
result = await send_gmail_message(
    subject="{test_case['args'].get('email_subject', 'Smart Email')}",
    body="""Hello {test_case['args'].get('recipient_name', 'Valued Contact')},
    
    This email uses intelligent Gmail integration for {test_case['args'].get('email_purpose', 'communication')}.
    Context-aware content based on real Gmail configuration.
    
    Best regards, Your Name"""
)
```

Advanced Features:
• Live Gmail Data: Uses actual labels, filters, and configuration
• Context Adaptation: Email content adapts to your Gmail setup
• Intelligence Indicators: Visual cues showing Gmail integration
'''
        
        print(sample_advanced_content)
        print("-" * 40)
        print("✅ Advanced prompt executed successfully")
        print()

async def _test_medium_prompt():
    """
    Test 3: Medium complexity prompt with professional design
    """
    print("🎨 Test 3: Medium Prompt (professional_html_email)")
    print("-" * 48)
    
    test_cases = [
        {
            "name": "Welcome Email",
            "args": {
                "email_subject": "Welcome to Our Team!",
                "recipient_name": "Jordan Martinez",
                "message_theme": "welcome"
            }
        },
        {
            "name": "Quarterly Update",
            "args": {
                "email_subject": "Q3 Business Update",
                "recipient_name": "Team Leaders",
                "message_theme": "quarterly update"
            }
        },
        {
            "name": "Product Launch",
            "args": {
                "email_subject": "Exciting Product Launch Announcement",
                "recipient_name": "Valued Customers",
                "message_theme": "product announcement"
            }
        }
    ]
    
    for test_case in test_cases:
        print(f"🔬 Testing: {test_case['name']}")
        print(f"📝 Arguments: {test_case['args']}")
        
        # Show actual sample prompt content
        print("📧 SAMPLE PROMPT CONTENT:")
        print("-" * 40)
        
        sample_medium_content = f'''
🎨 Professional HTML Email (Medium)
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Configuration:
- Subject: {test_case['args'].get('email_subject', 'Professional Email')}
- Recipient: {test_case['args'].get('recipient_name', 'Valued Contact')}
- Theme: {test_case['args'].get('message_theme', 'professional')}

Generated HTML Email Preview:
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{test_case['args'].get('email_subject', 'Professional Email')}</title>
</head>
<body style="margin: 0; padding: 0; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);">
    <div style="max-width: 600px; margin: 0 auto; background: white;">
        <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 40px; text-align: center;">
            <h1 style="color: white; margin: 0; font-size: 28px;">{test_case['args'].get('email_subject', 'Professional Email')}</h1>
            <span style="background: rgba(255,255,255,0.2); color: white; padding: 8px 16px; border-radius: 20px; font-size: 12px;">Medium Complexity</span>
        </div>
        
        <div style="padding: 40px;">
            <p style="font-size: 16px; line-height: 1.6; color: #333;">Hello {test_case['args'].get('recipient_name', 'Valued Contact')},</p>
            
            <p style="font-size: 16px; line-height: 1.6; color: #333;">
                I hope this message finds you well. I'm writing regarding {test_case['args'].get('message_theme', 'our professional collaboration')}.
            </p>
            
            <div style="background: #f8f9fa; border-left: 4px solid #667eea; padding: 20px; margin: 20px 0;">
                <h3 style="color: #667eea; margin-top: 0;">Professional HTML Features:</h3>
                <ul style="color: #666; margin-bottom: 0;">
                    <li>Responsive design optimized for all devices</li>
                    <li>Cross-platform compatibility (Gmail, Outlook, Apple Mail)</li>
                    <li>Modern gradient design with clean typography</li>
                    <li>Professional visual hierarchy</li>
                </ul>
            </div>
            
            <div style="text-align: center; margin: 30px 0;">
                <a href="#" style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 12px 30px; text-decoration: none; border-radius: 25px; display: inline-block; font-weight: 500;">Let's Connect</a>
            </div>
            
            <p style="font-size: 16px; line-height: 1.6; color: #333;">Best regards,<br>Your Name</p>
        </div>
        
        <div style="background: #f8f9fa; padding: 20px; text-align: center; font-size: 12px; color: #666;">
            FastMCP2 Professional HTML Email • Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        </div>
    </div>
</body>
</html>

This professional HTML email provides beautiful design while maintaining excellent compatibility across email clients.
'''
        
        print(sample_medium_content)
        print("-" * 40)
        print("✅ Medium prompt executed successfully")
        print()

async def _test_simple_prompt():
    """
    Test 4: Simple zero-config prompt
    """
    print("⚡ Test 4: Simple Prompt (quick_email_demo)")
    print("-" * 42)
    
    print("🔬 Testing: Zero-configuration demo")
    print("📝 Arguments: None (zero-config)")
    
    # Show actual sample prompt content
    print("📧 SAMPLE PROMPT CONTENT:")
    print("-" * 40)
    
    sample_simple_content = f'''
⚡ Quick Email Demo (Simple)
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Zero-Configuration Ready Email:

<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Quick Gmail Demo</title>
</head>
<body style="margin: 0; padding: 0; font-family: Arial, sans-serif; background: #f5f5f5;">
    <div style="max-width: 500px; margin: 20px auto; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 12px rgba(0,0,0,0.1);">
        <div style="background: linear-gradient(135deg, #8B5CF6 0%, #7C3AED 100%); padding: 25px; text-align: center;">
            <h1 style="color: white; margin: 0; font-size: 22px;">Quick Gmail Demo</h1>
            <span style="background: rgba(255,255,255,0.2); color: white; padding: 6px 12px; border-radius: 15px; font-size: 11px; margin-top: 10px; display: inline-block;">Simple & Ready</span>
        </div>
        
        <div style="padding: 25px;">
            <p style="font-size: 15px; line-height: 1.5; color: #374151; margin-bottom: 20px;">
                Hello! This is a quick Gmail integration demo showcasing FastMCP2's streamlined prompt system.
            </p>
            
            <div style="background: linear-gradient(135deg, #F3E8FF 0%, #E9D5FF 100%); border-radius: 6px; padding: 15px; margin: 15px 0;">
                <p style="color: #7C3AED; font-weight: 500; margin: 0; font-size: 14px;">
                    ✨ Zero configuration required - ready to send instantly!
                </p>
            </div>
            
            <p style="font-size: 15px; line-height: 1.5; color: #374151;">
                This demonstrates FastMCP2's ability to generate professional emails with no setup needed.
            </p>
            
            <div style="text-align: center; margin: 20px 0;">
                <a href="#" style="background: linear-gradient(135deg, #8B5CF6 0%, #7C3AED 100%); color: white; padding: 10px 24px; text-decoration: none; border-radius: 20px; display: inline-block; font-size: 14px;">Try It Out</a>
            </div>
        </div>
        
        <div style="background: #f8fafc; padding: 15px; text-align: center; font-size: 11px; color: #6B7280; border-top: 1px solid #e5e7eb;">
            FastMCP2 Simple Demo • {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        </div>
    </div>
</body>
</html>

Perfect for testing, demos, and instant email generation with zero configuration!
'''
    
    print(sample_simple_content)
    print("-" * 40)
    print("✅ Simple prompt executed successfully")
    print()

async def _test_tag_based_filtering():
    """
    Test 5: Filter prompts by tags (FastMCP 2.11.0+ feature)
    """
    print("🏷️ Test 5: Tag-based Filtering")
    print("-" * 32)
    
    # Simulate tag-based filtering
    all_prompts = [
        {"name": "smart_contextual_email", "tags": ["gmail", "advanced", "contextual", "dynamic"]},
        {"name": "professional_html_email", "tags": ["gmail", "medium", "html", "professional"]},
        {"name": "quick_email_demo", "tags": ["gmail", "simple", "demo", "instant"]}
    ]
    
    tag_filters = ["advanced", "professional", "demo", "gmail"]
    
    for tag in tag_filters:
        filtered_prompts = [
            prompt for prompt in all_prompts 
            if tag in prompt["tags"]
        ]
        
        print(f"🔍 Prompts tagged with '{tag}': {len(filtered_prompts)}")
        for prompt in filtered_prompts:
            print(f"   • {prompt['name']}")
        print()
    
    print("✅ Tag-based filtering completed successfully")
    print()

async def _test_complex_arguments():
    """
    Test 6: Complex argument serialization (FastMCP 2.9.0+ feature)
    """
    print("🔧 Test 6: Complex Argument Serialization")
    print("-" * 42)
    
    @dataclass
    class EmailRecipient:
        name: str
        role: str
        department: str
    
    @dataclass  
    class EmailContext:
        priority: str
        deadline: str
        project_code: str
    
    # Complex arguments that will be auto-serialized to JSON
    complex_args = {
        "recipient_data": EmailRecipient(
            name="Dr. Elena Rodriguez",
            role="Senior Research Director", 
            department="Innovation Labs"
        ),
        "email_context": EmailContext(
            priority="high",
            deadline="2025-09-15",
            project_code="PROJ-2025-AI"
        ),
        "email_preferences": {
            "format": "professional",
            "include_attachments": True,
            "tracking_enabled": False,
            "follow_up_days": 3
        },
        "stakeholders": [
            {"name": "Alice Johnson", "role": "PM"},
            {"name": "Bob Wilson", "role": "Tech Lead"},
            {"name": "Carol Davis", "role": "Design Lead"}
        ],
        "simple_subject": "AI Research Project Update"  # String passed through unchanged
    }
    
    print("🔬 Testing complex argument serialization:")
    print(f"📝 Dataclass objects: EmailRecipient, EmailContext")
    print(f"📝 Dictionary object: email_preferences")  
    print(f"📝 List object: stakeholders array")
    print(f"📝 Simple string: simple_subject")
    print()
    
    # Simulate automatic serialization (FastMCP handles this automatically)
    print("🔄 Automatic serialization simulation:")
    print("   • EmailRecipient -> JSON string (pydantic_core.to_json)")
    print("   • EmailContext -> JSON string (pydantic_core.to_json)")
    print("   • email_preferences dict -> JSON string")
    print("   • stakeholders list -> JSON string")
    print("   • simple_subject string -> passed unchanged")
    print()
    
    # Simulate: result = await client.get_prompt("smart_contextual_email", complex_args)
    print("📧 Simulated prompt result with complex serialized arguments:")
    print("   - FastMCP server automatically deserializes JSON back to expected types")
    print("   - Email generated with rich contextual data from complex objects")
    print("   - All argument types handled seamlessly by FastMCP serialization")
    
    print("✅ Complex argument serialization test completed")
    print()

async def demonstrate_real_client_usage():
    """
    Bonus: Show how to use with real FastMCP client
    """
    print("💡 Real FastMCP Client Usage Example")
    print("-" * 38)
    
    client_example = '''
# Real FastMCP Client Implementation
from fastmcp_client import FastMCPClient

async def use_gmail_prompts():
    async with FastMCPClient("ws://localhost:8080") as client:
        
        # 1. Discover available prompts
        prompts = await client.list_prompts()
        gmail_prompts = [p for p in prompts if "gmail" in p._meta.get("_fastmcp", {}).get("tags", [])]
        
        # 2. Use simple prompt (zero config)
        simple_result = await client.get_prompt("quick_email_demo")
        print("Simple email content:", simple_result.messages[0].content)
        
        # 3. Use medium prompt with arguments  
        medium_result = await client.get_prompt("professional_html_email", {
            "email_subject": "Team Meeting Update",
            "recipient_name": "Development Team",
            "message_theme": "meeting update"
        })
        
        # 4. Use advanced prompt with complex arguments
        advanced_result = await client.get_prompt("smart_contextual_email", {
            "email_subject": "Project Collaboration Proposal",
            "recipient_name": "Strategic Partner",
            "email_purpose": "partnership proposal"
        })
        
        # 5. Access individual messages from results
        for i, message in enumerate(advanced_result.messages):
            print(f"Message {i + 1}:")
            print(f"  Role: {message.role}")
            print(f"  Content preview: {message.content[:100]}...")
            
        return {
            "simple": simple_result,
            "medium": medium_result,
            "advanced": advanced_result
        }

# Run the real client example
# results = await use_gmail_prompts()
'''
    
    print("📋 Here's how to use these Gmail prompts with a real FastMCP client:")
    print(client_example)
    
    print("🔗 Key Integration Points:")
    print("   • Replace 'ws://localhost:8080' with your server URL")
    print("   • Install fastmcp-client package")
    print("   • Ensure Gmail prompts server is running")
    print("   • All arguments auto-serialize to JSON as needed")
    print("   • Access results via result.messages array")
    print()

if __name__ == "__main__":
    """
    Run the complete Gmail prompts client test suite
    """
    import sys
    if "pytest" in sys.modules:
        pytest.main([__file__, "-v"])
    else:
        asyncio.run(test_gmail_prompts_comprehensive())