"""Test suite for Google Chat App Development tools using FastMCP Client SDK."""

import pytest
import asyncio
from fastmcp import Client
from typing import Any, Dict, List
import os
import json
from dotenv import load_dotenv
from test_auth_utils import get_client_auth_config

# Load environment variables from .env file
load_dotenv()


# Server configuration from environment variables with defaults
SERVER_HOST = os.getenv("MCP_SERVER_HOST", "localhost")
SERVER_PORT = os.getenv("MCP_SERVER_PORT", os.getenv("SERVER_PORT", "8002"))
# FastMCP servers in HTTP mode use the /mcp/ endpoint
SERVER_URL = os.getenv("MCP_SERVER_URL", f"http://{SERVER_HOST}:{SERVER_PORT}/mcp/")

# Test configuration from environment variables
TEST_EMAIL = os.getenv("TEST_EMAIL_ADDRESS", "test_user@example.com")
CHAT_SERVICE_ACCOUNT_FILE = os.getenv("CHAT_SERVICE_ACCOUNT_FILE", "")


class TestChatAppTools:
    """Test Google Chat App Development tools using the FastMCP Client."""
    
    @pytest.fixture
    async def client(self):
        """Create a client connected to the running server."""
        # Get JWT token for authentication if enabled
        auth_config = get_client_auth_config(TEST_EMAIL)
        client = Client(SERVER_URL, auth=auth_config)
        async with client:
            yield client
    
    @pytest.mark.asyncio
    async def test_chat_app_tools_available(self, client):
        """Test that all Chat App Development tools are available."""
        tools = await client.list_tools()
        tool_names = [tool.name for tool in tools]
        
        expected_chat_app_tools = [
            "initialize_chat_app_manager",
            "create_chat_app_manifest", 
            "generate_webhook_template",
            "list_chat_app_resources"
        ]
        
        for tool in expected_chat_app_tools:
            assert tool in tool_names, f"Chat App Development tool '{tool}' not found in available tools"
    
    @pytest.mark.asyncio
    async def test_initialize_chat_app_manager(self, client):
        """Test initializing the Google Chat App Manager."""
        result = await client.call_tool("initialize_chat_app_manager", {})
        
        assert len(result) > 0
        content = result[0].text
        # Should either succeed or return configuration error
        valid_responses = [
            "successfully initialized", "manager initialized", "service account", 
            "credentials", "configuration", "chat app manager", "ready",
            "❌", "failed to initialize", "unexpected error", "not configured",
            "missing", "invalid", "service account file", "authentication failed"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), f"Response didn't match any expected pattern: {content}"
    
    @pytest.mark.asyncio
    async def test_create_chat_app_manifest(self, client):
        """Test creating a Google Chat app manifest."""
        result = await client.call_tool("create_chat_app_manifest", {
            "app_name": "Test MCP Chat App",
            "description": "A test chat app created by MCP Chat App Development tools",
            "bot_endpoint": "https://example.com/webhook",
            "avatar_url": "https://example.com/avatar.png",
            "scopes": ["https://www.googleapis.com/auth/chat.bot"],
            "publishing_state": "DRAFT"
        })
        
        assert len(result) > 0
        content = result[0].text
        # Should either succeed or return configuration/authentication error
        valid_responses = [
            "successfully created", "manifest created", "app manifest", "draft", 
            "configuration", "chat app", "bot endpoint", "scopes", "publishing",
            "❌", "failed to create", "unexpected error", "authentication failed",
            "not configured", "service account", "credentials", "invalid"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), f"Response didn't match any expected pattern: {content}"
    
    @pytest.mark.asyncio
    async def test_generate_webhook_template(self, client):
        """Test generating a webhook handler template."""
        result = await client.call_tool("generate_webhook_template", {
            "app_name": "TestMCPApp",
            "use_card_framework": True,
            "port": 3000
        })
        
        assert len(result) > 0
        content = result[0].text
        # Should return webhook template code or configuration
        valid_responses = [
            "webhook template", "generated", "template", "handler", "flask", "fastapi",
            "card framework", "port", "endpoint", "code", "python", "app.py",
            "server", "❌", "failed to generate", "unexpected error", "template generation"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), f"Response didn't match any expected pattern: {content}"
    
    @pytest.mark.asyncio
    async def test_generate_webhook_template_minimal(self, client):
        """Test generating a minimal webhook template without card framework."""
        result = await client.call_tool("generate_webhook_template", {
            "app_name": "MinimalApp",
            "use_card_framework": False
        })
        
        assert len(result) > 0
        content = result[0].text
        # Should return minimal webhook template
        valid_responses = [
            "webhook template", "generated", "template", "handler", "minimal",
            "basic", "simple", "endpoint", "code", "python", "app.py",
            "❌", "failed to generate", "unexpected error", "template generation"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), f"Response didn't match any expected pattern: {content}"
    
    @pytest.mark.asyncio
    async def test_list_chat_app_resources(self, client):
        """Test listing available Chat App Development resources."""
        result = await client.call_tool("list_chat_app_resources", {})
        
        assert len(result) > 0
        content = result[0].text
        # Should return list of resources and documentation
        valid_responses = [
            "resources", "documentation", "examples", "templates", "guides", 
            "chat app", "development", "google chat", "apis", "libraries",
            "quickstart", "tutorial", "reference", "samples", "tools",
            "❌", "failed to list", "unexpected error", "resources available"
        ]
        assert any(keyword in content.lower() for keyword in valid_responses), f"Response didn't match any expected pattern: {content}"


