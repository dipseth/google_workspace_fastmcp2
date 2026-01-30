"""
DAG-Based Structure Generator for Google Chat Cards

Uses the ModuleWrapper's NetworkX DAG to generate random but VALID
card structures. Unlike hardcoded generators, this guarantees:

1. All component nesting is valid (parent can actually contain child)
2. Structures can be generated from any starting component
3. DSL notation is automatically produced
4. Structures are validated against the real component hierarchy

Usage:
    from gchat.testing.dag_structure_generator import DAGStructureGenerator

    gen = DAGStructureGenerator()

    # Generate random valid structure
    result = gen.generate_random_structure(root="Section", max_depth=3)
    print(result["dsl"])  # §[δ, Ƀ[ᵬ×2]]
    print(result["components"])  # ['Section', 'DecoratedText', 'ButtonList', 'Button']

    # Generate card JSON from structure
    card = gen.structure_to_card(result)

    # Generate multiple random cards
    cards = gen.generate_random_cards(count=5)
"""

import random
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

from config.enhanced_logging import setup_logger

logger = setup_logger()


# =============================================================================
# PARAMETER SCHEMA EXTRACTION
# =============================================================================

@dataclass
class FieldInfo:
    """Information about a component field/parameter."""
    name: str
    field_type: str
    has_default: bool
    default_value: Any
    is_required: bool
    is_optional: bool  # Optional[X] type
    generated_value: Any = None
    used_default: bool = True


@dataclass
class ComponentSchema:
    """Schema for a component including all its parameters."""
    name: str
    fields: Dict[str, FieldInfo] = field(default_factory=dict)
    json_key: str = ""  # e.g., "decoratedText" for DecoratedText


def extract_component_schema(component_class: Any) -> Optional[ComponentSchema]:
    """
    Extract field schema from a component class.

    Args:
        component_class: The dataclass component (e.g., DecoratedText)

    Returns:
        ComponentSchema with all field information
    """
    from dataclasses import MISSING

    if not hasattr(component_class, '__dataclass_fields__'):
        return None

    name = component_class.__name__
    schema = ComponentSchema(name=name)

    # Determine JSON key (camelCase of class name)
    # DecoratedText -> decoratedText
    json_key = name[0].lower() + name[1:]
    schema.json_key = json_key

    for field_name, field_obj in component_class.__dataclass_fields__.items():
        # Skip private fields
        if field_name.startswith('_'):
            continue

        # Determine type
        type_str = getattr(field_obj.type, '__name__', str(field_obj.type))
        is_optional = 'Optional' in str(field_obj.type) or type_str == 'Optional'

        # Determine default
        if field_obj.default is not MISSING:
            has_default = True
            default_value = field_obj.default
        elif field_obj.default_factory is not MISSING:
            has_default = True
            default_value = "factory()"
        else:
            has_default = False
            default_value = None

        is_required = not has_default and not is_optional

        schema.fields[field_name] = FieldInfo(
            name=field_name,
            field_type=type_str,
            has_default=has_default,
            default_value=default_value,
            is_required=is_required,
            is_optional=is_optional,
        )

    return schema


# =============================================================================
# PARAMETER VALUE GENERATORS
# =============================================================================

# Import material icons for rich test data
try:
    from gchat.material_icons import (
        MATERIAL_ICONS,
        is_valid_icon,
        create_material_icon,
        SEMANTIC_ICONS,
    )
    _MATERIAL_ICONS_AVAILABLE = True
except ImportError:
    MATERIAL_ICONS = frozenset()
    SEMANTIC_ICONS = {}
    _MATERIAL_ICONS_AVAILABLE = False

    def is_valid_icon(name: str) -> bool:
        return False

    def create_material_icon(name: str, fill: bool = False) -> dict:
        return {"materialIcon": {"name": name}}

# Curated list of useful material icons for testing
# These are common, visually distinct icons that render well
CURATED_MATERIAL_ICONS = [
    "star", "favorite", "check_circle", "home", "settings",
    "person", "email", "phone", "calendar_today", "schedule",
    "notifications", "shopping_cart", "search", "edit", "delete",
    "add", "remove", "arrow_forward", "arrow_back", "refresh",
    "cloud", "folder", "attach_file", "link", "share",
    "thumb_up", "thumb_down", "bookmark", "flag", "info",
    "warning", "error", "help", "lightbulb", "verified",
]

# Sample values by type for generating test data
SAMPLE_VALUES_BY_TYPE = {
    "str": [
        "Test text", "Sample content", "Hello world",
        "Generated value", "Lorem ipsum", "Quick test",
        "Status update", "Action required", "Review pending",
    ],
    "bool": [True, False],
    "int": [0, 1, 5, 10, 42, 100],
    "float": [0.0, 0.5, 1.0, 3.14],
    "HorizontalAlignment": ["START", "CENTER", "END"],
    "VerticalAlignment": ["TOP", "CENTER", "BOTTOM"],
    "ImageType": ["SQUARE", "CIRCLE"],
    "SelectionType": ["CHECK_BOX", "RADIO_BUTTON", "SWITCH", "DROPDOWN"],
    "BorderType": ["NO_BORDER", "STROKE"],
    "LoadIndicator": ["SPINNER", "NONE"],
    "ResponseType": ["TYPE_UNSPECIFIED", "NEW_MESSAGE", "UPDATE_MESSAGE"],
    "OpenAs": ["FULL_SIZE", "OVERLAY"],
    "OnClose": ["NOTHING", "RELOAD"],
}

# Known icons (legacy format for knownIcon field)
KNOWN_ICONS = [
    "STAR", "BOOKMARK", "DESCRIPTION", "EMAIL", "CLOCK",
    "CONFIRMATION_NUMBER", "NOTIFICATIONS", "PERSON", "PHONE",
    "FLIGHT_ARRIVAL", "FLIGHT_DEPARTURE", "HOTEL", "INVITE",
]

# Sample images for testing (define here for use in COMPONENT_DEFAULTS)
PARAM_SAMPLE_IMAGES = [
    "https://picsum.photos/id/1/200/200",
    "https://picsum.photos/id/20/200/200",
    "https://picsum.photos/id/42/200/200",
    "https://picsum.photos/id/60/200/200",
]

# Component-specific default values (based on typical usage)
COMPONENT_DEFAULTS = {
    "DecoratedText": {
        "text": ["Status update", "Item details", "Quick info", "Notification"],
        "top_label": ["Label", "Category", "Type", "Status"],
        "bottom_label": ["Updated recently", "Click for details", "More info"],
        "wrap_text": [True],
    },
    "TextParagraph": {
        "text": [
            "This is a paragraph of text content.",
            "Welcome to the generated card test.",
            "Sample paragraph for testing purposes.",
        ],
    },
    "Button": {
        "text": ["Submit", "Cancel", "Confirm", "Next", "Back", "View", "Edit", "Delete"],
    },
    "Image": {
        "image_url": PARAM_SAMPLE_IMAGES,
        "alt_text": ["Test image", "Sample photo", "Generated image"],
    },
    "SelectionInput": {
        "label": ["Select option", "Choose item", "Pick one"],
        "name": ["selection_1", "dropdown_1", "choice_1"],
    },
    "DateTimePicker": {
        "label": ["Select date", "Choose time", "Pick date/time"],
        "name": ["datetime_1", "date_picker_1"],
    },
    "Grid": {
        "title": ["Grid View", "Items", "Gallery", "Options"],
        "column_count": [2, 3, 4],
    },
    "Chip": {
        "label": ["Tag 1", "Category", "Filter", "Option"],
    },
}


def generate_value_for_field(
    field_info: FieldInfo,
    component_name: Optional[str] = None,
    use_material_icons: bool = True,
) -> Tuple[Any, bool]:
    """
    Generate a test value for a field.

    Args:
        field_info: Field information
        component_name: Name of the component (for component-specific defaults)
        use_material_icons: Whether to use material design icons

    Returns:
        Tuple of (generated_value, used_default)
    """
    field_type = field_info.field_type
    field_name = field_info.name

    # Check for component-specific defaults first
    if component_name and component_name in COMPONENT_DEFAULTS:
        comp_defaults = COMPONENT_DEFAULTS[component_name]
        if field_name in comp_defaults:
            return random.choice(comp_defaults[field_name]), False

    # Decide whether to use default (30% chance if available)
    if field_info.has_default and random.random() < 0.3:
        return field_info.default_value, True

    # Generate based on type
    if field_type in SAMPLE_VALUES_BY_TYPE:
        return random.choice(SAMPLE_VALUES_BY_TYPE[field_type]), False

    # String fields
    if "str" in field_type.lower():
        return random.choice(SAMPLE_VALUES_BY_TYPE["str"]), False

    # Boolean fields
    if "bool" in field_type.lower():
        return random.choice([True, False]), False

    # Integer fields
    if "int" in field_type.lower():
        return random.randint(1, 10), False

    # Icon fields - use material icons if available
    if "Icon" in field_type or "icon" in field_name.lower():
        if use_material_icons and _MATERIAL_ICONS_AVAILABLE:
            # Use materialIcon format with curated icons via helper
            icon_name = random.choice(CURATED_MATERIAL_ICONS)
            # create_material_icon returns {"materialIcon": {"name": "..."}}
            return create_material_icon(icon_name), False
        else:
            # Fallback to knownIcon format
            return {"knownIcon": random.choice(KNOWN_ICONS)}, False

    # List fields
    if "List" in field_type:
        return [], False  # Empty list as default

    # Optional fields
    if field_info.is_optional:
        # 50% chance to provide value for optional fields
        if random.random() < 0.5:
            return None, True

    # Default: use the default value if available
    if field_info.has_default:
        return field_info.default_value, True

    return None, True


