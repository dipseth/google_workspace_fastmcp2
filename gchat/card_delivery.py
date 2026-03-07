"""Centralized card delivery with auto-split and retry.

Detects oversized payloads, splits them on section boundaries,
and sends each part with exponential-backoff retry.
"""

import asyncio
import copy
import json
import math
import time
import urllib.parse
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import requests

from auth.audit import log_security_event
from config.enhanced_logging import setup_logger
from gchat.card_builder.validation import clean_card_metadata, has_feedback
from gchat.card_tools import (
    _process_thread_key_for_request,
    _process_thread_key_for_webhook_url,
    _redact_webhook_url,
    _validate_webhook_url,
)

logger = setup_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

GCHAT_WEBHOOK_MAX_BYTES = 32_000  # Empirically determined webhook limit (~32KB)
GCHAT_WEBHOOK_SAFE_BYTES = 24_000  # 75% of max — split threshold
GCHAT_WEBHOOK_TIMEOUT = 30  # seconds per request
GCHAT_DELIVERY_MAX_RETRIES = 3
GCHAT_MAX_BACKOFF_SECONDS = 16
GCHAT_INTER_PART_DELAY = 0.5  # seconds between split parts


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass
class DeliveryResult:
    success: bool
    status_code: Optional[int] = None
    response_text: Optional[str] = None
    parts_sent: int = 1
    thread_key: Optional[str] = None
    error: Optional[str] = None
    failed_part: Optional[int] = None  # 1-indexed


# ---------------------------------------------------------------------------
# Size estimation
# ---------------------------------------------------------------------------


def _estimate_payload_bytes(payload: dict) -> int:
    """Return UTF-8 byte length of the JSON-serialised payload."""
    return len(json.dumps(payload).encode("utf-8"))


# ---------------------------------------------------------------------------
# Feedback section detection
# ---------------------------------------------------------------------------


def _is_feedback_section(section: dict) -> bool:
    """Return True if *section* is the card's feedback section.

    Detected by the presence of ``_feedback_assembly`` metadata or a
    ``collapseControl`` widget (the collapsible feedback UI pattern).
    """
    if "_feedback_assembly" in section:
        return True
    for widget in section.get("widgets", []):
        if isinstance(widget, dict) and "collapseControl" in widget:
            return True
    return False


# ---------------------------------------------------------------------------
# Splitting
# ---------------------------------------------------------------------------


def _distribute_evenly(items: List[Any], num_parts: int) -> List[List[Any]]:
    """Split *items* into *num_parts* contiguous chunks as equal in size as possible.

    Uses the divmod trick: if ``len(items) == 10`` and ``num_parts == 3``,
    produces chunks of size [4, 3, 3] (extras go to the first chunks).
    """
    n = len(items)
    base, extras = divmod(n, num_parts)
    chunks: List[List[Any]] = []
    start = 0
    for i in range(num_parts):
        size = base + (1 if i < extras else 0)
        chunks.append(items[start : start + size])
        start += size
    return chunks


def _split_card_payload(
    message_body: dict,
    max_bytes: int = GCHAT_WEBHOOK_SAFE_BYTES,
) -> List[dict]:
    """Split an oversized card payload into multiple parts on section boundaries.

    Each returned dict is a complete message body (with ``cardsV2``) that fits
    under *max_bytes*.  The feedback section, if present, is appended only to
    the last part.

    Returns a single-element list when the payload already fits or cannot be
    split (single section).
    """
    # If the whole payload already fits, return as-is
    if _estimate_payload_bytes(message_body) <= max_bytes:
        return [message_body]

    cards_v2 = message_body.get("cardsV2", [])
    if not cards_v2:
        return [message_body]

    card_wrapper = cards_v2[0]
    card = card_wrapper.get("card", {})
    sections = card.get("sections", [])

    if len(sections) <= 1:
        return [message_body]

    # Separate feedback section (always last when present)
    feedback_section = None
    content_sections = list(sections)
    if content_sections and _is_feedback_section(content_sections[-1]):
        feedback_section = content_sections.pop()

    if not content_sections:
        return [message_body]

    header = card.get("header")
    base_card_id = card_wrapper.get("cardId", "card")

    # Find the smallest num_parts where every chunk fits.
    # Sections are distributed as evenly as possible (round-robin style).
    for num_parts in range(2, len(content_sections) + 1):
        chunks = _distribute_evenly(content_sections, num_parts)
        # Append feedback to last chunk for size estimation
        trial_last = list(chunks[-1])
        if feedback_section:
            trial_last.append(feedback_section)

        # Build trial payloads and check sizes
        all_fit = True
        for idx, chunk in enumerate(chunks):
            trial_sections = chunk if idx < len(chunks) - 1 else trial_last
            trial = _build_part_payload(
                message_body,
                header,
                trial_sections,
                base_card_id,
                idx + 1,
                len(chunks),
            )
            if _estimate_payload_bytes(trial) > max_bytes:
                all_fit = False
                break

        if all_fit:
            # Build final payloads
            parts: List[dict] = []
            for idx, chunk in enumerate(chunks):
                is_last = idx == len(chunks) - 1
                part_sections = list(chunk)
                if is_last and feedback_section:
                    part_sections.append(feedback_section)
                part = _build_part_payload(
                    message_body,
                    header,
                    part_sections,
                    base_card_id,
                    idx + 1,
                    len(chunks),
                )
                parts.append(part)
            return parts

    # Could not split small enough — return unsplit as best effort
    return [message_body]


