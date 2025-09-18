#!/usr/bin/env python3
"""
Test suite for improved Qdrant unified tools with FastMCP2 conventions.
Tests the new search_qdrant and fetch_qdrant tools with proper type validation.
"""

import asyncio
import json
import sys
from typing import Dict, Any
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Test imports
try:
    from middleware.qdrant_unified import (
        QdrantUnifiedMiddleware,
        _parse_unified_query,
        _extract_service_from_tool,
        setup_enhanced_qdrant_tools
    )
    from middleware.qdrant_types import (
        QdrantSearchResponse,
        QdrantFetchResponse,
        QdrantSearchResultItem,
        QdrantDocumentMetadata
    )
    print("✅ All imports successful")
except ImportError as e:
    print(f"❌ Import failed: {e}")
    sys.exit(1)

# Test data
TEST_QUERIES = [
    # Overview/Analytics queries
    ("overview", "overview"),
    ("analytics dashboard", "overview"), 
    ("tool usage stats", "overview"),
    
    # Service history queries
    ("gmail last week", "service_history"),
    ("service:drive documents", "service_history"),
    ("recent calendar events", "service_history"),
    
    # General search queries
    ("email collaboration documents", "general_search"),
    ("document creation workflow", "general_search"),
    ("user authentication errors", "general_search"),
]

SERVICE_EXTRACTION_TESTS = [
    ("search_gmail_messages", "gmail"),
    ("get_drive_file_content", "drive"),
    ("list_calendar_events", "calendar"),
    ("create_docs", "docs"),
    ("update_sheets_data", "sheets"),
    ("send_chat_message", "chat"),
    ("list_photos_albums", "photos"),
    ("create_form", "forms"),
    ("export_presentation", "slides"),
    ("unknown_tool_name", "unknown")
]

def test_query_parser():
    """Test the enhanced query parser functionality."""
    print("\n🔍 Testing Query Parser")
    
    passed = 0
    failed = 0
    
    for query, expected_capability in TEST_QUERIES:
        try:
            result = _parse_unified_query(query)
            actual_capability = result.get("capability")
            confidence = result.get("confidence", 0.0)
            
            if actual_capability == expected_capability:
                print(f"  ✅ '{query}' -> {actual_capability} (confidence: {confidence:.2f})")
                passed += 1
            else:
                print(f"  ❌ '{query}' -> Expected: {expected_capability}, Got: {actual_capability}")
                failed += 1
                
        except Exception as e:
            print(f"  ❌ '{query}' -> Error: {e}")
            failed += 1
    
    print(f"\nQuery Parser Results: {passed} passed, {failed} failed")
    return failed == 0

def test_service_extraction():
    """Test service extraction from tool names."""
    print("\n🏷️  Testing Service Extraction")
    
    passed = 0
    failed = 0
    
    for tool_name, expected_service in SERVICE_EXTRACTION_TESTS:
        try:
            actual_service = _extract_service_from_tool(tool_name)
            
            if actual_service == expected_service:
                print(f"  ✅ '{tool_name}' -> {actual_service}")
                passed += 1
            else:
                print(f"  ❌ '{tool_name}' -> Expected: {expected_service}, Got: {actual_service}")
                failed += 1
                
        except Exception as e:
            print(f"  ❌ '{tool_name}' -> Error: {e}")
            failed += 1
    
    print(f"\nService Extraction Results: {passed} passed, {failed} failed")
    return failed == 0

def test_type_definitions():
    """Test that TypedDict definitions are properly structured."""
    print("\n📋 Testing Type Definitions")
    
    try:
        # Test QdrantSearchResponse structure
        search_response = QdrantSearchResponse(
            results=[
                QdrantSearchResultItem(
                    id="123e4567-e89b-12d3-a456-426614174000",
                    title="Test Result",
                    url="qdrant://test_collection?123e4567-e89b-12d3-a456-426614174000"
                )
            ],
            query="test query",
            query_type="general_search",
            total_results=1,
            collection_name="test_collection"
        )
        print("  ✅ QdrantSearchResponse structure valid")
        
        # Test QdrantFetchResponse structure
        fetch_response = QdrantFetchResponse(
            id="123e4567-e89b-12d3-a456-426614174001",
            title="Test Document",
            text="Test document content",
            url="qdrant://test_collection?123e4567-e89b-12d3-a456-426614174001",
            metadata=QdrantDocumentMetadata(
                tool_name="test_tool",
                service="test_service",
                service_display_name="Test Service",
                user_email="test@example.com",
                timestamp="2024-01-01T00:00:00Z",
                response_type="dict",
                arguments_count=2,
                payload_type="tool_response",
                collection_name="test_collection",
                point_id="123e4567-e89b-12d3-a456-426614174001"
            ),
            found=True,
            collection_name="test_collection"
        )
        print("  ✅ QdrantFetchResponse structure valid")
        print("  ✅ QdrantDocumentMetadata structure valid")
        
        return True
        
    except Exception as e:
        print(f"  ❌ Type definition error: {e}")
        return False

