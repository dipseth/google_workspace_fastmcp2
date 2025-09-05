"""Test suite for debugging service resource functionality using FastMCP Client SDK."""

import pytest
import json
import logging
from typing import Any, Dict, List
from .base_test_config import TEST_EMAIL
from .test_helpers import ToolTestRunner, TestResponseValidator, print_test_result

# Set up logging to see what's happening
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


@pytest.mark.service("debug")
@pytest.mark.auth_required
class TestServiceResourcesDebug:
    """Test and debug service resources functionality through MCP server."""
    
    @pytest.mark.asyncio
    async def test_service_lists_resource(self, client):
        """Test the service://gmail/lists resource to verify it works."""
        print("\n🔍 TESTING service://gmail/lists RESOURCE")
        print("=" * 60)
        
        # Test accessing the lists resource
        result = await client.read_resource("service://gmail/lists")
        
        assert result is not None
        
        # Handle list return format
        if isinstance(result, list):
            assert len(result) > 0
            content = result[0]
        else:
            assert len(result.contents) > 0
            content = result.contents[0]
        
        print(f"✅ Resource accessed successfully")
        print(f"📋 Content type: {content.mimeType if hasattr(content, 'mimeType') else 'text/plain'}")
        print(f"📄 Content preview (first 500 chars):")
        print(content.text[:500] if len(content.text) > 500 else content.text)
        
        # Parse and validate the JSON response
        data = json.loads(content.text)
        print(f"\n📊 Parsed data keys: {list(data.keys())}")
        
        assert "service" in data
        assert data["service"] == "gmail"
        assert "list_types" in data
        
        # Check that labels is in the list types
        list_types = data["list_types"]
        list_type_names = [lt["name"] for lt in list_types]
        print(f"📦 Available list types: {list_type_names}")
        
        assert "labels" in list_type_names, "Labels should be in Gmail list types"
        assert "filters" in list_type_names, "Filters should be in Gmail list types"
        
        print("✅ service://gmail/lists resource working correctly!")
    
    @pytest.mark.asyncio
    async def test_gmail_labels_resource(self, client):
        """Test the service://gmail/labels resource to debug empty results."""
        print("\n🔍 TESTING service://gmail/labels RESOURCE")
        print("=" * 60)
        
        # First, verify the tool exists
        tools = await client.list_tools()
        tool_names = [tool.name for tool in tools]
        print(f"📋 Available tools count: {len(tool_names)}")
        
        # Check if list_gmail_labels tool exists
        has_labels_tool = "list_gmail_labels" in tool_names
        print(f"🔧 list_gmail_labels tool available: {has_labels_tool}")
        
        if has_labels_tool:
            # Test calling the tool directly first
            print("\n📞 Testing direct tool call...")
            tool_result = await client.call_tool("list_gmail_labels", {
                "user_google_email": TEST_EMAIL
            })
            
            tool_content = tool_result.content[0].text
            print(f"🔧 Tool result preview (first 500 chars):")
            print(tool_content[:5000] if len(tool_content) > 5000 else tool_content)
            
            # Check if it's an error or actual data
            if "authentication" in tool_content.lower() or "credentials" in tool_content.lower():
                print("⚠️  Tool requires authentication")
            else:
                print("✅ Tool returned data (or handled error gracefully)")
        
        # Now test the resource
        print("\n📡 Testing resource access...")
        result = await client.read_resource("service://gmail/labels")
        
        assert result is not None
        
        # Handle list return format
        if isinstance(result, list):
            assert len(result) > 0
            content = result[0]
        else:
            assert len(result.contents) > 0
            content = result.contents[0]
        
        print(f"✅ Resource accessed successfully")
        print(f"📋 Content type: {content.mimeType if hasattr(content, 'mimeType') else 'text/plain'}")
        
        # Parse the JSON response
        data = json.loads(content.text)
        print(f"\n📊 Parsed data structure:")
        print(f"  - Keys: {list(data.keys())}")
        print(f"  - Service: {data.get('service', 'N/A')}")
        print(f"  - List type: {data.get('list_type', 'N/A')}")
        print(f"  - Count: {data.get('count', 'N/A')}")
        print(f"  - Items: {data.get('items', 'N/A')}")
        print(f"  - Data: {data.get('data', 'N/A')}")
        
        # Debug the actual content
        print(f"\n📄 Full response:")
        print(json.dumps(data, indent=2))
        
        # Check why items might be empty
        if data.get("count") == 0 or (data.get("items") is not None and len(data.get("items", [])) == 0):
            print("\n⚠️  ISSUE DETECTED: Empty items in response!")
            print("Possible causes:")
            print("  1. Authentication issue (no valid user email)")
            print("  2. Tool output parsing issue in _parse_list_result()")
            print("  3. Tool not being called correctly")
            print("  4. Tool returning different format than expected")
            
            # Check for authentication hints
            if data.get("error"):
                print(f"  ❌ Error in response: {data['error']}")
        else:
            print(f"\n✅ Resource returned {data.get('count', 0)} items")
    
    @pytest.mark.asyncio
    async def test_compare_tool_vs_resource(self, client):
        """Compare direct tool call vs resource access to identify differences."""
        print("\n🔬 COMPARING TOOL vs RESOURCE OUTPUT")
        print("=" * 60)
        
        tools = await client.list_tools()
        tool_names = [tool.name for tool in tools]
        
        if "list_gmail_labels" not in tool_names:
            pytest.skip("list_gmail_labels tool not available")
        
        # 1. Call the tool directly
        print("\n1️⃣ DIRECT TOOL CALL:")
        tool_result = await client.call_tool("list_gmail_labels", {
            "user_google_email": TEST_EMAIL
        })
        tool_content = tool_result.content[0].text
        print(f"   Length: {len(tool_content)} chars")
        print(f"   Type: {type(tool_content)}")
        print(f"   Preview: {tool_content[:200]}...")
        
        # 2. Access via resource
        print("\n2️⃣ RESOURCE ACCESS:")
        resource_result = await client.read_resource("service://gmail/labels")
        
        # Handle different return formats
        if isinstance(resource_result, list):
            # It's a list of resource contents
            resource_content = resource_result[0].text if resource_result else "{}"
        else:
            # It's an object with contents
            resource_content = resource_result.contents[0].text
        
        resource_data = json.loads(resource_content)
        print(f"   Length: {len(resource_content)} chars")
        print(f"   Type: JSON")
        print(f"   Structure: {list(resource_data.keys())}")
        print(f"   Items count: {resource_data.get('count', 'N/A')}")
        
        # 3. Analysis
        print("\n3️⃣ ANALYSIS:")
        
        # Check if tool returns structured data
        try:
            # Try to parse tool output as JSON
            tool_data = json.loads(tool_content)
            print("   ✅ Tool returns JSON data")
            print(f"   Tool data keys: {list(tool_data.keys()) if isinstance(tool_data, dict) else 'List'}")
        except json.JSONDecodeError:
            print("   ⚠️  Tool returns text/formatted output (not JSON)")
            print("   This might be why parsing fails in _parse_list_result()")
            
            # Check for common patterns in text output
            if "•" in tool_content:
                print("   📌 Tool uses bullet points (•) for formatting")
            if "ID:" in tool_content:
                print("   📌 Tool includes 'ID:' markers")
            if "Label:" in tool_content:
                print("   📌 Tool includes 'Label:' markers")
        
        # Check resource data structure
        print(f"\n   Resource data analysis:")
        if resource_data.get("items") is not None:
            print(f"   - Items type: {type(resource_data['items'])}")
            print(f"   - Items count: {len(resource_data['items'])}")
            if len(resource_data['items']) > 0:
                print(f"   - First item: {resource_data['items'][0]}")
        elif resource_data.get("data") is not None:
            print(f"   - Data type: {type(resource_data['data'])}")
            print(f"   - Data value: {resource_data['data']}")
        
        # Identify the issue
        print("\n4️⃣ DIAGNOSIS:")
        if resource_data.get("count") == 0 or (resource_data.get("items") == []):
            print("   ❌ PROBLEM IDENTIFIED: Resource returns empty items")
            print("   The _parse_list_result() method is not correctly parsing tool output")
            print("   Need to fix the parsing logic to handle the actual tool output format")
        else:
            print("   ✅ Resource correctly populates items from tool output")
    
    @pytest.mark.asyncio
    async def test_gmail_filters_resource(self, client):
        """Test Gmail filters resource as a comparison."""
        print("\n🔍 TESTING service://gmail/filters RESOURCE (for comparison)")
        print("=" * 60)
        
        # Test the filters resource
        result = await client.read_resource("service://gmail/filters")
        
        assert result is not None
        
        # Handle list return format
        if isinstance(result, list):
            assert len(result) > 0
            content = result[0]
        else:
            assert len(result.contents) > 0
            content = result.contents[0]
        
        data = json.loads(content.text)
        
        print(f"📊 Filters resource response:")
        print(f"  - Service: {data.get('service', 'N/A')}")
        print(f"  - List type: {data.get('list_type', 'N/A')}")
        print(f"  - Count: {data.get('count', 'N/A')}")
        print(f"  - Has items: {data.get('items') is not None}")
        
        if data.get("items"):
            print(f"  - Items count: {len(data['items'])}")
            if len(data['items']) > 0:
                print(f"  - Sample item: {data['items'][0]}")
        
        # Compare with labels behavior
        print("\n📊 Comparison with labels:")
        labels_result = await client.read_resource("service://gmail/labels")
        
        # Handle list return format
        if isinstance(labels_result, list):
            labels_content = labels_result[0]
        else:
            labels_content = labels_result.contents[0]
        
        labels_data = json.loads(labels_content.text)
        
        print(f"  Filters: count={data.get('count', 0)}, has_items={data.get('items') is not None}")
        print(f"  Labels:  count={labels_data.get('count', 0)}, has_items={labels_data.get('items') is not None}")
        
        if data.get("count", 0) > 0 and labels_data.get("count", 0) == 0:
            print("\n⚠️  INCONSISTENCY: Filters work but labels don't!")
            print("  This suggests the parsing logic is different between the two")

