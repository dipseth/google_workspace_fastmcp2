"""``content_type="mixed"`` is the default — without ``html_body`` it must mean plain.

A Desktop tester's first plain-text draft failed with "Parameter validation
error: missing html_body for mixed content". Nobody chose "mixed"; it is the
default, and a caller who only wrote a body has described a plain-text message.
Both ``send_gmail_message`` and ``draft_gmail_message`` now send that instead
of refusing.
"""

import base64
import email

import pytest
from fastmcp import Client, FastMCP

import gmail.compose as compose
from gmail.compose import draft_gmail_message, setup_compose_tools


class _FakeGmail:
    """Any attribute chain ends in execute(); bodies passed along the way are kept."""

    def __init__(self):
        self.bodies = []

    def __getattr__(self, _name):
        return self

    def __call__(self, *_args, **kwargs):
        if "body" in kwargs:
            self.bodies.append(kwargs["body"])
        return self

    def execute(self):
        return {
            "id": "r-1",
            "threadId": "t-1",
            "message": {"id": "m-1", "threadId": "t-1"},
        }


def _fields(out) -> dict:
    """draft_gmail_message hands back a dict; tolerate the model too."""
    return out if isinstance(out, dict) else out.model_dump()


def _mime(body: dict):
    raw = body["raw"] if "raw" in body else body["message"]["raw"]
    return email.message_from_bytes(base64.urlsafe_b64decode(raw + "=="))


@pytest.fixture
def gmail_api(monkeypatch):
    fake = _FakeGmail()

    async def _service(_email):
        return fake

    monkeypatch.setattr(compose, "_get_gmail_service_with_fallback", _service)
    return fake


class TestDraft:
    async def test_default_content_type_with_plain_body_drafts_plain_text(
        self, gmail_api
    ):
        out = await draft_gmail_message(
            subject="2.12 smoke",
            body="delete me",
            to="coach@example.com",
            user_google_email="me@example.com",
        )
        out = _fields(out)
        assert out["success"] is True, out.get("error")
        assert out["content_type"] == "plain"
        msg = _mime(gmail_api.bodies[-1])
        assert msg.get_content_type() == "text/plain"
        assert msg.get_payload(decode=True).decode() == "delete me"

    async def test_mixed_with_html_body_is_still_mixed(self, gmail_api):
        out = await draft_gmail_message(
            subject="s",
            body="plain",
            html_body="<p>rich</p>",
            to="coach@example.com",
            user_google_email="me@example.com",
        )
        out = _fields(out)
        assert out["success"] is True, out.get("error")
        assert out["content_type"] == "mixed"
        assert _mime(gmail_api.bodies[-1]).is_multipart()


class TestSend:
    async def test_default_content_type_with_plain_body_sends_plain_text(
        self, gmail_api, monkeypatch
    ):
        async def _all_allowed(*_a, **_k):
            return []

        monkeypatch.setattr(
            compose, "_resolve_recipients_and_check_allow_list", _all_allowed
        )
        mcp = FastMCP("compose-test")
        setup_compose_tools(mcp)
        async with Client(mcp) as client:
            result = await client.call_tool(
                "send_gmail_message",
                {
                    "subject": "hello",
                    "body": "just text",
                    "to": "coach@example.com",
                    "user_google_email": "me@example.com",
                },
            )
        out = result.structured_content
        assert out["success"] is True, out.get("error")
        assert out["contentType"] == "plain"
        assert _mime(gmail_api.bodies[-1]).get_content_type() == "text/plain"
