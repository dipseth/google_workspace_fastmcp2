"""Feedback endpoints for SmartCardBuilder feedback loop.

This module provides HTTP endpoints for capturing card feedback from users.
When users click 👍/👎 buttons on cards, they're directed here to record feedback.
"""

from typing import Any
from urllib.parse import parse_qs, urlparse

from fastmcp import FastMCP

from config.enhanced_logging import setup_logger
from config.settings import settings as _settings

logger = setup_logger()


def setup_feedback_endpoints(mcp: FastMCP):
    """
    Setup feedback endpoints for the SmartCardBuilder feedback loop.

    Provides endpoints for:
    - /card-feedback: Receives feedback clicks from card buttons
    - /card-feedback/stats: Shows feedback statistics (optional)

    Args:
        mcp: FastMCP application instance
    """

    @mcp.custom_route("/card-feedback", methods=["GET"])
    async def card_feedback_endpoint(request: Any):
        """
        Receive feedback from card buttons.

        Query params:
            card_id: Unique ID of the card
            feedback: "positive" or "negative"
            feedback_type: "content" or "form" (optional, defaults to updating both)
                - content: Rates values/inputs (affects inputs vector searches)
                - form: Rates layout/structure (affects relationships vector searches)

        Returns HTML page confirming feedback was received.
        """
        from starlette.responses import HTMLResponse

        try:
            # Parse query parameters
            query_params = dict(request.query_params)
            card_id = query_params.get("card_id", "")
            feedback = query_params.get("feedback", "")
            feedback_type = query_params.get("feedback_type", "")  # "content" or "form"

            logger.info(
                f"📝 Feedback received: card_id={card_id[:8]}..., feedback={feedback}, type={feedback_type or 'both'}"
            )

            if not card_id or not feedback:
                return HTMLResponse(
                    status_code=400,
                    content=_render_feedback_page(
                        success=False,
                        message="Missing card_id or feedback parameter",
                    ),
                )

            if feedback not in ("positive", "negative"):
                return HTMLResponse(
                    status_code=400,
                    content=_render_feedback_page(
                        success=False,
                        message=f"Invalid feedback value: {feedback}. Must be 'positive' or 'negative'",
                    ),
                )

            # Update the feedback in the feedback loop
            from gchat.feedback_loop import get_feedback_loop

            feedback_loop = get_feedback_loop()

            # Handle dual feedback types
            if feedback_type == "content":
                # Only update content feedback (affects inputs vector)
                success = feedback_loop.update_feedback(
                    card_id, content_feedback=feedback
                )
                feedback_label = "content"
            elif feedback_type == "form":
                # Only update form feedback (affects relationships vector)
                success = feedback_loop.update_feedback(card_id, form_feedback=feedback)
                feedback_label = "layout"
            else:
                # Legacy: update both (backwards compatibility)
                success = feedback_loop.update_feedback(card_id, feedback=feedback)
                feedback_label = "card"

            if success:
                logger.info(
                    f"✅ Feedback updated: {card_id[:8]}... -> {feedback} ({feedback_label})"
                )
                emoji = "👍" if feedback == "positive" else "👎"
                message = f"Thanks for your {feedback_label} feedback! {emoji}"

                # Try to render rich dashboard; fall back to simple page
                try:
                    dashboard_data = feedback_loop.get_pattern_dashboard_data(card_id)
                except Exception:
                    dashboard_data = None

                if dashboard_data:
                    from tools.feedback_dashboard import render_dashboard_page

                    html = render_dashboard_page(
                        dashboard_data, feedback, feedback_type, message
                    )
                else:
                    html = _render_feedback_page(
                        success=True,
                        message=message,
                        feedback=feedback,
                        feedback_type=feedback_type,
                    )

                return HTMLResponse(status_code=200, content=html)
            else:
                # Card ID not found - might be from before feedback loop was enabled
                # Still thank the user but note we couldn't find the card
                logger.warning(f"⚠️ Card not found for feedback: {card_id[:8]}...")
                return HTMLResponse(
                    status_code=200,
                    content=_render_feedback_page(
                        success=True,
                        message="Thanks for your feedback! (Card pattern not found in database)",
                        feedback=feedback,
                        feedback_type=feedback_type,
                    ),
                )

        except Exception as e:
            logger.error(f"❌ Feedback endpoint error: {e}")
            return HTMLResponse(
                status_code=500,
                content=_render_feedback_page(
                    success=False,
                    message=f"Error processing feedback: {str(e)}",
                ),
            )

    @mcp.custom_route("/card-feedback/stats", methods=["GET"])
    async def feedback_stats_endpoint(request: Any):
        """
        Show feedback statistics.

        Returns JSON with counts of positive/negative feedback.
        """
        from starlette.responses import JSONResponse

        try:
            from qdrant_client import models

            from config.qdrant_client import get_qdrant_client

            client = get_qdrant_client()
            collection = _settings.card_collection

            # Count positive feedback
            positive_count = client.count(
                collection_name=collection,
                count_filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="type",
                            match=models.MatchValue(value="instance_pattern"),
                        ),
                        models.FieldCondition(
                            key="feedback",
                            match=models.MatchValue(value="positive"),
                        ),
                    ]
                ),
            ).count

            # Count negative feedback
            negative_count = client.count(
                collection_name=collection,
                count_filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="type",
                            match=models.MatchValue(value="instance_pattern"),
                        ),
                        models.FieldCondition(
                            key="feedback",
                            match=models.MatchValue(value="negative"),
                        ),
                    ]
                ),
            ).count

            # Count pending (no feedback yet)
            pending_count = client.count(
                collection_name=collection,
                count_filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="type",
                            match=models.MatchValue(value="instance_pattern"),
                        ),
                    ],
                    must_not=[
                        models.FieldCondition(
                            key="feedback",
                            match=models.MatchValue(value="positive"),
                        ),
                        models.FieldCondition(
                            key="feedback",
                            match=models.MatchValue(value="negative"),
                        ),
                    ],
                ),
            ).count

            return JSONResponse(
                status_code=200,
                content={
                    "status": "ok",
                    "feedback_stats": {
                        "positive": positive_count,
                        "negative": negative_count,
                        "pending": pending_count,
                        "total_patterns": positive_count
                        + negative_count
                        + pending_count,
                    },
                },
            )

        except Exception as e:
            logger.error(f"❌ Feedback stats error: {e}")
            return JSONResponse(
                status_code=500,
                content={"status": "error", "message": str(e)},
            )

    # =========================================================================
    # EMAIL FEEDBACK ENDPOINT
    # =========================================================================

    @mcp.custom_route("/email-feedback", methods=["GET"])
    async def email_feedback_endpoint(request: Any):
        """
        Receive feedback from email buttons (signed redirect URLs).

        Query params:
            eid: Email identifier
            action: "positive" or "negative"
            type: "content" or "layout" (feedback category)
            exp: Expiry timestamp (unix)
            sig: HMAC-SHA256 signature

        Validates the signed token, records feedback, and returns
        an HTML confirmation page.
        """
        from starlette.responses import HTMLResponse

        try:
            query_params = dict(request.query_params)
            email_id = query_params.get("eid", "")
            action = query_params.get("action", "")
            feedback_type = query_params.get("type", "content")
            exp = query_params.get("exp", "")
            sig = query_params.get("sig", "")

            logger.info(
                f"📧 Email feedback received: eid={email_id[:8]}..., "
                f"action={action}, type={feedback_type}"
            )

            # Validate required params
            if not all([email_id, action, exp, sig]):
                return HTMLResponse(
                    status_code=400,
                    content=_render_email_feedback_page(
                        success=False,
                        message="Missing required parameters",
                    ),
                )

            if action not in ("positive", "negative"):
                return HTMLResponse(
                    status_code=400,
                    content=_render_email_feedback_page(
                        success=False,
                        message=f"Invalid action: {action}",
                    ),
                )

            # Verify signed token
            from gmail.email_feedback.urls import verify_feedback_url

            is_valid, error_msg = verify_feedback_url(
                email_id=email_id,
                action=action,
                feedback_type=feedback_type,
                exp=exp,
                sig=sig,
            )

            if not is_valid:
                return HTMLResponse(
                    status_code=403,
                    content=_render_email_feedback_page(
                        success=False,
                        message=error_msg or "Invalid or expired feedback link",
                    ),
                )

            # Store pattern in the shared card collection via FeedbackLoop.
            # Uses store_instance_pattern() which generates all 3 named vectors
            # (components, inputs, relationships) and stores card_id = email_id
            # so update_feedback() and get_pattern_dashboard_data() can find it.
            try:
                from gchat.feedback_loop import get_feedback_loop

                feedback_loop = get_feedback_loop()

                # Determine feedback fields
                content_fb = action if feedback_type == "content" else None
                form_fb = action if feedback_type == "layout" else None

                feedback_loop.store_instance_pattern(
                    card_description=f"Email feedback ({feedback_type})",
                    component_paths=[
                        "DividerBlock",
                        "TextBlock",
                        "ButtonBlock",
                        "ButtonBlock",
                    ],
                    instance_params={
                        "email_id": email_id,
                        "feedback_type": feedback_type,
                        "source": "email_feedback",
                    },
                    content_feedback=content_fb,
                    form_feedback=form_fb,
                    card_id=email_id,
                    structure_description="Email feedback section with divider, prompt, and two buttons",
                    pattern_type="feedback_ui",
                )
            except Exception as e:
                logger.warning(f"Could not store email feedback pattern: {e}")

            emoji = "\U0001f44d" if action == "positive" else "\U0001f44e"
            type_label = "content" if feedback_type == "content" else "layout"
            message = f"Thanks for your {type_label} feedback! {emoji}"

            # Try rich dashboard (reuses card dashboard renderer)
            try:
                from gchat.feedback_loop import get_feedback_loop

                fl = get_feedback_loop()
                dashboard_data = fl.get_pattern_dashboard_data(email_id)
            except Exception:
                dashboard_data = None

            if dashboard_data:
                from tools.feedback_dashboard import render_dashboard_page

                html_content = render_dashboard_page(
                    dashboard_data, action, feedback_type, message
                )
            else:
                html_content = _render_email_feedback_page(
                    success=True,
                    message=message,
                    feedback=action,
                    feedback_type=feedback_type,
                    email_id=email_id,
                )

            return HTMLResponse(status_code=200, content=html_content)

        except Exception as e:
            logger.error(f"Email feedback endpoint error: {e}")
            return HTMLResponse(
                status_code=500,
                content=_render_email_feedback_page(
                    success=False,
                    message=f"Error processing feedback: {str(e)}",
                ),
            )

    logger.info("Feedback endpoints registered:")
    logger.info("   /card-feedback - Receive feedback from card buttons")
    logger.info("   /card-feedback/stats - View feedback statistics")
    logger.info("   /email-feedback - Receive feedback from email buttons")


