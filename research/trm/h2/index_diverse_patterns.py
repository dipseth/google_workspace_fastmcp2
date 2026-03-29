"""Index diverse card patterns into Qdrant for better search coverage.

Generates systematic card structures covering the full combinatorial space
of component counts (1-8 buttons, 1-6 grid items, etc.) and stores them
as positive instance_patterns in the production Qdrant collection.

This ensures the learned scorer has patterns to find when users search
for "card with 5 buttons" or "grid with 4 items".

Usage:
    PYTHONPATH=. uv run python research/trm/h2/index_diverse_patterns.py
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

# Project root + SSL fix
_project_root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(_project_root))
try:
    import certifi
    if not os.environ.get("SSL_CERT_FILE"):
        os.environ["SSL_CERT_FILE"] = certifi.where()
except ImportError:
    pass

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Systematic DSL templates covering the combinatorial space
# ---------------------------------------------------------------------------

def build_diverse_recipes():
    """Build recipes that cover all useful multiplier combinations."""
    recipes = []

    # --- Button variations: 1-8 buttons ---
    for n in range(1, 9):
        mult = f"×{n}" if n > 1 else ""
        recipes.append({
            "dsl": f"§[δ, Ƀ[ᵬ{mult}]]",
            "description": f"Card with text and {n} button{'s' if n > 1 else ''}",
            "components": ["Section", "DecoratedText", "ButtonList"] + ["Button"] * n,
        })

    # --- Decorated text variations: 1-6 items ---
    for n in range(1, 7):
        mult = f"×{n}" if n > 1 else ""
        recipes.append({
            "dsl": f"§[δ{mult}]",
            "description": f"Card with {n} text item{'s' if n > 1 else ''}",
            "components": ["Section"] + ["DecoratedText"] * n,
        })

    # --- Text + buttons combos ---
    for nt in range(1, 5):
        for nb in range(1, 6):
            tmult = f"×{nt}" if nt > 1 else ""
            bmult = f"×{nb}" if nb > 1 else ""
            recipes.append({
                "dsl": f"§[δ{tmult}, Ƀ[ᵬ{bmult}]]",
                "description": f"Card with {nt} text{'s' if nt > 1 else ''} and {nb} button{'s' if nb > 1 else ''}",
                "components": ["Section"] + ["DecoratedText"] * nt + ["ButtonList"] + ["Button"] * nb,
            })

    # --- Grid variations: 1-8 items ---
    for n in range(1, 9):
        mult = f"×{n}" if n > 1 else ""
        recipes.append({
            "dsl": f"§[ℊ[ǵ{mult}]]",
            "description": f"Grid with {n} item{'s' if n > 1 else ''}",
            "components": ["Section", "Grid"] + ["GridItem"] * n,
        })

    # --- Carousel variations: 1-5 cards ---
    for n in range(1, 6):
        mult = f"×{n}" if n > 1 else ""
        recipes.append({
            "dsl": f"◦[▼{mult}]",
            "description": f"Carousel with {n} card{'s' if n > 1 else ''}",
            "components": ["Carousel"] + ["CarouselCard"] * n,
        })

    # --- Chip variations: 1-6 chips ---
    for n in range(1, 7):
        mult = f"×{n}" if n > 1 else ""
        recipes.append({
            "dsl": f"§[δ, ȼ[ℂ{mult}]]",
            "description": f"Card with text and {n} chip{'s' if n > 1 else ''}",
            "components": ["Section", "DecoratedText", "ChipList"] + ["Chip"] * n,
        })

    # --- Column variations: 2-4 columns ---
    for n in range(2, 5):
        recipes.append({
            "dsl": f"§[¢[ç×{n}]]",
            "description": f"Card with {n}-column layout",
            "components": ["Section", "Columns"] + ["Column"] * n,
        })

    # --- Rich combos: text + divider + buttons ---
    for nb in range(1, 6):
        bmult = f"×{nb}" if nb > 1 else ""
        recipes.append({
            "dsl": f"§[δ, Đ, Ƀ[ᵬ{bmult}]]",
            "description": f"Card with text, divider, and {nb} button{'s' if nb > 1 else ''}",
            "components": ["Section", "DecoratedText", "Divider", "ButtonList"] + ["Button"] * nb,
        })

    # --- Image cards ---
    recipes.append({
        "dsl": "§[ǐ, δ, Ƀ[ᵬ]]",
        "description": "Image card with text and button",
        "components": ["Section", "Image", "DecoratedText", "ButtonList", "Button"],
    })
    recipes.append({
        "dsl": "§[ǐ, δ×2, Ƀ[ᵬ×2]]",
        "description": "Image card with 2 texts and 2 buttons",
        "components": ["Section", "Image", "DecoratedText", "DecoratedText", "ButtonList", "Button", "Button"],
    })
    for n in range(1, 4):
        bmult = f"×{n}" if n > 1 else ""
        recipes.append({
            "dsl": f"§[ǐ, δ, Ƀ[ᵬ{bmult}]]",
            "description": f"Hero image card with text and {n} button{'s' if n > 1 else ''}",
            "components": ["Section", "Image", "DecoratedText", "ButtonList"] + ["Button"] * n,
        })

    # --- Multi-section cards ---
    recipes.append({
        "dsl": "§[δ×3] | §[Ƀ[ᵬ×2]]",
        "description": "Two sections: 3 texts then 2 buttons",
        "components": ["Section", "DecoratedText", "DecoratedText", "DecoratedText", "Section", "ButtonList", "Button", "Button"],
    })
    recipes.append({
        "dsl": "§[δ×2, Đ, Ƀ[ᵬ×3]]",
        "description": "Status dashboard with 2 indicators, divider, and 3 actions",
        "components": ["Section", "DecoratedText", "DecoratedText", "Divider", "ButtonList", "Button", "Button", "Button"],
    })

    # --- Form-like cards ---
    recipes.append({
        "dsl": "§[τ, ▲, Ƀ[ᵬ×2]]",
        "description": "Form with text input, selection, and submit/cancel buttons",
        "components": ["Section", "TextInput", "SelectionInput", "ButtonList", "Button", "Button"],
    })
    recipes.append({
        "dsl": "§[τ×2, Ƀ[ᵬ]]",
        "description": "Form with 2 text inputs and a submit button",
        "components": ["Section", "TextInput", "TextInput", "ButtonList", "Button"],
    })

    # --- Specific user scenarios ---
    for n in [3, 4, 5, 6]:
        recipes.append({
            "dsl": f"§[δ, Ƀ[ᵬ×{n}]]",
            "description": f"Status dashboard with {n} action buttons",
            "components": ["Section", "DecoratedText", "ButtonList"] + ["Button"] * n,
        })

    # Deduplicate by DSL
    seen = set()
    unique = []
    for r in recipes:
        if r["dsl"] not in seen:
            seen.add(r["dsl"])
            unique.append(r)

    return unique


def index_patterns():
    """Generate and index all diverse patterns into Qdrant."""
    # Force wrapper initialization
    from gchat.card_framework_wrapper import get_card_framework_wrapper
    from gchat.feedback_loop import get_feedback_loop
    wrapper = get_card_framework_wrapper()
    logger.info(f"Wrapper ready")

    feedback_loop = get_feedback_loop()
    recipes = build_diverse_recipes()
    logger.info(f"Built {len(recipes)} diverse recipes")

    stored = 0
    skipped = 0

    for i, recipe in enumerate(recipes):
        dsl = recipe["dsl"]
        desc = recipe["description"]
        components = recipe["components"]

        try:
            component_paths = [
                f"card_framework.v2.{c}" if "." not in c else c
                for c in components
            ]

            # Store DSL in both structure_description and card_description
            # so the search can extract it from multiple fields
            rich_desc = f"{desc} — {dsl}"

            point_id = feedback_loop.store_instance_pattern(
                card_description=rich_desc,
                component_paths=component_paths,
                instance_params={
                    "dsl": dsl,
                    "components": components,
                },
                content_feedback="positive",
                form_feedback="positive",
                user_email="diverse-patterns@system.local",
                card_id=f"diverse-{i:03d}",
                structure_description=f"{dsl} — {desc}",
                pattern_type="content",
            )

            if point_id:
                stored += 1
            else:
                skipped += 1

        except Exception as e:
            logger.warning(f"Failed to store '{dsl}': {e}")
            skipped += 1

        if (i + 1) % 25 == 0:
            logger.info(f"Progress: {i + 1}/{len(recipes)} ({stored} stored, {skipped} skipped)")

    logger.info(f"\nIndexing complete: {stored} stored, {skipped} skipped out of {len(recipes)} recipes")

    # Show coverage summary
    button_counts = set()
    grid_counts = set()
    text_counts = set()
    for r in recipes:
        nb = r["components"].count("Button")
        ng = r["components"].count("GridItem")
        nt = r["components"].count("DecoratedText")
        if nb: button_counts.add(nb)
        if ng: grid_counts.add(ng)
        if nt: text_counts.add(nt)

    logger.info(f"\nCoverage:")
    logger.info(f"  Button counts: {sorted(button_counts)}")
    logger.info(f"  GridItem counts: {sorted(grid_counts)}")
    logger.info(f"  DecoratedText counts: {sorted(text_counts)}")


if __name__ == "__main__":
    index_patterns()
