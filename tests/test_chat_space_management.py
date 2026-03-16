"""Tests for manage_space tool - Google Chat space administration."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastmcp import FastMCP

from gchat.chat_tools import setup_chat_tools


@pytest.fixture
def mcp():
    """Create a FastMCP instance with chat tools registered."""
    server = FastMCP("test")
    setup_chat_tools(server)
    return server


@pytest.fixture
def mock_chat_service():
    """Create a mock Google Chat service."""
    return MagicMock()


@pytest.fixture
def mock_get_service(mock_chat_service):
    """Patch _get_chat_service_with_fallback to return mock service."""
    with patch(
        "gchat.chat_tools._get_chat_service_with_fallback",
        new_callable=AsyncMock,
        return_value=mock_chat_service,
    ) as mock:
        yield mock


def _extract_result(tool_result) -> dict:
    """Extract the structured result dict from a FastMCP ToolResult."""
    sc = tool_result.structured_content
    if isinstance(sc, dict) and "result" in sc:
        return sc["result"]
    return sc


class TestListMembers:
    @pytest.mark.asyncio
    async def test_list_members_success(self, mcp, mock_get_service, mock_chat_service):
        mock_chat_service.spaces().members().list().execute.return_value = {
            "memberships": [
                {
                    "name": "spaces/abc/members/123",
                    "member": {
                        "name": "users/123",
                        "email": "user@example.com",
                        "displayName": "Test User",
                        "type": "HUMAN",
                    },
                    "role": "ROLE_MEMBER",
                    "createTime": "2024-01-01T00:00:00Z",
                }
            ]
        }

        result_raw = await mcp.call_tool(
            "manage_space",
            {"action": "list_members", "space_id": "spaces/abc"},
        )
        result = _extract_result(result_raw)
        assert result["success"] is True
        assert result["data"]["count"] == 1
        assert result["data"]["members"][0]["email"] == "user@example.com"

    @pytest.mark.asyncio
    async def test_list_members_missing_space_id(self, mcp, mock_get_service):
        result_raw = await mcp.call_tool(
            "manage_space",
            {"action": "list_members"},
        )
        result = _extract_result(result_raw)
        assert result["success"] is False
        assert "space_id" in result["error"]


class TestAddMember:
    @pytest.mark.asyncio
    async def test_add_member_success(self, mcp, mock_get_service, mock_chat_service):
        mock_chat_service.spaces().members().create().execute.return_value = {
            "name": "spaces/abc/members/456",
            "member": {"name": "users/new@example.com", "type": "HUMAN"},
            "role": "ROLE_MEMBER",
        }

        result_raw = await mcp.call_tool(
            "manage_space",
            {
                "action": "add_member",
                "space_id": "spaces/abc",
                "member_email": "new@example.com",
            },
        )
        result = _extract_result(result_raw)
        assert result["success"] is True
        assert "membership" in result["data"]

    @pytest.mark.asyncio
    async def test_add_member_missing_email(self, mcp, mock_get_service):
        result_raw = await mcp.call_tool(
            "manage_space",
            {"action": "add_member", "space_id": "spaces/abc"},
        )
        result = _extract_result(result_raw)
        assert result["success"] is False
        assert "member_email" in result["error"]

    @pytest.mark.asyncio
    async def test_add_member_missing_space_id(self, mcp, mock_get_service):
        result_raw = await mcp.call_tool(
            "manage_space",
            {"action": "add_member", "member_email": "x@y.com"},
        )
        result = _extract_result(result_raw)
        assert result["success"] is False
        assert "space_id" in result["error"]


class TestRemoveMember:
    @pytest.mark.asyncio
    async def test_remove_member_success(
        self, mcp, mock_get_service, mock_chat_service
    ):
        mock_chat_service.spaces().members().delete().execute.return_value = {}

        result_raw = await mcp.call_tool(
            "manage_space",
            {
                "action": "remove_member",
                "member_name": "spaces/abc/members/123",
            },
        )
        result = _extract_result(result_raw)
        assert result["success"] is True
        assert result["data"]["removedMember"] == "spaces/abc/members/123"

    @pytest.mark.asyncio
    async def test_remove_member_missing_name(self, mcp, mock_get_service):
        result_raw = await mcp.call_tool(
            "manage_space",
            {"action": "remove_member"},
        )
        result = _extract_result(result_raw)
        assert result["success"] is False
        assert "member_name" in result["error"]


class TestCreateSpace:
    @pytest.mark.asyncio
    async def test_create_space_success(self, mcp, mock_get_service, mock_chat_service):
        mock_chat_service.spaces().create().execute.return_value = {
            "name": "spaces/newspace",
            "displayName": "New Space",
            "spaceType": "SPACE",
        }

        result_raw = await mcp.call_tool(
            "manage_space",
            {"action": "create_space", "display_name": "New Space"},
        )
        result = _extract_result(result_raw)
        assert result["success"] is True
        assert result["spaceId"] == "spaces/newspace"

    @pytest.mark.asyncio
    async def test_create_space_missing_name(self, mcp, mock_get_service):
        result_raw = await mcp.call_tool(
            "manage_space",
            {"action": "create_space"},
        )
        result = _extract_result(result_raw)
        assert result["success"] is False
        assert "display_name" in result["error"]


class TestUpdateSpace:
    @pytest.mark.asyncio
    async def test_update_space_success(self, mcp, mock_get_service, mock_chat_service):
        mock_chat_service.spaces().patch().execute.return_value = {
            "name": "spaces/abc",
            "displayName": "Updated Name",
        }

        result_raw = await mcp.call_tool(
            "manage_space",
            {
                "action": "update_space",
                "space_id": "spaces/abc",
                "display_name": "Updated Name",
            },
        )
        result = _extract_result(result_raw)
        assert result["success"] is True
        assert result["spaceId"] == "spaces/abc"

    @pytest.mark.asyncio
    async def test_update_space_missing_space_id(self, mcp, mock_get_service):
        result_raw = await mcp.call_tool(
            "manage_space",
            {"action": "update_space", "display_name": "X"},
        )
        result = _extract_result(result_raw)
        assert result["success"] is False
        assert "space_id" in result["error"]

    @pytest.mark.asyncio
    async def test_update_space_missing_fields(self, mcp, mock_get_service):
        result_raw = await mcp.call_tool(
            "manage_space",
            {"action": "update_space", "space_id": "spaces/abc"},
        )
        result = _extract_result(result_raw)
        assert result["success"] is False
        assert "Missing parameter" in (result.get("error") or "")


class TestDeleteSpace:
    @pytest.mark.asyncio
    async def test_delete_space_success(self, mcp, mock_get_service, mock_chat_service):
        mock_chat_service.spaces().delete().execute.return_value = {}

        result_raw = await mcp.call_tool(
            "manage_space",
            {"action": "delete_space", "space_id": "spaces/abc"},
        )
        result = _extract_result(result_raw)
        assert result["success"] is True
        assert result["spaceId"] == "spaces/abc"

    @pytest.mark.asyncio
    async def test_delete_space_missing_space_id(self, mcp, mock_get_service):
        result_raw = await mcp.call_tool(
            "manage_space",
            {"action": "delete_space"},
        )
        result = _extract_result(result_raw)
        assert result["success"] is False
        assert "space_id" in result["error"]


class TestServiceUnavailable:
    @pytest.mark.asyncio
    async def test_service_unavailable(self, mcp):
        with patch(
            "gchat.chat_tools._get_chat_service_with_fallback",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result_raw = await mcp.call_tool(
                "manage_space",
                {"action": "list_members", "space_id": "spaces/abc"},
            )
            result = _extract_result(result_raw)
            assert result["success"] is False
            assert "Service unavailable" in (result.get("error") or "")


class TestHttpErrorHandling:
    @pytest.mark.asyncio
    async def test_http_error_handling(self, mcp, mock_chat_service):
        from unittest.mock import PropertyMock

        from googleapiclient.errors import HttpError

        # Create a proper HttpError mock
        mock_resp = MagicMock()
        mock_resp.status = 403
        mock_resp.reason = "Forbidden"
        http_error = HttpError(resp=mock_resp, content=b"Forbidden")

        mock_chat_service.spaces().members().list().execute.side_effect = http_error

        with patch(
            "gchat.chat_tools._get_chat_service_with_fallback",
            new_callable=AsyncMock,
            return_value=mock_chat_service,
        ):
            result_raw = await mcp.call_tool(
                "manage_space",
                {"action": "list_members", "space_id": "spaces/abc"},
            )
            result = _extract_result(result_raw)
            assert result["success"] is False
            assert result["error"] is not None
