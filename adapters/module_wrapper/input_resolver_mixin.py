"""
Input Resolution Mixin

Provides generic symbol-keyed param resolution and sequential context consumption
for any domain that uses DSL symbols mapped to component types.

Domains register field extractors, overflow handlers, and param key overrides
at setup time. The mixin handles:
- Symbol -> flat key resolution (e.g., delta -> "items")
- _shared/_items merging (merge shared props into each item)
- Sequential context consumption (buttons[0], buttons[1], ...)
- Context key -> param key bridging with overrides

Init order: 52 (after GraphMixin:50, SymbolsMixin:45)
"""

import logging
from typing import Any, Callable, Dict, FrozenSet, Optional, Set, Tuple

from adapters.module_wrapper.types import ComponentName, JsonDict

logger = logging.getLogger(__name__)

# Type aliases for registered callables
FieldExtractor = Callable[[dict, int], dict]  # (resource, index) -> extracted params
OverflowHandler = Callable[
    [str, int], dict
]  # (component_name, index) -> fallback params


class InputResolverMixin:
    """
    Mixin providing domain-agnostic input resolution for DSL-driven builders.

    Expects the following attributes on self (from GraphMixin / SymbolsMixin):
    - _context_resources: Dict[str, Tuple[str, str]] (component -> (context_key, index_key))
    - reverse_symbol_mapping: Dict[str, str] (symbol -> component name)

    Domains register extractors and handlers via register_input_resolution_batch().
    """

    # --- Mixin dependency contract ---
    _MIXIN_PROVIDES: FrozenSet[str] = frozenset(
        {
            "resolve_symbol_params",
            "consume_from_context",
            "normalize_shared_items",
            "register_field_extractor",
            "register_overflow_handler",
            "register_input_resolution_batch",
            "get_param_key_for_component",
        }
    )
    _MIXIN_REQUIRES: FrozenSet[str] = frozenset(
        {"_context_resources", "reverse_symbol_mapping"}
    )
    _MIXIN_INIT_ORDER: int = 52

    def __init__(self, *args, **kwargs):
        """Initialize input resolver registries."""
        super().__init__(*args, **kwargs)
        self._field_extractors: Dict[str, FieldExtractor] = {}
        self._overflow_handlers: Dict[str, OverflowHandler] = {}
        self._param_key_overrides: Dict[str, str] = {}
        self._scalar_param_keys: Set[str] = set()

    # =========================================================================
    # REGISTRATION
    # =========================================================================

    def register_field_extractor(
        self, context_key: str, extractor: FieldExtractor
    ) -> None:
        """Register a field extractor for a context key.

        Args:
            context_key: The context resource key (e.g., "buttons", "content_texts")
            extractor: Callable (resource_dict, index) -> extracted_params_dict
        """
        self._field_extractors[context_key] = extractor

    def register_overflow_handler(
        self, component_name: str, handler: OverflowHandler
    ) -> None:
        """Register an overflow handler for a component type.

        Called when context resources are exhausted (index >= len(resources)).

        Args:
            component_name: Component type (e.g., "Button", "GridItem")
            handler: Callable (component_name, index) -> fallback_params_dict
        """
        self._overflow_handlers[component_name] = handler

    def register_input_resolution_batch(
        self,
        extractors: Optional[Dict[str, FieldExtractor]] = None,
        overflow_handlers: Optional[Dict[str, OverflowHandler]] = None,
        param_key_overrides: Optional[Dict[str, str]] = None,
        scalar_params: Optional[Set[str]] = None,
    ) -> None:
        """Bulk registration of input resolution configuration.

        Args:
            extractors: context_key -> field extractor function
            overflow_handlers: component_name -> overflow handler function
            param_key_overrides: context_key -> flat param key (only non-identity)
            scalar_params: Set of param keys that are scalar (not list-wrapped)
        """
        if extractors:
            self._field_extractors.update(extractors)
        if overflow_handlers:
            self._overflow_handlers.update(overflow_handlers)
        if param_key_overrides:
            self._param_key_overrides.update(param_key_overrides)
        if scalar_params:
            self._scalar_param_keys.update(scalar_params)

        logger.info(
            f"Registered input resolution: "
            f"{len(self._field_extractors)} extractors, "
            f"{len(self._overflow_handlers)} overflow handlers, "
            f"{len(self._param_key_overrides)} param key overrides"
        )

    # =========================================================================
    # PARAM KEY RESOLUTION
    # =========================================================================

    def get_param_key_for_component(self, component_name: str) -> Optional[str]:
        """Derive the flat param key for a component.

        Uses _context_resources (from GraphMixin) to get the context_key,
        then applies param_key_overrides if registered.

        Args:
            component_name: Component type (e.g., "Button", "DecoratedText")

        Returns:
            Flat param key (e.g., "buttons", "items") or None if no resource info.
        """
        resource_info = self._context_resources.get(component_name)
        if not resource_info:
            return None
        context_key = resource_info[0]
        return self._param_key_overrides.get(context_key, context_key)

    # =========================================================================
    # SYMBOL PARAM RESOLUTION
    # =========================================================================

    def resolve_symbol_params(
        self,
        params: Optional[Dict[str, Any]],
        reverse_mapping: Optional[Dict[str, str]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Resolve symbol-keyed params to flat builder keys.

        Scans params for keys that are DSL symbols. For each symbol key found,
        resolves it to the corresponding flat builder key (e.g., delta -> "items").

        If no symbol keys are found, returns params unchanged.

        Args:
            params: Dict potentially containing symbol keys.
            reverse_mapping: symbol -> component name mapping. If None, uses
                self.reverse_symbol_mapping.

        Returns:
            New dict with symbol keys resolved to flat builder keys.
        """
        if not params:
            return params

        if reverse_mapping is None:
            reverse_mapping = getattr(self, "reverse_symbol_mapping", None)

        if not reverse_mapping:
            return params

        symbol_keys = {k for k in params if k in reverse_mapping}
        if not symbol_keys:
            return params

        result = {k: v for k, v in params.items() if k not in symbol_keys}

        for symbol in symbol_keys:
            component_name = reverse_mapping[symbol]
            flat_key = self.get_param_key_for_component(component_name)
            if flat_key is None:
                logger.warning(
                    f"No param key for component '{component_name}' "
                    f"(symbol '{symbol}'), skipping"
                )
                continue

            value = params[symbol]
            resolved = self.normalize_shared_items(value, flat_key)

            if resolved is not None:
                result[flat_key] = resolved
                logger.info(
                    f"Resolved symbol '{symbol}' -> '{component_name}' -> "
                    f"flat key '{flat_key}' "
                    f"({len(resolved) if isinstance(resolved, list) else type(resolved).__name__} items)"
                )

        return result

    # =========================================================================
    # SHARED/ITEMS NORMALIZATION
    # =========================================================================

    def normalize_shared_items(self, value: Any, flat_key: str) -> Any:
        """Normalize a symbol-keyed value to the format the builder expects.

        Supported formats:
            - list -> pass through
            - dict with "_items" -> merge _shared into each item
            - dict without "_items" -> wrap in list (for array-type keys)
            - str / other -> pass through
        """
        if isinstance(value, list):
            return value

        if isinstance(value, dict):
            items = value.get("_items")
            if items is not None:
                shared = value.get("_shared", {})
                return [{**shared, **item} for item in items]
            if flat_key not in self._scalar_param_keys:
                return [value]
            return value

        return value

    # =========================================================================
    # CONTEXT CONSUMPTION
    # =========================================================================

    def consume_from_context(
        self,
        component_name: ComponentName,
        context: JsonDict,
    ) -> JsonDict:
        """Consume the next resource from context for a component type.

        Uses registered field extractors to pull fields from the resource.
        Falls back to pass-through (dict(resource)) if no extractor is registered.

        Args:
            component_name: Component type (e.g., "Button", "DecoratedText")
            context: Shared context dict with resources and index counters

        Returns:
            Dict with params consumed from context
        """
        resource_info = self._context_resources.get(component_name)
        if not resource_info:
            return {}

        context_key, index_key = resource_info
        resources = context.get(context_key, [])
        current_index = context.get(index_key, 0)

        params: JsonDict = {}
        mapping_report = context.get("_mapping_report")

        if current_index < len(resources):
            resource = resources[current_index]
            if isinstance(resource, dict):
                extractor = self._field_extractors.get(context_key)
                if extractor:
                    params = extractor(resource, current_index)
                else:
                    # Default: pass through all fields
                    params = dict(resource)

                # Record consumption in mapping report if present
                if mapping_report:
                    # Use component-appropriate value for the report
                    report_value = str(
                        resource.get("text")
                        or resource.get("title")
                        or resource.get("label")
                        or resource.get("styled")
                        or ""
                    )
                    mapping_report.record(
                        input_type=context_key.rstrip("s"),  # buttons -> button
                        index=current_index,
                        value=report_value,
                        component=component_name,
                        field_name=context_key.rstrip("s"),
                    )
            context[index_key] = current_index + 1
        else:
            # Resources exhausted - use overflow handler if registered
            handler = self._overflow_handlers.get(component_name)
            if handler:
                params = handler(component_name, current_index)
            context[index_key] = current_index + 1

        return params


__all__ = [
    "InputResolverMixin",
    "FieldExtractor",
    "OverflowHandler",
]
