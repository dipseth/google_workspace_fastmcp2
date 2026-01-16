"""
Enhanced Natural Language Parameter Parser for Google Chat Cards

This module provides comprehensive natural language processing capabilities to extract
structured card parameters from free-form text descriptions, including support for:
- Multiple sections with headers
- Collapsible sections
- DecoratedText widgets with rich formatting
- Grid layouts
- Complex widgets with icons, buttons, switches

Examples:
    - "Create a card with two sections: 'User Info' and 'Stats'"
    - "Build a status dashboard with decoratedText showing account info with person icon"
    - "Make a grid layout with revenue update using dollar icon and bookmark end icon"
"""

import re
from dataclasses import dataclass, field

from typing_extensions import Any, Dict, List, Optional, Tuple, Union

from config.enhanced_logging import setup_logger

logger = setup_logger()


@dataclass
class ExtractedIcon:
    """Represents an icon extracted from natural language."""

    known_icon: Optional[str] = None
    icon_url: Optional[str] = None


@dataclass
class ExtractedButton:
    """Represents a button extracted from natural language."""

    text: str
    action: Optional[str] = None
    style: Optional[str] = None
    color: Optional[str] = None
    url: Optional[str] = None
    function: Optional[str] = None


@dataclass
class ExtractedSwitchControl:
    """Represents a switch control extracted from natural language."""

    name: str
    selected: bool = False
    control_type: str = "SWITCH"


@dataclass
class ExtractedDecoratedText:
    """Represents a decoratedText widget extracted from natural language."""

    icon: Optional[ExtractedIcon] = None
    top_label: Optional[str] = None
    text: Optional[str] = None
    bottom_label: Optional[str] = None
    button: Optional[ExtractedButton] = None
    switch_control: Optional[ExtractedSwitchControl] = None
    end_icon: Optional[ExtractedIcon] = None
    wrap_text: bool = True


@dataclass
class ExtractedSection:
    """Represents a section extracted from natural language."""

    header: Optional[str] = None
    collapsible: bool = False
    uncollapsible_widgets_count: int = 0
    widgets: List[Union[ExtractedDecoratedText, ExtractedButton, Dict[str, Any]]] = (
        field(default_factory=list)
    )


@dataclass
class ExtractedCard:
    """Represents card data extracted from natural language."""

    title: Optional[str] = None
    subtitle: Optional[str] = None
    text: Optional[str] = None
    image_url: Optional[str] = None
    image_alt_text: Optional[str] = None
    buttons: List[ExtractedButton] = field(default_factory=list)
    sections: List[ExtractedSection] = field(default_factory=list)
    style: Optional[str] = None
    color_theme: Optional[str] = None
    layout_type: str = "standard"  # standard, grid, columns


# Enhanced mappings
KNOWN_ICONS = {
    # People & Communication
    "person": "PERSON",
    "user": "PERSON",
    "profile": "PERSON",
    "account": "PERSON",
    "email": "EMAIL",
    "message": "EMAIL",
    "mail": "EMAIL",
    "phone": "PHONE",
    "call": "PHONE",
    # Actions & Status
    "star": "STAR",
    "rating": "STAR",
    "favorite": "STAR",
    "review": "STAR",
    "clock": "CLOCK",
    "time": "CLOCK",
    "schedule": "CLOCK",
    "timer": "CLOCK",
    "check": "CHECK_CIRCLE",
    "complete": "CHECK_CIRCLE",
    "done": "CHECK_CIRCLE",
    "bookmark": "BOOKMARK",
    "save": "BOOKMARK",
    "saved": "BOOKMARK",
    # Business & Finance
    "dollar": "DOLLAR",
    "money": "DOLLAR",
    "revenue": "DOLLAR",
    "price": "DOLLAR",
    "cost": "DOLLAR",
    "membership": "MEMBERSHIP",
    "subscription": "MEMBERSHIP",
    "plan": "MEMBERSHIP",
    "settings": "SETTINGS",
    "config": "SETTINGS",
    "preferences": "SETTINGS",
    # Content & Media
    "description": "DESCRIPTION",
    "info": "DESCRIPTION",
    "details": "DESCRIPTION",
    "attachment": "ATTACHMENT",
    "file": "ATTACHMENT",
    "document": "ATTACHMENT",
    "video": "VIDEO_CAMERA",
    "camera": "VIDEO_CAMERA",
    # Navigation & UI
    "home": "HOME",
    "house": "HOME",
    "search": "SEARCH",
    "find": "SEARCH",
    "menu": "MORE_VERT",
    "options": "MORE_VERT",
    "add": "ADD",
    "plus": "ADD",
    "create": "ADD",
    # Status & Alerts
    "warning": "WARNING",
    "alert": "WARNING",
    "caution": "WARNING",
    "error": "ERROR",
    "problem": "ERROR",
    "issue": "ERROR",
    "info": "INFO",
    "information": "INFO",
}

