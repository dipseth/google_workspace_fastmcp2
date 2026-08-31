"""Tests for reusable email templates (``gmail/email_templates.py``).

Everything runs in-process against a real Jinja environment on a temp
templates dir — no Gmail, no network. Covers: literal serialisation, merge and
placeholder semantics, EmailSpec ⇄ HTML round-trip, save/load/list/delete,
persistence across a "restart", MIME sources, and the compose integration.
"""

from __future__ import annotations

import json
from email.message import EmailMessage
from pathlib import Path

import pytest

from gmail import email_templates as et
from gmail.mjml_types import (
    ButtonBlock,
    Column,
    ColumnsBlock,
    DividerBlock,
    EmailSpec,
    FooterBlock,
    HeroBlock,
    TextBlock,
)
from middleware.filters.data_filters import (
    deep_merge,
    fill_placeholders,
    find_placeholders,
)


def _spec() -> EmailSpec:
    return EmailSpec(
        subject="Welcome aboard, Sam",
        preheader="Glad you're here",
        blocks=[
            HeroBlock(
                title="Welcome, Sam!",
                subtitle="Your account is ready",
                cta_text="Get started",
                cta_url="https://example.com/start?u=sam",
            ),
            TextBlock(text="Hi Sam, thanks for joining RiversUnlimited."),
            TextBlock(text="Your onboarding call is Tuesday 3pm."),
            ColumnsBlock(
                columns=[
                    Column(blocks=[TextBlock(text="Left")], width="50%"),
                    Column(
                        blocks=[ButtonBlock(text="Book", url="https://example.com/b")]
                    ),
                ]
            ),
            FooterBlock(text="You received this because you signed up."),
        ],
    )


@pytest.fixture
def store(tmp_path):
    """A real EnhancedTemplateMiddleware on an empty templates dir."""
    from middleware.template_middleware import EnhancedTemplateMiddleware

    mw = EnhancedTemplateMiddleware(
        enable_debug_logging=False, templates_dir=str(tmp_path)
    )
    et.set_template_store(mw)
    yield mw
    et.set_template_store(None)


# ---------------------------------------------------------------------------
# Jinja literal serialisation
# ---------------------------------------------------------------------------


def test_to_jinja_literal_roundtrips_hostile_strings(store):
    env = store.jinja_env_manager.get_environment()
    data = {
        "text": 'He said "hi" {{ not_jinja }} {% nor this %} {# nor #} \\ end',
        "unicode": "Welcome — ✨ ×2 🎉",
        "lines": "a\nb\tc",
        "n": 3,
        "f": 1.5,
        "flag": True,
        "nothing": None,
        "items": [{"k": "v"}, [1, 2]],
    }
    rendered = env.from_string(
        "{{ x | tojson }}".replace("x", et.to_jinja_literal(data))
    ).render()
    assert json.loads(rendered) == data


# ---------------------------------------------------------------------------
# deep_merge / placeholders
# ---------------------------------------------------------------------------


def test_deep_merge_patches_items_index_wise():
    base = {"TextBlock": {"_items": [{"text": "a"}, {"text": "b"}]}, "k": 1}
    over = {"TextBlock": {"_items": [{}, {"text": "B", "color": "#fff"}]}, "k": 2}
    merged = deep_merge(base, over)
    assert merged == {
        "TextBlock": {"_items": [{"text": "a"}, {"text": "B", "color": "#fff"}]},
        "k": 2,
    }
    assert base["TextBlock"]["_items"][1] == {"text": "b"}  # not mutated
    assert deep_merge(base, None) == base
    assert deep_merge([1], [2, 3]) == [2, 3]


def test_placeholder_mapping_prefers_longest_literal():
    value = {"a": "Hi Sam Rivers and Sam", "b": ["Sam & Co"]}
    out, infos = et.apply_placeholder_mapping(
        value, {"Sam": "first_name", "Sam Rivers": "full_name"}
    )
    assert out["a"] == "Hi [[full_name]] and [[first_name]]"
    assert out["b"] == ["[[first_name]] & Co"]
    assert {i.name for i in infos} == {"first_name", "full_name"}

    html, _ = et.apply_placeholder_mapping(
        "<p>Sam &amp; Co</p>", {"Sam & Co": "company"}, html_mode=True
    )
    assert html == "<p>[[company]]</p>"


