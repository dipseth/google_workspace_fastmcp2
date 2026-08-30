"""Reusable email templates for the MJML compose pipeline.

Gmail's own *Templates* feature (Settings → Advanced) is a web-UI-only
feature — the Gmail REST API, Apps Script and the add-on compose surface
expose nothing for it. This module provides the programmatic equivalent on
top of the server's existing Jinja macro pipeline:

* A saved template **is** a persisted Jinja macro
  (``middleware/templates/dynamic/<name>.j2``) tagged with ``EMAIL_TEMPLATE``.
  It is therefore listed under ``template://macros`` and callable from any
  Jinja-enabled tool parameter, exactly like hand-written macros such as
  ``team_update``::

      {{ welcome_series(email_symbols, mode='dsl') }}
      {{ welcome_series(email_symbols, mode='params', values={'recipient_name': 'Sam'}) }}

* ``compose_dynamic_email(template=<name>, template_values={...})`` is the
  ergonomic path: it loads the macro, fills ``[[placeholders]]``, deep-merges
  any ``email_params`` overrides and then continues through the normal
  DSL → EmailSpec → MJML → draft/send flow.

Two template kinds:

``blocks``
    DSL + params — fully re-parametrisable. Produced from compose inputs, or
    from any draft/sent message that was itself composed by
    ``compose_dynamic_email`` (every rendered email carries its EmailSpec in an
    HTML comment, see :func:`embed_email_spec`).
``html``
    The rendered HTML body of an arbitrary draft/sent message (e.g. one written
    in the Gmail UI). Placeholders work, block-level overrides don't.

Placeholders use ``[[snake_case_name]]`` — deliberately *not* ``{{ }}`` so the
template middleware never tries to resolve them as Jinja.
"""

from __future__ import annotations

import base64
import binascii
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html import escape as html_escape
from html import unescape as html_unescape
from typing import Any, Dict, List, Optional, Tuple

from config.enhanced_logging import setup_logger
from middleware.filters.data_filters import (
    deep_merge,
    fill_placeholders,
    find_placeholders,
)

logger = setup_logger()

TEMPLATE_MARKER = "{# EMAIL_TEMPLATE #}"
SPEC_COMMENT_PREFIX = "gws-email-spec:"
_SPEC_COMMENT_RE = re.compile(
    r"<!--\s*" + re.escape(SPEC_COMMENT_PREFIX) + r"([A-Za-z0-9+/=]+)\s*-->"
)
_BODY_CLOSE_RE = re.compile(r"</body\s*>", re.IGNORECASE)
_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# Fields whose values are prose/links worth turning into placeholders in
# ``auto_placeholders`` mode, per block class. Styling fields (colors,
# padding, sizes) and brand constants (logos, footers, headers) stay fixed.
_AUTO_PLACEHOLDER_FIELDS: Dict[str, Dict[str, str]] = {
    "HeroBlock": {
        "title": "hero_title",
        "subtitle": "hero_subtitle",
        "cta_text": "hero_cta_text",
        "cta_url": "hero_cta_url",
    },
    "TextBlock": {"text": "paragraph"},
    "ButtonBlock": {"text": "button_text", "url": "button_url"},
}


class EmailTemplateError(Exception):
    """Raised for user-facing template problems (bad name, missing store, …)."""


# =============================================================================
# EmailSpec ⇄ HTML round-trip (embedding)
# =============================================================================


def embed_email_spec(html: str, spec: Any) -> str:
    """Append the EmailSpec as a base64 JSON HTML comment before ``</body>``.

    The comment is invisible to recipients and lets a sent message or draft
    be turned back into a ``blocks`` template later. Base64 never contains
    ``--`` so the comment is always well-formed.
    """
    try:
        payload = spec.model_dump(exclude_none=True, mode="json", serialize_as_any=True)
    except AttributeError:
        payload = spec
    encoded = base64.b64encode(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
    ).decode("ascii")
    comment = f"<!--{SPEC_COMMENT_PREFIX}{encoded}-->"
    match = _BODY_CLOSE_RE.search(html)
    if match:
        return html[: match.start()] + comment + html[match.start() :]
    return html + comment


