"""
Universal DSL to Qdrant Query Parser

This module provides a robust and durable process for parsing DSL notation
and converting it to appropriate Qdrant queries. It serves as the canonical
implementation for DSL parsing across the codebase.

The DSL (Domain Specific Language) uses Unicode symbols to compactly represent
component structures:
    "§[δ×3, Ƀ[ᵬ×2]]" → Section with 3 DecoratedTexts and ButtonList with 2 Buttons

This parser handles TWO types of DSL:

1. **Structure DSL** - Component hierarchy and relationships:
   - "§[δ×3, Ƀ[ᵬ×2]]" → Section with 3 DecoratedTexts and ButtonList with 2 Buttons

2. **Content DSL** - Component content with styling modifiers:
   - "δ 'Status: Online' success bold" → DecoratedText with green bold text
   - "ᵬ Click Here https://example.com" → Button with URL action

Content DSL Features:
- Symbol prefix indicates component type (δ, ᵬ, §, etc.)
- Quoted or unquoted text content
- Style modifiers (yellow, bold, success, error, italic, etc.)
- URL detection for button/link actions
- Continuation lines (indented) for multi-line content

Usage:
    from adapters.module_wrapper.dsl_parser import DSLParser, parse_dsl_to_qdrant_query

    # With ModuleWrapper
    parser = DSLParser(wrapper)
    result = parser.parse("§[δ×3, Ƀ[ᵬ×2]]")

    # Direct query generation
    queries = parser.to_qdrant_queries()

    # Standalone function
    query = parse_dsl_to_qdrant_query("§[δ×3]", symbol_mapping)

    # Content DSL parsing
    content = parser.parse_content_dsl("δ 'Hello World' success bold")
    jinja = parser.content_to_jinja(content)  # "{{ 'Hello World' | success_text | bold }}"
"""

import logging
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set, Tuple, Union

from adapters.module_wrapper.types import (
    ComponentName,
    ComponentPaths,
    DSLNotation,
    HasSymbol,
    IssueList,
    Payload,
    ReverseSymbolMapping,
    Serializable,
    SuggestionList,
    Symbol,
    SymbolMapping,
)

if TYPE_CHECKING:
    from adapters.module_wrapper.core import ModuleWrapper

logger = logging.getLogger(__name__)


# =============================================================================
# DATA CLASSES
# =============================================================================


@dataclass
class DSLToken:
    """A single token from DSL tokenization."""

    type: str  # 'symbol', 'multiplier', 'open', 'close', 'component_name'
    value: str
    position: int


@dataclass
class DSLNode:
    """A node in the parsed DSL tree."""

    symbol: str
    component_name: str
    multiplier: int = 1
    children: List["DSLNode"] = field(default_factory=list)
    parent: Optional["DSLNode"] = None
    depth: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "symbol": self.symbol,
            "name": self.component_name,
            "multiplier": self.multiplier,
            "depth": self.depth,
            "children": [child.to_dict() for child in self.children],
        }

    def to_compact_dsl(self) -> str:
        """Convert back to compact DSL notation."""
        result = self.symbol
        if self.multiplier > 1:
            result = f"{self.symbol}×{self.multiplier}"
        if self.children:
            children_str = ", ".join(c.to_compact_dsl() for c in self.children)
            result = f"{result}[{children_str}]"
        return result

    def to_expanded_notation(self) -> str:
        """Convert to expanded component name notation."""
        result = self.component_name
        if self.multiplier > 1:
            result = f"{self.component_name}×{self.multiplier}"
        if self.children:
            children_str = ", ".join(c.to_expanded_notation() for c in self.children)
            result = f"{result}[{children_str}]"
        return result

    def flatten(self) -> List["DSLNode"]:
        """Flatten tree to list (pre-order traversal)."""
        nodes = [self]
        for child in self.children:
            nodes.extend(child.flatten())
        return nodes

    def get_component_counts(self) -> Dict[str, int]:
        """Get counts of each component type in subtree."""
        counts = Counter()
        counts[self.component_name] += self.multiplier
        for child in self.children:
            child_counts = child.get_component_counts()
            for name, count in child_counts.items():
                counts[name] += count
        return dict(counts)


@dataclass
class DSLParseResult:
    """Result of parsing a DSL string."""

    dsl: str
    is_valid: bool
    root_nodes: List[DSLNode] = field(default_factory=list)
    component_paths: List[str] = field(default_factory=list)
    component_counts: Dict[str, int] = field(default_factory=dict)
    issues: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    resolved_symbols: Dict[str, str] = field(default_factory=dict)  # symbol → name

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "dsl": self.dsl,
            "is_valid": self.is_valid,
            "root": self.root_nodes[0].to_dict() if self.root_nodes else None,
            "components": [n.to_dict() for n in self.root_nodes],
            "component_paths": self.component_paths,
            "component_counts": self.component_counts,
            "issues": self.issues,
            "suggestions": self.suggestions,
            "resolved_symbols": self.resolved_symbols,
        }


