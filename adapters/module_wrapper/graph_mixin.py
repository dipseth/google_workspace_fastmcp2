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
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

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
    """

    def __init__(self, *args, **kwargs):
        """Initialize graph-related attributes."""
        super().__init__(*args, **kwargs)
        self._relationship_graph = None
        self._graph_built = False

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
        node: str,
        depth: Optional[int] = None,
        include_self: bool = False,
    ) -> List[str]:
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
        node: str,
        include_self: bool = False,
    ) -> List[str]:
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

    def get_children(self, node: str) -> List[str]:
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

    def get_parents(self, node: str) -> List[str]:
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

    def get_path(self, source: str, target: str) -> List[str]:
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
        source: str,
        target: str,
        max_depth: Optional[int] = 10,
    ) -> List[List[str]]:
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

        Args:
            container: Container component name
            component: Component to check
            direct_only: If True, only check direct containment

        Returns:
            True if container can hold component

        Example:
            >>> wrapper.can_contain("Section", "Icon")
            True  # Via DecoratedText or Button
            >>> wrapper.can_contain("Section", "Icon", direct_only=True)
            False  # Section doesn't directly contain Icon
        """
        graph = self.get_relationship_graph()

        if container not in graph or component not in graph:
            return False

        if direct_only:
            return graph.has_edge(container, component)
        else:
            return component in self.get_descendants(container)

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


# Export for convenience
__all__ = [
    "GraphMixin",
    "_get_networkx",
]