def extract_embedded_spec(html: Optional[str]) -> Optional[Dict[str, Any]]:
    """Return the EmailSpec dict embedded by :func:`embed_email_spec`, if any."""
    if not html:
        return None
    match = _SPEC_COMMENT_RE.search(html)
    if not match:
        return None
    try:
        raw = base64.b64decode(match.group(1), validate=True)
        data = json.loads(raw.decode("utf-8"))
    except (binascii.Error, ValueError, UnicodeDecodeError) as exc:
        logger.warning(f"[email_templates] Embedded spec unreadable: {exc}")
        return None
    return data if isinstance(data, dict) and "blocks" in data else None


def strip_embedded_spec(html: str) -> str:
    """Remove the embedded spec comment (used when storing html-kind templates)."""
    return _SPEC_COMMENT_RE.sub("", html)


_FEEDBACK_URL_MARKER = "/email-feedback?"


def _references_feedback(block: Any) -> bool:
    url = getattr(block, "url", "") or ""
    text = getattr(block, "text", "") or ""
    return _FEEDBACK_URL_MARKER in url or _FEEDBACK_URL_MARKER in text


def strip_feedback_blocks(spec: Any) -> int:
    """Remove the trailing feedback widget from a recovered EmailSpec, in place.

    Emails rendered with ``ENABLE_EMAIL_FEEDBACK=true`` carry an appended
    widget (optional divider, prompt text, buttons/links signed against
    ``/email-feedback?``). Baking that into a template would replay dead,
    expiring URLs and stack a fresh widget on every save→compose cycle, so
    recovery drops it. Returns the number of blocks removed (0 if none, or if
    the trailing structure doesn't look like a pure feedback tail).
    """
    blocks = spec.blocks
    marker_idxs = [i for i, b in enumerate(blocks) if _references_feedback(b)]
    if not marker_idxs:
        return 0
    start = min(marker_idxs)
    # Absorb the prompt TextBlock right before the first button, then a
    # DividerBlock separator before that (with_divider / footer_style layouts).
    if (
        start > 0
        and type(blocks[start]).__name__ == "ButtonBlock"
        and type(blocks[start - 1]).__name__ == "TextBlock"
    ):
        start -= 1
    if start > 0 and type(blocks[start - 1]).__name__ == "DividerBlock":
        start -= 1
    tail = blocks[start:]
    # Safety: only strip a tail made purely of feedback-widget furniture.
    if not all(
        type(b).__name__ in ("DividerBlock", "TextBlock", "ButtonBlock") for b in tail
    ):
        logger.warning(
            "[email_templates] Feedback markers found but trailing blocks are "
            "not a clean widget tail; leaving spec unmodified"
        )
        return 0
    spec.blocks = blocks[:start]
    return len(tail)


# =============================================================================
# EmailSpec → DSL + params (normalised template form)
# =============================================================================


def _column_dsl(column: Any) -> str:
    inner = ", ".join(_block_dsl(b) for b in column.blocks)
    return f"Column[{inner}]" if inner else "Column"


def _block_dsl(block: Any) -> str:
    cls = type(block).__name__
    if cls == "ColumnsBlock":
        cols = ", ".join(_column_dsl(c) for c in block.columns)
        return f"ColumnsBlock[{cols}]"
    return cls


def _compact_runs(names: List[str]) -> str:
    """Collapse consecutive identical leaf names into ``Name×N``."""
    out: List[str] = []
    for name in names:
        if out and out[-1][0] == name and "[" not in name:
            out[-1][1] += 1
        else:
            out.append([name, 1])
    return ", ".join(n if c == 1 else f"{n}×{c}" for n, c in out)


