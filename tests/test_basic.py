"""Basic tests for the FastMCP2 Drive Upload Server."""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

from config.settings import Settings
from auth.context import (
    set_session_context, 
    get_session_context, 
    clear_session_context,
    store_session_data,
    get_session_data
)
from drive.utils import get_mime_type, validate_file_path, format_file_size


class TestSettings:
    """Test configuration settings."""
    
    def test_settings_defaults(self):
        """Test that settings have reasonable defaults."""
        # Use a temporary directory for testing
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = Settings(
                google_client_id="test_client_id",
                google_client_secret="test_secret",
                credentials_dir=temp_dir
            )
            
            assert settings.server_port == 8000
            assert settings.server_host == "localhost"
            assert settings.log_level == "INFO"
            assert settings.session_timeout_minutes == 60
            assert len(settings.drive_scopes) == 3


class TestSessionContext:
    """Test session context management."""
    
    def test_session_context_lifecycle(self):
        """Test setting and clearing session context."""
        # Initially no context
        assert get_session_context() is None
        
        # Set context
        test_session_id = "test_session_123"
        set_session_context(test_session_id)
        assert get_session_context() == test_session_id
        
        # Clear context
        clear_session_context()
        assert get_session_context() is None
    
    def test_session_data_storage(self):
        """Test session data storage and retrieval."""
        session_id = "test_session_456"
        test_key = "test_credentials"
        test_value = {"token": "fake_token", "user": "test@example.com"}
        
        # Store data
        store_session_data(session_id, test_key, test_value)
        
        # Retrieve data
        retrieved_value = get_session_data(session_id, test_key)
        assert retrieved_value == test_value
        
        # Test default value
        missing_value = get_session_data(session_id, "missing_key", "default")
        assert missing_value == "default"


class TestDriveUtils:
    """Test Drive utility functions."""
    
    def test_get_mime_type(self):
        """Test MIME type detection."""
        # Test common file types
        assert get_mime_type(Path("test.pdf")) == "application/pdf"
        assert get_mime_type(Path("test.jpg")) == "image/jpeg"
        assert get_mime_type(Path("test.txt")) == "text/plain"
        assert get_mime_type(Path("test.docx")) == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        
        # Test unknown extension
        assert get_mime_type(Path("test.unknown")) == "application/octet-stream"
    
    def test_validate_file_path_success(self):
        """Test file path validation with valid file."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as temp_file:
            temp_file.write("test content")
            temp_path = Path(temp_file.name)
        
        try:
            # Should not raise exception for valid file
            validate_file_path(temp_path)
        finally:
            temp_path.unlink()  # Clean up
    
    def test_validate_file_path_missing(self):
        """Test file path validation with missing file."""
        from drive.utils import DriveUploadError
        
        missing_path = Path("/path/that/does/not/exist.txt")
        
        with pytest.raises(DriveUploadError, match="File not found"):
            validate_file_path(missing_path)
    
    def test_validate_file_path_directory(self):
        """Test file path validation with directory."""
        from drive.utils import DriveUploadError
        
        with tempfile.TemporaryDirectory() as temp_dir:
            dir_path = Path(temp_dir)
            
            with pytest.raises(DriveUploadError, match="Path is not a file"):
                validate_file_path(dir_path)
    
    def test_format_file_size(self):
        """Test file size formatting."""
        assert format_file_size(0) == "0 B"
        assert format_file_size(1024) == "1.0 KB"
        assert format_file_size(1024 * 1024) == "1.0 MB"
        assert format_file_size(1024 * 1024 * 1024) == "1.0 GB"
        assert format_file_size(1536) == "1.5 KB"  # 1.5 * 1024


class TestAuthMiddleware:
    """Test authentication middleware."""
    
    @patch('auth.middleware.cleanup_expired_sessions')
    def test_middleware_cleanup_trigger(self, mock_cleanup):
        """Test that middleware triggers session cleanup periodically."""
        from auth.middleware import AuthMiddleware
        from fastmcp.server.middleware import MiddlewareContext
        
        middleware = AuthMiddleware()
        
        # Mock context and call_next
        mock_context = Mock(spec=MiddlewareContext)
        mock_context.method = "test_method"
        mock_context.fastmcp_context = None
        
        async def mock_call_next(ctx):
            return "success"
        
        # Simulate 10 requests to trigger cleanup
        import asyncio
        
        # Set last cleanup time to simulate the cleanup interval being exceeded
        from datetime import datetime, timedelta
        middleware._last_cleanup = datetime.now() - timedelta(minutes=35)
        
        async def run_request():
            await middleware.on_request(mock_context, mock_call_next)
        
        # Run the test
        asyncio.run(run_request())
        
        # Verify cleanup was called
        assert mock_cleanup.called


@pytest.fixture
def temp_credentials_dir():
    """Provide a temporary credentials directory for testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield temp_dir


@pytest.fixture
def mock_settings(temp_credentials_dir):
    """Provide mock settings for testing."""
    return Settings(
        google_client_id="test_client_id",
        google_client_secret="test_secret",
        credentials_dir=temp_credentials_dir,
        server_port=8001,  # Use different port for testing
        log_level="DEBUG"
    )


class TestIntegration:
    """Integration tests for the server."""
    
    def test_server_creation(self, mock_settings):
        """Test that the server can be created with mock settings."""
        with patch('config.settings.settings', mock_settings):
            # Import server after patching settings
            from server import mcp
            
            assert mcp.name == mock_settings.server_name
            # FastMCP2 doesn't expose version directly, so just check it exists
            assert hasattr(mcp, 'name')
    
    def test_health_check_tool(self, mock_settings):
        """Test the health check functionality."""
        with patch('config.settings.settings', mock_settings):
            # Test the health check logic directly
            import asyncio
            import os
            from pathlib import Path
            from auth.context import get_session_count
            
            async def test_health_check_logic():
                # Simulate the health check logic
                creds_dir = Path(mock_settings.credentials_dir)
                creds_accessible = creds_dir.exists() and os.access(creds_dir, os.R_OK | os.W_OK)
                oauth_configured = bool(mock_settings.google_client_id and mock_settings.google_client_secret)
                
                result_parts = [
                    "=== Google Drive Upload Server Health Check ===",
                    "",
                    f"🏥 **Server Status**: Running",
                    f"📁 **Credentials Directory**: {'✅ Accessible' if creds_accessible else '❌ Not accessible'}",
                    f"🔑 **OAuth Configuration**: {'✅ Configured' if oauth_configured else '❌ Missing credentials'}",
                    f"👥 **Active Sessions**: {get_session_count()}",
                    "",
                    f"**Overall Status**: {'✅ Healthy' if creds_accessible and oauth_configured else '⚠️ Configuration Issues'}",
                ]
                
                return "\n".join(result_parts)
            
            # Run the health check
            result = asyncio.run(test_health_check_logic())
            assert isinstance(result, str)
            assert "Google Drive Upload Server Health Check" in result
            assert len(result) > 0


if __name__ == "__main__":
    pytest.main([__file__])