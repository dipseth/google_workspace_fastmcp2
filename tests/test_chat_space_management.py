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


class TestGetMessage:
    @pytest.mark.asyncio
    async def test_get_message_success(self, mcp, mock_get_service, mock_chat_service):
        mock_chat_service.spaces().messages().get().execute.return_value = {
            "name": "spaces/abc/messages/msg1",
            "text": "Hello world",
            "space": {"name": "spaces/abc"},
            "createTime": "2024-01-01T00:00:00Z",
        }

        result_raw = await mcp.call_tool(
            "manage_space",
            {"action": "get_message", "message_name": "spaces/abc/messages/msg1"},
        )
        result = _extract_result(result_raw)
        assert result["success"] is True
        assert result["data"]["message"]["text"] == "Hello world"

    @pytest.mark.asyncio
    async def test_get_message_missing_message_name(self, mcp, mock_get_service):
        result_raw = await mcp.call_tool(
            "manage_space",
            {"action": "get_message"},
        )
        result = _extract_result(result_raw)
        assert result["success"] is False
        assert "message_name" in result["error"]


class TestUpdateMessage:
    @pytest.mark.asyncio
    async def test_update_message_success(
        self, mcp, mock_get_service, mock_chat_service
    ):
        mock_chat_service.spaces().messages().patch().execute.return_value = {
            "name": "spaces/abc/messages/msg1",
            "text": "Edited text",
            "space": {"name": "spaces/abc"},
        }

        result_raw = await mcp.call_tool(
            "manage_space",
            {
                "action": "update_message",
                "message_name": "spaces/abc/messages/msg1",
                "message_text": "Edited text",
            },
        )
        result = _extract_result(result_raw)
        assert result["success"] is True
        assert result["data"]["message"]["text"] == "Edited text"

    @pytest.mark.asyncio
    async def test_update_message_missing_message_name(self, mcp, mock_get_service):
        result_raw = await mcp.call_tool(
            "manage_space",
            {"action": "update_message", "message_text": "x"},
        )
        result = _extract_result(result_raw)
        assert result["success"] is False
        assert "message_name" in result["error"]

    @pytest.mark.asyncio
    async def test_update_message_missing_message_text(self, mcp, mock_get_service):
        result_raw = await mcp.call_tool(
            "manage_space",
            {"action": "update_message", "message_name": "spaces/abc/messages/msg1"},
        )
        result = _extract_result(result_raw)
        assert result["success"] is False
        assert "message_text" in result["error"]


class TestDeleteMessage:
    @pytest.mark.asyncio
    async def test_delete_message_success(
        self, mcp, mock_get_service, mock_chat_service
    ):
        mock_chat_service.spaces().messages().delete().execute.return_value = {}

        result_raw = await mcp.call_tool(
            "manage_space",
            {"action": "delete_message", "message_name": "spaces/abc/messages/msg1"},
        )
        result = _extract_result(result_raw)
        assert result["success"] is True
        assert result["data"]["deletedMessage"] == "spaces/abc/messages/msg1"

    @pytest.mark.asyncio
    async def test_delete_message_missing_message_name(self, mcp, mock_get_service):
        result_raw = await mcp.call_tool(
            "manage_space",
            {"action": "delete_message"},
        )
        result = _extract_result(result_raw)
        assert result["success"] is False
        assert "message_name" in result["error"]


