"""
Graph-Based Relationship Mixin

Provides DAG (Directed Acyclic Graph) representation of component relationships
using NetworkX. This complements the existing dict-based relationships with
proper graph traversal capabilities.

Key Features:
    - Multi-hop traversal (Section → Widget → Button → Icon)
    - Path queries (all paths from Card to Icon)
    - Ancestor/descendant queries
    - Subgraph extraction for DSL validation
    - Cycle detection for relationship validation
    - Graph serialization for caching

Usage:
    wrapper = ModuleWrapper("card_framework.v2", auto_initialize=True)

    # Build graph from existing relationships
    wrapper.build_relationship_graph()

    # Traverse descendants
    widgets = wrapper.get_descendants("Section", depth=2)

    # Find all paths
    paths = wrapper.get_all_paths("Card", "Icon")

    # Check containment
    can_contain = wrapper.can_contain("Section", "Button")  # True (via ButtonList)
"""

import json
import logging
from typing import Any, Dict, List, Optional, Protocol, Set, Tuple, runtime_checkable

from adapters.module_wrapper.types import (
    ComponentName,
    Payload,
    RelationshipDict,
    ReverseSymbolMapping,
    SymbolMapping,
)

logger = logging.getLogger(__name__)


# =============================================================================
# COMPONENT METADATA PROTOCOL
# =============================================================================
# Defines the interface for component metadata queries.
# Any class implementing this protocol can be used as a metadata provider.


@runtime_checkable
class ComponentMetadataProvider(Protocol):
    """Protocol for component metadata queries.

    This defines the interface that ModuleWrapper (via GraphMixin) implements.
    SmartCardBuilder and other consumers should type-hint against this protocol.
    """

    def get_context_resource(self, component: str) -> Optional[Tuple[str, str]]:
        """Get (context_key, index_key) for a component's resource consumption."""
        ...

    def get_children_field(self, container: str) -> Optional[str]:
        """Get JSON field name where container stores children."""
        ...

    def get_container_child_type(self, container: str) -> Optional[str]:
        """Get expected child type for a homogeneous container."""
        ...

    def get_required_wrapper(self, component: str) -> Optional[str]:
        """Get required wrapper parent for a component."""
        ...

    def is_widget_type(self, component: str) -> bool:
        """Check if component is a valid widget type."""
        ...

    def is_form_component(self, component: str) -> bool:
        """Check if component is a form component."""
        ...

    def is_empty_component(self, component: str) -> bool:
        """Check if component is empty (no content params)."""
        ...

# Lazy import for NetworkX
_networkx = None


def _get_networkx():
    """Lazy load NetworkX to avoid import overhead."""
    global _networkx
    if _networkx is None:
        try:
            import networkx as nx
            _networkx = nx
            logger.debug("NetworkX loaded successfully")
        except ImportError:
            logger.warning(
                "NetworkX not installed. Install with: pip install networkx"
            )
            raise
    return _networkx


