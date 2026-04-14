"""GchatCardBuilder — BuilderProtocol facade over SmartCardBuilderV2.

Implements the module-agnostic BuilderProtocol from adapters/module_wrapper
while delegating all real work to the existing SmartCardBuilderV2. This
allows the generic pipeline (SEARCH -> SCORE -> BUILD) to interact with
the gchat builder through a domain-neutral interface.

The existing builder_v2.py remains untouched and fully functional.

Usage:
    from gchat.card_builder.builder_v3 import GchatCardBuilder
    builder = GchatCardBuilder()
    card = builder.build("§[δ×3, Ƀ[ᵬ×2]] Dashboard", title="My Card")
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from adapters.module_wrapper.builder_base import (
    BuilderProtocol,
    ComponentInfo,
    ComponentRegistry,
    ParsedStructure,
)
from config.enhanced_logging import setup_logger

logger = setup_logger()


def _build_gchat_registry() -> ComponentRegistry:
    """Build a ComponentRegistry from the gchat COMPONENT_PARAMS constant."""
    from gchat.card_builder.constants import COMPONENT_PARAMS

    from research.trm.h2.domain_config import GCHAT_DOMAIN

    registry = ComponentRegistry(domain_id="gchat")
    for comp_name, fields in COMPONENT_PARAMS.items():
        pool = GCHAT_DOMAIN.component_to_pool.get(comp_name, "content_texts")
        registry.register(
            ComponentInfo(
                name=comp_name,
                pool=pool,
                fields={k: "str" for k in fields},
                defaults={},
                description=next(iter(fields.values()), ""),
            )
        )
    return registry


class GchatCardBuilder:
    """BuilderProtocol implementation for Google Chat cards.

    Wraps SmartCardBuilderV2 with the module-agnostic BuilderProtocol
    interface. Explicitly passes GCHAT_DOMAIN config to slot assignment.
    """

    def __init__(self) -> None:
        self._v2 = None  # Lazy init
        self._registry: Optional[ComponentRegistry] = None

    def _get_v2(self):
        """Lazy-load SmartCardBuilderV2."""
        if self._v2 is None:
            from gchat.card_builder.builder_v2 import SmartCardBuilderV2

            self._v2 = SmartCardBuilderV2()
        return self._v2

    @property
    def domain_id(self) -> str:
        return "gchat"

    @property
    def registry(self) -> ComponentRegistry:
        if self._registry is None:
            self._registry = _build_gchat_registry()
        return self._registry

    def parse_dsl(self, description: str) -> Optional[ParsedStructure]:
        """Parse DSL from description using the gchat wrapper's DSL parser."""
        v2 = self._get_v2()
        structure_dsl = v2._extract_structure_dsl(description)
        if not structure_dsl:
            return None

        # Parse content DSL for styled texts
        content = v2._parse_content_dsl(description)
        content_items: Dict[str, list] = {}
        if content:
            content_items["content_texts"] = content.get("texts", [])
            content_items["buttons"] = content.get("buttons", [])

        return ParsedStructure(
            components=[],  # Populated by v2 validator internally
            content_items=content_items,
            raw_dsl=structure_dsl,
            metadata={"has_content_dsl": content is not None},
        )

    def build_supply_map(
        self,
        parsed: ParsedStructure,
        **content_kwargs: Any,
    ) -> Dict[str, list]:
        """Build supply map from parsed structure and explicit content."""
        from research.trm.h2.domain_config import GCHAT_DOMAIN

        supply_map: Dict[str, list] = {pool: [] for pool in GCHAT_DOMAIN.pool_vocab}

        # Merge content from parsed DSL
        for pool_key, items in parsed.content_items.items():
            if pool_key in supply_map:
                supply_map[pool_key].extend(items)

        # Merge explicit content kwargs
        for key in ("buttons", "chips", "columns", "grid_items", "carousel_cards", "content_texts"):
            explicit = content_kwargs.get(key)
            if explicit and key in supply_map:
                supply_map[key].extend(explicit)

        return supply_map

    def reassign_slots(
        self,
        supply_map: Dict[str, list],
        demands: Dict[str, int],
    ) -> Dict[str, list]:
        """Use TRM scoring to reassign content, passing GCHAT_DOMAIN explicitly."""
        from gchat.card_builder.slot_assignment import reassign_supply_map
        from research.trm.h2.domain_config import GCHAT_DOMAIN

        return reassign_supply_map(
            supply_map, demands, domain_config=GCHAT_DOMAIN
        )

    def render_component(self, name: str, params: Dict[str, Any]) -> Any:
        """Render a gchat component via the wrapper's cached class loader."""
        v2 = self._get_v2()
        wrapper = v2._get_wrapper()
        if wrapper is None:
            return params

        cls = wrapper.get_cached_class(name)
        if cls is None:
            return params

        try:
            return cls(**params)
        except Exception:
            return params

    def build(self, description: str, **kwargs: Any) -> Any:
        """Delegate to SmartCardBuilderV2.build() for full pipeline.

        Accepts the same kwargs as SmartCardBuilderV2.build():
        title, subtitle, buttons, chips, image_url, text, items,
        grid_items, cards.
        """
        v2 = self._get_v2()
        return v2.build(description, **kwargs)

    # =========================================================================
    # GCHAT-SPECIFIC: Feedback section creation
    # =========================================================================

    def build_with_feedback(self, description: str, **kwargs: Any) -> Any:
        """Build a card with feedback buttons appended.

        Delegates to v2 builder which handles feedback section creation,
        icon building, and pattern storage — all gchat-specific operations.
        """
        v2 = self._get_v2()
        # Ensure feedback is enabled for this build
        kwargs.setdefault("include_feedback", True)
        return v2.build(description, **kwargs)

    def build_icon(self, icon_name: str, fill: bool = None, weight: int = None) -> dict:
        """Build a gchat Material Icon dict — gchat-specific rendering."""
        v2 = self._get_v2()
        return v2._build_material_icon(icon_name, fill, weight)

    def store_pattern(self, description: str, card: dict) -> None:
        """Store a card build as a reusable prepared pattern — gchat-specific."""
        v2 = self._get_v2()
        if hasattr(v2, '_store_pattern_async'):
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(v2._store_pattern_async(description, card))
                else:
                    loop.run_until_complete(v2._store_pattern_async(description, card))
            except RuntimeError:
                pass  # No event loop — skip pattern storage