def test_auto_placeholders_name_fields_descriptively():
    _, params = et.spec_to_dsl_and_params(_spec())
    out, infos = et.apply_auto_placeholders(params)
    names = [i.name for i in infos]
    assert names[:4] == ["hero_title", "hero_subtitle", "hero_cta_text", "hero_cta_url"]
    assert "paragraph_1" in names and "paragraph_3" in names  # 3 text blocks
    assert "button_text" in names and "button_url" in names  # single button
    assert out["FooterBlock"]["_items"][0]["text"].startswith("You received")
    assert infos[0].example == "Welcome, Sam!"


def test_fill_and_find_placeholders():
    obj = {"s": "Hi [[name]], see [[ when ]]", "l": ["[[name]]"]}
    assert find_placeholders(obj) == ["name", "when"]
    filled = fill_placeholders(obj, {"name": "Sam"})
    assert filled == {"s": "Hi Sam, see [[ when ]]", "l": ["Sam"]}
    assert find_placeholders(filled) == ["when"]


# ---------------------------------------------------------------------------
# EmailSpec ⇄ HTML / DSL
# ---------------------------------------------------------------------------


def test_embed_and_extract_spec_roundtrip():
    spec = _spec()
    html = "<html><body><p>hi</p></body></html>"
    out = et.embed_email_spec(html, spec)
    assert out.index("<!--gws-email-spec:") < out.index("</body>")
    assert "--" not in out.split("<!--gws-email-spec:")[1].split("-->")[0]
    recovered = et.extract_embedded_spec(out)
    assert EmailSpec(**recovered).model_dump() == spec.model_dump()
    assert et.strip_embedded_spec(out) == html
    assert et.extract_embedded_spec("<p>no comment</p>") is None
    assert et.extract_embedded_spec("<!--gws-email-spec:!!notb64-->") is None


def test_spec_to_dsl_and_params_matches_builder_order():
    dsl, params = et.spec_to_dsl_and_params(_spec())
    assert dsl == (
        "EmailSpec[HeroBlock, TextBlock×2, "
        "ColumnsBlock[Column[TextBlock], Column[ButtonBlock]], FooterBlock]"
    )
    # Column inner blocks are appended in traversal order after the top-level ones
    assert [i["text"] for i in params["TextBlock"]["_items"]] == [
        "Hi Sam, thanks for joining RiversUnlimited.",
        "Your onboarding call is Tuesday 3pm.",
        "Left",
    ]
    assert params["Column"]["_items"] == [{"width": "50%"}, {}]
    assert params["preheader"] == "Glad you're here"
    assert "block_type" not in params["HeroBlock"]["_items"][0]


def test_dsl_and_params_rebuild_equivalent_spec():
    """The normalised form must feed straight back into the compose builder."""
    from gmail.compose import _build_email_spec_from_dsl
    from gmail.email_wrapper_api import parse_email_dsl

    spec = _spec()
    dsl, params = et.spec_to_dsl_and_params(spec)
    parsed = parse_email_dsl(dsl)
    assert parsed.is_valid, parsed.issues
    rebuilt = _build_email_spec_from_dsl(parsed, dict(params), f"{dsl} {spec.subject}")
    assert rebuilt.subject == spec.subject
    assert [type(b).__name__ for b in rebuilt.blocks] == [
        type(b).__name__ for b in spec.blocks
    ]
    assert rebuilt.blocks[0].title == "Welcome, Sam!"
    cols = rebuilt.blocks[3]
    assert [type(b).__name__ for c in cols.columns for b in c.blocks] == [
        "TextBlock",
        "ButtonBlock",
    ]
    assert cols.columns[0].width == "50%"
    assert cols.columns[1].blocks[0].url == "https://example.com/b"


# ---------------------------------------------------------------------------
# Save / load / list / delete
# ---------------------------------------------------------------------------


