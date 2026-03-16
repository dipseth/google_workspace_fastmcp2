"""Authentication middleware for session management and service injection."""

from config.enhanced_logging import setup_logger

logger = setup_logger()
import base64
import json
import os
import secrets
from datetime import datetime
from enum import Enum
from pathlib import Path

from fastmcp.server.dependencies import get_context
from fastmcp.server.middleware import Middleware, MiddlewareContext
from google.oauth2.credentials import Credentials
from typing_extensions import Any, Dict, Optional

# Try to import GoogleProvider - it might not be available
try:
    from fastmcp.server.auth.providers.google import GoogleProvider

    GOOGLE_PROVIDER_AVAILABLE = True
except ImportError:
    GoogleProvider = None
    GOOGLE_PROVIDER_AVAILABLE = False

from config.enhanced_logging import setup_logger
from config.settings import settings

from .context import (
    _get_pending_service_requests,
    _set_injected_service,
    _set_service_error,
    cleanup_expired_sessions,
    set_user_email_context,
)
from .dual_auth_bridge import get_dual_auth_bridge
from .service_manager import GoogleServiceError, get_google_service
from .types import AuthProvenance, SessionKey

logger = setup_logger()


class CredentialStorageMode(Enum):
    """Credential storage modes."""

    FILE_PLAINTEXT = "file_plaintext"  # Current: JSON files (backward compatible)
    FILE_ENCRYPTED = "file_encrypted"  # New: Encrypted JSON files
    MEMORY_ONLY = "memory_only"  # New: In-memory only (no persistence)
    MEMORY_WITH_BACKUP = "memory_with_backup"  # New: Memory + encrypted backup


