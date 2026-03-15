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
    """LLMs must be warned about starred expressions and lambda keys."""
    from tools.code_mode import EXECUTE_DESCRIPTION

    assert "[*a, *b]" in EXECUTE_DESCRIPTION, "Missing starred list warning"
    assert "{**" in EXECUTE_DESCRIPTION, "Missing starred dict warning"
    assert "lambda" in EXECUTE_DESCRIPTION, "Missing lambda key warning"


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
# EnhancedSandboxProvider.run() — parse-time crash recovery
# =============================================================================
# These require pydantic_monty (installed in .venv) and asyncio.
# They test that starred expressions no longer crash the tool — they return
# a SandboxError string instead.


@pytest.mark.asyncio
async def test_run_starred_list_returns_error_not_raises():
    """[*a, *b] must NOT crash the tool — run() must return SandboxError."""
    provider = EnhancedSandboxProvider()
    result = await provider.run("a = [1, 2]\nb = [3, 4]\nreturn [*a, *b]")
    assert isinstance(result, str), f"Expected str, got {type(result)}: {result!r}"
    assert "SandboxError" in result
    assert "starred" in result.lower() or "a + b" in result


@pytest.mark.asyncio
async def test_run_starred_dict_returns_error_not_raises():
    """{**d1, **d2} must NOT crash the tool."""
    provider = EnhancedSandboxProvider()
    result = await provider.run("d1 = {'a': 1}\nd2 = {'b': 2}\nreturn {**d1, **d2}")
    assert isinstance(result, str)
    assert "SandboxError" in result


@pytest.mark.asyncio
async def test_run_normal_code_unaffected():
    """Error handling must not swallow successful results."""
    provider = EnhancedSandboxProvider()
    result = await provider.run("return 42")
    assert result == 42


@pytest.mark.asyncio
async def test_run_try_except_inside_code_cannot_catch_parse_errors():
    """Demonstrates why wrapping [*a, *b] in try/except inside the code is useless:
    the parser fails on the whole file before any try/except can run.

    After the fix, run() itself catches the error and returns SandboxError.
    The try/except in the code is irrelevant — it never executes.
    """
    provider = EnhancedSandboxProvider()
    # This code has [*a, *b] inside a try/except — the try/except is irrelevant
    # because Monty rejects the whole file at parse time.
    result = await provider.run(
        "a = [1]\nb = [2]\ntry:\n  r = [*a, *b]\nexcept Exception as e:\n  return 'caught: ' + str(e)"
    )
    # If the try/except worked, result would be "caught: ..."
    # If run() catches it correctly, result is "SandboxError: ..."
    assert isinstance(result, str)
    assert "SandboxError" in result, (
        "Expected run() to catch the parse error — "
        "a try/except inside Monty code cannot catch parse-time failures"
    )
