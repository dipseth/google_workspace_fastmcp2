"""Integration tests for the code-mode `execute` tool.

Calls the live MCP server via StreamableHttp.  Server must be running.
These tests verify that the EnhancedSandboxProvider + pydantic-monty pipeline
produces correct output end-to-end — not just that the helpers exist.

## Critical sandbox failure modes (tested here, not in unit tests)

### Starred expressions — parse-time crash
`[*a, *b]` and `{**d1, **d2}` fail at PARSE TIME in pydantic_monty.Monty().
The ENTIRE code block is rejected before any line executes.  This means:
  - A `try/except` block wrapping `[*a, *b]` inside the code does NOT help —
    Monty never reaches the try/except because it can't parse the file.
  - BEFORE fix: `client.call_tool("execute", ...)` raised an MCP-level
    exception (MontyRuntimeError), crashing the entire tool call visibly to
    the user.
  - AFTER fix: run() catches the error and returns "SandboxError: ..." as
    text content — the tool call succeeds, the user sees a helpful message.

### Lambda keys in sorted_()
`sorted_(items, key=lambda x: x['k'])` causes TypeError at runtime because
Monty serialises the lambda to a string, and sorted() then tries to call a
string as the key function.  This is a Monty quirk, not a bug in sorted_().

### url_decode("+")
Uses urllib.parse.unquote (NOT unquote_plus), so "+" stays as "+" — it is NOT
decoded as a space the way HTML form data would be.

### truncate("hello", 5) — exact-length boundary
len(text) == n → no ellipsis.  len(text) > n → add "...".
"""

import json

import pytest
import pytest_asyncio

from .base_test_config import TEST_EMAIL, create_test_client
from .test_helpers import ensure_tools_enabled

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope="module")
async def exec_client():
    """Module-scoped client with execute tool enabled."""
    try:
        client = await create_test_client(TEST_EMAIL)
    except Exception as e:
        pytest.skip(f"MCP server not reachable: {e}")

    async with client:
        await ensure_tools_enabled(client, tool_names=["execute"])
        yield client


async def run(client, code: str):
    """Run a code snippet via the execute tool and return the text response."""
    result = await client.call_tool("execute", {"code": code})
    assert result.content, "execute returned empty content"
    text = result.content[0].text
    return text


async def run_json(client, code: str):
    """Run code that returns a JSON-serialisable value and parse the result."""
    text = await run(client, code)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


# ---------------------------------------------------------------------------
# Datetime helpers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestDatetimeIntegration:
    async def test_now(self, exec_client):
        out = await run(exec_client, "return now()")
        assert "202" in out  # sanity: year

    async def test_today_format(self, exec_client):
        out = await run(exec_client, "return today()")
        assert len(out.strip()) == 10
        assert out.count("-") == 2

    async def test_days_ago(self, exec_client):
        out = await run(exec_client, "return days_ago(7)")
        assert "T" in out

    async def test_timestamp_is_numeric(self, exec_client):
        out = await run(exec_client, "return str(timestamp())")
        assert out.strip().isdigit()

    async def test_format_date(self, exec_client):
        out = await run(exec_client, "return format_date('2025-06-15T10:30:00')")
        assert out.strip() == "2025-06-15 10:30"

    async def test_parse_date_empty(self, exec_client):
        out = await run(exec_client, "return parse_date('')")
        assert out.strip() == ""