class AuthMiddleware(Middleware):
    """Enhanced middleware for secure credential management, session context, service injection, and FastMCP GoogleProvider integration."""

    def __init__(
        self,
        storage_mode: CredentialStorageMode = CredentialStorageMode.FILE_ENCRYPTED,
        encryption_key: Optional[str] = None,
        google_provider: Optional["GoogleProvider"] = None,
    ):
        """
        Initialize AuthMiddleware with configurable credential storage and GoogleProvider integration.

        Args:
            storage_mode: How to store credentials (file_plaintext, file_encrypted, memory_only, memory_with_backup)
            encryption_key: Custom encryption key (auto-generated if not provided for encrypted modes)
            google_provider: FastMCP 2.12.0 GoogleProvider instance for unified authentication
        """
        self._last_cleanup = datetime.now()
        self._cleanup_interval_minutes = 30
        self._service_injection_enabled = True

        # Credential storage configuration
        self._storage_mode = storage_mode
        self._memory_credentials: Dict[str, Credentials] = {}
        self._encryption_key = encryption_key

        # GoogleProvider integration for unified authentication
        self._google_provider = google_provider
        self._unified_auth_enabled = bool(
            google_provider and settings.enable_unified_auth
        )

        # Service selection configuration
        self._enable_service_selection = True

        # Initialize dual auth bridge
        self._dual_auth_bridge = get_dual_auth_bridge()

        # PHASE 1 FIX: Instance-level session tracking (independent of FastMCP context)
        import threading

        self._active_sessions: Dict[int, str] = {}  # request_id -> session_id
        self._session_lock = threading.Lock()

        # Initialize encryption if needed
        if storage_mode in [
            CredentialStorageMode.FILE_ENCRYPTED,
            CredentialStorageMode.MEMORY_WITH_BACKUP,
        ]:
            self._setup_encryption()

        logger.debug(
            f"🔐 AuthMiddleware initialized with storage mode: {storage_mode.value}"
        )

        if self._unified_auth_enabled:
            logger.debug(
                "✅ Unified authentication enabled (FastMCP GoogleProvider integration)"
            )
            logger.debug("🔄 GoogleProvider ↔ Legacy Tool Bridge active")
            logger.debug("🌉 Dual Auth Bridge initialized for multi-account support")
        else:
            logger.debug(
                "⭕ Unified authentication disabled (no GoogleProvider or enable_unified_auth=False)"
            )

        # Log security recommendations
        if storage_mode == CredentialStorageMode.FILE_PLAINTEXT:
            logger.warning(
                "⚠️ Using plaintext file storage - consider upgrading to FILE_ENCRYPTED for production"
            )

    def _get_request_id(self, context: MiddlewareContext) -> int:
        """
        Get a unique identifier for this request.

        PHASE 1 FIX: Use Python's id() function on the context object itself
        to create a stable request identifier without relying on FastMCP context.
        """
        return id(context)

    def _get_or_create_session(self, request_id: int) -> str:
        """
        Get existing session or create new one for this request.

        PHASE 1 FIX: Session management independent of FastMCP context.
        Reuses existing sessions from thread-safe session store.
        """
        import uuid

        from .context import list_sessions

        # Check if we already have a session for this request
        with self._session_lock:
            if request_id in self._active_sessions:
                session_id = self._active_sessions[request_id]
                logger.debug(
                    f"♻️ Reusing session for request {request_id}: {session_id}"
                )
                return session_id

        # Try to reuse most recent active session from store
        active_sessions = list_sessions()
        if active_sessions:
            session_id = active_sessions[-1]
            logger.debug(f"♻️ Reusing most recent active session: {session_id}")
        else:
            # Generate new session only if necessary
            session_id = str(uuid.uuid4())
            logger.debug(f"🆕 Generated new session ID: {session_id}")

        # Track this session for this request
        with self._session_lock:
            self._active_sessions[request_id] = session_id

        return session_id

    async def on_request(self, context: MiddlewareContext, call_next):
        """
        Handle incoming requests and set session context.

        PHASE 1 FIX: Uses instance-level session tracking instead of FastMCP context.
        This avoids "Context is not available" errors during early request phases.
        """

        # PHASE 1 FIX: Get request ID and session without accessing FastMCP context
        request_id = self._get_request_id(context)
        session_id = self._get_or_create_session(request_id)

        logger.debug(f"🔍 Request {request_id} using session: {session_id}")

        # Periodic cleanup of expired sessions
        now = datetime.now()
        if (now - self._last_cleanup).total_seconds() > (
            self._cleanup_interval_minutes * 60
        ):
            try:
                cleanup_expired_sessions(settings.session_timeout_minutes)
                self._last_cleanup = now
                logger.debug("Performed periodic session cleanup")
            except Exception as e:
                logger.error(f"Error during session cleanup: {e}")

        try:
            result = await call_next(context)
            return result
        except Exception as e:
            logger.error(f"Error in request processing: {e}")
            raise
        finally:
            # PHASE 1 FIX: Clean up request-session mapping after request completes
            with self._session_lock:
                self._active_sessions.pop(request_id, None)
            logger.debug(
                f"🧹 Cleaned up request {request_id} (session preserved in store)"
            )

    async def on_call_tool(self, context: MiddlewareContext, call_next):
        """
        Handle tool execution with session context, service injection, and unified GoogleProvider authentication.

        PHASE 1 FIX: Uses instance-level session tracking for reliable session management.

        This method implements the unified OAuth architecture by:
        1. Extracting user context from GoogleProvider if available
        2. Auto-injecting user_google_email into tool calls
        3. Bridging credentials between authentication systems
        4. Providing seamless tool execution

        Args:
            context: MiddlewareContext containing tool call information
            call_next: Function to continue the middleware chain
        """
        from .context import get_session_data, store_session_data

        tool_name = context.message.name
        logger.debug(f"Processing tool call: {tool_name}")

        # PHASE 1 FIX: Get session from instance tracking (reliable and early-access safe)
        request_id = self._get_request_id(context)

        with self._session_lock:
            session_id = self._active_sessions.get(request_id)

        if not session_id:
            # Fallback: create session if on_request didn't run (shouldn't happen normally)
            session_id = self._get_or_create_session(request_id)
            logger.debug(
                f"⚠️ Created session in on_call_tool for {tool_name}: {session_id}"
            )
        else:
            logger.debug(f"✅ Using session for tool {tool_name}: {session_id}")

        # FastMCP Pattern: FIRST try JWT token (following FastMCP examples)
        user_email = None
        logger.debug(f"🔍 Starting user extraction for tool {tool_name}")

        # Detect auth provenance (api_key vs oauth) and store in session
        auth_provenance = self._detect_auth_provenance()
        if auth_provenance and session_id:
            store_session_data(session_id, SessionKey.AUTH_PROVENANCE, auth_provenance)

        # JWT AUTH: Primary authentication method following FastMCP pattern
        user_email = self._extract_user_from_jwt_token()
        if user_email:
            logger.debug(
                f"🎫 Extracted user from JWT token for tool {tool_name}: {user_email}"
            )
            # Register as primary account in dual auth bridge
            self._dual_auth_bridge.set_primary_account(user_email)
            # Store in session for future use
            if session_id:
                store_session_data(session_id, SessionKey.USER_EMAIL, user_email)
            # Set context immediately
            await set_user_email_context(user_email)
            # Auto-inject into tool arguments if missing
            await self._auto_inject_email_parameter(context, user_email)
        else:
            logger.debug(f"No JWT token authentication found for tool {tool_name}")

        # UNIFIED AUTH: Secondary - try GoogleProvider if configured
        if not user_email and self._unified_auth_enabled:
            user_email = await self._extract_user_from_google_provider()
            if user_email:
                logger.debug(
                    f"🔑 Extracted user from GoogleProvider for tool {tool_name}: {user_email}"
                )
                # Store in session for future use
                if session_id:
                    store_session_data(session_id, SessionKey.USER_EMAIL, user_email)
                # Set context immediately
                await set_user_email_context(user_email)
                # Auto-inject into tool arguments if missing
                await self._auto_inject_email_parameter(context, user_email)
            else:
                logger.debug(
                    f"No GoogleProvider authentication found for tool {tool_name}"
                )

        # LEGACY AUTH: Fallback to session data (OAuth authenticated)
        if not user_email and session_id:
            user_email = get_session_data(session_id, SessionKey.USER_EMAIL)
            if user_email:
                logger.debug(
                    f"✅ Retrieved user email from session storage for tool {tool_name}: {user_email}"
                )
                # Also set it in context for immediate use
                await set_user_email_context(user_email)
                # Auto-inject into tool arguments
                await self._auto_inject_email_parameter(context, user_email)
            else:
                logger.debug(
                    f"⚠️ No user email in session storage for session {session_id}"
                )

        # OAUTH FILE FALLBACK: Check for stored OAuth authentication data
        # Skip for API key / per-user key sessions — they must not inherit another user's identity
        if not user_email and auth_provenance not in (
            AuthProvenance.API_KEY,
            AuthProvenance.USER_API_KEY,
        ):
            user_email = self._load_oauth_authentication_data()
            if user_email:
                logger.debug(
                    f"✅ Retrieved user email from OAuth authentication file for tool {tool_name}: {user_email}"
                )
                # Register as secondary account in dual auth bridge
                self._dual_auth_bridge.add_secondary_account(user_email)
                # Store in session for future use
                if session_id:
                    store_session_data(session_id, SessionKey.USER_EMAIL, user_email)
                # Set context immediately
                await set_user_email_context(user_email)
                # Auto-inject into tool arguments if missing
                await self._auto_inject_email_parameter(context, user_email)
            else:
                logger.debug(f"No OAuth authentication file found for tool {tool_name}")

        # LEGACY AUTH: Fallback to tool arguments
        if not user_email:
            user_email = self._extract_user_email(context)
            if user_email:
                logger.debug(
                    f"🔍 DEBUG: Extracted user email from tool arguments for tool {tool_name}: {user_email}"
                )
                # Check if this is a known account or register as secondary
                if not (
                    self._dual_auth_bridge.is_primary_account(user_email)
                    or self._dual_auth_bridge.is_secondary_account(user_email)
                ):
                    self._dual_auth_bridge.add_secondary_account(user_email)
                # Store it in session for future use
                if session_id:
                    store_session_data(session_id, SessionKey.USER_EMAIL, user_email)
            else:
                logger.debug(
                    f"🔍 DEBUG: No user email found in tool arguments for tool {tool_name}"
                )

        # CREDENTIAL ISOLATION: Shared API key sessions can only use credentials
        # they created via start_google_auth in this session.
        # Ownership is tracked per-session (not global) to prevent cross-session leakage.
        if auth_provenance == AuthProvenance.API_KEY:
            # CodeMode meta-tools (tags, search, get_schema, execute) are transport
            # wrappers — they don't access Google credentials directly, so exempt
            # them from credential isolation.  The *inner* tool calls they dispatch
            # will go through on_call_tool again with the real tool_name.
            if tool_name in self._CODE_MODE_TOOLS:
                logger.debug(
                    f"🔓 Skipping credential isolation for CodeMode meta-tool: {tool_name}"
                )
            else:
                # Shared API key has no email claim — check tool arguments for target email
                tool_args = getattr(context.message, "arguments", {}) or {}
                target_email = (
                    (tool_args.get("user_google_email") or "").lower().strip()
                )

                # Also check the resolved user_email (from session data or fallback)
                effective_email = target_email or (user_email or "").lower().strip()

                if effective_email:
                    # Load per-session owned accounts from session storage
                    owned_raw = (
                        get_session_data(session_id, SessionKey.API_KEY_OWNED_ACCOUNTS)
                        if session_id
                        else None
                    )
                    owned_accounts = set(owned_raw) if owned_raw else set()

                    if tool_name == "start_google_auth":
                        # Register this email as owned by THIS session
                        owned_accounts.add(effective_email)
                        if session_id:
                            store_session_data(
                                session_id,
                                SessionKey.API_KEY_OWNED_ACCOUNTS,
                                list(owned_accounts),
                            )
                        logger.info(
                            f"🔑 Registered API key owned account (session-scoped): {effective_email}"
                        )
                    elif effective_email not in owned_accounts:
                        from .audit import log_security_event

                        log_security_event(
                            "api_key_credential_access_blocked",
                            user_email=effective_email,
                            details={
                                "tool_name": tool_name,
                                "session_id": session_id,
                                "reason": "API key session attempted to use credentials it did not create",
                            },
                        )
                        raise ValueError(
                            f"API key sessions can only access credentials they created. "
                            f"No credentials found for {effective_email} in this API key session.\n\n"
                            f"Run `start_google_auth` with your email to create credentials."
                        )

        # SEED SESSION_AUTHED_EMAILS: Ensure the session's authenticated email
        # (from OAuth, JWT, API key, etc.) is recorded so that subsequent
        # start_google_auth calls for OTHER emails can discover it and link.
        if session_id and user_email:
            _existing_authed = set(
                get_session_data(session_id, SessionKey.SESSION_AUTHED_EMAILS) or []
            )
            _norm_email = user_email.lower().strip()
            if _norm_email not in _existing_authed:
                _existing_authed.add(_norm_email)
                store_session_data(
                    session_id,
                    SessionKey.SESSION_AUTHED_EMAILS,
                    sorted(_existing_authed),
                )
                logger.debug(
                    f"🔗 Seeded SESSION_AUTHED_EMAILS with {_norm_email} "
                    f"(now {len(_existing_authed)} email(s))"
                )

        # SESSION-LEVEL ACCOUNT LINKING: When start_google_auth is called for
        # a new email, create pending links to ALL previously-authenticated
        # emails in this session.  This works for every auth type (OAuth,
        # API key, per-user key) — not just per-user key sessions.
        if tool_name == "start_google_auth" and session_id:
            from auth.user_api_keys import request_link

            tool_args = getattr(context.message, "arguments", {}) or {}
            target_email = (tool_args.get("user_google_email") or "").lower().strip()

            if target_email:
                # Load previously authenticated emails in this session
                prev_raw = (
                    get_session_data(session_id, SessionKey.SESSION_AUTHED_EMAILS) or []
                )
                prev_emails = set(prev_raw)

                # Determine link method and enforce time window for API key sessions.
                # API key sessions can only create links within 30 minutes of
                # key creation; after that, OAuth is required.
                if auth_provenance == AuthProvenance.OAUTH:
                    _link_method = "oauth"
                    _link_allowed = True
                elif auth_provenance == AuthProvenance.USER_API_KEY:
                    _link_method = "api_key"
                    from auth.user_api_keys import is_key_within_link_window

                    _link_allowed = is_key_within_link_window(user_email or "")
                    if not _link_allowed:
                        logger.warning(
                            f"🔗 API key link window expired for {user_email} → {target_email}. "
                            f"OAuth required to establish new links."
                        )
                else:
                    _link_method = "session"
                    _link_allowed = True

                # Queue pending links to every prior email in this session
                for prev in prev_emails:
                    if prev != target_email and _link_allowed:
                        request_link(prev, target_email, method=_link_method)
                        logger.info(
                            f"🔗 {_link_method} link: {prev} → {target_email} (deferred until OAuth completes)"
                        )

                # Record this email in the session's authenticated set
                prev_emails.add(target_email)
                store_session_data(
                    session_id, SessionKey.SESSION_AUTHED_EMAILS, sorted(prev_emails)
                )

        # PER-USER API KEY: can access bound email + linked accounts.
        if auth_provenance == AuthProvenance.USER_API_KEY:
            from auth.user_api_keys import get_accessible_emails

            # Stash the bearer token in session for per-user credential decryption.
            # The token IS the per-user API key — needed to derive the Fernet key
            # for encrypted credential files (split-key model).
            try:
                from fastmcp.server.dependencies import get_access_token as _gat

                _at = _gat()
                if _at and hasattr(_at, "token") and session_id:
                    store_session_data(
                        session_id, SessionKey.PER_USER_ENCRYPTION_KEY, _at.token
                    )
            except Exception:
                pass

            key_email = user_email  # From JWT claims (always the key-bound email)

            # Check tool arguments for a different target email
            tool_args = getattr(context.message, "arguments", {}) or {}
            target_email = tool_args.get("user_google_email", "")
            if target_email:
                target_email = target_email.lower().strip()

            if (
                tool_name != "start_google_auth"
                and target_email
                and key_email
                and target_email != key_email.lower()
            ):
                # Accessing a different account — check if linked
                accessible = get_accessible_emails(key_email)
                if target_email not in {e.lower() for e in accessible}:
                    from .audit import log_security_event

                    log_security_event(
                        "user_api_key_access_blocked",
                        user_email=target_email,
                        details={
                            "tool_name": tool_name,
                            "key_email": key_email,
                            "accessible_emails": sorted(accessible),
                            "reason": "Per-user key attempted to access unlinked account",
                        },
                    )
                    raise ValueError(
                        f"Your API key ({key_email}) does not have access to {target_email}.\n"
                        f"Accessible accounts: {', '.join(sorted(accessible))}\n\n"
                        f"Run `start_google_auth` with {target_email} to link it to your key."
                    )

        # Set user email context if found
        if user_email:
            await set_user_email_context(user_email)
            logger.debug(
                f"🔍 DEBUG: Set user email context for tool {tool_name}: {user_email}"
            )

            # Bridge credentials if needed (GoogleProvider → Legacy)
            if self._unified_auth_enabled:
                await self._bridge_credentials_if_needed(user_email)
        else:
            logger.debug(f"🔍 DEBUG: No user email available for tool {tool_name}")

        # Handle service injection if enabled
        if self._service_injection_enabled:
            await self._inject_services(tool_name, user_email)

        try:
            result = await call_next(context)
            logger.debug(f"Tool {tool_name} executed successfully")
            return result
        except Exception as e:
            logger.error(f"Error executing tool {tool_name}: {e}")
            raise

    async def on_read_resource(self, context: MiddlewareContext, call_next):
        """
        Handle resource access with session context and unified GoogleProvider authentication.

        PHASE 1 FIX: Uses instance-level session tracking for reliable session management.

        This method implements the unified OAuth architecture for resource access by:
        1. Extracting user context from GoogleProvider if available
        2. Setting user email context for resource authentication
        3. Bridging credentials between authentication systems
        4. Ensuring resources work immediately after OAuth authentication

        Args:
            context: MiddlewareContext containing resource access information
            call_next: Function to continue the middleware chain
        """
        from .context import get_session_data, store_session_data

        resource_uri = str(context.message.uri) if context.message.uri else "unknown"
        logger.debug(f"Processing resource access: {resource_uri}")

        # PHASE 1 FIX: Get session from instance tracking (reliable and context-independent)
        request_id = self._get_request_id(context)

        with self._session_lock:
            session_id = self._active_sessions.get(request_id)

        if not session_id:
            # Fallback: create session if needed (shouldn't happen normally)
            session_id = self._get_or_create_session(request_id)
            logger.debug(
                f"⚠️ Created session in on_read_resource for {resource_uri}: {session_id}"
            )
        else:
            logger.debug(f"✅ Using session for resource {resource_uri}: {session_id}")

        # FastMCP Pattern: FIRST try JWT token (following FastMCP examples)
        user_email = None
        logger.debug(f"🔍 Starting user extraction for resource {resource_uri}")

        # JWT AUTH: Primary authentication method following FastMCP pattern
        user_email = self._extract_user_from_jwt_token()
        if user_email:
            logger.debug(
                f"🎫 Extracted user from JWT token for resource {resource_uri}: {user_email}"
            )
            # Store in session for future use
            if session_id:
                store_session_data(session_id, SessionKey.USER_EMAIL, user_email)
            # Set context immediately
            await set_user_email_context(user_email)
        else:
            logger.debug(
                f"No JWT token authentication found for resource {resource_uri}"
            )

        # UNIFIED AUTH: Secondary - try GoogleProvider if configured
        if not user_email and self._unified_auth_enabled:
            user_email = await self._extract_user_from_google_provider()
            if user_email:
                logger.debug(
                    f"🔑 Extracted user from GoogleProvider for resource {resource_uri}: {user_email}"
                )
                # Store in session for future use
                if session_id:
                    store_session_data(session_id, SessionKey.USER_EMAIL, user_email)
                # Set context immediately
                await set_user_email_context(user_email)
            else:
                logger.debug(
                    f"No GoogleProvider authentication found for resource {resource_uri}"
                )

        # LEGACY AUTH: Fallback to session data (OAuth authenticated)
        if not user_email and session_id:
            user_email = get_session_data(session_id, SessionKey.USER_EMAIL)
            if user_email:
                logger.debug(
                    f"✅ Retrieved user email from session storage for resource {resource_uri}: {user_email}"
                )
                # Also set it in context for immediate use
                await set_user_email_context(user_email)
            else:
                logger.debug(
                    f"⚠️ No user email in session storage for session {session_id}"
                )

        # OAUTH FILE FALLBACK: Check for stored OAuth authentication data
        # Skip for API key / per-user key sessions — they must not inherit another user's identity
        auth_provenance = (
            get_session_data(session_id, SessionKey.AUTH_PROVENANCE)
            if session_id
            else None
        )
        if not user_email and auth_provenance not in (
            AuthProvenance.API_KEY,
            AuthProvenance.USER_API_KEY,
        ):
            user_email = self._load_oauth_authentication_data()
            if user_email:
                logger.debug(
                    f"✅ Retrieved user email from OAuth authentication file for resource {resource_uri}: {user_email}"
                )
                # Store in session for future use
                if session_id:
                    store_session_data(session_id, SessionKey.USER_EMAIL, user_email)
                # Set context immediately
                await set_user_email_context(user_email)
            else:
                logger.debug(
                    f"No OAuth authentication file found for resource {resource_uri}"
                )

        # Set user email context if found
        if user_email:
            await set_user_email_context(user_email)
            logger.debug(
                f"🔍 DEBUG: Set user email context for resource {resource_uri}: {user_email}"
            )

            # Bridge credentials if needed (GoogleProvider → Legacy)
            if self._unified_auth_enabled:
                await self._bridge_credentials_if_needed(user_email)
        else:
            logger.debug(
                f"🔍 DEBUG: No user email available for resource {resource_uri}"
            )

        try:
            result = await call_next(context)
            logger.debug(f"Resource {resource_uri} accessed successfully")
            return result
        except Exception as e:
            logger.error(f"Error accessing resource {resource_uri}: {e}")
            raise

    def _extract_user_email(self, context: MiddlewareContext) -> str:
        """
        Extract user email from tool arguments.

        Common parameter names: user_email, user_google_email, email
        """
        try:
            # Get arguments from the message
            if context.message.arguments:
                args = context.message.arguments

                # Try common user email parameter names
                for param_name in [
                    "user_email",
                    "user_google_email",
                    "email",
                    "google_email",
                ]:
                    if param_name in args and args[param_name]:
                        return args[param_name]

            logger.debug("No user email found in tool arguments")
            return None

        except Exception as e:
            logger.warning(f"Error extracting user email from tool arguments: {e}")
            return None

    async def _inject_services(self, tool_name: str, user_email: str):
        """
        Inject requested Google services into the context using secure credential loading.

        Args:
            tool_name: Name of the tool being executed
            user_email: User's email address for service authentication
        """
        if not user_email:
            logger.debug(
                f"No user email available for service injection in tool: {tool_name}"
            )
            return

        # Get pending service requests
        pending_requests = await _get_pending_service_requests()

        if not pending_requests:
            logger.debug(f"No pending service requests for tool: {tool_name}")
            return

        logger.debug(
            f"🔧 Injecting {len(pending_requests)} Google services for tool: {tool_name} (storage: {self._storage_mode.value})"
        )

        # Fulfill each service request
        for service_key, service_data in pending_requests.items():
            try:
                service_type = service_data["service_type"]
                scopes = service_data["scopes"]
                version = service_data["version"]
                cache_enabled = service_data["cache_enabled"]

                logger.debug(f"Creating {service_type} service for {user_email}")

                # Create the Google service using the new credential management
                service = await get_google_service(
                    user_email=user_email,
                    service_type=service_type,
                    scopes=scopes,
                    version=version,
                    cache_enabled=cache_enabled,
                )

                # Inject the service into context
                await _set_injected_service(service_key, service)

                logger.debug(
                    f"✅ Successfully injected {service_type} service "
                    f"for {user_email} in tool {tool_name}"
                )

            except GoogleServiceError as e:
                error_msg = (
                    f"Failed to create {service_data['service_type']} service: {str(e)}"
                )
                logger.error(f"❌ Service injection error for {tool_name}: {error_msg}")
                await _set_service_error(service_key, error_msg)

            except Exception as e:
                error_msg = f"Unexpected error creating {service_data['service_type']} service: {str(e)}"
                logger.error(f"❌ Service injection error for {tool_name}: {error_msg}")
                await _set_service_error(service_key, error_msg)

    def enable_service_injection(self, enabled: bool = True):
        """Enable or disable automatic service injection."""
        self._service_injection_enabled = enabled
        logger.debug(f"Service injection {'enabled' if enabled else 'disabled'}")

    @staticmethod
    def _derive_fernet_key(secret: str) -> bytes:
        """Derive a Fernet-compatible key from a secret string using HKDF.

        Uses HKDF-SHA256 to derive a 32-byte key from the secret, then
        base64url-encodes it for Fernet compatibility.

        Args:
            secret: The secret to derive from (e.g., MCP_API_KEY).

        Returns:
            Base64url-encoded 32-byte key suitable for Fernet.
        """
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.kdf.hkdf import HKDF

        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b"mcp-google-workspace-v1",
            info=b"credential-encryption",
        )
        return base64.urlsafe_b64encode(hkdf.derive(secret.encode()))

    def _get_server_secret(self) -> bytes:
        """Return the server-side secret used as HKDF salt for per-user encryption.

        This is the `.auth_encryption_key` file content.  If the file doesn't
        exist yet (fresh install), one is generated.  The secret never leaves
        the server, ensuring that per-user API keys alone cannot decrypt
        credential files.
        """
        key_path = Path(settings.credentials_dir) / ".auth_encryption_key"
        if key_path.exists():
            with open(key_path, "rb") as f:
                return f.read()
        # Generate and persist a new server secret
        from cryptography.fernet import Fernet

        key_bytes = Fernet.generate_key()
        key_path.parent.mkdir(parents=True, exist_ok=True)
        with open(key_path, "wb") as f:
            f.write(key_bytes)
        try:
            key_path.chmod(0o600)
        except OSError:
            logger.warning(
                "Could not set restrictive permissions on server secret "
                f"(.auth_encryption_key) — file may be world-readable"
            )
        return key_bytes

    def derive_per_user_fernet_key(self, per_user_key: str) -> bytes:
        """Derive a Fernet key from a per-user API key + server secret.

        Split-key model: decryption requires BOTH the per-user key (held by
        the user, shown once) AND the server secret (on disk, never exposed).
        Neither half alone is sufficient.

        Args:
            per_user_key: The plaintext per-user API key (bearer token).

        Returns:
            Base64url-encoded 32-byte Fernet key.
        """
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.kdf.hkdf import HKDF

        server_secret = self._get_server_secret()
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=server_secret,
            info=b"per-user-credential-encryption-v1",
        )
        return base64.urlsafe_b64encode(hkdf.derive(per_user_key.encode()))

    def _derive_oauth_recipient_key(self, google_sub: str, password: str = "") -> str:
        """Derive a deterministic recipient key for OAuth identity-based decryption.

        Uses Google's immutable account ID (``sub``) as the identity component.
        This is non-public — an attacker cannot derive it from just the email
        address; they'd need to actually complete OAuth for the Google account.

        When a ``password`` is provided it is mixed into the derivation,
        requiring the OAuth session to also know the passphrase.

        Security model: requires the server secret (on disk, 0600) AND the
        Google ``sub`` (only obtainable via OAuth) AND the optional password.

        Args:
            google_sub: Google's immutable numeric account ID (from ``sub`` claim).
            password: Optional passphrase set by the credential owner.

        Returns:
            A deterministic string key that can be passed to derive_per_user_fernet_key.
        """
        import hashlib

        server_secret = self._get_server_secret()
        material = (
            server_secret + b":oauth-identity-recipient-v2:" + google_sub.encode()
        )
        if password:
            material += b":" + password.encode()
        return hashlib.sha256(material).hexdigest()

    def _resolve_oauth_recipient_key(
        self,
        google_sub: Optional[str],
        normalized_email: str,
        password: str = "",
    ) -> Optional[str]:
        """Derive the OAuth recipient key for an email, respecting linkage prefs.

        The password is passed in from the caller (form submission or session),
        never read from disk.

        Returns None if cross-OAuth is disabled or google_sub is unavailable.
        """
        if not google_sub:
            return None
        try:
            from auth.user_api_keys import get_oauth_linkage

            linkage = get_oauth_linkage(normalized_email)
            if not linkage.get("enabled", True):
                return None
            return self._derive_oauth_recipient_key(google_sub, password=password)
        except Exception:
            return self._derive_oauth_recipient_key(google_sub, password=password)

    def _resolve_oauth_recipient_key_for_load(
        self,
        google_sub: Optional[str],
        normalized_email: str,
        session_password: str = "",
    ) -> list:
        """Build list of OAuth recipient keys to try during decryption.

        Tries session-provided password first, then no-password fallback.
        """
        if not google_sub:
            return []
        keys = []
        if session_password:
            keys.append(
                self._derive_oauth_recipient_key(google_sub, password=session_password)
            )
        # Always try without password (covers default no-password envelopes)
        keys.append(self._derive_oauth_recipient_key(google_sub))
        return keys

    def _try_decrypt_with_keys(
        self,
        path: Path,
        per_user_key: Optional[str],
        google_sub: Optional[str],
        normalized_email: str,
    ) -> Optional[Credentials]:
        """Try decrypting a credential file with all available keys.

        Priority: per-user key → OAuth recipient (with session password) → OAuth (no password).
        """
        keys_to_try = []
        if per_user_key:
            keys_to_try.append(per_user_key)

        if google_sub:
            # Get passphrase from current session first; fall back to scan
            # to avoid cross-session leakage in multi-user scenarios.
            session_password = ""
            try:
                from .context import (
                    get_session_context_sync,
                    get_session_data,
                    list_sessions,
                )

                current_sid = get_session_context_sync()
                if current_sid:
                    session_password = (
                        get_session_data(current_sid, SessionKey.OAUTH_LINKAGE_PASSWORD)
                        or ""
                    )
                if not session_password:
                    # Fallback for contexts without FastMCP session (e.g. OAuth callback)
                    for sid in reversed(list_sessions()):
                        pwd = get_session_data(sid, SessionKey.OAUTH_LINKAGE_PASSWORD)
                        if pwd:
                            session_password = pwd
                            break
            except Exception:
                pass
            keys_to_try.extend(
                self._resolve_oauth_recipient_key_for_load(
                    google_sub, normalized_email, session_password
                )
            )

        for key in keys_to_try:
            try:
                creds = self._load_encrypted_file(path, key)
                if creds:
                    return creds
            except Exception:
                continue
        return None

    def _save_encrypted_with_recipients(
        self,
        path: Path,
        credentials: Credentials,
        per_user_key: Optional[str],
        additional_keys: Optional[list],
        oauth_recipient_key: Optional[str],
        normalized_email: str,
    ) -> None:
        """Save credentials with per-user + OAuth recipients, with proper fallbacks."""
        if per_user_key:
            all_additional = list(additional_keys or [])
            if oauth_recipient_key:
                all_additional.append(oauth_recipient_key)
            self._save_per_user_encrypted(
                path,
                credentials,
                per_user_key,
                additional_keys=all_additional if all_additional else None,
            )
            logger.info(
                f"🔐 Saved per-user encrypted credentials for {normalized_email}"
                + (" (+OAuth recipient)" if oauth_recipient_key else "")
            )
        elif oauth_recipient_key:
            self._save_per_user_encrypted(
                path,
                credentials,
                oauth_recipient_key,
                additional_keys=additional_keys,
            )
            logger.info(
                f"🔐 Saved OAuth-recipient encrypted credentials for {normalized_email} "
                f"(per-user key recipient restored on next key-based auth)"
            )
        else:
            encrypted_data = self._encrypt_credentials(credentials)
            with open(path, "w") as f:
                f.write(encrypted_data)
            logger.debug(f"Saved server-encrypted credentials for {normalized_email}")

    def _setup_encryption(self):
        """Setup encryption for secure credential storage.

        Key derivation priority:
        1. Explicit ``encryption_key`` parameter (base64-encoded)
        2. Derived from ``MCP_API_KEY`` env var via HKDF — crypto-binds
           credential files to the API secret so they are undecryptable
           without it.
        3. Auto-generated random server key stored in ``.auth_encryption_key``
           (fallback when no API key is configured).

        When switching from server key → MCP_API_KEY derivation, the old
        server key is kept as ``_legacy_fernet`` so existing credential
        files can still be decrypted (and transparently re-encrypted on
        next save).
        """
        try:
            if self._encryption_key:
                # Use provided key
                key_bytes = base64.urlsafe_b64decode(self._encryption_key.encode())
                self._key_source = "explicit"
            else:
                # Priority: MCP_API_KEY derivation > auto-generated server key
                mcp_api_key = os.getenv("MCP_API_KEY", "")
                if mcp_api_key:
                    key_bytes = self._derive_fernet_key(mcp_api_key)
                    self._key_source = "mcp_api_key"
                    logger.info(
                        "🔐 Encryption key derived from MCP_API_KEY (crypto-bound)"
                    )
                else:
                    # Fallback: auto-generated random server key
                    key_path = Path(settings.credentials_dir) / ".auth_encryption_key"

                    if key_path.exists():
                        with open(key_path, "rb") as f:
                            key_bytes = f.read()
                    else:
                        # Generate new key
                        key_bytes = base64.urlsafe_b64encode(secrets.token_bytes(32))
                        key_path.parent.mkdir(parents=True, exist_ok=True)

                        with open(key_path, "wb") as f:
                            f.write(key_bytes)

                        # Set restrictive permissions
                        try:
                            key_path.chmod(0o600)
                        except (OSError, AttributeError):
                            logger.warning(
                                "Could not set restrictive permissions on encryption key"
                            )
                    self._key_source = "server_key"

            # Import here to avoid dependency issues if cryptography not installed
            from cryptography.fernet import Fernet

            self._fernet = Fernet(key_bytes)

            # Migration: keep legacy server key for decrypting old credentials
            # when we've switched to MCP_API_KEY-derived encryption.
            if self._key_source == "mcp_api_key":
                legacy_path = Path(settings.credentials_dir) / ".auth_encryption_key"
                if legacy_path.exists():
                    try:
                        with open(legacy_path, "rb") as f:
                            legacy_key = f.read()
                        self._legacy_fernet = Fernet(legacy_key)
                        logger.debug(
                            "🔄 Legacy server key loaded for credential migration"
                        )
                    except Exception:
                        pass

            logger.debug("✅ Encryption initialized for secure credential storage")

        except ImportError:
            logger.error(
                "❌ cryptography package required for encrypted storage. Install with: pip install cryptography"
            )
            logger.debug("🔄 Falling back to plaintext storage...")
            self._storage_mode = CredentialStorageMode.FILE_PLAINTEXT
        except Exception as e:
            logger.error(f"❌ Failed to setup encryption: {e}")
            logger.debug("🔄 Falling back to plaintext storage...")
            self._storage_mode = CredentialStorageMode.FILE_PLAINTEXT

    def _encrypt_credentials(self, credentials: Credentials) -> str:
        """Encrypt credentials for secure storage."""
        if not hasattr(self, "_fernet"):
            raise RuntimeError("Encryption not initialized")

        creds_data = {
            "token": credentials.token,
            "refresh_token": credentials.refresh_token,
            "token_uri": credentials.token_uri,
            "client_id": credentials.client_id,
            "client_secret": credentials.client_secret,
            "scopes": credentials.scopes,
            "expiry": credentials.expiry.isoformat() if credentials.expiry else None,
            "encrypted_at": datetime.now().isoformat(),
            "storage_mode": self._storage_mode.value,
        }

        json_data = json.dumps(creds_data).encode()
        encrypted_data = self._fernet.encrypt(json_data)
        return base64.urlsafe_b64encode(encrypted_data).decode()

    def _decrypt_credentials(self, encrypted_data: str) -> Credentials:
        """Decrypt and reconstruct credentials.

        Tries the primary Fernet key first.  If that fails and a legacy
        server key exists (migration from random key → MCP_API_KEY-derived
        key), retries with the legacy key so existing credential files are
        not orphaned.
        """
        if not hasattr(self, "_fernet"):
            raise RuntimeError("Encryption not initialized")

        try:
            encrypted_bytes = base64.urlsafe_b64decode(encrypted_data.encode())

            try:
                decrypted_data = self._fernet.decrypt(encrypted_bytes)
            except Exception:
                # Migration fallback: try legacy server key
                if hasattr(self, "_legacy_fernet"):
                    logger.info(
                        "🔄 Primary key failed — decrypting with legacy server key "
                        "(credentials will be re-encrypted with derived key on next save)"
                    )
                    decrypted_data = self._legacy_fernet.decrypt(encrypted_bytes)
                else:
                    raise

            creds_data = json.loads(decrypted_data.decode())

            credentials = Credentials(
                token=creds_data["token"],
                refresh_token=creds_data["refresh_token"],
                token_uri=creds_data.get(
                    "token_uri", "https://oauth2.googleapis.com/token"
                ),
                client_id=creds_data["client_id"],
                client_secret=creds_data["client_secret"],
                scopes=creds_data.get("scopes", settings.drive_scopes),
            )

            if creds_data.get("expiry"):
                expiry = datetime.fromisoformat(creds_data["expiry"])
                # Keep timezone-naive to match Google's Credentials.expired property
                # which uses datetime.utcnow() internally
                if expiry.tzinfo is not None:
                    # Convert timezone-aware to naive UTC
                    expiry = expiry.replace(tzinfo=None)
                credentials.expiry = expiry

            return credentials

        except Exception as e:
            logger.error(f"Failed to decrypt credentials: {e}")
            raise

    def save_credentials(
        self,
        user_email: str,
        credentials: Credentials,
        per_user_key: Optional[str] = None,
        additional_keys: Optional[list] = None,
        google_sub: Optional[str] = None,
        oauth_linkage_password: str = "",
    ) -> None:
        """
        Save credentials using the configured storage mode.

        When ``per_user_key`` is provided the credential file is encrypted
        with a split-key derived from the per-user API key + server secret.
        This makes the file undecryptable without the user presenting their
        bearer token at runtime.

        Args:
            user_email: User's email address (will be normalized to lowercase)
            credentials: Google OAuth credentials
            per_user_key: Optional plaintext per-user API key for per-user encryption
            additional_keys: Optional list of additional per-user keys to add as
                recipients (for linked accounts)
            google_sub: Optional Google account ID (sub claim) for OAuth recipient
            oauth_linkage_password: Passphrase for OAuth recipient key derivation
                (in-memory only, never persisted)
        """
        # Import normalization function
        from .google_auth import _normalize_email

        normalized_email = _normalize_email(user_email)

        logger.debug(
            f"💾 Saving credentials for {normalized_email} using {self._storage_mode.value}"
        )

        if self._storage_mode == CredentialStorageMode.MEMORY_ONLY:
            # Store only in memory with normalized email
            self._memory_credentials[normalized_email] = credentials
            logger.debug(f"Stored credentials in memory for {normalized_email}")

        elif self._storage_mode == CredentialStorageMode.FILE_PLAINTEXT:
            # Backward compatibility - use existing file-based storage (handles normalization)
            from .google_auth import _save_credentials

            _save_credentials(normalized_email, credentials)

        elif self._storage_mode == CredentialStorageMode.FILE_ENCRYPTED:
            # Encrypted file storage with normalized email
            safe_email = normalized_email.replace("@", "_at_").replace(".", "_")
            creds_path = (
                Path(settings.credentials_dir) / f"{safe_email}_credentials.enc"
            )
            creds_path.parent.mkdir(parents=True, exist_ok=True)

            oauth_recipient_key = self._resolve_oauth_recipient_key(
                google_sub, normalized_email, password=oauth_linkage_password
            )
            self._save_encrypted_with_recipients(
                creds_path,
                credentials,
                per_user_key,
                additional_keys,
                oauth_recipient_key,
                normalized_email,
            )

            # Set restrictive permissions
            try:
                creds_path.chmod(0o600)
            except (OSError, AttributeError):
                logger.warning(
                    "Could not set restrictive permissions on credential file"
                )

        elif self._storage_mode == CredentialStorageMode.MEMORY_WITH_BACKUP:
            # Store in memory + encrypted backup with normalized email
            self._memory_credentials[normalized_email] = credentials

            # Also save encrypted backup
            safe_email = normalized_email.replace("@", "_at_").replace(".", "_")
            backup_path = Path(settings.credentials_dir) / f"{safe_email}_backup.enc"
            backup_path.parent.mkdir(parents=True, exist_ok=True)

            oauth_recipient_key = self._resolve_oauth_recipient_key(
                google_sub, normalized_email, password=oauth_linkage_password
            )
            self._save_encrypted_with_recipients(
                backup_path,
                credentials,
                per_user_key,
                additional_keys,
                oauth_recipient_key,
                normalized_email,
            )

            try:
                backup_path.chmod(0o600)
            except (OSError, AttributeError):
                pass

    @staticmethod
    def _key_id(per_user_key: str) -> str:
        """Deterministic identifier for a per-user key (full SHA-256 hex digest).

        Used as the key in the ``recipients`` dict so we can look up the
        correct wrapped CEK without trying every entry.
        """
        import hashlib

        return hashlib.sha256(per_user_key.encode()).hexdigest()

    def _compute_envelope_hmac(self, envelope: dict) -> str:
        """Compute HMAC-SHA256 over the envelope (excluding the hmac field itself).

        Keyed with the server secret to detect tampering, recipient removal,
        and downgrade attacks.
        """
        import hashlib
        import hmac as _hmac

        # Build a canonical representation excluding the hmac field
        hmac_input = {k: v for k, v in envelope.items() if k != "hmac"}
        payload = json.dumps(hmac_input, sort_keys=True).encode()
        server_secret = self._get_server_secret()
        return _hmac.new(server_secret, payload, hashlib.sha256).hexdigest()

    def _verify_envelope_hmac(self, envelope: dict) -> bool:
        """Verify the envelope's HMAC. Returns True if valid or if no HMAC present (legacy)."""
        import hmac as _hmac

        stored_hmac = envelope.get("hmac")
        if not stored_hmac:
            return True  # Legacy envelope without HMAC — allow for backward compat
        expected = self._compute_envelope_hmac(envelope)
        return _hmac.compare_digest(stored_hmac, expected)

    @staticmethod
    def _zero_bytes(b: bytes) -> None:
        """Best-effort zeroing of a bytes object in CPython.

        This is not guaranteed by Python but raises the bar against memory
        inspection attacks on long-running server processes.
        """
        try:
            import ctypes

            ctypes.memset(id(b) + bytes.__basicsize__ - 1, 0, len(b))
        except Exception:
            pass  # Non-CPython or restricted environment

    def _save_per_user_encrypted(
        self,
        path: Path,
        credentials: Credentials,
        per_user_key: str,
        additional_keys: Optional[list] = None,
    ) -> None:
        """Encrypt credentials with a random CEK and wrap for each authorized user.

        Multi-recipient envelope format::

            {
              "v": 2,
              "enc": "per_user",
              "recipients": {
                "<key_id_A>": "<CEK wrapped for A>",
                "<key_id_B>": "<CEK wrapped for B>"
              },
              "data": "<credentials encrypted with CEK>"
            }

        Args:
            path: Where to write the envelope.
            credentials: Google API credentials to encrypt.
            per_user_key: The primary owner's plaintext per-user API key.
            additional_keys: Optional list of additional plaintext per-user keys
                that should also be able to decrypt (linked accounts).
        """
        from cryptography.fernet import Fernet

        # 1. Generate random Content Encryption Key (CEK)
        cek = Fernet.generate_key()  # 32-byte URL-safe base64

        try:
            # 2. Encrypt credentials with CEK
            creds_data = {
                "token": credentials.token,
                "refresh_token": credentials.refresh_token,
                "token_uri": credentials.token_uri,
                "client_id": credentials.client_id,
                "client_secret": credentials.client_secret,
                "scopes": credentials.scopes,
                "expiry": credentials.expiry.isoformat()
                if credentials.expiry
                else None,
                "encrypted_at": datetime.now().isoformat(),
            }
            cek_fernet = Fernet(cek)
            encrypted_creds = cek_fernet.encrypt(json.dumps(creds_data).encode())

            # 3. Wrap CEK for each authorized user
            recipients = {}
            all_keys = [per_user_key] + (additional_keys or [])
            for key in all_keys:
                kid = self._key_id(key)
                wrapper_fernet_key = self.derive_per_user_fernet_key(key)
                wrapper = Fernet(wrapper_fernet_key)
                wrapped_cek = wrapper.encrypt(cek)
                recipients[kid] = base64.urlsafe_b64encode(wrapped_cek).decode()

            # 4. Build envelope with integrity HMAC
            envelope = {
                "v": 2,
                "enc": "per_user",
                "recipients": recipients,
                "data": base64.urlsafe_b64encode(encrypted_creds).decode(),
            }
            envelope["hmac"] = self._compute_envelope_hmac(envelope)

            with open(path, "w") as f:
                json.dump(envelope, f)
        finally:
            # Best-effort zeroing of CEK in memory
            self._zero_bytes(cek)

        logger.debug(
            f"🔐 Wrote multi-recipient envelope to {path.name} "
            f"({len(recipients)} recipient(s))"
        )

    def _load_per_user_encrypted(
        self, envelope: dict, per_user_key: str
    ) -> Credentials:
        """Decrypt a per-user encrypted credential envelope.

        Supports both legacy single-recipient (no ``recipients`` key) and
        multi-recipient (with ``recipients`` dict) formats.
        """
        from cryptography.fernet import Fernet

        # Verify envelope integrity before processing
        if not self._verify_envelope_hmac(envelope):
            raise ValueError("Envelope HMAC verification failed — possible tampering")

        fernet_key = self.derive_per_user_fernet_key(per_user_key)
        cek = None

        try:
            if "recipients" in envelope:
                # Multi-recipient: unwrap CEK first, then decrypt credentials
                kid = self._key_id(per_user_key)
                wrapped_cek_b64 = envelope["recipients"].get(kid)
                if not wrapped_cek_b64:
                    raise ValueError(
                        f"No recipient entry for this key. "
                        f"{len(envelope['recipients'])} recipient(s) in envelope."
                    )
                wrapped_cek = base64.urlsafe_b64decode(wrapped_cek_b64.encode())
                cek = Fernet(fernet_key).decrypt(wrapped_cek)
                # CEK is itself a Fernet key — use it to decrypt credentials
                encrypted_creds = base64.urlsafe_b64decode(envelope["data"].encode())
                decrypted_data = Fernet(cek).decrypt(encrypted_creds)
            else:
                # Legacy single-recipient: per-user key encrypts credentials directly
                encrypted_bytes = base64.urlsafe_b64decode(envelope["data"].encode())
                decrypted_data = Fernet(fernet_key).decrypt(encrypted_bytes)
        finally:
            if cek:
                self._zero_bytes(cek)

        creds_data = json.loads(decrypted_data.decode())

        credentials = Credentials(
            token=creds_data["token"],
            refresh_token=creds_data["refresh_token"],
            token_uri=creds_data.get(
                "token_uri", "https://oauth2.googleapis.com/token"
            ),
            client_id=creds_data["client_id"],
            client_secret=creds_data["client_secret"],
            scopes=creds_data.get("scopes", settings.drive_scopes),
        )

        if creds_data.get("expiry"):
            expiry = datetime.fromisoformat(creds_data["expiry"])
            if expiry.tzinfo is not None:
                expiry = expiry.replace(tzinfo=None)
            credentials.expiry = expiry

        return credentials

    def add_recipient_to_encrypted_file(
        self, path: Path, existing_key: str, new_key: str
    ) -> bool:
        """Add a new recipient to an existing multi-recipient envelope.

        Uses file locking to prevent TOCTOU races when concurrent sessions
        modify the same envelope. Verifies envelope HMAC before processing
        and recomputes it after modification.

        Args:
            path: Path to the ``.enc`` credential file.
            existing_key: Plaintext per-user key that can already decrypt.
            new_key: Plaintext per-user key to add as a new recipient.

        Returns:
            True if the recipient was added, False on failure.
        """
        import fcntl

        from cryptography.fernet import Fernet

        if not path.exists():
            logger.warning(f"Cannot add recipient — file not found: {path}")
            return False

        cek = None
        try:
            with open(path, "r+") as f:
                # Exclusive lock to prevent concurrent read-modify-write races
                fcntl.flock(f, fcntl.LOCK_EX)
                try:
                    envelope = json.load(f)

                    if (
                        not isinstance(envelope, dict)
                        or envelope.get("enc") != "per_user"
                    ):
                        logger.warning(f"Not a per-user envelope: {path}")
                        return False

                    if "recipients" not in envelope:
                        logger.warning(
                            f"Legacy single-recipient envelope — cannot add recipient: {path}. "
                            f"Re-encrypt with multi-recipient format first."
                        )
                        return False

                    # Verify envelope integrity
                    if not self._verify_envelope_hmac(envelope):
                        logger.error(f"Envelope HMAC verification failed: {path.name}")
                        return False

                    new_kid = self._key_id(new_key)
                    if new_kid in envelope["recipients"]:
                        logger.debug(f"Recipient already in envelope {path.name}")
                        return True

                    # Unwrap CEK with existing key
                    existing_kid = self._key_id(existing_key)
                    wrapped_cek_b64 = envelope["recipients"].get(existing_kid)
                    if not wrapped_cek_b64:
                        logger.error(
                            f"Cannot unwrap CEK — existing key not in recipients of {path.name}"
                        )
                        return False

                    existing_fernet_key = self.derive_per_user_fernet_key(existing_key)
                    wrapped_cek = base64.urlsafe_b64decode(wrapped_cek_b64.encode())
                    cek = Fernet(existing_fernet_key).decrypt(wrapped_cek)

                    # Wrap CEK for new recipient
                    new_fernet_key = self.derive_per_user_fernet_key(new_key)
                    new_wrapped_cek = Fernet(new_fernet_key).encrypt(cek)
                    envelope["recipients"][new_kid] = base64.urlsafe_b64encode(
                        new_wrapped_cek
                    ).decode()

                    # Recompute HMAC over updated envelope
                    envelope["hmac"] = self._compute_envelope_hmac(envelope)

                    # Write back atomically within the lock
                    f.seek(0)
                    f.truncate()
                    json.dump(envelope, f)

                    logger.info(
                        f"🔐 Added recipient to {path.name} "
                        f"(now {len(envelope['recipients'])} recipient(s))"
                    )
                    return True
                finally:
                    fcntl.flock(f, fcntl.LOCK_UN)

        except Exception as e:
            logger.error(f"Failed to add recipient to {path.name}: {e}")
            return False
        finally:
            if cek:
                self._zero_bytes(cek)

    def load_credentials(
        self,
        user_email: str,
        per_user_key: Optional[str] = None,
        google_sub: Optional[str] = None,
    ) -> Optional[Credentials]:
        """
        Load credentials using the configured storage mode.

        For per-user encrypted files, ``per_user_key`` (the bearer token)
        is required to derive the decryption key.  Falls back to the OAuth
        identity recipient key (derived from ``google_sub`` + server secret)
        when no per-user key is available.

        Args:
            user_email: User's email address (will be normalized to lowercase)
            per_user_key: Plaintext per-user API key (bearer token) for per-user decryption
            google_sub: Google account ID for OAuth recipient key derivation

        Returns:
            Credentials if found and decryptable, None otherwise
        """
        # Import normalization function
        from .google_auth import _normalize_email

        normalized_email = _normalize_email(user_email)

        if self._storage_mode == CredentialStorageMode.MEMORY_ONLY:
            return self._memory_credentials.get(normalized_email)

        elif self._storage_mode == CredentialStorageMode.MEMORY_WITH_BACKUP:
            # Try memory first with normalized email
            if normalized_email in self._memory_credentials:
                return self._memory_credentials[normalized_email]

            # Fall back to encrypted backup
            safe_email = normalized_email.replace("@", "_at_").replace(".", "_")
            backup_path = Path(settings.credentials_dir) / f"{safe_email}_backup.enc"

            if backup_path.exists():
                creds = self._try_decrypt_with_keys(
                    backup_path, per_user_key, google_sub, normalized_email
                )
                if creds:
                    return creds

            return None

        elif self._storage_mode == CredentialStorageMode.FILE_ENCRYPTED:
            safe_email = normalized_email.replace("@", "_at_").replace(".", "_")
            creds_path = (
                Path(settings.credentials_dir) / f"{safe_email}_credentials.enc"
            )

            if not creds_path.exists():
                return None

            creds = self._try_decrypt_with_keys(
                creds_path, per_user_key, google_sub, normalized_email
            )
            if creds:
                return creds

            logger.warning(
                f"Could not decrypt credentials for {normalized_email} "
                f"with any available key"
            )
            return None

        elif self._storage_mode == CredentialStorageMode.FILE_PLAINTEXT:
            # Backward compatibility - use existing file-based storage (handles normalization)
            from .google_auth import _load_credentials

            return _load_credentials(normalized_email)

        return None

    def _load_encrypted_file(
        self, path: Path, per_user_key: Optional[str] = None
    ) -> Optional[Credentials]:
        """Load and decrypt a credential file, handling both per-user and server encryption.

        Detection:
        - JSON with ``{"v": 2, "enc": "per_user"}`` → per-user split-key decryption
        - Raw base64 string → server-wide Fernet decryption (legacy)
        """
        with open(path, "r") as f:
            raw = f.read()

        # Try JSON envelope first (v2 format)
        try:
            envelope = json.loads(raw)
            if isinstance(envelope, dict) and envelope.get("enc") == "per_user":
                if not per_user_key:
                    logger.warning(
                        f"🔐 Per-user encrypted file requires bearer token to decrypt: {path.name}"
                    )
                    return None
                return self._load_per_user_encrypted(envelope, per_user_key)
        except (json.JSONDecodeError, ValueError):
            pass  # Not JSON — treat as legacy raw base64

        # Legacy: server-wide encrypted (raw base64 Fernet)
        return self._decrypt_credentials(raw)

    def get_storage_mode(self) -> CredentialStorageMode:
        """Get the current credential storage mode."""
        return self._storage_mode

    def get_credential_summary(self) -> Dict[str, Any]:
        """Get summary of stored credentials for debugging."""
        summary = {
            "storage_mode": self._storage_mode.value,
            "memory_credentials": list(self._memory_credentials.keys()),
            "file_credentials": [],
        }

        # Check file-based credentials
        try:
            creds_dir = Path(settings.credentials_dir)
            if creds_dir.exists():
                for pattern in [
                    "*_credentials.json",
                    "*_credentials.enc",
                    "*_backup.enc",
                ]:
                    for file_path in creds_dir.glob(pattern):
                        safe_email = file_path.stem.replace("_credentials", "").replace(
                            "_backup", ""
                        )
                        email = safe_email.replace("_at_", "@").replace("_", ".")
                        summary["file_credentials"].append(
                            {
                                "email": email,
                                "file": file_path.name,
                                "encrypted": file_path.suffix == ".enc",
                            }
                        )
        except Exception as e:
            summary["file_error"] = str(e)

        return summary

    def is_service_injection_enabled(self) -> bool:
        """Check if service injection is enabled."""
        return self._service_injection_enabled

    def migrate_credentials(self, target_mode: CredentialStorageMode) -> Dict[str, str]:
        """
        Migrate existing credentials to a different storage mode.

        Args:
            target_mode: Target storage mode to migrate to

        Returns:
            Dictionary with migration results per user
        """
        results = {}

        # Get current credentials
        current_summary = self.get_credential_summary()

        # Find all users with credentials
        all_users = set()

        # Add users from memory
        all_users.update(current_summary.get("memory_credentials", []))

        # Add users from files
        for file_info in current_summary.get("file_credentials", []):
            all_users.add(file_info["email"])

        logger.debug(f"🔄 Migrating {len(all_users)} users to {target_mode.value}")

        # Migrate each user
        for user_email in all_users:
            try:
                # Load credentials using current mode
                credentials = self.load_credentials(user_email)

                if credentials:
                    # Temporarily switch to target mode
                    old_mode = self._storage_mode
                    self._storage_mode = target_mode

                    # Save using new mode
                    self.save_credentials(user_email, credentials)

                    # Restore original mode for next user
                    self._storage_mode = old_mode

                    results[user_email] = f"✅ Migrated to {target_mode.value}"
                else:
                    results[user_email] = "⚠️ No credentials found"

            except Exception as e:
                results[user_email] = f"❌ Migration failed: {str(e)}"
                logger.error(f"Failed to migrate credentials for {user_email}: {e}")

        # Update to target mode
        self._storage_mode = target_mode
        logger.debug(f"✅ Migration completed. New storage mode: {target_mode.value}")

        return results

    async def _extract_user_from_google_provider(self) -> Optional[str]:
        """
        Extract user email from FastMCP 2.12.0 GoogleProvider token context.

        This implements the unified OAuth architecture by extracting authenticated
        user information from GoogleProvider without requiring manual email parameters.

        Returns:
            User email address if authenticated via GoogleProvider, None otherwise
        """
        if not self._google_provider:
            return None

        try:
            # Get current FastMCP context
            ctx = get_context()

            # Method 1: Check for GoogleProvider authentication token
            # The exact API may vary based on FastMCP 2.12.0 implementation
            token_info = getattr(ctx, "_auth_token", None)
            if token_info:
                # Extract email from token claims
                claims = getattr(token_info, "claims", {})
                user_email = claims.get("email")

                if user_email:
                    logger.debug(
                        f"📧 Found user email in GoogleProvider token claims: {user_email}"
                    )
                    return user_email

            # Method 2: Check FastMCP context state for user info
            # This might be set by GoogleProvider after authentication
            user_email = await ctx.get_state("authenticated_user_email")
            if user_email:
                logger.debug(
                    f"📧 Found user email in GoogleProvider context state: {user_email}"
                )
                return user_email

            # Method 3: Alternative - Check if GoogleProvider has current user info
            if hasattr(self._google_provider, "get_current_user"):
                try:
                    current_user = await self._google_provider.get_current_user()
                    if current_user and hasattr(current_user, "email"):
                        logger.debug(
                            f"📧 Found user email via GoogleProvider.get_current_user: {current_user.email}"
                        )
                        return current_user.email
                except Exception as e:
                    logger.debug(f"Could not get current user from GoogleProvider: {e}")

            return None

        except Exception as e:
            # No valid token - this means we need to authenticate
            logger.debug(
                f"🔍 GoogleProvider: No valid token ({e}), service selection needed"
            )

            # Store indication that service selection is needed
            self._set_service_selection_needed(True)

            return None

    async def _bridge_credentials_if_needed(self, user_email: str) -> None:
        """
        Bridge GoogleProvider credentials to legacy credential system if needed.

        This ensures that tools expecting legacy credentials can still work
        with GoogleProvider authentication. This is a key part of the unified
        OAuth architecture that maintains backward compatibility.

        When the user has identity-only auth (GoogleProvider) but no API credentials,
        this is detected and logged — the user will get a clear "scope upgrade"
        message when they try to use a Google API tool.

        Args:
            user_email: User's email address
        """
        try:
            # Check if user already has valid legacy credentials
            from .google_auth import get_valid_credentials

            existing_credentials = get_valid_credentials(user_email)
            if existing_credentials and not existing_credentials.expired:
                logger.debug(
                    f"✅ User {user_email} has valid API credentials, no bridging needed"
                )
                return

            # Check if this is an identity-only user (GoogleProvider without API creds)
            if self._dual_auth_bridge.needs_scope_upgrade(user_email):
                logger.info(
                    f"🔑 User {user_email} authenticated via GoogleProvider (identity-only). "
                    f"API tools will prompt for scope upgrade via start_google_auth."
                )
                return

            # If no valid legacy credentials, try to bridge from GoogleProvider
            if settings.credential_migration:
                logger.debug(
                    f"🔄 Bridging GoogleProvider credentials to legacy system for {user_email}"
                )

                # Use dual auth bridge for credential bridging
                bridged_credentials = self._dual_auth_bridge.bridge_credentials(
                    user_email, "memory"
                )
                if bridged_credentials:
                    logger.debug(
                        f"✅ Successfully bridged credentials for {user_email}"
                    )
                else:
                    logger.debug(f"⚠️ Could not bridge credentials for {user_email}")

        except Exception as e:
            logger.warning(f"⚠️ Could not bridge credentials for {user_email}: {e}")

    # CodeMode meta-tools use strict Pydantic schemas — skip user_google_email injection.
    # Actual tool names: tags, search, get_schema, execute
    _CODE_MODE_TOOLS = frozenset({"tags", "search", "get_schema", "execute"})

    async def _auto_inject_email_parameter(
        self, context: MiddlewareContext, user_email: str
    ) -> None:
        """
        Automatically inject user_google_email parameter into tool calls.

        CRITICAL FIX: Properly resolve "me"/"myself" to OAuth file email instead of "unknown".
        When user_email is None, try to load from OAuth authentication file before giving up.
        This prevents unnecessary re-authentication across different clients.

        Args:
            context: The middleware context containing the tool call
            user_email: User's email address to inject (can be None)
        """
        try:
            # Skip injection for CodeMode meta-tools (strict Pydantic schemas)
            if context.message.name in self._CODE_MODE_TOOLS:
                return

            # Standard FastMCP pattern: arguments are in context.message.arguments
            args = context.message.arguments
            if not isinstance(args, dict):
                logger.debug(f"Arguments is not a dict: {type(args)}")
                return

            # Check current value
            current_value = args.get("user_google_email")

            # CRITICAL FIX: Resolve 'me'/'myself'/None to OAuth email BEFORE injection
            final_email = user_email

            if (
                current_value in ["me", "myself"]
                or user_email is None
                or not user_email
            ):
                # Skip OAuth file fallback for API key sessions
                from .context import get_session_data

                request_id = self._get_request_id(context)
                with self._session_lock:
                    _sid = self._active_sessions.get(request_id)
                _provenance = (
                    get_session_data(_sid, SessionKey.AUTH_PROVENANCE) if _sid else None
                )

                # Try to get email from OAuth authentication file (not for API key / per-user key sessions)
                oauth_email = (
                    self._load_oauth_authentication_data()
                    if _provenance
                    not in (AuthProvenance.API_KEY, AuthProvenance.USER_API_KEY)
                    else None
                )
                if oauth_email:
                    final_email = oauth_email
                    logger.debug(
                        f"✅ Resolved 'me'/'myself'/None to OAuth email: {oauth_email}"
                    )
                else:
                    logger.debug(
                        f"⚠️ No OAuth email found - user_email remains: {final_email}"
                    )

            # Only inject if we have a real email address (not None, not "unknown")
            # FIX: explicit parentheses to avoid operator-precedence bug
            # (previously `and ... or ...` let the `or` branch bypass checks)
            if (
                final_email and current_value in ["me", "myself", None]
            ) or "user_google_email" not in args:
                if final_email:  # Double-check we have something real
                    args["user_google_email"] = final_email
                    logger.debug(f"✅ Auto-injected user_google_email={final_email}")
                else:
                    logger.debug(
                        "⚠️ No email to inject - leaving parameter unset (tool will fail clearly)"
                    )
            else:
                # user_google_email is already set to a real email — validate it
                # matches the authenticated user (skip for start_google_auth which
                # needs to accept any email to initiate authentication)
                tool_name = context.message.name

                # Allow registered secondary accounts through the dual-auth bridge
                is_secondary = (
                    current_value
                    and self._dual_auth_bridge.is_secondary_account(
                        current_value.lower().strip()
                    )
                )

                # Allow linked accounts for per-user API key sessions
                is_linked_account = False
                if current_value and final_email:
                    try:
                        from auth.user_api_keys import get_accessible_emails

                        accessible = get_accessible_emails(final_email)
                        if current_value.lower().strip() in {
                            e.lower() for e in accessible
                        }:
                            is_linked_account = True
                    except Exception:
                        pass

                if tool_name == "start_google_auth":
                    # start_google_auth must accept any email to begin auth
                    pass
                elif not final_email:
                    # Cannot determine the authenticated user — refuse to let
                    # an arbitrary email through silently.
                    from .audit import log_security_event

                    log_security_event(
                        "email_mismatch_rejected",
                        user_email=current_value,
                        details={
                            "reason": "final_email_unknown",
                            "tool": tool_name,
                        },
                    )
                    raise ValueError(
                        f"Cannot verify identity: authenticated user is unknown "
                        f"but tool '{tool_name}' was called with '{current_value}'. "
                        f"Please authenticate first using start_google_auth."
                    )
                elif current_value.lower().strip() == final_email.lower().strip():
                    # Exact match — user passed their own email explicitly, all good
                    pass
                elif is_secondary:
                    from .audit import log_security_event

                    log_security_event(
                        "email_mismatch_allowed_secondary",
                        user_email=final_email,
                        details={
                            "secondary_email": current_value,
                            "tool": tool_name,
                        },
                    )
                    logger.debug(
                        f"✅ Allowed secondary account: {current_value} "
                        f"(primary: {final_email})"
                    )
                elif is_linked_account:
                    logger.debug(
                        f"✅ Allowed linked account: {current_value} "
                        f"(key owner: {final_email})"
                    )
                elif current_value.lower().strip() != final_email.lower().strip():
                    from .audit import log_security_event

                    log_security_event(
                        "email_mismatch_rejected",
                        user_email=final_email,
                        details={
                            "requested_email": current_value,
                            "tool": tool_name,
                        },
                    )
                    raise ValueError(
                        f"Email mismatch: you are authenticated as '{final_email}' "
                        f"but tool '{tool_name}' was called with '{current_value}'. "
                        f"Use your authenticated email or 'me'/'myself' instead."
                    )
                logger.debug(f"user_google_email already set: {current_value}")

        except ValueError:
            # Re-raise email mismatch errors — these should not be silenced
            raise
        except Exception as e:
            logger.warning(f"Could not auto-inject email parameter: {e}")

    def set_google_provider(self, google_provider: Optional["GoogleProvider"]) -> None:
        """
        Set or update the GoogleProvider instance for unified authentication.

        Args:
            google_provider: GoogleProvider instance from FastMCP 2.12.0
        """
        self._google_provider = google_provider
        self._unified_auth_enabled = bool(
            google_provider and settings.enable_unified_auth
        )

        if self._unified_auth_enabled:
            logger.debug("✅ GoogleProvider updated - unified authentication enabled")
        else:
            logger.debug("⭕ GoogleProvider cleared - unified authentication disabled")

    def is_unified_auth_enabled(self) -> bool:
        """Check if unified authentication is enabled."""
        return self._unified_auth_enabled

    def _set_service_selection_needed(self, needed: bool):
        """Set flag indicating service selection is needed."""
        try:
            from .context import get_session_context_sync, store_session_data

            session_id = get_session_context_sync()
            if session_id:
                store_session_data(
                    session_id, SessionKey.SERVICE_SELECTION_NEEDED, needed
                )
                logger.debug(
                    f"Set service selection needed flag: {needed} for session {session_id}"
                )
        except Exception as e:
            logger.debug(f"Could not set service selection flag: {e}")

    def enable_service_selection(self, enabled: bool = True):
        """Enable or disable service selection interface."""
        self._enable_service_selection = enabled
        logger.debug(f"Service selection {'enabled' if enabled else 'disabled'}")

    def _extract_user_from_jwt_token(self) -> Optional[str]:
        """
        Extract user email from JWT token using FastMCP's standard pattern.

        This follows the official FastMCP example pattern:
        1. Use get_access_token() from FastMCP dependencies
        2. Extract email from token claims
        3. Return user email for automatic injection

        Returns:
            User email address if found in JWT token, None otherwise
        """
        try:
            # Follow the FastMCP pattern exactly as shown in examples
            from fastmcp.server.dependencies import get_access_token

            # MCP SDK 1.21.1 FIX: get_access_token() may fail during handshake
            try:
                access_token = get_access_token()
            except RuntimeError as ctx_error:
                if "context" in str(ctx_error).lower():
                    # Context not available yet - this is normal during handshake
                    return None
                raise

            # Check if we have token claims (GoogleProvider or JWT)
            if hasattr(access_token, "claims"):
                # Direct access to claims (GoogleProvider pattern)
                user_email = access_token.claims.get(
                    "email"
                ) or access_token.claims.get("google_email")

                # Stash Google's immutable account ID (sub) for OAuth recipient
                # key derivation.  This is non-public — only obtainable by
                # completing OAuth for the account.
                google_sub = access_token.claims.get("sub")
                if google_sub and user_email:
                    try:
                        from .context import (
                            get_session_data,
                            list_sessions,
                            store_session_data,
                        )

                        for sid in reversed(list_sessions()):
                            # Only write if not already set (avoid redundant writes per tool call)
                            if not get_session_data(sid, SessionKey.GOOGLE_SUB):
                                store_session_data(
                                    sid, SessionKey.GOOGLE_SUB, google_sub
                                )
                            break
                    except Exception:
                        pass

                if user_email:
                    logger.debug(
                        f"📧 Extracted user email from token claims: {user_email}"
                    )
                    return user_email

            # Try raw token decoding (JWT pattern)
            if hasattr(access_token, "raw_token"):
                import jwt

                # Decode without verification (already verified by FastMCP)
                claims = jwt.decode(
                    access_token.raw_token, options={"verify_signature": False}
                )
                user_email = claims.get("email") or claims.get("google_email")
                if user_email:
                    logger.debug(
                        f"📧 Extracted user email from JWT raw token: {user_email}"
                    )
                    return user_email

            # Fallback: extract from client_id/subject
            if hasattr(access_token, "client_id"):
                client_id = access_token.client_id
                if client_id and client_id.startswith("google-user-"):
                    user_email = client_id.replace("google-user-", "")
                    logger.debug(
                        f"📧 Extracted user email from client_id: {user_email}"
                    )
                    return user_email

            return None

        except Exception as e:
            # This is expected if no token is present
            logger.debug(f"No JWT/token authentication available: {e}")
            return None

    def _detect_auth_provenance(self) -> Optional[str]:
        """Detect the authentication method for the current request.

        Returns:
            "api_key" for shared MCP_API_KEY sessions
            "user_api_key" for per-user API key sessions
            None for normal OAuth sessions
        """
        try:
            from fastmcp.server.dependencies import get_access_token

            try:
                access_token = get_access_token()
            except RuntimeError:
                return None

            if hasattr(access_token, "claims"):
                auth_method = access_token.claims.get("auth_method")
                if auth_method == AuthProvenance.API_KEY:
                    logger.debug("🔑 Detected API key session (shared MCP_API_KEY)")
                    return AuthProvenance.API_KEY
                if auth_method == AuthProvenance.USER_API_KEY:
                    logger.debug("🔑 Detected per-user API key session")
                    return AuthProvenance.USER_API_KEY

            return None
        except Exception:
            return None

    def _load_oauth_authentication_data(self) -> Optional[str]:
        """
        Load OAuth authentication data from persistent storage.

        This checks for OAuth authentication data stored by the OAuth endpoint
        when authentication completes outside of the FastMCP request context.

        Returns:
            User email address if found in OAuth authentication file, None otherwise
        """
        try:
            import json
            from datetime import datetime, timedelta
            from pathlib import Path

            oauth_data_path = (
                Path(settings.credentials_dir) / ".oauth_authentication.json"
            )

            if not oauth_data_path.exists():
                logger.debug("No OAuth authentication file found")
                return None

            with open(oauth_data_path, "r") as f:
                oauth_data = json.load(f)

            authenticated_email = oauth_data.get("authenticated_email")
            authenticated_at_str = oauth_data.get("authenticated_at")

            if not authenticated_email:
                logger.debug("OAuth authentication file exists but no email found")
                return None

            # Check if authentication is still recent (within 24 hours)
            if authenticated_at_str:
                try:
                    authenticated_at = datetime.fromisoformat(authenticated_at_str)
                    age = datetime.now() - authenticated_at
                    if age > timedelta(hours=24):
                        logger.warning(
                            f"OAuth authentication is stale (age: {age}), may need re-authentication"
                        )
                        # Still return it but warn - credentials might need refresh
                except Exception as e:
                    logger.debug(f"Could not parse authentication timestamp: {e}")

            logger.debug(
                f"📂 Loaded OAuth authentication data for: {authenticated_email}"
            )
            return authenticated_email

        except Exception as e:
            logger.debug(f"Could not load OAuth authentication data: {e}")
            return None


