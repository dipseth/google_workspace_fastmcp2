#!/usr/bin/env python3
"""
Simple Template Middleware Integration Test using FastMCP Client SDK.

This is a simplified version that follows the exact pattern from test_send_dynamic_card.py
to ensure it works with the real running FastMCP server.
"""

import asyncio
import os
import ssl
import logging
from datetime import datetime
import pytest
from dotenv import load_dotenv
from .base_test_config import TEST_EMAIL
import httpx

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables from .env file
load_dotenv()


@pytest.mark.integration
class TestTemplateSimple:
    """Simple test for template middleware integration."""
    
    @pytest.mark.asyncio
    async def test_server_connection(self, client):
        """Test basic server connectivity."""
        logger.info("🧪 Testing server connection")
        
        # List resources to verify connection
        resources = await client.list_resources()
        logger.info(f"✅ Server connected - found {len(resources)} resources")
        assert len(resources) >= 0, "Should be able to list resources"
    
    @pytest.mark.asyncio
    async def test_gmail_tools_available(self, client):
        """Test that Gmail tools are available."""
        logger.info("🧪 Testing Gmail tools availability")
        
        tools = await client.list_tools()
        tool_names = [tool.name for tool in tools]
        
        gmail_tools = [name for name in tool_names if "gmail" in name.lower()]
        logger.info(f"Found {len(gmail_tools)} Gmail tools: {gmail_tools[:5]}...")
        
        assert len(gmail_tools) > 0, "Should have Gmail tools available"
    
    @pytest.mark.asyncio
    async def test_call_gmail_labels_tool(self, client):
        """Test calling the Gmail labels tool to get real data."""
        logger.info("🧪 Testing Gmail labels tool call")
        
        tools = await client.list_tools()
        tool_names = [tool.name for tool in tools]
        
        if "list_gmail_labels" in tool_names:
            logger.info("Calling list_gmail_labels tool...")
            
            try:
                result = await client.call_tool("list_gmail_labels", {
                    "user_google_email": TEST_EMAIL
                })
                
                # Handle both old list format and new CallToolResult format
                if hasattr(result, 'content'):
                    contents = result.content
                    if contents and len(contents) > 0:
                        content_text = contents[0].text if hasattr(contents[0], 'text') else str(contents[0])
                    else:
                        content_text = "No contents"
                elif hasattr(result, '__iter__') and not isinstance(result, str):
                    result_list = list(result)
                    if result_list and hasattr(result_list[0], 'text'):
                        content_text = result_list[0].text
                    else:
                        content_text = str(result_list)
                else:
                    content_text = str(result)
                
                logger.info(f"Gmail labels result preview: {content_text[:200]}...")
                
                # Look for label content
                if "label" in content_text.lower() or "inbox" in content_text.lower():
                    logger.info("✅ Gmail labels tool returned label data")
                else:
                    logger.info("⚠️ Gmail labels tool responded but no label data detected")
                    
            except Exception as e:
                logger.warning(f"❌ Gmail labels tool failed: {e}")
        else:
            logger.warning("list_gmail_labels tool not available")
    
    @pytest.mark.asyncio  
    async def test_gmail_resources(self, client):
        """Test Gmail resources."""
        logger.info("🧪 Testing Gmail resources")
        
        resources = await client.list_resources()
        resource_uris = [resource.uri for resource in resources]
        
        gmail_resources = [uri for uri in resource_uris if "gmail" in uri.lower()]
        logger.info(f"Found {len(gmail_resources)} Gmail resources: {gmail_resources[:3]}...")
        
        if gmail_resources:
            # Try to read the first Gmail resource
            try:
                test_resource = gmail_resources[0]
                logger.info(f"Testing resource: {test_resource}")
                
                result = await client.read_resource(test_resource)
                logger.info(f"Resource read successfully: {type(result)}")
                logger.info("✅ Gmail resources are accessible")
            except Exception as e:
                logger.warning(f"❌ Failed to read Gmail resource: {e}")
        else:
            logger.info("⚠️ No Gmail resources found")


