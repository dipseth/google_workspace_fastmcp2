"""
Universal Styling Filters for Jinja2/Nunjucks Templates

Provides semantic color and formatting filters that work across all modules
and output targets (GChat, HTML email, Markdown, etc.).

Jinja2 and Nunjucks share the same syntax, so these filters work in both:
- Python backend: Jinja2
- JavaScript frontend: Nunjucks

Usage in templates:
    {{ "Success!" | color('success') }}
    {{ sale_price | price(original_price) }}
    {{ "NEW" | badge('info') }}
    {{ item.status | status_icon }}

Output Targets:
    - gchat: Google Chat HTML subset (<font color>, <b>, <i>, <s>)
    - html: Full HTML with inline styles
    - markdown: Markdown formatting (no color support)

The default target is 'gchat' for Google Chat card compatibility.
"""

from typing import Optional, Union, List, Iterator, Dict, Any
from enum import Enum
from itertools import cycle


class OutputTarget(Enum):
    """Supported output formats for styling filters."""
    GCHAT = "gchat"      # Google Chat HTML subset
    HTML = "html"        # Full HTML with CSS
    MARKDOWN = "markdown"  # Markdown (limited styling)


# =============================================================================
# SEMANTIC COLOR PALETTE
# =============================================================================
# Google's Material Design colors aligned with semantic meaning.
# These work well in both light and dark themes.

SEMANTIC_COLORS = {
    # Status colors
    "success": "#34a853",   # Google Green
    "error": "#ea4335",     # Google Red
    "warning": "#fbbc05",   # Google Yellow
    "info": "#4285f4",      # Google Blue

    # Neutral colors
    "muted": "#9aa0a6",     # Gray 500
    "subtle": "#bdc1c6",    # Gray 400
    "dark": "#3c4043",      # Gray 800

    # Accent colors
    "primary": "#1a73e8",   # Bright Blue
    "secondary": "#5f6368", # Gray 700
    "accent": "#8430ce",    # Purple

    # Semantic aliases (common use cases)
    "positive": "#34a853",  # = success
    "negative": "#ea4335",  # = error
    "neutral": "#5f6368",   # = secondary
    "highlight": "#fbbc05", # = warning

    # Price-specific
    "sale": "#34a853",      # Green for sale prices
    "original": "#9aa0a6",  # Muted for original prices

    # Status-specific
    "active": "#34a853",
    "inactive": "#9aa0a6",
    "pending": "#fbbc05",
    "cancelled": "#ea4335",

    # Common color name aliases (for NL descriptions like "green header")
    "green": "#34a853",     # = success/Google Green
    "red": "#ea4335",       # = error/Google Red
    "blue": "#4285f4",      # = info/Google Blue
    "yellow": "#fbbc05",    # = warning/Google Yellow
    "orange": "#ff6d01",    # Google Orange
    "purple": "#8430ce",    # = accent
    "gray": "#5f6368",      # = secondary
    "grey": "#5f6368",      # = secondary (British spelling)
}

# Background colors for badges (lighter versions)
BADGE_BACKGROUNDS = {
    "success": "#e6f4ea",
    "error": "#fce8e6",
    "warning": "#fef7e0",
    "info": "#e8f0fe",
    "muted": "#f1f3f4",
    "accent": "#f3e8fd",
}

# Status to icon mapping
STATUS_ICONS = {
    "success": "✓",
    "error": "✗",
    "warning": "⚠",
    "info": "ℹ",
    "pending": "◐",
    "active": "●",
    "inactive": "○",
    "loading": "◌",
}


# =============================================================================
# CORE STYLING FILTERS
# =============================================================================

def color_filter(
    text: str,
    color_name: str,
    target: str = "gchat",
    bold: bool = False,
) -> str:
    """
    Apply semantic color to text.

    Args:
        text: Text to colorize
        color_name: Semantic name ('success', 'error') or hex ('#ff0000')
        target: Output target ('gchat', 'html', 'markdown')
        bold: Also make text bold

    Returns:
        Formatted text string

    Usage:
        {{ "Done!" | color('success') }}
        {{ error_msg | color('error', bold=true) }}
        {{ custom | color('#ff6600') }}
    """
    # Resolve semantic color or use raw hex
    hex_color = SEMANTIC_COLORS.get(color_name, color_name)

    # Ensure hex format
    if not hex_color.startswith('#'):
        hex_color = f"#{hex_color}"

    if target == "markdown":
        # Markdown doesn't support color, use bold for emphasis
        return f"**{text}**" if bold or color_name in ('success', 'error') else text

    elif target == "html":
        # Full HTML with inline styles
        style = f"color:{hex_color}"
        if bold:
            style += ";font-weight:bold"
        return f'<span style="{style}">{text}</span>'

    else:  # gchat (default)
        # Google Chat supports <font color=""> and <b>
        result = f'<font color="{hex_color}">{text}</font>'
        if bold:
            result = f'<b>{result}</b>'
        return result