class GraphMixin:
    """
    Mixin providing DAG-based relationship representation.

    Expects the following attributes on self:
    - relationships: Dict[str, List[str]] (parent → children)
    - symbol_mapping: Dict[str, str] (component → symbol)
    - reverse_symbol_mapping: Dict[str, str] (symbol → component)
    - components: Dict[str, ModuleComponent]

    This is a GENERAL-PURPOSE mixin for any Python module's component graph.

    Provides:
    1. DAG construction and traversal (get_children, get_descendants, can_contain, etc.)
    2. Component metadata registry (register_*, get_*) for domain-specific metadata

    Domain-specific wrappers (e.g., card_framework_wrapper.py) should:
    1. Call register_* methods to populate component metadata
    2. Query via get_* methods
    """

    def __init__(self, *args, **kwargs):
        """Initialize graph-related attributes."""
        super().__init__(*args, **kwargs)
        self._relationship_graph = None
        self._graph_built = False

        # Component metadata registries (populated by domain-specific wrappers)
        self._context_resources: Dict[str, Tuple[str, str]] = {}  # component → (context_key, index_key)
        self._container_children_field: Dict[str, str] = {}  # container → json_field_name
        self._container_child_type: Dict[str, str] = {}  # container → expected_child_type
        self._required_wrappers: Dict[str, str] = {}  # child → required_wrapper_parent
        self._widget_types: Set[str] = set()  # valid widget types (can be children of heterogeneous containers)
        self._heterogeneous_containers: Set[str] = set()  # containers that can hold any widget_type
        self._form_components: Set[str] = set()  # components needing 'name' field
        self._empty_components: Set[str] = set()  # components with no content params

    # =========================================================================
    # GRAPH CONSTRUCTION
    # =========================================================================

    def build_relationship_graph(self, force: bool = False) -> "nx.DiGraph":
        """
        Build a NetworkX DiGraph from the existing relationships dict.

        The graph represents containment relationships where an edge from
        A → B means "A can contain B".

        Args:
            force: Rebuild even if graph already exists

        Returns:
            NetworkX DiGraph with component nodes and containment edges
        """
        if self._graph_built and not force:
            return self._relationship_graph

        nx = _get_networkx()

        # Create directed graph
        self._relationship_graph = nx.DiGraph()

        # Get relationships (may need to extract if not already done)
        relationships = getattr(self, "relationships", {})
        if not relationships and hasattr(self, "extract_relationships"):
            self.extract_relationships()
            relationships = getattr(self, "relationships", {})

        if not relationships:
            logger.warning("No relationships found to build graph")
            return self._relationship_graph

        # Add nodes and edges
        symbol_mapping = getattr(self, "symbol_mapping", {})
        components = getattr(self, "components", {})

        # First pass: add all nodes
        all_components = set(relationships.keys())
        for children in relationships.values():
            all_components.update(children)

        for comp_name in all_components:
            # Get component metadata
            node_attrs = {
                "name": comp_name,
                "symbol": symbol_mapping.get(comp_name, ""),
            }

            # Try to get component type from components dict
            for path, comp in components.items():
                if comp.name == comp_name:
                    node_attrs["type"] = comp.component_type
                    node_attrs["full_path"] = path
                    node_attrs["docstring"] = (comp.docstring or "")[:200]
                    break

            self._relationship_graph.add_node(comp_name, **node_attrs)

        # Second pass: add edges (containment relationships)
        for parent, children in relationships.items():
            for child in children:
                self._relationship_graph.add_edge(
                    parent,
                    child,
                    type="contains",
                )

        self._graph_built = True

        logger.info(
            f"Built relationship graph: {self._relationship_graph.number_of_nodes()} nodes, "
            f"{self._relationship_graph.number_of_edges()} edges"
        )

        return self._relationship_graph

    def add_relationships_to_graph(
        self,
        relationships: Dict[str, List[str]],
        edge_type: str = "contains",
    ) -> int:
        """
        Add additional relationships to the existing graph.

        This is useful for merging custom widget hierarchies (like Section → DecoratedText)
        with the type-annotation-based relationships.

        Args:
            relationships: Dict mapping parent → list of children
            edge_type: Type label for the edges

        Returns:
            Number of edges added

        Example:
            >>> wrapper.add_relationships_to_graph({
            ...     "Section": ["DecoratedText", "ButtonList", "Image"],
            ...     "ButtonList": ["Button"],
            ... })
        """
        if not self._graph_built:
            self.build_relationship_graph()

        graph = self._relationship_graph
        symbol_mapping = getattr(self, "symbol_mapping", {})
        edges_added = 0

        for parent, children in relationships.items():
            # Ensure parent node exists
            if parent not in graph:
                graph.add_node(
                    parent,
                    name=parent,
                    symbol=symbol_mapping.get(parent, ""),
                )

            for child in children:
                # Ensure child node exists
                if child not in graph:
                    graph.add_node(
                        child,
                        name=child,
                        symbol=symbol_mapping.get(child, ""),
                    )

                # Add edge if it doesn't exist
                if not graph.has_edge(parent, child):
                    graph.add_edge(parent, child, type=edge_type)
                    edges_added += 1

        if edges_added > 0:
            logger.info(f"Added {edges_added} edges to relationship graph")

        return edges_added

    def get_relationship_graph(self) -> "nx.DiGraph":
        """
        Get the relationship graph, building it if necessary.

        Returns:
            NetworkX DiGraph
        """
        if not self._graph_built:
            self.build_relationship_graph()
        return self._relationship_graph

    # =========================================================================
    # TRAVERSAL METHODS
    # =========================================================================

    def get_descendants(
        self,
        node: ComponentName,
        depth: Optional[int] = None,
        include_self: bool = False,
    ) -> List[ComponentName]:
        """
        Get all components that can be contained within a component (recursively).

        This answers: "What can Section contain at any nesting level?"

        Args:
            node: Component name (e.g., "Section")
            depth: Maximum traversal depth (None = unlimited)
            include_self: Whether to include the starting node

        Returns:
            List of descendant component names

        Example:
            >>> wrapper.get_descendants("Section", depth=2)
            ['DecoratedText', 'ButtonList', 'Image', 'Button', 'Icon', ...]
        """
        nx = _get_networkx()
        graph = self.get_relationship_graph()

        if node not in graph:
            logger.warning(f"Node '{node}' not found in relationship graph")
            return []

        if depth is not None:
            # BFS with depth limit
            descendants = list(nx.bfs_tree(graph, node, depth_limit=depth).nodes())
        else:
            # All descendants
            descendants = [node] + list(nx.descendants(graph, node))

        if not include_self and node in descendants:
            descendants.remove(node)

        return descendants

    def get_ancestors(
        self,
        node: ComponentName,
        include_self: bool = False,
    ) -> List[ComponentName]:
        """
        Get all components that can contain this component.

        This answers: "What containers can hold a Button?"

        Args:
            node: Component name (e.g., "Button")
            include_self: Whether to include the starting node

        Returns:
            List of ancestor component names

        Example:
            >>> wrapper.get_ancestors("Button")
            ['ButtonList', 'DecoratedText', 'Section', 'Card']
        """
        nx = _get_networkx()
        graph = self.get_relationship_graph()

        if node not in graph:
            logger.warning(f"Node '{node}' not found in relationship graph")
            return []

        ancestors = list(nx.ancestors(graph, node))

        if include_self:
            ancestors = [node] + ancestors

        return ancestors

    def get_children(self, node: ComponentName) -> List[ComponentName]:
        """
        Get direct children of a component (one level only).

        Args:
            node: Component name

        Returns:
            List of direct child component names
        """
        graph = self.get_relationship_graph()

        if node not in graph:
            return []

        return list(graph.successors(node))

    def get_parents(self, node: ComponentName) -> List[ComponentName]:
        """
        Get direct parents of a component (one level only).

        Args:
            node: Component name

        Returns:
            List of direct parent component names
        """
        graph = self.get_relationship_graph()

        if node not in graph:
            return []

        return list(graph.predecessors(node))

    # =========================================================================
    # PATH QUERIES
    # =========================================================================

    def get_path(self, source: ComponentName, target: ComponentName) -> List[ComponentName]:
        """
        Get the shortest containment path from source to target.

        This answers: "How does Icon end up inside Section?"

        Args:
            source: Starting component (container)
            target: Ending component (contained)

        Returns:
            List of components in the path, or empty list if no path exists

        Example:
            >>> wrapper.get_path("Section", "Icon")
            ['Section', 'DecoratedText', 'Icon']
        """
        nx = _get_networkx()
        graph = self.get_relationship_graph()

        if source not in graph or target not in graph:
            return []

        try:
            return nx.shortest_path(graph, source, target)
        except nx.NetworkXNoPath:
            return []

    def get_all_paths(
        self,
        source: ComponentName,
        target: ComponentName,
        max_depth: Optional[int] = 10,
    ) -> List[List[ComponentName]]:
        """
        Get all possible containment paths from source to target.

        This answers: "All the ways Button can appear inside Card"

        Args:
            source: Starting component (container)
            target: Ending component (contained)
            max_depth: Maximum path length to prevent infinite loops

        Returns:
            List of paths, where each path is a list of component names

        Example:
            >>> wrapper.get_all_paths("Section", "Icon")
            [
                ['Section', 'DecoratedText', 'Icon'],
                ['Section', 'ButtonList', 'Button', 'Icon'],
                ['Section', 'Chip', 'Icon'],
            ]
        """
        nx = _get_networkx()
        graph = self.get_relationship_graph()

        if source not in graph or target not in graph:
            return []

        try:
            paths = list(nx.all_simple_paths(
                graph, source, target, cutoff=max_depth
            ))
            return paths
        except nx.NetworkXNoPath:
            return []

    def get_path_with_symbols(self, source: str, target: str) -> str:
        """
        Get the shortest path as a DSL-like string.

        Args:
            source: Starting component
            target: Ending component

        Returns:
            DSL-style path string

        Example:
            >>> wrapper.get_path_with_symbols("Section", "Icon")
            "§ → δ → Ɨ"
        """
        path = self.get_path(source, target)
        if not path:
            return ""

        symbol_mapping = getattr(self, "symbol_mapping", {})
        symbols = [symbol_mapping.get(comp, comp) for comp in path]
        return " → ".join(symbols)

    # =========================================================================
    # CONTAINMENT QUERIES
    # =========================================================================

    def can_contain(
        self,
        container: str,
        component: str,
        direct_only: bool = False,
    ) -> bool:
        """
        Check if a container can hold a component (directly or nested).

        Uses both DAG relationships and registered metadata:
        - Heterogeneous containers (Section, Column) can hold any widget_type
        - Components requiring wrappers are valid if the wrapper is valid

        Args:
            container: Container component name
            component: Component to check
            direct_only: If True, only check direct containment

        Returns:
            True if container can hold component

        Example:
            >>> wrapper.can_contain("Section", "DecoratedText")
            True  # Section is heterogeneous, DecoratedText is widget_type
            >>> wrapper.can_contain("Section", "Icon")
            True  # Via DecoratedText or Button
            >>> wrapper.can_contain("Section", "Icon", direct_only=True)
            False  # Section doesn't directly contain Icon
        """
        graph = self.get_relationship_graph()

        # Check graph-based containment
        container_in_graph = container in graph
        component_in_graph = component in graph

        if direct_only:
            # Direct containment: check graph edge or heterogeneous container
            if container_in_graph and component_in_graph:
                if graph.has_edge(container, component):
                    return True
            # Heterogeneous containers can directly contain widget types
            if container in self._heterogeneous_containers and component in self._widget_types:
                return True
            return False

        # Non-direct (nested) containment checks
        # 1. Check if heterogeneous container can hold widget type directly
        if container in self._heterogeneous_containers and component in self._widget_types:
            return True

        # 2. Check if component needs a wrapper that container can hold
        if component in self._required_wrappers:
            wrapper = self._required_wrappers[component]
            if self.can_contain(container, wrapper, direct_only=False):
                return True

        # 3. Check graph descendants for nested containment
        if container_in_graph and component_in_graph:
            if component in self.get_descendants(container):
                return True

        # 4. Check if any widget type that container can hold can itself contain component
        if container in self._heterogeneous_containers:
            for widget_type in self._widget_types:
                if widget_type in graph and component_in_graph:
                    if component in self.get_descendants(widget_type):
                        return True

        return False

    def get_common_ancestors(self, *nodes: str) -> List[str]:
        """
        Find components that can contain all specified components.

        This answers: "What container can hold both Button AND Image?"

        Args:
            *nodes: Component names to find common ancestors for

        Returns:
            List of common ancestor component names

        Example:
            >>> wrapper.get_common_ancestors("Button", "Image")
            ['Section', 'Card']
        """
        nx = _get_networkx()
        graph = self.get_relationship_graph()

        if not nodes:
            return []

        # Get ancestors for each node
        ancestor_sets = []
        for node in nodes:
            if node in graph:
                ancestor_sets.append(set(nx.ancestors(graph, node)))
            else:
                return []  # Node not found

        # Find intersection
        common = ancestor_sets[0]
        for ancestors in ancestor_sets[1:]:
            common = common.intersection(ancestors)

        return list(common)

    # =========================================================================
    # SUBGRAPH EXTRACTION
    # =========================================================================

    def get_subgraph(
        self,
        root: str,
        depth: Optional[int] = None,
    ) -> "nx.DiGraph":
        """
        Extract a subgraph starting from a root node.

        Useful for getting just the widgets relevant to a Section, for example.

        Args:
            root: Root component to start from
            depth: Maximum depth (None = full subtree)

        Returns:
            NetworkX DiGraph containing the subgraph
        """
        nx = _get_networkx()
        graph = self.get_relationship_graph()

        if root not in graph:
            return nx.DiGraph()

        descendants = self.get_descendants(root, depth=depth, include_self=True)
        return graph.subgraph(descendants).copy()

    def get_component_neighborhood(
        self,
        node: str,
        radius: int = 1,
    ) -> "nx.DiGraph":
        """
        Get the neighborhood around a component (both parents and children).

        Args:
            node: Center component
            radius: How many hops in each direction

        Returns:
            NetworkX DiGraph of the neighborhood
        """
        nx = _get_networkx()
        graph = self.get_relationship_graph()

        if node not in graph:
            return nx.DiGraph()

        # Get nodes within radius (undirected for neighborhood)
        undirected = graph.to_undirected()
        neighborhood_nodes = nx.single_source_shortest_path_length(
            undirected, node, cutoff=radius
        ).keys()

        return graph.subgraph(neighborhood_nodes).copy()

    # =========================================================================
    # VALIDATION
    # =========================================================================

    def validate_containment_chain(
        self, component_sequence: List[str]
    ) -> Tuple[bool, List[str]]:
        """
        Validate that a sequence of components forms a valid containment chain.

        This is useful for validating DSL structures like §[δ, Ƀ[ᵬ]]

        Args:
            component_sequence: List of components in nesting order
                e.g., ["Section", "DecoratedText"] or ["Section", "ButtonList", "Button"]

        Returns:
            Tuple of (is_valid, list of issues)

        Example:
            >>> wrapper.validate_containment_chain(["Section", "ButtonList", "Button"])
            (True, [])
            >>> wrapper.validate_containment_chain(["Button", "Section"])
            (False, ["Button cannot contain Section"])
        """
        if len(component_sequence) < 2:
            return True, []

        issues = []
        for i in range(len(component_sequence) - 1):
            parent = component_sequence[i]
            child = component_sequence[i + 1]

            if not self.can_contain(parent, child, direct_only=True):
                issues.append(f"{parent} cannot directly contain {child}")

        return len(issues) == 0, issues

    def has_cycles(self) -> bool:
        """
        Check if the relationship graph has any cycles.

        A cycle would indicate an invalid relationship (A contains B contains A).

        Returns:
            True if cycles exist (invalid state)
        """
        nx = _get_networkx()
        graph = self.get_relationship_graph()

        try:
            nx.find_cycle(graph)
            return True
        except nx.NetworkXNoCycle:
            return False

    def find_cycles(self) -> List[List[str]]:
        """
        Find all cycles in the relationship graph.

        Returns:
            List of cycles, where each cycle is a list of edges
        """
        nx = _get_networkx()
        graph = self.get_relationship_graph()

        try:
            cycle = nx.find_cycle(graph)
            return [list(cycle)]
        except nx.NetworkXNoCycle:
            return []

    # =========================================================================
    # GRAPH ANALYSIS
    # =========================================================================

    def get_root_components(self) -> List[str]:
        """
        Get components that have no parents (top-level containers).

        Returns:
            List of root component names (e.g., ["Card"])
        """
        graph = self.get_relationship_graph()
        return [node for node in graph.nodes() if graph.in_degree(node) == 0]

    def get_leaf_components(self) -> List[str]:
        """
        Get components that have no children (cannot contain anything).

        Returns:
            List of leaf component names (e.g., ["Icon", "Divider"])
        """
        graph = self.get_relationship_graph()
        return [node for node in graph.nodes() if graph.out_degree(node) == 0]

    def get_hub_components(self, min_connections: int = 5) -> List[Tuple[str, int]]:
        """
        Get components with many connections (important in the hierarchy).

        Args:
            min_connections: Minimum in+out degree to be considered a hub

        Returns:
            List of (component_name, connection_count) tuples, sorted by count
        """
        graph = self.get_relationship_graph()
        hubs = []

        for node in graph.nodes():
            degree = graph.in_degree(node) + graph.out_degree(node)
            if degree >= min_connections:
                hubs.append((node, degree))

        return sorted(hubs, key=lambda x: x[1], reverse=True)

    def get_graph_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the relationship graph.

        Returns:
            Dict with graph statistics
        """
        nx = _get_networkx()
        graph = self.get_relationship_graph()

        return {
            "nodes": graph.number_of_nodes(),
            "edges": graph.number_of_edges(),
            "roots": len(self.get_root_components()),
            "leaves": len(self.get_leaf_components()),
            "is_dag": nx.is_directed_acyclic_graph(graph),
            "density": nx.density(graph),
            "avg_out_degree": sum(d for _, d in graph.out_degree()) / max(graph.number_of_nodes(), 1),
        }

    # =========================================================================
    # SERIALIZATION
    # =========================================================================

    def graph_to_dict(self) -> Dict[str, Any]:
        """
        Serialize the relationship graph to a dictionary.

        Returns:
            Dict representation suitable for JSON serialization
        """
        nx = _get_networkx()
        graph = self.get_relationship_graph()

        return {
            "nodes": [
                {"name": node, **graph.nodes[node]}
                for node in graph.nodes()
            ],
            "edges": [
                {"source": u, "target": v, **graph.edges[u, v]}
                for u, v in graph.edges()
            ],
            "stats": self.get_graph_stats(),
        }

    def graph_to_json(self, indent: int = 2) -> str:
        """
        Serialize the relationship graph to JSON.

        Args:
            indent: JSON indentation level

        Returns:
            JSON string
        """
        return json.dumps(self.graph_to_dict(), indent=indent, default=str)

    def load_graph_from_dict(self, data: Dict[str, Any]) -> "nx.DiGraph":
        """
        Load a relationship graph from a dictionary.

        Args:
            data: Dict with "nodes" and "edges" keys

        Returns:
            NetworkX DiGraph
        """
        nx = _get_networkx()

        self._relationship_graph = nx.DiGraph()

        for node_data in data.get("nodes", []):
            name = node_data.pop("name")
            self._relationship_graph.add_node(name, **node_data)

        for edge_data in data.get("edges", []):
            source = edge_data.pop("source")
            target = edge_data.pop("target")
            self._relationship_graph.add_edge(source, target, **edge_data)

        self._graph_built = True
        return self._relationship_graph

    # =========================================================================
    # VISUALIZATION (Optional)
    # =========================================================================

    def print_tree(
        self,
        root: Optional[str] = None,
        max_depth: int = 3,
        use_symbols: bool = True,
    ) -> str:
        """
        Print a text representation of the component tree.

        Args:
            root: Starting component (defaults to first root found)
            max_depth: Maximum depth to display
            use_symbols: Use DSL symbols instead of names

        Returns:
            Tree string representation
        """
        graph = self.get_relationship_graph()
        symbol_mapping = getattr(self, "symbol_mapping", {})

        if root is None:
            roots = self.get_root_components()
            if not roots:
                return "No root components found"
            root = roots[0]

        lines = []

        def _build_tree(node: str, prefix: str, depth: int):
            if depth > max_depth:
                return

            display = symbol_mapping.get(node, node) if use_symbols else node
            lines.append(f"{prefix}{display}")

            children = list(graph.successors(node))
            for i, child in enumerate(children):
                is_last = i == len(children) - 1
                child_prefix = prefix.replace("├── ", "│   ").replace("└── ", "    ")
                connector = "└── " if is_last else "├── "
                _build_tree(child, child_prefix + connector, depth + 1)

        _build_tree(root, "", 0)
        return "\n".join(lines)


    # =========================================================================
    # COMPONENT METADATA REGISTRATION (General-Purpose)
    # =========================================================================
    # Domain-specific wrappers call these to register their component metadata.
    # Example: card_framework_wrapper registers Button→("buttons", "_button_index")

    def register_context_resource(
        self, component: str, context_key: str, index_key: str
    ) -> None:
        """
        Register what context resource a component consumes.

        Args:
            component: Component name (e.g., "Button")
            context_key: Context dict key (e.g., "buttons")
            index_key: Index tracking key (e.g., "_button_index")

        Example:
            >>> wrapper.register_context_resource("Button", "buttons", "_button_index")
            >>> wrapper.register_context_resource("Chip", "chips", "_chip_index")
        """
        self._context_resources[component] = (context_key, index_key)
        logger.debug(f"Registered context resource: {component} → {context_key}")

    def register_container(
        self,
        container: str,
        children_field: str,
        child_type: Optional[str] = None,
    ) -> None:
        """
        Register a container component's structure.

        Args:
            container: Container name (e.g., "ButtonList")
            children_field: JSON field for children (e.g., "buttons")
            child_type: Expected child type if homogeneous (e.g., "Button")

        Example:
            >>> wrapper.register_container("ButtonList", "buttons", "Button")
            >>> wrapper.register_container("Section", "widgets")  # heterogeneous
        """
        self._container_children_field[container] = children_field
        if child_type:
            self._container_child_type[container] = child_type
        logger.debug(f"Registered container: {container}.{children_field} → {child_type}")

    def register_wrapper_requirement(self, child: str, wrapper: str) -> None:
        """
        Register that a component requires a wrapper parent.

        Args:
            child: Child component name (e.g., "Button")
            wrapper: Required wrapper parent (e.g., "ButtonList")

        Example:
            >>> wrapper.register_wrapper_requirement("Button", "ButtonList")
            >>> wrapper.register_wrapper_requirement("Chip", "ChipList")
        """
        self._required_wrappers[child] = wrapper
        logger.debug(f"Registered wrapper requirement: {child} → {wrapper}")

    def register_widget_type(self, component: str) -> None:
        """Register a component as a valid widget type."""
        self._widget_types.add(component)

    def register_form_component(self, component: str) -> None:
        """Register a component as a form component (needs 'name' field)."""
        self._form_components.add(component)

    def register_empty_component(self, component: str) -> None:
        """Register a component as empty (no content params)."""
        self._empty_components.add(component)

    def register_component_metadata_batch(
        self,
        context_resources: Optional[Dict[str, Tuple[str, str]]] = None,
        containers: Optional[Dict[str, Tuple[str, Optional[str]]]] = None,
        wrapper_requirements: Optional[Dict[str, str]] = None,
        widget_types: Optional[Set[str]] = None,
        heterogeneous_containers: Optional[Set[str]] = None,
        form_components: Optional[Set[str]] = None,
        empty_components: Optional[Set[str]] = None,
    ) -> None:
        """
        Register multiple component metadata entries at once.

        Args:
            context_resources: {component: (context_key, index_key)}
            containers: {container: (children_field, child_type)}
            wrapper_requirements: {child: wrapper}
            widget_types: Set of widget type names (valid children for heterogeneous containers)
            heterogeneous_containers: Set of containers that can hold any widget_type
            form_components: Set of form component names
            empty_components: Set of empty component names

        Example:
            >>> wrapper.register_component_metadata_batch(
            ...     context_resources={
            ...         "Button": ("buttons", "_button_index"),
            ...         "Chip": ("chips", "_chip_index"),
            ...     },
            ...     containers={
            ...         "ButtonList": ("buttons", "Button"),
            ...         "Section": ("widgets", None),
            ...     },
            ...     wrapper_requirements={
            ...         "Button": "ButtonList",
            ...         "Chip": "ChipList",
            ...     },
            ...     widget_types={"DecoratedText", "ButtonList", "Image"},
            ...     heterogeneous_containers={"Section", "Column"},
            ... )
        """
        if context_resources:
            for comp, (ctx_key, idx_key) in context_resources.items():
                self.register_context_resource(comp, ctx_key, idx_key)

        if containers:
            for container, (field, child_type) in containers.items():
                self.register_container(container, field, child_type)

        if wrapper_requirements:
            for child, wrapper in wrapper_requirements.items():
                self.register_wrapper_requirement(child, wrapper)

        if widget_types:
            self._widget_types.update(widget_types)

        if heterogeneous_containers:
            self._heterogeneous_containers.update(heterogeneous_containers)

        if form_components:
            self._form_components.update(form_components)

        if empty_components:
            self._empty_components.update(empty_components)

        logger.info(
            f"Registered component metadata batch: "
            f"{len(context_resources or {})} resources, "
            f"{len(containers or {})} containers, "
            f"{len(wrapper_requirements or {})} wrappers"
        )

    # =========================================================================
    # COMPONENT METADATA QUERIES (General-Purpose)
    # =========================================================================

    def get_context_resource(self, component: str) -> Optional[Tuple[str, str]]:
        """
        Get what context resource a component consumes.

        Returns:
            Tuple of (context_key, index_key) or None
        """
        return self._context_resources.get(component)

    def get_children_field(self, container: str) -> Optional[str]:
        """
        Get the JSON field name where container stores children.

        Returns:
            Field name (e.g., "buttons", "widgets") or None
        """
        return self._container_children_field.get(container)

    def get_container_child_type(self, container: str) -> Optional[str]:
        """
        Get the expected child type for a homogeneous container.

        Returns:
            Child type name or None if container is heterogeneous
        """
        return self._container_child_type.get(container)

    def get_required_wrapper(self, component: str) -> Optional[str]:
        """
        Get the wrapper parent required for a component.

        Returns:
            Wrapper name or None if no wrapper needed
        """
        return self._required_wrappers.get(component)

    def get_widget_types(self) -> Set[str]:
        """Get all registered widget types."""
        return self._widget_types.copy()

    def is_widget_type(self, component: str) -> bool:
        """Check if component is a registered widget type."""
        return component in self._widget_types

    def is_form_component(self, component: str) -> bool:
        """Check if component is a form component."""
        return component in self._form_components

    def is_empty_component(self, component: str) -> bool:
        """Check if component is empty (no content params)."""
        return component in self._empty_components

    def is_container(self, component: str) -> bool:
        """Check if component is a registered container."""
        return component in self._container_children_field

    def get_all_context_resources(self) -> Dict[str, Tuple[str, str]]:
        """Get all registered context resources."""
        return self._context_resources.copy()

    def get_all_containers(self) -> Dict[str, str]:
        """Get all registered containers with their children fields."""
        return self._container_children_field.copy()

    def get_all_wrapper_requirements(self) -> Dict[str, str]:
        """Get all registered wrapper requirements."""
        return self._required_wrappers.copy()

    # =========================================================================
    # SYMBOL RESOLUTION IN CONTEXT
    # =========================================================================

    def resolve_symbol_in_context(
        self,
        symbol: str,
        parent_component: str,
        symbol_mapping: Optional[Dict[str, str]] = None,
        reverse_symbol_mapping: Optional[Dict[str, str]] = None,
    ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """
        Resolve a symbol to a valid component for a given parent context.

        If the symbol maps to a component that isn't valid for the parent,
        uses the DAG to find the closest valid match.

        Args:
            symbol: The DSL symbol (e.g., "ℬ")
            parent_component: The parent context (e.g., "Section")
            symbol_mapping: Optional {component_name: symbol} mapping
            reverse_symbol_mapping: Optional {symbol: component_name} mapping

        Returns:
            Tuple of (resolved_component, suggested_symbol, suggestion_message)
            - resolved_component: The component name (original or closest match)
            - suggested_symbol: The correct symbol if different from input
            - suggestion_message: Human-readable suggestion if correction needed

        Example:
            >>> wrapper.resolve_symbol_in_context("ℬ", "Section")
            ("ButtonList", "Ƀ", "ℬ (BorderType) invalid in Section; use Ƀ (ButtonList)")
        """
        # Get mappings from self if not provided
        if symbol_mapping is None:
            symbol_mapping = getattr(self, "symbol_mapping", {})
        if reverse_symbol_mapping is None:
            reverse_symbol_mapping = getattr(self, "reverse_symbol_mapping", {})

        # Resolve symbol to component name
        component = reverse_symbol_mapping.get(symbol, symbol)

        # Get valid children for parent (uses DAG + registered widget types)
        valid_children = self.get_valid_children_for_parent(parent_component)

        # Check if component is valid in this context
        if component in valid_children:
            return (component, None, None)  # Valid, no correction needed

        # Component is invalid - find closest valid match
        if not valid_children:
            return (component, None, f"No valid children for {parent_component}")

        # Score candidates by similarity to the invalid component
        def similarity_score(candidate: str) -> float:
            score = 0.0

            # 1. Symbol visual similarity (same starting character)
            cand_symbol = symbol_mapping.get(candidate, "")
            if cand_symbol and symbol:
                # Check if symbols look similar (same Unicode block or starting letter)
                if cand_symbol[0].lower() == symbol[0].lower():
                    score += 3.0
                # Check similar category (both uppercase, both lowercase, etc.)
                if cand_symbol[0].isupper() == symbol[0].isupper():
                    score += 1.0

            # 2. Name similarity (same starting letter, same suffix)
            if candidate[0].lower() == component[0].lower():
                score += 2.0
            if candidate.endswith("List") and component.endswith("Type"):
                score += 1.5  # Common confusion: BorderType vs ButtonList
            if candidate.endswith("List") and "List" not in component:
                # Prefer list containers when user used non-list
                score += 0.5

            # 3. Functional similarity (both containers, both have children)
            if self.is_container(candidate) and self.is_container(component):
                score += 1.0

            return score

        # Sort candidates by score
        scored = [(c, similarity_score(c)) for c in valid_children]
        scored.sort(key=lambda x: (-x[1], x[0]))  # Highest score first, then alpha

        best_match = scored[0][0] if scored else None

        if best_match:
            best_symbol = symbol_mapping.get(best_match, best_match[0])
            suggestion = (
                f"{symbol} ({component}) invalid in {parent_component}; "
                f"use {best_symbol} ({best_match})"
            )
            return (best_match, best_symbol, suggestion)

        return (component, None, f"{component} invalid in {parent_component}")

    def get_valid_children_for_parent(self, parent: str) -> List[str]:
        """
        Get all valid direct children for a parent component.

        Combines DAG relationships with widget types for heterogeneous containers.

        Args:
            parent: Parent component name

        Returns:
            List of valid child component names
        """
        valid = set(self.get_children(parent))

        # Heterogeneous containers can contain any registered widget type
        if parent in self._heterogeneous_containers:
            valid |= self._widget_types

        return sorted(valid)

    def register_heterogeneous_container(self, container: str) -> None:
        """
        Register a container that can hold any widget type.

        Args:
            container: Container component name (e.g., "Section", "Column")
        """
        self._heterogeneous_containers.add(container)

    def get_heterogeneous_containers(self) -> Set[str]:
        """Get all registered heterogeneous containers."""
        return self._heterogeneous_containers.copy()


# Export for convenience
__all__ = [
    "GraphMixin",
    "ComponentMetadataProvider",
    "_get_networkx",
]
