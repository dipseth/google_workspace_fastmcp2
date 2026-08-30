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


def _first(x):
    return x[0] if isinstance(x, list) else x


class TestCopyButton:
    def _click(self, raw):
        spec = _build_result_card(raw, []).to_json()
        btn = _find(spec, "Button")
        assert btn["label"] == "Copy"
        click = _first(btn["onClick"])
        assert click["action"] == "callHandler" and click["handler"] == "copy"
        return spec, click

    def test_small_result_carries_its_text_and_targets_its_code_block(self):
        spec, click = self._click('{"a": 1}')
        assert click["arguments"]["text"] == '{\n  "a": 1\n}'
        assert _find(spec, "Code")["id"] == click["arguments"]["target"]
        assert _first(click["onSuccess"])["action"] == "showToast"
        assert _first(click["onError"])["action"] == "showToast"

    def test_large_result_is_not_duplicated_into_the_button(self):
        """The card reaches the model; the body is already in it once."""
        from tools.ui_apps import _COPY_INLINE_MAX_CHARS

        big = json.dumps({"k": "x" * (_COPY_INLINE_MAX_CHARS + 10)})
        spec, click = self._click(big)
        assert "text" not in click["arguments"]
        assert click["arguments"]["target"] == _find(spec, "Code")["id"]


class TestRendererHandlers:
    def test_copy_handler_is_registered_before_the_renderer_loads(self):
        from tools.ui_apps import code_mode_renderer_html

        html = code_mode_renderer_html()
        assert "__prefab_handlers" in html
        assert "reg.actions.copy" in html
        assert html.index("__prefab_handlers") < html.index('type="module"')
        assert html.count('<div id="root">') == 1, "the page itself is intact"
