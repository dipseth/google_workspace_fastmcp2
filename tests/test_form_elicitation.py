"""Tests for generic form-mode prompts (tools/elicitation.prompt_for_form).

The Gmail send/forward confirmation rides the same two-round shape as the
OAuth prompt on 2026-07-28 connections: the tool returns a form-mode
``InputRequiredResult`` under a stable key, the client calls the tool again
with ``inputResponses``, and the re-run reads the answer back. Anything that is
not a form-capable client on a 2026-07-28 connection must come back
``unsupported`` so the caller keeps its ``ctx.elicit`` path or its fallback.
"""

import pytest

from tools import elicitation as oe


class _FakeElicitation:
    def __init__(self, form=None, url=None):
        self.form = form
        self.url = url


class _FakeCapabilities:
    def __init__(self, elicitation=None):
        self.elicitation = elicitation


class _FakeSession:
    def __init__(self, capabilities, protocol_version):
        self.client_capabilities = capabilities
        self.protocol_version = protocol_version


class _FakeAnswer:
    def __init__(self, action, content=None):
        self.action = action
        self.content = content


class _FakeContext:
    def __init__(self, session, input_responses=None):
        self.session = session
        self.input_responses = input_responses


def _bare_ctx(protocol_version, responses=None):
    """``elicitation: {}`` — what Claude Code declares."""
    return _FakeContext(
        _FakeSession(_FakeCapabilities(_FakeElicitation()), protocol_version),
        input_responses=responses,
    )


def _patch(monkeypatch, ctx):
    monkeypatch.setattr(oe, "_context", lambda: ctx)


SCHEMA = {
    "type": "object",
    "properties": {"action": {"type": "string", "enum": ["send", "cancel"]}},
    "required": ["action"],
}


# ── prompt_for_form ──────────────────────────────────────────────────────


def test_modern_form_capable_client_is_suspended_with_the_schema(monkeypatch):
    _patch(monkeypatch, _bare_ctx("2026-07-28"))
    prompt = oe.prompt_for_form("confirm", "Send it?", SCHEMA, request_state="s1")
    assert prompt.outcome == "suspended"
    assert prompt.handled is True
    request = prompt.suspend.input_requests["confirm"]
    assert request.params.mode == "form"
    assert request.params.message == "Send it?"
    assert request.params.requested_schema == SCHEMA
    assert prompt.suspend.request_state == "s1"


def test_handshake_era_client_is_unsupported(monkeypatch):
    """Pre-2026 connections push via ctx.elicit; the caller keeps that path."""
    _patch(monkeypatch, _bare_ctx("2025-11-25"))
    assert oe.prompt_for_form("confirm", "Send it?", SCHEMA).outcome == "unsupported"


def test_no_context_is_unsupported(monkeypatch):
    _patch(monkeypatch, None)
    assert oe.prompt_for_form("confirm", "Send it?", SCHEMA).outcome == "unsupported"


def test_client_without_elicitation_is_unsupported(monkeypatch):
    _patch(
        monkeypatch,
        _FakeContext(_FakeSession(_FakeCapabilities(None), "2026-07-28")),
    )
    assert oe.prompt_for_form("confirm", "Send it?", SCHEMA).outcome == "unsupported"


def test_suppressed_nested_call_is_unsupported(monkeypatch):
    _patch(monkeypatch, _bare_ctx("2026-07-28"))
    with oe.suppress_elicitation():
        assert (
            oe.prompt_for_form("confirm", "Send it?", SCHEMA).outcome == "unsupported"
        )


# ── answered_prompt ──────────────────────────────────────────────────────


def test_first_run_has_no_answer(monkeypatch):
    _patch(monkeypatch, _bare_ctx("2026-07-28"))
    assert oe.answered_prompt("confirm") is None


def test_re_run_returns_the_answer_under_its_key(monkeypatch):
    answer = _FakeAnswer("accept", {"action": "send"})
    _patch(monkeypatch, _bare_ctx("2026-07-28", responses={"confirm": answer}))
    assert oe.answered_prompt("confirm") is answer
    assert oe.answered_prompt("other") is None


