"""SSO GitHub Provider for FastMCP with alpha repo-star gating.

Extends FastMCP's built-in GitHubProvider to:
1. Extract GitHub user identity (login, email, user ID) from the OAuth token
2. Enforce alpha access by checking if the user has starred the gating repo
3. Store GitHub session data for downstream middleware consumption
"""

from __future__ import annotations

from fastmcp.server.auth.providers.github import GitHubProvider

from config.enhanced_logging import setup_logger

logger = setup_logger()


class SSOGitHubProvider(GitHubProvider):
    """GitHubProvider that enforces alpha access via repo star gating."""

    def __init__(self, *, gating_repo: str = "", alpha_mode: bool = False, **kwargs):
        """Initialize with alpha gating config.

        Args:
            gating_repo: Repository in "owner/repo" format to check for star
            alpha_mode: Whether alpha access gating is enabled
            **kwargs: Passed through to GitHubProvider
        """
        super().__init__(**kwargs)
        self._gating_repo = gating_repo
        self._alpha_mode = alpha_mode
        # Store GitHub user data from the last successful auth, keyed by token
        # This is consumed by AuthMiddleware to set session context
        self._github_user_cache: dict[str, dict] = {}

    async def exchange_authorization_code(self, client, authorization_code):
        """Intercept token exchange to enforce star gating and cache user data."""
        # Read the idp_tokens BEFORE the parent deletes the code
        code_model = await self._code_store.get(key=authorization_code.code)
        idp_tokens = code_model.idp_tokens if code_model else None

        if idp_tokens and self._alpha_mode:
            # Enforce alpha access before completing the exchange
            access_token = idp_tokens.get("access_token")
            if access_token:
                user_data = await self._fetch_github_user(access_token)
                if user_data:
                    await self._enforce_star_gating(access_token, user_data)

        # Call parent to do the real exchange (issues FastMCP JWT)
        result = await super().exchange_authorization_code(client, authorization_code)

        # Cache GitHub user data for session enrichment
        if idp_tokens:
            try:
                access_token = idp_tokens.get("access_token")
                if access_token:
                    user_data = await self._fetch_github_user(access_token)
                    if user_data:
                        # Cache keyed by GitHub user ID for lookup during token verify
                        github_user_id = str(user_data.get("id", ""))
                        self._github_user_cache[github_user_id] = {
                            "login": user_data.get("login"),
                            "email": user_data.get("email"),
                            "name": user_data.get("name"),
                            "id": github_user_id,
                            "avatar_url": user_data.get("avatar_url"),
                            "starred_gating_repo": True,  # Passed gating if we got here
                        }
                        logger.info(
                            f"GitHub OAuth completed for {user_data.get('login')} "
                            f"(id: {github_user_id})"
                        )
            except Exception as e:
                logger.warning(f"Failed to cache GitHub user data: {e}")

        return result

    async def _extract_upstream_claims(self, idp_tokens: dict) -> dict | None:
        """Extract GitHub user claims to embed in FastMCP JWT."""
        access_token = idp_tokens.get("access_token")
        if not access_token:
            return None

        user_data = await self._fetch_github_user(access_token)
        if not user_data:
            return None

        return {
            "github_sub": str(user_data["id"]),
            "github_login": user_data.get("login"),
            "github_email": user_data.get("email"),
            "github_name": user_data.get("name"),
            "auth_provider": "github",
        }

    async def _fetch_github_user(self, access_token: str) -> dict | None:
        """Fetch GitHub user profile from the API."""
        import httpx

        try:
            async with httpx.AsyncClient(timeout=10) as http_client:
                resp = await http_client.get(
                    "https://api.github.com/user",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Accept": "application/vnd.github.v3+json",
                        "User-Agent": "FastMCP-GitHub-Alpha",
                    },
                )
                if resp.status_code == 200:
                    return resp.json()
                logger.warning(f"GitHub user API returned {resp.status_code}")
                return None
        except Exception as e:
            logger.warning(f"Failed to fetch GitHub user: {e}")
            return None

    async def _enforce_star_gating(self, access_token: str, user_data: dict) -> None:
        """Check repo star and raise if not starred."""
        if not self._gating_repo:
            return

        from auth.alpha_gating import AlphaAccessDenied, check_github_star

        starred = await check_github_star(access_token, self._gating_repo)
        if not starred:
            login = user_data.get("login", "unknown")
            logger.warning(
                f"GitHub user {login} denied alpha access — "
                f"has not starred {self._gating_repo}"
            )
            raise AlphaAccessDenied(
                f"Please star github.com/{self._gating_repo} to get alpha access, "
                f"then retry authentication.",
                "github",
            )

    def get_cached_github_user(self, github_user_id: str) -> dict | None:
        """Retrieve cached GitHub user data by user ID."""
        return self._github_user_cache.get(github_user_id)
