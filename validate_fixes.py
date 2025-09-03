"""
Simple validation script to check our service list resource fixes.

This script validates that:
1. Calendar events configuration no longer has id_field set (should call real tool)
2. Gmail filters/labels configurations are correct
3. The service list configurations are properly structured
"""

import json
from resources.service_list_resources import ServiceListDiscovery
from fastmcp import FastMCP

def validate_fixes():
    """Validate that our fixes are correctly implemented."""
    print("🔍 Validating service list resource fixes...")
    
    # Create a mock FastMCP instance for testing
    mcp = FastMCP()
    discovery = ServiceListDiscovery(mcp)
    
    print("\n📅 Calendar Configuration:")
    calendar_config = discovery.SERVICE_MAPPINGS.get("calendar", {})
    
    # Test calendar events configuration
    events_config = calendar_config.get("events", {})
    print(f"  Events tool: {events_config.get('tool')}")
    print(f"  Events id_field: {events_config.get('id_field')}")
    
    if events_config.get("id_field") is None:
        print("  ✅ Calendar events id_field is None - will call real tool")
    else:
        print(f"  ❌ Calendar events id_field is set to: {events_config.get('id_field')} - will return example data")
    
    # Test calendar calendars configuration
    calendars_config = calendar_config.get("calendars", {})
    print(f"  Calendars tool: {calendars_config.get('tool')}")
    print(f"  Calendars id_field: {calendars_config.get('id_field')}")
    
    print("\n📧 Gmail Configuration:")
    gmail_config = discovery.SERVICE_MAPPINGS.get("gmail", {})
    
    # Test gmail filters configuration
    filters_config = gmail_config.get("filters", {})
    print(f"  Filters tool: {filters_config.get('tool')}")
    print(f"  Filters id_field: {filters_config.get('id_field')}")
    print(f"  Filters list_field: {filters_config.get('list_field')}")
    
    if filters_config.get("id_field") is None:
        print("  ✅ Gmail filters id_field is None - will call tool directly")
    else:
        print(f"  ❌ Gmail filters id_field is set: {filters_config.get('id_field')}")
    
    # Test gmail labels configuration
    labels_config = gmail_config.get("labels", {})
    print(f"  Labels tool: {labels_config.get('tool')}")
    print(f"  Labels id_field: {labels_config.get('id_field')}")
    print(f"  Labels list_field: {labels_config.get('list_field')}")
    
    if labels_config.get("id_field") is None:
        print("  ✅ Gmail labels id_field is None - will call tool directly")
    else:
        print(f"  ❌ Gmail labels id_field is set: {labels_config.get('id_field')}")
    
    print("\n🔧 Configuration Summary:")
    
    # Count services with proper configuration
    total_services = len(discovery.SERVICE_MAPPINGS)
    print(f"  Total configured services: {total_services}")
    
    for service_name, service_config in discovery.SERVICE_MAPPINGS.items():
        print(f"  📦 {service_name}: {', '.join(service_config.keys())}")
        for list_type, config in service_config.items():
            tool_name = config.get('tool', 'unknown')
            id_field = config.get('id_field')
            if id_field is None:
                status = "✅ Direct call"
            else:
                status = f"🔍 Needs ID: {id_field}"
            print(f"    - {list_type} -> {tool_name} ({status})")
    
    print("\n🎯 Fix Validation Results:")
    
    # Calendar events fix
    if events_config.get("id_field") is None:
        print("  ✅ Calendar events fix: WORKING - will call real tool")
    else:
        print("  ❌ Calendar events fix: FAILED - still returns examples")
    
    # Gmail filters fix 
    if filters_config.get("id_field") is None and filters_config.get("list_field") == "filters":
        print("  ✅ Gmail filters fix: WORKING - parameter filtering active")
    else:
        print("  ❌ Gmail filters fix: NEEDS REVIEW")
    
    # Gmail labels fix
    if labels_config.get("id_field") is None and labels_config.get("list_field") == "labels":
        print("  ✅ Gmail labels fix: WORKING - parameter filtering active")
    else:
        print("  ❌ Gmail labels fix: NEEDS REVIEW")
    
    print("\n🔍 Expected Behavior:")
    print("  📅 service://calendar/events -> Calls list_events tool directly")
    print("  📅 service://calendar/calendars -> Calls list_calendars tool directly")
    print("  📧 service://gmail/filters -> Calls list_gmail_filters with filtered params")
    print("  📧 service://gmail/labels -> Calls list_gmail_labels with filtered params")
    
    print("\n✅ Validation complete!")

if __name__ == "__main__":
    validate_fixes()