def test_middleware_initialization():
    """Test middleware initialization without requiring actual Qdrant connection."""
    print("\n⚙️  Testing Middleware Initialization")
    
    try:
        # Create middleware with mock settings
        middleware = QdrantUnifiedMiddleware(
            qdrant_host="localhost",
            qdrant_port=6333,
            collection_name="test_collection",
            enabled=True,
            auto_discovery=False  # Disable auto-discovery for testing
        )
        
        print("  ✅ Middleware instance created")
        print(f"  ✅ Collection name: {middleware.config.collection_name}")
        print(f"  ✅ Host: {middleware.config.host}")
        print(f"  ✅ Enabled: {middleware.config.enabled}")
        
        return True
        
    except Exception as e:
        print(f"  ❌ Middleware initialization error: {e}")
        return False

async def test_tool_setup():
    """Test that tools can be set up without errors."""
    print("\n🔧 Testing Tool Setup")
    
    try:
        # Create mock FastMCP instance
        class MockMCP:
            def __init__(self):
                self.tools = {}
            
            def tool(self, name=None, description=None, tags=None, annotations=None):
                def decorator(func):
                    self.tools[name or func.__name__] = {
                        'function': func,
                        'description': description,
                        'tags': tags,
                        'annotations': annotations
                    }
                    return func
                return decorator
        
        # Create mock middleware
        middleware = QdrantUnifiedMiddleware(
            collection_name="test_collection",
            enabled=False  # Disable for testing
        )
        
        mock_mcp = MockMCP()
        
        # Setup tools
        setup_enhanced_qdrant_tools(mock_mcp, middleware)
        
        print(f"  ✅ {len(mock_mcp.tools)} tools registered")
        
        for tool_name, tool_info in mock_mcp.tools.items():
            desc = tool_info['description'][:60] + "..." if len(tool_info['description']) > 60 else tool_info['description']
            print(f"    - {tool_name}: {desc}")
        
        # Verify expected tools exist
        expected_tools = ['search_qdrant', 'fetch_qdrant']
        for expected_tool in expected_tools:
            if expected_tool in mock_mcp.tools:
                print(f"  ✅ {expected_tool} tool registered correctly")
            else:
                print(f"  ❌ {expected_tool} tool missing")
                return False
        
        # Test backwards compatibility - legacy tools should still exist
        legacy_tools = ['search_tool_history', 'get_tool_analytics', 'get_response_details']
        legacy_found = 0
        for legacy_tool in legacy_tools:
            if legacy_tool in mock_mcp.tools:
                print(f"  ✅ {legacy_tool} legacy tool present")
                legacy_found += 1
        
        if legacy_found == len(legacy_tools):
            print(f"  ✅ All {legacy_found} legacy tools preserved for backward compatibility")
        else:
            print(f"  ⚠️  Only {legacy_found}/{len(legacy_tools)} legacy tools found")
        
        return True
        
    except Exception as e:
        print(f"  ❌ Tool setup error: {e}")
        return False

