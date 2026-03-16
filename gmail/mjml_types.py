"""
Email block types for MJML-based email rendering.

Pydantic block classes that ModuleWrapper can introspect. Each block
serializes to MJML markup via to_mjml(). EmailSpec is the top-level
container that renders the full MJML document.

Usage:
    from gmail.mjml_types import EmailSpec, HeroBlock, TextBlock, ButtonBlock

    spec = EmailSpec(
        subject="Welcome!",
        blocks=[
            HeroBlock(title="Hello", cta_text="Get Started", cta_url="https://..."),
            TextBlock(text="Thanks for joining."),
            ButtonBlock(text="View Dashboard", url="https://..."),
        ],
    )
    result = spec.render()
    if result.success:
        html = result.html
"""

import html
import logging
from typing import Annotated, Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Discriminator, Field, Tag, model_validator

logger = logging.getLogger(__name__)


def _safe_url(url: Optional[str]) -> str:
    """Validate URL to prevent javascript: and data: protocol injection."""
    if not url:
        return ""
    stripped = url.strip()
    lower = stripped.lower()
    if lower.startswith(("http://", "https://", "/", "#", "mailto:")):
        return html.escape(stripped, quote=True)
    # Reject javascript:, data:, vbscript:, etc.
    return ""


# =============================================================================
# THEME
# =============================================================================


class EmailTheme(BaseModel):
    """Theme settings for email rendering."""

    primary_color: str = "#2563EB"
    text_color: str = "#0f172a"
    muted_color: str = "#64748B"
    bg_color: str = "#F8FAFC"
    card_bg_color: str = "#FFFFFF"
    font_family: str = "Inter, Arial, sans-serif"
    border_color: str = "#E2E8F0"


# =============================================================================
# RENDER RESULT TYPES
# =============================================================================


class MjmlDiagnostic(BaseModel):
    """Structured diagnostic from MJML rendering."""

    level: str = "error"
    message: str = ""
    line: Optional[int] = None


class MjmlRenderOptions(BaseModel):
    """Options for MJML rendering."""

    minify: bool = False
    beautify: bool = False


class MjmlRenderResult(BaseModel):
    """Result from rendering an EmailSpec to HTML."""

    success: bool
    html: Optional[str] = None
    normalized_html: Optional[str] = None
    mjml_source: Optional[str] = None
    diagnostics: List[MjmlDiagnostic] = Field(default_factory=list)


# =============================================================================
# EMAIL BLOCKS
# =============================================================================


class EmailBlock(BaseModel):
    """Base class for all email blocks."""

    block_type: str = ""
    background_color: Optional[str] = None

    def to_mjml(self, theme: Optional[EmailTheme] = None) -> str:
        raise NotImplementedError


class HeroBlock(EmailBlock):
    """Full-width hero section with title, subtitle, and CTA button."""

    block_type: Literal["hero"] = "hero"
    title: str
    subtitle: Optional[str] = None
    cta_text: Optional[str] = None
    cta_url: Optional[str] = None
    background_image_url: Optional[str] = None
    title_color: Optional[str] = None
    subtitle_color: Optional[str] = None
    title_size: str = "28px"
    subtitle_size: str = "16px"

    def to_mjml(self, theme: Optional[EmailTheme] = None) -> str:
        theme = theme or EmailTheme()
        t_color = self.title_color or theme.text_color
        s_color = self.subtitle_color or "#334155"
        parts = []
        parts.append(
            f'<mj-text font-size="{self.title_size}" font-weight="700" '
            f'color="{t_color}" padding="0 0 8px 0">{html.escape(self.title)}</mj-text>'
        )
        if self.subtitle:
            parts.append(
                f'<mj-text font-size="{self.subtitle_size}" color="{s_color}" '
                f'padding="0 0 16px 0">{html.escape(self.subtitle)}</mj-text>'
            )
        if self.cta_text and self.cta_url:
            parts.append(
                f'<mj-button href="{_safe_url(self.cta_url)}" '
                f'padding="0 0 8px 0">{html.escape(self.cta_text)}</mj-button>'
            )
        return "\n".join(parts)


