"""MCP tool: ``manage_email_templates`` — save / list / get / delete reusable
email templates (see :mod:`gmail.email_templates` for the model).
"""

import json
from typing import Any, Dict, List, Optional, Union

from fastmcp import Context, FastMCP
from pydantic import Field
from typing_extensions import Annotated, Literal

from config.enhanced_logging import setup_logger
from tools.common_types import UserGoogleEmail

from . import email_templates as et
from .gmail_types import ManageEmailTemplatesResponse
from .service import _get_gmail_service_with_fallback

logger = setup_logger()


def _coerce_dict(value: Optional[Union[dict, str]], label: str) -> Optional[dict]:
    """MCP clients / Jinja macros may send dict params as JSON strings."""
    if value is None or isinstance(value, dict):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            parsed = json.loads(text)
        except (ValueError, TypeError) as exc:
            raise et.EmailTemplateError(f"{label} must be a JSON object: {exc}")
        if not isinstance(parsed, dict):
            raise et.EmailTemplateError(f"{label} must be a JSON object.")
        return parsed
    raise et.EmailTemplateError(f"{label} must be a JSON object.")


def _response(
    action: str,
    *,
    success: bool = True,
    templates: Optional[List[Dict[str, Any]]] = None,
    template: Optional[Dict[str, Any]] = None,
    message: str = "",
    error: Optional[str] = None,
) -> ManageEmailTemplatesResponse:
    templates = templates or []
    return ManageEmailTemplatesResponse(
        success=success,
        action=action,
        templates=templates,
        count=len(templates),
        template=template,
        message=message,
        error=error,
    )


async def manage_email_templates(
    action: str,
    name: Optional[str] = None,
    description: str = "",
    email_description: Optional[str] = None,
    email_params: Optional[Union[dict, str]] = None,
    draft_id: Optional[str] = None,
    message_id: Optional[str] = None,
    subject: Optional[str] = None,
    placeholders: Optional[Union[dict, str]] = None,
    auto_placeholders: bool = False,
    overwrite: bool = False,
    user_google_email: UserGoogleEmail = None,
) -> ManageEmailTemplatesResponse:
    """Implementation behind the ``manage_email_templates`` tool."""
    try:
        if action == "list":
            templates = et.list_email_templates()
            return _response(
                action,
                templates=templates,
                message=(
                    f"{len(templates)} email template(s) saved."
                    if templates
                    else "No email templates saved yet. Use action='save' with "
                    "email_description+email_params, a draft_id, or a message_id."
                ),
            )

        if action == "get":
            detail = et.template_detail(name or "")
            return _response(
                action,
                template=detail,
                message=f"Template '{detail['name']}' ({detail.get('kind')}). "
                f"Use it with: {detail['usage']}",
            )

        if action == "delete":
            slug = et.normalize_template_name(name)
            if et.delete_email_template(slug):
                return _response(action, message=f"Deleted email template '{slug}'.")
            return _response(
                action,
                success=False,
                error=f"No email template named '{slug}'.",
                message=f"No email template named '{slug}'.",
            )

        if action == "save":
            slug = et.normalize_template_name(name)
            params = _coerce_dict(email_params, "email_params")
            mapping = _coerce_dict(placeholders, "placeholders")

            if draft_id or message_id:
                gmail_service = await _get_gmail_service_with_fallback(
                    user_google_email
                )
                source = await et.source_from_gmail(
                    gmail_service,
                    draft_id=draft_id,
                    message_id=message_id,
                    subject_override=subject,
                )
            elif email_description:
                source = et.source_from_compose_inputs(email_description, params)
                if subject:
                    source.subject = subject
            else:
                raise et.EmailTemplateError(
                    "action='save' needs a source: email_description (+ email_params), "
                    "a draft_id, or a message_id."
                )

            meta = et.save_email_template(
                slug,
                source,
                description=description or "",
                placeholders=mapping,
                auto_placeholders=auto_placeholders,
                overwrite=overwrite,
            )
            names = [p["name"] for p in meta.get("placeholders", [])]
            origin = meta.get("source", {})
            how = {
                "compose": "from compose inputs",
                "draft": f"from draft {origin.get('id')}",
                "message": f"from message {origin.get('id')}",
            }.get(origin.get("type"), "")
            kind_note = (
                "block template (re-parametrisable DSL + params)"
                if meta["kind"] == "blocks"
                else "html template (body kept verbatim; no block overrides)"
            )
            if origin.get("type") in ("draft", "message") and meta["kind"] == "html":
                kind_note += (
                    " — the source email was not composed by compose_dynamic_email, "
                    "so its block structure could not be recovered"
                )
            msg = (
                f"Saved {kind_note} '{slug}' {how}. "
                f"Placeholders: {', '.join(f'[[{n}]]' for n in names) or 'none'}. "
                f"Use it with: {meta['usage']}"
            )
            if not meta.get("persisted", True):
                msg += (
                    " (WARNING: could not write to disk — template is in-memory only)"
                )
            return _response(action, template=meta, message=msg)

        raise et.EmailTemplateError(
            f"Unknown action '{action}'. Use list, get, save or delete."
        )

    except et.EmailTemplateError as exc:
        return _response(action, success=False, error=str(exc), message=str(exc))
    except Exception as exc:  # network / API failures
        logger.error(f"[manage_email_templates] {action} failed: {exc}", exc_info=True)
        return _response(
            action,
            success=False,
            error=str(exc),
            message=f"manage_email_templates {action} failed: {exc}",
        )


