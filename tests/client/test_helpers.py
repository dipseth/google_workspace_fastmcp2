"""Helper utilities for standardized client testing framework.

🔧 MCP Tools Used:
- N/A (Helper module - supports testing of all MCP tools)
- Provides utilities for validating responses from any MCP tool

🧪 What's Being Tested:
- Response format validation across all services
- Authentication pattern testing (explicit email vs middleware injection)
- Error response identification and handling
- Service-specific response validation patterns
- Tool execution with standardized parameter handling
- Success/failure determination from response content

🔍 Potential Duplications:
- No duplications - this provides shared utilities to eliminate code duplication
- Centralizes response validation logic used across all service tests
- Standardizes authentication pattern testing to avoid repetition

Note: This is a framework support file providing reusable test utilities.
"""

import json
from typing import Any, Dict, List, Optional, Tuple

from fastmcp import Client


class TestResponseValidator:
    """Utility class for validating test responses."""

    @staticmethod
    def is_valid_auth_response(content: str) -> bool:
        """Check if response indicates valid authentication handling."""
        auth_indicators = [
            "authentication" in content.lower(),
            "credentials" in content.lower(),
            "not authenticated" in content.lower(),
            "please check your" in content.lower(),
            "oauth" in content.lower(),
            "permission" in content.lower(),
        ]
        return any(auth_indicators)

    @staticmethod
    def is_success_response(content: str) -> bool:
        """Check if response indicates successful operation."""
        success_indicators = [
            "success" in content.lower(),
            "found" in content.lower(),
            "created" in content.lower(),
            "sent" in content.lower(),
            "updated" in content.lower(),
            "deleted" in content.lower(),
            len(content) > 50,  # Non-empty substantial response
        ]
        return any(success_indicators)

    @staticmethod
    def parse_json_response(content: str) -> Tuple[Optional[Dict], bool]:
        """Try to parse response as JSON, return (data, is_json)."""
        try:
            data = json.loads(content)
            return data, True
        except json.JSONDecodeError:
            return None, False

    @staticmethod
    def validate_service_response(content: str, service_name: str) -> bool:
        """Validate response for specific Google service."""
        service_patterns = {
            "gmail": ["labels", "messages", "threads", "gmail"],
            "drive": ["files", "folders", "drive", "upload"],
            "docs": ["documents", "docs", "content"],
            "forms": ["forms", "questions", "responses"],
            "sheets": ["spreadsheets", "sheets", "ranges", "values"],
            "slides": ["presentations", "slides"],
            "calendar": ["events", "calendars", "calendar"],
            "chat": ["spaces", "messages", "chat", "cards"],
        }

        patterns = service_patterns.get(service_name.lower(), [])
        return any(pattern in content.lower() for pattern in patterns)


