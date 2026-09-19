"""
Test that upload_photos_batch applies the caller's description.

upload_photos routes any list of paths (even a list of one, which is what the
client-filesystem handshake produces) through the batch path, which used to
hardcode "Uploaded from <filename>" and drop the description.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from photos.optimized_client import OptimizedPhotosClient


@pytest.fixture
def client(tmp_path):
    service = MagicMock()
    client = OptimizedPhotosClient(service)
    client._upload_media_content = AsyncMock(return_value="token")
    client._make_request = AsyncMock(
        return_value={"newMediaItemResults": [{"mediaItem": {"id": "m1"}}]}
    )
    photo = tmp_path / "shot.jpg"
    photo.write_bytes(b"\xff\xd8\xff")
    return client, service, str(photo)


def _sent_description(service):
    body = service.mediaItems().batchCreate.call_args.kwargs["body"]
    return body["newMediaItems"][0]["description"]


@pytest.mark.asyncio
async def test_batch_applies_description(client):
    client, service, photo = client
    results = await client.upload_photos_batch([photo], None, "My caption")
    assert len(results["successful"]) == 1
    assert _sent_description(service) == "My caption"


@pytest.mark.asyncio
async def test_batch_defaults_description_to_filename(client):
    client, service, photo = client
    await client.upload_photos_batch([photo])
    assert _sent_description(service) == "Uploaded from shot.jpg"
