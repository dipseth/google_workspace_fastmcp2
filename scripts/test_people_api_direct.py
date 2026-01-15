"""Direct test of People API using encrypted credentials."""

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
from googleapiclient.discovery import build

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


async def test_people_api_direct(user_email: str, space_id: str):
    """Test People API directly with encrypted credentials."""
    logger.info("=" * 80)
    logger.info("🧪 Direct People API Test with Encrypted Credentials")
    logger.info("=" * 80)

    # Load credentials
    logger.info(f"\n📧 User: {user_email}")
    try:
        credentials = load_encrypted_credentials(user_email)
        logger.info("✅ Loaded encrypted credentials")
        logger.info(f"📋 Scopes: {len(credentials.scopes)}")

        # Check for People API scope
        people_scope = "https://www.googleapis.com/auth/contacts.readonly"
        has_people_scope = people_scope in credentials.scopes
        logger.info(f"👤 People API scope: {has_people_scope}")

        if not has_people_scope:
            logger.error("❌ People API scope missing - please re-authenticate")
            return

    except Exception as e:
        logger.error(f"❌ Error loading credentials: {e}")
        return

    # Build Chat service directly
    logger.info("\n💬 Building Chat service...")
    chat_service = build("chat", "v1", credentials=credentials)
    logger.info("✅ Chat service created")

    # List messages
    logger.info(f"\n📋 Listing messages from: {space_id}")
    try:
        response = (
            chat_service.spaces().messages().list(parent=space_id, pageSize=5).execute()
        )

        messages = response.get("messages", [])
        logger.info(f"✅ Retrieved {len(messages)} messages\n")

        # Collect user IDs
        user_ids = set()
        for msg in messages:
            sender = msg.get("sender", {})
            sender_id = sender.get("name", "")
            if sender_id and sender_id.startswith("users/"):
                user_id = sender_id.split("/")[-1]
                user_ids.add(user_id)
                logger.info(f"🔍 Found user ID: {user_id}")

        if not user_ids:
            logger.info("✅ All senders already have display names!")
            return

        # Build People API service
        logger.info(f"\n👤 Testing People API for {len(user_ids)} users...")
        people_service = build("people", "v1", credentials=credentials)
        logger.info("✅ People service created\n")

        # Test each user
        for user_id in user_ids:
            try:
                resource_name = f"people/{user_id}"
                person = (
                    people_service.people()
                    .get(
                        resourceName=resource_name, personFields="names,emailAddresses"
                    )
                    .execute()
                )

                names = person.get("names", [])
                emails = person.get("emailAddresses", [])

                display_name = names[0].get("displayName") if names else None
                email = emails[0].get("value") if emails else None

                if display_name or email:
                    logger.info(f"✅ {user_id}:")
                    logger.info(f"   Name: {display_name}")
                    logger.info(f"   Email: {email}\n")
                else:
                    logger.info(f"⚠️  {user_id}: No profile data\n")

            except Exception as e:
                logger.info(f"❌ {user_id}: {str(e)[:100]}\n")

        logger.info("=" * 80)
        logger.info("🎉 People API Test Complete!")
        logger.info("=" * 80)
        logger.info("\n✨ Middleware will do this automatically after server restart!")

    except Exception as e:
        logger.error(f"❌ Error: {e}", exc_info=True)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(
            "Usage: uv run python scripts/test_people_api_direct.py <email> <space_id>"
        )
        print(
            "Example: uv run python scripts/test_people_api_direct.py srivers@groupon.com spaces/AAAA8RCqhYI"
        )
        sys.exit(1)

    asyncio.run(test_people_api_direct(sys.argv[1], sys.argv[2]))
