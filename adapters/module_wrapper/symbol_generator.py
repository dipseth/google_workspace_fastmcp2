"""
Symbol Generator for Module Components

Generates unique, token-efficient Unicode symbols for module components.
Symbols are designed to:
  1. Be single tokens (not split by tokenizers)
  2. Be visually distinct
  3. Have mnemonic associations where possible
  4. Support multi-module disambiguation via prefixes

Usage:
    generator = SymbolGenerator()

    # Single module
    symbols = generator.generate_symbols(["Button", "Grid", "Section"])
    # => {"Button": "ᵬ", "Grid": "ℊ", "Section": "§"}

    # Multi-module with prefixes
    symbols = generator.generate_symbols(
        ["Button", "Grid"],
        module_prefix="gchat"
    )
    # => {"Button": "g:ᵬ", "Grid": "g:ℊ"}
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from adapters.module_wrapper.types import (
    ComponentName,
    Payload,
    ReverseSymbolMapping,
    Symbol,
    SymbolMapping,
)

logger = logging.getLogger(__name__)


# =============================================================================
# UNICODE SYMBOL POOLS
# =============================================================================

# Primary symbols per letter - chosen to be:
# - Single tokens (not split by BPE/SentencePiece)
# - Visually distinct
# - Not commonly used in English text

LETTER_SYMBOLS: Dict[str, List[str]] = {
    "A": ["ǎ", "ă", "ą", "Å", "α"],  # Action, Arrow, etc.
    "B": ["ᵬ", "Ƀ", "β", "ℬ", "ɓ"],  # Button, ButtonList
    "C": ["©", "¢", "ȼ", "ℂ", "ç"],  # Card, Chip, Column
    "D": ["đ", "Đ", "ð", "δ", "ɖ"],  # DecoratedText, DateTimePicker, Divider
    "E": ["ε", "ė", "ę", "ə", "ɛ"],  # Element, Entry
    "F": ["ƒ", "ℱ", "φ", "ɟ", "ʄ"],  # Footer, Form
    "G": ["ℊ", "ǵ", "ǧ", "γ", "ɠ"],  # Grid, GridItem
    "H": ["Ħ", "ħ", "ℏ", "η", "ɦ"],  # Header
    "I": ["ɨ", "ǐ", "ı", "ι", "ɪ"],  # Image, Icon, Input
    "J": ["ʲ", "ɟ", "ʝ", "ĵ", "ȷ"],  # (reserved)
    "K": ["ĸ", "κ", "ķ", "ƙ", "ǩ"],  # (reserved)
    "L": ["ŀ", "ℓ", "λ", "ɭ", "ł"],  # Link, Label
    "M": ["μ", "ɱ", "ɯ", "ℳ", "ṁ"],  # Menu, MenuItem
    "N": ["ŋ", "ñ", "ν", "ɲ", "ƞ"],  # (reserved)
    "O": ["ø", "Ω", "ω", "ɵ", "ð"],  # OnClick, OverflowMenu
    "P": ["¶", "π", "ρ", "ƥ", "þ"],  # Paragraph, Picker
    "Q": ["ʠ", "Ǫ", "ǫ", "ɋ", "ʔ"],  # (reserved)
    "R": ["ɽ", "ř", "ρ", "ʀ", "ɾ"],  # Row, Range
    "S": ["§", "ʂ", "ş", "ș", "σ"],  # Section, SelectionInput, SwitchControl
    "T": ["ŧ", "Ʈ", "τ", "ƭ", "ʈ"],  # TextParagraph, TextInput
    "U": ["ʊ", "ü", "υ", "ų", "ʉ"],  # (reserved)
    "V": ["ʋ", "ν", "ʌ", "ɤ", "ỽ"],  # (reserved)
    "W": ["ʍ", "ω", "ẃ", "ẁ", "ŵ"],  # Widget
    "X": ["×", "χ", "ẋ", "ɤ", "ẍ"],  # Multiplier (special)
    "Y": ["ɣ", "ý", "ŷ", "ÿ", "ƴ"],  # (reserved)
    "Z": ["ʐ", "ζ", "ẑ", "ž", "ƶ"],  # (reserved)
}

# Fallback symbols for when all letter symbols are exhausted
FALLBACK_SYMBOLS = [
    "†",
    "‡",
    "•",
    "◦",
    "◆",
    "◇",
    "★",
    "☆",
    "♠",
    "♣",
    "♥",
    "♦",
    "►",
    "◄",
    "▲",
    "▼",
    "●",
    "○",
    "■",
    "□",
    "▪",
    "▫",
    "◙",
    "◘",
]

# Module prefix symbols - use for multi-module disambiguation
MODULE_PREFIX_SYMBOLS: Dict[str, str] = {
    "gchat": "g",
    "google_chat": "g",
    "card_framework": "c",
    "gmail": "m",
    "drive": "d",
    "sheets": "s",
    "docs": "o",
    "calendar": "l",
    "forms": "f",
    "slides": "i",
    "tasks": "t",
}


# =============================================================================
# STYLING REGISTRY
# =============================================================================


@dataclass
class StyleRule:
    """A styling rule that can be applied to card content."""

    name: str  # e.g., "success_color"
    description: str  # e.g., "Green color for success states"
    html_template: str  # e.g., '<font color="#34a853">{text}</font>'
    semantic_triggers: List[str]  # e.g., ["success", "ok", "valid", "approved"]


# Default styling rules (from SmartCardBuilder patterns)
# These are NOT in the dataclass module but are application-level customizations
DEFAULT_STYLE_RULES: List[StyleRule] = [
    # Color semantic mappings
    StyleRule(
        name="success_color",
        description="Green color for success, valid, approved states",
        html_template='<font color="#34a853">{text}</font>',
        semantic_triggers=["success", "ok", "valid", "approved", "complete", "active"],
    ),
    StyleRule(
        name="error_color",
        description="Red color for error, failed, invalid states",
        html_template='<font color="#ea4335">{text}</font>',
        semantic_triggers=["error", "failed", "invalid", "rejected", "danger", "alert"],
    ),
    StyleRule(
        name="warning_color",
        description="Orange/yellow color for warning states",
        html_template='<font color="#fbbc04">{text}</font>',
        semantic_triggers=["warning", "caution", "pending", "attention"],
    ),
    StyleRule(
        name="info_color",
        description="Blue color for informational states",
        html_template='<font color="#4285f4">{text}</font>',
        semantic_triggers=["info", "information", "note", "notice"],
    ),
    # Text formatting
    StyleRule(
        name="strikethrough_price",
        description="Strikethrough for original/old prices",
        html_template="<s>{text}</s>",
        semantic_triggers=["original_price", "old_price", "was", "msrp"],
    ),
    StyleRule(
        name="bold_emphasis",
        description="Bold for emphasis",
        html_template="<b>{text}</b>",
        semantic_triggers=["important", "key", "highlight", "emphasis"],
    ),
    StyleRule(
        name="italic_quote",
        description="Italic for quotes and annotations",
        html_template="<i>{text}</i>",
        semantic_triggers=["quote", "note", "annotation", "comment"],
    ),
]


@dataclass
class StylingRegistry:
    """
    Registry for styling rules that aren't defined in module dataclasses.

    These are application-level formatting rules (colors, text styles) that
    the card builder can apply based on semantic triggers.
    """

    rules: List[StyleRule] = field(default_factory=list)
    _trigger_index: Dict[str, StyleRule] = field(default_factory=dict)

    def __post_init__(self):
        """Build trigger index after initialization."""
        self._build_trigger_index()

    def _build_trigger_index(self):
        """Build index from triggers to rules."""
        self._trigger_index = {}
        for rule in self.rules:
            for trigger in rule.semantic_triggers:
                self._trigger_index[trigger.lower()] = rule

    def add_rule(self, rule: StyleRule):
        """Add a styling rule."""
        self.rules.append(rule)
        for trigger in rule.semantic_triggers:
            self._trigger_index[trigger.lower()] = rule

    def find_by_trigger(self, text: str) -> Optional[StyleRule]:
        """Find a style rule by semantic trigger."""
        text_lower = text.lower()
        # Exact match
        if text_lower in self._trigger_index:
            return self._trigger_index[text_lower]
        # Partial match
        for trigger, rule in self._trigger_index.items():
            if trigger in text_lower or text_lower in trigger:
                return rule
        return None

    def apply_style(self, text: str, style_name: str) -> str:
        """Apply a named style to text."""
        for rule in self.rules:
            if rule.name == style_name:
                return rule.html_template.format(text=text)
        return text

    def to_embedding_text(self) -> str:
        """Generate text for embedding the styling rules."""
        parts = []
        for rule in self.rules:
            triggers = ", ".join(rule.semantic_triggers[:3])
            parts.append(f"{rule.name}: {rule.description} ({triggers})")
        return " | ".join(parts)


# =============================================================================
# SYMBOL GENERATOR
# =============================================================================


class SymbolGenerator:
    """
    Generates unique Unicode symbols for module components.

    The generator maintains state to ensure uniqueness across multiple
    calls and supports multi-module scenarios with prefixes.
    """

    def __init__(
        self,
        module_prefix: Optional[str] = None,
        custom_symbols: Optional[SymbolMapping] = None,
    ):
        """
        Initialize the symbol generator.

        Args:
            module_prefix: Optional module identifier for multi-module support.
                          If provided, symbols will be prefixed (e.g., "g:ᵬ").
            custom_symbols: Optional dict of component_name → symbol overrides.
        """
        self.module_prefix = module_prefix
        self.custom_symbols = custom_symbols or {}

        # Track used symbols to ensure uniqueness
        self._used_symbols: Set[str] = set()
        self._letter_usage: Dict[str, int] = {}  # Letter -> next index to use
        self._fallback_index = 0

        # Generated mappings
        self._component_to_symbol: Dict[str, str] = {}
        self._symbol_to_component: Dict[str, str] = {}

        # Pre-register custom symbols to prevent collisions
        for comp, sym in self.custom_symbols.items():
            self._used_symbols.add(sym)
            self._component_to_symbol[comp] = sym
            self._symbol_to_component[sym] = comp

    def _get_prefix(self) -> str:
        """Get the module prefix string."""
        if not self.module_prefix:
            return ""

        # Use short prefix from mapping or first letter
        short = MODULE_PREFIX_SYMBOLS.get(
            self.module_prefix.lower(), self.module_prefix[0].lower()
        )
        return f"{short}:"

    def _get_symbol_for_letter(self, letter: str) -> str:
        """Get the next available symbol for a letter, skipping used ones."""
        letter_upper = letter.upper()

        # Get available symbols for this letter
        symbols = LETTER_SYMBOLS.get(letter_upper, [])

        # Find the first unused symbol for this letter
        for symbol in symbols:
            if symbol not in self._used_symbols:
                return symbol

        # Exhausted letter symbols - use fallback
        for symbol in FALLBACK_SYMBOLS:
            if symbol not in self._used_symbols:
                return symbol

        # Ultimate fallback - use letter with subscript number
        counter = len([s for s in self._used_symbols if s.startswith(letter_upper)])
        return f"{letter_upper}_{counter}"

    def generate_symbol(self, component_name: ComponentName) -> Symbol:
        """
        Generate a symbol for a single component.

        Args:
            component_name: Name of the component (e.g., "Button", "GridItem")

        Returns:
            Unicode symbol, optionally prefixed (e.g., "ᵬ" or "g:ᵬ")
        """
        # Check custom override
        if component_name in self.custom_symbols:
            base_symbol = self.custom_symbols[component_name]
        elif component_name in self._component_to_symbol:
            base_symbol = self._component_to_symbol[component_name]
        else:
            # Generate new symbol based on first letter
            first_letter = component_name[0] if component_name else "X"
            base_symbol = self._get_symbol_for_letter(first_letter)

            # Track usage
            self._used_symbols.add(base_symbol)
            self._component_to_symbol[component_name] = base_symbol
            self._symbol_to_component[base_symbol] = component_name

        # Add prefix if configured
        prefix = self._get_prefix()
        return f"{prefix}{base_symbol}" if prefix else base_symbol

    def generate_symbols(
        self,
        component_names: List[str],
        module_prefix: Optional[str] = None,
        priority_scores: Optional[Dict[str, int]] = None,
    ) -> Dict[str, str]:
        """
        Generate symbols for multiple components.

        Components are processed in priority order - higher scores get their
        preferred symbols first. This ensures container components (Section,
        ButtonList, Grid) get their intuitive symbols before leaf components.

        Args:
            component_names: List of component names
            module_prefix: Optional override for module prefix
            priority_scores: Optional dict of component_name → priority score.
                            Higher scores are processed first. Components with
                            more children in the hierarchy should have higher scores.
                            If not provided, processes alphabetically.

        Returns:
            Dict mapping component names to symbols
        """
        # Temporarily set prefix if provided
        old_prefix = self.module_prefix
        if module_prefix is not None:
            self.module_prefix = module_prefix

        # Sort by priority if provided, otherwise alphabetical
        if priority_scores:
            # Calculate effective priority: base priority + dominant bonus for shorter names.
            # This ensures within same-letter groups, shorter names ALWAYS win:
            # - Button (6 chars) beats ButtonList (10 chars) for 'ᵬ'
            # - Grid (4 chars) beats GridItem (8 chars) for 'ℊ'
            # - Card (4 chars) beats CardHeader (10 chars) for '©'
            #
            # Bonus formula: (20 - len) * 20 gives up to +320 bonus for short names
            # This dominates base priority differences within same-letter groups
            def effective_priority(name):
                base = priority_scores.get(name, 0)
                length_bonus = max(0, (20 - len(name)) * 20)  # Shorter = dominant bonus
                return base + length_bonus

            sorted_names = sorted(
                component_names, key=lambda n: (-effective_priority(n), n)
            )
        else:
            sorted_names = sorted(component_names)

        result = {}
        for name in sorted_names:
            result[name] = self.generate_symbol(name)

        # Restore prefix
        self.module_prefix = old_prefix

        return result

    def get_reverse_mapping(self) -> Dict[str, str]:
        """Get symbol → component name mapping."""
        prefix = self._get_prefix()
        if prefix:
            return {
                f"{prefix}{sym}": comp
                for sym, comp in self._symbol_to_component.items()
            }
        return self._symbol_to_component.copy()

    def get_symbol_table_text(self) -> str:
        """
        Generate human-readable symbol table for LLM instructions.

        Returns:
            Formatted text suitable for MCP tool descriptions
        """
        if not self._component_to_symbol:
            return "No symbols generated yet."

        prefix = self._get_prefix()
        lines = []

        # Group by category (first letter)
        by_letter: Dict[str, List[Tuple[str, str]]] = {}
        for comp, sym in sorted(self._component_to_symbol.items()):
            letter = comp[0].upper()
            if letter not in by_letter:
                by_letter[letter] = []
            full_sym = f"{prefix}{sym}" if prefix else sym
            by_letter[letter].append((full_sym, comp))

        for letter in sorted(by_letter.keys()):
            items = by_letter[letter]
            mappings = [f"{sym}={comp}" for sym, comp in items]
            lines.append(f"**{letter}:** {', '.join(mappings)}")

        return "\n".join(lines)

    def build_embedding_text(self, component_name: str) -> str:
        """
        Build text for embedding that creates strong symbol-component association.

        The symbol appears multiple times in different contexts to strengthen
        the bidirectional embedding association.

        Args:
            component_name: Name of the component

        Returns:
            Text suitable for embedding
        """
        symbol = self.generate_symbol(component_name)
        base_sym = symbol.split(":")[-1] if ":" in symbol else symbol

        # Multiple mentions create stronger association
        return f"{base_sym} {component_name} {base_sym} | {component_name} widget {base_sym}"


# =============================================================================
# FACTORY FUNCTIONS
# =============================================================================


def create_generator_for_module(
    module_name: str,
    component_names: List[str],
    custom_overrides: Optional[Dict[str, str]] = None,
) -> SymbolGenerator:
    """
    Create a symbol generator pre-populated with component names.

    Args:
        module_name: Module name for prefix generation
        component_names: List of component names to generate symbols for
        custom_overrides: Optional symbol overrides

    Returns:
        Configured SymbolGenerator
    """
    generator = SymbolGenerator(
        module_prefix=module_name,
        custom_symbols=custom_overrides,
    )
    generator.generate_symbols(component_names)
    return generator


def create_default_styling_registry() -> StylingRegistry:
    """
    Create a styling registry with default rules.

    Returns:
        StylingRegistry with common styling patterns
    """
    registry = StylingRegistry(rules=DEFAULT_STYLE_RULES.copy())
    return registry


# =============================================================================
# INTEGRATION HELPERS
# =============================================================================


def extract_component_names_from_wrapper(wrapper: "ModuleWrapper") -> List[str]:
    """
    Extract class component names from a ModuleWrapper.

    Args:
        wrapper: Initialized ModuleWrapper instance

    Returns:
        List of class component names
    """
    names = []
    for full_path, component in wrapper.components.items():
        if component.component_type == "class":
            names.append(component.name)
    return names