def test_save_load_list_delete_roundtrip(store, tmp_path):
    source = et.source_from_spec(_spec(), {"type": "compose"})
    meta = et.save_email_template(
        "Welcome Series",
        source,
        description="New user welcome",
        placeholders={"Sam": "recipient_name", "Tuesday 3pm": "call_time"},
    )
    assert meta["name"] == "welcome_series"
    assert meta["kind"] == "blocks"
    assert [p["name"] for p in meta["placeholders"]] == ["recipient_name", "call_time"]
    assert meta["block_counts"] == {
        "HeroBlock": 1,
        "TextBlock": 3,
        "ButtonBlock": 1,
        "FooterBlock": 1,
    }
    assert 'compose_dynamic_email(template="welcome_series"' in meta["usage"]
    j2 = tmp_path / "dynamic" / "welcome_series.j2"
    assert j2.exists() and j2.read_text().startswith(et.TEMPLATE_MARKER)

    loaded = et.load_email_template("welcome_series")
    assert loaded.subject == "Welcome aboard, [[recipient_name]]"
    assert (
        loaded.params["HeroBlock"]["_items"][0]["title"]
        == "Welcome, [[recipient_name]]!"
    )
    assert loaded.params["HeroBlock"]["_items"][0]["cta_url"] == (
        "https://example.com/start?u=sam"  # case-sensitive: 'sam' untouched
    )
    assert loaded.params["TextBlock"]["_items"][1]["text"] == (
        "Your onboarding call is [[call_time]]."
    )

    listed = et.list_email_templates()
    assert [t["name"] for t in listed] == ["welcome_series"]
    assert listed[0]["description"] == "New user welcome"

    # The template is a first-class macro too.
    env = store.jinja_env_manager.get_environment()
    out = env.from_string(
        "{{ welcome_series(mode='params', values={'recipient_name': 'Ada'}) }}"
    ).render()
    assert json.loads(out)["HeroBlock"]["_items"][0]["title"] == "Welcome, Ada!"
    assert "welcome_series" in store.macro_manager.get_macro_registry()

    with pytest.raises(et.EmailTemplateError, match="already exists"):
        et.save_email_template("welcome_series", source)
    et.save_email_template("welcome_series", source, overwrite=True)

    assert et.delete_email_template("welcome_series") is True
    assert not j2.exists()
    assert et.list_email_templates() == []
    with pytest.raises(et.EmailTemplateError, match="No email template"):
        et.load_email_template("welcome_series")


def test_save_refuses_to_shadow_non_template_macro(store):
    store.macro_manager.add_dynamic_macro(
        "plain_macro", "{% macro plain_macro() %}x{% endmacro %}"
    )
    with pytest.raises(et.EmailTemplateError, match="non-template macro"):
        et.save_email_template(
            "plain_macro", et.source_from_spec(_spec(), {"type": "compose"})
        )
    assert et.list_email_templates() == []  # plain macros are not templates


def test_templates_survive_restart(store, tmp_path):
    et.save_email_template(
        "restart_me", et.source_from_spec(_spec(), {"type": "compose"})
    )
    from middleware.template_middleware import EnhancedTemplateMiddleware

    fresh = EnhancedTemplateMiddleware(
        enable_debug_logging=False, templates_dir=str(tmp_path)
    )
    et.set_template_store(fresh)
    info = fresh.macro_manager.get_macro_registry()["restart_me"]
    assert info["source"] == "dynamic" and info["persisted"] is True
    assert [t["name"] for t in et.list_email_templates()] == ["restart_me"]
    assert et.load_email_template("restart_me").dsl.startswith("EmailSpec[")
    assert et.delete_email_template("restart_me") is True
    assert not (tmp_path / "dynamic" / "restart_me.j2").exists()


def test_fill_email_template_reports_missing(store):
    et.save_email_template(
        "fill_me",
        et.source_from_spec(_spec(), {"type": "compose"}),
        placeholders={"Sam": "recipient_name", "Tuesday 3pm": "call_time"},
    )
    loaded = et.load_email_template("fill_me")
    filled = et.fill_email_template(
        loaded,
        values={"recipient_name": "Ada"},
        overrides={"TextBlock": {"_items": [{"text": "Patched opener"}]}},
    )
    assert filled.subject == "Welcome aboard, Ada"
    assert filled.params["TextBlock"]["_items"][0]["text"] == "Patched opener"
    assert filled.params["TextBlock"]["_items"][1]["text"] == (
        "Your onboarding call is [[call_time]]."
    )
    assert filled.missing == ["call_time"]


# ---------------------------------------------------------------------------
# MIME sources (drafts / sent mail)
# ---------------------------------------------------------------------------


def _mime(html: str | None, plain: str = "plain body", subject: str = "Subj"):
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = "me@example.com"
    msg.set_content(plain)
    if html is not None:
        msg.add_alternative(html, subtype="html")
    return msg


def test_source_from_mime_recovers_blocks_from_composed_email():
    spec = _spec()
    html = et.embed_email_spec("<html><body>rendered</body></html>", spec)
    source = et.source_from_mime(_mime(html), {"type": "draft", "id": "r1"})
    assert source.kind == "blocks"
    assert source.subject == spec.subject
    assert source.dsl.startswith("EmailSpec[HeroBlock")
    assert source.origin == {"type": "draft", "id": "r1", "recovered_spec": True}