def spec_to_dsl_and_params(spec: Any) -> Tuple[str, Dict[str, Any]]:
    """Convert an EmailSpec into class-name DSL + symbol-free ``email_params``.

    The output is exactly what ``compose_dynamic_email`` accepts, with params
    keyed by block class name and one ``_items`` entry per block in DSL order
    (the same order ``_build_email_spec_from_dsl`` consumes them). Class names
    rather than Unicode symbols keep templates readable and immune to symbol
    regeneration.
    """
    params: Dict[str, Any] = {}

    def _add(cls: str, data: Dict[str, Any]) -> None:
        params.setdefault(cls, {"_items": []})["_items"].append(data)

    def _collect(block: Any) -> None:
        cls = type(block).__name__
        if cls == "ColumnsBlock":
            for column in block.columns:
                for inner in column.blocks:
                    _collect(inner)
                col: Dict[str, Any] = {}
                if column.width:
                    col["width"] = column.width
                if column.padding and column.padding != "0":
                    col["padding"] = column.padding
                _add("Column", col)
            return
        data = block.model_dump(exclude_none=True, mode="json", serialize_as_any=True)
        data.pop("block_type", None)
        _add(cls, data)

    for block in spec.blocks:
        _collect(block)

    dsl = f"EmailSpec[{_compact_runs([_block_dsl(b) for b in spec.blocks])}]"
    if spec.preheader:
        params["preheader"] = spec.preheader
    return dsl, params


def _block_counts(params: Dict[str, Any]) -> Dict[str, int]:
    return {
        cls: len(entry.get("_items", []))
        for cls, entry in params.items()
        if isinstance(entry, dict) and cls != "Column"
    }


# =============================================================================
# Placeholders
# =============================================================================


@dataclass
class PlaceholderInfo:
    name: str
    example: str

    def to_dict(self) -> Dict[str, str]:
        return {"name": self.name, "example": self.example}


def _example(text: str, limit: int = 80) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _normalize_placeholder_name(name: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_]+", "_", name.strip()).strip("_").lower()
    if not slug:
        raise EmailTemplateError(f"Invalid placeholder name: {name!r}")
    if slug[0].isdigit():
        slug = f"p_{slug}"
    return slug


def apply_placeholder_mapping(
    value: Any, mapping: Optional[Dict[str, str]], html_mode: bool = False
) -> Tuple[Any, List[PlaceholderInfo]]:
    """Replace literal text with ``[[name]]`` markers across ``value``.

    ``mapping`` is ``{literal_text: placeholder_name}``. Longer literals are
    applied first so "Sam Rivers" wins over "Sam". In ``html_mode`` the
    HTML-escaped form of each literal is matched too ("Sam &amp; Co").
    """
    if not mapping:
        return value, []
    normalized: List[Tuple[str, str]] = []
    for literal, name in mapping.items():
        if not literal or not isinstance(literal, str):
            continue
        normalized.append((literal, _normalize_placeholder_name(str(name))))
    normalized.sort(key=lambda pair: len(pair[0]), reverse=True)

    hits: Dict[str, str] = {}

    def _replace_str(text: str) -> str:
        for literal, name in normalized:
            marker = f"[[{name}]]"
            variants = [literal]
            if html_mode:
                escaped = html_escape(literal, quote=False)
                if escaped != literal:
                    variants.append(escaped)
            for variant in variants:
                if variant in text:
                    text = text.replace(variant, marker)
                    hits.setdefault(name, literal)
        return text

    def _walk(node: Any) -> Any:
        if isinstance(node, str):
            return _replace_str(node)
        if isinstance(node, dict):
            return {k: _walk(v) for k, v in node.items()}
        if isinstance(node, list):
            return [_walk(v) for v in node]
        return node

    result = _walk(value)
    infos = [PlaceholderInfo(name, _example(lit)) for name, lit in hits.items()]
    return result, infos


