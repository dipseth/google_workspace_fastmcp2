"""Unit tests for EnhancedSandboxProvider helpers in tools/code_mode.py.

Two layers of tests:

1. Helper logic (via _build_helpers()) — no server, no Monty.
   These verify that each lambda does what it claims.  They do NOT cover
   Monty-sandbox behaviour — a helper can work fine in isolation yet still
   fail when LLM-generated code passes it through the parser.

2. Sandbox error-handling (async, via EnhancedSandboxProvider.run()) — no
   server, but pydantic_monty must be installed.  These test the failure
   modes that bite LLM code in production:
     - Starred expressions ([*a, *b], {**d}) fail at PARSE TIME — the entire
       code block is rejected before any line executes, so a try/except
       inside the code is useless.
     - Lambda arguments to sorted_() cause TypeError at runtime because Monty
       serialises lambda objects to strings before passing them to the helper.
"""

import copy
import json

import pytest
import pytest_asyncio

from tools.code_mode import EnhancedSandboxProvider, _format_sandbox_error


@pytest.fixture(scope="module")
def h():
    """All helpers as a dict."""
    # Clear cache so tests always get a fresh build (important for isolation)
    EnhancedSandboxProvider._HELPERS = {}
    return EnhancedSandboxProvider._build_helpers()


# =============================================================================
# Datetime helpers
# =============================================================================


class TestDatetimeHelpers:
    def test_now_returns_string(self, h):
        result = h["now"]()
        assert isinstance(result, str)
        assert "2" in result  # year starts with 2

    def test_now_custom_tz(self, h):
        utc = h["now"](tz_offset=0)
        cst = h["now"](tz_offset=-6)
        assert utc != cst

    def test_today_format(self, h):
        result = h["today"]()
        assert len(result) == 10
        parts = result.split("-")
        assert len(parts) == 3
        assert len(parts[0]) == 4  # YYYY

    def test_days_ago_is_earlier(self, h):
        now_ts = h["timestamp"]()
        ago = h["days_ago"](1)
        # days_ago returns ISO string — just check it's non-empty and in the past
        assert isinstance(ago, str)
        assert "T" in ago

    def test_hours_ago_returns_iso(self, h):
        result = h["hours_ago"](2)
        assert isinstance(result, str)
        assert "T" in result

    def test_format_date(self, h):
        result = h["format_date"]("2025-06-15T10:30:00")
        assert result == "2025-06-15 10:30"

    def test_format_date_custom_fmt(self, h):
        result = h["format_date"]("2025-06-15T10:30:00", fmt="%d/%m/%Y")
        assert result == "15/06/2025"

    def test_format_date_empty(self, h):
        assert h["format_date"]("") == ""

    def test_parse_date_round_trips(self, h):
        iso = "2025-06-15T10:30:00"
        result = h["parse_date"](iso)
        assert "2025-06-15" in result

    def test_parse_date_empty(self, h):
        assert h["parse_date"]("") == ""

    def test_timestamp_is_int(self, h):
        result = h["timestamp"]()
        assert isinstance(result, int)
        assert result > 1_700_000_000  # sanity: after 2023


# =============================================================================
# JSON helpers
# =============================================================================


class TestJsonHelpers:
    def test_to_json_dict(self, h):
        result = h["to_json"]({"a": 1})
        assert result == '{"a": 1}'

    def test_to_json_indent(self, h):
        result = h["to_json"]({"a": 1}, indent=2)
        assert "\n" in result

    def test_to_json_non_serializable_uses_str(self, h):
        class Obj:
            def __str__(self):
                return "custom"

        result = h["to_json"]({"x": Obj()})
        assert '"custom"' in result

    def test_from_json_string(self, h):
        result = h["from_json"]('{"a": 1}')
        assert result == {"a": 1}

    def test_from_json_passthrough_dict(self, h):
        d = {"a": 1}
        assert h["from_json"](d) is d

    def test_from_json_passthrough_list(self, h):
        lst = [1, 2, 3]
        assert h["from_json"](lst) is lst


# =============================================================================
# URL helpers
# =============================================================================


class TestUrlHelpers:
    def test_url_encode_spaces(self, h):
        assert h["url_encode"]("hello world") == "hello%20world"

    def test_url_encode_special(self, h):
        assert h["url_encode"]("a&b=c") == "a%26b%3Dc"

    def test_url_decode_percent(self, h):
        assert h["url_decode"]("hello%20world") == "hello world"

    def test_url_decode_plus_is_literal(self, h):
        # unquote (not unquote_plus) — + is NOT decoded as space
        assert h["url_decode"]("hello+world") == "hello+world"

    def test_url_decode_symbols(self, h):
        assert h["url_decode"]("%21%40%23") == "!@#"

    def test_url_join_basic(self, h):
        result = h["url_join"]("https://example.com", "api", "v1")
        assert result == "https://example.com/api/v1"

    def test_url_join_strips_slashes(self, h):
        result = h["url_join"]("https://example.com/", "/api/", "/v1/")
        assert result == "https://example.com/api/v1"

    def test_query_string(self, h):
        result = h["query_string"]({"a": "1", "b": "hello world"})
        assert "a=1" in result
        assert "b=hello+world" in result or "b=hello%20world" in result


# =============================================================================
# Regex helpers
# =============================================================================


class TestRegexHelpers:
    def test_re_find(self, h):
        result = h["re_find"](r"\d+", "abc 123 def 456")
        assert result == ["123", "456"]

    def test_re_find_no_match(self, h):
        assert h["re_find"](r"\d+", "no digits") == []

    def test_re_match_true(self, h):
        assert h["re_match"](r"^\d+", "123abc") is True

    def test_re_match_false(self, h):
        assert h["re_match"](r"^\d+", "abc123") is False

    def test_re_sub(self, h):
        result = h["re_sub"](r"\d+", "NUM", "abc 123 def 456")
        assert result == "abc NUM def NUM"