class ToolTestRunner:
    """Helper class for running standardized tool tests."""

    def __init__(self, client: Client, test_email: str):
        self.client = client
        self.test_email = test_email

    async def test_tool_availability(self, tool_name: str) -> bool:
        """Test if a tool is available in the server."""
        tools = await self.client.list_tools()
        tool_names = [tool.name for tool in tools]
        return tool_name in tool_names

    async def get_tool_info(self, tool_name: str) -> Optional[Dict]:
        """Get detailed information about a tool."""
        tools = await self.client.list_tools()
        for tool in tools:
            if tool.name == tool_name:
                return {
                    "name": tool.name,
                    "description": tool.description,
                    "inputSchema": tool.inputSchema,
                    "has_user_email_param": "user_google_email"
                    in str(tool.inputSchema),
                }
        return None

    async def test_tool_basic(
        self, tool_name: str, params: Dict[str, Any] = None
    ) -> Dict:
        """Test tool with provided parameters (without auto-adding user_google_email).

        Use this for tools that don't require user_google_email or when you want
        to provide your own parameters directly.
        """
        if params is None:
            params = {}

        try:
            result = await self.client.call_tool(tool_name, params)
            content = result.content[0].text if result.content else ""

            return {
                "success": True,
                "content": content,
                "response_length": len(content),
                "is_auth_related": TestResponseValidator.is_valid_auth_response(
                    content
                ),
                "is_success": TestResponseValidator.is_success_response(content),
            }
        except Exception as e:
            return {
                "success": False,
                "content": str(e),
                "error": str(e),
                "response_length": 0,
                "is_auth_related": False,
                "is_success": False,
            }

    async def test_tool_with_explicit_email(
        self, tool_name: str, params: Dict[str, Any] = None
    ) -> Dict:
        """Test tool with explicit user_google_email parameter."""
        if params is None:
            params = {}

        params["user_google_email"] = self.test_email

        result = await self.client.call_tool(tool_name, params)
        content = result.content[0].text if result.content else ""

        return {
            "success": result is not None,
            "content": content,
            "response_length": len(content),
            "is_auth_related": TestResponseValidator.is_valid_auth_response(content),
            "is_success": TestResponseValidator.is_success_response(content),
        }

    async def test_tool_without_email(
        self, tool_name: str, params: Dict[str, Any] = None
    ) -> Dict:
        """Test tool without user_google_email parameter (middleware injection)."""
        if params is None:
            params = {}

        try:
            result = await self.client.call_tool(tool_name, params)
            content = result.content[0].text if result.content else ""

            return {
                "success": True,
                "content": content,
                "response_length": len(content),
                "middleware_worked": True,
                "is_auth_related": TestResponseValidator.is_valid_auth_response(
                    content
                ),
                "is_success": TestResponseValidator.is_success_response(content),
            }
        except Exception as e:
            error_message = str(e).lower()
            is_param_required_error = (
                "required" in error_message or "missing" in error_message
            )

            return {
                "success": False,
                "error": str(e),
                "middleware_worked": False,
                "param_required_at_client": is_param_required_error,
                "content": "",
            }

    async def test_auth_patterns(
        self, tool_name: str, base_params: Dict[str, Any] = None
    ) -> Dict:
        """Test both authentication patterns for a tool."""
        base_params = base_params or {}

        # Test with explicit email
        explicit_result = await self.test_tool_with_explicit_email(
            tool_name, base_params.copy()
        )

        # Test without email (middleware)
        middleware_result = await self.test_tool_without_email(
            tool_name, base_params.copy()
        )

        return {
            "tool_name": tool_name,
            "explicit_email": explicit_result,
            "middleware_injection": middleware_result,
            "backward_compatible": explicit_result["success"],
            "middleware_supported": middleware_result.get("middleware_worked", False),
        }


def create_service_test_params(service: str) -> Dict[str, Dict[str, Any]]:
    """Create common test parameters for different Google services."""
    service_params = {
        "gmail": {
            "search_gmail_messages": {"query": "test"},
            "list_gmail_labels": {},
            "send_gmail_message": {
                "to": "test@example.com",
                "subject": "Test",
                "body": "Test message",
            },
        },
        "drive": {
            "search_drive_files": {"query": "test"},
            "list_drive_items": {"folder_id": "root"},
            "upload_file_to_drive": {"file_path": "/tmp/test.txt", "folder_id": "root"},
        },
        "docs": {
            "create_google_doc": {"title": "Test Document"},
            "list_user_google_docs": {"max_results": 10},
        },
        "forms": {
            "create_form": {"title": "Test Form", "description": "Test"},
            "get_form": {"form_id": "test_form_id"},
        },
        "sheets": {
            "create_spreadsheet": {"title": "Test Sheet"},
            "list_spreadsheets": {"max_results": 10},
        },
        "slides": {
            "create_presentation": {"title": "Test Presentation"},
            "get_presentation_info": {"presentation_id": "test_id"},
        },
        "calendar": {
            "list_calendars": {},
            "create_event": {
                "calendar_id": "primary",
                "summary": "Test Event",
                "start_time": "2025-02-01T10:00:00Z",
                "end_time": "2025-02-01T11:00:00Z",
            },
        },
        "chat": {
            "list_spaces": {},
            "send_message": {"space_id": "test_space", "text": "Test message"},
        },
    }

    return service_params.get(service.lower(), {})


