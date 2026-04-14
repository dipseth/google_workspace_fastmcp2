"""Alpha access gating for multi-provider OAuth.

Controls access during alpha release:
- GitHub OAuth users must star a designated repo
- Google OAuth users must be on an email allowlist

Both checks are optional and controlled via settings (alpha_mode).
"""

from __future__ import annotations

import httpx

from config.enhanced_logging import redact_email, setup_logger

logger = setup_logger()


class AlphaAccessDenied(Exception):
    """Raised when a user fails alpha access checks."""

    def __init__(self, reason: str, provider: str):
        self.reason = reason
        self.provider = provider
        super().__init__(f"Alpha access denied ({provider}): {reason}")


async def check_github_star(
    token: str,
    repo: str,
    *,
    timeout: int = 10,
) -> bool:
    """Check if the authenticated GitHub user has starred a repo.

    Args:
        token: GitHub OAuth access token
        repo: Repository in "owner/repo" format
        timeout: HTTP request timeout in seconds

    Returns:
        True if the user has starred the repo, False otherwise
    """
    if not repo:
        logger.debug("No gating repo configured, skipping star check")
        return True

    url = f"https://api.github.com/user/starred/{repo}"
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.get(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": "FastMCP-GitHub-Alpha",
            },
        )
        # 204 = starred, 404 = not starred
        if response.status_code == 204:
            logger.info(f"GitHub user has starred {repo}")
            return True
        elif response.status_code == 404:
            logger.info(f"GitHub user has NOT starred {repo}")
            return False
        else:
            logger.warning(
                f"Unexpected status {response.status_code} checking star for {repo}"
            )
            return False


def check_google_email_allowlist(
    email: str,
    allowlist_csv: str,
) -> bool:
    """Check if a Google email is on the alpha allowlist.

    Args:
        email: User's Google email address
        allowlist_csv: Comma-separated list of allowed emails

    Returns:
        True if the email is allowed (or if allowlist is empty/disabled)
    """
    if not allowlist_csv:
        # No allowlist = everyone allowed
        return True

    allowed_emails = {e.strip().lower() for e in allowlist_csv.split(",") if e.strip()}
    is_allowed = email.lower() in allowed_emails
    if not is_allowed:
        logger.info(f"Google email {redact_email(email)} not on alpha allowlist")
    return is_allowed


async def enforce_alpha_access(
    *,
    provider: str,
    github_token: str | None = None,
    github_login: str | None = None,
    google_email: str | None = None,
    settings=None,
) -> None:
    """Enforce alpha access rules. Raises AlphaAccessDenied on failure.

    Args:
        provider: "github" or "google"
        github_token: GitHub OAuth token (required for GitHub provider)
        github_login: GitHub username (for logging)
        google_email: Google email (required for Google provider)
        settings: App settings object (loaded from config if None)
    """
    if settings is None:
        from config.settings import Settings

        settings = Settings()

    if not settings.alpha_mode:
        return  # Alpha gating disabled

    if provider == "github":
        if not github_token:
            raise AlphaAccessDenied("No GitHub token provided", provider)

        if settings.alpha_github_require_star and settings.github_oauth_gating_repo:
            starred = await check_github_star(
                github_token, settings.github_oauth_gating_repo
            )
            if not starred:
                repo = settings.github_oauth_gating_repo
                raise AlphaAccessDenied(
                    f"Please star the repository github.com/{repo} to get alpha access. "
                    f"Then retry authentication.",
                    provider,
                )
            logger.info(
                f"GitHub user {github_login or 'unknown'} passed alpha star check"
            )

    elif provider == "google":
        if not google_email:
            raise AlphaAccessDenied("No Google email available", provider)

        if not check_google_email_allowlist(
            google_email, settings.alpha_google_email_allowlist
        ):
            raise AlphaAccessDenied(
                "Your Google account is not on the alpha access list. "
                "Contact the server administrator for access.",
                provider,
            )
        logger.info(f"Google user {google_email} passed alpha allowlist check")
