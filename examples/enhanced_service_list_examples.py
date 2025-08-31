"""
Enhanced Service List Resources - Usage Examples

This module demonstrates how to use the enhanced service list resources with:
- Rich documentation and metadata
- Default values and pagination
- Tool transformations
- Error handling with suggestions
"""

import asyncio
import json
from typing_extensions import Dict, Any, List
from fastmcp import FastMCP, Context
from resources.service_list_resources_enhanced import (
    setup_service_list_resources,
    ServiceMetadata,
    ServiceRequest,
    ServiceListRequest,
    ServiceItemRequest,
    get_supported_services,
    get_supported_service_documentation,
    create_enhanced_tool,
    ServiceListDiscovery,
    SupportedService
)
from fastmcp.tools import Tool
from fastmcp.tools.tool_transform import ArgTransform


# ============================================================================
# EXAMPLE 1: BASIC USAGE WITH DEFAULTS
# ============================================================================

async def example_basic_usage():
    """Demonstrate basic usage with automatic defaults."""
    
    # Create FastMCP instance
    mcp = FastMCP(name="ServiceListExample")
    
    # Setup enhanced resources
    setup_service_list_resources(mcp)
    
    # Create a mock context with user email
    ctx = Context()
    ctx.metadata = {"user_email": "user@example.com"}
    
    print("=" * 60)
    print("EXAMPLE 1: Basic Usage with Defaults")
    print("=" * 60)
    
    # 1. Get available services with documentation
    services = get_supported_services()
    print(f"\n📋 Available Services ({len(services)}):")
    for service in services:
        info = ServiceMetadata.get_service_info(service)
        print(f"  {info['icon']} {service}: {info['description']}")
    
    # Show the generated documentation
    print("\n📖 Service Documentation:")
    doc = get_supported_service_documentation()
    print(doc[:200] + "..." if len(doc) > 200 else doc)
    
    # 2. Get list types for Gmail with defaults
    print("\n📧 Gmail List Types:")
    # This will use default pagination (page_size=25 for Gmail)
    request = ServiceListRequest(
        service="gmail",
        list_type="filters"
        # page_size will default to 25 (Gmail's default)
        # page_token defaults to None
    )
    print(f"  Request with defaults: {request.model_dump()}")
    
    # 3. Demonstrate service-specific defaults
    print("\n🔧 Service-Specific Defaults:")
    for service in ["gmail", "drive", "photos"]:
        info = ServiceMetadata.get_service_info(service)
        print(f"  {info['icon']} {service}:")
        print(f"    - Default page size: {info['default_page_size']}")
        print(f"    - Max page size: {info['max_page_size']}")
        print(f"    - Categories: {', '.join(info['categories'])}")


# ============================================================================
# EXAMPLE 2: ENHANCED DOCUMENTATION GENERATION
# ============================================================================

async def example_documentation_generation():
    """Generate comprehensive documentation for services."""
    
    print("\n" + "=" * 60)
    print("EXAMPLE 2: Documentation Generation")
    print("=" * 60)
    
    # Generate documentation for Gmail service
    gmail_doc = ServiceMetadata.generate_service_documentation("gmail")
    print("\n📚 Generated Gmail Documentation:")
    print(gmail_doc)
    
    # Generate documentation snippet for all services
    print("\n📖 Quick Reference - All Services:")
    for service in get_supported_services()[:3]:  # Show first 3 as example
        info = ServiceMetadata.get_service_info(service)
        print(f"\n{info['icon']} **{info['display_name']}**")
        print(f"  Version: {info['version']}")
        print(f"  Use Cases: {', '.join(info['common_use_cases'][:2])}")
        
        # Show features
        if info['features']:
            print(f"  Key Features:")
            for feature, desc in list(info['features'].items())[:2]:
                print(f"    • {feature}: {desc}")


# ============================================================================
# EXAMPLE 3: TOOL TRANSFORMATION WITH ENHANCED ARGS
# ============================================================================

