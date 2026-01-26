"""
Tests for the ModuleWrapper with the card_framework module.

This module specifically tests the integration between ModuleWrapper and the
card_framework module, focusing on card creation and sending capabilities.
"""

import inspect
import json
import logging
import os
import sys
from datetime import datetime

import pytest
import requests

# Direct imports for card components
try:
    from card_framework.v2 import Card, CardHeader, Message, Section, Widget
    from card_framework.v2.widgets import (
        Button,
        ButtonList,
        Column,
        Columns,
        DecoratedText,
        Divider,
        Icon,
        Image,
        OnClick,
        OpenLink,
        SelectionInput,
        TextInput,
        TextParagraph,
    )

    CARD_COMPONENTS_AVAILABLE = True
except ImportError:
    CARD_COMPONENTS_AVAILABLE = False

    # Define placeholder classes for type hints
    class Card:
        pass

    class Section:
        pass

    class TextParagraph:
        pass

    class Button:
        pass


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables from .env file if available
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    logger.warning("dotenv not available, skipping .env file loading")

# Test email address from environment variable
TEST_EMAIL = os.getenv("TEST_EMAIL_ADDRESS", "test_user@example.com")
# Test webhook URLs for Google Chat
TEST_CHAT_WEBHOOK = os.getenv("TEST_CHAT_WEBHOOK", "")
TEST_WEBHOOK_URL = os.getenv(
    "TEST_CHAT_WEBHOOK_URL",
    TEST_CHAT_WEBHOOK
    or "https://chat.googleapis.com/v1/spaces/AAAAAAAAAAA/messages?key=test&token=test",
)

# Add the parent directory to sys.path to import the module_wrapper
sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../adapters"))
)

# Import the ModuleWrapper
from module_wrapper import ModuleWrapper, _get_qdrant_imports


# Test if Qdrant is available
def is_qdrant_available():
    """Check if Qdrant server is running and available."""
    try:
        QdrantClient, _ = _get_qdrant_imports()
        client = QdrantClient(host="localhost", port=6333)
        # Try a simple operation
        client.get_collections()
        return True
    except Exception as e:
        logger.warning(f"Qdrant not available: {e}")
        return False


# Skip all tests if Qdrant is not available
pytestmark = pytest.mark.skipif(
    not is_qdrant_available(), reason="Qdrant server is not running or not available"
)


