"""Reading emails returns what the recipient sees: the HTML, as text.

A client read a designed email whose text/plain part was one line ("Your 4
originals polished… View in an HTML-capable client") while the HTML held the
whole list. ``_extract_message_body`` always returned the plain part, so the
tool showed only the line. Live testing also found prod-sent emails whose
plain part was a CSS-polluted conversion. The HTML is now the source of
truth; text/plain is the fallback when the HTML has no readable text.
"""

import base64
from pathlib import Path

from gmail.utils import _extract_message_body, _html_to_plain_text

ARTIFACTS = Path(__file__).parent / "artifacts"

DESIGNED_HTML = """<!doctype html><html><head><title>Haunts</title>
<style>.mj-column-per-100{width:100%!important}</style></head><body>
<!--[if mso]><table><tr><td><![endif]-->
<table><tr><td><h1>Your haunts</h1></td></tr>
<tr><td><p>1. Old Mill &amp; Lantern</p></td></tr>
<tr><td><p>2. Crypt Cafe</p></td></tr>
<tr><td><a href="https://example.com/grab">Grab list</a></td></tr>
</table></body></html>"""


def _b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode()


def _alternative(plain: str, html: str) -> dict:
    return {
        "mimeType": "multipart/alternative",
        "parts": [
            {"mimeType": "text/plain", "body": {"data": _b64(plain)}},
            {"mimeType": "text/html", "body": {"data": _b64(html)}},
        ],
    }


def test_stub_plain_part_falls_back_to_html():
    payload = _alternative(
        "Your 4 originals polished. View in an HTML-capable client.", DESIGNED_HTML
    )
    body = _extract_message_body(payload)
    assert "Old Mill & Lantern" in body
    assert "Crypt Cafe" in body
    assert "Grab list (https://example.com/grab)" in body
    assert "HTML-capable" not in body


def test_html_preferred_over_complete_plain_part():
    # Even a full plain part loses: senders' plain parts drift from the HTML
    # (e.g. old conversions that leaked CSS), and the HTML is what's shown.
    plain = "#outlook a { padding:0; }\nYour haunts\n1. Old Mill & Lantern"
    body = _extract_message_body(_alternative(plain, DESIGNED_HTML))
    assert body.startswith("Your haunts")
    assert "outlook" not in body


def test_plain_used_when_html_has_no_text():
    html = '<html><body><img src="banner.png"></body></html>'
    payload = _alternative("Big sale this weekend.", html)
    assert _extract_message_body(payload) == "Big sale this weekend."


def test_nested_multipart_mixed_with_attachment():
    payload = {
        "mimeType": "multipart/mixed",
        "parts": [
            _alternative("View this email in your browser.", DESIGNED_HTML),
            {
                "mimeType": "application/pdf",
                "filename": "x.pdf",
                "body": {"attachmentId": "a1"},
            },
        ],
    }
    assert "Crypt Cafe" in _extract_message_body(payload)


def test_html_only_message_drops_head_and_css():
    payload = {"mimeType": "text/html", "body": {"data": _b64(DESIGNED_HTML)}}
    body = _extract_message_body(payload)
    assert body.startswith("Your haunts")
    assert "mj-column" not in body
    assert "[if mso]" not in body


def test_plain_only_message_unchanged():
    payload = {"mimeType": "text/plain", "body": {"data": _b64("just text")}}
    assert _extract_message_body(payload) == "just text"


def test_mjml_render_converts_cleanly():
    html = (ARTIFACTS / "mjml_sample_email.html").read_text()
    text = _html_to_plain_text(html)
    assert text.startswith("Thanks for joining")
    assert "Get started (https://example.com/start)" in text
    assert "{" not in text  # no CSS
    assert "\n\n\n" not in text


def test_escaped_markup_stays_literal():
    assert _html_to_plain_text("<p>use &lt;b&gt; tags</p>") == "use <b> tags"


def test_link_label_equal_to_url_not_duplicated():
    html = '<a href="https://example.com">https://example.com</a>'
    assert _html_to_plain_text(html) == "https://example.com"


# --- parser edge cases (stdlib HTMLParser, not regex) ---


def test_gt_inside_attribute_does_not_break_tag():
    assert _html_to_plain_text('<p title="a > b">Hello</p>') == "Hello"


def test_image_alt_text_kept():
    html = '<a href="https://x.com/buy"><img alt="Buy now" src="a.png"></a>'
    assert _html_to_plain_text(html) == "Buy now (https://x.com/buy)"


def test_hidden_preheader_dropped():
    html = '<div style="display: none; max-height:0">Preview only</div><p>Body</p>'
    assert _html_to_plain_text(html) == "Body"
    assert _html_to_plain_text("<p hidden>secret</p><p>shown</p>") == "shown"


def test_pre_whitespace_preserved():
    html = "<p>x</p><pre>a    b\n    c</pre><p>y</p>"
    assert _html_to_plain_text(html) == "x\n\na    b\n    c\n\ny"


def test_source_newlines_are_spaces():
    assert _html_to_plain_text("<p>hello\n   world</p>") == "hello world"


def test_malformed_html_tolerated():
    assert _html_to_plain_text("<ul><li>one<li>two</ul><p>a<p>b") == (
        "• one\n• two\n\na\n\nb"
    )
    assert _html_to_plain_text("</div></td>text</span>") == "text"
    assert _html_to_plain_text("<a href=https://x.com>go</a>") == ("go (https://x.com)")
    # Unclosed <style> swallows the rest, as in a browser - but never leaks CSS.
    assert "color" not in _html_to_plain_text("<style>a{color:red}<p>Body</p>")


def test_part_charset_respected():
    raw = "Café — naïve".encode("windows-1252", errors="replace")
    payload = {
        "mimeType": "text/plain",
        "headers": [
            {"name": "Content-Type", "value": 'text/plain; charset="windows-1252"'}
        ],
        "body": {"data": base64.urlsafe_b64encode(raw).decode()},
    }
    assert _extract_message_body(payload) == "Café — naïve"


def test_unknown_charset_falls_back_to_utf8():
    payload = {
        "mimeType": "text/plain",
        "headers": [{"name": "Content-Type", "value": "text/plain; charset=x-bogus"}],
        "body": {"data": _b64("Café")},
    }
    assert _extract_message_body(payload) == "Café"


def test_block_inside_list_item_keeps_bullet_on_line():
    html = "<ul><li><p>one</p></li><li>two</li></ul><p>after</p>"
    assert _html_to_plain_text(html) == "• one\n\n• two\n\nafter"
