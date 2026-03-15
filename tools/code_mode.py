"""Code Mode setup for FastMCP — BM25 discovery + sandboxed execution with stdlib helpers.

Extracts the EnhancedSandboxProvider and CodeMode configuration from server.py
so that server.py stays focused on wiring, not implementation details.
"""

from __future__ import annotations

from fastmcp import FastMCP
from fastmcp.experimental.transforms.code_mode import (
    CodeMode,
    GetSchemas,
    GetTags,
    MontySandboxProvider,
    Search,
)

from config.enhanced_logging import setup_logger

logger = setup_logger()


def _format_sandbox_error(exc: Exception) -> str:
    """Convert a Monty parse/runtime error to a human-readable string.

    Returns a string so that ``execute`` produces text content instead of
    crashing the entire tool call with an MCP-level error.
    """
    msg = str(exc)
    hints: list[str] = []

    if "starred" in msg.lower():
        hints.append(
            "Starred expressions are not supported by the sandbox parser.\n"
            "  Replace [*a, *b]   →  a + b\n"
            "  Replace {**d1, **d2}  →  d = d1.copy(); d.update(d2)"
        )
    if "'str' object is not callable" in msg:
        hints.append(
            "Lambda expressions cannot be passed as function arguments (e.g., key=lambda).\n"
            "  Use a builtin key like key=len, or sort by index: sorted_(items, key=lambda x: x[0]) won't work.\n"
            "  Workaround: extract the key into a list, zip, sort, unzip."
        )
    if any(
        kw in msg.lower()
        for kw in [
            "unknown symbol",
            "cannot be direct child",
            "dsl",
            "card_description",
        ]
    ):
        hints.append(
            "DSL structure error detected. Use get_schema('send_dynamic_card') "
            "to see valid DSL syntax, or validate with parse_dsl() before calling."
        )

    hint_block = ("\n\nHints:\n" + "\n".join(hints)) if hints else ""
    return f"SandboxError: {msg}{hint_block}"


