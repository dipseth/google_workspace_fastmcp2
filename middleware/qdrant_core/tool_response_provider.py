"""
Tool Response RIC Text Provider

Domain-specific provider for tool response components.
Implements the RICTextProvider protocol for component_type="tool_response".

This file lives in qdrant_core/ (not module_wrapper/) because it's
domain-specific to the middleware layer.
"""

import json
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class ToolResponseProvider:
    """RIC text provider for tool response components.

    Generates the 3 text representations for embedding tool call data:
      - component_text: Tool identity (name + service + type)
      - inputs_text: Arguments + response content
      - relationships_text: Service graph context + optional co-occurrence graph

    Optionally uses a ToolRelationshipGraph for richer relationship text.
    Without the graph, falls back to basic service/user/session context.
    """

    def __init__(self, tool_graph: Optional[Any] = None):
        """
        Args:
            tool_graph: Optional ToolRelationshipGraph for co-occurrence data.
                        If None, relationships_text uses basic fallback.
        """
        self._tool_graph = tool_graph

    @property
    def component_type(self) -> str:
        return "tool_response"

    def component_text(self, name: str, metadata: Dict[str, Any]) -> str:
        """Tool identity: name + service + type.

        Expected metadata keys:
            - service (str): Service group e.g. "chat", "drive"
        """
        service = metadata.get("service", "")
        return f"Tool: {name}\nService: {service}\nType: tool_response"

    def inputs_text(self, name: str, metadata: Dict[str, Any]) -> str:
        """Arguments + response content.

        Expected metadata keys:
            - tool_args (dict): Arguments passed to the tool
            - response (Any): Tool response content
        """
        tool_args = metadata.get("tool_args", {})
        response = metadata.get("response", "")

        args_str = (
            json.dumps(tool_args) if isinstance(tool_args, dict) else str(tool_args)
        )
        response_str = str(response)[:1000]

        return f"Arguments: {args_str}\nResponse: {response_str}"

    def relationships_text(self, name: str, metadata: Dict[str, Any]) -> str:
        """Service graph context + co-occurrence relationships.

        Expected metadata keys:
            - service (str): Service group
            - user_email (str): User identifier
            - session_id (str): Session identifier

        If a ToolRelationshipGraph is available, delegates to it for
        rich graph-based relationship text. Otherwise uses basic fallback.
        """
        service = metadata.get("service", "")
        user_email = metadata.get("user_email", "")
        session_id = metadata.get("session_id", "")

        if self._tool_graph is not None:
            return self._tool_graph.get_relationship_text(
                name,
                user_email=user_email,
                session_id=session_id,
            )

        # Basic fallback (matches current _store_point_named_vectors inline text)
        parts = [f"{name} belongs to {service}."]
        if user_email:
            parts.append(f"User: {user_email}.")
        if session_id:
            parts.append(f"Session: {session_id}.")
        return " ".join(parts)


__all__ = [
    "ToolResponseProvider",
]