def apply_auto_placeholders(
    params: Dict[str, Any],
) -> Tuple[Dict[str, Any], List[PlaceholderInfo]]:
    """Turn the prose fields of hero/text/button blocks into placeholders.

    Names are descriptive per field (``hero_title``, ``paragraph_2``,
    ``button_url``) and only get a numeric suffix when a class occurs more
    than once. Fields that already hold a placeholder are left alone.
    """
    out = json.loads(json.dumps(params))  # deep copy, JSON-safe
    infos: List[PlaceholderInfo] = []
    for cls, fields in _AUTO_PLACEHOLDER_FIELDS.items():
        entry = out.get(cls)
        items = entry.get("_items") if isinstance(entry, dict) else None
        if not items:
            continue
        multi = len(items) > 1
        for idx, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                continue
            for field_name, base in fields.items():
                current = item.get(field_name)
                if not isinstance(current, str) or not current.strip():
                    continue
                if find_placeholders(current):
                    continue
                name = f"{base}_{idx}" if multi else base
                item[field_name] = f"[[{name}]]"
                infos.append(PlaceholderInfo(name, _example(current)))
    return out, infos


def collect_placeholders(*values: Any, examples: Dict[str, str]) -> List[Dict]:
    """Final placeholder list for a template's metadata (name + example)."""
    names: List[str] = []
    for value in values:
        for name in find_placeholders(value):
            if name not in names:
                names.append(name)
    return [{"name": n, "example": examples.get(n, "")} for n in names]


# =============================================================================
# Macro generation
# =============================================================================


def to_jinja_literal(value: Any) -> str:
    """Serialise JSON-like data as a Jinja2 expression literal.

    ``json.dumps`` output is *almost* valid Jinja — the differences are
    ``null`` → ``none`` and that strings must not be interpreted as template
    syntax. Emitting each scalar ourselves (strings via ``json.dumps``, which
    Jinja's lexer decodes with the same escape rules) sidesteps both problems
    and keeps ``{{``/``{%`` sequences inside content harmless.
    """
    if value is None:
        return "none"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=True)
    if isinstance(value, dict):
        inner = ", ".join(
            f"{to_jinja_literal(str(k))}: {to_jinja_literal(v)}"
            for k, v in value.items()
        )
        return "{" + inner + "}"
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(to_jinja_literal(v) for v in value) + "]"
    return json.dumps(str(value), ensure_ascii=True)


def build_template_macro(
    name: str,
    meta: Dict[str, Any],
    *,
    subject: str,
    dsl: Optional[str] = None,
    params: Optional[Dict[str, Any]] = None,
    html: Optional[str] = None,
) -> str:
    """Render the ``.j2`` source for a saved email template macro.

    Modes: ``meta`` (JSON metadata), ``subject``, ``dsl`` (DSL + subject, the
    ``email_description`` form), ``params`` (JSON, overrides deep-merged),
    ``html`` (html-kind body). ``values`` fills ``[[placeholders]]``.
    """
    kind = meta.get("kind", "blocks")
    lines = [
        TEMPLATE_MARKER,
        f"{{% macro {name}(symbols=none, mode='dsl', overrides=none, values=none) %}}",
        f"{{%- set meta = {to_jinja_literal(meta)} -%}}",
        f"{{%- set subject = {to_jinja_literal(subject)} -%}}",
    ]
    if kind == "blocks":
        lines.append(f"{{%- set dsl = {to_jinja_literal(dsl or '')} -%}}")
        lines.append(f"{{%- set params = {to_jinja_literal(params or {})} -%}}")
    else:
        lines.append(f"{{%- set html = {to_jinja_literal(html or '')} -%}}")
    lines.append("{%- if mode == 'meta' -%}{{ meta | tojson }}")
    lines.append(
        "{%- elif mode == 'subject' -%}{{ subject | fill_placeholders(values) }}"
    )
    if kind == "blocks":
        lines.append(
            "{%- elif mode == 'dsl' -%}{{ dsl }} {{ subject | fill_placeholders(values) }}"
        )
        lines.append(
            "{%- elif mode == 'params' -%}"
            "{{ params | deep_merge(overrides) | fill_placeholders(values) | tojson }}"
        )
    else:
        lines.append(
            "{%- elif mode == 'html' -%}{{ html | fill_placeholders(values) }}"
        )
    lines.append("{%- endif -%}")
    lines.append("{% endmacro %}")
    return "\n".join(lines) + "\n"