# =============================================================================
# Text helpers
# =============================================================================


class TestTextHelpers:
    def test_truncate_over_limit(self, h):
        result = h["truncate"]("hello!", 5)
        assert result == "hello..."

    def test_truncate_exact_limit(self, h):
        # Exact length → no ellipsis (len(text) == n, not > n)
        result = h["truncate"]("hello", 5)
        assert result == "hello"

    def test_truncate_under_limit(self, h):
        assert h["truncate"]("hi", 10) == "hi"

    def test_truncate_default(self, h):
        long = "x" * 81
        result = h["truncate"](long)
        assert result.endswith("...")
        assert len(result) == 83  # 80 chars + "..."

    def test_join_default_sep(self, h):
        assert h["join"](["a", "b", "c"]) == "a, b, c"

    def test_join_custom_sep(self, h):
        assert h["join"]([1, 2, 3], " | ") == "1 | 2 | 3"

    def test_join_empty(self, h):
        assert h["join"]([]) == ""

    def test_html_escape(self, h):
        result = h["html_escape"]('<a href="x">&amp;</a>')
        assert result == "&lt;a href=&quot;x&quot;&gt;&amp;amp;&lt;/a&gt;"

    def test_dedent_removes_common_indent(self, h):
        indented = "    line one\n    line two\n    line three"
        result = h["dedent"](indented)
        assert result == "line one\nline two\nline three"

    def test_dedent_mixed_indent(self, h):
        # textwrap.dedent removes only the common prefix
        text = "    a\n      b\n    c"
        result = h["dedent"](text)
        assert result == "a\n  b\nc"

    def test_wrap_text_wraps_at_width(self, h):
        text = "The quick brown fox jumps over the lazy dog"
        result = h["wrap_text"](text, 20)
        lines = result.split("\n")
        assert all(len(line) <= 20 for line in lines)
        assert len(lines) > 1

    def test_wrap_text_default_width(self, h):
        # Default is 72 — short text should not wrap
        assert h["wrap_text"]("hello world") == "hello world"

    def test_pad_left_spaces(self, h):
        assert h["pad_left"]("42", 6) == "    42"

    def test_pad_left_zeros(self, h):
        assert h["pad_left"]("42", 6, "0") == "000042"

    def test_pad_left_no_truncate(self, h):
        assert h["pad_left"]("toolong", 4) == "toolong"

    def test_pad_right_spaces(self, h):
        assert h["pad_right"]("hi", 6) == "hi    "

    def test_pad_right_custom_char(self, h):
        assert h["pad_right"]("hi", 6, "-") == "hi----"

    def test_pad_right_numeric_input(self, h):
        assert h["pad_right"](7, 4, ".") == "7..."


# =============================================================================
# Math helpers
# =============================================================================


class TestMathHelpers:
    def test_sqrt(self, h):
        assert h["sqrt"](9) == 3.0

    def test_ceil(self, h):
        assert h["ceil"](1.2) == 2

    def test_floor(self, h):
        assert h["floor"](1.9) == 1

    def test_round_(self, h):
        assert h["round_"](3.14159) == 3.14

    def test_round_custom_digits(self, h):
        assert h["round_"](3.14159, 4) == 3.1416

    def test_abs_(self, h):
        assert h["abs_"](-5) == 5

    def test_min_(self, h):
        assert h["min_"]([3, 1, 2]) == 1

    def test_max_(self, h):
        assert h["max_"]([3, 1, 2]) == 3

    def test_sum_list(self, h):
        assert h["sum_"]([1, 2, 3]) == 6

    def test_sum_empty(self, h):
        assert h["sum_"]([]) == 0


# =============================================================================
# Collections helpers
# =============================================================================


class TestCollectionHelpers:
    def test_sorted_ascending(self, h):
        assert h["sorted_"]([3, 1, 2]) == [1, 2, 3]

    def test_sorted_descending(self, h):
        assert h["sorted_"]([3, 1, 2], reverse=True) == [3, 2, 1]

    def test_sorted_with_builtin_key(self, h):
        result = h["sorted_"](["bb", "a", "ccc"], key=len)
        assert result == ["a", "bb", "ccc"]

    def test_sorted_strings(self, h):
        assert h["sorted_"](["b", "a", "c"]) == ["a", "b", "c"]

    def test_unique_preserves_order(self, h):
        assert h["unique"]([1, 2, 1, 3, 2]) == [1, 2, 3]

    def test_unique_empty(self, h):
        assert h["unique"]([]) == []

    def test_flatten(self, h):
        assert h["flatten"]([[1, 2], [3, 4], [5]]) == [1, 2, 3, 4, 5]

    def test_flatten_empty_sublists(self, h):
        assert h["flatten"]([[], [1], []]) == [1]

    def test_counter_basic(self, h):
        result = h["counter"](["a", "b", "a", "c", "b", "a"])
        assert result == {"a": 3, "b": 2, "c": 1}

    def test_counter_empty(self, h):
        assert h["counter"]([]) == {}

    def test_chunk_basic(self, h):
        assert h["chunk"]([1, 2, 3, 4, 5], 2) == [[1, 2], [3, 4], [5]]

    def test_chunk_exact(self, h):
        assert h["chunk"]([1, 2, 3, 4], 2) == [[1, 2], [3, 4]]

    def test_chunk_empty(self, h):
        assert h["chunk"]([], 3) == []

    def test_zip_basic(self, h):
        result = h["zip_"]([1, 2, 3], ["a", "b", "c"])
        assert result == [[1, "a"], [2, "b"], [3, "c"]]

    def test_zip_truncates_to_shortest(self, h):
        result = h["zip_"]([1, 2, 3], ["a", "b"])
        assert result == [[1, "a"], [2, "b"]]

    def test_dict_get_nested(self, h):
        d = {"a": {"b": {"c": 42}}}
        assert h["dict_get"](d, "a.b.c") == 42

    def test_dict_get_missing_key(self, h):
        assert h["dict_get"]({"a": 1}, "a.b", "missing") == "missing"

    def test_dict_get_none_input(self, h):
        assert h["dict_get"](None, "a.b", "default") == "default"

    def test_dict_get_int_node(self, h):
        # Path traversal hits a non-dict leaf (int), should return default
        assert h["dict_get"]({"a": 42}, "a.b", "missing") == "missing"

    def test_dict_get_top_level(self, h):
        assert h["dict_get"]({"x": 99}, "x") == 99


