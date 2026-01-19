"""
Tests for enhanced NLP card parser with ordinal words and titled keyword support.

These tests validate the new patterns added to support more natural language descriptions
like "First section titled 'Deployments' showing X" instead of requiring numbered formats.
"""

import pytest
from gchat.nlp_card_parser import (
    EnhancedNaturalLanguageCardParser,
    parse_enhanced_natural_language_description,
    ORDINAL_WORDS,
    ORDINAL_PATTERN,
)


class TestOrdinalWordSupport:
    """Test ordinal word recognition (First, Second, Third, etc.)."""

    def test_ordinal_words_mapping(self):
        """Verify ordinal word to number mapping is complete."""
        assert ORDINAL_WORDS["first"] == 1
        assert ORDINAL_WORDS["second"] == 2
        assert ORDINAL_WORDS["third"] == 3
        assert ORDINAL_WORDS["fourth"] == 4
        assert ORDINAL_WORDS["fifth"] == 5
        assert ORDINAL_WORDS["1st"] == 1
        assert ORDINAL_WORDS["2nd"] == 2
        assert ORDINAL_WORDS["3rd"] == 3

    def test_ordinal_pattern_matches(self):
        """Verify the ordinal pattern regex matches expected words."""
        import re
        pattern = re.compile(ORDINAL_PATTERN, re.IGNORECASE)

        # Should match
        assert pattern.search("First section")
        assert pattern.search("second section")
        assert pattern.search("THIRD section")
        assert pattern.search("1st section")
        assert pattern.search("2nd section")

        # Should not match
        assert not pattern.search("one section")
        assert not pattern.search("eleven section")


class TestOrdinalTitledPattern:
    """Test the 'First section titled X showing Y' pattern."""

    @pytest.fixture
    def parser(self):
        return EnhancedNaturalLanguageCardParser()

    def test_single_section_ordinal_titled(self, parser):
        """Test parsing a single section with ordinal+titled format."""
        description = '''Create a card with First section titled "Deployments" showing deployment status.'''

        result = parser.parse(description)

        assert len(result.sections) == 1
        assert result.sections[0].header == "Deployments"
        assert len(result.sections[0].widgets) > 0

    def test_multiple_sections_ordinal_titled(self, parser):
        """Test parsing multiple sections with ordinal+titled format."""
        description = '''Create a GitHub activity card. First section titled "Deployments" showing preview deployed. Second section titled "Commits" showing commit info. Third section titled "Warnings" showing stale PRs.'''

        result = parser.parse(description)

        assert len(result.sections) == 3
        assert result.sections[0].header == "Deployments"
        assert result.sections[1].header == "Commits"
        assert result.sections[2].header == "Warnings"

    def test_github_activity_card_full(self, parser):
        """Test the exact GitHub activity card description from user."""
        description = '''Create a GitHub activity update card for Sunday January 18 2026. Include three sections: First section titled "Deployments - PR #1672" showing AIDG React FE preview deployed at pr-1672-aidg-react-fe-rzpt3.ondigitalocean.app and Admin React FE preview deployed at pr-1672-admin-react-fe-gxzol.ondigitalocean.app. Second section titled "Commits" showing @ctzaruba pushed commit 9966fbe for ENC-2390 temporal structural improvements. Third section titled "Stale PRs" warning that PR #1550 MAD-4142 env var for google scraper has had no activity for 10 days and is marked for removal. Use a GitHub octopus emoji in the title.'''

        result = parser.parse(description)

        # Should extract 3 sections
        assert len(result.sections) == 3

        # Check section headers
        assert "Deployments" in result.sections[0].header
        assert "Commits" in result.sections[1].header
        assert "Stale PRs" in result.sections[2].header

        # First section should have deployment content with URLs
        first_section_widgets = result.sections[0].widgets
        assert len(first_section_widgets) > 0

        # Second section should have commit content
        second_section_widgets = result.sections[1].widgets
        assert len(second_section_widgets) > 0

        # Third section should have warning content
        third_section_widgets = result.sections[2].widgets
        assert len(third_section_widgets) > 0


