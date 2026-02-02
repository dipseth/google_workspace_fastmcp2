"""
Tests for FastMCP compatibility utilities.

These tests verify the utilities that replace cascading hasattr/getattr patterns.
"""

import pytest
from unittest.mock import Mock, MagicMock
from config.fastmcp_compat import (
    FastMCPToolRegistry,
    ResourceContentExtractor,
    ResponseSerializer,
    ToolsListAccessor,
    ContextExtractor,
)


class TestFastMCPToolRegistry:
    """Tests for FastMCPToolRegistry."""

    def test_get_tools_dict_fastmcp_2x(self):
        """Test accessing tools from FastMCP 2.x structure."""
        # Mock FastMCP 2.x server
        mock_server = Mock()
        mock_server._tool_manager = Mock()
        mock_server._tool_manager._tools = {"tool1": "instance1", "tool2": "instance2"}
        
        result = FastMCPToolRegistry.get_tools_dict(mock_server)
        
        assert result == {"tool1": "instance1", "tool2": "instance2"}

    def test_get_tools_dict_fastmcp_3x(self):
        """Test accessing tools from FastMCP 3.0+ structure."""
        # Skip the actual Tool import validation since it requires fastmcp to be installed
        # The logic just needs isinstance check to work
        pytest.skip("Requires fastmcp installed - logic tested in integration tests")

    def test_get_tools_dict_unsupported(self):
        """Test error when server structure is unsupported."""
        mock_server = Mock(spec=[])  # Empty spec = no attributes
        
        with pytest.raises(RuntimeError, match="Cannot access tool registry"):
            FastMCPToolRegistry.get_tools_dict(mock_server)

    def test_extract_callable_fn_attribute(self):
        """Test extracting callable from tool with 'fn' attribute."""
        mock_tool = Mock()
        mock_func = Mock()
        mock_tool.fn = mock_func
        
        result = FastMCPToolRegistry.extract_callable(mock_tool)
        
        assert result is mock_func

    def test_extract_callable_func_attribute(self):
        """Test extracting callable from tool with 'func' attribute."""
        mock_tool = Mock()
        mock_tool.fn = None  # No fn attribute
        delattr(mock_tool, "fn")
        mock_func = Mock()
        mock_tool.func = mock_func
        
        result = FastMCPToolRegistry.extract_callable(mock_tool)
        
        assert result is mock_func

    def test_extract_callable_direct_callable(self):
        """Test extracting callable when tool is directly callable."""
        mock_tool = Mock()
        
        result = FastMCPToolRegistry.extract_callable(mock_tool)
        
        assert callable(result)

    def test_extract_callable_not_callable(self):
        """Test error when tool has no callable."""
        # Create an object that truly isn't callable
        class NonCallableTool:
            name = "test"
        
        mock_tool = NonCallableTool()
        
        with pytest.raises(RuntimeError, match="not callable"):
            FastMCPToolRegistry.extract_callable(mock_tool)


class TestResourceContentExtractor:
    """Tests for ResourceContentExtractor."""

    def test_extract_with_content_attribute_string(self):
        """Test extracting string content from resource."""
        mock_resource = Mock()
        mock_resource.content = "test content"
        
        result = ResourceContentExtractor.extract(mock_resource)
        
        assert result == "test content"

    def test_extract_with_content_attribute_json(self):
        """Test extracting and parsing JSON content."""
        mock_resource = Mock()
        mock_resource.content = '{"key": "value"}'
        mock_resource.mime_type = "application/json"
        
        result = ResourceContentExtractor.extract(mock_resource)
        
        assert result == {"key": "value"}

    def test_extract_with_contents_list_text(self):
        """Test extracting from standard MCP contents structure."""
        mock_item = Mock()
        mock_item.text = '{"data": "test"}'
        mock_item.blob = None
        
        mock_resource = Mock(spec=["contents"])
        mock_resource.contents = [mock_item]
        
        result = ResourceContentExtractor.extract(mock_resource)
        
        assert result == {"data": "test"}

    def test_extract_with_contents_list_blob(self):
        """Test extracting blob from contents."""
        mock_item = Mock(spec=["text", "blob"])
        mock_item.text = None
        mock_item.blob = b"binary data"
        
        mock_resource = Mock(spec=["contents"])
        mock_resource.contents = [mock_item]
        
        result = ResourceContentExtractor.extract(mock_resource)
        
        assert result == b"binary data"

    def test_extract_dict_with_contents(self):
        """Test extracting from dict-based response."""
        resource_dict = {
            "contents": [
                {"text": '{"result": "success"}'}
            ]
        }
        
        result = ResourceContentExtractor.extract(resource_dict)
        
        assert result == {"result": "success"}

    def test_extract_plain_dict(self):
        """Test extracting plain dict returns as-is."""
        resource_dict = {"key": "value"}
        
        result = ResourceContentExtractor.extract(resource_dict)
        
        assert result == {"key": "value"}