# ---------------------------------------------------------------------------
# JSON helpers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestJsonIntegration:
    async def test_to_json_round_trip(self, exec_client):
        out = await run(
            exec_client,
            "d = {'a': 1, 'b': [1, 2, 3]}\nreturn from_json(to_json(d)) == d",
        )
        assert "True" in out

    async def test_from_json_passthrough(self, exec_client):
        out = await run(
            exec_client,
            "d = {'x': 42}\nreturn from_json(d)['x']",
        )
        assert "42" in out

    async def test_to_json_indent(self, exec_client):
        out = await run(exec_client, "return to_json({'a': 1}, indent=2)")
        assert "\n" in out


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestUrlIntegration:
    async def test_url_encode_decode_round_trip(self, exec_client):
        out = await run(
            exec_client,
            "s = 'hello world & foo=bar'\nreturn url_decode(url_encode(s))",
        )
        assert "hello world & foo=bar" in out

    async def test_url_decode_plus_literal(self, exec_client):
        # unquote does NOT decode + as space
        out = await run(exec_client, "return url_decode('hello+world')")
        assert out.strip() == "hello+world"

    async def test_url_join(self, exec_client):
        out = await run(
            exec_client,
            "return url_join('https://example.com/', '/api/', '/v1')",
        )
        assert out.strip() == "https://example.com/api/v1"

    async def test_query_string(self, exec_client):
        out = await run(exec_client, "return query_string({'a': '1', 'b': '2'})")
        assert "a=1" in out
        assert "b=2" in out


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestTextIntegration:
    async def test_truncate_over(self, exec_client):
        out = await run(exec_client, "return truncate('hello!', 5)")
        assert out.strip() == "hello..."

    async def test_truncate_exact_no_ellipsis(self, exec_client):
        out = await run(exec_client, "return truncate('hello', 5)")
        assert out.strip() == "hello"

    async def test_html_escape(self, exec_client):
        out = await run(exec_client, "return html_escape('<b>\"hi\"</b>')")
        assert "&lt;" in out
        assert "&gt;" in out
        assert "&quot;" in out

    async def test_pad_left_zeros(self, exec_client):
        out = await run(exec_client, "return pad_left('42', 6, '0')")
        assert out.strip() == "000042"

    async def test_pad_right(self, exec_client):
        out = await run(exec_client, "return pad_right('hi', 6, '-')")
        assert out.strip() == "hi----"

    async def test_dedent(self, exec_client):
        code = "text = '    a\\n    b\\n    c'\nreturn dedent(text)"
        out = await run(exec_client, code)
        assert "    " not in out  # leading spaces removed

    async def test_wrap_text(self, exec_client):
        code = (
            "long = 'The quick brown fox jumps over the lazy dog and then some more'\n"
            "return wrap_text(long, 20)"
        )
        out = await run(exec_client, code)
        lines = out.split("\n")
        assert len(lines) > 1


# ---------------------------------------------------------------------------
# Math helpers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestMathIntegration:
    async def test_sqrt(self, exec_client):
        out = await run(exec_client, "return sqrt(16)")
        assert "4.0" in out

    async def test_round_(self, exec_client):
        out = await run(exec_client, "return round_(3.14159, 2)")
        assert "3.14" in out

    async def test_sum_empty(self, exec_client):
        out = await run(exec_client, "return sum_([])")
        assert "0" in out

    async def test_min_max(self, exec_client):
        out = await run(
            exec_client, "return str(min_([3,1,2])) + ',' + str(max_([3,1,2]))"
        )
        assert "1" in out and "3" in out


# ---------------------------------------------------------------------------
# Collections helpers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestCollectionsIntegration:
    async def test_sorted_basic(self, exec_client):
        out = await run(exec_client, "return to_json(sorted_([3,1,2]))")
        assert json.loads(out) == [1, 2, 3]

    async def test_sorted_with_builtin_key(self, exec_client):
        out = await run(
            exec_client,
            "return to_json(sorted_(['bb', 'a', 'ccc'], key=len))",
        )
        assert json.loads(out) == ["a", "bb", "ccc"]

    async def test_unique(self, exec_client):
        out = await run(exec_client, "return to_json(unique([1,2,1,3,2]))")
        assert json.loads(out) == [1, 2, 3]

    async def test_flatten(self, exec_client):
        out = await run(exec_client, "return to_json(flatten([[1,2],[3],[4,5]]))")
        assert json.loads(out) == [1, 2, 3, 4, 5]

    async def test_counter_empty(self, exec_client):
        out = await run(exec_client, "return to_json(counter([]))")
        assert json.loads(out) == {}

    async def test_chunk(self, exec_client):
        out = await run(exec_client, "return to_json(chunk([1,2,3,4,5], 2))")
        assert json.loads(out) == [[1, 2], [3, 4], [5]]

    async def test_chunk_empty(self, exec_client):
        out = await run(exec_client, "return to_json(chunk([], 3))")
        assert json.loads(out) == []

    async def test_zip_truncates(self, exec_client):
        out = await run(exec_client, "return to_json(zip_([1,2,3], ['a','b']))")
        assert json.loads(out) == [[1, "a"], [2, "b"]]

    async def test_dict_get_nested(self, exec_client):
        out = await run(
            exec_client,
            "d = {'a': {'b': {'c': 99}}}\nreturn dict_get(d, 'a.b.c')",
        )
        assert "99" in out

    async def test_dict_get_none_input(self, exec_client):
        out = await run(exec_client, "return dict_get(None, 'a.b', 'default')")
        assert "default" in out

    async def test_dict_get_int_node(self, exec_client):
        out = await run(exec_client, "return dict_get({'a': 42}, 'a.b', 'miss')")
        assert "miss" in out


# ---------------------------------------------------------------------------
# Hash helpers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestHashIntegration:
    async def test_md5_known(self, exec_client):
        out = await run(exec_client, "return md5('hello')")
        assert out.strip() == "5d41402abc4b2a76b9719d911017c592"

    async def test_sha256_known(self, exec_client):
        out = await run(exec_client, "return sha256('hello')")
        expected = "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
        assert out.strip() == expected


