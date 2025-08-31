"""
End-to-End Test for OAuth Authentication Flow with OAuth Proxy

This test suite verifies the complete OAuth authentication flow including:
- Discovery endpoints
- Dynamic Client Registration (DCR) with temporary credentials
- OAuth Proxy credential mapping
- Token exchange
- Security validation (real credentials never exposed)
"""

import asyncio
import json
import logging
import os
import tempfile
import unittest
from pathlib import Path
from typing import Dict, Any, Optional
from unittest.mock import Mock, patch, AsyncMock, MagicMock
import aiohttp
import pytest
from datetime import datetime, timedelta, timezone

# Configure logging for detailed test output
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Test constants
TEST_SERVER_HOST = "localhost"
TEST_SERVER_PORT = 8002
BASE_URL = f"http://{TEST_SERVER_HOST}:{TEST_SERVER_PORT}"

# Test client metadata for DCR
TEST_CLIENT_METADATA = {
    "client_name": "Test MCP Client",
    "redirect_uris": [
        "http://127.0.0.1:6274/oauth/callback/debug",
        "http://localhost:3000/auth/callback"
    ],
    "grant_types": ["authorization_code", "refresh_token"],
    "response_types": ["code"],
    "scope": "openid email profile https://www.googleapis.com/auth/drive.file",
    "token_endpoint_auth_method": "client_secret_basic"
}

# Mock Google OAuth credentials (for testing only)
MOCK_GOOGLE_CLIENT_ID = "856407677608-test.apps.googleusercontent.com"
MOCK_GOOGLE_CLIENT_SECRET = "GOCSPX-test_secret_12345"