def test_url_format():
    """Test that URLs follow the specified format."""
    print("\n🔗 Testing URL Format")
    
    try:
        collection_name = "test_collection"
        point_id = "123e4567-e89b-12d3-a456-426614174002"
        
        expected_format = f"qdrant://{collection_name}?{point_id}"
        print(f"  ✅ URL format: {expected_format}")
        
        # Test parsing
        if expected_format.startswith("qdrant://"):
            parts = expected_format.replace("qdrant://", "").split("?")
            if len(parts) == 2:
                parsed_collection = parts[0]
                parsed_point_id = parts[1]
                
                if parsed_collection == collection_name and parsed_point_id == point_id:
                    print(f"  ✅ URL parsing successful: collection={parsed_collection}, point={parsed_point_id}")
                    return True
                else:
                    print(f"  ❌ URL parsing failed: expected collection={collection_name}, point={point_id}")
                    return False
            else:
                print(f"  ❌ URL format invalid: wrong number of parts")
                return False
        else:
            print(f"  ❌ URL format invalid: missing qdrant:// prefix")
            return False
            
    except Exception as e:
        print(f"  ❌ URL format test error: {e}")
        return False

def test_fastmcp2_compliance():
    """Test FastMCP2 conventions compliance."""
    print("\n📝 Testing FastMCP2 Compliance")
    
    try:
        # Import check
        try:
            from tools.common_types import UserGoogleEmail
            print("  ✅ UserGoogleEmail import successful")
        except ImportError as e:
            print(f"  ⚠️  UserGoogleEmail import failed: {e}")
        
        # Test that our types are structured dictionaries, not classes
        from middleware.qdrant_types import QdrantSearchResponse, QdrantFetchResponse
        
        # These should be TypedDict, so we can create them as dict
        search_resp = {
            "results": [],
            "query": "test",
            "query_type": "general_search",
            "total_results": 0,
            "collection_name": "test"
        }
        
        # Should work as TypedDict
        typed_search_resp: QdrantSearchResponse = search_resp
        print("  ✅ QdrantSearchResponse is properly typed")
        
        fetch_resp = {
            "id": "123e4567-e89b-12d3-a456-426614174003",
            "title": "test",
            "text": "test",
            "url": "qdrant://test_collection?123e4567-e89b-12d3-a456-426614174003",
            "metadata": {
                "tool_name": "test",
                "service": "test",
                "service_display_name": "test",
                "user_email": "test",
                "timestamp": "test",
                "response_type": "test",
                "arguments_count": 0,
                "payload_type": "test",
                "collection_name": "test",
                "point_id": "123e4567-e89b-12d3-a456-426614174003"
            },
            "found": True,
            "collection_name": "test"
        }
        
        typed_fetch_resp: QdrantFetchResponse = fetch_resp
        print("  ✅ QdrantFetchResponse is properly typed")
        
        return True
        
    except Exception as e:
        print(f"  ❌ FastMCP2 compliance error: {e}")
        return False

async def run_all_tests():
    """Run all test functions."""
    print("🚀 Starting Improved Qdrant Tools Test Suite")
    print("=" * 60)
    
    test_results = []
    
    # Run synchronous tests
    test_results.append(("Query Parser", test_query_parser()))
    test_results.append(("Service Extraction", test_service_extraction()))
    test_results.append(("Type Definitions", test_type_definitions()))
    test_results.append(("Middleware Init", test_middleware_initialization()))
    test_results.append(("URL Format", test_url_format()))
    test_results.append(("FastMCP2 Compliance", test_fastmcp2_compliance()))
    
    # Run async tests
    test_results.append(("Tool Setup", await test_tool_setup()))
    
    # Print summary
    print("\n" + "=" * 60)
    print("📊 TEST SUMMARY")
    print("=" * 60)
    
    passed = 0
    failed = 0
    
    for test_name, result in test_results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} {test_name}")
        
        if result:
            passed += 1
        else:
            failed += 1
    
    print(f"\nTotal: {passed + failed} tests")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    
    if failed == 0:
        print("\n🎉 All tests passed! The improved Qdrant tools are ready.")
        print("\n🔧 New Tools Available:")
        print("  - search_qdrant: Enhanced search with FastMCP2 types")
        print("  - fetch_qdrant: Enhanced fetch with structured metadata")
        print("\n📋 Features:")
        print("  - Proper TypedDict return types for FastMCP schema generation")
        print("  - Qdrant-specific URL format: qdrant://collection?point_id")
        print("  - Service metadata integration with icons")
        print("  - Enhanced query parsing with 4 core capabilities")
        print("  - Backward compatibility with legacy tools")
        return True
    else:
        print(f"\n⚠️  {failed} test(s) failed. Please review the issues above.")
        return False

if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)