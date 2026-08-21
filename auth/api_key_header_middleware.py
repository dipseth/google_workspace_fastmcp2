"""ASGI middleware: accept the per-user MCP API key via an ``X-API-Key`` header.

Some MCP clients (e.g. Claude Desktop's custom-connector UI) only allow an
approved list of custom header names and do not let users set
``Authorization`` directly. This middleware lets those clients send the minted
key in an alternate header; it is rewritten to ``Authorization: Bearer <key>``
before the request reaches FastMCP's bearer auth, so every existing auth path
keeps working unchanged.

Accepted header names (first match wins), overridable via the
``MCP_API_KEY_HEADERS`` env var (comma-separated):

    x-api-key, x-apikey, x-api-token, x-auth-token, x-access-token, x-token

An existing ``Authorization`` header always takes precedence.
"""

from __future__ import annotations

import os

from starlette.types import ASGIApp, Receive, Scope, Send

DEFAULT_API_KEY_HEADERS = (
    "x-api-key",
    "x-apikey",
    "x-api-token",
    "x-auth-token",
    "x-access-token",
    "x-token",
)


def _configured_headers() -> tuple[bytes, ...]:
    raw = os.getenv("MCP_API_KEY_HEADERS", "")
    names = [h.strip().lower() for h in raw.split(",") if h.strip()] or list(
        DEFAULT_API_KEY_HEADERS
    )
    return tuple(n.encode("latin-1") for n in names)


class ApiKeyHeaderMiddleware:
    """Promote an ``X-API-Key``-style header to ``Authorization: Bearer``."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self._names = _configured_headers()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers: list[tuple[bytes, bytes]] = list(scope.get("headers", []))
        has_authz = any(k.lower() == b"authorization" for k, _ in headers)
        if not has_authz:
            for name in self._names:
                for k, v in headers:
                    if k.lower() == name and v.strip():
                        token = v.strip()
                        if not token.lower().startswith(b"bearer "):
                            token = b"Bearer " + token
                        headers.append((b"authorization", token))
                        scope = {**scope, "headers": headers}
                        break
                else:
                    continue
                break

        await self.app(scope, receive, send)
