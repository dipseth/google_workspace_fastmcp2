"""Tests for resolve_icon_name() in gchat/material_icons.py."""

import logging

import pytest

from gchat.material_icons import resolve_icon_name


class TestCaseNormalization:
    """Icon names should be lowercased and matched against MATERIAL_ICONS."""

    def test_uppercase_folder(self):
        assert resolve_icon_name("FOLDER") == "folder"

    def test_mixed_case(self):
        assert resolve_icon_name("Check_Circle") == "check_circle"

    def test_already_lowercase(self):
        assert resolve_icon_name("folder") == "folder"

    def test_with_whitespace(self):
        assert resolve_icon_name("  folder  ") == "folder"


class TestSemanticResolution:
    """Semantic keywords should resolve to their mapped icon names."""

    def test_success(self):
        assert resolve_icon_name("success") == "check_circle"

    def test_calendar(self):
        assert resolve_icon_name("calendar") == "calendar_today"

    def test_error(self):
        assert resolve_icon_name("error") == "error"

    def test_warning(self):
        assert resolve_icon_name("warning") == "warning"

    def test_info(self):
        assert resolve_icon_name("info") == "info"

    def test_bug(self):
        assert resolve_icon_name("bug") == "bug_report"

    def test_semantic_case_insensitive(self):
        assert resolve_icon_name("SUCCESS") == "check_circle"

    def test_semantic_calendar_uppercase(self):
        assert resolve_icon_name("CALENDAR") == "calendar_today"


class TestPassthrough:
    """Already-valid icon names should pass through unchanged."""

    def test_check_circle(self):
        assert resolve_icon_name("check_circle") == "check_circle"

    def test_arrow_forward(self):
        assert resolve_icon_name("arrow_forward") == "arrow_forward"

    def test_thumb_up(self):
        assert resolve_icon_name("thumb_up") == "thumb_up"


class TestInvalidNonStrict:
    """Unrecognized icons in non-strict mode should return as-is with a warning."""

    def test_returns_normalized(self):
        result = resolve_icon_name("xyzgarbage")
        assert result == "xyzgarbage"

    def test_logs_warning(self, caplog):
        with caplog.at_level(logging.WARNING, logger="gchat.material_icons"):
            resolve_icon_name("xyzgarbage")
        assert "Unrecognized icon name" in caplog.text
        assert "xyzgarbage" in caplog.text


class TestInvalidStrict:
    """Unrecognized icons in strict mode should raise ValueError."""

    def test_raises_value_error(self):
        with pytest.raises(ValueError, match="Invalid icon name"):
            resolve_icon_name("xyzgarbage", strict=True)

    def test_error_includes_suggestions(self):
        # "hom" is a substring of "home", "home_filled", etc.
        with pytest.raises(ValueError, match="Did you mean"):
            resolve_icon_name("hom", strict=True)

    def test_no_suggestions_for_total_garbage(self):
        with pytest.raises(ValueError, match="Invalid icon name"):
            resolve_icon_name("zzzzzzzzzzz", strict=True)


class TestEdgeCases:
    """Edge cases for icon resolution."""

    def test_semantic_that_is_also_valid_icon(self):
        # "error" is both a semantic key AND a valid material icon
        # Direct match should take priority (both resolve to "error")
        assert resolve_icon_name("error") == "error"

    def test_folder_is_direct_match_not_semantic(self):
        # "folder" is both in MATERIAL_ICONS directly and in SEMANTIC_ICONS
        # Direct match should take priority
        assert resolve_icon_name("folder") == "folder"

    def test_empty_string_strict(self):
        with pytest.raises(ValueError):
            resolve_icon_name("", strict=True)
