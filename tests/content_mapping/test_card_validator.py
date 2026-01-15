"""
Tests for the CardValidator class.
"""

import os
import sys
import unittest

# Add the parent directory to the path so we can import the modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from gchat.content_mapping.card_validator import CardValidator


class TestCardValidator(unittest.TestCase):
    """Test cases for the CardValidator class."""

    def setUp(self):
        """Set up test fixtures."""
        self.validator = CardValidator()

    def test_validate_card_structure_valid(self):
        """Test validating a valid card structure."""
        # Create a valid card with header and sections
        card = {
            "header": {"title": "Test Card"},
            "sections": [
                {"widgets": [{"textParagraph": {"text": "This is a test card."}}]}
            ],
        }

        is_valid, issues = self.validator.validate_card_structure(card)

        self.assertTrue(is_valid)
        self.assertEqual(len(issues), 0)

    def test_validate_card_structure_invalid_missing_required(self):
        """Test validating a card with missing required fields."""
        # Create a card with missing required fields
        card = {
            "header": {
                # Missing required title
            },
            "sections": [
                {
                    # Missing required widgets
                }
            ],
        }

        is_valid, issues = self.validator.validate_card_structure(card)

        self.assertFalse(is_valid)
        self.assertGreater(len(issues), 0)
        self.assertTrue(
            any("Missing required header field: title" in issue for issue in issues)
        )
        self.assertTrue(
            any(
                "Missing required field in section 0: widgets" in issue
                for issue in issues
            )
        )

    def test_validate_card_structure_invalid_unknown_fields(self):
        """Test validating a card with unknown fields."""
        # Create a card with unknown fields
        card = {
            "header": {"title": "Test Card", "unknown_field": "value"},  # Unknown field
            "sections": [
                {
                    "widgets": [
                        {
                            "textParagraph": {
                                "text": "This is a test card.",
                                "unknown_param": "value",  # Unknown parameter
                            }
                        }
                    ],
                    "unknown_section_field": "value",  # Unknown field
                }
            ],
            "unknown_card_field": "value",  # Unknown field
        }

        is_valid, issues = self.validator.validate_card_structure(card)

        self.assertFalse(is_valid)
        self.assertGreater(len(issues), 0)
        self.assertTrue(any("Unknown header fields" in issue for issue in issues))
        self.assertTrue(any("Unknown fields in section 0" in issue for issue in issues))
        self.assertTrue(any("Unknown card fields" in issue for issue in issues))

    def test_validate_card_structure_invalid_empty(self):
        """Test validating an empty card."""
        # Create an empty card
        card = {}

        is_valid, issues = self.validator.validate_card_structure(card)

        self.assertFalse(is_valid)
        self.assertGreater(len(issues), 0)
        self.assertTrue(
            any("Card must have either header or sections" in issue for issue in issues)
        )

    def test_validate_widget_valid(self):
        """Test validating a valid widget."""
        # Create a valid text paragraph widget
        widget = {"textParagraph": {"text": "This is a test widget."}}

        is_valid, issues = self.validator.validate_widget(widget)

        self.assertTrue(is_valid)
        self.assertEqual(len(issues), 0)

    def test_validate_widget_invalid_missing_required(self):
        """Test validating a widget with missing required fields."""
        # Create a widget with missing required fields
        widget = {
            "textParagraph": {
                # Missing required text field
            }
        }

        is_valid, issues = self.validator.validate_widget(widget)

        self.assertFalse(is_valid)
        self.assertGreater(len(issues), 0)
        self.assertTrue(
            any("Missing required field 'text'" in issue for issue in issues)
        )

    def test_validate_widget_invalid_unknown_type(self):
        """Test validating a widget with unknown type."""
        # Create a widget with unknown type
        widget = {"unknownWidgetType": {"param": "value"}}

        is_valid, issues = self.validator.validate_widget(widget)

        self.assertFalse(is_valid)
        self.assertGreater(len(issues), 0)
        self.assertTrue(any("Unknown widget type" in issue for issue in issues))

    def test_auto_fix_common_issues_missing_text(self):
        """Test auto-fixing a widget with missing text."""
        # Create a card with a widget missing text
        card = {
            "sections": [{"widgets": [{"textParagraph": {"text": ""}}]}]  # Empty text
        }

        fixed_card = self.validator.auto_fix_common_issues(card)

        # Check that the text was fixed
        self.assertEqual(
            fixed_card["sections"][0]["widgets"][0]["textParagraph"]["text"],
            "No text provided",
        )

    def test_auto_fix_common_issues_missing_alt_text(self):
        """Test auto-fixing an image widget with missing alt text."""
        # Create a card with an image widget missing alt text
        card = {
            "sections": [
                {
                    "widgets": [
                        {
                            "image": {
                                "imageUrl": "https://example.com/image.jpg"
                                # Missing alt text
                            }
                        }
                    ]
                }
            ]
        }

        fixed_card = self.validator.auto_fix_common_issues(card)

        # Check that the alt text was added
        self.assertEqual(
            fixed_card["sections"][0]["widgets"][0]["image"]["altText"], "Image"
        )

    def test_auto_fix_common_issues_invalid_url(self):
        """Test auto-fixing an image widget with invalid URL."""
        # Create a card with an image widget with invalid URL
        card = {
            "sections": [
                {
                    "widgets": [
                        {
                            "image": {
                                "imageUrl": "example.com/image.jpg"  # Missing protocol
                            }
                        }
                    ]
                }
            ]
        }

        fixed_card = self.validator.auto_fix_common_issues(card)

        # Check that the URL was fixed
        self.assertEqual(
            fixed_card["sections"][0]["widgets"][0]["image"]["imageUrl"],
            "https://example.com/image.jpg",
        )

    def test_auto_fix_common_issues_empty_button_list(self):
        """Test auto-fixing an empty button list."""
        # Create a card with an empty button list
        card = {
            "sections": [
                {"widgets": [{"buttonList": {"buttons": []}}]}  # Empty buttons array
            ]
        }

        fixed_card = self.validator.auto_fix_common_issues(card)

        # Check that a default button was added
        self.assertEqual(
            len(fixed_card["sections"][0]["widgets"][0]["buttonList"]["buttons"]), 1
        )
        self.assertEqual(
            fixed_card["sections"][0]["widgets"][0]["buttonList"]["buttons"][0]["text"],
            "Click here",
        )

    def test_auto_fix_common_issues_missing_header(self):
        """Test auto-fixing a card with no header or sections."""
        # Create an empty card
        card = {}

        fixed_card = self.validator.auto_fix_common_issues(card)

        # Check that a default section with a widget was added
        self.assertIn("sections", fixed_card)
        self.assertEqual(len(fixed_card["sections"]), 1)
        self.assertIn("widgets", fixed_card["sections"][0])
        self.assertEqual(len(fixed_card["sections"][0]["widgets"]), 1)
        self.assertIn("textParagraph", fixed_card["sections"][0]["widgets"][0])

    def test_suggest_improvements_minimal_card(self):
        """Test suggesting improvements for a minimal card."""
        # Create a minimal card with just text
        card = {
            "sections": [
                {"widgets": [{"textParagraph": {"text": "This is a minimal card."}}]}
            ]
        }

        suggestions = self.validator.suggest_improvements(card)

        # Check that appropriate suggestions were made
        self.assertGreater(len(suggestions), 0)
        self.assertTrue(
            any("header" in suggestion.lower() for suggestion in suggestions)
        )
        self.assertTrue(
            any("interactive" in suggestion.lower() for suggestion in suggestions)
        )
        self.assertTrue(
            any("image" in suggestion.lower() for suggestion in suggestions)
        )

    def test_suggest_improvements_complete_card(self):
        """Test suggesting improvements for a complete card."""
        # Create a complete card with header, images, and interactive elements
        card = {
            "header": {"title": "Complete Card", "subtitle": "With all features"},
            "sections": [
                {
                    "widgets": [
                        {"textParagraph": {"text": "This is a complete card."}},
                        {
                            "image": {
                                "imageUrl": "https://example.com/image.jpg",
                                "altText": "Example image",
                            }
                        },
                        {
                            "buttonList": {
                                "buttons": [
                                    {
                                        "text": "Click me",
                                        "onClick": {
                                            "openLink": {"url": "https://example.com"}
                                        },
                                    }
                                ]
                            }
                        },
                        {"divider": {}},
                    ]
                }
            ],
        }

        suggestions = self.validator.suggest_improvements(card)

        # A complete card should have fewer suggestions
        self.assertLessEqual(len(suggestions), 1)


if __name__ == "__main__":
    unittest.main()