def price_filter(
    current: Union[float, int, str],
    original: Optional[Union[float, int, str]] = None,
    currency: str = "$",
    target: str = "gchat",
) -> str:
    """
    Format a price with optional strikethrough for original price.

    Args:
        current: Current/sale price
        original: Original price (if on sale)
        currency: Currency symbol
        target: Output target

    Returns:
        Formatted price string

    Usage:
        {{ item.price | price }}
        {{ sale_price | price(original_price) }}
        {{ amount | price(currency='€') }}
    """
    # Convert to float
    try:
        current_val = float(str(current).replace(',', '').replace(currency, ''))
    except (ValueError, TypeError):
        return str(current)

    current_str = f"{currency}{current_val:,.2f}"

    if original is not None:
        try:
            original_val = float(str(original).replace(',', '').replace(currency, ''))
        except (ValueError, TypeError):
            original_val = None

        if original_val and original_val > current_val:
            original_str = f"{currency}{original_val:,.2f}"

            if target == "markdown":
                return f"**{current_str}** ~~{original_str}~~"
            elif target == "html":
                return (
                    f'<span style="color:{SEMANTIC_COLORS["sale"]};font-weight:bold">'
                    f'{current_str}</span> '
                    f'<span style="color:{SEMANTIC_COLORS["original"]};text-decoration:line-through">'
                    f'{original_str}</span>'
                )
            else:  # gchat
                return (
                    f'<font color="{SEMANTIC_COLORS["sale"]}"><b>{current_str}</b></font> '
                    f'<s>{original_str}</s>'
                )

    return current_str


def badge_filter(
    text: str,
    style: str = "info",
    target: str = "gchat",
) -> str:
    """
    Create a badge/chip styled element.

    Args:
        text: Badge text
        style: Semantic style ('success', 'error', 'warning', 'info')
        target: Output target

    Returns:
        Formatted badge string

    Usage:
        {{ "NEW" | badge }}
        {{ "SOLD" | badge('error') }}
        {{ tag | badge('success') }}
    """
    fg = SEMANTIC_COLORS.get(style, SEMANTIC_COLORS["info"])
    bg = BADGE_BACKGROUNDS.get(style, BADGE_BACKGROUNDS["info"])

    if target == "markdown":
        return f"[{text}]"
    elif target == "html":
        return (
            f'<span style="background:{bg};color:{fg};padding:2px 8px;'
            f'border-radius:4px;font-size:12px;font-weight:500">{text}</span>'
        )
    else:  # gchat - limited styling
        # GChat doesn't support background colors, use bold + color
        return f'<font color="{fg}"><b>[{text}]</b></font>'


def status_icon_filter(
    status: str,
    with_text: bool = False,
    target: str = "gchat",
) -> str:
    """
    Get an icon for a status value.

    Args:
        status: Status name ('success', 'error', 'pending', etc.)
        with_text: Include status text after icon
        target: Output target

    Returns:
        Icon string, optionally with colored text

    Usage:
        {{ item.status | status_icon }}
        {{ "success" | status_icon(with_text=true) }}
    """
    status_lower = status.lower()
    icon = STATUS_ICONS.get(status_lower, "•")
    color = SEMANTIC_COLORS.get(status_lower, SEMANTIC_COLORS["muted"])

    if target == "markdown":
        result = icon
        if with_text:
            result = f"{icon} {status}"
        return result

    elif target == "html":
        result = f'<span style="color:{color}">{icon}</span>'
        if with_text:
            result = f'{result} <span style="color:{color}">{status}</span>'
        return result

    else:  # gchat
        result = f'<font color="{color}">{icon}</font>'
        if with_text:
            result = f'{result} <font color="{color}">{status}</font>'
        return result


def bold_filter(text: str, target: str = "gchat") -> str:
    """
    Make text bold.

    Usage:
        {{ title | bold }}
    """
    if target == "markdown":
        return f"**{text}**"
    else:  # html, gchat
        return f"<b>{text}</b>"