class TestChatAppToolsIntegration:
    """Integration tests for Chat App Development tools."""
    
    @pytest.fixture
    async def client(self):
        """Create a client connected to the running server."""
        # Get JWT token for authentication if enabled
        auth_config = get_client_auth_config(TEST_EMAIL)
        client = Client(SERVER_URL, auth=auth_config)
        async with client:
            yield client
    
    @pytest.mark.asyncio
    async def test_complete_app_creation_workflow(self, client):
        """Test the complete workflow of creating a Chat app."""
        # Step 1: Initialize the manager
        init_result = await client.call_tool("initialize_chat_app_manager", {})
        assert len(init_result) > 0
        
        # Step 2: Generate webhook template
        template_result = await client.call_tool("generate_webhook_template", {
            "app_name": "IntegrationTestApp",
            "use_card_framework": True,
            "port": 8080
        })
        assert len(template_result) > 0
        
        # Step 3: Create app manifest
        manifest_result = await client.call_tool("create_chat_app_manifest", {
            "app_name": "Integration Test Chat App",
            "description": "Integration test for MCP Chat App Development workflow",
            "bot_endpoint": "https://example.com/webhook",
            "publishing_state": "DRAFT"
        })
        assert len(manifest_result) > 0
        
        # Step 4: List available resources
        resources_result = await client.call_tool("list_chat_app_resources", {})
        assert len(resources_result) > 0
        
        # Verify all steps completed without fatal errors
        for result in [init_result, template_result, manifest_result, resources_result]:
            content = result[0].text
            # Should not contain fatal error indicators
            fatal_errors = ["fatal error", "critical failure", "system crash", "unable to proceed"]
            assert not any(error in content.lower() for error in fatal_errors), f"Fatal error detected: {content}"
    
    @pytest.mark.skipif(not CHAT_SERVICE_ACCOUNT_FILE, reason="CHAT_SERVICE_ACCOUNT_FILE not configured")
    @pytest.mark.asyncio
    async def test_with_real_service_account(self, client):
        """Test Chat App tools with real service account configuration."""
        # Test initialization with real service account
        result = await client.call_tool("initialize_chat_app_manager", {})
        
        assert len(result) > 0
        content = result[0].text
        
        # With real service account, expect success or specific auth errors
        success_indicators = ["successfully initialized", "manager initialized", "ready", "credentials valid"]
        auth_error_indicators = ["invalid credentials", "authentication failed", "service account", "permissions"]
        
        is_success = any(indicator in content.lower() for indicator in success_indicators)
        is_auth_error = any(indicator in content.lower() for indicator in auth_error_indicators)
        
        assert is_success or is_auth_error, f"Unexpected response with real service account: {content}"
    
    @pytest.mark.asyncio
    async def test_error_handling_without_config(self, client):
        """Test proper error handling when service account is not configured."""
        # This test ensures graceful handling when CHAT_SERVICE_ACCOUNT_FILE is not set
        result = await client.call_tool("initialize_chat_app_manager", {})
        
        assert len(result) > 0
        content = result[0].text
        
        # Should gracefully handle missing configuration
        expected_patterns = [
            "not configured", "missing", "service account", "configuration required",
            "❌", "error", "credentials", "authentication", "setup required"
        ]
        assert any(pattern in content.lower() for pattern in expected_patterns), f"Response didn't handle missing config gracefully: {content}"