class TextBlock(EmailBlock):
    """Rich text content block."""

    block_type: Literal["text"] = "text"
    text: str
    font_size: str = "16px"
    color: Optional[str] = None
    align: str = "left"
    padding: str = "0 0 12px 0"

    def to_mjml(self, theme: Optional[EmailTheme] = None) -> str:
        theme = theme or EmailTheme()
        color = self.color or theme.text_color
        return (
            f'<mj-text font-size="{self.font_size}" color="{color}" '
            f'padding="{self.padding}">{html.escape(self.text)}</mj-text>'
        )


class ButtonBlock(EmailBlock):
    """Call-to-action button."""

    block_type: Literal["button"] = "button"
    text: str
    url: str
    background_color: Optional[str] = None
    color: str = "#ffffff"
    border_radius: str = "8px"
    align: str = "center"
    padding: str = "0 0 8px 0"

    def to_mjml(self, theme: Optional[EmailTheme] = None) -> str:
        theme = theme or EmailTheme()
        bg = self.background_color or theme.primary_color
        return (
            f'<mj-button href="{_safe_url(self.url)}" background-color="{bg}" '
            f'color="{self.color}" border-radius="{self.border_radius}" '
            f'align="{self.align}" padding="{self.padding}">{html.escape(self.text)}</mj-button>'
        )


class ImageBlock(EmailBlock):
    """Responsive image block."""

    block_type: Literal["image"] = "image"
    src: str
    alt: str = ""
    width: Optional[str] = None
    href: Optional[str] = None
    padding: str = "0 0 12px 0"

    def to_mjml(self, theme: Optional[EmailTheme] = None) -> str:
        attrs = [
            f'src="{_safe_url(self.src)}"',
            f'alt="{html.escape(self.alt, quote=True)}"',
            f'padding="{self.padding}"',
        ]
        if self.width:
            attrs.append(f'width="{self.width}"')
        if self.href:
            attrs.append(f'href="{_safe_url(self.href)}"')
        return f"<mj-image {' '.join(attrs)} />"


class Column(BaseModel):
    """Individual column within a ColumnsBlock."""

    blocks: List[EmailBlock]
    width: Optional[str] = None
    padding: str = "0"
    background_color: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def _resolve_block_types(cls, data: Any) -> Any:
        """Resolve block dicts to proper subclass instances."""
        if isinstance(data, dict) and "blocks" in data:
            resolved = []
            for b in data["blocks"]:
                if isinstance(b, dict) and "block_type" in b:
                    # Lazy lookup — _BLOCK_TYPE_MAP defined after all blocks
                    block_map = globals().get("_BLOCK_TYPE_MAP", {})
                    block_cls = block_map.get(b["block_type"])
                    if block_cls:
                        resolved.append(block_cls(**b))
                        continue
                resolved.append(b)
            data = {**data, "blocks": resolved}
        return data

    def to_mjml(self, theme: Optional[EmailTheme] = None) -> str:
        attrs = [f'padding="{self.padding}"']
        if self.width:
            attrs.append(f'width="{self.width}"')
        if self.background_color:
            attrs.append(f'background-color="{self.background_color}"')
        inner = "\n".join(b.to_mjml(theme) for b in self.blocks)
        return f"<mj-column {' '.join(attrs)}>\n{inner}\n</mj-column>"


class ColumnsBlock(EmailBlock):
    """Multi-column layout (2-4 columns)."""

    block_type: Literal["columns"] = "columns"
    columns: List[Column]
    padding: str = "0"

    def to_mjml(self, theme: Optional[EmailTheme] = None) -> str:
        cols = "\n".join(c.to_mjml(theme) for c in self.columns)
        bg = (
            f' background-color="{self.background_color}"'
            if self.background_color
            else ""
        )
        return f'<mj-section{bg} padding="{self.padding}">\n{cols}\n</mj-section>'


class SpacerBlock(EmailBlock):
    """Vertical spacing."""

    block_type: Literal["spacer"] = "spacer"
    height_px: int = 20

    def to_mjml(self, theme: Optional[EmailTheme] = None) -> str:
        return f'<mj-spacer height="{self.height_px}px" />'


class DividerBlock(EmailBlock):
    """Horizontal rule divider."""

    block_type: Literal["divider"] = "divider"
    border_color: Optional[str] = None
    padding: str = "16px 0"

    def to_mjml(self, theme: Optional[EmailTheme] = None) -> str:
        theme = theme or EmailTheme()
        color = self.border_color or theme.border_color
        return f'<mj-divider border-color="{color}" padding="{self.padding}" />'


