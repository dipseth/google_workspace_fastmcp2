"""
Tests for download_drive_file: byte downloads of Drive files.

get_drive_file_content only returns text, so binary files (scanned PDFs,
images) came back as "[Binary or unsupported text encoding]". These cover the
byte path: signed URL (default), base64, and save-to-disk, plus exports of
native Google files, shortcuts, and the size limits.
"""

import base64
import os
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import parse_qs, urlparse

import pytest

from drive import drive_tools
from drive.drive_tools import download_drive_file

PDF_BYTES = b"%PDF-1.7\n\xff\xfe\x00scanned page bytes\x80\x81"
PDF_MIME = "application/pdf"
DOC_MIME = "application/vnd.google-apps.document"
SHEET_MIME = "application/vnd.google-apps.spreadsheet"


class FakeDownloader:
    """Stands in for MediaIoBaseDownload: writes the request's bytes in chunks."""

    def __init__(self, fh, request, chunksize=None):
        self._fh = fh
        self._chunks = list(request.chunks)

    def next_chunk(self):
        self._fh.write(self._chunks.pop(0))
        return None, not self._chunks


def _media_request(content: bytes, chunks: int = 1):
    request = MagicMock()
    step = max(1, len(content) // chunks)
    request.chunks = [content[i : i + step] for i in range(0, len(content), step)]
    return request


def _drive_service(files_by_id: dict, content: bytes = PDF_BYTES, chunks: int = 1):
    """Drive service whose files().get() serves ``files_by_id`` metadata."""
    service = MagicMock()
    files = service.files.return_value

    def _get(fileId, **kwargs):
        call = MagicMock()
        call.execute.return_value = files_by_id[fileId]
        return call

    files.get.side_effect = _get
    files.get_media.return_value = _media_request(content, chunks)
    files.export_media.return_value = _media_request(content, chunks)
    return service


def _pdf_metadata(size: int = len(PDF_BYTES)):
    return {
        "id": "pdf1",
        "name": "Scanned_20260928-2226.pdf",
        "mimeType": PDF_MIME,
        "size": str(size),
        "webViewLink": "https://drive.google.com/file/d/pdf1/view",
    }


@pytest.fixture
def temp_dir(tmp_path):
    from gmail.attachment_server import reset_state

    reset_state()
    attachments = tmp_path / "attachments"
    with patch("config.settings.settings.attachment_temp_dir", str(attachments)):
        yield attachments


@pytest.fixture
def use_service():
    """Patch the Drive service lookup and the chunked downloader."""

    def _use(service):
        service_patch = patch.object(
            drive_tools,
            "_get_drive_service_with_fallback",
            AsyncMock(return_value=service),
        )
        downloader_patch = patch.object(
            drive_tools, "MediaIoBaseDownload", FakeDownloader
        )
        service_patch.start()
        downloader_patch.start()
        return service

    yield _use
    patch.stopall()


async def test_binary_file_returns_signed_url(temp_dir, use_service):
    from gmail.attachment_server import get_attachment_path, verify_attachment_url

    service = use_service(_drive_service({"pdf1": _pdf_metadata()}, chunks=3))

    result = await download_drive_file("pdf1")

    assert result["success"] is True
    assert result["fileName"] == "Scanned_20260928-2226.pdf"
    assert result["mimeType"] == PDF_MIME
    assert result["size"] == len(PDF_BYTES)
    assert "data" not in result and "file_path" not in result
    service.files.return_value.export_media.assert_not_called()

    # The URL verifies and points at the exact bytes Drive served
    params = parse_qs(urlparse(result["download_url"]).query)
    valid, fid, error = verify_attachment_url(
        params["fid"][0], params["fn"][0], params["exp"][0], params["sig"][0]
    )
    assert valid, error
    with open(get_attachment_path(fid), "rb") as f:
        assert f.read() == PDF_BYTES


async def test_signed_url_is_served_by_download_endpoint(temp_dir, use_service):
    from fastmcp import FastMCP
    from starlette.testclient import TestClient

    from tools.attachment_endpoints import setup_attachment_endpoints

    use_service(_drive_service({"pdf1": _pdf_metadata()}))
    result = await download_drive_file("pdf1")

    mcp = FastMCP("test")
    setup_attachment_endpoints(mcp)
    url = urlparse(result["download_url"])
    with TestClient(mcp.http_app()) as client:
        served = client.get(f"{url.path}?{url.query}")
        assert served.status_code == 200
        assert served.content == PDF_BYTES
        assert "Scanned_20260928-2226.pdf" in served.headers["content-disposition"]
        # One-time use
        assert client.get(f"{url.path}?{url.query}").status_code == 410


async def test_return_content_gives_base64(temp_dir, use_service):
    use_service(_drive_service({"pdf1": _pdf_metadata()}))

    result = await download_drive_file("pdf1", return_url=False, return_content=True)

    assert result["success"] is True
    assert base64.b64decode(result["data"]) == PDF_BYTES
    assert "download_url" not in result
    assert not temp_dir.exists() or not os.listdir(temp_dir)


async def test_save_dir_writes_file_without_overwriting(tmp_path, use_service):
    use_service(_drive_service({"pdf1": _pdf_metadata()}))
    save_dir = tmp_path / "out"

    first = await download_drive_file("pdf1", return_url=False, save_dir=str(save_dir))
    use_service(_drive_service({"pdf1": _pdf_metadata()}))
    second = await download_drive_file("pdf1", return_url=False, save_dir=str(save_dir))

    assert first["file_path"] == str(save_dir / "Scanned_20260928-2226.pdf")
    assert second["file_path"] == str(save_dir / "Scanned_20260928-2226 (1).pdf")
    for result in (first, second):
        with open(result["file_path"], "rb") as f:
            assert f.read() == PDF_BYTES


@pytest.mark.parametrize(
    "source_mime,export_format,expected_mime,expected_name",
    [
        (DOC_MIME, None, PDF_MIME, "Plan.pdf"),
        (
            SHEET_MIME,
            None,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "Plan.xlsx",
        ),
        (
            DOC_MIME,
            "docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "Plan.docx",
        ),
    ],
)
async def test_native_files_are_exported(
    temp_dir, use_service, source_mime, export_format, expected_mime, expected_name
):
    service = use_service(
        _drive_service({"g1": {"id": "g1", "name": "Plan", "mimeType": source_mime}})
    )

    result = await download_drive_file("g1", export_format=export_format)

    assert result["success"] is True
    assert result["fileName"] == expected_name
    assert result["mimeType"] == expected_mime
    assert result["sourceMimeType"] == source_mime
    service.files.return_value.export_media.assert_called_once_with(
        fileId="g1", mimeType=expected_mime
    )
    service.files.return_value.get_media.assert_not_called()


async def test_export_format_ignored_for_uploaded_files(temp_dir, use_service):
    service = use_service(_drive_service({"pdf1": _pdf_metadata()}))

    result = await download_drive_file("pdf1", export_format="docx")

    assert result["success"] is True
    assert result["mimeType"] == PDF_MIME
    assert result["fileName"] == "Scanned_20260928-2226.pdf"
    service.files.return_value.export_media.assert_not_called()


async def test_shortcut_downloads_its_target(temp_dir, use_service):
    service = use_service(
        _drive_service(
            {
                "sc1": {
                    "id": "sc1",
                    "name": "Shortcut to scan",
                    "mimeType": "application/vnd.google-apps.shortcut",
                    "shortcutDetails": {"targetId": "pdf1"},
                },
                "pdf1": _pdf_metadata(),
            }
        )
    )

    result = await download_drive_file("sc1")

    assert result["success"] is True
    assert result["fileId"] == "pdf1"
    assert result["fileName"] == "Scanned_20260928-2226.pdf"
    assert service.files.return_value.get_media.call_args.kwargs["fileId"] == "pdf1"


async def test_folder_has_no_content(temp_dir, use_service):
    service = use_service(
        _drive_service(
            {
                "f1": {
                    "id": "f1",
                    "name": "Recipes",
                    "mimeType": "application/vnd.google-apps.folder",
                }
            }
        )
    )

    result = await download_drive_file("f1")

    assert result["success"] is False
    assert "no downloadable content" in result["error"]
    service.files.return_value.get_media.assert_not_called()
    service.files.return_value.export_media.assert_not_called()


async def test_oversized_file_rejected_before_download(temp_dir, use_service):
    service = use_service(
        _drive_service({"pdf1": _pdf_metadata(size=101 * 1024 * 1024)})
    )

    result = await download_drive_file("pdf1")

    assert result["success"] is False
    assert "too large" in result["error"]
    assert "100 MB" in result["error"]
    service.files.return_value.get_media.assert_not_called()


async def test_base64_has_tighter_limit(temp_dir, use_service):
    use_service(_drive_service({"pdf1": _pdf_metadata(size=11 * 1024 * 1024)}))

    result = await download_drive_file("pdf1", return_url=False, return_content=True)

    assert result["success"] is False
    assert "10 MB" in result["error"]


async def test_oversized_export_aborts_and_cleans_up(temp_dir, use_service):
    # Exports report no size, so the limit can only trip mid-stream
    use_service(
        _drive_service(
            {"g1": {"id": "g1", "name": "Plan", "mimeType": DOC_MIME}},
            content=b"x" * 4096,
            chunks=4,
        )
    )

    with patch("config.settings.settings.drive_download_max_size_mb", 0.001):
        result = await download_drive_file("g1")

    assert result["success"] is False
    assert "too large" in result["error"]
    assert os.listdir(temp_dir) == []


async def test_drive_api_error_is_reported(temp_dir, use_service):
    from googleapiclient.errors import HttpError

    service = use_service(_drive_service({}))
    response = MagicMock(status=404, reason="Not Found")
    service.files.return_value.get.side_effect = HttpError(response, b"File not found")

    result = await download_drive_file("missing")

    assert result["success"] is False
    assert result["fileId"] == "missing"
    assert "Drive API error" in result["error"]
