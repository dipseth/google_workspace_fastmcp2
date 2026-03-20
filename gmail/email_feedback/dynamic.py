"""
Dynamic email feedback builder using ModuleWrapper's DAG and variation system.

Mirrors gchat/card_builder/feedback/dynamic.py but produces EmailBlock
instances (DividerBlock, TextBlock, ButtonBlock) instead of Google Chat
widget dicts. Uses signed redirect URLs instead of onClick callbacks.

Usage:
    builder = EmailFeedbackBuilder()
    blocks = builder.build_feedback_blocks(
        email_id="msg_abc123",
        base_url="https://server.example.com",
        feedback_type="content",
        variation_type="parameter",
    )
    # Returns list of EmailBlock instances to append to EmailSpec.blocks
"""

import random
from typing import Any, Dict, List, Optional

from config.enhanced_logging import setup_logger
from gmail.email_feedback.components import BUTTON_STYLES, LAYOUT_WRAPPERS
from gmail.email_feedback.prompts import (
    CONTENT_FEEDBACK_PROMPTS,
    LAYOUT_FEEDBACK_PROMPTS,
    NEGATIVE_EMOJI_LABELS,
    NEGATIVE_LABELS,
    POSITIVE_EMOJI_LABELS,
    POSITIVE_LABELS,
)
from gmail.email_feedback.urls import generate_feedback_url
from gmail.mjml_types import ButtonBlock, DividerBlock, EmailBlock, TextBlock

logger = setup_logger()