class FooterBlock(EmailBlock):
    """Footer with optional unsubscribe link."""

    block_type: Literal["footer"] = "footer"
    text: str
    unsubscribe_url: Optional[str] = None
    font_size: str = "12px"
    color: Optional[str] = None

    def to_mjml(self, theme: Optional[EmailTheme] = None) -> str:
        theme = theme or EmailTheme()
        color = self.color or theme.muted_color
        parts = [
            f'<mj-divider border-color="{theme.border_color}" padding="16px 0" />',
            f'<mj-text font-size="{self.font_size}" color="{color}" padding="0">'
            f"{html.escape(self.text)}</mj-text>",
        ]
        if self.unsubscribe_url:
            parts.append(
                f'<mj-text font-size="{self.font_size}" color="{color}" padding="8px 0 0 0">\n'
                f'  <a href="{_safe_url(self.unsubscribe_url)}" style="color:{color}">Unsubscribe</a>\n'
                f"</mj-text>"
            )
        return "\n".join(parts)


class HeaderBlock(EmailBlock):
    """Email header with logo or title."""

    block_type: Literal["header"] = "header"
    logo_url: Optional[str] = None
    logo_alt: str = ""
    logo_width: str = "150px"
    title: Optional[str] = None
    text_color: Optional[str] = None
    padding: str = "16px 0"

    def to_mjml(self, theme: Optional[EmailTheme] = None) -> str:
        theme = theme or EmailTheme()
        bg = self.background_color or theme.card_bg_color
        color = self.text_color or theme.text_color
        parts = []
        if self.logo_url:
            parts.append(
                f'<mj-image src="{_safe_url(self.logo_url)}" alt="{html.escape(self.logo_alt, quote=True)}" '
                f'width="{self.logo_width}" padding="0" />'
            )
        if self.title:
            parts.append(
                f'<mj-text font-size="24px" font-weight="700" '
                f'color="{color}" padding="0">{html.escape(self.title)}</mj-text>'
            )
        inner = "\n".join(parts)
        return (
            f'<mj-section background-color="{bg}" padding="{self.padding}">\n'
            f"<mj-column>\n{inner}\n</mj-column>\n</mj-section>"
        )


class SocialLink(BaseModel):
    """Single social media link."""

    name: str  # "twitter", "linkedin", "github", etc.
    href: str
    icon_url: Optional[str] = None


class SocialBlock(EmailBlock):
    """Social media icon links."""

    block_type: Literal["social"] = "social"
    links: List[SocialLink]
    mode: str = "horizontal"
    padding: str = "8px 0"

    def to_mjml(self, theme: Optional[EmailTheme] = None) -> str:
        elements = []
        for link in self.links:
            if link.icon_url:
                elements.append(
                    f'<mj-social-element name="{html.escape(link.name, quote=True)}" href="{_safe_url(link.href)}" '
                    f'src="{_safe_url(link.icon_url)}" />'
                )
            else:
                elements.append(
                    f'<mj-social-element name="{html.escape(link.name, quote=True)}" href="{_safe_url(link.href)}" />'
                )
        inner = "\n".join(elements)
        return (
            f'<mj-social mode="{self.mode}" padding="{self.padding}">\n'
            f"{inner}\n</mj-social>"
        )


class TableRow(BaseModel):
    """Single row of table data."""

    cells: List[str]


class TableBlock(EmailBlock):
    """Simple data table."""

    block_type: Literal["table"] = "table"
    headers: List[str]
    rows: List[TableRow]
    padding: str = "0 0 12px 0"

    def to_mjml(self, theme: Optional[EmailTheme] = None) -> str:
        theme = theme or EmailTheme()
        header_cells = "".join(
            f'<th style="padding:8px;border-bottom:2px solid {theme.border_color};'
            f'text-align:left">{html.escape(h)}</th>'
            for h in self.headers
        )
        data_rows = []
        for row in self.rows:
            cells = "".join(
                f'<td style="padding:8px;border-bottom:1px solid {theme.border_color}">'
                f"{html.escape(c)}</td>"
                for c in row.cells
            )
            data_rows.append(f"<tr>{cells}</tr>")

        return (
            f'<mj-table padding="{self.padding}">\n'
            f"<tr>{header_cells}</tr>\n" + "\n".join(data_rows) + "\n</mj-table>"
        )


# =============================================================================
# INTERACTIVE BLOCKS
# =============================================================================


