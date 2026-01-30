#!/usr/bin/env python3
"""
Test TextParagraph markdown capabilities against Google Chat webhook.

Tests:
1. TextParagraph with HTML (default)
2. TextParagraph with MARKDOWN textSyntax
3. DecoratedText with text parameter
4. Various markdown formatting options

Reference: https://developers.google.com/workspace/chat/api/reference/rest/v1/cards#textparagraph
"""

import json
import os
import sys
import time

import httpx

# Webhook URL from .env
WEBHOOK_URL = os.environ.get(
    "TEST_CHAT_WEBHOOK",
    "https://chat.googleapis.com/v1/spaces/AAQAKl_yP9Y/messages?key=AIzaSyDdI0hCZtE6vySjMm-WEfRq3CPzqKqqsHI&token=Ie8-brhWHA9kE_2JiqKRDhqjadPHK4RNe15UcWwLXDA"
)


def send_card(card_payload: dict, description: str = ""):
    """Send a card to the webhook and report result."""
    print(f"\n{'='*60}")
    print(f"TEST: {description}")
    print(f"{'='*60}")
    print(f"Payload:\n{json.dumps(card_payload, indent=2)[:500]}...")

    try:
        response = httpx.post(
            WEBHOOK_URL,
            json=card_payload,
            headers={"Content-Type": "application/json"},
            timeout=30.0,
        )

        if response.status_code == 200:
            print(f"✅ SUCCESS (status={response.status_code})")
            return True
        else:
            print(f"❌ FAILED (status={response.status_code})")
            print(f"Response: {response.text[:500]}")
            return False

    except Exception as e:
        print(f"❌ ERROR: {e}")
        return False


def test_textparagraph_html_default():
    """Test TextParagraph with HTML (default behavior)."""
    payload = {
        "cardsV2": [{
            "cardId": "test-html-default",
            "card": {
                "header": {
                    "title": "TextParagraph: HTML (Default)",
                    "subtitle": "textSyntax not set"
                },
                "sections": [{
                    "widgets": [{
                        "textParagraph": {
                            "text": "<b>Bold</b>, <i>Italic</i>, <u>Underline</u><br>"
                                    "<font color=\"#00FF00\">Green text</font>, "
                                    "<a href=\"https://google.com\">Link</a>"
                        }
                    }]
                }]
            }
        }]
    }
    return send_card(payload, "TextParagraph with HTML (default)")


def test_textparagraph_html_explicit():
    """Test TextParagraph with explicit HTML textSyntax."""
    payload = {
        "cardsV2": [{
            "cardId": "test-html-explicit",
            "card": {
                "header": {
                    "title": "TextParagraph: HTML (Explicit)",
                    "subtitle": "textSyntax: HTML"
                },
                "sections": [{
                    "widgets": [{
                        "textParagraph": {
                            "text": "<b>Bold</b>, <i>Italic</i>, <strike>Strikethrough</strike><br>"
                                    "<font color=\"#FF5733\">Orange text</font>",
                            "textSyntax": "HTML"
                        }
                    }]
                }]
            }
        }]
    }
    return send_card(payload, "TextParagraph with explicit HTML textSyntax")


def test_textparagraph_markdown():
    """Test TextParagraph with MARKDOWN textSyntax."""
    markdown_text = """**Bold text** and *italic text*

- Bullet point 1
- Bullet point 2
- Bullet point 3

`inline code`

[Click here](https://google.com)

> Blockquote text

~~Strikethrough~~"""

    payload = {
        "cardsV2": [{
            "cardId": "test-markdown",
            "card": {
                "header": {
                    "title": "TextParagraph: MARKDOWN",
                    "subtitle": "textSyntax: MARKDOWN"
                },
                "sections": [{
                    "widgets": [{
                        "textParagraph": {
                            "text": markdown_text,
                            "textSyntax": "MARKDOWN"
                        }
                    }]
                }]
            }
        }]
    }
    return send_card(payload, "TextParagraph with MARKDOWN textSyntax")


def test_textparagraph_markdown_code_block():
    """Test TextParagraph with markdown code blocks."""
    markdown_text = """Code example:

```python
def hello():
    print("Hello, World!")
```

Inline: `variable = 42`"""

    payload = {
        "cardsV2": [{
            "cardId": "test-markdown-code",
            "card": {
                "header": {
                    "title": "TextParagraph: Markdown Code",
                    "subtitle": "Testing code blocks"
                },
                "sections": [{
                    "widgets": [{
                        "textParagraph": {
                            "text": markdown_text,
                            "textSyntax": "MARKDOWN"
                        }
                    }]
                }]
            }
        }]
    }
    return send_card(payload, "TextParagraph with markdown code blocks")


def test_textparagraph_max_lines():
    """Test TextParagraph with maxLines parameter."""
    long_text = """Line 1: This is the first line of text.
Line 2: This is the second line of text.
Line 3: This is the third line of text.
Line 4: This is the fourth line of text.
Line 5: This is the fifth line of text.
Line 6: This should be hidden with maxLines=3.
Line 7: Also hidden.
Line 8: Also hidden."""

    payload = {
        "cardsV2": [{
            "cardId": "test-maxlines",
            "card": {
                "header": {
                    "title": "TextParagraph: maxLines",
                    "subtitle": "maxLines: 3"
                },
                "sections": [{
                    "widgets": [{
                        "textParagraph": {
                            "text": long_text,
                            "maxLines": 3
                        }
                    }]
                }]
            }
        }]
    }
    return send_card(payload, "TextParagraph with maxLines=3")