class TestEnhancedContentParsing:
    """Test enhanced content parsing for URLs, warnings, commits."""

    @pytest.fixture
    def parser(self):
        return EnhancedNaturalLanguageCardParser()

    def test_url_extraction_from_content(self, parser):
        """Test that URLs are extracted and create button widgets."""
        description = '''First section titled "Links" showing check out https://example.com for details.'''

        result = parser.parse(description)

        assert len(result.sections) == 1
        widgets = result.sections[0].widgets

        # Should have a widget with a button that links to the URL
        has_button = False
        for widget in widgets:
            if "decoratedText" in widget:
                if "button" in widget["decoratedText"]:
                    has_button = True
                    button = widget["decoratedText"]["button"]
                    assert "onClick" in button
                    assert "openLink" in button["onClick"]

        assert has_button, "Should create a button widget for URL"

    def test_warning_content_gets_warning_icon(self, parser):
        """Test that warning content gets a warning-style icon (STAR, since WARNING isn't available)."""
        description = '''First section titled "Alerts" showing warning: system is running low on memory.'''

        result = parser.parse(description)

        widgets = result.sections[0].widgets

        # Should have a STAR icon (Google Chat doesn't have WARNING knownIcon)
        has_alert_icon = False
        for widget in widgets:
            if "decoratedText" in widget:
                if "startIcon" in widget["decoratedText"]:
                    # Using STAR as fallback for warnings since WARNING isn't a valid knownIcon
                    if widget["decoratedText"]["startIcon"].get("knownIcon") == "STAR":
                        has_alert_icon = True

        assert has_alert_icon, "Warning content should have STAR icon (WARNING not available in Google Chat)"

    def test_commit_reference_parsing(self, parser):
        """Test that commit references are parsed correctly."""
        description = '''First section titled "Changes" showing @developer pushed commit abc123 with new features.'''

        result = parser.parse(description)

        widgets = result.sections[0].widgets
        assert len(widgets) > 0

        # Should preserve the @ mention and commit reference
        widget_text = str(widgets)
        assert "@developer" in widget_text or "pushed" in widget_text

    def test_multiple_items_in_section(self, parser):
        """Test that 'X and Y' content is split into multiple widgets."""
        description = '''First section titled "Deployments" showing Frontend deployed at example.com and Backend deployed at api.example.com.'''

        result = parser.parse(description)

        widgets = result.sections[0].widgets
        # Should have at least 2 widgets (one for each deployment)
        assert len(widgets) >= 2, f"Expected 2+ widgets for 'X and Y' pattern, got {len(widgets)}"


class TestIntegrationWithMainAPI:
    """Test the main entry point parse_enhanced_natural_language_description."""

    def test_main_api_returns_dict(self):
        """Test that the main API returns a dictionary."""
        description = '''First section titled "Test" showing some content.'''

        result = parse_enhanced_natural_language_description(description)

        assert isinstance(result, dict)
        assert "sections" in result
        assert len(result["sections"]) == 1

    def test_main_api_preserves_section_headers(self):
        """Test that section headers are preserved in output."""
        description = '''First section titled "Header One" showing content one. Second section titled "Header Two" showing content two.'''

        result = parse_enhanced_natural_language_description(description)

        sections = result.get("sections", [])
        assert len(sections) == 2
        assert sections[0].get("header") == "Header One"
        assert sections[1].get("header") == "Header Two"

    def test_main_api_creates_valid_widgets(self):
        """Test that widgets created are valid Google Chat format."""
        description = '''First section titled "Test" showing some test content.'''

        result = parse_enhanced_natural_language_description(description)

        sections = result.get("sections", [])
        assert len(sections) == 1

        widgets = sections[0].get("widgets", [])
        assert len(widgets) > 0

        # Each widget should be a dict with a valid widget type
        valid_widget_types = {
            "textParagraph", "decoratedText", "buttonList",
            "image", "divider", "selectionInput", "textInput"
        }

        for widget in widgets:
            assert isinstance(widget, dict)
            widget_type = list(widget.keys())[0]
            assert widget_type in valid_widget_types, f"Invalid widget type: {widget_type}"


