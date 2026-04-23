"""Dual OAuth Provider — combines Google and GitHub OAuth behind a single endpoint.

Wraps two OAuthProxy-based providers (Google + GitHub) behind a single set of
MCP-compliant OAuth endpoints. Shows a provider selection page instead of the
standard consent page, letting users choose how to authenticate.

The provider selection page replaces the standard consent screen and redirects
the user to the chosen upstream provider's authorization flow.
"""

from __future__ import annotations

import secrets
import time
from typing import Any
from urllib.parse import urlencode

from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse
from starlette.routing import Route

from config.enhanced_logging import redact_email, setup_logger

logger = setup_logger()

# ─── Provider Selection HTML Template ─────────────────────────────────────────

PROVIDER_SELECT_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Sign In — {server_name}</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: #0a0a0a;
    color: #e5e5e5;
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
  }}
  .card {{
    background: #1a1a1a;
    border: 1px solid #333;
    border-radius: 16px;
    padding: 40px;
    max-width: 420px;
    width: 100%;
    text-align: center;
  }}
  .logo {{ font-size: 48px; margin-bottom: 16px; }}
  h1 {{ font-size: 22px; margin-bottom: 8px; color: #fff; }}
  .subtitle {{ color: #888; font-size: 14px; margin-bottom: 32px; }}
  .btn {{
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 12px;
    width: 100%;
    padding: 14px 20px;
    border: 1px solid #333;
    border-radius: 10px;
    background: #222;
    color: #fff;
    font-size: 15px;
    font-weight: 500;
    cursor: pointer;
    text-decoration: none;
    transition: background 0.2s, border-color 0.2s;
    margin-bottom: 12px;
  }}
  .btn:hover {{ background: #2a2a2a; border-color: #555; }}
  .btn-google {{ border-color: #4285f4; }}
  .btn-google:hover {{ background: #1a237e22; border-color: #4285f4; }}
  .btn-github {{ border-color: #6e40c9; }}
  .btn-github:hover {{ background: #4a148c22; border-color: #6e40c9; }}
  .btn svg {{ width: 20px; height: 20px; flex-shrink: 0; }}
  .divider {{
    display: flex;
    align-items: center;
    margin: 20px 0;
    color: #555;
    font-size: 13px;
  }}
  .divider::before, .divider::after {{
    content: '';
    flex: 1;
    border-bottom: 1px solid #333;
  }}
  .divider::before {{ margin-right: 12px; }}
  .divider::after {{ margin-left: 12px; }}
  .note {{
    color: #666;
    font-size: 12px;
    margin-top: 20px;
    line-height: 1.5;
  }}
  .note a {{ color: #888; }}
  .star-callout {{
    background: #1e1033;
    border: 1px solid #6e40c9;
    border-radius: 10px;
    padding: 14px 16px;
    margin-bottom: 20px;
    text-align: left;
    display: flex;
    align-items: flex-start;
    gap: 10px;
  }}
  .star-callout .star-icon {{
    font-size: 22px;
    line-height: 1;
    flex-shrink: 0;
  }}
  .star-callout .star-text {{
    font-size: 13px;
    color: #d1c4e9;
    line-height: 1.5;
  }}
  .star-callout .star-text strong {{
    color: #e1bee7;
    font-weight: 600;
  }}
  .star-callout .star-text a {{
    color: #bb86fc;
    text-decoration: underline;
    text-underline-offset: 2px;
  }}
  .star-callout .star-text a:hover {{
    color: #e1bee7;
  }}
  .alpha-badge {{
    display: inline-block;
    background: #4a148c;
    color: #e1bee7;
    font-size: 11px;
    font-weight: 600;
    padding: 2px 8px;
    border-radius: 4px;
    margin-left: 8px;
    vertical-align: middle;
  }}
</style>
</head>
<body>
<div class="card">
  <div class="logo">{server_icon}</div>
  <h1>{server_name}{alpha_badge}</h1>
  <p class="subtitle">{subtitle}</p>

  {google_button}

  {divider}

  {star_callout}

  {github_button}

  <p class="note">{note}</p>
</div>
</body>
</html>"""

# SVG icons
GOOGLE_SVG = '<svg viewBox="0 0 24 24"><path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 01-2.2 3.32v2.77h3.57c2.08-1.92 3.27-4.74 3.27-8.1z"/><path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/><path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/><path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/></svg>'
GITHUB_SVG = '<svg viewBox="0 0 24 24" fill="#fff"><path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z"/></svg>'


def build_provider_select_html(
    *,
    server_name: str = "MCP Server",
    server_icon: str = "&#x1f512;",
    google_url: str | None = None,
    github_url: str | None = None,
    alpha_mode: bool = False,
    github_gating_repo: str = "",
) -> str:
    """Build the provider selection HTML page."""
    alpha_badge = '<span class="alpha-badge">ALPHA</span>' if alpha_mode else ""

    subtitle = "Choose how to sign in"
    if alpha_mode:
        subtitle = "Choose how to sign in for alpha access"

    google_button = ""
    if google_url:
        google_button = (
            f'<a href="{google_url}" class="btn btn-google">'
            f"{GOOGLE_SVG} Continue with Google</a>"
        )

    github_button = ""
    if github_url:
        github_button = (
            f'<a href="{github_url}" class="btn btn-github">'
            f"{GITHUB_SVG} Continue with GitHub</a>"
        )

    divider = ""
    if google_url and github_url:
        divider = '<div class="divider">or</div>'

    # Prominent star callout above GitHub button
    star_callout = ""
    if alpha_mode and github_gating_repo and github_url:
        star_callout = (
            '<div class="star-callout">'
            '<span class="star-icon">&#11088;</span>'
            '<span class="star-text">'
            "<strong>Star required for access</strong><br>"
            f'Star <a href="https://github.com/{github_gating_repo}" '
            f'target="_blank">{github_gating_repo}</a> on GitHub '
            "before signing in."
            "</span>"
            "</div>"
        )

    note_parts = []
    if alpha_mode and google_url:
        note_parts.append("Google sign-in is limited to approved accounts.")
    note = " ".join(note_parts)

    return PROVIDER_SELECT_HTML.format(
        server_name=server_name,
        server_icon=server_icon,
        alpha_badge=alpha_badge,
        subtitle=subtitle,
        google_button=google_button,
        github_button=github_button,
        divider=divider,
        star_callout=star_callout,
        note=note,
    )


class DualOAuthRouter:
    """Manages dual-provider OAuth routing behind a single MCP auth endpoint.

    Intercepts the GoogleProvider's authorize flow to show a provider selection
    page. The MCP client hits /authorize as normal, but instead of going straight
    to Google, the user sees a choice of Google or GitHub.

    Flow:
    1. MCP client hits /authorize → GoogleProvider.authorize() creates a txn
       and returns /auth/select?txn_id=X (instead of upstream Google URL)
    2. User sees provider selection page
    3. User clicks "Google" → redirect to upstream Google OAuth URL for that txn
    4. User clicks "GitHub" → /auth/github/authorize with MCP client params from txn
    5. GitHub callback → /auth/github/callback → star check → token → client redirect
    """

    def __init__(
        self,
        *,
        google_provider=None,
        github_provider=None,
        settings=None,
    ):
        from config.settings import Settings

        self._settings = settings or Settings()
        self._google_provider = google_provider
        self._github_provider = github_provider
        # Pending GitHub authorization transactions
        self._github_transactions: dict[str, dict[str, Any]] = {}

    def patch_authorize(self):
        """Patch the GoogleProvider's authorize method to redirect to /auth/select.

        This is the key integration point: instead of going straight to Google,
        the authorize method returns our provider selection page URL with the
        txn_id, so the user can choose Google or GitHub.
        """
        if not self._google_provider:
            return

        provider = self._google_provider
        _original_authorize = provider.authorize

        async def _authorize_with_select(client, params):
            """Intercept authorize to show provider selection instead of Google."""
            # Call the original authorize to create the transaction and get the
            # upstream Google URL. The original returns either:
            #   - upstream Google URL (consent disabled) — we need this for "Continue with Google"
            #   - /consent URL (consent enabled) — same idea
            upstream_url = await _original_authorize(client, params)

            # The transaction was just stored in provider._transaction_store.
            # We need to find the txn_id. The upstream_url contains it as a param
            # or we can extract it from the transaction store.
            #
            # When consent is disabled, upstream_url is the Google URL with our
            # callback. The txn_id is embedded in the state param sent to Google.
            # But we need the txn_id to look up the transaction later.
            #
            # Better approach: store the upstream_url keyed by a select_id,
            # and pass select_id to /auth/select.
            select_id = secrets.token_urlsafe(32)
            self._select_transactions = getattr(self, "_select_transactions", {})
            self._select_transactions[select_id] = {
                "upstream_google_url": upstream_url,
                "created_at": time.time(),
                "client_redirect_uri": str(params.redirect_uri),
                "client_state": params.state or "",
            }

            # Clean up expired select transactions (> 15 min)
            cutoff = time.time() - 900
            expired = [
                k
                for k, v in self._select_transactions.items()
                if v["created_at"] < cutoff
            ]
            for k in expired:
                del self._select_transactions[k]

            # Return our provider selection page URL
            base = str(provider.base_url).rstrip("/")
            select_url = f"{base}/auth/select?select_id={select_id}"
            logger.info(
                f"🔀 Redirecting to provider selection (select_id: {select_id[:8]}...)"
            )
            return select_url

        provider.authorize = _authorize_with_select
        logger.info("✅ Patched GoogleProvider.authorize → provider selection page")

    def get_custom_routes(self) -> list[Route]:
        """Return Starlette routes to register on the FastMCP app."""
        routes = []

        if self._github_provider:
            routes.append(
                Route(
                    "/auth/github/authorize",
                    endpoint=self._github_authorize,
                    methods=["GET"],
                    name="github_authorize",
                )
            )
            routes.append(
                Route(
                    "/auth/github/callback",
                    endpoint=self._github_callback,
                    methods=["GET"],
                    name="github_callback",
                )
            )

        # Provider selection page
        if self._google_provider and self._github_provider:
            routes.append(
                Route(
                    "/auth/select",
                    endpoint=self._provider_select,
                    methods=["GET"],
                    name="provider_select",
                )
            )
            # Route for "Continue with Google" — resumes the original Google flow
            routes.append(
                Route(
                    "/auth/select/google",
                    endpoint=self._select_google,
                    methods=["GET"],
                    name="select_google",
                )
            )

        return routes

    async def _provider_select(self, request: Request) -> HTMLResponse:
        """Show provider selection page.

        Accepts select_id from the patched authorize method to link back
        to the original MCP OAuth transaction.
        """
        select_id = request.query_params.get("select_id", "")
        params = dict(request.query_params)

        # "Continue with Google" — redirect to /auth/select/google with select_id
        google_url = None
        if self._google_provider and select_id:
            google_url = f"/auth/select/google?select_id={select_id}"
        elif self._google_provider:
            # Fallback: direct /authorize (no transaction context)
            google_url = f"/authorize?{urlencode(params)}"

        # "Continue with GitHub" — pass select_id so we can extract client redirect
        github_url = None
        if self._github_provider:
            github_params = {"select_id": select_id} if select_id else params
            github_url = f"/auth/github/authorize?{urlencode(github_params)}"

        html = build_provider_select_html(
            server_name=self._settings.server_name,
            google_url=google_url,
            github_url=github_url,
            alpha_mode=self._settings.alpha_mode,
            github_gating_repo=self._settings.github_oauth_gating_repo,
        )
        return HTMLResponse(html)

    async def _select_google(self, request: Request) -> RedirectResponse | HTMLResponse:
        """User chose Google — redirect to the upstream Google OAuth URL."""
        select_id = request.query_params.get("select_id", "")
        select_transactions = getattr(self, "_select_transactions", {})
        txn = select_transactions.get(select_id)

        if not txn:
            return HTMLResponse(
                "<h1>Session Expired</h1><p>Please try signing in again.</p>",
                status_code=400,
            )

        upstream_url = txn["upstream_google_url"]
        logger.info(f"🔑 User chose Google, redirecting to upstream OAuth")
        return RedirectResponse(url=upstream_url, status_code=302)

    async def _github_authorize(self, request: Request) -> RedirectResponse:
        """Initiate GitHub OAuth flow."""
        txn_id = secrets.token_urlsafe(32)
        state = secrets.token_urlsafe(32)

        # Try to get MCP client redirect info from select_id transaction
        select_id = request.query_params.get("select_id", "")
        select_transactions = getattr(self, "_select_transactions", {})
        select_txn = select_transactions.get(select_id, {})

        client_redirect_uri = select_txn.get(
            "client_redirect_uri",
            request.query_params.get("redirect_uri", ""),
        )
        client_state = select_txn.get(
            "client_state",
            request.query_params.get("state", ""),
        )

        # Grab the upstream Google OAuth URL so that after GitHub gating
        # succeeds we can continue the Google OAuth flow (which issues the
        # real FastMCP tokens that Claude Code expects).
        upstream_google_url = select_txn.get("upstream_google_url", "")

        self._github_transactions[txn_id] = {
            "state": state,
            "created_at": time.time(),
            "original_params": dict(request.query_params),
            "client_redirect_uri": client_redirect_uri,
            "client_state": client_state,
            "upstream_google_url": upstream_google_url,
        }

        # Clean up old transactions (> 15 min)
        cutoff = time.time() - 900
        expired = [
            k for k, v in self._github_transactions.items() if v["created_at"] < cutoff
        ]
        for k in expired:
            del self._github_transactions[k]

        # Build GitHub authorization URL
        scopes = self._settings.github_oauth_required_scopes.replace(",", " ")
        base_url = self._settings.base_url.rstrip("/")
        github_auth_params = {
            "client_id": self._settings.github_oauth_client_id,
            "redirect_uri": f"{base_url}/auth/github/callback",
            "scope": scopes,
            "state": f"{txn_id}:{state}",
        }

        github_url = (
            f"https://github.com/login/oauth/authorize?{urlencode(github_auth_params)}"
        )
        logger.info(f"Redirecting to GitHub OAuth (txn: {txn_id[:8]}...)")
        return RedirectResponse(url=github_url, status_code=302)

    async def _github_callback(
        self, request: Request
    ) -> HTMLResponse | RedirectResponse:
        """Handle GitHub OAuth callback."""
        import httpx

        code = request.query_params.get("code")
        state = request.query_params.get("state", "")
        error = request.query_params.get("error")

        if error:
            return HTMLResponse(
                f"<h1>GitHub Authentication Failed</h1><p>{error}</p>",
                status_code=400,
            )

        if not code or ":" not in state:
            return HTMLResponse(
                "<h1>Invalid callback</h1><p>Missing code or state</p>",
                status_code=400,
            )

        txn_id, expected_state = state.split(":", 1)
        txn = self._github_transactions.pop(txn_id, None)

        if not txn or txn["state"] != expected_state:
            return HTMLResponse(
                "<h1>Invalid or expired session</h1><p>Please try again.</p>",
                status_code=400,
            )

        # Exchange code for token
        base_url = self._settings.base_url.rstrip("/")
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    "https://github.com/login/oauth/access_token",
                    data={
                        "client_id": self._settings.github_oauth_client_id,
                        "client_secret": self._settings.github_oauth_client_secret,
                        "code": code,
                        "redirect_uri": f"{base_url}/auth/github/callback",
                    },
                    headers={"Accept": "application/json"},
                )
                token_data = resp.json()
        except Exception as e:
            logger.error(f"GitHub token exchange failed: {e}")
            return HTMLResponse(
                "<h1>Authentication Error</h1><p>Failed to exchange code.</p>",
                status_code=500,
            )

        access_token = token_data.get("access_token")
        if not access_token:
            error_desc = token_data.get("error_description", "Unknown error")
            return HTMLResponse(
                f"<h1>Authentication Failed</h1><p>{error_desc}</p>",
                status_code=400,
            )

        # Fetch user info
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                user_resp = await client.get(
                    "https://api.github.com/user",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Accept": "application/vnd.github.v3+json",
                        "User-Agent": "FastMCP-GitHub-Alpha",
                    },
                )
                user_data = user_resp.json()
        except Exception as e:
            logger.error(f"GitHub user fetch failed: {e}")
            return HTMLResponse(
                "<h1>Authentication Error</h1><p>Failed to fetch user info.</p>",
                status_code=500,
            )

        github_login = user_data.get("login", "unknown")
        github_email = user_data.get("email")

        # Alpha gating: check repo star
        if self._settings.alpha_mode:
            from auth.alpha_gating import check_github_star

            if (
                self._settings.alpha_github_require_star
                and self._settings.github_oauth_gating_repo
            ):
                starred = await check_github_star(
                    access_token, self._settings.github_oauth_gating_repo
                )
                if not starred:
                    repo = self._settings.github_oauth_gating_repo
                    retry_params = urlencode(txn.get("original_params", {}))
                    return HTMLResponse(
                        f"""<!DOCTYPE html>
<html><head><title>Alpha Access Required</title>
<style>
body {{ font-family: -apple-system, sans-serif; background: #0a0a0a; color: #e5e5e5;
       display: flex; align-items: center; justify-content: center; min-height: 100vh; }}
.card {{ background: #1a1a1a; border: 1px solid #333; border-radius: 16px;
         padding: 40px; max-width: 440px; text-align: center; }}
h1 {{ color: #e1bee7; font-size: 20px; margin-bottom: 16px; }}
p {{ color: #888; font-size: 14px; line-height: 1.6; margin-bottom: 20px; }}
a {{ color: #bb86fc; text-decoration: none; }}
a:hover {{ text-decoration: underline; }}
.star-btn {{
  display: flex; align-items: center; justify-content: center; gap: 10px;
  width: 100%; padding: 14px 20px; border: 1px solid #6e40c9; border-radius: 10px;
  background: #1e1033; color: #e1bee7; font-size: 15px; font-weight: 500;
  cursor: pointer; transition: all 0.25s; margin-bottom: 12px;
}}
.star-btn:hover {{ background: #2a1745; border-color: #9c64ff; }}
.star-btn.starred {{ border-color: #ffd54f; background: #2e2614; color: #ffd54f; }}
.star-btn.starred:hover {{ background: #3a2e16; }}
.star-btn .star-icon {{ font-size: 20px; transition: transform 0.3s; }}
.star-btn.loading .star-icon {{ animation: spin 0.8s linear infinite; }}
@keyframes spin {{ to {{ transform: rotate(360deg); }} }}
.star-btn .repo-name {{ font-size: 12px; color: #888; margin-top: 2px; }}
.continue-btn {{
  display: flex; align-items: center; justify-content: center; gap: 8px;
  width: 100%; padding: 14px 20px; border: 1px solid #333; border-radius: 10px;
  background: #222; color: #888; font-size: 14px; cursor: not-allowed;
  transition: all 0.25s; text-decoration: none; margin-top: 8px; opacity: 0.5;
}}
.continue-btn.active {{
  background: #6e40c9; color: #fff; border-color: #6e40c9;
  cursor: pointer; opacity: 1;
}}
.continue-btn.active:hover {{ background: #7c4dff; }}
.status-msg {{ font-size: 12px; color: #666; margin-top: 12px; min-height: 18px; }}
</style></head><body><div class="card">
<h1>&#11088; Star Required for Alpha Access</h1>
<p>Hi <strong>{github_login}</strong>! Star the repo below to unlock access.</p>

<button id="starBtn" class="star-btn" onclick="toggleStar()">
  <span class="star-icon">&#9734;</span>
  <span>
    <span id="starLabel">Star this repo</span><br>
    <span class="repo-name">{repo}</span>
  </span>
</button>

<a id="continueBtn" class="continue-btn" href="/auth/github/authorize?{retry_params}">
  Continue to sign in
</a>

<p id="statusMsg" class="status-msg"></p>

<script>
const TOKEN = "{access_token}";
const REPO = "{repo}";
const API = "https://api.github.com/user/starred/" + REPO;
const HDR = {{ "Authorization": "Bearer " + TOKEN,
              "Accept": "application/vnd.github.v3+json" }};
let isStarred = false;

async function checkStar() {{
  try {{
    const r = await fetch(API, {{ headers: HDR }});
    if (r.status === 204) {{ setStarred(true); }}
  }} catch(e) {{}}
}}

function setStarred(v) {{
  isStarred = v;
  const btn = document.getElementById("starBtn");
  const label = document.getElementById("starLabel");
  const cont = document.getElementById("continueBtn");
  const msg = document.getElementById("statusMsg");
  btn.classList.remove("loading");
  if (v) {{
    btn.classList.add("starred");
    label.textContent = "Starred";
    btn.querySelector(".star-icon").innerHTML = "&#11088;";
    cont.classList.add("active");
    msg.textContent = "\\u2705 You're all set — click continue below!";
    msg.style.color = "#81c784";
  }} else {{
    btn.classList.remove("starred");
    label.textContent = "Star this repo";
    btn.querySelector(".star-icon").innerHTML = "\\u2606";
    cont.classList.remove("active");
    msg.textContent = "";
  }}
}}

async function toggleStar() {{
  const btn = document.getElementById("starBtn");
  btn.classList.add("loading");
  try {{
    if (isStarred) {{
      await fetch(API, {{ method: "DELETE", headers: HDR }});
      setStarred(false);
    }} else {{
      await fetch(API, {{ method: "PUT", headers: HDR,
                         body: "", headers: {{ ...HDR, "Content-Length": "0" }} }});
      setStarred(true);
    }}
  }} catch(e) {{
    btn.classList.remove("loading");
    document.getElementById("statusMsg").textContent = "Request failed — try again.";
    document.getElementById("statusMsg").style.color = "#ef5350";
  }}
}}

checkStar();
</script>
</div></body></html>""",
                        status_code=403,
                    )

        logger.info(
            f"GitHub OAuth successful for {github_login} ({redact_email(github_email)})"
        )

        # Cache GitHub user data for session enrichment
        if self._github_provider:
            github_user_id = str(user_data.get("id", ""))
            self._github_provider._github_user_cache[github_user_id] = {
                "login": github_login,
                "email": github_email,
                "name": user_data.get("name"),
                "id": github_user_id,
                "avatar_url": user_data.get("avatar_url"),
                "access_token": access_token,
                "starred_gating_repo": True,
            }

        # After GitHub gating succeeds, continue to Google OAuth so that
        # FastMCP's OAuth proxy can issue proper JWT tokens.  GitHub was just
        # the gate; Google provides the actual Workspace credentials.
        upstream_google_url = txn.get("upstream_google_url", "")

        if upstream_google_url:
            logger.info(
                f"✅ GitHub gating passed for {github_login}, "
                f"continuing to Google OAuth"
            )
            repo = self._settings.github_oauth_gating_repo or ""
            return HTMLResponse(
                f"""<!DOCTYPE html>
<html><head><title>Access Granted</title>
<style>
body {{ font-family: -apple-system, sans-serif; background: #0a0a0a; color: #e5e5e5;
       display: flex; align-items: center; justify-content: center; min-height: 100vh; }}
.card {{ background: #1a1a1a; border: 1px solid #333; border-radius: 16px;
         padding: 40px; max-width: 440px; text-align: center; }}
h1 {{ color: #81c784; font-size: 20px; margin-bottom: 12px; }}
p {{ color: #aaa; font-size: 14px; line-height: 1.6; margin-bottom: 8px; }}
.star-toggle {{
  display: flex; align-items: center; justify-content: center; gap: 10px;
  width: 100%; padding: 12px 16px; border: 1px solid #ffd54f; border-radius: 10px;
  background: #2e2614; color: #ffd54f; font-size: 14px; font-weight: 500;
  cursor: pointer; transition: all 0.25s; margin: 16px 0 8px;
}}
.star-toggle:hover {{ background: #3a2e16; }}
.star-toggle.unstarred {{ border-color: #555; background: #1e1033; color: #aaa; }}
.star-toggle.unstarred:hover {{ border-color: #6e40c9; }}
.star-toggle .icon {{ font-size: 18px; transition: transform 0.3s; }}
.star-toggle.loading .icon {{ animation: spin 0.8s linear infinite; }}
@keyframes spin {{ to {{ transform: rotate(360deg); }} }}
.continue-btn {{
  display: flex; align-items: center; justify-content: center;
  width: 100%; padding: 14px 20px; border: 1px solid #2e7d32; border-radius: 10px;
  background: #1b5e20; color: #fff; font-size: 15px; font-weight: 500;
  cursor: pointer; text-decoration: none; transition: all 0.2s; margin-top: 8px;
}}
.continue-btn:hover {{ background: #2e7d32; }}
.redirect-note {{ color: #666; font-size: 12px; margin-top: 12px; }}
</style></head><body><div class="card">
<h1>&#x2705; Welcome, {github_login}!</h1>
<p>Your alpha access has been verified.</p>

<button id="starBtn" class="star-toggle" onclick="toggleStar()">
  <span class="icon">&#11088;</span>
  <span id="starLabel">Starred {repo}</span>
</button>

<a class="continue-btn" href="{upstream_google_url}">
  Continue to Google sign-in &rarr;
</a>

<p class="redirect-note">You'll sign in with Google for Workspace access.</p>

<script>
const TOKEN = "{access_token}";
const REPO = "{repo}";
const API = "https://api.github.com/user/starred/" + REPO;
const HDR = {{ "Authorization": "Bearer " + TOKEN,
              "Accept": "application/vnd.github.v3+json" }};
let isStarred = true;

function render() {{
  const btn = document.getElementById("starBtn");
  const label = document.getElementById("starLabel");
  btn.classList.remove("loading");
  if (isStarred) {{
    btn.classList.remove("unstarred");
    btn.querySelector(".icon").innerHTML = "&#11088;";
    label.textContent = "Starred " + REPO;
  }} else {{
    btn.classList.add("unstarred");
    btn.querySelector(".icon").innerHTML = "\\u2606";
    label.textContent = "Star " + REPO;
  }}
}}

async function toggleStar() {{
  const btn = document.getElementById("starBtn");
  btn.classList.add("loading");
  try {{
    if (isStarred) {{
      await fetch(API, {{ method: "DELETE", headers: HDR }});
      isStarred = false;
    }} else {{
      await fetch(API, {{ method: "PUT", headers: HDR,
                         headers: {{ ...HDR, "Content-Length": "0" }} }});
      isStarred = true;
    }}
    render();
  }} catch(e) {{
    btn.classList.remove("loading");
  }}
}}
</script>
</div></body></html>"""
            )

        # Fallback: no upstream Google URL (e.g. direct /auth/github/authorize
        # without going through /auth/select).
        # GitHub is only used for star-gating — never return a raw GitHub token
        # as the bearer token, because FastMCP expects its own JWTs.
        # Instead, redirect through Google OAuth to get proper tokens.
        original_params = txn.get("original_params", {})
        base_url = self._settings.base_url.rstrip("/")

        if self._google_provider:
            # Redirect to /authorize which will go through Google OAuth
            # and issue proper FastMCP JWT tokens.
            authorize_params = {
                k: v
                for k, v in original_params.items()
                if k
                in (
                    "redirect_uri",
                    "state",
                    "code_challenge",
                    "code_challenge_method",
                    "scope",
                    "response_type",
                    "client_id",
                )
            }
            if authorize_params:
                logger.info(
                    f"✅ GitHub gating passed for {github_login}, "
                    f"redirecting to Google OAuth (no upstream URL in txn)"
                )
                return RedirectResponse(
                    url=f"{base_url}/authorize?{urlencode(authorize_params)}",
                    status_code=302,
                )

        # No Google provider or no params — show success page (manual flow)
        return HTMLResponse(
            f"""<!DOCTYPE html>
<html><head><title>Authenticated</title>
<style>
body {{ font-family: -apple-system, sans-serif; background: #0a0a0a; color: #e5e5e5;
       display: flex; align-items: center; justify-content: center; min-height: 100vh; }}
.card {{ background: #1a1a1a; border: 1px solid #333; border-radius: 16px;
         padding: 40px; max-width: 420px; text-align: center; }}
h1 {{ color: #81c784; font-size: 20px; margin-bottom: 12px; }}
p {{ color: #888; font-size: 14px; }}
</style></head><body><div class="card">
<h1>&#x2705; Alpha Access Verified</h1>
<p>Welcome, <strong>{github_login}</strong>!</p>
<p>Please reconnect your MCP client to sign in with Google.</p>
</div></body></html>"""
        )
