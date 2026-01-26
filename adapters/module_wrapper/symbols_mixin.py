"""
Advanced Symbol Functionality Mixin

Provides symbol generation, DSL parsing, backfill, and embedding text
generation for the ModuleWrapper system.
"""

import logging
from collections import Counter
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# =============================================================================
# SYMBOLS MIXIN
# =============================================================================

class SymbolsMixin:
    """
    Mixin providing advanced symbol functionality.

    Expects the following attributes on self:
    - symbol_mapping: Dict[str, str] (component → symbol)
    - reverse_symbol_mapping: Dict[str, str] (symbol → component)
    - components: Dict[str, ModuleComponent]
    - relationships: Dict[str, List[str]]
    - client: Qdrant client
    - collection_name: str
    - module_name: str
    """

    def get_symbol_table_text(
        self,
        module_prefix: Optional[str] = None,
        custom_overrides: Optional[Dict[str, str]] = None,
    ) -> str:
        """
        Generate human-readable symbol table for LLM instructions.

        Args:
            module_prefix: Optional module identifier
            custom_overrides: Optional symbol overrides

        Returns:
            Formatted markdown text suitable for MCP tool descriptions
        """
        from adapters.module_wrapper.symbol_generator import SymbolGenerator

        prefix = module_prefix or self.module_name

        component_names = [
            comp.name for comp in self.components.values()
            if comp.component_type == "class"
        ]

        generator = SymbolGenerator(
            module_prefix=prefix,
            custom_symbols=custom_overrides,
        )
        generator.generate_symbols(component_names)

        return generator.get_symbol_table_text()

    def build_component_embedding_with_symbol(
        self,
        component_name: str,
        module_prefix: Optional[str] = None,
    ) -> str:
        """
        Build embedding text for a component that includes its symbol.

        Args:
            component_name: Name of the component
            module_prefix: Optional module prefix

        Returns:
            Text for embedding with strong symbol-component association
        """
        from adapters.module_wrapper.symbol_generator import SymbolGenerator

        prefix = module_prefix or self.module_name
        generator = SymbolGenerator(module_prefix=prefix)

        return generator.build_embedding_text(component_name)

    def get_symbol_wrapped_text(self, component_name: str, text: str) -> str:
        """
        Wrap text with the component's symbol for deterministic ColBERT embedding.

        Format: "{symbol} {text} {symbol}"

        This creates strong bidirectional token-level associations in ColBERT
        embeddings. The format is ALWAYS the same - no variation.

        Args:
            component_name: Name of the component (e.g., "Button")
            text: The text to wrap

        Returns:
            Symbol-wrapped text if mapping exists, otherwise original text

        Example:
            >>> wrapper.get_symbol_wrapped_text("Button", "Button click widget")
            "ᵬ Button click widget ᵬ"
        """
        symbol = self.symbol_mapping.get(component_name)
        if symbol:
            return f"{symbol} {text} {symbol}"
        return text

    def get_symbol_for_component(self, component_name: str) -> Optional[str]:
        """Get the symbol for a component, if one exists."""
        return self.symbol_mapping.get(component_name)

    def get_component_for_symbol(self, symbol: str) -> Optional[str]:
        """Get the component name for a symbol, if one exists."""
        return self.reverse_symbol_mapping.get(symbol)

    def query_by_symbol(
        self,
        symbol: str,
        collection_name: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Query Qdrant for a component by its symbol.

        Uses the symbol payload index for fast exact matching.

        Args:
            symbol: The symbol to look up (e.g., "ᵬ")
            collection_name: Collection to query

        Returns:
            Component payload dict if found, None otherwise
        """
        if not self.client:
            comp_name = self.get_component_for_symbol(symbol)
            if comp_name and comp_name in self.components:
                return self.components[comp_name].to_dict()
            return None

        from qdrant_client import models

        target_collection = collection_name or self.collection_name

        try:
            results, _ = self.client.scroll(
                collection_name=target_collection,
                scroll_filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="symbol",
                            match=models.MatchValue(value=symbol),
                        )
                    ]
                ),
                limit=1,
                with_payload=True,
            )

            if results:
                return dict(results[0].payload)
            return None

        except Exception as e:
            logger.warning(f"Symbol query failed: {e}")
            comp_name = self.get_component_for_symbol(symbol)
            if comp_name and comp_name in self.components:
                return self.components[comp_name].to_dict()
            return None

    def parse_dsl_to_components(self, dsl_string: str) -> Dict[str, Any]:
        """
        Parse DSL notation and resolve to component names and paths.

        This is the CANONICAL method for parsing DSL notation like "§[δ×3, Ƀ[ᵬ×2]]"
        into a structured representation with resolved component names.

        Args:
            dsl_string: DSL notation string (e.g., "§[δ×3, Ƀ[ᵬ×2]]")

        Returns:
            Dict with:
                - dsl: Original DSL string
                - root: Root component info
                - components: List of all components with counts
                - component_paths: Flat list of component paths for instantiation
                - is_valid: Whether structure passed validation
                - structure: Nested structure representation
        """
        reverse_symbols = self.reverse_symbol_mapping

        def tokenize(s: str) -> List[str]:
            """Tokenize DSL string."""
            tokens = []
            i = 0
            while i < len(s):
                char = s[i]
                if char in " ,\n\t":
                    i += 1
                    continue
                if char in "[]":
                    tokens.append(char)
                    i += 1
                    continue
                if char in "×*x" and i + 1 < len(s) and s[i + 1].isdigit():
                    j = i + 1
                    while j < len(s) and s[j].isdigit():
                        j += 1
                    tokens.append(f"×{s[i+1:j]}")
                    i = j
                    continue
                if char in reverse_symbols:
                    tokens.append(char)
                    i += 1
                    continue
                if char.isalpha():
                    j = i
                    while j < len(s) and (s[j].isalnum() or s[j] == "_"):
                        j += 1
                    tokens.append(s[i:j])
                    i = j
                    continue
                i += 1
            return tokens

        def parse_tokens(tokens: List[str], pos: int) -> tuple:
            """Parse tokens into nested structure."""
            nodes = []
            while pos < len(tokens):
                token = tokens[pos]
                if token == "]":
                    return nodes, pos + 1
                if token == "[":
                    pos += 1
                    continue
                if token.startswith("×"):
                    if nodes:
                        nodes[-1]["count"] = int(token[1:])
                    pos += 1
                    continue

                comp_name = reverse_symbols.get(token, token)
                symbol = self.symbol_mapping.get(comp_name, token)

                node = {
                    "symbol": symbol,
                    "name": comp_name,
                    "count": 1,
                    "children": [],
                }

                if pos + 1 < len(tokens) and tokens[pos + 1] == "[":
                    children, pos = parse_tokens(tokens, pos + 2)
                    node["children"] = children
                else:
                    pos += 1

                nodes.append(node)
            return nodes, pos

        def collect_paths(node: dict, paths: List[str]) -> None:
            """Recursively collect component paths."""
            for _ in range(node["count"]):
                paths.append(node["name"])
            for child in node.get("children", []):
                collect_paths(child, paths)

        def flatten_components(nodes: List[dict], result: List[dict]) -> None:
            """Flatten nested structure to component list."""
            for node in nodes:
                result.append({
                    "symbol": node["symbol"],
                    "name": node["name"],
                    "count": node["count"],
                })
                flatten_components(node.get("children", []), result)

        # Parse
        tokens = tokenize(dsl_string)
        if not tokens:
            return {
                "dsl": dsl_string,
                "root": None,
                "components": [],
                "component_paths": [],
                "is_valid": False,
                "error": "Empty or invalid DSL string",
            }

        parsed, _ = parse_tokens(tokens, 0)

        root = parsed[0] if parsed else None
        components = []
        flatten_components(parsed, components)

        component_paths = []
        for node in parsed:
            collect_paths(node, component_paths)

        validation = self.validate_structure(dsl_string)

        return {
            "dsl": dsl_string,
            "root": {"symbol": root["symbol"], "name": root["name"]} if root else None,
            "components": components,
            "component_paths": component_paths,
            "is_valid": validation.is_valid,
            "issues": validation.issues if not validation.is_valid else [],
            "structure": parsed,
        }

    def instantiate_from_dsl(
        self,
        dsl_string: str,
        content: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Parse DSL and prepare component instances with content.

        Args:
            dsl_string: DSL notation string (e.g., "§[δ×3, Ƀ[ᵬ×2]]")
            content: Optional dict mapping component symbols/names to content values

        Returns:
            Dict with parsed info, instances list, and component_classes
        """
        parsed = self.parse_dsl_to_components(dsl_string)

        if not parsed.get("is_valid", False):
            return {
                "parsed": parsed,
                "instances": [],
                "component_classes": {},
                "error": parsed.get("error") or parsed.get("issues", ["Invalid structure"]),
            }

        content = content or {}
        instances = []
        component_classes = {}

        for comp_info in parsed.get("components", []):
            comp_name = comp_info["name"]
            symbol = comp_info["symbol"]
            count = comp_info["count"]

            comp_class = self.get_component_by_path(f"{self.module_name}.{comp_name}")
            if comp_class:
                component_classes[comp_name] = comp_class

            comp_content = content.get(symbol) or content.get(comp_name)

            for i in range(count):
                instance_content = None
                if isinstance(comp_content, list) and i < len(comp_content):
                    instance_content = comp_content[i]
                elif comp_content and not isinstance(comp_content, list):
                    instance_content = comp_content

                instances.append({
                    "name": comp_name,
                    "symbol": symbol,
                    "index": i,
                    "class": comp_class,
                    "content": instance_content,
                })

        return {
            "parsed": parsed,
            "instances": instances,
            "component_classes": component_classes,
        }

    def build_dsl_from_paths(
        self,
        component_paths: List[str],
        structure_description: str = "",
        root_component: Optional[str] = None,
    ) -> str:
        """
        Build DSL notation from a list of component paths.

        This is the CANONICAL method for generating DSL notation for instance_patterns.

        Args:
            component_paths: List of component paths or names
            structure_description: Optional NL description to append
            root_component: Optional root component name

        Returns:
            DSL notation string suitable for embedding in relationships vector
        """
        symbols = self.symbol_mapping

        if not component_paths:
            root_name = root_component or "Root"
            root_symbol = symbols.get(root_name, root_name[0])
            empty_dsl = f"{root_symbol}[]"
            if structure_description:
                return f"{empty_dsl} | {structure_description[:100]}"
            return empty_dsl

        components = []
        for path in component_paths:
            name = path.split(".")[-1] if "." in path else path
            components.append(name)

        root_name = root_component or components[0]
        root_symbol = symbols.get(root_name, root_name[0])

        counts = Counter(components)

        dsl_parts = []
        name_parts = []
        seen = set()

        for comp in components:
            if comp in seen:
                continue
            seen.add(comp)

            count = counts[comp]
            symbol = symbols.get(comp, comp[0])

            if comp == root_name:
                continue

            if count > 1:
                dsl_parts.append(f"{symbol}×{count}")
                name_parts.append(f"{comp}×{count}")
            else:
                dsl_parts.append(symbol)
                name_parts.append(comp)

        dsl_notation = f"{root_symbol}[{', '.join(dsl_parts)}]" if dsl_parts else f"{root_symbol}[]"
        names_text = " ".join(name_parts) if name_parts else root_name

        combined = f"{dsl_notation} | {names_text}"

        if structure_description:
            combined = f"{combined} :: {structure_description[:100]}"

        return combined

    def get_dsl_for_component(self, component_name: str, max_children: int = 5) -> str:
        """
        Get the DSL structure showing what a component can contain.

        Args:
            component_name: Component to get DSL for
            max_children: Max children to include

        Returns:
            DSL string like "§[ʍ, δ, Ƀ]"
        """
        symbol = self.symbol_mapping.get(component_name, component_name)
        children = self.relationships.get(component_name, [])

        if not children:
            return symbol

        child_syms = [self.symbol_mapping.get(c, c) for c in children[:max_children]]
        return f"{symbol}[{', '.join(child_syms)}]"

    def get_embedding_text(self, component_name: str, include_dsl: bool = True) -> str:
        """
        Get embedding-efficient text for a component.

        Combines symbol, name, and DSL relationships into compact text.

        Args:
            component_name: Name of the component
            include_dsl: Whether to include DSL structure in text

        Returns:
            Compact text suitable for embedding
        """
        validator = self.get_structure_validator()
        return validator.get_enriched_relationship_text(component_name)

    def get_all_embedding_texts(self) -> Dict[str, str]:
        """Get embedding texts for all components with relationships."""
        validator = self.get_structure_validator()
        return validator.get_all_enriched_relationships()

    def backfill_symbols(self, batch_size: int = 100) -> Dict[str, int]:
        """
        Backfill symbol fields for existing points that don't have them.

        Args:
            batch_size: Number of points to process per batch

        Returns:
            Dict with counts: {"updated": N, "skipped": N, "errors": N}
        """
        if not self.client:
            logger.warning("Cannot backfill symbols: Qdrant client not available")
            return {"updated": 0, "skipped": 0, "errors": 0}

        try:
            from qdrant_client.models import PointStruct

            symbols = self.symbol_mapping
            updated = 0
            skipped = 0
            errors = 0

            logger.info(f"Starting symbol backfill for {self.collection_name}...")

            offset = None
            while True:
                results = self.client.scroll(
                    collection_name=self.collection_name,
                    limit=batch_size,
                    offset=offset,
                    with_payload=True,
                    with_vectors=True,
                )

                points, next_offset = results
                if not points:
                    break

                updated_points = []
                for point in points:
                    try:
                        payload = point.payload or {}

                        if payload.get("symbol"):
                            skipped += 1
                            continue

                        point_type = payload.get("type")
                        symbol = None
                        component_symbols = []

                        if point_type == "instance_pattern":
                            parent_paths = payload.get("parent_paths", [])
                            if not parent_paths:
                                skipped += 1
                                continue

                            comp_names = [p.split(".")[-1] if "." in p else p for p in parent_paths]
                            root_name = comp_names[0] if comp_names else None
                            symbol = symbols.get(root_name) if root_name else None
                            component_symbols = [symbols.get(n) for n in comp_names if symbols.get(n)]

                            if not symbol:
                                skipped += 1
                                continue
                        else:
                            name = payload.get("name")
                            if not name:
                                skipped += 1
                                continue

                            symbol = symbols.get(name)
                            if not symbol:
                                skipped += 1
                                continue

                        new_payload = payload.copy()
                        new_payload["symbol"] = symbol

                        if point_type == "instance_pattern" and component_symbols:
                            new_payload["component_symbols"] = component_symbols

                        updated_point = PointStruct(
                            id=point.id,
                            vector=point.vector,
                            payload=new_payload,
                        )
                        updated_points.append(updated_point)
                        updated += 1

                    except Exception as e:
                        logger.warning(f"Error processing point {point.id}: {e}")
                        errors += 1

                if updated_points:
                    self.client.upsert(
                        collection_name=self.collection_name,
                        points=updated_points,
                    )
                    logger.info(f"Backfilled {len(updated_points)} points with symbols")

                if next_offset is None:
                    break
                offset = next_offset

            logger.info(f"Symbol backfill complete: {updated} updated, {skipped} skipped, {errors} errors")
            return {"updated": updated, "skipped": skipped, "errors": errors}

        except Exception as e:
            logger.error(f"Symbol backfill failed: {e}")
            return {"updated": 0, "skipped": 0, "errors": 1}

    def print_dsl_summary(self, use_rich: bool = True) -> None:
        """
        Print a summary of DSL symbols and relationships.

        Args:
            use_rich: Use Rich library for formatted output
        """
        try:
            if use_rich:
                from rich.console import Console
                from rich.table import Table

                console = Console()

                table = Table(title=f"DSL Symbols for {self.module_name}")
                table.add_column("Symbol", style="cyan")
                table.add_column("Component", style="green")
                table.add_column("Can Contain", style="yellow")

                for comp, sym in sorted(self.symbol_mapping.items(), key=lambda x: x[0])[:30]:
                    children = self.relationships.get(comp, [])
                    child_syms = [self.symbol_mapping.get(c, c) for c in children[:4]]
                    child_str = ", ".join(child_syms) if child_syms else "-"
                    table.add_row(sym, comp, child_str)

                console.print(table)

                meta = self.dsl_metadata
                console.print(f"\n[bold]Summary:[/bold]")
                console.print(f"  Symbols: {meta['symbol_count']}")
                console.print(f"  Containers: {len(meta['containers'])}")
                console.print(f"  Items: {len(meta['items'])}")
            else:
                raise ImportError("Rich not requested")

        except ImportError:
            print(f"DSL Symbols for {self.module_name}")
            print("=" * 50)
            for comp, sym in sorted(self.symbol_mapping.items())[:20]:
                children = self.relationships.get(comp, [])
                child_str = ", ".join(children[:3]) if children else "-"
                print(f"  {sym} = {comp} → [{child_str}]")

            meta = self.dsl_metadata
            print(f"\nSymbols: {meta['symbol_count']}, Containers: {len(meta['containers'])}")

    def get_styling_registry(self):
        """Get the styling registry for formatting rules."""
        from adapters.module_wrapper.symbol_generator import create_default_styling_registry
        return create_default_styling_registry()


# Export for convenience
__all__ = [
    "SymbolsMixin",
]