class EnhancedSandboxProvider(MontySandboxProvider):
    """Sandbox that injects common stdlib helpers alongside call_tool.

    The Monty sandbox blocks all imports.  This provider adds utility
    functions so LLM-generated code can do things like get the current
    time, format dates, parse JSON, and build URLs without importing
    any modules.
    """

    _HELPERS: dict = {}

    @staticmethod
    def _build_helpers() -> dict:
        """Build stdlib helper functions once (lazy, cached)."""
        if EnhancedSandboxProvider._HELPERS:
            return EnhancedSandboxProvider._HELPERS

        import asyncio
        import datetime
        import hashlib
        import json
        import math
        import re
        import textwrap
        import urllib.parse
        from collections import Counter

        def _tz(offset=-6):
            return datetime.timezone(datetime.timedelta(hours=offset))

        helpers = {
            # --- datetime ---
            "now": lambda tz_offset=-6: str(datetime.datetime.now(_tz(tz_offset))),
            "today": lambda tz_offset=-6: datetime.datetime.now(
                _tz(tz_offset)
            ).strftime("%Y-%m-%d"),
            "days_ago": lambda n, tz_offset=-6: (
                datetime.datetime.now(_tz(tz_offset)) - datetime.timedelta(days=n)
            ).isoformat(),
            "hours_ago": lambda n, tz_offset=-6: (
                datetime.datetime.now(_tz(tz_offset)) - datetime.timedelta(hours=n)
            ).isoformat(),
            "format_date": lambda iso_str, fmt="%Y-%m-%d %H:%M": (
                datetime.datetime.fromisoformat(iso_str).strftime(fmt)
                if iso_str
                else ""
            ),
            "parse_date": lambda iso_str: datetime.datetime.fromisoformat(
                iso_str
            ).isoformat()
            if iso_str
            else "",
            "timestamp": lambda: int(datetime.datetime.now(_tz()).timestamp()),
            # --- json ---
            "to_json": lambda obj, indent=None: json.dumps(
                obj, indent=indent, default=str, ensure_ascii=False
            ),
            "from_json": lambda s: json.loads(s) if isinstance(s, str) else s,
            # --- url ---
            "url_encode": lambda s: urllib.parse.quote(str(s), safe=""),
            "url_decode": lambda s: urllib.parse.unquote(str(s)),
            "url_join": lambda base, *parts: "/".join(
                [base.rstrip("/")] + [str(p).strip("/") for p in parts]
            ),
            "query_string": lambda params: urllib.parse.urlencode(params),
            # --- text / regex ---
            "re_find": lambda pattern, text: re.findall(pattern, text),
            "re_match": lambda pattern, text: bool(re.match(pattern, text)),
            "re_sub": lambda pattern, repl, text: re.sub(pattern, repl, text),
            "truncate": lambda text, n=80: (text[:n] + "...")
            if len(text) > n
            else text,
            "dedent": textwrap.dedent,
            "wrap_text": lambda text, width=72: textwrap.fill(text, width=width),
            # --- math ---
            "sqrt": math.sqrt,
            "ceil": math.ceil,
            "floor": math.floor,
            "round_": lambda n, digits=2: round(n, digits),
            "abs_": abs,
            "min_": min,
            "max_": max,
            "sum_": sum,
            # --- collections / data ---
            "sorted_": lambda items, key=None, reverse=False: sorted(
                items, key=key, reverse=reverse
            ),
            "unique": lambda items: list(dict.fromkeys(items)),
            "flatten": lambda lists: [item for sublist in lists for item in sublist],
            "counter": lambda items: dict(Counter(items)),
            "chunk": lambda items, size: [
                items[i : i + size] for i in range(0, len(items), size)
            ],
            "zip_": lambda *iterables: [list(t) for t in zip(*iterables)],
            "dict_get": lambda d, path, default=None: (
                # nested dict access: dict_get(d, "a.b.c") → d["a"]["b"]["c"]
                (
                    lambda parts: (lambda f: f(f, d, parts))(
                        lambda fn, obj, keys: obj
                        if not keys
                        else fn(fn, obj[keys[0]], keys[1:])
                        if isinstance(obj, dict) and keys[0] in obj
                        else default
                    )
                )(path.split("."))
            ),
            # --- hashing ---
            "md5": lambda s: hashlib.md5(str(s).encode()).hexdigest(),
            "sha256": lambda s: hashlib.sha256(str(s).encode()).hexdigest(),
            # --- async ---
            "sleep": lambda seconds: asyncio.sleep(seconds),
            # --- string formatting ---
            "join": lambda items, sep=", ": sep.join(str(i) for i in items),
            "pad_left": lambda s, width, char=" ": str(s).rjust(width, char),
            "pad_right": lambda s, width, char=" ": str(s).ljust(width, char),
            "html_escape": lambda s: (
                str(s)
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;")
            ),
        }
        EnhancedSandboxProvider._HELPERS = helpers
        return helpers

    async def run(self, code, *, inputs=None, external_functions=None):
        ef = external_functions or {}
        extra: dict = {}

        # Provide gather_tools(*calls) where each call is (tool_name, params).
        # This creates real asyncio coroutines outside the Monty sandbox so that
        # asyncio.gather can await them — direct `gather(call_tool(...), ...)` fails
        # because Monty-awaitable objects are not standard asyncio coroutines.
        if "call_tool" in ef:
            _call_tool = ef["call_tool"]

            async def gather_tools(calls: list) -> list:
                """Run multiple tool calls and return their results as a list.

                ``calls`` is a list of ``[tool_name, params]`` pairs.
                Returns a list of results in the same order.

                Example::

                    results = await gather_tools([
                        ["health_check", {"user_google_email": "..."}],
                        ["list_events", {"user_google_email": "...", "calendar_id": "primary"}],
                    ])
                    health = results[0]
                    events = results[1]
                """
                results = []
                for call in calls:
                    name, params = call[0], call[1]
                    results.append(await _call_tool(name, params))
                return results

            extra["gather_tools"] = gather_tools

        # Key insight from pydantic-monty's run_monty_async:
        #   - If ext_function(...) returns a coroutine → async future path (needs `await`)
        #   - If ext_function(...) returns a plain value → direct return_value path (no await needed)
        #
        # _ensure_async wraps sync lambdas in `async def wrapper`, making them return
        # coroutines even when called without `await`, which causes helpers to show as
        # `<coroutine external_future(N)>` in output instead of their actual values.
        #
        # Fix: bypass super().run() and call pydantic_monty directly.
        # Sync helpers are registered as-is (return plain values → direct path).
        # Only truly async functions (call_tool, gather_tools) get _ensure_async.
        import importlib

        from fastmcp.experimental.transforms.code_mode import _ensure_async

        pydantic_monty = importlib.import_module("pydantic_monty")

        helpers = self._build_helpers()
        async_ef = {**ef, **extra}  # call_tool + gather_tools (truly async)

        # Build final external_functions dict: sync helpers as-is, async ones wrapped.
        all_external = {
            **helpers,  # sync lambdas — return plain values, use direct path
            **{
                k: _ensure_async(v) for k, v in async_ef.items()
            },  # async — use future path
        }

        try:
            monty = pydantic_monty.Monty(
                code,
                inputs=list((inputs or {}).keys()),
                external_functions=list(all_external.keys()),
            )
        except Exception as exc:
            return _format_sandbox_error(exc)

        run_kwargs: dict = {"external_functions": all_external}
        if inputs:
            run_kwargs["inputs"] = inputs
        if self.limits is not None:
            run_kwargs["limits"] = self.limits
        try:
            return await pydantic_monty.run_monty_async(monty, **run_kwargs)
        except Exception as exc:
            return _format_sandbox_error(exc)


