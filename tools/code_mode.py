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
            "gather": lambda *coros: asyncio.gather(*coros),
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
        merged = {**self._build_helpers(), **(external_functions or {})}
        return await super().run(code, inputs=inputs, external_functions=merged)


# Description shown to LLMs for the execute tool — documents every available helper.
EXECUTE_DESCRIPTION = (
    "Chain `await call_tool(...)` calls in one Python block; prefer returning the final answer from a single block.\n"
    "Use `return` to produce output.\n"
    "Only `call_tool(tool_name: str, params: dict) -> Any` is available in scope.\n"
    "\n"
    "**IMPORTANT: `import` is not available.** Use these built-in helpers instead:\n"
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
    "- `gather(*coros)` \u2192 run multiple awaits concurrently\n"
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
