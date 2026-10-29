"""Bring-your-own-module tools: wrap an installed module, search it, build its objects.

An assistant names any installed Python package; the server wraps it (components,
symbols, Qdrant index with description vectors), searches it by need, and builds real
objects from symbol DSL — the same loop the card and email tools run on
``card_framework`` and the MJML blocks.

Off unless ``MODULE_TOOLS_ENABLED=true``. Standard-library modules are refused, and
``MODULE_TOOLS_ALLOWED`` (comma-separated package prefixes) narrows what can be
wrapped. Building is limited to data classes (pydantic models, dataclasses, enums):
constructing an arbitrary class can run arbitrary code.
"""

from __future__ import annotations

import asyncio
import dataclasses
import enum
import importlib
import os
import sys
from typing import Annotated, Any, Dict, List, Optional

from pydantic import Field

from config.enhanced_logging import setup_logger

logger = setup_logger()

_REGISTRY_PREFIX = "byo:"
# Bump when what gets indexed changes, so old collections are not reused.
_INDEX_VERSION = "v2"


def module_tools_enabled() -> bool:
    return os.getenv("MODULE_TOOLS_ENABLED", "false").lower() == "true"


def _allowed_prefixes() -> List[str]:
    raw = os.getenv("MODULE_TOOLS_ALLOWED", "")
    return [p.strip() for p in raw.split(",") if p.strip()]


def check_module_allowed(module_name: str) -> Optional[str]:
    """Return a refusal reason, or None when ``module_name`` may be wrapped."""
    top = module_name.split(".")[0]
    if not module_name.replace(".", "").replace("_", "").isalnum():
        return f"Not a module name: {module_name!r}"
    if top in sys.stdlib_module_names:
        return f"Standard-library modules can't be wrapped: {module_name}"
    allowed = _allowed_prefixes()
    if allowed and not any(
        module_name == p or module_name.startswith(p + ".") for p in allowed
    ):
        return f"{module_name} is not in MODULE_TOOLS_ALLOWED ({', '.join(allowed)})"
    return None


def collection_for(module_name: str) -> str:
    return f"mcp_module_{_INDEX_VERSION}_" + module_name.replace(".", "_")


def _create_wrapper(module_name: str):
    from adapters.module_wrapper import ModuleWrapper
    from config.settings import settings

    return ModuleWrapper(
        module_or_name=module_name,
        qdrant_url=settings.qdrant_url,
        qdrant_api_key=settings.qdrant_api_key,
        collection_name=collection_for(module_name),
        auto_initialize=True,
        index_nested=True,
        index_private=False,
        max_depth=2,
        skip_standard_library=True,
        include_modules=[module_name.split(".")[0]],
        own_members_only=True,
    )


def get_byo_wrapper(module_name: str):
    """Wrap ``module_name`` once per process (indexing continues in the background)."""
    from adapters.module_wrapper.wrapper_factory import WrapperRegistry

    key = _REGISTRY_PREFIX + module_name
    if not WrapperRegistry.is_registered(key):
        importlib.import_module(module_name)  # fail fast with ImportError
        WrapperRegistry.register(key, lambda: _create_wrapper(module_name))
    return WrapperRegistry.get(key)


def field_signature(obj: Any) -> Dict[str, str]:
    """Field name -> compact type, for pydantic models and dataclasses."""
    from adapters.module_wrapper.docstrings import _type_name

    fields = getattr(obj, "model_fields", None)
    if isinstance(fields, dict):
        return {
            n: _type_name(getattr(f, "annotation", None)) for n, f in fields.items()
        }
    if dataclasses.is_dataclass(obj):
        return {f.name: _type_name(f.type) for f in dataclasses.fields(obj)}
    return {}


