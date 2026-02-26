"""
DAG warm-start recipes and generation for card_framework.

Self-contained leaf module — all dependencies are lazy imports
in the function body to avoid circular imports.
"""

import logging

from config.enhanced_logging import setup_logger

logger = setup_logger(__name__)

# Diverse structure recipes for DAG warm-start.
# Each recipe generates a different card structure pattern.
_DAG_WARMSTART_RECIPES = [
    # Basic widget patterns
    {"root": "Section", "required": ["DecoratedText"], "desc": "Simple text card"},
    {
        "root": "Section",
        "required": ["DecoratedText", "ButtonList"],
        "desc": "Text with action buttons",
    },
    {"root": "Section", "required": ["Grid"], "desc": "Grid layout card"},
    {"root": "Section", "required": ["Image"], "desc": "Card with image"},
    {
        "root": "Section",
        "required": ["TextParagraph", "ButtonList"],
        "desc": "Paragraph with buttons",
    },
    {
        "root": "Section",
        "required": ["DecoratedText", "ChipList"],
        "desc": "Text with chip filters",
    },
    {"root": "Section", "required": ["Columns"], "desc": "Multi-column layout"},
    {
        "root": "Section",
        "required": ["SelectionInput"],
        "desc": "Form with selection input",
    },
    {"root": "Section", "required": ["TextInput"], "desc": "Form with text input"},
    {
        "root": "Section",
        "required": ["DecoratedText", "Image", "ButtonList"],
        "desc": "Rich content card",
    },
    # Carousel patterns
    {"root": "Carousel", "required": [], "desc": "Carousel of cards"},
]


def _warm_start_with_dag_patterns(wrapper, count_per_recipe: int = 2) -> int:
    """
    Generate DAG-based instance patterns and store them in the collection.

    Uses DAGStructureGenerator to create random but valid card structures,
    then stores them via FeedbackLoop.store_instance_pattern() as positive
    instance_patterns for warm-starting the search/feedback system.

    Args:
        wrapper: The initialized ModuleWrapper for card_framework
        count_per_recipe: Number of random structures per recipe

    Returns:
        Number of patterns stored
    """
    from gchat.feedback_loop import get_feedback_loop
    from gchat.testing.dag_structure_generator import DAGStructureGenerator

    logger.info(
        f"🌱 DAG warm-start: generating {len(_DAG_WARMSTART_RECIPES)} recipes "
        f"× {count_per_recipe} variations..."
    )

    try:
        gen = DAGStructureGenerator()
    except Exception as e:
        logger.warning(f"⚠️ Could not create DAGStructureGenerator: {e}")
        return 0

    feedback_loop = get_feedback_loop()
    stored = 0

    for recipe in _DAG_WARMSTART_RECIPES:
        root = recipe["root"]
        required = recipe.get("required", [])
        desc = recipe["desc"]

        for i in range(count_per_recipe):
            try:
                structure = gen.generate_random_structure(
                    root=root,
                    required_components=required if required else None,
                )

                if not structure.is_valid:
                    logger.debug(
                        f"   Skipping invalid structure: {structure.validation_issues}"
                    )
                    continue

                # Build component paths from the generated structure
                component_paths = [
                    f"card_framework.v2.{comp}" if "." not in comp else comp
                    for comp in structure.components
                ]

                # Build a natural description
                card_description = (
                    f"{desc} with {', '.join(structure.components[:4])}"
                    f"{' and more' if len(structure.components) > 4 else ''}"
                )

                point_id = feedback_loop.store_instance_pattern(
                    card_description=card_description,
                    component_paths=component_paths,
                    instance_params={
                        "dsl": structure.dsl,
                        "components": structure.components,
                        "depth": structure.depth,
                    },
                    content_feedback="positive",
                    form_feedback="positive",
                    user_email="dag-warmstart@system.local",
                    card_id=f"dag-warmstart-{root.lower()}-{i}",
                    structure_description=f"DSL: {structure.dsl}",
                    pattern_type="content",
                )

                if point_id:
                    stored += 1

            except Exception as e:
                logger.debug(f"   Error generating {desc} variant {i}: {e}")
                continue

    logger.info(f"🌱 DAG warm-start complete: {stored} patterns stored")
    return stored
