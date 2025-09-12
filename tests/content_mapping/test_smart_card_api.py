"""
Tests for Smart Card API

This module contains tests for the Smart Card API, which provides a simplified
interface for LLMs to interact with the card creation system.
"""

import unittest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock

import sys
import os

# Add the parent directory to the path so we can import the modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from gchat.content_mapping.smart_card_api import (
    send_smart_card, create_card_from_template, create_card_from_description,
    parse_natural_language_content, _content_mapping_engine, _parameter_inference_engine,
    _template_manager, _widget_specification_parser, _card_validator
)


class TestSmartCardAPI(unittest.TestCase):
    """Test cases for the Smart Card API."""

    def setUp(self):
        """Set up test fixtures."""
        # Create mock for asyncio.to_thread
        self.to_thread_patcher = patch('asyncio.to_thread')
        self.mock_to_thread = self.to_thread_patcher.start()
        self.mock_to_thread.return_value = {'name': 'spaces/123/messages/456', 'createTime': '2025-07-03T12:00:00Z'}

        # Create mock for _get_chat_service_with_fallback
        self.get_service_patcher = patch('gchat.content_mapping.smart_card_api._get_chat_service_with_fallback')
        self.mock_get_service = self.get_service_patcher.start()
        
        # Mock chat service
        self.mock_chat_service = MagicMock()
        self.mock_messages = MagicMock()
        self.mock_spaces = MagicMock()
        self.mock_create = MagicMock()
        self.mock_execute = MagicMock()
        
        self.mock_chat_service.spaces.return_value = self.mock_spaces
        self.mock_spaces.messages.return_value = self.mock_messages
        self.mock_messages.create.return_value = self.mock_create
        self.mock_create.execute.return_value = {'name': 'spaces/123/messages/456', 'createTime': '2025-07-03T12:00:00Z'}
        
        self.mock_get_service.return_value = self.mock_chat_service
        
        # Create mock for _find_card_component
        self.find_component_patcher = patch('gchat.content_mapping.smart_card_api._find_card_component')
        self.mock_find_component = self.find_component_patcher.start()
        self.mock_find_component.return_value = [
            {
                'component': MagicMock(),
                'path': 'card_framework.v2.Card',
                'score': 0.95,
                'type': 'simple'
            }
        ]
        
        # Create mock for _create_card_from_component
        self.create_card_patcher = patch('gchat.content_mapping.smart_card_api._create_card_from_component')
        self.mock_create_card = self.create_card_patcher.start()
        self.mock_create_card.return_value = {'header': {'title': 'Test Card'}, 'sections': []}
        
        # Create mock for _convert_card_to_google_format
        self.convert_card_patcher = patch('gchat.content_mapping.smart_card_api._convert_card_to_google_format')
        self.mock_convert_card = self.convert_card_patcher.start()
        self.mock_convert_card.return_value = {'cardId': 'test_card_123', 'card': {'header': {'title': 'Test Card'}, 'sections': []}}
        
        # Create mock for Message
        self.message_patcher = patch('gchat.content_mapping.smart_card_api.Message')
        self.mock_message_class = self.message_patcher.start()
        self.mock_message = MagicMock()
        self.mock_message.cards_v2 = []
        self.mock_message.render.return_value = {'cardsV2': [{'cardId': 'test_card_123', 'card': {'header': {'title': 'Test Card'}, 'sections': []}}]}
        self.mock_message_class.return_value = self.mock_message
        
        # Create mock for requests
        self.requests_patcher = patch('requests.post')
        self.mock_requests_post = self.requests_patcher.start()
        self.mock_response = MagicMock()
        self.mock_response.status_code = 200
        self.mock_requests_post.return_value = self.mock_response

    def tearDown(self):
        """Tear down test fixtures."""
        self.to_thread_patcher.stop()
        self.get_service_patcher.stop()
        self.find_component_patcher.stop()
        self.create_card_patcher.stop()
        self.convert_card_patcher.stop()
        self.message_patcher.stop()
        self.requests_patcher.stop()

    def test_parse_natural_language_content(self):
        """Test parsing natural language content."""
        # Test with pipe separator
        content = "Title: Meeting Update | Text: Team standup at 2 PM | Button: Join -> https://meet.google.com/abc"
        result = parse_natural_language_content(content)
        
        self.assertEqual(result['title'], 'Meeting Update')
        self.assertEqual(result['text'], 'Team standup at 2 PM')
        self.assertEqual(len(result['buttons']), 1)
        self.assertEqual(result['buttons'][0]['text'], 'Join')
        self.assertEqual(result['buttons'][0]['url'], 'https://meet.google.com/abc')
        
        # Test with newline separator
        content = """
        Title: Project Status
        Text: Sprint completed successfully
        Button: View Dashboard -> https://dashboard.example.com
        """
        result = parse_natural_language_content(content)
        
        self.assertEqual(result['title'], 'Project Status')
        self.assertEqual(result['text'], 'Sprint completed successfully')
        self.assertEqual(len(result['buttons']), 1)
        self.assertEqual(result['buttons'][0]['text'], 'View Dashboard')
        self.assertEqual(result['buttons'][0]['url'], 'https://dashboard.example.com')

    @patch('gchat.content_mapping.smart_card_api._ensure_template_manager_initialized')
    async def test_send_smart_card(self, mock_ensure_initialized):
        """Test sending a smart card."""
        # Mock content mapping engine
        _content_mapping_engine.parse_content = MagicMock()
        _content_mapping_engine.parse_content.return_value = {
            'header': {'title': 'Meeting Update'},
            'sections': [{'widgets': [{'textParagraph': {'text': 'Team standup at 2 PM'}}]}]
        }
        
        # Mock card validator
        _card_validator.validate_card_structure = MagicMock()
        _card_validator.validate_card_structure.return_value = (True, [])
        
        # Test sending via API
        result = await send_smart_card(
            user_google_email="user@example.com",
            space_id="spaces/123",
            content="Title: Meeting Update | Text: Team standup at 2 PM",
            style="announcement"
        )
        
        # Verify the result
        self.assertIn("✅ Smart card sent to space", result)
        self.assertIn("spaces/123", result)
        self.assertIn("user@example.com", result)
        
        # Verify the mocks were called correctly
        mock_ensure_initialized.assert_called_once()
        _content_mapping_engine.parse_content.assert_called_once()
        self.mock_find_component.assert_called_once_with("header card")
        self.mock_create_card.assert_called_once()
        self.mock_convert_card.assert_called_once()
        self.mock_get_service.assert_called_once_with("user@example.com")
        
        # Test sending via webhook
        result = await send_smart_card(
            user_google_email="user@example.com",
            space_id="spaces/123",
            content="Title: Meeting Update | Text: Team standup at 2 PM",
            style="default",
            webhook_url="https://chat.googleapis.com/v1/spaces/123/messages"
        )
        
        # Verify the result
        self.assertIn("✅ Smart card sent successfully via webhook", result)
        
        # Verify the webhook was called
        self.mock_requests_post.assert_called_once()

    @patch('gchat.content_mapping.smart_card_api._ensure_template_manager_initialized')
    async def test_create_card_from_template(self, mock_ensure_initialized):
        """Test creating a card from a template."""
        # Mock template manager
        _template_manager.find_templates = AsyncMock()
        _template_manager.find_templates.return_value = [
            {
                'template_id': 'template_123',
                'name': 'Meeting Template',
                'description': 'Template for meeting announcements'
            }
        ]
        
        _template_manager.get_template = AsyncMock()
        _template_manager.get_template.return_value = {
            'template_id': 'template_123',
            'name': 'Meeting Template',
            'description': 'Template for meeting announcements',
            'template': {'header': {'title': '{meeting_title}'}, 'sections': [{'widgets': [{'textParagraph': {'text': '{meeting_time}'}}]}]},
            'placeholders': {'meeting_title': 'header.title', 'meeting_time': 'sections.0.widgets.0.textParagraph.text'}
        }
        
        _template_manager.apply_template = MagicMock()
        _template_manager.apply_template.return_value = {
            'header': {'title': 'Team Standup'},
            'sections': [{'widgets': [{'textParagraph': {'text': '2 PM today'}}]}]
        }
        
        # Test sending via API
        result = await create_card_from_template(
            template_name="Meeting Template",
            content={
                'meeting_title': 'Team Standup',
                'meeting_time': '2 PM today'
            },
            user_google_email="user@example.com",
            space_id="spaces/123"
        )
        
        # Verify the result
        self.assertIn("✅ Template card sent to space", result)
        self.assertIn("spaces/123", result)
        self.assertIn("user@example.com", result)
        
        # Verify the mocks were called correctly
        mock_ensure_initialized.assert_called_once()
        _template_manager.find_templates.assert_called_once_with("Meeting Template")
        _template_manager.get_template.assert_called_once_with("template_123")
        _template_manager.apply_template.assert_called_once()
        self.mock_get_service.assert_called_once_with("user@example.com")

    async def test_create_card_from_description(self):
        """Test creating a card from a description without sending."""
        # Mock content mapping engine
        _content_mapping_engine.parse_content = MagicMock()
        _content_mapping_engine.parse_content.return_value = {
            'header': {'title': 'Meeting Update'},
            'sections': [{'widgets': [{'textParagraph': {'text': 'Team standup at 2 PM'}}]}]
        }
        
        # Mock parameter inference engine
        _parameter_inference_engine.infer_card_type = MagicMock()
        _parameter_inference_engine.infer_card_type.return_value = "simple"
        
        # Mock card validator
        _card_validator.validate_card_structure = MagicMock()
        _card_validator.validate_card_structure.return_value = (True, [])
        
        # Test creating card
        result = await create_card_from_description(
            description="Title: Meeting Update | Text: Team standup at 2 PM"
        )
        
        # Verify the result
        self.assertEqual(result['card_type'], "simple")
        self.assertIn('card', result)
        
        # Verify the mocks were called correctly
        _content_mapping_engine.parse_content.assert_called_once()
        _parameter_inference_engine.infer_card_type.assert_called_once()
        self.mock_find_component.assert_called_once_with("simple card")
        self.mock_create_card.assert_called_once()


def run_async_test(coro):
    """Helper function to run async tests."""
    return asyncio.run(coro)


if __name__ == '__main__':
    unittest.main()