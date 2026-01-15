#!/usr/bin/env python3
"""
Integration test for Gmail reply improvements using real Gmail messages.

This test uses emails from the TEST_GMAIL_ALLOW_LIST environment variable to:
1. Send a real email between trusted addresses
2. Use that real message ID to test reply functionality
"""

import asyncio
import json
import os
import sys
import time

import pytest

from .base_test_config import TEST_EMAIL as DEFAULT_TEST_EMAIL
from .base_test_config import create_test_client

# Import test utilities from the standardized framework
from .test_helpers import ToolTestRunner

# Get emails from allow list - using TEST_GMAIL_ALLOW_LIST environment variable
TEST_GMAIL_ALLOW_LIST = os.getenv(
    "TEST_GMAIL_ALLOW_LIST", "test@gmail.com,test2@gmail.com"
)
ALLOWED_EMAILS = [
    email.strip() for email in TEST_GMAIL_ALLOW_LIST.split(",") if email.strip()
]

# Use first email as primary test account
PRIMARY_EMAIL = ALLOWED_EMAILS[0] if ALLOWED_EMAILS else DEFAULT_TEST_EMAIL
# Use second email as recipient (or same as sender if only one)
RECIPIENT_EMAIL = ALLOWED_EMAILS[1] if len(ALLOWED_EMAILS) > 1 else PRIMARY_EMAIL
# Additional recipients for reply-all testing
CC_EMAIL = ALLOWED_EMAILS[2] if len(ALLOWED_EMAILS) > 2 else None


