"""Code Mode setup for FastMCP — BM25 discovery + sandboxed execution with stdlib helpers.

Extracts the EnhancedSandboxProvider and CodeMode configuration from server.py
so that server.py stays focused on wiring, not implementation details.
"""

from __future__ import annotations

import json
from typing import Annotated, Any

from fastmcp import FastMCP
from fastmcp.experimental.transforms.code_mode import (
    CodeMode,
    GetSchemas,
    GetTags,
    GetToolCatalog,
    MontySandboxProvider,
    Search,
)
from fastmcp.server.context import Context
from fastmcp.tools import Tool, ToolResult
from mcp.types import TextContent
from pydantic import Field

from config.enhanced_logging import setup_logger

logger = setup_logger()

# Type alias — middleware auto-injects this; discovery tools accept and forward it.
UserGoogleEmail = Annotated[
    str | None, "User's Google email (auto-injected by middleware)"
]


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

        def _tz(offset=0):
            return datetime.timezone(datetime.timedelta(hours=offset))

        helpers = {
            # --- datetime ---
            "now": lambda tz_offset=0: str(datetime.datetime.now(_tz(tz_offset))),
            "today": lambda tz_offset=0: datetime.datetime.now(_tz(tz_offset)).strftime(
                "%Y-%m-%d"
            ),
            "days_ago": lambda n, tz_offset=0: (
                datetime.datetime.now(_tz(tz_offset)) - datetime.timedelta(days=n)
            ).isoformat(),
            "hours_ago": lambda n, tz_offset=0: (
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
            # pydantic-monty >=0.0.8 removed external_functions from Monty()
            # constructor; external_functions are now only passed to run_monty_async.
            monty = pydantic_monty.Monty(
                code,
                inputs=list((inputs or {}).keys()),
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
    "- `now(tz_offset=0)` \u2192 current datetime string (UTC by default)\n"
    "- `today(tz_offset=0)` \u2192 current date 'YYYY-MM-DD' (UTC by default)\n"
    "- `days_ago(n, tz_offset=0)` \u2192 ISO datetime string N days ago\n"
    "- `hours_ago(n, tz_offset=0)` \u2192 ISO datetime string N hours ago\n"
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


# ---------------------------------------------------------------------------
# Helpers for discovery tools
# ---------------------------------------------------------------------------


def _unwrap_result(result: ToolResult) -> dict[str, Any] | str:
    """Extract usable data from a ToolResult.

    Mirrors ``_unwrap_tool_result`` from fastmcp code_mode but is local so
    discovery tools can call it without importing a private helper.
    """
    if result.structured_content is not None:
        return result.structured_content

    parts: list[str] = []
    for content in result.content:
        if isinstance(content, TextContent):
            parts.append(content.text)
        else:
            parts.append(str(content))
    return "\n".join(parts)


def _parse_unwrapped(raw: dict[str, Any] | str) -> dict[str, Any] | str:
    """If *raw* is a JSON string, parse it; otherwise return as-is."""
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return raw
    return raw


# ---------------------------------------------------------------------------
# Discovery tool: SemanticSearch
# ---------------------------------------------------------------------------


def _get_qdrant_dsl_reference() -> str:
    """Build a compact DSL symbol reference from the qdrant models wrapper.

    Returns a multi-line string suitable for tool docstrings. Symbols are
    loaded dynamically — never hardcoded.
    """
    try:
        from middleware.qdrant_core.qdrant_models_wrapper import (
            get_qdrant_models_wrapper,
        )

        wrapper = get_qdrant_models_wrapper()
        symbols = dict(wrapper.symbol_mapping) if wrapper.symbol_mapping else {}
        if not symbols:
            return ""

        # Separate filter vs query symbols (same logic as _build_grammar_description)
        filter_syms: list[str] = []
        query_syms: list[str] = []
        for name, sym in sorted(symbols.items()):
            lower = name.lower()
            if any(
                k in lower
                for k in (
                    "filter",
                    "fieldcondition",
                    "matchvalue",
                    "matchtext",
                    "range",
                    "matchany",
                    "hasidcondition",
                    "isnullcondition",
                    "isemptycondition",
                    "datetimerange",
                )
            ):
                filter_syms.append(f"{sym}={name}")
            elif any(
                k in lower
                for k in (
                    "recommend",
                    "discover",
                    "fusion",
                    "prefetch",
                    "orderby",
                    "context",
                    "searchparams",
                )
            ):
                query_syms.append(f"{sym}={name}")

        lines = ["DSL filter symbols: " + ", ".join(filter_syms)]
        if query_syms:
            lines.append("Advanced query symbols: " + ", ".join(query_syms))

        # Build dynamic examples from actual symbols
        f_sym = symbols.get("Filter", "")
        fc_sym = symbols.get("FieldCondition", "")
        mv_sym = symbols.get("MatchValue", "")
        ma_sym = symbols.get("MatchAny", "")
        if f_sym and fc_sym and mv_sym:
            lines.append(
                f'Example: {f_sym}{{must=[{fc_sym}{{key="tool_name", '
                f'match={mv_sym}{{value="send_dynamic_card"}}}}]}}'
            )
        if f_sym and fc_sym and ma_sym:
            lines.append(
                f'MatchAny: {f_sym}{{must=[{fc_sym}{{key="tool_name", '
                f'match={ma_sym}{{any=["tool_a", "tool_b"]}}}}]}}'
            )

        return "\n".join(lines)
    except Exception:
        return ""


class SemanticSearch:
    """Full-featured Qdrant vector search exposed as a discovery tool.

    Wraps ``qdrant_search`` with all its capabilities — semantic search,
    DSL filters, recommendation, prefetch, and dry-run — so the LLM can
    search stored responses without writing an execute block.
    """

    def __init__(
        self, *, name: str = "semantic_search", default_limit: int = 5
    ) -> None:
        self._name = name
        self._default_limit = default_limit

    def __call__(self, get_catalog: GetToolCatalog) -> Tool:
        default_limit = self._default_limit

        async def semantic_search(
            query: Annotated[
                str,
                "Search query — natural language, 'service:gmail recent', "
                "'overview', 'id:<point_id>', or semantic text when filter_dsl is set",
            ],
            filter_dsl: Annotated[
                str | None,
                "Qdrant DSL filter notation for precise filtering (see docstring for symbols)",
            ] = None,
            query_dsl: Annotated[
                str | None,
                "Advanced query DSL for recommend, discover, fusion, or order-by queries",
            ] = None,
            prefetch_dsl: Annotated[
                str | None,
                "Multi-stage prefetch DSL for hierarchical search strategies",
            ] = None,
            positive_point_ids: Annotated[
                list[str] | None,
                "Point IDs to use as positive examples for recommendation search",
            ] = None,
            negative_point_ids: Annotated[
                list[str] | None,
                "Point IDs to use as negative examples for recommendation search",
            ] = None,
            limit: Annotated[int, "Maximum results to return"] = default_limit,
            score_threshold: Annotated[
                float, "Minimum similarity score (0.0-1.0)"
            ] = 0.3,
            collection: Annotated[
                str | None,
                "Qdrant collection to search. Default: mcp_tool_responses",
            ] = None,
            dry_run: Annotated[
                bool,
                "If true with filter_dsl, parse and validate DSL without executing the query",
            ] = False,
            user_google_email: UserGoogleEmail = None,
            ctx: Context = None,  # type: ignore[assignment]
        ) -> str:
            """Search the Qdrant vector database."""
            params: dict[str, Any] = {
                "query": query,
                "limit": limit,
                "score_threshold": score_threshold,
            }
            if filter_dsl:
                params["filter_dsl"] = filter_dsl
            if query_dsl:
                params["query_dsl"] = query_dsl
            if prefetch_dsl:
                params["prefetch_dsl"] = prefetch_dsl
            if positive_point_ids:
                params["positive_point_ids"] = positive_point_ids
            if negative_point_ids:
                params["negative_point_ids"] = negative_point_ids
            if collection:
                params["collection"] = collection
            if dry_run:
                params["dry_run"] = dry_run
            if user_google_email:
                params["user_google_email"] = user_google_email

            try:
                result = await ctx.fastmcp.call_tool("qdrant_search", params)
                raw = _parse_unwrapped(_unwrap_result(result))
            except Exception as exc:
                return f"Search failed: {exc}"

            if isinstance(raw, str):
                return raw

            # Dry-run returns filter repr instead of results
            if dry_run:
                return (
                    f"DSL dry-run:\n"
                    f"  filter_dsl: {raw.get('dsl_input', filter_dsl)}\n"
                    f"  built_filter: {raw.get('built_filter_repr', '?')}\n"
                    f"  error: {raw.get('error', 'none')}"
                )

            # Format compact results table
            results = raw.get("results", [])
            error = raw.get("error")
            if error:
                return f"Search error: {error}"
            if not results:
                return f"No results for: {query}"

            query_type = raw.get("query_type", "semantic")
            total = raw.get("total_results", len(results))
            header = f"Found {total} results for: {query}"
            if query_type not in ("semantic", "general_search"):
                header += f"  (type: {query_type})"
            lines = [header + "\n"]
            for item in results:
                score = item.get("score", 0)
                svc = item.get("service", "?")
                tool = item.get("tool_name", "?")
                ts = item.get("timestamp", "?")
                pid = item.get("id", "?")
                lines.append(f"  {score:.3f}  {svc}/{tool}  {ts}  id:{pid}")

            return "\n".join(lines)

        # Dynamic docstring — symbols generated from wrapper, never hardcoded
        dsl_ref = _get_qdrant_dsl_reference()
        semantic_search.__doc__ = (
            "Search the Qdrant vector database.\n\n"
            "Supports multiple search modes:\n"
            "- Semantic: natural language query matched by embedding similarity\n"
            "- Service history: 'service:gmail last week', 'tool:search recent'\n"
            "- Analytics: 'overview', 'dashboard', 'usage stats'\n"
            "- DSL filter: filter_dsl for precise structured filtering\n"
            "- Recommendation: find similar via positive/negative point IDs\n"
            "- Advanced: query_dsl for fusion, discover, order-by queries\n"
            "- Multi-stage: prefetch_dsl for hierarchical retrieval\n\n"
            "Returns point IDs usable with fetch_document for content preview.\n"
            + (f"\n{dsl_ref}" if dsl_ref else "")
        )

        return Tool.from_function(fn=semantic_search, name=self._name)


# ---------------------------------------------------------------------------
# Discovery tool: FetchDocument
# ---------------------------------------------------------------------------


class FetchDocument:
    """Discovery tool that peeks at a stored Qdrant document.

    Wraps the ``fetch`` tool and returns a truncated preview so the LLM
    can inspect content without writing an execute block.
    """

    PREVIEW_CHARS = 500

    def __init__(
        self, *, name: str = "fetch_document", preview_chars: int = 500
    ) -> None:
        self._name = name
        self.PREVIEW_CHARS = preview_chars

    def __call__(self, get_catalog: GetToolCatalog) -> Tool:
        preview_chars = self.PREVIEW_CHARS

        async def fetch_document(
            point_id: Annotated[str, "Qdrant point ID (UUID) from a search result"],
            user_google_email: UserGoogleEmail = None,
            ctx: Context = None,  # type: ignore[assignment]
        ) -> str:
            """Peek at a stored response by point ID.

            Returns tool name, service, timestamp, arguments, and a
            truncated content preview. For full content, use fetch in
            an execute block.
            """
            params: dict[str, Any] = {"point_id": point_id}
            if user_google_email:
                params["user_google_email"] = user_google_email

            try:
                result = await ctx.fastmcp.call_tool("fetch", params)
                raw = _parse_unwrapped(_unwrap_result(result))
            except Exception as exc:
                return f"Fetch failed: {exc}"

            if isinstance(raw, str):
                return raw

            if not raw.get("found", False):
                return f"Document not found: {point_id}"

            meta = raw.get("metadata", {})
            text = raw.get("text", "")
            preview = text[:preview_chars] + (
                "..." if len(text) > preview_chars else ""
            )

            lines = [
                f"Document: {point_id}",
                f"  Tool:      {meta.get('tool_name', '?')}",
                f"  Service:   {meta.get('service', '?')} ({meta.get('service_display_name', '')})",
                f"  Timestamp: {meta.get('timestamp', '?')}",
                f"  User:      {meta.get('user_email', '?')}",
                f"  Args:      {meta.get('arguments_count', 0)} params",
                f"\nPreview ({len(text)} chars total):",
                preview,
            ]
            return "\n".join(lines)

        return Tool.from_function(fn=fetch_document, name=self._name)


# ---------------------------------------------------------------------------
# Discovery tool: ToolActivity
# ---------------------------------------------------------------------------


class ToolActivity:
    """Discovery tool that shows a dashboard of recent tool usage.

    Wraps ``get_tool_analytics`` with ``summary_only=True`` so the LLM
    can understand activity patterns without writing an execute block.
    """

    def __init__(self, *, name: str = "tool_activity", default_limit: int = 10) -> None:
        self._name = name
        self._default_limit = default_limit

    def __call__(self, get_catalog: GetToolCatalog) -> Tool:
        default_limit = self._default_limit

        async def tool_activity(
            group_by: Annotated[
                str,
                "Group results by 'tool_name' or 'user_email'",
            ] = "tool_name",
            limit: Annotated[int, "Maximum groups to show"] = default_limit,
            user_google_email: UserGoogleEmail = None,
            ctx: Context = None,  # type: ignore[assignment]
        ) -> str:
            """Show a dashboard of tool usage activity.

            Returns which tools have been called, how often, error rates,
            and sample point IDs for deeper inspection via fetch_document.
            """
            params: dict[str, Any] = {"summary_only": True, "group_by": group_by}
            if user_google_email:
                params["user_google_email"] = user_google_email

            try:
                result = await ctx.fastmcp.call_tool(
                    "get_tool_analytics",
                    params,
                )
                raw = _parse_unwrapped(_unwrap_result(result))
            except Exception as exc:
                return f"Analytics failed: {exc}"

            if isinstance(raw, str):
                return raw

            total = raw.get("total_responses", 0)
            collection = raw.get("collection_name", "?")
            date_range = raw.get("date_range", {})
            summary = raw.get("summary", {})
            groups = raw.get("groups_summary", raw.get("groups", {}))

            lines = [
                f"Tool Activity Dashboard  (collection: {collection})",
                f"  Total responses: {total}",
            ]
            if date_range:
                lines.append(
                    f"  Date range: {date_range.get('earliest', '?')} → {date_range.get('latest', '?')}"
                )
            if summary:
                lines.append(f"  Unique tools: {summary.get('unique_tools', '?')}")
                lines.append(f"  Unique users: {summary.get('unique_users', '?')}")

            lines.append(f"\nTop {limit} by {group_by}:")
            lines.append(
                f"  {'Group':<35} {'Count':>6}  {'Errors':>6}  {'Last Used':<20}  Sample IDs"
            )
            lines.append("  " + "-" * 100)

            count = 0
            for name, data in groups.items():
                if count >= limit:
                    break
                count += 1
                cnt = data.get("count", data.get("total", 0))
                errors = data.get("error_count", data.get("errors", 0))
                last = data.get("last_used", data.get("latest_timestamp", "?"))
                # Truncate last-used to date+time
                if isinstance(last, str) and len(last) > 19:
                    last = last[:19]
                sample_ids = data.get("sample_point_ids", data.get("point_ids", []))
                ids_str = ", ".join(str(s) for s in sample_ids[:3])
                lines.append(
                    f"  {name:<35} {cnt:>6}  {errors:>6}  {last:<20}  {ids_str}"
                )

            return "\n".join(lines)

        return Tool.from_function(fn=tool_activity, name=self._name)


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------


def setup_code_mode(mcp: FastMCP) -> None:
    """Register the CodeMode transform on *mcp*.

    IMPORTANT: We monkey-patch ``get_tool_catalog`` on the CodeMode instance
    because the default implementation's ContextVar-based bypass does not
    reliably propagate through FastMCP's nested ``list_tools`` calls
    (new Context objects + middleware re-entry).  The patched version reads
    tools directly from the local provider, which is both simpler and
    correct — discovery tools (``search``, ``tags``) should see the full
    catalog regardless of session-level filtering.
    """
    code_mode = CodeMode(
        sandbox_provider=EnhancedSandboxProvider(),
        discovery_tools=[
            GetTags(),
            Search(default_limit=10),
            GetSchemas(),
            SemanticSearch(),
            FetchDocument(),
            ToolActivity(),
        ],
        execute_description=EXECUTE_DESCRIPTION,
    )

    # ------------------------------------------------------------------
    # Patch: fetch the real tool catalog directly from the provider
    # ------------------------------------------------------------------
    # The upstream CatalogTransform.get_tool_catalog() sets a _bypass
    # ContextVar then re-enters list_tools(run_middleware=True).  In this
    # server the session-filtering middleware + nested Context creation
    # causes the bypass flag to be invisible by the time transforms run,
    # so the catalog returns the 7 discovery tools instead of 72+ real
    # tools.  Fix: read from the provider (pre-transform) directly.
    async def _patched_get_tool_catalog(
        ctx: Context = None, *, run_middleware: bool = True
    ):
        """Return the real registered tools, bypassing transforms."""
        try:
            components = mcp.local_provider._components
            return [v for v in components.values() if isinstance(v, Tool)]
        except Exception:
            logger.warning(
                "code_mode: patched get_tool_catalog failed, falling back to upstream"
            )
            # Fall back to the original (may still be broken, but is safe)
            return await code_mode.__class__.get_tool_catalog(
                code_mode, ctx, run_middleware=run_middleware
            )

    code_mode.get_tool_catalog = _patched_get_tool_catalog

    # ------------------------------------------------------------------
    # Patch: wrap the execute tool's inner call_tool with argument
    # recovery so that ValidationErrors inside the sandbox get a chance
    # to be fixed by an LLM before surfacing as SandboxError.
    # ------------------------------------------------------------------
    _original_make_execute = code_mode._make_execute_tool

    def _patched_make_execute() -> Tool:
        from collections.abc import Sequence as _Seq

        from fastmcp.experimental.transforms.code_mode import (
            NotFoundError,
            _unwrap_tool_result,
        )
        from fastmcp.tools import ToolResult as _ToolResult
        from pydantic import ValidationError as _VE

        transform = code_mode

        async def execute(
            code: Annotated[
                str,
                Field(
                    description=(
                        "Python async code to execute tool calls"
                        " via call_tool(name, arguments)"
                    )
                ),
            ],
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Any:
            """Execute tool calls using Python code."""
            cached_tools: _Seq[Tool] | None = None

            async def _get_cached_tools() -> _Seq[Tool]:
                nonlocal cached_tools
                if cached_tools is None:
                    cached_tools = await transform.get_tool_catalog(ctx)
                return cached_tools

            async def call_tool(tool_name: str, params: dict[str, Any]) -> Any:
                backend_tools = await _get_cached_tools()
                tool = transform._find_tool(tool_name, backend_tools)
                if tool is None:
                    raise NotFoundError(f"Unknown tool: {tool_name}")

                try:
                    result = await ctx.fastmcp.call_tool(tool.name, params)
                    return _unwrap_tool_result(result)
                except _VE as ve:
                    # Attempt argument recovery via LLM
                    corrected = await _recover_args(ctx, tool, tool_name, params, ve)
                    if corrected is not None:
                        result = await ctx.fastmcp.call_tool(tool.name, corrected)
                        return _unwrap_tool_result(result)
                    raise  # re-raise if recovery failed

            # Clear stale dashboard-tool tracker so a *previous*
            # execute's cached tool doesn't bleed into this one.
            try:
                from middleware.dashboard_cache_middleware import (
                    clear_last_dashboard_tool,
                )

                clear_last_dashboard_tool()
            except Exception:
                pass

            raw = await transform.sandbox_provider.run(
                code,
                external_functions={"call_tool": call_tool},
            )

            # If a dashboard-enabled tool was called during THIS execute,
            # embed a Prefab dashboard directly in the ToolResult so
            # VS Code renders it inline (no resource-fetch race).
            try:
                from middleware.dashboard_cache_middleware import (
                    get_cached_result,
                    get_last_dashboard_tool,
                )

                last_tool = get_last_dashboard_tool()
                if last_tool is not None:
                    cached = get_cached_result(last_tool)
                    if cached:
                        from tools.ui_apps import (
                            _build_prefab_data_dashboard,
                            get_data_dashboard_config,
                        )

                        config = get_data_dashboard_config(last_tool)
                        prefab = _build_prefab_data_dashboard(
                            last_tool, cached, config
                        )
                        if prefab is not None:
                            return _ToolResult(
                                content=raw,
                                structured_content=prefab.to_json(),
                            )
            except Exception:
                pass
            return raw

        tool = Tool.from_function(
            fn=execute,
            name=transform.execute_tool_name,
            description=transform._build_execute_description(),
        )

        # Dashboard rendering is now handled inline via Prefab
        # structured_content in the ToolResult (see execute body above),
        # so no resourceUri is needed on the tool definition.

        return tool

    async def _recover_args(
        ctx: Context,
        tool: Tool,
        tool_name: str,
        original_params: dict,
        error: Exception,
    ) -> dict | None:
        """Use LLM sampling to fix tool arguments on ValidationError."""
        try:
            from config.settings import settings as _s

            if not getattr(_s, "sampling_argument_recovery_enabled", True):
                return None
        except Exception:
            pass

        try:
            schema = tool.parameters
            error_details = str(error)

            # Use the shared keepalive system prompt so the Anthropic
            # prompt cache prefix matches the keepalive engine's calls.
            try:
                from middleware.cache_keepalive import _build_execute_system_prompt

                system_prompt = _build_execute_system_prompt()
            except Exception:
                system_prompt = (
                    "You are a tool argument correction agent. A tool call "
                    "failed because the arguments did not match the expected "
                    "schema. Fix the arguments by mapping incorrect parameter "
                    "names to the correct ones, adding missing required "
                    "parameters with sensible defaults, and removing unknown "
                    "parameters.\n\n"
                    "IMPORTANT: Return ONLY a valid JSON object with the "
                    "corrected arguments. No explanation, no markdown, "
                    "no code fences — just the JSON object."
                )

            user_message = (
                f"Tool: {tool_name}\n"
                f"Description: {tool.description or 'N/A'}\n\n"
                f"Expected parameter schema:\n"
                f"{json.dumps(schema, indent=2)}\n\n"
                f"Original arguments provided:\n"
                f"{json.dumps(original_params, indent=2, default=str)}\n\n"
                f"Validation error:\n{error_details}\n\n"
                "Return the corrected arguments as a JSON object."
            )

            # Use LiteLLM directly (same as keepalive engine) since we
            # don't have a SamplingContext inside the sandbox.
            import litellm

            from config.settings import settings as _settings

            model = _settings.litellm_model
            kwargs: dict[str, Any] = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                "max_tokens": 300,
                "temperature": 0.0,
            }
            api_key = getattr(_settings, "litellm_api_key", None)
            api_base = getattr(_settings, "litellm_api_base", None)
            if api_key:
                kwargs["api_key"] = api_key
            if api_base:
                kwargs["api_base"] = api_base

            response = await litellm.acompletion(**kwargs)

            text = ""
            choices = getattr(response, "choices", [])
            if choices:
                msg = getattr(choices[0], "message", None)
                if msg:
                    text = (getattr(msg, "content", "") or "").strip()

            # Strip markdown fences
            if text.startswith("```"):
                lines = text.split("\n")
                text = "\n".join(ln for ln in lines if not ln.strip().startswith("```"))

            corrected = json.loads(text)
            if not isinstance(corrected, dict):
                return None

            logger.info(
                "Argument recovery (execute) for %s: "
                "original_keys=%s corrected_keys=%s",
                tool_name,
                list(original_params.keys()),
                list(corrected.keys()),
            )
            return corrected

        except Exception as exc:
            logger.warning(
                "Argument recovery (execute) failed for %s: %s",
                tool_name,
                exc,
            )
            return None

    # Replace the cached execute tool with our patched version
    code_mode._make_execute_tool = _patched_make_execute
    code_mode._cached_execute_tool = None  # force re-creation

    mcp.add_transform(code_mode)
    logger.info(
        "Code Mode enabled — LLMs will use BM25 search + sandboxed execution + stdlib helpers"
    )
