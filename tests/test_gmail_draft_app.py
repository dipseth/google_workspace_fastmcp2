"""Tests for the interactive Gmail draft app (``gmail/draft_app.py``).

These cover preview fidelity (the MJML output must survive verbatim),
lossless recipient rewriting, and MCP App wiring. No network access — every
test builds a real MIME message locally.
"""

import json
from email.message import EmailMessage

import pytest
from fastmcp import Client, FastMCP

from gmail.draft_app import (
    _PREVIEW_MAX_BYTES,
    DraftSnapshot,
    _b64url_decode,
    _build_draft_view,
    _ensure_html_document,
    _parse_raw_message,
    _serialize,
    _set_header,
    _split_recipients,
    create_gmail_draft_app,
)

MJML_HTML = (
    '<!doctype html><html xmlns:v="urn:schemas-microsoft-com:vml">'
    '<head><meta charset="utf-8">'
    '<style type="text/css">@media only screen and (max-width:600px)'
    "{.mj-column{width:100%!important}}</style></head>"
    '<body style="background:#f4f4f4">'
    '<!--[if mso | IE]><table role="presentation"><tr><td><![endif]-->'
    '<div class="mj-column"><h1>Quarterly ✨ Update</h1>'
    '<img src="cid:hero001" alt="hero">'
    '<a href="https://example.com">Read more</a></div>'
    "<!--[if mso | IE]></td></tr></table><![endif]-->"
    "</body></html>"
)


def _make_draft(
    *,
    html: str | None = MJML_HTML,
    plain: str = "Plain fallback",
    to: str = "a@example.com, b@example.com",
    cc: str = "",
    subject: str = "Quarterly ✨ Update",
    with_inline_image: bool = True,
    with_attachment: bool = False,
) -> DraftSnapshot:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = "me@example.com"
    msg["To"] = to
    if cc:
        msg["Cc"] = cc
    msg.set_content(plain)
    if html is not None:
        msg.add_alternative(html, subtype="html")
        if with_inline_image:
            msg.get_payload()[1].add_related(
                b"\x89PNG\r\n\x1a\n" + b"0" * 64,
                maintype="image",
                subtype="png",
                cid="<hero001>",
            )
    if with_attachment:
        msg.add_attachment(
            b"%PDF-1.4" + b"x" * 256,
            maintype="application",
            subtype="pdf",
            filename="report.pdf",
        )
    return DraftSnapshot(
        "r-test-1",
        {"message": {"id": "m1", "threadId": "t1"}},
        _parse_raw_message(msg.as_bytes()),
    )


# ── Preview fidelity ────────────────────────────────────────────────


def test_preview_preserves_mjml_output():
    """Doctype, <style>, media queries and MSO conditionals survive intact."""
    html, warning = _make_draft().preview_html()
    assert warning is None
    assert html.lstrip().lower().startswith("<!doctype")
    assert "@media only screen and (max-width:600px)" in html
    assert "<!--[if mso | IE]>" in html
    assert 'xmlns:v="urn:schemas-microsoft-com:vml"' in html
    assert "Quarterly ✨ Update" in html


def test_preview_inlines_cid_images():
    html, _ = _make_draft().preview_html()
    assert "data:image/png;base64," in html
    assert "cid:hero001" not in html


def test_preview_reports_unresolved_cid():
    """A cid: with no matching part is left alone and surfaced as a warning."""
    snapshot = _make_draft(with_inline_image=False)
    html, warning = snapshot.preview_html()
    assert "cid:hero001" in html
    assert warning is not None and "could not be resolved" in warning


def test_preview_falls_back_to_plain_text():
    html, warning = _make_draft(html=None, plain="line one\nline <two>").preview_html()
    assert warning is None
    assert "<pre" in html
    assert "line &lt;two&gt;" in html  # escaped, not injected


def test_preview_truncates_oversized_html():
    huge = "<html><body>" + ("<p>x</p>" * 200_000) + "</body></html>"
    html, warning = _make_draft(html=huge, with_inline_image=False).preview_html()
    assert warning is not None and "truncated" in warning
    assert len(html.encode("utf-8")) <= _PREVIEW_MAX_BYTES + 1024  # banner overhead


def test_ensure_html_document_wraps_fragments():
    wrapped = _ensure_html_document("<b>hi</b>")
    assert wrapped.lower().startswith("<!doctype html>")
    assert 'charset="utf-8"' in wrapped
    assert "<b>hi</b>" in wrapped


def test_ensure_html_document_injects_missing_charset():
    out = _ensure_html_document(
        "<html><head><title>t</title></head><body>x</body></html>"
    )
    assert '<meta charset="utf-8">' in out
    assert out.count("<head>") == 1


