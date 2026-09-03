"""Tests for the interactive Gmail draft app (``gmail/draft_app.py``).

These cover preview fidelity (the MJML output must survive verbatim),
lossless recipient rewriting, and MCP App wiring. No network access — every
test builds a real MIME message locally.
"""

import json
from email.message import EmailMessage
from types import SimpleNamespace

import pytest
from fastmcp import Client, FastMCP

from gmail.draft_app import (
    _PREVIEW_MAX_BYTES,
    _REMOTE_ATTR_RE,
    _REMOTE_CSS_URL_RE,
    DraftSnapshot,
    _b64url_decode,
    _build_draft_view,
    _decode_part_text,
    _embedded_spec,
    _ensure_html_document,
    _find_body_part,
    _parse_raw_message,
    _serialize,
    _set_header,
    _split_recipients,
    _update_draft_body,
    apply_content_edits,
    content_fields,
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
    filler = "<p>x</p>" * ((_PREVIEW_MAX_BYTES // 8) + 50_000)
    huge = "<html><body>" + filler + "</body></html>"
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
    # FastMCP 4 lists app-only tools and leaves visibility to the host; the
    # server applies the rule for clients without the UI extension.
    from middleware.app_visibility_middleware import AppVisibilityMiddleware

    mcp.add_middleware(AppVisibilityMiddleware())
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
        "gmail_draft_apply_edits": ["app"],
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


# ── View regression: components must attach to their container ──────


def _walk(node, out):
    """Flatten a serialized Prefab tree into a list of component dicts.

    Descends every nested value, not just ``children`` — ``If`` serializes to
    a ``Condition`` node that hides its subtree under ``cases[].children``.
    """
    if isinstance(node, dict):
        if node.get("type"):
            out.append(node)
        for value in node.values():
            if isinstance(value, (dict, list)):
                _walk(value, out)
    elif isinstance(node, list):
        for item in node:
            _walk(item, out)
    return out


def _components(app, type_name):
    return [n for n in _walk(app.to_json(), []) if n.get("type") == type_name]


def test_view_renders_every_recipient_input():
    """Regression: components built outside their `with` block vanish.

    Prefab attaches a component to the enclosing container at construction
    time, so constructing an Input first and merely referencing it inside the
    layout silently drops it — the card renders labels with no fields.
    """
    app = _build_draft_view(_make_draft(cc="c@example.com"), "me@example.com")
    names = {i.get("name") for i in _components(app, "Input")}
    assert names == {"subject", "to", "cc", "bcc"}


def test_view_prefills_inputs_from_the_draft():
    app = _build_draft_view(_make_draft(cc="c@example.com"), "me@example.com")
    by_name = {i["name"]: i.get("value") for i in _components(app, "Input")}
    assert by_name["to"] == "a@example.com, b@example.com"
    assert by_name["cc"] == "c@example.com"
    assert by_name["subject"] == "Quarterly ✨ Update"


def test_contact_picker_appears_only_with_contacts():
    without = _build_draft_view(_make_draft(), "me@example.com")
    assert _components(without, "Combobox") == []

    with_contacts = _build_draft_view(
        _make_draft(),
        "me@example.com",
        contacts=[{"name": "Ada Lovelace", "email": "ada@example.com"}],
    )
    options = _components(with_contacts, "ComboboxOption")
    assert [o["value"] for o in options] == ["ada@example.com"]
    assert "Ada Lovelace" in options[0]["label"]


def test_actions_send_edited_values_not_snapshot_values():
    """Buttons must interpolate live state, or edits are silently discarded."""
    payload = json.dumps(_build_draft_view(_make_draft(), "me@example.com").to_json())
    assert '"to": "{{ to }}"' in payload
    assert '"subject": "{{ subject }}"' in payload


# ── Remote image handling ───────────────────────────────────────────


@pytest.mark.parametrize(
    "markup,expected",
    [
        (
            '<img src="https://cdn.example.com/a.png">',
            ["https://cdn.example.com/a.png"],
        ),
        (
            '<td background="https://cdn.example.com/b.jpg">',
            ["https://cdn.example.com/b.jpg"],
        ),
        (
            '<v:image src="https://cdn.example.com/c.png"/>',
            ["https://cdn.example.com/c.png"],
        ),
    ],
)
def test_remote_attr_regex_covers_mjml_markup(markup, expected):
    assert [m.group(2) for m in _REMOTE_ATTR_RE.finditer(markup)] == expected


def test_remote_css_url_regex_covers_background_images():
    css = "background:url(https://cdn.example.com/hero.jpg) center/cover"
    assert [m.group(2) for m in _REMOTE_CSS_URL_RE.finditer(css)] == [
        "https://cdn.example.com/hero.jpg"
    ]


@pytest.mark.asyncio
async def test_unfetchable_remote_images_are_left_intact():
    """A failed fetch must leave the markup alone, never mangle it."""
    from gmail.draft_app import _inline_remote_images

    html = '<img src="https://invalid.invalid/nope.png">'
    out, unresolved = await _inline_remote_images(html)
    assert out == html
    assert unresolved == 1


@pytest.mark.asyncio
async def test_inlining_is_a_noop_without_remote_images():
    from gmail.draft_app import _inline_remote_images

    html = "<p>no images here</p>"
    assert await _inline_remote_images(html) == (html, 0)


# ── Degraded (text-only) card ───────────────────────────────────────


def test_text_only_app_omits_the_preview_iframe():
    """The whole point of degrading: none of the expensive payload ships."""
    from gmail.draft_app import _text_only_app

    app = _text_only_app(_make_draft(cc="c@example.com"), "Plain excerpt")
    assert _components(app, "Iframe") == []
    assert _components(app, "Image") == []


def test_text_only_app_keeps_the_identifying_details():
    """Degraded does not mean useless — the model still needs to act on it."""
    from gmail.draft_app import _text_only_app

    snapshot = _make_draft(cc="c@example.com")
    payload = json.dumps(
        _text_only_app(snapshot, "Plain excerpt").to_json(), ensure_ascii=False
    )
    assert snapshot.subject in payload
    assert "a@example.com" in payload
    assert "c@example.com" in payload
    assert "Plain excerpt" in payload
    assert snapshot.draft_id in payload


class TestContactPickerScope:
    """The contact roster must not ride along on every preview.

    `_load_contacts` returns up to 60 names and addresses, which the card
    renders as Combobox options. Those travel in structuredContent, so on a
    draft that already has recipients they are ~59% of the payload and put
    the user's address book in front of the model for no benefit.
    """

    class _Snapshot:
        subject = "Preview card test"
        draft_id = "r-1"
        cc: list = []
        bcc: list = []
        from_addr = "me@example.com"
        attachments: list = []

        def __init__(self, to):
            self.to = to

    @staticmethod
    def _card(to, contacts):
        from gmail.draft_app import _build_draft_view

        snap = TestContactPickerScope._Snapshot(to)
        return _build_draft_view(
            snap,
            "me@example.com",
            preview=("<html><body>hi</body></html>", None),
            contacts=contacts,
        ).to_json()

    def test_roster_dominates_the_card_when_included(self):
        import json

        contacts = [
            {"name": f"Contact Person {i}", "email": f"person{i}@company{i}.com"}
            for i in range(60)
        ]
        with_c = len(json.dumps(self._card(["a@b.com"], contacts)))
        without = len(json.dumps(self._card(["a@b.com"], [])))
        assert with_c > without * 2, "roster should be the bulk of the payload"

    def test_no_contact_options_when_roster_is_empty(self):
        import json

        card = json.dumps(self._card(["a@b.com"], []))
        assert "ComboboxOption" not in card
        assert "Add from contacts" not in card

    @pytest.mark.asyncio
    async def test_entry_tool_skips_the_lookup_when_recipients_exist(
        self, draft_app_server, monkeypatch
    ):
        """Drive the real tool: the People API call must not happen at all."""
        import gmail.draft_app as da

        mcp, _ = draft_app_server
        called = []

        async def _spy_contacts(email, limit=60):
            called.append(email)
            return [{"name": "Someone", "email": "someone@example.com"}]

        async def _fake_service(email):
            return object()

        async def _fake_load(service, draft_id):
            return self._Snapshot(["already@there.com"])

        monkeypatch.setattr(da, "_load_contacts", _spy_contacts)
        monkeypatch.setattr(da, "_load_draft", _fake_load)
        monkeypatch.setattr(da, "client_renders_ui", lambda: True)
        monkeypatch.setattr(
            "gmail.service._get_gmail_service_with_fallback", _fake_service
        )

        async def _preview_doc(self_):
            return ("<html><body>hi</body></html>", None)

        monkeypatch.setattr(
            self._Snapshot, "preview_document", _preview_doc, raising=False
        )

        async with Client(mcp) as client:
            result = await client.call_tool("preview_gmail_draft", {"draft_id": "r-1"})

        card = json.dumps(result.structured_content or {})
        assert called == [], "no People API call for a draft that has recipients"
        assert "ComboboxOption" not in card
        assert "already@there.com" in card


# ── Content editing (embedded EmailSpec) ────────────────────────────


def _make_spec_draft(**kwargs):
    """A draft whose HTML carries an embedded EmailSpec, plus that spec."""
    from gmail.email_templates import embed_email_spec
    from gmail.mjml_types import (
        ButtonBlock,
        Column,
        ColumnsBlock,
        EmailSpec,
        HeroBlock,
        TextBlock,
    )

    spec = EmailSpec(
        subject="Quarterly ✨ Update",
        blocks=[
            HeroBlock(
                title="Big News",
                subtitle="From the team",
                cta_text="Read more",
                cta_url="https://example.com/a",
            ),
            TextBlock(text="First paragraph"),
            TextBlock(text="Second paragraph"),
            ColumnsBlock(
                columns=[
                    Column(blocks=[TextBlock(text="Left cell")]),
                    Column(
                        blocks=[ButtonBlock(text="Go", url="https://example.com/b")]
                    ),
                ]
            ),
        ],
    )
    return _make_draft(html=embed_email_spec(MJML_HTML, spec), **kwargs), spec


def test_embedded_spec_roundtrips_through_mime():
    snapshot, _ = _make_spec_draft()
    spec_data = _embedded_spec(snapshot)
    assert spec_data is not None
    assert len(spec_data["blocks"]) == 4


def test_embedded_spec_absent_for_plain_drafts():
    assert _embedded_spec(_make_draft()) is None
    assert _embedded_spec(_make_draft(html=None)) is None


def test_content_fields_cover_prose_and_links_in_document_order():
    snapshot, _ = _make_spec_draft()
    fields = content_fields(_embedded_spec(snapshot))
    assert [(f["path"], f["label"]) for f in fields] == [
        ("blocks.0.title", "Hero title"),
        ("blocks.0.subtitle", "Hero subtitle"),
        ("blocks.0.cta_text", "Hero button text"),
        ("blocks.0.cta_url", "Hero button URL"),
        ("blocks.1.text", "Paragraph 1"),
        ("blocks.2.text", "Paragraph 2"),
        ("blocks.3.columns.0.blocks.0.text", "Paragraph 3"),
        ("blocks.3.columns.1.blocks.0.text", "Button text"),
        ("blocks.3.columns.1.blocks.0.url", "Button URL"),
    ]
    by_path = {f["path"]: f for f in fields}
    assert by_path["blocks.1.text"]["multiline"] is True
    assert by_path["blocks.0.title"]["multiline"] is False
    assert by_path["blocks.0.title"]["value"] == "Big News"


def test_content_fields_cover_image_urls():
    """Swapping an image is a value edit — src/alt/href must surface."""
    from gmail.email_templates import embed_email_spec
    from gmail.mjml_types import EmailSpec, ImageBlock

    spec = EmailSpec(
        subject="Pics",
        blocks=[
            ImageBlock(src="https://example.com/a.png", href="https://example.com"),
        ],
    )
    snapshot = _make_draft(html=embed_email_spec(MJML_HTML, spec))
    fields = content_fields(_embedded_spec(snapshot))
    assert [(f["path"], f["label"], f["value"]) for f in fields] == [
        ("blocks.0.src", "Image URL", "https://example.com/a.png"),
        # alt defaults to "" — still editable so alt text can be added
        ("blocks.0.alt", "Image alt text", ""),
        ("blocks.0.href", "Image link", "https://example.com"),
    ]
    spec_data = _embedded_spec(snapshot)
    assert apply_content_edits(spec_data, {"blocks.0.src": "https://x.com/b.webp"})
    assert spec_data["blocks"][0]["src"] == "https://x.com/b.webp"


def test_apply_content_edits_patches_leaf_values():
    from gmail.mjml_types import EmailSpec

    snapshot, _ = _make_spec_draft()
    spec_data = _embedded_spec(snapshot)
    changed = apply_content_edits(
        spec_data,
        {
            "blocks.0.title": "Bigger News",
            "blocks.3.columns.1.blocks.0.url": "https://example.com/c",
            "blocks.1.text": "First paragraph",  # unchanged — not counted
        },
    )
    assert changed == 2
    assert spec_data["blocks"][0]["title"] == "Bigger News"
    assert (
        spec_data["blocks"][3]["columns"][1]["blocks"][0]["url"]
        == "https://example.com/c"
    )
    EmailSpec(**spec_data)  # patched dict still validates


@pytest.mark.parametrize(
    "path",
    [
        "blocks.0.block_type",  # structure
        "blocks.0.title_size",  # styling
        "blocks",  # container, not a leaf
        "theme",  # not under blocks
        "blocks.99.title",  # out of range
        "blocks.0.nope",  # unknown field
        "blocks.3.columns.0.width",  # column layout
        "blocks.3.columns.0.blocks.0.padding",  # block styling
    ],
)
def test_apply_content_edits_rejects_non_content_paths(path):
    snapshot, _ = _make_spec_draft()
    spec_data = _embedded_spec(snapshot)
    with pytest.raises(ValueError):
        apply_content_edits(spec_data, {path: "x"})


def test_apply_content_edits_rejects_non_string_values():
    snapshot, _ = _make_spec_draft()
    with pytest.raises(ValueError):
        apply_content_edits(_embedded_spec(snapshot), {"blocks.0.title": 5})


def test_view_spec_draft_gets_the_content_editor():
    snapshot, _ = _make_spec_draft()
    app = _build_draft_view(snapshot, "me@example.com")
    data = app.to_json()
    payload = json.dumps(data)

    assert "gmail_draft_apply_edits" in payload
    # Inputs interpolate live state, keyed by index, mapped back to spec paths.
    assert '"blocks.0.title": "{{ edit_0 }}"' in payload
    assert '"blocks.3.columns.1.blocks.0.url": "{{ edit_8 }}"' in payload
    # Every field is seeded so untouched inputs never submit a raw template.
    assert data["state"]["edit_0"] == "Big News"
    assert data["state"]["edit_8"] == "https://example.com/b"
    assert data["state"]["show_edit"] is False
    # Paragraphs get a textarea, single-line prose an input.
    textarea_names = {t.get("name") for t in _components(app, "Textarea")}
    assert textarea_names == {"edit_4", "edit_5", "edit_6"}


def test_view_spec_draft_preview_is_reactive():
    snapshot, _ = _make_spec_draft()
    data = _build_draft_view(snapshot, "me@example.com").to_json()
    embeds = [n for n in _walk(data, []) if n.get("type") == "Embed"]
    assert embeds[0]["html"] == "{{ preview_doc }}"
    assert data["state"]["preview_doc"].lstrip().lower().startswith("<!doctype")
    # An empty preview in the result (error / no-op) must not blank the iframe.
    assert "{{ $result.preview || preview_doc }}" in json.dumps(data)


def test_view_without_spec_keeps_the_static_preview():
    data = _build_draft_view(_make_draft(), "me@example.com").to_json()
    payload = json.dumps(data)
    assert "gmail_draft_apply_edits" not in payload
    assert "preview_doc" not in data["state"]
    embeds = [n for n in _walk(data, []) if n.get("type") == "Embed"]
    assert embeds[0]["html"].lstrip().lower().startswith("<!doctype")


class _FakeGmailService:
    """Just enough of the Gmail client to capture ``drafts().update`` calls."""

    def __init__(self):
        self.updated: list[tuple[str, dict]] = []

    def users(self):
        return self

    def drafts(self):
        return self

    def update(self, userId, id, body):
        self.updated.append((id, body))
        return SimpleNamespace(execute=lambda: {})


@pytest.mark.asyncio
async def test_update_draft_body_swaps_bodies_losslessly():
    """New html/plain payloads; headers, attachments and images survive."""
    snapshot, _ = _make_spec_draft(with_attachment=True)
    new_html = (
        '<!doctype html><html><head><meta charset="utf-8"></head>'
        "<body><h1>Rewritten ✨</h1><!--gws-email-spec:QUJD--></body></html>"
    )
    service = _FakeGmailService()
    await _update_draft_body(service, snapshot, new_html, "Rewritten plain ✨")

    ((draft_id, body),) = service.updated
    assert draft_id == "r-test-1"
    assert body["message"]["threadId"] == "t1"

    msg = _parse_raw_message(_b64url_decode(body["message"]["raw"]))
    html = _decode_part_text(_find_body_part(msg, "html"))
    plain = _decode_part_text(_find_body_part(msg, "plain"))
    assert html.rstrip("\r\n") == new_html
    assert plain.rstrip("\r\n") == "Rewritten plain ✨"
    assert str(msg["Subject"]) == "Quarterly ✨ Update"
    assert str(msg["To"]) == "a@example.com, b@example.com"
    filenames = [
        part.get_filename()
        for part in msg.walk()
        if (part.get_content_disposition() or "") == "attachment"
    ]
    assert filenames == ["report.pdf"]
    cids = [
        part.get("Content-ID")
        for part in msg.walk()
        if part.get_content_type().startswith("image/")
    ]
    assert cids == ["<hero001>"]


@pytest.mark.asyncio
async def test_update_draft_body_requires_an_html_part():
    snapshot = _make_draft(html=None)
    with pytest.raises(ValueError):
        await _update_draft_body(_FakeGmailService(), snapshot, "<html></html>")