def setup_oauth_coordination(mcp, google_auth_provider):
    """
    Setup OAuth coordination between modern GoogleProvider and legacy system.

    CRITICAL FIX: The "invalid transaction ID" error occurs because FastMCP 2.12.x
    GoogleProvider has its own built-in OAuth proxy that conflicts with custom endpoints.

    Solution: Let GoogleProvider handle OAuth entirely when active.

    Args:
        mcp: FastMCP application instance
        google_auth_provider: Modern GoogleProvider instance (or None)
    """

    if google_auth_provider:
        logger.info(
            "🔄 GoogleProvider active - disabling conflicting custom OAuth endpoints"
        )
        logger.info(
            "  CRITICAL: FastMCP 2.12.x GoogleProvider has built-in OAuth proxy"
        )
        logger.info("  SOLUTION: Let GoogleProvider handle OAuth flow entirely")
        logger.info("  BENEFIT: No transaction ID conflicts, enhanced security")

        # Only provide minimal discovery endpoint for MCP Inspector
        @mcp.custom_route(
            "/.well-known/oauth-authorization-server/mcp", methods=["GET", "OPTIONS"]
        )
        async def oauth_authorization_server_mcp(request):
            """Minimal MCP-specific OAuth authorization server endpoint."""
            from starlette.responses import JSONResponse, Response

            from config.settings import settings

            if request.method == "OPTIONS":
                return Response(
                    status_code=200,
                    headers={
                        "Access-Control-Allow-Origin": "*",
                        "Access-Control-Allow-Methods": "GET, OPTIONS",
                        "Access-Control-Allow-Headers": "Content-Type, Authorization",
                    },
                )

            # Return metadata pointing to GoogleProvider's endpoints
            metadata = {
                "issuer": "https://accounts.google.com",
                "authorization_endpoint": "https://accounts.google.com/o/oauth2/v2/auth",
                "token_endpoint": "https://oauth2.googleapis.com/token",
                "jwks_uri": "https://www.googleapis.com/oauth2/v3/certs",
                "response_types_supported": ["code"],
                "grant_types_supported": ["authorization_code", "refresh_token"],
                "code_challenge_methods_supported": ["S256"],
                "subject_types_supported": ["public"],
                "id_token_signing_alg_values_supported": ["RS256"],
                "userinfo_endpoint": "https://www.googleapis.com/oauth2/v1/userinfo",
                # Point to GoogleProvider's built-in registration
                "registration_endpoint": f"{settings.base_url}/auth/register",
            }

            return JSONResponse(
                content=metadata,
                headers={
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "GET, OPTIONS",
                    "Access-Control-Allow-Headers": "Content-Type, Authorization",
                },
            )

        logger.info("✅ OAuth coordination: Modern GoogleProvider mode")
        logger.info("  🚫 Custom OAuth endpoints: DISABLED (prevents conflicts)")
        logger.info("  ✅ GoogleProvider OAuth proxy: ACTIVE")
        logger.info("  ✅ Transaction ID management: FastMCP built-in")

    else:
        logger.info("🔄 No GoogleProvider - using full legacy OAuth system")