COLOR_MAPPINGS = {
    "red": {"theme": "error", "button_type": "FILLED", "html_color": "#ea4335"},
    "green": {"theme": "success", "button_type": "FILLED", "html_color": "#34a853"},
    "blue": {"theme": "info", "button_type": "FILLED", "html_color": "#1a73e8"},
    "yellow": {
        "theme": "warning",
        "button_type": "FILLED_TONAL",
        "html_color": "#fbbc04",
    },
    "orange": {
        "theme": "warning",
        "button_type": "FILLED_TONAL",
        "html_color": "#ff6d01",
    },
    "gray": {"theme": "neutral", "button_type": "OUTLINED", "html_color": "#9aa0a6"},
    "grey": {"theme": "neutral", "button_type": "OUTLINED", "html_color": "#9aa0a6"},
}

SEMANTIC_COLOR_MAPPINGS = {
    "warning": "yellow",
    "error": "red",
    "danger": "red",
    "success": "green",
    "info": "blue",
    "information": "blue",
    "neutral": "gray",
    "primary": "blue",
    "secondary": "gray",
}

BUTTON_TYPE_MAPPINGS = {
    "filled": "FILLED",
    "primary": "FILLED",
    "outlined": "OUTLINED",
    "secondary": "OUTLINED",
    "text": "BORDERLESS",
    "ghost": "BORDERLESS",
    "tonal": "FILLED_TONAL",
    "accent": "FILLED_TONAL",
}