class EmailFeedbackBuilder:
    """
    Builds email feedback blocks dynamically using the module wrapper's DAG
    and variation system.

    Produces EmailBlock instances that can be appended to EmailSpec.blocks.
    Uses signed redirect URLs for feedback button hrefs.

    Supports:
    - Content feedback (rates data accuracy)
    - Layout feedback (rates formatting/design)
    - Multiple layout styles (with_divider, compact, footer_style)
    - Multiple button styles (standard, subtle, outline, brand)
    - Variation via StructureVariator and ParameterVariator
    """

    # Valid block types for feedback by role
    FEEDBACK_BLOCK_TYPES = {
        "text_prompt": ["TextBlock"],
        "action_button": ["ButtonBlock"],
        "separator": ["DividerBlock"],
    }

    def __init__(self, wrapper=None):
        """
        Initialize the email feedback builder.

        Args:
            wrapper: ModuleWrapper instance (optional, fetched lazily).
        """
        self._wrapper = wrapper
        self._structure_variator = None
        self._param_variator = None

    @staticmethod
    def _get_feedback_base_url() -> str:
        """Get the feedback base URL from settings.

        Uses ``settings.feedback_base_url`` — the same URL used by the card
        feedback system (``FEEDBACK_BASE_URL`` env var, falling back to
        ``settings.base_url``).

        Returns:
            Base URL string, or empty string if not configured.
        """
        try:
            from config.settings import settings

            return settings.feedback_base_url or ""
        except Exception:
            return ""

    def _get_wrapper(self):
        """Get or create the email module wrapper instance."""
        if self._wrapper is None:
            try:
                from gmail.email_wrapper_setup import get_email_wrapper

                self._wrapper = get_email_wrapper()
            except (ImportError, Exception) as e:
                logger.debug(f"Could not get email wrapper: {e}")
        return self._wrapper

    def _get_structure_variator(self):
        """Get or create the structure variator from wrapper's relationships."""
        if self._structure_variator is None:
            wrapper = self._get_wrapper()
            if wrapper:
                try:
                    from adapters.module_wrapper.instance_pattern_mixin import (
                        StructureVariator,
                    )

                    relationships = getattr(wrapper, "relationships", {})
                    feedback_rels = self._get_feedback_relationships()
                    relationships = {**relationships, **feedback_rels}
                    self._structure_variator = StructureVariator(relationships)
                except Exception as e:
                    logger.debug(f"Could not create structure variator: {e}")
        return self._structure_variator

    def _get_param_variator(self):
        """Get or create the parameter variator."""
        if self._param_variator is None:
            try:
                from adapters.module_wrapper.instance_pattern_mixin import (
                    ParameterVariator,
                )

                custom_variators = {
                    "prompt": self._vary_prompt,
                    "button_style": self._vary_button_style,
                }
                self._param_variator = ParameterVariator(custom_variators)
            except Exception as e:
                logger.debug(f"Could not create parameter variator: {e}")
        return self._param_variator

    def _get_feedback_relationships(self) -> Dict[str, List[str]]:
        """Define email feedback block containment relationships."""
        return {
            "EmailFeedbackSection": [
                "TextBlock",
                "ButtonBlock",
                "DividerBlock",
            ],
            "EmailFeedbackPrompt": ["TextBlock"],
            "EmailFeedbackAction": ["ButtonBlock"],
            "TextBlock": [],
            "ButtonBlock": [],
            "DividerBlock": [],
        }

    def _vary_prompt(self, value: str) -> str:
        """Custom variator for feedback prompt text.

        Returns plain text only — no HTML tags — because TextBlock
        escapes HTML in to_mjml().
        """
        if "{keyword}" in str(value):
            return value
        # Plain-text emphasis only
        return value

    def _vary_button_style(self, value: str) -> str:
        """Custom variator for button style names."""
        styles = list(BUTTON_STYLES.keys())
        return random.choice(styles)

    def _select_prompt(
        self, feedback_type: str
    ) -> tuple[str, str]:
        """Select a random prompt template and keyword for the feedback type."""
        if feedback_type == "layout":
            prompts = LAYOUT_FEEDBACK_PROMPTS
        else:
            prompts = CONTENT_FEEDBACK_PROMPTS
        return random.choice(prompts)

    def _select_labels(
        self, use_emoji: bool = False
    ) -> tuple[str, str]:
        """Select random positive and negative button labels."""
        if use_emoji:
            return (
                random.choice(POSITIVE_EMOJI_LABELS),
                random.choice(NEGATIVE_EMOJI_LABELS),
            )
        return (
            random.choice(POSITIVE_LABELS),
            random.choice(NEGATIVE_LABELS),
        )

    def _build_prompt_block(
        self,
        feedback_type: str,
    ) -> TextBlock:
        """Build a TextBlock containing the feedback prompt.

        Uses plain text (no HTML) because TextBlock.to_mjml() escapes HTML.
        The keyword is inserted as-is; the entire prompt is styled via
        TextBlock.color and font_size.
        """
        template, keyword = self._select_prompt(feedback_type)
        prompt_text = template.format(keyword=keyword)

        return TextBlock(
            text=prompt_text,
            font_size="14px",
            color="#64748B",
            align="center",
            padding="4px 0 8px 0",
        )

    def _build_button_blocks(
        self,
        email_id: str,
        base_url: str,
        feedback_type: str,
        button_style_name: str = "standard",
        use_emoji: bool = False,
    ) -> List[ButtonBlock]:
        """Build positive and negative feedback ButtonBlocks with signed URLs.

        Args:
            email_id: Unique email identifier for URL signing.
            base_url: Server base URL for redirect endpoint.
            feedback_type: "content" or "layout".
            button_style_name: Key into BUTTON_STYLES.
            use_emoji: Whether to use emoji labels.

        Returns:
            List of two ButtonBlocks [positive, negative].
        """
        pos_label, neg_label = self._select_labels(use_emoji)
        style = BUTTON_STYLES.get(button_style_name, BUTTON_STYLES["standard"])

        pos_url = generate_feedback_url(
            base_url=base_url,
            email_id=email_id,
            action="positive",
            feedback_type=feedback_type,
        )
        neg_url = generate_feedback_url(
            base_url=base_url,
            email_id=email_id,
            action="negative",
            feedback_type=feedback_type,
        )

        return [
            ButtonBlock(
                text=pos_label,
                url=pos_url,
                background_color=style["positive_bg"],
                color=style["text_color"],
                border_radius="6px",
                align="center",
                padding="4px 8px 4px 0",
            ),
            ButtonBlock(
                text=neg_label,
                url=neg_url,
                background_color=style["negative_bg"],
                color=style["text_color"],
                border_radius="6px",
                align="center",
                padding="4px 0 4px 8px",
            ),
        ]

    def build_feedback_blocks(
        self,
        email_id: str,
        base_url: Optional[str] = None,
        feedback_type: str = "content",
        layout: Optional[str] = None,
        button_style: Optional[str] = None,
        use_emoji: bool = False,
        variation_type: Optional[str] = None,
    ) -> List[EmailBlock]:
        """
        Build feedback blocks to append to an EmailSpec.

        This is the main entry point for email feedback generation.

        Args:
            email_id: Unique email identifier (used in signed URLs).
            base_url: Server base URL. If None, resolved from
                ``settings.feedback_base_url`` (same as card feedback).
            feedback_type: "content" or "layout".
            layout: Layout wrapper style (default: random from LAYOUT_WRAPPERS).
            button_style: Button color scheme (default: random from BUTTON_STYLES).
            use_emoji: Whether to use emoji labels on buttons.
            variation_type: "structure", "parameter", or None for random.

        Returns:
            List of EmailBlock instances to append to EmailSpec.blocks.
        """
        if not base_url:
            base_url = self._get_feedback_base_url()
        if not base_url:
            logger.warning("No feedback base URL configured; cannot build feedback blocks")
            return []
        layout = layout or random.choice(LAYOUT_WRAPPERS)
        button_style = button_style or random.choice(list(BUTTON_STYLES.keys()))

        # Apply parameter variation if requested
        if variation_type == "parameter":
            variator = self._get_param_variator()
            if variator:
                params = {
                    "button_style": button_style,
                    "layout": layout,
                }
                varied = variator.vary_params(params)
                button_style = varied.get("button_style", button_style)
                layout = varied.get("layout", layout)

        blocks: List[EmailBlock] = []

        # Add separator based on layout
        if layout == "with_divider":
            blocks.append(DividerBlock(padding="16px 0 8px 0"))
        elif layout == "compact":
            pass  # No separator
        elif layout == "footer_style":
            blocks.append(DividerBlock(padding="24px 0 8px 0"))

        # Add prompt text
        prompt_block = self._build_prompt_block(feedback_type)
        blocks.append(prompt_block)

        # Add feedback buttons
        button_blocks = self._build_button_blocks(
            email_id=email_id,
            base_url=base_url,
            feedback_type=feedback_type,
            button_style_name=button_style,
            use_emoji=use_emoji,
        )
        blocks.extend(button_blocks)

        return blocks

    def build_dual_feedback_blocks(
        self,
        email_id: str,
        base_url: Optional[str] = None,
        layout: Optional[str] = None,
        button_style: Optional[str] = None,
        use_emoji: bool = False,
    ) -> List[EmailBlock]:
        """
        Build both content and layout feedback blocks.

        Produces a combined section with content feedback first,
        then layout feedback.

        Args:
            email_id: Unique email identifier.
            base_url: Server base URL. If None, resolved from
                ``settings.feedback_base_url``.
            layout: Layout wrapper style.
            button_style: Button color scheme.
            use_emoji: Whether to use emoji labels.

        Returns:
            List of EmailBlock instances for both feedback types.
        """
        layout = layout or "with_divider"
        button_style = button_style or random.choice(list(BUTTON_STYLES.keys()))

        blocks: List[EmailBlock] = []

        # Content feedback
        content_blocks = self.build_feedback_blocks(
            email_id=email_id,
            base_url=base_url,
            feedback_type="content",
            layout=layout,
            button_style=button_style,
            use_emoji=use_emoji,
        )
        blocks.extend(content_blocks)

        # Layout feedback (compact, no extra divider)
        layout_blocks = self.build_feedback_blocks(
            email_id=email_id,
            base_url=base_url,
            feedback_type="layout",
            layout="compact",
            button_style=button_style,
            use_emoji=use_emoji,
        )
        blocks.extend(layout_blocks)

        return blocks

    def store_feedback_pattern(
        self,
        email_id: str,
        feedback: str = "positive",
        feedback_type: str = "content",
    ) -> Optional[str]:
        """
        Store a successful email feedback pattern for learning.

        Args:
            email_id: Email identifier.
            feedback: "positive" or "negative".
            feedback_type: "content" or "layout".

        Returns:
            Pattern ID if stored, None otherwise.
        """
        wrapper = self._get_wrapper()
        if not wrapper or not hasattr(wrapper, "store_instance_pattern"):
            return None

        component_paths = ["DividerBlock", "TextBlock", "ButtonBlock", "ButtonBlock"]
        instance_params = {
            "email_id": email_id,
            "feedback_type": feedback_type,
        }

        # Store card_id as top-level payload field (via metadata) so
        # FeedbackLoop.update_feedback() and get_pattern_dashboard_data()
        # can find this pattern using the same lookup as card patterns.
        metadata = {
            "card_id": email_id,
            "source": "email_feedback",
            "card_description": f"Email feedback ({feedback_type})",
        }

        try:
            return wrapper.store_instance_pattern(
                component_paths=component_paths,
                instance_params=instance_params,
                description=f"Email feedback pattern ({feedback_type})",
                feedback=feedback,
                metadata=metadata,
                generate_variations=feedback == "positive",
            )
        except Exception as e:
            logger.warning(f"Failed to store email feedback pattern: {e}")
            return None

# Global singleton
_email_feedback_builder: Optional[EmailFeedbackBuilder] = None

def get_email_feedback_builder() -> EmailFeedbackBuilder:
    """Get the singleton EmailFeedbackBuilder instance."""
    global _email_feedback_builder
    if _email_feedback_builder is None:
        _email_feedback_builder = EmailFeedbackBuilder()
    return _email_feedback_builder

__all__ = [
    "EmailFeedbackBuilder",
    "get_email_feedback_builder",
]