def test_decorated_text_with_text():
    """Test DecoratedText with text parameter (uses TextParagraph internally)."""
    payload = {
        "cardsV2": [{
            "cardId": "test-decorated-text",
            "card": {
                "header": {
                    "title": "DecoratedText with text",
                    "subtitle": "Testing text parameter"
                },
                "sections": [{
                    "widgets": [{
                        "decoratedText": {
                            "topLabel": "Status",
                            "text": "<b>Online</b> - <font color=\"#00FF00\">All systems operational</font>",
                            "bottomLabel": "Updated 5 minutes ago",
                            "startIcon": {
                                "knownIcon": "STAR"
                            }
                        }
                    }]
                }]
            }
        }]
    }
    return send_card(payload, "DecoratedText with HTML in text parameter")


def test_decorated_text_wrap_text():
    """Test DecoratedText with wrapText for long content."""
    long_text = "This is a very long text that should wrap across multiple lines when wrapText is enabled. " * 3

    payload = {
        "cardsV2": [{
            "cardId": "test-decorated-wrap",
            "card": {
                "header": {
                    "title": "DecoratedText: wrapText",
                    "subtitle": "Testing text wrapping"
                },
                "sections": [{
                    "widgets": [
                        {
                            "decoratedText": {
                                "topLabel": "Without wrapText",
                                "text": long_text,
                                "wrapText": False
                            }
                        },
                        {
                            "decoratedText": {
                                "topLabel": "With wrapText=true",
                                "text": long_text,
                                "wrapText": True
                            }
                        }
                    ]
                }]
            }
        }]
    }
    return send_card(payload, "DecoratedText with wrapText comparison")


def test_markdown_in_decorated_text():
    """Test if DecoratedText text parameter supports markdown syntax."""
    # Note: DecoratedText may not support textSyntax - this tests if markdown works anyway
    payload = {
        "cardsV2": [{
            "cardId": "test-decorated-md",
            "card": {
                "header": {
                    "title": "DecoratedText: Markdown Test",
                    "subtitle": "Does text support markdown?"
                },
                "sections": [{
                    "widgets": [{
                        "decoratedText": {
                            "topLabel": "Markdown in text",
                            "text": "**Bold** and *italic* and `code`",
                            "bottomLabel": "Raw markdown syntax"
                        }
                    }]
                }]
            }
        }]
    }
    return send_card(payload, "DecoratedText with raw markdown (may not render)")


def test_textparagraph_markdown_tables():
    """Test TextParagraph with markdown tables (may not be supported)."""
    markdown_text = """| Header 1 | Header 2 |
|----------|----------|
| Cell 1   | Cell 2   |
| Cell 3   | Cell 4   |"""

    payload = {
        "cardsV2": [{
            "cardId": "test-markdown-table",
            "card": {
                "header": {
                    "title": "TextParagraph: Markdown Table",
                    "subtitle": "Testing table support"
                },
                "sections": [{
                    "widgets": [{
                        "textParagraph": {
                            "text": markdown_text,
                            "textSyntax": "MARKDOWN"
                        }
                    }]
                }]
            }
        }]
    }
    return send_card(payload, "TextParagraph with markdown table")


def test_textparagraph_mixed_section():
    """Test a section with both TextParagraph and DecoratedText."""
    payload = {
        "cardsV2": [{
            "cardId": "test-mixed",
            "card": {
                "header": {
                    "title": "Mixed Widgets Test",
                    "subtitle": "TextParagraph + DecoratedText"
                },
                "sections": [{
                    "header": "Markdown Section",
                    "widgets": [{
                        "textParagraph": {
                            "text": "**Status Report**\n\n- Server: *Online*\n- Database: *Connected*",
                            "textSyntax": "MARKDOWN"
                        }
                    }]
                }, {
                    "header": "Details Section",
                    "widgets": [{
                        "decoratedText": {
                            "topLabel": "CPU Usage",
                            "text": "<font color=\"#00FF00\">23%</font>",
                            "startIcon": {"knownIcon": "CLOCK"}
                        }
                    }, {
                        "decoratedText": {
                            "topLabel": "Memory",
                            "text": "<font color=\"#FFA500\">67%</font>",
                            "startIcon": {"knownIcon": "BOOKMARK"}
                        }
                    }]
                }]
            }
        }]
    }
    return send_card(payload, "Mixed TextParagraph and DecoratedText")


if __name__ == "__main__":
    print("=" * 60)
    print("TEXTPARAGRAPH MARKDOWN CAPABILITY TESTS")
    print("=" * 60)
    print(f"Webhook: {WEBHOOK_URL[:60]}...")

    tests = [
        test_textparagraph_html_default,
        test_textparagraph_html_explicit,
        test_textparagraph_markdown,
        test_textparagraph_markdown_code_block,
        test_textparagraph_max_lines,
        test_decorated_text_with_text,
        test_decorated_text_wrap_text,
        test_markdown_in_decorated_text,
        test_textparagraph_markdown_tables,
        test_textparagraph_mixed_section,
    ]

    results = []
    for test in tests:
        result = test()
        results.append((test.__name__, result))
        time.sleep(1)  # Rate limiting

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    passed = sum(1 for _, r in results if r)
    failed = len(results) - passed

    for name, result in results:
        status = "✅" if result else "❌"
        print(f"  {status} {name}")

    print(f"\nTotal: {passed} passed, {failed} failed")