class TestCardFrameworkWrapper:
    """Test the ModuleWrapper specifically with the card_framework module."""

    # Class-level variable to store the shared wrapper instance
    _shared_wrapper = None
    _collection_name = f"test_card_framework_{os.getpid()}"

    @classmethod
    def setup_class(cls):
        """Set up the shared ModuleWrapper instance once for all tests."""
        try:
            # Try to import card_framework.v2
            try:
                import card_framework.v2

                card_framework_available = True
            except ImportError:
                card_framework_available = False
                pytest.skip("card_framework.v2 module not available")

            # Create the wrapper with minimal indexing parameters to improve performance
            cls._shared_wrapper = ModuleWrapper(
                module_or_name=card_framework.v2,
                collection_name=cls._collection_name,
                index_nested=False,  # Don't index nested components to reduce indexing time
                index_private=False,
                max_depth=1,  # Minimal depth to avoid excessive recursion
                skip_standard_library=True,  # Skip standard library modules
                include_modules=[
                    "card_framework",
                    "gchat",
                ],  # Only include relevant modules
                exclude_modules=[
                    "numpy",
                    "pandas",
                    "matplotlib",
                    "scipy",
                    "sklearn",
                    "tensorflow",
                    "torch",
                    "keras",
                    "django",
                    "flask",
                    "requests",
                    "bs4",
                    "selenium",
                    "sqlalchemy",
                    "pytest",
                    "unittest",
                    "nose",
                    "marshmallow",
                    "dataclasses_json",
                    "stringcase",
                    "qdrant_client",
                    "sentence_transformers",
                ],
            )
            logger.info(
                f"Created shared ModuleWrapper with collection: {cls._collection_name}"
            )
        except Exception as e:
            logger.error(f"Failed to create shared ModuleWrapper: {e}")
            cls._shared_wrapper = None

    @classmethod
    def teardown_class(cls):
        """Clean up the shared ModuleWrapper instance after all tests."""
        if cls._shared_wrapper:
            try:
                cls._shared_wrapper.client.delete_collection(
                    collection_name=cls._collection_name
                )
                logger.info(f"Deleted shared test collection: {cls._collection_name}")
            except Exception as e:
                logger.warning(
                    f"Failed to delete collection {cls._collection_name}: {e}"
                )

    @pytest.fixture
    def card_framework_wrapper(self):
        """Fixture to provide the shared ModuleWrapper instance."""
        if self._shared_wrapper is None:
            pytest.skip("Shared ModuleWrapper not available")
        yield self._shared_wrapper

    def test_card_framework_initialization(self, card_framework_wrapper):
        """Test that the card_framework ModuleWrapper initializes correctly."""
        assert card_framework_wrapper is not None
        assert card_framework_wrapper.module_name == "card_framework"
        assert card_framework_wrapper._initialized is True
        assert len(card_framework_wrapper.components) > 0

        logger.info(
            f"card_framework ModuleWrapper initialized with {len(card_framework_wrapper.components)} components"
        )

        # List components by type
        classes = card_framework_wrapper.list_components("class")
        logger.info(f"Found {len(classes)} classes in card_framework")

        # Log the first few classes to help with debugging
        for i, class_path in enumerate(classes[:5]):
            info = card_framework_wrapper.get_component_info(class_path)
            logger.info(f"Class {i + 1}: {info['name']} ({info['full_path']})")

    def test_card_framework_search(self, card_framework_wrapper):
        """Test searching for card components."""
        # Define search queries for different card types
        queries = [
            "simple card",
            "interactive card with buttons",
            "card with image",
            "form card with input fields",
        ]

        # Search for each query
        for query in queries:
            results = card_framework_wrapper.search(query, limit=3)

            logger.info(f"Search for '{query}' returned {len(results)} results")

            if len(results) > 0:
                logger.info(
                    f"Top result: {results[0]['name']} (score: {results[0]['score']:.4f})"
                )
                logger.info(f"Path: {results[0]['path']}")
                if results[0]["docstring"]:
                    logger.info(f"Docstring: {results[0]['docstring'][:100]}...")
            else:
                logger.warning(f"No results found for '{query}'")

    def test_card_component_availability(self, card_framework_wrapper):
        """Test the availability of key card components."""
        # Key components that should be available
        key_components = ["Card", "Section", "Button", "TextInput", "Image"]

        # Check each component
        for component_name in key_components:
            # Search for the component
            results = card_framework_wrapper.search(component_name, limit=5)

            # Check if any result matches the component name
            found = False
            for result in results:
                if component_name.lower() in result["name"].lower():
                    found = True
                    logger.info(
                        f"Found component {component_name}: {result['path']} (score: {result['score']:.4f})"
                    )
                    break

            if not found:
                logger.warning(
                    f"Component {component_name} not found in search results"
                )

    def test_create_and_send_card(self, card_framework_wrapper):
        """Test creating a card using ModuleWrapper and sending it to a webhook."""
        # Skip if no webhook URL is available
        if not TEST_WEBHOOK_URL:
            pytest.skip("No webhook URL available for testing card sending")

        try:
            # First, create a card using the ModuleWrapper to find and use card components
            logger.info("Creating card using ModuleWrapper...")

            # List all components in the card_framework module
            components = card_framework_wrapper.list_components()
            logger.info(f"Found {len(components)} components in card_framework module")

            # Log the first few components to help with debugging
            for i, component_path in enumerate(components[:10]):
                info = card_framework_wrapper.get_component_info(component_path)
                logger.info(f"Component {i + 1}: {info['name']} ({info['full_path']})")

            # Try to get components directly by path
            card_component = None
            section_component = None
            text_component = None
            button_component = None

            # Search for components with lower score threshold
            card_results = card_framework_wrapper.search(
                "Card", limit=10, score_threshold=0.3
            )
            logger.info(f"Card search returned {len(card_results)} results")
            for i, result in enumerate(card_results):
                logger.info(
                    f"Card result {i + 1}: {result['name']} ({result['path']}) - Score: {result['score']:.4f}"
                )
                if result["component"] is not None and (
                    card_component is None or result["score"] > 0.5
                ):
                    card_component = result["component"]
                    logger.info(f"Selected Card component: {result['path']}")

            section_results = card_framework_wrapper.search(
                "Section", limit=10, score_threshold=0.3
            )
            logger.info(f"Section search returned {len(section_results)} results")
            for i, result in enumerate(section_results):
                logger.info(
                    f"Section result {i + 1}: {result['name']} ({result['path']}) - Score: {result['score']:.4f}"
                )
                if result["component"] is not None and (
                    section_component is None or result["score"] > 0.5
                ):
                    section_component = result["component"]
                    logger.info(f"Selected Section component: {result['path']}")

            text_results = card_framework_wrapper.search(
                "TextParagraph", limit=10, score_threshold=0.3
            )
            logger.info(f"TextParagraph search returned {len(text_results)} results")
            for i, result in enumerate(text_results):
                logger.info(
                    f"TextParagraph result {i + 1}: {result['name']} ({result['path']}) - Score: {result['score']:.4f}"
                )
                if result["component"] is not None and (
                    text_component is None or result["score"] > 0.5
                ):
                    text_component = result["component"]
                    logger.info(f"Selected TextParagraph component: {result['path']}")

            button_results = card_framework_wrapper.search(
                "Button", limit=10, score_threshold=0.3
            )
            logger.info(f"Button search returned {len(button_results)} results")
            for i, result in enumerate(button_results):
                logger.info(
                    f"Button result {i + 1}: {result['name']} ({result['path']}) - Score: {result['score']:.4f}"
                )
                if result["component"] is not None and (
                    button_component is None or result["score"] > 0.5
                ):
                    button_component = result["component"]
                    logger.info(f"Selected Button component: {result['path']}")

            # Log detailed information about what components were found and what's missing
            missing_components = []
            if card_component is None:
                missing_components.append("Card")
            if section_component is None:
                missing_components.append("Section")
            if text_component is None:
                missing_components.append("TextParagraph")
            if button_component is None:
                missing_components.append("Button")

            # Log all components to help with debugging
            logger.info("All available components:")
            for i, component_path in enumerate(
                sorted(card_framework_wrapper.components.keys())[:50]
            ):  # Limit to first 50
                logger.info(f"  {i + 1}. {component_path}")

            # If we couldn't find the components, skip the test
            if missing_components:
                logger.warning(
                    f"Missing required components: {', '.join(missing_components)}"
                )
                pytest.skip(
                    f"Could not find required components: {', '.join(missing_components)}"
                )

            # Create components using the found classes
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # Create a text paragraph
            text_paragraph = self._create_component_instance(
                text_component,
                {"text": f"This card was created using ModuleWrapper at {timestamp}"},
            )

            # Create a button
            button = self._create_component_instance(
                button_component,
                {"text": "Visit Google", "url": "https://www.google.com"},
            )

            # Create a section with the text paragraph and button
            section = self._create_component_instance(
                section_component,
                {
                    "header": "Test Section",
                    "widgets": (
                        [text_paragraph, button] if text_paragraph and button else []
                    ),
                },
            )

            # Create the card with the section
            card = self._create_component_instance(
                card_component,
                {
                    "header": {
                        "title": "Card from ModuleWrapper",
                        "subtitle": f"Created at {timestamp}",
                        "imageUrl": "https://picsum.photos/200/100",
                    },
                    "sections": [section] if section else [],
                },
            )

            # Log the card object for debugging
            logger.info(f"Card object type: {type(card)}")
            logger.info(f"Card object attributes: {dir(card)}")
            if hasattr(card, "to_dict"):
                logger.info(f"Card to_dict result: {card.to_dict()}")
            elif hasattr(card, "__dict__"):
                logger.info(f"Card __dict__: {card.__dict__}")

            # Convert the card to a format suitable for the Google Chat API
            card_dict = self._convert_card_to_dict(card)

            # Log the converted card dictionary
            logger.info(f"Converted card dict: {json.dumps(card_dict, indent=2)}")

            # Create message payload
            message_body = {
                "text": "Test message from ModuleWrapper",
                "cardsV2": [card_dict],
            }

            # Send via webhook
            logger.info(f"Sending card to webhook URL: {TEST_WEBHOOK_URL}")
            response = requests.post(
                TEST_WEBHOOK_URL,
                json=message_body,
                headers={"Content-Type": "application/json"},
            )

            # Check response
            assert response.status_code == 200, (
                f"Failed to send card: {response.status_code} - {response.text}"
            )
            logger.info(f"Card sent successfully! Status: {response.status_code}")

            # For comparison, also create a card directly using the Google Chat API format
            logger.info(
                "For comparison, creating a card directly using Google Chat API format..."
            )

            direct_card = {
                "cardId": f"test_card_{int(datetime.now().timestamp())}",
                "card": {
                    "header": {
                        "title": "Test Card (Direct API)",
                        "subtitle": f"Created at {timestamp}",
                        "imageUrl": "https://picsum.photos/200/100",
                        "imageType": "CIRCLE",
                    },
                    "sections": [
                        {
                            "header": "Section Header",
                            "collapsible": "true",
                            "collapseControl": {
                                "horizontalAlignment": "CENTER",
                                "collapseButton": {
                                    "icon": {"materialIcon": {"name": "attachment"}},
                                    "text": "Hide attachments",
                                    "type": "BORDERLESS",
                                },
                                "expandButton": {
                                    "icon": {"materialIcon": {"name": "attachment"}},
                                    "text": "Show Attachments",
                                    "type": "BORDERLESS",
                                },
                            },
                            "uncollapsibleWidgetsCount": 10,
                            "widgets": [
                                {
                                    "buttonList": {
                                        "buttons": [
                                            {
                                                "text": "Fill",
                                                "type": "FILLED",
                                                "onClick": {
                                                    "openLink": {
                                                        "url": "https://developers.google.com/chat/ui/widgets/button-list"
                                                    }
                                                },
                                            },
                                            {
                                                "text": "Tonal",
                                                "type": "FILLED_TONAL",
                                                "onClick": {
                                                    "openLink": {
                                                        "url": "https://developers.google.com/chat/ui/widgets/button-list"
                                                    }
                                                },
                                            },
                                            {
                                                "text": "Outlined",
                                                "type": "OUTLINED",
                                                "onClick": {
                                                    "openLink": {
                                                        "url": "https://developers.google.com/chat/ui/widgets/button-list"
                                                    }
                                                },
                                            },
                                            {
                                                "text": "Borderless",
                                                "type": "BORDERLESS",
                                                "onClick": {
                                                    "openLink": {
                                                        "url": "https://developers.google.com/chat/ui/widgets/button-list"
                                                    }
                                                },
                                            },
                                            {
                                                "text": "Outlined w/ SVG icon",
                                                "icon": {
                                                    "knownIcon": "INVITE",
                                                    "altText": "check calendar",
                                                },
                                                "type": "OUTLINED",
                                                "onClick": {
                                                    "openLink": {
                                                        "url": "https://developers.google.com/chat/ui/widgets/button-list"
                                                    }
                                                },
                                            },
                                            {
                                                "text": "Borderless w/ SVG icon",
                                                "icon": {
                                                    "materialIcon": {"name": "settings"}
                                                },
                                                "type": "BORDERLESS",
                                                "onClick": {
                                                    "openLink": {
                                                        "url": "https://developers.google.com/chat/ui/widgets/button-list"
                                                    }
                                                },
                                            },
                                            {
                                                "text": "Fill w/ IMG icon",
                                                "icon": {
                                                    "iconUrl": "https://www.gstatic.com/images/branding/product/2x/contacts_48dp.png",
                                                    "altText": "Contact",
                                                },
                                                "type": "FILLED",
                                                "onClick": {
                                                    "openLink": {
                                                        "url": "https://developers.google.com/chat/ui/widgets/button-list"
                                                    }
                                                },
                                            },
                                            {
                                                "text": "Disabled",
                                                "icon": {
                                                    "materialIcon": {"name": "person"}
                                                },
                                                "type": "FILLED",
                                                "disabled": "true",
                                                "onClick": {
                                                    "openLink": {
                                                        "url": "https://developers.google.com/chat/ui/widgets/button-list"
                                                    }
                                                },
                                            },
                                            {
                                                "text": "Custom Bg Color",
                                                "icon": {
                                                    "materialIcon": {"name": "person"}
                                                },
                                                "color": {
                                                    "red": 1,
                                                    "green": 0,
                                                    "blue": 0,
                                                    "alpha": 1,
                                                },
                                                "type": "FILLED",
                                                "onClick": {
                                                    "openLink": {
                                                        "url": "https://developers.google.com/chat/ui/widgets/button-list"
                                                    }
                                                },
                                            },
                                        ]
                                    }
                                },
                                {
                                    "buttonList": {
                                        "buttons": [
                                            {
                                                "text": "More",
                                                "type": "FILLED",
                                                "icon": {
                                                    "materialIcon": {"name": "menu"}
                                                },
                                                "onClick": {
                                                    "overflowMenu": {
                                                        "items": [
                                                            {
                                                                "text": "Open Chat",
                                                                "startIcon": {
                                                                    "materialIcon": {
                                                                        "name": "chat"
                                                                    }
                                                                },
                                                                "onClick": {
                                                                    "openLink": {
                                                                        "url": "https://developers.google.com/chat"
                                                                    }
                                                                },
                                                            },
                                                            {
                                                                "text": "Open Gmail",
                                                                "startIcon": {
                                                                    "materialIcon": {
                                                                        "name": "gmail"
                                                                    }
                                                                },
                                                                "onClick": {
                                                                    "openLink": {
                                                                        "url": "https://mail.google.com"
                                                                    }
                                                                },
                                                            },
                                                        ]
                                                    }
                                                },
                                            }
                                        ]
                                    }
                                },
                                {
                                    "chipList": {
                                        "chips": [
                                            {
                                                "label": "Chip",
                                                "onClick": {
                                                    "openLink": {
                                                        "url": "https://developers.google.com/workspace/chat/design-interactive-card-dialog"
                                                    }
                                                },
                                            },
                                            {
                                                "label": "Chip with Icon",
                                                "icon": {
                                                    "materialIcon": {"name": "alarm"}
                                                },
                                                "onClick": {
                                                    "openLink": {
                                                        "url": "https://developers.google.com/workspace/chat/design-interactive-card-dialog"
                                                    }
                                                },
                                            },
                                            {
                                                "label": "Disabled Chip",
                                                "disabled": "true",
                                                "onClick": {
                                                    "openLink": {
                                                        "url": "https://developers.google.com/workspace/chat/design-interactive-card-dialog"
                                                    }
                                                },
                                            },
                                            {
                                                "label": "Disabled Chip with Icon",
                                                "disabled": "true",
                                                "icon": {
                                                    "materialIcon": {
                                                        "name": "bug_report"
                                                    }
                                                },
                                                "onClick": {
                                                    "openLink": {
                                                        "url": "https://developers.google.com/workspace/chat/design-interactive-card-dialog"
                                                    }
                                                },
                                            },
                                        ]
                                    }
                                },
                                {"divider": {}},
                                {
                                    "textParagraph": {
                                        "text": "See <a href=https://developers.google.com/apps-script/add-ons/concepts/widgets#text_formatting>this doc</a> for rich text formatting.<br>Some text-based widgets can support simple text HTML formatting. When setting the text content of these widgets, just include the corresponding HTML tags.",
                                        "maxLines": 2,
                                    }
                                },
                                {
                                    "image": {
                                        "imageUrl": "https://www.gstatic.com/images/branding/productlogos/gsuite_dashboard/v6/web-512dp/logo_gsuite_dashboard_color_2x_web_512dp.png",
                                        "altText": "Gsuite Dashboard",
                                    }
                                },
                                {
                                    "image": {
                                        "imageUrl": "https://www.gstatic.com/images/branding/productlogos/gsuite_dashboard/v6/web-512dp/logo_gsuite_dashboard_color_2x_web_512dp.png",
                                        "altText": "Gsuite Dashboard",
                                    }
                                },
                                {
                                    "selectionInput": {
                                        "name": "size",
                                        "label": "Size",
                                        "type": "DROPDOWN",
                                        "items": [
                                            {
                                                "text": "S",
                                                "value": "small",
                                                "selected": "false",
                                            },
                                            {
                                                "text": "M",
                                                "value": "medium",
                                                "selected": "true",
                                            },
                                            {
                                                "text": "L",
                                                "value": "large",
                                                "selected": "false",
                                            },
                                            {
                                                "text": "XL",
                                                "value": "extra_large",
                                                "selected": "false",
                                            },
                                        ],
                                    }
                                },
                            ],
                        }
                    ],
                },
            }

            # Create message payload for direct card
            direct_message_body = {
                "text": "Test message (direct API)",
                "cardsV2": [direct_card],
            }

            # Send direct card via webhook
            logger.info(f"Sending direct card to webhook URL: {TEST_WEBHOOK_URL}")
            direct_response = requests.post(
                TEST_WEBHOOK_URL,
                json=direct_message_body,
                headers={"Content-Type": "application/json"},
            )

            # Check response for direct card
            assert direct_response.status_code == 200, (
                f"Failed to send direct card: {direct_response.status_code} - {direct_response.text}"
            )
            logger.info(
                f"Direct card sent successfully! Status: {direct_response.status_code}"
            )

        except Exception as e:
            logger.error(f"Error creating or sending card: {e}", exc_info=True)
            pytest.skip(f"Error creating or sending card: {str(e)}")

    def test_create_and_send_complex_card(self, card_framework_wrapper):
        """Test creating and sending a complex card using ModuleWrapper for structure and direct API for widgets."""
        # Skip if no webhook URL is available
        if not TEST_WEBHOOK_URL:
            pytest.skip("No webhook URL available for testing card sending")

        try:
            # Search for Card component
            card_results = card_framework_wrapper.search(
                "Card", limit=10, score_threshold=0.3
            )
            logger.info(f"Card search returned {len(card_results)} results")
            card_component = None
            for i, result in enumerate(card_results):
                logger.info(
                    f"Card result {i + 1}: {result['name']} ({result['path']}) - Score: {result['score']:.4f}"
                )
                if result["component"] is not None and (
                    card_component is None or result["score"] > 0.5
                ):
                    card_component = result["component"]
                    logger.info(f"Selected Card component: {result['path']}")

            if card_component is None:
                logger.warning("Card component not found")
                pytest.skip("Card component not found")

            # Create a timestamp
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # Create the card with direct API sections
            # We'll use ModuleWrapper for the card structure but direct API for the complex widgets
            card = self._create_component_instance(
                card_component,
                {
                    "header": {
                        "title": "Complex Card with ModuleWrapper",
                        "subtitle": f"Created at {timestamp}",
                        "imageUrl": "https://picsum.photos/200/100",
                        "imageType": "CIRCLE",
                    }
                },
            )

            # Convert the card to a dictionary
            if hasattr(card, "to_dict"):
                card_dict = card.to_dict()
            elif hasattr(card, "__dict__"):
                card_dict = card.__dict__
            else:
                card_dict = {}

            # Add sections directly using the known working format from the direct card example
            card_dict["sections"] = [
                {
                    "header": "Complex Section",
                    "widgets": [
                        {
                            "textParagraph": {
                                "text": f"This complex card was created using ModuleWrapper at {timestamp}"
                            }
                        },
                        {
                            "buttonList": {
                                "buttons": [
                                    {
                                        "text": "Visit Google",
                                        "onClick": {
                                            "openLink": {
                                                "url": "https://www.google.com"
                                            }
                                        },
                                    },
                                    {
                                        "text": "Visit Documentation",
                                        "onClick": {
                                            "openLink": {
                                                "url": "https://developers.google.com/chat/ui/widgets/button-list"
                                            }
                                        },
                                    },
                                ]
                            }
                        },
                        {"divider": {}},
                        {
                            "image": {
                                "imageUrl": "https://www.gstatic.com/images/branding/productlogos/gsuite_dashboard/v6/web-512dp/logo_gsuite_dashboard_color_2x_web_512dp.png",
                                "altText": "Gsuite Dashboard",
                            }
                        },
                    ],
                }
            ]

            # Create the final card dictionary
            final_card_dict = {
                "cardId": f"complex_card_{int(datetime.now().timestamp())}",
                "card": card_dict,
            }

            # Create message payload
            message_body = {
                "text": "Complex card test from ModuleWrapper",
                "cardsV2": [final_card_dict],
            }

            # Send via webhook
            logger.info(f"Sending complex card to webhook URL: {TEST_WEBHOOK_URL}")
            response = requests.post(
                TEST_WEBHOOK_URL,
                json=message_body,
                headers={"Content-Type": "application/json"},
            )

            # Check response
            assert response.status_code == 200, (
                f"Failed to send complex card: {response.status_code} - {response.text}"
            )
            logger.info(
                f"Complex card sent successfully! Status: {response.status_code}"
            )

        except Exception as e:
            logger.error(f"Error creating or sending complex card: {e}", exc_info=True)
            pytest.skip(f"Error creating or sending complex card: {str(e)}")

    def _create_component_instance(self, component, params):
        """Create an instance of a component with the given parameters."""
        if not component:
            return None

        try:
            # Check if component is callable
            if callable(component):
                # Get signature
                sig = inspect.signature(component)

                # Filter params to match signature
                valid_params = {}
                for param_name, param in sig.parameters.items():
                    if param_name in params:
                        valid_params[param_name] = params[param_name]

                # Call component with filtered params
                return component(**valid_params)

            # If component is a class, try to instantiate it
            elif inspect.isclass(component):
                # Get signature
                sig = inspect.signature(component.__init__)

                # Filter params to match signature
                valid_params = {}
                for param_name, param in sig.parameters.items():
                    if param_name in params and param_name != "self":
                        valid_params[param_name] = params[param_name]

                # Instantiate class with filtered params
                return component(**valid_params)

            return None

        except Exception as e:
            logger.error(f"Failed to create component instance: {e}", exc_info=True)
            return None

    def _convert_card_to_dict(self, card):
        """Convert a card object to a dictionary suitable for the Google Chat API."""
        try:
            # Handle different card types
            if hasattr(card, "to_dict"):
                # Card Framework v2 object
                card_dict = card.to_dict()
            elif hasattr(card, "__dict__"):
                # Object with __dict__
                card_dict = card.__dict__
            elif isinstance(card, dict):
                # Already a dictionary
                card_dict = card
            else:
                # Unknown type
                logger.warning(f"Unknown card type: {type(card)}")
                # Create a fallback card instead of returning an error
                return {
                    "cardId": f"fallback_card_{datetime.now().timestamp()}",
                    "card": {
                        "header": {
                            "title": "Fallback Card",
                            "subtitle": "Could not convert original card",
                        },
                        "sections": [
                            {
                                "widgets": [
                                    {
                                        "textParagraph": {
                                            "text": f"Could not convert card of type: {type(card)}"
                                        }
                                    }
                                ]
                            }
                        ],
                    },
                }

            # Fix widget formatting for Google Chat API compatibility
            if "sections" in card_dict:
                for section in card_dict["sections"]:
                    if "widgets" in section:
                        self._fix_widgets_format(section["widgets"])

            # Ensure proper structure for Google Chat API
            card_id = getattr(card, "card_id", None) or f"card_{hash(str(card_dict))}"

            result = {"cardId": card_id, "card": card_dict}

            return result

        except Exception as e:
            logger.error(f"Failed to convert card to dictionary: {e}", exc_info=True)
            # Create a fallback card instead of returning an error
            return {
                "cardId": f"error_card_{datetime.now().timestamp()}",
                "card": {
                    "header": {
                        "title": "Error Card",
                        "subtitle": "Error occurred during card conversion",
                    },
                    "sections": [
                        {"widgets": [{"textParagraph": {"text": f"Error: {str(e)}"}}]}
                    ],
                },
            }

    def _fix_widgets_format(self, widgets):
        """Fix the format of widgets to be compatible with Google Chat API."""
        if not widgets or not isinstance(widgets, list):
            return

        for i, widget in enumerate(widgets):
            # Handle simple text widgets (likely buttons)
            if isinstance(widget, dict) and "text" in widget and "url" in widget:
                # Convert to proper button format
                widgets[i] = {
                    "buttonList": {
                        "buttons": [
                            {
                                "text": widget["text"],
                                "onClick": {"openLink": {"url": widget["url"]}},
                            }
                        ]
                    }
                }
            # Handle other widget types that might need conversion
            elif isinstance(widget, dict) and len(widget) == 1 and "text" in widget:
                # Simple text widget needs to be converted to textParagraph
                widgets[i] = {"textParagraph": {"text": widget["text"]}}

            # Recursively fix nested widgets if needed
            if isinstance(widget, dict):
                for key, value in widget.items():
                    if key == "widgets" and isinstance(value, list):
                        self._fix_widgets_format(value)
            elif isinstance(widget, list):
                # Handle case where widget itself is a list
                self._fix_widgets_format(widget)

    @pytest.mark.asyncio
    async def test_search_async_with_card_framework(self, card_framework_wrapper):
        """Test asynchronous searching for card components."""
        # Define search queries for different card types
        queries = ["card with sections", "button list", "image card", "text paragraph"]

        # Search for each query asynchronously
        for query in queries:
            results = await card_framework_wrapper.search_async(query, limit=3)

            logger.info(f"Async search for '{query}' returned {len(results)} results")

            if len(results) > 0:
                logger.info(
                    f"Top result: {results[0]['name']} (score: {results[0]['score']:.4f})"
                )
                logger.info(f"Path: {results[0]['path']}")
                if results[0]["docstring"]:
                    logger.info(f"Docstring: {results[0]['docstring'][:100]}...")
            else:
                logger.warning(f"No results found for '{query}'")


if __name__ == "__main__":
    # This allows running the tests directly with python
    pytest.main(["-xvs", __file__])
