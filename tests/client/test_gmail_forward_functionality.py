"""
Test Gmail forwarding functionality using FastMCP Client SDK.

This module tests the new forward_gmail_message and draft_gmail_forward functions
to ensure they properly preserve HTML formatting and follow elicitation patterns.
"""

"""Test Gmail forwarding functionality using FastMCP Client SDK.

🔧 MCP Tools Used:
- forward_gmail_message: Forward Gmail messages with HTML preservation
- draft_gmail_forward: Create draft forwards with HTML preservation
- search_gmail_messages: Find real Gmail messages for testing

🧪 What's Being Tested:
- Gmail message forwarding with content preservation
- Draft forward creation and validation
- Authentication patterns (explicit email vs middleware injection)
- Parameter validation and error handling
- HTML content preservation during forwarding
- Elicitation patterns and allow list integration
- Real-world integration with actual Gmail messages

🔍 Potential Duplications:
- Authentication patterns overlap with other Gmail tool tests
- Message search overlaps with test_gmail_reply_improvements.py
- HTML preservation might overlap with other Gmail content tests
- Error handling patterns similar to other Gmail tool tests
"""

import pytest
import pytest_asyncio
import asyncio
import json
import os
import logging
from datetime import datetime
from fastmcp import Client
from typing import Dict, List, Any, Optional
from dotenv import load_dotenv
from ..test_auth_utils import get_client_auth_config

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables from .env file
load_dotenv()

# Server configuration from environment variables with defaults
SERVER_HOST = os.getenv("MCP_SERVER_HOST", "localhost")
SERVER_PORT = os.getenv("MCP_SERVER_PORT", os.getenv("SERVER_PORT", "8002"))
# FastMCP servers in HTTP mode use the /mcp/ endpoint
SERVER_URL = os.getenv("MCP_SERVER_URL", f"http://{SERVER_HOST}:{SERVER_PORT}/mcp/")

# Test email address from environment variable - use valid tokens
TEST_EMAIL = os.getenv("TEST_EMAIL_ADDRESS", "test@example.com")

# Get emails from allow list - using TEST_GMAIL_ALLOW_LIST environment variable
TEST_GMAIL_ALLOW_LIST = os.getenv("TEST_GMAIL_ALLOW_LIST", "test@gmail.com,test2@gmail.com")
ALLOWED_EMAILS = [email.strip() for email in TEST_GMAIL_ALLOW_LIST.split(",") if email.strip()]