class EnhancedNaturalLanguageCardParser:
    """Enhanced parser that extracts complex card parameters from natural language descriptions."""

    def __init__(self):
        self.patterns = self._compile_patterns()

    def _compile_patterns(self) -> Dict[str, re.Pattern]:
        """Compile comprehensive regex patterns for extraction."""
        patterns = {}

        # Basic element patterns
        patterns["title"] = re.compile(
            r'(?:titled?|heading|called|named)\s+["\']([^"\']+)["\']|'
            r"(?:titled?|heading|called|named)\s+([A-Z][^,.\n]+?)(?:\s+with|\s+and|$)",
            re.IGNORECASE,
        )

        patterns["subtitle"] = re.compile(
            r'(?:subtitle|subheading|with subtitle)\s+["\']([^"\']+)["\']|'
            r"(?:subtitle|subheading|with subtitle)\s+([^,.\n]+?)(?:\s+with|\s+and|$)",
            re.IGNORECASE,
        )

        # Section patterns
        patterns["sections"] = re.compile(
            r"(?:sections?|parts?):\s*([^.]+?)(?:\s+(?:with|and)|$)|"
            r"(?:with|create|build)\s+(?:sections?|parts?)\s+([^.]+?)(?:\s+(?:with|and)|$)",
            re.IGNORECASE,
        )

        patterns["section_list"] = re.compile(
            r'["\']([^"\']+)["\']|' r"(\w+(?:\s+\w+)*?)(?:\s+(?:and|,)|$)",
            re.IGNORECASE,
        )

        patterns["collapsible"] = re.compile(
            r"\b(?:collapsible|expandable|foldable)\b", re.IGNORECASE
        )

        # DecoratedText patterns
        patterns["decorated_text"] = re.compile(
            r"(?:decoratedtext|decorated\s+text|rich\s+text|status\s+item)",
            re.IGNORECASE,
        )

        patterns["with_icon"] = re.compile(
            r"(?:with|using|showing)\s+([a-zA-Z]+)\s+icon", re.IGNORECASE
        )

        patterns["top_label"] = re.compile(
            r'top\s+label\s+["\']([^"\']+)["\']|' r'label\s+["\']([^"\']+)["\']',
            re.IGNORECASE,
        )

        patterns["bottom_label"] = re.compile(
            r'bottom\s+label\s+["\']([^"\']+)["\']|' r'subtitle\s+["\']([^"\']+)["\']',
            re.IGNORECASE,
        )

        # Layout patterns
        patterns["grid_layout"] = re.compile(
            r"\b(?:grid|table|layout|columns?|rows?)\b", re.IGNORECASE
        )

        # Rich text formatting patterns
        patterns["bold_text"] = re.compile(
            r'(?:bold|strong)\s+["\']([^"\']+)["\']', re.IGNORECASE
        )

        patterns["colored_text"] = re.compile(
            r'(red|green|blue|yellow|orange|gray|grey)\s+text\s+["\']([^"\']+)["\']',
            re.IGNORECASE,
        )

        # Button patterns with enhanced functionality
        patterns["buttons_list"] = re.compile(
            r"(?:buttons?|actions?):\s*(.+?)(?:\s+(?:with|and|include|plus)|$)",
            re.IGNORECASE | re.DOTALL,
        )

        patterns["button_with_action"] = re.compile(
            r"([A-Za-z\s]+?)\s+(?:button|action)\s+(?:that\s+)?(?:opens?|goes?\s+to|links?\s+to)\s+([^\s,]+)",
            re.IGNORECASE,
        )

        # Switch control patterns
        patterns["switch_control"] = re.compile(
            r'(?:switch|toggle)\s+(?:control\s+)?(?:named\s+)?["\']?([^"\']+)["\']?\s+(?:set\s+to\s+)?(on|off|true|false|enabled|disabled)?',
            re.IGNORECASE,
        )

        # End icon patterns
        patterns["end_icon"] = re.compile(
            r"end\s+icon\s+([a-zA-Z]+)|"
            r"([a-zA-Z]+)\s+(?:end\s+)?icon\s+(?:at\s+)?(?:the\s+)?end",
            re.IGNORECASE,
        )

        return patterns

    def parse(self, description: str) -> ExtractedCard:
        """
        Parse a comprehensive natural language description to extract card parameters.

        Args:
            description: Natural language description of the desired card

        Returns:
            ExtractedCard object with extracted parameters
        """
        logger.info(f"🔍 Parsing enhanced description: {description[:100]}...")

        card = ExtractedCard()

        # Extract basic elements
        card.title = self._extract_title(description)
        card.subtitle = self._extract_subtitle(description)
        card.text = self._extract_text(description)
        card.color_theme, card.style = self._extract_color_style(description)
        card.image_url, card.image_alt_text = self._extract_image(description)

        # Determine layout type
        card.layout_type = self._determine_layout_type(description)

        # Extract sections and complex widgets
        card.sections = self._extract_sections(description)

        # Extract standalone buttons (not in sections)
        if not card.sections:
            card.buttons = self._extract_buttons(description)

        # CRITICAL: Form-card descriptions often omit explicit "sections:" syntax.
        # If we have *no sections* but the user clearly asked for form inputs,
        # synthesize a single section with the extracted input widgets so downstream
        # code doesn't fall back to a generic "buttons only" card.
        if not card.sections:
            inferred_widgets = []

            # Minimal heuristics (we don't have dedicated extract_*_inputs helpers today).
            # Detect common form intents and create the simplest valid widgets.
            text_lower = description.lower()

            wants_text_input = any(
                k in text_lower for k in ["text input", "textinput", "input field", "enter your"]
            )
            wants_dropdown = any(
                k in text_lower for k in ["dropdown", "select", "pick one", "choose"]
            )

            # Try to infer a label for a single text input (handles: labeled "X").
            import re

            label_match = re.search(r"labeled\s+[\"']([^\"']+)[\"']", description, re.IGNORECASE)
            inferred_label = label_match.group(1).strip() if label_match else None

            if wants_text_input:
                inferred_widgets.append(
                    {
                        "textInput": {
                            "label": inferred_label or "Your name",
                            "name": (inferred_label or "your_name").lower().replace(" ", "_"),
                        }
                    }
                )

            # Extremely simple dropdown inference (only when explicit options present).
            options_match = re.search(
                r"options\s+([A-Za-z0-9/,_\- ]+)", description, re.IGNORECASE
            )
            if wants_dropdown and options_match:
                raw = options_match.group(1)
                # Split on common separators
                parts = [p.strip() for p in re.split(r"[/,]", raw) if p.strip()]
                if parts:
                    inferred_widgets.append(
                        {
                            "selectionInput": {
                                "name": "selection",
                                "label": "Select",
                                "type": "DROPDOWN",
                                "items": [
                                    {"text": p, "value": p.lower().replace(" ", "_"), "selected": i == 0}
                                    for i, p in enumerate(parts[:10])
                                ],
                            }
                        }
                    )

            if inferred_widgets:
                section = ExtractedSection(header=None, collapsible=False)
                section.widgets = inferred_widgets
                card.sections = [section]
                logger.info(
                    f"✅ Inferred form section with {len(inferred_widgets)} widget(s) from description"
                )

        # Add theme-based content enhancement
        self._enhance_with_theme(card, description)

        logger.info(
            f"✅ Enhanced extraction: title='{card.title}', sections={len(card.sections)}, layout='{card.layout_type}'"
        )

        return card

    def _determine_layout_type(self, text: str) -> str:
        """Determine the layout type from description."""
        if self.patterns["grid_layout"].search(text):
            return "grid"
        elif "column" in text.lower():
            return "columns"
        return "standard"

    def _extract_sections(self, text: str) -> List[ExtractedSection]:
        """Extract section information from text."""
        sections = []

        # Pattern 1: Numbered list format with quoted sections
        # Example: "1. 'Health Check' section with decoratedText..."
        numbered_pattern = re.compile(
            r"\d+\.\s+['\"]([^'\"]+)['\"]?\s+section\s+(?:with|showing|containing)\s+(.+?)(?=\d+\.|$)",
            re.IGNORECASE | re.DOTALL,
        )

        numbered_matches = numbered_pattern.findall(text)
        if numbered_matches:
            for section_name, section_content in numbered_matches:
                section = ExtractedSection(
                    header=section_name.strip(),
                    collapsible=bool(self.patterns["collapsible"].search(text)),
                )

                # Parse the section content to extract widgets
                section.widgets = self._parse_section_content(
                    section_content, section_name
                )

                if section.collapsible:
                    section.uncollapsible_widgets_count = min(2, len(section.widgets))

                sections.append(section)

            return sections

        # Pattern 2: Dash/bullet list format
        # Example: "- First section 'Completed Tasks' with decoratedText..."
        dash_pattern = re.compile(
            r"[-•]\s+(?:First|Second|Third|Fourth|Fifth)?\s*(?:section\s+)?['\"]([^'\"]+)['\"]?\s+(?:section\s+)?(?:with|showing|containing)\s+(.+?)(?=[-•]|$)",
            re.IGNORECASE | re.DOTALL,
        )

        dash_matches = dash_pattern.findall(text)
        if dash_matches:
            for section_name, section_content in dash_matches:
                section = ExtractedSection(
                    header=section_name.strip(),
                    collapsible=bool(self.patterns["collapsible"].search(text)),
                )

                # Parse the section content to extract widgets
                section.widgets = self._parse_section_content(
                    section_content, section_name
                )

                if section.collapsible:
                    section.uncollapsible_widgets_count = min(2, len(section.widgets))

                sections.append(section)

            return sections

        # Pattern 3: Original pattern for explicit section mentions
        match = self.patterns["sections"].search(text)
        if match:
            section_text = match.group(1) or match.group(2)

            # Parse the full text to understand section structure
            # Split by section names to get content for each
            remaining_text = text

            # First extract section names
            section_names = self._parse_section_names(section_text)

            for i, name in enumerate(section_names):
                section = ExtractedSection(
                    header=name.strip(),
                    collapsible=bool(self.patterns["collapsible"].search(text)),
                )

                # Look for content specific to this section
                # Pattern: 'Section Name' section with/showing X
                section_pattern = re.compile(
                    f"['\"]?{re.escape(name)}['\"]?\\s*(?:section)?[^.]*?(?:with|showing|containing|displays?)\\s+(.+?)(?:(?:['\"]\\w+['\"]\\s+section)|$)",
                    re.IGNORECASE | re.DOTALL,
                )

                section_match = section_pattern.search(remaining_text)
                if section_match:
                    section_content = section_match.group(1)
                    # Extract widgets from this section's content
                    section.widgets = self._parse_section_content(section_content, name)
                else:
                    # Try simpler extraction if no match
                    section.widgets = [{"textParagraph": {"text": name}}]

                if section.collapsible:
                    section.uncollapsible_widgets_count = min(2, len(section.widgets))

                sections.append(section)

        # Pattern 4: If no explicit sections but decoratedText mentioned, extract directly
        elif "decoratedtext" in text.lower() or "decorated text" in text.lower():
            # Extract decoratedText patterns directly
            decorated_pattern = re.compile(
                r"decoratedtext\s+(?:with|showing|displaying)\s+['\"]?([^'\"]+)['\"]?\s+with\s+(\w+)\s+icon",
                re.IGNORECASE,
            )

            matches = decorated_pattern.findall(text)
            if matches:
                widgets = []
                for text_content, icon_name in matches:
                    widget = self._create_simple_decorated_text(
                        text_content.strip(), icon_name
                    )
                    widgets.append(widget)

                section = ExtractedSection(header="Details", widgets=widgets)
                sections.append(section)

        return sections

    def _parse_section_names(self, section_text: str) -> List[str]:
        """Parse section names from text like 'User Info and Stats' or 'User Info, Stats, Settings'."""
        names = []

        # Handle quoted names first
        quoted_matches = self.patterns["section_list"].findall(section_text)
        for match in quoted_matches:
            name = match[0] or match[1]
            if name and name.strip():
                names.append(name.strip())

        # If no quoted names found, split on common separators
        if not names:
            parts = re.split(r",\s*(?:and\s+)?|\s+and\s+", section_text)
            for part in parts:
                part = part.strip().strip("\"'")
                if part:
                    names.append(part)

        return names[:5]  # Limit to 5 sections max

    def _parse_section_content(
        self, content: str, section_name: str
    ) -> List[Dict[str, Any]]:
        """Parse content for a specific section and extract widgets."""
        widgets = []

        # First, try the most specific patterns with all details
        # Pattern for: decoratedText 'text' with topLabel 'label' and [color] [type] icon
        full_decorated_pattern = re.compile(
            r"decoratedtext\s+['\"]([^'\"]+)['\"]?\s+"
            r"with\s+topLabel\s+['\"]([^'\"]+)['\"]?\s*"
            r"(?:and\s+(?:a\s+)?(\w+)\s+(?:\w+\s+)?icon)?",
            re.IGNORECASE,
        )

        match = full_decorated_pattern.search(content)
        if match:
            text_content, top_label, icon_name = match.groups()
            widget = {
                "decoratedText": {
                    "text": text_content.strip(),
                    "topLabel": top_label.strip(),
                }
            }

            # Add icon if specified (Google Chat Cards v2 uses "startIcon")
            if icon_name:
                # Handle color icons (green check -> CHECK_CIRCLE)
                if icon_name.lower() in ["check", "checkmark", "green"]:
                    widget["decoratedText"]["startIcon"] = {"knownIcon": "CHECK_CIRCLE"}
                elif icon_name.lower() in ["clock", "orange", "time"]:
                    widget["decoratedText"]["startIcon"] = {"knownIcon": "CLOCK"}
                elif icon_name.lower() in KNOWN_ICONS:
                    widget["decoratedText"]["startIcon"] = {
                        "knownIcon": KNOWN_ICONS[icon_name.lower()]
                    }

            widgets.append(widget)
            return widgets

        # Pattern for simpler decoratedText without topLabel
        simple_decorated_pattern = re.compile(
            r"decoratedtext\s+(?:showing\s+)?['\"]([^'\"]+)['\"]?\s*"
            r"(?:with\s+(?:a\s+)?(\w+)\s+(?:\w+\s+)?icon)?",
            re.IGNORECASE,
        )

        match = simple_decorated_pattern.search(content)
        if match:
            text_content, icon_name = match.groups()
            widget = self._create_simple_decorated_text(
                text_content.strip(), icon_name if icon_name else None
            )
            widgets.append(widget)
            return widgets

        # Check for button patterns
        if "button" in content.lower():
            # Pattern for: button 'text' linking to URL
            button_pattern = re.compile(
                r"button\s+['\"]([^'\"]+)['\"]?\s+(?:linking\s+to|opens?|goes?\s+to)\s+([^\s]+)",
                re.IGNORECASE,
            )

            match = button_pattern.search(content)
            if match:
                button_text, button_url = match.groups()
                widget = {
                    "buttonList": {
                        "buttons": [
                            {
                                "text": button_text.strip(),
                                "onClick": {"openLink": {"url": button_url.strip()}},
                            }
                        ]
                    }
                }
                widgets.append(widget)
                return widgets

            # Fallback to general button extraction
            buttons = self._extract_buttons(content)
            for button in buttons:
                widgets.append(self._button_to_widget(button))
                return widgets

        # If content has quotes, extract quoted text
        if "'" in content or '"' in content:
            text_pattern = re.compile(r"['\"]([^'\"]+)['\"]")
            text_matches = text_pattern.findall(content)

            if text_matches:
                # Check if there's a topLabel mention
                if "toplabel" in content.lower() or "top label" in content.lower():
                    # Try to extract topLabel value
                    label_pattern = re.compile(
                        r"(?:topLabel|top\s+label)\s+['\"]([^'\"]+)['\"]", re.IGNORECASE
                    )
                    label_match = label_pattern.search(content)

                    if label_match and text_matches:
                        widget = {
                            "decoratedText": {
                                "text": text_matches[0].strip(),
                                "topLabel": label_match.group(1).strip(),
                            }
                        }
                        widgets.append(widget)
                        return widgets

                # Otherwise just use the first quoted text
                for text_content in text_matches[:1]:  # Take first quote only
                    widget = {"textParagraph": {"text": text_content}}
                    widgets.append(widget)
                    return widgets

        # If no widgets extracted, add a default text widget
        if not widgets:
            widgets.append({"textParagraph": {"text": f"{section_name} section"}})

        return widgets

    def _create_simple_decorated_text(
        self, text_content: str, icon_name: str = None
    ) -> Dict[str, Any]:
        """Create a simple decoratedText widget with extracted content."""
        widget = {"decoratedText": {"text": text_content}}

        # Google Chat Cards v2 uses "startIcon" for decoratedText
        if icon_name and icon_name.lower() in KNOWN_ICONS:
            widget["decoratedText"]["startIcon"] = {
                "knownIcon": KNOWN_ICONS[icon_name.lower()]
            }

        return widget

    def _create_decorated_text_widget(
        self,
        icon_name: str = None,
        top_label: str = None,
        text_content: str = None,
        bottom_label: str = None,
        button_text: str = None,
        button_url: str = None,
        button_function: str = None,
        switch_name: str = None,
        switch_selected: bool = False,
        end_icon_name: str = None,
    ) -> Dict[str, Any]:
        """Create a decoratedText widget dictionary."""
        widget = {"decoratedText": {"wrapText": True}}

        decorated_text = widget["decoratedText"]

        # Add icon (Google Chat Cards v2 uses "startIcon" for decoratedText)
        if icon_name and icon_name.lower() in KNOWN_ICONS:
            decorated_text["startIcon"] = {"knownIcon": KNOWN_ICONS[icon_name.lower()]}

        # Add labels and text
        if top_label:
            decorated_text["topLabel"] = top_label

        if text_content:
            decorated_text["text"] = text_content

        if bottom_label:
            decorated_text["bottomLabel"] = bottom_label

        # Add button
        if button_text:
            button = {"text": button_text}

            if button_url:
                button["onClick"] = {"openLink": {"url": button_url}}
            elif button_function:
                button["onClick"] = {"action": {"function": button_function}}

            decorated_text["button"] = button

        # Add switch control
        if switch_name:
            decorated_text["switchControl"] = {
                "name": switch_name,
                "selected": switch_selected,
                "controlType": "SWITCH",
            }

        # Add end icon
        if end_icon_name and end_icon_name.lower() in KNOWN_ICONS:
            decorated_text["endIcon"] = {
                "knownIcon": KNOWN_ICONS[end_icon_name.lower()]
            }

        return widget

    def _extract_title(self, text: str) -> Optional[str]:
        """Extract title from text."""
        match = self.patterns["title"].search(text)
        if match:
            title = match.group(1) or match.group(2)
            return title.strip() if title else None
        return None

    def _extract_subtitle(self, text: str) -> Optional[str]:
        """Extract subtitle from text."""
        match = self.patterns["subtitle"].search(text)
        if match:
            subtitle = match.group(1) or match.group(2)
            return subtitle.strip() if subtitle else None
        return None

    def _extract_text(self, text: str) -> Optional[str]:
        """Extract main text/message from text."""
        # Look for explicit text patterns
        patterns_to_try = [
            r'(?:saying|with text|message|content)\s+["\']([^"\']+)["\']',
            r"(?:saying|with text|message|content)\s+([^,.\n]+?)(?:\s+(?:with|and)|$)",
        ]

        for pattern in patterns_to_try:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                content = match.group(1)
                return content.strip() if content else None

        return None

    def _extract_buttons(self, text: str) -> List[ExtractedButton]:
        """Extract button information from text."""
        buttons = []

        # Try different button patterns
        button_text = None

        # Pattern 1: "buttons: X, Y, Z"
        match = self.patterns["buttons_list"].search(text)
        if match:
            button_text = match.group(1)

        if button_text:
            buttons = self._parse_button_list(button_text)

        # Also look for button with action patterns
        action_matches = self.patterns["button_with_action"].findall(text)
        for name, url in action_matches:
            buttons.append(ExtractedButton(text=name.strip(), url=url, action=url))

        return buttons

    def _parse_button_list(self, button_text: str) -> List[ExtractedButton]:
        """Parse a list of buttons from text."""
        buttons = []

        # Handle parentheses format
        button_text = button_text.strip("()")

        # Split on common separators
        button_parts = re.split(r",\s*(?:and\s+)?|;\s*|\s+and\s+", button_text)

        for part in button_parts:
            part = part.strip()
            if not part:
                continue

            # Extract button name and style
            match = re.match(
                r"([A-Za-z\s]+?)(?:\s+in\s+(red|green|blue|yellow|orange|gray|grey|primary|secondary|outlined|filled|tonal))?",
                part,
                re.IGNORECASE,
            )
            if match:
                name = match.group(1).strip()
                style = match.group(2).lower() if match.group(2) else None

                button_type = None
                color = None

                if style:
                    if style in COLOR_MAPPINGS:
                        color = style
                        button_type = COLOR_MAPPINGS[style]["button_type"]
                    elif style in BUTTON_TYPE_MAPPINGS:
                        button_type = BUTTON_TYPE_MAPPINGS[style]
                    elif style in SEMANTIC_COLOR_MAPPINGS:
                        color = SEMANTIC_COLOR_MAPPINGS[style]
                        button_type = COLOR_MAPPINGS.get(color, {}).get(
                            "button_type", "FILLED"
                        )

                action = f"#{name.lower().replace(' ', '_')}"

                buttons.append(
                    ExtractedButton(
                        text=name, action=action, style=button_type, color=color
                    )
                )
            else:
                buttons.append(
                    ExtractedButton(
                        text=part, action=f"#{part.lower().replace(' ', '_')}"
                    )
                )

        return buttons

    def _extract_color_style(self, text: str) -> Tuple[Optional[str], Optional[str]]:
        """Extract color theme and style from text."""
        color_theme = None
        style = None

        # Check for semantic styles first
        for semantic, color in SEMANTIC_COLOR_MAPPINGS.items():
            if semantic in text.lower():
                color_theme = color
                style = semantic
                break

        # Check for direct colors
        if not color_theme:
            for color in COLOR_MAPPINGS.keys():
                if color in text.lower():
                    color_theme = color
                    style = color
                    break

        return color_theme, style

    def _extract_image(self, text: str) -> Tuple[Optional[str], Optional[str]]:
        """Extract image URL and alt text from text."""
        patterns = [
            # Pattern 1: quoted URLs after image/picture/etc keywords
            r'(?:image|picture|chart|graph|photo)\s+(?:from\s+)?["\']([^"\']+)["\']',
            # Pattern 2: https:// URLs after image/picture/etc keywords (capture full URL path)
            r'(?:image|picture|chart|graph|photo)\s+(?:from\s+)?(https?://[^\s,]+)',
            # Pattern 3: file extensions
            r'(?:image|picture|chart|graph|photo)\s+(?:from\s+)?(\S+\.(?:png|jpg|jpeg|gif|svg|webp))',
            # Pattern 4: include keyword with file extension
            r"include\s+(?:the\s+)?([^.\s]+\.(?:png|jpg|jpeg|gif|svg|webp))",
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                url = match.group(1)
                alt_text = "image"

                # Generate contextual alt text
                context_words = ["chart", "graph", "status", "report", "diagram"]
                for word in context_words:
                    if word in text.lower():
                        alt_text = f"{word} image"
                        break

                return url, alt_text

        return None, None

    def _enhance_with_theme(self, card: ExtractedCard, description: str):
        """Enhance card content based on detected theme."""
        if not card.color_theme:
            return

        # Add theme-appropriate content if missing
        if not card.text and not card.sections:
            theme_messages = {
                "red": "❌ Alert",
                "yellow": "⚠️ Warning",
                "green": "✅ Success",
                "blue": "ℹ️ Information",
            }

            if card.color_theme in theme_messages:
                card.text = theme_messages[card.color_theme]

    def _button_to_widget(self, button: ExtractedButton) -> Dict[str, Any]:
        """Convert ExtractedButton to widget format."""
        widget = {"buttonList": {"buttons": [{"text": button.text}]}}

        button_dict = widget["buttonList"]["buttons"][0]

        if button.url:
            button_dict["onClick"] = {"openLink": {"url": button.url}}
        elif button.function:
            button_dict["onClick"] = {"action": {"function": button.function}}
        elif button.action:
            button_dict["onClick"] = {"openLink": {"url": button.action}}

        if button.style:
            button_dict["type"] = button.style

        return widget


def build_enhanced_card_params(extracted: ExtractedCard) -> Dict[str, Any]:
    """
    Convert ExtractedCard to enhanced card_params dictionary format.

    Args:
        extracted: ExtractedCard object with extracted parameters

    Returns:
        Dictionary in card_params format for send_dynamic_card
    """
    params = {}

    # Basic card properties
    if extracted.title:
        params["title"] = extracted.title

    if extracted.subtitle:
        params["subtitle"] = extracted.subtitle

    if extracted.text:
        params["text"] = extracted.text

    # Image properties
    if extracted.image_url:
        params["image_url"] = extracted.image_url
        if extracted.image_alt_text:
            params["image_alt_text"] = extracted.image_alt_text

    # Enhanced sections support
    if extracted.sections:
        sections_list = []
        for section in extracted.sections:
            section_dict = {"widgets": []}

            if section.header:
                section_dict["header"] = section.header

            if section.collapsible:
                section_dict["collapsible"] = True
                section_dict["uncollapsibleWidgetsCount"] = (
                    section.uncollapsible_widgets_count
                )

            # Add widgets to section
            for widget in section.widgets:
                if isinstance(widget, dict):
                    section_dict["widgets"].append(widget)
                else:
                    # Convert other widget types as needed
                    section_dict["widgets"].append(widget)

            sections_list.append(section_dict)

        params["sections"] = sections_list

    # Button properties (for non-section cards)
    elif extracted.buttons:
        button_list = []
        for btn in extracted.buttons:
            button_dict = {"text": btn.text}

            if btn.url:
                button_dict["onclick_action"] = btn.url
            elif btn.action:
                button_dict["onclick_action"] = btn.action

            if btn.style:
                button_dict["type"] = btn.style

            button_list.append(button_dict)

        params["buttons"] = button_list

    # Style properties
    if extracted.color_theme:
        params["theme"] = extracted.color_theme

    # Layout properties
    if extracted.layout_type != "standard":
        params["layout_type"] = extracted.layout_type

    return params


def parse_enhanced_natural_language_description(description: str) -> Dict[str, Any]:
    """
    Main entry point for parsing enhanced natural language descriptions into card parameters.

    Args:
        description: Natural language description of the card

    Returns:
        Dictionary of enhanced card parameters
    """
    parser = EnhancedNaturalLanguageCardParser()
    extracted = parser.parse(description)
    return build_enhanced_card_params(extracted)