# ---------------------------------------------------------------------------
# Sandbox quirks / restrictions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestSandboxBehaviours:
    async def test_starred_list_returns_sandbox_error(self, exec_client):
        """[*a, *b] fails at Monty PARSE TIME — not catchable inside the code.

        WRONG approach (what we originally tested):
            try:
                r = [*a, *b]       # ← inside the code passed to Monty
            except Exception as e:
                return str(e)      # ← this never runs; parser rejects the whole file

        CORRECT expectation after fix: execute returns "SandboxError: ..." as text,
        the tool call does NOT raise an MCP-level exception.
        """
        out = await run(exec_client, "a = [1, 2]\nb = [3, 4]\nreturn [*a, *b]")
        assert "SandboxError" in out, (
            f"Expected SandboxError in output, got: {out!r}\n"
            "If this test raises instead of returning, run() is not catching parse errors."
        )
        assert "starred" in out.lower() or "a + b" in out

    async def test_starred_dict_returns_sandbox_error(self, exec_client):
        """{**d1, **d2} also fails at parse time."""
        out = await run(
            exec_client, "d1 = {'a': 1}\nd2 = {'b': 2}\nreturn {**d1, **d2}"
        )
        assert "SandboxError" in out

    async def test_starred_in_try_except_is_still_parse_error(self, exec_client):
        """Wrapping [*a, *b] in try/except inside the code does NOT help.

        The parser sees [*a, *b] and rejects the whole file before any
        try/except can execute.  After the fix, run() catches it externally
        and the output is SandboxError — NOT 'caught: ...'.
        """
        code = (
            "a = [1]\nb = [2]\n"
            "try:\n"
            "  r = [*a, *b]\n"
            "except Exception as e:\n"
            "  return 'caught: ' + str(e)"
        )
        out = await run(exec_client, code)
        assert "caught:" not in out, (
            "try/except inside Monty code cannot catch parse-time failures"
        )
        assert "SandboxError" in out

    async def test_sorted_lambda_key_returns_error(self, exec_client):
        """sorted_(items, key=lambda x: x['n']) causes TypeError at runtime.

        Monty serialises the lambda to a string, so sorted() receives a string
        as the key function and raises TypeError: 'str' object is not callable.
        The fix makes run() catch this and return SandboxError.

        Workaround: extract keys manually, sort by position.
        """
        code = (
            "items = [{'n': 'b'}, {'n': 'a'}]\n"
            "return to_json(sorted_(items, key=lambda x: x['n']))"
        )
        out = await run(exec_client, code)
        assert "SandboxError" in out or "'str' object is not callable" in out, (
            f"Expected an error for lambda key, got: {out!r}"
        )

    async def test_sorted_builtin_key_works(self, exec_client):
        """Builtin keys like key=len work fine in Monty — they're real callables."""
        out = await run(
            exec_client, "return to_json(sorted_(['bb', 'a', 'ccc'], key=len))"
        )
        assert json.loads(out) == ["a", "bb", "ccc"]

    async def test_list_concat_workaround_for_starred(self, exec_client):
        """a + b works where [*a, *b] doesn't."""
        out = await run(exec_client, "a = [1, 2]\nb = [3, 4]\nreturn to_json(a + b)")
        assert json.loads(out) == [1, 2, 3, 4]

    async def test_dict_update_workaround_for_starred(self, exec_client):
        """d.copy(); d.update(d2) works where {**d1, **d2} doesn't."""
        code = "d1 = {'a': 1}\nd2 = {'b': 2}\nd = d1.copy()\nd.update(d2)\nreturn to_json(d)"
        out = await run(exec_client, code)
        assert json.loads(out) == {"a": 1, "b": 2}

    async def test_unpacking_assignment_works(self, exec_client):
        """a, *rest = x (assignment unpacking) IS supported."""
        out = await run(
            exec_client,
            "items = [1, 2, 3, 4]\nfirst, *rest = items\nreturn str(first) + ',' + str(rest)",
        )
        assert "1" in out
        assert "2" in out

    async def test_import_subprocess_raises(self, exec_client):
        out = await run(
            exec_client,
            "try:\n  import subprocess\nexcept Exception as e:\n  return str(e)",
        )
        assert "subprocess" in out.lower() or "module" in out.lower()

    async def test_return_required_for_output(self, exec_client):
        """Without return, execute produces no meaningful output."""
        out = await run(exec_client, "x = 42")
        assert out.strip() in ("", "None", "null")

    async def test_multiline_computation(self, exec_client):
        """Complex multi-step logic works end-to-end."""
        code = (
            "items = ['banana', 'apple', 'cherry', 'apple', 'banana', 'banana']\n"
            "counts = counter(items)\n"
            "return to_json(counts)"
        )
        out = await run(exec_client, code)
        data = json.loads(out)
        assert data["banana"] == 3
        assert data["apple"] == 2
        assert data["cherry"] == 1