# =============================================================================
# Hash helpers
# =============================================================================


class TestHashHelpers:
    def test_md5_known(self, h):
        assert h["md5"]("hello") == "5d41402abc4b2a76b9719d911017c592"

    def test_md5_empty(self, h):
        assert h["md5"]("") == "d41d8cd98f00b204e9800998ecf8427e"

    def test_sha256_known(self, h):
        result = h["sha256"]("hello")
        assert (
            result == "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
        )

    def test_md5_coerces_non_string(self, h):
        # Uses str(s) internally so numbers are fine
        result = h["md5"](42)
        assert isinstance(result, str)
        assert len(result) == 32


# =============================================================================
# Helpers completeness check
# =============================================================================


EXPECTED_HELPERS = {
    # datetime
    "now",
    "today",
    "days_ago",
    "hours_ago",
    "format_date",
    "parse_date",
    "timestamp",
    # json
    "to_json",
    "from_json",
    # url
    "url_encode",
    "url_decode",
    "url_join",
    "query_string",
    # regex
    "re_find",
    "re_match",
    "re_sub",
    # text
    "truncate",
    "dedent",
    "wrap_text",
    "join",
    "pad_left",
    "pad_right",
    "html_escape",
    # math
    "sqrt",
    "ceil",
    "floor",
    "round_",
    "abs_",
    "min_",
    "max_",
    "sum_",
    # collections
    "sorted_",
    "unique",
    "flatten",
    "counter",
    "chunk",
    "zip_",
    "dict_get",
    # hash
    "md5",
    "sha256",
    # async
    "sleep",
}


def test_all_expected_helpers_present(h):
    missing = EXPECTED_HELPERS - set(h.keys())
    assert not missing, f"Missing helpers: {missing}"


def test_execute_description_documents_all_text_helpers():
    from tools.code_mode import EXECUTE_DESCRIPTION

    for name in ("dedent", "wrap_text", "pad_left", "pad_right"):
        assert name in EXECUTE_DESCRIPTION, f"EXECUTE_DESCRIPTION missing: {name}"


def test_execute_description_documents_sandbox_restrictions():
    """LLMs must be warned about the restrictions that still exist.

    Starred expressions are supported since pydantic-monty 0.0.17, so the
    description must NOT warn about them anymore — stale restrictions make
    the model write worse code.
    """
    from tools.code_mode import EXECUTE_DESCRIPTION

    assert "lambda" in EXECUTE_DESCRIPTION, "Missing lambda key warning"
    assert "import" in EXECUTE_DESCRIPTION, "Missing import restriction note"
    assert "[*a, *b]" not in EXECUTE_DESCRIPTION, "Stale starred list warning"
    assert "{**" not in EXECUTE_DESCRIPTION, "Stale starred dict warning"


# =============================================================================
# sorted_() with lambda — catches a real production bug
# =============================================================================
# NOTE: The helpers work fine when called directly in Python.  The failure only
# happens when sorted_() receives a lambda that was constructed inside the Monty
# sandbox — Monty serialises callable objects differently, causing
# TypeError: 'str' object is not callable at runtime.
#
# These tests confirm the *helper* accepts lambdas (unit level), while the
# integration tests confirm the *sandbox* rejects them.


class TestSortedLambdaDirectly:
    """sorted_() accepts lambdas when called outside the sandbox."""

    def test_lambda_key_works_outside_monty(self, h):
        items = [{"n": "b"}, {"n": "a"}, {"n": "c"}]
        result = h["sorted_"](items, key=lambda x: x["n"])
        assert [i["n"] for i in result] == ["a", "b", "c"]

    def test_lambda_key_reverse(self, h):
        result = h["sorted_"]([3, 1, 2], key=lambda x: -x)
        assert result == [3, 2, 1]


# =============================================================================
# _format_sandbox_error — the error formatter
# =============================================================================


class TestFormatSandboxError:
    def test_starred_gets_hint(self):
        exc = NotImplementedError(
            "The monty syntax parser does not yet support starred expressions (*expr)"
        )
        msg = _format_sandbox_error(exc)
        assert msg.startswith("SandboxError:")
        assert "a + b" in msg  # shows the fix

    def test_lambda_str_callable_gets_hint(self):
        exc = TypeError("'str' object is not callable")
        msg = _format_sandbox_error(exc)
        assert "SandboxError:" in msg
        assert "lambda" in msg.lower()

    def test_generic_error_no_hint(self):
        exc = RuntimeError("something unexpected")
        msg = _format_sandbox_error(exc)
        assert msg.startswith("SandboxError:")
        assert "Hints:" not in msg

    def test_returns_string_not_raises(self):
        exc = Exception("any error")
        result = _format_sandbox_error(exc)
        assert isinstance(result, str)


