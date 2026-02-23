"""
Tool Relationship Graph

Provides a rustworkx PyDiGraph tracking tool co-occurrence patterns
across sessions. Used by BehavioralRelationshipStrategy to generate
relationship text for the RIC embedding pipeline.

Nodes: One per unique tool_name (~50 tools)
Edges: Temporal succession within sessions (A -> B = A called before B)

Graph analysis (all via rustworkx):
    - k-core membership per tool
    - betweenness/closeness centrality
    - predecessor/successor frequency
    - cycle detection for recurring tool loops
"""

import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

# Lazy rustworkx import (reuse pattern from graph_mixin.py)
_rustworkx = None


def _get_rustworkx():
    """Lazy load rustworkx."""
    global _rustworkx
    if _rustworkx is None:
        import rustworkx as rx
        _rustworkx = rx
    return _rustworkx


@dataclass
class ToolNodeData:
    """Attributes stored on each tool node."""

    tool_name: str
    service: str = ""
    first_seen: float = 0.0
    call_count: int = 0
    total_execution_ms: float = 0.0

    @property
    def avg_execution_ms(self) -> float:
        if self.call_count == 0:
            return 0.0
        return self.total_execution_ms / self.call_count


@dataclass
class ToolEdgeData:
    """Attributes stored on each co-occurrence edge."""

    co_occurrence_count: int = 0
    total_time_delta_ms: float = 0.0
    sessions_seen_in: Set[str] = field(default_factory=set)

    @property
    def avg_time_delta_ms(self) -> float:
        if self.co_occurrence_count == 0:
            return 0.0
        return self.total_time_delta_ms / self.co_occurrence_count


