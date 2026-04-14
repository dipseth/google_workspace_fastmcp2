"""EmailBuilder — BuilderProtocol implementation for MJML email rendering.

Implements the module-agnostic BuilderProtocol for composing email
blocks using the same SEARCH -> SCORE -> BUILD pipeline as gchat cards.
Uses EMAIL_DOMAIN config for TRM-based slot assignment.

Supports all 13 email block types: Hero, Text, Button, Image, Columns,
Spacer, Divider, Footer, Header, Social, Table, Accordion, Carousel.

Usage:
    from gmail.email_builder import EmailBuilder
    builder = EmailBuilder()
    spec = builder.build("Welcome newsletter with CTA", subject="Welcome!")
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


def _build_email_registry() -> ComponentRegistry:
    """Build ComponentRegistry from email block types."""
    from adapters.domain_config import EMAIL_DOMAIN
    from gmail.email_wrapper_setup import EMAIL_WIDGET_TYPES

    registry = ComponentRegistry(domain_id="email")

    # Map block types to their key fields
    block_fields = {
        "HeroBlock": {
            "title": "str",
            "subtitle": "str",
            "cta_text": "str",
            "cta_url": "str",
        },
        "TextBlock": {"text": "str", "font_size": "str", "align": "str"},
        "ButtonBlock": {"text": "str", "url": "str", "background_color": "str"},
        "ImageBlock": {"src": "str", "alt": "str", "width": "str"},
        "ColumnsBlock": {"columns": "list"},
        "SpacerBlock": {"height_px": "int"},
        "DividerBlock": {"border_color": "str"},
        "FooterBlock": {"text": "str", "unsubscribe_url": "str"},
        "HeaderBlock": {"logo_url": "str", "title": "str"},
        "SocialBlock": {"links": "list"},
        "TableBlock": {"headers": "list", "rows": "list"},
        "AccordionBlock": {"items": "list"},
        "CarouselBlock": {"images": "list"},
    }

    for comp_name in EMAIL_WIDGET_TYPES:
        pool = EMAIL_DOMAIN.component_to_pool.get(comp_name, "content")
        fields = block_fields.get(comp_name, {})
        registry.register(
            ComponentInfo(
                name=comp_name,
                pool=pool,
                fields=fields,
                defaults={},
                description=f"Email {comp_name}",
            )
        )
    return registry


class EmailBuilder:
    """BuilderProtocol implementation for MJML email rendering.

    Uses EMAIL_DOMAIN config for slot assignment and renders
    email blocks via their to_mjml() methods.
    """

    def __init__(self) -> None:
        self._registry: Optional[ComponentRegistry] = None

    @property
    def domain_id(self) -> str:
        return "email"

    @property
    def registry(self) -> ComponentRegistry:
        if self._registry is None:
            self._registry = _build_email_registry()
        return self._registry

    def parse_dsl(self, description: str) -> Optional[ParsedStructure]:
        """Parse email DSL from description."""
        from gmail.email_wrapper_api import (
            extract_email_dsl_from_description,
            parse_email_dsl,
        )

        dsl_str = extract_email_dsl_from_description(description)
        if not dsl_str:
            return None

        result = parse_email_dsl(dsl_str)
        if not result or not result.is_valid:
            return None

        components = [(name, count) for name, count in result.component_counts.items()]

        return ParsedStructure(
            components=components,
            content_items={},
            raw_dsl=dsl_str,
            metadata={"parse_result": result},
        )

    def build_supply_map(
        self,
        parsed: ParsedStructure,
        **content_kwargs: Any,
    ) -> Dict[str, list]:
        """Build supply map from parsed structure and explicit content."""
        from adapters.domain_config import EMAIL_DOMAIN

        supply_map: Dict[str, list] = {pool: [] for pool in EMAIL_DOMAIN.pool_vocab}

        # Merge content from parsed DSL
        for pool_key, items in parsed.content_items.items():
            if pool_key in supply_map:
                supply_map[pool_key].extend(items)

        # Merge explicit content kwargs
        for key in EMAIL_DOMAIN.pool_vocab:
            explicit = content_kwargs.get(key)
            if explicit:
                supply_map[key].extend(explicit)

        return supply_map

    def reassign_slots(
        self,
        supply_map: Dict[str, list],
        demands: Dict[str, int],
    ) -> Dict[str, list]:
        """Use TRM scoring to reassign content, passing EMAIL_DOMAIN explicitly."""
        from adapters.domain_config import EMAIL_DOMAIN
        from gchat.card_builder.slot_assignment import reassign_supply_map

        return reassign_supply_map(supply_map, demands, domain_config=EMAIL_DOMAIN)

    def render_component(self, name: str, params: Dict[str, Any]) -> Any:
        """Render an email block to MJML markup.

        Creates the appropriate Pydantic block model and calls to_mjml().
        """
        import gmail.mjml_types as mt

        block_cls = getattr(mt, name, None)
        if block_cls is None:
            logger.warning(f"Unknown email block type: {name}")
            return f"<!-- Unknown block: {name} -->"

        try:
            block = block_cls(**params)
            return block.to_mjml()
        except Exception as e:
            logger.warning(f"Failed to render {name}: {e}")
            return f"<!-- Error rendering {name}: {e} -->"

    def build(self, description: str, **kwargs: Any) -> Any:
        """Build an EmailSpec from description.

        Args:
            description: DSL or natural language description
            subject: Email subject line (default: first 80 chars of description)
            preheader: Preview text for email clients
            blocks: Optional explicit block list (bypass auto-generation)
            text: Body text content
            button_text / button_url: CTA button
            hero_title / hero_subtitle / hero_cta_text / hero_cta_url: Hero section
            image_src / image_alt: Image block
            footer_text / unsubscribe_url: Footer
            header_title / header_logo_url: Header
            spacer_height: Spacer height in px
            theme: EmailTheme override

        Returns:
            EmailSpec instance (call .to_mjml() for MJML, .render() for HTML)
        """
        import gmail.mjml_types as mt

        subject = kwargs.get("subject", description[:80])
        preheader = kwargs.get("preheader")
        theme = kwargs.get("theme")
        blocks_param = kwargs.get("blocks")

        if blocks_param:
            spec_kwargs = {"subject": subject, "blocks": blocks_param}
            if preheader:
                spec_kwargs["preheader"] = preheader
            if theme:
                spec_kwargs["theme"] = theme
            return mt.EmailSpec(**spec_kwargs)

        blocks: List = []

        # Header
        header_title = kwargs.get("header_title")
        header_logo = kwargs.get("header_logo_url")
        if header_title or header_logo:
            blocks.append(
                mt.HeaderBlock(
                    title=header_title,
                    logo_url=header_logo,
                )
            )

        # Hero section
        hero_title = kwargs.get("hero_title")
        if hero_title:
            blocks.append(
                mt.HeroBlock(
                    title=hero_title,
                    subtitle=kwargs.get("hero_subtitle"),
                    cta_text=kwargs.get("hero_cta_text"),
                    cta_url=kwargs.get("hero_cta_url"),
                )
            )

        # Main text content
        text_content = kwargs.get("text", description)
        if text_content:
            blocks.append(mt.TextBlock(text=text_content))

        # Image
        image_src = kwargs.get("image_src")
        if image_src:
            blocks.append(
                mt.ImageBlock(
                    src=image_src,
                    alt=kwargs.get("image_alt", ""),
                )
            )

        # Button CTA
        button_text = kwargs.get("button_text")
        button_url = kwargs.get("button_url")
        if button_text and button_url:
            blocks.append(mt.ButtonBlock(text=button_text, url=button_url))

        # Spacer
        spacer_height = kwargs.get("spacer_height")
        if spacer_height:
            blocks.append(mt.SpacerBlock(height_px=spacer_height))

        # Divider
        if kwargs.get("divider"):
            blocks.append(mt.DividerBlock())

        # Table
        table_headers = kwargs.get("table_headers")
        table_rows = kwargs.get("table_rows")
        if table_headers and table_rows:
            rows = [
                mt.TableRow(cells=r) if isinstance(r, list) else r for r in table_rows
            ]
            blocks.append(mt.TableBlock(headers=table_headers, rows=rows))

        # Accordion
        accordion_items = kwargs.get("accordion_items")
        if accordion_items:
            items = [
                mt.AccordionItem(**item) if isinstance(item, dict) else item
                for item in accordion_items
            ]
            blocks.append(mt.AccordionBlock(items=items))

        # Social links
        social_links = kwargs.get("social_links")
        if social_links:
            links = [
                mt.SocialLink(**link) if isinstance(link, dict) else link
                for link in social_links
            ]
            blocks.append(mt.SocialBlock(links=links))

        # Carousel
        carousel_images = kwargs.get("carousel_images")
        if carousel_images:
            images = [
                mt.CarouselImage(**img) if isinstance(img, dict) else img
                for img in carousel_images
            ]
            blocks.append(mt.CarouselBlock(images=images))

        # Footer (always last)
        footer_text = kwargs.get("footer_text")
        if footer_text:
            blocks.append(
                mt.FooterBlock(
                    text=footer_text,
                    unsubscribe_url=kwargs.get("unsubscribe_url"),
                )
            )

        spec_kwargs = {"subject": subject, "blocks": blocks}
        if preheader:
            spec_kwargs["preheader"] = preheader
        if theme:
            spec_kwargs["theme"] = theme
        return mt.EmailSpec(**spec_kwargs)