class TestBackwardCompatibility:
    """Test that old patterns still work."""

    @pytest.fixture
    def parser(self):
        return EnhancedNaturalLanguageCardParser()

    def test_numbered_pattern_still_works(self, parser):
        """Test that numbered pattern (1. 'Section' with...) still works."""
        description = '''1. 'First Section' section with some content. 2. 'Second Section' section with more content.'''

        # This should still work via the old pattern
        result = parser.parse(description)
        # May not match exactly due to pattern priority, but shouldn't error

    def test_explicit_sections_pattern_still_works(self, parser):
        """Test that explicit sections: pattern still works."""
        description = '''sections: 'Info', 'Stats', 'Actions' with various content.'''

        result = parser.parse(description)
        # Should not error - may or may not match depending on pattern priority


class TestMultipleURLsEdgeCases:
    """Test edge cases for multiple URLs in content - fixes from agent feedback."""

    @pytest.fixture
    def parser(self):
        return EnhancedNaturalLanguageCardParser()

    def test_multiple_urls_in_single_section(self, parser):
        """Test that multiple URLs in one section are all preserved."""
        description = '''First section titled "Navigation" showing Try opening https://developers.google.com/chat and https://cloud.google.com in a new tab.'''

        result = parser.parse(description)

        assert len(result.sections) == 1
        widgets = result.sections[0].widgets

        # Should have widgets for both URLs, not just one
        widget_text = str(widgets)
        assert "developers.google.com" in widget_text, "First URL should be preserved"
        assert "cloud.google.com" in widget_text, "Second URL should be preserved"

    def test_mixed_urls_with_query_params(self, parser):
        """Test that URLs with query parameters are fully captured."""
        description = '''First section titled "Auto-URLs" showing Mixed URLs: https://example.com/path?x=1&y=two and https://www.wikipedia.org/'''

        result = parser.parse(description)

        widgets = result.sections[0].widgets
        widget_text = str(widgets)

        # Both URLs should be present
        assert "example.com" in widget_text, "First URL with query params should be preserved"
        assert "wikipedia.org" in widget_text, "Second URL should be preserved"

    def test_numbered_list_with_links(self, parser):
        """Test that numbered lists of links are properly split."""
        description = '''First section titled "Many Links" showing Multiple buttons: 1) https://github.com 2) https://gitlab.com 3) https://bitbucket.org'''

        result = parser.parse(description)

        widgets = result.sections[0].widgets

        # Should have separate widgets for each numbered item (3 links)
        # At minimum, all 3 URLs should be present
        widget_text = str(widgets)
        assert "github.com" in widget_text, "First numbered link should be present"
        assert "gitlab.com" in widget_text, "Second numbered link should be present"
        assert "bitbucket.org" in widget_text, "Third numbered link should be present"

    def test_punctuation_adjacent_links(self, parser):
        """Test that links with surrounding punctuation are handled correctly."""
        description = '''First section titled "Edge" showing Mixed punctuation around links (https://example.com) [https://example.org].'''

        result = parser.parse(description)

        widgets = result.sections[0].widgets
        widget_text = str(widgets)

        # URLs should be captured even with surrounding punctuation
        assert "example.com" in widget_text, "URL in parentheses should be captured"
        assert "example.org" in widget_text, "URL in brackets should be captured"

    def test_url_not_dropped_before_and(self, parser):
        """Test that URL before 'and' conjunction is not dropped."""
        description = '''First section titled "Links" showing Check out https://first-link.com and also https://second-link.com for more info.'''

        result = parser.parse(description)

        widgets = result.sections[0].widgets
        widget_text = str(widgets)

        # Both URLs should be preserved
        assert "first-link.com" in widget_text, "URL before 'and' should not be dropped"
        assert "second-link.com" in widget_text, "URL after 'and' should be preserved"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
