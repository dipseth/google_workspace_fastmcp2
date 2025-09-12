"""Tests for credential management flow."""

import pytest
import json
import tempfile
import shutil
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
import os
import stat

from google.oauth2.credentials import Credentials
from google.auth.exceptions import RefreshError

# Add parent directory to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from auth.google_auth import (
    _save_credentials,
    _load_credentials,
    _refresh_credentials,
    get_valid_credentials,
    GoogleAuthError
)
from auth.middleware import AuthMiddleware, CredentialStorageMode
from config.settings import settings


class TestCredentialManagement:
    """Test suite for credential management functionality."""
    
    @pytest.fixture
    def temp_credentials_dir(self):
        """Create a temporary directory for credentials."""
        temp_dir = tempfile.mkdtemp()
        original_dir = settings.credentials_dir
        settings.credentials_dir = temp_dir
        yield temp_dir
        settings.credentials_dir = original_dir
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    @pytest.fixture
    def mock_credentials(self):
        """Create mock Google OAuth2 credentials."""
        creds = Mock(spec=Credentials)
        creds.token = "test_access_token"
        creds.refresh_token = "test_refresh_token"
        creds.token_uri = "https://oauth2.googleapis.com/token"
        creds.client_id = "test_client_id"
        creds.client_secret = "test_client_secret"
        creds.scopes = ["https://www.googleapis.com/auth/drive.file"]
        creds.expiry = datetime.now() + timedelta(hours=1)
        creds.expired = False
        creds.valid = True
        return creds
    
    def test_save_credentials_success(self, temp_credentials_dir, mock_credentials):
        """Test successful credential saving with proper permissions."""
        user_email = "test@example.com"
        
        # Save credentials
        _save_credentials(user_email, mock_credentials)
        
        # Check file was created
        creds_path = Path(temp_credentials_dir) / "test_at_example_com_credentials.json"
        assert creds_path.exists()
        
        # Check file permissions (on Unix-like systems)
        if hasattr(os, 'chmod'):
            file_stat = creds_path.stat()
            file_mode = oct(file_stat.st_mode)[-3:]
            # File should have 600 permissions (owner read/write only)
            assert file_mode == '600'
        
        # Check file content
        with open(creds_path, 'r') as f:
            saved_data = json.load(f)
        
        assert saved_data["token"] == "test_access_token"
        assert saved_data["refresh_token"] == "test_refresh_token"
        assert saved_data["client_id"] == "test_client_id"
        assert saved_data["client_secret"] == "test_client_secret"
        assert saved_data["user_email"] == user_email
        assert "saved_at" in saved_data
    
    def test_save_credentials_without_refresh_token(self, temp_credentials_dir):
        """Test saving credentials without refresh token (should log warning)."""
        user_email = "test@example.com"
        
        # Create credentials without refresh token
        creds = Mock(spec=Credentials)
        creds.token = "test_access_token"
        creds.refresh_token = None  # No refresh token
        creds.token_uri = "https://oauth2.googleapis.com/token"
        creds.client_id = "test_client_id"
        creds.client_secret = "test_client_secret"
        creds.scopes = ["https://www.googleapis.com/auth/drive.file"]
        creds.expiry = datetime.now() + timedelta(hours=1)
        
        # Should save with warning
        _save_credentials(user_email, creds)
        
        creds_path = Path(temp_credentials_dir) / "test_at_example_com_credentials.json"
        assert creds_path.exists()
    
    def test_save_credentials_missing_access_token(self, temp_credentials_dir):
        """Test that saving fails without access token."""
        user_email = "test@example.com"
        
        # Create credentials without access token
        creds = Mock(spec=Credentials)
        creds.token = None  # No access token
        creds.refresh_token = "test_refresh_token"
        creds.token_uri = "https://oauth2.googleapis.com/token"
        creds.client_id = "test_client_id"
        creds.client_secret = "test_client_secret"
        creds.scopes = ["https://www.googleapis.com/auth/drive.file"]
        creds.expiry = None
        
        # Should raise error
        with pytest.raises(GoogleAuthError, match="Missing access token"):
            _save_credentials(user_email, creds)
    
    def test_load_credentials_success(self, temp_credentials_dir):
        """Test successful credential loading."""
        user_email = "test@example.com"
        
        # Create a credential file
        creds_data = {
            "token": "test_access_token",
            "refresh_token": "test_refresh_token",
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": "test_client_id",
            "client_secret": "test_client_secret",
            "scopes": ["https://www.googleapis.com/auth/drive.file"],
            "expiry": (datetime.now() + timedelta(hours=1)).isoformat(),
            "user_email": user_email,
            "saved_at": datetime.now().isoformat()
        }
        
        creds_path = Path(temp_credentials_dir) / "test_at_example_com_credentials.json"
        with open(creds_path, 'w') as f:
            json.dump(creds_data, f)
        
        # Load credentials
        loaded_creds = _load_credentials(user_email)
        
        assert loaded_creds is not None
        assert loaded_creds.token == "test_access_token"
        assert loaded_creds.refresh_token == "test_refresh_token"
        assert loaded_creds.client_id == "test_client_id"
        assert loaded_creds.client_secret == "test_client_secret"
    
    def test_load_credentials_file_not_found(self, temp_credentials_dir):
        """Test loading when credential file doesn't exist."""
        user_email = "nonexistent@example.com"
        
        loaded_creds = _load_credentials(user_email)
        assert loaded_creds is None
    
    def test_load_credentials_corrupt_json(self, temp_credentials_dir):
        """Test loading with corrupt JSON file."""
        user_email = "test@example.com"
        
        # Create a corrupt JSON file
        creds_path = Path(temp_credentials_dir) / "test_at_example_com_credentials.json"
        with open(creds_path, 'w') as f:
            f.write("{ invalid json content")
        
        # Should handle gracefully and return None
        loaded_creds = _load_credentials(user_email)
        assert loaded_creds is None
        
        # Check that corrupt file was backed up
        backup_path = creds_path.with_suffix('.json.corrupt')
        assert backup_path.exists()
    
    def test_load_credentials_email_mismatch(self, temp_credentials_dir):
        """Test loading when stored email doesn't match requested email."""
        user_email = "test@example.com"
        wrong_email = "wrong@example.com"
        
        # Create credential file with wrong email
        creds_data = {
            "token": "test_access_token",
            "refresh_token": "test_refresh_token",
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": "test_client_id",
            "client_secret": "test_client_secret",
            "scopes": ["https://www.googleapis.com/auth/drive.file"],
            "user_email": wrong_email
        }
        
        creds_path = Path(temp_credentials_dir) / "test_at_example_com_credentials.json"
        with open(creds_path, 'w') as f:
            json.dump(creds_data, f)
        
        # Should return None due to email mismatch
        loaded_creds = _load_credentials(user_email)
        assert loaded_creds is None
    
    def test_refresh_credentials_success(self, temp_credentials_dir, mock_credentials):
        """Test successful credential refresh."""
        user_email = "test@example.com"
        
        # Mock the refresh method
        mock_credentials.refresh = Mock()
        mock_credentials.token = "new_access_token"
        mock_credentials.expiry = datetime.now() + timedelta(hours=2)
        
        # Refresh credentials
        refreshed_creds = _refresh_credentials(mock_credentials, user_email)
        
        # Check refresh was called
        mock_credentials.refresh.assert_called_once()
        
        # Check credentials were saved
        creds_path = Path(temp_credentials_dir) / "test_at_example_com_credentials.json"
        assert creds_path.exists()
    
    def test_refresh_credentials_no_refresh_token(self, temp_credentials_dir):
        """Test refresh fails without refresh token."""
        user_email = "test@example.com"
        
        # Create credentials without refresh token
        creds = Mock(spec=Credentials)
        creds.refresh_token = None
        
        # Should raise error
        with pytest.raises(GoogleAuthError, match="No refresh token available"):
            _refresh_credentials(creds, user_email)
    
    def test_refresh_credentials_invalid_grant(self, temp_credentials_dir, mock_credentials):
        """Test refresh with invalid grant error."""
        user_email = "test@example.com"
        
        # Mock refresh to raise invalid_grant error
        mock_credentials.refresh = Mock(side_effect=RefreshError("invalid_grant: Token has been expired or revoked"))
        
        # Should raise GoogleAuthError with helpful message
        with pytest.raises(GoogleAuthError, match="Refresh token is invalid or expired"):
            _refresh_credentials(mock_credentials, user_email)
    
    def test_get_valid_credentials_with_refresh(self, temp_credentials_dir):
        """Test get_valid_credentials refreshes expired token."""
        user_email = "test@example.com"
        
        # Create expired credentials
        creds_data = {
            "token": "old_access_token",
            "refresh_token": "test_refresh_token",
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": "test_client_id",
            "client_secret": "test_client_secret",
            "scopes": ["https://www.googleapis.com/auth/drive.file"],
            "expiry": (datetime.now() - timedelta(hours=1)).isoformat(),  # Expired
            "user_email": user_email
        }
        
        creds_path = Path(temp_credentials_dir) / "test_at_example_com_credentials.json"
        with open(creds_path, 'w') as f:
            json.dump(creds_data, f)
        
        # Mock the refresh process
        with patch('auth.google_auth._refresh_credentials') as mock_refresh:
            mock_new_creds = Mock(spec=Credentials)
            mock_new_creds.expired = False
            mock_new_creds.refresh_token = "test_refresh_token"
            mock_refresh.return_value = mock_new_creds
            
            # Get valid credentials (should trigger refresh)
            valid_creds = get_valid_credentials(user_email)
            
            assert valid_creds is not None
            mock_refresh.assert_called_once()