def _build_part_payload(
    original_body: dict,
    header: Optional[dict],
    sections: List[dict],
    base_card_id: str,
    part_num: int,
    total_parts: int,
) -> dict:
    """Construct a complete message body for one part of a split card."""
    part_header = None
    if header:
        part_header = copy.deepcopy(header)
        subtitle = part_header.get("subtitle", "")
        part_label = f"Part {part_num}/{total_parts}"
        if part_num > 1:
            part_header["subtitle"] = f"{subtitle} (continued) - {part_label}".strip(
                " -"
            )
        else:
            if subtitle:
                part_header["subtitle"] = f"{subtitle} - {part_label}"
            else:
                part_header["subtitle"] = part_label

    card: Dict[str, Any] = {}
    if part_header:
        card["header"] = part_header
    card["sections"] = sections

    card_id = f"{base_card_id}-part-{part_num}" if total_parts > 1 else base_card_id

    body: Dict[str, Any] = {
        "cardsV2": [{"cardId": card_id, "card": card}],
    }

    # Preserve top-level keys (e.g. text/fallbackText) from the original
    for key in ("text", "fallbackText"):
        if key in original_body:
            body[key] = original_body[key]

    return body


# ---------------------------------------------------------------------------
# Retry helpers
# ---------------------------------------------------------------------------


def _is_retryable_status(code: int) -> bool:
    return code == 429 or code >= 500


def _post_webhook_with_retry(
    url: str,
    payload: dict,
    *,
    max_retries: int = GCHAT_DELIVERY_MAX_RETRIES,
    timeout: int = GCHAT_WEBHOOK_TIMEOUT,
) -> requests.Response:
    """POST *payload* to *url* with exponential-backoff retry."""
    last_exc: Optional[Exception] = None
    for attempt in range(max_retries):
        try:
            resp = requests.post(
                url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=timeout,
            )
            if not _is_retryable_status(resp.status_code):
                return resp
            # Retryable HTTP status — fall through to backoff
            last_exc = None
        except (requests.Timeout, requests.ConnectionError) as exc:
            last_exc = exc

        if attempt < max_retries - 1:
            delay = min(2**attempt, GCHAT_MAX_BACKOFF_SECONDS)
            logger.warning(
                "Webhook POST attempt %d/%d failed — retrying in %ds",
                attempt + 1,
                max_retries,
                delay,
            )
            time.sleep(delay)

    # Final attempt (or return last retryable response)
    if last_exc is not None:
        raise last_exc
    return resp  # type: ignore[possibly-undefined]


async def _send_api_with_retry(
    chat_service: Any,
    request_params: dict,
    *,
    max_retries: int = GCHAT_DELIVERY_MAX_RETRIES,
) -> dict:
    """Execute a Chat API ``spaces.messages.create`` with backoff retry."""
    from googleapiclient.errors import HttpError

    last_exc: Optional[Exception] = None
    for attempt in range(max_retries):
        try:
            result = await asyncio.to_thread(
                chat_service.spaces().messages().create(**request_params).execute
            )
            return result
        except HttpError as exc:
            status = exc.resp.status
            if (status == 429 or status >= 500) and attempt < max_retries - 1:
                last_exc = exc
            else:
                raise
        except (TimeoutError, ConnectionError) as exc:
            if attempt < max_retries - 1:
                last_exc = exc
            else:
                raise

        delay = min(2**attempt, GCHAT_MAX_BACKOFF_SECONDS)
        logger.warning(
            "Chat API attempt %d/%d failed — retrying in %ds",
            attempt + 1,
            max_retries,
            delay,
        )
        await asyncio.sleep(delay)

    raise last_exc  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