class TestOAuthFlowEndToEnd(unittest.TestCase):
    """End-to-end tests for OAuth authentication flow with OAuth Proxy."""
    
    @classmethod
    def setUpClass(cls):
        """Set up test environment."""
        # Create temporary credentials directory
        cls.temp_dir = tempfile.mkdtemp()
        cls.credentials_dir = Path(cls.temp_dir) / "credentials"
        cls.credentials_dir.mkdir(parents=True, exist_ok=True)
        
        # Mock environment variables
        os.environ["CREDENTIALS_DIR"] = str(cls.credentials_dir)
        os.environ["GOOGLE_CLIENT_ID"] = MOCK_GOOGLE_CLIENT_ID
        os.environ["GOOGLE_CLIENT_SECRET"] = MOCK_GOOGLE_CLIENT_SECRET
        
        logger.info(f"Test environment setup with credentials dir: {cls.credentials_dir}")
    
    @classmethod
    def tearDownClass(cls):
        """Clean up test environment."""
        import shutil
        if Path(cls.temp_dir).exists():
            shutil.rmtree(cls.temp_dir)
        logger.info("Test environment cleaned up")
    
    def setUp(self):
        """Set up each test."""
        # Clear any existing proxy clients
        from auth.oauth_proxy import oauth_proxy
        oauth_proxy._proxy_clients.clear()
        
        # Store registered clients for cleanup
        self.registered_clients = []
    
    def tearDown(self):
        """Clean up after each test."""
        # Clean up registered proxy clients
        from auth.oauth_proxy import oauth_proxy
        for client_id in self.registered_clients:
            if client_id in oauth_proxy._proxy_clients:
                del oauth_proxy._proxy_clients[client_id]
    
    def test_01_oauth_discovery_endpoints(self):
        """Test that OAuth discovery endpoints return correct metadata."""
        logger.info("\n=== Test 1: OAuth Discovery Endpoints ===")
        
        from auth.fastmcp_oauth_endpoints import setup_oauth_endpoints_fastmcp
        from fastmcp import FastMCP
        from starlette.requests import Request
        from starlette.responses import JSONResponse
        
        # Create a mock FastMCP instance with proper custom_route method
        mcp = FastMCP("test_mcp")
        mcp._custom_routes = {}
        
        # Add a mock custom_route method to store routes
        def mock_custom_route(path, methods=None):
            def decorator(func):
                mcp._custom_routes[path] = {"handler": func, "methods": methods}
                return func
            return decorator
        
        mcp.custom_route = mock_custom_route
        
        # Set up OAuth endpoints
        setup_oauth_endpoints_fastmcp(mcp)
        
        # Test 1: OAuth Protected Resource endpoint
        logger.info("Testing /.well-known/oauth-protected-resource")
        
        # Create mock request
        mock_request = Mock(spec=Request)
        mock_request.method = "GET"
        
        # Get the endpoint handler
        endpoint_handler = mcp._custom_routes.get("/.well-known/oauth-protected-resource")
        self.assertIsNotNone(endpoint_handler, "OAuth protected resource endpoint not registered")
        
        # Call the endpoint synchronously (wrap async call)
        async def test_protected_resource():
            response = await endpoint_handler["handler"](mock_request)
            return response
        
        response = asyncio.run(test_protected_resource())
        self.assertIsInstance(response, JSONResponse)
        
        # Parse response body
        metadata = json.loads(response.body.decode())
        
        # Verify required fields
        self.assertIn("resource_server", metadata)
        self.assertIn("authorization_servers", metadata)
        self.assertIn("bearer_methods_supported", metadata)
        self.assertIn("scopes_supported", metadata)
        
        # Verify Google OAuth is configured
        self.assertIn("https://accounts.google.com", metadata["authorization_servers"])
        
        logger.info(f"✅ OAuth protected resource metadata: {list(metadata.keys())}")
        
        # Test 2: OAuth Authorization Server endpoint
        logger.info("\nTesting /.well-known/oauth-authorization-server")
        
        endpoint_handler = mcp._custom_routes.get("/.well-known/oauth-authorization-server")
        self.assertIsNotNone(endpoint_handler, "OAuth authorization server endpoint not registered")
        
        async def test_auth_server():
            response = await endpoint_handler["handler"](mock_request)
            return response
        
        response = asyncio.run(test_auth_server())
        metadata = json.loads(response.body.decode())
        
        # Verify required OAuth 2.0 metadata fields
        self.assertIn("issuer", metadata)
        self.assertIn("authorization_endpoint", metadata)
        self.assertIn("token_endpoint", metadata)
        self.assertIn("registration_endpoint", metadata)
        self.assertIn("grant_types_supported", metadata)
        self.assertIn("response_types_supported", metadata)
        
        # Verify our local endpoints are configured
        self.assertIn("/oauth/register", metadata["registration_endpoint"])
        self.assertIn("/oauth/token", metadata["token_endpoint"])
        
        logger.info(f"✅ OAuth authorization server metadata verified")
        logger.info(f"   Registration endpoint: {metadata['registration_endpoint']}")
        logger.info(f"   Token endpoint: {metadata['token_endpoint']}")
    
    @patch.object(Path, 'exists', return_value=True)
    def test_02_dynamic_client_registration(self, mock_exists):
        """Test Dynamic Client Registration with OAuth Proxy."""
        logger.info("\n=== Test 2: Dynamic Client Registration with OAuth Proxy ===")
        
        # Mock OAuth configuration methods at class level
        from config.settings import Settings
        
        with patch.object(Settings, 'is_oauth_configured', return_value=True), \
             patch.object(Settings, 'get_oauth_client_config', return_value={
                 'client_id': MOCK_GOOGLE_CLIENT_ID,
                 'client_secret': MOCK_GOOGLE_CLIENT_SECRET
             }):
            from auth.dynamic_client_registration import client_registry
            from auth.oauth_proxy import oauth_proxy
            
            # Register a client via DCR
            logger.info("Registering client with DCR...")
            registration_response = client_registry.register_client(TEST_CLIENT_METADATA)
            
            # Verify registration response
            self.assertIn("client_id", registration_response)
            self.assertIn("client_secret", registration_response)
            self.assertIn("registration_access_token", registration_response)
            
            temp_client_id = registration_response["client_id"]
            temp_client_secret = registration_response["client_secret"]
            reg_access_token = registration_response["registration_access_token"]
            
            # Store for cleanup
            self.registered_clients.append(temp_client_id)
            
            # Verify temporary credentials format
            self.assertTrue(temp_client_id.startswith("mcp_"),
                           f"Client ID should be temporary (mcp_*): {temp_client_id}")
            
            logger.info(f"✅ Client registered with temporary credentials:")
            logger.info(f"   Temp Client ID: {temp_client_id}")
            logger.info(f"   Temp Secret Length: {len(temp_client_secret)}")
            
            # Verify real credentials are NOT exposed
            self.assertNotEqual(temp_client_id, MOCK_GOOGLE_CLIENT_ID)
            self.assertNotEqual(temp_client_secret, MOCK_GOOGLE_CLIENT_SECRET)
            
            logger.info("✅ Real Google credentials are NOT exposed")
            
            # Verify OAuth Proxy has the mapping
            proxy_client = oauth_proxy.get_proxy_client(temp_client_id)
            self.assertIsNotNone(proxy_client, "Proxy client not found in OAuth Proxy")
            
            # Verify proxy client stores real credentials internally
            self.assertEqual(proxy_client.real_client_id, MOCK_GOOGLE_CLIENT_ID)
            self.assertEqual(proxy_client.real_client_secret, MOCK_GOOGLE_CLIENT_SECRET)
            
            logger.info("✅ OAuth Proxy correctly maps temporary to real credentials")
            
            # Test credential retrieval through proxy
            real_creds = oauth_proxy.get_real_credentials(temp_client_id, temp_client_secret)
            self.assertIsNotNone(real_creds)
            real_client_id, real_client_secret = real_creds
            self.assertEqual(real_client_id, MOCK_GOOGLE_CLIENT_ID)
            self.assertEqual(real_client_secret, MOCK_GOOGLE_CLIENT_SECRET)
            
            logger.info("✅ OAuth Proxy can retrieve real credentials with valid temp credentials")
            
            # Test invalid temp secret
            invalid_creds = oauth_proxy.get_real_credentials(temp_client_id, "wrong_secret")
            self.assertIsNone(invalid_creds, "Should not return credentials with invalid secret")
            
            logger.info("✅ OAuth Proxy rejects invalid temporary credentials")
    
    @patch('requests.post')
    @patch.object(Path, 'exists', return_value=True)
    def test_03_token_exchange_with_proxy(self, mock_exists, mock_post):
        """Test token exchange through OAuth Proxy."""
        logger.info("\n=== Test 3: Token Exchange with OAuth Proxy ===")
        
        # Mock OAuth configuration methods at class level
        from config.settings import Settings
        
        with patch.object(Settings, 'is_oauth_configured', return_value=True), \
             patch.object(Settings, 'get_oauth_client_config', return_value={
                 'client_id': MOCK_GOOGLE_CLIENT_ID,
                 'client_secret': MOCK_GOOGLE_CLIENT_SECRET
             }):
            from auth.dynamic_client_registration import client_registry
            from auth.oauth_proxy import handle_token_exchange
            
            # First register a client
            registration_response = client_registry.register_client(TEST_CLIENT_METADATA)
            temp_client_id = registration_response["client_id"]
            temp_client_secret = registration_response["client_secret"]
            
            # Store for cleanup
            self.registered_clients.append(temp_client_id)
            
            logger.info(f"Registered proxy client: {temp_client_id}")
            
            # Mock Google's token response
            mock_token_response = {
                "access_token": "ya29.test_access_token_12345",
                "token_type": "Bearer",
                "expires_in": 3600,
                "refresh_token": "1//test_refresh_token_67890",
                "scope": "openid email profile https://www.googleapis.com/auth/drive.file"
            }
            
            mock_response = Mock()
            mock_response.json.return_value = mock_token_response
            mock_response.raise_for_status = Mock()
            mock_post.return_value = mock_response
            
            # Test token exchange with temporary credentials
            logger.info("Testing token exchange with temporary credentials...")
            
            test_auth_code = "4/test_authorization_code_abc123"
            test_redirect_uri = "http://localhost:3000/auth/callback"
            
            token_result = handle_token_exchange(
                auth_code=test_auth_code,
                client_id=temp_client_id,  # Using TEMPORARY credentials
                client_secret=temp_client_secret,
                redirect_uri=test_redirect_uri,
                code_verifier=None  # Test without PKCE first
            )
            
            # Verify token exchange succeeded
            self.assertIsNotNone(token_result)
            self.assertIn("access_token", token_result)
            self.assertEqual(token_result["access_token"], mock_token_response["access_token"])
            
            logger.info("✅ Token exchange successful with temporary credentials")
            
            # Verify that Google was called with REAL credentials
            mock_post.assert_called_once()
            call_args = mock_post.call_args
            
            # Check the data sent to Google
            sent_data = call_args[1]["data"] if "data" in call_args[1] else call_args[0][1]
            
            # Verify REAL credentials were used with Google
            self.assertEqual(sent_data["client_id"], MOCK_GOOGLE_CLIENT_ID)
            self.assertEqual(sent_data["client_secret"], MOCK_GOOGLE_CLIENT_SECRET)
            
            logger.info("✅ Google OAuth was called with REAL credentials (not temporary)")
            logger.info(f"   Real Client ID used: {sent_data['client_id'][:20]}...")
            
            # Test with invalid temporary credentials
            logger.info("\nTesting token exchange with invalid credentials...")
            
            with self.assertRaises(ValueError) as context:
                handle_token_exchange(
                    auth_code=test_auth_code,
                    client_id="mcp_invalid_client",
                    client_secret="invalid_secret",
                    redirect_uri=test_redirect_uri,
                    code_verifier=None  # Test invalid credentials without PKCE
                )
        
            self.assertIn("Invalid proxy client credentials", str(context.exception))
            logger.info("✅ Token exchange rejected with invalid temporary credentials")
    
    @patch.object(Path, 'exists', return_value=True)
    def test_04_client_deletion(self, mock_exists):
        """Test client deletion through OAuth Proxy."""
        logger.info("\n=== Test 4: Client Deletion ===")
        
        # Mock OAuth configuration methods at class level
        from config.settings import Settings
        
        with patch.object(Settings, 'is_oauth_configured', return_value=True), \
             patch.object(Settings, 'get_oauth_client_config', return_value={
                 'client_id': MOCK_GOOGLE_CLIENT_ID,
                 'client_secret': MOCK_GOOGLE_CLIENT_SECRET
             }):
            from auth.dynamic_client_registration import client_registry
            from auth.oauth_proxy import oauth_proxy
            
            # Register a client
            registration_response = client_registry.register_client(TEST_CLIENT_METADATA)
            temp_client_id = registration_response["client_id"]
            reg_access_token = registration_response["registration_access_token"]
            
            logger.info(f"Registered client: {temp_client_id}")
            
            # Verify client exists
            proxy_client = oauth_proxy.get_proxy_client(temp_client_id)
            self.assertIsNotNone(proxy_client)
            
            # Delete the client
            success = client_registry.delete_client(temp_client_id, reg_access_token)
            self.assertTrue(success, "Client deletion should succeed")
            
            logger.info("✅ Client deleted successfully")
            
            # Verify client no longer exists
            proxy_client = oauth_proxy.get_proxy_client(temp_client_id)
            self.assertIsNone(proxy_client, "Client should not exist after deletion")
            
            logger.info("✅ Client removed from OAuth Proxy")
            
            # Test deletion with invalid token
            registration_response = client_registry.register_client(TEST_CLIENT_METADATA)
            temp_client_id = registration_response["client_id"]
            self.registered_clients.append(temp_client_id)
        
            # Try to delete with invalid token - should return False
            success = client_registry.delete_client(temp_client_id, "invalid_token")
            self.assertFalse(success, "Client deletion should fail with invalid token")
            
            # Verify client still exists (wasn't deleted)
            proxy_client = oauth_proxy.get_proxy_client(temp_client_id)
            self.assertIsNotNone(proxy_client, "Client should still exist after failed deletion")
            
            logger.info("✅ Client deletion rejected with invalid token")
    
    def test_05_credential_storage(self):
        """Test credential storage and retrieval."""
        logger.info("\n=== Test 5: Credential Storage ===")
        
        from auth.middleware import AuthMiddleware, CredentialStorageMode
        from google.oauth2.credentials import Credentials
        
        # Create middleware with file storage
        middleware = AuthMiddleware(storage_mode=CredentialStorageMode.FILE_PLAINTEXT)
        
        # Create test credentials
        test_email = "test_user@example.com"
        test_credentials = Credentials(
            token="test_access_token",
            refresh_token="test_refresh_token",
            token_uri="https://oauth2.googleapis.com/token",
            client_id=MOCK_GOOGLE_CLIENT_ID,
            client_secret=MOCK_GOOGLE_CLIENT_SECRET,
            scopes=["https://www.googleapis.com/auth/drive.file"]
        )
        
        # Save credentials
        middleware.save_credentials(test_email, test_credentials)
        logger.info(f"✅ Saved credentials for {test_email}")
        
        # Verify file was created
        safe_email = test_email.replace("@", "_at_").replace(".", "_")
        creds_file = self.credentials_dir / f"{safe_email}_credentials.json"
        self.assertTrue(creds_file.exists(), f"Credential file should exist: {creds_file}")
        
        logger.info(f"✅ Credential file created: {creds_file.name}")
        
        # Load credentials
        loaded_creds = middleware.load_credentials(test_email)
        self.assertIsNotNone(loaded_creds, "Should load saved credentials")
        self.assertEqual(loaded_creds.token, test_credentials.token)
        self.assertEqual(loaded_creds.refresh_token, test_credentials.refresh_token)
        
        logger.info("✅ Credentials loaded successfully")
        
        # Test with non-existent user
        missing_creds = middleware.load_credentials("nonexistent@example.com")
        self.assertIsNone(missing_creds, "Should return None for non-existent user")
        
        logger.info("✅ Returns None for non-existent credentials")
    
    def test_06_security_validation(self):
        """Test security validations to ensure real credentials are never exposed."""
        logger.info("\n=== Test 6: Security Validation ===")
        
        from auth.oauth_proxy import oauth_proxy, ProxyClient
        from datetime import datetime, timezone
        
        # Create a proxy client manually
        proxy_client = ProxyClient(
            temp_client_id="mcp_test_security",
            temp_client_secret="temp_secret_123",
            real_client_id=MOCK_GOOGLE_CLIENT_ID,
            real_client_secret=MOCK_GOOGLE_CLIENT_SECRET,
            client_metadata=TEST_CLIENT_METADATA,
            created_at=datetime.now(timezone.utc)
        )
        
        oauth_proxy._proxy_clients["mcp_test_security"] = proxy_client
        
        # Test 1: Cannot get real credentials without correct temp secret
        result = oauth_proxy.get_real_credentials("mcp_test_security", "wrong_secret")
        self.assertIsNone(result, "Should not return credentials with wrong secret")
        
        logger.info("✅ Real credentials protected with wrong temp secret")
        
        # Test 2: Cannot get real credentials for non-existent client
        result = oauth_proxy.get_real_credentials("mcp_nonexistent", "any_secret")
        self.assertIsNone(result, "Should not return credentials for non-existent client")
        
        logger.info("✅ No credentials returned for non-existent client")
        
        # Test 3: Expired clients are rejected
        expired_client = ProxyClient(
            temp_client_id="mcp_expired",
            temp_client_secret="expired_secret",
            real_client_id=MOCK_GOOGLE_CLIENT_ID,
            real_client_secret=MOCK_GOOGLE_CLIENT_SECRET,
            client_metadata=TEST_CLIENT_METADATA,
            created_at=datetime.now(timezone.utc) - timedelta(hours=25)  # Expired
        )
        
        oauth_proxy._proxy_clients["mcp_expired"] = expired_client
        
        result = oauth_proxy.get_real_credentials("mcp_expired", "expired_secret")
        self.assertIsNone(result, "Should not return credentials for expired client")
        self.assertNotIn("mcp_expired", oauth_proxy._proxy_clients, "Expired client should be removed")
        
        logger.info("✅ Expired proxy clients are rejected and cleaned up")
        
        # Test 4: Verify temp credentials don't contain real values
        from auth.dynamic_client_registration import client_registry
        from config.settings import Settings
        
        with patch.object(Settings, 'is_oauth_configured', return_value=True), \
             patch.object(Settings, 'get_oauth_client_config', return_value={
                 'client_id': MOCK_GOOGLE_CLIENT_ID,
                 'client_secret': MOCK_GOOGLE_CLIENT_SECRET
             }), \
             patch.object(Path, 'exists', return_value=True):
            registration = client_registry.register_client(TEST_CLIENT_METADATA)
            
            # Ensure returned credentials are temporary
            self.assertTrue(registration["client_id"].startswith("mcp_"))
            self.assertNotIn(MOCK_GOOGLE_CLIENT_ID, str(registration))
            self.assertNotIn(MOCK_GOOGLE_CLIENT_SECRET, str(registration))
            
            logger.info("✅ Registration response contains only temporary credentials")
            
            # Clean up
            self.registered_clients.append(registration["client_id"])
    
    def test_07_complete_flow_simulation(self):
        """Simulate complete OAuth flow from discovery to authentication."""
        logger.info("\n=== Test 7: Complete Flow Simulation ===")
        logger.info("Simulating MCP Inspector OAuth flow...")
        
        # Step 1: Discovery
        logger.info("\n1️⃣ DISCOVERY PHASE")
        
        from auth.fastmcp_oauth_endpoints import setup_oauth_endpoints_fastmcp
        from fastmcp import FastMCP
        from starlette.requests import Request
        
        # Create a mock FastMCP instance with proper custom_route method
        mcp = FastMCP("test_mcp")
        mcp._custom_routes = {}
        
        # Add a mock custom_route method to store routes
        def mock_custom_route(path, methods=None):
            def decorator(func):
                mcp._custom_routes[path] = {"handler": func, "methods": methods}
                return func
            return decorator
        
        mcp.custom_route = mock_custom_route
        
        # Now setup the endpoints
        setup_oauth_endpoints_fastmcp(mcp)
        
        # Discover OAuth endpoints
        mock_request = Mock(spec=Request)
        mock_request.method = "GET"
        
        endpoint_handler = mcp._custom_routes.get("/.well-known/oauth-authorization-server")
        self.assertIsNotNone(endpoint_handler, "OAuth authorization server endpoint should be registered")
        
        async def discover():
            response = await endpoint_handler["handler"](mock_request)
            return json.loads(response.body.decode())
        
        metadata = asyncio.run(discover())
        registration_endpoint = metadata["registration_endpoint"]
        token_endpoint = metadata["token_endpoint"]
        
        logger.info(f"✅ Discovered registration endpoint: {registration_endpoint}")
        logger.info(f"✅ Discovered token endpoint: {token_endpoint}")
        
        # Step 2: Dynamic Client Registration
        logger.info("\n2️⃣ CLIENT REGISTRATION PHASE")
        
        from config.settings import Settings
        from auth.dynamic_client_registration import client_registry
        
        with patch.object(Settings, 'is_oauth_configured', return_value=True), \
             patch.object(Settings, 'get_oauth_client_config', return_value={
                 'client_id': MOCK_GOOGLE_CLIENT_ID,
                 'client_secret': MOCK_GOOGLE_CLIENT_SECRET
             }), \
             patch.object(Path, 'exists', return_value=True):
            registration = client_registry.register_client(TEST_CLIENT_METADATA)
            temp_client_id = registration["client_id"]
            temp_client_secret = registration["client_secret"]
            
            self.registered_clients.append(temp_client_id)
            
            logger.info(f"✅ Registered with temporary credentials:")
            logger.info(f"   Client ID: {temp_client_id}")
            logger.info(f"   Secret: ***{temp_client_secret[-8:]}")
        
        # Step 3: User Authorization (simulated)
        logger.info("\n3️⃣ USER AUTHORIZATION PHASE")
        logger.info("   [User would be redirected to Google OAuth]")
        logger.info("   [User authorizes the application]")
        logger.info("   [Google returns authorization code]")
        
        simulated_auth_code = "4/simulated_authorization_code_xyz789"
        logger.info(f"✅ Received auth code: {simulated_auth_code[:20]}...")
        
        # Step 4: Token Exchange
        logger.info("\n4️⃣ TOKEN EXCHANGE PHASE")
        
        with patch('requests.post') as mock_post:
            # Mock Google's response
            mock_response = Mock()
            mock_response.json.return_value = {
                "access_token": "ya29.final_access_token",
                "token_type": "Bearer",
                "expires_in": 3600,
                "refresh_token": "1//final_refresh_token",
                "scope": "openid email profile"
            }
            mock_response.raise_for_status = Mock()
            mock_post.return_value = mock_response
            
            from auth.oauth_proxy import handle_token_exchange
            
            tokens = handle_token_exchange(
                auth_code=simulated_auth_code,
                client_id=temp_client_id,
                client_secret=temp_client_secret,
                redirect_uri="http://localhost:3000/auth/callback",
                code_verifier=None  # Simulate flow without PKCE
            )
            
            logger.info("✅ Tokens received:")
            logger.info(f"   Access Token: {tokens['access_token'][:20]}...")
            logger.info(f"   Token Type: {tokens['token_type']}")
            logger.info(f"   Expires In: {tokens['expires_in']} seconds")
            
            # Verify Google was called with real credentials
            call_data = mock_post.call_args[1]["data"]
            self.assertEqual(call_data["client_id"], MOCK_GOOGLE_CLIENT_ID)
            logger.info("✅ Google OAuth called with real credentials (not temporary)")
        
        # Step 5: Authenticated Requests
        logger.info("\n5️⃣ AUTHENTICATED REQUESTS PHASE")
        logger.info("   MCP client can now make authenticated requests")
        logger.info(f"   Authorization: Bearer {tokens['access_token'][:20]}...")
        
        logger.info("\n🎉 COMPLETE OAUTH FLOW SUCCESSFUL!")
        logger.info("   ✅ Discovery completed")
        logger.info("   ✅ Client registered with temporary credentials")
        logger.info("   ✅ Real credentials never exposed to client")
        logger.info("   ✅ Token exchange successful")
        logger.info("   ✅ Ready for authenticated MCP operations")