def test_source_from_mime_falls_back_to_html_and_plain():
    html_src = et.source_from_mime(
        _mime("<p>Hello <b>Sam</b></p>", subject="Hi Sam"), {"type": "message"}
    )
    assert html_src.kind == "html"
    assert html_src.subject == "Hi Sam"
    assert "<b>Sam</b>" in html_src.html

    plain_src = et.source_from_mime(_mime(None, plain="a < b\nline 2"), {})
    assert plain_src.kind == "html"
    assert "a &lt; b" in plain_src.html and "pre-wrap" in plain_src.html


def test_save_html_template_with_placeholders(store):
    source = et.source_from_mime(
        _mime("<p>Hello <b>Sam</b>, invoice #4471 is due.</p>", subject="Invoice 4471"),
        {"type": "message", "id": "m1"},
    )
    meta = et.save_email_template(
        "invoice_note",
        source,
        placeholders={"Sam": "customer_name", "4471": "invoice_number"},
        auto_placeholders=True,  # ignored for html kind
    )
    assert meta["kind"] == "html"
    assert [p["name"] for p in meta["placeholders"]] == [
        "invoice_number",
        "customer_name",
    ]
    loaded = et.load_email_template("invoice_note")
    assert loaded.subject == "Invoice [[invoice_number]]"
    filled = et.fill_email_template(
        loaded, {"customer_name": "Ada", "invoice_number": "9"}
    )
    assert filled.html == "<p>Hello <b>Ada</b>, invoice #9 is due.</p>"
    assert filled.missing == []


# ---------------------------------------------------------------------------
# compose_dynamic_email integration (tool registered on a bare FastMCP)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_compose_dynamic_email_uses_template(store, monkeypatch):
    from fastmcp import Client, FastMCP

    import gmail.compose as compose

    calls = []

    async def fake_draft(**kwargs):
        calls.append(kwargs)
        return {
            "success": True,
            "draft_id": "r-1",
            "subject": kwargs["subject"],
            "content_type": "html",
            "has_recipients": True,
            "recipient_count": 1,
            "userEmail": "me@example.com",
        }

    monkeypatch.setattr(compose, "draft_gmail_message", fake_draft)

    et.save_email_template(
        "tpl_compose",
        et.source_from_spec(_spec(), {"type": "compose"}),
        placeholders={"Sam": "recipient_name", "Tuesday 3pm": "call_time"},
    )

    mcp = FastMCP("t")
    compose.setup_compose_tools(mcp)
    async with Client(mcp) as client:
        # Draft with one placeholder unfilled → draft created, warning attached.
        res = await client.call_tool(
            "compose_dynamic_email",
            {
                "template": "tpl_compose",
                "template_values": {"recipient_name": "Ada"},
                "email_params": {"TextBlock": {"_items": [{"text": "New opener"}]}},
                "to": "ada@example.com",
            },
        )
        data = json.loads(res.content[0].text)
        assert data["success"] is True, data
        assert "[[call_time]]" in data["warning"]
        spec = calls[-1]["email_spec"]
        assert spec.subject == "Welcome aboard, Ada"
        assert spec.blocks[0].title == "Welcome, Ada!"
        assert spec.blocks[1].text == "New opener"
        assert "[[call_time]]" in spec.blocks[2].text

        # Sending with unfilled placeholders is refused before delivery.
        res = await client.call_tool(
            "compose_dynamic_email",
            {
                "template": "tpl_compose",
                "template_values": {"recipient_name": "Ada"},
                "action": "send",
                "to": "ada@example.com",
            },
        )
        data = json.loads(res.content[0].text)
        assert data["success"] is False and "call_time" in data["error"]
        assert len(calls) == 1  # no delivery attempted

        # Subject override via plain email_description text.
        res = await client.call_tool(
            "compose_dynamic_email",
            {
                "template": "tpl_compose",
                "email_description": "Custom subject",
                "template_values": {"recipient_name": "Ada", "call_time": "Wed 9am"},
            },
        )
        data = json.loads(res.content[0].text)
        assert data["success"] is True and "warning" not in data
        assert calls[-1]["email_spec"].subject == "Custom subject"

        # Unknown template is a clean error.
        res = await client.call_tool("compose_dynamic_email", {"template": "nope"})
        assert json.loads(res.content[0].text)["success"] is False


