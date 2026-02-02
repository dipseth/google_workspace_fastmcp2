"""
Structure Validator and Composer for Module Components

Provides:
1. Deterministic validation of component structures against hierarchy
2. Fallback structure generation from inputs
3. Symbol-enriched relationship text for embeddings
4. Template composition system

This is module-agnostic - works with any ModuleWrapper.

Usage:
    from adapters.module_wrapper.structure_validator import StructureValidator

    validator = StructureValidator(wrapper)

    # Validate a structure
    is_valid, issues = validator.validate_structure("§[đ, ᵬ]")

    # Generate structure from inputs
    structure = validator.generate_structure_from_inputs({"text": "Hello", "button": "Click"})

    # Get symbol-enriched relationship text for embedding
    text = validator.get_enriched_relationship_text("Section")
"""

import logging
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set, Tuple

from adapters.module_wrapper.types import (
    ComponentName,
    IssueList,
    RelationshipDict,
    ReverseSymbolMapping,
    SuggestionList,
    Symbol,
    SymbolMapping,
    Validatable,
)

if TYPE_CHECKING:
    from adapters.module_wrapper.core import ModuleWrapper

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of structure validation."""

    is_valid: bool
    structure: str
    issues: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    resolved_components: Dict[str, str] = field(
        default_factory=dict
    )  # symbol → component name


@dataclass
class ComponentSlot:
    """A slot in a structure that can accept inputs."""

    component_name: str
    symbol: str
    field_name: Optional[str] = None
    accepts_types: List[str] = field(default_factory=list)
    multiplier: int = 1


# =============================================================================
# INPUT TYPE INFERENCE
# =============================================================================

# Patterns to infer what component an input needs
INPUT_PATTERNS = {
    # Text content → DecoratedText or TextParagraph
    "text": ["DecoratedText", "TextParagraph"],
    "title": ["DecoratedText", "CardHeader"],
    "subtitle": ["DecoratedText", "CardHeader"],
    "description": ["TextParagraph", "DecoratedText"],
    # Media → Image or Icon
    "image": ["Image"],
    "image_url": ["Image"],
    "icon": ["Icon"],
    "icon_name": ["Icon"],
    # Interactive → Button
    "button": ["Button", "ButtonList"],
    "button_text": ["Button"],
    "buttons": ["ButtonList"],
    "action": ["Button", "OnClick"],
    "url": ["OpenLink", "Button"],
    # Selection → SelectionInput
    "select": ["SelectionInput"],
    "options": ["SelectionInput"],
    "dropdown": ["SelectionInput"],
    "checkbox": ["SelectionInput"],
    # Grid → Grid/GridItem
    "grid": ["Grid"],
    "items": ["Grid", "GridItem"],
    "columns": ["Columns"],
    # Date/Time
    "date": ["DateTimePicker"],
    "time": ["DateTimePicker"],
    "datetime": ["DateTimePicker"],
}

# Components that can be direct children of Section (Widget subtypes)
WIDGET_TYPES = {
    "DecoratedText",
    "TextParagraph",
    "Image",
    "ButtonList",
    "Grid",
    "SelectionInput",
    "DateTimePicker",
    "Divider",
    "TextInput",
    "Columns",
    "ChipList",
}

# Components that need a wrapper
NEEDS_WRAPPER = {
    "Button": "ButtonList",  # Button needs to be in ButtonList
    "Chip": "ChipList",  # Chip needs to be in ChipList
    "GridItem": "Grid",  # GridItem needs to be in Grid
    "Column": "Columns",  # Column needs to be in Columns
}


class StructureValidator:
    """
    Validates and composes component structures.

    Module-agnostic: works with any ModuleWrapper instance.
    """

    def __init__(self, wrapper: "ModuleWrapper"):
        """
        Initialize with a ModuleWrapper instance.

        Args:
            wrapper: ModuleWrapper with loaded components and relationships
        """
        self.wrapper = wrapper
        self._symbols: Optional[Dict[str, str]] = None
        self._reverse_symbols: Optional[Dict[str, str]] = None
        self._relationships: Optional[Dict[str, List[str]]] = None
        self._widget_types: Set[str] = WIDGET_TYPES.copy()

    @property
    def symbols(self) -> SymbolMapping:
        """Get symbol mappings (cached).

        Uses shared symbols from structure_dsl for consistency with the DSL parser.
        Falls back to ModuleWrapper-generated symbols if structure_dsl not available.
        """
        if self._symbols is None:
            try:
                # Use shared symbols from structure_dsl for consistency
                from gchat.structure_dsl import COMPONENT_TO_SYMBOL, ensure_initialized

                ensure_initialized()
                if COMPONENT_TO_SYMBOL:
                    self._symbols = COMPONENT_TO_SYMBOL.copy()
                else:
                    # Fallback to ModuleWrapper-generated symbols
                    self._symbols = self.wrapper.generate_component_symbols(
                        use_prefix=False
                    )
            except ImportError:
                # structure_dsl not available, use ModuleWrapper symbols
                self._symbols = self.wrapper.generate_component_symbols(
                    use_prefix=False
                )
        return self._symbols

    @property
    def reverse_symbols(self) -> ReverseSymbolMapping:
        """Get reverse symbol mappings: symbol → component name."""
        if self._reverse_symbols is None:
            self._reverse_symbols = {v: k for k, v in self.symbols.items()}
        return self._reverse_symbols

    @property
    def relationships(self) -> RelationshipDict:
        """Get parent → children relationships (cached)."""
        if self._relationships is None:
            raw_rels = self.wrapper.extract_relationships_by_parent(max_depth=3)
            # Flatten to just child class names
            self._relationships = {}
            for parent, children in raw_rels.items():
                child_names = list(
                    set(
                        c.get("child_class", "")
                        for c in children
                        if c.get("child_class")
                    )
                )
                if child_names:
                    self._relationships[parent] = child_names
        return self._relationships

    # =========================================================================
    # STRUCTURE PARSING
    # =========================================================================

    def parse_structure(self, structure: str) -> List[Dict[str, Any]]:
        """
        Parse a DSL structure string into components.

        Args:
            structure: DSL string like "§[đ, ᵬ×2]"

        Returns:
            List of parsed components with nesting info
        """
        # Remove whitespace
        structure = structure.strip()

        components = []
        self._parse_recursive(structure, components, depth=0)
        return components

    def _parse_recursive(self, s: str, components: List, depth: int):
        """Recursively parse structure."""
        if not s:
            return

        # Split by comma at current level (not inside brackets)
        parts = self._split_at_level(s)

        for part in parts:
            part = part.strip()
            if not part:
                continue

            # Parse component: symbol(×N)?([children])?
            # Use proper bracket matching, not regex for nested brackets
            symbol = ""
            multiplier = 1
            children_str = ""

            i = 0
            # Extract symbol (everything before [ or × or end)
            while i < len(part) and part[i] not in "[×":
                symbol += part[i]
                i += 1

            symbol = symbol.strip()
            if not symbol:
                continue

            # Check for multiplier (×N)
            if i < len(part) and part[i] == "×":
                i += 1
                num_str = ""
                while i < len(part) and part[i].isdigit():
                    num_str += part[i]
                    i += 1
                if num_str:
                    multiplier = int(num_str)

            # Check for children [...]
            if i < len(part) and part[i] == "[":
                # Find matching closing bracket using level counting
                level = 0
                start = i + 1
                for j in range(i, len(part)):
                    if part[j] == "[":
                        level += 1
                    elif part[j] == "]":
                        level -= 1
                        if level == 0:
                            children_str = part[start:j]
                            break

            # Resolve symbol to component name
            component_name = self.reverse_symbols.get(symbol, symbol)

            comp = {
                "symbol": symbol,
                "name": component_name,
                "multiplier": multiplier,
                "depth": depth,
                "children": [],
            }

            # Parse children if present
            if children_str:
                self._parse_recursive(children_str, comp["children"], depth + 1)

            components.append(comp)

    def _split_at_level(self, s: str) -> List[str]:
        """Split string by comma, but only at the top bracket level."""
        parts = []
        current = ""
        level = 0

        for char in s:
            if char == "[":
                level += 1
                current += char
            elif char == "]":
                level -= 1
                current += char
            elif char == "," and level == 0:
                parts.append(current.strip())
                current = ""
            else:
                current += char

        if current.strip():
            parts.append(current.strip())

        return parts

    # =========================================================================
    # VALIDATION
    # =========================================================================

    def validate_structure(self, structure: str) -> ValidationResult:
        """
        Validate a DSL structure against the component hierarchy.

        Args:
            structure: DSL string like "§[đ, Ƀ[ᵬ×2]]"

        Returns:
            ValidationResult with is_valid, issues, and suggestions
        """
        result = ValidationResult(
            is_valid=True,
            structure=structure,
        )

        try:
            components = self.parse_structure(structure)
        except Exception as e:
            result.is_valid = False
            result.issues.append(f"Parse error: {e}")
            return result

        # Validate each component
        for comp in components:
            self._validate_component(comp, None, result)

        return result

    def _validate_component(
        self,
        comp: Dict,
        parent: Optional[Dict],
        result: ValidationResult,
    ):
        """Validate a single component and its children."""
        name = comp["name"]
        symbol = comp["symbol"]

        # Check if symbol is known
        if symbol not in self.reverse_symbols and name not in self.symbols:
            result.issues.append(f"Unknown symbol/component: {symbol}")
            # Don't mark invalid - might still work
        else:
            result.resolved_components[symbol] = name

        # Check parent-child relationship
        if parent:
            parent_name = parent["name"]
            valid_children = self.relationships.get(parent_name, [])

            # Check direct relationship
            if name not in valid_children:
                # Check if it's a Widget type (can go in Section/Column)
                if parent_name in ["Section", "Column"] and name in self._widget_types:
                    pass  # Valid - Widget types can go in Section/Column
                elif name in NEEDS_WRAPPER:
                    wrapper = NEEDS_WRAPPER[name]
                    result.issues.append(f"{name} should be wrapped in {wrapper}")
                    result.suggestions.append(
                        f"Use {self.symbols.get(wrapper, wrapper)}[{symbol}] instead of {symbol}"
                    )
                    result.is_valid = False
                else:
                    result.issues.append(
                        f"{name} cannot be direct child of {parent_name}"
                    )
                    result.is_valid = False

        # Validate children recursively
        for child in comp.get("children", []):
            self._validate_component(child, comp, result)

    def can_contain(self, parent: str, child: str) -> bool:
        """
        Check if parent component can contain child component.

        Args:
            parent: Parent component name
            child: Child component name

        Returns:
            True if valid containment
        """
        # Direct relationship
        if child in self.relationships.get(parent, []):
            return True

        # Widget types can go in Section/Column
        if parent in ["Section", "Column"] and child in self._widget_types:
            return True

        # Check if child needs wrapper that parent can contain
        if child in NEEDS_WRAPPER:
            wrapper = NEEDS_WRAPPER[child]
            return self.can_contain(parent, wrapper)

        return False

    # =========================================================================
    # STRUCTURE GENERATION (Fallback)
    # =========================================================================

    def generate_structure_from_inputs(
        self,
        inputs: Dict[str, Any],
        container: str = "Section",
    ) -> str:
        """
        Deterministically generate a valid structure from inputs.

        This is the FALLBACK when LLM doesn't provide perfect structure.

        Args:
            inputs: Dict of input values (e.g., {"text": "Hello", "button": "Click"})
            container: Root container component (default: Section)

        Returns:
            Valid DSL structure string
        """
        # Step 1: Infer components from input keys
        needed_components = self._infer_components_from_inputs(inputs)

        # Step 2: Wrap components that need wrappers
        wrapped = self._apply_wrappers(needed_components)

        # Step 3: Filter to only Widget types (can go in Section)
        valid_children = [c for c in wrapped if c in self._widget_types]

        # Step 4: Build structure
        container_sym = self.symbols.get(container, container)

        if not valid_children:
            # Default to DecoratedText if no valid components found
            return f"{container_sym}[{self.symbols.get('DecoratedText', 'đ')}]"

        child_syms = []
        for child in valid_children:
            sym = self.symbols.get(child, child)

            # Check if this component has sub-components
            if child == "ButtonList" and "buttons" in inputs:
                # Count buttons
                btn_count = (
                    len(inputs["buttons"]) if isinstance(inputs["buttons"], list) else 1
                )
                btn_sym = self.symbols.get("Button", "ᵬ")
                child_syms.append(f"{sym}[{btn_sym}×{btn_count}]")
            elif child == "Grid" and "items" in inputs:
                item_count = (
                    len(inputs["items"]) if isinstance(inputs["items"], list) else 1
                )
                item_sym = self.symbols.get("GridItem", "ǵ")
                child_syms.append(f"{sym}[{item_sym}×{item_count}]")
            else:
                child_syms.append(sym)

        return f"{container_sym}[{', '.join(child_syms)}]"

    def _infer_components_from_inputs(self, inputs: Dict[str, Any]) -> List[str]:
        """Infer which components are needed based on input keys."""
        components = []

        for key in inputs.keys():
            key_lower = key.lower()

            # Check exact match first
            if key_lower in INPUT_PATTERNS:
                components.extend(INPUT_PATTERNS[key_lower][:1])  # Take first match
                continue

            # Check partial match
            for pattern, comps in INPUT_PATTERNS.items():
                if pattern in key_lower or key_lower in pattern:
                    components.extend(comps[:1])
                    break

        # Remove duplicates while preserving order
        seen = set()
        unique = []
        for c in components:
            if c not in seen:
                seen.add(c)
                unique.append(c)

        return unique

    def _apply_wrappers(self, components: List[str]) -> List[str]:
        """Apply necessary wrappers to components."""
        result = []

        for comp in components:
            if comp in NEEDS_WRAPPER:
                wrapper = NEEDS_WRAPPER[comp]
                if wrapper not in result:
                    result.append(wrapper)
            else:
                result.append(comp)

        return result

    # =========================================================================
    # SYMBOL-ENRICHED RELATIONSHIPS (for embedding)
    # =========================================================================

    def get_enriched_relationship_text(self, component_name: str) -> str:
        """
        Get relationship text enriched with symbols for embedding.

        This creates text like:
        "§ Section contains ʍ Widget | §[đ, ᵬ] Section with DecoratedText Button"

        Args:
            component_name: Component to get relationships for

        Returns:
            Symbol-enriched text suitable for embedding
        """
        symbol = self.symbols.get(component_name, "?")
        children = self.relationships.get(component_name, [])

        if not children:
            return f"{symbol} {component_name}"

        parts = []

        # Part 1: Name with symbol
        parts.append(f"{symbol} {component_name}")

        # Part 2: Contains relationships with symbols
        child_parts = []
        for child in children[:5]:  # Limit for embedding efficiency
            child_sym = self.symbols.get(child, "?")
            child_parts.append(f"{child_sym} {child}")

        parts.append(f"contains {', '.join(child_parts)}")

        # Part 3: DSL example
        child_syms = [self.symbols.get(c, c) for c in children[:3]]
        dsl_example = f"{symbol}[{', '.join(child_syms)}]"
        parts.append(dsl_example)

        return " | ".join(parts)

    def get_all_enriched_relationships(self) -> Dict[str, str]:
        """
        Get enriched relationship text for all components.

        Returns:
            Dict mapping component name to enriched text
        """
        enriched = {}

        for component_name in self.relationships.keys():
            enriched[component_name] = self.get_enriched_relationship_text(
                component_name
            )

        return enriched

    # =========================================================================
    # TEMPLATE COMPOSITION
    # =========================================================================

    def compose_from_template(
        self,
        template: str,
        inputs: Dict[str, Any],
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Compose a structure from a template with variable substitution.

        Templates use {variable} syntax:
        - "§[đ, Ƀ[ᵬ×{button_count}]]"
        - "§[ɨ, đ×{text_count}, Ƀ[ᵬ×{button_count}]]"

        Args:
            template: Template string with {variables}
            inputs: Dict with variable values and content

        Returns:
            Tuple of (resolved_structure, field_mapping)
        """
        structure = template

        # Substitute variables
        for key, value in inputs.items():
            placeholder = f"{{{key}}}"
            if placeholder in structure:
                if isinstance(value, (list, tuple)):
                    structure = structure.replace(placeholder, str(len(value)))
                else:
                    structure = structure.replace(placeholder, str(value))

        # Remove any remaining unresolved placeholders (default to 1)
        structure = re.sub(r"\{[^}]+\}", "1", structure)

        return structure, inputs


# =============================================================================
# FACTORY FUNCTION
# =============================================================================


def create_validator(wrapper: "ModuleWrapper") -> StructureValidator:
    """
    Create a StructureValidator for a ModuleWrapper.

    Args:
        wrapper: Initialized ModuleWrapper

    Returns:
        StructureValidator instance
    """
    return StructureValidator(wrapper)