@dataclass
class QdrantQuery:
    """A Qdrant query specification."""

    collection: str
    vector_name: str  # 'components', 'inputs', 'relationships'
    query_text: str
    filters: Dict[str, Any] = field(default_factory=dict)
    limit: int = 10

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for execution."""
        return {
            "collection": self.collection,
            "vector_name": self.vector_name,
            "query_text": self.query_text,
            "filters": self.filters,
            "limit": self.limit,
        }


# =============================================================================
# CONTENT DSL DATA CLASSES
# =============================================================================


@dataclass
class StyleModifier:
    """A style modifier parsed from Content DSL."""

    name: str  # Original modifier name (e.g., "yellow", "bold", "success")
    jinja_filter: str  # Jinja filter name (e.g., "color", "bold", "success_text")
    jinja_args: Optional[str] = (
        None  # Arguments for filter (e.g., "'yellow'" for color)
    )

    def to_jinja(self) -> str:
        """Convert to Jinja filter syntax."""
        if self.jinja_args:
            return f"{self.jinja_filter}({self.jinja_args})"
        return self.jinja_filter


@dataclass
class ContentLine:
    """A single line of Content DSL."""

    symbol: str  # Component symbol (δ, ᵬ, etc.)
    component_name: str  # Resolved component name
    content: str  # The text content
    modifiers: List[StyleModifier] = field(default_factory=list)
    url: Optional[str] = None  # Detected URL for buttons/links
    line_number: int = 0
    is_continuation: bool = False  # True if this line continues previous

    def to_jinja(self) -> str:
        """Convert content to Jinja expression."""
        # Escape single quotes in content
        safe_content = self.content.replace("'", "\\'")
        expr = f"'{safe_content}'"

        # Apply modifiers as Jinja filters
        for mod in self.modifiers:
            expr = f"{expr} | {mod.to_jinja()}"

        return "{{ " + expr + " }}"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "symbol": self.symbol,
            "component": self.component_name,
            "content": self.content,
            "modifiers": [m.name for m in self.modifiers],
            "url": self.url,
            "jinja": self.to_jinja(),
        }


@dataclass
class ContentBlock:
    """A block of content lines for a single component."""

    primary: ContentLine
    continuations: List[ContentLine] = field(default_factory=list)

    @property
    def all_lines(self) -> List[ContentLine]:
        """Get all lines in the block."""
        return [self.primary] + self.continuations

    @property
    def full_content(self) -> str:
        """Get combined content from all lines."""
        parts = [self.primary.content]
        parts.extend(c.content for c in self.continuations)
        return "\n".join(parts)

    def to_jinja(self) -> str:
        """Convert entire block to Jinja expression."""
        if not self.continuations:
            return self.primary.to_jinja()

        # Multi-line: combine content then apply modifiers
        safe_content = self.full_content.replace("'", "\\'")
        expr = f"'{safe_content}'"

        # Apply modifiers from primary line
        for mod in self.primary.modifiers:
            expr = f"{expr} | {mod.to_jinja()}"

        return "{{ " + expr + " }}"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "symbol": self.primary.symbol,
            "component": self.primary.component_name,
            "content": self.full_content,
            "modifiers": [m.name for m in self.primary.modifiers],
            "url": self.primary.url,
            "jinja": self.to_jinja(),
            "line_count": len(self.all_lines),
        }


@dataclass
class ContentDSLResult:
    """Result of parsing Content DSL."""

    raw: str
    blocks: List[ContentBlock] = field(default_factory=list)
    issues: List[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        """Check if parsing was successful."""
        return len(self.blocks) > 0 and len(self.issues) == 0

    def to_jinja_list(self) -> List[str]:
        """Convert all blocks to Jinja expressions."""
        return [block.to_jinja() for block in self.blocks]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "raw": self.raw,
            "is_valid": self.is_valid,
            "blocks": [b.to_dict() for b in self.blocks],
            "issues": self.issues,
            "jinja_expressions": self.to_jinja_list(),
        }


# Style modifier registry - maps modifier names to Jinja filters
STYLE_MODIFIERS: Dict[str, Tuple[str, Optional[str]]] = {
    # Colors (filter_name, arg or None)
    "red": ("color", "'red'"),
    "green": ("color", "'green'"),
    "blue": ("color", "'blue'"),
    "yellow": ("color", "'yellow'"),
    "orange": ("color", "'orange'"),
    "purple": ("color", "'purple'"),
    "gray": ("color", "'gray'"),
    "grey": ("color", "'gray'"),
    "white": ("color", "'white'"),
    "black": ("color", "'black'"),
    # Semantic colors
    "success": ("success_text", None),
    "error": ("error_text", None),
    "warning": ("warning_text", None),
    "info": ("info_text", None),
    "danger": ("error_text", None),
    "ok": ("success_text", None),
    # Text formatting
    "bold": ("bold", None),
    "italic": ("italic", None),
    "strike": ("strikethrough", None),
    "strikethrough": ("strikethrough", None),
    "underline": ("underline", None),
    "code": ("monospace", None),
    "mono": ("monospace", None),
    "monospace": ("monospace", None),
    # Size modifiers
    "small": ("small", None),
    "large": ("large", None),
    # Special formatting
    "price": ("price", "'USD'"),
    "price_usd": ("price", "'USD'"),
    "price_eur": ("price", "'EUR'"),
    "price_gbp": ("price", "'GBP'"),
    "percent": ("percent", None),
    "date": ("date", None),
    "time": ("time", None),
    "datetime": ("datetime", None),
}


# =============================================================================
# DSL PARSER
# =============================================================================


class DSLParser:
    """
    Universal DSL Parser for component structure notation.

    This parser handles the complete lifecycle of DSL processing:
    1. Tokenization: String → Token list
    2. Parsing: Tokens → Tree structure
    3. Validation: Check against component hierarchy
    4. Query generation: Create Qdrant query specifications

    Thread-safe and stateless after initialization.
    """

    def __init__(
        self,
        symbol_mapping: Optional[SymbolMapping] = None,
        reverse_mapping: Optional[ReverseSymbolMapping] = None,
        relationships: Optional[Dict[str, List[str]]] = None,
        wrapper: Optional["ModuleWrapper"] = None,
    ):
        """
        Initialize the DSL parser.

        Args:
            symbol_mapping: Component name → symbol mapping (e.g., {"Button": "ᵬ"})
            reverse_mapping: Symbol → component name mapping (e.g., {"ᵬ": "Button"})
            relationships: Parent → [children] mapping for validation
            wrapper: Optional ModuleWrapper to get mappings from
        """
        self._wrapper = wrapper

        if wrapper:
            self._symbol_mapping = wrapper.symbol_mapping
            self._reverse_mapping = wrapper.reverse_symbol_mapping
            self._relationships = wrapper.relationships
        else:
            self._symbol_mapping = symbol_mapping or {}
            self._reverse_mapping = reverse_mapping or {}
            self._relationships = relationships or {}

        # Build symbol set for fast lookup
        self._all_symbols: Set[str] = set(self._reverse_mapping.keys())

        # Cache for repeated parses
        self._parse_cache: Dict[str, DSLParseResult] = {}

    @property
    def symbols(self) -> SymbolMapping:
        """Get component → symbol mapping."""
        return self._symbol_mapping

    @property
    def reverse_symbols(self) -> ReverseSymbolMapping:
        """Get symbol → component mapping."""
        return self._reverse_mapping

    @property
    def relationships(self) -> Dict[str, List[str]]:
        """Get parent → children relationships."""
        return self._relationships

    def refresh_from_wrapper(self):
        """Refresh mappings from wrapper (if available)."""
        if self._wrapper:
            self._symbol_mapping = self._wrapper.symbol_mapping
            self._reverse_mapping = self._wrapper.reverse_symbol_mapping
            self._relationships = self._wrapper.relationships
            self._all_symbols = set(self._reverse_mapping.keys())
            self._parse_cache.clear()

    # =========================================================================
    # TOKENIZATION
    # =========================================================================

    def tokenize(self, dsl_string: DSLNotation) -> List[DSLToken]:
        """
        Tokenize a DSL string into tokens.

        Token types:
        - 'symbol': Unicode symbol (e.g., §, ᵬ, ℊ)
        - 'multiplier': Repeat notation (e.g., ×3)
        - 'open': Opening bracket [
        - 'close': Closing bracket ]
        - 'component_name': Full component name (e.g., Button)

        Args:
            dsl_string: DSL notation string

        Returns:
            List of DSLToken objects
        """
        tokens = []
        i = 0
        s = dsl_string.strip()

        while i < len(s):
            char = s[i]

            # Skip whitespace and commas
            if char in " ,\n\t":
                i += 1
                continue

            # Brackets
            if char == "[":
                tokens.append(DSLToken(type="open", value="[", position=i))
                i += 1
                continue

            if char == "]":
                tokens.append(DSLToken(type="close", value="]", position=i))
                i += 1
                continue

            # Multiplier (×N, *N, or xN)
            if char in "×*x" and i + 1 < len(s) and s[i + 1].isdigit():
                j = i + 1
                while j < len(s) and s[j].isdigit():
                    j += 1
                multiplier_value = s[i + 1 : j]
                tokens.append(
                    DSLToken(
                        type="multiplier", value=f"×{multiplier_value}", position=i
                    )
                )
                i = j
                continue

            # Known symbol
            if char in self._all_symbols:
                tokens.append(DSLToken(type="symbol", value=char, position=i))
                i += 1
                continue

            # Component name (alphanumeric)
            if char.isalpha():
                j = i
                while j < len(s) and (s[j].isalnum() or s[j] == "_"):
                    j += 1
                word = s[i:j]

                # Check if it's a known component name
                if word in self._symbol_mapping:
                    # Convert to symbol token for consistency
                    sym = self._symbol_mapping[word]
                    tokens.append(DSLToken(type="symbol", value=sym, position=i))
                else:
                    # Keep as component name (might be unknown)
                    tokens.append(
                        DSLToken(type="component_name", value=word, position=i)
                    )
                i = j
                continue

            # Unknown character - skip with warning
            logger.debug(f"Skipping unknown character '{char}' at position {i}")
            i += 1

        return tokens

    # =========================================================================
    # PARSING
    # =========================================================================

    def parse(self, dsl_string: str, use_cache: bool = True) -> DSLParseResult:
        """
        Parse a DSL string into a structured result.

        This is the main entry point for DSL parsing.

        Args:
            dsl_string: DSL notation (e.g., "§[δ×3, Ƀ[ᵬ×2]]")
            use_cache: Whether to use cached results for repeated parses

        Returns:
            DSLParseResult with parsed structure and validation info
        """
        dsl_string = dsl_string.strip()

        # Check cache
        if use_cache and dsl_string in self._parse_cache:
            return self._parse_cache[dsl_string]

        # Tokenize
        try:
            tokens = self.tokenize(dsl_string)
        except Exception as e:
            return DSLParseResult(
                dsl=dsl_string,
                is_valid=False,
                issues=[f"Tokenization error: {e}"],
            )

        if not tokens:
            return DSLParseResult(
                dsl=dsl_string,
                is_valid=False,
                issues=["Empty or invalid DSL string"],
            )

        # Parse tokens to tree
        try:
            root_nodes, _ = self._parse_tokens(tokens, 0, 0)
        except Exception as e:
            return DSLParseResult(
                dsl=dsl_string,
                is_valid=False,
                issues=[f"Parse error: {e}"],
            )

        # Build result
        result = DSLParseResult(
            dsl=dsl_string,
            is_valid=True,
            root_nodes=root_nodes,
        )

        # Collect component paths and counts
        for node in root_nodes:
            self._collect_paths(node, result.component_paths)
            counts = node.get_component_counts()
            for name, count in counts.items():
                result.component_counts[name] = (
                    result.component_counts.get(name, 0) + count
                )

        # Collect resolved symbols
        for node in root_nodes:
            for flat_node in node.flatten():
                result.resolved_symbols[flat_node.symbol] = flat_node.component_name

        # Validate structure
        self._validate_result(result)

        # Cache result
        if use_cache:
            self._parse_cache[dsl_string] = result

        return result

    def _parse_tokens(
        self,
        tokens: List[DSLToken],
        pos: int,
        depth: int,
    ) -> Tuple[List[DSLNode], int]:
        """Recursively parse tokens into DSLNode tree."""
        nodes = []

        while pos < len(tokens):
            token = tokens[pos]

            # End of current level
            if token.type == "close":
                return nodes, pos + 1

            # Start of children (should attach to previous node)
            if token.type == "open":
                if nodes:
                    children, pos = self._parse_tokens(tokens, pos + 1, depth + 1)
                    nodes[-1].children = children
                    for child in children:
                        child.parent = nodes[-1]
                else:
                    # Orphan bracket - skip
                    pos += 1
                continue

            # Multiplier (attach to previous node)
            if token.type == "multiplier":
                if nodes:
                    nodes[-1].multiplier = int(token.value[1:])  # Skip the ×
                pos += 1
                continue

            # Symbol or component name
            if token.type in ("symbol", "component_name"):
                if token.type == "symbol":
                    symbol = token.value
                    component_name = self._reverse_mapping.get(symbol, symbol)
                else:
                    component_name = token.value
                    symbol = self._symbol_mapping.get(
                        component_name, component_name[0] if component_name else "?"
                    )

                node = DSLNode(
                    symbol=symbol,
                    component_name=component_name,
                    depth=depth,
                )
                nodes.append(node)
                pos += 1
                continue

            # Unknown token - skip
            pos += 1

        return nodes, pos

    def _collect_paths(self, node: DSLNode, paths: List[str]):
        """Collect component paths from node tree."""
        for _ in range(node.multiplier):
            paths.append(node.component_name)
        for child in node.children:
            self._collect_paths(child, paths)

    # =========================================================================
    # VALIDATION
    # =========================================================================

    def _validate_result(self, result: DSLParseResult):
        """Validate parsed result against component hierarchy."""
        for node in result.root_nodes:
            self._validate_node(node, None, result)

    def _validate_node(
        self,
        node: DSLNode,
        parent: Optional[DSLNode],
        result: DSLParseResult,
    ):
        """Validate a single node and its children."""
        # Check if symbol is known
        if (
            node.symbol not in self._all_symbols
            and node.component_name not in self._symbol_mapping
        ):
            result.issues.append(f"Unknown symbol/component: {node.symbol}")
            # Don't mark invalid - might still work

        # Check parent-child relationship
        if parent and self._relationships:
            parent_name = parent.component_name
            valid_children = self._relationships.get(parent_name, [])

            if node.component_name not in valid_children and valid_children:
                # Check for wrapper requirements
                wrapper_needed = self._get_required_wrapper(node.component_name)
                if wrapper_needed:
                    result.issues.append(
                        f"{node.component_name} should be wrapped in {wrapper_needed}"
                    )
                    wrapper_sym = self._symbol_mapping.get(
                        wrapper_needed, wrapper_needed
                    )
                    result.suggestions.append(
                        f"Use {wrapper_sym}[{node.symbol}] instead of {node.symbol}"
                    )
                    result.is_valid = False
                else:
                    result.issues.append(
                        f"{node.component_name} cannot be direct child of {parent_name}"
                    )
                    result.is_valid = False

        # Validate children recursively
        for child in node.children:
            self._validate_node(child, node, result)

    def _get_required_wrapper(self, component_name: str) -> Optional[str]:
        """Get the wrapper component needed for a component, if any."""
        wrappers = {
            "Button": "ButtonList",
            "Chip": "ChipList",
            "GridItem": "Grid",
            "Column": "Columns",
            "SelectionItem": "SelectionInput",
        }
        return wrappers.get(component_name)

    # =========================================================================
    # QDRANT QUERY GENERATION
    # =========================================================================

    def to_qdrant_queries(
        self,
        result: DSLParseResult,
        collection_name: str = "mcp_gchat_cards_v7",
        search_strategy: str = "auto",
    ) -> List[QdrantQuery]:
        """
        Generate Qdrant queries from a parsed DSL result.

        Generates queries for different vectors based on strategy:
        - 'components': Search by component identity (class name, structure)
        - 'relationships': Search by DSL notation in relationship text
        - 'inputs': Search by parameter values
        - 'auto': Generates queries for all relevant vectors

        Args:
            result: Parsed DSL result
            collection_name: Qdrant collection name
            search_strategy: 'components', 'relationships', 'inputs', or 'auto'

        Returns:
            List of QdrantQuery objects for execution
        """
        queries = []

        if not result.is_valid or not result.root_nodes:
            return queries

        if search_strategy in ("auto", "relationships"):
            # Query 1: Search by DSL notation in relationships vector
            # This finds instance_patterns with matching structure
            queries.append(
                QdrantQuery(
                    collection=collection_name,
                    vector_name="relationships",
                    query_text=result.dsl,  # Use original DSL notation
                    filters={"type": "instance_pattern"},
                    limit=10,
                )
            )

        if search_strategy in ("auto", "components"):
            # Query 2: Search by component identity
            # Find components by name/type
            root_name = result.root_nodes[0].component_name
            component_names = list(result.component_counts.keys())

            queries.append(
                QdrantQuery(
                    collection=collection_name,
                    vector_name="components",
                    query_text=f"{root_name} containing {' '.join(component_names[:5])}",
                    filters={"type": "class"},
                    limit=10,
                )
            )

        if search_strategy in ("auto", "inputs"):
            # Query 3: Build an expanded text query for inputs vector
            # This matches patterns by their content structure
            expanded = (
                result.root_nodes[0].to_expanded_notation() if result.root_nodes else ""
            )
            queries.append(
                QdrantQuery(
                    collection=collection_name,
                    vector_name="inputs",
                    query_text=expanded,
                    limit=10,
                )
            )

        return queries

    def build_qdrant_filter(
        self,
        result: DSLParseResult,
        additional_filters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Build a Qdrant filter from parsed DSL result.

        Creates filters that can be used with Qdrant search to narrow results
        to components matching the DSL structure.

        Args:
            result: Parsed DSL result
            additional_filters: Extra filters to merge

        Returns:
            Qdrant filter dict for use with search/scroll
        """
        must_conditions = []

        # Filter by component names present in the DSL
        if result.component_counts:
            # Match any of the component names
            component_names = list(result.component_counts.keys())
            if component_names:
                must_conditions.append(
                    {"key": "name", "match": {"any": component_names}}
                )

        # Filter by symbol if root is known
        if result.root_nodes:
            root_symbol = result.root_nodes[0].symbol
            must_conditions.append({"key": "symbol", "match": {"value": root_symbol}})

        # Merge additional filters
        if additional_filters:
            for key, value in additional_filters.items():
                must_conditions.append({"key": key, "match": {"value": value}})

        return {"must": must_conditions} if must_conditions else {}

    # =========================================================================
    # UTILITY METHODS
    # =========================================================================

    def extract_dsl_from_text(self, text: str) -> Optional[str]:
        """
        Extract DSL notation from a text string.

        Looks for patterns like:
        - "§[δ×3, Ƀ[ᵬ×2]] Server Status" → returns "§[δ×3, Ƀ[ᵬ×2]]"
        - "Build a Ƀ[ᵬ×4] Quick Actions card" → returns "Ƀ[ᵬ×4]"

        Args:
            text: Text that may contain DSL notation

        Returns:
            DSL string if found, None otherwise
        """
        if not text:
            return None

        text = text.strip()

        # Check if text starts with a known symbol
        first_char = text[0] if text else ""

        if first_char not in self._all_symbols:
            # Scan for first symbol in text
            for i, char in enumerate(text):
                if char in self._all_symbols:
                    text = text[i:]
                    first_char = char
                    break
            else:
                return None

        # Find the end of DSL structure (after matching brackets)
        bracket_count = 0
        dsl_end = 0
        in_dsl = False

        for i, char in enumerate(text):
            if char == "[":
                bracket_count += 1
                in_dsl = True
            elif char == "]":
                bracket_count -= 1
                if bracket_count == 0 and in_dsl:
                    dsl_end = i + 1
                    break
            elif not in_dsl and char in " \t\n":
                # End of simple symbol (no brackets)
                dsl_end = i
                break

        if dsl_end > 0:
            return text[:dsl_end]
        elif not in_dsl:
            # Single symbol without brackets
            return first_char

        return None

    def normalize_dsl(self, dsl_string: str) -> str:
        """
        Normalize a DSL string to canonical form.

        - Removes extra whitespace
        - Ensures consistent comma placement
        - Sorts children alphabetically (optional)

        Args:
            dsl_string: Input DSL string

        Returns:
            Normalized DSL string
        """
        result = self.parse(dsl_string)
        if not result.is_valid or not result.root_nodes:
            return dsl_string

        # Reconstruct from parsed structure
        return ", ".join(node.to_compact_dsl() for node in result.root_nodes)

    def expand_dsl(self, dsl_string: str) -> str:
        """
        Expand DSL to full component name notation.

        Args:
            dsl_string: Compact DSL (e.g., "§[δ, ᵬ×2]")

        Returns:
            Expanded notation (e.g., "Section[DecoratedText, Button×2]")
        """
        result = self.parse(dsl_string)
        if not result.is_valid or not result.root_nodes:
            return dsl_string

        return ", ".join(node.to_expanded_notation() for node in result.root_nodes)

    def compact_to_dsl(self, component_notation: str) -> str:
        """
        Convert component name notation to compact DSL.

        Args:
            component_notation: Full names (e.g., "Section[DecoratedText, Button×2]")

        Returns:
            Compact DSL (e.g., "§[δ, ᵬ×2]")
        """
        result = self.parse(component_notation)
        if not result.is_valid or not result.root_nodes:
            return component_notation

        return ", ".join(node.to_compact_dsl() for node in result.root_nodes)

    # =========================================================================
    # CONTENT DSL PARSING
    # =========================================================================

    def parse_content_dsl(self, text: str) -> ContentDSLResult:
        """
        Parse Content DSL text into structured content blocks.

        Content DSL format:
            δ 'Status: Online' success bold
            ᵬ Click Here https://example.com
              Continue on next line
            § Header Text

        Args:
            text: Multi-line Content DSL text

        Returns:
            ContentDSLResult with parsed blocks
        """
        result = ContentDSLResult(raw=text)
        lines = text.strip().split("\n")

        current_block: Optional[ContentBlock] = None

        for line_num, line in enumerate(lines, 1):
            # Check for continuation (indented line)
            is_continuation = (
                line.startswith(("  ", "\t")) and current_block is not None
            )

            if is_continuation:
                # Parse continuation line (content only, no symbol)
                content = line.strip()
                cont_line = ContentLine(
                    symbol=current_block.primary.symbol,
                    component_name=current_block.primary.component_name,
                    content=content,
                    line_number=line_num,
                    is_continuation=True,
                )
                current_block.continuations.append(cont_line)
            else:
                # Save previous block if exists
                if current_block:
                    result.blocks.append(current_block)

                # Parse new primary line
                parsed = self._parse_content_line(line, line_num)
                if parsed:
                    current_block = ContentBlock(primary=parsed)
                elif line.strip():  # Non-empty but unparseable
                    result.issues.append(
                        f"Line {line_num}: Could not parse '{line.strip()}'"
                    )
                    current_block = None
                else:
                    current_block = None

        # Don't forget the last block
        if current_block:
            result.blocks.append(current_block)

        return result

    def _parse_content_line(
        self, line: str, line_num: int = 0
    ) -> Optional[ContentLine]:
        """
        Parse a single Content DSL line.

        Format: SYMBOL [CONTENT] [MODIFIERS...] [URL]

        Content can be:
        - Quoted: δ 'Hello World'
        - Unquoted: δ Hello World (runs until modifiers/URL)

        Args:
            line: Single line of Content DSL
            line_num: Line number for error reporting

        Returns:
            ContentLine or None if unparseable
        """
        line = line.strip()
        if not line:
            return None

        # First character should be a symbol
        first_char = line[0]
        if first_char not in self._all_symbols:
            return None

        symbol = first_char
        component_name = self._reverse_mapping.get(symbol, symbol)
        rest = line[1:].strip()

        # Parse content (quoted or unquoted)
        content, remaining = self._extract_content(rest)

        # Parse remaining for modifiers and URL
        modifiers, url = self._parse_modifiers_and_url(remaining)

        return ContentLine(
            symbol=symbol,
            component_name=component_name,
            content=content,
            modifiers=modifiers,
            url=url,
            line_number=line_num,
        )

    def _extract_content(self, text: str) -> Tuple[str, str]:
        """
        Extract content from text, handling quoted strings.

        Args:
            text: Text after the symbol

        Returns:
            Tuple of (content, remaining_text)
        """
        text = text.strip()
        if not text:
            return "", ""

        # Quoted content
        if text[0] in ('"', "'"):
            quote_char = text[0]
            end_pos = text.find(quote_char, 1)
            if end_pos > 0:
                content = text[1:end_pos]
                remaining = text[end_pos + 1 :].strip()
                return content, remaining
            else:
                # Unclosed quote - take everything
                return text[1:], ""

        # Unquoted content - parse until we hit a known modifier or URL
        words = text.split()
        content_words = []
        remaining_words = []
        found_modifier = False

        for word in words:
            if found_modifier:
                remaining_words.append(word)
            elif self._is_modifier_or_url(word):
                found_modifier = True
                remaining_words.append(word)
            else:
                content_words.append(word)

        content = " ".join(content_words)
        remaining = " ".join(remaining_words)
        return content, remaining

    def _is_modifier_or_url(self, word: str) -> bool:
        """Check if a word is a style modifier or URL."""
        word_lower = word.lower()

        # Check against known modifiers
        if word_lower in STYLE_MODIFIERS:
            return True

        # Check for URL patterns
        if word.startswith(("http://", "https://", "www.")):
            return True

        return False

    def _parse_modifiers_and_url(
        self, text: str
    ) -> Tuple[List[StyleModifier], Optional[str]]:
        """
        Parse style modifiers and URL from remaining text.

        Args:
            text: Text after content extraction

        Returns:
            Tuple of (modifiers list, url or None)
        """
        modifiers = []
        url = None

        words = text.strip().split()

        for word in words:
            # Check for URL
            if word.startswith(("http://", "https://", "www.")):
                url = word if word.startswith("http") else f"https://{word}"
                continue

            # Check for modifier
            word_lower = word.lower()
            if word_lower in STYLE_MODIFIERS:
                filter_name, filter_args = STYLE_MODIFIERS[word_lower]
                modifiers.append(
                    StyleModifier(
                        name=word_lower,
                        jinja_filter=filter_name,
                        jinja_args=filter_args,
                    )
                )

        return modifiers, url

    def content_to_jinja(self, content_result: ContentDSLResult) -> List[str]:
        """
        Convert Content DSL result to list of Jinja expressions.

        Args:
            content_result: Parsed Content DSL result

        Returns:
            List of Jinja template expressions
        """
        return content_result.to_jinja_list()

    def content_to_component_params(
        self,
        content_result: ContentDSLResult,
    ) -> List[Dict[str, Any]]:
        """
        Convert Content DSL to component parameter dictionaries.

        Useful for directly building card components.

        Args:
            content_result: Parsed Content DSL result

        Returns:
            List of dicts with component params (text, url, modifiers)
        """
        params = []

        for block in content_result.blocks:
            param = {
                "component": block.primary.component_name,
                "text": block.full_content,
                "jinja_text": block.to_jinja(),
            }

            if block.primary.url:
                param["url"] = block.primary.url

            if block.primary.modifiers:
                param["styles"] = [m.name for m in block.primary.modifiers]

            params.append(param)

        return params