def italic_filter(text: str, target: str = "gchat") -> str:
    """
    Make text italic.

    Usage:
        {{ subtitle | italic }}
    """
    if target == "markdown":
        return f"*{text}*"
    else:  # html, gchat
        return f"<i>{text}</i>"


def strike_filter(text: str, target: str = "gchat") -> str:
    """
    Strikethrough text.

    Usage:
        {{ old_price | strike }}
    """
    if target == "markdown":
        return f"~~{text}~~"
    else:  # html, gchat
        return f"<s>{text}</s>"


def link_filter(
    text: str,
    url: str,
    target: str = "gchat",
) -> str:
    """
    Create a hyperlink.

    Usage:
        {{ "Click here" | link(item.url) }}
    """
    if target == "markdown":
        return f"[{text}]({url})"
    else:  # html, gchat
        return f'<a href="{url}">{text}</a>'


# =============================================================================
# COMPOSITE FILTERS (Common Patterns)
# =============================================================================

def success_text_filter(text: str, target: str = "gchat") -> str:
    """Shorthand for green success text."""
    return color_filter(text, "success", target)


def error_text_filter(text: str, target: str = "gchat") -> str:
    """Shorthand for red error text."""
    return color_filter(text, "error", target)


def warning_text_filter(text: str, target: str = "gchat") -> str:
    """Shorthand for yellow warning text."""
    return color_filter(text, "warning", target)


def muted_text_filter(text: str, target: str = "gchat") -> str:
    """Shorthand for gray muted text."""
    return color_filter(text, "muted", target)


def highlight_filter(text: str, target: str = "gchat") -> str:
    """Highlight important text (bold + primary color)."""
    return color_filter(text, "primary", target, bold=True)


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def get_color(name: str) -> str:
    """
    Get hex color value by semantic name.

    Useful for programmatic access outside templates.

    Args:
        name: Semantic color name or hex value

    Returns:
        Hex color string
    """
    return SEMANTIC_COLORS.get(name, name)


def get_all_colors() -> dict:
    """Get all available semantic colors."""
    return SEMANTIC_COLORS.copy()


# =============================================================================
# FILTER REGISTRY
# =============================================================================
# All filters exported for Jinja2 registration

STYLING_FILTERS = {
    # Core filters
    "color": color_filter,
    "price": price_filter,
    "badge": badge_filter,
    "status_icon": status_icon_filter,

    # Text formatting
    "bold": bold_filter,
    "italic": italic_filter,
    "strike": strike_filter,
    "link": link_filter,

    # Shortcuts
    "success_text": success_text_filter,
    "error_text": error_text_filter,
    "warning_text": warning_text_filter,
    "muted_text": muted_text_filter,
    "highlight": highlight_filter,

    # Color cycling (added after class definitions below)
    # "alternating_colors": alternating_color_filter,  # Added dynamically
}

# =============================================================================
# COLOR SCHEMES (Alternating/Cycling)
# =============================================================================

# Pre-defined color schemes for alternating components
COLOR_SCHEMES = {
    "default": ["#4285f4", "#34a853", "#fbbc05", "#ea4335"],  # Google colors
    "blue_green": ["#1a73e8", "#34a853"],
    "warm": ["#ea4335", "#fbbc05", "#ff6d01"],
    "cool": ["#4285f4", "#8430ce", "#00acc1"],
    "neutral": ["#5f6368", "#9aa0a6", "#bdc1c6"],
    "vibrant": ["#ea4335", "#4285f4", "#34a853", "#fbbc05", "#8430ce"],
    "pastel": ["#e8f0fe", "#e6f4ea", "#fef7e0", "#fce8e6"],
    "dark": ["#202124", "#3c4043", "#5f6368"],
}