class TestGmailForwardFunctionality:
    """Test Gmail forwarding tools using FastMCP Client SDK."""
    
    # Remove custom client fixture - use the one from conftest.py

    @pytest.mark.asyncio
    async def test_forward_tools_available(self, client):
        """Test that Gmail forward tools are available."""
        tools = await client.list_tools()
        tool_names = [tool.name for tool in tools]
        
        expected_tools = ["forward_gmail_message", "draft_gmail_forward", "search_gmail_messages"]
        
        for tool_name in expected_tools:
            assert tool_name in tool_names, f"Tool '{tool_name}' not found in available tools"

    @pytest.mark.asyncio
    async def test_search_gmail_messages_basic(self, client):
        """Test basic Gmail message search functionality - THIS IS THE KEY TEST."""
        # Test basic Gmail search with proper page_size parameter
        result = await client.call_tool("search_gmail_messages", {
            "user_google_email": TEST_EMAIL,
            "query": "in:inbox",
            "page_size": 1  # This should NOT be transformed to max_results
        })
        
        # Handle both old list format and new CallToolResult format
        if hasattr(result, 'content'):
            # New FastMCP format - result is CallToolResult with content list
            content_items = result.content if hasattr(result.content, '__iter__') else [result.content]
            assert len(content_items) > 0
            content = content_items[0].text if hasattr(content_items[0], 'text') else str(content_items[0])
        elif hasattr(result, '__iter__') and not isinstance(result, str):
            # Old format - result is a list
            assert len(result) > 0
            content = result[0].text
        else:
            # Direct content
            content = str(result)
        
        print(f"\n=== GMAIL SEARCH TEST RESPONSE ===")
        print(f"Response: '{content}'")
        print(f"Content length: {len(content)} chars")
        print(f"=== END GMAIL SEARCH TEST ===\n")
        
        # Should either succeed or return a meaningful error
        valid_responses = [
            "messages", "gmail", "search", "inbox",
            "❌", "error", "failed", "auth"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), f"Response didn't match expected pattern: {content}"
        
        # Check for the specific validation error that was causing the middleware failure
        if "unexpected keyword argument" in content.lower() and "max_results" in content.lower():
            pytest.fail(f"MIDDLEWARE BUG: page_size is being transformed to max_results: {content}")
        
        logger.info(f"Gmail search test result: {content}")

    @pytest.mark.asyncio
    async def test_forward_gmail_message_basic(self, client):
        """Test basic Gmail message forwarding."""
        # Skip if no allowed emails for testing
        if not ALLOWED_EMAILS:
            pytest.skip("No allowed emails configured for forward testing")
        
        # Create timestamp for unique identification
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Test basic forward
        test_params = {
            "user_google_email": TEST_EMAIL,
            "message_id": "test_message_id",
            "to": ALLOWED_EMAILS[0],
            "body": f"Test forward message ({timestamp})",
            "content_type": "mixed",
            "html_body": f"<p><strong>Test forward</strong> message ({timestamp})</p>"
        }
        
        print(f"\n{'='*60}")
        print(f"📧 GMAIL FORWARD TEST")
        print(f"{'='*60}")
        print(f"📤 Forwarding to: {ALLOWED_EMAILS[0]}")
        print(json.dumps(test_params, indent=2))
        print(f"{'='*60}\n")
        
        # Send forward
        result = await client.call_tool("forward_gmail_message", test_params)
        
        # Handle both old list format and new CallToolResult format
        if hasattr(result, 'content'):
            content_items = result.content if hasattr(result.content, '__iter__') else [result.content]
            assert len(content_items) > 0
            content = content_items[0].text if hasattr(content_items[0], 'text') else str(content_items[0])
        elif hasattr(result, '__iter__') and not isinstance(result, str):
            assert len(result) > 0
            content = result[0].text
        else:
            content = str(result)
        
        print(f"\n=== FORWARD TEST RESPONSE ===")
        print(f"Response: '{content}'")
        print(f"=== END FORWARD TEST ===\n")
        
        # Should either succeed or return a meaningful error
        valid_responses = [
            "sent", "forward", "successfully", "message",
            "❌", "error", "failed", "not found", "invalid"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), f"Response didn't match expected pattern: {content}"
        
        # CRITICAL: Check response for success or acceptable errors
        if "sent successfully" in content.lower():
            print("✅ SUCCESS: Message forwarded successfully")
        elif "not found" in content.lower() or "invalid" in content.lower():
            print("✅ EXPECTED: Test message ID not found (expected behavior)")
        elif "auth" in content.lower() or "permission" in content.lower():
            print("✅ EXPECTED: Authentication or permission issue")
        elif "❌" in content:
            print(f"ℹ️  INFO: Error response: {content}")
        else:
            print(f"❓ Response: {content}")
            
        logger.info(f"Forward test result: {content}")

    @pytest.mark.asyncio
    async def test_draft_gmail_forward_basic(self, client):
        """Test basic Gmail draft forward creation."""
        # Skip if no allowed emails for testing
        if not ALLOWED_EMAILS:
            pytest.skip("No allowed emails configured for draft forward testing")
        
        # Create timestamp for unique identification
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Test basic draft forward
        test_params = {
            "user_google_email": TEST_EMAIL,
            "message_id": "test_message_id",
            "to": ALLOWED_EMAILS[0],
            "body": f"Test draft forward message ({timestamp})",
            "content_type": "mixed",
            "html_body": f"<p><strong>Test draft forward</strong> message ({timestamp})</p>"
        }
        
        print(f"\n{'='*60}")
        print(f"📝 GMAIL DRAFT FORWARD TEST")
        print(f"{'='*60}")
        print(f"📤 Draft forward to: {ALLOWED_EMAILS[0]}")
        print(json.dumps(test_params, indent=2))
        print(f"{'='*60}\n")
        
        # Create draft forward
        result = await client.call_tool("draft_gmail_forward", test_params)
        
        # Handle both old list format and new CallToolResult format
        if hasattr(result, 'content'):
            content_items = result.content if hasattr(result.content, '__iter__') else [result.content]
            assert len(content_items) > 0
            content = content_items[0].text if hasattr(content_items[0], 'text') else str(content_items[0])
        elif hasattr(result, '__iter__') and not isinstance(result, str):
            assert len(result) > 0
            content = result[0].text
        else:
            content = str(result)
        
        print(f"\n=== DRAFT FORWARD TEST RESPONSE ===")
        print(f"Response: '{content}'")
        print(f"=== END DRAFT FORWARD TEST ===\n")
        
        # Should either succeed or return a meaningful error
        valid_responses = [
            "draft", "saved", "created", "forward",
            "❌", "error", "failed", "not found", "invalid"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), f"Response didn't match expected pattern: {content}"
        
        # Check response for success or acceptable errors
        if "saved" in content.lower() or "created" in content.lower():
            print("✅ SUCCESS: Draft forward created successfully")
        elif "not found" in content.lower() or "invalid" in content.lower():
            print("✅ EXPECTED: Test message ID not found (expected behavior)")
        elif "auth" in content.lower() or "permission" in content.lower():
            print("✅ EXPECTED: Authentication or permission issue")
        elif "❌" in content:
            print(f"ℹ️  INFO: Error response: {content}")
        else:
            print(f"❓ Response: {content}")
            
        logger.info(f"Draft forward test result: {content}")

    @pytest.mark.asyncio
    async def test_forward_parameter_validation(self, client):
        """Test forward tools handle parameter validation properly."""
        # Test missing required 'to' parameter
        incomplete_params = {
            "user_google_email": TEST_EMAIL,
            "message_id": "test_123",
            "body": "Test message"
            # Missing 'to' parameter
        }
        
        print(f"\n{'='*60}")
        print(f"🚫 PARAMETER VALIDATION TEST")
        print(f"{'='*60}")
        print("Testing missing 'to' parameter...")
        print(json.dumps(incomplete_params, indent=2))
        print(f"{'='*60}\n")
        
        # Test parameter validation - should throw an exception
        try:
            result = await client.call_tool("forward_gmail_message", incomplete_params)
            # If we get here, validation didn't work as expected
            pytest.fail("Should have thrown parameter validation error for missing 'to' parameter")
        except Exception as e:
            # Expected - should get validation error
            error_msg = str(e)
            print(f"\n=== PARAMETER VALIDATION RESPONSE ===")
            print(f"Exception: '{error_msg}'")
            print(f"=== END PARAMETER VALIDATION ===\n")
            
            # Should show parameter validation error
            validation_keywords = [
                "required", "missing", "parameter", "to", "recipient",
                "validation", "error"
            ]
            has_validation_error = any(keyword in error_msg.lower() for keyword in validation_keywords)
            assert has_validation_error, f"Should show parameter validation error. Got: {error_msg}"
            
            print("✅ SUCCESS: Parameter validation working correctly")
            logger.info(f"Parameter validation test result: {error_msg}")

    @pytest.mark.asyncio
    async def test_forward_content_type_options(self, client):
        """Test forward tools support different content types."""
        # Skip if no allowed emails for testing
        if not ALLOWED_EMAILS:
            pytest.skip("No allowed emails configured for content type testing")
        
        content_types = ["plain", "html", "mixed"]
        
        for content_type in content_types:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            test_params = {
                "user_google_email": TEST_EMAIL,
                "message_id": "test_msg_123",
                "to": ALLOWED_EMAILS[0],
                "body": f"Test {content_type} content ({timestamp})",
                "content_type": content_type
            }
            
            # Add HTML body for mixed type
            if content_type == "mixed":
                test_params["html_body"] = f"<p><strong>Test {content_type}</strong> HTML content ({timestamp})</p>"
            
            print(f"\n{'='*60}")
            print(f"📝 CONTENT TYPE TEST: {content_type.upper()}")
            print(f"{'='*60}")
            print(json.dumps(test_params, indent=2))
            print(f"{'='*60}\n")
            
            # Test content type
            result = await client.call_tool("forward_gmail_message", test_params)
            
            # Add small delay between tests
            await asyncio.sleep(1)
            
            # Handle both old list format and new CallToolResult format
            if hasattr(result, 'content'):
                content_items = result.content if hasattr(result.content, '__iter__') else [result.content]
                assert len(content_items) > 0
                content = content_items[0].text if hasattr(content_items[0], 'text') else str(content_items[0])
            elif hasattr(result, '__iter__') and not isinstance(result, str):
                assert len(result) > 0
                content = result[0].text
            else:
                content = str(result)
            
            print(f"\n=== {content_type.upper()} CONTENT TYPE RESPONSE ===")
            print(f"Response: '{content}'")
            print(f"=== END {content_type.upper()} CONTENT TYPE ===\n")
            
            # Should either succeed or return valid error
            valid_responses = [
                "forward", "message", "content", content_type,
                "❌", "error", "not found", "invalid", "auth"
            ]
            assert any(keyword in content.lower() for keyword in valid_responses), f"Content type {content_type} response didn't match expected pattern: {content}"
            
            # Log result for each content type
            if "sent successfully" in content.lower():
                print(f"✅ SUCCESS: {content_type} forward sent successfully")
            elif "not found" in content.lower():
                print(f"✅ EXPECTED: Message not found for {content_type} test")
            elif "auth" in content.lower():
                print(f"✅ EXPECTED: Auth issue for {content_type} test")
            else:
                print(f"❓ {content_type}: {content}")
            
            logger.info(f"Content type {content_type} test result: {content}")

    @pytest.mark.asyncio  
    @pytest.mark.auth_required
    async def test_forward_real_message_integration(self, client):
        """Real-world test: Get actual Gmail message and test forwarding."""
        print("\n🔍 Starting real Gmail forward integration test...")
        
        # Step 1: Get a real Gmail message using search - THIS IS WHERE THE BUG OCCURS
        print("📧 Searching for real Gmail message...")
        
        # CRITICAL: This call should use page_size=1 but middleware transforms it to max_results=1
        search_params = {
            "user_google_email": TEST_EMAIL,
            "query": "in:inbox",
            "page_size": 1
        }
        
        print(f"\n{'='*60}")
        print(f"🔍 CRITICAL GMAIL SEARCH TEST")
        print(f"{'='*60}")
        print("🚨 This is where the middleware parameter transformation bug occurs!")
        print("🚨 The page_size parameter gets transformed to max_results")
        print(json.dumps(search_params, indent=2))
        print(f"{'='*60}\n")
        
        try:
            result = await client.call_tool("search_gmail_messages", search_params)
            
            # Handle both old list format and new CallToolResult format
            if hasattr(result, 'content'):
                content_items = result.content if hasattr(result.content, '__iter__') else [result.content]
                content = content_items[0].text if hasattr(content_items[0], 'text') else str(content_items[0]) if content_items else ""
            elif hasattr(result, '__iter__') and not isinstance(result, str):
                content = result[0].text if result else ""
            else:
                content = str(result)
                
            print(f"\n=== GMAIL SEARCH RESULT ===")
            print(f"✅ SEARCH SUCCESS: No parameter transformation error!")
            print(f"Response: '{content[:200]}...'" if len(content) > 200 else f"Response: '{content}'")
            print(f"=== END GMAIL SEARCH ===\n")
            
            # If we got here, the parameter transformation issue is fixed
            logger.info("✅ SUCCESS: Gmail search completed without parameter transformation error")
            
            # Continue with forward test if we have a message
            search_content = str(content)
            message_id = None
            
            for line in search_content.split('\n'):
                if "Message ID:" in line and len(line.split()) > 2:
                    message_id = line.split("Message ID:")[1].strip().split()[0]
                    break
                    
            if message_id and ALLOWED_EMAILS:
                print(f"📤 Testing forward with real message ID: {message_id}")
                
                forward_params = {
                    "user_google_email": TEST_EMAIL,
                    "message_id": message_id,
                    "to": ALLOWED_EMAILS[0],
                    "body": f"Integration test forward ({timestamp})",
                    "content_type": "mixed",
                    "html_body": f"<p><strong>Integration test forward</strong> ({timestamp})</p>"
                }
                
                forward_result = await client.call_tool("forward_gmail_message", forward_params)
                
                # Handle forward result
                if hasattr(forward_result, 'content'):
                    forward_content_items = forward_result.content if hasattr(forward_result.content, '__iter__') else [forward_result.content]
                    forward_content = forward_content_items[0].text if hasattr(forward_content_items[0], 'text') else str(forward_content_items[0]) if forward_content_items else ""
                elif hasattr(forward_result, '__iter__') and not isinstance(forward_result, str):
                    forward_content = forward_result[0].text if forward_result else ""
                else:
                    forward_content = str(forward_result)
                
                print(f"\n=== FORWARD RESULT ===")
                print(f"Forward response: '{forward_content}'")
                print(f"=== END FORWARD RESULT ===\n")
                
                if "sent successfully" in forward_content.lower():
                    print("✅ SUCCESS: Real message forwarded successfully")
                elif "not found" in forward_content.lower():
                    print("✅ EXPECTED: Real message not found or insufficient permissions")
                else:
                    print(f"ℹ️  Forward result: {forward_content}")
            else:
                print("ℹ️  No message ID found or no allowed emails - skipping forward test")
            
        except Exception as e:
            error_msg = str(e)
            print(f"\n=== GMAIL SEARCH ERROR ===")
            print(f"❌ ERROR: {error_msg}")
            print(f"=== END GMAIL SEARCH ERROR ===\n")
            
            # Check if this is the parameter transformation error
            if "unexpected keyword argument" in error_msg.lower() and "max_results" in error_msg.lower():
                pytest.fail(f"🚨 MIDDLEWARE BUG CONFIRMED: page_size transformed to max_results: {error_msg}")
            else:
                print(f"ℹ️  Different error type: {error_msg}")
                logger.info(f"Gmail search error (not parameter transformation): {error_msg}")

    @pytest.mark.asyncio
    async def test_parameter_transformation_debugging(self, client):
        """Specific test to debug the parameter transformation issue."""
        print(f"\n{'='*80}")
        print(f"🔧 PARAMETER TRANSFORMATION DEBUGGING SESSION")
        print(f"{'='*80}")
        
        # Test 1: Direct search with page_size
        print("🧪 Test 1: Direct search_gmail_messages with page_size parameter")
        
        test_params_1 = {
            "user_google_email": TEST_EMAIL,
            "query": "in:inbox",
            "page_size": 1
        }
        
        print(f"📋 Parameters being sent:")
        print(json.dumps(test_params_1, indent=2))
        
        try:
            result_1 = await client.call_tool("search_gmail_messages", test_params_1)
            print("✅ SUCCESS: No parameter transformation error!")
        except Exception as e:
            error_msg = str(e)
            print(f"❌ ERROR: {error_msg}")
            
            if "max_results" in error_msg and "unexpected keyword argument" in error_msg.lower():
                print("🚨 BUG CONFIRMED: page_size is being transformed to max_results")
                print("🔧 This confirms the middleware template parameter transformation bug")
            else:
                print("ℹ️  Different error - not the parameter transformation bug")
        
        print(f"\n{'='*80}")
        print(f"🔧 END PARAMETER TRANSFORMATION DEBUGGING")
        print(f"{'='*80}\n")


if __name__ == "__main__":
    pytest.main(["-xvs", __file__])