def log_oauth_transition_status(google_auth_provider):
    """Log the current OAuth transition status."""

    if google_auth_provider:
        logger.info("📊 OAuth Transition Status: MODERN")
        logger.info("  🏗️ Architecture: FastMCP 2.12.x built-in OAuth proxy")
        logger.info("  🔐 Security: Enhanced with automatic PKCE")
        logger.info("  📋 Scope Management: ScopeRegistry integration")
        logger.info("  🎯 Token Validation: Google tokeninfo API")
        logger.info("  ⚠️ Note: Custom OAuth endpoints disabled to prevent conflicts")
    else:
        logger.info("📊 OAuth Transition Status: LEGACY")
        logger.info("  🔧 Architecture: Custom OAuth proxy and endpoints")
        logger.info("  📁 Credentials: File-based storage")
        logger.info("  📋 Scope Management: Manual ScopeRegistry integration")


def create_enhanced_auth_middleware(
    storage_mode: CredentialStorageMode = CredentialStorageMode.FILE_PLAINTEXT,
    encryption_key: Optional[str] = None,
    google_provider: Optional["GoogleProvider"] = None,
) -> AuthMiddleware:
    """
    Factory function to create AuthMiddleware with unified authentication support.

    This factory creates the enhanced AuthMiddleware that bridges FastMCP 2.12.0
    GoogleProvider with existing tool architecture, implementing the unified OAuth design.

    Args:
        storage_mode: Credential storage mode
        encryption_key: Optional encryption key
        google_provider: GoogleProvider instance for unified auth

    Returns:
        Configured AuthMiddleware with unified authentication capabilities
    """
    middleware = AuthMiddleware(
        storage_mode=storage_mode,
        encryption_key=encryption_key,
        google_provider=google_provider,
    )

    if middleware.is_unified_auth_enabled():
        logger.debug("🎯 Unified OAuth Architecture Active:")
        logger.debug("  ✅ FastMCP GoogleProvider → Legacy Tool Bridge")
        logger.debug("  ✅ Automatic user context injection")
        logger.debug("  ✅ Backward compatibility maintained")
        logger.debug("  ✅ No tool signature changes required")
        logger.debug("  🔄 Phase 1 migration successfully implemented")

    # Log OAuth coordination status
    log_oauth_transition_status(google_provider)

    return middleware