@pytest.mark.asyncio
async def test_manage_email_templates_tool_save_from_inputs(store):
    from fastmcp import Client, FastMCP

    from gmail.email_templates_tool import setup_email_template_tools

    mcp = FastMCP("t")
    setup_email_template_tools(mcp)
    async with Client(mcp) as client:
        res = await client.call_tool(
            "manage_email_templates",
            {
                "action": "save",
                "name": "Quick Note",
                "email_description": "EmailSpec[HeroBlock, TextBlock] Hello Sam",
                "email_params": {
                    "HeroBlock": {"_items": [{"title": "Hey Sam"}]},
                    "TextBlock": {"_items": [{"text": "See you Friday."}]},
                },
                "placeholders": {"Sam": "recipient_name", "Friday": "day"},
            },
        )
        data = json.loads(res.content[0].text)
        assert data["success"], data
        tpl = data["template"]
        assert tpl["name"] == "quick_note"
        assert [p["name"] for p in tpl["placeholders"]] == ["recipient_name", "day"]
        assert tpl["params"]["TextBlock"]["_items"][0]["text"] == "See you [[day]]."

        res = await client.call_tool("manage_email_templates", {"action": "list"})
        data = json.loads(res.content[0].text)
        assert data["count"] == 1 and data["templates"][0]["name"] == "quick_note"

        res = await client.call_tool(
            "manage_email_templates", {"action": "get", "name": "quick_note"}
        )
        assert json.loads(res.content[0].text)["template"]["subject"] == (
            "Hello [[recipient_name]]"
        )

        res = await client.call_tool(
            "manage_email_templates", {"action": "save", "name": "x"}
        )
        data = json.loads(res.content[0].text)
        assert data["success"] is False and "needs a source" in data["error"]

        res = await client.call_tool(
            "manage_email_templates", {"action": "delete", "name": "quick_note"}
        )
        assert json.loads(res.content[0].text)["success"] is True
        assert not any(Path(p).exists() for p in [])  # keep Path import honest


# ---------------------------------------------------------------------------
# Feedback-widget regressions (live findings 2026-08-30)
# ---------------------------------------------------------------------------


def _feedback_button(action="positive"):
    return ButtonBlock(
        text="Yes, helpful",
        url=f"https://localhost:8002/email-feedback?eid=x&action={action}&sig=abc",
    )


def test_render_embed_excludes_injected_feedback_blocks(monkeypatch):
    """_maybe_append_feedback_blocks mutates in place — the embedded spec must
    still be the authored one, or templates recovered from sent mail inherit
    the widget and re-inject cumulatively."""
    import gmail.compose as compose

    def fake_feedback(spec, email_id=None):
        spec.blocks.extend(
            [
                DividerBlock(),
                TextBlock(text="Did this response answer your question?"),
                _feedback_button(),
                _feedback_button("negative"),
            ]
        )
        return spec

    monkeypatch.setattr(compose, "_maybe_append_feedback_blocks", fake_feedback)
    spec = _spec()
    authored = len(spec.blocks)
    try:
        _, html = compose._render_email_spec(spec.model_copy(deep=True))
    except ValueError as exc:
        pytest.skip(f"MJML renderer unavailable: {exc}")
    recovered = et.extract_embedded_spec(html)
    assert recovered is not None
    assert len(recovered["blocks"]) == authored
    assert not any("email-feedback" in json.dumps(b) for b in recovered["blocks"])
    # The rendered HTML itself still contains the widget for recipients.
    assert "email-feedback" in html


def test_strip_feedback_blocks_variants():
    # with_divider layout: divider + prompt + two buttons
    spec = _spec()
    spec.blocks.extend(
        [
            DividerBlock(),
            TextBlock(text="Did this response answer your question?"),
            _feedback_button(),
            _feedback_button("negative"),
        ]
    )
    assert et.strip_feedback_blocks(spec) == 4
    assert len(spec.blocks) == 5

    # text_link_pair layout: divider + single TextBlock with inline links
    spec = _spec()
    spec.blocks.extend(
        [
            DividerBlock(),
            TextBlock(
                text='<a href="https://h/email-feedback?eid=1&action=positive">Yes</a>'
            ),
        ]
    )
    assert et.strip_feedback_blocks(spec) == 2
    assert len(spec.blocks) == 5

    # No markers → untouched
    spec = _spec()
    assert et.strip_feedback_blocks(spec) == 0
    assert len(spec.blocks) == 5

    # Authored content after the marker → refuse to strip (conservative)
    spec = _spec()
    spec.blocks.extend([_feedback_button(), HeroBlock(title="Authored after")])
    assert et.strip_feedback_blocks(spec) == 0
    assert len(spec.blocks) == 7


