"""
Test create_photos_album's create-or-rename behavior.

Renaming an app-created album uses albums.patch, which is the only
Photos Library operation in this codebase that exercises the
photoslibrary.edit.appcreateddata scope (Google's verification review
requires every configured scope to map to a demonstrable feature).

These tests mock the Photos service, so they run in every environment.
"""

from unittest.mock import MagicMock, patch

import pytest
from fastmcp import FastMCP

from photos.photos_tools import setup_photos_tools


@pytest.fixture
def create_album_fn():
    import asyncio

    mcp = FastMCP("test")
    setup_photos_tools(mcp)
    tool = asyncio.run(mcp.get_tool("create_photos_album"))
    return tool.fn


@pytest.fixture
def mock_photos_service():
    service = MagicMock()
    with patch(
        "photos.photos_tools._get_photos_service_with_fallback",
        return_value=service,
    ):
        yield service


@pytest.mark.asyncio
async def test_create_mode_calls_albums_create(create_album_fn, mock_photos_service):
    mock_photos_service.albums().create().execute.return_value = {
        "id": "album-123",
        "title": "My Album",
        "productUrl": "https://photos.google.com/album/123",
    }

    result = await create_album_fn(
        user_google_email="user@example.com", title="My Album"
    )

    assert result.success is True
    assert result.album_id == "album-123"
    assert result.album_title == "My Album"
    mock_photos_service.albums().create.assert_called_with(
        body={"album": {"title": "My Album"}}
    )
    mock_photos_service.albums().patch.assert_not_called()


@pytest.mark.asyncio
async def test_rename_mode_calls_albums_patch(create_album_fn, mock_photos_service):
    mock_photos_service.albums().patch().execute.return_value = {
        "id": "album-123",
        "title": "New Title",
        "productUrl": "https://photos.google.com/album/123",
    }

    result = await create_album_fn(
        user_google_email="user@example.com",
        title="New Title",
        album_id="album-123",
    )

    assert result.success is True
    assert result.album_id == "album-123"
    assert result.album_title == "New Title"
    assert "renamed" in result.message
    mock_photos_service.albums().patch.assert_called_with(
        id="album-123", updateMask="title", body={"title": "New Title"}
    )


@pytest.mark.asyncio
async def test_rename_failure_reports_error(create_album_fn, mock_photos_service):
    mock_photos_service.albums().patch().execute.side_effect = RuntimeError(
        "permission denied"
    )

    result = await create_album_fn(
        user_google_email="user@example.com",
        title="New Title",
        album_id="album-123",
    )

    assert result.success is False
    assert result.album_id == "album-123"
    assert result.error is not None