def _render_feedback_page(
    success: bool, message: str, feedback: str = None, feedback_type: str = None
) -> str:
    """Render a simple HTML page for feedback response."""
    bg_color = "#1a1a2e" if success else "#2e1a1a"
    text_color = "#e0e0e0"
    accent_color = (
        "#4ade80"
        if feedback == "positive"
        else "#f87171"
        if feedback == "negative"
        else "#60a5fa"
    )

    emoji = ""
    if feedback == "positive":
        emoji = "👍"
    elif feedback == "negative":
        emoji = "👎"

    # Add feedback type indicator
    type_label = ""
    if feedback_type == "content":
        type_label = "Content feedback recorded"
    elif feedback_type == "form":
        type_label = "Layout feedback recorded"

    return f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Card Feedback</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background-color: {bg_color};
            color: {text_color};
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            margin: 0;
            padding: 20px;
            box-sizing: border-box;
        }}
        .container {{
            text-align: center;
            max-width: 400px;
            padding: 40px;
            background: rgba(255, 255, 255, 0.05);
            border-radius: 16px;
            box-shadow: 0 4px 24px rgba(0, 0, 0, 0.2);
        }}
        .emoji {{
            font-size: 64px;
            margin-bottom: 20px;
        }}
        .message {{
            font-size: 18px;
            line-height: 1.6;
            color: {accent_color};
        }}
        .type-label {{
            font-size: 12px;
            color: #a0a0a0;
            margin-top: 10px;
            font-style: italic;
        }}
        .subtitle {{
            font-size: 14px;
            color: #888;
            margin-top: 20px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="emoji">{emoji if emoji else ("✅" if success else "❌")}</div>
        <div class="message">{message}</div>
        {f'<div class="type-label">{type_label}</div>' if type_label else ""}
        <div class="subtitle">You can close this window.</div>
    </div>
</body>
</html>
"""


def _render_email_feedback_page(
    success: bool,
    message: str,
    feedback: str = None,
    feedback_type: str = None,
    email_id: str = None,
) -> str:
    """Render a dashboard-style HTML page for email feedback responses.

    Uses the same dark-themed, card-surface visual style as the card
    feedback dashboard so the UX is consistent across email and chat.
    """
    import html as _html
    import time as _time

    accent = (
        "#4ade80"
        if feedback == "positive"
        else "#f87171"
        if feedback == "negative"
        else "#60a5fa"
    )

    emoji = ""
    if feedback == "positive":
        emoji = "\U0001f44d"
    elif feedback == "negative":
        emoji = "\U0001f44e"
    elif success:
        emoji = "\u2705"
    else:
        emoji = "\u274c"

    type_label = ""
    if feedback_type == "content":
        type_label = "Email content feedback recorded"
    elif feedback_type == "layout":
        type_label = "Email layout feedback recorded"

    # Metadata section (only on success)
    meta_html = ""
    if success and email_id:
        fb_color = "#4ade80" if feedback == "positive" else "#f87171"
        fb_pill = (
            f'<span class="pill" style="background:{fb_color}20;color:{fb_color}">'
            f"{_html.escape(feedback_type or 'general')}: "
            f"{_html.escape(feedback or 'unknown')}</span>"
        )
        ts = _time.strftime("%Y-%m-%dT%H:%M:%S")
        meta_html = f"""
    <section class="card-surface">
        <h2>Email Feedback Details</h2>
        <div class="meta-grid">
            <div class="meta-item">
                <span class="meta-label">Email ID</span>
                <code class="meta-value">{_html.escape((email_id or '')[:16])}...</code>
            </div>
            <div class="meta-item">
                <span class="meta-label">Source</span>
                <span class="meta-value">Email redirect button</span>
            </div>
            <div class="meta-item">
                <span class="meta-label">Timestamp</span>
                <span class="meta-value">{ts}</span>
            </div>
            <div class="meta-item">
                <span class="meta-label">Feedback</span>
                <span class="meta-value">{fb_pill}</span>
            </div>
        </div>
    </section>"""

    # Status section for errors
    error_section = ""
    if not success:
        error_section = f"""
    <section class="card-surface" style="border-color:rgba(248,113,113,0.3)">
        <h2 style="color:#f87171">Error</h2>
        <p style="color:#e0e0e0">{_html.escape(message)}</p>
    </section>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Email Feedback</title>
    <style>
        :root {{
            --bg: #1a1a2e;
            --surface: rgba(255,255,255,0.05);
            --border: rgba(255,255,255,0.08);
            --text: #e0e0e0;
            --text-dim: #888;
            --green: #4ade80;
            --red: #f87171;
            --blue: #60a5fa;
        }}
        *,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
        body{{
            font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
            background:var(--bg);color:var(--text);
            padding:24px;max-width:640px;margin:0 auto;
            line-height:1.5;
        }}
        h1{{font-size:1.3rem;font-weight:600}}
        h2{{font-size:1rem;font-weight:600;margin-bottom:12px;color:var(--blue)}}
        code{{font-family:'SF Mono',Monaco,Consolas,monospace;font-size:0.85em}}
        .dash-header{{text-align:center;padding:24px 0 16px}}
        .header-emoji{{font-size:48px;display:block;margin-bottom:8px}}
        .type-label{{font-size:0.8rem;color:var(--text-dim);font-style:italic;margin-top:4px}}
        .card-surface{{
            background:var(--surface);border:1px solid var(--border);
            border-radius:16px;padding:20px;margin:16px 0;
            box-shadow:0 4px 24px rgba(0,0,0,0.2);
        }}
        .meta-grid{{display:grid;gap:8px}}
        .meta-item{{display:flex;gap:12px;align-items:baseline}}
        .meta-label{{font-size:0.8rem;color:var(--text-dim);min-width:90px;flex-shrink:0}}
        .meta-value{{font-size:0.85rem}}
        .pill{{
            display:inline-block;padding:2px 8px;border-radius:10px;
            font-size:0.75rem;font-weight:500;
        }}
        .dash-footer{{
            text-align:center;color:var(--text-dim);font-size:0.85rem;
            padding:24px 0 8px;
        }}
    </style>
</head>
<body>
    <header class="dash-header">
        <span class="header-emoji">{emoji}</span>
        <h1 style="color:{accent}">{_html.escape(message)}</h1>
        {f'<p class="type-label">{_html.escape(type_label)}</p>' if type_label else ""}
    </header>
    {meta_html}
    {error_section}
    <footer class="dash-footer">You can close this window.</footer>
</body>
</html>"""