class TestAuthMiddleware:
    """Test suite for AuthMiddleware credential storage modes."""
    
    @pytest.fixture
    def temp_credentials_dir(self):
        """Create a temporary directory for credentials."""
        temp_dir = tempfile.mkdtemp()
        original_dir = settings.credentials_dir
        settings.credentials_dir = temp_dir
        yield temp_dir
        settings.credentials_dir = original_dir
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    @pytest.fixture
    def mock_credentials(self):
        """Create mock Google OAuth2 credentials."""
        creds = Mock(spec=Credentials)
        creds.token = "test_access_token"
        creds.refresh_token = "test_refresh_token"
        creds.token_uri = "https://oauth2.googleapis.com/token"
        creds.client_id = "test_client_id"
        creds.client_secret = "test_client_secret"
        creds.scopes = ["https://www.googleapis.com/auth/drive.file"]
        creds.expiry = datetime.now() + timedelta(hours=1)
        return creds
    
    def test_plaintext_storage_mode(self, temp_credentials_dir, mock_credentials):
        """Test FILE_PLAINTEXT storage mode."""
        middleware = AuthMiddleware(storage_mode=CredentialStorageMode.FILE_PLAINTEXT)
        user_email = "test@example.com"
        
        # Save credentials
        middleware.save_credentials(user_email, mock_credentials)
        
        # Check file exists
        creds_path = Path(temp_credentials_dir) / "test_at_example_com_credentials.json"
        assert creds_path.exists()
        
        # Load credentials
        loaded_creds = middleware.load_credentials(user_email)
        assert loaded_creds is not None
        assert loaded_creds.token == "test_access_token"
    
    def test_memory_only_storage_mode(self, mock_credentials):
        """Test MEMORY_ONLY storage mode."""
        middleware = AuthMiddleware(storage_mode=CredentialStorageMode.MEMORY_ONLY)
        user_email = "test@example.com"
        
        # Save credentials (should only store in memory)
        middleware.save_credentials(user_email, mock_credentials)
        
        # Load credentials from memory
        loaded_creds = middleware.load_credentials(user_email)
        assert loaded_creds is not None
        assert loaded_creds.token == "test_access_token"
        
        # Create new middleware instance (simulating restart)
        new_middleware = AuthMiddleware(storage_mode=CredentialStorageMode.MEMORY_ONLY)
        
        # Credentials should not persist
        loaded_creds = new_middleware.load_credentials(user_email)
        assert loaded_creds is None
    
    def test_credential_summary(self, temp_credentials_dir, mock_credentials):
        """Test getting credential summary."""
        middleware = AuthMiddleware(storage_mode=CredentialStorageMode.FILE_PLAINTEXT)
        
        # Save credentials for multiple users
        middleware.save_credentials("user1@example.com", mock_credentials)
        middleware.save_credentials("user2@example.com", mock_credentials)
        
        # Get summary
        summary = middleware.get_credential_summary()
        
        assert summary["storage_mode"] == "file_plaintext"
        assert len(summary["file_credentials"]) == 2
        
        # Check users are in the summary
        emails = [cred["email"] for cred in summary["file_credentials"]]
        assert "user1@example.com" in emails
        assert "user2@example.com" in emails
    
    def test_migrate_credentials(self, temp_credentials_dir, mock_credentials):
        """Test migrating credentials between storage modes."""
        # Start with plaintext mode
        middleware = AuthMiddleware(storage_mode=CredentialStorageMode.FILE_PLAINTEXT)
        user_email = "test@example.com"
        
        # Save credentials in plaintext
        middleware.save_credentials(user_email, mock_credentials)
        
        # Migrate to memory only
        results = middleware.migrate_credentials(CredentialStorageMode.MEMORY_ONLY)
        
        assert user_email in results
        assert "Migrated" in results[user_email]
        
        # Check new mode is active
        assert middleware.get_storage_mode() == CredentialStorageMode.MEMORY_ONLY
        
        # Credentials should be in memory
        loaded_creds = middleware.load_credentials(user_email)
        assert loaded_creds is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])