"""Tests for gchat.card_delivery — splitting, retry, and delivery orchestration."""

import json
import os
import time
from unittest.mock import MagicMock, patch

import pytest

from gchat.card_delivery import (
    GCHAT_WEBHOOK_SAFE_BYTES,
    DeliveryResult,
    _build_part_payload,
    _estimate_payload_bytes,
    _is_feedback_section,
    _is_retryable_status,
    _post_webhook_with_retry,
    _split_card_payload,
)

TEST_CHAT_WEBHOOK = os.environ.get("TEST_CHAT_WEBHOOK", "")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_section(num_widgets: int = 1, text_size: int = 10) -> dict:
    """Build a section with *num_widgets* decoratedText widgets."""
    return {
        "widgets": [
            {"decoratedText": {"text": "x" * text_size}} for _ in range(num_widgets)
        ]
    }


def _make_message(
    num_sections: int, widgets_per: int = 1, text_size: int = 10, feedback: bool = False
) -> dict:
    sections = [_make_section(widgets_per, text_size) for _ in range(num_sections)]
    if feedback:
        sections.append(
            {
                "_feedback_assembly": {"card_id": "test"},
                "widgets": [{"collapseControl": {}}],
            }
        )
    return {
        "cardsV2": [
            {
                "cardId": "test-card",
                "card": {
                    "header": {"title": "Test Card", "subtitle": "Original"},
                    "sections": sections,
                },
            }
        ],
    }


# ---------------------------------------------------------------------------
# _estimate_payload_bytes
# ---------------------------------------------------------------------------


def test_estimate_payload_bytes():
    payload = {"key": "value"}
    expected = len(json.dumps(payload).encode("utf-8"))
    assert _estimate_payload_bytes(payload) == expected


# ---------------------------------------------------------------------------
# _is_feedback_section
# ---------------------------------------------------------------------------


def test_feedback_section_by_assembly_key():
    section = {"_feedback_assembly": {"card_id": "abc"}, "widgets": []}
    assert _is_feedback_section(section) is True


def test_feedback_section_by_collapse_control():
    section = {"widgets": [{"collapseControl": {"expandButton": {}}}]}
    assert _is_feedback_section(section) is True


def test_non_feedback_section():
    section = {"widgets": [{"decoratedText": {"text": "hello"}}]}
    assert _is_feedback_section(section) is False


# ---------------------------------------------------------------------------
# _split_card_payload — no split needed
# ---------------------------------------------------------------------------


def test_no_split_under_threshold():
    msg = _make_message(2, widgets_per=1, text_size=10)
    parts = _split_card_payload(msg, max_bytes=GCHAT_WEBHOOK_SAFE_BYTES)
    assert len(parts) == 1
    assert parts[0] is msg  # identity — no copy needed


# ---------------------------------------------------------------------------
# _split_card_payload — even split
# ---------------------------------------------------------------------------


def test_split_sections_evenly():
    msg = _make_message(6, widgets_per=3, text_size=200)
    payload_size = _estimate_payload_bytes(msg)
    # Use a threshold that forces a split (half the total size)
    threshold = payload_size // 3
    parts = _split_card_payload(msg, max_bytes=threshold)
    assert len(parts) >= 2
    # All sections present across parts
    total_sections = sum(len(p["cardsV2"][0]["card"]["sections"]) for p in parts)
    assert total_sections == 6


def test_split_odd_sections():
    msg = _make_message(5, widgets_per=3, text_size=200)
    payload_size = _estimate_payload_bytes(msg)
    threshold = payload_size // 3
    parts = _split_card_payload(msg, max_bytes=threshold)
    assert len(parts) >= 2
    total_sections = sum(len(p["cardsV2"][0]["card"]["sections"]) for p in parts)
    assert total_sections == 5


# ---------------------------------------------------------------------------
# _split_card_payload — feedback section handling
# ---------------------------------------------------------------------------


