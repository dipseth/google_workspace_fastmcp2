"""Gmail draft preview app — interactive draft card via MCP Apps.

Renders an existing Gmail draft as a Prefab UI card in the chat: the real
rendered email in a sandboxed iframe, editable recipient fields, and Send /
Save / Discard buttons wired to backend tools.

Design notes
------------
**Preview fidelity.** The draft is fetched with ``format="raw"`` and parsed
with :mod:`email`, so the preview shows the *exact* ``text/html`` MIME part
that Gmail will deliver — full MJML documents (doctype, ``<head><style>``,
media queries, MSO conditional comments, nested tables, VML) render verbatim.
Nothing is sanitised or rewritten except ``cid:`` references, which are
inlined as ``data:`` URIs so embedded images resolve inside the iframe.

**Script-free sandbox.** The preview iframe is sandboxed *without*
``allow-scripts``, which matches Gmail's own behaviour (Gmail strips
``<script>``). Only popups are permitted so links still open.

**Header-only edits.** Recipient changes rewrite ``To``/``Cc``/``Bcc`` on the
parsed MIME message and re-upload via ``drafts().update``. The body,
attachments, transfer encodings and ``threadId`` survive untouched — no
re-render, no lossy round-trip.

Requires ``fastmcp[apps]`` (prefab-ui) and a client that advertises the
``io.modelcontextprotocol/ui`` extension (Claude Desktop, MCP Inspector).
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import email
import email.policy
import logging
import re
from email.message import Message
from typing import Any, Optional, Union

from config.settings import settings
from tools.common_types import UserGoogleEmail

try:  # Optional extra: fastmcp[apps] / prefab-ui
    from prefab_ui.app import PrefabApp

    _HAS_PREFAB = True
except ImportError:  # pragma: no cover - exercised only without the extra
    PrefabApp = Any  # type: ignore[assignment,misc]
    _HAS_PREFAB = False

logger = logging.getLogger(__name__)

# Hard ceiling on the HTML we inline into the app payload. MCP messages are
# JSON over a single transport frame; a 50 MB newsletter would wedge the
# client. Above this we degrade gracefully instead of failing.
_PREVIEW_MAX_BYTES = 400_000

# Cap on a single inlined image. Anything larger stays a broken cid: ref
# rather than blowing the whole payload on one hero photo.
_INLINE_IMAGE_MAX_BYTES = 200_000

_CID_PATTERN = re.compile(r"""cid:([^"'\s>)]+)""", re.IGNORECASE)


# ---------------------------------------------------------------------------
# MIME helpers
# ---------------------------------------------------------------------------


def _b64url_decode(data: str) -> bytes:
    """Decode Gmail's URL-safe base64, tolerating missing padding."""
    if not data:
        return b""
    padded = data + "=" * (-len(data) % 4)
    try:
        return base64.urlsafe_b64decode(padded)
    except (binascii.Error, ValueError):
        return base64.b64decode(padded, altchars=b"-_", validate=False)


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii")


def _parse_raw_message(raw: bytes) -> Message:
    """Parse raw RFC-822 bytes, falling back to compat32 on exotic input.

    ``email.policy.default`` gives clean header/charset handling but is
    stricter; a malformed real-world message must still render, so fall back
    rather than raise.
    """
    try:
        return email.message_from_bytes(raw, policy=email.policy.default)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(
            f"[draft_app] default policy parse failed ({exc}); using compat32"
        )
        return email.message_from_bytes(raw)


def _decode_part_text(part: Message) -> str:
    """Best-effort decode of a text part to ``str``.

    Handles quoted-printable/base64 transfer encodings and any declared
    charset, with a permissive UTF-8 fallback for mislabelled parts.
    """
    try:
        content = part.get_content()
        if isinstance(content, str):
            return content
        if isinstance(content, bytes):
            return content.decode("utf-8", errors="replace")
    except (LookupError, KeyError, TypeError, ValueError, AttributeError):
        pass

    payload = part.get_payload(decode=True)
    if payload is None:
        payload = part.get_payload()
        return payload if isinstance(payload, str) else ""
    charset = part.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace")
    except LookupError:
        return payload.decode("utf-8", errors="replace")


def _iter_parts(msg: Message):
    """Yield every leaf part, tolerating non-multipart messages."""
    if msg.is_multipart():
        for part in msg.walk():
            if not part.is_multipart():
                yield part
    else:
        yield msg


def _find_body_part(msg: Message, subtype: str) -> Optional[Message]:
    """Return the first non-attachment ``text/<subtype>`` part."""
    for part in _iter_parts(msg):
        if part.get_content_type() != f"text/{subtype}":
            continue
        disposition = (part.get_content_disposition() or "").lower()
        if disposition == "attachment":
            continue
        return part
    return None


def _collect_inline_images(msg: Message) -> dict[str, str]:
    """Map ``Content-ID`` (and inline filenames) to ``data:`` URIs."""
    images: dict[str, str] = {}
    for part in _iter_parts(msg):
        ctype = part.get_content_type()
        if not ctype.startswith("image/"):
            continue
        try:
            payload = part.get_payload(decode=True)
        except Exception:  # pragma: no cover - defensive
            continue
        if not payload or len(payload) > _INLINE_IMAGE_MAX_BYTES:
            continue
        data_uri = f"data:{ctype};base64,{base64.b64encode(payload).decode('ascii')}"
        cid = part.get("Content-ID")
        if cid:
            images[cid.strip().strip("<>")] = data_uri
        filename = part.get_filename()
        if filename:
            images.setdefault(filename, data_uri)
    return images


def _inline_cid_references(html: str, images: dict[str, str]) -> tuple[str, int]:
    """Replace ``cid:`` URLs with data URIs. Returns (html, unresolved_count)."""
    if not images and "cid:" not in html.lower():
        return html, 0

    unresolved = 0

    def _replace(match: re.Match[str]) -> str:
        nonlocal unresolved
        key = match.group(1).strip().strip("<>")
        data_uri = images.get(key)
        if data_uri is None:
            # Some senders append query junk or URL-encode the CID.
            data_uri = images.get(key.split("?")[0])
        if data_uri is None:
            unresolved += 1
            return match.group(0)
        return data_uri

    return _CID_PATTERN.sub(_replace, html), unresolved


def _ensure_html_document(html: str) -> str:
    """Wrap bare fragments and guarantee a UTF-8 charset declaration.

    MJML always emits a full document, but hand-written drafts and Gmail's
    own composer emit fragments. The iframe needs an explicit charset or it
    guesses (and mangles emoji / non-Latin subjects).
    """
    stripped = html.lstrip()
    lowered = stripped.lower()
    has_doc = lowered.startswith("<!doctype") or lowered.startswith("<html")

    if not has_doc:
        return (
            '<!DOCTYPE html><html><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '</head><body style="margin:0">' + html + "</body></html>"
        )

    if "charset" in lowered[: lowered.find("</head>") + 7 or 2048]:
        return html

    # Inject a charset meta as the first thing in <head>.
    match = re.search(r"<head[^>]*>", html, re.IGNORECASE)
    if match:
        idx = match.end()
        return html[:idx] + '<meta charset="utf-8">' + html[idx:]
    return html


def _plain_text_fallback(text: str) -> str:
    """Render a plain-text body as preformatted HTML."""
    escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return (
        '<!DOCTYPE html><html><head><meta charset="utf-8"></head>'
        '<body style="margin:0;padding:16px;background:#fff">'
        '<pre style="font:14px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;'
        'white-space:pre-wrap;word-wrap:break-word;color:#202124;margin:0">'
        f"{escaped}</pre></body></html>"
    )


def _banner(message: str, html: str) -> str:
    """Prepend a visible notice inside the preview document."""
    notice = (
        '<div style="font:12px/1.4 -apple-system,Segoe UI,Roboto,sans-serif;'
        "background:#fff4e5;color:#8a5a00;padding:8px 12px;"
        f'border-bottom:1px solid #f0d5a8">{message}</div>'
    )
    match = re.search(r"<body[^>]*>", html, re.IGNORECASE)
    if match:
        idx = match.end()
        return html[:idx] + notice + html[idx:]
    return notice + html


def _header_list(msg: Message, name: str) -> list[str]:
    """Return a flat list of addresses for a possibly repeated header."""
    values = msg.get_all(name)
    if not values:
        return []
    out: list[str] = []
    for value in values:
        for addr in str(value).split(","):
            addr = addr.strip()
            if addr:
                out.append(addr)
    return out


def _set_header(msg: Message, name: str, value: str) -> None:
    """Replace (or delete) a header, preserving everything else."""
    del msg[name]
    if value:
        msg[name] = value


def _serialize(msg: Message) -> str:
    """Serialize back to Gmail's URL-safe base64 raw form."""
    try:
        raw = msg.as_bytes(policy=email.policy.SMTP)
    except Exception:  # pragma: no cover - defensive
        raw = msg.as_bytes()
    return _b64url_encode(raw)


def _split_recipients(value: Union[str, list[str], None]) -> list[str]:
    """Normalize a UI text field or list into a clean address list."""
    if value is None:
        return []
    if isinstance(value, list):
        items = value
    else:
        items = re.split(r"[,;\n]", value)
    return [item.strip() for item in items if item and item.strip()]


# ---------------------------------------------------------------------------
# Draft loading
# ---------------------------------------------------------------------------


class DraftSnapshot:
    """Everything the UI needs about one draft, plus the parsed MIME message."""

    def __init__(self, draft_id: str, draft: dict, msg: Message) -> None:
        self.draft_id = draft_id
        self.message_id: str = (draft.get("message") or {}).get("id", "")
        self.thread_id: str = (draft.get("message") or {}).get("threadId", "")
        self.msg = msg
        self.subject: str = str(msg.get("Subject") or "")
        self.to = _header_list(msg, "To")
        self.cc = _header_list(msg, "Cc")
        self.bcc = _header_list(msg, "Bcc")
        self.from_addr: str = str(msg.get("From") or "")
        self.attachments = [
            part.get_filename() or part.get_content_type()
            for part in _iter_parts(msg)
            if (part.get_content_disposition() or "").lower() == "attachment"
        ]

    def preview_html(self) -> tuple[str, Optional[str]]:
        """Build the iframe document. Returns ``(html, warning)``."""
        warning: Optional[str] = None

        html_part = _find_body_part(self.msg, "html")
        if html_part is not None:
            html = _decode_part_text(html_part)
        else:
            plain_part = _find_body_part(self.msg, "plain")
            plain = _decode_part_text(plain_part) if plain_part is not None else ""
            if not plain.strip():
                return (
                    _plain_text_fallback("(This draft has no readable body.)"),
                    "Draft has no text/html or text/plain body part.",
                )
            return _plain_text_fallback(plain), None

        images = _collect_inline_images(self.msg)
        inlined, unresolved = _inline_cid_references(html, images)

        if len(inlined.encode("utf-8", errors="replace")) > _PREVIEW_MAX_BYTES:
            # Embedded images are almost always the culprit — drop them first
            # so the layout still renders.
            inlined = html
            warning = (
                "Preview is large — embedded images were not inlined and may "
                "appear broken here. The sent email is unaffected."
            )
        elif unresolved:
            warning = (
                f"{unresolved} embedded image reference(s) could not be resolved "
                "in this preview. The sent email is unaffected."
            )

        document = _ensure_html_document(inlined)
        encoded = document.encode("utf-8", errors="replace")
        if len(encoded) > _PREVIEW_MAX_BYTES:
            document = encoded[:_PREVIEW_MAX_BYTES].decode("utf-8", errors="ignore")
            warning = (
                "Preview truncated — this email is larger than the inline "
                "preview limit. The draft itself is complete and unmodified."
            )

        if warning:
            document = _banner(warning, document)
        return document, warning


async def _load_draft(gmail_service: Any, draft_id: str) -> DraftSnapshot:
    """Fetch a draft in raw form and parse it."""
    draft = await asyncio.to_thread(
        gmail_service.users()
        .drafts()
        .get(userId="me", id=draft_id, format="raw")
        .execute
    )
    raw = _b64url_decode((draft.get("message") or {}).get("raw", ""))
    return DraftSnapshot(draft_id, draft, _parse_raw_message(raw))


async def _update_draft_headers(
    gmail_service: Any,
    snapshot: DraftSnapshot,
    to: list[str],
    cc: list[str],
    bcc: list[str],
) -> None:
    """Rewrite recipient headers in place and re-upload the draft."""
    _set_header(snapshot.msg, "To", ", ".join(to))
    _set_header(snapshot.msg, "Cc", ", ".join(cc))
    _set_header(snapshot.msg, "Bcc", ", ".join(bcc))

    body: dict[str, Any] = {"message": {"raw": _serialize(snapshot.msg)}}
    if snapshot.thread_id:
        body["message"]["threadId"] = snapshot.thread_id

    await asyncio.to_thread(
        gmail_service.users()
        .drafts()
        .update(userId="me", id=snapshot.draft_id, body=body)
        .execute
    )


async def _check_allow_list(
    to: list[str], cc: list[str], bcc: list[str], user_google_email: str
) -> list[str]:
    """Return recipients that are not covered by the Gmail allow list."""
    allow_list = settings.get_gmail_allow_list()
    if not allow_list:
        return []
    from gmail.compose import _resolve_recipients_and_check_allow_list

    return await _resolve_recipients_and_check_allow_list(
        to, cc, bcc, user_google_email, allow_list
    )


# ---------------------------------------------------------------------------
# MCP App — interactive draft card
# ---------------------------------------------------------------------------

_ENTRY_TOOL_NAME = "preview_gmail_draft"

_ENTRY_DESCRIPTION = """\
Render a Gmail draft as an interactive card in the chat with Send, Save and
Discard buttons, a live preview of the fully rendered email, and editable
To/Cc/Bcc fields.

Call this after creating a draft (pass the ``draft_id`` returned by
``draft_gmail_message`` / ``draft_gmail_reply`` / ``draft_gmail_forward``), or
call it with ``subject``/``body``/``html_body``/``email_spec`` and no
``draft_id`` to create the draft and preview it in one step.

After calling this tool, STOP and wait — the user decides whether to send,
keep, or discard the draft from the card.
"""

# Email HTML routinely pulls images from arbitrary CDNs. The Prefab renderer's
# default CSP only allows jsdelivr, which would leave every remote image in the
# preview broken, so widen it for this app's iframe.
_PREVIEW_RESOURCE_DOMAINS = ["https:", "data:"]

# No allow-scripts: Gmail strips <script> too, so a script-free iframe is both
# safer and a more honest preview. Popups keep links clickable.
_PREVIEW_SANDBOX = "allow-popups allow-popups-to-escape-sandbox"


def _error_app(message: str, detail: str | None = None):
    """Render a failure as a card so the user sees why nothing appeared."""
    from prefab_ui.app import PrefabApp
    from prefab_ui.components import H3, Card, CardContent, CardHeader, Column, Muted

    with Card(css_class="max-w-2xl") as view:
        with CardHeader():
            H3("Draft preview unavailable")
        with CardContent(), Column(gap=2):
            Muted(message)
            if detail:
                Muted(detail)
    return PrefabApp(view=view)


def _build_draft_view(snapshot: DraftSnapshot, user_email: str):
    """Build the Prefab view for one draft snapshot."""
    from prefab_ui.actions import SetState, ToggleState
    from prefab_ui.actions.mcp import (
        CallTool,
        RequestDisplayMode,
        SendMessage,
        UpdateContext,
    )
    from prefab_ui.app import PrefabApp
    from prefab_ui.components import (
        H3,
        Badge,
        Button,
        Card,
        CardContent,
        CardFooter,
        CardHeader,
        Column,
        If,
        Input,
        Label,
        Muted,
        Row,
        Separator,
        Text,
    )
    from prefab_ui.components.embed import Embed
    from prefab_ui.rx import ERROR, RESULT, STATE

    preview_html, warning = snapshot.preview_html()

    to_value = ", ".join(snapshot.to)
    cc_value = ", ".join(snapshot.cc)
    bcc_value = ", ".join(snapshot.bcc)

    subject = snapshot.subject or "(no subject)"
    from_addr = snapshot.from_addr or user_email

    to_input = Input(name="to", value=to_value, placeholder="name@example.com")
    cc_input = Input(name="cc", value=cc_value, placeholder="Cc (optional)")
    bcc_input = Input(name="bcc", value=bcc_value, placeholder="Bcc (optional)")

    recipient_args = {
        "draft_id": snapshot.draft_id,
        "to": to_input.rx,
        "cc": cc_input.rx,
        "bcc": bcc_input.rx,
    }

    with Card(css_class="max-w-3xl") as view:
        with CardHeader(), Column(gap=1):
            with Row(gap=2, css_class="items-center justify-between"):
                H3(subject)
                Badge("Draft", variant="secondary")
            meta_bits = [f"From {from_addr}"]
            if snapshot.attachments:
                meta_bits.append(
                    f"{len(snapshot.attachments)} attachment"
                    f"{'s' if len(snapshot.attachments) != 1 else ''}"
                )
            Muted(" · ".join(meta_bits))

        with CardContent(), Column(gap=3):
            with Column(gap=1):
                Label("To")
                to_input
            with Row(gap=2):
                Button(
                    "Cc / Bcc",
                    variant="ghost",
                    size="xs",
                    on_click=ToggleState("show_cc"),
                )
            with If(STATE.show_cc), Column(gap=1):
                Label("Cc")
                cc_input
                Label("Bcc")
                bcc_input

            Separator()

            Embed(
                html=preview_html,
                width="100%",
                height="520px",
                sandbox=_PREVIEW_SANDBOX,
            )

            if warning:
                Muted(warning)

            with If(STATE.status):
                Text(STATE.status, css_class="text-sm")

        with CardFooter(), Column(gap=2):
            with Row(gap=2):
                Button(
                    "Send",
                    variant="success",
                    disabled=STATE.done,
                    on_click=[
                        SetState("status", "Sending…"),
                        CallTool(
                            "gmail_draft_send",
                            arguments=recipient_args,
                            on_success=[
                                SetState("status", RESULT.message),
                                SetState("done", RESULT.sent),
                                SetState("needs_confirm", RESULT.needs_confirm),
                                SendMessage(RESULT.message),
                            ],
                            on_error=[SetState("status", ERROR)],
                        ),
                    ],
                )
                Button(
                    "Save draft",
                    variant="outline",
                    disabled=STATE.done,
                    on_click=[
                        SetState("status", "Saving…"),
                        CallTool(
                            "gmail_draft_save",
                            arguments=recipient_args,
                            on_success=[
                                SetState("status", RESULT.message),
                                UpdateContext(content=RESULT.message),
                            ],
                            on_error=[SetState("status", ERROR)],
                        ),
                    ],
                )
                Button(
                    "Discard",
                    variant="destructive",
                    disabled=STATE.done,
                    on_click=ToggleState("confirm_discard"),
                )
                Button(
                    "Expand",
                    variant="ghost",
                    size="xs",
                    on_click=RequestDisplayMode("fullscreen"),
                )

            with If(STATE.confirm_discard), Row(gap=2, css_class="items-center"):
                Muted("Delete this draft permanently?")
                Button(
                    "Yes, delete",
                    variant="destructive",
                    size="sm",
                    on_click=CallTool(
                        "gmail_draft_discard",
                        arguments={"draft_id": snapshot.draft_id},
                        on_success=[
                            SetState("status", RESULT.message),
                            SetState("done", RESULT.deleted),
                            SetState("confirm_discard", False),
                            SendMessage(RESULT.message),
                        ],
                        on_error=[SetState("status", ERROR)],
                    ),
                )
                Button(
                    "Keep it",
                    variant="ghost",
                    size="sm",
                    on_click=SetState("confirm_discard", False),
                )

            with If(STATE.needs_confirm), Column(gap=1):
                Muted(
                    "Some recipients are not on the Gmail allow list. "
                    "Confirm to send anyway."
                )
                Button(
                    "Send anyway",
                    variant="warning",
                    size="sm",
                    on_click=CallTool(
                        "gmail_draft_send",
                        arguments={**recipient_args, "confirm_untrusted": True},
                        on_success=[
                            SetState("status", RESULT.message),
                            SetState("done", RESULT.sent),
                            SetState("needs_confirm", False),
                            SendMessage(RESULT.message),
                        ],
                        on_error=[SetState("status", ERROR)],
                    ),
                )

    return PrefabApp(
        view=view,
        state={
            "to": to_value,
            "cc": cc_value,
            "bcc": bcc_value,
            "show_cc": bool(cc_value or bcc_value),
            "confirm_discard": False,
            "needs_confirm": False,
            "done": False,
            "status": "",
        },
    )


def create_gmail_draft_app(mcp: Any = None):
    """Build the ``GmailDraft`` :class:`~fastmcp.apps.app.FastMCPApp` provider.

    Returns ``None`` when ``prefab-ui`` is not installed so the server can
    start without the optional ``fastmcp[apps]`` extra.
    """
    if not _HAS_PREFAB:
        logger.warning("⚠️ Gmail draft app unavailable — install fastmcp[apps]")
        return None

    from fastmcp import FastMCPApp

    app = FastMCPApp("GmailDraft")

    # ── Backend tools (UI-only; the model never calls these) ──────────

    @app.tool()
    async def gmail_draft_send(
        draft_id: str,
        to: str = "",
        cc: str = "",
        bcc: str = "",
        confirm_untrusted: bool = False,
        user_google_email: UserGoogleEmail = None,
    ) -> dict:
        """Send an existing Gmail draft, applying any recipient edits first."""
        from gmail.service import _get_gmail_service_with_fallback

        to_list = _split_recipients(to)
        cc_list = _split_recipients(cc)
        bcc_list = _split_recipients(bcc)

        if not to_list:
            return {
                "ok": False,
                "sent": False,
                "needs_confirm": False,
                "draft_id": draft_id,
                "message": "Add at least one recipient in the To field before sending.",
            }

        try:
            service = await _get_gmail_service_with_fallback(user_google_email)
            snapshot = await _load_draft(service, draft_id)

            if not confirm_untrusted:
                not_allowed = await _check_allow_list(
                    to_list, cc_list, bcc_list, user_google_email or ""
                )
                if not_allowed:
                    return {
                        "ok": False,
                        "sent": False,
                        "needs_confirm": True,
                        "draft_id": draft_id,
                        "message": (
                            "Not on the Gmail allow list: "
                            + ", ".join(not_allowed)
                            + ". Use “Send anyway” to confirm, or add them with "
                            "add_to_gmail_allow_list."
                        ),
                    }

            if (
                to_list != snapshot.to
                or cc_list != snapshot.cc
                or bcc_list != snapshot.bcc
            ):
                await _update_draft_headers(
                    service, snapshot, to_list, cc_list, bcc_list
                )

            sent = await asyncio.to_thread(
                service.users()
                .drafts()
                .send(userId="me", body={"id": draft_id})
                .execute
            )
            recipients = ", ".join(to_list)
            return {
                "ok": True,
                "sent": True,
                "needs_confirm": False,
                "draft_id": draft_id,
                "message_id": sent.get("id", ""),
                "thread_id": sent.get("threadId", ""),
                "message": f"Sent “{snapshot.subject or '(no subject)'}” to {recipients}.",
            }
        except Exception as exc:
            logger.error(f"[gmail_draft_send] {exc}", exc_info=True)
            return {
                "ok": False,
                "sent": False,
                "needs_confirm": False,
                "draft_id": draft_id,
                "message": f"Send failed: {exc}",
            }

    @app.tool()
    async def gmail_draft_save(
        draft_id: str,
        to: str = "",
        cc: str = "",
        bcc: str = "",
        user_google_email: UserGoogleEmail = None,
    ) -> dict:
        """Persist recipient edits to the draft without sending it."""
        from gmail.service import _get_gmail_service_with_fallback

        to_list = _split_recipients(to)
        cc_list = _split_recipients(cc)
        bcc_list = _split_recipients(bcc)

        try:
            service = await _get_gmail_service_with_fallback(user_google_email)
            snapshot = await _load_draft(service, draft_id)
            await _update_draft_headers(service, snapshot, to_list, cc_list, bcc_list)
            summary = ", ".join(to_list) if to_list else "no recipients yet"
            return {
                "ok": True,
                "draft_id": draft_id,
                "message": f"Draft saved ({summary}). It stays in Gmail → Drafts.",
            }
        except Exception as exc:
            logger.error(f"[gmail_draft_save] {exc}", exc_info=True)
            return {
                "ok": False,
                "draft_id": draft_id,
                "message": f"Save failed: {exc}",
            }

    @app.tool()
    async def gmail_draft_discard(
        draft_id: str,
        user_google_email: UserGoogleEmail = None,
    ) -> dict:
        """Permanently delete the draft."""
        from gmail.service import _get_gmail_service_with_fallback

        try:
            service = await _get_gmail_service_with_fallback(user_google_email)
            await asyncio.to_thread(
                service.users().drafts().delete(userId="me", id=draft_id).execute
            )
            return {
                "ok": True,
                "deleted": True,
                "draft_id": draft_id,
                "message": "Draft deleted.",
            }
        except Exception as exc:
            logger.error(f"[gmail_draft_discard] {exc}", exc_info=True)
            return {
                "ok": False,
                "deleted": False,
                "draft_id": draft_id,
                "message": f"Delete failed: {exc}",
            }

    # ── Entry point (model-visible) ───────────────────────────────────

    @app.ui(name=_ENTRY_TOOL_NAME, description=_ENTRY_DESCRIPTION)
    async def preview_gmail_draft(
        draft_id: Optional[str] = None,
        subject: Optional[str] = None,
        body: Optional[str] = None,
        html_body: Optional[str] = None,
        email_spec: Optional[dict] = None,
        to: Optional[str] = None,
        cc: Optional[str] = None,
        bcc: Optional[str] = None,
        content_type: str = "mixed",
        user_google_email: UserGoogleEmail = None,
    ) -> PrefabApp:
        """Render a Gmail draft as an interactive card."""
        from gmail.service import _get_gmail_service_with_fallback

        try:
            if not draft_id:
                if not (body or html_body or email_spec):
                    return _error_app(
                        "Nothing to preview.",
                        "Pass a draft_id, or subject plus body/html_body/email_spec "
                        "to create the draft first.",
                    )
                from gmail.compose import draft_gmail_message

                created = await draft_gmail_message(
                    subject=subject or "",
                    body=body or "",
                    user_google_email=user_google_email,
                    to=_split_recipients(to) or None,
                    content_type=content_type,  # type: ignore[arg-type]
                    html_body=html_body,
                    cc=_split_recipients(cc) or None,
                    bcc=_split_recipients(bcc) or None,
                    email_spec=email_spec,
                )
                if not created.get("success"):
                    return _error_app(
                        "Could not create the draft.",
                        str(created.get("error") or ""),
                    )
                draft_id = created.get("draft_id") or ""

            service = await _get_gmail_service_with_fallback(user_google_email)
            snapshot = await _load_draft(service, draft_id)
            return _build_draft_view(snapshot, user_google_email or "")
        except Exception as exc:
            logger.error(f"[preview_gmail_draft] {exc}", exc_info=True)
            return _error_app("Could not load the draft.", str(exc))

    _widen_preview_csp(app)
    return app


def _widen_preview_csp(app: Any) -> None:
    """Allow the preview iframe to load remote email images.

    ``@app.ui()`` hardcodes its ``AppConfig``, and the Prefab renderer's
    default CSP only permits ``cdn.jsdelivr.net``. Email HTML pulls images
    from arbitrary CDNs, so patch the entry tool's ``meta["ui"]["csp"]``
    after registration — the renderer synthesizer merges it with the
    defaults at ``list_resources`` time.
    """
    try:
        for key, component in app._local._components.items():
            if not key.startswith("tool:"):
                continue
            if component.name != _ENTRY_TOOL_NAME:
                continue
            meta = dict(component.meta or {})
            ui = dict(meta.get("ui") or {})
            csp = dict(ui.get("csp") or {})
            existing = list(csp.get("resourceDomains") or [])
            for domain in _PREVIEW_RESOURCE_DOMAINS:
                if domain not in existing:
                    existing.append(domain)
            csp["resourceDomains"] = existing
            ui["csp"] = csp
            meta["ui"] = ui
            component.meta = meta
            return
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(f"⚠️ Could not widen Gmail draft preview CSP: {exc}")
