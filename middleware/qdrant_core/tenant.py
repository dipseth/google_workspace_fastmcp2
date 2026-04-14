"""
Qdrant Multi-Tenant Isolation.

Provides mandatory user-scoped filtering so each user can only
access their own data in shared Qdrant collections.

Two-layer defence:
1. Application-level filter injection (this module) — works with any Qdrant setup.
2. Qdrant JWT RBAC with payload-filtered access (opt-in via config).
"""

import time
from typing import Optional

from config.enhanced_logging import setup_logger

logger = setup_logger()

# ---------------------------------------------------------------------------
# Application-level tenant filter helpers
# ---------------------------------------------------------------------------


def build_tenant_filter(user_email: str):
    """Return a Qdrant ``Filter`` with a ``must`` condition on ``user_email``.

    Args:
        user_email: Authenticated user's email address.

    Returns:
        ``qdrant_client.models.Filter`` scoped to this user.
    """
    from qdrant_client.models import FieldCondition, Filter, MatchValue

    return Filter(
        must=[
            FieldCondition(
                key="user_email",
                match=MatchValue(value=user_email),
            )
        ]
    )


def merge_tenant_filter(existing_filter, user_email: str):
    """Merge the mandatory tenant filter into an existing Qdrant filter.

    If *existing_filter* is ``None``, a new filter scoped to *user_email* is
    returned.  Otherwise the tenant condition is **appended** to the existing
    ``must`` list so both the user's own filter criteria and the tenant
    restriction are enforced.

    Args:
        existing_filter: An existing ``Filter`` (or ``None``).
        user_email: Authenticated user's email address.

    Returns:
        A ``Filter`` that includes the tenant condition.
    """
    from qdrant_client.models import FieldCondition, Filter, MatchValue

    tenant_condition = FieldCondition(
        key="user_email",
        match=MatchValue(value=user_email),
    )

    if existing_filter is None:
        return Filter(must=[tenant_condition])

    # existing_filter.must may be None
    must_list = list(existing_filter.must or [])
    must_list.append(tenant_condition)

    return Filter(
        must=must_list,
        should=existing_filter.should,
        must_not=existing_filter.must_not,
        min_should=getattr(existing_filter, "min_should", None),
    )


def verify_point_ownership(point_payload: dict, user_email: str) -> bool:
    """Check whether a retrieved point belongs to *user_email*.

    Used as a post-filter for ``client.retrieve()`` / ID lookups where
    Qdrant does not support query-time filters.

    Args:
        point_payload: The ``payload`` dict from a Qdrant point.
        user_email: Authenticated user's email address.

    Returns:
        ``True`` if the point's ``user_email`` matches.
    """
    stored = (point_payload or {}).get("user_email", "")
    return stored.lower().strip() == user_email.lower().strip()


# ---------------------------------------------------------------------------
# Qdrant JWT RBAC (Layer 2 — opt-in)
# ---------------------------------------------------------------------------


def generate_tenant_jwt(
    user_email: str,
    api_key: str,
    collection: str,
    ttl_seconds: int = 3600,
) -> str:
    """Generate a Qdrant JWT with payload-filtered read access for one user.

    Requires ``PyJWT`` (``pip install pyjwt``).  The token is signed with
    HS256 using the Qdrant API key (``QDRANT__SERVICE__API_KEY``).

    The resulting JWT enforces **server-side** isolation: even if the
    application code has a bug, Qdrant itself will only return points
    whose ``user_email`` matches the claim.

    Args:
        user_email: Email address to scope the token to.
        api_key: Qdrant API key used as the HMAC signing secret.
        collection: Qdrant collection name.
        ttl_seconds: Token lifetime in seconds (default 1 hour).

    Returns:
        Encoded JWT string.
    """
    import jwt  # PyJWT

    now = int(time.time())
    payload = {
        "exp": now + ttl_seconds,
        "iat": now,
        "access": [
            {
                "collection": collection,
                "access": "r",
                "payload": {
                    "user_email": user_email,
                },
            }
        ],
    }
    return jwt.encode(payload, api_key, algorithm="HS256")