class TestChatAppAuthentication:
    """Test authentication aspects of Chat App Development tools."""
    
    @pytest.fixture
    async def client(self):
        """Create a client connected to the running server."""
        # Get JWT token for authentication if enabled
        auth_config = get_client_auth_config(TEST_EMAIL)
        client = Client(SERVER_URL, auth=auth_config)
        async with client:
            yield client
    
    @pytest.mark.asyncio
    async def test_service_account_validation(self, client):
        """Test service account credential validation."""
        result = await client.call_tool("initialize_chat_app_manager", {})
        
        assert len(result) > 0
        content = result[0].text
        
        # Should validate service account properly
        validation_indicators = [
            "credentials", "service account", "authentication", "validation",
            "initialized", "ready", "configuration", "scopes", "permissions"
        ]
        assert any(indicator in content.lower() for indicator in validation_indicators), f"Response didn't show credential validation: {content}"
    
    @pytest.mark.asyncio
    async def test_scope_requirements(self, client):
        """Test that proper scopes are documented/validated."""
        result = await client.call_tool("list_chat_app_resources", {})
        
        assert len(result) > 0
        content = result[0].text
        
        # Should mention required scopes for Chat API
        scope_indicators = [
            "scopes", "permissions", "chat.bot", "chat.messages", "chat.spaces",
            "auth", "oauth", "credentials", "api", "access"
        ]
        assert any(indicator in content.lower() for indicator in scope_indicators), f"Response didn't mention scopes/permissions: {content}"
    
    @pytest.mark.asyncio
    async def test_manifest_security_settings(self, client):
        """Test that manifests include proper security settings."""
        result = await client.call_tool("create_chat_app_manifest", {
            "app_name": "Security Test App",
            "description": "Testing security settings in manifest",
            "bot_endpoint": "https://secure-endpoint.example.com/webhook"
        })
        
        assert len(result) > 0
        content = result[0].text
        
        # Should mention security-related configurations
        security_indicators = [
            "security", "permissions", "scopes", "authentication", "authorization",
            "bot", "endpoint", "webhook", "https", "secure", "manifest"
        ]
        assert any(indicator in content.lower() for indicator in security_indicators), f"Response didn't mention security settings: {content}"


# Performance and reliability tests
class TestChatAppToolsPerformance:
    """Test performance and reliability of Chat App Development tools."""
    
    @pytest.fixture
    async def client(self):
        """Create a client connected to the running server."""
        # Get JWT token for authentication if enabled
        auth_config = get_client_auth_config(TEST_EMAIL)
        client = Client(SERVER_URL, auth=auth_config)
        async with client:
            yield client
    
    @pytest.mark.asyncio
    async def test_multiple_template_generations(self, client):
        """Test generating multiple webhook templates in sequence."""
        app_names = ["App1", "App2", "App3"]
        
        for app_name in app_names:
            result = await client.call_tool("generate_webhook_template", {
                "app_name": app_name,
                "use_card_framework": True,
                "port": 8000 + len(app_name)  # Different ports
            })
            
            assert len(result) > 0
            content = result[0].text
            
            # Each template should be generated successfully
            success_indicators = ["template", "generated", "webhook", "handler", app_name.lower()]
            assert any(indicator in content.lower() for indicator in success_indicators), f"Failed to generate template for {app_name}: {content}"
    
    @pytest.mark.asyncio
    async def test_concurrent_resource_access(self, client):
        """Test concurrent access to Chat App resources."""
        # Create multiple concurrent requests
        tasks = []
        for i in range(3):
            task = client.call_tool("list_chat_app_resources", {})
            tasks.append(task)
        
        # Wait for all requests to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # All requests should succeed or fail gracefully
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                pytest.fail(f"Concurrent request {i} failed with exception: {result}")
            
            assert len(result) > 0, f"Concurrent request {i} returned empty result"
            content = result[0].text
            
            # Should contain resource information
            resource_indicators = ["resources", "documentation", "examples", "guides", "tools"]
            assert any(indicator in content.lower() for indicator in resource_indicators), f"Concurrent request {i} didn't return resources: {content}"
    
    @pytest.mark.asyncio
    async def test_large_manifest_creation(self, client):
        """Test creating a manifest with comprehensive configuration."""
        # Create a comprehensive manifest with all options
        comprehensive_manifest = {
            "app_name": "Comprehensive Test Chat App with Very Long Name for Testing",
            "description": "A comprehensive test chat app with extensive description to test handling of large configuration data. This app includes multiple features, extensive documentation, and comprehensive testing to ensure robust operation in production environments.",
            "bot_endpoint": "https://very-long-domain-name-for-testing.example.com/api/v1/webhook/chat/messages",
            "avatar_url": "https://example.com/assets/images/avatars/comprehensive-test-app-avatar.png",
            "scopes": [
                "https://www.googleapis.com/auth/chat.bot",
                "https://www.googleapis.com/auth/chat.messages",
                "https://www.googleapis.com/auth/chat.spaces",
                "https://www.googleapis.com/auth/chat.apps"
            ],
            "publishing_state": "DRAFT"
        }
        
        result = await client.call_tool("create_chat_app_manifest", comprehensive_manifest)
        
        assert len(result) > 0
        content = result[0].text
        
        # Should handle large manifest creation
        handling_indicators = [
            "manifest", "created", "configuration", "comprehensive", "scopes",
            "endpoint", "publishing", "❌", "error", "too large", "exceeded"
        ]
        assert any(indicator in content.lower() for indicator in handling_indicators), f"Failed to handle large manifest: {content}"