def test_ensure_html_document_leaves_declared_charset_alone():
    src = (
        '<html><head><meta charset="utf-8"><title>t</title></head><body>x</body></html>'
    )
    assert _ensure_html_document(src) == src


# ── Recipient handling ──────────────────────────────────────────────


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("a@x.com, b@x.com", ["a@x.com", "b@x.com"]),
        ("a@x.com;b@x.com", ["a@x.com", "b@x.com"]),
        ("a@x.com\nb@x.com", ["a@x.com", "b@x.com"]),
        ("  ", []),
        (None, []),
        (["a@x.com", " b@x.com "], ["a@x.com", "b@x.com"]),
    ],
)
def test_split_recipients(raw, expected):
    assert _split_recipients(raw) == expected


def test_header_rewrite_is_lossless():
    """Rewriting To/Cc/Bcc must not disturb the body or attachments."""
    snapshot = _make_draft(with_attachment=True)
    assert snapshot.attachments == ["report.pdf"]

    _set_header(snapshot.msg, "To", "new@example.com")
    _set_header(snapshot.msg, "Cc", "")
    _set_header(snapshot.msg, "Bcc", "hidden@example.com")

    round_tripped = DraftSnapshot(
        "r-test-1",
        {"message": {}},
        _parse_raw_message(_b64url_decode(_serialize(snapshot.msg))),
    )
    assert round_tripped.to == ["new@example.com"]
    assert round_tripped.cc == []
    assert round_tripped.bcc == ["hidden@example.com"]
    assert round_tripped.attachments == ["report.pdf"]

    html, _ = round_tripped.preview_html()
    assert "@media only screen and (max-width:600px)" in html
    assert "data:image/png;base64," in html


def test_serialize_uses_crlf_line_endings():
    snapshot = _make_draft()
    assert b"\r\n" in _b64url_decode(_serialize(snapshot.msg))


# ── View wiring ─────────────────────────────────────────────────────


def test_view_wires_all_three_actions():
    payload = json.dumps(_build_draft_view(_make_draft(), "me@example.com").to_json())
    for tool in ("gmail_draft_send", "gmail_draft_save", "gmail_draft_discard"):
        assert tool in payload


def test_view_preview_iframe_is_script_free():
    view = _build_draft_view(_make_draft(), "me@example.com").to_json()
    payload = json.dumps(view)
    assert '"type": "Embed"' in json.dumps(view, indent=1)
    assert "allow-scripts" not in payload


def test_view_seeds_recipient_state():
    state = _build_draft_view(
        _make_draft(cc="c@example.com"), "me@example.com"
    ).to_json()["state"]
    assert state["to"] == "a@example.com, b@example.com"
    assert state["cc"] == "c@example.com"
    assert state["show_cc"] is True
    assert state["done"] is False


def test_view_hides_cc_when_empty():
    state = _build_draft_view(_make_draft(), "me@example.com").to_json()["state"]
    assert state["show_cc"] is False


# ── MCP App registration ────────────────────────────────────────────


@pytest.fixture
def draft_app_server():
    mcp = FastMCP("test-gmail-draft")
    app = create_gmail_draft_app(mcp)
    assert app is not None, "prefab-ui must be installed for these tests"
    mcp.add_provider(app)
    return mcp, app


@pytest.mark.asyncio
async def test_only_entry_tool_is_model_visible(draft_app_server):
    mcp, _ = draft_app_server
    async with Client(mcp) as client:
        names = [t.name for t in await client.list_tools()]
    assert names == ["preview_gmail_draft"]


def test_backend_tools_are_app_scoped(draft_app_server):
    _, app = draft_app_server
    backend = {
        component.name: component.meta["ui"]["visibility"]
        for key, component in app._local._components.items()
        if key.startswith("tool:") and component.name != "preview_gmail_draft"
    }
    assert backend == {
        "gmail_draft_send": ["app"],
        "gmail_draft_save": ["app"],
        "gmail_draft_discard": ["app"],
    }


@pytest.mark.asyncio
async def test_renderer_resource_allows_remote_images(draft_app_server):
    """Email HTML pulls images from arbitrary CDNs — CSP must permit that."""
    mcp, _ = draft_app_server
    async with Client(mcp) as client:
        resources = await client.list_resources()
    domains = resources[0].meta["ui"]["csp"]["resourceDomains"]
    assert "https:" in domains and "data:" in domains
    assert "https://cdn.jsdelivr.net" in domains  # renderer default preserved
