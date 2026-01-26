"""
Smart Card Builder v2 - DSL + Embeddings Focused

A streamlined card builder that uses:
1. Structure DSL: §[δ×3, Ƀ[ᵬ×2]] for component hierarchy
2. Content DSL: δ 'text' success bold for styled content
3. Qdrant ColBERT embeddings for semantic search
4. ModuleWrapper for component loading

This replaces the legacy NL parsing with a cleaner DSL-first approach.

Usage:
    builder = SmartCardBuilderV2()
    card = builder.build(
        description="§[δ×3, Ƀ[ᵬ×2]] Dashboard\\n\\nδ 'Status: Online' success bold",
        title="My Card"
    )
"""

import json
import logging
import os
import random
import uuid
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv

from config.settings import settings as _settings
from middleware.filters.styling_filters import SEMANTIC_COLORS

load_dotenv()

logger = logging.getLogger(__name__)

# Feature flag for feedback buttons
ENABLE_FEEDBACK_BUTTONS = os.getenv("ENABLE_CARD_FEEDBACK", "true").lower() == "true"


# =============================================================================
# FEEDBACK CONTENT POOLS
# =============================================================================

CONTENT_FEEDBACK_PROMPTS = [
    "Was the <b>content</b> correct?",
    "Did the <b>data</b> look right?",
    "Were the <b>values</b> accurate?",
    "Was the <b>information</b> helpful?",
    "Were the <b>details</b> correct?",
]

FORM_FEEDBACK_PROMPTS = [
    "Was the <b>layout</b> correct?",
    "Did the <b>structure</b> look good?",
    "Was the <b>formatting</b> appropriate?",
    "Did the <b>arrangement</b> work well?",
    "Was the <b>design</b> suitable?",
]

POSITIVE_LABELS = ["👍 Good", "👍 Yes", "👍 Correct", "✅ Looks good", "👍 Accurate"]
NEGATIVE_LABELS = ["👎 Bad", "👎 No", "👎 Wrong", "❌ Needs work", "👎 Not quite"]


# =============================================================================
# COMPONENT PATHS REGISTRY
# =============================================================================

COMPONENT_PATHS = {
    "Section": "card_framework.v2.section.Section",
    "Card": "card_framework.v2.card.Card",
    "CardHeader": "card_framework.v2.card.CardHeader",
    "Columns": "card_framework.v2.widgets.columns.Columns",
    "Column": "card_framework.v2.widgets.columns.Column",
    "DecoratedText": "card_framework.v2.widgets.decorated_text.DecoratedText",
    "TextParagraph": "card_framework.v2.widgets.text_paragraph.TextParagraph",
    "Image": "card_framework.v2.widgets.image.Image",
    "Divider": "card_framework.v2.widgets.divider.Divider",
    "Button": "card_framework.v2.widgets.decorated_text.Button",
    "ButtonList": "card_framework.v2.widgets.button_list.ButtonList",
    "Icon": "card_framework.v2.widgets.decorated_text.Icon",
    "OnClick": "card_framework.v2.widgets.decorated_text.OnClick",
    "TextInput": "card_framework.v2.widgets.text_input.TextInput",
    "SelectionInput": "card_framework.v2.widgets.selection_input.SelectionInput",
    "DateTimePicker": "card_framework.v2.widgets.date_time_picker.DateTimePicker",
    "Grid": "card_framework.v2.widgets.grid.Grid",
    "GridItem": "card_framework.v2.widgets.grid.GridItem",
    "ImageComponent": "card_framework.v2.widgets.grid.ImageComponent",
}

FEEDBACK_DETECTION_PATTERNS = [
    "feedback",
    "👍",
    "👎",
    "feedback_type=content",
    "feedback_type=form",
]


