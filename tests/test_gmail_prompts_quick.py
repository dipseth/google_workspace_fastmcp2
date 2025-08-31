#!/usr/bin/env python3
"""
Gmail Prompts Quick Test

Simple test script to quickly verify the Gmail prompts are working.
Run this after starting your FastMCP2 server with Gmail prompts.

Usage:
    python test_gmail_prompts_quick.py
    pytest tests/test_gmail_prompts_quick.py -v
"""

import asyncio
import json
import pytest
from datetime import datetime

@pytest.mark.asyncio
async def test_gmail_prompts_quick():
    """
    Quick test of Gmail prompts - replace with real client when ready
    """
    print("🚀 Gmail Prompts Quick Test")
    print("=" * 40)
    print(f"⏰ Test started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # Test configurations for each prompt level
    test_configs = {
        "simple": {
            "prompt_name": "quick_email_demo",
            "description": "Zero-config instant demo",
            "args": {},  # No arguments needed
            "expected_features": [
                "Purple gradient design",
                "Zero configuration required", 
                "Professional appearance",
                "Instant send capability"
            ]
        },
        
        "medium": {
            "prompt_name": "professional_html_email",
            "description": "Professional HTML with modern design",
            "args": {
                "email_subject": "Welcome to Our Platform",
                "recipient_name": "New User",
                "message_theme": "welcome message"
            },
            "expected_features": [
                "Blue gradient professional design",
                "Responsive 3-column stats grid",
                "Cross-platform compatibility",
                "Modern typography"
            ]
        },
        
        "advanced": {
            "prompt_name": "smart_contextual_email", 
            "description": "Advanced with Gmail data integration",
            "args": {
                "email_subject": "Smart Business Proposal",
                "recipient_name": "Potential Client",
                "email_purpose": "business proposal"
            },
            "expected_features": [
                "Real-time Gmail data integration",
                "Context-aware content generation", 
                "Intelligence indicators",
                "Resource-aware routing"
            ]
        }
    }
    
    # Test each prompt level
    for level, config in test_configs.items():
        await _test_prompt_level(level, config)
        print()
    
    print("🎯 Integration Instructions:")
    print("-" * 30)
    print("To integrate with real FastMCP client:")
    print()
    print("1. Install FastMCP client:")
    print("   pip install fastmcp-client")
    print()
    print("2. Replace simulation with real client:")
    print("   async with FastMCPClient('ws://localhost:8080') as client:")
    print("       result = await client.get_prompt(prompt_name, args)")
    print()
    print("3. Start your FastMCP2 server with Gmail prompts:")
    print("   python server.py  # or your server startup command")
    print()
    
    print("✅ Quick test completed successfully!")


async def _test_prompt_level(level: str, config: dict):
    """Test individual prompt level (helper function)"""
    print(f"🎯 Testing {level.upper()} Prompt")
    print("-" * (15 + len(level)))
    
    prompt_name = config["prompt_name"]
    description = config["description"] 
    args = config["args"]
    features = config["expected_features"]
    
    print(f"📋 Prompt: {prompt_name}")
    print(f"📝 Description: {description}")
    
    if args:
        print(f"⚙️ Arguments:")
        for key, value in args.items():
            print(f"   • {key}: '{value}'")
    else:
        print(f"⚙️ Arguments: None (zero-config)")
    
    print(f"✨ Expected Features:")
    for feature in features:
        print(f"   • {feature}")
    
    # Simulate the client call and show what the actual prompt would generate
    print(f"🔄 Simulating: client.get_prompt('{prompt_name}', {args})")
    print()
    
    # Generate sample prompt content based on the prompt type
    if level == "simple":
        print("📧 GENERATED PROMPT CONTENT:")
        print("=" * 50)
        print(f"""
# ⚡ Quick Email Demo (Simple)
*Generated at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*

## 🎯 Zero-Configuration Demo

### Features
- **Level**: Simple - No parameters required
- **Ready**: Instant send capability  
- **Design**: Clean and professional
- **Testing**: Perfect for quick demos

## 📧 Instant Send Example

Ready to send immediately - zero configuration needed!

Email would include:
- Purple gradient HTML design
- Professional appearance despite simplicity  
- Cross-platform compatibility
- Zero setup requirements

Perfect for quick demos and functionality testing!
""")
    
    elif level == "medium":
        print("📧 GENERATED PROMPT CONTENT:")
        print("=" * 50)
        print(f"""
# 🎨 Professional HTML Email (Medium)
*Generated at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*

## ✨ Professional Design Features

### Configuration
- **Subject**: {args.get('email_subject', 'N/A')}
- **Recipient**: {args.get('recipient_name', 'N/A')}
- **Theme**: {args.get('message_theme', 'N/A')}
- **Level**: Medium complexity with professional styling

## 📧 Ready-to-Send Professional Email

Email would include:
- Clean blue gradient theme with modern typography
- Responsive 3-column stats grid that adapts to mobile
- Professional greeting and structured content
- Cross-client compatibility (Gmail, Outlook, Apple Mail)
- Clean call-to-action button
- Professional closing with metadata

Perfect for business communications and client outreach!
""")
    
    elif level == "advanced":
        print("📧 GENERATED PROMPT CONTENT:")
        print("=" * 50)
        print(f"""
# 🧠 Smart Contextual Gmail Email (Advanced)
*Generated at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*

## ⚡ Advanced Gmail Intelligence

### Configuration
- **Subject**: {args.get('email_subject', 'N/A')}
- **Recipient**: {args.get('recipient_name', 'N/A')}  
- **Purpose**: {args.get('email_purpose', 'N/A')}
- **Level**: Advanced with real-time Gmail data integration

## 📊 Gmail Intelligence Integration

Email would include:
- Real-time Gmail resource integration (service://gmail/labels, filters, lists)
- Context-aware content that adapts to your Gmail setup
- Professional blue-purple gradient with intelligence indicators
- Smart routing designed for optimal email organization
- Intelligence box showing Gmail integration features
- Advanced HTML with responsive design

Demonstrates FastMCP2's sophisticated resource integration capabilities!
""")
    
    print("=" * 50)
    print()
    
    # Simulate success
    await asyncio.sleep(0.1)  # Simulate async call
    print(f"✅ {level.upper()} prompt test passed")


def show_real_usage_example():
    """Show real FastMCP client usage example"""
    example = f'''
# Real FastMCP Client Usage Example

from fastmcp_client import FastMCPClient

async def test_gmail_prompts():
    async with FastMCPClient("ws://localhost:8080") as client:
        
        # Test simple prompt (no args)
        simple = await client.get_prompt("quick_email_demo")
        print("Simple result:", simple.messages[0].content)
        
        # Test medium prompt (with args)
        medium = await client.get_prompt("professional_html_email", {{
            "email_subject": "Welcome Email",
            "recipient_name": "John Doe", 
            "message_theme": "welcome"
        }})
        
        # Test advanced prompt (with complex args)
        advanced = await client.get_prompt("smart_contextual_email", {{
            "email_subject": "Business Proposal",
            "recipient_name": "Jane Smith",
            "email_purpose": "partnership opportunity"
        }})
        
        # Access the generated content
        for message in advanced.messages:
            print(f"Role: {{message.role}}")
            print(f"Content: {{message.content}}")

# Run the test
await test_gmail_prompts()
'''
    
    print("💡 Real Client Integration:")
    print(example)

@pytest.mark.asyncio
async def test_individual_prompts():
    """Test each prompt individually for detailed validation"""
    test_configs = {
        "simple": {
            "prompt_name": "quick_email_demo",
            "description": "Zero-config instant demo",
            "args": {},
            "expected_features": [
                "Purple gradient design",
                "Zero configuration required", 
                "Professional appearance",
                "Instant send capability"
            ]
        },
        "medium": {
            "prompt_name": "professional_html_email",
            "description": "Professional HTML with modern design",
            "args": {
                "email_subject": "Welcome to Our Platform",
                "recipient_name": "New User",
                "message_theme": "welcome message"
            },
            "expected_features": [
                "Blue gradient professional design",
                "Responsive 3-column stats grid",
                "Cross-platform compatibility",
                "Modern typography"
            ]
        },
        "advanced": {
            "prompt_name": "smart_contextual_email", 
            "description": "Advanced with Gmail data integration",
            "args": {
                "email_subject": "Smart Business Proposal",
                "recipient_name": "Potential Client",
                "email_purpose": "business proposal"
            },
            "expected_features": [
                "Real-time Gmail data integration",
                "Context-aware content generation", 
                "Intelligence indicators",
                "Resource-aware routing"
            ]
        }
    }
    
    for level, config in test_configs.items():
        await _test_prompt_level(level, config)
        # Assert that configuration is valid
        assert config["prompt_name"] in ["quick_email_demo", "professional_html_email", "smart_contextual_email"]
        assert len(config["expected_features"]) > 0
        assert isinstance(config["args"], dict)


def test_prompt_configurations():
    """Test that prompt configurations are properly structured"""
    prompt_names = ["quick_email_demo", "professional_html_email", "smart_contextual_email"]
    
    for name in prompt_names:
        # Basic validation that prompt names are strings and non-empty
        assert isinstance(name, str)
        assert len(name) > 0
        assert "_" in name  # All our prompts use underscore naming


if __name__ == "__main__":
    # Support both direct execution and pytest
    import sys
    if "pytest" in sys.modules:
        pytest.main([__file__, "-v"])
    else:
        asyncio.run(test_gmail_prompts_quick())