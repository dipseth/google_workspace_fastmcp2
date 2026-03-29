"""SSO GoogleProvider — subclasses FastMCP's GoogleProvider to intercept OAuth
token exchange and store Google API credentials automatically.

Includes all monkey-patches applied to the provider instance:
- CIMD redirect URI fix (dynamic localhost ports)
- API key + per-user key authentication (admin key, user keys, OAuth fallback)
- Stale-header / grace-period fallback for misconfigured clients
- Auto-registration of unknown OAuth clients (proxy DCR)
- Metadata patch: advertise ``token_endpoint_auth_methods = ["none"]``
"""

import logging as _logging
import os

from config.enhanced_logging import setup_logger

logger = setup_logger()

# Module-level mutable state for rate limiting and stale-header fallback.
# Encapsulated here (was previously inline closures in server.py).
_failed_auth_attempts: dict[str, list[float]] = {}
_RATE_LIMIT_WINDOW = 60.0  # seconds
_RATE_LIMIT_MAX = 15  # max failures per window (generous for refresh loops)
_MAX_TRACKED_PREFIXES = 1000  # cap to prevent memory growth from brute-force
_last_stale_warn: dict[str, float] = {}

# Grace period / stale-header fallback cache
_latest_issued_jwt: list = [None, 0.0]  # [jwt_string, issued_at]
_GRACE_PERIOD_SECONDS = 30.0
_stale_token_aliases: set = set()


def _clear_auth_rate_limits():
    """Clear all rate limit state — called after successful token issuance."""
    _failed_auth_attempts.clear()
    _last_stale_warn.clear()


