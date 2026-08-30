"""The execute result card pretty-prints JSON, one key per line.

The sandbox returns a block's value already serialized, so a dict reached the
card as a single line of compact JSON — readable only by scrolling sideways.
"""

import json

from tools.ui_apps import _build_result_card, _parse_json_data


def _find(node, type_name):
    if isinstance(node, dict):
        if node.get("type") == type_name:
            return node
        for v in node.values():
            found = _find(v, type_name)
            if found is not None:
                return found
    if isinstance(node, list):
        for v in node:
            found = _find(v, type_name)
            if found is not None:
                return found
    return None


def _card(raw):
    spec = _build_result_card(raw, ["delete_gmail_draft"]).to_json()
    return _find(spec, "Code"), _find(spec, "Badge")


class TestParseJsonData:
    def test_object_and_array(self):
        assert _parse_json_data('{"a": 1}') == {"a": 1}
        assert _parse_json_data(" [1, 2] ") == [1, 2]

    def test_scalars_and_text_are_not_data(self):
        assert _parse_json_data("42") is None
        assert _parse_json_data("true") is None
        assert _parse_json_data('"quoted"') is None
        assert _parse_json_data("done: 65 labels") is None
        assert _parse_json_data("{not json") is None
        assert _parse_json_data("") is None


class TestResultCard:
    def test_compact_json_string_is_pretty_printed(self):
        raw = json.dumps(
            {"success": True, "draftId": "r-1", "message": "Draft r-1 deleted."}
        )
        assert "\n" not in raw
        code, badge = _card(raw)
        assert badge["label"] == "JSON"
        assert code["language"] == "json"
        lines = code["content"].splitlines()
        assert lines[0] == "{"
        assert '  "success": true,' in lines
        assert '  "draftId": "r-1",' in lines
        assert '  "message": "Draft r-1 deleted."' in lines
        assert lines[-1] == "}"

    def test_dict_is_pretty_printed_too(self):
        code, badge = _card({"n": 1, "items": [1, 2]})
        assert badge["label"] == "JSON"
        assert code["content"] == '{\n  "n": 1,\n  "items": [\n    1,\n    2\n  ]\n}'

    def test_plain_text_stays_text(self):
        code, badge = _card("done: 65 labels")
        assert badge["label"] == "TEXT"
        assert code["content"] == "done: 65 labels"

    def test_unicode_survives(self):
        code, _ = _card('{"label": "Café — été"}')
        assert "Café — été" in code["content"]