def _usage_example(name: str, placeholders: List[Dict[str, str]]) -> str:
    if placeholders:
        # Every placeholder is listed: a truncated call copied verbatim would
        # trip the unfilled-placeholder send guard.
        sample = ", ".join(f"'{p['name']}': '…'" for p in placeholders)
        return f"{{{{ {name}(email_symbols, mode='params', values={{{sample}}}) }}}}"
    return f"{{{{ {name}(email_symbols, mode='dsl') }}}}"


# =============================================================================
# Store access (macro manager + Jinja environment)
# =============================================================================

_store_override: Optional[Any] = None  # tests inject an EnhancedTemplateMiddleware


def set_template_store(middleware: Optional[Any]) -> None:
    """Inject the template middleware to use (tests / embedding)."""
    global _store_override
    _store_override = middleware


def _get_store() -> Tuple[Any, Any]:
    """Return ``(macro_manager, jinja_env)`` or raise if unavailable."""
    middleware = _store_override
    if middleware is None:
        from middleware.template_middleware import get_template_middleware_instance

        middleware = get_template_middleware_instance()
    if middleware is None:
        raise EmailTemplateError(
            "Template store unavailable: the template middleware is not registered."
        )
    jinja_env = middleware.jinja_env_manager.get_environment()
    if jinja_env is None:
        raise EmailTemplateError("Template store unavailable: Jinja2 is not installed.")
    return middleware.macro_manager, jinja_env


def normalize_template_name(name: Optional[str]) -> str:
    """Slugify a human name into a macro-safe identifier."""
    if not name or not str(name).strip():
        raise EmailTemplateError("A template name is required.")
    slug = re.sub(r"[^A-Za-z0-9_]+", "_", str(name).strip()).strip("_").lower()
    if not slug:
        raise EmailTemplateError(f"Invalid template name: {name!r}")
    if slug[0].isdigit():
        slug = f"t_{slug}"
    if not _NAME_RE.match(slug):
        raise EmailTemplateError(f"Invalid template name: {name!r}")
    return slug


def _is_email_template(macro_info: Dict[str, Any]) -> bool:
    return TEMPLATE_MARKER in (macro_info.get("content") or "")


def _macro(jinja_env: Any, name: str) -> Any:
    macro = jinja_env.globals.get(name)
    if macro is None or not callable(macro):
        raise EmailTemplateError(
            f"No email template named '{name}'. "
            "Use manage_email_templates(action='list') to see saved templates."
        )
    return macro


@dataclass
class LoadedTemplate:
    """A template resolved from the macro store, ready to fill/compose."""

    name: str
    kind: str
    subject: str
    meta: Dict[str, Any]
    dsl: Optional[str] = None
    params: Dict[str, Any] = field(default_factory=dict)
    html: Optional[str] = None

    @property
    def placeholders(self) -> List[str]:
        return [p["name"] for p in self.meta.get("placeholders", [])]


def load_email_template(name: str) -> LoadedTemplate:
    """Resolve a saved template by name (raises EmailTemplateError if missing)."""
    manager, jinja_env = _get_store()
    slug = normalize_template_name(name)
    info = manager.get_macro_registry().get(slug)
    if info is None or not _is_email_template(info):
        raise EmailTemplateError(
            f"No email template named '{slug}'. "
            "Use manage_email_templates(action='list') to see saved templates."
        )
    macro = _macro(jinja_env, slug)
    meta = json.loads(str(macro(mode="meta")))
    kind = meta.get("kind", "blocks")
    loaded = LoadedTemplate(
        name=slug, kind=kind, subject=str(macro(mode="subject")), meta=meta
    )
    if kind == "blocks":
        dsl_and_subject = str(macro(mode="dsl"))
        loaded.dsl = meta.get("dsl") or dsl_and_subject.split(" ", 1)[0]
        loaded.params = json.loads(str(macro(mode="params")))
    else:
        loaded.html = str(macro(mode="html"))
    return loaded