def test_oauth_helper_still_reads_its_own_key(monkeypatch):
    answer = _FakeAnswer("accept")
    _patch(
        monkeypatch,
        _bare_ctx("2026-07-28", responses={oe.OAUTH_INPUT_KEY: answer}),
    )
    assert oe.answered_oauth_prompt() is answer


# ── Gmail confirmation adapter ───────────────────────────────────────────


@pytest.fixture
def compose():
    return pytest.importorskip("gmail.compose")


def test_gmail_schema_matches_email_action(compose):
    assert compose.EMAIL_ACTION_SCHEMA["properties"]["action"]["enum"] == [
        "send",
        "save_draft",
        "cancel",
    ]
    assert compose.EMAIL_ACTION_SCHEMA["required"] == ["action"]


def test_accepted_answer_carries_the_chosen_action(compose):
    response = compose._confirmation_answer(
        _FakeAnswer("accept", {"action": "save_draft"})
    )
    assert response.action == "accept"
    assert response.data.action == "save_draft"


def test_declined_answer_has_no_choice(compose):
    response = compose._confirmation_answer(_FakeAnswer("decline"))
    assert response.action == "decline"
    assert response.data.action is None


def test_no_answer_means_ask(compose):
    assert compose._confirmation_answer(None) is None


# ── Editable confirmation form ───────────────────────────────────────────

SPEC = {
    "subject": "Hello",
    "blocks": [
        {"block_type": "hero", "title": "Big title", "subtitle": "Sub"},
        {"block_type": "text", "text": "First paragraph"},
        {"block_type": "button", "text": "Go", "url": "https://x"},
    ],
}


def test_schema_offers_subject_then_sections_then_action(compose):
    schema = compose._confirmation_schema("Hello", "<html/>", "html", SPEC)
    keys = list(schema["properties"])
    assert keys[0] == "subject" and keys[-1] == "action"
    assert schema["properties"]["subject"]["default"] == "Hello"
    assert schema["properties"]["blocks.0.title"]["default"] == "Big title"
    assert schema["properties"]["blocks.1.text"]["maxLength"] == 20000
    assert schema["properties"]["action"]["enum"] == ["send", "save_draft", "cancel"]
    assert schema["required"] == ["action"]


def test_plain_email_offers_body_instead_of_sections(compose):
    schema = compose._confirmation_schema("Hi", "plain body", "plain", None)
    assert list(schema["properties"]) == ["subject", "body", "action"]
    assert schema["properties"]["body"]["default"] == "plain body"


def test_edits_patch_the_spec_and_re_render(compose, monkeypatch):
    rendered = {}

    def fake_render(spec, email_id=None):
        rendered["spec"] = spec
        return spec["subject"], "<html>" + spec["blocks"][1]["text"] + "</html>"

    monkeypatch.setattr(compose, "_render_email_spec", fake_render)
    subject, body, spec, changed = compose._apply_confirmation_edits(
        {"subject": "New subject", "blocks.1.text": "Edited paragraph"},
        "Hello",
        "<html>old</html>",
        "html",
        SPEC,
    )
    assert subject == "New subject"
    assert body == "<html>Edited paragraph</html>"
    assert spec["blocks"][1]["text"] == "Edited paragraph"
    assert rendered["spec"]["subject"] == "New subject"
    assert changed == 2


def test_untouched_form_changes_nothing(compose, monkeypatch):
    monkeypatch.setattr(
        compose, "_render_email_spec", lambda *a, **k: pytest.fail("no re-render")
    )
    subject, body, spec, changed = compose._apply_confirmation_edits(
        {"subject": "Hello", "blocks.1.text": "First paragraph"},
        "Hello",
        "<html>old</html>",
        "html",
        SPEC,
    )
    assert (subject, body, changed) == ("Hello", "<html>old</html>", 0)


