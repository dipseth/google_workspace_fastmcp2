"""CredentialBridge for managing dual-mode credential storage.

This module provides an abstraction layer for credential storage that supports
both new FastMCP 2.12.0 format and legacy credential formats during migration.
"""

import logging

from config.enhanced_logging import setup_logger
logger = setup_logger()
import json
import os
from pathlib import Path
from typing import Optional, Dict, Any, Union, List
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class CredentialFormat(Enum):
    """Credential storage formats."""
    LEGACY = "legacy"  # Original format with token, refresh_token, etc.
    FASTMCP = "fastmcp"  # FastMCP 2.12.0 format
    UNIFIED = "unified"  # New unified format for migration


class CredentialMetadata(BaseModel):
    """Metadata for stored credentials."""
    
    format: CredentialFormat = Field(..., description="Credential format")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Creation time")
    last_modified: datetime = Field(default_factory=datetime.utcnow, description="Last modification time")
    migrated: bool = Field(False, description="Whether credentials have been migrated")
    migration_date: Optional[datetime] = Field(None, description="Migration date if migrated")
    source_format: Optional[str] = Field(None, description="Original format before migration")
    version: str = Field("1.0.0", description="Credential format version")


class StoredCredential(BaseModel):
    """Model for stored credentials."""
    
    user_email: str = Field(..., description="User's email address")
    credentials: Dict[str, Any] = Field(..., description="Credential data")
    metadata: CredentialMetadata = Field(default_factory=CredentialMetadata, description="Credential metadata")


