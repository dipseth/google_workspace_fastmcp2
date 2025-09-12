import pytest
import asyncio
from jsonschema import ValidationError
from datetime import datetime

# Import the validation function from service_resources
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from resources.service_resources import validate_service_config

@pytest.mark.service("resources")
class TestGoogleServiceResources:
    """Test Google Service Configuration resources using the FastMCP Client."""

    @pytest.mark.asyncio
    async def test_get_service_config_gmail(self, client):
        """Test retrieving Gmail service configuration."""
        result = await client.read_resource("google://services/gmail/config")
        
        assert result is not None
        assert result.get("service") == "gmail"
        assert result["configuration"]["api_name"] == "gmail"
        assert result["configuration"]["api_version"] == "v1"
        assert "https://gmail.googleapis.com" in result["configuration"]["base_url"]
        assert "https://mail.google.com/" in result["configuration"]["scopes"]["full"]
        assert result["metadata"]["authentication_required"] is True
        assert "email" in result["metadata"]["tags"]
        
        # Ensure it passes schema validation (handled internally by resource)
        # We can also explicitly validate the returned structure
        validate_service_config(result)

    @pytest.mark.asyncio
    async def test_get_service_config_drive(self, client):
        """Test retrieving Drive service configuration."""
        result = await client.read_resource("google://services/drive/config")
        
        assert result is not None
        assert result.get("service") == "drive"
        assert result["configuration"]["api_name"] == "drive"
        assert result["configuration"]["api_version"] == "v3"
        assert "https://www.googleapis.com/drive" in result["configuration"]["base_url"]
        assert "https://www.googleapis.com/auth/drive" in result["configuration"]["scopes"]["full"]
        assert result["metadata"]["authentication_required"] is True
        assert "storage" in result["metadata"]["tags"]
        
        # Ensure it passes schema validation
        validate_service_config(result)

    @pytest.mark.asyncio
    async def test_get_service_config_invalid_service(self, client):
        """Test retrieving configuration for an invalid service type."""
        # The resource handler itself raises ValueError for unknown services
        with pytest.raises(Exception) as excinfo: # Catch generic Exception as Client might wrap ValueError
            await client.read_resource("google://services/non_existent_service/config")
        assert "No configuration found for Google service type: non_existent_service" in str(excinfo.value)

    @pytest.mark.asyncio
    async def test_get_service_scopes_by_group(self, client):
        """Test retrieving service scopes by group."""
        result = await client.read_resource("google://services/gmail/scopes/full")
        
        assert result is not None
        assert result.get("service_type") == "gmail"
        assert result.get("scope_group") == "full"
        assert "https://mail.google.com/" in result["scopes"]

    @pytest.mark.asyncio
    async def test_get_service_versions(self, client):
        """Test retrieving service API versions."""
        result = await client.read_resource("google://services/drive/versions")
        
        assert result is not None
        assert result.get("service_type") == "drive"
        assert "v2" in result["available_versions"]
        assert "v3" in result["available_versions"]

    @pytest.mark.asyncio
    async def test_get_service_quota(self, client):
        """Test retrieving service quota information."""
        result = await client.read_resource("google://services/gmail/quota")
        
        assert result is not None
        assert result.get("service_type") == "gmail"
        assert result["quota_limits"]["requests_per_minute"] == 1000

    @pytest.mark.asyncio
    async def test_get_service_endpoints(self, client):
        """Test retrieving service API endpoints."""
        result = await client.read_resource("google://services/calendar/endpoints")
        
        assert result is not None
        assert result.get("service_type") == "calendar"
        assert "https://www.googleapis.com/calendar/v3/" in result["base_endpoint"]

    # Note: Direct testing of schema validation failure via client is harder
    # because the server-side resource handler already validates and raises an error.
    # To test this, one would need to mock the server's internal behavior or
    # create a separate test resource that intentionally returns invalid data.
    # The current implementation validates internally, so if it returns, it's valid.
    # The test_schema_validation_failure in the previous version was mocking the server.
    # For client-side tests, we assume the server correctly handles validation.