class ToolRelationshipGraph:
    """
    Rustworkx-based directed graph tracking tool co-occurrence.

    Usage:
        graph = ToolRelationshipGraph()

        # Record tool calls in a session
        graph.record_tool_call("list_spaces", "chat", session_id="s1")
        graph.record_tool_call("send_message", "chat", session_id="s1")

        # Get relationship text for embedding
        text = graph.get_relationship_text("send_message", user_email="u@x.com", session_id="s1")

        # Recompute expensive metrics periodically
        graph.recompute_metrics()
    """

    # How many recent tool calls per session to link as predecessors
    PREDECESSOR_WINDOW = 3

    def __init__(self):
        rx = _get_rustworkx()
        self._graph: Any = rx.PyDiGraph()  # rx.PyDiGraph

        # Bidirectional name <-> index mappings
        self._name_to_idx: Dict[str, int] = {}
        self._idx_to_name: Dict[int, str] = {}

        # Per-session recent tool history (for edge creation)
        self._session_history: Dict[str, List[Tuple[str, float]]] = defaultdict(list)

        # Cached graph metrics (recomputed periodically)
        self._betweenness: Dict[int, float] = {}
        self._closeness: Dict[int, float] = {}
        self._k_cores: Dict[int, int] = {}
        self._metrics_stale = True

    # =========================================================================
    # NODE / EDGE MANAGEMENT
    # =========================================================================

    def _ensure_node(self, tool_name: str, service: str = "") -> int:
        """Add a tool node if it doesn't exist. Returns node index."""
        if tool_name in self._name_to_idx:
            return self._name_to_idx[tool_name]

        data = ToolNodeData(
            tool_name=tool_name,
            service=service,
            first_seen=time.time(),
        )
        idx = self._graph.add_node(data)
        self._name_to_idx[tool_name] = idx
        self._idx_to_name[idx] = tool_name
        return idx

    def _ensure_edge(self, src_idx: int, dst_idx: int) -> ToolEdgeData:
        """Add or get the edge between two nodes."""
        if self._graph.has_edge(src_idx, dst_idx):
            edge_idx = self._graph.get_edge_data(src_idx, dst_idx)
            # edge_idx is actually the edge data object
            return edge_idx
        data = ToolEdgeData()
        self._graph.add_edge(src_idx, dst_idx, data)
        return data

    # =========================================================================
    # RECORDING
    # =========================================================================

    def record_tool_call(
        self,
        tool_name: str,
        service: str = "",
        session_id: str = "",
        execution_time_ms: float = 0.0,
        timestamp_ms: Optional[float] = None,
    ) -> None:
        """
        Record a tool call and update the co-occurrence graph.

        Creates edges from recent prior tools in the same session to this tool.

        Args:
            tool_name: Name of the tool called
            service: Service group (e.g., "chat", "drive")
            session_id: Session identifier for temporal grouping
            execution_time_ms: How long the tool took
            timestamp_ms: Call timestamp (defaults to now)
        """
        now = timestamp_ms or (time.time() * 1000)
        idx = self._ensure_node(tool_name, service)

        # Update node stats
        node_data: ToolNodeData = self._graph.get_node_data(idx)
        node_data.call_count += 1
        node_data.total_execution_ms += execution_time_ms
        if service and not node_data.service:
            node_data.service = service

        # Create edges from recent predecessors in this session
        if session_id:
            history = self._session_history[session_id]

            # Link from each recent predecessor to this tool
            window = history[-self.PREDECESSOR_WINDOW:]
            for prev_name, prev_ts in window:
                if prev_name == tool_name:
                    continue  # Skip self-loops
                prev_idx = self._name_to_idx.get(prev_name)
                if prev_idx is None:
                    continue
                edge_data = self._ensure_edge(prev_idx, idx)
                edge_data.co_occurrence_count += 1
                edge_data.total_time_delta_ms += (now - prev_ts)
                edge_data.sessions_seen_in.add(session_id)

            # Append to session history
            history.append((tool_name, now))

            # Trim old history to prevent unbounded growth
            if len(history) > 50:
                self._session_history[session_id] = history[-50:]

        self._metrics_stale = True

    # =========================================================================
    # GRAPH ANALYSIS
    # =========================================================================

    def recompute_metrics(self) -> None:
        """Recompute expensive graph metrics (centrality, k-cores).

        Call periodically (e.g., every N tool calls or on a timer),
        not on every record_tool_call.
        """
        rx = _get_rustworkx()
        graph = self._graph

        if graph.num_nodes() == 0:
            self._betweenness = {}
            self._closeness = {}
            self._k_cores = {}
            self._metrics_stale = False
            return

        try:
            self._betweenness = rx.digraph_betweenness_centrality(graph)
        except Exception:
            self._betweenness = {}

        try:
            self._closeness = rx.digraph_closeness_centrality(graph)
        except Exception:
            self._closeness = {}

        try:
            # k-core requires undirected graph
            undirected = graph.to_undirected()
            self._k_cores = rx.core_number(undirected)
        except Exception:
            self._k_cores = {}

        self._metrics_stale = False
        logger.debug(
            f"Recomputed graph metrics: {graph.num_nodes()} nodes, "
            f"{graph.num_edges()} edges"
        )

    def get_predecessors(self, tool_name: str, top_n: int = 3) -> List[Tuple[str, int]]:
        """Get top-N predecessors by co-occurrence count.

        Returns:
            List of (tool_name, count) tuples sorted by count descending.
        """
        idx = self._name_to_idx.get(tool_name)
        if idx is None:
            return []

        preds = []
        for pred_idx in self._graph.predecessor_indices(idx):
            edge_data: ToolEdgeData = self._graph.get_edge_data(pred_idx, idx)
            pred_name = self._idx_to_name.get(pred_idx, "?")
            preds.append((pred_name, edge_data.co_occurrence_count))

        preds.sort(key=lambda x: x[1], reverse=True)
        return preds[:top_n]

    def get_successors(self, tool_name: str, top_n: int = 3) -> List[Tuple[str, int]]:
        """Get top-N successors by co-occurrence count.

        Returns:
            List of (tool_name, count) tuples sorted by count descending.
        """
        idx = self._name_to_idx.get(tool_name)
        if idx is None:
            return []

        succs = []
        for succ_idx in self._graph.successor_indices(idx):
            edge_data: ToolEdgeData = self._graph.get_edge_data(idx, succ_idx)
            succ_name = self._idx_to_name.get(succ_idx, "?")
            succs.append((succ_name, edge_data.co_occurrence_count))

        succs.sort(key=lambda x: x[1], reverse=True)
        return succs[:top_n]

    def get_typical_chain(self, tool_name: str, length: int = 3) -> List[str]:
        """Get a typical workflow chain starting from (or including) tool_name.

        Follows the most frequent successor edges greedily.
        """
        chain = [tool_name]
        current = tool_name
        visited = {tool_name}

        for _ in range(length - 1):
            succs = self.get_successors(current, top_n=1)
            if not succs:
                break
            next_tool = succs[0][0]
            if next_tool in visited:
                break
            chain.append(next_tool)
            visited.add(next_tool)
            current = next_tool

        return chain

    # =========================================================================
    # RELATIONSHIP TEXT GENERATION
    # =========================================================================

    def get_relationship_text(
        self,
        tool_name: str,
        user_email: str = "",
        session_id: str = "",
    ) -> str:
        """
        Generate relationship text for embedding in the 'relationships' vector.

        Template:
            {tool_name} belongs to {service} service.
            Predecessors: {top_3}.
            Successors: {top_3}.
            User: {user_email}. Session: {session_id}.
            Core: {k_core}. Centrality: {betweenness:.2f}.
            Workflow: [{typical_chain}].
        """
        idx = self._name_to_idx.get(tool_name)
        if idx is None:
            return f"{tool_name} tool_response (no graph data)"

        node_data: ToolNodeData = self._graph.get_node_data(idx)

        # Ensure metrics are computed
        if self._metrics_stale:
            self.recompute_metrics()

        # Predecessors and successors
        preds = self.get_predecessors(tool_name)
        succs = self.get_successors(tool_name)
        pred_str = ", ".join(f"{n}({c})" for n, c in preds) if preds else "none"
        succ_str = ", ".join(f"{n}({c})" for n, c in succs) if succs else "none"

        # Metrics (rustworkx returns CentralityMapping / dict-like objects
        # that may not support .get(), so use index access with fallback)
        try:
            betweenness = self._betweenness[idx]
        except (KeyError, IndexError, TypeError):
            betweenness = 0.0
        try:
            k_core = self._k_cores[idx]
        except (KeyError, IndexError, TypeError):
            k_core = 0

        # Typical chain
        chain = self.get_typical_chain(tool_name)
        chain_str = " -> ".join(chain)

        parts = [
            f"{tool_name} belongs to {node_data.service} service.",
            f"Predecessors: {pred_str}.",
            f"Successors: {succ_str}.",
        ]
        if user_email:
            parts.append(f"User: {user_email}.")
        if session_id:
            parts.append(f"Session: {session_id}.")
        parts.append(f"Core: {k_core}. Centrality: {betweenness:.2f}.")
        parts.append(f"Workflow: [{chain_str}].")

        return " ".join(parts)

    # =========================================================================
    # SERIALIZATION
    # =========================================================================

    def get_stats(self) -> Dict[str, Any]:
        """Get graph statistics."""
        return {
            "nodes": self._graph.num_nodes(),
            "edges": self._graph.num_edges(),
            "sessions_tracked": len(self._session_history),
            "metrics_stale": self._metrics_stale,
        }

    def get_node_info(self, tool_name: str) -> Optional[Dict[str, Any]]:
        """Get info about a specific tool node."""
        idx = self._name_to_idx.get(tool_name)
        if idx is None:
            return None

        data: ToolNodeData = self._graph.get_node_data(idx)
        return {
            "tool_name": data.tool_name,
            "service": data.service,
            "call_count": data.call_count,
            "avg_execution_ms": data.avg_execution_ms,
            "in_degree": self._graph.in_degree(idx),
            "out_degree": self._graph.out_degree(idx),
            "betweenness": self._betweenness.get(idx, 0.0),
            "k_core": self._k_cores.get(idx, 0),
        }

    def clear_session(self, session_id: str) -> None:
        """Remove session history (called on session end)."""
        self._session_history.pop(session_id, None)

    @property
    def tool_names(self) -> Set[str]:
        """All tracked tool names."""
        return set(self._name_to_idx.keys())


__all__ = [
    "ToolRelationshipGraph",
    "ToolNodeData",
    "ToolEdgeData",
]
