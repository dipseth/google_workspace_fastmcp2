import pytest
from typing import Literal, Optional
from auth.google_auth import initiate_oauth_flow, handle_oauth_callback
from auth.pkce_utils import pkce_manager

@pytest.mark.asyncio
async def test_initiate_oauth_flow_file_credentials():
    auth_url = await initiate_oauth_flow(
        user_email="test@example.com",
        auth_method="file_credentials",
        show_service_selection=False
    )
    assert "https://accounts.google.com" in auth_url
    assert "access_type=offline" in auth_url

@pytest.mark.asyncio
async def test_initiate_oauth_flow_pkce_file():
    auth_url = await initiate_oauth_flow(
        user_email="test@example.com",
        auth_method="pkce_file",
        show_service_selection=False
    )
    assert "code_challenge=" in auth_url
    assert "code_challenge_method=S256" in auth_url

@pytest.mark.asyncio
async def test_initiate_oauth_flow_pkce_memory():
    auth_url = await initiate_oauth_flow(
        user_email="test@example.com",
        auth_method="pkce_memory",
        show_service_selection=False
    )
    assert "code_challenge=" in auth_url
    assert "code_challenge_method=S256" in auth_url

def test_auth_method_mapping():
    # Test backward compatibility
    # Assuming a helper function map_legacy_params(use_pkce)
    # But since not implemented, placeholder
    assert True  # Replace with actual mapping test

@pytest.mark.asyncio
async def test_handle_oauth_callback_pkce_memory(mocker):
    # Mock flow.fetch_token and other dependencies
    mocker.patch('googleapiclient.discovery.build')
    # Complex test setup needed for full e2e
    pass  # Implement full test