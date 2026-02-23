"""
Tests for the Universal RIC Provider System.

Covers:
1. RICTextProvider protocol compliance
2. IntrospectionProvider produces identical text to previous inline code
3. ToolResponseProvider generates expected text
4. Provider registry dispatch
5. ToolRelationshipGraph integration with ToolResponseProvider
"""

import dataclasses
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest

from adapters.module_wrapper.ric_provider import (
    IntrospectionProvider,
    RICTextProvider,
)
from middleware.qdrant_core.tool_response_provider import ToolResponseProvider

# =============================================================================
# FIXTURES
# =============================================================================


@dataclasses.dataclass
class FakeDataclass:
    """A simple dataclass for testing extract_input_values."""

    name: str = "default"
    count: int = 10
    optional: Optional[str] = None


class FakeComponent:
    """Minimal stub matching ModuleComponent interface for provider tests."""

    def __init__(
        self,
        name: str,
        component_type: str = "class",
        full_path: str = "",
        module_path: str = "test_module",
        docstring: str = "",
        source: str = "",
        obj: Any = None,
    ):
        self.name = name
        self.component_type = component_type
        self.module_path = module_path
        self.docstring = docstring
        self.source = source
        self.obj = obj

    @property
    def full_path(self) -> str:
        return f"{self.module_path}.{self.name}"


# =============================================================================
# TEST: RICTextProvider protocol
# =============================================================================


class TestRICTextProviderProtocol:
    def test_introspection_provider_is_ric_provider(self):
        provider = IntrospectionProvider()
        assert isinstance(provider, RICTextProvider)

    def test_tool_response_provider_is_ric_provider(self):
        provider = ToolResponseProvider()
        assert isinstance(provider, RICTextProvider)

    def test_custom_provider_protocol_compliance(self):
        """A custom provider that implements the protocol should pass isinstance."""

        class MyProvider:
            @property
            def component_type(self) -> str:
                return "api_endpoint"

            def component_text(self, name: str, metadata: Dict[str, Any]) -> str:
                return f"Endpoint: {name}"

            def inputs_text(self, name: str, metadata: Dict[str, Any]) -> str:
                return "params"

            def relationships_text(self, name: str, metadata: Dict[str, Any]) -> str:
                return "standalone"

        assert isinstance(MyProvider(), RICTextProvider)


# =============================================================================
# TEST: IntrospectionProvider
# =============================================================================


class TestIntrospectionProvider:
    def setup_method(self):
        self.provider = IntrospectionProvider()

    def test_component_type(self):
        assert self.provider.component_type == "class"

    def test_component_text_basic(self):
        metadata = {
            "component_type": "class",
            "full_path": "module.MyClass",
            "docstring": "",
        }
        text = self.provider.component_text("MyClass", metadata)
        assert "Name: MyClass" in text
        assert "Type: class" in text
        assert "Path: module.MyClass" in text
        assert "Documentation" not in text  # No docstring

    def test_component_text_with_docstring(self):
        metadata = {
            "component_type": "function",
            "full_path": "module.my_func",
            "docstring": "Does something useful",
        }
        text = self.provider.component_text("my_func", metadata)
        assert "Documentation: Does something useful" in text

    def test_component_text_truncates_long_docstring(self):
        metadata = {
            "component_type": "class",
            "full_path": "m.C",
            "docstring": "x" * 600,
        }
        text = self.provider.component_text("C", metadata)
        assert len(text.split("Documentation: ")[1]) == 500

    def test_inputs_text_with_component_object(self):
        """When a live ModuleComponent is available, delegates to extract_input_values."""
        component = FakeComponent(
            name="FakeDataclass",
            component_type="class",
            obj=FakeDataclass,
        )
        metadata = {"component": component}
        text = self.provider.inputs_text("FakeDataclass", metadata)
        # extract_input_values should find default fields
        assert "name=" in text
        assert "count=" in text

    def test_inputs_text_fallback(self):
        """Without a component object, produces basic fallback text."""
        metadata = {"component_type": "class"}
        text = self.provider.inputs_text("MyClass", metadata)
        assert text == "MyClass class"

    def test_relationships_text_no_validator_no_rels(self):
        metadata = {
            "component_type": "class",
            "relationships": [],
            "structure_validator": None,
            "symbols": {},
        }
        text = self.provider.relationships_text("MyClass", metadata)
        # build_compact_relationship_text with empty rels
        assert "MyClass" in text
        assert "class" in text

    def test_relationships_text_with_rels(self):
        rels = [
            {
                "child_class": "Button",
                "field_name": "button",
                "is_optional": True,
                "depth": 1,
            },
            {
                "child_class": "Icon",
                "field_name": "icon",
                "is_optional": False,
                "depth": 1,
            },
        ]
        metadata = {
            "component_type": "class",
            "relationships": rels,
            "structure_validator": None,
            "symbols": {},
        }
        text = self.provider.relationships_text("Section", metadata)
        assert "Section" in text
        assert "Button" in text
        assert "Icon" in text

    def test_relationships_text_matches_inline_code(self):
        """Verify that IntrospectionProvider produces identical output
        to the previous inline code in run_ingestion_pipeline."""
        from adapters.module_wrapper.pipeline_mixin import (
            build_compact_relationship_text,
        )

        rels = [
            {
                "child_class": "Button",
                "field_name": "button",
                "is_optional": True,
                "depth": 1,
            },
        ]

        # What the old inline code produced:
        expected = build_compact_relationship_text("Parent", rels, "class")

        # What the provider produces:
        metadata = {
            "component_type": "class",
            "relationships": rels,
            "structure_validator": None,
            "symbols": {},
        }
        actual = self.provider.relationships_text("Parent", metadata)
        assert actual == expected

    def test_relationships_text_with_structure_validator(self):
        """When structure_validator is available and name is in its symbols, use it."""
        mock_validator = MagicMock()
        mock_validator.get_enriched_relationship_text.return_value = "enriched text"

        metadata = {
            "component_type": "class",
            "relationships": [],
            "structure_validator": mock_validator,
            "symbols": {"MyClass": "X"},  # name must be in symbols
        }
        text = self.provider.relationships_text("MyClass", metadata)
        assert text == "enriched text"
        mock_validator.get_enriched_relationship_text.assert_called_once_with("MyClass")


