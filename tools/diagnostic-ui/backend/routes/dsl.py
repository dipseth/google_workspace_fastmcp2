"""DSL parsing, validation, suggestion, and containment rule endpoints."""

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(tags=["dsl"])


class ParseDslRequest(BaseModel):
    dsl: str


class SuggestDslRequest(BaseModel):
    text: str


class SearchRequest(BaseModel):
    description: str
    limit: int = 10
    include_classes: bool = True


@router.post("/parse-dsl")
async def parse_dsl_endpoint(req: ParseDslRequest):
    """Parse and validate a DSL string, returning AST, expanded notation, and issues."""
    try:
        from gchat.wrapper_api import expand_dsl, parse_dsl, validate_dsl

        result = parse_dsl(req.dsl)

        # Get expanded notation
        expanded = ""
        try:
            expanded = expand_dsl(req.dsl)
        except Exception:
            pass

        # Build serializable AST
        def node_to_dict(node):
            d = {
                "name": getattr(node, "component_name", None)
                or getattr(node, "name", str(node)),
                "symbol": getattr(node, "symbol", ""),
                "multiplier": getattr(node, "multiplier", 1),
            }
            children = getattr(node, "children", [])
            if children:
                d["children"] = [node_to_dict(c) for c in children]
            else:
                d["children"] = []
            return d

        root_nodes = []
        if hasattr(result, "root_nodes") and result.root_nodes:
            root_nodes = [node_to_dict(n) for n in result.root_nodes]
        elif hasattr(result, "tree") and result.tree:
            root_nodes = [
                node_to_dict(n)
                for n in (
                    result.tree if isinstance(result.tree, list) else [result.tree]
                )
            ]

        return {
            "is_valid": result.is_valid,
            "expanded": expanded,
            "component_counts": getattr(result, "component_counts", {}),
            "component_paths": getattr(result, "component_paths", []),
            "root_nodes": root_nodes,
            "issues": getattr(result, "issues", []),
            "suggestions": getattr(result, "suggestions", []),
        }
    except Exception as e:
        return {
            "is_valid": False,
            "expanded": "",
            "component_counts": {},
            "component_paths": [],
            "root_nodes": [],
            "issues": [str(e)],
            "suggestions": [],
        }


@router.post("/suggest-dsl")
async def suggest_dsl_endpoint(req: SuggestDslRequest):
    """Generate DSL from natural language description."""
    try:
        from gchat.wrapper_api import expand_dsl, extract_dsl_from_description

        dsl = extract_dsl_from_description(req.text)
        if not dsl:
            return {
                "suggested_dsl": None,
                "expanded": None,
                "message": "No DSL pattern detected in text",
            }

        expanded = ""
        try:
            expanded = expand_dsl(dsl)
        except Exception:
            pass

        return {"suggested_dsl": dsl, "expanded": expanded}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/search")
async def search_components_endpoint(req: SearchRequest):
    """Search for card components using the learned scorer.

    Takes natural language and returns ranked candidates with scores,
    structure descriptions, and suggested DSL.
    """
    try:
        from gchat.card_framework_wrapper import get_card_framework_wrapper
        from gchat.wrapper_api import get_gchat_symbols

        wrapper = get_card_framework_wrapper()
        symbols = get_gchat_symbols()

        class_results, content_patterns, form_patterns = wrapper.search_hybrid_dispatch(
            description=req.description,
            component_paths=None,
            limit=req.limit,
            token_ratio=1.0,
            content_feedback="positive",
            form_feedback="positive",
            include_classes=req.include_classes,
        )

        def serialize_result(r):
            return {
                "name": r.get("name", ""),
                "type": r.get("type", ""),
                "symbol": r.get("symbol", ""),
                "score": round(r.get("score", 0), 4),
                "sim_components": round(r.get("sim_components", 0), 4),
                "sim_inputs": round(r.get("sim_inputs", 0), 4),
                "sim_relationships": round(r.get("sim_relationships", 0), 4),
                "structure_description": r.get("structure_description", ""),
                "card_description": r.get("card_description", ""),
                "relationship_text": r.get("relationship_text", ""),
                "docstring": r.get("docstring", "")[:200],
                "full_path": r.get("full_path", ""),
                "parent_paths": r.get("parent_paths", []),
                "content_feedback": r.get("content_feedback"),
                "form_feedback": r.get("form_feedback"),
            }

        all_results = (
            [serialize_result(r) for r in class_results]
            + [serialize_result(r) for r in content_patterns]
            + [serialize_result(r) for r in form_patterns]
        )

        # Deduplicate by name+type, keep highest score
        seen = {}
        for r in all_results:
            key = f"{r['name']}:{r['type']}"
            if key not in seen or r["score"] > seen[key]["score"]:
                seen[key] = r
        deduped = sorted(seen.values(), key=lambda x: x["score"], reverse=True)

        # Extract best DSL from pattern results
        # Strategy: score each pattern's description against the query for relevance,
        # then pick the DSL from the most relevant pattern
        suggested_dsl = None
        query_words = set(req.description.lower().split())

        best_match_score = -1
        for r in deduped:
            if r.get("type") != "instance_pattern":
                continue

            # Check multiple DSL sources
            dsl_candidate = None
            for text in [
                r.get("structure_description", ""),
                r.get("relationship_text", ""),
                r.get("card_description", ""),
            ]:
                if not text:
                    continue
                from gchat.wrapper_api import extract_dsl_from_description

                extracted = extract_dsl_from_description(text)
                if extracted:
                    dsl_candidate = extracted
                    break

            if not dsl_candidate:
                continue

            # Score description relevance to query (word overlap)
            desc_words = set(
                (r.get("card_description", "") or r.get("name", "")).lower().split()
            )
            overlap = len(query_words & desc_words)
            # Boost by search score (normalized)
            relevance = overlap + max(0, r["score"] + 5) * 0.1

            if relevance > best_match_score:
                best_match_score = relevance
                suggested_dsl = dsl_candidate

        return {
            "results": deduped[: req.limit],
            "total": len(deduped),
            "suggested_dsl": suggested_dsl,
            "class_count": len(class_results),
            "pattern_count": len(content_patterns),
            "form_count": len(form_patterns),
        }
    except Exception as e:
        import traceback

        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