def print_test_result(test_name: str, result: Dict, verbose: bool = True):
    """Print formatted test result."""
    status = "✅" if result.get("success", False) else "❌"
    print(f"\n{status} {test_name}")

    if verbose:
        if result.get("content"):
            content_preview = (
                result["content"][:150] + "..."
                if len(result["content"]) > 150
                else result["content"]
            )
            print(f"   Response: {content_preview}")

        if result.get("response_length"):
            print(f"   Response length: {result['response_length']} characters")

        if result.get("error"):
            print(f"   Error: {result['error']}")

        if "middleware_worked" in result:
            middleware_status = "✅" if result["middleware_worked"] else "❌"
            print(f"   Middleware injection: {middleware_status}")


async def ensure_tools_enabled(
    client: Client,
    tool_names: Optional[List[str]] = None,
    service_filter: Optional[str] = None,
) -> bool:
    """Enable specific tools or all tools for the current session.

    Useful for tests that depend on tools which are disabled by default
    in minimal startup mode.

    Args:
        client: The MCP client.
        tool_names: Specific tool names to enable. Mutually exclusive with service_filter.
        service_filter: Enable all tools for a service (e.g., 'gmail', 'drive').
        If neither is provided, enables all tools.

    Returns:
        True on success, False on failure (logs a warning instead of raising).
    """
    try:
        params: Dict[str, Any] = {"action": "enable", "scope": "session"}
        if tool_names:
            params["tool_names"] = tool_names
        elif service_filter:
            params["service_filter"] = service_filter
        else:
            params["action"] = "enable_all"

        await client.call_tool("manage_tools", params)
        return True
    except Exception as e:
        import warnings

        warnings.warn(f"Could not enable tools for test: {e}", stacklevel=2)
        return False


def get_common_test_tools(service: str) -> List[str]:
    """Get list of common tools to test for each service."""
    service_tools = {
        "gmail": ["list_gmail_labels", "search_gmail_messages", "send_gmail_message"],
        "drive": ["search_drive_files", "list_drive_items", "upload_file_to_drive"],
        "docs": ["list_user_google_docs", "create_google_doc"],
        "forms": ["create_form", "get_form", "list_form_responses"],
        "sheets": ["list_spreadsheets", "create_spreadsheet", "read_sheet_values"],
        "slides": ["create_presentation", "get_presentation_info", "add_slide"],
        "calendar": ["list_calendars", "list_events", "create_event"],
        "chat": ["list_spaces", "send_message", "send_card_message"],
    }

    return service_tools.get(service.lower(), [])


async def get_registered_tools(client: Client) -> List[str]:
    """Get list of all registered tools from the server via manage_tools.

    This returns ALL tools in the registry, regardless of whether they are
    currently enabled/exposed via list_tools(). Use this to verify tools
    exist in the server rather than checking client.list_tools() which
    only shows currently enabled tools.

    By design, the server starts with only 5 core tools enabled:
    - start_google_auth
    - check_drive_auth
    - health_check
    - manage_tools
    - search

    Other tools are registered but disabled by default.
    """
    result = await client.call_tool("manage_tools", {"action": "list"})
    content = (
        result.content[0].text
        if hasattr(result.content[0], "text")
        else str(result.content[0])
    )

    try:
        data = json.loads(content)
        tool_list = data.get("toolList", [])
        return [t["name"] for t in tool_list]
    except (json.JSONDecodeError, KeyError):
        return []


async def assert_tools_registered(
    client: Client, expected_tools: List[str], context: str = ""
):
    """Assert that specified tools are registered in the server.

    This checks the tool registry via manage_tools, not client.list_tools().
    Tools may be registered but not currently enabled/exposed.

    Args:
        client: The MCP client
        expected_tools: List of tool names that should be registered
        context: Optional context string for error messages
    """
    registered = await get_registered_tools(client)

    missing = [t for t in expected_tools if t not in registered]
    if missing:
        ctx = f" ({context})" if context else ""
        raise AssertionError(
            f"Tools not registered{ctx}: {missing}\n"
            f"Expected: {expected_tools}\n"
            f"Registered: {len(registered)} tools"
        )
