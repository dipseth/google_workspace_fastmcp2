"""Feedback endpoints for SmartCardBuilder feedback loop.

This module provides HTTP endpoints for capturing card feedback from users.
When users click 👍/👎 buttons on cards, they're directed here to record feedback.
"""

import logging
from typing import Any
from urllib.parse import parse_qs, urlparse

from fastmcp import FastMCP

from config.settings import settings as _settings

logger = logging.getLogger(__name__)


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
                return HTMLResponse(
                    status_code=200,
                    content=_render_feedback_page(
                        success=True,
                        message=f"Thanks for your {feedback_label} feedback! {emoji}",
                        feedback=feedback,
                        feedback_type=feedback_type,
                    ),
                )
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

    logger.info("✅ Feedback endpoints registered:")
    logger.info("   • /card-feedback - Receive feedback from card buttons")
    logger.info("   • /card-feedback/stats - View feedback statistics")


def _render_feedback_page(
    success: bool, message: str, feedback: str = None, feedback_type: str = None
) -> str:
    """Render a simple HTML page for feedback response."""
    bg_color = "#1a1a2e" if success else "#2e1a1a"
    text_color = "#e0e0e0"
    accent_color = (
        "#4ade80"
        if feedback == "positive"
        else "#f87171" if feedback == "negative" else "#60a5fa"
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