class SmartCardBuilderV2:
    """
    Streamlined card builder using DSL + Qdrant embeddings.

    Flow:
    1. Parse Structure DSL from description (e.g., §[δ×3, Ƀ[ᵬ×2]])
    2. Parse Content DSL for styled content (e.g., δ 'text' success bold)
    3. Build card from parsed structure with styled content
    4. Add feedback section for learning loop
    """

    def __init__(self):
        """Initialize the builder."""
        self._wrapper = None
        self._qdrant_client = None
        self._embedder = None

    # =========================================================================
    # INFRASTRUCTURE
    # =========================================================================

    def _get_wrapper(self):
        """Get or create the ModuleWrapper singleton."""
        if self._wrapper is None:
            try:
                from gchat.card_framework_wrapper import get_card_framework_wrapper
                self._wrapper = get_card_framework_wrapper()
            except Exception as e:
                logger.warning(f"Could not get ModuleWrapper: {e}")
        return self._wrapper

    def _get_qdrant_client(self):
        """Get or create the Qdrant client."""
        if self._qdrant_client is None:
            try:
                from config.qdrant_client import get_qdrant_client
                self._qdrant_client = get_qdrant_client()
            except Exception as e:
                logger.warning(f"Could not get Qdrant client: {e}")
        return self._qdrant_client

    def _get_dsl_parser(self):
        """Get the DSL parser from card_framework_wrapper."""
        try:
            from gchat.card_framework_wrapper import get_dsl_parser
            return get_dsl_parser()
        except Exception as e:
            logger.warning(f"Could not get DSL parser: {e}")
            return None

    # =========================================================================
    # DSL EXTRACTION
    # =========================================================================

    def _extract_structure_dsl(self, description: str) -> Optional[str]:
        """
        Extract Structure DSL notation from description.

        Example: "§[δ×3, Ƀ[ᵬ×2]] Dashboard" → "§[δ×3, Ƀ[ᵬ×2]]"
        """
        if not description:
            return None

        try:
            from gchat.card_framework_wrapper import extract_dsl_from_description
            return extract_dsl_from_description(description)
        except Exception as e:
            logger.debug(f"DSL extraction failed: {e}")
            return None

    def _parse_content_dsl(self, description: str) -> Optional[Dict[str, Any]]:
        """
        Parse Content DSL from description.

        Content DSL format:
            δ 'Status: Online' success bold
            ᵬ Click Here https://example.com

        Returns dict with styled texts and buttons.
        """
        if not description:
            return None

        try:
            parser = self._get_dsl_parser()
            if not parser:
                return None

            # Extract content after Structure DSL
            structure_dsl = self._extract_structure_dsl(description)
            if structure_dsl:
                content_text = description[len(structure_dsl):].strip()
            else:
                content_text = description.strip()

            if not content_text:
                return None

            # Find Content DSL lines (starting with symbols)
            symbols = set(parser.reverse_symbols.keys())
            lines = content_text.split('\n')

            content_dsl_lines = []
            for line in lines:
                stripped = line.strip()
                if not stripped:
                    continue
                if stripped[0] in symbols:
                    content_dsl_lines.append(line)
                elif line.startswith(("  ", "\t")) and content_dsl_lines:
                    content_dsl_lines.append(line)

            if not content_dsl_lines:
                return None

            # Parse Content DSL
            content_dsl_text = '\n'.join(content_dsl_lines)
            result = parser.parse_content_dsl(content_dsl_text)

            if not result.is_valid or not result.blocks:
                return None

            logger.info(f"🎨 Content DSL: Parsed {len(result.blocks)} blocks")

            # Build structured result
            parsed = {"blocks": [], "buttons": [], "texts": []}

            for block in result.blocks:
                block_info = {
                    "symbol": block.primary.symbol,
                    "component": block.primary.component_name,
                    "content": block.full_content,
                    "styles": [m.name for m in block.primary.modifiers],
                    "url": block.primary.url,
                }
                parsed["blocks"].append(block_info)

                if block.primary.component_name == "Button":
                    parsed["buttons"].append({
                        "text": block.full_content,
                        "url": block.primary.url,
                    })
                else:
                    styled = self._apply_styles(
                        block.full_content,
                        [m.name for m in block.primary.modifiers]
                    )
                    parsed["texts"].append({
                        "content": block.full_content,
                        "styled": styled,
                        "component": block.primary.component_name,
                    })

            return parsed

        except Exception as e:
            logger.debug(f"Content DSL parsing failed: {e}")
            return None

    def _apply_styles(self, text: str, styles: List[str]) -> str:
        """Apply Content DSL styles to text, generating Google Chat HTML."""
        result = text
        color = None
        is_bold = False
        is_italic = False
        is_strike = False

        for style in styles:
            style_lower = style.lower()

            # Check semantic colors
            if style_lower in SEMANTIC_COLORS:
                color = SEMANTIC_COLORS[style_lower]
            elif style_lower == "bold":
                is_bold = True
            elif style_lower == "italic":
                is_italic = True
            elif style_lower in ("strike", "strikethrough"):
                is_strike = True
            elif style_lower in ("success", "ok", "active"):
                color = SEMANTIC_COLORS.get("success", "#34a853")
            elif style_lower in ("error", "danger", "failed"):
                color = SEMANTIC_COLORS.get("error", "#ea4335")
            elif style_lower in ("warning", "caution", "pending"):
                color = SEMANTIC_COLORS.get("warning", "#fbbc05")
            elif style_lower in ("info", "note", "notice"):
                color = SEMANTIC_COLORS.get("info", "#4285f4")

        # Apply formatting (innermost first)
        if is_strike:
            result = f"<s>{result}</s>"
        if is_italic:
            result = f"<i>{result}</i>"
        if is_bold:
            result = f"<b>{result}</b>"
        if color:
            result = f'<font color="{color}">{result}</font>'

        return result

    # =========================================================================
    # CARD BUILDING FROM DSL
    # =========================================================================

    def _build_from_dsl(
        self,
        structure_dsl: str,
        description: str,
        title: Optional[str] = None,
        subtitle: Optional[str] = None,
        buttons: Optional[List[Dict]] = None,
        image_url: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Build a card from parsed DSL structure."""
        wrapper = self._get_wrapper()
        if not wrapper:
            return None

        try:
            validator = wrapper.get_structure_validator()
            parsed = validator.parse_structure(structure_dsl)
            if not parsed:
                return None

            logger.info(f"📐 Parsed DSL into {len(parsed)} component(s)")

            # Parse Content DSL for styled content
            content_dsl = self._parse_content_dsl(description)

            # Override buttons with Content DSL buttons
            if content_dsl and content_dsl.get("buttons") and not buttons:
                buttons = content_dsl["buttons"]

            # Build sections from structure
            sections = []
            text_index = 0

            content_texts = content_dsl.get("texts", []) if content_dsl else []

            for component in parsed:
                comp_name = component.get("name", "")
                multiplier = component.get("multiplier", 1)
                children = component.get("children", [])

                if comp_name == "Section":
                    widgets = self._build_widgets(
                        children, buttons, image_url, content_texts
                    )
                    if widgets:
                        sections.append({"widgets": widgets})

                elif comp_name == "ButtonList":
                    btn_widget = self._build_button_list(children, buttons, multiplier)
                    if btn_widget:
                        sections.append({"widgets": [btn_widget]})

                elif comp_name == "Grid":
                    grid_widget = self._build_grid(children, multiplier)
                    if grid_widget:
                        sections.append({"widgets": [grid_widget]})

                elif comp_name == "DecoratedText":
                    for _ in range(multiplier):
                        if text_index < len(content_texts):
                            widget_text = content_texts[text_index].get("styled", "")
                            text_index += 1
                        else:
                            widget_text = f"Item {text_index + 1}"
                            text_index += 1

                        sections.append({
                            "widgets": [{"decoratedText": {"text": widget_text, "wrapText": True}}]
                        })

            if not sections:
                return None

            # Build card
            card = {"sections": sections}

            if title:
                card["header"] = {"title": title}
                if subtitle:
                    card["header"]["subtitle"] = subtitle

            return card

        except Exception as e:
            logger.warning(f"DSL card building failed: {e}")
            return None

    def _build_widgets(
        self,
        children: List[Dict],
        buttons: Optional[List[Dict]],
        image_url: Optional[str],
        content_texts: List[Dict],
    ) -> List[Dict]:
        """Build widgets from DSL children."""
        widgets = []
        text_index = 0

        for child in children:
            child_name = child.get("name", "")
            multiplier = child.get("multiplier", 1)
            grandchildren = child.get("children", [])

            for _ in range(multiplier):
                if child_name == "DecoratedText":
                    if text_index < len(content_texts):
                        widget_text = content_texts[text_index].get("styled", "")
                        text_index += 1
                    else:
                        widget_text = f"Item {text_index + 1}"
                        text_index += 1

                    widgets.append({"decoratedText": {"text": widget_text, "wrapText": True}})

                elif child_name == "TextParagraph":
                    if text_index < len(content_texts):
                        widget_text = content_texts[text_index].get("styled", "")
                        text_index += 1
                    else:
                        widget_text = f"Paragraph {text_index + 1}"
                        text_index += 1

                    widgets.append({"textParagraph": {"text": widget_text}})

                elif child_name == "ButtonList":
                    btn_widget = self._build_button_list(grandchildren, buttons, 1)
                    if btn_widget:
                        widgets.append(btn_widget)

                elif child_name == "Grid":
                    grid_widget = self._build_grid(grandchildren, 1)
                    if grid_widget:
                        widgets.append(grid_widget)

                elif child_name == "Image":
                    if image_url:
                        widgets.append({"image": {"imageUrl": image_url}})

        return widgets

    def _build_button_list(
        self,
        children: List[Dict],
        buttons: Optional[List[Dict]],
        parent_multiplier: int,
    ) -> Optional[Dict]:
        """Build a buttonList widget."""
        expected = sum(
            c.get("multiplier", 1) for c in children if c.get("name") == "Button"
        ) or parent_multiplier

        btn_list = []
        if buttons:
            for btn in buttons[:expected]:
                if isinstance(btn, dict):
                    btn_obj = {"text": btn.get("text", "Button")}
                    if btn.get("url"):
                        btn_obj["onClick"] = {"openLink": {"url": btn["url"]}}
                    btn_list.append(btn_obj)
        else:
            for i in range(expected):
                btn_list.append({"text": f"Button {i+1}"})

        return {"buttonList": {"buttons": btn_list}} if btn_list else None

    def _build_grid(self, children: List[Dict], multiplier: int) -> Optional[Dict]:
        """Build a grid widget."""
        expected = sum(
            c.get("multiplier", 1) for c in children if c.get("name") == "GridItem"
        ) or multiplier

        items = [
            {"title": f"Item {i+1}", "image": {"imageUri": f"https://picsum.photos/200/200?{i}"}}
            for i in range(expected)
        ]

        return {"grid": {"columnCount": min(3, len(items)), "items": items}} if items else None

    # =========================================================================
    # FEEDBACK SECTION
    # =========================================================================

    def _has_feedback(self, card: Dict) -> bool:
        """Check if card already has feedback content."""
        card_str = json.dumps(card).lower()
        return any(p.lower() in card_str for p in FEEDBACK_DETECTION_PATTERNS)

    def _create_feedback_section(self, card_id: str) -> Dict:
        """Create feedback section with dual 👍/👎 buttons."""
        # Use a valid placeholder URL if no feedback webhook is configured
        # Invalid URLs (like just "?params") break the entire card rendering
        base_url = getattr(_settings, 'feedback_webhook_url', '') or "https://feedback.example.com"
        widgets = []

        # Content feedback
        content_prompt = random.choice(CONTENT_FEEDBACK_PROMPTS)
        widgets.append({"textParagraph": {"text": f"<i>{content_prompt}</i>"}})

        pos_label = random.choice(POSITIVE_LABELS)
        neg_label = random.choice(NEGATIVE_LABELS)

        widgets.append({
            "buttonList": {
                "buttons": [
                    {
                        "text": pos_label,
                        "onClick": {"openLink": {"url": f"{base_url}?card_id={card_id}&feedback=positive&feedback_type=content"}}
                    },
                    {
                        "text": neg_label,
                        "onClick": {"openLink": {"url": f"{base_url}?card_id={card_id}&feedback=negative&feedback_type=content"}}
                    }
                ]
            }
        })

        # Form feedback
        form_prompt = random.choice(FORM_FEEDBACK_PROMPTS)
        widgets.append({"textParagraph": {"text": f"<i>{form_prompt}</i>"}})

        pos_label2 = random.choice(POSITIVE_LABELS)
        neg_label2 = random.choice(NEGATIVE_LABELS)

        widgets.append({
            "buttonList": {
                "buttons": [
                    {
                        "text": pos_label2,
                        "onClick": {"openLink": {"url": f"{base_url}?card_id={card_id}&feedback=positive&feedback_type=form"}}
                    },
                    {
                        "text": neg_label2,
                        "onClick": {"openLink": {"url": f"{base_url}?card_id={card_id}&feedback=negative&feedback_type=form"}}
                    }
                ]
            }
        })

        return {"widgets": widgets}

    # =========================================================================
    # MAIN BUILD METHOD
    # =========================================================================

    def build(
        self,
        description: str,
        title: Optional[str] = None,
        subtitle: Optional[str] = None,
        buttons: Optional[List[Dict]] = None,
        image_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Build a card from DSL description.

        Args:
            description: Card description with optional DSL notation
                Structure DSL: §[δ×3, Ƀ[ᵬ×2]] Dashboard
                Content DSL:
                    δ 'Status: Online' success bold
                    ᵬ Refresh https://example.com
            title: Card header title
            subtitle: Card header subtitle
            buttons: Explicit button list (overrides Content DSL buttons)
            image_url: Image URL for image widgets

        Returns:
            Card dict in Google Chat format
        """
        card_id = str(uuid.uuid4())[:8]
        card = None

        # Try DSL-based building first
        structure_dsl = self._extract_structure_dsl(description)
        if structure_dsl:
            logger.info(f"🔣 Found Structure DSL: {structure_dsl}")
            card = self._build_from_dsl(
                structure_dsl=structure_dsl,
                description=description,
                title=title,
                subtitle=subtitle,
                buttons=buttons,
                image_url=image_url,
            )

        # Fallback: Try Content DSL only (no structure)
        if not card:
            content_dsl = self._parse_content_dsl(description)
            if content_dsl and content_dsl.get("texts"):
                logger.info("🎨 Building from Content DSL only")
                sections = []

                # Build text widgets
                for text_info in content_dsl["texts"]:
                    sections.append({
                        "widgets": [{"decoratedText": {"text": text_info["styled"], "wrapText": True}}]
                    })

                # Build buttons
                if content_dsl.get("buttons"):
                    btn_list = []
                    for btn in content_dsl["buttons"]:
                        btn_obj = {"text": btn.get("text", "Button")}
                        if btn.get("url"):
                            btn_obj["onClick"] = {"openLink": {"url": btn["url"]}}
                        btn_list.append(btn_obj)
                    sections.append({"widgets": [{"buttonList": {"buttons": btn_list}}]})

                if sections:
                    card = {"sections": sections}
                    if title:
                        card["header"] = {"title": title}
                        if subtitle:
                            card["header"]["subtitle"] = subtitle

        # Fallback: Simple card from description
        if not card:
            logger.info("📝 Building simple card from description")
            card = {
                "sections": [
                    {"widgets": [{"textParagraph": {"text": description}}]}
                ]
            }
            if title:
                card["header"] = {"title": title}
                if subtitle:
                    card["header"]["subtitle"] = subtitle

        # Add feedback section
        if ENABLE_FEEDBACK_BUTTONS and card and not self._has_feedback(card):
            feedback = self._create_feedback_section(card_id)
            if "sections" in card:
                card["sections"].append(feedback)
            else:
                card["sections"] = [feedback]

        # Add metadata
        card["_card_id"] = card_id
        if structure_dsl:
            card["_dsl_structure"] = structure_dsl

        return card


# =============================================================================
# COMPATIBILITY METHODS
# =============================================================================

    def build_card_from_description(
        self,
        description: str,
        title: Optional[str] = None,
        subtitle: Optional[str] = None,
        image_url: Optional[str] = None,
        text: Optional[str] = None,
        buttons: Optional[List[Dict]] = None,
        fields: Optional[List[Dict]] = None,
        submit_action: Optional[Dict] = None,
        grid: Optional[Dict] = None,
        images: Optional[List[str]] = None,
        image_titles: Optional[List[str]] = None,
        column_count: int = 2,
        sections: Optional[List[Dict]] = None,
        strict_mode: bool = False,
    ) -> Dict[str, Any]:
        """
        Build a card from description - v1 compatible interface.

        This method provides compatibility with the v1 SmartCardBuilder interface.
        All parameters are accepted but DSL in description takes precedence.

        For explicit sections, grids, or forms - use DSL notation:
        - Forms: τ (TextInput), ► (SelectionInput), □ (DateTimePicker)
        - Grids: ℊ[ǵ×4] (Grid with 4 GridItems)
        - Sections: §[δ×3] (Section with 3 DecoratedText)

        Args:
            description: Card description with optional DSL notation
            title: Card header title
            subtitle: Card header subtitle
            image_url: Image URL for image widgets
            text: Explicit text content (merged with description)
            buttons: Button list [{text, url}]
            fields: Form fields (use DSL instead: τ, ►, □)
            submit_action: Form submit (use DSL for forms)
            grid: Grid structure (use DSL instead: ℊ[ǵ×N])
            images: Image URLs for grid (use DSL)
            image_titles: Titles for grid images
            column_count: Grid column count
            sections: Explicit sections (bypass DSL if provided)
            strict_mode: If True, minimal processing

        Returns:
            Card dict in Google Chat format
        """
        # Handle explicit sections passthrough
        if sections:
            logger.info(f"📋 Explicit sections provided: {len(sections)} section(s)")
            card = {"sections": sections}
            if title:
                card["header"] = {"title": title}
                if subtitle:
                    card["header"]["subtitle"] = subtitle
            # Add feedback section
            card_id = str(uuid.uuid4())[:8]
            if ENABLE_FEEDBACK_BUTTONS and not self._has_feedback(card):
                feedback = self._create_feedback_section(card_id)
                card["sections"].append(feedback)
            card["_card_id"] = card_id
            return card

        # Handle grid/images params
        if grid or images:
            logger.info(f"🔲 Grid params provided - building grid card")
            # Build grid section
            grid_items = []
            if images:
                for i, img_url in enumerate(images):
                    item = {
                        "image": {"imageUri": img_url},
                        "title": image_titles[i] if image_titles and i < len(image_titles) else f"Item {i+1}"
                    }
                    grid_items.append(item)
            elif grid and grid.get("items"):
                grid_items = grid["items"]

            if grid_items:
                grid_widget = {
                    "grid": {
                        "columnCount": grid.get("columnCount", column_count) if grid else column_count,
                        "items": grid_items
                    }
                }
                sections_list = [{"widgets": [grid_widget]}]
                if buttons:
                    btn_list = [{"text": b.get("text", "Button"), **({"onClick": {"openLink": {"url": b["url"]}}} if b.get("url") else {})} for b in buttons]
                    sections_list.append({"widgets": [{"buttonList": {"buttons": btn_list}}]})

                card = {"sections": sections_list}
                if title:
                    card["header"] = {"title": title}
                    if subtitle:
                        card["header"]["subtitle"] = subtitle

                card_id = str(uuid.uuid4())[:8]
                if ENABLE_FEEDBACK_BUTTONS:
                    feedback = self._create_feedback_section(card_id)
                    card["sections"].append(feedback)
                card["_card_id"] = card_id
                return card

        # Merge text into description if provided
        if text and text not in description:
            description = f"{description}\n\n{text}"

        # Delegate to main build method
        return self.build(
            description=description,
            title=title,
            subtitle=subtitle,
            buttons=buttons,
            image_url=image_url,
        )

    def initialize(self):
        """Initialize the builder (v1 compatibility)."""
        # V2 initializes lazily, this is a no-op for compatibility
        pass

    def _get_embedder(self):
        """Get embedder (v1 compatibility for ColBERT init)."""
        # V2 doesn't use ColBERT directly - it queries Qdrant via wrapper
        return None


# =============================================================================
# SINGLETON AND CONVENIENCE FUNCTIONS
# =============================================================================

_builder: Optional[SmartCardBuilderV2] = None


def get_smart_card_builder() -> SmartCardBuilderV2:
    """Get the global SmartCardBuilderV2 instance (v1 compatible)."""
    global _builder
    if _builder is None:
        _builder = SmartCardBuilderV2()
    return _builder


def reset_builder():
    """Reset the singleton builder."""
    global _builder
    _builder = None


def build_card(
    description: str,
    title: Optional[str] = None,
    subtitle: Optional[str] = None,
    **kwargs
) -> Dict[str, Any]:
    """Build a card using SmartCardBuilderV2."""
    builder = get_smart_card_builder()
    return builder.build(description=description, title=title, subtitle=subtitle, **kwargs)


# Backwards compatibility alias
SmartCardBuilder = SmartCardBuilderV2