def setup_email_template_tools(mcp: FastMCP) -> None:
    """Register the manage_email_templates tool."""

    @mcp.tool(
        name="manage_email_templates",
        description=(
            "Save, list, inspect or delete reusable email templates for compose_dynamic_email. "
            "Gmail's own Templates feature has no API, so this is the programmatic equivalent: "
            "each template is a persisted Jinja macro (also visible under template://macros).\n"
            "Save from any of three sources: (1) the email_description + email_params you would "
            "pass to compose_dynamic_email; (2) draft_id of a Gmail draft; (3) message_id of a sent "
            "or received message. Emails composed by compose_dynamic_email round-trip into block "
            "templates (DSL + params, fully re-parametrisable); other emails become html templates "
            "(body kept verbatim).\n"
            'Placeholders: pass placeholders={"literal text": "snake_case_name"} to swap '
            'concrete content for descriptive [[name]] markers (e.g. {"Sam": "recipient_name", '
            '"Tuesday 3pm": "meeting_time"}) — choose names that describe the role of the text. '
            "auto_placeholders=true additionally replaces every hero/paragraph/button text and CTA "
            "URL with field-named markers (hero_title, paragraph, button_url…; numbered "
            "paragraph_1, paragraph_2… only when a block class occurs more than once). Unmapped "
            "text stays as fixed boilerplate. Feedback widgets injected by ENABLE_EMAIL_FEEDBACK "
            "are stripped automatically when saving from a draft/message.\n"
            "Use a saved template with compose_dynamic_email(template=<name>, template_values={...}); "
            "the response's 'usage' field shows the exact call. To also put a template into Gmail's "
            "native Templates menu, draft it with compose_dynamic_email and click ⋮ → Templates → "
            "'Save draft as template' in Gmail (web only; not automatable).\n"
            "Returns: template metadata incl. placeholders (name + example text) and usage. "
            "Errors: unknown template, duplicate name without overwrite, source without a body."
        ),
        tags={"gmail", "email", "template", "mjml", "compose", "macro"},
        annotations={
            "title": "Manage Email Templates",
            "readOnlyHint": False,
            "destructiveHint": True,  # action='delete' removes the macro file
            "idempotentHint": False,
            "openWorldHint": True,
        },
    )
    async def manage_email_templates_tool(
        ctx: Context,
        action: Annotated[
            Literal["list", "get", "save", "delete"],
            Field(
                description="list = all saved templates; get = full detail (params/html) for one; "
                "save = create/replace from a source; delete = remove."
            ),
        ],
        name: Annotated[
            Optional[str],
            Field(
                description="Template name (get/save/delete). Slugified to a snake_case identifier, "
                "e.g. 'Welcome Series' → welcome_series."
            ),
        ] = None,
        description: Annotated[
            Optional[str],
            Field(description="save: what the template is for (shown in list)."),
        ] = None,
        email_description: Annotated[
            Optional[str],
            Field(
                description="save source (1): DSL + subject exactly as for compose_dynamic_email, "
                "e.g. 'ε[ħ, τx2, Ƀ] Welcome aboard'."
            ),
        ] = None,
        email_params: Annotated[
            Optional[Union[dict, str]],
            Field(
                description="save source (1): block content keyed by symbol/class, same shape as "
                "compose_dynamic_email's email_params."
            ),
        ] = None,
        draft_id: Annotated[
            Optional[str],
            Field(
                description="save source (2): Gmail draft id (from compose_dynamic_email's response "
                "or search_gmail_messages 'in:draft')."
            ),
        ] = None,
        message_id: Annotated[
            Optional[str],
            Field(
                description="save source (3): Gmail message id of a sent (or received) email, "
                "e.g. from search_gmail_messages 'in:sent'."
            ),
        ] = None,
        subject: Annotated[
            Optional[str],
            Field(
                description="save: override the template's subject line (may contain [[placeholders]])."
            ),
        ] = None,
        placeholders: Annotated[
            Optional[Union[dict, str]],
            Field(
                description='save: {"literal text": "placeholder_name"} — every occurrence of the '
                "literal (in any block text, URL, or the subject) becomes [[placeholder_name]]. "
                "Pick descriptive names: recipient_name, meeting_time, invoice_total, cta_url."
            ),
        ] = None,
        auto_placeholders: Annotated[
            bool,
            Field(
                description="save (block templates): also replace hero title/subtitle/CTA, every "
                "paragraph, and button text/URL with field-named placeholders."
            ),
        ] = False,
        overwrite: Annotated[
            bool,
            Field(description="save: replace an existing template with the same name."),
        ] = False,
        user_google_email: UserGoogleEmail = None,
    ) -> ManageEmailTemplatesResponse:
        return await manage_email_templates(
            action=action,
            name=name,
            description=description or "",
            email_description=email_description,
            email_params=email_params,
            draft_id=draft_id,
            message_id=message_id,
            subject=subject,
            placeholders=placeholders,
            auto_placeholders=auto_placeholders,
            overwrite=overwrite,
            user_google_email=user_google_email,
        )