def list_email_templates() -> List[Dict[str, Any]]:
    """Metadata for every saved email template (sorted by name)."""
    manager, jinja_env = _get_store()
    templates: List[Dict[str, Any]] = []
    for name, info in sorted(manager.get_macro_registry().items()):
        if not _is_email_template(info):
            continue
        try:
            meta = json.loads(str(_macro(jinja_env, name)(mode="meta")))
        except Exception as exc:  # corrupt file — report, don't crash the list
            logger.warning(f"[email_templates] Could not read template '{name}': {exc}")
            meta = {"name": name, "kind": "unknown", "error": str(exc)}
        meta.setdefault("name", name)
        meta["usage"] = _compose_usage(name, meta.get("placeholders", []))
        templates.append(meta)
    return templates


def delete_email_template(name: str) -> bool:
    manager, _ = _get_store()
    slug = normalize_template_name(name)
    info = manager.get_macro_registry().get(slug)
    if info is None or not _is_email_template(info):
        return False
    return bool(manager.remove_dynamic_macro(slug))


def _compose_usage(name: str, placeholders: List[Dict[str, str]]) -> str:
    # All placeholders, not a sample — see _usage_example.
    values = ", ".join(f'"{p["name"]}": "…"' for p in placeholders)
    values_arg = f", template_values={{{values}}}" if values else ""
    return f'compose_dynamic_email(template="{name}"{values_arg}, to=…, action="draft")'


# =============================================================================
# Saving
# =============================================================================


@dataclass
class TemplateSource:
    """Normalised input for :func:`save_email_template`."""

    kind: str  # "blocks" | "html"
    subject: str
    dsl: Optional[str] = None
    params: Optional[Dict[str, Any]] = None
    html: Optional[str] = None
    origin: Dict[str, Any] = field(default_factory=dict)


def source_from_spec(spec: Any, origin: Dict[str, Any]) -> TemplateSource:
    dsl, params = spec_to_dsl_and_params(spec)
    return TemplateSource(
        kind="blocks", subject=spec.subject, dsl=dsl, params=params, origin=origin
    )


def source_from_compose_inputs(
    email_description: str, email_params: Optional[Dict[str, Any]]
) -> TemplateSource:
    """Validate compose inputs by building the EmailSpec, then normalise."""
    from gmail.compose import _build_email_spec_from_dsl
    from gmail.email_wrapper_api import (
        extract_email_dsl_from_description,
        parse_email_dsl,
    )

    dsl_string = extract_email_dsl_from_description(email_description or "")
    if not dsl_string:
        raise EmailTemplateError(
            "No DSL notation found in email_description — pass the same "
            "email_description/email_params you would give compose_dynamic_email, "
            "or a draft_id / message_id."
        )
    parsed = parse_email_dsl(dsl_string)
    if not parsed.is_valid:
        raise EmailTemplateError(f"Invalid DSL: {'; '.join(parsed.issues)}")
    spec = _build_email_spec_from_dsl(parsed, email_params or {}, email_description)
    return source_from_spec(spec, {"type": "compose"})


def source_from_mime(
    msg: Any, origin: Dict[str, Any], subject_override: Optional[str] = None
) -> TemplateSource:
    """Build a source from a parsed RFC-822 message (draft or sent mail).

    Messages composed by ``compose_dynamic_email`` carry their EmailSpec and
    become ``blocks`` templates; anything else becomes an ``html`` template.
    """
    from gmail.mjml_types import EmailSpec

    subject = subject_override or _header(msg, "Subject") or "Email"
    html_body, text_body = _extract_bodies(msg)
    spec_data = extract_embedded_spec(html_body)
    if spec_data:
        try:
            spec = EmailSpec(**spec_data)
            if subject_override:
                spec.subject = subject_override
            elif not spec.subject:
                spec.subject = subject
            stripped = strip_feedback_blocks(spec)
            src_origin = {**origin, "recovered_spec": True}
            if stripped:
                src_origin["stripped_feedback_blocks"] = stripped
            return source_from_spec(spec, src_origin)
        except Exception as exc:
            logger.warning(
                f"[email_templates] Embedded spec rejected, falling back to html: {exc}"
            )
    if html_body:
        html = strip_embedded_spec(html_body)
    elif text_body:
        html = (
            '<div style="white-space:pre-wrap;font-family:Arial,sans-serif">'
            f"{html_escape(text_body)}</div>"
        )
    else:
        raise EmailTemplateError("The message has no text or HTML body to template.")
    return TemplateSource(kind="html", subject=subject, html=html, origin=origin)


