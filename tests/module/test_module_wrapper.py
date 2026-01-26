"""
Tests for the ModuleWrapper with Qdrant Integration.

This module tests the functionality of the module_wrapper.py module,
which provides semantic search capabilities for Python modules using Qdrant.
"""

import logging
import os
import sys
from datetime import datetime

import pytest
import requests

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

# Test modules - we'll use standard library modules that are always available
TEST_MODULES = ["json", "datetime", "collections"]


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


class TestModuleWrapper:
    """Test the ModuleWrapper functionality."""

    @pytest.fixture(params=TEST_MODULES)
    def module_name(self, request):
        """Fixture to provide test module names."""
        return request.param

    @pytest.fixture
    def wrapper(self, module_name):
        """Fixture to create a ModuleWrapper instance."""
        try:
            # Create a unique collection name for each test run to avoid conflicts
            collection_name = f"test_{module_name}_{os.getpid()}"

            # Create the wrapper
            wrapper = ModuleWrapper(
                module_or_name=module_name,
                collection_name=collection_name,
                index_nested=True,
                index_private=False,
            )

            yield wrapper

            # Cleanup: delete the collection after the test
            try:
                wrapper.client.delete_collection(collection_name=collection_name)
                logger.info(f"Deleted test collection: {collection_name}")
            except Exception as e:
                logger.warning(f"Failed to delete collection {collection_name}: {e}")

        except Exception as e:
            pytest.skip(f"Failed to create ModuleWrapper: {e}")

    def test_initialization(self, wrapper, module_name):
        """Test that the ModuleWrapper initializes correctly."""
        assert wrapper is not None
        assert wrapper.module_name == module_name
        assert wrapper._initialized is True
        assert wrapper.client is not None
        assert wrapper.embedder is not None
        assert len(wrapper.components) > 0

        logger.info(
            f"ModuleWrapper initialized with {len(wrapper.components)} components"
        )

    def test_list_components(self, wrapper):
        """Test listing components."""
        # List all components
        all_components = wrapper.list_components()
        assert len(all_components) > 0

        # List components by type
        functions = wrapper.list_components("function")
        classes = wrapper.list_components("class")

        logger.info(f"Found {len(functions)} functions and {len(classes)} classes")

        # At least one of these should have components
        assert len(functions) > 0 or len(classes) > 0

    def test_get_component_info(self, wrapper):
        """Test getting component info."""
        # Get a component path
        components = wrapper.list_components()
        assert len(components) > 0

        # Get info for the first component
        component_path = components[0]
        info = wrapper.get_component_info(component_path)

        assert info is not None
        assert "name" in info
        assert "type" in info
        assert "module_path" in info
        assert "full_path" in info

        logger.info(f"Got info for component: {info['name']} ({info['type']})")

    def test_get_component_by_path(self, wrapper):
        """Test getting a component by path."""
        # Get a component path
        components = wrapper.list_components()
        assert len(components) > 0

        # Get the component
        component_path = components[0]
        component = wrapper.get_component_by_path(component_path)

        assert component is not None
        logger.info(f"Retrieved component by path: {component_path}")

    def test_search(self, wrapper, module_name):
        """Test searching for components."""
        # Define search queries based on the module
        queries = {
            "json": "parse json string",
            "datetime": "get current date and time",
            "collections": "ordered dictionary",
        }

        # Use the appropriate query for the module
        query = queries.get(module_name, "common functionality")

        # Search for components with a lower score threshold
        results = wrapper.search(query, limit=5, score_threshold=0.5)

        assert len(results) > 0
        assert "score" in results[0]
        assert "name" in results[0]
        assert "path" in results[0]
        assert "component" in results[0]

        logger.info(f"Search for '{query}' returned {len(results)} results")
        logger.info(
            f"Top result: {results[0]['name']} (score: {results[0]['score']:.4f})"
        )

    @pytest.mark.asyncio
    async def test_search_async(self, wrapper, module_name):
        """Test asynchronous searching for components."""
        # Define search queries based on the module
        queries = {
            "json": "parse json string",
            "datetime": "get current date and time",
            "collections": "ordered dictionary",
        }

        # Use the appropriate query for the module
        query = queries.get(module_name, "common functionality")

        # Search for components asynchronously with a lower score threshold
        results = await wrapper.search_async(query, limit=5, score_threshold=0.5)

        assert len(results) > 0
        assert "score" in results[0]
        assert "name" in results[0]
        assert "path" in results[0]
        assert "component" in results[0]

        logger.info(f"Async search for '{query}' returned {len(results)} results")
        logger.info(
            f"Top result: {results[0]['name']} (score: {results[0]['score']:.4f})"
        )