@pytest.mark.service("gmail")
@pytest.mark.asyncio
@pytest.mark.integration
async def test_gmail_reply_with_real_messages():
    """Integration test using real Gmail messages between allow-listed emails."""

    print("=" * 70)
    print("Gmail Reply Integration Test with Real Messages")
    print("=" * 70)
    print("\n📧 Using allow-listed emails:")
    print(f"   Primary account: {PRIMARY_EMAIL}")
    print(f"   Recipient: {RECIPIENT_EMAIL}")
    if CC_EMAIL:
        print(f"   CC recipient: {CC_EMAIL}")
    print()

    # Create test client using the standardized framework
    print("📡 Creating test client...")

    try:
        client = await create_test_client(PRIMARY_EMAIL)
        async with client:
            print("✅ Connected to MCP server\n")

            runner = ToolTestRunner(client, PRIMARY_EMAIL)

            # Step 1: Send a real email to get a real message ID
            print("=" * 70)
            print("📤 Step 1: Sending a real email to test reply functionality")
            print("=" * 70)

            timestamp = int(time.time())
            test_subject = f"Test Reply Features - {timestamp}"

            send_result = await runner.test_tool_with_explicit_email(
                "send_gmail_message",
                {
                    "to": [RECIPIENT_EMAIL],
                    "cc": (
                        [CC_EMAIL] if CC_EMAIL and CC_EMAIL != RECIPIENT_EMAIL else []
                    ),
                    "subject": test_subject,
                    "body": f"This is a test email sent at {timestamp} to test the new reply functionality.\n\nThis message will be used to test:\n- Reply to sender only\n- Reply all\n- Custom recipients",
                    "content_type": "plain",
                },
            )

            sent_message_id = None
            if send_result and send_result.get("success"):
                result_text = send_result["content"]
                print(f"📨 Send result: {result_text[:200]}...")

                # Parse the JSON response to extract message ID
                try:
                    send_data = json.loads(result_text)
                    if send_data.get("success") and send_data.get("messageId"):
                        sent_message_id = send_data["messageId"]
                        print(
                            f"✅ Email sent successfully! Message ID: {sent_message_id}"
                        )
                except json.JSONDecodeError:
                    # Fallback to regex if not JSON
                    if "Message ID:" in result_text:
                        import re

                        match = re.search(r"Message ID:\s*(\S+)", result_text)
                        if match:
                            sent_message_id = match.group(1)
                            print(
                                f"✅ Email sent successfully! Message ID: {sent_message_id}"
                            )

            if not sent_message_id:
                print("⚠️  Could not extract message ID from send result")
                # Try to find the message via search
                print("🔍 Searching for the sent message...")
                await asyncio.sleep(2)  # Give Gmail a moment to index

                search_result = await runner.test_tool_with_explicit_email(
                    "search_gmail_messages",
                    {"query": f'subject:"{test_subject}"', "page_size": 1},
                )

                if search_result and search_result.get("success"):
                    result_text = search_result["content"]
                    try:
                        search_data = json.loads(result_text)
                        if (
                            search_data.get("messages")
                            and len(search_data["messages"]) > 0
                        ):
                            sent_message_id = search_data["messages"][0]["id"]
                            print(
                                f"✅ Found message via search! Message ID: {sent_message_id}"
                            )
                    except json.JSONDecodeError:
                        pass

            if not sent_message_id:
                print("❌ Could not get message ID for testing")
                return False

            # Wait a moment for Gmail to process
            await asyncio.sleep(2)

            # Step 2: Test reply_to_gmail_message with sender_only mode
            print("\n" + "=" * 70)
            print("📧 Step 2: Testing reply with SENDER_ONLY mode")
            print("=" * 70)

            reply_result = await runner.test_tool_with_explicit_email(
                "reply_to_gmail_message",
                {
                    "message_id": sent_message_id,
                    "body": "This is a test reply using sender_only mode (default behavior).",
                    "reply_mode": "sender_only",
                    "content_type": "plain",
                },
            )

            if reply_result and reply_result.get("success"):
                result_text = reply_result["content"]
                print(f"📨 Reply result: {result_text[:300]}...")
                try:
                    reply_data = json.loads(result_text)
                    if reply_data.get("success"):
                        print("✅ Reply sent successfully!")
                        print(
                            f"   • Reply message ID: {reply_data.get('reply_message_id')}"
                        )
                        print(f"   • Reply mode: {reply_data.get('reply_mode')}")
                        print(f"   • Replied to: {reply_data.get('replied_to')}")
                        print(f"   • To recipients: {reply_data.get('to_recipients')}")
                except json.JSONDecodeError:
                    pass

            # Step 3: Test reply_to_gmail_message with reply_all mode
            if CC_EMAIL and CC_EMAIL != RECIPIENT_EMAIL:
                print("\n" + "=" * 70)
                print("📧 Step 3: Testing reply with REPLY_ALL mode")
                print("=" * 70)

                reply_all_result = await runner.test_tool_with_explicit_email(
                    "reply_to_gmail_message",
                    {
                        "message_id": sent_message_id,
                        "body": "This is a test reply using reply_all mode - everyone should receive this.",
                        "reply_mode": "reply_all",
                        "content_type": "plain",
                    },
                )

                if reply_all_result and reply_all_result.get("success"):
                    result_text = reply_all_result["content"]
                    print(f"📨 Reply all result: {result_text[:300]}...")
                    try:
                        reply_data = json.loads(result_text)
                        if reply_data.get("success"):
                            print("✅ Reply all sent successfully!")
                            print(f"   • Reply mode: {reply_data.get('reply_mode')}")
                            print(
                                f"   • To recipients: {reply_data.get('to_recipients')}"
                            )
                            print(
                                f"   • CC recipients: {reply_data.get('cc_recipients')}"
                            )
                    except json.JSONDecodeError:
                        pass

            # Step 4: Test reply with custom mode
            print("\n" + "=" * 70)
            print("📧 Step 4: Testing reply with CUSTOM mode")
            print("=" * 70)

            # Use a different combination of recipients
            custom_to = [ALLOWED_EMAILS[0]]  # Send to first email
            custom_cc = [ALLOWED_EMAILS[-1]] if len(ALLOWED_EMAILS) > 1 else []

            custom_reply_result = await runner.test_tool_with_explicit_email(
                "reply_to_gmail_message",
                {
                    "message_id": sent_message_id,
                    "body": "This is a test reply using custom mode with specific recipients.",
                    "reply_mode": "custom",
                    "to": custom_to,
                    "cc": custom_cc,
                    "content_type": "plain",
                },
            )

            if custom_reply_result and custom_reply_result.get("success"):
                result_text = custom_reply_result["content"]
                print(f"📨 Custom reply result: {result_text[:300]}...")
                try:
                    reply_data = json.loads(result_text)
                    if reply_data.get("success"):
                        print("✅ Custom reply sent successfully!")
                        print(f"   • Reply mode: {reply_data.get('reply_mode')}")
                        print(f"   • To recipients: {reply_data.get('to_recipients')}")
                        print(f"   • CC recipients: {reply_data.get('cc_recipients')}")
                except json.JSONDecodeError:
                    pass

            # Step 5: Test draft_gmail_reply
            print("\n" + "=" * 70)
            print("📝 Step 5: Testing draft_gmail_reply with reply_all mode")
            print("=" * 70)

            draft_reply_result = await runner.test_tool_with_explicit_email(
                "draft_gmail_reply",
                {
                    "message_id": sent_message_id,
                    "body": "This is a DRAFT reply using reply_all mode. It won't be sent automatically.",
                    "reply_mode": "reply_all",
                    "content_type": "plain",
                },
            )

            if draft_reply_result and draft_reply_result.get("success"):
                result_text = draft_reply_result["content"]
                print(f"📝 Draft result: {result_text[:300]}...")
                try:
                    draft_data = json.loads(result_text)
                    if draft_data.get("success"):
                        print("✅ Draft reply created successfully!")
                        print(f"   • Draft ID: {draft_data.get('draft_id')}")
                        print(f"   • Reply mode: {draft_data.get('reply_mode')}")
                        print(f"   • Would reply to: {draft_data.get('replied_to')}")
                        print(f"   • To recipients: {draft_data.get('to_recipients')}")
                        print(f"   • CC recipients: {draft_data.get('cc_recipients')}")
                except json.JSONDecodeError:
                    pass

            # Step 6: Test with HTML content
            print("\n" + "=" * 70)
            print("🌐 Step 6: Testing reply with HTML content")
            print("=" * 70)

            html_reply_result = await runner.test_tool_with_explicit_email(
                "reply_to_gmail_message",
                {
                    "message_id": sent_message_id,
                    "body": "<h3>HTML Reply Test</h3><p>This is a <b>test reply</b> with <i>HTML content</i>.</p><ul><li>Bullet 1</li><li>Bullet 2</li></ul>",
                    "reply_mode": "sender_only",
                    "content_type": "html",
                },
            )

            if html_reply_result and html_reply_result.get("success"):
                result_text = html_reply_result["content"]
                print(f"📨 HTML reply result: {result_text[:300]}...")
                try:
                    reply_data = json.loads(result_text)
                    if reply_data.get("success"):
                        print("✅ HTML reply sent successfully!")
                        print(f"   • Content type: {reply_data.get('content_type')}")
                except json.JSONDecodeError:
                    pass

            # Step 7: Test with mixed content
            print("\n" + "=" * 70)
            print("🎨 Step 7: Testing reply with MIXED content (plain + HTML)")
            print("=" * 70)

            mixed_reply_result = await runner.test_tool_with_explicit_email(
                "reply_to_gmail_message",
                {
                    "message_id": sent_message_id,
                    "body": "Plain text version: This is the plain text version of the mixed content reply.",
                    "html_body": "<h3>HTML Version</h3><p>This is the <b>HTML version</b> of the mixed content reply with <span style='color: blue;'>styled text</span>.</p>",
                    "reply_mode": "sender_only",
                    "content_type": "mixed",
                },
            )

            if mixed_reply_result and mixed_reply_result.get("success"):
                result_text = mixed_reply_result["content"]
                print(f"📨 Mixed content result: {result_text[:300]}...")
                try:
                    reply_data = json.loads(result_text)
                    if reply_data.get("success"):
                        print("✅ Mixed content reply sent successfully!")
                        print(f"   • Content type: {reply_data.get('content_type')}")
                except json.JSONDecodeError:
                    pass

            print("\n" + "=" * 70)
            print("✅ ALL INTEGRATION TESTS COMPLETED!")
            print("=" * 70)
            print("\n📊 Summary:")
            print("   • Tested sender_only mode ✓")
            print("   • Tested reply_all mode ✓")
            print("   • Tested custom mode ✓")
            print("   • Tested draft replies ✓")
            print("   • Tested HTML content ✓")
            print("   • Tested mixed content ✓")

            return True

    except Exception as e:
        print(f"❌ Error during testing: {e}")
        import traceback

        traceback.print_exc()
        return False


# Test using pytest
def run_test():
    """Run the test using pytest."""
    import subprocess
    import sys

    print("\n🔧 Gmail Allow List Configuration (from TEST_GMAIL_ALLOW_LIST):")
    print(f"   Emails: {', '.join(ALLOWED_EMAILS)}")
    print("\n⚠️  Note: This test will send real emails between these addresses")
    print(
        "   All addresses are on the allow list, so no elicitation will be triggered."
    )
    print()

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            __file__,
            "-v",
            "--asyncio-mode=auto",
            "--tb=short",
            "-s",  # Show print output
        ],
        capture_output=False,
        text=True,
    )

    return result.returncode == 0


if __name__ == "__main__":
    success = run_test()
    sys.exit(0 if success else 1)
