"""
Resolve symbol-keyed card_params to flat builder keys.

Allows LLMs to use DSL symbols (δ, ᵬ, ǵ, etc.) as keys in card_params
for a direct 1:1 correspondence between structure DSL and content.

Example:
    {"δ": {"_shared": {"top_label": "Service"}, "_items": [{"text": "Drive"}, {"text": "Gmail"}]}}
    →
    {"items": [{"top_label": "Service", "text": "Drive"}, {"top_label": "Service", "text": "Gmail"}]}
"""

import logging
from typing import Any, Dict, Optional

from gchat.card_builder.metadata import get_context_resource

logger = logging.getLogger(__name__)

# Bridge between builder context keys and the flat card_params keys.
# Only entries where context_key != param_key need to be listed.
_CONTEXT_KEY_TO_PARAM: Dict[str, str] = {
    "content_texts": "items",
    "carousel_cards": "cards",
    "grid_items": "items",
}

# Scalar param keys (value is a single string, not a list)
_SCALAR_PARAMS = frozenset({"image_url"})


def _resolve_param_key(
    component_name: str, wrapper: Optional[Any] = None
) -> Optional[str]:
    """Derive the flat card_params key for a component.

    Uses the wrapper (SSoT) or metadata fallback to get the context_key,
    then maps it to the card_params key.
    """
    resource_info = get_context_resource(component_name, wrapper)
    if resource_info:
        context_key, _ = resource_info
        return _CONTEXT_KEY_TO_PARAM.get(context_key, context_key)
    return None


def resolve_symbol_params(
    card_params: Dict[str, Any],
    reverse_symbol_mapping: Dict[str, str],
    wrapper: Optional[Any] = None,
) -> Dict[str, Any]:
    """Resolve symbol-keyed card_params to flat builder keys.

    Scans card_params for keys that are DSL symbols. For each symbol key found,
    resolves it to the corresponding flat builder key (e.g. δ → "items",
    ᵬ → "buttons") using the wrapper's context resource metadata.

    If no symbol keys are found, returns card_params unchanged (backwards compatible).

    Args:
        card_params: The card_params dict, potentially containing symbol keys.
        reverse_symbol_mapping: symbol → component name mapping from the wrapper.
        wrapper: Optional ModuleWrapper for dynamic metadata lookups.

    Returns:
        A new dict with symbol keys resolved to flat builder keys.
    """
    if not card_params or not reverse_symbol_mapping:
        return card_params

    # Detect which keys are symbols
    symbol_keys = {k for k in card_params if k in reverse_symbol_mapping}

    if not symbol_keys:
        return card_params

    # Build result: start with non-symbol keys
    result = {k: v for k, v in card_params.items() if k not in symbol_keys}

    for symbol in symbol_keys:
        component_name = reverse_symbol_mapping[symbol]
        flat_key = _resolve_param_key(component_name, wrapper)
        if flat_key is None:
            logger.warning(
                f"No param key for component '{component_name}' (symbol '{symbol}'), skipping"
            )
            continue

        value = card_params[symbol]
        resolved = _normalize_value(value, flat_key)

        if resolved is not None:
            # Symbol keys override flat keys on conflict
            result[flat_key] = resolved
            logger.debug(
                f"Resolved symbol '{symbol}' → '{component_name}' → flat key '{flat_key}'"
            )

    return result


def _normalize_value(value: Any, flat_key: str) -> Any:
    """Normalize a symbol-keyed value to the format the builder expects.

    Supported formats:
        - list → array of component instances (pass through)
        - dict with "_items" → merge _shared into each item
        - dict without "_items" → single component instance (wrapped in list)
        - str → single value (for scalar keys like image_url)
    """
    if isinstance(value, list):
        return value

    if isinstance(value, dict):
        items = value.get("_items")
        if items is not None:
            shared = value.get("_shared", {})
            return [{**shared, **item} for item in items]
        # Single component dict — wrap in list for array-type keys
        if flat_key not in _SCALAR_PARAMS:
            return [value]
        return value

    if isinstance(value, str):
        return value

    return value