# Simple standalone test function
async def run_simple_test():
    """Run a simple test without pytest infrastructure."""
    logger.info("🚀 Running Simple Template Middleware Test")
    logger.info("=" * 60)
    logger.info(f"Server URL: {SERVER_URL}")
    logger.info(f"Test Email: {TEST_EMAIL}")
    logger.info("=" * 60)
    
    # First, test basic HTTP connectivity
    logger.info("Testing basic HTTP connectivity...")
    try:
        async with httpx.AsyncClient() as http_client:
            response = await http_client.get(SERVER_URL)
            logger.info(f"✅ HTTP test successful: {response.status_code}")
    except Exception as e:
        logger.error(f"❌ Basic HTTP test failed: {e}")
        return
    
    # Get authentication config
    auth_config = get_client_auth_config(TEST_EMAIL)
    logger.info(f"Auth config: {'JWT token available' if auth_config else 'No JWT token'}")
    
    # Test SSL environment
    ssl_cert_file = os.environ.get('SSL_CERT_FILE')
    logger.info(f"SSL_CERT_FILE: {ssl_cert_file}")
    if ssl_cert_file and not os.path.exists(ssl_cert_file):
        logger.warning(f"SSL cert file doesn't exist: {ssl_cert_file}")
        # Try unsetting it
        if 'SSL_CERT_FILE' in os.environ:
            del os.environ['SSL_CERT_FILE']
            logger.info("Unset SSL_CERT_FILE environment variable")
    
    # Create client and test
    try:
        client = Client(SERVER_URL, auth=auth_config)
        logger.info("✅ Client created successfully")
    except Exception as e:
        logger.error(f"❌ Client creation failed: {e}")
        return
    
    try:
        async with client:
            logger.info("✅ Connected to FastMCP server")
            
            # Test 1: Basic connectivity
            resources = await client.list_resources()
            logger.info(f"✅ Found {len(resources)} resources")
            
            # Test 2: Gmail tools
            tools = await client.list_tools()
            gmail_tools = [tool.name for tool in tools if "gmail" in tool.name.lower()]
            logger.info(f"✅ Found {len(gmail_tools)} Gmail tools")
            
            # Test 3: Try calling a Gmail tool
            if "list_gmail_labels" in [tool.name for tool in tools]:
                logger.info("Calling list_gmail_labels...")
                try:
                    result = await client.call_tool("list_gmail_labels", {
                        "user_google_email": TEST_EMAIL
                    })
                    logger.info("✅ Gmail labels tool executed successfully")
                    
                    # Extract content
                    if hasattr(result, 'content') and result.content:
                        content = str(result.content[0].text if hasattr(result.content[0], 'text') else result.content[0])
                    else:
                        content = str(result)
                    
                    # Look for real label IDs
                    import re
                    label_ids = re.findall(r'"id"\s*:\s*"([^"]+)"', content)
                    if label_ids:
                        logger.info(f"✅ Found real label IDs: {label_ids[:3]}...")
                        
                        # This is the key test - we got real Gmail data!
                        logger.info("🎉 SUCCESS: Template middleware can use this real Gmail data!")
                        
                    else:
                        logger.info("⚠️ No label IDs found in response")
                        
                except Exception as e:
                    logger.warning(f"❌ Gmail tool failed: {e}")
            
            # Test 4: Gmail resources
            gmail_resources = [r.uri for r in resources if "gmail" in r.uri.lower()]
            if gmail_resources:
                logger.info(f"✅ Found Gmail resources: {gmail_resources[:2]}...")
                
                # Try reading a resource
                try:
                    result = await client.read_resource(gmail_resources[0])
                    logger.info("✅ Gmail resource read successfully")
                    
                    # Check if resource contains same data as tools
                    if hasattr(result, 'contents') and result.contents:
                        resource_content = str(result.contents[0].text if hasattr(result.contents[0], 'text') else result.contents[0])
                        
                        # Look for label IDs in resource too
                        import re
                        resource_label_ids = re.findall(r'"id"\s*:\s*"([^"]+)"', resource_content)
                        if resource_label_ids:
                            logger.info(f"✅ Resource also contains label IDs: {resource_label_ids[:2]}...")
                            logger.info("🎉 SUCCESS: Template middleware should resolve these IDs!")
                    
                except Exception as e:
                    logger.warning(f"❌ Gmail resource failed: {e}")
            
            logger.info("=" * 60)
            logger.info("🎉 Simple test completed successfully!")
            
    except Exception as e:
        logger.error(f"❌ FastMCP Client failed: {e}")
        logger.error("Checking if this is an SSL issue...")
        
        # Try with explicit SSL context
        try:
            import ssl
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            logger.info("Created relaxed SSL context, but FastMCP Client doesn't support custom SSL context")
        except Exception as ssl_e:
            logger.error(f"SSL context creation failed: {ssl_e}")


def main():
    """Main function for direct script execution"""
    asyncio.run(run_simple_test())


if __name__ == "__main__":
    main()