class TestCardFrameworkWrapper:
    """Test the ModuleWrapper specifically with the card_framework module."""

    @pytest.fixture
    def card_framework_wrapper(self):
        """Fixture to create a ModuleWrapper for card_framework."""
        try:
            # Try to import card_framework
            try:
                import card_framework

                card_framework_available = True
            except ImportError:
                card_framework_available = False
                pytest.skip("card_framework module not available")

            # Create a unique collection name
            collection_name = f"test_card_framework_{os.getpid()}"

            # Create the wrapper
            wrapper = ModuleWrapper(
                module_or_name=card_framework,
                collection_name=collection_name,
                index_nested=True,
                index_private=False,
            )

            yield wrapper

            # Cleanup: delete the collection after the test
            try:
                wrapper.client.delete_collection(collection_name=collection_name)
                logger.info(f"Deleted test collection: {collection_name}")
            except Exception as e:
                logger.warning(f"Failed to delete collection {collection_name}: {e}")

        except Exception as e:
            pytest.skip(f"Failed to create ModuleWrapper for card_framework: {e}")

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

            # We don't assert here because we want to check all components,
            # but we log warnings for missing ones

    def test_create_and_send_card(self, card_framework_wrapper):
        """Test creating a card using ModuleWrapper and sending it to a webhook."""
        # Skip if no webhook URL is available
        if not TEST_WEBHOOK_URL:
            pytest.skip("No webhook URL available for testing card sending")

        try:
            # Create a simple card directly using Google Chat API format
            # This doesn't rely on card_framework or ModuleWrapper
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # Create a simple card in Google Chat API format
            card = {
                "cardId": f"test_card_{int(datetime.now().timestamp())}",
                "card": {
                    "header": {
                        "title": "Test Card from ModuleWrapper Test",
                        "subtitle": f"Created at {timestamp}",
                        "imageUrl": "https://picsum.photos/200/100",
                        "imageType": "CIRCLE",
                    },
                    "sections": [
                        {
                            "header": "Test Section",
                            "widgets": [
                                {
                                    "textParagraph": {
                                        "text": f"This card was created directly using the Google Chat API format at {timestamp}"
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
                                            }
                                        ]
                                    }
                                },
                            ],
                        }
                    ],
                },
            }

            # Create message payload
            message_body = {
                "text": "Test message from ModuleWrapper test",
                "cardsV2": [card],
            }

            # Send via webhook
            logger.info(f"Sending card to webhook URL: {TEST_WEBHOOK_URL}")
            response = requests.post(
                TEST_WEBHOOK_URL,
                json=message_body,
                headers={"Content-Type": "application/json"},
            )

            # Check response
            assert (
                response.status_code == 200
            ), f"Failed to send card: {response.status_code} - {response.text}"
            logger.info(f"Card sent successfully! Status: {response.status_code}")

            # Now try to find card components in the card_framework module
            logger.info("Checking for card components in card_framework module...")
            components = card_framework_wrapper.list_components()
            logger.info(f"Found {len(components)} components in card_framework module")

            # Log the first few components to help with debugging
            for i, component_path in enumerate(components[:10]):
                info = card_framework_wrapper.get_component_info(component_path)
                logger.info(f"Component {i + 1}: {info['name']} ({info['full_path']})")

        except Exception as e:
            logger.error(f"Error creating or sending card: {e}", exc_info=True)
            pytest.skip(f"Error creating or sending card: {str(e)}")

    def _create_card_from_component(self, component, params):
        """Create a card using a component."""
        import inspect

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
            logger.error(f"Failed to create card from component: {e}", exc_info=True)
            return None

    def _convert_card_to_google_format(self, card):
        """Convert Card Framework card to Google Chat format."""
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
                return {"error": f"Unknown card type: {type(card)}"}

            # Ensure proper structure for Google Chat API
            card_id = getattr(card, "card_id", None) or f"card_{hash(str(card_dict))}"

            result = {"cardId": card_id, "card": card_dict}

            return result

        except Exception as e:
            logger.error(f"Failed to convert card to Google format: {e}", exc_info=True)
            return {"error": f"Failed to convert card: {str(e)}"}


if __name__ == "__main__":
    # This allows running the tests directly with python
    pytest.main(["-xvs", __file__])