async def example_tool_transformation():
    """Demonstrate tool transformation for better documentation."""
    
    print("\n" + "=" * 60)
    print("EXAMPLE 3: Tool Transformation")
    print("=" * 60)
    
    # Create a sample tool
    @Tool()
    async def list_service_items(service: str, list_type: str, page_size: int = 10):
        """List items from a service."""
        return {"service": service, "list_type": list_type, "page_size": page_size}
    
    # Transform with enhanced documentation and defaults
    enhanced_tool = Tool.from_tool(
        list_service_items,
        name="list_service_items_enhanced",
        description="""
        List items from Google services with comprehensive metadata.
        
        This enhanced version provides:
        - Automatic pagination with service-specific defaults
        - Rich metadata for each item
        - Example IDs for testing
        - Required scope information
        """,
        transform_args={
            "service": ArgTransform(
                description=f"Google service. Options: {', '.join(get_supported_services())}\n\n{get_supported_service_documentation()}"
            ),
            "list_type": ArgTransform(
                description="Type of list (e.g., 'filters' for Gmail, 'albums' for Photos)"
            ),
            "page_size": ArgTransform(
                description="Items per page. Uses service-specific default if not provided.",
                default=25  # Override default
            )
        },
        tags={"enhanced", "service", "list", "pagination"},
        meta={
            "version": "2.0",
            "enhanced": True,
            "supports_defaults": True
        }
    )
    
    print("\n🔧 Original Tool:")
    print(f"  Name: {list_service_items.name}")
    print(f"  Description: {list_service_items.description}")
    print(f"  Parameters: service, list_type, page_size(=10)")
    
    print("\n✨ Enhanced Tool:")
    print(f"  Name: {enhanced_tool.name}")
    print(f"  Description: {enhanced_tool.description[:100]}...")
    print(f"  Tags: {', '.join(enhanced_tool.tags)}")
    print(f"  Meta: {enhanced_tool.meta}")
    
    # Test the enhanced tool
    result = await enhanced_tool.function(service="gmail", list_type="filters")
    print(f"\n📊 Enhanced Tool Result: {result}")


# ============================================================================
# EXAMPLE 4: ERROR HANDLING WITH SUGGESTIONS
# ============================================================================

async def example_error_handling():
    """Demonstrate enhanced error handling with helpful suggestions."""
    
    print("\n" + "=" * 60)
    print("EXAMPLE 4: Enhanced Error Handling")
    print("=" * 60)
    
    # Test invalid service with suggestions
    print("\n❌ Testing Invalid Service:")
    try:
        request = ServiceRequest(service="gmal")  # Typo in 'gmail'
    except ValueError as e:
        error_msg = str(e)
        print(f"  Error: {error_msg}")
        
        # Error includes suggestions for services starting with 'g'
        if "Did you mean:" in error_msg:
            print("  ✅ Error includes helpful suggestions!")
    
    # Test with partial match
    print("\n🔍 Testing Partial Match:")
    test_cases = [
        ("cal", ["calendar"]),  # Should suggest 'calendar'
        ("dr", ["drive", "docs"]),  # Should suggest 'drive' and 'docs'
        ("ph", ["photos"]),  # Should suggest 'photos'
    ]
    
    for partial, expected in test_cases:
        suggestions = [s for s in get_supported_services() 
                      if s.startswith(partial)]
        print(f"  '{partial}' → Suggestions: {', '.join(suggestions)}")
        assert any(e in suggestions for e in expected), f"Expected {expected} in {suggestions}"
    
    # Demonstrate error response structure
    print("\n📋 Error Response Structure:")
    error_response = {
        "error": "Service 'xyz' not supported",
        "error_code": "INVALID_SERVICE",
        "service": "xyz",
        "available_services": get_supported_services(),
        "suggestions": ["No services start with 'x'"],
        "documentation_url": "https://docs.fastmcp2.com/services/"
    }
    print(json.dumps(error_response, indent=2))


# ============================================================================
# EXAMPLE 5: PAGINATION WITH DEFAULTS
# ============================================================================

async def example_pagination():
    """Demonstrate pagination with service-specific defaults."""
    
    print("\n" + "=" * 60)
    print("EXAMPLE 5: Pagination with Defaults")
    print("=" * 60)
    
    # Create discovery instance
    mcp = FastMCP(name="PaginationExample")
    discovery = ServiceListDiscovery(mcp)
    
    print("\n📄 Pagination Support by Service:")
    
    services_to_check = ["gmail", "drive", "photos", "calendar"]
    for service in services_to_check:
        info = ServiceMetadata.get_service_info(service)
        list_types = discovery.get_service_lists(service)
        
        print(f"\n{info['icon']} {service.upper()}:")
        print(f"  Default page size: {info['default_page_size']}")
        print(f"  Max page size: {info['max_page_size']}")
        
        for list_type_info in list_types:
            pagination = "✅" if list_type_info['supports_pagination'] else "❌"
            print(f"  - {list_type_info['name']}: {pagination} Pagination")
            if list_type_info['supports_pagination']:
                print(f"    Default: {list_type_info['default_page_size']} items/page")
    
    # Example pagination request
    print("\n📨 Example Pagination Request:")
    request = ServiceListRequest(
        service="gmail",
        list_type="filters",
        page_size=50,  # Override default
        page_token="next_page_xyz"
    )
    
    print(f"  Service: {request.service}")
    print(f"  List Type: {request.list_type}")
    print(f"  Page Size: {request.page_size} (overridden from default 25)")
    print(f"  Page Token: {request.page_token}")


# ============================================================================
# EXAMPLE 6: METADATA AND SCOPES
# ============================================================================