def create_sso_google_provider(
    client_id: str,
    client_secret: str,
    base_url: str,
    comprehensive_scopes: list[str],
    mcp_api_key: str,
    settings,
):
    """Build a fully-patched SSOGoogleProvider instance.

    Applies:
    1. SSOGoogleProvider class (intercepts token exchange → saves Google creds)
    2. CIMD redirect URI fix (dynamic localhost ports)
    3. API key + per-user key authentication layer
    4. Auto-registration of unknown OAuth clients
    5. Metadata patch (token_endpoint_auth_methods includes "none")
    6. DEBUG logging for OAuth flow tracing

    Returns the configured GoogleProvider instance, or None on failure.
    """
    from fastmcp.server.auth.providers.google import (
        GoogleProvider,
    )

    class SSOGoogleProvider(GoogleProvider):
        """GoogleProvider that saves Google API credentials on first auth."""

        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            # Override the token verifier's required_scopes so load_access_token
            # doesn't reject tokens missing any of the 30+ API scopes.
            if hasattr(self, "_token_validator") and hasattr(
                self._token_validator, "required_scopes"
            ):
                self._token_validator.required_scopes = ["openid"]

        async def exchange_authorization_code(self, client, authorization_code):
            """Intercept token exchange to save Google API credentials."""
            code_model = await self._code_store.get(key=authorization_code.code)
            idp_tokens = code_model.idp_tokens if code_model else None

            result = await super().exchange_authorization_code(
                client, authorization_code
            )

            # Cache the newly-issued JWT for stale-header fallback.
            if result and hasattr(result, "access_token") and result.access_token:
                import time as _t

                _latest_issued_jwt[0] = result.access_token
                _latest_issued_jwt[1] = _t.time()
                logger.debug("🔑 Cached latest JWT for stale-header fallback")

            # Now save the Google tokens as API credentials
            if idp_tokens:
                try:
                    await self._save_google_credentials(idp_tokens)
                except Exception as e:
                    logger.warning(
                        f"⚠️ SSO credential save failed (auth still works): {e}"
                    )

            return result

        async def exchange_refresh_token(self, client, refresh_token, scopes):
            """Intercept refresh to update stale-header fallback cache."""
            result = await super().exchange_refresh_token(
                client, refresh_token, scopes
            )
            if result and hasattr(result, "access_token") and result.access_token:
                import time as _t

                _latest_issued_jwt[0] = result.access_token
                _latest_issued_jwt[1] = _t.time()
                logger.debug(
                    "🔑 Refresh: updated latest JWT for stale-header fallback"
                )
            return result

        async def _save_google_credentials(self, idp_tokens: dict):
            """Convert raw Google tokens to Credentials and save them."""
            from google.oauth2.credentials import Credentials

            from auth.google_auth import _save_credentials

            access_token = idp_tokens.get("access_token")
            refresh_token = idp_tokens.get("refresh_token")
            id_token_str = idp_tokens.get("id_token")

            if not access_token:
                logger.warning("SSO: No access_token in idp_tokens, skipping save")
                return

            # Determine user email from the id_token or userinfo
            user_email = None
            if id_token_str:
                try:
                    import base64
                    import json

                    parts = id_token_str.split(".")
                    if len(parts) >= 2:
                        payload_b64 = parts[1] + "=" * (4 - len(parts[1]) % 4)
                        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
                        user_email = payload.get("email")
                        self._google_sub = payload.get("sub")
                except Exception as e:
                    logger.debug(f"SSO: Could not decode id_token: {e}")

            if not user_email:
                try:
                    import httpx

                    async with httpx.AsyncClient(timeout=10) as http_client:
                        resp = await http_client.get(
                            "https://www.googleapis.com/oauth2/v2/userinfo",
                            headers={"Authorization": f"Bearer {access_token}"},
                        )
                        if resp.status_code == 200:
                            userinfo = resp.json()
                            user_email = userinfo.get("email")
                            self._google_sub = userinfo.get("id")
                except Exception as e:
                    logger.warning(f"SSO: Could not fetch userinfo: {e}")

            if not user_email:
                logger.warning("SSO: Could not determine user email, skipping save")
                return

            credentials = Credentials(
                token=access_token,
                refresh_token=refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=client_id,
                client_secret=client_secret,
                scopes=comprehensive_scopes,
            )
            credentials._google_sub = getattr(self, "_google_sub", None)

            _save_credentials(user_email, credentials)
            user_api_key = getattr(credentials, "_user_api_key", None)
            from config.enhanced_logging import redact_email

            _redacted = redact_email(user_email)
            if user_api_key:
                logger.info(
                    f"🔑 SSO: Per-user API key generated for {_redacted} "
                    f"(key will be available via check_drive_auth)"
                )
            logger.info(
                f"✅ SSO: Google API credentials saved for {_redacted} "
                f"(refresh_token: {'yes' if refresh_token else 'no'}, "
                f"scopes: {len(comprehensive_scopes)})"
            )
            _clear_auth_rate_limits()

    # --- Instantiate the provider ---
    provider = SSOGoogleProvider(
        client_id=client_id,
        client_secret=client_secret,
        base_url=base_url,
        required_scopes=comprehensive_scopes,
        redirect_path="/auth/callback",
        require_authorization_consent=False,
    )

    # --- CIMD Redirect URI Fix ---
    _cimd_mgr = getattr(provider, "_cimd_manager", None)
    if _cimd_mgr is not None:
        _original_get_client = _cimd_mgr.get_client
        _localhost_wildcards = [
            "http://localhost:*/callback",
            "http://127.0.0.1:*/callback",
        ]
        _in_patched_get_client = [False]

        async def _patched_get_client(client_id_url: str):
            if _in_patched_get_client[0]:
                _cimd_mgr.get_client = _original_get_client
                try:
                    return await _original_get_client(client_id_url)
                finally:
                    _cimd_mgr.get_client = _patched_get_client
            _in_patched_get_client[0] = True
            try:
                client = await _original_get_client(client_id_url)
            finally:
                _in_patched_get_client[0] = False
            if client and client.cimd_document:
                existing = list(client.cimd_document.redirect_uris or [])
                for pattern in _localhost_wildcards:
                    if pattern not in existing:
                        existing.append(pattern)
                client.cimd_document.redirect_uris = existing
            return client

        _cimd_mgr.get_client = _patched_get_client

    # --- API Key + Per-User Key Authentication ---
    from fastmcp.server.auth.auth import AccessToken as _FastMCPAccessToken

    _original_load_access_token = provider.load_access_token

    async def _load_access_token_with_api_key(token: str):
        """Check for admin key / per-user key before delegating to OAuth."""
        import hmac
        import time as _time

        token_prefix = token[:8]
        now = _time.time()
        attempts = _failed_auth_attempts.get(token_prefix, [])
        attempts = [t for t in attempts if now - t < _RATE_LIMIT_WINDOW]
        if attempts:
            _failed_auth_attempts[token_prefix] = attempts
        elif token_prefix in _failed_auth_attempts:
            del _failed_auth_attempts[token_prefix]
        if len(attempts) >= _RATE_LIMIT_MAX:
            last_warn = _last_stale_warn.get(token_prefix, 0)
            if now - last_warn > 30.0:
                logger.warning(
                    f"🚫 Rate limit exceeded for auth attempts "
                    f"(prefix={token_prefix}..., {len(attempts)} failures in "
                    f"{_RATE_LIMIT_WINDOW}s window). Client may be sending a "
                    f"stale cached token — client should clear MCP auth cache "
                    f"and re-authenticate."
                )
                _last_stale_warn[token_prefix] = now
            return None

        from auth.types import AuthProvenance

        # 1. Shared admin API key
        if mcp_api_key and hmac.compare_digest(token, mcp_api_key):
            logger.debug("🔑 Admin API key authentication — bypassing OAuth")
            return _FastMCPAccessToken(
                token=token,
                client_id="api-key-client",
                scopes=comprehensive_scopes,
                expires_at=int(_time.time()) + 86400,
                claims={
                    "sub": "api-key-user",
                    "auth_method": AuthProvenance.API_KEY,
                },
            )

        # 2. Per-user API key
        from auth.user_api_keys import lookup_key

        user_email = lookup_key(token)
        if user_email:
            from config.enhanced_logging import redact_email as _redact

            logger.debug(f"🔑 Per-user API key matched: {_redact(user_email)}")
            return _FastMCPAccessToken(
                token=token,
                client_id=f"user-key-{user_email}",
                scopes=comprehensive_scopes,
                expires_at=int(_time.time()) + 86400,
                claims={
                    "sub": user_email,
                    "email": user_email,
                    "auth_method": AuthProvenance.USER_API_KEY,
                },
            )

        # 3. Normal OAuth token validation (FastMCP JWT)
        logger.debug(f"🔍 load_access_token called, token prefix: {token[:8]}...")
        result = await _original_load_access_token(token)
        if result is not None:
            logger.info(
                f"✅ load_access_token succeeded: client={result.client_id}, scopes={result.scopes}"
            )
            return result

        # 4. Fallback: try validating as a raw Google access token
        if (
            ("." not in token[:40] or not token.startswith("eyJ"))
            and token_prefix not in _stale_token_aliases
        ):
            logger.info(
                "🔄 Token is not a FastMCP JWT — trying Google tokeninfo fallback..."
            )
            try:
                import httpx as _httpx

                async with _httpx.AsyncClient(timeout=10) as _http:
                    _resp = await _http.get(
                        "https://www.googleapis.com/oauth2/v1/tokeninfo",
                        params={"access_token": token},
                    )
                if _resp.status_code == 200:
                    _info = _resp.json()
                    _email = _info.get("email")
                    _expires_in = int(_info.get("expires_in", 0))
                    if _email and _expires_in > 0:
                        from config.enhanced_logging import redact_email as _re

                        logger.info(
                            f"✅ Google tokeninfo fallback succeeded: {_re(_email)} "
                            f"(expires_in={_expires_in}s)"
                        )
                        return _FastMCPAccessToken(
                            token=token,
                            client_id=f"google-tokeninfo-{_email}",
                            scopes=comprehensive_scopes,
                            expires_at=int(_time.time()) + _expires_in,
                            claims={
                                "sub": _email,
                                "email": _email,
                                "auth_method": AuthProvenance.USER_API_KEY,
                            },
                        )
                    else:
                        logger.debug(
                            f"Google tokeninfo returned no email or token expired "
                            f"(email={_email}, expires_in={_expires_in})"
                        )
                else:
                    logger.info(
                        f"🔄 Google tokeninfo fallback rejected: HTTP {_resp.status_code} "
                        f"— token is not a valid Google access token either. "
                        f"Client is likely sending a stale/expired cached token."
                    )
            except Exception as _e:
                logger.debug(f"Google tokeninfo fallback error: {_e}")

        # 5. Stale-header fallback
        if not token.startswith("eyJ") and _latest_issued_jwt[0]:
            _grace_jwt = _latest_issued_jwt[0]
            _grace_ts = _latest_issued_jwt[1]
            _JWT_MAX_AGE = 3700.0
            if now - _grace_ts > _JWT_MAX_AGE:
                _latest_issued_jwt[0] = None
                _latest_issued_jwt[1] = 0.0
                _stale_token_aliases.clear()
                logger.debug(
                    "🧹 Cleared expired JWT from stale-header fallback cache"
                )
            else:
                _is_known_stale = token_prefix in _stale_token_aliases
                _in_grace_window = now - _grace_ts <= _GRACE_PERIOD_SECONDS
                if _is_known_stale or _in_grace_window:
                    _grace_result = await _original_load_access_token(_grace_jwt)
                    if _grace_result is not None:
                        if not _is_known_stale:
                            logger.warning(
                                f"🔄 STALE HEADER FALLBACK: client sent "
                                f"non-JWT token (prefix={token_prefix}...) "
                                f"but a valid JWT was issued "
                                f"{now - _grace_ts:.1f}s ago. Using the "
                                f"fresh JWT. FIX: remove the hardcoded "
                                f"'Authorization' header from the client's "
                                f"MCP server config — OAuth handles auth "
                                f"automatically."
                            )
                            _stale_token_aliases.add(token_prefix)
                        return _grace_result
                    elif _is_known_stale:
                        _latest_issued_jwt[0] = None
                        _latest_issued_jwt[1] = 0.0
                        _stale_token_aliases.discard(token_prefix)

        # Detect repeated stale token
        prior_count = len(attempts)
        if prior_count >= 3:
            if prior_count == 3:
                logger.warning(
                    f"⚠️ Token prefix {token_prefix}... has failed {prior_count + 1} "
                    f"times — client appears stuck sending a stale cached token. "
                    f"Token is not a JWT (no 'eyJ' prefix), not an API key, and "
                    f"not a valid Google access token. Check if the client's MCP "
                    f"config has a hardcoded 'Authorization' header that should "
                    f"be removed (OAuth handles auth automatically)."
                )
        else:
            logger.warning(
                f"⚠️ load_access_token returned None for token: {token[:8]}..."
            )
        _failed_auth_attempts.setdefault(token_prefix, []).append(now)
        if len(_failed_auth_attempts) > _MAX_TRACKED_PREFIXES:
            oldest_key = next(iter(_failed_auth_attempts))
            del _failed_auth_attempts[oldest_key]
        return None

    provider.load_access_token = _load_access_token_with_api_key
    if mcp_api_key:
        logger.info("  🔑 Token auth: admin key + per-user keys + OAuth")
    else:
        logger.info("  🔑 Token auth: per-user keys + OAuth (no admin key)")

    # --- Auto-register unknown clients ---
    _original_provider_get_client = provider.get_client

    async def _get_client_with_auto_register(client_id_str: str):
        """Auto-register unknown clients instead of rejecting them."""
        client = await _original_provider_get_client(client_id_str)
        if client is not None:
            return client

        logger.info(f"🔧 Auto-registering unknown client: {client_id_str[:30]}...")
        try:
            from mcp.shared.auth import OAuthClientInformationFull

            auto_client = OAuthClientInformationFull(
                client_id=client_id_str,
                client_secret=None,
                redirect_uris=["http://localhost"],
                grant_types=["authorization_code", "refresh_token"],
                response_types=["code"],
                token_endpoint_auth_method="none",
                scope="openid email profile",
                client_name=f"Auto-registered ({client_id_str[:20]}...)",
            )
            await provider.register_client(auto_client)
            logger.info(f"✅ Auto-registered client: {client_id_str[:30]}...")
            return await _original_provider_get_client(client_id_str)
        except Exception as e:
            logger.warning(
                f"⚠️ Auto-registration failed for {client_id_str[:30]}...: {e}"
            )
            return None

    provider.get_client = _get_client_with_auto_register

    # --- Metadata patch: advertise token_endpoint_auth_method="none" ---
    import mcp.server.auth.routes as _auth_routes

    _original_build_metadata = _auth_routes.build_metadata

    def _patched_build_metadata(*args, **kwargs):
        metadata = _original_build_metadata(*args, **kwargs)
        if metadata.token_endpoint_auth_methods_supported:
            if "none" not in metadata.token_endpoint_auth_methods_supported:
                metadata.token_endpoint_auth_methods_supported.append("none")
        else:
            metadata.token_endpoint_auth_methods_supported = ["none"]
        return metadata

    _auth_routes.build_metadata = _patched_build_metadata
    try:
        import fastmcp.server.auth.oauth_proxy.proxy as _proxy_module

        _proxy_module.build_metadata = _patched_build_metadata
    except (ImportError, AttributeError):
        pass
    logger.info(
        '  🔓 Metadata patched: token_endpoint_auth_methods includes "none"'
    )

    # --- Enable DEBUG logging for OAuth flow tracing ---
    for _oauth_logger_name in [
        "fastmcp.server.auth.oauth_proxy.proxy",
        "fastmcp.server.auth.providers.google",
        "mcp.server.auth.handlers.token",
        "mcp.server.auth.handlers.authorize",
    ]:
        _logging.getLogger(_oauth_logger_name).setLevel(_logging.DEBUG)

    logger.info("✅ GoogleProvider configured for OAuth 2.1 (MCP protocol auth)")
    logger.info(f"  🌐 Base URL: {base_url}")
    logger.info("  🔐 PKCE: Automatic (S256)")
    logger.info("  📋 DCR: Built-in (RFC 7591)")
    logger.info("  🔍 Discovery: Auto-registered (RFC 9728 + RFC 8414)")
    logger.info("  🎯 Callback: /auth/callback")
    logger.info("  🔓 Auto-register: Unknown clients proxied automatically")
    logger.info("  ⚡ Consent page: DISABLED (Google provides its own)")
    logger.info("  🐛 OAuth DEBUG logging: ENABLED")
    logger.info("  ✅ Compatible with: Claude.ai, Claude Desktop, MCP Inspector")

    return provider