class TestOAuthProxyStats(unittest.TestCase):
    """Test OAuth Proxy statistics and management."""
    
    def test_proxy_stats(self):
        """Test OAuth Proxy statistics."""
        from auth.oauth_proxy import oauth_proxy
        
        # Get initial stats
        stats = oauth_proxy.get_stats()
        initial_count = stats["active_proxy_clients"]
        
        logger.info(f"Initial proxy clients: {initial_count}")
        
        # Add test clients
        from datetime import datetime, timezone
        from auth.oauth_proxy import ProxyClient
        
        for i in range(3):
            client = ProxyClient(
                temp_client_id=f"mcp_test_{i}",
                temp_client_secret=f"secret_{i}",
                real_client_id="real_id",
                real_client_secret="real_secret",
                client_metadata={},
                created_at=datetime.now(timezone.utc)
            )
            oauth_proxy._proxy_clients[f"mcp_test_{i}"] = client
        
        # Get updated stats
        stats = oauth_proxy.get_stats()
        self.assertEqual(stats["active_proxy_clients"], initial_count + 3)
        
        logger.info(f"✅ Stats show {stats['active_proxy_clients']} active clients")
        
        # Clean up
        for i in range(3):
            del oauth_proxy._proxy_clients[f"mcp_test_{i}"]


