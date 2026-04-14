"""Module-agnostic builder protocol and component registry.

Defines the interface that domain-specific builders (gchat, email, etc.)
must implement. The protocol lives in the adapter layer and MUST NOT import
from any domain-specific package (gchat/, gmail/, etc.). This is enforced
by test_wrapper_agnostic.py.

Usage:
    from adapters.module_wrapper.builder_base import BuilderProtocol, ComponentRegistry

    class GchatCardBuilder:
        '''Implements BuilderProtocol for Google Chat cards.'''
        ...

    assert isinstance(GchatCardBuilder(), BuilderProtocol)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


# =============================================================================
# COMPONENT REGISTRY
# =============================================================================


@dataclass
class ComponentInfo:
    """Metadata for a single component in a domain's registry.

    Attributes:
        name: Component class name (e.g., "Button", "TextBlock")
        pool: Pool key this component belongs to (e.g., "buttons", "content")
        fields: Mapping of field name -> field type hint as string
        defaults: Default values for optional fields
        description: Human-readable description of the component
    """

    name: str
    pool: str
    fields: Dict[str, str] = field(default_factory=dict)
    defaults: Dict[str, Any] = field(default_factory=dict)
    description: str = ""


class ComponentRegistry:
    """Registry mapping component names to their metadata for a domain.

    Each domain (gchat, email, etc.) creates its own registry populated
    from its module wrapper's introspected components.

    Example:
        registry = ComponentRegistry(domain_id="gchat")
        registry.register(ComponentInfo(
            name="Button", pool="buttons",
            fields={"text": "str", "url": "str"},
            defaults={"url": ""},
        ))
        info = registry.get("Button")
    """

    def __init__(self, domain_id: str):
        self.domain_id = domain_id
        self._components: Dict[str, ComponentInfo] = {}

    def register(self, info: ComponentInfo) -> None:
        """Register a component."""
        self._components[info.name] = info

    def get(self, name: str) -> Optional[ComponentInfo]:
        """Get component info by name, or None if not registered."""
        return self._components.get(name)

    def list_components(self) -> List[str]:
        """List all registered component names."""
        return list(self._components.keys())

    def get_pool(self, name: str) -> Optional[str]:
        """Get the pool key for a component, or None."""
        info = self._components.get(name)
        return info.pool if info else None

    def components_for_pool(self, pool: str) -> List[str]:
        """List component names that belong to a given pool."""
        return [
            name
            for name, info in self._components.items()
            if info.pool == pool
        ]

    def __len__(self) -> int:
        return len(self._components)

    def __contains__(self, name: str) -> bool:
        return name in self._components


# =============================================================================
# PARSED STRUCTURE
# =============================================================================


@dataclass
class ParsedStructure:
    """Result of parsing a DSL description.

    Domain-agnostic representation of what components are needed
    and how content maps to them.

    Attributes:
        components: List of (component_name, count) tuples
        content_items: Mapping of pool_key -> list of content strings/dicts
        raw_dsl: The original DSL string (if any)
        metadata: Additional parse metadata (e.g., symbols found)
    """

    components: List[tuple] = field(default_factory=list)
    content_items: Dict[str, list] = field(default_factory=dict)
    raw_dsl: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


# =============================================================================
# BUILDER PROTOCOL
# =============================================================================


@runtime_checkable
class BuilderProtocol(Protocol):
    """Interface for domain-specific component builders.

    Each domain (gchat, email, etc.) implements this protocol to:
    1. Parse DSL descriptions into structured component demands
    2. Build supply maps mapping content to pool keys
    3. Use TRM scoring to reassign content to optimal slots
    4. Render individual components in the domain's format
    5. Assemble the final output

    The protocol ensures that the generic pipeline (SEARCH -> SCORE -> BUILD)
    can work with any domain without coupling to domain specifics.
    """

    @property
    def domain_id(self) -> str:
        """The domain identifier (e.g., 'gchat', 'email')."""
        ...

    @property
    def registry(self) -> ComponentRegistry:
        """The component registry for this domain."""
        ...

    def parse_dsl(self, description: str) -> Optional[ParsedStructure]:
        """Parse a DSL or natural-language description into structured demands.

        Args:
            description: DSL string or natural language description

        Returns:
            ParsedStructure with component demands and content items,
            or None if parsing fails.
        """
        ...

    def build_supply_map(
        self,
        parsed: ParsedStructure,
        **content_kwargs: Any,
    ) -> Dict[str, list]:
        """Build a supply map from parsed structure.

        Maps content items to pool keys based on domain rules.

        Args:
            parsed: The parsed DSL structure
            **content_kwargs: Additional content (e.g., extra items, overrides)

        Returns:
            Dict mapping pool_key -> list of content items
        """
        ...

    def reassign_slots(
        self,
        supply_map: Dict[str, list],
        demands: Dict[str, int],
    ) -> Dict[str, list]:
        """Use TRM scoring to reassign content across pools.

        Calls reassign_supply_map with the domain's DomainConfig.

        Args:
            supply_map: Current pool -> items mapping
            demands: Component name -> count demands from DSL

        Returns:
            Reassigned supply_map (new dict, original unchanged)
        """
        ...

    def render_component(self, name: str, params: Dict[str, Any]) -> Any:
        """Render a single component in the domain's output format.

        Args:
            name: Component class name
            params: Parameters for the component

        Returns:
            Domain-specific output (dict for gchat, MJML string for email, etc.)
        """
        ...

    def build(self, description: str, **kwargs: Any) -> Any:
        """Full pipeline: parse -> supply_map -> reassign -> render -> assemble.

        Args:
            description: DSL or natural language description
            **kwargs: Domain-specific options (title, feedback, etc.)

        Returns:
            Domain-specific output (card dict, EmailSpec, etc.)
        """
        ...