COLUMNS_SPEC = {
    "subject": "Cols",
    "blocks": [
        {
            "block_type": "columns",
            "columns": [
                {
                    "blocks": [
                        {"block_type": "text", "text": "Left"},
                        {"block_type": "button", "text": "Go", "url": "https://x"},
                    ]
                },
                {"blocks": [{"block_type": "text", "text": "Right"}]},
            ],
        },
        {"block_type": "text", "text": "Outer"},
    ],
}


def test_columns_round_trip_keeps_inner_blocks(compose):
    """A plain model_dump keeps only base fields inside columns; the spec
    dict must re-validate or the re-run crashes."""
    from gmail.mjml_types import EmailSpec

    spec_data = compose._spec_dict(COLUMNS_SPEC)
    assert spec_data["blocks"][0]["columns"][0]["blocks"][0]["text"] == "Left"
    EmailSpec(**spec_data)  # re-validates
    schema = compose._confirmation_schema("Cols", "<html/>", "html", COLUMNS_SPEC)
    assert "blocks.0.columns.0.blocks.0.text" in schema["properties"]
    assert "blocks.0.columns.1.blocks.0.text" in schema["properties"]


def test_column_edit_re_renders(compose, monkeypatch):
    monkeypatch.setattr(
        compose,
        "_render_email_spec",
        lambda spec, email_id=None: (
            spec["subject"],
            spec["blocks"][0]["columns"][1]["blocks"][0]["text"],
        ),
    )
    _, body, spec, changed = compose._apply_confirmation_edits(
        {"blocks.0.columns.1.blocks.0.text": "Right, edited"},
        "Cols",
        "old",
        "html",
        COLUMNS_SPEC,
    )
    assert body == "Right, edited"
    assert changed == 1


def test_plain_body_edit_is_applied(compose):
    subject, body, spec, changed = compose._apply_confirmation_edits(
        {"body": "rewritten"}, "Hi", "original", "plain", None
    )
    assert (subject, body, spec, changed) == ("Hi", "rewritten", None, 1)


def test_mixed_email_with_html_part_keeps_body_read_only(compose):
    """Editing only the text alternative would leave it disagreeing with the
    HTML part, so a mixed email with html_body offers no body field."""
    schema = compose._confirmation_schema(
        "Hi", "plain", "mixed", None, html_body="<p>rich</p>"
    )
    assert list(schema["properties"]) == ["subject", "action"]
    _, body, _, changed = compose._apply_confirmation_edits(
        {"body": "rewritten"}, "Hi", "plain", "mixed", None, html_body="<p>rich</p>"
    )
    assert (body, changed) == ("plain", 0)


def test_mixed_email_without_html_part_behaves_as_plain(compose):
    schema = compose._confirmation_schema("Hi", "plain", "mixed", None)
    assert "body" in schema["properties"]


def test_answer_carries_edits(compose):
    response = compose._confirmation_answer(
        _FakeAnswer("accept", {"action": "send", "subject": "S", "blocks.0.title": "T"})
    )
    assert response.data.action == "send"
    assert response.edits == {"subject": "S", "blocks.0.title": "T"}


# ── Confirmation preview ─────────────────────────────────────────────────


def test_html_body_previews_as_visible_text(compose):
    body = (
        "<!doctype html><html><head><style>p{color:red}</style></head>"
        "<body><!--[if mso]>x<![endif]--><h1>Hello &amp; welcome</h1>"
        "<p>First line.<br/>Second line.</p><a href='https://x'>Open</a></body></html>"
    )
    assert (
        compose._preview_excerpt(body, "html")
        == "Hello & welcome\nFirst line.\nSecond line.\nOpen"
    )


def test_plain_body_is_passed_through_and_capped(compose):
    assert compose._preview_excerpt("hi there", "plain") == "hi there"
    long = "x" * 400
    assert compose._preview_excerpt(long, "plain") == "x" * 300 + "... [truncated]"
