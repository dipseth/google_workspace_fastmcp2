"""Test script to verify People API integration for Chat sender enrichment."""

import asyncio
import base64
import json
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from datetime import datetime

from google.oauth2.credentials import Credentials

from auth.service_helpers import get_service
from config.enhanced_logging import setup_logger
from config.settings import settings

logger = setup_logger()


def load_encrypted_credentials(user_email: str) -> Credentials:
    """Load credentials from encrypted file."""
    from cryptography.fernet import Fernet

    # Load encryption key
    key_path = Path(settings.credentials_dir) / ".auth_encryption_key"
    with open(key_path, "rb") as f:
        key_bytes = f.read()

    fernet = Fernet(key_bytes)

    # Load encrypted credentials
    safe_email = user_email.replace("@", "_at_").replace(".", "_")
    creds_path = Path(settings.credentials_dir) / f"{safe_email}_credentials.enc"

    with open(creds_path, "r") as f:
        encrypted_data = f.read()

    # Decrypt
    encrypted_bytes = base64.urlsafe_b64decode(encrypted_data.encode())
    decrypted_data = fernet.decrypt(encrypted_bytes)
    creds_data = json.loads(decrypted_data.decode())

    # Reconstruct credentials
    credentials = Credentials(
        token=creds_data["token"],
        refresh_token=creds_data["refresh_token"],
        token_uri=creds_data.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=creds_data["client_id"],
        client_secret=creds_data["client_secret"],
        scopes=creds_data.get("scopes", []),
    )

    if creds_data.get("expiry"):
        credentials.expiry = datetime.fromisoformat(creds_data["expiry"])

    return credentials


async def test_people_api_enrichment(user_email: str, space_id: str):
    """
    Test People API integration for Chat message enrichment.

    Args:
        user_email: User's Google email address
        space_id: Chat space ID to list messages from
    """
    logger.info("=" * 80)
    logger.info("🧪 Testing People API Integration for Chat Sender Enrichment")
    logger.info("=" * 80)

    # Step 1: Check authentication
    logger.info(f"\n📧 User Email: {user_email}")

    try:
        credentials = load_encrypted_credentials(user_email)
        logger.info(f"✅ Loaded encrypted credentials for {user_email}")
    except FileNotFoundError:
        logger.error(f"❌ No encrypted credentials found for {user_email}")
        logger.info(
            "Credentials should be at: credentials/srivers_at_groupon_com_credentials.enc"
        )
        return
    except Exception as e:
        logger.error(f"❌ Error loading credentials: {e}")
        return

    logger.info(f"✅ Valid credentials found for {user_email}")
    logger.info(f"📋 Scopes: {len(credentials.scopes)} scopes")

    # Check for People API scope
    people_scope = "https://www.googleapis.com/auth/contacts.readonly"
    has_people_scope = people_scope in credentials.scopes
    logger.info(f"👤 People API scope present: {has_people_scope}")

    if not has_people_scope:
        logger.warning("⚠️ People API scope not found - re-authentication needed")
        logger.info("Run: uv run python scripts/auth_test.py chat")

    # Step 2: Get Chat service
    logger.info("\n💬 Getting Chat service...")
    chat_service = await get_service("chat", user_email)
    logger.info("✅ Chat service created")

    # Step 3: List messages
    logger.info(f"\n📋 Listing messages from space: {space_id}")
    try:
        response = (
            chat_service.spaces().messages().list(parent=space_id, pageSize=5).execute()
        )

        messages = response.get("messages", [])
        logger.info(f"✅ Retrieved {len(messages)} messages")

        # Display messages
        logger.info("\n" + "=" * 80)
        logger.info("📨 MESSAGES (Before Enrichment):")
        logger.info("=" * 80)

        user_ids_found = set()
        for i, msg in enumerate(messages, 1):
            sender = msg.get("sender", {})
            sender_name = sender.get("displayName") or sender.get("name", "Unknown")
            text = msg.get("text", "")[:100]

            logger.info(f"\n{i}. Sender: {sender_name}")
            logger.info(f"   Text: {text}")

            # Check if sender name looks like a user ID
            if sender_name.startswith("users/"):
                user_id = sender_name.split("/")[-1]
                user_ids_found.add(user_id)
                logger.info(f"   🔍 User ID detected: {user_id}")

        # Step 4: Test People API enrichment
        if user_ids_found and has_people_scope:
            logger.info("\n" + "=" * 80)
            logger.info(
                f"👤 Testing People API enrichment for {len(user_ids_found)} users..."
            )
            logger.info("=" * 80)

            people_service = await get_service("people", user_email)
            logger.info("✅ People service created")

            for user_id in user_ids_found:
                try:
                    resource_name = f"people/{user_id}"
                    person = (
                        people_service.people()
                        .get(
                            resourceName=resource_name,
                            personFields="names,emailAddresses",
                        )
                        .execute()
                    )

                    names = person.get("names", [])
                    emails = person.get("emailAddresses", [])

                    display_name = names[0].get("displayName") if names else None
                    email = emails[0].get("value") if emails else None

                    if display_name or email:
                        logger.info(f"\n✅ {user_id}:")
                        logger.info(f"   Name: {display_name or 'N/A'}")
                        logger.info(f"   Email: {email or 'N/A'}")
                    else:
                        logger.info(f"\n⚠️ {user_id}: No profile data available")

                except Exception as e:
                    logger.info(f"\n❌ {user_id}: {e}")

        elif not has_people_scope:
            logger.warning("\n⚠️ People API scope missing - cannot test enrichment")
            logger.info("Re-authenticate with People API scope to enable enrichment")
        else:
            logger.info(
                "\n✅ No user IDs found in messages - all senders already have display names"
            )

    except Exception as e:
        logger.error(f"❌ Error listing messages: {e}", exc_info=True)

    logger.info("\n" + "=" * 80)
    logger.info("🧪 Test Complete")
    logger.info("=" * 80)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(
            "Usage: uv run python scripts/test_people_api_enrichment.py <user_email> <space_id>"
        )
        print(
            "Example: uv run python scripts/test_people_api_enrichment.py user@example.com spaces/AAAAAbCdEfG"
        )
        sys.exit(1)

    user_email = sys.argv[1]
    space_id = sys.argv[2]

    asyncio.run(test_people_api_enrichment(user_email, space_id))