def _header(msg: Any, name: str) -> str:
    value = msg.get(name)
    return str(value).strip() if value else ""


def _decode_part(part: Any) -> str:
    try:
        content = part.get_content()  # EmailMessage (policy.default)
        if isinstance(content, str):
            return content.rstrip("\r\n")
    except Exception:
        pass
    payload = part.get_payload(decode=True)
    if payload is None:
        return ""
    charset = part.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace").rstrip("\r\n")
    except LookupError:
        return payload.decode("utf-8", errors="replace").rstrip("\r\n")


def _extract_bodies(msg: Any) -> Tuple[Optional[str], Optional[str]]:
    """Return ``(html, plain)`` bodies, skipping attachments."""
    html_body: Optional[str] = None
    text_body: Optional[str] = None
    parts = msg.walk() if msg.is_multipart() else [msg]
    for part in parts:
        if part.is_multipart():
            continue
        disposition = str(part.get("Content-Disposition") or "").lower()
        if disposition.startswith("attachment"):
            continue
        ctype = part.get_content_type()
        if ctype == "text/html" and html_body is None:
            html_body = _decode_part(part)
        elif ctype == "text/plain" and text_body is None:
            text_body = _decode_part(part)
    return html_body, text_body


async def source_from_gmail(
    gmail_service: Any,
    *,
    draft_id: Optional[str] = None,
    message_id: Optional[str] = None,
    subject_override: Optional[str] = None,
) -> TemplateSource:
    """Fetch a draft or message in raw form and turn it into a source."""
    import asyncio

    from gmail.draft_app import _b64url_decode, _parse_raw_message

    if draft_id:
        draft = await asyncio.to_thread(
            gmail_service.users()
            .drafts()
            .get(userId="me", id=draft_id, format="raw")
            .execute
        )
        raw = (draft.get("message") or {}).get("raw", "")
        origin = {"type": "draft", "id": draft_id}
    elif message_id:
        message = await asyncio.to_thread(
            gmail_service.users()
            .messages()
            .get(userId="me", id=message_id, format="raw")
            .execute
        )
        raw = message.get("raw", "")
        origin = {"type": "message", "id": message_id}
    else:
        raise EmailTemplateError("Provide draft_id or message_id.")
    if not raw:
        raise EmailTemplateError("Gmail returned an empty message body.")
    msg = _parse_raw_message(_b64url_decode(raw))
    return source_from_mime(msg, origin, subject_override)