def generate_component_test_values(
    component_name: str,
    schema: Optional[ComponentSchema] = None,
    fill_all: bool = False,
) -> Dict[str, Any]:
    """
    Generate a complete set of test values for a component.

    Args:
        component_name: Name of the component
        schema: Optional pre-extracted schema
        fill_all: If True, fill all fields; otherwise use probabilistic filling

    Returns:
        Dict of field name to generated value
    """
    if schema is None:
        return {}

    values = {}
    for field_name, field_info in schema.fields.items():
        if fill_all or field_info.is_required or random.random() < 0.5:
            value, _ = generate_value_for_field(field_info, component_name)
            if value is not None:
                values[field_name] = value

    return values


# =============================================================================
# CONFIGURATION
# =============================================================================

@dataclass
class DAGGeneratorConfig:
    """Configuration for DAG-based structure generation."""

    # Structure constraints
    max_depth: int = 3
    max_children_per_node: int = 4
    min_children_per_node: int = 1

    # Component preferences (boost probability)
    preferred_components: List[str] = field(default_factory=lambda: [
        "DecoratedText", "ButtonList", "Button", "TextParagraph"
    ])

    # Components to avoid (reduce probability)
    avoid_components: List[str] = field(default_factory=lambda: [
        "Carousel", "CarouselCard", "NestedWidget",  # Complex carousel
        "Columns", "Column",  # Complex multi-column
        "CollapseControl",  # Requires special handling
    ])

    # Required components (must appear somewhere in structure)
    required_components: List[str] = field(default_factory=list)

    # Probability weights
    prefer_weight: float = 2.0  # Multiplier for preferred components
    avoid_weight: float = 0.2   # Multiplier for avoided components

    # Content generation
    include_content: bool = True
    webhook_url: Optional[str] = None
    test_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])


@dataclass
class GeneratedStructure:
    """Result of structure generation."""

    root: str
    components: List[str]
    dsl: str
    tree: Dict[str, Any]
    depth: int
    is_valid: bool
    validation_issues: List[str] = field(default_factory=list)


# =============================================================================
# WIDGET HIERARCHY (Canonical containment rules)
# =============================================================================

# This defines what containers can hold what children
# This is the SSoT for valid card structures
# Matches CUSTOM_CHAT_API_RELATIONSHIPS from card_framework_wrapper.py
WIDGET_HIERARCHY = {
    # Card-level containers
    "Card": ["Section", "CardHeader", "CardFixedFooter", "Carousel"],
    "CardHeader": [],  # Just displays title/subtitle
    "CardFixedFooter": ["Button"],  # primaryButton, secondaryButton

    # Section is the main container for widgets
    "Section": [
        "DecoratedText", "TextParagraph", "Image", "Divider",
        "ButtonList", "Grid", "Columns", "SelectionInput",
        "DateTimePicker", "ChipList", "CollapseControl"
    ],

    # CollapseControl for expandable sections
    "CollapseControl": ["Button"],  # expandButton, collapseButton

    # Widget internals
    "DecoratedText": ["Icon", "Button", "SwitchControl"],
    "ButtonList": ["Button"],
    "Button": ["Icon"],
    "Grid": ["GridItem"],
    "GridItem": ["Image"],
    "Columns": ["Column"],
    "Column": ["DecoratedText", "TextParagraph", "Image", "ButtonList"],
    "ChipList": ["Chip"],
    "Chip": ["Icon"],

    # Carousel (Custom Google Chat API component)
    # Note: NestedWidget only supports textParagraph, buttonList, image (NOT decoratedText!)
    "Carousel": ["CarouselCard"],
    "CarouselCard": ["NestedWidget"],
    "NestedWidget": ["TextParagraph", "ButtonList", "Image"],  # Limited set per API docs
}

# Leaf components (no children)
LEAF_COMPONENTS = {
    "TextParagraph", "Image", "Divider", "Icon",
    "SwitchControl", "SelectionInput", "DateTimePicker",
    "Widget", "CardHeader"
}

# Internal types that are NOT renderable widgets (exclude from generation)
# These come from type annotations but aren't actual widget containers
INTERNAL_TYPES = {
    # Enums and types
    "Type", "Color", "OnClick", "Action", "OverflowMenu",
    "HorizontalAlignment", "VerticalAlignment", "HorizontalSizeStyle",
    "ControlType", "DisplayStyle", "LoadIndicator", "MatchedUrl",
    "ResponseType", "Interaction", "BorderType", "ImageType",
    "GridItemLayout", "Layout", "DividerStyle", "WrapStyle",
    "OpenAs", "OnClose", "UpdatedWidget", "SelectionType",
    "PlatformDataSource", "CommonDataSource",
    # Internal structures
    "AttachmentDataRef", "CustomEmojiPayload", "SuggestionItem",
    "CollapseControl", "ImageComponent",
}


# =============================================================================
# SAMPLE CONTENT POOLS
# =============================================================================

SAMPLE_TEXTS = [
    "Status update available",
    "Task completed successfully",
    "New notification received",
    "Action required",
    "Review pending items",
    "System check passed",
]

SAMPLE_BUTTON_LABELS = [
    "View Details", "Confirm", "Cancel", "Submit",
    "Next", "Previous", "Approve", "Reject",
]

SAMPLE_ICONS = [
    "STAR", "BOOKMARK", "DESCRIPTION", "EMAIL",
    "CLOCK", "CONFIRMATION_NUMBER", "NOTIFICATIONS",
]

SAMPLE_IMAGES = [
    "https://picsum.photos/id/1/200/200",
    "https://picsum.photos/id/20/200/200",
    "https://picsum.photos/id/42/200/200",
]


# =============================================================================
# DAG STRUCTURE GENERATOR
# =============================================================================

@dataclass
class ParameterizedNode:
    """A node in the structure tree with parameter values."""
    name: str
    symbol: str
    depth: int
    children: List["ParameterizedNode"] = field(default_factory=list)
    schema: Optional[ComponentSchema] = None
    parameters: Dict[str, FieldInfo] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "name": self.name,
            "symbol": self.symbol,
            "depth": self.depth,
            "children": [c.to_dict() for c in self.children],
            "parameters": {
                name: {
                    "type": f.field_type,
                    "value": f.generated_value,
                    "used_default": f.used_default,
                    "is_required": f.is_required,
                }
                for name, f in self.parameters.items()
            } if self.parameters else {},
        }


@dataclass
class ParameterizedStructure:
    """Generated structure with full parameter information."""
    root: str
    components: List[str]
    dsl: str
    tree: ParameterizedNode
    depth: int
    is_valid: bool
    validation_issues: List[str] = field(default_factory=list)
    total_parameters: int = 0
    parameters_with_values: int = 0
    parameters_using_defaults: int = 0


