"""
Tests for the Enhanced Card Tool with Content Mapping and Parameter Inference.
"""

import json
import os

# Import the components to test
import sys
from unittest.mock import MagicMock, patch

import pytest

# Add the parent directory to the path so we can import the modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from gchat.content_mapping.card_validator import CardValidator
from gchat.content_mapping.content_mapping_engine import ContentMappingEngine
from gchat.content_mapping.parameter_inference_engine import ParameterInferenceEngine
from gchat.content_mapping.template_manager import TemplateManager
from gchat.content_mapping.widget_specification_parser import WidgetSpecificationParser
from gchat.enhanced_card_tool import (
    _ensure_components_initialized,
    find_card_templates,
    save_card_template,
    send_enhanced_card,
    validate_card,
)

# Test constants
TEST_EMAIL = "test@example.com"
TEST_SPACE_ID = "spaces/test"
TEST_WEBHOOK_URL = "https://example.com/webhook"


class TestEnhancedCardTool:
    """Test suite for the Enhanced Card Tool."""

    @pytest.fixture
    def mock_content_mapping_engine(self):
        """Fixture for mocked ContentMappingEngine."""
        mock_engine = MagicMock(spec=ContentMappingEngine)
        mock_engine.parse_content.return_value = {
            "title": "Test Card",
            "text": "This is a test card",
        }
        return mock_engine

    @pytest.fixture
    def mock_parameter_inference_engine(self):
        """Fixture for mocked ParameterInferenceEngine."""
        mock_engine = MagicMock(spec=ParameterInferenceEngine)
        mock_engine.infer_card_type.return_value = "simple"
        mock_engine.infer_parameters.return_value = {
            "title": "Inferred Title",
            "text": "Inferred text content",
        }
        mock_engine.validate_parameters.return_value = {
            "title": "Validated Title",
            "text": "Validated text content",
        }
        return mock_engine

    @pytest.fixture
    def mock_template_manager(self):
        """Fixture for mocked TemplateManager."""
        mock_manager = MagicMock(spec=TemplateManager)
        mock_manager.get_template.return_value = {
            "template_id": "test_template",
            "name": "Test Template",
            "description": "A test template",
            "template": {
                "header": {"title": "Template Title", "subtitle": "Template Subtitle"}
            },
            "placeholders": {"content": "sections.0.widgets.0.textParagraph.text"},
        }
        mock_manager.apply_template.return_value = {
            "header": {"title": "Template Title", "subtitle": "Template Subtitle"},
            "sections": [{"widgets": [{"textParagraph": {"text": "Applied content"}}]}],
        }
        mock_manager.store_template.return_value = "test_template_id"
        mock_manager.find_templates.return_value = [
            {
                "template_id": "template1",
                "name": "Template 1",
                "description": "First test template",
                "score": 0.95,
            },
            {
                "template_id": "template2",
                "name": "Template 2",
                "description": "Second test template",
                "score": 0.85,
            },
        ]
        return mock_manager

    @pytest.fixture
    def mock_widget_specification_parser(self):
        """Fixture for mocked WidgetSpecificationParser."""
        mock_parser = MagicMock(spec=WidgetSpecificationParser)
        mock_parser.parse_widget_description.return_value = {
            "buttonList": {
                "buttons": [
                    {
                        "text": "View Details",
                        "onClick": {"openLink": {"url": "https://example.com"}},
                    }
                ]
            }
        }
        mock_parser.identify_widget_type.return_value = "button"
        mock_parser.extract_widget_parameters.return_value = {
            "text": "View Details",
            "url": "https://example.com",
        }
        mock_parser.convert_to_widget_object.return_value = {
            "buttonList": {
                "buttons": [
                    {
                        "text": "View Details",
                        "onClick": {"openLink": {"url": "https://example.com"}},
                    }
                ]
            }
        }
        return mock_parser

    @pytest.fixture
    def mock_card_validator(self):
        """Fixture for mocked CardValidator."""
        mock_validator = MagicMock(spec=CardValidator)
        mock_validator.validate_card_structure.return_value = (True, [])
        mock_validator.auto_fix_common_issues.return_value = {
            "header": {"title": "Fixed Card Title"},
            "sections": [{"widgets": [{"textParagraph": {"text": "Fixed content"}}]}],
        }
        mock_validator.suggest_improvements.return_value = [
            "Consider adding interactive elements for better user engagement",
            "Add images to make the card more visually appealing",
        ]
        mock_validator.validate_widget.return_value = (True, [])
        return mock_validator

    @pytest.mark.asyncio
    async def test_component_initialization(
        self,
        mock_content_mapping_engine,
        mock_parameter_inference_engine,
        mock_template_manager,
        mock_widget_specification_parser,
        mock_card_validator,
    ):
        """Test that components are properly initialized."""
        with (
            patch("gchat.enhanced_card_tool._content_mapping_engine", None),
            patch("gchat.enhanced_card_tool._parameter_inference_engine", None),
            patch("gchat.enhanced_card_tool._template_manager", None),
            patch("gchat.enhanced_card_tool._widget_specification_parser", None),
            patch("gchat.enhanced_card_tool._card_validator", None),
            patch(
                "gchat.enhanced_card_tool.ContentMappingEngine",
                return_value=mock_content_mapping_engine,
            ),
            patch(
                "gchat.enhanced_card_tool.ParameterInferenceEngine",
                return_value=mock_parameter_inference_engine,
            ),
            patch(
                "gchat.enhanced_card_tool.TemplateManager",
                return_value=mock_template_manager,
            ),
            patch(
                "gchat.enhanced_card_tool.WidgetSpecificationParser",
                return_value=mock_widget_specification_parser,
            ),
            patch(
                "gchat.enhanced_card_tool.CardValidator",
                return_value=mock_card_validator,
            ),
        ):

            # Call the initialization function
            _ensure_components_initialized()

            # Check that components were initialized
            from gchat.enhanced_card_tool import (
                _card_validator,
                _content_mapping_engine,
                _parameter_inference_engine,
                _template_manager,
                _widget_specification_parser,
            )

            assert _content_mapping_engine is not None
            assert _parameter_inference_engine is not None
            assert _template_manager is not None
            assert _widget_specification_parser is not None
            assert _card_validator is not None

    @pytest.mark.asyncio
    async def test_send_enhanced_card(
        self,
        mock_content_mapping_engine,
        mock_parameter_inference_engine,
        mock_template_manager,
        mock_widget_specification_parser,
        mock_card_validator,
    ):
        """Test sending an enhanced card."""
        # Mock the components and functions
        with (
            patch(
                "gchat.enhanced_card_tool._content_mapping_engine",
                mock_content_mapping_engine,
            ),
            patch(
                "gchat.enhanced_card_tool._parameter_inference_engine",
                mock_parameter_inference_engine,
            ),
            patch("gchat.enhanced_card_tool._template_manager", mock_template_manager),
            patch(
                "gchat.enhanced_card_tool._widget_specification_parser",
                mock_widget_specification_parser,
            ),
            patch("gchat.enhanced_card_tool._card_validator", mock_card_validator),
            patch(
                "gchat.enhanced_card_tool._find_card_component"
            ) as mock_find_component,
            patch(
                "gchat.enhanced_card_tool._create_card_from_component"
            ) as mock_create_card,
            patch(
                "gchat.enhanced_card_tool._convert_card_to_google_format"
            ) as mock_convert_card,
            patch(
                "gchat.enhanced_card_tool._get_chat_service_with_fallback"
            ) as mock_get_service,
            patch("gchat.enhanced_card_tool.Message") as mock_message_class,
            patch("gchat.enhanced_card_tool.asyncio.to_thread") as mock_to_thread,
        ):

            # Setup mocks
            mock_find_component.return_value = [
                {
                    "score": 0.95,
                    "name": "SimpleCard",
                    "path": "card_framework.v2.SimpleCard",
                    "type": "class",
                    "component": MagicMock(),
                }
            ]
            mock_create_card.return_value = MagicMock()
            mock_convert_card.return_value = {
                "card": {"header": {"title": "Test Card"}}
            }

            mock_message = MagicMock()
            mock_message.render.return_value = {
                "text": "Test message",
                "cardsV2": [{"card": {"header": {"title": "Test Card"}}}],
            }
            mock_message_class.return_value = mock_message

            mock_service = MagicMock()
            mock_get_service.return_value = mock_service

            mock_execute = MagicMock()
            mock_execute.return_value = {
                "name": "messages/123",
                "createTime": "2025-07-03T10:00:00Z",
            }
            mock_create = MagicMock()
            mock_create.return_value = mock_execute
            mock_messages = MagicMock()
            mock_messages.create.return_value = mock_create
            mock_spaces = MagicMock()
            mock_spaces.messages.return_value = mock_messages
            mock_service.spaces.return_value = mock_spaces

            mock_to_thread.return_value = mock_execute.return_value

            # Call the function
            result = await send_enhanced_card(
                user_google_email=TEST_EMAIL,
                space_id=TEST_SPACE_ID,
                content_spec="Create a simple card with title 'Test Card' and some text content",
                card_params={"title": "Explicit Title"},
                thread_key="thread123",
                widget_description="Add a button labeled 'View Details' that opens https://example.com",
                validate_card=True,
            )

            # Check that the function called the expected methods
            mock_content_mapping_engine.parse_content.assert_called_once()
            mock_parameter_inference_engine.infer_card_type.assert_called_once()
            mock_find_component.assert_called_once_with("simple card")
            mock_parameter_inference_engine.infer_parameters.assert_called_once()
            mock_widget_specification_parser.parse_widget_description.assert_called_once_with(
                "Add a button labeled 'View Details' that opens https://example.com"
            )
            mock_parameter_inference_engine.validate_parameters.assert_called_once()
            mock_card_validator.validate_card_structure.assert_called_once()
            mock_card_validator.auto_fix_common_issues.assert_not_called()  # Should not be called if validation passes
            mock_create_card.assert_called_once()
            mock_convert_card.assert_called_once()
            mock_get_service.assert_called_once_with(TEST_EMAIL)

            # Check that the result contains success message
            assert "✅" in result
            assert TEST_SPACE_ID in result
            assert TEST_EMAIL in result

            # Test with validation issues
            mock_card_validator.validate_card_structure.return_value = (
                False,
                ["Missing required field"],
            )

            result = await send_enhanced_card(
                user_google_email=TEST_EMAIL,
                space_id=TEST_SPACE_ID,
                content_spec="Create a simple card with title 'Test Card' and some text content",
                validate_card=True,
            )

            # Check that auto-fix was called
            mock_card_validator.auto_fix_common_issues.assert_called_once()
            mock_card_validator.suggest_improvements.assert_called_once()

    @pytest.mark.asyncio
    async def test_save_card_template(self, mock_template_manager):
        """Test saving a card template."""
        with (
            patch("gchat.enhanced_card_tool._template_manager", mock_template_manager),
            patch("gchat.enhanced_card_tool._ensure_async_components_initialized"),
        ):

            # Test data
            template_name = "Test Template"
            template_description = "A test template for cards"
            template_data = {
                "header": {"title": "Template Title", "subtitle": "Template Subtitle"},
                "sections": [{"widgets": [{"textParagraph": {"text": "{{content}}"}}]}],
            }
            placeholders = {"content": "sections.0.widgets.0.textParagraph.text"}

            # Call the function
            result = await save_card_template(
                name=template_name,
                description=template_description,
                template=template_data,
                placeholders=placeholders,
            )

            # Check that the template manager was called correctly
            mock_template_manager.store_template.assert_called_once_with(
                name=template_name,
                description=template_description,
                template=template_data,
                placeholders=placeholders,
            )

            # Check that the result contains success message
            assert "✅" in result
            assert "test_template_id" in result

    @pytest.mark.asyncio
    async def test_find_card_templates(self, mock_template_manager):
        """Test finding card templates."""
        with (
            patch("gchat.enhanced_card_tool._template_manager", mock_template_manager),
            patch("gchat.enhanced_card_tool._ensure_async_components_initialized"),
        ):

            # Call the function
            result = await find_card_templates(query="test template", limit=5)

            # Check that the template manager was called correctly
            mock_template_manager.find_templates.assert_called_once_with(
                "test template", 5
            )

            # Parse the result JSON
            result_data = json.loads(result)

            # Check the result structure
            assert "query" in result_data
            assert "templates" in result_data
            assert "count" in result_data
            assert result_data["query"] == "test template"
            assert result_data["count"] == 2
            assert len(result_data["templates"]) == 2
            assert result_data["templates"][0]["template_id"] == "template1"
            assert result_data["templates"][1]["template_id"] == "template2"

    @pytest.mark.asyncio
    async def test_validate_card(self, mock_card_validator):
        """Test validating a card structure."""
        with (
            patch("gchat.enhanced_card_tool._card_validator", mock_card_validator),
            patch("gchat.enhanced_card_tool._ensure_components_initialized"),
        ):

            # Test data
            test_card = {
                "header": {"title": "Test Card"},
                "sections": [
                    {"widgets": [{"textParagraph": {"text": "This is a test card."}}]}
                ],
            }

            # Test with valid card
            mock_card_validator.validate_card_structure.return_value = (True, [])

            result = await validate_card(
                card=test_card, auto_fix=True, get_suggestions=True
            )

            # Check that the validator was called correctly
            mock_card_validator.validate_card_structure.assert_called_once_with(
                test_card
            )
            mock_card_validator.auto_fix_common_issues.assert_not_called()  # Should not be called if validation passes
            mock_card_validator.suggest_improvements.assert_called_once_with(test_card)

            # Check the result structure
            assert "is_valid" in result
            assert result["is_valid"] is True
            assert "issues" in result
            assert "suggestions" in result
            assert "card" in result

            # Test with invalid card
            mock_card_validator.validate_card_structure.reset_mock()
            mock_card_validator.auto_fix_common_issues.reset_mock()
            mock_card_validator.suggest_improvements.reset_mock()

            mock_card_validator.validate_card_structure.return_value = (
                False,
                ["Missing required field"],
            )
            mock_card_validator.auto_fix_common_issues.return_value = {
                "header": {"title": "Fixed Card Title"},
                "sections": [
                    {"widgets": [{"textParagraph": {"text": "Fixed content"}}]}
                ],
            }

            result = await validate_card(
                card=test_card, auto_fix=True, get_suggestions=True
            )

            # Check that the validator was called correctly
            mock_card_validator.validate_card_structure.assert_called_once_with(
                test_card
            )
            mock_card_validator.auto_fix_common_issues.assert_called_once_with(
                test_card
            )
            mock_card_validator.suggest_improvements.assert_called_once()

            # Check the result structure
            assert "is_valid" in result
            assert result["is_valid"] is False
            assert "issues" in result
            assert "fixed_card" in result
            assert "suggestions" in result

            # Test without auto-fix
            mock_card_validator.validate_card_structure.reset_mock()
            mock_card_validator.auto_fix_common_issues.reset_mock()
            mock_card_validator.suggest_improvements.reset_mock()

            mock_card_validator.validate_card_structure.return_value = (
                False,
                ["Missing required field"],
            )

            result = await validate_card(
                card=test_card, auto_fix=False, get_suggestions=True
            )

            # Check that auto-fix was not called
            mock_card_validator.auto_fix_common_issues.assert_not_called()
            mock_card_validator.suggest_improvements.assert_called_once_with(test_card)

            # Test without suggestions
            mock_card_validator.validate_card_structure.reset_mock()
            mock_card_validator.auto_fix_common_issues.reset_mock()
            mock_card_validator.suggest_improvements.reset_mock()

            mock_card_validator.validate_card_structure.return_value = (True, [])

            result = await validate_card(
                card=test_card, auto_fix=True, get_suggestions=False
            )

            # Check that suggestions were not requested
            mock_card_validator.suggest_improvements.assert_not_called()
