"""
Public API for email wrapper — symbols, DSL docs, and DSL parsing.

Mirrors the pattern from gchat/wrapper_api.py but simplified for email blocks.

Usage:
    from gmail.email_wrapper_api import get_email_symbols, parse_email_dsl
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

import gmail.email_wrapper_setup as _setup
from config.enhanced_logging import setup_logger

logger = setup_logger()


# =============================================================================
# PYDANTIC RESULT TYPES
# =============================================================================


class EmailDSLResult(BaseModel):
    """Structured email DSL generation result.

    Used by DSL recovery to return corrected DSL. Fields must contain ONLY
    the corrected values — no explanations, commentary, or reasoning.
    """

    email_description: str = Field(
        description=(
            "The corrected DSL notation followed by the email subject. "
            "Must start with the DSL expression (e.g. 'ε[ħ, τ×2, Ƀ]') "
            "followed by the original subject text. "
            "Do NOT include explanations or commentary — ONLY the DSL and subject."
        ),
    )
    email_params: dict = Field(
        description=(
            "Block content keyed by DSL symbol or class name. "
            "Preserve the original content from the user's request."
        ),
    )


# =============================================================================
# SYMBOL GENERATION
# =============================================================================


def get_email_symbols(force_regenerate: bool = False) -> Dict[str, str]:
    """
    Get the symbol table for email block components.

    Returns cached symbols from the ModuleWrapper singleton.

    Args:
        force_regenerate: If True, reinitialize wrapper to regenerate symbols

    Returns:
        Dict mapping component names to symbols (e.g., {"HeroBlock": "ħ"})
    """
    if force_regenerate:
        wrapper = _setup.get_email_wrapper(force_reinitialize=True)
    else:
        wrapper = _setup.get_email_wrapper()

    return wrapper.symbol_mapping


# =============================================================================
# AUTO-GENERATED DSL DOCUMENTATION
# =============================================================================


def get_email_dsl_documentation(include_examples: bool = True) -> str:
    """
    Auto-generate compact DSL documentation for email MCP tool descriptions.

    Organizes symbols by role: container, layout, content, structure, chrome.

    Args:
        include_examples: Whether to include usage examples

    Returns:
        Markdown-formatted documentation string
    """
    symbols = get_email_symbols()

    # Organize by role
    CATEGORIES = {
        "Container": ["EmailSpec"],
        "Layout": ["ColumnsBlock", "Column"],
        "Content": ["HeroBlock", "TextBlock", "ButtonBlock", "ImageBlock"],
        "Structure": ["SpacerBlock", "DividerBlock"],
        "Chrome": [
            "HeaderBlock",
            "FooterBlock",
            "SocialBlock",
            "TableBlock",
        ],
        "Interactive": ["AccordionBlock", "CarouselBlock"],
    }

    lines = ["## Email DSL Quick Reference\n"]

    # Core symbols organized by category
    lines.append("### Symbols")
    for category, components in CATEGORIES.items():
        mappings = [
            f"{symbols.get(c, '?')}={c}" for c in components if c in symbols
        ]
        if mappings:
            lines.append(f"**{category}:** {', '.join(mappings)}")

    # Containment rules
    spec_sym = symbols["EmailSpec"]
    cols_sym = symbols["ColumnsBlock"]
    col_sym = symbols["Column"]

    lines.append("\n### Containment Rules")
    lines.append(
        f"- {spec_sym} EmailSpec → all block types (top-level container)"
    )
    lines.append(f"- {cols_sym} ColumnsBlock → {col_sym} Column")
    lines.append(
        f"- {col_sym} Column → content blocks (TextBlock, ButtonBlock, ImageBlock)"
    )

    if include_examples:
        hero_sym = symbols["HeroBlock"]
        text_sym = symbols["TextBlock"]
        btn_sym = symbols["ButtonBlock"]
        img_sym = symbols["ImageBlock"]
        spacer_sym = symbols["SpacerBlock"]
        divider_sym = symbols["DividerBlock"]
        header_sym = symbols["HeaderBlock"]
        footer_sym = symbols["FooterBlock"]

        lines.append("\n### Examples")
        lines.append(
            f"- `{spec_sym}[{hero_sym}, {text_sym}]` = hero + text email"
        )
        lines.append(
            f"- `{spec_sym}[{hero_sym}, {text_sym}x2, {btn_sym}]` = hero + 2 text blocks + button"
        )
        lines.append(
            f"- `{spec_sym}[{header_sym}, {text_sym}, {divider_sym}, {footer_sym}]` = "
            "header + text + divider + footer"
        )
        lines.append(
            f"- `{spec_sym}[{hero_sym}, {cols_sym}[{col_sym}x2], {btn_sym}]` = "
            "hero + 2-column layout + button"
        )
        lines.append(
            "- Syntax: `xN` = multiplier, `[]` = children, `,` = siblings"
        )

    return "\n".join(lines)


def get_email_dsl_field_description() -> str:
    """
    Get a compact field description for the email_description parameter.

    Returns a single-line description suitable for Field(description=...).
    """
    symbols = get_email_symbols()

    key_mappings = []
    key_components = [
        "EmailSpec",
        "HeroBlock",
        "TextBlock",
        "ButtonBlock",
        "ImageBlock",
        "ColumnsBlock",
        "Column",
        "HeaderBlock",
        "FooterBlock",
        "AccordionBlock",
        "CarouselBlock",
    ]

    for comp in key_components:
        if comp in symbols:
            key_mappings.append(f"{symbols[comp]}={comp}")

    return (
        f"DSL structure using symbols. Symbols: {', '.join(key_mappings)}."
    )


def get_email_tool_examples(
    max_examples: int = 5,
) -> List[Dict[str, Any]]:
    """
    Generate dynamic tool examples using symbols.

    Args:
        max_examples: Maximum number of examples to generate

    Returns:
        List of example dicts with description, email_description, email_params
    """
    symbols = get_email_symbols()

    spec = symbols["EmailSpec"]
    hero = symbols["HeroBlock"]
    text = symbols["TextBlock"]
    btn = symbols["ButtonBlock"]
    img = symbols["ImageBlock"]
    header = symbols["HeaderBlock"]
    footer = symbols["FooterBlock"]
    divider = symbols["DividerBlock"]
    cols = symbols["ColumnsBlock"]
    col = symbols["Column"]
    accordion = symbols["AccordionBlock"]
    carousel = symbols["CarouselBlock"]

    all_examples = [
        {
            "description": "Simple welcome email",
            "email_description": f"{spec}[{hero}, {text}] Welcome email",
            "email_params": {
                hero: {
                    "title": "Welcome!",
                    "subtitle": "Thanks for joining",
                },
                text: {
                    "_items": [{"text": "We're glad to have you."}]
                },
            },
        },
        {
            "description": "Newsletter with CTA",
            "email_description": f"{spec}[{hero}, {text}x2, {btn}]",
            "email_params": {
                hero: {
                    "title": "Monthly Update",
                    "subtitle": "March 2026",
                },
                text: {
                    "_items": [
                        {"text": "Here's what happened this month."},
                        {"text": "Check out our latest features."},
                    ]
                },
                btn: {
                    "_items": [
                        {
                            "text": "Read More",
                            "url": "https://example.com",
                        }
                    ]
                },
            },
        },
        {
            "description": "Branded email with header/footer",
            "email_description": f"{spec}[{header}, {text}, {divider}, {footer}]",
            "email_params": {
                header: {"title": "Acme Corp"},
                text: {
                    "_items": [{"text": "Important announcement."}]
                },
                footer: {
                    "_items": [
                        {
                            "text": "2026 Acme Corp. All rights reserved."
                        }
                    ]
                },
            },
        },
        {
            "description": "Two-column comparison",
            "email_description": f"{spec}[{hero}, {cols}[{col}x2], {btn}]",
            "email_params": {
                hero: {"title": "Compare Plans"},
                col: {
                    "_items": [
                        {
                            "blocks": [
                                {
                                    "block_type": "text",
                                    "text": "Basic: $10/mo",
                                }
                            ]
                        },
                        {
                            "blocks": [
                                {
                                    "block_type": "text",
                                    "text": "Pro: $25/mo",
                                }
                            ]
                        },
                    ]
                },
                btn: {
                    "_items": [
                        {
                            "text": "Choose Plan",
                            "url": "https://example.com/plans",
                        }
                    ]
                },
            },
        },
        {
            "description": "Image + text email",
            "email_description": f"{spec}[{img}, {text}, {btn}]",
            "email_params": {
                img: {
                    "_items": [
                        {
                            "src": "https://picsum.photos/600/300",
                            "alt": "Banner",
                        }
                    ]
                },
                text: {
                    "_items": [
                        {"text": "Check out our new product."}
                    ]
                },
                btn: {
                    "_items": [
                        {
                            "text": "Shop Now",
                            "url": "https://example.com/shop",
                        }
                    ]
                },
            },
        },
        {
            "description": "FAQ with accordion",
            "email_description": f"{spec}[{hero}, {accordion}, {btn}]",
            "email_params": {
                hero: {"title": "FAQ"},
                accordion: {
                    "_items": [
                        {
                            "items": [
                                {
                                    "title": "How does it work?",
                                    "content": "It just works.",
                                },
                                {
                                    "title": "Is it free?",
                                    "content": "Yes, completely free.",
                                },
                            ]
                        }
                    ]
                },
                btn: {
                    "_items": [
                        {
                            "text": "Contact Us",
                            "url": "https://example.com/contact",
                        }
                    ]
                },
            },
        },
        {
            "description": "Image carousel showcase",
            "email_description": f"{spec}[{hero}, {carousel}]",
            "email_params": {
                hero: {"title": "Gallery"},
                carousel: {
                    "_items": [
                        {
                            "images": [
                                {
                                    "src": "https://picsum.photos/600/300?1",
                                    "alt": "Photo 1",
                                },
                                {
                                    "src": "https://picsum.photos/600/300?2",
                                    "alt": "Photo 2",
                                },
                                {
                                    "src": "https://picsum.photos/600/300?3",
                                    "alt": "Photo 3",
                                },
                            ]
                        }
                    ]
                },
            },
        },
    ]

    return all_examples[:max_examples]


# =============================================================================
# DSL PARSING HELPERS
# =============================================================================


def get_email_dsl_parser():
    """
    Get a configured DSL parser for email block components.

    Returns:
        DSLParser instance configured with email symbols and relationships
    """
    from adapters.module_wrapper.dsl_parser import DSLParser

    symbols = get_email_symbols()
    relationships = _get_email_relationships()

    return DSLParser(
        symbol_mapping=symbols,
        reverse_mapping={v: k for k, v in symbols.items()},
        relationships=relationships,
    )


def _get_email_relationships() -> Dict[str, List[str]]:
    """Get component containment relationships for email blocks."""
    return {
        "EmailSpec": list(_setup.EMAIL_WIDGET_TYPES),
        "ColumnsBlock": ["Column"],
        "Column": [
            "TextBlock",
            "ButtonBlock",
            "ImageBlock",
            "SpacerBlock",
            "DividerBlock",
        ],
        "AccordionBlock": [],  # Leaf — items come from params, not DSL children
        "CarouselBlock": [],  # Leaf — images come from params, not DSL children
    }


def parse_email_dsl(dsl_string: str):
    """
    Parse an email DSL string.

    Args:
        dsl_string: DSL notation like "ε[ħ, τ×2, Ƀ]"

    Returns:
        DSLParseResult with component_counts, root_nodes, etc.

    Example:
        result = parse_email_dsl("ε[ħ, τ×2, Ƀ]")
        print(result.component_counts)
        # {'EmailSpec': 1, 'HeroBlock': 1, 'TextBlock': 2, 'ButtonBlock': 1}
    """
    parser = get_email_dsl_parser()
    return parser.parse(dsl_string)


def extract_email_dsl_from_description(
    description: str,
) -> Optional[str]:
    """
    Extract DSL notation from a description string.

    Args:
        description: Text that may contain DSL notation
                    e.g., "ε[ħ, τ×2, Ƀ] Welcome newsletter"

    Returns:
        DSL string if found, None otherwise
    """
    if not description:
        return None

    parser = get_email_dsl_parser()
    return parser.extract_dsl_from_text(description)
