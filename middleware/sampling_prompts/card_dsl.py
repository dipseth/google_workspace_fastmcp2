"""Card DSL validation prompt builder for send_dynamic_card."""


def get_card_validation_prompt(tool_args: dict) -> str:
    """Build expert system prompt for validating Google Chat card DSL.

    Dynamically includes DSL documentation from the card builder module.
    """
    # Fetch live DSL docs
    dsl_docs = ""
    try:
        from gchat.wrapper_api import get_dsl_documentation

        dsl_docs = get_dsl_documentation(include_examples=True, include_hierarchy=True)
    except Exception:
        dsl_docs = "(DSL documentation unavailable)"

    return f"""You are a Google Chat card DSL expert validator. Your job is to review
the card_description and card_params provided by the calling LLM and check for
semantic correctness — not just syntax, but whether the input makes sense and
follows best practices.

## DSL Reference
{dsl_docs}

## Validation Checklist
1. **Symbol usage**: Every symbol in card_description must be from the DSL reference.
   - Section = `\u00a7`, DecoratedText = `\u03b4`, ButtonList = `\u0181`, Button = `\u1d6c`,
     Grid = `\u210a`, GridItem = `\u01f5`, Carousel = `\u25e6`, CarouselCard = `\u25bc`,
     SelectionInput = `\u25b2`
2. **Hierarchy**: Buttons must be inside ButtonList (`\u0181[\u1d6c\u00d72]`), GridItems
   inside Grid, CarouselCards inside Carousel. Sections are top-level containers.
3. **card_params alignment**: Every widget in card_description must have corresponding
   content in card_params via symbol keys (`\u03b4._items`, `\u1d6c._items`, etc.).
   Count of items must match the multiplier in card_description.
4. **_shared/_items pattern**: If `_shared` is provided, its keys are merged into each
   item — avoid duplicating shared keys in individual items.
5. **Content completeness**: DecoratedText should have at least `text`; Buttons need
   `text` and either `url` or `action`.

## Response Format
Return a JSON object matching this schema:
{{
  "is_valid": bool,
  "confidence": float (0.0-1.0),
  "validated_input": {{"card_description": "...", "card_params": {{...}}}} or {{}},
  "issues": ["list of problems found"],
  "suggestions": ["list of improvements"],
  "variations": [optional alternative card_description/card_params dicts]
}}

If the input is valid, set is_valid=true, confidence near 1.0, and leave validated_input
empty. If corrections are needed, provide the corrected values in validated_input.

## Current Tool Arguments
card_description: {tool_args.get("card_description", "(not provided)")}
card_params: {tool_args.get("card_params", "(not provided)")}
"""