def run_tests():
    """Run all tests with detailed output."""
    # Create test suite
    suite = unittest.TestSuite()
    
    # Add tests in order
    suite.addTest(TestOAuthFlowEndToEnd('test_01_oauth_discovery_endpoints'))
    suite.addTest(TestOAuthFlowEndToEnd('test_02_dynamic_client_registration'))
    suite.addTest(TestOAuthFlowEndToEnd('test_03_token_exchange_with_proxy'))
    suite.addTest(TestOAuthFlowEndToEnd('test_04_client_deletion'))
    suite.addTest(TestOAuthFlowEndToEnd('test_05_credential_storage'))
    suite.addTest(TestOAuthFlowEndToEnd('test_06_security_validation'))
    suite.addTest(TestOAuthFlowEndToEnd('test_07_complete_flow_simulation'))
    suite.addTest(TestOAuthProxyStats('test_proxy_stats'))
    
    # Run tests with detailed output
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Print summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    print(f"Tests Run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print(f"Success Rate: {((result.testsRun - len(result.failures) - len(result.errors)) / result.testsRun * 100):.1f}%")
    
    if result.failures:
        print("\nFAILURES:")
        for test, traceback in result.failures:
            print(f"  - {test}: {traceback.split(chr(10))[0]}")
    
    if result.errors:
        print("\nERRORS:")
        for test, traceback in result.errors:
            print(f"  - {test}: {traceback.split(chr(10))[0]}")
    
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    exit(0 if success else 1)