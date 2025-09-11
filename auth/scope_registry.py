"""
OAuth Scope Registry - Single Source of Truth for Google API Scopes

This module provides a centralized registry for all Google API scopes used across
the FastMCP2 system, eliminating the previous fragmentation across 7+ files.
"""

import logging

from config.enhanced_logging import setup_logger
logger = setup_logger()
from typing_extensions import Dict, List, Optional, Set, Union
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class ValidationResult:
    """Result of scope validation"""
    is_valid: bool
    missing_scopes: List[str] = None
    invalid_scopes: List[str] = None
    warnings: List[str] = None
    
    def __post_init__(self):
        if self.missing_scopes is None:
            self.missing_scopes = []
        if self.invalid_scopes is None:
            self.invalid_scopes = []
        if self.warnings is None:
            self.warnings = []


@dataclass
class ServiceMetadata:
    """Comprehensive service metadata"""
    name: str
    description: str
    icon: str
    version: str
    scopes: Dict[str, str]
    default_scope_group: str
    features: List[str]
    api_endpoint: str
    documentation_url: str
    service_config: Dict[str, str]


class ScopeRegistry:
    """Central registry for all Google API scopes and service metadata"""
    
    # Core scope registry - Single Source of Truth
    GOOGLE_API_SCOPES = {
        # Base OAuth scopes
        "base": {
            "userinfo_email": "https://www.googleapis.com/auth/userinfo.email",
            "userinfo_profile": "https://www.googleapis.com/auth/userinfo.profile",
            "openid": "openid"
        },
        
        # Google Drive scopes
        "drive": {
            "readonly": "https://www.googleapis.com/auth/drive.readonly",
            "file": "https://www.googleapis.com/auth/drive.file",
            "full": "https://www.googleapis.com/auth/drive",
            "appdata": "https://www.googleapis.com/auth/drive.appdata",
            "metadata": "https://www.googleapis.com/auth/drive.metadata",
            "metadata_readonly": "https://www.googleapis.com/auth/drive.metadata.readonly",
            "photos_readonly": "https://www.googleapis.com/auth/drive.photos.readonly",
            "scripts": "https://www.googleapis.com/auth/drive.scripts"
        },
        
        # Gmail scopes
        "gmail": {
            "readonly": "https://www.googleapis.com/auth/gmail.readonly",
            "send": "https://www.googleapis.com/auth/gmail.send",
            "compose": "https://www.googleapis.com/auth/gmail.compose",
            "modify": "https://www.googleapis.com/auth/gmail.modify",
            "labels": "https://www.googleapis.com/auth/gmail.labels",
            "full": "https://mail.google.com/",
            "insert": "https://www.googleapis.com/auth/gmail.insert",
            "metadata": "https://www.googleapis.com/auth/gmail.metadata",
            "settings_basic": "https://www.googleapis.com/auth/gmail.settings.basic",
            "settings_sharing": "https://www.googleapis.com/auth/gmail.settings.sharing"
        },
        
        # Google Calendar scopes
        "calendar": {
            "readonly": "https://www.googleapis.com/auth/calendar.readonly",
            "events": "https://www.googleapis.com/auth/calendar.events",
            "full": "https://www.googleapis.com/auth/calendar",
            "settings_readonly": "https://www.googleapis.com/auth/calendar.settings.readonly"
        },
        
        # Google Docs scopes
        "docs": {
            "readonly": "https://www.googleapis.com/auth/documents.readonly",
            "full": "https://www.googleapis.com/auth/documents"
        },
        
        # Google Sheets scopes
        "sheets": {
            "readonly": "https://www.googleapis.com/auth/spreadsheets.readonly",
            "full": "https://www.googleapis.com/auth/spreadsheets"
        },
        
        # Google Chat scopes
        "chat": {
            "messages_readonly": "https://www.googleapis.com/auth/chat.messages.readonly",
            "messages": "https://www.googleapis.com/auth/chat.messages",
            "spaces": "https://www.googleapis.com/auth/chat.spaces",
            "memberships_readonly": "https://www.googleapis.com/auth/chat.memberships.readonly",
            "memberships": "https://www.googleapis.com/auth/chat.memberships"
        },
        
        # Google Forms scopes
        "forms": {
            "body": "https://www.googleapis.com/auth/forms.body",
            "body_readonly": "https://www.googleapis.com/auth/forms.body.readonly",
            "responses_readonly": "https://www.googleapis.com/auth/forms.responses.readonly"
        },
        
        # Google Slides scopes
        "slides": {
            "full": "https://www.googleapis.com/auth/presentations",
            "readonly": "https://www.googleapis.com/auth/presentations.readonly"
        },
        
        # Google Photos scopes
        "photos": {
            "readonly": "https://www.googleapis.com/auth/photoslibrary.readonly",
            "appendonly": "https://www.googleapis.com/auth/photoslibrary.appendonly", 
            "full": "https://www.googleapis.com/auth/photoslibrary",
            "readonly_appcreated": "https://www.googleapis.com/auth/photoslibrary.readonly.appcreateddata",
            "edit_appcreated": "https://www.googleapis.com/auth/photoslibrary.edit.appcreateddata"
            # Note: Added back 'full' scope - needed for album listing and search operations
        },
        
        # Admin scopes
        "admin": {
            "users": "https://www.googleapis.com/auth/admin.directory.user",
            "groups": "https://www.googleapis.com/auth/admin.directory.group",
            "roles": "https://www.googleapis.com/auth/admin.directory.rolemanagement",
            "orgunit": "https://www.googleapis.com/auth/admin.directory.orgunit"
        },
        
        # Cloud Platform scopes (Note: Require special project setup and approval)
        "cloud": {
            "platform": "https://www.googleapis.com/auth/cloud-platform",
            "platform_readonly": "https://www.googleapis.com/auth/cloud-platform.read-only",
            "functions": "https://www.googleapis.com/auth/cloudfunctions",
            "pubsub": "https://www.googleapis.com/auth/pubsub",
            "iam": "https://www.googleapis.com/auth/iam"
        },
        
        # Other Google services
        "tasks": {
            "readonly": "https://www.googleapis.com/auth/tasks.readonly",
            "full": "https://www.googleapis.com/auth/tasks"
        },
        
        "youtube": {
            "readonly": "https://www.googleapis.com/auth/youtube.readonly",
            "upload": "https://www.googleapis.com/auth/youtube.upload",
            "full": "https://www.googleapis.com/auth/youtube"
        },
        
        "script": {
            "projects": "https://www.googleapis.com/auth/script.projects",
            "deployments": "https://www.googleapis.com/auth/script.deployments"
            # Removed external_request - deprecated/invalid scope
        }
    }
    
    # Comprehensive service metadata registry
    SERVICE_METADATA = {
        "drive": ServiceMetadata(
            name="Google Drive",
            description="Cloud storage and file synchronization service",
            icon="📁",
            version="v3",
            scopes=GOOGLE_API_SCOPES["drive"],
            default_scope_group="drive_basic",
            features=["file_storage", "sharing", "collaboration", "version_control"],
            api_endpoint="https://www.googleapis.com/drive/v3",
            documentation_url="https://developers.google.com/drive/api/v3/reference",
            service_config={"service": "drive", "version": "v3"}
        ),
        
        "gmail": ServiceMetadata(
            name="Gmail",
            description="Email service with powerful search, filtering, and organization features",
            icon="📧",
            version="v1",
            scopes=GOOGLE_API_SCOPES["gmail"],
            default_scope_group="gmail_basic",
            features=["email", "search", "labels", "filters", "templates", "batch_operations"],
            api_endpoint="https://www.googleapis.com/gmail/v1",
            documentation_url="https://developers.google.com/gmail/api/reference",
            service_config={"service": "gmail", "version": "v1"}
        ),
        
        "calendar": ServiceMetadata(
            name="Google Calendar",
            description="Time management and scheduling service",
            icon="📅",
            version="v3",
            scopes=GOOGLE_API_SCOPES["calendar"],
            default_scope_group="calendar_basic",
            features=["events", "scheduling", "reminders", "sharing", "bulk_operations"],
            api_endpoint="https://www.googleapis.com/calendar/v3",
            documentation_url="https://developers.google.com/calendar/api/v3/reference",
            service_config={"service": "calendar", "version": "v3"}
        ),
        
        "docs": ServiceMetadata(
            name="Google Docs",
            description="Document creation and collaboration service",
            icon="📄",
            version="v1",
            scopes=GOOGLE_API_SCOPES["docs"],
            default_scope_group="docs_basic",
            features=["document_creation", "rich_formatting", "collaboration", "templates"],
            api_endpoint="https://docs.googleapis.com/v1",
            documentation_url="https://developers.google.com/docs/api/reference",
            service_config={"service": "docs", "version": "v1"}
        ),
        
        "sheets": ServiceMetadata(
            name="Google Sheets",
            description="Spreadsheet and data analysis service",
            icon="📊",
            version="v4",
            scopes=GOOGLE_API_SCOPES["sheets"],
            default_scope_group="sheets_basic",
            features=["spreadsheets", "data_analysis", "formulas", "charts", "collaboration"],
            api_endpoint="https://sheets.googleapis.com/v4",
            documentation_url="https://developers.google.com/sheets/api/reference",
            service_config={"service": "sheets", "version": "v4"}
        ),
        
        "chat": ServiceMetadata(
            name="Google Chat",
            description="Team messaging and collaboration platform",
            icon="💬",
            version="v1",
            scopes=GOOGLE_API_SCOPES["chat"],
            default_scope_group="chat_basic",
            features=["messaging", "spaces", "cards", "bots", "webhooks"],
            api_endpoint="https://chat.googleapis.com/v1",
            documentation_url="https://developers.google.com/chat/api/reference",
            service_config={"service": "chat", "version": "v1"}
        ),
        
        "forms": ServiceMetadata(
            name="Google Forms",
            description="Survey and form creation service",
            icon="📝",
            version="v1",
            scopes=GOOGLE_API_SCOPES["forms"],
            default_scope_group="forms_basic",
            features=["form_creation", "responses", "validation", "analysis"],
            api_endpoint="https://forms.googleapis.com/v1",
            documentation_url="https://developers.google.com/forms/api/reference",
            service_config={"service": "forms", "version": "v1"}
        ),
        
        "slides": ServiceMetadata(
            name="Google Slides",
            description="Presentation creation and sharing service",
            icon="🎯",
            version="v1",
            scopes=GOOGLE_API_SCOPES["slides"],
            default_scope_group="slides_basic",
            features=["presentations", "templates", "animations", "collaboration"],
            api_endpoint="https://slides.googleapis.com/v1",
            documentation_url="https://developers.google.com/slides/api/reference",
            service_config={"service": "slides", "version": "v1"}
        ),
        
        "photos": ServiceMetadata(
            name="Google Photos",
            description="Photo and video storage service",
            icon="📷",
            version="v1",
            scopes=GOOGLE_API_SCOPES["photos"],
            default_scope_group="photos_basic",
            features=["photo_storage", "albums", "sharing", "search", "metadata"],
            api_endpoint="https://photoslibrary.googleapis.com/v1",
            documentation_url="https://developers.google.com/photos/library/reference",
            service_config={"service": "photoslibrary", "version": "v1"}
        ),
        
        "tasks": ServiceMetadata(
            name="Google Tasks",
            description="Task management service",
            icon="✅",
            version="v1",
            scopes=GOOGLE_API_SCOPES["tasks"],
            default_scope_group="tasks_basic",
            features=["task_lists", "due_dates", "notes", "completion_tracking"],
            api_endpoint="https://tasks.googleapis.com/tasks/v1",
            documentation_url="https://developers.google.com/tasks/reference",
            service_config={"service": "tasks", "version": "v1"}
        )
    }
    
    # Predefined service scope groups for common use cases
    SERVICE_SCOPE_GROUPS = {
        # Basic service combinations
        "drive_basic": ["base.userinfo_email", "base.openid", "drive.file", "drive.readonly"],
        "drive_full": ["base.userinfo_email", "base.openid", "drive.full"],
        "gmail_basic": ["base.userinfo_email", "base.openid", "gmail.readonly", "gmail.send", "gmail.settings_basic", "gmail.settings_sharing"],
        "gmail_full": ["base.userinfo_email", "base.openid", "gmail.full"],
        "calendar_basic": ["base.userinfo_email", "base.openid", "calendar.readonly", "calendar.events", "calendar.full"],
        "calendar_full": ["base.userinfo_email", "base.openid", "calendar.full"],
        "docs_basic": ["base.userinfo_email", "base.openid", "docs.readonly", "docs.full"],
        "sheets_basic": ["base.userinfo_email", "base.openid", "sheets.readonly", "sheets.full"],
        "chat_basic": ["base.userinfo_email", "base.openid", "chat.messages_readonly", "chat.messages"],
        "forms_basic": ["base.userinfo_email", "base.openid", "forms.body", "forms.responses_readonly"],
        "slides_basic": ["base.userinfo_email", "base.openid", "slides.full", "slides.readonly"],
        "photos_basic": ["base.userinfo_email", "base.openid", "photos.readonly", "photos.appendonly", "photos.readonly_appcreated"],
        "photos_full": ["base.userinfo_email", "base.openid", "photos.readonly", "photos.appendonly", "photos.full", "photos.readonly_appcreated", "photos.edit_appcreated"],
        "tasks_basic": ["base.userinfo_email", "base.openid", "tasks.readonly", "tasks.full"],
        "tasks_full": ["base.userinfo_email", "base.openid", "tasks.full"],
        
        # Multi-service combinations
        "office_suite": ["base.userinfo_email", "base.openid", "drive.file", "docs.full", "sheets.full", "slides.full"],
        "communication_suite": ["base.userinfo_email", "base.openid", "gmail.modify", "chat.messages", "calendar.events"],
        "admin_suite": ["base.userinfo_email", "base.openid", "admin.users", "admin.groups", "admin.roles"],
        
        # Comprehensive access for OAuth flows (validated scopes only)
        "oauth_comprehensive": [
            "base.userinfo_email", "base.userinfo_profile", "base.openid",
            "drive.full", "drive.readonly", "drive.file",
            "docs.readonly", "docs.full",
            "gmail.readonly", "gmail.send", "gmail.compose", "gmail.modify", "gmail.labels",
            "gmail.settings_basic", "gmail.settings_sharing",
            "chat.messages_readonly", "chat.messages", "chat.spaces",
            "sheets.readonly", "sheets.full",
            "forms.body", "forms.body_readonly", "forms.responses_readonly",
            "slides.full", "slides.readonly",
            "photos.readonly", "photos.appendonly", "photos.full", "photos.readonly_appcreated", "photos.edit_appcreated",
            "calendar.readonly", "calendar.events", "calendar.full",
            "tasks.readonly", "tasks.full"
        ]
    }
    
    # Convenient access to individual service scope groups
    DRIVE_SCOPES = GOOGLE_API_SCOPES["drive"]
    GMAIL_SCOPES = GOOGLE_API_SCOPES["gmail"]
    CALENDAR_SCOPES = GOOGLE_API_SCOPES["calendar"]
    DOCS_SCOPES = GOOGLE_API_SCOPES["docs"]
    SHEETS_SCOPES = GOOGLE_API_SCOPES["sheets"]
    CHAT_SCOPES = GOOGLE_API_SCOPES["chat"]
    FORMS_SCOPES = GOOGLE_API_SCOPES["forms"]
    SLIDES_SCOPES = GOOGLE_API_SCOPES["slides"]
    PHOTOS_SCOPES = GOOGLE_API_SCOPES["photos"]
    TASKS_SCOPES = GOOGLE_API_SCOPES["tasks"]
    BASE_SCOPES = GOOGLE_API_SCOPES["base"]
    
    @classmethod
    def get_service_metadata(cls, service: str) -> Optional[ServiceMetadata]:
        """
        Get comprehensive metadata for a service.
        
        Args:
            service: Service name
            
        Returns:
            ServiceMetadata object or None if service not found
        """
        return cls.SERVICE_METADATA.get(service)
    
    @classmethod
    def get_all_services(cls) -> List[str]:
        """Get list of all available services."""
        return list(cls.SERVICE_METADATA.keys())
    
    @classmethod
    def get_service_scopes(cls, service: str, access_level: str = "basic") -> List[str]:
        """
        Get scopes for a specific service with access level.
        
        Args:
            service: Service name (drive, gmail, calendar, etc.)
            access_level: Access level (basic, full, readonly, etc.)
            
        Returns:
            List of scope URLs for the service
        """
        logger.debug(f"SCOPE_REGISTRY: Getting {service} scopes with {access_level} access")
        
        if service not in cls.GOOGLE_API_SCOPES:
            available_services = list(cls.GOOGLE_API_SCOPES.keys())
            raise ValueError(f"Unknown service: {service}. Available: {available_services}")
        
        # Try predefined group first
        group_name = f"{service}_{access_level}"
        if group_name in cls.SERVICE_SCOPE_GROUPS:
            return cls.resolve_scope_group(group_name)
        
        # Fallback to service-specific logic
        service_scopes = cls.GOOGLE_API_SCOPES[service]
        base_scopes = cls.GOOGLE_API_SCOPES["base"]
        
        result_scopes = [
            base_scopes["userinfo_email"],
            base_scopes["openid"]
        ]
        
        if access_level == "readonly":
            # Add only readonly scopes
            if "readonly" in service_scopes:
                result_scopes.append(service_scopes["readonly"])
        elif access_level == "full":
            # Add full access scope
            if "full" in service_scopes:
                result_scopes.append(service_scopes["full"])
            else:
                # If no full scope, add all available scopes
                result_scopes.extend(service_scopes.values())
        else:
            # Basic access - add commonly needed scopes
            if service == "drive":
                result_scopes.extend([service_scopes["file"], service_scopes["readonly"]])
            elif service == "gmail":
                result_scopes.extend([service_scopes["readonly"], service_scopes["send"]])
            elif service == "calendar":
                result_scopes.extend([service_scopes["readonly"], service_scopes["events"]])
            elif service == "photos":
                result_scopes.extend([service_scopes["readonly"], service_scopes["appendonly"]])
            else:
                # Default to readonly and full if available
                if "readonly" in service_scopes:
                    result_scopes.append(service_scopes["readonly"])
                if "full" in service_scopes:
                    result_scopes.append(service_scopes["full"])
        
        return result_scopes
    
    @classmethod
    def resolve_scope_group(cls, group_name: str) -> List[str]:
        """
        Resolve a scope group name to actual scope URLs.
        
        Args:
            group_name: Name of the scope group
            
        Returns:
            List of resolved scope URLs
        """
        logger.debug(f"SCOPE_REGISTRY: Resolving scope group '{group_name}'")
        
        if group_name not in cls.SERVICE_SCOPE_GROUPS:
            available_groups = list(cls.SERVICE_SCOPE_GROUPS.keys())
            raise ValueError(f"Unknown scope group: {group_name}. Available: {available_groups}")
        
        scope_refs = cls.SERVICE_SCOPE_GROUPS[group_name]
        resolved_scopes = []
        
        for scope_ref in scope_refs:
            if "." in scope_ref:
                # Service.scope_name format
                try:
                    service, scope_name = scope_ref.split(".", 1)
                    if service in cls.GOOGLE_API_SCOPES and scope_name in cls.GOOGLE_API_SCOPES[service]:
                        scope_url = cls.GOOGLE_API_SCOPES[service][scope_name]
                        resolved_scopes.append(scope_url)
                        logger.debug(f"SCOPE_REGISTRY: Resolved {scope_ref} -> {scope_url}")
                    else:
                        logger.warning(f"SCOPE_REGISTRY: Invalid scope reference: {scope_ref}")
                except ValueError:
                    logger.warning(f"SCOPE_REGISTRY: Malformed scope reference: {scope_ref}")
            else:
                # Direct scope URL
                resolved_scopes.append(scope_ref)
                logger.debug(f"SCOPE_REGISTRY: Using direct scope: {scope_ref}")
        
        # Remove duplicates while preserving order
        unique_scopes = list(dict.fromkeys(resolved_scopes))
        logger.info(f"SCOPE_REGISTRY: Group '{group_name}' resolved to {len(unique_scopes)} scopes")
        
        return unique_scopes
    
    @classmethod
    def get_oauth_scopes(cls, services: List[str]) -> List[str]:
        """
        Get OAuth scopes for multiple services.
        
        Now uses the validated oauth_comprehensive scope group as the single source of truth
        instead of dynamically building scopes which could include problematic ones.
        
        Args:
            services: List of service names (ignored - uses comprehensive list)
            
        Returns:
            Combined list of scopes from oauth_comprehensive group
        """
        logger.info(f"SCOPE_REGISTRY: Getting OAuth scopes - using oauth_comprehensive as single source of truth")
        
        # Use our cleaned-up oauth_comprehensive group as the single source of truth
        return cls.resolve_scope_group("oauth_comprehensive")
    
    @classmethod
    def validate_scope_combination(cls, scopes: List[str]) -> ValidationResult:
        """
        Validate that scope combination is valid and consistent.
        
        Args:
            scopes: List of scope URLs to validate
            
        Returns:
            ValidationResult with validation details
        """
        logger.debug(f"SCOPE_REGISTRY: Validating {len(scopes)} scopes")
        
        result = ValidationResult(is_valid=True)
        all_known_scopes = set()
        
        # Collect all known scopes
        for service_scopes in cls.GOOGLE_API_SCOPES.values():
            all_known_scopes.update(service_scopes.values())
        
        # Check for invalid scopes
        for scope in scopes:
            if scope not in all_known_scopes:
                result.invalid_scopes.append(scope)
                logger.warning(f"SCOPE_REGISTRY: Unknown scope: {scope}")
        
        # Check for missing base scopes
        base_scopes = cls.GOOGLE_API_SCOPES["base"]
        has_userinfo = base_scopes["userinfo_email"] in scopes
        has_openid = base_scopes["openid"] in scopes
        
        if not has_userinfo:
            result.missing_scopes.append(base_scopes["userinfo_email"])
            result.warnings.append("Missing userinfo.email scope - user identification may fail")
        
        if not has_openid:
            result.missing_scopes.append(base_scopes["openid"])
            result.warnings.append("Missing openid scope - OAuth flow may fail")
        
        # Set overall validity
        result.is_valid = len(result.invalid_scopes) == 0
        
        if result.is_valid:
            logger.info(f"SCOPE_REGISTRY: Scope validation passed for {len(scopes)} scopes")
        else:
            logger.error(f"SCOPE_REGISTRY: Scope validation failed - {len(result.invalid_scopes)} invalid scopes")
        
        return result
    
    @classmethod
    def resolve_legacy_scope(cls, legacy_scope: str) -> str:
        """
        Resolve legacy scope names to current format.
        
        Args:
            legacy_scope: Legacy scope name or URL
            
        Returns:
            Current scope URL
        """
        logger.debug(f"SCOPE_REGISTRY: Resolving legacy scope '{legacy_scope}'")
        
        # If it's already a full URL, return as-is
        if legacy_scope.startswith("https://"):
            return legacy_scope
        
        # Handle common legacy formats
        legacy_mappings = {
            "userinfo": cls.GOOGLE_API_SCOPES["base"]["userinfo_email"],
            "openid": cls.GOOGLE_API_SCOPES["base"]["openid"],
            "drive_read": cls.GOOGLE_API_SCOPES["drive"]["readonly"],
            "drive_file": cls.GOOGLE_API_SCOPES["drive"]["file"],
            "drive_full": cls.GOOGLE_API_SCOPES["drive"]["full"],
            "gmail_read": cls.GOOGLE_API_SCOPES["gmail"]["readonly"],
            "gmail_send": cls.GOOGLE_API_SCOPES["gmail"]["send"],
            "gmail_modify": cls.GOOGLE_API_SCOPES["gmail"]["modify"],
            "gmail_settings_basic": cls.GOOGLE_API_SCOPES["gmail"]["settings_basic"],
            "gmail_settings_sharing": cls.GOOGLE_API_SCOPES["gmail"]["settings_sharing"],
            "calendar_read": cls.GOOGLE_API_SCOPES["calendar"]["readonly"],
            "calendar_events": cls.GOOGLE_API_SCOPES["calendar"]["events"],
            "docs_read": cls.GOOGLE_API_SCOPES["docs"]["readonly"],
            "docs_write": cls.GOOGLE_API_SCOPES["docs"]["full"],
            "sheets_read": cls.GOOGLE_API_SCOPES["sheets"]["readonly"],
            "sheets_write": cls.GOOGLE_API_SCOPES["sheets"]["full"],
            "photos_read": cls.GOOGLE_API_SCOPES["photos"]["readonly"],
            "photos_append": cls.GOOGLE_API_SCOPES["photos"]["appendonly"],
            "tasks_read": cls.GOOGLE_API_SCOPES["tasks"]["readonly"],
            "tasks_full": cls.GOOGLE_API_SCOPES["tasks"]["full"]
        }
        
        if legacy_scope in legacy_mappings:
            resolved = legacy_mappings[legacy_scope]
            logger.info(f"SCOPE_REGISTRY: Legacy scope '{legacy_scope}' -> '{resolved}'")
            return resolved
        
        # Try to find in current scopes by partial match
        for service_scopes in cls.GOOGLE_API_SCOPES.values():
            for scope_name, scope_url in service_scopes.items():
                if legacy_scope in scope_name or scope_name in legacy_scope:
                    logger.info(f"SCOPE_REGISTRY: Legacy scope '{legacy_scope}' matched '{scope_url}'")
                    return scope_url
        
        # If no match found, return as-is and log warning
        logger.warning(f"SCOPE_REGISTRY: Could not resolve legacy scope '{legacy_scope}'")
        return legacy_scope