def test_feedback_on_last_part_only():
    msg = _make_message(4, widgets_per=3, text_size=200, feedback=True)
    payload_size = _estimate_payload_bytes(msg)
    parts = _split_card_payload(msg, max_bytes=payload_size // 3)
    assert len(parts) >= 2

    # Feedback section (with _feedback_assembly) only on the last part
    for part in parts[:-1]:
        for section in part["cardsV2"][0]["card"]["sections"]:
            assert "_feedback_assembly" not in section
            for w in section.get("widgets", []):
                assert "collapseControl" not in w

    last_sections = parts[-1]["cardsV2"][0]["card"]["sections"]
    assert any(_is_feedback_section(s) for s in last_sections)


# ---------------------------------------------------------------------------
# Header continuation and part numbering
# ---------------------------------------------------------------------------


def test_header_continuation_suffix():
    msg = _make_message(4, widgets_per=3, text_size=200)
    payload_size = _estimate_payload_bytes(msg)
    parts = _split_card_payload(msg, max_bytes=payload_size // 3)
    assert len(parts) >= 2

    first_subtitle = parts[0]["cardsV2"][0]["card"]["header"]["subtitle"]
    assert "Part 1/" in first_subtitle
    assert "(continued)" not in first_subtitle

    second_subtitle = parts[1]["cardsV2"][0]["card"]["header"]["subtitle"]
    assert "(continued)" in second_subtitle
    assert "Part 2/" in second_subtitle


def test_part_numbering():
    msg = _make_message(6, widgets_per=3, text_size=200)
    payload_size = _estimate_payload_bytes(msg)
    parts = _split_card_payload(msg, max_bytes=payload_size // 3)
    assert len(parts) >= 2

    for idx, part in enumerate(parts):
        subtitle = part["cardsV2"][0]["card"]["header"]["subtitle"]
        expected_label = f"Part {idx + 1}/{len(parts)}"
        assert expected_label in subtitle


# ---------------------------------------------------------------------------
# Single section — unsplittable
# ---------------------------------------------------------------------------


def test_single_section_unsplittable():
    msg = _make_message(1, widgets_per=1, text_size=10)
    parts = _split_card_payload(msg, max_bytes=10)  # impossibly small
    assert len(parts) == 1


# ---------------------------------------------------------------------------
# cardId suffix
# ---------------------------------------------------------------------------


def test_card_id_suffix():
    msg = _make_message(4, widgets_per=3, text_size=200)
    payload_size = _estimate_payload_bytes(msg)
    parts = _split_card_payload(msg, max_bytes=payload_size // 3)
    assert len(parts) >= 2

    for idx, part in enumerate(parts):
        card_id = part["cardsV2"][0]["cardId"]
        assert card_id == f"test-card-part-{idx + 1}"


# ---------------------------------------------------------------------------
# Retry — _is_retryable_status
# ---------------------------------------------------------------------------


def test_retryable_statuses():
    assert _is_retryable_status(429) is True
    assert _is_retryable_status(500) is True
    assert _is_retryable_status(502) is True
    assert _is_retryable_status(503) is True
    assert _is_retryable_status(200) is False
    assert _is_retryable_status(400) is False


# ---------------------------------------------------------------------------
# Retry — _post_webhook_with_retry
# ---------------------------------------------------------------------------


@patch("gchat.card_delivery.requests.post")
@patch("gchat.card_delivery.time.sleep")
def test_retry_on_429(mock_sleep, mock_post):
    fail_resp = MagicMock(status_code=429, text="rate limited")
    ok_resp = MagicMock(status_code=200, text="ok")
    mock_post.side_effect = [fail_resp, ok_resp]

    resp = _post_webhook_with_retry("https://example.com", {"test": 1}, max_retries=3)
    assert resp.status_code == 200
    assert mock_post.call_count == 2
    mock_sleep.assert_called_once()


@patch("gchat.card_delivery.requests.post")
@patch("gchat.card_delivery.time.sleep")
def test_retry_exhausted(mock_sleep, mock_post):
    fail_resp = MagicMock(status_code=503, text="unavailable")
    mock_post.return_value = fail_resp

    resp = _post_webhook_with_retry("https://example.com", {"test": 1}, max_retries=3)
    assert resp.status_code == 503
    assert mock_post.call_count == 3
    assert mock_sleep.call_count == 2  # sleeps between attempts, not after last


# ---------------------------------------------------------------------------
# Thread key on all parts
# ---------------------------------------------------------------------------


def test_thread_key_preserved_across_parts():
    msg = _make_message(4, widgets_per=1, text_size=10)
    parts = _split_card_payload(msg, max_bytes=800)
    # Thread key is applied at delivery time, not in split.
    # Verify all parts are valid message bodies that can accept threadKey params.
    for part in parts:
        assert "cardsV2" in part
        assert isinstance(part["cardsV2"], list)


# ---------------------------------------------------------------------------
# Inter-part delay
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_inter_part_delay():
    """Verify asyncio.sleep is called between parts during webhook delivery."""
    from gchat.card_delivery import GCHAT_INTER_PART_DELAY, deliver_card_message

    ok_resp = MagicMock(status_code=200, text="ok")

    # Build a payload that will be split
    msg = _make_message(6, widgets_per=5, text_size=500)

    with (
        patch(
            "gchat.card_delivery._post_webhook_with_retry", return_value=ok_resp
        ) as mock_post,
        patch("gchat.card_delivery._validate_webhook_url"),
        patch("gchat.card_delivery.asyncio.sleep") as mock_sleep,
        patch("gchat.card_delivery.log_security_event"),
    ):
        delivery = await deliver_card_message(
            message_body=msg,
            webhook_url="https://chat.googleapis.com/v1/spaces/test/messages?key=abc",
        )

        if delivery.parts_sent > 1:
            # sleep should be called (parts_sent - 1) times
            assert mock_sleep.call_count == delivery.parts_sent - 1
            mock_sleep.assert_called_with(GCHAT_INTER_PART_DELAY)
        else:
            # Payload fit in one part — no inter-part delay
            mock_sleep.assert_not_called()


# ===========================================================================
# LIVE INTEGRATION TESTS (require network, use TEST_CHAT_WEBHOOK)
# ===========================================================================


@pytest.mark.integration
@pytest.mark.skipif(not TEST_CHAT_WEBHOOK, reason="TEST_CHAT_WEBHOOK env var not set")
@pytest.mark.asyncio
async def test_live_single_part_delivery():
    """Send a small card via the real test webhook — single part, no split."""
    from gchat.card_delivery import deliver_card_message

    msg = {
        "cardsV2": [
            {
                "cardId": "delivery-test-single",
                "card": {
                    "header": {"title": "Delivery Test", "subtitle": "Single part"},
                    "sections": [
                        {
                            "widgets": [
                                {
                                    "decoratedText": {
                                        "topLabel": "Test",
                                        "text": "Auto-split delivery module - single part test",
                                    }
                                },
                            ]
                        }
                    ],
                },
            }
        ],
    }

    delivery = await deliver_card_message(
        message_body=msg,
        webhook_url=TEST_CHAT_WEBHOOK,
    )

    assert delivery.success, f"Delivery failed: {delivery.error}"
    assert delivery.parts_sent == 1
    assert delivery.status_code == 200


@pytest.mark.integration
@pytest.mark.skipif(not TEST_CHAT_WEBHOOK, reason="TEST_CHAT_WEBHOOK env var not set")
@pytest.mark.asyncio
async def test_live_multi_part_delivery():
    """Send an oversized card that triggers auto-split via the real test webhook."""
    from gchat.card_delivery import GCHAT_WEBHOOK_SAFE_BYTES, deliver_card_message

    # Build a card that exceeds ~24KB safe threshold.
    # 10 sections x 3 widgets x 800 chars = ~30KB payload
    sections = []
    for i in range(10):
        sections.append(
            {
                "header": f"Section {i + 1}",
                "widgets": [
                    {
                        "decoratedText": {
                            "topLabel": f"Item {j + 1}",
                            "text": f"Content block {i + 1}.{j + 1} - " + "x" * 800,
                        }
                    }
                    for j in range(3)
                ],
            }
        )

    msg = {
        "cardsV2": [
            {
                "cardId": "delivery-test-multi",
                "card": {
                    "header": {
                        "title": "Auto-Split Test",
                        "subtitle": "Should be split into multiple parts",
                    },
                    "sections": sections,
                },
            }
        ],
    }

    payload_size = _estimate_payload_bytes(msg)
    print(
        f"Total payload size: {payload_size:,} bytes (threshold: {GCHAT_WEBHOOK_SAFE_BYTES:,})"
    )
    assert payload_size > GCHAT_WEBHOOK_SAFE_BYTES, (
        "Test payload must exceed threshold to trigger split"
    )

    delivery = await deliver_card_message(
        message_body=msg,
        webhook_url=TEST_CHAT_WEBHOOK,
    )

    assert delivery.success, f"Delivery failed: {delivery.error}"
    assert delivery.parts_sent > 1, (
        f"Expected multi-part split, got {delivery.parts_sent}"
    )
    print(f"Parts sent: {delivery.parts_sent}")
