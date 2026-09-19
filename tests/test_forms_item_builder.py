"""Unit tests for the Forms item builder (no network, no credentials)."""

import pytest

from forms.forms_tools import (
    build_create_item_requests,
    build_image,
    build_question_item,
    validate_question_structure,
)

IMG = "https://example.com/poster.png"


class TestImageItem:
    def test_image_item_minimal(self):
        item = build_question_item({"type": "IMAGE_ITEM", "image_url": IMG})
        assert item == {"imageItem": {"image": {"sourceUri": IMG}}}

    def test_image_item_full(self):
        item = build_question_item(
            {
                "type": "IMAGE_ITEM",
                "image_url": IMG,
                "title": "Poster A",
                "description": "The Wall",
                "image_alt_text": "Dark poster",
                "image_width": 600,
                "image_alignment": "center",
            }
        )
        assert item["title"] == "Poster A"
        assert item["description"] == "The Wall"
        assert item["imageItem"]["image"] == {
            "sourceUri": IMG,
            "altText": "Dark poster",
            "properties": {"width": 600, "alignment": "CENTER"},
        }

    def test_image_item_requires_url(self):
        assert not validate_question_structure({"type": "IMAGE_ITEM", "title": "A"})

    @pytest.mark.parametrize("url", ["poster.png", "file:///tmp/a.png", "", None, 3])
    def test_image_url_must_be_http(self, url):
        assert not validate_question_structure({"type": "IMAGE_ITEM", "image_url": url})

    def test_bad_alignment_raises(self):
        with pytest.raises(ValueError, match="image_alignment"):
            build_image({"image_url": IMG, "image_alignment": "TOP"})


class TestQuestionImages:
    def test_question_image(self):
        item = build_question_item(
            {"type": "TEXT_QUESTION", "title": "Thoughts?", "image_url": IMG}
        )
        assert item["questionItem"]["image"] == {"sourceUri": IMG}
        assert "textQuestion" in item["questionItem"]["question"]

    def test_question_without_image_has_no_image_key(self):
        item = build_question_item({"type": "TEXT_QUESTION", "title": "Name"})
        assert "image" not in item["questionItem"]

    def test_question_with_bad_image_url_is_invalid(self):
        assert not validate_question_structure(
            {"type": "TEXT_QUESTION", "title": "Name", "image_url": "nope"}
        )

    def test_option_images_mix_with_plain_options(self):
        item = build_question_item(
            {
                "type": "MULTIPLE_CHOICE_QUESTION",
                "title": "Pick",
                "options": [{"value": "A", "image_url": IMG}, "B"],
            }
        )
        choice = item["questionItem"]["question"]["choiceQuestion"]
        assert choice["type"] == "RADIO"
        assert choice["options"] == [
            {"value": "A", "image": {"sourceUri": IMG}},
            {"value": "B"},
        ]

    def test_option_dict_without_value_raises(self):
        with pytest.raises(ValueError, match="value"):
            build_question_item(
                {
                    "type": "CHECKBOX_QUESTION",
                    "title": "Pick",
                    "options": [{"image_url": IMG}],
                }
            )


class TestOtherItems:
    def test_description_on_question(self):
        item = build_question_item(
            {"type": "TEXT_QUESTION", "title": "Name", "description": "Optional"}
        )
        assert item["description"] == "Optional"

    def test_text_item(self):
        item = build_question_item(
            {"type": "TEXT_ITEM", "title": "Heads up", "description": "2 minutes"}
        )
        assert item == {"title": "Heads up", "description": "2 minutes", "textItem": {}}

    def test_page_break_item(self):
        item = build_question_item({"type": "PAGE_BREAK_ITEM", "title": "Part 2"})
        assert item == {"title": "Part 2", "pageBreakItem": {}}

    def test_video_item(self):
        url = "https://www.youtube.com/watch?v=abc"
        item = build_question_item(
            {"type": "VIDEO_ITEM", "youtube_url": url, "caption": "Watch"}
        )
        assert item == {"videoItem": {"video": {"youtubeUri": url}, "caption": "Watch"}}

    def test_dropdown(self):
        item = build_question_item(
            {"type": "DROPDOWN_QUESTION", "title": "Pick", "options": ["A", "B"]}
        )
        choice = item["questionItem"]["question"]["choiceQuestion"]
        assert choice["type"] == "DROP_DOWN"

    def test_existing_question_shape_unchanged(self):
        item = build_question_item(
            {
                "type": "MULTIPLE_CHOICE_QUESTION",
                "title": "Pick one",
                "options": ["A", "B"],
                "required": True,
            }
        )
        assert item == {
            "title": "Pick one",
            "questionItem": {
                "question": {
                    "required": True,
                    "choiceQuestion": {
                        "type": "RADIO",
                        "options": [{"value": "A"}, {"value": "B"}],
                        "shuffle": False,
                    },
                }
            },
        }

    def test_unknown_type_is_invalid(self):
        assert not validate_question_structure({"type": "NOPE", "title": "x"})


class TestCreateItemRequests:
    def test_indexes_start_at_offset(self):
        requests, skipped = build_create_item_requests(
            [
                {"type": "IMAGE_ITEM", "image_url": IMG},
                {"type": "TEXT_QUESTION", "title": "Name"},
            ],
            start_index=11,
        )
        assert [r["createItem"]["location"]["index"] for r in requests] == [11, 12]
        assert skipped == []

    def test_skipped_item_leaves_no_index_gap(self):
        requests, skipped = build_create_item_requests(
            [
                {"type": "TEXT_QUESTION", "title": "One"},
                {"type": "IMAGE_ITEM"},  # no image_url
                {"type": "TEXT_QUESTION", "title": "Two"},
            ],
            start_index=0,
        )
        assert [r["createItem"]["location"]["index"] for r in requests] == [0, 1]
        assert len(skipped) == 1 and skipped[0].startswith("#1:")