async def example_metadata_and_scopes():
    """Demonstrate metadata extraction and scope requirements."""
    
    print("\n" + "=" * 60)
    print("EXAMPLE 6: Metadata and OAuth Scopes")
    print("=" * 60)
    
    mcp = FastMCP(name="MetadataExample")
    discovery = ServiceListDiscovery(mcp)
    
    print("\n🔐 Required OAuth Scopes by Service:")
    
    for service in ["gmail", "drive", "calendar"]:
        info = ServiceMetadata.get_service_info(service)
        print(f"\n{info['icon']} {service.upper()}:")
        
        list_types = discovery.get_service_lists(service)
        for list_type_info in list_types:
            if list_type_info['required_scopes']:
                print(f"  {list_type_info['name']}:")
                for scope in list_type_info['required_scopes']:
                    print(f"    - {scope}")
    
    print("\n📊 Example IDs for Testing:")
    for service in ["gmail", "calendar", "photos"]:
        info = ServiceMetadata.get_service_info(service)
        print(f"\n{info['icon']} {service.upper()}:")
        
        list_types = discovery.get_service_lists(service)
        for list_type_info in list_types:
            if list_type_info['example_ids']:
                print(f"  {list_type_info['name']}:")
                for example_id in list_type_info['example_ids'][:2]:
                    print(f"    - {example_id}")


# ============================================================================
# EXAMPLE 7: COMPREHENSIVE WORKFLOW
# ============================================================================

async def example_comprehensive_workflow():
    """Demonstrate a complete workflow using all enhanced features."""
    
    print("\n" + "=" * 60)
    print("EXAMPLE 7: Comprehensive Workflow")
    print("=" * 60)
    
    # Setup
    mcp = FastMCP(name="ComprehensiveExample")
    setup_service_list_resources(mcp)
    discovery = ServiceListDiscovery(mcp)
    
    # Mock context
    ctx = Context()
    ctx.metadata = {"user_email": "user@example.com"}
    
    print("\n🚀 Complete Workflow: Gmail Filter Management")
    print("-" * 40)
    
    # Step 1: Validate service
    print("\n1️⃣ Validate Service:")
    try:
        service_req = ServiceRequest(service="gmail")
        print(f"   ✅ Service '{service_req.service}' is valid")
    except ValueError as e:
        print(f"   ❌ Error: {e}")
        return
    
    # Step 2: Get service metadata
    print("\n2️⃣ Get Service Metadata:")
    gmail_info = ServiceMetadata.get_service_info("gmail")
    print(f"   Name: {gmail_info['display_name']}")
    print(f"   Icon: {gmail_info['icon']}")
    print(f"   Categories: {', '.join(gmail_info['categories'])}")
    
    # Step 3: List available list types
    print("\n3️⃣ Available List Types:")
    list_types = discovery.get_service_lists("gmail")
    for lt in list_types:
        print(f"   - {lt['name']}: {lt['description']}")
        print(f"     Pagination: {'Yes' if lt['supports_pagination'] else 'No'}")
        print(f"     Default size: {lt['default_page_size']}")
    
    # Step 4: Create list request with defaults
    print("\n4️⃣ Create List Request:")
    list_req = ServiceListRequest(
        service="gmail",
        list_type="filters"
        # page_size defaults to 25
        # page_token defaults to None
    )
    print(f"   Service: {list_req.service}")
    print(f"   List Type: {list_req.list_type}")
    print(f"   Page Size: {list_req.page_size} (defaulted)")
    print(f"   Page Token: {list_req.page_token} (defaulted)")
    
    # Step 5: Handle pagination
    print("\n5️⃣ Pagination Example:")
    print("   First page: page_size=25, page_token=None")
    print("   Next page: page_size=25, page_token='abc123'")
    print("   Custom size: page_size=50, page_token=None")
    
    # Step 6: Get item details
    print("\n6️⃣ Get Item Details:")
    item_req = ServiceItemRequest(
        service="gmail",
        list_type="filters",
        item_id="filter_123",
        include_metadata=True,  # Default
        include_raw=False  # Default
    )
    print(f"   Item ID: {item_req.item_id}")
    print(f"   Include Metadata: {item_req.include_metadata}")
    print(f"   Include Raw: {item_req.include_raw}")
    
    # Step 7: Generate documentation
    print("\n7️⃣ Generate Documentation:")
    doc = ServiceMetadata.generate_service_documentation("gmail")
    print(f"   Generated {len(doc)} characters of documentation")
    print(f"   Preview: {doc[:150]}...")
    
    print("\n✅ Workflow Complete!")


# ============================================================================
# MAIN EXECUTION
# ============================================================================

async def main():
    """Run all examples."""
    
    print("""
╔══════════════════════════════════════════════════════════╗
║     Enhanced Service List Resources - Usage Examples     ║
╚══════════════════════════════════════════════════════════╝
    """)
    
    # Run examples
    await example_basic_usage()
    await example_documentation_generation()
    await example_tool_transformation()
    await example_error_handling()
    await example_pagination()
    await example_metadata_and_scopes()
    await example_comprehensive_workflow()
    
    print("""
╔══════════════════════════════════════════════════════════╗
║                    Examples Complete!                     ║
╚══════════════════════════════════════════════════════════╝
    """)


if __name__ == "__main__":
    asyncio.run(main())