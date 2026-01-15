"""
Tests for the WidgetSpecificationParser class.
"""

import os
import sys
import unittest
from unittest.mock import MagicMock

# Add the parent directory to the path so we can import the modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from gchat.content_mapping.parameter_inference_engine import ParameterInferenceEngine
from gchat.content_mapping.widget_specification_parser import WidgetSpecificationParser


class TestWidgetSpecificationParser(unittest.TestCase):
    """Test cases for the WidgetSpecificationParser class."""

    def setUp(self):
        """Set up test fixtures."""
        self.parameter_inference_engine = MagicMock(spec=ParameterInferenceEngine)
        self.parser = WidgetSpecificationParser(self.parameter_inference_engine)

    def test_identify_widget_type_button(self):
        """Test identifying a button widget from natural language."""
        descriptions = [
            "Add a button labeled 'View Details'",
            "Create a button that opens https://example.com",
            "Insert a button for submitting the form",
        ]

        for description in descriptions:
            with self.subTest(description=description):
                widget_type = self.parser.identify_widget_type(description)
                self.assertEqual(widget_type, "button")

    def test_identify_widget_type_image(self):
        """Test identifying an image widget from natural language."""
        descriptions = [
            "Add an image from https://example.com/image.jpg",
            "Insert a picture of a cat",
            "Show an image with alt text 'Product screenshot'",
        ]

        for description in descriptions:
            with self.subTest(description=description):
                widget_type = self.parser.identify_widget_type(description)
                self.assertEqual(widget_type, "image")

    def test_identify_widget_type_text(self):
        """Test identifying a text widget from natural language."""
        descriptions = [
            "Add text saying 'Welcome to our service'",
            "Insert a paragraph with the message 'Thank you for your purchase'",
            "Show some text with the content 'Please fill out the form below'",
        ]

        for description in descriptions:
            with self.subTest(description=description):
                widget_type = self.parser.identify_widget_type(description)
                self.assertEqual(widget_type, "text")

    def test_identify_widget_type_decorated_text(self):
        """Test identifying a decorated text widget from natural language."""
        descriptions = [
            "Add decorated text with icon STAR",
            "Insert styled text with label 'Status'",
            "Show text with top label 'Priority' and bottom label 'High'",
        ]

        for description in descriptions:
            with self.subTest(description=description):
                widget_type = self.parser.identify_widget_type(description)
                self.assertEqual(widget_type, "decoratedText")

    def test_identify_widget_type_divider(self):
        """Test identifying a divider widget from natural language."""
        descriptions = [
            "Add a divider",
            "Insert a horizontal line",
            "Show a separator between sections",
        ]

        for description in descriptions:
            with self.subTest(description=description):
                widget_type = self.parser.identify_widget_type(description)
                self.assertEqual(widget_type, "divider")

    def test_extract_widget_parameters_button(self):
        """Test extracting parameters for a button widget."""
        description = (
            "Add a button labeled 'View Details' that opens https://example.com"
        )
        parameters = self.parser.extract_widget_parameters(description, "button")

        self.assertEqual(parameters.get("text"), "View Details")
        self.assertEqual(parameters.get("url"), "https://example.com")

    def test_extract_widget_parameters_image(self):
        """Test extracting parameters for an image widget."""
        description = (
            "Add an image from https://example.com/image.jpg with alt text 'Product'"
        )
        parameters = self.parser.extract_widget_parameters(description, "image")

        self.assertEqual(parameters.get("imageUrl"), "https://example.com/image.jpg")
        self.assertEqual(parameters.get("altText"), "Product")

    def test_extract_widget_parameters_text(self):
        """Test extracting parameters for a text widget."""
        description = "Add text saying 'Welcome to our service'"
        parameters = self.parser.extract_widget_parameters(description, "text")

        self.assertEqual(parameters.get("text"), "Welcome to our service")

    def test_extract_widget_parameters_decorated_text(self):
        """Test extracting parameters for a decorated text widget."""
        description = (
            "Add decorated text 'Status: Active' with top label 'Status' and icon STAR"
        )
        parameters = self.parser.extract_widget_parameters(description, "decoratedText")

        self.assertEqual(parameters.get("text"), "Status: Active")
        self.assertEqual(parameters.get("topLabel"), "Status")
        self.assertEqual(parameters.get("startIcon"), {"knownIcon": "STAR"})

    def test_convert_to_widget_object_button(self):
        """Test converting parameters to a button widget object."""
        parameters = {"text": "View Details", "url": "https://example.com"}

        widget_object = self.parser.convert_to_widget_object("button", parameters)

        self.assertIn("buttonList", widget_object)
        self.assertIn("buttons", widget_object["buttonList"])
        self.assertEqual(len(widget_object["buttonList"]["buttons"]), 1)
        self.assertEqual(
            widget_object["buttonList"]["buttons"][0]["text"], "View Details"
        )
        self.assertEqual(
            widget_object["buttonList"]["buttons"][0]["onClick"]["openLink"]["url"],
            "https://example.com",
        )

    def test_convert_to_widget_object_image(self):
        """Test converting parameters to an image widget object."""
        parameters = {"imageUrl": "https://example.com/image.jpg", "altText": "Product"}

        widget_object = self.parser.convert_to_widget_object("image", parameters)

        self.assertIn("image", widget_object)
        self.assertEqual(
            widget_object["image"]["imageUrl"], "https://example.com/image.jpg"
        )
        self.assertEqual(widget_object["image"]["altText"], "Product")

    def test_convert_to_widget_object_text(self):
        """Test converting parameters to a text widget object."""
        parameters = {"text": "Welcome to our service"}

        widget_object = self.parser.convert_to_widget_object("text", parameters)

        self.assertIn("textParagraph", widget_object)
        self.assertEqual(
            widget_object["textParagraph"]["text"], "Welcome to our service"
        )

    def test_convert_to_widget_object_decorated_text(self):
        """Test converting parameters to a decorated text widget object."""
        parameters = {
            "text": "Status: Active",
            "topLabel": "Status",
            "startIcon": {"knownIcon": "STAR"},
        }

        widget_object = self.parser.convert_to_widget_object(
            "decoratedText", parameters
        )

        self.assertIn("decoratedText", widget_object)
        self.assertEqual(widget_object["decoratedText"]["text"], "Status: Active")
        self.assertEqual(widget_object["decoratedText"]["topLabel"], "Status")
        self.assertEqual(
            widget_object["decoratedText"]["startIcon"]["knownIcon"], "STAR"
        )
        self.assertTrue(widget_object["decoratedText"]["wrapText"])

    def test_parse_widget_description_button(self):
        """Test parsing a complete button widget description."""
        description = (
            "Add a button labeled 'View Details' that opens https://example.com"
        )

        widget_object = self.parser.parse_widget_description(description)

        self.assertIn("buttonList", widget_object)
        self.assertIn("buttons", widget_object["buttonList"])
        self.assertEqual(len(widget_object["buttonList"]["buttons"]), 1)
        self.assertEqual(
            widget_object["buttonList"]["buttons"][0]["text"], "View Details"
        )
        self.assertEqual(
            widget_object["buttonList"]["buttons"][0]["onClick"]["openLink"]["url"],
            "https://example.com",
        )

    def test_parse_widget_description_image(self):
        """Test parsing a complete image widget description."""
        description = (
            "Add an image from https://example.com/image.jpg with alt text 'Product'"
        )

        widget_object = self.parser.parse_widget_description(description)

        self.assertIn("image", widget_object)
        self.assertEqual(
            widget_object["image"]["imageUrl"], "https://example.com/image.jpg"
        )
        self.assertEqual(widget_object["image"]["altText"], "Product")

    def test_parse_widget_description_text(self):
        """Test parsing a complete text widget description."""
        description = "Add text saying 'Welcome to our service'"

        widget_object = self.parser.parse_widget_description(description)

        self.assertIn("textParagraph", widget_object)
        self.assertEqual(
            widget_object["textParagraph"]["text"], "Welcome to our service"
        )

    def test_parse_widget_description_decorated_text(self):
        """Test parsing a complete decorated text widget description."""
        description = (
            "Add decorated text 'Status: Active' with top label 'Status' and icon STAR"
        )

        widget_object = self.parser.parse_widget_description(description)

        self.assertIn("decoratedText", widget_object)
        self.assertEqual(widget_object["decoratedText"]["text"], "Status: Active")
        self.assertEqual(widget_object["decoratedText"]["topLabel"], "Status")
        self.assertEqual(
            widget_object["decoratedText"]["startIcon"]["knownIcon"], "STAR"
        )

    def test_parse_widget_description_divider(self):
        """Test parsing a complete divider widget description."""
        description = "Add a divider"

        widget_object = self.parser.parse_widget_description(description)

        self.assertIn("divider", widget_object)
        self.assertEqual(widget_object["divider"], {})


if __name__ == "__main__":
    unittest.main()