class ColorCycler:
    """
    Cycles through colors for alternating component styling.

    Usage:
        cycler = ColorCycler(["#ff0000", "#0000ff"])
        color1 = cycler.next()  # #ff0000
        color2 = cycler.next()  # #0000ff
        color3 = cycler.next()  # #ff0000 (wraps around)

        # Or use a preset scheme
        cycler = ColorCycler.from_scheme("google")
    """

    def __init__(self, colors: List[str]):
        """
        Initialize with a list of colors.

        Args:
            colors: List of hex colors to cycle through
        """
        if not colors:
            colors = COLOR_SCHEMES["default"]
        self._colors = colors
        self._cycle = cycle(colors)
        self._index = 0

    @classmethod
    def from_scheme(cls, scheme_name: str) -> "ColorCycler":
        """Create a cycler from a named color scheme."""
        colors = COLOR_SCHEMES.get(scheme_name, COLOR_SCHEMES["default"])
        return cls(colors)

    @classmethod
    def from_base_colors(cls, base_colors: List[str], total_needed: int = 10) -> "ColorCycler":
        """
        Create a cycler that alternates base colors to fill total_needed.

        If you have 2 base colors and need 10, it will alternate:
        [color1, color2, color1, color2, ...]

        Args:
            base_colors: Base colors to alternate (e.g., ["red", "blue"])
            total_needed: How many colors total are needed

        Returns:
            ColorCycler ready to provide alternating colors
        """
        # Resolve semantic names to hex
        resolved = [SEMANTIC_COLORS.get(c, c) for c in base_colors]
        return cls(resolved)

    def next(self) -> str:
        """Get the next color in the cycle."""
        self._index += 1
        return next(self._cycle)

    def peek(self) -> str:
        """See the current color without advancing."""
        return self._colors[(self._index) % len(self._colors)]

    def reset(self) -> None:
        """Reset to the beginning of the cycle."""
        self._cycle = cycle(self._colors)
        self._index = 0

    def get_all(self, count: int) -> List[str]:
        """Get a list of `count` colors from the cycle."""
        return [self.next() for _ in range(count)]

    @property
    def colors(self) -> List[str]:
        """Get the base color list."""
        return self._colors.copy()


class ComponentStyler:
    """
    Applies consistent styling to card components during traversal.

    Provides:
    - Alternating colors for repeated components (sections, items, etc.)
    - Consistent styling based on component type
    - Integration with Jinja2 filters

    Usage:
        styler = ComponentStyler(base_colors=["success", "info"])

        # During component traversal
        for section in sections:
            color = styler.get_color_for("section")
            styled_title = styler.style_text(section.title, color=color, bold=True)

        # Or auto-style components
        styled = styler.auto_style(component_type="grid_item", text="Item 1")
    """

    def __init__(
        self,
        base_colors: Optional[List[str]] = None,
        scheme: Optional[str] = None,
        target: str = "gchat",
    ):
        """
        Initialize the component styler.

        Args:
            base_colors: Custom colors to cycle (semantic names or hex)
            scheme: Named color scheme ('default', 'blue_green', 'warm', etc.)
            target: Output target ('gchat', 'html', 'markdown')
        """
        self.target = target

        # Initialize color cyclers for different component types
        if base_colors:
            self._default_colors = [SEMANTIC_COLORS.get(c, c) for c in base_colors]
        elif scheme:
            self._default_colors = COLOR_SCHEMES.get(scheme, COLOR_SCHEMES["default"])
        else:
            self._default_colors = COLOR_SCHEMES["default"]

        # Separate cyclers for different component types
        self._cyclers: Dict[str, ColorCycler] = {}

    def _get_cycler(self, component_type: str) -> ColorCycler:
        """Get or create a color cycler for a component type."""
        if component_type not in self._cyclers:
            self._cyclers[component_type] = ColorCycler(self._default_colors)
        return self._cyclers[component_type]

    def get_color_for(self, component_type: str) -> str:
        """
        Get the next alternating color for a component type.

        Different component types have independent cycles:
        - Sections alternate independently from grid items
        - This prevents visual collision when nesting

        Args:
            component_type: Type of component ('section', 'grid_item', 'button', etc.)

        Returns:
            Hex color string
        """
        return self._get_cycler(component_type).next()

    def peek_color_for(self, component_type: str) -> str:
        """See the current color without advancing the cycle."""
        return self._get_cycler(component_type).peek()

    def reset(self, component_type: Optional[str] = None) -> None:
        """
        Reset color cycles.

        Args:
            component_type: Reset specific type, or None to reset all
        """
        if component_type:
            if component_type in self._cyclers:
                self._cyclers[component_type].reset()
        else:
            for cycler in self._cyclers.values():
                cycler.reset()

    def style_text(
        self,
        text: str,
        color: Optional[str] = None,
        bold: bool = False,
        component_type: Optional[str] = None,
    ) -> str:
        """
        Style text with color and formatting.

        Args:
            text: Text to style
            color: Explicit color (semantic name or hex), or None for auto
            bold: Whether to make text bold
            component_type: If no color given, get next from this type's cycle

        Returns:
            Styled text string
        """
        if color is None and component_type:
            color = self.get_color_for(component_type)
        elif color is None:
            color = "primary"

        return color_filter(text, color, target=self.target, bold=bold)

    def auto_style(
        self,
        component_type: str,
        text: str,
        bold: bool = False,
    ) -> str:
        """
        Automatically style text based on component type with alternating colors.

        Args:
            component_type: Type of component
            text: Text to style
            bold: Whether to bold

        Returns:
            Styled text
        """
        color = self.get_color_for(component_type)
        return color_filter(text, color, target=self.target, bold=bold)

    def style_component(
        self,
        component: Dict[str, Any],
        text_field: str = "text",
        color_field: str = "color",
    ) -> Dict[str, Any]:
        """
        Apply styling to a component dict in-place.

        Useful for traversing component trees and applying alternating colors.

        Args:
            component: Component dict with text fields
            text_field: Field name containing text to style
            color_field: Field name to store the color

        Returns:
            The component dict with styling applied
        """
        comp_type = component.get("type", "default")
        color = self.get_color_for(comp_type)

        if text_field in component and component[text_field]:
            component[text_field] = self.style_text(
                component[text_field],
                color=color,
            )

        component[color_field] = color
        return component

    def traverse_and_style(
        self,
        components: List[Dict[str, Any]],
        type_field: str = "type",
        text_field: str = "text",
        children_field: str = "children",
    ) -> List[Dict[str, Any]]:
        """
        Recursively traverse and style a component tree.

        Args:
            components: List of component dicts
            type_field: Field containing component type
            text_field: Field containing text to style
            children_field: Field containing child components

        Returns:
            Components with alternating colors applied
        """
        for comp in components:
            comp_type = comp.get(type_field, "default")
            color = self.get_color_for(comp_type)

            # Style the text if present
            if text_field in comp and comp[text_field]:
                comp[text_field] = color_filter(
                    comp[text_field], color, target=self.target
                )
            comp["_applied_color"] = color

            # Recurse into children
            if children_field in comp and comp[children_field]:
                self.traverse_and_style(
                    comp[children_field],
                    type_field=type_field,
                    text_field=text_field,
                    children_field=children_field,
                )

        return components