# =============================================================================
# TEST: ToolResponseProvider
# =============================================================================


class TestToolResponseProvider:
    def setup_method(self):
        self.provider = ToolResponseProvider()

    def test_component_type(self):
        assert self.provider.component_type == "tool_response"

    def test_component_text(self):
        metadata = {"service": "chat"}
        text = self.provider.component_text("send_message", metadata)
        assert "Tool: send_message" in text
        assert "Service: chat" in text
        assert "Type: tool_response" in text

    def test_inputs_text(self):
        metadata = {
            "tool_args": {"space_id": "spaces/ABC", "message_text": "hello"},
            "response": {"name": "spaces/ABC/messages/123"},
        }
        text = self.provider.inputs_text("send_message", metadata)
        assert "Arguments:" in text
        assert "space_id" in text
        assert "Response:" in text

    def test_inputs_text_truncates_response(self):
        metadata = {
            "tool_args": {},
            "response": "x" * 2000,
        }
        text = self.provider.inputs_text("tool", metadata)
        # Response should be capped at 1000 chars
        response_part = text.split("Response: ")[1]
        assert len(response_part) == 1000

    def test_relationships_text_basic_fallback(self):
        metadata = {
            "service": "drive",
            "user_email": "user@test.com",
            "session_id": "sess-123",
        }
        text = self.provider.relationships_text("upload_file", metadata)
        assert "upload_file belongs to drive." in text
        assert "User: user@test.com." in text
        assert "Session: sess-123." in text

    def test_relationships_text_empty_optional_fields(self):
        metadata = {"service": "chat", "user_email": "", "session_id": ""}
        text = self.provider.relationships_text("list_spaces", metadata)
        assert "list_spaces belongs to chat." in text
        # Empty strings should not appear as "User: ." etc.
        assert "User:" not in text
        assert "Session:" not in text

    def test_relationships_text_with_graph(self):
        """When a ToolRelationshipGraph is provided, delegates to it."""
        mock_graph = MagicMock()
        mock_graph.get_relationship_text.return_value = "graph-enriched text"

        provider = ToolResponseProvider(tool_graph=mock_graph)
        metadata = {
            "service": "chat",
            "user_email": "u@x.com",
            "session_id": "s1",
        }
        text = provider.relationships_text("send_message", metadata)
        assert text == "graph-enriched text"
        mock_graph.get_relationship_text.assert_called_once_with(
            "send_message", user_email="u@x.com", session_id="s1"
        )


# =============================================================================
# TEST: Provider Registry (PipelineMixin)
# =============================================================================