async def deliver_card_message(
    message_body: dict,
    *,
    webhook_url: Optional[str] = None,
    chat_service: Any = None,
    space_id: Optional[str] = None,
    thread_key: Optional[str] = None,
    builder: Any = None,
) -> DeliveryResult:
    """Estimate payload size, split if needed, and deliver with retry.

    Exactly one of *webhook_url* or *chat_service* must be provided.

    Args:
        message_body: The full message dict **before** ``_clean_card_metadata``
            (so feedback-section detection still works).
        webhook_url: Webhook endpoint (mutually exclusive with *chat_service*).
        chat_service: Authenticated Google Chat API service resource.
        space_id: Target space (required for API path).
        thread_key: Thread key for threading all parts together.
        builder: SmartCardBuilderV2 instance (used for ``_clean_card_metadata``).
    """
    # --- estimate & split (before metadata cleaning) -----------------------
    cleaned_body = clean_card_metadata(message_body)
    payload_bytes = _estimate_payload_bytes(cleaned_body)

    if payload_bytes > GCHAT_WEBHOOK_SAFE_BYTES:
        # Split on the *unclean* body so feedback detection works, then clean each part
        parts_raw = _split_card_payload(
            message_body, max_bytes=GCHAT_WEBHOOK_SAFE_BYTES
        )
        parts = [clean_card_metadata(p) for p in parts_raw]
        logger.info(
            "Payload %d bytes exceeds %d threshold — split into %d parts",
            payload_bytes,
            GCHAT_WEBHOOK_SAFE_BYTES,
            len(parts),
        )
    else:
        parts = [cleaned_body]

    total_parts = len(parts)
    thread_key_for_result = thread_key

    # --- webhook delivery --------------------------------------------------
    if webhook_url:
        _validate_webhook_url(webhook_url)

        if thread_key:
            webhook_url = _process_thread_key_for_webhook_url(webhook_url, thread_key)

        log_security_event(
            "webhook_request",
            details={
                "host": urllib.parse.urlparse(webhook_url).hostname,
                "payload_size": payload_bytes,
                "parts": total_parts,
            },
        )

        for idx, part in enumerate(parts):
            part_num = idx + 1
            logger.info(
                "Sending part %d/%d via webhook (%d bytes)",
                part_num,
                total_parts,
                _estimate_payload_bytes(part),
            )
            logger.debug("Webhook URL: %s", webhook_url)
            logger.debug("Payload: %s", json.dumps(part, indent=2))

            try:
                resp = await asyncio.to_thread(
                    _post_webhook_with_retry,
                    webhook_url,
                    part,
                )
            except (requests.Timeout, requests.ConnectionError) as exc:
                return DeliveryResult(
                    success=False,
                    error=f"Part {part_num}/{total_parts} network error: {exc}",
                    parts_sent=idx,
                    failed_part=part_num,
                    thread_key=thread_key_for_result,
                )

            logger.info(
                "Part %d/%d response: status=%d body=%s",
                part_num,
                total_parts,
                resp.status_code,
                resp.text[:200],
            )

            if _is_retryable_status(resp.status_code) or resp.status_code >= 400:
                return DeliveryResult(
                    success=False,
                    status_code=resp.status_code,
                    response_text=resp.text,
                    error=f"Part {part_num}/{total_parts} failed: HTTP {resp.status_code}",
                    parts_sent=idx,
                    failed_part=part_num,
                    thread_key=thread_key_for_result,
                )

            # Inter-part delay
            if part_num < total_parts:
                await asyncio.sleep(GCHAT_INTER_PART_DELAY)

        # All parts succeeded — return last response info
        return DeliveryResult(
            success=True,
            status_code=resp.status_code,  # type: ignore[possibly-undefined]
            response_text=resp.text,  # type: ignore[possibly-undefined]
            parts_sent=total_parts,
            thread_key=thread_key_for_result,
        )

    # --- API delivery ------------------------------------------------------
    if chat_service is None:
        return DeliveryResult(
            success=False,
            error="No webhook_url or chat_service provided",
        )

    for idx, part in enumerate(parts):
        part_num = idx + 1
        request_params: Dict[str, Any] = {"parent": space_id, "body": part}
        _process_thread_key_for_request(request_params, thread_key)

        logger.info("Sending part %d/%d via Chat API", part_num, total_parts)

        try:
            api_result = await _send_api_with_retry(chat_service, request_params)
        except Exception as exc:
            return DeliveryResult(
                success=False,
                error=f"Part {part_num}/{total_parts} API error: {exc}",
                parts_sent=idx,
                failed_part=part_num,
                thread_key=thread_key_for_result,
            )

        # Use thread from first response for subsequent parts
        if idx == 0 and not thread_key:
            thread_name = api_result.get("thread", {}).get("name")
            if thread_name:
                thread_key = thread_name
                thread_key_for_result = thread_name

        if part_num < total_parts:
            await asyncio.sleep(GCHAT_INTER_PART_DELAY)

    return DeliveryResult(
        success=True,
        response_text=json.dumps(api_result),  # type: ignore[possibly-undefined]
        parts_sent=total_parts,
        thread_key=thread_key_for_result,
    )