class ServiceScopeManager:
    """Manage service-specific scope requirements"""
    
    def __init__(self, service_name: str):
        """
        Initialize service scope manager.
        
        Args:
            service_name: Name of the Google service
        """
        self.service_name = service_name
        self.logger = logging.getLogger(f"{__name__}.{service_name}")
        
        if service_name not in ScopeRegistry.GOOGLE_API_SCOPES:
            available_services = list(ScopeRegistry.GOOGLE_API_SCOPES.keys())
            raise ValueError(f"Unknown service: {service_name}. Available: {available_services}")
    
    def get_default_scopes(self) -> List[str]:
        """Get default scopes for this service"""
        return ScopeRegistry.get_service_scopes(self.service_name, "basic")
    
    def get_minimal_scopes(self) -> List[str]:
        """Get minimal scopes for basic functionality"""
        base_scopes = ScopeRegistry.GOOGLE_API_SCOPES["base"]
        service_scopes = ScopeRegistry.GOOGLE_API_SCOPES[self.service_name]
        
        minimal = [
            base_scopes["userinfo_email"],
            base_scopes["openid"]
        ]
        
        # Add the most basic scope for the service
        if "readonly" in service_scopes:
            minimal.append(service_scopes["readonly"])
        elif "file" in service_scopes:
            minimal.append(service_scopes["file"])
        elif service_scopes:
            # Add the first available scope
            minimal.append(list(service_scopes.values())[0])
        
        return minimal
    
    def get_full_scopes(self) -> List[str]:
        """Get all available scopes for this service"""
        return ScopeRegistry.get_service_scopes(self.service_name, "full")
    
    def validate_scopes(self, scopes: List[str]) -> ValidationResult:
        """Validate scopes are appropriate for this service"""
        return ScopeRegistry.validate_scope_combination(scopes)
    
    def get_scope_recommendations(self, requested_operations: List[str]) -> Dict[str, List[str]]:
        """
        Get scope recommendations based on requested operations.
        
        Args:
            requested_operations: List of operations (read, write, delete, etc.)
            
        Returns:
            Dictionary with recommended scopes for each operation level
        """
        recommendations = {
            "minimal": self.get_minimal_scopes(),
            "basic": self.get_default_scopes(),
            "full": self.get_full_scopes()
        }
        
        # Add operation-specific recommendations
        service_scopes = ScopeRegistry.GOOGLE_API_SCOPES[self.service_name]
        
        if "read" in requested_operations and "readonly" in service_scopes:
            recommendations["readonly"] = [
                ScopeRegistry.GOOGLE_API_SCOPES["base"]["userinfo_email"],
                ScopeRegistry.GOOGLE_API_SCOPES["base"]["openid"],
                service_scopes["readonly"]
            ]
        
        if any(op in requested_operations for op in ["write", "create", "update", "delete"]):
            if "full" in service_scopes:
                recommendations["write"] = [
                    ScopeRegistry.GOOGLE_API_SCOPES["base"]["userinfo_email"],
                    ScopeRegistry.GOOGLE_API_SCOPES["base"]["openid"],
                    service_scopes["full"]
                ]
        
        return recommendations