class TestResponseSerializer:
    """Tests for ResponseSerializer."""

    def test_serialize_with_content(self):
        """Test serializing object with content attribute."""
        mock_response = Mock()
        mock_response.content = {"result": "data"}
        
        result = ResponseSerializer.serialize(mock_response)
        
        assert result == {"result": "data"}

    def test_serialize_with_to_dict(self):
        """Test serializing object with to_dict method."""
        mock_response = Mock(spec=["to_dict"])
        mock_response.to_dict.return_value = {"key": "value"}
        
        result = ResponseSerializer.serialize(mock_response)
        
        assert result == {"key": "value"}

    def test_serialize_with_dict(self):
        """Test serializing object with __dict__."""
        class TestObj:
            def __init__(self):
                self.field1 = "value1"
                self.field2 = "value2"
        
        obj = TestObj()
        result = ResponseSerializer.serialize(obj)
        
        assert result == {"field1": "value1", "field2": "value2"}

    def test_serialize_primitive(self):
        """Test serializing primitive returns as-is."""
        result = ResponseSerializer.serialize("string value")
        assert result == "string value"
        
        result = ResponseSerializer.serialize(42)
        assert result == 42
        
        result = ResponseSerializer.serialize([1, 2, 3])
        assert result == [1, 2, 3]


class TestToolsListAccessor:
    """Tests for ToolsListAccessor."""

    def test_get_tools_dict_public_list(self):
        """Test accessing tools via public tools attribute (list)."""
        mock_tool1 = Mock()
        mock_tool1.name = "tool1"
        mock_tool2 = Mock()
        mock_tool2.name = "tool2"
        
        mock_server = Mock()
        mock_server.tools = [mock_tool1, mock_tool2]
        
        result = ToolsListAccessor.get_tools_dict(mock_server)
        
        assert result == {"tool1": mock_tool1, "tool2": mock_tool2}

    def test_get_tools_dict_public_dict(self):
        """Test accessing tools via public tools attribute (dict)."""
        tools_dict = {"tool1": "instance1", "tool2": "instance2"}
        
        class MockDict(dict):
            def items(self):
                return super().items()
        
        mock_dict = MockDict(tools_dict)
        mock_server = Mock()
        mock_server.tools = mock_dict
        
        result = ToolsListAccessor.get_tools_dict(mock_server)
        
        assert result == tools_dict

    def test_get_tools_dict_tool_manager_fallback(self):
        """Test fallback to _tool_manager._tools."""
        mock_server = Mock(spec=["_tool_manager"])
        mock_server._tool_manager = Mock()
        mock_server._tool_manager._tools = {"tool1": "instance1"}
        
        result = ToolsListAccessor.get_tools_dict(mock_server)
        
        assert result == {"tool1": "instance1"}

    def test_get_tools_dict_no_access(self):
        """Test error when no tool access method works."""
        mock_server = Mock(spec=[])
        
        with pytest.raises(RuntimeError, match="Cannot access tools"):
            ToolsListAccessor.get_tools_dict(mock_server)


class TestContextExtractor:
    """Tests for ContextExtractor."""

    def test_get_tool_name_from_context(self):
        """Test extracting tool name from context."""
        mock_context = Mock()
        mock_context.message = Mock()
        mock_context.message.name = "my_tool"
        
        result = ContextExtractor.get_tool_name(mock_context)
        
        assert result == "my_tool"

    def test_get_tool_name_default(self):
        """Test default value when tool name not available."""
        mock_context = Mock(spec=[])
        
        result = ContextExtractor.get_tool_name(mock_context)
        
        assert result == "unknown_tool"

    def test_get_tool_name_custom_default(self):
        """Test custom default value."""
        mock_context = Mock(spec=[])
        
        result = ContextExtractor.get_tool_name(mock_context, default="fallback_tool")
        
        assert result == "fallback_tool"

    def test_get_arguments_from_context(self):
        """Test extracting arguments from context."""
        mock_context = Mock()
        mock_context.message = Mock()
        mock_context.message.arguments = {"param1": "value1", "param2": "value2"}
        
        result = ContextExtractor.get_arguments(mock_context)
        
        assert result == {"param1": "value1", "param2": "value2"}

    def test_get_arguments_default(self):
        """Test default value when arguments not available."""
        mock_context = Mock(spec=[])
        
        result = ContextExtractor.get_arguments(mock_context)
        
        assert result == {}

    def test_get_arguments_custom_default(self):
        """Test custom default value for arguments."""
        mock_context = Mock(spec=[])
        custom_default = {"default": "param"}
        
        result = ContextExtractor.get_arguments(mock_context, default=custom_default)
        
        assert result == custom_default