def test_source_from_mime_strips_feedback_from_recovered_spec():
    spec = _spec()
    rendered_spec = spec.model_copy(deep=True)
    rendered_spec.blocks.extend(
        [
            DividerBlock(),
            TextBlock(text="Did this response answer your question?"),
            _feedback_button(),
            _feedback_button("negative"),
        ]
    )
    html = et.embed_email_spec("<html><body>x</body></html>", rendered_spec)
    source = et.source_from_mime(_mime(html), {"type": "draft", "id": "r9"})
    assert source.kind == "blocks"
    assert source.origin["stripped_feedback_blocks"] == 4
    assert source.dsl == et.spec_to_dsl_and_params(spec)[0]
    assert "email-feedback" not in json.dumps(source.params)


def test_usage_lists_every_placeholder(store):
    meta = et.save_email_template(
        "many_holes",
        et.source_from_spec(_spec(), {"type": "compose"}),
        auto_placeholders=True,
    )
    names = [p["name"] for p in meta["placeholders"]]
    assert len(names) >= 9  # hero×4, paragraph×3, button×2
    for n in names:
        assert n in meta["usage"], f"usage truncated: missing {n}"
        assert n in meta["macro_usage"], f"macro_usage truncated: missing {n}"


@pytest.mark.asyncio
async def test_compose_template_tolerates_stringified_params(store, monkeypatch):
    """Client bridges sometimes stringify dict params — JSON and Python-literal
    strings must still apply; garbage must be an explicit error, never a
    silent un-patched compose."""
    from fastmcp import Client, FastMCP

    import gmail.compose as compose

    calls = []

    async def fake_draft(**kwargs):
        calls.append(kwargs)
        return {
            "success": True,
            "draft_id": "r-2",
            "subject": kwargs["subject"],
            "content_type": "html",
            "has_recipients": True,
            "recipient_count": 1,
            "userEmail": "me@example.com",
        }

    monkeypatch.setattr(compose, "draft_gmail_message", fake_draft)
    et.save_email_template(
        "tpl_str",
        et.source_from_spec(_spec(), {"type": "compose"}),
        placeholders={"Sam": "recipient_name", "Tuesday 3pm": "call_time"},
    )

    mcp = FastMCP("t")
    compose.setup_compose_tools(mcp)
    async with Client(mcp) as client:
        # Python-literal string (single quotes) — the json.loads-only path
        # used to drop this silently.
        res = await client.call_tool(
            "compose_dynamic_email",
            {
                "template": "tpl_str",
                "template_values": "{'recipient_name': 'Ada', 'call_time': 'Tue'}",
                "email_params": "{'TextBlock': {'_items': [{'text': 'Patched'}]}}",
            },
        )
        data = json.loads(res.content[0].text)
        assert data["success"] is True, data
        assert calls[-1]["email_spec"].blocks[1].text == "Patched"
        assert data["template_info"]["override_keys_applied"] == ["TextBlock"]
        assert data["template_info"]["values_applied"] == [
            "call_time",
            "recipient_name",
        ]

        # Envelope fields smuggled into email_params merge harmlessly but must
        # be reported as ignored, not as applied block overrides.
        res = await client.call_tool(
            "compose_dynamic_email",
            {
                "template": "tpl_str",
                "template_values": {"recipient_name": "Ada", "call_time": "Tue"},
                "email_params": {
                    "TextBlock": {"_items": [{"text": "Patched again"}]},
                    "to": "ada@example.com",
                    "from": "me@example.com",
                    "body": "junk",
                },
            },
        )
        data = json.loads(res.content[0].text)
        assert data["success"] is True, data
        info = data["template_info"]
        assert info["override_keys_applied"] == ["TextBlock"]
        assert info["override_keys_ignored"] == ["body", "from", "to"]
        assert calls[-1]["email_spec"].blocks[1].text == "Patched again"

        # Garbage string → explicit error, no silent un-patched draft.
        res = await client.call_tool(
            "compose_dynamic_email",
            {"template": "tpl_str", "email_params": "not a dict at all {"},
        )
        data = json.loads(res.content[0].text)
        assert data["success"] is False
        assert "email_params" in data["error"]
        assert len(calls) == 2  # the two successful drafts above; no third