# =============================================================================
# STANDALONE FUNCTIONS
# =============================================================================


def parse_dsl_to_qdrant_query(
    dsl_string: str,
    symbol_mapping: Dict[str, str],
    collection_name: str = "mcp_gchat_cards_v7",
) -> List[Dict[str, Any]]:
    """
    Standalone function to parse DSL and generate Qdrant queries.

    Convenience function that creates a parser and generates queries.

    Args:
        dsl_string: DSL notation string
        symbol_mapping: Component name → symbol mapping
        collection_name: Qdrant collection name

    Returns:
        List of query dicts ready for execution
    """
    reverse_mapping = {v: k for k, v in symbol_mapping.items()}

    parser = DSLParser(
        symbol_mapping=symbol_mapping,
        reverse_mapping=reverse_mapping,
    )

    result = parser.parse(dsl_string)
    queries = parser.to_qdrant_queries(result, collection_name)

    return [q.to_dict() for q in queries]


def extract_dsl_from_description(
    description: str,
    symbol_mapping: Dict[str, str],
) -> Tuple[Optional[str], str]:
    """
    Extract DSL notation from a description string.

    Returns both the DSL and the remaining content.

    Args:
        description: Text that may contain DSL notation
        symbol_mapping: Component name → symbol mapping

    Returns:
        Tuple of (dsl_string or None, remaining_content)
    """
    reverse_mapping = {v: k for k, v in symbol_mapping.items()}

    parser = DSLParser(
        symbol_mapping=symbol_mapping,
        reverse_mapping=reverse_mapping,
    )

    dsl = parser.extract_dsl_from_text(description)

    if dsl:
        # Get remaining content after DSL
        remaining = description[len(dsl) :].strip()
        return dsl, remaining

    return None, description


