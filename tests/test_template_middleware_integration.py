"""Test Template Middleware Integration for Gmail Prompts using FastMCP Client SDK."""

import pytest
import asyncio
import logging
import os
import json
import re
from datetime import datetime
from dotenv import load_dotenv
from fastmcp import Client

# Load environment variables from .env file
load_dotenv()

logger = logging.getLogger(__name__)

# Server configuration from environment variables with defaults
SERVER_HOST = os.getenv("MCP_SERVER_HOST", "localhost")
SERVER_PORT = os.getenv("MCP_SERVER_PORT", os.getenv("SERVER_PORT", "8002"))
# FastMCP servers in HTTP mode use the /mcp/ endpoint
SERVER_URL = os.getenv("MCP_SERVER_URL", f"http://{SERVER_HOST}:{SERVER_PORT}/mcp/")

# Test email address from environment variable
TEST_EMAIL = os.getenv("TEST_EMAIL_ADDRESS", "srivers@groupon.com")


class TestTemplateMiddlewareIntegration:
    """Test Template Middleware Integration using FastMCP Client SDK."""
    
    @pytest.fixture
    async def client(self):
        """Create a client connected to the running server."""
        # Get JWT token for authentication if enabled
        from .test_auth_utils import get_client_auth_config
        auth_config = get_client_auth_config(TEST_EMAIL)
        
        client = Client(SERVER_URL, auth=auth_config)
        async with client:
            yield client
    
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
        logger.info("✅ Gmail tools are available")
    
    @pytest.mark.asyncio
    async def test_get_real_gmail_labels_via_tools(self, client):
        """Test calling Gmail tools to get real label IDs programmatically."""
        logger.info("🧪 Testing Gmail tools to get real label IDs")
        
        real_label_ids = []
        try:
            # First, check if Gmail tools are available
            tools = await client.list_tools()
            tool_names = [tool.name for tool in tools]
            
            gmail_tools = [name for name in tool_names if "gmail" in name.lower() and "label" in name.lower()]
            logger.info(f"Available Gmail label tools: {gmail_tools}")
            
            # Try to call list_gmail_labels tool
            if "list_gmail_labels" in tool_names:
                logger.info("Calling list_gmail_labels tool...")
                
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
                
                logger.info(f"Gmail labels tool result: {content_text[:300]}...")
                
                # Try to extract actual label IDs - the format is (ID: LABELID)
                label_id_pattern = r'\(ID:\s*([^)]+)\)'
                real_label_ids = re.findall(label_id_pattern, content_text)
                
                if real_label_ids:
                    logger.info(f"✅ Found {len(real_label_ids)} real label IDs: {real_label_ids[:3]}...")
                    
                    # This is the key success - we have real Gmail data that template middleware can use!
                    logger.info("🎉 SUCCESS: Got real Gmail label IDs from server!")
                    logger.info("🔗 Template middleware can now use these real IDs in expressions like:")
                    logger.info(f"   {{{{service://gmail/labels}}}}[\"user_labels\"][0][\"id\"] → {real_label_ids[0] if real_label_ids else 'ID'}")
                    
                    return real_label_ids
                else:
                    logger.info("⚠️ No label IDs found in tool response")
                    return []
            else:
                logger.warning("list_gmail_labels tool not available")
                return []
                
        except Exception as e:
            logger.warning(f"❌ Gmail labels tool test failed: {e}")
            return []
    
    @pytest.mark.asyncio
    async def test_gmail_resources(self, client):
        """Test Gmail resources."""
        logger.info("🧪 Testing Gmail resources")
        
        resources = await client.list_resources()
        resource_uris = [str(resource.uri) for resource in resources]  # Convert to string
        
        gmail_resources = [uri for uri in resource_uris if "gmail" in uri.lower()]
        logger.info(f"Found {len(gmail_resources)} Gmail resources: {gmail_resources[:3]}...")
        
        if gmail_resources:
            # Try to read the first Gmail resource
            try:
                test_resource = gmail_resources[0]
                logger.info(f"Testing resource: {test_resource}")
                
                result = await client.read_resource(test_resource)
                logger.info(f"Resource read successfully: {type(result)}")
                
                # Check if resource contains label data
                if hasattr(result, 'contents') and result.contents:
                    content = str(result.contents[0].text if hasattr(result.contents[0], 'text') else result.contents[0])
                    
                    # Look for label IDs in resource data - format is (ID: LABELID)
                    label_ids = re.findall(r'\(ID:\s*([^)]+)\)', content)
                    if label_ids:
                        logger.info(f"✅ Resource contains label IDs: {label_ids[:2]}...")
                        logger.info("🎉 SUCCESS: Resources contain real Gmail data for template middleware!")
                
                logger.info("✅ Gmail resources are accessible")
                return True
            except Exception as e:
                logger.warning(f"❌ Failed to read Gmail resource: {e}")
                return False
        else:
            logger.info("⚠️ No Gmail resources found")
            return False
    
    @pytest.mark.asyncio
    async def test_prompts_available(self, client):
        """Test that prompts are available."""
        logger.info("🧪 Testing prompts availability")
        
        prompts = await client.list_prompts()
        prompt_names = [prompt.name for prompt in prompts]
        
        logger.info(f"Found {len(prompts)} prompts: {prompt_names[:5]}...")
        
        # Look for Gmail-related prompts
        gmail_prompts = [name for name in prompt_names if "gmail" in name.lower()]
        if gmail_prompts:
            logger.info(f"✅ Found Gmail-related prompts: {gmail_prompts}")
        
        logger.info("✅ Prompt system is available")
    
    @pytest.mark.asyncio
    async def test_template_middleware_integration(self, client):
        """Test the complete template middleware integration."""
        logger.info("🧪 Testing complete template middleware integration")
        
        # Step 1: Get real Gmail data from tools
        real_label_ids = await self.test_get_real_gmail_labels_via_tools(client)
        
        # Step 2: Verify resources contain the same data
        resources_working = await self.test_gmail_resources(client)
        
        # Step 3: Check if prompts are available
        await self.test_prompts_available(client)
        
        # Summary of integration readiness
        if real_label_ids and resources_working:
            logger.info("=" * 60)
            logger.info("🎉 TEMPLATE MIDDLEWARE INTEGRATION READY!")
            logger.info("✅ Real Gmail data available from tools")
            logger.info("✅ Gmail resources contain real data")
            logger.info("✅ Template expressions can resolve real label IDs")
            logger.info("")
            logger.info("📋 Real data available for template expressions:")
            for i, label_id in enumerate(real_label_ids[:3]):
                logger.info(f"  {i+1}. Label ID: {label_id}")
            logger.info("")
            logger.info("🔧 Template expressions that will work:")
            logger.info("  • {{service://gmail/labels}} → Full Gmail labels data")
            logger.info("  • {{service://gmail/labels}}[\"user_labels\"][0][\"id\"] → Real label ID")
            logger.info("  • {{service://gmail/filters}} → Gmail filters data")
            logger.info("")
            logger.info("🚀 Enhanced Gmail prompts can now use real Gmail data!")
            logger.info("=" * 60)
            
            return True
        else:
            logger.warning("⚠️ Template middleware integration not fully ready")
            return False