def to_jsonable(obj: Any) -> Any:
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json", exclude_none=True)
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return dataclasses.asdict(obj)
    if isinstance(obj, enum.Enum):
        return obj.value
    if isinstance(obj, list):
        return [to_jsonable(o) for o in obj]
    if isinstance(obj, dict):
        return {k: to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    return repr(obj)


def _class_entry(wrapper, name: str, score: Optional[float] = None) -> Dict[str, Any]:
    from adapters.module_wrapper.docstrings import describe_component

    comp = next(
        (c for c in wrapper.components.values() if c.name == name and c.obj),
        None,
    )
    symbol = (wrapper.symbol_mapping or {}).get(name)
    fields = field_signature(comp.obj) if comp else {}
    entry: Dict[str, Any] = {
        "name": name,
        "symbol": symbol,
        "path": comp.full_path if comp else None,
        "description": describe_component(comp.obj)[:300] if comp else "",
        "fields": fields,
    }
    if score is not None:
        entry["score"] = round(float(score), 4)
    if symbol and fields:
        sample = ", ".join(f"{k}=…" for k in list(fields)[:3])
        entry["dsl"] = f"{symbol}{{{sample}}}"
    return entry


_RERANK_POOL = 25


def jev_rerank(query: str, entries: List[Dict[str, Any]]) -> Optional[List[float]]:
    """Probability per entry that it is what ``query`` asks for, from TypeSafe's Jev.

    One Choice question over the candidate pool, each option described by its class
    description. On the intent benchmark (unseen module, no training) this took
    top-1 from 16.7% (pool order) to 50.7%. Returns None when not configured or on
    any error, so callers keep pool order.
    """
    import httpx

    key = os.getenv("TYPESAFE_API_KEY")
    if not key or os.getenv("MODULE_TOOLS_RERANK", "jev").lower() != "jev":
        return None
    criteria = {e["name"]: (e.get("description") or e["name"])[:400] for e in entries}
    if len(criteria) < 2:
        return None
    body = {
        "model": os.getenv("TYPESAFE_MODEL", "jev-latest"),
        "state": {"request": query},
        "questions": {
            "component": {
                "type": "choice",
                "instructions": {
                    "question": "Which component best fulfils the developer's request?",
                    "inspect": "request",
                },
                "criteria": criteria,
            }
        },
    }
    try:
        r = httpx.post(
            os.getenv("TYPESAFE_BASE_URL", "https://api.typesafe.ai") + "/v1/systemone",
            json=body,
            headers={"Authorization": f"Bearer {key}"},
            timeout=10.0,
        )
        r.raise_for_status()
        probs = r.json()["answers"]["component"]["probabilities"]
        return [float(probs.get(e["name"], 0.0)) for e in entries]
    except Exception as e:
        logger.warning(f"Jev rerank failed, keeping pool order: {e}")
        return None


def setup_module_tools(mcp) -> None:
    if not module_tools_enabled():
        logger.info("⏭️ Module tools off (set MODULE_TOOLS_ENABLED=true to enable)")
        return

    @mcp.tool(
        name="wrap_module",
        description=(
            "Wrap an installed Python package for search and object building: "
            "indexes its classes (with description vectors) and assigns each a DSL "
            "symbol. Indexing continues in the background after this returns."
        ),
        tags={"module", "wrapper", "dsl", "index"},
        annotations={
            "title": "Wrap Module",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def wrap_module(
        module_name: Annotated[
            str, Field(description="Importable module, e.g. 'openai.types'")
        ],
    ) -> Dict[str, Any]:
        refusal = check_module_allowed(module_name)
        if refusal:
            return {"module": module_name, "error": refusal}
        try:
            wrapper = await asyncio.to_thread(get_byo_wrapper, module_name)
        except ImportError as e:
            return {"module": module_name, "error": f"Import failed: {e}"}
        classes = [
            c.name for c in wrapper.components.values() if c.component_type == "class"
        ]
        symbols = wrapper.symbol_mapping or {}
        return {
            "module": module_name,
            "collection": wrapper.collection_name,
            "components": len(wrapper.components),
            "classes": len(set(classes)),
            "symbols": len(symbols),
            "indexing": str(getattr(wrapper, "_pipeline_status", "unknown")),
            "symbol_sample": dict(list(symbols.items())[:20]),
            "next": "search_module to find classes by need; build_module_object "
            "with symbol DSL like  Sym{field=value, nested=Sym2{...}}",
        }

    @mcp.tool(
        name="search_module",
        description=(
            "Find classes in a wrapped module by describing what you need. Returns "
            "each class's DSL symbol, fields and a DSL starter. When TYPESAFE_API_KEY "
            "is set, the candidate pool is reranked by TypeSafe's Jev."
        ),
        tags={"module", "search", "dsl"},
        annotations={
            "title": "Search Module",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def search_module(
        module_name: Annotated[
            str, Field(description="A module passed to wrap_module")
        ],
        query: Annotated[
            str, Field(description="What you need, e.g. 'retry policy for HTTP calls'")
        ],
        limit: Annotated[int, Field(ge=1, le=25)] = 5,
    ) -> Dict[str, Any]:
        refusal = check_module_allowed(module_name)
        if refusal:
            return {"module": module_name, "error": refusal}
        try:
            wrapper = await asyncio.to_thread(get_byo_wrapper, module_name)
        except ImportError as e:
            return {"module": module_name, "error": f"Import failed: {e}"}
        classes, _patterns, _rels = await asyncio.to_thread(
            wrapper.search_hybrid, query, None, max(limit, _RERANK_POOL)
        )
        seen, pool = set(), []
        for hit in classes:
            name = hit.get("name")
            if name and name not in seen:
                seen.add(name)
                pool.append(_class_entry(wrapper, name, hit.get("score")))
        reranked_by = "pool"
        probs = await asyncio.to_thread(jev_rerank, query, pool)
        if probs is not None:
            for entry, p in zip(pool, probs):
                entry["probability"] = round(p, 4)
            pool.sort(key=lambda e: -e["probability"])
            reranked_by = "jev"
        return {
            "module": module_name,
            "query": query,
            "ranked_by": reranked_by,
            "results": pool[:limit],
        }

    @mcp.tool(
        name="build_module_object",
        description=(
            "Build a real object of a wrapped module from symbol DSL, e.g. "
            "'ƒ{must=[ʄ{key=\"x\", match=☆{value=1}}]}'. Class names work in place of "
            "symbols. Only data classes (pydantic models, dataclasses, enums) can be "
            "built. Returns the object as JSON, or the error with the class's fields."
        ),
        tags={"module", "dsl", "build"},
        annotations={
            "title": "Build Module Object",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def build_module_object(
        module_name: Annotated[
            str, Field(description="A module passed to wrap_module")
        ],
        dsl: Annotated[str, Field(description="Symbol DSL with {key=value} params")],
    ) -> Dict[str, Any]:
        from adapters.module_wrapper.dsl_builder import DSLObjectBuilder

        refusal = check_module_allowed(module_name)
        if refusal:
            return {"module": module_name, "error": refusal}
        try:
            wrapper = await asyncio.to_thread(get_byo_wrapper, module_name)
        except ImportError as e:
            return {"module": module_name, "error": f"Import failed: {e}"}
        builder = DSLObjectBuilder(wrapper, data_only=True)
        parsed = builder.parse_dsl(dsl)
        if not parsed.root_nodes:
            return {"module": module_name, "dsl": dsl, "error": parsed.issues}
        root = parsed.root_nodes[0]
        try:
            obj = builder.build(root)
        except ValueError as e:
            return {
                "module": module_name,
                "dsl": dsl,
                "error": str(e),
                "expected": _class_entry(wrapper, root.component_name),
            }
        return {
            "module": module_name,
            "dsl": dsl,
            "type": f"{type(obj).__module__}.{type(obj).__qualname__}",
            "object": to_jsonable(obj),
        }

    logger.info(
        "✅ Module tools registered: wrap_module, search_module, build_module_object"
    )