def save_email_template(
    name: str,
    source: TemplateSource,
    *,
    description: str = "",
    placeholders: Optional[Dict[str, str]] = None,
    auto_placeholders: bool = False,
    overwrite: bool = False,
    placeholder_examples: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Persist ``source`` as a template macro and return its metadata.

    ``placeholder_examples`` seeds example text for placeholders already
    present in the source (e.g. when re-saving an existing template).
    """
    manager, jinja_env = _get_store()
    slug = normalize_template_name(name)

    existing = manager.get_macro_registry().get(slug)
    if existing is not None:
        if not _is_email_template(existing):
            raise EmailTemplateError(
                f"'{slug}' is already a non-template macro; choose another name."
            )
        if not overwrite:
            raise EmailTemplateError(
                f"Template '{slug}' already exists. Pass overwrite=true to replace it."
            )

    examples: Dict[str, str] = dict(placeholder_examples or {})
    subject = source.subject or "Email"
    dsl = source.dsl
    params = source.params
    html = source.html

    if source.kind == "blocks":
        params = params or {}
        if auto_placeholders:
            params, infos = apply_auto_placeholders(params)
            examples.update({i.name: i.example for i in infos})
        params, infos = apply_placeholder_mapping(params, placeholders)
        examples.update({i.name: i.example for i in infos})
    else:
        html, infos = apply_placeholder_mapping(
            html or "", placeholders, html_mode=True
        )
        examples.update({i.name: i.example for i in infos})
    subject, infos = apply_placeholder_mapping(subject, placeholders)
    examples.update({i.name: i.example for i in infos})

    placeholder_list = collect_placeholders(
        subject, params if source.kind == "blocks" else html, examples=examples
    )

    meta: Dict[str, Any] = {
        "name": slug,
        "kind": source.kind,
        "description": description or "",
        "subject": subject,
        "placeholders": placeholder_list,
        "source": source.origin,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "version": 1,
    }
    if source.kind == "blocks":
        meta["dsl"] = dsl
        meta["block_counts"] = _block_counts(params or {})
    else:
        meta["html_bytes"] = len((html or "").encode("utf-8"))

    macro_source = build_template_macro(
        slug, meta, subject=subject, dsl=dsl, params=params, html=html
    )
    result = manager.add_dynamic_macro(
        macro_name=slug,
        macro_content=macro_source,
        description=description or f"Email template '{slug}' ({source.kind})",
        usage_example=_usage_example(slug, placeholder_list),
        persist_to_file=True,
    )
    if not result.get("success"):
        raise EmailTemplateError(
            "Failed to register template macro: "
            + "; ".join(result.get("errors") or ["unknown error"])
        )
    if result.get("macro_info", {}).get("persisted") is False:
        logger.warning(
            f"[email_templates] Template '{slug}' registered but not persisted: "
            f"{result.get('errors')}"
        )

    meta["usage"] = _compose_usage(slug, placeholder_list)
    meta["persisted"] = bool(result.get("macro_info", {}).get("persisted"))
    meta["macro_usage"] = _usage_example(slug, placeholder_list)
    if source.kind == "blocks":
        meta["params"] = params
    else:
        meta["html_preview"] = _example(
            html_unescape(re.sub(r"<[^>]+>", " ", html or "")), 300
        )
    return meta


def template_detail(name: str) -> Dict[str, Any]:
    """Full detail for ``action='get'`` — metadata plus params/html."""
    loaded = load_email_template(name)
    detail = dict(loaded.meta)
    detail["usage"] = _compose_usage(loaded.name, loaded.meta.get("placeholders", []))
    detail["macro_usage"] = _usage_example(
        loaded.name, loaded.meta.get("placeholders", [])
    )
    if loaded.kind == "blocks":
        detail["params"] = loaded.params
    else:
        detail["html"] = loaded.html
    return detail


# =============================================================================
# Filling (used by compose_dynamic_email)
# =============================================================================


@dataclass
class FilledTemplate:
    kind: str
    subject: str
    dsl: Optional[str]
    params: Dict[str, Any]
    html: Optional[str]
    missing: List[str]


def fill_email_template(
    loaded: LoadedTemplate,
    values: Optional[Dict[str, Any]] = None,
    overrides: Optional[Dict[str, Any]] = None,
    subject_override: Optional[str] = None,
) -> FilledTemplate:
    """Apply placeholder values and block overrides; report unfilled names."""
    values = values or {}
    subject = fill_placeholders(subject_override or loaded.subject, values)
    if loaded.kind == "blocks":
        params = deep_merge(loaded.params, overrides or {})
        params = fill_placeholders(params, values)
        missing = find_placeholders({"subject": subject, "params": params})
        return FilledTemplate("blocks", subject, loaded.dsl, params, None, missing)
    html = fill_placeholders(loaded.html or "", values)
    missing = find_placeholders({"subject": subject, "html": html})
    return FilledTemplate("html", subject, None, {}, html, missing)