def validate_dsl_structure(
    dsl_string: str,
    symbol_mapping: Dict[str, str],
    relationships: Dict[str, List[str]],
) -> Tuple[bool, List[str]]:
    """
    Validate a DSL structure against component hierarchy.

    Args:
        dsl_string: DSL notation string
        symbol_mapping: Component name → symbol mapping
        relationships: Parent → [children] relationship mapping

    Returns:
        Tuple of (is_valid, list of issues)
    """
    reverse_mapping = {v: k for k, v in symbol_mapping.items()}

    parser = DSLParser(
        symbol_mapping=symbol_mapping,
        reverse_mapping=reverse_mapping,
        relationships=relationships,
    )

    result = parser.parse(dsl_string)
    return result.is_valid, result.issues


# =============================================================================
# CONTENT DSL STANDALONE FUNCTIONS
# =============================================================================


def parse_content_dsl(
    text: str,
    symbol_mapping: Dict[str, str],
) -> ContentDSLResult:
    """
    Parse Content DSL text using provided symbol mapping.

    Content DSL format:
        δ 'Status: Online' success bold
        ᵬ Click Here https://example.com

    Args:
        text: Multi-line Content DSL text
        symbol_mapping: Component name → symbol mapping

    Returns:
        ContentDSLResult with parsed blocks
    """
    reverse_mapping = {v: k for k, v in symbol_mapping.items()}

    parser = DSLParser(
        symbol_mapping=symbol_mapping,
        reverse_mapping=reverse_mapping,
    )

    return parser.parse_content_dsl(text)