class TestProviderRegistry:
    def test_register_and_get_provider(self):
        from adapters.module_wrapper.pipeline_mixin import PipelineMixin

        mixin = PipelineMixin()
        provider = ToolResponseProvider()
        mixin.register_ric_provider(provider)

        retrieved = mixin.get_ric_provider("tool_response")
        assert retrieved is provider

    def test_get_default_provider(self):
        from adapters.module_wrapper.pipeline_mixin import PipelineMixin

        mixin = PipelineMixin()
        provider = mixin.get_ric_provider("class")
        assert isinstance(provider, IntrospectionProvider)

    def test_get_unknown_type_returns_default(self):
        from adapters.module_wrapper.pipeline_mixin import PipelineMixin

        mixin = PipelineMixin()
        provider = mixin.get_ric_provider("unknown_type")
        assert isinstance(provider, IntrospectionProvider)

    def test_registered_provider_overrides_default(self):
        from adapters.module_wrapper.pipeline_mixin import PipelineMixin

        mixin = PipelineMixin()

        class CustomClassProvider:
            @property
            def component_type(self):
                return "class"

            def component_text(self, name, metadata):
                return "custom"

            def inputs_text(self, name, metadata):
                return "custom"

            def relationships_text(self, name, metadata):
                return "custom"

        custom = CustomClassProvider()
        mixin.register_ric_provider(custom)

        retrieved = mixin.get_ric_provider("class")
        assert retrieved is custom
        assert retrieved.component_text("X", {}) == "custom"


# =============================================================================
# TEST: build_provider_metadata
# =============================================================================


class TestBuildProviderMetadata:
    def test_metadata_has_all_required_keys(self):
        from adapters.module_wrapper.pipeline_mixin import PipelineMixin

        mixin = PipelineMixin()
        component = FakeComponent(
            name="MyClass",
            component_type="class",
            docstring="A class",
        )

        relationships_by_parent = {
            "MyClass": [
                {
                    "child_class": "Child",
                    "field_name": "child",
                    "is_optional": True,
                    "depth": 1,
                }
            ]
        }

        metadata = mixin._build_provider_metadata(component, relationships_by_parent)

        assert metadata["component"] is component
        assert metadata["component_type"] == "class"
        assert metadata["full_path"] == "test_module.MyClass"
        assert metadata["docstring"] == "A class"
        assert len(metadata["relationships"]) == 1
        assert metadata["relationships"][0]["child_class"] == "Child"

    def test_non_class_gets_empty_relationships(self):
        from adapters.module_wrapper.pipeline_mixin import PipelineMixin

        mixin = PipelineMixin()
        component = FakeComponent(name="my_func", component_type="function")

        relationships_by_parent = {
            "my_func": [
                {"child_class": "X", "field_name": "x", "is_optional": True, "depth": 1}
            ]
        }

        metadata = mixin._build_provider_metadata(component, relationships_by_parent)
        # Functions don't get structural relationships
        assert metadata["relationships"] == []


# =============================================================================
# TEST: ToolRelationshipGraph + ToolResponseProvider integration
# =============================================================================


class TestToolGraphIntegration:
    def test_graph_enriches_relationship_text(self):
        """Record some tool calls, then verify the provider uses graph data."""
        from adapters.module_wrapper.tool_relationship_graph import (
            ToolRelationshipGraph,
        )

        graph = ToolRelationshipGraph()
        graph.record_tool_call("list_spaces", "chat", session_id="s1")
        graph.record_tool_call("send_message", "chat", session_id="s1")
        graph.record_tool_call("search_messages", "chat", session_id="s1")

        provider = ToolResponseProvider(tool_graph=graph)
        metadata = {
            "service": "chat",
            "user_email": "u@x.com",
            "session_id": "s1",
        }
        text = provider.relationships_text("send_message", metadata)

        # Should contain graph-derived data
        assert "send_message" in text
        assert "chat" in text
        # Should have predecessors/successors from the graph
        assert "Predecessors:" in text or "Successors:" in text


# =============================================================================
# TEST: QdrantStorageManager provider integration
# =============================================================================


class TestStorageManagerProvider:
    def test_set_ric_provider(self):
        """Verify set_ric_provider stores the provider."""
        from middleware.qdrant_core.storage import QdrantStorageManager

        mock_client_manager = MagicMock()
        mock_client_manager.config = MagicMock()
        storage = QdrantStorageManager(mock_client_manager)

        assert storage._ric_provider is None

        provider = ToolResponseProvider()
        storage.set_ric_provider(provider)
        assert storage._ric_provider is provider