# =============================================================================
# EnhancedSandboxProvider.run() — sandbox capability contract
# =============================================================================
# These require pydantic_monty (installed in .venv) and asyncio.
# pydantic-monty >= 0.0.17 parses starred expressions natively, so they
# evaluate normally; lambdas passed as function arguments still fail and
# must come back as a SandboxError string (never a raised exception).


@pytest.mark.asyncio
async def test_run_starred_list_is_supported():
    """[*a, *b] parses and evaluates on current pydantic-monty."""
    provider = EnhancedSandboxProvider()
    result = await provider.run("a = [1, 2]\nb = [3, 4]\nreturn [*a, *b]")
    assert result == [1, 2, 3, 4]


@pytest.mark.asyncio
async def test_run_starred_dict_is_supported():
    """{**d1, **d2} parses and evaluates on current pydantic-monty."""
    provider = EnhancedSandboxProvider()
    result = await provider.run("d1 = {'a': 1}\nd2 = {'b': 2}\nreturn {**d1, **d2}")
    assert result == {"a": 1, "b": 2}


@pytest.mark.asyncio
async def test_run_normal_code_unaffected():
    """Error handling must not swallow successful results."""
    provider = EnhancedSandboxProvider()
    result = await provider.run("return 42")
    assert result == 42


@pytest.mark.asyncio
async def test_run_lambda_key_returns_error_not_raises():
    """Lambdas as function arguments still fail — run() must return a
    SandboxError string with the workaround hint, never raise."""
    provider = EnhancedSandboxProvider()
    result = await provider.run(
        "items = [[2], [1, 1]]\nreturn sorted_(items, key=lambda x: x[0])"
    )
    assert isinstance(result, str), f"Expected str, got {type(result)}: {result!r}"
    assert "SandboxError" in result
    assert "lambda" in result.lower()


# =============================================================================
# gather_tools() — sequential multi-call helper
# =============================================================================