# Description shown to LLMs for the execute tool — documents every available helper.
EXECUTE_DESCRIPTION = (
    "Chain `await call_tool(...)` calls in one Python block; prefer returning the final answer from a single block.\n"
    "Use `return` to produce output.\n"
    "Only `call_tool(tool_name: str, params: dict) -> Any` is available in scope.\n"
    "\n"
    "**SANDBOX RESTRICTIONS — these produce SandboxError, avoid them:**\n"
    "- `[*a, *b]` → use `a + b` instead\n"
    "- `{**d1, **d2}` → use `d = d1.copy(); d.update(d2)` instead\n"
    "- `sorted_(items, key=lambda x: x['k'])` → lambda args fail; use builtins like `key=len` or sort manually\n"
    "- `import` is sandboxed — use only the built-in helpers listed below\n"
    "\n"
    "**Built-in helpers (`import` is not available — use these instead):**\n"
    "- `now(tz_offset=-6)` \u2192 current datetime string\n"
    "- `today(tz_offset=-6)` \u2192 current date 'YYYY-MM-DD'\n"
    "- `days_ago(n, tz_offset=-6)` \u2192 ISO datetime string N days ago\n"
    "- `hours_ago(n, tz_offset=-6)` \u2192 ISO datetime string N hours ago\n"
    "- `format_date(iso_str, fmt='%Y-%m-%d %H:%M')` \u2192 formatted date\n"
    "- `parse_date(iso_str)` \u2192 normalized ISO datetime\n"
    "- `timestamp()` \u2192 current unix timestamp (int)\n"
    "- `to_json(obj, indent=None)` \u2192 JSON string\n"
    "- `from_json(s)` \u2192 parsed object\n"
    "- `url_encode(s)` \u2192 URL-encoded string\n"
    "- `url_decode(s)` \u2192 URL-decoded string\n"
    "- `url_join(base, *parts)` \u2192 joined URL path\n"
    "- `query_string(params)` \u2192 URL query string from dict\n"
    "- `re_find(pattern, text)` \u2192 list of matches\n"
    "- `re_match(pattern, text)` \u2192 bool\n"
    "- `re_sub(pattern, repl, text)` \u2192 substituted string\n"
    "- `truncate(text, n=80)` \u2192 truncated with '...'\n"
    "- `dedent(text)` \u2192 remove common leading whitespace\n"
    "- `wrap_text(text, width=72)` \u2192 word-wrap to width\n"
    "- `pad_left(s, width, char=' ')` \u2192 right-justify / zero-pad\n"
    "- `pad_right(s, width, char=' ')` \u2192 left-justify\n"
    "- `join(items, sep=', ')` \u2192 joined string\n"
    "- `html_escape(s)` \u2192 HTML-safe string\n"
    "- `sqrt(n)`, `ceil(n)`, `floor(n)` \u2192 math\n"
    "- `round_(n, digits=2)`, `abs_()`, `min_()`, `max_()`, `sum_()` \u2192 math\n"
    "- `sorted_(items, key=None, reverse=False)` \u2192 sorted list\n"
    "- `unique(items)` \u2192 deduplicated list (preserves order)\n"
    "- `flatten(lists)` \u2192 flat list from nested lists\n"
    "- `counter(items)` \u2192 dict of {item: count}\n"
    "- `chunk(items, size)` \u2192 list of chunks\n"
    "- `zip_(*iterables)` \u2192 zipped as list of lists\n"
    "- `dict_get(d, 'a.b.c', default=None)` \u2192 nested dict access\n"
    "- `md5(s)`, `sha256(s)` \u2192 hash hex digests\n"
    "- `gather_tools(calls)` → run multiple tool calls sequentially; `calls` is a list of `[tool_name, params]` pairs, returns list of results (assign to variable, then index: `r = await gather_tools([...]); a, b = r[0], r[1]`)\n"
    "- `sleep(seconds)` \u2192 async sleep\n"
)


def setup_code_mode(mcp: FastMCP) -> None:
    """Register the CodeMode transform on *mcp*."""
    code_mode = CodeMode(
        sandbox_provider=EnhancedSandboxProvider(),
        discovery_tools=[
            GetTags(),
            Search(default_limit=10),
            GetSchemas(),
        ],
        execute_description=EXECUTE_DESCRIPTION,
    )
    mcp.add_transform(code_mode)
    logger.info(
        "Code Mode enabled \u2014 LLMs will use BM25 search + sandboxed execution + stdlib helpers"
    )