def content_dsl_to_jinja(
    text: str,
    symbol_mapping: Dict[str, str],
) -> List[str]:
    """
    Convert Content DSL text directly to Jinja expressions.

    Args:
        text: Content DSL text
        symbol_mapping: Component name → symbol mapping

    Returns:
        List of Jinja template expressions
    """
    result = parse_content_dsl(text, symbol_mapping)
    return result.to_jinja_list()


def get_style_modifiers() -> Dict[str, Tuple[str, Optional[str]]]:
    """
    Get the available style modifiers.

    Returns:
        Dict mapping modifier names to (jinja_filter, args) tuples
    """
    return STYLE_MODIFIERS.copy()


def add_style_modifier(
    name: str,
    jinja_filter: str,
    jinja_args: Optional[str] = None,
):
    """
    Add a custom style modifier.

    Args:
        name: Modifier name (e.g., "brand_color")
        jinja_filter: Jinja filter name (e.g., "color")
        jinja_args: Optional filter arguments (e.g., "'#FF5733'")
    """
    STYLE_MODIFIERS[name.lower()] = (jinja_filter, jinja_args)


# =============================================================================
# INTEGRATION WITH MODULE WRAPPER
# =============================================================================


def create_parser_from_wrapper(wrapper: "ModuleWrapper") -> DSLParser:
    """
    Create a DSL parser from a ModuleWrapper instance.

    Args:
        wrapper: Initialized ModuleWrapper

    Returns:
        DSLParser configured with wrapper's mappings
    """
    return DSLParser(wrapper=wrapper)
