#!/usr/bin/env python3
"""Test script to verify access control is working correctly."""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from auth.access_control import get_access_control, validate_user_access
from auth.google_auth import get_all_stored_users
from config.enhanced_logging import setup_logger

logger = setup_logger()


async def test_access_control():
    """Test access control functionality."""

    print("\n" + "=" * 80)
    print("🔒 ACCESS CONTROL TEST")
    print("=" * 80 + "\n")

    # Get access control instance
    access_control = get_access_control()

    # Get stats
    stats = access_control.get_stats()
    print("📊 Access Control Configuration:")
    print(f"  Mode: {stats['mode']}")
    print(f"  Require existing credentials: {stats['require_existing_credentials']}")
    print(f"  Allowlist configured: {stats['allowlist_configured']}")
    print(f"  Allowlist count: {stats['allowlist_count']}")
    print(f"  Stored credentials count: {stats['stored_credentials_count']}")
    print()

    # Get all stored users
    stored_users = get_all_stored_users()
    print("✅ Authorized Users (have credentials):")
    for email in stored_users:
        print(f"  • {email}")
    print()

    # Test authorized users
    print("🧪 Testing Authorized Users:")
    for email in stored_users:
        is_allowed = validate_user_access(email)
        status = "✅ ALLOWED" if is_allowed else "🚫 DENIED"
        print(f"  {email}: {status}")
    print()

    # Test unauthorized users
    print("🧪 Testing Unauthorized Users:")
    test_emails = [
        "random@gmail.com",
        "unauthorized@example.com",
        "hacker@malicious.com",
    ]

    for email in test_emails:
        is_allowed = validate_user_access(email)
        status = "✅ ALLOWED" if is_allowed else "🚫 DENIED"
        print(f"  {email}: {status}")
    print()

    # Summary
    print("=" * 80)
    print("📋 SUMMARY")
    print("=" * 80)
    print(f"Authorized users: {len(stored_users)}")
    print(f"Access control mode: {stats['mode']}")
    print()

    if stats["mode"] == "strict":
        print("✅ Server is SECURE for Tailscale Funnel deployment")
        print("   Only users with existing credentials can authenticate")
    elif stats["mode"] == "open":
        print("⚠️  Server is OPEN - ANY Google user can authenticate")
        print("   NOT recommended for public deployment")

    print()


if __name__ == "__main__":
    asyncio.run(test_access_control())
