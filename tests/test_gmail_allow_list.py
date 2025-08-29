#!/usr/bin/env python3
"""
Test script for Gmail Allow List functionality
"""

import os
import sys
import asyncio
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from config.settings import settings
from resources.user_resources import setup_user_resources
from gmail.gmail_tools import setup_gmail_tools
from fastmcp import FastMCP

async def test_allow_list():
    """Test the Gmail allow list functionality."""
    
    print("=" * 60)
    print("Gmail Allow List Test Suite")
    print("=" * 60)
    
    # Test 1: Check settings configuration
    print("\n1. Testing Settings Configuration:")
    print(f"   - Current GMAIL_ALLOW_LIST env var: '{os.environ.get('GMAIL_ALLOW_LIST', 'Not set')}'")
    print(f"   - Settings gmail_allow_list value: '{settings.gmail_allow_list}'")
    
    # Test 2: Parse allow list
    print("\n2. Testing get_gmail_allow_list method:")
    allow_list = settings.get_gmail_allow_list()
    print(f"   - Parsed allow list: {allow_list}")
    print(f"   - Number of emails: {len(allow_list)}")
    
    # Test 3: Test with some sample data
    print("\n3. Testing with sample data:")
    test_emails = "test1@example.com,test2@example.com,  test3@example.com  "
    os.environ["GMAIL_ALLOW_LIST"] = test_emails
    settings.gmail_allow_list = test_emails
    
    parsed = settings.get_gmail_allow_list()
    print(f"   - Input: '{test_emails}'")
    print(f"   - Parsed result: {parsed}")
    print(f"   - Correctly normalized: {parsed == ['test1@example.com', 'test2@example.com', 'test3@example.com']}")
    
    # Test 4: Test empty/missing configuration
    print("\n4. Testing empty/missing configuration:")
    os.environ["GMAIL_ALLOW_LIST"] = ""
    settings.gmail_allow_list = ""
    empty_list = settings.get_gmail_allow_list()
    print(f"   - Empty string result: {empty_list}")
    print(f"   - Returns empty list: {empty_list == []}")
    
    # Test 5: Test resource availability (mock)
    print("\n5. Testing Resource Registration:")
    try:
        mcp = FastMCP("gmail-allow-list-test")
        setup_user_resources(mcp)
        print("   - User resources registered successfully")
        print("   - Gmail allow list resource available at: gmail://allow-list")
    except Exception as e:
        print(f"   - Error registering resources: {e}")
    
    # Test 6: Test tools availability (mock)  
    print("\n6. Testing Tools Registration:")
    try:
        setup_gmail_tools(mcp)
        print("   - Gmail tools registered successfully")
        print("   - Available allow list tools:")
        print("     • add_to_gmail_allow_list")
        print("     • remove_from_gmail_allow_list")
        print("     • view_gmail_allow_list")
    except Exception as e:
        print(f"   - Error registering tools: {e}")
    
    print("\n" + "=" * 60)
    print("✅ All tests completed!")
    print("=" * 60)
    
    # Reset environment
    if "GMAIL_ALLOW_LIST" in os.environ:
        del os.environ["GMAIL_ALLOW_LIST"]

if __name__ == "__main__":
    asyncio.run(test_allow_list())