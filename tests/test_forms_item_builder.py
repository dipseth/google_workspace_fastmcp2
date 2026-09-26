"""Unit tests for the Forms item builder (no network, no credentials)."""

import pytest

from forms.forms_tools import (
    build_batch_update_request,
    build_create_item_requests,
    build_image,
    build_question_item,
    build_settings_requests,
    extract_question_type,
    format_question_details,
    validate_question_structure,
    validate_update_request,
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


FORM_ITEMS = [
    {"itemId": "img1", "title": "Poster A", "imageItem": {"image": {}}},
    {
        "itemId": "q1",
        "title": "Pick one",
        "questionItem": {
            "question": {
                "required": True,
                "choiceQuestion": {"type": "CHECKBOX", "options": [{"value": "A"}]},
            }
        },
    },
    {
        "itemId": "q2",
        "title": "Name",
        "questionItem": {"question": {"textQuestion": {}}},
    },
    {"itemId": "txt1", "title": "Heading", "textItem": {}},
]


class TestBatchUpdate:
    def test_fields_merge_into_one_update_with_location(self):
        body = build_batch_update_request(
            [{"item_id": "q2", "title": "Your name", "required": True}], FORM_ITEMS
        )
        assert body["requests"] == [
            {
                "updateItem": {
                    "item": {
                        "itemId": "q2",
                        "title": "Your name",
                        "questionItem": {"question": {"required": True}},
                    },
                    "location": {"index": 2},
                    "updateMask": "title,questionItem.question.required",
                }
            }
        ]

    def test_options_with_images_keep_the_choice_type(self):
        body = build_batch_update_request(
            [
                {
                    "item_id": "q1",
                    "options": [{"value": "A", "image_url": IMG}, "None of them"],
                }
            ],
            FORM_ITEMS,
        )
        update = body["requests"][0]["updateItem"]
        choice = update["item"]["questionItem"]["question"]["choiceQuestion"]
        assert choice["type"] == "CHECKBOX"
        assert choice["options"] == [
            {"value": "A", "image": {"sourceUri": IMG}},
            {"value": "None of them"},
        ]
        assert update["updateMask"] == "questionItem.question.choiceQuestion.options"
        assert update["location"] == {"index": 1}

    def test_image_url_targets_question_or_image_item(self):
        body = build_batch_update_request(
            [
                {"item_id": "q2", "image_url": IMG},
                {"item_id": "img1", "image_url": IMG, "image_alignment": "center"},
            ],
            FORM_ITEMS,
        )
        first, second = [r["updateItem"] for r in body["requests"]]
        assert first["item"]["questionItem"]["image"] == {"sourceUri": IMG}
        assert first["updateMask"] == "questionItem.image"
        assert second["item"]["imageItem"]["image"]["properties"] == {
            "alignment": "CENTER"
        }
        assert second["updateMask"] == "imageItem.image"

    def test_deletes_run_last_from_the_highest_index(self):
        body = build_batch_update_request(
            [
                {"item_id": "img1", "delete": True},
                {"item_id": "q2", "title": "Your name"},
                {"item_id": "txt1", "delete": True},
            ],
            FORM_ITEMS,
        )
        assert [list(r)[0] for r in body["requests"]] == [
            "updateItem",
            "deleteItem",
            "deleteItem",
        ]
        assert [r["deleteItem"]["location"]["index"] for r in body["requests"][1:]] == [
            3,
            0,
        ]

    @pytest.mark.parametrize(
        "update",
        [
            {"item_id": "missing", "title": "x"},
            {"item_id": "q2", "options": ["A"]},
            {"item_id": "txt1", "required": True},
            {"item_id": "txt1", "image_url": IMG},
        ],
    )
    def test_mismatched_updates_raise(self, update):
        with pytest.raises(ValueError):
            build_batch_update_request([update], FORM_ITEMS)

    def test_validator_accepts_new_fields_and_rejects_unknown(self):
        assert validate_update_request({"item_id": "q1", "required": True})[0]
        assert validate_update_request({"item_id": "q1", "delete": True})[0]
        assert not validate_update_request({"item_id": "q1", "bogus": 1})[0]
        assert not validate_update_request({"item_id": "q1"})[0]


class TestReadingQuestionsBack:
    """get_form reported every question as "Unknown": the API's Question has no
    "type" field, the kind is whichever *Question key is present."""

    def _item(self, question, **question_item):
        return {
            "itemId": "q1",
            "title": "Pick",
            "questionItem": {"question": question, **question_item},
        }

    def test_kind_comes_from_the_question_key(self):
        assert extract_question_type(self._item({"textQuestion": {}})) == "TEXT"
        assert extract_question_type(self._item({"scaleQuestion": {}})) == "SCALE"
        assert (
            extract_question_type(self._item({"fileUploadQuestion": {}}))
            == "FILE_UPLOAD"
        )
        assert extract_question_type({"textItem": {}}) == "NOT_A_QUESTION"

    def test_choice_details_list_kind_options_and_images(self):
        item = self._item(
            {
                "required": True,
                "choiceQuestion": {
                    "type": "DROP_DOWN",
                    "shuffle": True,
                    "options": [
                        {"value": "Blue", "image": {"contentUri": "https://x"}},
                        {"value": "Yellow"},
                    ],
                },
            },
            image={"contentUri": "https://y"},
        )
        details = format_question_details(item)
        assert "Type: MULTIPLE_CHOICE" in details
        assert "Required: Yes" in details
        assert "Kind: Dropdown" in details
        assert "Options: Blue, Yellow" in details
        assert "Option images: 1" in details
        assert "Shuffled: Yes" in details
        assert "Image: Yes" in details
        assert "Unknown" not in details

    def test_text_question_details(self):
        details = format_question_details(
            self._item({"textQuestion": {"paragraph": True}})
        )
        assert "Type: TEXT" in details and "Paragraph: Yes" in details
        assert "Image" not in details


class TestBranchingAndOther:
    def test_options_branch_by_action_or_section(self):
        item = build_question_item(
            {
                "type": "MULTIPLE_CHOICE_QUESTION",
                "title": "Attending?",
                "options": [
                    {"value": "Yes", "go_to_section_id": "sec2"},
                    {"value": "No", "go_to_action": "submit_form"},
                    {"is_other": True},
                ],
            }
        )
        assert item["questionItem"]["question"]["choiceQuestion"]["options"] == [
            {"value": "Yes", "goToSectionId": "sec2"},
            {"value": "No", "goToAction": "SUBMIT_FORM"},
            {"isOther": True},
        ]

    @pytest.mark.parametrize(
        "q_type, option",
        [
            ("CHECKBOX_QUESTION", {"value": "A", "go_to_action": "NEXT_SECTION"}),
            ("DROPDOWN_QUESTION", {"is_other": True}),
            ("MULTIPLE_CHOICE_QUESTION", {"value": "A", "go_to_action": "NOWHERE"}),
            (
                "MULTIPLE_CHOICE_QUESTION",
                {"value": "A", "go_to_action": "SUBMIT_FORM", "go_to_section_id": "s"},
            ),
        ],
    )
    def test_unsupported_option_fields_raise(self, q_type, option):
        with pytest.raises(ValueError):
            build_question_item({"type": q_type, "title": "Q", "options": [option]})

    def test_update_checks_branching_against_the_existing_kind(self):
        branching = [{"value": "A", "go_to_action": "SUBMIT_FORM"}]
        # q1 is a checkbox question, which cannot branch
        with pytest.raises(ValueError):
            build_batch_update_request(
                [{"item_id": "q1", "options": branching}], FORM_ITEMS
            )

        radio = {
            "itemId": "r1",
            "questionItem": {"question": {"choiceQuestion": {"type": "RADIO"}}},
        }
        body = build_batch_update_request(
            [{"item_id": "r1", "options": branching}], [radio]
        )
        choice = body["requests"][0]["updateItem"]["item"]["questionItem"]["question"][
            "choiceQuestion"
        ]
        assert choice["options"] == [{"value": "A", "goToAction": "SUBMIT_FORM"}]


class TestGridRatingVideo:
    def test_grid(self):
        item = build_question_item(
            {
                "type": "GRID_QUESTION",
                "title": "Rate each",
                "rows": ["Speed", "Price"],
                "columns": ["Bad", "Good"],
                "multiple": True,
                "shuffle_rows": True,
                "required": True,
            }
        )
        assert item == {
            "title": "Rate each",
            "questionGroupItem": {
                "questions": [
                    {"required": True, "rowQuestion": {"title": "Speed"}},
                    {"required": True, "rowQuestion": {"title": "Price"}},
                ],
                "grid": {
                    "columns": {
                        "type": "CHECKBOX",
                        "options": [{"value": "Bad"}, {"value": "Good"}],
                    },
                    "shuffleQuestions": True,
                },
            },
        }

    @pytest.mark.parametrize(
        "grid", [{"rows": [], "columns": ["A"]}, {"rows": ["R"]}, {"columns": ["A"]}]
    )
    def test_grid_needs_rows_and_columns(self, grid):
        assert not validate_question_structure(
            {"type": "GRID_QUESTION", "title": "G", **grid}
        )

    def test_rating_icon_defaults_to_star(self):
        rating = {"type": "RATING_QUESTION", "title": "R", "rating_scale_level": 5}
        built = build_question_item(rating)["questionItem"]["question"]
        assert built["ratingQuestion"] == {"ratingScaleLevel": 5, "iconType": "STAR"}
        built = build_question_item({**rating, "icon_type": "heart"})
        assert (
            built["questionItem"]["question"]["ratingQuestion"]["iconType"] == "HEART"
        )
        with pytest.raises(ValueError):
            build_question_item({**rating, "icon_type": "SMILEY"})

    def test_video_properties(self):
        item = build_question_item(
            {
                "type": "VIDEO_ITEM",
                "youtube_url": "https://www.youtube.com/watch?v=abc",
                "video_width": 480,
                "video_alignment": "center",
            }
        )
        assert item["videoItem"]["video"]["properties"] == {
            "width": 480,
            "alignment": "CENTER",
        }


class TestMoves:
    def test_moves_track_the_order_left_by_earlier_moves(self):
        ids = [item["itemId"] for item in FORM_ITEMS]
        first, last = ids[0], ids[-1]
        body = build_batch_update_request(
            [
                {"item_id": last, "move_to_index": 0},
                {"item_id": first, "move_to_index": 0},
            ],
            FORM_ITEMS,
        )
        n = len(ids) - 1
        assert [r["moveItem"] for r in body["requests"]] == [
            {"originalLocation": {"index": n}, "newLocation": {"index": 0}},
            {"originalLocation": {"index": 1}, "newLocation": {"index": 0}},
        ]

    def test_delete_index_follows_a_move(self):
        ids = [item["itemId"] for item in FORM_ITEMS]
        body = build_batch_update_request(
            [
                {"item_id": ids[0], "delete": True},
                {"item_id": ids[-1], "move_to_index": 0},
            ],
            FORM_ITEMS,
        )
        assert [list(r)[0] for r in body["requests"]] == ["moveItem", "deleteItem"]
        assert body["requests"][1]["deleteItem"]["location"]["index"] == 1

    def test_noop_move_is_dropped_and_bad_index_raises(self):
        ids = [item["itemId"] for item in FORM_ITEMS]
        assert build_batch_update_request(
            [{"item_id": ids[0], "move_to_index": 0}], FORM_ITEMS
        ) == {"requests": []}
        with pytest.raises(ValueError):
            build_batch_update_request(
                [{"item_id": ids[0], "move_to_index": len(ids)}], FORM_ITEMS
            )


class TestSettingsRequests:
    def test_only_given_fields_are_masked(self):
        assert build_settings_requests() == []
        assert build_settings_requests(description="") == [
            {
                "updateFormInfo": {
                    "info": {"description": ""},
                    "updateMask": "description",
                }
            }
        ]
        assert build_settings_requests(
            title="T", is_quiz=True, email_collection_type="verified"
        ) == [
            {"updateFormInfo": {"info": {"title": "T"}, "updateMask": "title"}},
            {
                "updateSettings": {
                    "settings": {
                        "quizSettings": {"isQuiz": True},
                        "emailCollectionType": "VERIFIED",
                    },
                    "updateMask": "quizSettings.isQuiz,emailCollectionType",
                }
            },
        ]

    def test_bad_email_collection_type_raises(self):
        with pytest.raises(ValueError):
            build_settings_requests(email_collection_type="ALWAYS")