class DAGStructureGenerator:
    """
    Generates random valid card structures using the ModuleWrapper's DAG.

    Key features:
    - Uses actual component containment rules from the DAG
    - Generates valid DSL notation
    - Can target specific component combinations
    - Validates all generated structures
    - Can generate parameter values for each component field
    """

    def __init__(self, config: Optional[DAGGeneratorConfig] = None):
        self.config = config or DAGGeneratorConfig()
        self._wrapper = None
        self._graph_built = False
        self._schema_cache: Dict[str, ComponentSchema] = {}

    def _get_wrapper(self):
        """Get ModuleWrapper singleton with graph built."""
        if self._wrapper is None:
            from gchat.card_framework_wrapper import get_card_framework_wrapper
            self._wrapper = get_card_framework_wrapper()

        # Ensure graph is built with widget hierarchy
        if not self._graph_built:
            self._wrapper.build_relationship_graph()
            self._wrapper.add_relationships_to_graph(
                WIDGET_HIERARCHY,
                edge_type="widget_contains"
            )
            self._graph_built = True

        return self._wrapper

    # =========================================================================
    # STRUCTURE GENERATION
    # =========================================================================

    def get_valid_children(self, component: str) -> List[str]:
        """Get list of components that can be direct children of the given component."""
        # Use ONLY the canonical hierarchy - don't include DAG type annotations
        # The DAG includes internal types (OnClick, Color, etc.) that aren't widgets
        if component in WIDGET_HIERARCHY:
            children = WIDGET_HIERARCHY[component]
        else:
            # Fallback to DAG for components not in our hierarchy
            wrapper = self._get_wrapper()
            children = wrapper.get_children(component)

        # Filter out internal types that aren't renderable widgets
        return [c for c in children if c not in INTERNAL_TYPES]

    def is_leaf(self, component: str) -> bool:
        """Check if component is a leaf (has no valid children)."""
        if component in LEAF_COMPONENTS:
            return True
        return len(self.get_valid_children(component)) == 0

    def get_component_schema(self, component_name: str) -> Optional[ComponentSchema]:
        """
        Get the parameter schema for a component.

        Args:
            component_name: Name of the component (e.g., "DecoratedText")

        Returns:
            ComponentSchema with field information, or None if not found
        """
        # Check cache first
        if component_name in self._schema_cache:
            return self._schema_cache[component_name]

        wrapper = self._get_wrapper()

        # Find the component class
        for path, comp in wrapper.components.items():
            if comp.name == component_name:
                cls = comp.obj
                if cls:
                    schema = extract_component_schema(cls)
                    if schema:
                        self._schema_cache[component_name] = schema
                        return schema
                break

        return None

    def generate_parameters_for_component(
        self,
        component_name: str,
        fill_required: bool = True,
        fill_optional_probability: float = 0.3,
    ) -> Dict[str, FieldInfo]:
        """
        Generate parameter values for a component.

        Args:
            component_name: Name of the component
            fill_required: Always fill required fields
            fill_optional_probability: Probability of filling optional fields

        Returns:
            Dict of field name to FieldInfo with generated values
        """
        schema = self.get_component_schema(component_name)
        if not schema:
            return {}

        parameters = {}
        for field_name, field_info in schema.fields.items():
            # Copy the field info
            param = FieldInfo(
                name=field_info.name,
                field_type=field_info.field_type,
                has_default=field_info.has_default,
                default_value=field_info.default_value,
                is_required=field_info.is_required,
                is_optional=field_info.is_optional,
            )

            # Decide whether to generate a value
            should_fill = (
                (fill_required and param.is_required) or
                (param.is_optional and random.random() < fill_optional_probability)
            )

            if should_fill:
                value, used_default = generate_value_for_field(param, component_name)
                param.generated_value = value
                param.used_default = used_default
            else:
                param.generated_value = param.default_value
                param.used_default = True

            parameters[field_name] = param

        return parameters

    def select_children(
        self,
        parent: str,
        available: List[str],
        required: Optional[Set[str]] = None,
    ) -> List[str]:
        """
        Select children for a parent component using weighted random selection.

        Args:
            parent: Parent component name
            available: List of valid child components
            required: Components that must be included if possible

        Returns:
            List of selected child component names
        """
        if not available:
            return []

        required = required or set()
        config = self.config

        # Build weighted list
        weighted = []
        for comp in available:
            weight = 1.0

            # Apply preference weights
            if comp in config.preferred_components:
                weight *= config.prefer_weight
            if comp in config.avoid_components:
                weight *= config.avoid_weight
            if comp in required:
                weight *= 3.0  # Strong boost for required

            weighted.append((comp, weight))

        # Determine number of children
        num_children = random.randint(
            config.min_children_per_node,
            min(config.max_children_per_node, len(available))
        )

        # Weighted selection without replacement
        selected = []
        remaining = weighted.copy()

        # First, try to include required components
        for comp in list(required):
            matching = [w for w in remaining if w[0] == comp]
            if matching:
                selected.append(matching[0][0])
                remaining = [w for w in remaining if w[0] != comp]
                required.discard(comp)

        # Then fill remaining slots with weighted random
        while len(selected) < num_children and remaining:
            total = sum(w for _, w in remaining)
            if total == 0:
                break

            r = random.uniform(0, total)
            cumulative = 0
            for i, (comp, weight) in enumerate(remaining):
                cumulative += weight
                if r <= cumulative:
                    selected.append(comp)
                    remaining.pop(i)
                    break

        return selected

    def generate_tree(
        self,
        root: str,
        depth: int = 0,
        required: Optional[Set[str]] = None,
    ) -> Dict[str, Any]:
        """
        Recursively generate a valid component tree.

        Args:
            root: Root component to start from
            depth: Current depth (for limiting recursion)
            required: Components that should appear somewhere in the tree

        Returns:
            Tree dict with 'name', 'children', 'symbol', 'depth'
        """
        wrapper = self._get_wrapper()
        required = required or set()

        # Get symbol for this component
        symbol = wrapper.symbol_mapping.get(root, root[0])

        node = {
            "name": root,
            "symbol": symbol,
            "depth": depth,
            "children": [],
        }

        # Check if we should stop
        if depth >= self.config.max_depth or self.is_leaf(root):
            return node

        # Get valid children
        valid_children = self.get_valid_children(root)
        if not valid_children:
            return node

        # Select children (pass down required components)
        selected = self.select_children(root, valid_children, required)

        # Recursively generate child subtrees
        remaining_required = required.copy()
        for child_name in selected:
            remaining_required.discard(child_name)
            child_node = self.generate_tree(
                child_name,
                depth + 1,
                remaining_required,
            )
            node["children"].append(child_node)

        return node

    def generate_parameterized_tree(
        self,
        root: str,
        depth: int = 0,
        required: Optional[Set[str]] = None,
        fill_optional_probability: float = 0.3,
    ) -> ParameterizedNode:
        """
        Generate a tree with parameter values for each component.

        Args:
            root: Root component to start from
            depth: Current depth
            required: Required components
            fill_optional_probability: Probability of filling optional fields

        Returns:
            ParameterizedNode with parameters filled in
        """
        wrapper = self._get_wrapper()
        required = required or set()

        # Get symbol
        symbol = wrapper.symbol_mapping.get(root, root[0])

        # Get schema and generate parameters
        schema = self.get_component_schema(root)
        parameters = self.generate_parameters_for_component(
            root,
            fill_required=True,
            fill_optional_probability=fill_optional_probability,
        )

        node = ParameterizedNode(
            name=root,
            symbol=symbol,
            depth=depth,
            children=[],
            schema=schema,
            parameters=parameters,
        )

        # Check if we should stop
        if depth >= self.config.max_depth or self.is_leaf(root):
            return node

        # Get valid children
        valid_children = self.get_valid_children(root)
        if not valid_children:
            return node

        # Select children
        selected = self.select_children(root, valid_children, required)

        # Recursively generate child subtrees
        remaining_required = required.copy()
        for child_name in selected:
            remaining_required.discard(child_name)
            child_node = self.generate_parameterized_tree(
                child_name,
                depth + 1,
                remaining_required,
                fill_optional_probability,
            )
            node.children.append(child_node)

        return node

    def generate_parameterized_structure(
        self,
        root: str = "Section",
        required_components: Optional[List[str]] = None,
        fill_optional_probability: float = 0.3,
    ) -> ParameterizedStructure:
        """
        Generate a structure with full parameter information.

        Args:
            root: Root component
            required_components: Required components
            fill_optional_probability: Probability of filling optional fields

        Returns:
            ParameterizedStructure with parameter details
        """
        required = set(required_components or [])

        # Generate parameterized tree
        tree = self.generate_parameterized_tree(
            root,
            depth=0,
            required=required,
            fill_optional_probability=fill_optional_probability,
        )

        # Convert to DSL (using dict format for compatibility)
        def tree_to_dict(node: ParameterizedNode) -> Dict[str, Any]:
            return {
                "name": node.name,
                "symbol": node.symbol,
                "depth": node.depth,
                "children": [tree_to_dict(c) for c in node.children],
            }

        dsl = self.tree_to_dsl(tree_to_dict(tree))

        # Collect component list and parameter stats
        components = []
        total_params = 0
        params_with_values = 0
        params_using_defaults = 0

        def collect_stats(node: ParameterizedNode):
            nonlocal total_params, params_with_values, params_using_defaults
            components.append(node.name)
            for field_info in node.parameters.values():
                total_params += 1
                if field_info.generated_value is not None:
                    params_with_values += 1
                if field_info.used_default:
                    params_using_defaults += 1
            for child in node.children:
                collect_stats(child)

        collect_stats(tree)

        # Calculate depth
        def calc_depth(node: ParameterizedNode) -> int:
            if not node.children:
                return 1
            return 1 + max(calc_depth(c) for c in node.children)

        depth = calc_depth(tree)

        return ParameterizedStructure(
            root=root,
            components=components,
            dsl=dsl,
            tree=tree,
            depth=depth,
            is_valid=True,
            total_parameters=total_params,
            parameters_with_values=params_with_values,
            parameters_using_defaults=params_using_defaults,
        )

    def tree_to_dsl(self, tree: Dict[str, Any]) -> str:
        """
        Convert a component tree to DSL notation.

        Args:
            tree: Tree dict from generate_tree()

        Returns:
            DSL string like "§[δ, Ƀ[ᵬ×2]]"
        """
        symbol = tree["symbol"]
        children = tree.get("children", [])

        if not children:
            return symbol

        # Group consecutive identical children for ×N notation
        groups = []
        current_group = None
        current_count = 0

        for child in children:
            child_dsl = self.tree_to_dsl(child)
            if child_dsl == current_group:
                current_count += 1
            else:
                if current_group is not None:
                    groups.append((current_group, current_count))
                current_group = child_dsl
                current_count = 1

        if current_group is not None:
            groups.append((current_group, current_count))

        # Build DSL parts
        parts = []
        for dsl, count in groups:
            if count > 1:
                parts.append(f"{dsl}×{count}")
            else:
                parts.append(dsl)

        return f"{symbol}[{', '.join(parts)}]"

    def tree_to_component_list(self, tree: Dict[str, Any]) -> List[str]:
        """Extract flat list of all components in tree."""
        components = [tree["name"]]
        for child in tree.get("children", []):
            components.extend(self.tree_to_component_list(child))
        return components

    def calculate_depth(self, tree: Dict[str, Any]) -> int:
        """Calculate maximum depth of tree."""
        children = tree.get("children", [])
        if not children:
            return 1
        return 1 + max(self.calculate_depth(c) for c in children)

    def generate_random_structure(
        self,
        root: str = "Section",
        required_components: Optional[List[str]] = None,
    ) -> GeneratedStructure:
        """
        Generate a random valid structure starting from root.

        Args:
            root: Root component (default: Section)
            required_components: Components that must appear in structure

        Returns:
            GeneratedStructure with tree, DSL, components, validation
        """
        wrapper = self._get_wrapper()
        required = set(required_components or self.config.required_components)

        # Generate tree
        tree = self.generate_tree(root, depth=0, required=required)

        # Convert to DSL
        dsl = self.tree_to_dsl(tree)

        # Get component list
        components = self.tree_to_component_list(tree)

        # Calculate depth
        depth = self.calculate_depth(tree)

        # Validate using the DAG
        is_valid = True
        issues = []

        # Check that required components are present
        for req in required:
            if req not in components:
                is_valid = False
                issues.append(f"Required component '{req}' not in structure")

        # Validate containment chain for each path
        def validate_paths(node: Dict, path: List[str] = None):
            nonlocal is_valid, issues
            path = path or []
            current_path = path + [node["name"]]

            for child in node.get("children", []):
                # Check if parent can contain child
                if not wrapper.can_contain(node["name"], child["name"], direct_only=True):
                    # Also check our hierarchy
                    hierarchy_children = WIDGET_HIERARCHY.get(node["name"], [])
                    if child["name"] not in hierarchy_children:
                        is_valid = False
                        issues.append(
                            f"{node['name']} cannot contain {child['name']}"
                        )
                validate_paths(child, current_path)

        validate_paths(tree)

        return GeneratedStructure(
            root=root,
            components=components,
            dsl=dsl,
            tree=tree,
            depth=depth,
            is_valid=is_valid,
            validation_issues=issues,
        )

    # =========================================================================
    # CARD JSON GENERATION
    # =========================================================================

    def _build_carousel_card(
        self,
        carousel_card_tree: Dict[str, Any],
        widget_index: int,
    ) -> Tuple[Dict[str, Any], int]:
        """Build a single CarouselCard from tree."""
        card_content = {
            "widgets": [],
            "footerWidgets": [],
        }

        # Process children (NestedWidget contains the actual widgets)
        for child in carousel_card_tree.get("children", []):
            if child["name"] == "NestedWidget":
                # NestedWidget children become card widgets (NOT wrapped in nestedWidget)
                for nested_child in child.get("children", []):
                    child_widgets, widget_index = self.tree_to_widgets(
                        nested_child, widget_index
                    )
                    card_content["widgets"].extend(child_widgets)

        # Add a default widget if empty
        if not card_content["widgets"]:
            card_content["widgets"].append({
                "textParagraph": {"text": "Carousel card content"}
            })

        return card_content, widget_index

    def _generate_content(self, component: str, index: int = 0) -> Dict[str, Any]:
        """Generate sample content for a component."""
        if component == "DecoratedText":
            return {
                "decoratedText": {
                    "startIcon": {"knownIcon": random.choice(SAMPLE_ICONS)},
                    "text": random.choice(SAMPLE_TEXTS),
                    "wrapText": True,
                }
            }
        elif component == "TextParagraph":
            return {
                "textParagraph": {
                    "text": random.choice(SAMPLE_TEXTS),
                }
            }
        elif component == "Button":
            btn = {"text": random.choice(SAMPLE_BUTTON_LABELS)}
            if self.config.webhook_url:
                btn["onClick"] = {
                    "openLink": {
                        "url": f"{self.config.webhook_url}?btn={index}&test={self.config.test_id}"
                    }
                }
            return btn
        elif component == "ButtonList":
            return {"buttonList": {"buttons": []}}
        elif component == "Image":
            return {
                "image": {
                    "imageUrl": random.choice(SAMPLE_IMAGES),
                    "altText": "Generated test image",
                }
            }
        elif component == "Divider":
            return {"divider": {}}
        elif component == "Icon":
            return {"knownIcon": random.choice(SAMPLE_ICONS)}
        elif component == "Grid":
            return {
                "grid": {
                    "title": "Test Grid",
                    "columnCount": 2,
                    "items": [],
                }
            }
        elif component == "GridItem":
            return {
                "title": f"Item {index + 1}",
                "subtitle": "Test item",
            }
        elif component == "SelectionInput":
            return {
                "selectionInput": {
                    "name": f"select_{index}",
                    "label": "Select option",
                    "type": "DROPDOWN",
                    "items": [
                        {"text": "Option A", "value": "a", "selected": True},
                        {"text": "Option B", "value": "b"},
                    ],
                }
            }
        elif component == "DateTimePicker":
            return {
                "dateTimePicker": {
                    "name": f"datetime_{index}",
                    "label": "Select date",
                    "type": "DATE_AND_TIME",
                }
            }
        else:
            # Generic fallback
            return {"text": f"{component} content"}

    def _generate_content_from_params(
        self,
        node: ParameterizedNode,
        index: int = 0,
    ) -> Dict[str, Any]:
        """
        Generate widget content using the node's parameter values.

        This uses the generated/default values from the ParameterizedNode
        instead of hardcoded sample values.

        Args:
            node: ParameterizedNode with parameter values
            index: Widget index for unique IDs

        Returns:
            Widget content dict
        """
        component = node.name
        params = node.parameters

        def get_param(name: str, default: Any = None) -> Any:
            """Get parameter value, using generated value if available."""
            if name in params:
                val = params[name].generated_value
                return val if val is not None else default
            return default

        if component == "DecoratedText":
            content = {
                "decoratedText": {
                    "text": get_param("text", random.choice(SAMPLE_TEXTS)),
                    "wrapText": get_param("wrap_text", True),
                }
            }
            # Add optional fields if values were generated
            if get_param("top_label"):
                content["decoratedText"]["topLabel"] = get_param("top_label")
            if get_param("bottom_label"):
                content["decoratedText"]["bottomLabel"] = get_param("bottom_label")
            # Add icon - prefer generated materialIcon
            icon_val = get_param("start_icon") or get_param("icon")
            if icon_val and isinstance(icon_val, dict):
                content["decoratedText"]["startIcon"] = icon_val
            else:
                # Use a material icon from our curated list via helper
                content["decoratedText"]["startIcon"] = create_material_icon(
                    random.choice(CURATED_MATERIAL_ICONS)
                )
            return content

        elif component == "TextParagraph":
            return {
                "textParagraph": {
                    "text": get_param("text", random.choice(SAMPLE_TEXTS)),
                }
            }

        elif component == "Button":
            btn = {"text": get_param("text", random.choice(SAMPLE_BUTTON_LABELS))}
            # Add icon if generated
            icon_val = get_param("icon")
            if icon_val and isinstance(icon_val, dict):
                btn["icon"] = icon_val
            if self.config.webhook_url:
                btn["onClick"] = {
                    "openLink": {
                        "url": f"{self.config.webhook_url}?btn={index}&test={self.config.test_id}"
                    }
                }
            return btn

        elif component == "ButtonList":
            return {"buttonList": {"buttons": []}}

        elif component == "Image":
            return {
                "image": {
                    "imageUrl": get_param("image_url", random.choice(SAMPLE_IMAGES)),
                    "altText": get_param("alt_text", "Generated test image"),
                }
            }

        elif component == "Divider":
            return {"divider": {}}

        elif component == "Icon":
            # Return icon dict - prefer material icon format
            icon_val = get_param("material_icon") or get_param("known_icon")
            if icon_val and isinstance(icon_val, dict):
                return icon_val
            # Use material icon via helper
            return create_material_icon(random.choice(CURATED_MATERIAL_ICONS))

        elif component == "Grid":
            return {
                "grid": {
                    "title": get_param("title", "Test Grid"),
                    "columnCount": get_param("column_count", 2),
                    "items": [],
                }
            }

        elif component == "GridItem":
            return {
                "title": get_param("title", f"Item {index + 1}"),
                "subtitle": get_param("subtitle", "Test item"),
            }

        elif component == "SelectionInput":
            return {
                "selectionInput": {
                    "name": get_param("name", f"select_{index}"),
                    "label": get_param("label", "Select option"),
                    "type": get_param("type", "DROPDOWN"),
                    "items": [
                        {"text": "Option A", "value": "a", "selected": True},
                        {"text": "Option B", "value": "b"},
                    ],
                }
            }

        elif component == "DateTimePicker":
            return {
                "dateTimePicker": {
                    "name": get_param("name", f"datetime_{index}"),
                    "label": get_param("label", "Select date"),
                    "type": get_param("type", "DATE_AND_TIME"),
                }
            }

        elif component == "Chip":
            chip = {
                "label": get_param("label", f"Chip {index + 1}"),
                "enabled": get_param("enabled", True),
            }
            icon_val = get_param("icon")
            if icon_val and isinstance(icon_val, dict):
                chip["icon"] = icon_val
            return chip

        else:
            # Generic fallback
            return {"text": f"{component} content"}

    def parameterized_tree_to_widgets(
        self,
        node: ParameterizedNode,
        widget_index: int = 0,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Convert a ParameterizedNode tree to widget JSON using generated parameter values.

        This is the parameterized version of tree_to_widgets that uses
        the actual generated values from each node's parameters dict.

        Args:
            node: ParameterizedNode with parameter values
            widget_index: Running index for unique IDs

        Returns:
            Tuple of (widgets list, updated index)
        """
        widgets = []
        component = node.name
        children = node.children

        # Generate content using parameterized values
        content = self._generate_content_from_params(node, widget_index)
        widget_index += 1

        # Handle special cases for nesting
        if component == "Section":
            section_widgets = []
            for child in children:
                child_widgets, widget_index = self.parameterized_tree_to_widgets(child, widget_index)
                section_widgets.extend(child_widgets)
            return section_widgets, widget_index

        elif component == "ButtonList":
            buttons = []
            for child in children:
                if child.name == "Button":
                    btn_content = self._generate_content_from_params(child, widget_index)
                    widget_index += 1
                    # Handle Button's children (Icon)
                    for btn_child in child.children:
                        if btn_child.name == "Icon":
                            btn_content["icon"] = self._generate_content_from_params(btn_child)
                    buttons.append(btn_content)
            content["buttonList"]["buttons"] = buttons
            widgets.append(content)

        elif component == "DecoratedText":
            # DecoratedText has a oneof for control: either button OR switchControl (not both)
            control_set = False
            for child in children:
                if child.name == "Icon":
                    content["decoratedText"]["startIcon"] = self._generate_content_from_params(child)
                elif child.name == "Button" and not control_set:
                    content["decoratedText"]["button"] = self._generate_content_from_params(child, widget_index)
                    widget_index += 1
                    control_set = True  # Can't add switchControl now
                elif child.name == "SwitchControl" and not control_set:
                    content["decoratedText"]["switchControl"] = {
                        "name": f"switch_{widget_index}",
                        "selected": random.choice([True, False]),
                    }
                    widget_index += 1
                    control_set = True  # Can't add button now
            widgets.append(content)

        elif component == "Grid":
            items = []
            for child in children:
                if child.name == "GridItem":
                    item = self._generate_content_from_params(child, widget_index)
                    widget_index += 1
                    for item_child in child.children:
                        if item_child.name == "Image":
                            item["image"] = {
                                "imageUri": random.choice(SAMPLE_IMAGES),
                                "altText": "Grid image",
                            }
                    items.append(item)
            content["grid"]["items"] = items
            widgets.append(content)

        elif component == "ChipList":
            chips = []
            for child in children:
                if child.name == "Chip":
                    chip = self._generate_content_from_params(child, widget_index)
                    widget_index += 1
                    chips.append(chip)
            widgets.append({
                "chipList": {
                    "chips": chips if chips else [{"label": "Default Chip"}],
                }
            })

        elif component == "Carousel":
            carousel_cards = []
            for child in children:
                if child.name == "CarouselCard":
                    card_content, widget_index = self._build_parameterized_carousel_card(child, widget_index)
                    carousel_cards.append(card_content)

            if not carousel_cards:
                carousel_cards.append({
                    "widgets": [{"textParagraph": {"text": "Carousel item"}}],
                    "footerWidgets": [],
                })

            widgets.append({
                "carousel": {
                    "carouselCards": carousel_cards,
                }
            })

        elif component == "NestedWidget":
            for child in children:
                child_widgets, widget_index = self.parameterized_tree_to_widgets(child, widget_index)
                widgets.extend(child_widgets)

        elif component == "Columns":
            columns = []
            for child in children:
                if child.name == "Column":
                    col_widgets = []
                    for col_child in child.children:
                        child_widgets, widget_index = self.parameterized_tree_to_widgets(
                            col_child, widget_index
                        )
                        col_widgets.extend(child_widgets)

                    columns.append({
                        "horizontalSizeStyle": "FILL_AVAILABLE_SPACE",
                        "horizontalAlignment": "CENTER",
                        "verticalAlignment": "CENTER",
                        "widgets": col_widgets if col_widgets else [
                            {"textParagraph": {"text": "Column content"}}
                        ],
                    })

            if columns:
                widgets.append({
                    "columns": {
                        "columnItems": columns,
                    }
                })

        else:
            # Leaf widgets
            widgets.append(content)

        return widgets, widget_index

    def _build_parameterized_carousel_card(
        self,
        carousel_card_node: ParameterizedNode,
        widget_index: int,
    ) -> Tuple[Dict[str, Any], int]:
        """Build a CarouselCard from ParameterizedNode."""
        card_content = {
            "widgets": [],
            "footerWidgets": [],
        }

        for child in carousel_card_node.children:
            if child.name == "NestedWidget":
                for nested_child in child.children:
                    child_widgets, widget_index = self.parameterized_tree_to_widgets(
                        nested_child, widget_index
                    )
                    card_content["widgets"].extend(child_widgets)

        if not card_content["widgets"]:
            card_content["widgets"].append({
                "textParagraph": {"text": "Carousel card content"}
            })

        return card_content, widget_index

    def parameterized_structure_to_card(
        self,
        structure: ParameterizedStructure,
        title: str = "Generated Card",
        subtitle: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Convert a ParameterizedStructure to complete card JSON.

        This uses the generated parameter values from each node
        instead of hardcoded sample values.

        Args:
            structure: ParameterizedStructure from generate_parameterized_structure()
            title: Card header title
            subtitle: Card header subtitle (auto-generated if None)

        Returns:
            Complete message payload with cards_v2
        """
        # Convert tree to widgets using parameterized values
        widgets, _ = self.parameterized_tree_to_widgets(structure.tree)

        # Build card structure
        card_dict = {
            "card_id": f"dag-param-{self.config.test_id}",
            "card": {
                "header": {
                    "title": title,
                    "subtitle": subtitle or f"DSL: {structure.dsl}",
                },
                "sections": [{
                    "widgets": widgets,
                }],
            },
        }

        # Build message using Message component
        message = self._build_message_payload(card_dict)

        # Add metadata including parameter stats
        message["_dag_gen_meta"] = {
            "test_id": self.config.test_id,
            "dsl": structure.dsl,
            "components": structure.components,
            "depth": structure.depth,
            "is_valid": structure.is_valid,
            "timestamp": datetime.now().isoformat(),
            "parameter_stats": {
                "total": structure.total_parameters,
                "with_values": structure.parameters_with_values,
                "using_defaults": structure.parameters_using_defaults,
            },
        }

        return message

    def generate_parameterized_card(
        self,
        root: str = "Section",
        required_components: Optional[List[str]] = None,
        fill_optional_probability: float = 0.5,
    ) -> Dict[str, Any]:
        """
        Generate a card with parameterized component values.

        This is like generate_random_card but uses the full parameter
        generation system to provide meaningful test values.

        Args:
            root: Root component
            required_components: Components that must appear
            fill_optional_probability: Probability of filling optional fields

        Returns:
            Complete card JSON with generated parameter values
        """
        # Generate new test ID for each card
        self.config.test_id = str(uuid.uuid4())[:8]

        structure = self.generate_parameterized_structure(
            root,
            required_components,
            fill_optional_probability,
        )

        return self.parameterized_structure_to_card(structure)

    def tree_to_widgets(
        self,
        tree: Dict[str, Any],
        widget_index: int = 0,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Convert a component tree to widget JSON.

        Args:
            tree: Component tree
            widget_index: Running index for unique IDs

        Returns:
            Tuple of (widgets list, updated index)
        """
        widgets = []
        component = tree["name"]
        children = tree.get("children", [])

        # Generate base content
        content = self._generate_content(component, widget_index)
        widget_index += 1

        # Handle special cases for nesting
        if component == "Section":
            # Section contains widgets directly
            section_widgets = []
            for child in children:
                child_widgets, widget_index = self.tree_to_widgets(child, widget_index)
                section_widgets.extend(child_widgets)
            return section_widgets, widget_index

        elif component == "ButtonList":
            # ButtonList wraps buttons
            buttons = []
            for child in children:
                if child["name"] == "Button":
                    btn_content = self._generate_content("Button", widget_index)
                    widget_index += 1
                    # Handle Button's children (Icon)
                    for btn_child in child.get("children", []):
                        if btn_child["name"] == "Icon":
                            btn_content["icon"] = self._generate_content("Icon")
                    buttons.append(btn_content)
            content["buttonList"]["buttons"] = buttons
            widgets.append(content)

        elif component == "DecoratedText":
            # DecoratedText has a oneof for control: either button OR switchControl (not both)
            control_set = False
            for child in children:
                if child["name"] == "Icon":
                    content["decoratedText"]["startIcon"] = self._generate_content("Icon")
                elif child["name"] == "Button" and not control_set:
                    content["decoratedText"]["button"] = self._generate_content("Button", widget_index)
                    widget_index += 1
                    control_set = True
                elif child["name"] == "SwitchControl" and not control_set:
                    content["decoratedText"]["switchControl"] = {
                        "name": f"switch_{widget_index}",
                        "selected": random.choice([True, False]),
                    }
                    widget_index += 1
                    control_set = True
            widgets.append(content)

        elif component == "Grid":
            # Grid contains GridItems
            items = []
            for child in children:
                if child["name"] == "GridItem":
                    item = self._generate_content("GridItem", widget_index)
                    widget_index += 1
                    # GridItem can have Image
                    for item_child in child.get("children", []):
                        if item_child["name"] == "Image":
                            item["image"] = {
                                "imageUri": random.choice(SAMPLE_IMAGES),
                                "altText": "Grid image",
                            }
                    items.append(item)
            content["grid"]["items"] = items
            widgets.append(content)

        elif component == "Carousel":
            # Carousel contains CarouselCards - outputs a carousel widget
            carousel_cards = []
            for child in children:
                if child["name"] == "CarouselCard":
                    card_content, widget_index = self._build_carousel_card(child, widget_index)
                    carousel_cards.append(card_content)

            # Add at least one card if empty
            if not carousel_cards:
                carousel_cards.append({
                    "widgets": [{"textParagraph": {"text": "Carousel item"}}],
                    "footerWidgets": [],
                })

            widgets.append({
                "carousel": {
                    "carouselCards": carousel_cards,
                }
            })

        elif component == "CarouselCard":
            # Standalone CarouselCard (shouldn't happen, but handle it)
            card_content, widget_index = self._build_carousel_card(tree, widget_index)
            widgets.append({
                "carousel": {
                    "carouselCards": [card_content],
                }
            })

        elif component == "NestedWidget":
            # NestedWidget just passes through its children (no wrapping)
            for child in children:
                child_widgets, widget_index = self.tree_to_widgets(child, widget_index)
                widgets.extend(child_widgets)

        elif component == "CollapseControl":
            # CollapseControl has expand/collapse buttons
            buttons = []
            for child in children:
                if child["name"] == "Button":
                    btn = self._generate_content("Button", widget_index)
                    widget_index += 1
                    buttons.append(btn)
            if buttons:
                widgets.append({
                    "collapseControl": {
                        "expandButton": buttons[0] if len(buttons) > 0 else None,
                        "collapseButton": buttons[1] if len(buttons) > 1 else None,
                    }
                })

        elif component == "Columns":
            # Columns widget contains Column items
            columns = []
            for child in children:
                if child["name"] == "Column":
                    # Column contains widgets
                    col_widgets = []
                    for col_child in child.get("children", []):
                        child_widgets, widget_index = self.tree_to_widgets(
                            col_child, widget_index
                        )
                        col_widgets.extend(child_widgets)

                    columns.append({
                        "horizontalSizeStyle": "FILL_AVAILABLE_SPACE",
                        "horizontalAlignment": "CENTER",
                        "verticalAlignment": "CENTER",
                        "widgets": col_widgets if col_widgets else [
                            {"textParagraph": {"text": "Column content"}}
                        ],
                    })

            if columns:
                widgets.append({
                    "columns": {
                        "columnItems": columns,
                    }
                })

        elif component == "ChipList":
            # ChipList contains Chip items
            chips = []
            for child in children:
                if child["name"] == "Chip":
                    chip = {
                        "label": f"Chip {len(chips) + 1}",
                        "enabled": True,
                    }
                    # Handle Chip's children (Icon)
                    for chip_child in child.get("children", []):
                        if chip_child["name"] == "Icon":
                            chip["icon"] = self._generate_content("Icon")
                    chips.append(chip)

            widgets.append({
                "chipList": {
                    "chips": chips if chips else [{"label": "Default Chip"}],
                }
            })

        else:
            # Leaf widgets
            widgets.append(content)

        return widgets, widget_index

    def _build_message_payload(
        self,
        card_dict: Dict[str, Any],
        fallback_text: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Build a proper message payload for webhook API.

        Note: The 'text' field is optional for webhooks - cards render without it.
        If provided, text appears in notifications and as fallback.

        Args:
            card_dict: Card dictionary with 'card' key
            fallback_text: Optional text for notifications (None = card only)

        Returns:
            Message payload ready for webhook
        """
        try:
            from card_framework.v2 import Message

            message_obj = Message()
            if fallback_text:
                message_obj.text = fallback_text
            message_obj.cards_v2.append(card_dict)
            message_body = message_obj.render()

            # Fix field name issues for webhook API (expects snake_case)
            if "cards_v_2" in message_body:
                message_body["cards_v2"] = message_body.pop("cards_v_2")
            if "cardsV2" in message_body:
                message_body["cards_v2"] = message_body.pop("cardsV2")

            return message_body

        except ImportError:
            # Fallback if card_framework not available
            payload = {"cards_v2": [card_dict]}
            if fallback_text:
                payload["text"] = fallback_text
            return payload

    def structure_to_card(
        self,
        structure: GeneratedStructure,
        title: str = "Generated Card",
        subtitle: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Convert a GeneratedStructure to complete card JSON.

        Uses card_framework.v2.Message for proper message building.

        Args:
            structure: Generated structure from generate_random_structure()
            title: Card header title
            subtitle: Card header subtitle (auto-generated if None)

        Returns:
            Complete message payload with cards_v2
        """
        # Convert tree to widgets
        widgets, _ = self.tree_to_widgets(structure.tree)

        # Build card structure
        card_dict = {
            "card_id": f"dag-gen-{self.config.test_id}",
            "card": {
                "header": {
                    "title": title,
                    "subtitle": subtitle or f"DSL: {structure.dsl}",
                },
                "sections": [{
                    "widgets": widgets,
                }],
            },
        }

        # Build message using Message component
        message = self._build_message_payload(card_dict)

        # Add metadata
        message["_dag_gen_meta"] = {
            "test_id": self.config.test_id,
            "dsl": structure.dsl,
            "components": structure.components,
            "depth": structure.depth,
            "is_valid": structure.is_valid,
            "timestamp": datetime.now().isoformat(),
        }

        return message

    def generate_random_card(
        self,
        root: str = "Section",
        required_components: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Generate a complete random card.

        Args:
            root: Root component
            required_components: Components that must appear

        Returns:
            Complete card JSON
        """
        # Generate new test ID for each card
        self.config.test_id = str(uuid.uuid4())[:8]

        structure = self.generate_random_structure(root, required_components)
        return self.structure_to_card(structure)

    def generate_random_cards(
        self,
        count: int = 5,
        root: str = "Section",
        required_components: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Generate multiple random cards.

        Args:
            count: Number of cards to generate
            root: Root component for each card
            required_components: Components that must appear in each

        Returns:
            List of card JSON structures
        """
        return [
            self.generate_random_card(root, required_components)
            for _ in range(count)
        ]

    def generate_widget_showcase_carousel(self) -> Dict[str, Any]:
        """
        Generate a showcase carousel demonstrating CarouselCard capabilities.

        NOTE: NestedWidget in CarouselCard only supports:
        - textParagraph
        - buttonList
        - image

        Each carousel card shows different variations of these supported widgets.

        Returns:
            Complete card JSON with showcase carousel
        """
        self.config.test_id = str(uuid.uuid4())[:8]

        carousel_cards = []

        # Card 1: Text Formatting
        carousel_cards.append({
            "widgets": [
                {"textParagraph": {"text": "<b>📝 Text Formatting</b>"}},
                {"textParagraph": {"text": "Normal text paragraph"}},
                {"textParagraph": {"text": "<i>Italic text</i> and <b>bold text</b>"}},
                {"textParagraph": {"text": "<font color=\"#4285F4\">Colored text</font>"}},
            ],
            "footerWidgets": [
                {"buttonList": {"buttons": [{"text": "Text Demo"}]}}
            ],
        })

        # Card 2: Images
        carousel_cards.append({
            "widgets": [
                {"textParagraph": {"text": "<b>🖼️ Images</b>"}},
                {
                    "image": {
                        "imageUrl": SAMPLE_IMAGES[0],
                        "altText": "Sample image 1",
                    }
                },
                {"textParagraph": {"text": "Images with alt text for accessibility"}},
            ],
            "footerWidgets": [
                {"buttonList": {"buttons": [{"text": "View Gallery"}]}}
            ],
        })

        # Card 3: More Images
        carousel_cards.append({
            "widgets": [
                {"textParagraph": {"text": "<b>🎨 Gallery Item</b>"}},
                {
                    "image": {
                        "imageUrl": SAMPLE_IMAGES[1],
                        "altText": "Sample image 2",
                    }
                },
                {"textParagraph": {"text": "Carousel cards are great for galleries!"}},
            ],
            "footerWidgets": [
                {"buttonList": {"buttons": [{"text": "Next →"}]}}
            ],
        })

        # Card 4: Button Variations
        carousel_cards.append({
            "widgets": [
                {"textParagraph": {"text": "<b>🔘 Button List</b>"}},
                {"textParagraph": {"text": "Buttons with material icons:"}},
                {
                    "buttonList": {
                        "buttons": [
                            {"text": "Star", "icon": create_material_icon("star")},
                            {"text": "Save", "icon": create_material_icon("bookmark")},
                            {"text": "Share", "icon": create_material_icon("share")},
                        ]
                    }
                },
            ],
            "footerWidgets": [
                {"buttonList": {"buttons": [
                    {"text": "Action 1"},
                    {"text": "Action 2"},
                ]}}
            ],
        })

        # Card 5: Combined
        carousel_cards.append({
            "widgets": [
                {"textParagraph": {"text": "<b>✨ Combined</b>"}},
                {
                    "image": {
                        "imageUrl": SAMPLE_IMAGES[2] if len(SAMPLE_IMAGES) > 2 else SAMPLE_IMAGES[0],
                        "altText": "Feature image",
                    }
                },
                {"textParagraph": {"text": "<b>Feature Title</b><br>Description text here"}},
                {
                    "buttonList": {
                        "buttons": [
                            {"text": "Learn More", "icon": create_material_icon("arrow_forward")},
                        ]
                    }
                },
            ],
            "footerWidgets": [
                {"buttonList": {"buttons": [{"text": "Get Started"}]}}
            ],
        })

        # Build card structure
        card_dict = {
            "card_id": f"showcase-{self.config.test_id}",
            "card": {
                "header": {
                    "title": "Carousel Showcase",
                    "subtitle": "NestedWidget: textParagraph, buttonList, image",
                },
                "sections": [{
                    "widgets": [
                        {"carousel": {"carouselCards": carousel_cards}},
                    ],
                }],
            },
        }

        message = self._build_message_payload(card_dict)
        message["_dag_gen_meta"] = {
            "test_id": self.config.test_id,
            "dsl": "§[◦[▲×5]]",
            "components": ["Carousel", "CarouselCard", "NestedWidget",
                           "TextParagraph", "Image", "ButtonList", "Button", "Icon"],
            "is_showcase": True,
        }

        return message

    def generate_carousel_card(
        self,
        num_carousel_items: int = 3,
    ) -> Dict[str, Any]:
        """
        Generate a card containing a Carousel widget.

        Args:
            num_carousel_items: Number of CarouselCard items

        Returns:
            Complete card JSON with carousel
        """
        self.config.test_id = str(uuid.uuid4())[:8]

        # Build carousel cards manually for reliable structure
        carousel_cards = []
        for i in range(num_carousel_items):
            carousel_cards.append({
                "widgets": [
                    {"textParagraph": {"text": f"<b>Carousel Item {i+1}</b>"}},
                    {"textParagraph": {"text": random.choice(SAMPLE_TEXTS)}},
                    {"image": {
                        "imageUrl": random.choice(SAMPLE_IMAGES),
                        "altText": f"Image {i+1}",
                    }},
                ],
                "footerWidgets": [
                    {"buttonList": {"buttons": [
                        {"text": f"Action {i+1}"},
                    ]}},
                ],
            })

        # Build card structure
        card_dict = {
            "card_id": f"carousel-{self.config.test_id}",
            "card": {
                "header": {
                    "title": "DAG Carousel Test",
                    "subtitle": f"DSL: §[◦[▲×{num_carousel_items}]]",
                },
                "sections": [{
                    "widgets": [
                        {"carousel": {"carouselCards": carousel_cards}},
                    ],
                }],
            },
        }

        # Build message using Message component
        message = self._build_message_payload(card_dict)

        message["_dag_gen_meta"] = {
            "test_id": self.config.test_id,
            "dsl": f"§[◦[▲×{num_carousel_items}]]",
            "components": ["Section", "Carousel"] + ["CarouselCard"] * num_carousel_items,
            "is_carousel": True,
        }

        return message

    # =========================================================================
    # TARGETED GENERATION
    # =========================================================================

    def generate_with_components(
        self,
        components: List[str],
        root: str = "Section",
    ) -> GeneratedStructure:
        """
        Generate a structure that includes all specified components.

        The generator will find valid paths to include each component.

        Args:
            components: Components that must appear in the structure
            root: Root component to start from

        Returns:
            GeneratedStructure containing all specified components
        """
        # Store original config
        original_required = self.config.required_components

        try:
            self.config.required_components = components
            return self.generate_random_structure(root, components)
        finally:
            self.config.required_components = original_required

    def generate_all_component_cards(
        self,
        components: Optional[List[str]] = None,
        max_per_card: int = 4,
    ) -> List[Dict[str, Any]]:
        """
        Generate cards that exercise all specified components.

        Splits components into groups and generates a card for each group.

        Args:
            components: Components to exercise (default: all Section children)
            max_per_card: Maximum components to require per card

        Returns:
            List of cards that together exercise all components
        """
        if components is None:
            # Default to all Section children
            components = self.get_valid_children("Section")

        cards = []
        remaining = list(components)

        while remaining:
            # Take a batch
            batch = remaining[:max_per_card]
            remaining = remaining[max_per_card:]

            # Generate card with this batch
            card = self.generate_random_card("Section", batch)
            cards.append(card)

        return cards


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def generate_dag_card(
    root: str = "Section",
    required: Optional[List[str]] = None,
    webhook_url: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Generate a single random valid card.

    Args:
        root: Root component
        required: Required components
        webhook_url: Webhook for button callbacks

    Returns:
        Card JSON
    """
    config = DAGGeneratorConfig(webhook_url=webhook_url)
    gen = DAGStructureGenerator(config)
    return gen.generate_random_card(root, required)


def generate_dag_structure(
    root: str = "Section",
    max_depth: int = 3,
) -> GeneratedStructure:
    """
    Generate a random valid structure.

    Args:
        root: Root component
        max_depth: Maximum nesting depth

    Returns:
        GeneratedStructure with DSL and tree
    """
    config = DAGGeneratorConfig(max_depth=max_depth)
    gen = DAGStructureGenerator(config)
    return gen.generate_random_structure(root)


async def send_parameterized_cards_to_webhook(
    webhook_url: str,
    count: int = 3,
    root: str = "Section",
    required: Optional[List[str]] = None,
    include_carousel: bool = False,
    delay_seconds: float = 1.0,
    fill_optional_probability: float = 0.5,
) -> List[Dict[str, Any]]:
    """
    Generate and send parameterized cards to a webhook.

    This version uses the full parameter generation system for richer test values.

    Args:
        webhook_url: Google Chat webhook URL
        count: Number of cards to send
        root: Root component for generation
        required: Required components in each card
        include_carousel: Whether to include a Carousel card
        delay_seconds: Delay between card sends
        fill_optional_probability: Probability of filling optional fields

    Returns:
        List of results with card info and response status
    """
    import asyncio
    import httpx

    config = DAGGeneratorConfig(webhook_url=webhook_url)
    gen = DAGStructureGenerator(config)
    results = []

    async with httpx.AsyncClient(verify=False) as client:
        for i in range(count):
            config.test_id = str(uuid.uuid4())[:8]

            if include_carousel and i == count - 1:
                card = gen.generate_carousel_card()
                structure_dsl = card.get("_dag_gen_meta", {}).get("dsl", "§[◦[▲]]")
                components = card.get("_dag_gen_meta", {}).get("components", [])
                param_stats = None
            else:
                structure = gen.generate_parameterized_structure(
                    root,
                    required,
                    fill_optional_probability,
                )
                card = gen.parameterized_structure_to_card(
                    structure,
                    title=f"Parameterized Card #{i+1}",
                    subtitle=f"DSL: {structure.dsl}"
                )
                structure_dsl = structure.dsl
                components = structure.components
                param_stats = {
                    "total": structure.total_parameters,
                    "with_values": structure.parameters_with_values,
                    "using_defaults": structure.parameters_using_defaults,
                }

            meta = card.pop("_dag_gen_meta", {})

            result = {
                "index": i + 1,
                "test_id": config.test_id,
                "dsl": structure_dsl,
                "components": components,
                "parameter_stats": param_stats,
                "valid": True,
                "success": False,
                "error": None,
            }

            try:
                response = await client.post(
                    webhook_url,
                    json=card,
                    timeout=30.0,
                )

                if response.status_code == 200:
                    result["success"] = True
                    stats_str = ""
                    if param_stats:
                        stats_str = f" [params: {param_stats['with_values']}/{param_stats['total']}]"
                    print(f"✅ Card {i+1}: {structure_dsl}{stats_str}")
                else:
                    result["error"] = f"HTTP {response.status_code}: {response.text[:100]}"
                    print(f"❌ Card {i+1}: {result['error']}")

            except Exception as e:
                result["error"] = str(e)
                print(f"❌ Card {i+1}: {e}")

            results.append(result)

            if i < count - 1:
                await asyncio.sleep(delay_seconds)

    return results


async def send_dag_cards_to_webhook(
    webhook_url: str,
    count: int = 3,
    root: str = "Section",
    required: Optional[List[str]] = None,
    include_carousel: bool = False,
    delay_seconds: float = 1.0,
) -> List[Dict[str, Any]]:
    """
    Generate and send random DAG-based cards to a webhook.

    Args:
        webhook_url: Google Chat webhook URL
        count: Number of cards to send
        root: Root component for generation
        required: Required components in each card
        include_carousel: Whether to include a Carousel card
        delay_seconds: Delay between card sends

    Returns:
        List of results with card info and response status
    """
    import asyncio
    import httpx

    config = DAGGeneratorConfig(webhook_url=webhook_url)
    gen = DAGStructureGenerator(config)
    results = []

    async with httpx.AsyncClient(verify=False) as client:
        for i in range(count):
            # Generate card
            config.test_id = str(uuid.uuid4())[:8]

            if include_carousel and i == count - 1:
                # Last card includes a Carousel widget
                card = gen.generate_carousel_card()
                structure_dsl = "§[◦[▲[ŋ[...]]]]"  # Carousel DSL placeholder
                components = ["Section", "Carousel", "CarouselCard", "NestedWidget"]
            else:
                structure = gen.generate_random_structure(root, required)
                card = gen.structure_to_card(
                    structure,
                    title=f"DAG Test Card #{i+1}",
                    subtitle=f"DSL: {structure.dsl}"
                )
                structure_dsl = structure.dsl
                components = structure.components

            meta = card.pop("_dag_gen_meta", {})

            result = {
                "index": i + 1,
                "test_id": config.test_id,
                "dsl": structure_dsl,
                "components": components,
                "valid": True,
                "success": False,
                "error": None,
            }

            try:
                response = await client.post(
                    webhook_url,
                    json=card,
                    timeout=30.0,
                )

                if response.status_code == 200:
                    result["success"] = True
                    print(f"✅ Card {i+1}: {structure_dsl}")
                else:
                    result["error"] = f"HTTP {response.status_code}: {response.text[:100]}"
                    print(f"❌ Card {i+1}: {result['error']}")

            except Exception as e:
                result["error"] = str(e)
                print(f"❌ Card {i+1}: {e}")

            results.append(result)

            if i < count - 1:
                await asyncio.sleep(delay_seconds)

    return results


async def run_stress_test(
    webhook_url: str,
    fill_probability: float = 0.8,
    delay_seconds: float = 1.0,
) -> Dict[str, Any]:
    """
    Run comprehensive stress test covering ALL components with complex parameters.

    This test:
    1. Tests each component type at least once
    2. Uses high parameter fill probability
    3. Generates complex nested structures
    4. Reports component coverage

    Args:
        webhook_url: Google Chat webhook URL
        fill_probability: Probability of filling optional fields (0.8 = 80%)
        delay_seconds: Delay between card sends

    Returns:
        Dict with test results and coverage stats
    """
    import asyncio
    import httpx

    # All testable components from WIDGET_HIERARCHY
    ALL_COMPONENTS = set()
    for parent, children in WIDGET_HIERARCHY.items():
        ALL_COMPONENTS.add(parent)
        ALL_COMPONENTS.update(children)

    # Remove internal/abstract types
    TESTABLE_COMPONENTS = ALL_COMPONENTS - INTERNAL_TYPES - {"Card", "CardHeader", "CardFixedFooter"}

    # Group components by what can contain them (for targeted testing)
    SECTION_CHILDREN = set(WIDGET_HIERARCHY.get("Section", []))
    BUTTON_RELATIVES = {"Button", "ButtonList", "Icon"}
    DECORATED_CHILDREN = {"DecoratedText", "Icon", "Button", "SwitchControl"}
    GRID_CHILDREN = {"Grid", "GridItem", "Image"}
    CHIP_CHILDREN = {"ChipList", "Chip", "Icon"}
    CAROUSEL_CHILDREN = {"Carousel", "CarouselCard", "NestedWidget"}

    config = DAGGeneratorConfig(
        max_depth=4,
        max_children_per_node=5,
        avoid_components=[],  # Don't avoid anything in stress test
    )
    gen = DAGStructureGenerator(config)

    results = {
        "total_cards": 0,
        "successful": 0,
        "failed": 0,
        "components_tested": set(),
        "components_missing": set(),
        "errors": [],
        "cards": [],
    }

    async with httpx.AsyncClient(verify=False) as client:
        # Test batch 1: Basic Section widgets
        print("📦 Testing basic Section widgets...")
        basic_widgets = ["DecoratedText", "TextParagraph", "Image", "Divider", "ButtonList", "SelectionInput", "DateTimePicker"]
        for widget in basic_widgets:
            config.test_id = str(uuid.uuid4())[:8]
            try:
                structure = gen.generate_parameterized_structure(
                    "Section",
                    required_components=[widget],
                    fill_optional_probability=fill_probability,
                )
                card = gen.parameterized_structure_to_card(
                    structure,
                    title=f"Stress: {widget}",
                    subtitle=f"DSL: {structure.dsl}"
                )
                meta = card.pop("_dag_gen_meta", {})

                response = await client.post(webhook_url, json=card, timeout=30.0)
                results["total_cards"] += 1

                if response.status_code == 200:
                    results["successful"] += 1
                    results["components_tested"].update(structure.components)
                    print(f"  ✅ {widget}: {structure.dsl}")
                else:
                    results["failed"] += 1
                    results["errors"].append({
                        "widget": widget,
                        "dsl": structure.dsl,
                        "error": response.text[:100],
                    })
                    print(f"  ❌ {widget}: {response.text[:80]}")

                results["cards"].append({
                    "widget": widget,
                    "dsl": structure.dsl,
                    "success": response.status_code == 200,
                    "params": meta.get("parameter_stats", {}),
                })

            except Exception as e:
                results["failed"] += 1
                results["errors"].append({"widget": widget, "error": str(e)})
                print(f"  ❌ {widget}: {e}")

            await asyncio.sleep(delay_seconds)

        # Test batch 2: Complex nested structures
        print("\n🏗️ Testing complex nested structures...")
        complex_combos = [
            ["DecoratedText", "ButtonList", "Image"],
            ["Grid", "GridItem"],
            ["ChipList", "Chip"],
            ["Columns", "Column", "TextParagraph"],
        ]
        for combo in complex_combos:
            config.test_id = str(uuid.uuid4())[:8]
            try:
                structure = gen.generate_parameterized_structure(
                    "Section",
                    required_components=combo,
                    fill_optional_probability=fill_probability,
                )
                card = gen.parameterized_structure_to_card(
                    structure,
                    title=f"Complex: {'+'.join(combo[:2])}",
                    subtitle=f"DSL: {structure.dsl}"
                )
                meta = card.pop("_dag_gen_meta", {})

                response = await client.post(webhook_url, json=card, timeout=30.0)
                results["total_cards"] += 1

                if response.status_code == 200:
                    results["successful"] += 1
                    results["components_tested"].update(structure.components)
                    print(f"  ✅ {'+'.join(combo[:2])}: {structure.dsl}")
                else:
                    results["failed"] += 1
                    results["errors"].append({
                        "combo": combo,
                        "dsl": structure.dsl,
                        "error": response.text[:100],
                    })
                    print(f"  ❌ {'+'.join(combo[:2])}: {response.text[:80]}")

            except Exception as e:
                results["failed"] += 1
                results["errors"].append({"combo": combo, "error": str(e)})
                print(f"  ❌ {'+'.join(combo[:2])}: {e}")

            await asyncio.sleep(delay_seconds)

        # Test batch 3: Carousel
        print("\n🎠 Testing Carousel...")
        config.test_id = str(uuid.uuid4())[:8]
        try:
            card = gen.generate_carousel_card(num_carousel_items=4)
            meta = card.pop("_dag_gen_meta", {})

            response = await client.post(webhook_url, json=card, timeout=30.0)
            results["total_cards"] += 1

            if response.status_code == 200:
                results["successful"] += 1
                results["components_tested"].update(["Carousel", "CarouselCard", "NestedWidget"])
                print(f"  ✅ Carousel: {meta.get('dsl')}")
            else:
                results["failed"] += 1
                print(f"  ❌ Carousel: {response.text[:80]}")

        except Exception as e:
            results["failed"] += 1
            print(f"  ❌ Carousel: {e}")

    # Calculate coverage
    results["components_tested"] = set(results["components_tested"])
    results["components_missing"] = TESTABLE_COMPONENTS - results["components_tested"]
    coverage = len(results["components_tested"]) / len(TESTABLE_COMPONENTS) * 100

    # Summary
    print("\n" + "=" * 60)
    print(f"STRESS TEST COMPLETE")
    print("=" * 60)
    print(f"Cards: {results['successful']}/{results['total_cards']} successful")
    print(f"Coverage: {len(results['components_tested'])}/{len(TESTABLE_COMPONENTS)} components ({coverage:.1f}%)")
    print(f"\nTested: {sorted(results['components_tested'])}")
    if results["components_missing"]:
        print(f"Missing: {sorted(results['components_missing'])}")
    if results["errors"]:
        print(f"\nErrors ({len(results['errors'])}):")
        for err in results["errors"][:5]:
            print(f"  - {err}")

    return results


def run_dag_stress_test(
    webhook_url: str,
    fill_probability: float = 0.8,
) -> Dict[str, Any]:
    """
    Run comprehensive stress test covering ALL components.

    Args:
        webhook_url: Google Chat webhook URL
        fill_probability: Probability of filling optional fields

    Returns:
        Dict with test results and coverage stats
    """
    import asyncio
    return asyncio.run(run_stress_test(webhook_url, fill_probability))


def run_dag_smoke_test(
    webhook_url: str,
    count: int = 5,
    use_parameterized: bool = True,
) -> None:
    """
    Run a DAG-based smoke test against a webhook.

    Args:
        webhook_url: Google Chat webhook URL
        count: Number of cards to generate and send
        use_parameterized: Use full parameter generation (richer test values)
    """
    import asyncio

    mode = "parameterized" if use_parameterized else "basic"
    print(f"🔥 Running DAG smoke test ({mode}): {count} cards")
    print(f"   Webhook: {webhook_url[:50]}...")
    print()

    if use_parameterized:
        results = asyncio.run(send_parameterized_cards_to_webhook(
            webhook_url,
            count=count,
            include_carousel=True,
            fill_optional_probability=0.5,
        ))
    else:
        results = asyncio.run(send_dag_cards_to_webhook(
            webhook_url,
            count=count,
            include_carousel=True,
        ))

    # Summary
    success = sum(1 for r in results if r["success"])
    print()
    print("=" * 60)
    print(f"DAG SMOKE TEST: {success}/{len(results)} cards sent successfully")
    print("=" * 60)

    for r in results:
        status = "✅" if r["success"] else "❌"
        stats_str = ""
        if r.get("parameter_stats"):
            ps = r["parameter_stats"]
            stats_str = f" [{ps['with_values']}/{ps['total']} params]"
        print(f"  {status} #{r['index']}: {r['dsl']}{stats_str}")
        if r["error"]:
            print(f"      Error: {r['error'][:60]}")


# =============================================================================
# CLI ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    import json
    import os
    import sys

    # Check for webhook URL in args or env
    webhook_url = None
    count = 3

    if len(sys.argv) >= 2:
        webhook_url = sys.argv[1]
    else:
        webhook_url = os.environ.get("MCP_CHAT_WEBHOOK")

    if len(sys.argv) >= 3:
        count = int(sys.argv[2])

    if webhook_url:
        # Run smoke test with webhook (uses parameterized mode by default)
        run_dag_smoke_test(webhook_url, count, use_parameterized=True)
    else:
        # Demo mode - just print structures
        print("=== DAG Structure Generator Demo ===")
        print("(Set MCP_CHAT_WEBHOOK env var or pass URL to send cards)\n")

        gen = DAGStructureGenerator()

        # Generate random structures (basic)
        print("Generating random structures (basic)...\n")

        for i in range(3):
            structure = gen.generate_random_structure("Section")
            print(f"{i+1}. DSL: {structure.dsl}")
            print(f"   Components: {structure.components}")
            print(f"   Depth: {structure.depth}, Valid: {structure.is_valid}")
            print()

        # Generate parameterized structures
        print("\nGenerating parameterized structures...\n")

        for i in range(3):
            structure = gen.generate_parameterized_structure(
                "Section",
                fill_optional_probability=0.5,
            )
            print(f"{i+1}. DSL: {structure.dsl}")
            print(f"   Components: {structure.components}")
            print(f"   Parameters: {structure.parameters_with_values}/{structure.total_parameters} filled")
            print(f"   Using defaults: {structure.parameters_using_defaults}")
            print()

        # Generate a Carousel
        print("Generating Carousel structure...")
        carousel = gen.generate_random_structure("Carousel")
        print(f"   DSL: {carousel.dsl}")
        print(f"   Components: {carousel.components}")
        print()

        # Generate a parameterized card
        print("Generating parameterized card...")
        card = gen.generate_parameterized_card("Section", ["DecoratedText", "ButtonList"])
        meta = card.pop("_dag_gen_meta", {})

        print(f"\nCard DSL: {meta.get('dsl')}")
        print(f"Components: {meta.get('components')}")
        param_stats = meta.get("parameter_stats", {})
        print(f"Parameter stats: {param_stats.get('with_values', 0)}/{param_stats.get('total', 0)} filled")
        print("\nCard JSON (first section):")
        # Handle both snake_case and camelCase field names
        cards = card.get("cards_v2") or card.get("cardsV2") or []
        if cards:
            print(json.dumps(cards[0]["card"]["sections"][0], indent=2))
