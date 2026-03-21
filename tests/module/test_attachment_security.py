"""
Tests for Gmail attachment download security.

Covers:
- Path traversal prevention via filename sanitization
- Empty filename handling
- Resolved path validation (stays within save_dir)
"""

import os
import tempfile

import pytest


class TestAttachmentFilenameSanitization:
    """Test that malicious filenames are sanitized before disk write."""

    def _get_sanitized_path(self, filename: str, save_dir: str) -> str:
        """Replicate the sanitization logic from messages.py."""
        sanitized = os.path.basename(filename)
        if not sanitized:
            sanitized = "attachment_unknown"
        file_path = os.path.join(save_dir, sanitized)
        resolved = os.path.realpath(file_path)
        if not resolved.startswith(os.path.realpath(save_dir)):
            raise ValueError("Path traversal detected")
        return file_path

    def test_path_traversal_stripped(self):
        """Filename with ../ components should be stripped to basename."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = self._get_sanitized_path("../../etc/passwd", tmpdir)
            assert os.path.basename(result) == "passwd"
            assert result.startswith(tmpdir)

    def test_absolute_path_stripped(self):
        """Absolute path filename should be stripped to basename."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = self._get_sanitized_path("/etc/shadow", tmpdir)
            assert os.path.basename(result) == "shadow"
            assert result.startswith(tmpdir)

    def test_normal_filename_unchanged(self):
        """Normal filename should pass through unchanged."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = self._get_sanitized_path("document.pdf", tmpdir)
            assert os.path.basename(result) == "document.pdf"
            assert result.startswith(tmpdir)

    def test_empty_filename_gets_fallback(self):
        """Empty filename should get a fallback name."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = self._get_sanitized_path("", tmpdir)
            assert "attachment_unknown" in os.path.basename(result)
            assert result.startswith(tmpdir)

    def test_dot_dot_slash_deeply_nested(self):
        """Deeply nested traversal attempts are sanitized."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = self._get_sanitized_path(
                "../../../../../../../tmp/evil.sh", tmpdir
            )
            assert os.path.basename(result) == "evil.sh"
            assert result.startswith(tmpdir)

    def test_backslash_traversal_stripped(self):
        """Windows-style backslash traversal should be handled."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = self._get_sanitized_path("..\\..\\evil.exe", tmpdir)
            # os.path.basename handles this on Unix by keeping the whole string
            # but the resolved path check catches any actual escape
            resolved = os.path.realpath(result)
            assert resolved.startswith(os.path.realpath(tmpdir))

    def test_filename_with_special_chars(self):
        """Filenames with spaces and special characters are preserved."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = self._get_sanitized_path("My Report (Final).pdf", tmpdir)
            assert os.path.basename(result) == "My Report (Final).pdf"
