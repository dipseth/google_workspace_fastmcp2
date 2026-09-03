"""Per-service OAuth scopes on the access token, and the Photos scope step-up.

Google refuses to put Photos Library scopes in the same authorization request
as Workspace scopes, so Photos is consented separately and its credential
lives in its own token group (``credentials/token_groups/photos/``). Until
3.0.0 the access token this server minted always claimed the comprehensive
scope list, so nothing could tell a caller that Photos in particular was
missing; the Photos tools failed deep inside the API client and the only way
back was the generic service-selection page, which does not preselect Photos.

Now:

- ``scopes_for_principal`` puts the Photos scopes on a token only once the
  Photos credential exists for that email (the shared admin key always carries
  them: it addresses arbitrary accounts by argument). Every mint site in
  ``auth/sso_google_provider.py`` uses it, and the OAuth JWT's verified claims
  are widened the same way on each ``load_access_token``.
- ``ScopeStepUpMiddleware`` checks, on ``tools/call`` only, that a tool tagged
  ``photos`` is called with those scopes. A shortfall is an
  ``InsufficientScopeError`` naming exactly the missing scopes — the same error
  FastMCP's ``AuthMiddleware(auth=restrict_tag(...))`` raises — but instead of
  letting it reach the client as a bare JSON-RPC error (4.0.1 has no HTTP
  ``insufficient_scope`` challenge for a tool call), the middleware answers with
  the existing OAuth elicitation from ``tools/elicitation.py`` carrying a
  Photos-only authorize link: url-mode ``InputRequiredResult`` for 2026-07-28
  clients, a pushed ``elicitation/create`` for handshake clients, the link in
  the error text for clients with no elicitation. On the next call the token is
  loaded again, finds the credential, and the tool runs.

Why not FastMCP's ``AuthMiddleware`` itself: it also filters ``tools/list`` by
the same check, which would hide the very tools whose call triggers the
step-up, so a client could never ask for Photos in the first place.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

from fastmcp.exceptions import InsufficientScopeError, ToolError
from fastmcp.server.middleware import Middleware, MiddlewareContext

from config.enhanced_logging import redact_email, setup_logger

logger = setup_logger()

PHOTOS_TAG = "photos"
PHOTOS_TOKEN_GROUP = "photos"
PHOTOS_SCOPE_GROUP = "photos_basic"
STEP_UP_STATE_PREFIX = "scope_step_up:photos:"


def photos_required_scopes() -> list[str]:
    """The scope URLs a Photos tool needs (what the Photos consent grants)."""
    from auth.scope_registry import ScopeRegistry

    scopes = ScopeRegistry.resolve_scope_group(PHOTOS_SCOPE_GROUP)
    return [s for s in scopes if "photoslibrary" in s]


def has_photos_credentials(email: Optional[str]) -> bool:
    """Whether a Photos-group credential is stored for ``email`` (plain or encrypted)."""
    if not email:
        return False
    try:
        from auth.google_auth import _get_credentials_path

        path = _get_credentials_path(email, PHOTOS_TOKEN_GROUP)
    except Exception:
        return False
    return path.exists() or path.with_suffix(".enc").exists()


def scopes_for_principal(
    email: Optional[str], base_scopes: Iterable[str], *, admin: bool = False
) -> list[str]:
    """Token scopes: ``base_scopes`` plus Photos once its credential exists.

    ``admin`` (the shared key) always carries Photos: it acts on accounts named
    by argument, so a per-email check has nothing to key on.
    """
    scopes = list(dict.fromkeys(base_scopes))
    if admin or has_photos_credentials(email):
        for scope in photos_required_scopes():
            if scope not in scopes:
                scopes.append(scope)
    return scopes


def missing_photos_scopes(token: Any) -> list[str]:
    """Photos scopes the token lacks; empty when it has them all."""
    granted = set(getattr(token, "scopes", None) or [])
    return [s for s in photos_required_scopes() if s not in granted]


async def _photos_auth_url(email: str) -> str:
    """A Google authorize URL for the Photos token group only (no selection page)."""
    from auth.google_auth import initiate_oauth_flow

    return await initiate_oauth_flow(
        user_email=email,
        service_name="Google Photos",
        selected_services=[PHOTOS_TAG],
        show_service_selection=False,
        use_pkce=True,
        auth_method="pkce_file",
    )


def _link_error(email: str, url: str) -> ToolError:
    return ToolError(
        f"Google Photos is not authorized for {email} yet. Open this link, "
        f"grant Photos access, then call the tool again:\n{url}"
    )


class ScopeStepUpMiddleware(Middleware):
    """Turn a Photos scope shortfall on ``tools/call`` into an OAuth step-up."""

    async def on_call_tool(self, context: MiddlewareContext, call_next):
        tool_name = getattr(context.message, "name", None)
        if not tool_name:
            return await call_next(context)

        from fastmcp.server.dependencies import get_access_token

        from auth.user_state import principal_email

        try:
            token = get_access_token()
        except Exception:
            token = None
        if token is None:
            # No auth on this connection (stdio, legacy no-auth): nothing to step up.
            return await call_next(context)

        if not await self._is_photos_tool(context, tool_name):
            return await call_next(context)

        missing = missing_photos_scopes(token)
        if not missing:
            return await call_next(context)

        email = principal_email()
        error = InsufficientScopeError(
            missing,
            message=(
                f"Authorization failed for tool '{tool_name}': insufficient scope "
                f"(required: {', '.join(missing)})"
            ),
        )
        if not email:
            # The shared key already carries Photos; anything else without an
            # email has no account to authorize for.
            raise ToolError(str(error))

        from tools.elicitation import answered_oauth_prompt, prompt_for_oauth

        try:
            url = await _photos_auth_url(email)
        except Exception as exc:
            logger.warning(f"Could not build Photos authorize URL: {exc}")
            raise ToolError(str(error)) from exc

        answer = answered_oauth_prompt()
        if answer is not None:
            # Re-run after the prompt. The token was loaded fresh for this
            # request and still lacks Photos, so the consent did not land
            # (tab closed, wrong account). Say so with the link; never loop.
            action = getattr(answer, "action", None)
            if action == "accept":
                raise ToolError(
                    f"Photos authorization for {email} did not complete "
                    f"(no Photos credential was stored). Try the link again:\n{url}"
                )
            raise ToolError(
                f"Photos authorization for {email} was "
                f"{action or 'cancelled'}; the tool needs it to run."
            )

        logger.info(
            f"🔐 Photos scope step-up for {redact_email(email)} on '{tool_name}' "
            f"(missing {len(missing)} scopes)"
        )
        prompt = await prompt_for_oauth(
            message=(
                f"Authorize Google Photos access for {email}. You will grant "
                f"Photos separately from your Workspace consent, then return "
                f"here — no need to repeat your request."
            ),
            url=url,
            request_state=f"{STEP_UP_STATE_PREFIX}{email}",
        )
        if prompt.outcome == "suspended":
            # A tool body returns the bare ``InputRequiredResult`` and FastMCP
            # wraps it; a middleware return value skips that step, so wrap here.
            # The wire handler reads ``.input_required`` off the wrapper, and
            # Code Mode's bridge recognizes it as an ask rather than content.
            from fastmcp.tools.base import InputRequiredToolResult

            return InputRequiredToolResult(prompt.suspend)
        if prompt.outcome == "completed":
            # Handshake-era client walked the user through it inline. The
            # token object for this request predates the consent; widen it
            # from the credential that now exists and run the tool.
            if has_photos_credentials(email):
                token.scopes = scopes_for_principal(email, token.scopes)
                return await call_next(context)
            raise ToolError(
                f"Photos authorization for {email} did not complete "
                f"(no Photos credential was stored). Try the link again:\n{url}"
            )
        if prompt.outcome == "declined":
            raise ToolError(
                f"Photos authorization for {email} was "
                f"{prompt.action or 'cancelled'}; the tool needs it to run."
            )
        raise _link_error(email, url)

    @staticmethod
    async def _is_photos_tool(context: MiddlewareContext, tool_name: str) -> bool:
        try:
            server = context.fastmcp_context.fastmcp
            tool = await server.get_tool(tool_name)
        except Exception:
            return False
        if tool is None:
            return False
        return PHOTOS_TAG in (getattr(tool, "tags", None) or set())


__all__ = [
    "PHOTOS_TAG",
    "ScopeStepUpMiddleware",
    "has_photos_credentials",
    "missing_photos_scopes",
    "photos_required_scopes",
    "scopes_for_principal",
]
