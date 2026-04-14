"""Tests for attachment signed URL generation, verification, and security."""

import os
import shutil
import tempfile
import time
from unittest.mock import patch

import pytest


class TestAttachmentServer:
    """Test attachment_server URL signing and file management."""

    def setup_method(self):
        from gmail.attachment_server import reset_state

        reset_state()
        self._temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self._temp_dir, ignore_errors=True)

    def _patch_settings(self):
        return patch("config.settings.settings.attachment_temp_dir", self._temp_dir)

    def test_save_and_retrieve(self):
        from gmail.attachment_server import get_attachment_path, save_attachment

        with self._patch_settings():
            file_id = save_attachment(b"hello world", "test.txt")
            path = get_attachment_path(file_id)
            assert path is not None
            with open(path, "rb") as f:
                assert f.read() == b"hello world"

    def test_url_generation_roundtrip(self):
        from gmail.attachment_server import (
            generate_attachment_url,
            save_attachment,
            verify_attachment_url,
        )

        with self._patch_settings():
            file_id = save_attachment(b"data", "report.pdf")
            url = generate_attachment_url("https://example.com", file_id, "report.pdf")

            assert "/attachment-download?" in url
            assert "fid=" in url
            assert "fn=report.pdf" in url
            assert "sig=" in url

            from urllib.parse import parse_qs, urlparse

            parsed = urlparse(url)
            params = parse_qs(parsed.query)

            valid, fid, error = verify_attachment_url(
                file_id=params["fid"][0],
                filename=params["fn"][0],
                exp=params["exp"][0],
                sig=params["sig"][0],
            )
            assert valid, error
            assert fid == file_id
            assert error == ""

    def test_one_time_use(self):
        from gmail.attachment_server import (
            generate_attachment_url,
            save_attachment,
            verify_attachment_url,
        )

        with self._patch_settings():
            file_id = save_attachment(b"data", "file.txt")
            url = generate_attachment_url("https://x.com", file_id, "file.txt")

            from urllib.parse import parse_qs, urlparse

            params = parse_qs(urlparse(url).query)
            kwargs = dict(
                file_id=params["fid"][0],
                filename=params["fn"][0],
                exp=params["exp"][0],
                sig=params["sig"][0],
            )

            valid, _, _ = verify_attachment_url(**kwargs)
            assert valid

            valid, _, error = verify_attachment_url(**kwargs)
            assert not valid
            assert "Already downloaded" in error

    def test_invalid_signature(self):
        from gmail.attachment_server import verify_attachment_url

        valid, _, error = verify_attachment_url(
            file_id="abc123",
            filename="test.txt",
            exp=str(int(time.time()) + 1000),
            sig="0" * 64,
        )
        assert not valid
        assert "Invalid signature" in error

    def test_path_traversal_rejected(self):
        from gmail.attachment_server import get_attachment_path

        with self._patch_settings():
            result = get_attachment_path("../etc/passwd")
            assert result is None

    def test_cleanup_attachment(self):
        from gmail.attachment_server import (
            cleanup_attachment,
            get_attachment_path,
            save_attachment,
        )

        with self._patch_settings():
            file_id = save_attachment(b"temp data", "temp.bin")
            path = get_attachment_path(file_id)
            assert path is not None
            assert os.path.exists(path)

            cleanup_attachment(file_id)
            assert not os.path.exists(path)

    def test_saved_file_within_temp_dir(self):
        from gmail.attachment_server import get_attachment_path, save_attachment

        with self._patch_settings():
            file_id = save_attachment(b"data", "../../etc/passwd")
            path = get_attachment_path(file_id)
            assert path is not None
            # On macOS /tmp -> /private/tmp, so realpath both sides
            real_temp = os.path.realpath(self._temp_dir)
            real_path = os.path.realpath(path)
            assert real_path.startswith(real_temp)
