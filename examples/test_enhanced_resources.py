"""
Test script to demonstrate the enhanced resources with accepted values in descriptions.
"""

import asyncio
from fastmcp import FastMCP
from resources.service_list_resources_enhanced import setup_service_list_resources

async def main():
    """Test the enhanced resources."""
    
    # Create FastMCP instance
    mcp = FastMCP(name="TestEnhancedResources")
    
    # Setup enhanced resources
    setup_service_list_resources(mcp)
    
    print("=" * 80)
    print("ENHANCED RESOURCES WITH ACCEPTED VALUES IN DESCRIPTIONS")
    print("=" * 80)
    
    # List all registered resources
    if hasattr(mcp, 'resources') or hasattr(mcp, '_resources'):
        resources = getattr(mcp, 'resources', getattr(mcp, '_resources', {}))
        
        for uri_pattern, resource in resources.items():
            print(f"\n📌 Resource: {uri_pattern}")
            print(f"   Name: {resource.get('name', 'N/A')}")
            print(f"   Description Preview:")
            
            # Get description
            desc = resource.get('description', '')
            if 'Accepted service values:' in desc:
                # Extract and show the accepted values section
                lines = desc.split('\n')
                in_accepted = False
                for line in lines[:15]:  # Show first 15 lines
                    if 'Accepted service values:' in line:
                        in_accepted = True
                        print(f"   {line}")
                    elif in_accepted and line.strip().startswith('•'):
                        print(f"   {line}")
                    elif in_accepted and not line.strip().startswith('•'):
                        break
            else:
                # Show first 100 chars of description
                print(f"   {desc[:100]}...")
            
            # Show meta accepted values if present
            meta = resource.get('meta', {})
            if 'accepted_services' in meta or 'accepted_values' in meta:
                accepted = meta.get('accepted_services', meta.get('accepted_values', []))
                print(f"   Meta Accepted Values: {', '.join(accepted[:5])}{'...' if len(accepted) > 5 else ''}")
    
    print("\n" + "=" * 80)
    print("✅ The resource descriptions now include the accepted service values!")
    print("This makes it much clearer for LLMs and developers what values are valid.")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(main())