class AccordionItem(BaseModel):
    """Single expandable/collapsible item within an AccordionBlock."""

    title: str
    content: str
    title_background_color: Optional[str] = None
    title_color: Optional[str] = None
    content_background_color: Optional[str] = None


class AccordionBlock(EmailBlock):
    """Expandable/collapsible accordion sections.

    Renders via mj-accordion. Degrades gracefully in clients without
    CSS support — all sections show expanded.
    """

    block_type: Literal["accordion"] = "accordion"
    items: List[AccordionItem]
    border: str = "1px solid #E2E8F0"
    icon_position: str = "right"
    padding: str = "0 0 12px 0"
    font_family: Optional[str] = None

    def to_mjml(self, theme: Optional[EmailTheme] = None) -> str:
        theme = theme or EmailTheme()
        attrs = [
            f'border="{self.border}"',
            f'icon-position="{self.icon_position}"',
            f'padding="{self.padding}"',
        ]
        if self.font_family:
            attrs.append(f'font-family="{self.font_family}"')

        elements = []
        for item in self.items:
            title_attrs = []
            if item.title_background_color:
                title_attrs.append(f'background-color="{item.title_background_color}"')
            if item.title_color:
                title_attrs.append(f'color="{item.title_color}"')

            text_attrs = []
            if item.content_background_color:
                text_attrs.append(f'background-color="{item.content_background_color}"')

            elements.append(
                f"<mj-accordion-element>\n"
                f"  <mj-accordion-title {' '.join(title_attrs)}>"
                f"{html.escape(item.title)}</mj-accordion-title>\n"
                f"  <mj-accordion-text {' '.join(text_attrs)}>"
                f"{html.escape(item.content)}</mj-accordion-text>\n"
                f"</mj-accordion-element>"
            )

        inner = "\n".join(elements)
        return f"<mj-accordion {' '.join(attrs)}>\n{inner}\n</mj-accordion>"


class CarouselImage(BaseModel):
    """Single image within a CarouselBlock."""

    src: str
    alt: str = ""
    href: Optional[str] = None
    thumbnails_src: Optional[str] = None
    title: Optional[str] = None


class CarouselBlock(EmailBlock):
    """Image carousel with navigation arrows and thumbnails.

    Renders via mj-carousel. Best support in Apple Mail and iOS;
    falls back to first image in Gmail/Outlook.
    """

    block_type: Literal["carousel"] = "carousel"
    images: List[CarouselImage]
    thumbnails: str = "visible"
    border_radius: str = "6px"
    icon_width: str = "44px"
    padding: str = "0 0 12px 0"

    def to_mjml(self, theme: Optional[EmailTheme] = None) -> str:
        attrs = [
            f'thumbnails="{self.thumbnails}"',
            f'border-radius="{self.border_radius}"',
            f'icon-width="{self.icon_width}"',
            f'padding="{self.padding}"',
        ]

        img_elements = []
        for img in self.images:
            img_attrs = [
                f'src="{_safe_url(img.src)}"',
                f'alt="{html.escape(img.alt, quote=True)}"',
            ]
            if img.href:
                img_attrs.append(f'href="{_safe_url(img.href)}"')
            if img.thumbnails_src:
                img_attrs.append(f'thumbnails-src="{_safe_url(img.thumbnails_src)}"')
            if img.title:
                img_attrs.append(f'title="{html.escape(img.title, quote=True)}"')
            img_elements.append(f"<mj-carousel-image {' '.join(img_attrs)} />")

        inner = "\n".join(img_elements)
        return f"<mj-carousel {' '.join(attrs)}>\n{inner}\n</mj-carousel>"


# =============================================================================
# BLOCK TYPE DISCRIMINATOR
# =============================================================================

_BLOCK_TYPE_MAP = {
    "hero": HeroBlock,
    "text": TextBlock,
    "button": ButtonBlock,
    "image": ImageBlock,
    "columns": ColumnsBlock,
    "spacer": SpacerBlock,
    "divider": DividerBlock,
    "footer": FooterBlock,
    "header": HeaderBlock,
    "social": SocialBlock,
    "table": TableBlock,
    "accordion": AccordionBlock,
    "carousel": CarouselBlock,
}


def _discriminate_block(v: Any) -> str:
    """Discriminator function for EmailBlock union."""
    if isinstance(v, dict):
        return v.get("block_type", "")
    return getattr(v, "block_type", "")