class TestAddReaction:
    @pytest.mark.asyncio
    async def test_add_reaction_success(self, mcp, mock_get_service, mock_chat_service):
        mock_chat_service.spaces().messages().reactions().create().execute.return_value = {
            "name": "spaces/abc/messages/msg1/reactions/r1",
            "emoji": {"unicode": "\U0001f680"},
        }

        result_raw = await mcp.call_tool(
            "manage_space",
            {
                "action": "add_reaction",
                "message_name": "spaces/abc/messages/msg1",
                "emoji": "\U0001f680",
                "user_google_email": "user@example.com",
            },
        )
        result = _extract_result(result_raw)
        assert result["success"] is True
        assert "reaction" in result["data"]

    @pytest.mark.asyncio
    async def test_add_reaction_missing_message_name(self, mcp, mock_get_service):
        result_raw = await mcp.call_tool(
            "manage_space",
            {
                "action": "add_reaction",
                "emoji": "\U0001f680",
                "user_google_email": "u@x.com",
            },
        )
        result = _extract_result(result_raw)
        assert result["success"] is False
        assert "message_name" in result["error"]

    @pytest.mark.asyncio
    async def test_add_reaction_missing_emoji(self, mcp, mock_get_service):
        result_raw = await mcp.call_tool(
            "manage_space",
            {
                "action": "add_reaction",
                "message_name": "spaces/abc/messages/msg1",
                "user_google_email": "u@x.com",
            },
        )
        result = _extract_result(result_raw)
        assert result["success"] is False
        assert "emoji" in result["error"]

    @pytest.mark.asyncio
    async def test_add_reaction_missing_user_email(self, mcp, mock_get_service):
        result_raw = await mcp.call_tool(
            "manage_space",
            {
                "action": "add_reaction",
                "message_name": "spaces/abc/messages/msg1",
                "emoji": "\U0001f680",
            },
        )
        result = _extract_result(result_raw)
        assert result["success"] is False
        assert "user_google_email" in result["error"] or "user-level" in result["error"]


class TestListReactions:
    @pytest.mark.asyncio
    async def test_list_reactions_success(
        self, mcp, mock_get_service, mock_chat_service
    ):
        mock_chat_service.spaces().messages().reactions().list().execute.return_value = {
            "reactions": [
                {
                    "name": "spaces/abc/messages/msg1/reactions/r1",
                    "emoji": {"unicode": "\U0001f44d"},
                    "user": {"name": "users/123", "type": "HUMAN"},
                }
            ]
        }

        result_raw = await mcp.call_tool(
            "manage_space",
            {
                "action": "list_reactions",
                "message_name": "spaces/abc/messages/msg1",
                "user_google_email": "user@example.com",
            },
        )
        result = _extract_result(result_raw)
        assert result["success"] is True
        assert result["data"]["count"] == 1

    @pytest.mark.asyncio
    async def test_list_reactions_missing_message_name(self, mcp, mock_get_service):
        result_raw = await mcp.call_tool(
            "manage_space",
            {"action": "list_reactions", "user_google_email": "u@x.com"},
        )
        result = _extract_result(result_raw)
        assert result["success"] is False
        assert "message_name" in result["error"]

    @pytest.mark.asyncio
    async def test_list_reactions_missing_user_email(self, mcp, mock_get_service):
        result_raw = await mcp.call_tool(
            "manage_space",
            {"action": "list_reactions", "message_name": "spaces/abc/messages/msg1"},
        )
        result = _extract_result(result_raw)
        assert result["success"] is False
        assert "user_google_email" in result["error"] or "user-level" in result["error"]


class TestDeleteReaction:
    @pytest.mark.asyncio
    async def test_delete_reaction_success(
        self, mcp, mock_get_service, mock_chat_service
    ):
        mock_chat_service.spaces().messages().reactions().delete().execute.return_value = {}

        result_raw = await mcp.call_tool(
            "manage_space",
            {
                "action": "delete_reaction",
                "reaction_name": "spaces/abc/messages/msg1/reactions/r1",
                "user_google_email": "user@example.com",
            },
        )
        result = _extract_result(result_raw)
        assert result["success"] is True
        assert (
            result["data"]["deletedReaction"] == "spaces/abc/messages/msg1/reactions/r1"
        )

    @pytest.mark.asyncio
    async def test_delete_reaction_missing_reaction_name(self, mcp, mock_get_service):
        result_raw = await mcp.call_tool(
            "manage_space",
            {"action": "delete_reaction", "user_google_email": "u@x.com"},
        )
        result = _extract_result(result_raw)
        assert result["success"] is False
        assert "reaction_name" in result["error"]

    @pytest.mark.asyncio
    async def test_delete_reaction_missing_user_email(self, mcp, mock_get_service):
        result_raw = await mcp.call_tool(
            "manage_space",
            {
                "action": "delete_reaction",
                "reaction_name": "spaces/abc/messages/msg1/reactions/r1",
            },
        )
        result = _extract_result(result_raw)
        assert result["success"] is False
        assert "user_google_email" in result["error"] or "user-level" in result["error"]


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