# =============================================================================
# JINJA2 INTEGRATION HELPERS
# =============================================================================

def create_styler_for_template(
    base_colors: Optional[List[str]] = None,
    scheme: Optional[str] = None,
    target: str = "gchat",
) -> ComponentStyler:
    """
    Create a ComponentStyler for use in Jinja2 templates.

    Can be passed as a template variable:
        env.globals["styler"] = create_styler_for_template(scheme="blue_green")

    Template usage:
        {{ styler.auto_style("section", "Section Title") }}
        {{ styler.get_color_for("grid_item") }}
    """
    return ComponentStyler(base_colors=base_colors, scheme=scheme, target=target)


def alternating_color_filter(
    items: List[Any],
    colors: Optional[List[str]] = None,
    scheme: str = "default",
) -> Iterator[tuple]:
    """
    Jinja2 filter to iterate items with alternating colors.

    Usage in templates:
        {% for item, color in items | alternating_colors %}
            <font color="{{ color }}">{{ item.name }}</font>
        {% endfor %}

        {% for item, color in items | alternating_colors(["red", "blue"]) %}
            ...
        {% endfor %}
    """
    if colors:
        resolved = [SEMANTIC_COLORS.get(c, c) for c in colors]
    else:
        resolved = COLOR_SCHEMES.get(scheme, COLOR_SCHEMES["default"])

    color_cycle = cycle(resolved)
    for item in items:
        yield item, next(color_cycle)


# For direct import
__all__ = [
    # Core filters
    "color_filter",
    "price_filter",
    "badge_filter",
    "status_icon_filter",

    # Text formatting
    "bold_filter",
    "italic_filter",
    "strike_filter",
    "link_filter",

    # Shortcuts
    "success_text_filter",
    "error_text_filter",
    "warning_text_filter",
    "muted_text_filter",
    "highlight_filter",

    # Utilities
    "get_color",
    "get_all_colors",

    # Constants
    "SEMANTIC_COLORS",
    "BADGE_BACKGROUNDS",
    "STATUS_ICONS",
    "STYLING_FILTERS",
    "OutputTarget",

    # Color cycling/alternating
    "COLOR_SCHEMES",
    "ColorCycler",
    "ComponentStyler",
    "create_styler_for_template",
    "alternating_color_filter",
]

# Add alternating_colors filter to registry (after function is defined)
STYLING_FILTERS["alternating_colors"] = alternating_color_filter
