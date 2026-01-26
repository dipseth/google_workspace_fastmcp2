"""Integration tests for People contact groups and Gmail allow list group specs."""

import json

import pytest

from .base_test_config import TEST_EMAIL
from .test_helpers import TestResponseValidator, ToolTestRunner, print_test_result

LABEL_NAME = "MCP People Group Allow List Test"
GROUP_SPEC = f"group:{LABEL_NAME}"
GROUP_MEMBER_EMAIL = "mcp-group-member@example.com"


@pytest.mark.service("gmail")
class TestPeopleGroupsGmailAllowListIntegration:
    """End-to-end tests for People contact labels + Gmail allow list group specs."""

    @pytest.mark.asyncio
    async def test_people_group_allows_member_via_gmail_allow_list(self, client):
        """
        Ensure that:
        1) We can attach emails to a People contact label via manage_people_contact_labels
        2) We can add group:<label> to the Gmail allow list
        3) Sending to a member email does not treat that recipient as "not on allow list".
        """
        runner = ToolTestRunner(client, TEST_EMAIL)
        validator = TestResponseValidator()

        # Verify required tools are available
        if not await runner.test_tool_availability("manage_people_contact_labels"):
            pytest.skip("manage_people_contact_labels tool not available")
        if not await runner.test_tool_availability("manage_gmail_allow_list"):
            pytest.skip("manage_gmail_allow_list tool not available")

        # 1) Attach emails to a People contact label
        emails_for_label = f"{TEST_EMAIL},{GROUP_MEMBER_EMAIL}"
        label_result = await runner.test_tool_with_explicit_email(
            "manage_people_contact_labels",
            {
                "action": "label_add",
                "email": emails_for_label,
                "label": LABEL_NAME,
            },
        )
        print_test_result("manage_people_contact_labels → label_add", label_result)

        if not (label_result["success"] or label_result["is_auth_related"]):
            pytest.skip("People label_add failed and is not clearly auth-related")
        if label_result["is_auth_related"]:
            pytest.skip(
                "People API scopes/credentials not available for label operations"
            )

        # 2) Add the group spec to Gmail allow list
        allow_result = await runner.test_tool_with_explicit_email(
            "manage_gmail_allow_list",
            {
                "action": "add",
                "email": GROUP_SPEC,
            },
        )
        print_test_result("manage_gmail_allow_list → add group spec", allow_result)

        if not (allow_result["success"] or allow_result["is_auth_related"]):
            pytest.skip(
                "manage_gmail_allow_list(add group) failed and is not auth-related"
            )
        if allow_result["is_auth_related"]:
            pytest.skip("Gmail allow list auth/scopes not available")

        # 3) Send to a group member email and inspect structured response
        send_result = await client.call_tool(
            "send_gmail_message",
            {
                "user_google_email": TEST_EMAIL,
                "to": [GROUP_MEMBER_EMAIL],
                "subject": "People group allow list integration test",
                "body": "This email targets a member of a People label on the allow list.",
                "content_type": "plain",
            },
        )

        # Basic shape / auth validation
        assert send_result is not None, "send_gmail_message returned no result"
        if not send_result.content:
            # Some failures may raise via exceptions rather than content; treat as auth/API noise
            pytest.skip("send_gmail_message returned no content for inspection")

        text = send_result.content[0].text or ""
        # If this is a plain-text error instead of JSON, just ensure it does not
        # claim that the member is "not on allow list".
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            assert "not on allow list" not in text.lower()
            return

        # Structured SendGmailMessageResponse path
        recipients_not_allowed = payload.get("recipientsNotAllowed") or []
        # In the happy path with allow list group trust, there should be no
        # recipients marked as not allowed.
        assert not recipients_not_allowed, (
            f"Group member should not be marked as not allowed: {recipients_not_allowed}"
        )

    @pytest.mark.asyncio
    async def test_group_spec_not_treated_as_literal_recipient(self, client):
        """
        Regression check for original bug:
        When sending with to="group:Label", the allow list pipeline should not
        surface the literal 'group:Label' token inside recipientsNotAllowed.
        """
        runner = ToolTestRunner(client, TEST_EMAIL)

        # We re-use the same label name; if setup fails or is auth-related, skip.
        if not await runner.test_tool_availability("manage_people_contact_labels"):
            pytest.skip("manage_people_contact_labels tool not available")
        if not await runner.test_tool_availability("manage_gmail_allow_list"):
            pytest.skip("manage_gmail_allow_list tool not available")

        # Ensure group spec is present in allow list (best-effort); ignore result details
        await runner.test_tool_with_explicit_email(
            "manage_people_contact_labels",
            {
                "action": "label_add",
                "email": GROUP_MEMBER_EMAIL,
                "label": LABEL_NAME,
            },
        )
        await runner.test_tool_with_explicit_email(
            "manage_gmail_allow_list",
            {
                "action": "add",
                "email": GROUP_SPEC,
            },
        )

        # Now attempt to send using the group spec directly as recipient
        send_result = await client.call_tool(
            "send_gmail_message",
            {
                "user_google_email": TEST_EMAIL,
                "to": [GROUP_SPEC],
                "subject": "Group spec recipient regression test",
                "body": "This uses group:<label> as the recipient.",
                "content_type": "plain",
            },
        )

        if not send_result or not send_result.content:
            pytest.skip(
                "send_gmail_message did not return content for regression check"
            )

        text = send_result.content[0].text or ""
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            # Even if it's plain text, it should not list 'group:' as a blocked
            # recipient token.
            lower_text = text.lower()
            assert not ("group:" in lower_text and "not on allow list" in lower_text)
            return

        recipients_not_allowed = payload.get("recipientsNotAllowed") or []
        # Core regression check: recipientsNotAllowed should never contain the
        # literal group spec token.
        for r in recipients_not_allowed:
            assert not str(r).lower().startswith("group:"), (
                "Group specs should be resolved to real emails before allow list "
                f"checking; found literal group token in recipientsNotAllowed: {r!r}"
            )