class TextSearchRequest(BaseModel):
    query: str
    field: str = "name"
    limit: int = 20


@router.post("/text-search")
async def text_search_endpoint(req: TextSearchRequest):
    """Search using Qdrant text index (exact/stemmed match on name, docstring, relationships)."""
    try:
        from gchat.card_framework_wrapper import get_card_framework_wrapper

        wrapper = get_card_framework_wrapper()

        results = wrapper.search_by_text(
            field=req.field, query=req.query, limit=req.limit
        )

        # Also search relationship descriptions for NL queries
        rel_results = []
        if req.field == "name":
            rel_results = wrapper.search_by_relationship_text(
                query=req.query, limit=req.limit
            )

        # Merge and deduplicate
        seen = {}
        for r in results + rel_results:
            key = r.get("name", "")
            if key and key not in seen:
                seen[key] = {
                    "name": r.get("name", ""),
                    "type": r.get("type", ""),
                    "symbol": r.get("symbol", ""),
                    "full_path": r.get("full_path", ""),
                    "docstring": r.get("docstring", ""),
                    "source": "text_index",
                }

        return {
            "results": list(seen.values())[: req.limit],
            "total": len(seen),
            "field": req.field,
            "query": req.query,
        }
    except Exception as e:
        import traceback

        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/containment-rules")
async def get_containment_rules():
    """Return parent->children adjacency graph for DSL autocomplete."""
    try:
        from gchat.wrapper_api import (
            get_component_relationships_for_dsl,
            get_gchat_symbols,
        )

        adjacency = get_component_relationships_for_dsl()
        symbols = get_gchat_symbols()
        reverse = {v: k for k, v in symbols.items()}

        # Build symbol-keyed adjacency (symbol -> list of child symbols)
        symbol_adjacency = {}
        for parent, children in adjacency.items():
            parent_sym = symbols.get(parent)
            if parent_sym:
                child_syms = []
                for child in children:
                    child_sym = symbols.get(child)
                    if child_sym:
                        child_syms.append({"symbol": child_sym, "name": child})
                if child_syms:
                    symbol_adjacency[parent_sym] = child_syms

        # Identify wrapper requirements (e.g., Button must be inside ButtonList)
        # Build from adjacency: if X only appears as child of Y, then X requires Y
        wrapper_requirements = {}
        # Common known wrappers
        known_wrappers = {
            "Button": "ButtonList",
            "Chip": "ChipList",
            "GridItem": "Grid",
            "Column": "Columns",
            "CarouselCard": "Carousel",
            "NestedWidget": "CarouselCard",
        }
        for child, parent in known_wrappers.items():
            child_sym = symbols.get(child)
            parent_sym = symbols.get(parent)
            if child_sym and parent_sym:
                wrapper_requirements[child_sym] = {"symbol": parent_sym, "name": parent}

        return {
            "adjacency": adjacency,
            "symbol_adjacency": symbol_adjacency,
            "symbols": symbols,
            "wrapper_requirements": wrapper_requirements,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