AnyEmailBlock = Annotated[
    Union[
        Annotated[HeroBlock, Tag("hero")],
        Annotated[TextBlock, Tag("text")],
        Annotated[ButtonBlock, Tag("button")],
        Annotated[ImageBlock, Tag("image")],
        Annotated[ColumnsBlock, Tag("columns")],
        Annotated[SpacerBlock, Tag("spacer")],
        Annotated[DividerBlock, Tag("divider")],
        Annotated[FooterBlock, Tag("footer")],
        Annotated[HeaderBlock, Tag("header")],
        Annotated[SocialBlock, Tag("social")],
        Annotated[TableBlock, Tag("table")],
        Annotated[AccordionBlock, Tag("accordion")],
        Annotated[CarouselBlock, Tag("carousel")],
    ],
    Discriminator(_discriminate_block),
]


# =============================================================================
# EMAIL SPEC (top-level container)
# =============================================================================


class EmailSpec(BaseModel):
    """Top-level email specification — analogous to Card in gchat.

    Contains an ordered list of EmailBlocks that are rendered to MJML,
    then compiled to responsive HTML via mjml_to_html().
    """

    subject: str
    preheader: Optional[str] = None
    blocks: List[AnyEmailBlock]
    theme: EmailTheme = Field(default_factory=EmailTheme)

    def to_mjml(self) -> str:
        """Produce full MJML document string."""
        theme = self.theme
        parts = []

        # Head with global attributes
        parts.append("<mjml>")
        parts.append("<mj-head>")
        parts.append("<mj-attributes>")
        parts.append(f'<mj-all font-family="{theme.font_family}" />')
        parts.append(
            f'<mj-button background-color="{theme.primary_color}" '
            f'color="#ffffff" border-radius="8px" />'
        )
        parts.append("</mj-attributes>")
        parts.append("</mj-head>")

        # Body
        parts.append(f'<mj-body background-color="{theme.bg_color}">')

        # Preheader (hidden text for email preview)
        if self.preheader:
            parts.append('<mj-section padding="0">')
            parts.append("<mj-column>")
            parts.append(
                f'<mj-text font-size="1px" color="{theme.bg_color}" '
                f'height="0" line-height="1px" padding="0">'
                f"{html.escape(self.preheader)}</mj-text>"
            )
            parts.append("</mj-column>")
            parts.append("</mj-section>")

        # Content wrapper
        parts.append('<mj-wrapper padding="0">')

        # Render blocks — each block either:
        # 1. Renders its own <mj-section> (ColumnsBlock, HeaderBlock)
        # 2. Gets its own <mj-section> if it has a custom background_color
        # 3. Groups with adjacent blocks into a shared <mj-section>
        inline_blocks: List[EmailBlock] = []

        def _flush_inline(inline: List[EmailBlock]) -> None:
            if not inline:
                return
            parts.append(
                f'<mj-section background-color="{theme.card_bg_color}" padding="24px">'
            )
            parts.append("<mj-column>")
            for block in inline:
                parts.append(block.to_mjml(theme))
            parts.append("</mj-column>")
            parts.append("</mj-section>")

        for block in self.blocks:
            if isinstance(block, (ColumnsBlock, HeaderBlock)):
                _flush_inline(inline_blocks)
                inline_blocks = []
                parts.append(block.to_mjml(theme))
            elif block.background_color and not isinstance(block, ButtonBlock):
                # Block has a custom section background — give it its own section
                # (ButtonBlock.background_color is the button element color, not section)
                _flush_inline(inline_blocks)
                inline_blocks = []
                bg = block.background_color
                parts.append(f'<mj-section background-color="{bg}" padding="24px">')
                parts.append("<mj-column>")
                parts.append(block.to_mjml(theme))
                parts.append("</mj-column>")
                parts.append("</mj-section>")
            else:
                inline_blocks.append(block)

        _flush_inline(inline_blocks)

        parts.append("</mj-wrapper>")
        parts.append("</mj-body>")
        parts.append("</mjml>")

        return "\n".join(parts)

    def render(self, options: Optional[MjmlRenderOptions] = None) -> MjmlRenderResult:
        """Render to HTML via mjml_to_html. Delegates to mjml_wrapper."""
        from gmail.mjml_wrapper import render_email_spec

        return render_email_spec(self, options)
