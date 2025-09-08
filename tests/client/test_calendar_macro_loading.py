#!/usr/bin/env python3
"""
Test calendar dashboard macro loading from templates folder
Tests the enhanced template middleware's automatic macro discovery and loading.
Standalone test using mock data - no FastMCP client/server required.
"""

import pytest
import sys
import asyncio
from pathlib import Path

# Add the project root to the path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from middleware.template_middleware import EnhancedTemplateMiddleware

class TestCalendarMacroLoading:
    """Test calendar dashboard macro loading from template files using mock data."""
    
    @pytest.mark.asyncio
    async def test_calendar_macro_discovery(self):
        """Test calendar dashboard macro discovery and loading - standalone test with mock data"""
        print("🧪 Testing Calendar Dashboard Macro Discovery...")
        print("=" * 60)
        
        # Initialize middleware with templates directory
        templates_dir = project_root / "middleware" / "templates"
        middleware = EnhancedTemplateMiddleware(templates_dir=str(templates_dir))
        
        print(f"📁 Templates directory: {templates_dir}")
        print(f"📄 Template files found: {list(templates_dir.glob('*.j2'))}")
        
        # Test Jinja2 environment setup
        assert middleware.jinja2_env is not None, "Jinja2 environment should be created"
        
        print(f"\n📊 Jinja2 Environment Info:")
        print(f"   Environment created: {middleware.jinja2_env is not None}")
        print(f"   Loader type: {type(middleware.jinja2_env.loader)}")
        
        if hasattr(middleware.jinja2_env.loader, 'loaders'):
            print(f"   Sub-loaders: {[type(loader).__name__ for loader in middleware.jinja2_env.loader.loaders]}")
        
        # Test macro loading by checking if templates can be loaded
        if hasattr(middleware.jinja2_env.loader, 'loaders'):
            # Get the FileSystemLoader specifically
            fs_loader = None
            for loader in middleware.jinja2_env.loader.loaders:
                if hasattr(loader, 'searchpath'):
                    fs_loader = loader
                    break
            
            if fs_loader:
                print(f"   FileSystemLoader search paths: {fs_loader.searchpath}")
                available_templates = fs_loader.list_templates()
                print(f"   Available templates: {available_templates}")
                
                # Check for our calendar dashboard template
                assert 'calendar_dashboard.j2' in available_templates, "calendar_dashboard.j2 should be available"
        
        # Check if macro is available in environment globals
        print(f"\n🔍 Checking macro availability:")
        print(f"   Environment globals count: {len(middleware.jinja2_env.globals)}")
        print(f"   Has render_calendar_dashboard: {'render_calendar_dashboard' in middleware.jinja2_env.globals}")
        
        # The macro should be loaded automatically
        assert 'render_calendar_dashboard' in middleware.jinja2_env.globals, \
            "render_calendar_dashboard macro should be loaded automatically"
    
    @pytest.mark.asyncio
    async def test_calendar_macro_rendering(self):
        """Test calendar dashboard macro rendering with mock data - no FastMCP client required"""
        
        # Initialize middleware with templates directory
        templates_dir = project_root / "middleware" / "templates"
        middleware = EnhancedTemplateMiddleware(templates_dir=str(templates_dir))
        
        # Test with comprehensive mock data
        mock_calendar_data = {
            "items": [
                {
                    "id": "primary@gmail.com",
                    "summary": "Primary Calendar",
                    "accessRole": "owner",
                    "primary": True,
                    "timeZone": "America/New_York",
                    "description": "Primary calendar for testing"
                },
                {
                    "id": "owned@gmail.com", 
                    "summary": "My Work Calendar",
                    "accessRole": "owner",
                    "primary": False,
                    "timeZone": "America/New_York",
                    "description": "Owned work calendar"
                },
                {
                    "id": "shared@example.com",
                    "summary": "Team Shared Calendar",
                    "accessRole": "writer",
                    "primary": False,
                    "timeZone": "America/New_York",
                    "description": "Shared team calendar"
                },
                {
                    "id": "readonly@example.com",
                    "summary": "Read-Only Calendar",
                    "accessRole": "reader",
                    "primary": False,
                    "timeZone": "Europe/London",
                    "description": "Read-only shared calendar"
                }
            ]
        }
        
        print(f"\n🧪 Testing macro with mock data:")
        
        # Ensure macro is available
        assert 'render_calendar_dashboard' in middleware.jinja2_env.globals, \
            "render_calendar_dashboard macro should be available"
        
        # Test macro rendering
        template = middleware.jinja2_env.from_string(
            "{{ render_calendar_dashboard(calendar_data, 'Macro Test Dashboard') }}"
        )
        result = template.render(calendar_data=mock_calendar_data)
        
        print(f"   Render successful: {len(result)} characters")
        print(f"   Contains primary calendar: {'Primary Calendar' in result}")
        print(f"   Contains work calendar: {'My Work Calendar' in result}")
        print(f"   Contains shared calendar: {'Team Shared Calendar' in result}")
        print(f"   Contains statistics: {'Calendar Statistics' in result}")
        print(f"   Contains primary section: {'Primary Calendars' in result}")
        print(f"   Contains shared section: {'Shared Calendars' in result}")
        
        # Validate rendered content with comprehensive mock data
        assert len(result) > 3000, "Rendered template should be substantial with 4 calendars"
        assert 'Macro Test Dashboard' in result, "Should contain custom dashboard title"
        assert 'Primary Calendar' in result, "Should contain primary calendar data"
        assert 'My Work Calendar' in result, "Should contain owned calendar data"
        assert 'Team Shared Calendar' in result, "Should contain shared calendar data"
        assert 'Read-Only Calendar' in result, "Should contain read-only calendar data"
        assert 'Calendar Statistics' in result, "Should contain statistics section"
        assert 'Shared Calendars' in result, "Should contain shared calendars section"
        
        # Show first part of rendered output for debugging
        print(f"\n📄 First 500 chars of rendered result:")
        print(result[:500] + "..." if len(result) > 500 else result)
        
        # Additional validation
        assert 'Calendar Management Dashboard' in result, "Should contain subtitle"
        assert 'Total' in result, "Should contain total count"
        assert '📅 Google Calendar Integration' in result, "Should contain footer"
        
        print("\n🎉 Calendar dashboard macro successfully loaded and functional!")

    @pytest.mark.asyncio 
    async def test_template_file_discovery(self):
        """Test that template files are properly discovered - filesystem validation only"""
        
        templates_dir = project_root / "middleware" / "templates"
        
        # Check that template files exist
        email_card_template = templates_dir / "email_card.j2"
        calendar_dashboard_template = templates_dir / "calendar_dashboard.j2"
        
        assert email_card_template.exists(), "email_card.j2 should exist"
        assert calendar_dashboard_template.exists(), "calendar_dashboard.j2 should exist"
        
        # Check template content
        with open(calendar_dashboard_template, 'r') as f:
            content = f.read()
            
        assert 'render_calendar_dashboard' in content, "Template should define render_calendar_dashboard macro"
        assert 'Google Calendar Dashboard' in content, "Template should contain calendar dashboard content"
        assert 'Calendar Statistics' in content, "Template should contain statistics section"

if __name__ == "__main__":
    # Allow running directly for development
    async def run_tests():
        test_instance = TestCalendarMacroLoading()
        await test_instance.test_calendar_macro_discovery()
        await test_instance.test_calendar_macro_rendering()
        await test_instance.test_template_file_discovery()
    
    asyncio.run(run_tests())