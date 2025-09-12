"""Pytest configuration and fixtures for standardized client testing.

🔧 MCP Tools Used:
- N/A (Pytest configuration - enables testing of all MCP tools)
- Provides client fixture used by all MCP tool tests

🧪 What's Being Tested:
- Pytest fixture configuration for client testing
- Global test markers and categories
- Client instance management and reuse
- Test session configuration and cleanup
- Integration with base_test_config for connection management

🔍 Potential Duplications:
- No duplications - this is the central pytest configuration
- Eliminates fixture duplication across individual test files
- Provides shared client instance to avoid connection overhead

Note: This is the pytest framework configuration file.
"""

import pytest
import pytest_asyncio
import asyncio
import os
from .base_test_config import create_test_client, print_test_configuration
from .resource_helpers import (
    get_real_gmail_message_id, get_real_gmail_filter_id,
    get_real_drive_document_id, get_real_drive_folder_id,
    get_real_calendar_event_id, get_real_photos_album_id,
    get_real_forms_form_id, get_real_chat_space_id
)


def pytest_configure(config):
    """Configure pytest with custom markers and settings."""
    config.addinivalue_line(
        "markers",
        "auth_required: mark test as requiring authentication"
    )
    config.addinivalue_line(
        "markers",
        "service(name): mark test as belonging to a specific Google service"
    )
    config.addinivalue_line(
        "markers",
        "integration: mark test as integration test requiring server"
    )


@pytest.fixture(scope="session", autouse=True)
def print_global_test_config():
    """Print test configuration once per session."""
    print_test_configuration()


@pytest_asyncio.fixture
async def client():
    """Create a client connected to the running server with protocol auto-detection.
    
    This is the standard client fixture that all tests should use.
    """
    from .base_test_config import TEST_EMAIL, SERVER_URL
    from ..test_auth_utils import get_client_auth_config
    from fastmcp import Client
    
    # Create client directly in fixture to avoid double context management
    auth_config = get_client_auth_config(TEST_EMAIL)
    client_obj = Client(SERVER_URL, auth=auth_config)
    
    # Start the client connection
    await client_obj.__aenter__()
    
    try:
        yield client_obj
    finally:
        # Ensure client is properly closed
        await client_obj.__aexit__(None, None, None)


@pytest.fixture
async def custom_client():
    """Factory fixture for creating clients with custom email addresses."""
    async def _create_client(test_email: str):
        client = await create_test_client(test_email)
        async with client:
            yield client
    return _create_client


# =============================================================================
# Real ID Fixtures from Resource System
# =============================================================================

@pytest_asyncio.fixture
async def real_gmail_message_id(client):
    """Get a real Gmail message ID from resources."""
    real_id = await get_real_gmail_message_id(client)
    return real_id or "fake_message_id_fallback"

@pytest_asyncio.fixture  
async def real_gmail_filter_id(client):
    """Get a real Gmail filter ID from resources."""
    real_id = await get_real_gmail_filter_id(client)
    return real_id or "fake_filter_id_fallback"

@pytest_asyncio.fixture
async def real_drive_document_id(client):
    """Get a real Drive document ID from resources."""
    real_id = await get_real_drive_document_id(client)
    return real_id or "fake_document_id_fallback"

@pytest_asyncio.fixture
async def real_drive_folder_id(client):
    """Get a real Drive folder ID from resources."""
    real_id = await get_real_drive_folder_id(client)
    return real_id or "fake_folder_id_fallback"

@pytest_asyncio.fixture
async def real_calendar_event_id(client):
    """Get a real Calendar event ID from resources."""
    real_id = await get_real_calendar_event_id(client)
    return real_id or "fake_event_id_fallback"

@pytest_asyncio.fixture
async def real_photos_album_id(client):
    """Get a real Photos album ID from resources."""
    real_id = await get_real_photos_album_id(client)
    return real_id or "fake_album_id_fallback"

@pytest_asyncio.fixture
async def real_forms_form_id(client):
    """Get a real Forms form ID from resources."""
    real_id = await get_real_forms_form_id(client)
    return real_id or "fake_form_id_fallback"

@pytest_asyncio.fixture
async def real_chat_space_id(client):
    """Get a real Chat space ID from resources."""
    real_id = await get_real_chat_space_id(client)
    return real_id or "fake_space_id_fallback"


# Configure asyncio mode for all tests
pytest_plugins = ["pytest_asyncio"]


def pytest_collection_modifyitems(config, items):
    """Automatically mark async tests with asyncio marker."""
    for item in items:
        if asyncio.iscoroutinefunction(item.function):
            item.add_marker(pytest.mark.asyncio)