class TestGatherTools:
    """Test the gather_tools() helper injected by EnhancedSandboxProvider."""

    @pytest.mark.asyncio
    async def test_sequential_execution(self):
        call_log = []

        async def mock_call_tool(name, params):
            call_log.append(name)
            return f"result-{name}"

        provider = EnhancedSandboxProvider()
        result = await provider.run(
            'r = await gather_tools([["tool_a", {}], ["tool_b", {}]])\nreturn r',
            external_functions={"call_tool": mock_call_tool},
        )
        assert result == ["result-tool_a", "result-tool_b"]
        assert call_log == ["tool_a", "tool_b"]

    @pytest.mark.asyncio
    async def test_single_call(self):
        async def mock_call_tool(name, params):
            return 42

        provider = EnhancedSandboxProvider()
        result = await provider.run(
            'r = await gather_tools([["only", {}]])\nreturn r',
            external_functions={"call_tool": mock_call_tool},
        )
        assert result == [42]

    @pytest.mark.asyncio
    async def test_empty_list(self):
        async def mock_call_tool(name, params):
            return None

        provider = EnhancedSandboxProvider()
        result = await provider.run(
            "r = await gather_tools([])\nreturn r",
            external_functions={"call_tool": mock_call_tool},
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_error_propagates(self):
        async def mock_call_tool(name, params):
            raise RuntimeError("boom")

        provider = EnhancedSandboxProvider()
        result = await provider.run(
            'r = await gather_tools([["bad", {}]])\nreturn r',
            external_functions={"call_tool": mock_call_tool},
        )
        # Monty surfaces runtime errors as SandboxError strings
        assert isinstance(result, str)
        assert "boom" in result or "SandboxError" in result or "Error" in result


# =============================================================================
# setup_code_mode() — registration
# =============================================================================


class TestSetupCodeMode:
    def test_code_mode_uses_enhanced_sandbox(self):
        """setup_code_mode should use EnhancedSandboxProvider (with helpers), not base Monty."""
        from unittest.mock import MagicMock

        from tools.code_mode import EnhancedSandboxProvider, setup_code_mode

        mock_mcp = MagicMock()
        setup_code_mode(mock_mcp)
        code_mode = mock_mcp.add_transform.call_args[0][0]
        assert isinstance(code_mode.sandbox_provider, EnhancedSandboxProvider)

    def test_code_mode_has_execute_description_with_helpers(self):
        """Execute description must document helpers — LLMs won't use undocumented functions."""
        from unittest.mock import MagicMock

        from tools.code_mode import setup_code_mode

        mock_mcp = MagicMock()
        setup_code_mode(mock_mcp)
        code_mode = mock_mcp.add_transform.call_args[0][0]
        desc = code_mode.execute_description
        # Verify critical helpers are documented
        for helper in ["gather_tools", "now", "to_json", "from_json", "call_tool"]:
            assert helper in desc, (
                f"EXECUTE_DESCRIPTION missing '{helper}' — LLM won't know about it"
            )


# =============================================================================
# Edge cases
# =============================================================================


class TestEdgeCases:
    @pytest.mark.asyncio
    async def test_empty_code(self):
        provider = EnhancedSandboxProvider()
        result = await provider.run("")
        assert result is None or result == "" or isinstance(result, str)

    @pytest.mark.asyncio
    async def test_assignment_only_no_return(self):
        provider = EnhancedSandboxProvider()
        result = await provider.run("x = 42")
        assert result is None

    def test_sync_helpers_not_coroutines(self):
        EnhancedSandboxProvider._HELPERS = {}
        helpers = EnhancedSandboxProvider._build_helpers()
        result = helpers["now"]()
        assert isinstance(result, str)  # not a coroutine
        assert "20" in result  # year starts with 20xx

    def test_execute_description_documents_gather_tools(self):
        from tools.code_mode import EXECUTE_DESCRIPTION

        assert "gather_tools" in EXECUTE_DESCRIPTION


# =============================================================================
# Prefab view specs handed to clients that cannot draw them
# =============================================================================


class TestPrefabPlainText:
    """`execute` must not return layout JSON to a non-UI client.

    An MCP App entry tool (``preview_gmail_draft``) returns its serialized
    view as the tool result. When the UI gate says the client cannot draw a
    card, that JSON is pure cost — the model cannot act on it and nobody
    renders it — so it is flattened back to the text the card would show.
    """

    @staticmethod
    def _draft_card():
        """The Gmail draft text-only fallback, as `_text_only_app` emits it."""
        return {
            "$prefab": {"version": "0.2"},
            "view": {
                "cssClass": "pf-app-root",
                "type": "Div",
                "children": [
                    {
                        "type": "Card",
                        "children": [
                            {
                                "type": "CardHeader",
                                "children": [
                                    {"content": "Blue Crushers", "type": "H3"}
                                ],
                            },
                            {
                                "type": "CardContent",
                                "children": [
                                    {
                                        "cssClass": "gap-1",
                                        "type": "Column",
                                        "children": [
                                            {"content": "Draft r-764", "type": "Muted"},
                                            {
                                                "content": "To: julia@example.com",
                                                "type": "Muted",
                                            },
                                        ],
                                    }
                                ],
                            },
                        ],
                    }
                ],
            },
        }

    def test_view_spec_becomes_its_visible_text(self):
        from tools.code_mode import _prefab_plain_text

        assert _prefab_plain_text(self._draft_card()) == (
            "Blue Crushers\nDraft r-764\nTo: julia@example.com"
        )

    def test_ordinary_tool_results_pass_through_untouched(self):
        from tools.code_mode import _prefab_plain_text

        assert _prefab_plain_text({"messages": [{"id": "1"}]}) is None
        assert _prefab_plain_text("plain string") is None
        assert _prefab_plain_text(None) is None

    def test_dict_with_a_view_key_but_no_prefab_marker_is_not_a_card(self):
        """A tool returning its own `view` field must not be mangled."""
        from tools.code_mode import _prefab_plain_text

        assert _prefab_plain_text({"view": "grid", "content": "hi"}) is None

    def test_state_bindings_are_skipped(self):
        """A binding serializes as a dict; it has no text until resolved."""
        from tools.code_mode import _prefab_plain_text

        spec = {
            "$prefab": {"version": "0.2"},
            "view": {
                "type": "Div",
                "children": [
                    {"content": {"$state": "status"}, "type": "Text"},
                    {"content": "  Send  ", "type": "Button"},
                ],
            },
        }
        assert _prefab_plain_text(spec) == "Send"

    def test_a_card_with_no_text_falls_back_rather_than_erasing_the_result(self):
        from tools.code_mode import _prefab_plain_text

        spec = {"$prefab": {"version": "0.2"}, "view": {"type": "Div", "children": []}}
        assert _prefab_plain_text(spec) is None


class TestExecuteDoesNotReturnViewJSON:
    """End-to-end: the gate's downgrade path through the real `execute` tool.

    The unit tests above cover the flattening; this covers the wiring, which
    is where the bug actually lived — `execute` returned an app tool's view
    spec verbatim to a client that could not draw it.

    The in-memory client reports `clientInfo.name == "mcp"`, which is not on
    the `DRAFT_PREVIEW_UI_CLIENTS` allowlist and advertises no UI extension,
    so it exercises the downgrade without any monkeypatching.
    """

    CARD = {
        "$prefab": {"version": "0.2"},
        "view": {
            "type": "Div",
            "children": [
                {
                    "type": "CardHeader",
                    "children": [{"content": "Blue Crushers", "type": "H3"}],
                },
                {"content": "Draft r-764", "type": "Muted"},
            ],
        },
    }

    @pytest.mark.asyncio
    async def test_app_view_spec_is_flattened_for_a_non_ui_client(self, monkeypatch):
        from fastmcp import Client, FastMCP

        from config.settings import settings
        from tools.code_mode import setup_code_mode

        # Pin the gate on: a developer .env carrying
        # DRAFT_PREVIEW_UI_GATING=false otherwise switches off the very path
        # under test, and the failure reads as a regression in the flattening.
        monkeypatch.setattr(settings, "draft_preview_ui_gating", True)

        mcp = FastMCP("test-server")

        @mcp.tool
        def fake_card() -> dict:
            """An app entry tool: its return value IS the serialized view."""
            return TestExecuteDoesNotReturnViewJSON.CARD

        setup_code_mode(mcp)

        async with Client(mcp) as client:
            result = await client.call_tool(
                "execute", {"code": "r = await call_tool('fake_card', {})\nreturn r"}
            )

        text = result.content[0].text if result.content else ""
        assert text == "Blue Crushers\nDraft r-764"
        assert "$prefab" not in text
        assert result.structured_content is None


class TestTemplateEnvelope:
    """Discovery tools must see the payload, not the middleware's wrapper.

    The Jinja template middleware wraps every tool result as
    {"jinjaTemplateApplied": ..., "jinjaTemplateError": ..., "result": ...}.
    Reading fields off that envelope made `tool_activity` report 0 responses
    against a store holding 447, and would make `fetch` report "not found"
    for a document it actually returned.
    """

    def test_envelope_is_peeled(self):
        from tools.code_mode import _parse_unwrapped

        envelope = {
            "jinjaTemplateApplied": False,
            "jinjaTemplateError": None,
            "result": {"total_responses": 447, "collection_name": "mcp_tool_responses"},
        }
        assert _parse_unwrapped(envelope) == {
            "total_responses": 447,
            "collection_name": "mcp_tool_responses",
        }

    def test_envelope_with_json_string_payload_is_parsed(self):
        from tools.code_mode import _parse_unwrapped

        envelope = {"jinjaTemplateApplied": True, "result": '{"found": true}'}
        assert _parse_unwrapped(envelope) == {"found": True}

    def test_a_tools_own_result_key_is_left_alone(self):
        """No Jinja marker means this is the tool's own payload, not a wrapper."""
        from tools.code_mode import _parse_unwrapped

        payload = {"result": "ok", "count": 3}
        assert _parse_unwrapped(payload) == payload

    def test_json_string_input_still_parses(self):
        from tools.code_mode import _parse_unwrapped

        assert _parse_unwrapped('{"found": false}') == {"found": False}
        assert _parse_unwrapped("not json") == "not json"

    def test_unwrapped_payload_passes_through(self):
        from tools.code_mode import _parse_unwrapped

        assert _parse_unwrapped({"total_responses": 5}) == {"total_responses": 5}


class TestExecuteKeepsItsOwnResult:
    """A card rendered mid-chain must not swallow the block's return value.

    `execute` captures any Prefab app a called tool returns and puts it in
    structured_content. It used to *replace* the block's own output with a
    "Rendered the X app card" summary, so an orchestration that previewed a
    draft partway through silently lost its result — and its exceptions,
    which the sandbox surfaces as the block's value.
    """

    CARD = {
        "$prefab": {"version": "0.2"},
        "view": {"type": "Div", "children": [{"content": "Draft card", "type": "H3"}]},
    }

    @staticmethod
    def _server():
        from fastmcp import FastMCP

        from tools.code_mode import setup_code_mode

        mcp = FastMCP("test-server")

        @mcp.tool
        def fake_card() -> dict:
            """A prefab UI tool."""
            return TestExecuteKeepsItsOwnResult.CARD

        setup_code_mode(mcp)
        return mcp

    @pytest.fixture(autouse=True)
    def _ui_capable(self, monkeypatch):
        import tools.client_capabilities as cc

        monkeypatch.setattr(cc, "client_renders_ui", lambda: True)

    async def _run(self, code):
        from fastmcp import Client

        async with Client(self._server()) as client:
            result = await client.call_tool("execute", {"code": code})
        text = result.content[0].text if result.content else ""
        return text, result.structured_content

    @pytest.mark.asyncio
    async def test_block_result_survives_a_card_call(self):
        text, structured = await self._run(
            "r = await call_tool('fake_card', {})\nreturn {'my': 'value', 'n': 42}"
        )
        assert "value" in text and "42" in text
        assert structured and "view" in structured, "card still rendered for the user"

    @pytest.mark.asyncio
    async def test_returning_the_card_itself_is_still_summarized(self):
        """The view spec must not be echoed back as the block's output."""
        text, structured = await self._run(
            "r = await call_tool('fake_card', {})\nreturn r"
        )
        assert "$prefab" not in text
        assert "app card" in text
        assert structured and "view" in structured

    @pytest.mark.asyncio
    async def test_errors_are_not_swallowed_by_the_card(self):
        text, _ = await self._run(
            "r = await call_tool('fake_card', {})\nraise ValueError('boom')"
        )
        assert "boom" in text

    @pytest.mark.asyncio
    async def test_block_result_is_drawn_below_the_card(self):
        """A host that draws only the card must still show the block's output.

        Keeping the value in the result text is enough for the model and
        invisible to the user, so it has to reach the view as well.
        """
        _, structured = await self._run(
            "r = await call_tool('fake_card', {})\nreturn {'my': 'value', 'n': 42}"
        )
        children = structured["view"]["children"]
        assert len(children) == 2, "card's own children plus the block result"
        assert children[0] == self.CARD["view"]["children"][0], "card left intact"
        assert "42" in json.dumps(children[1])

    @pytest.mark.asyncio
    async def test_nothing_is_appended_when_the_block_returns_the_card(self):
        _, structured = await self._run(
            "r = await call_tool('fake_card', {})\nreturn r"
        )
        assert structured["view"]["children"] == self.CARD["view"]["children"]

    def test_folding_does_not_mutate_the_tools_own_spec(self):
        from tools.code_mode import _fold_block_output_into_card

        spec = copy.deepcopy(self.CARD)
        folded = _fold_block_output_into_card(spec, {"n": 1}, ["fake_card"])

        assert spec == self.CARD, "the called tool may cache and reuse this"
        assert len(folded["view"]["children"]) == 2

    def test_a_view_that_cannot_take_a_child_is_left_alone(self):
        from tools.code_mode import _fold_block_output_into_card

        spec = {"$prefab": {"version": "0.2"}, "view": {"type": "H3"}}
        assert _fold_block_output_into_card(spec, {"n": 1}) == spec


class TestSandboxUnwrapPrefersData:
    """A dashboard tool's data must survive the card the middleware injects.

    DashboardCacheMiddleware overwrites a watched tool's structured_content
    with a Prefab view and leaves the real payload in the text content. The
    default unwrap prefers structured_content, so code calling one of those 13
    tools read fields off a view spec and got None for every one — silently,
    which is how `manage_tools` appeared to report a null clientSupportsUI.
    """

    class _Text:
        def __init__(self, text):
            self.text = text

    class _Result:
        def __init__(self, structured_content, content):
            self.structured_content = structured_content
            self.content = content

    VIEW = {"$prefab": {"version": "0.3"}, "view": {"type": "Div", "children": []}}

    def _unwrap(self, result, tool_name="manage_tools"):
        from tools.code_mode import _unwrap_for_sandbox

        return _unwrap_for_sandbox(
            result,
            lambda r: r.structured_content or "fallback-not-used",
            tool_name,
        )

    @pytest.fixture(autouse=True)
    def _watched(self, monkeypatch):
        """manage_tools is only watched once the server has registered it."""
        from middleware import dashboard_cache_middleware as dc

        monkeypatch.setattr(dc, "_watched_tools", {"manage_tools"})

    def test_injected_view_falls_back_to_the_text_payload(self):
        result = self._Result(
            self.VIEW,
            [self._Text('{"totalTools": 100, "clientName": "claude-code"}')],
        )
        assert self._unwrap(result) == {"totalTools": 100, "clientName": "claude-code"}

    def test_template_envelope_is_peeled_off_the_fallback(self):
        result = self._Result(
            self.VIEW,
            [self._Text('{"jinjaTemplateApplied": false, "result": {"n": 3}}')],
        )
        assert self._unwrap(result) == {"n": 3}

    def test_non_json_text_is_not_mistaken_for_the_payload(self):
        """Text that isn't JSON isn't the payload the middleware displaced."""
        result = self._Result(self.VIEW, [self._Text("plain words")])
        assert self._unwrap(result) == self.VIEW

    def test_view_with_no_text_content_keeps_the_default_unwrap(self):
        result = self._Result(self.VIEW, [])
        assert self._unwrap(result) == self.VIEW

    def test_ordinary_structured_content_is_untouched(self):
        """Only a view spec triggers the fallback; real data passes straight."""
        payload = {"totalTools": 100}
        result = self._Result(payload, [self._Text('{"stale": true}')])
        assert self._unwrap(result) == payload

    def test_an_app_tools_own_view_is_not_traded_for_the_placeholder(self):
        """The regression: preview_gmail_draft rendered "[Rendered Prefab UI]".

        An MCP App entry tool returns its view legitimately, and FastMCP puts a
        placeholder in the text content rather than data. Falling back there
        hands the block the placeholder and loses the card.
        """
        result = self._Result(
            self.VIEW,
            [self._Text("[Rendered Prefab UI]")],
        )
        assert self._unwrap(result, tool_name="preview_gmail_draft") == self.VIEW

    def test_placeholder_text_is_ignored_even_for_a_watched_tool(self):
        """Second guard: only JSON is treated as a recoverable payload."""
        result = self._Result(self.VIEW, [self._Text("[Rendered Prefab UI]")])
        assert self._unwrap(result) == self.VIEW


class TestTextlessCardIsNotDumpedAsJSON:
    """A card with no literal text must not degrade to its own layout JSON.

    The draft preview is built from inputs, comboboxes and an iframe — every
    string is a label, placeholder or binding, so flattening it yields nothing.
    Both branches used "did it flatten to text?" as a proxy for "is this a
    view?", which is false for exactly this card: the block-output node under
    the rendered card filled with {"$prefab": ...}, and the downgrade path
    returned the same JSON it exists to suppress.
    """

    TEXTLESS = {
        "$prefab": {"version": "0.3"},
        "view": {
            "type": "Div",
            "children": [
                {"type": "Input", "placeholder": "Subject"},
                {"type": "Button", "label": "Send"},
            ],
        },
    }

    def test_flattening_a_textless_card_still_yields_nothing(self):
        from tools.code_mode import _prefab_plain_text

        assert _prefab_plain_text(self.TEXTLESS) is None

    def test_but_it_is_still_recognised_as_a_view(self):
        from tools.code_mode import _is_prefab_view

        assert _is_prefab_view(self.TEXTLESS) is True

    def test_ordinary_data_is_not_a_view(self):
        from tools.code_mode import _is_prefab_view

        assert _is_prefab_view({"totalTools": 100}) is False
        assert _is_prefab_view("some text") is False


class TestCardPathDoesNotFoldTheViewIntoItself:
    """The card path's counterpart to TestExecuteDoesNotReturnViewJSON.

    When the client CAN draw the card, execute sends the view as
    structured_content and the block's own output as the text. A single-call
    `return await call_tool(app_tool, ...)` has no output of its own — the view
    IS the return value — so the text must be the summary and the card must go
    out unmodified. Keying that decision off "did the view flatten to text?"
    broke for a card with no literal text: the layout JSON got pasted into a
    block-output node underneath the card.
    """

    TEXTLESS_CARD = {
        "$prefab": {"version": "0.3"},
        "view": {
            "type": "Div",
            "children": [
                {"type": "Input", "placeholder": "Subject"},
                {"type": "Button", "label": "Send"},
            ],
        },
    }

    @pytest.mark.asyncio
    async def test_textless_card_is_returned_whole_with_a_summary(self, monkeypatch):
        from fastmcp import Client, FastMCP

        from config.settings import settings
        from tools.code_mode import setup_code_mode

        # Gating off => client_renders_ui() is True => card path.
        monkeypatch.setattr(settings, "draft_preview_ui_gating", False)

        mcp = FastMCP("test-server")

        @mcp.tool
        def textless_card() -> dict:
            """An app entry tool whose card carries no literal text."""
            return TestCardPathDoesNotFoldTheViewIntoItself.TEXTLESS_CARD

        setup_code_mode(mcp)

        async with Client(mcp) as client:
            result = await client.call_tool(
                "execute",
                {"code": "r = await call_tool('textless_card', {})\nreturn r"},
            )

        text = result.content[0].text if result.content else ""
        assert text == "Rendered the textless_card app card for the user."
        assert "$prefab" not in text

        # The card goes out untouched — no block-output node appended.
        assert result.structured_content == self.TEXTLESS_CARD


class TestExecuteSuspendsForClientInput:
    """A nested tool's ask for client input becomes ``execute``'s own result.

    Under Code Mode the block is the only thing that crosses the wire. The OAuth
    prompt (``prompt_for_oauth``) suspends its tool with an ``InputRequiredResult``
    that carries no content, so before this ``execute`` suppressed it and the user
    got the clickable link instead. Now the ask is returned from ``execute``; the
    client answers and re-runs the block with ``inputResponses``, and the nested
    tool reads the answer off the same request context.

    The in-memory client negotiates 2026-07-28, so this is the same wire shape
    Claude Code sees. Claude Code negotiates no tasks, so the client's automatic
    tasks extension is switched off: with it on, ``execute`` runs in a
    background worker that has no session to elicit through.
    """

    @pytest.fixture(autouse=True)
    def _inline_execute(self, monkeypatch):
        from fastmcp import Client

        monkeypatch.setattr(Client, "_auto_internal_extensions", False)

    @staticmethod
    def _server(rounds: list):
        from typing import Any

        from fastmcp import FastMCP

        from tools import elicitation as oe
        from tools.code_mode import setup_code_mode

        mcp = FastMCP("test-server")

        @mcp.tool
        async def start_fake_auth() -> Any:
            """Stand-in for start_google_auth: prompt once, then report the answer."""
            rounds.append(1)
            answer = oe.answered_oauth_prompt()
            if answer is not None:
                return f"answered:{answer.action}"
            prompt = await oe.prompt_for_oauth(
                "Finish OAuth", "https://example.com/auth"
            )
            if prompt.outcome == "suspended":
                return prompt.suspend
            return f"fallback:{prompt.outcome}"

        setup_code_mode(mcp)
        return mcp

    @staticmethod
    def _handler(action: str, seen: list):
        from fastmcp.client.elicitation import ElicitResult

        async def handler(message, response_type, params, context):
            seen.append(params)
            return ElicitResult(action=action)

        return handler

    @pytest.mark.asyncio
    async def test_the_ask_round_trips_through_execute(self, monkeypatch):
        from fastmcp import Client

        from tools import elicitation as oe

        monkeypatch.setattr(oe, "url_elicitation_supported", lambda ctx=None: True)
        rounds: list = []
        seen: list = []
        mcp = self._server(rounds)

        async with Client(
            mcp, elicitation_handler=self._handler("accept", seen)
        ) as client:
            result = await client.call_tool(
                "execute", {"code": "return await call_tool('start_fake_auth', {})"}
            )

        assert result.content[0].text == "answered:accept"
        assert len(seen) == 1
        assert getattr(seen[0], "mode", None) == "url"
        assert str(getattr(seen[0], "url", "")) == "https://example.com/auth"
        assert len(rounds) == 2  # asked, then answered on the re-run

    @pytest.mark.asyncio
    async def test_a_refusal_reaches_the_tool(self, monkeypatch):
        from fastmcp import Client

        from tools import elicitation as oe

        monkeypatch.setattr(oe, "url_elicitation_supported", lambda ctx=None: True)
        mcp = self._server([])

        async with Client(
            mcp, elicitation_handler=self._handler("decline", [])
        ) as client:
            result = await client.call_tool(
                "execute", {"code": "return await call_tool('start_fake_auth', {})"}
            )

        assert result.content[0].text == "answered:decline"

    @pytest.mark.asyncio
    async def test_the_ask_wins_over_a_block_that_swallows_it(self, monkeypatch):
        """LLM code wraps calls in try/except; the abort must not be catchable
        into a half-result that skips the user."""
        from fastmcp import Client

        from tools import elicitation as oe

        monkeypatch.setattr(oe, "url_elicitation_supported", lambda ctx=None: True)
        seen: list = []
        mcp = self._server([])
        code = (
            "try:\n"
            "    r = await call_tool('start_fake_auth', {})\n"
            "except Exception:\n"
            "    r = 'swallowed'\n"
            "return r"
        )

        async with Client(
            mcp, elicitation_handler=self._handler("accept", seen)
        ) as client:
            result = await client.call_tool("execute", {"code": code})

        assert len(seen) == 1
        assert result.content[0].text == "answered:accept"

    @pytest.mark.asyncio
    async def test_a_form_only_client_gets_the_link_in_a_form(self, monkeypatch):
        """Claude Code's shape: bare ``elicitation: {}``, which its SDK reads as
        form-only. The test client declares both modes, so the url gate is
        pinned off; the form gate stays real, and the form's message carries
        the URL."""
        from fastmcp import Client
        from fastmcp.client.elicitation import ElicitResult

        from tools import elicitation as oe

        monkeypatch.setattr(oe, "url_elicitation_supported", lambda ctx=None: False)
        rounds: list = []
        seen: list = []
        mcp = self._server(rounds)

        async def handler(message, response_type, params, context):
            seen.append((message, params))
            return ElicitResult(action="accept", content={"authorized": True})

        async with Client(mcp, elicitation_handler=handler) as client:
            result = await client.call_tool(
                "execute", {"code": "return await call_tool('start_fake_auth', {})"}
            )

        assert result.content[0].text == "answered:accept"
        assert len(seen) == 1
        message, params = seen[0]
        assert getattr(params, "mode", None) == "form"
        assert "https://example.com/auth" in message
        assert len(rounds) == 2