class CredentialBridge:
    """Bridge for managing credentials across different storage formats.
    
    This class provides a unified interface for reading, writing, and migrating
    credentials between legacy and FastMCP 2.12.0 formats.
    """
    
    def __init__(self, credentials_dir: Optional[str] = None):
        """Initialize CredentialBridge.
        
        Args:
            credentials_dir: Directory for credential storage
        """
        self.credentials_dir = Path(credentials_dir or os.getenv("CREDENTIALS_DIR", "./credentials"))
        self.credentials_dir.mkdir(parents=True, exist_ok=True)
        
        self._enhanced_logging = os.getenv("ENHANCED_LOGGING", "false").lower() == "true"
        self._credential_migration = os.getenv("CREDENTIAL_MIGRATION", "false").lower() == "true"
        
        # Migration tracking
        self._migration_log_file = self.credentials_dir / "migration_log.json"
        self._migration_log: List[Dict[str, Any]] = []
        self._load_migration_log()
        
        if self._enhanced_logging:
            logger.info("🌉 CredentialBridge initialized")
            logger.info(f"  Credentials directory: {self.credentials_dir}")
            logger.info(f"  Migration enabled: {self._credential_migration}")
    
    def _load_migration_log(self):
        """Load migration log from file."""
        if self._migration_log_file.exists():
            try:
                with open(self._migration_log_file, 'r') as f:
                    self._migration_log = json.load(f)
            except Exception as e:
                logger.warning(f"Could not load migration log: {e}")
                self._migration_log = []
    
    def _save_migration_log(self):
        """Save migration log to file."""
        try:
            with open(self._migration_log_file, 'w') as f:
                json.dump(self._migration_log, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Failed to save migration log: {e}")
    
    def _log_migration(self, user_email: str, source_format: str, target_format: str, 
                      success: bool, details: Optional[str] = None):
        """Log a migration attempt."""
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "user_email": user_email,
            "source_format": source_format,
            "target_format": target_format,
            "success": success,
            "details": details
        }
        self._migration_log.append(entry)
        self._save_migration_log()
        
        if self._enhanced_logging:
            status = "✅" if success else "❌"
            logger.info(f"{status} Migration: {user_email} ({source_format} → {target_format})")
    
    def read_credentials(self, user_email: str, format_hint: Optional[CredentialFormat] = None) -> Optional[StoredCredential]:
        """Read credentials for a user.
        
        Args:
            user_email: User's email address
            format_hint: Hint about expected format (optional)
            
        Returns:
            StoredCredential if found, None otherwise
        """
        try:
            # Try different file patterns
            patterns = [
                f"token_{user_email}.json",  # Legacy format
                f"creds_{user_email}.json",  # Alternative legacy
                f"fastmcp_{user_email}.json",  # FastMCP format
                f"unified_{user_email}.json"  # Unified format
            ]
            
            for pattern in patterns:
                cred_file = self.credentials_dir / pattern
                if cred_file.exists():
                    with open(cred_file, 'r') as f:
                        data = json.load(f)
                    
                    # Determine format
                    format_type = self._detect_format(data)
                    
                    # Create StoredCredential
                    if "metadata" in data:
                        # Already has metadata
                        return StoredCredential(**data)
                    else:
                        # Add metadata
                        metadata = CredentialMetadata(
                            format=format_type,
                            created_at=datetime.fromtimestamp(cred_file.stat().st_ctime),
                            last_modified=datetime.fromtimestamp(cred_file.stat().st_mtime)
                        )
                        return StoredCredential(
                            user_email=user_email,
                            credentials=data,
                            metadata=metadata
                        )
            
            if self._enhanced_logging:
                logger.info(f"❌ No credentials found for {user_email}")
            return None
            
        except Exception as e:
            logger.error(f"Failed to read credentials for {user_email}: {e}")
            return None
    
    def write_credentials(self, stored_credential: StoredCredential, format_type: Optional[CredentialFormat] = None):
        """Write credentials to storage.
        
        Args:
            stored_credential: Credential to store
            format_type: Format to use (defaults to credential's format)
        """
        try:
            format_type = format_type or stored_credential.metadata.format
            
            # Determine filename based on format
            if format_type == CredentialFormat.LEGACY:
                filename = f"token_{stored_credential.user_email}.json"
            elif format_type == CredentialFormat.FASTMCP:
                filename = f"fastmcp_{stored_credential.user_email}.json"
            else:
                filename = f"unified_{stored_credential.user_email}.json"
            
            cred_file = self.credentials_dir / filename
            
            # Update metadata
            stored_credential.metadata.last_modified = datetime.utcnow()
            stored_credential.metadata.format = format_type
            
            # Write to file
            with open(cred_file, 'w') as f:
                json.dump(stored_credential.model_dump(mode='json'), f, indent=2, default=str)
            
            if self._enhanced_logging:
                logger.info(f"✅ Wrote {format_type.value} credentials for {stored_credential.user_email}")
            
        except Exception as e:
            logger.error(f"Failed to write credentials: {e}")
            raise
    
    def migrate_credentials(self, user_email: str, target_format: CredentialFormat) -> bool:
        """Migrate credentials to a different format.
        
        Args:
            user_email: User's email address
            target_format: Target credential format
            
        Returns:
            True if migration successful, False otherwise
        """
        if not self._credential_migration:
            logger.warning("Credential migration is disabled")
            return False
        
        try:
            # Read existing credentials
            stored_cred = self.read_credentials(user_email)
            if not stored_cred:
                logger.error(f"No credentials found for {user_email}")
                return False
            
            source_format = stored_cred.metadata.format
            
            if source_format == target_format:
                logger.info(f"Credentials already in {target_format.value} format")
                return True
            
            # Convert credentials
            converted_creds = self._convert_format(
                stored_cred.credentials,
                source_format,
                target_format
            )
            
            # Update metadata
            stored_cred.credentials = converted_creds
            stored_cred.metadata.migrated = True
            stored_cred.metadata.migration_date = datetime.utcnow()
            stored_cred.metadata.source_format = source_format.value
            stored_cred.metadata.format = target_format
            
            # Write in new format
            self.write_credentials(stored_cred, target_format)
            
            # Log migration
            self._log_migration(
                user_email,
                source_format.value,
                target_format.value,
                success=True
            )
            
            if self._enhanced_logging:
                logger.info(f"✅ Migrated {user_email} from {source_format.value} to {target_format.value}")
            
            return True
            
        except Exception as e:
            logger.error(f"Migration failed for {user_email}: {e}")
            self._log_migration(
                user_email,
                source_format.value if 'source_format' in locals() else "unknown",
                target_format.value,
                success=False,
                details=str(e)
            )
            return False
    
    def _detect_format(self, credentials: Dict[str, Any]) -> CredentialFormat:
        """Detect credential format from structure.
        
        Args:
            credentials: Credential dictionary
            
        Returns:
            Detected CredentialFormat
        """
        # Check for FastMCP 2.12.0 specific fields
        if "provider" in credentials and credentials.get("provider") == "google":
            return CredentialFormat.FASTMCP
        
        # Check for unified format markers
        if "format_version" in credentials and credentials.get("format_version") == "unified":
            return CredentialFormat.UNIFIED
        
        # Default to legacy for traditional format
        if "token" in credentials or "access_token" in credentials:
            return CredentialFormat.LEGACY
        
        # Unknown format, treat as legacy
        return CredentialFormat.LEGACY
    
    def _convert_format(self, credentials: Dict[str, Any], 
                       source: CredentialFormat, 
                       target: CredentialFormat) -> Dict[str, Any]:
        """Convert credentials between formats.
        
        Args:
            credentials: Source credentials
            source: Source format
            target: Target format
            
        Returns:
            Converted credentials
        """
        if source == CredentialFormat.LEGACY and target == CredentialFormat.FASTMCP:
            # Legacy to FastMCP
            return {
                "provider": "google",
                "access_token": credentials.get("token") or credentials.get("access_token"),
                "refresh_token": credentials.get("refresh_token"),
                "token_expiry": credentials.get("expiry") or credentials.get("token_expiry"),
                "scopes": credentials.get("scopes", []),
                "client_id": credentials.get("client_id") or os.getenv("FASTMCP_SERVER_AUTH_GOOGLE_CLIENT_ID"),
                "client_secret": credentials.get("client_secret") or os.getenv("FASTMCP_SERVER_AUTH_GOOGLE_CLIENT_SECRET")
            }
        
        elif source == CredentialFormat.FASTMCP and target == CredentialFormat.LEGACY:
            # FastMCP to Legacy
            return {
                "token": credentials.get("access_token"),
                "refresh_token": credentials.get("refresh_token"),
                "expiry": credentials.get("token_expiry"),
                "scopes": credentials.get("scopes", []),
                "client_id": credentials.get("client_id"),
                "client_secret": credentials.get("client_secret"),
                "token_uri": "https://oauth2.googleapis.com/token"
            }
        
        elif target == CredentialFormat.UNIFIED:
            # Any format to Unified
            return {
                "format_version": "unified",
                "provider": "google",
                "tokens": {
                    "access": credentials.get("access_token") or credentials.get("token"),
                    "refresh": credentials.get("refresh_token"),
                    "expiry": credentials.get("token_expiry") or credentials.get("expiry")
                },
                "oauth_config": {
                    "client_id": credentials.get("client_id") or os.getenv("FASTMCP_SERVER_AUTH_GOOGLE_CLIENT_ID"),
                    "client_secret": credentials.get("client_secret") or os.getenv("FASTMCP_SERVER_AUTH_GOOGLE_CLIENT_SECRET"),
                    "scopes": credentials.get("scopes", [])
                },
                "metadata": {
                    "created": datetime.utcnow().isoformat(),
                    "source_format": source.value
                }
            }
        
        else:
            # No conversion needed or unsupported
            return credentials
    
    def list_credentials(self) -> List[Dict[str, Any]]:
        """List all stored credentials.
        
        Returns:
            List of credential summaries
        """
        credentials = []
        
        for cred_file in self.credentials_dir.glob("*.json"):
            if cred_file.name == "migration_log.json":
                continue
            
            try:
                with open(cred_file, 'r') as f:
                    data = json.load(f)
                
                # Extract user email from filename or data
                if "user_email" in data:
                    user_email = data["user_email"]
                else:
                    # Try to extract from filename
                    parts = cred_file.stem.split("_", 1)
                    user_email = parts[1] if len(parts) > 1 else "unknown"
                
                format_type = self._detect_format(data.get("credentials", data))
                
                credentials.append({
                    "user_email": user_email,
                    "file": cred_file.name,
                    "format": format_type.value,
                    "size": cred_file.stat().st_size,
                    "modified": datetime.fromtimestamp(cred_file.stat().st_mtime).isoformat()
                })
                
            except Exception as e:
                logger.warning(f"Could not read {cred_file.name}: {e}")
        
        return credentials
    
    def get_migration_status(self) -> Dict[str, Any]:
        """Get migration status summary.
        
        Returns:
            Dictionary with migration statistics
        """
        credentials = self.list_credentials()
        
        format_counts = {}
        for cred in credentials:
            format_type = cred["format"]
            format_counts[format_type] = format_counts.get(format_type, 0) + 1
        
        successful_migrations = sum(1 for entry in self._migration_log if entry["success"])
        failed_migrations = sum(1 for entry in self._migration_log if not entry["success"])
        
        return {
            "total_credentials": len(credentials),
            "format_distribution": format_counts,
            "migration_log_entries": len(self._migration_log),
            "successful_migrations": successful_migrations,
            "failed_migrations": failed_migrations,
            "last_migration": self._migration_log[-1] if self._migration_log else None
        }