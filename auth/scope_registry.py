"""
OAuth Scope Registry - Single Source of Truth for Google API Scopes

This module provides a centralized registry for all Google API scopes used across
the FastMCP2 system, eliminating the previous fragmentation across 7+ files.
"""

from dataclasses import dataclass

from typing_extensions import Any, Dict, List, Optional

from config.enhanced_logging import setup_logger

logger = setup_logger()


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
            "openid": "openid",
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
            "scripts": "https://www.googleapis.com/auth/drive.scripts",
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
            "settings_sharing": "https://www.googleapis.com/auth/gmail.settings.sharing",
        },
        # Google Calendar scopes
        "calendar": {
            "readonly": "https://www.googleapis.com/auth/calendar.readonly",
            "events": "https://www.googleapis.com/auth/calendar.events",
            "full": "https://www.googleapis.com/auth/calendar",
            "settings_readonly": "https://www.googleapis.com/auth/calendar.settings.readonly",
        },
        # Google Docs scopes
        "docs": {
            "readonly": "https://www.googleapis.com/auth/documents.readonly",
            "full": "https://www.googleapis.com/auth/documents",
        },
        # Google Sheets scopes
        "sheets": {
            "readonly": "https://www.googleapis.com/auth/spreadsheets.readonly",
            "full": "https://www.googleapis.com/auth/spreadsheets",
        },
        # Google Chat scopes
        "chat": {
            "messages_readonly": "https://www.googleapis.com/auth/chat.messages.readonly",
            "messages": "https://www.googleapis.com/auth/chat.messages",
            "messages_create": "https://www.googleapis.com/auth/chat.messages.create",
            "spaces": "https://www.googleapis.com/auth/chat.spaces",
            "spaces_create": "https://www.googleapis.com/auth/chat.spaces.create",
            "memberships_readonly": "https://www.googleapis.com/auth/chat.memberships.readonly",
            "memberships": "https://www.googleapis.com/auth/chat.memberships",
            "memberships_app": "https://www.googleapis.com/auth/chat.memberships.app",
            "delete": "https://www.googleapis.com/auth/chat.delete",
            # Reaction scopes (require user-level / delegated auth)
            "reactions": "https://www.googleapis.com/auth/chat.messages.reactions",
            "reactions_create": "https://www.googleapis.com/auth/chat.messages.reactions.create",
            "reactions_readonly": "https://www.googleapis.com/auth/chat.messages.reactions.readonly",
            # App-level scopes (service account authentication)
            "app_memberships": "https://www.googleapis.com/auth/chat.app.memberships",
            "app_spaces": "https://www.googleapis.com/auth/chat.app.spaces",
            "app_spaces_create": "https://www.googleapis.com/auth/chat.app.spaces.create",
            "app_delete": "https://www.googleapis.com/auth/chat.app.delete",
            # Bot identity scope (SA acts as the Chat app itself — required for sending cards)
            "bot": "https://www.googleapis.com/auth/chat.bot",
        },
        # Google Forms scopes
        "forms": {
            "body": "https://www.googleapis.com/auth/forms.body",
            "body_readonly": "https://www.googleapis.com/auth/forms.body.readonly",
            "responses_readonly": "https://www.googleapis.com/auth/forms.responses.readonly",
        },
        # Google Slides scopes
        "slides": {
            "full": "https://www.googleapis.com/auth/presentations",
            "readonly": "https://www.googleapis.com/auth/presentations.readonly",
        },
        # Google Photos scopes
        # The photoslibrary, photoslibrary.readonly, and photoslibrary.sharing
        # scopes were retired by Google after March 31, 2025 and now return
        # 403 PERMISSION_DENIED. Only app-created-data scopes remain, and the
        # Library API only returns albums/media created by this app.
        "photos": {
            "appendonly": "https://www.googleapis.com/auth/photoslibrary.appendonly",
            "readonly_appcreated": "https://www.googleapis.com/auth/photoslibrary.readonly.appcreateddata",
            "edit_appcreated": "https://www.googleapis.com/auth/photoslibrary.edit.appcreateddata",
        },
        # Google People API scopes
        "people": {
            "readonly": "https://www.googleapis.com/auth/contacts.readonly",
            "contacts": "https://www.googleapis.com/auth/contacts",
            "directory_readonly": "https://www.googleapis.com/auth/directory.readonly",
        },
        # Admin scopes
        "admin": {
            "users": "https://www.googleapis.com/auth/admin.directory.user",
            "groups": "https://www.googleapis.com/auth/admin.directory.group",
            "roles": "https://www.googleapis.com/auth/admin.directory.rolemanagement",
            "orgunit": "https://www.googleapis.com/auth/admin.directory.orgunit",
        },
        # Cloud Platform scopes (Note: Require special project setup and approval)
        "cloud": {
            "platform": "https://www.googleapis.com/auth/cloud-platform",
            "platform_readonly": "https://www.googleapis.com/auth/cloud-platform.read-only",
            "functions": "https://www.googleapis.com/auth/cloudfunctions",
            "pubsub": "https://www.googleapis.com/auth/pubsub",
            "iam": "https://www.googleapis.com/auth/iam",
        },
        # Other Google services
        "tasks": {
            "readonly": "https://www.googleapis.com/auth/tasks.readonly",
            "full": "https://www.googleapis.com/auth/tasks",
        },
        "youtube": {
            "readonly": "https://www.googleapis.com/auth/youtube.readonly",
            "upload": "https://www.googleapis.com/auth/youtube.upload",
            "full": "https://www.googleapis.com/auth/youtube",
        },
        "script": {
            "projects": "https://www.googleapis.com/auth/script.projects",
            "deployments": "https://www.googleapis.com/auth/script.deployments",
            # Removed external_request - deprecated/invalid scope
        },
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
            service_config={"service": "drive", "version": "v3"},
        ),
        "gmail": ServiceMetadata(
            name="Gmail",
            description="Email service with powerful search, filtering, and organization features",
            icon="📧",
            version="v1",
            scopes=GOOGLE_API_SCOPES["gmail"],
            default_scope_group="gmail_basic",
            features=[
                "email",
                "search",
                "labels",
                "filters",
                "templates",
                "batch_operations",
            ],
            api_endpoint="https://www.googleapis.com/gmail/v1",
            documentation_url="https://developers.google.com/gmail/api/reference",
            service_config={"service": "gmail", "version": "v1"},
        ),
        "calendar": ServiceMetadata(
            name="Google Calendar",
            description="Time management and scheduling service",
            icon="📅",
            version="v3",
            scopes=GOOGLE_API_SCOPES["calendar"],
            default_scope_group="calendar_basic",
            features=[
                "events",
                "scheduling",
                "reminders",
                "sharing",
                "bulk_operations",
            ],
            api_endpoint="https://www.googleapis.com/calendar/v3",
            documentation_url="https://developers.google.com/calendar/api/v3/reference",
            service_config={"service": "calendar", "version": "v3"},
        ),
        "docs": ServiceMetadata(
            name="Google Docs",
            description="Document creation and collaboration service",
            icon="📄",
            version="v1",
            scopes=GOOGLE_API_SCOPES["docs"],
            default_scope_group="docs_basic",
            features=[
                "document_creation",
                "rich_formatting",
                "collaboration",
                "templates",
            ],
            api_endpoint="https://docs.googleapis.com/v1",
            documentation_url="https://developers.google.com/docs/api/reference",
            service_config={"service": "docs", "version": "v1"},
        ),
        "sheets": ServiceMetadata(
            name="Google Sheets",
            description="Spreadsheet and data analysis service",
            icon="📊",
            version="v4",
            scopes=GOOGLE_API_SCOPES["sheets"],
            default_scope_group="sheets_basic",
            features=[
                "spreadsheets",
                "data_analysis",
                "formulas",
                "charts",
                "collaboration",
            ],
            api_endpoint="https://sheets.googleapis.com/v4",
            documentation_url="https://developers.google.com/sheets/api/reference",
            service_config={"service": "sheets", "version": "v4"},
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
            service_config={"service": "chat", "version": "v1"},
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
            service_config={"service": "forms", "version": "v1"},
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
            service_config={"service": "slides", "version": "v1"},
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
            service_config={"service": "photoslibrary", "version": "v1"},
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
            service_config={"service": "tasks", "version": "v1"},
        ),
        "people": ServiceMetadata(
            name="Google People API",
            description="User profile and contact information service",
            icon="👤",
            version="v1",
            scopes=GOOGLE_API_SCOPES["people"],
            default_scope_group="people_basic",
            features=["user_profiles", "contacts", "directory", "profile_enrichment"],
            api_endpoint="https://people.googleapis.com/v1",
            documentation_url="https://developers.google.com/people/api/rest",
            service_config={"service": "people", "version": "v1"},
        ),
    }

    # Predefined service scope groups for common use cases
    SERVICE_SCOPE_GROUPS = {
        # Base OAuth scopes for user authentication
        "base": ["base.userinfo_email", "base.userinfo_profile", "base.openid"],
        # Basic service combinations.
        # These are what tools request by default, so each must stay a
        # subset of what the OAuth flows actually grant (oauth_comprehensive
        # for Workspace services, photos_basic for Photos) — full scopes
        # cover the readonly variants at the API level, and requesting
        # narrower strings the token doesn't carry just produces
        # "missing scopes" warnings.
        "drive_basic": [
            "base.userinfo_email",
            "base.openid",
            "drive.full",  # Full Drive access for MCP - required to access shared/organizational files
        ],
        "drive_full": ["base.userinfo_email", "base.openid", "drive.full"],
        "gmail_basic": [
            "base.userinfo_email",
            "base.openid",
            "gmail.modify",
            "gmail.settings_basic",
            "gmail.settings_sharing",
        ],
        "gmail_full": ["base.userinfo_email", "base.openid", "gmail.full"],
        "calendar_basic": [
            "base.userinfo_email",
            "base.openid",
            "calendar.full",
        ],
        "calendar_full": ["base.userinfo_email", "base.openid", "calendar.full"],
        "docs_basic": [
            "base.userinfo_email",
            "base.openid",
            "docs.full",
        ],
        "sheets_basic": [
            "base.userinfo_email",
            "base.openid",
            "sheets.full",
        ],
        "chat_basic": [
            "base.userinfo_email",
            "base.userinfo_profile",
            "base.openid",
            "chat.messages",
            "chat.spaces",
            "chat.memberships",
            "people.contacts",
        ],
        # Bot identity scope (SA acts as Chat app — can send cards)
        "chat_bot": [
            "chat.bot",
        ],
        # Service account (app-level) scopes for Chat API
        "chat_app": [
            "chat.spaces",
            "chat.spaces_create",
            "chat.delete",
            "chat.messages",
            "chat.messages_readonly",
            "chat.messages_create",
            "chat.memberships",
            "chat.memberships_readonly",
            "chat.memberships_app",
            "chat.app_memberships",
            "chat.app_spaces",
            "chat.app_spaces_create",
            "chat.app_delete",
            "chat.reactions",
            "chat.reactions_create",
            "chat.reactions_readonly",
        ],
        "forms_basic": [
            "base.userinfo_email",
            "base.openid",
            "forms.body",
            # No full scope covers form responses — this must stay.
            "forms.responses_readonly",
        ],
        "slides_basic": [
            "base.userinfo_email",
            "base.openid",
            "slides.full",
        ],
        # Photos scopes CANNOT be combined with Drive (or other Workspace)
        # scopes in a single authorization request — Google's auth server
        # rejects the mix with "Error 400: invalid_request — This request
        # contains scopes that cannot be requested together". Photos must be
        # authorized in its own OAuth flow (selected_services=["photos"]).
        "photos_basic": [
            "base.userinfo_email",
            "base.openid",
            "photos.appendonly",
            "photos.readonly_appcreated",
            "photos.edit_appcreated",
        ],
        "photos_full": [
            "base.userinfo_email",
            "base.openid",
            "photos.appendonly",
            "photos.readonly_appcreated",
            "photos.edit_appcreated",
        ],
        "tasks_basic": [
            "base.userinfo_email",
            "base.openid",
            "tasks.full",
        ],
        "tasks_full": ["base.userinfo_email", "base.openid", "tasks.full"],
        "people_basic": [
            "base.userinfo_email",
            "base.userinfo_profile",
            "base.openid",
            "people.contacts",  # Full contacts covers readonly; write needed for contact groups
            # No full scope covers directory data — this must stay.
            "people.directory_readonly",
        ],
        "people_full": [
            "base.userinfo_email",
            "base.userinfo_profile",
            "base.openid",
            "people.contacts",
            "people.directory_readonly",
        ],
        # Multi-service combinations
        "office_suite": [
            "base.userinfo_email",
            "base.openid",
            "drive.full",
            "docs.full",
            "sheets.full",
            "slides.full",
        ],
        "communication_suite": [
            "base.userinfo_email",
            "base.openid",
            "gmail.modify",
            "chat.messages",
            "calendar.full",
        ],
        "admin_suite": [
            "base.userinfo_email",
            "base.openid",
            "admin.users",
            "admin.groups",
            "admin.roles",
        ],
        # Comprehensive access for OAuth flows (validated scopes only).
        #
        # Least-privilege invariant (Google OAuth verification requires it):
        # never request a narrower scope alongside the full scope that
        # already covers it. Full scopes cover their readonly variants at
        # the API level (drive ⊇ drive.readonly/drive.file, gmail.modify ⊇
        # gmail.readonly/send/compose/labels, contacts ⊇ contacts.readonly,
        # etc.), so the narrow strings here were redundant and Google's
        # review flags such pairs. forms.responses_readonly and
        # people.directory_readonly stay: no requested full scope covers
        # form responses or directory data.
        "oauth_comprehensive": [
            "base.userinfo_email",
            "base.userinfo_profile",
            "base.openid",
            "drive.full",
            "docs.full",
            "gmail.modify",
            "gmail.settings_basic",
            "gmail.settings_sharing",
            "chat.messages",
            "chat.spaces",
            "chat.memberships",
            "sheets.full",
            "forms.body",
            "forms.responses_readonly",
            "slides.full",
            # photos.* intentionally excluded: Google rejects authorization
            # requests that combine photoslibrary scopes with Drive scopes
            # (400 invalid_request). Photos requires its own OAuth flow —
            # see SEPARATE_AUTH_SERVICES and the photos_basic group.
            "calendar.full",
            "tasks.full",
            "people.contacts",
            "people.directory_readonly",
        ],
    }

    # Scopes Google has removed entirely. Requesting them fails; API calls
    # relying on them return 403 PERMISSION_DENIED. (Photos Library scopes
    # retired after March 31, 2025.)
    RETIRED_SCOPES = {
        "https://www.googleapis.com/auth/photoslibrary",
        "https://www.googleapis.com/auth/photoslibrary.readonly",
        "https://www.googleapis.com/auth/photoslibrary.sharing",
    }

    # Services whose scopes Google refuses to combine with other services'
    # scopes in a single authorization request (400 invalid_request:
    # "This request contains scopes that cannot be requested together").
    # These must be authorized in their own OAuth flow with their own token.
    SEPARATE_AUTH_SERVICES = {"photos"}

    # Token group used by the combined Workspace flow. Services in
    # SEPARATE_AUTH_SERVICES each get their own token group (named after the
    # service), stored and refreshed independently so a Photos-only
    # authorization never overwrites the Workspace token for the same account.
    DEFAULT_TOKEN_GROUP = "workspace"

    # Aliases used by service configs that map onto a registry service name
    _TOKEN_GROUP_SERVICE_ALIASES = {"photoslibrary": "photos"}

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
    PEOPLE_SCOPES = GOOGLE_API_SCOPES["people"]
    BASE_SCOPES = GOOGLE_API_SCOPES["base"]

    @classmethod
    def get_token_group_for_service(cls, service: str) -> str:
        """
        Get the credential token group a service's tokens belong to.

        Services in SEPARATE_AUTH_SERVICES get their own group (named after
        the service); everything else shares DEFAULT_TOKEN_GROUP.

        Args:
            service: Service name (e.g. "drive", "photos", "photoslibrary")

        Returns:
            Token group name (e.g. "workspace" or "photos")
        """
        normalized = cls._TOKEN_GROUP_SERVICE_ALIASES.get(service, service)
        if normalized in cls.SEPARATE_AUTH_SERVICES:
            return normalized
        return cls.DEFAULT_TOKEN_GROUP

    @classmethod
    def get_token_group_for_services(cls, services: List[str]) -> str:
        """
        Get the token group for a set of services selected for one OAuth flow.

        A flow made up entirely of one separate-auth service maps to that
        service's group; any other combination maps to DEFAULT_TOKEN_GROUP
        (get_scopes_for_services drops separate-auth services from mixed
        requests, so the resulting token is a Workspace token).

        Args:
            services: Service names selected for the flow

        Returns:
            Token group name for the credentials this flow will produce
        """
        groups = {cls.get_token_group_for_service(s) for s in services or []}
        if len(groups) == 1:
            return groups.pop()
        return cls.DEFAULT_TOKEN_GROUP

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
        logger.debug(
            f"SCOPE_REGISTRY: Getting {service} scopes with {access_level} access"
        )

        if service not in cls.GOOGLE_API_SCOPES:
            available_services = list(cls.GOOGLE_API_SCOPES.keys())
            raise ValueError(
                f"Unknown service: {service}. Available: {available_services}"
            )

        # Try predefined group first
        group_name = f"{service}_{access_level}"
        if group_name in cls.SERVICE_SCOPE_GROUPS:
            return cls.resolve_scope_group(group_name)

        # Fallback to service-specific logic
        service_scopes = cls.GOOGLE_API_SCOPES[service]
        base_scopes = cls.GOOGLE_API_SCOPES["base"]

        result_scopes = [base_scopes["userinfo_email"], base_scopes["openid"]]

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
            # Basic access — request the full scope where one exists (it
            # covers readonly at the API level and keeps requests aligned
            # with what the OAuth flows grant).
            if service == "drive":
                result_scopes.append(service_scopes["full"])
            elif service == "gmail":
                result_scopes.append(service_scopes["modify"])
            elif service == "calendar":
                result_scopes.append(service_scopes["full"])
            elif service == "photos":
                result_scopes.extend(
                    [
                        service_scopes["appendonly"],
                        service_scopes["readonly_appcreated"],
                    ]
                )
            else:
                # Default to the full scope, falling back to readonly
                if "full" in service_scopes:
                    result_scopes.append(service_scopes["full"])
                elif "readonly" in service_scopes:
                    result_scopes.append(service_scopes["readonly"])

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
            raise ValueError(
                f"Unknown scope group: {group_name}. Available: {available_groups}"
            )

        scope_refs = cls.SERVICE_SCOPE_GROUPS[group_name]
        resolved_scopes = []

        for scope_ref in scope_refs:
            if "." in scope_ref:
                # Service.scope_name format
                try:
                    service, scope_name = scope_ref.split(".", 1)
                    if (
                        service in cls.GOOGLE_API_SCOPES
                        and scope_name in cls.GOOGLE_API_SCOPES[service]
                    ):
                        scope_url = cls.GOOGLE_API_SCOPES[service][scope_name]
                        resolved_scopes.append(scope_url)
                        logger.debug(
                            f"SCOPE_REGISTRY: Resolved {scope_ref} -> {scope_url}"
                        )
                    else:
                        logger.warning(
                            f"SCOPE_REGISTRY: Invalid scope reference: {scope_ref}"
                        )
                except ValueError:
                    logger.warning(
                        f"SCOPE_REGISTRY: Malformed scope reference: {scope_ref}"
                    )
            else:
                # Direct scope URL
                resolved_scopes.append(scope_ref)
                logger.debug(f"SCOPE_REGISTRY: Using direct scope: {scope_ref}")

        # Remove duplicates while preserving order
        unique_scopes = list(dict.fromkeys(resolved_scopes))
        logger.debug(
            f"SCOPE_REGISTRY: Group '{group_name}' resolved to {len(unique_scopes)} scopes"
        )

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
        logger.info(
            "SCOPE_REGISTRY: Getting OAuth scopes - using oauth_comprehensive as single source of truth"
        )

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

        # Google rejects authorization requests mixing Photos Library scopes
        # with any other Google API scopes (400 invalid_request)
        photos_scopes = [s for s in scopes if "auth/photoslibrary" in s]
        other_api_scopes = [
            s
            for s in scopes
            if "auth/photoslibrary" not in s
            and s not in cls.GOOGLE_API_SCOPES["base"].values()
        ]
        if photos_scopes and other_api_scopes:
            result.is_valid = False
            result.warnings.append(
                "Photos Library scopes cannot be requested together with other "
                "Google API scopes - Google returns 400 invalid_request. "
                "Authorize Photos in a separate OAuth flow."
            )
            logger.error(
                f"SCOPE_REGISTRY: Invalid combination - {len(photos_scopes)} Photos "
                f"scopes mixed with {len(other_api_scopes)} other API scopes"
            )

        # Check for missing base scopes
        base_scopes = cls.GOOGLE_API_SCOPES["base"]
        has_userinfo = base_scopes["userinfo_email"] in scopes
        has_openid = base_scopes["openid"] in scopes

        if not has_userinfo:
            result.missing_scopes.append(base_scopes["userinfo_email"])
            result.warnings.append(
                "Missing userinfo.email scope - user identification may fail"
            )

        if not has_openid:
            result.missing_scopes.append(base_scopes["openid"])
            result.warnings.append("Missing openid scope - OAuth flow may fail")

        # Set overall validity (preserve failures already recorded, e.g. the
        # Photos/other-API mutual exclusion above)
        result.is_valid = result.is_valid and len(result.invalid_scopes) == 0

        if result.is_valid:
            logger.info(
                f"SCOPE_REGISTRY: Scope validation passed for {len(scopes)} scopes"
            )
        else:
            logger.error(
                f"SCOPE_REGISTRY: Scope validation failed - {len(result.invalid_scopes)} invalid scopes"
            )

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
            "gmail_settings_sharing": cls.GOOGLE_API_SCOPES["gmail"][
                "settings_sharing"
            ],
            "calendar_read": cls.GOOGLE_API_SCOPES["calendar"]["readonly"],
            "calendar_events": cls.GOOGLE_API_SCOPES["calendar"]["events"],
            "docs_read": cls.GOOGLE_API_SCOPES["docs"]["readonly"],
            "docs_write": cls.GOOGLE_API_SCOPES["docs"]["full"],
            "sheets_read": cls.GOOGLE_API_SCOPES["sheets"]["readonly"],
            "sheets_write": cls.GOOGLE_API_SCOPES["sheets"]["full"],
            "photos_read": cls.GOOGLE_API_SCOPES["photos"]["readonly_appcreated"],
            "photos_append": cls.GOOGLE_API_SCOPES["photos"]["appendonly"],
            "tasks_read": cls.GOOGLE_API_SCOPES["tasks"]["readonly"],
            "tasks_full": cls.GOOGLE_API_SCOPES["tasks"]["full"],
        }

        if legacy_scope in legacy_mappings:
            resolved = legacy_mappings[legacy_scope]
            logger.info(
                f"SCOPE_REGISTRY: Legacy scope '{legacy_scope}' -> '{resolved}'"
            )
            return resolved

        # Try to find in current scopes by partial match
        for service_scopes in cls.GOOGLE_API_SCOPES.values():
            for scope_name, scope_url in service_scopes.items():
                if legacy_scope in scope_name or scope_name in legacy_scope:
                    logger.info(
                        f"SCOPE_REGISTRY: Legacy scope '{legacy_scope}' matched '{scope_url}'"
                    )
                    return scope_url

        # If no match found, return as-is and log warning
        logger.warning(
            f"SCOPE_REGISTRY: Could not resolve legacy scope '{legacy_scope}'"
        )
        return legacy_scope

    @classmethod
    def get_service_catalog(cls) -> Dict[str, Dict[str, Any]]:
        """Get user-friendly service catalog for selection interface."""
        return {
            "userinfo": {
                "name": "Basic Profile",
                "description": "Access your basic profile information and email",
                "category": "Core Services",
                "required": True,
                "scopes": cls.resolve_scope_group("base"),
            },
            "drive": {
                "name": "Google Drive",
                "description": "Upload, download, and manage files in Google Drive",
                "category": "Storage & Files",
                "required": False,
                "scopes": cls.get_service_scopes("drive", "basic"),
            },
            "gmail": {
                "name": "Gmail",
                "description": "Send, read, and manage email messages",
                "category": "Communication",
                "required": False,
                "scopes": cls.get_service_scopes("gmail", "basic"),
            },
            "calendar": {
                "name": "Google Calendar",
                "description": "Manage calendar events and scheduling",
                "category": "Productivity",
                "required": False,
                "scopes": cls.get_service_scopes("calendar", "basic"),
            },
            "docs": {
                "name": "Google Docs",
                "description": "Create and edit documents",
                "category": "Office Suite",
                "required": False,
                "scopes": cls.get_service_scopes("docs", "basic"),
            },
            "sheets": {
                "name": "Google Sheets",
                "description": "Create and edit spreadsheets",
                "category": "Office Suite",
                "required": False,
                "scopes": cls.get_service_scopes("sheets", "basic"),
            },
            "slides": {
                "name": "Google Slides",
                "description": "Create and edit presentations",
                "category": "Office Suite",
                "required": False,
                "scopes": cls.get_service_scopes("slides", "basic"),
            },
            "chat": {
                "name": "Google Chat",
                "description": "Send messages and manage chat spaces",
                "category": "Communication",
                "required": False,
                "scopes": cls.get_service_scopes("chat", "basic"),
            },
            "forms": {
                "name": "Google Forms",
                "description": "Create forms and collect responses",
                "category": "Productivity",
                "required": False,
                "scopes": cls.get_service_scopes("forms", "basic"),
            },
            "photos": {
                "name": "Google Photos",
                "description": (
                    "Upload photos and manage app-created albums. Requires a "
                    "separate sign-in - Google does not allow Photos scopes in "
                    "the same authorization as other services"
                ),
                "category": "Storage & Files",
                "required": False,
                "default_selected": False,
                "scopes": cls.get_service_scopes("photos", "basic"),
            },
            "people": {
                "name": "Google People API",
                "description": "Access user profiles and contact information",
                "category": "User Information",
                "required": False,
                "scopes": cls.get_service_scopes("people", "basic"),
            },
            "tasks": {
                "name": "Google Tasks",
                "description": "Manage task lists and to-do items",
                "category": "Productivity",
                "required": False,
                "default_selected": False,
                "scopes": cls.get_service_scopes("tasks", "basic"),
            },
        }

    @classmethod
    def get_default_services(cls) -> List[str]:
        """Return optional service keys that are selected by default."""
        return [
            key
            for key, info in cls.get_service_catalog().items()
            if not info.get("required", False) and info.get("default_selected", True)
        ]

    @classmethod
    def get_scopes_for_services(cls, service_keys: List[str]) -> List[str]:
        """
        Get combined scopes for selected services.

        Services in SEPARATE_AUTH_SERVICES (currently Photos) cannot share an
        authorization request with other services — Google rejects the mix
        with 400 invalid_request. When such a service is selected alongside
        others, it is dropped from the combined request and must be
        authorized in its own flow (e.g. selected_services=["photos"]).
        """
        catalog = cls.get_service_catalog()
        all_scopes = set()

        selected = [key for key in service_keys if key in catalog]
        exclusive = [key for key in selected if key in cls.SEPARATE_AUTH_SERVICES]
        combinable = [key for key in selected if key not in cls.SEPARATE_AUTH_SERVICES]

        if exclusive and combinable:
            logger.warning(
                f"SCOPE_REGISTRY: {exclusive} cannot be authorized together with "
                f"{combinable} - Google rejects the combined request "
                f"(400 invalid_request). Dropping {exclusive} from this flow; "
                f"authorize them separately (e.g. selected_services={exclusive})."
            )
        elif exclusive:
            # Only exclusive service(s) selected - honor them
            combinable = exclusive

        # Always include required services
        for service_key, service_info in catalog.items():
            if service_info.get("required", False):
                all_scopes.update(service_info["scopes"])

        # Add selected services
        for key in combinable:
            all_scopes.update(catalog[key]["scopes"])

        return list(all_scopes)


class ServiceScopeManager:
    """Manage service-specific scope requirements"""

    def __init__(self, service_name: str):
        """
        Initialize service scope manager.

        Args:
            service_name: Name of the Google service
        """
        self.service_name = service_name
        self.logger = setup_logger()

        if service_name not in ScopeRegistry.GOOGLE_API_SCOPES:
            available_services = list(ScopeRegistry.GOOGLE_API_SCOPES.keys())
            raise ValueError(
                f"Unknown service: {service_name}. Available: {available_services}"
            )

    def get_default_scopes(self) -> List[str]:
        """Get default scopes for this service"""
        return ScopeRegistry.get_service_scopes(self.service_name, "basic")

    def get_minimal_scopes(self) -> List[str]:
        """Get minimal scopes for basic functionality"""
        base_scopes = ScopeRegistry.GOOGLE_API_SCOPES["base"]
        service_scopes = ScopeRegistry.GOOGLE_API_SCOPES[self.service_name]

        minimal = [base_scopes["userinfo_email"], base_scopes["openid"]]

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

    def get_scope_recommendations(
        self, requested_operations: List[str]
    ) -> Dict[str, List[str]]:
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
            "full": self.get_full_scopes(),
        }

        # Add operation-specific recommendations
        service_scopes = ScopeRegistry.GOOGLE_API_SCOPES[self.service_name]

        if "read" in requested_operations and "readonly" in service_scopes:
            recommendations["readonly"] = [
                ScopeRegistry.GOOGLE_API_SCOPES["base"]["userinfo_email"],
                ScopeRegistry.GOOGLE_API_SCOPES["base"]["openid"],
                service_scopes["readonly"],
            ]

        if any(
            op in requested_operations for op in ["write", "create", "update", "delete"]
        ):
            if "full" in service_scopes:
                recommendations["write"] = [
                    ScopeRegistry.GOOGLE_API_SCOPES["base"]["userinfo_email"],
                    ScopeRegistry.GOOGLE_API_SCOPES["base"]["openid"],
                    service_scopes["full"],
                ]

        return recommendations
