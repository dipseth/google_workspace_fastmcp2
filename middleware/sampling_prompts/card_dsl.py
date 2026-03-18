"""Card DSL validation and draft variations prompt builders for send_dynamic_card."""

from typing import Any, Dict, List


def _get_symbols() -> Dict[str, str]:
    """Load symbols dynamically from SymbolGenerator — never hardcode."""
    try:
        from gchat.wrapper_api import get_gchat_symbols

        return get_gchat_symbols()
    except Exception:
        return {}


def get_card_validation_prompt(tool_args: dict) -> str:
    """Build expert system prompt for validating Google Chat card DSL.

    Dynamically includes DSL documentation and symbols from the card builder module.
    """
    # Fetch live DSL docs
    dsl_docs = ""
    try:
        from gchat.wrapper_api import get_dsl_documentation

        dsl_docs = get_dsl_documentation(include_examples=True, include_hierarchy=True)
    except Exception:
        dsl_docs = "(DSL documentation unavailable)"

    # Load symbols dynamically
    sym = _get_symbols()
    section = sym.get("Section", "Section")
    dtext = sym.get("DecoratedText", "DecoratedText")
    btnlist = sym.get("ButtonList", "ButtonList")
    btn = sym.get("Button", "Button")
    grid = sym.get("Grid", "Grid")
    gitem = sym.get("GridItem", "GridItem")
    carousel = sym.get("Carousel", "Carousel")
    ccard = sym.get("CarouselCard", "CarouselCard")
    selinput = sym.get("SelectionInput", "SelectionInput")

    return f"""You are a Google Chat card DSL expert validator. Your job is to review
the card_description and card_params provided by the calling LLM and check for
semantic correctness — not just syntax, but whether the input makes sense and
follows best practices.

## DSL Reference
{dsl_docs}

## Validation Checklist
1. **Symbol usage**: Every symbol in card_description must be from the DSL reference.
   - Section = `{section}`, DecoratedText = `{dtext}`, ButtonList = `{btnlist}`, Button = `{btn}`,
     Grid = `{grid}`, GridItem = `{gitem}`, Carousel = `{carousel}`, CarouselCard = `{ccard}`,
     SelectionInput = `{selinput}`
2. **Hierarchy**: Buttons must be inside ButtonList (`{btnlist}[{btn}\u00d72]`), GridItems
   inside Grid, CarouselCards inside Carousel. Sections are top-level containers.
3. **card_params alignment**: Every widget in card_description must have corresponding
   content in card_params via symbol keys (`{dtext}._items`, `{btn}._items`, etc.).
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


# ============================================================================
# AGENT TOOL WRAPPERS — callable tools for the draft variations sampling agent
# ============================================================================


def agent_validate_dsl(dsl_string: str) -> dict:
    """Validate a DSL structure string.

    Returns dict with is_valid (bool), issues (list of strings),
    and component_counts (dict of component name to count).
    """
    from gchat.wrapper_api import parse_dsl

    result = parse_dsl(dsl_string)
    return {
        "is_valid": result.is_valid,
        "issues": result.issues,
        "component_counts": result.component_counts,
    }


def agent_search_patterns(description: str, limit: int = 5) -> dict:
    """Search historical card patterns matching a description.

    Returns dict with has_dsl, dsl, patterns (list of matching DSL patterns
    with component_paths and instance_params), and classes.
    """
    from gchat.wrapper_api import search_patterns_for_card

    return search_patterns_for_card(description, limit=limit)


def agent_get_relationships() -> dict:
    """Get valid parent-child component relationships for DSL hierarchy.

    Returns dict mapping parent component names to lists of valid child names.
    """
    from gchat.wrapper_api import get_component_relationships_for_dsl

    return get_component_relationships_for_dsl()


def agent_generate_random_structure(required_components: str = "") -> dict:
    """Generate a random valid card structure using the DAG containment rules.

    Args:
        required_components: Comma-separated component names that must appear
            (e.g. "DecoratedText,ButtonList"). Empty string for no requirements.

    Returns dict with dsl (valid DSL string), components (list of component names),
    is_valid (bool), and depth (int).
    """
    from gchat.testing.dag_structure_generator import DAGStructureGenerator

    gen = DAGStructureGenerator()
    required = (
        [c.strip() for c in required_components.split(",") if c.strip()]
        if required_components
        else None
    )
    structure = gen.generate_random_structure(
        root="Section", required_components=required
    )
    return {
        "dsl": structure.dsl,
        "components": structure.components,
        "is_valid": structure.is_valid,
        "depth": structure.depth,
        "validation_issues": structure.validation_issues,
    }


DRAFT_AGENT_TOOLS = [
    agent_validate_dsl,
    agent_search_patterns,
    agent_get_relationships,
    agent_generate_random_structure,
]


def get_draft_variations_prompt(tool_args: dict) -> str:
    """Build system prompt for the draft variations sampling agent.

    This agent has access to agent_validate_dsl, agent_search_patterns, and
    agent_get_relationships tools to generate 3 informed card variations.
    All symbols are loaded dynamically from SymbolGenerator.
    """
    # Fetch live DSL docs
    dsl_docs = ""
    try:
        from gchat.wrapper_api import get_dsl_documentation

        dsl_docs = get_dsl_documentation(include_examples=True, include_hierarchy=True)
    except Exception:
        dsl_docs = "(DSL documentation unavailable)"

    # Load symbols dynamically — never hardcode Unicode
    sym = _get_symbols()
    section = sym.get("Section", "Section")
    dtext = sym.get("DecoratedText", "DecoratedText")
    btnlist = sym.get("ButtonList", "ButtonList")
    btn = sym.get("Button", "Button")
    grid = sym.get("Grid", "Grid")
    gitem = sym.get("GridItem", "GridItem")
    carousel = sym.get("Carousel", "Carousel")
    ccard = sym.get("CarouselCard", "CarouselCard")
    divider = sym.get("Divider", "Divider")
    card = sym.get("Card", "Card")
    cheader = sym.get("CardHeader", "CardHeader")

    return f"""You are a Google Chat card designer. Given a card_description and card_params,
generate exactly 3 variations of the card, each with a different design philosophy.

## DSL Reference
{dsl_docs}

## CRITICAL DSL RULES
- DSL MUST start at **Section level** using `{section}` (Section symbol). Example: `{section}[{dtext}\u00d72, {btnlist}[{btn}\u00d72]]`
- NEVER wrap DSL in Card (`{card}`) or CardHeader (`{cheader}`) — the builder adds those automatically
  from the title/subtitle in card_params.
- Valid top-level containers: `{section}` (Section) only. Everything else nests inside sections.
- `{btnlist}[{btn}\u00d7N]` = ButtonList with N buttons (buttons MUST be inside ButtonList)
- `{grid}[{gitem}\u00d7N]` = Grid with N items
- `{carousel}[{ccard}\u00d7N]` = Carousel with N cards
- `{divider}` = Divider (standalone widget in a section)
- Multiple sections are possible (`{section}[...] {section}[...]`) but **prefer single-section DSL**
  to avoid rendering issues. Put all widgets in one section: `{section}[{dtext}\u00d72, {divider}, {btnlist}[{btn}\u00d72]]`

## card_params Format
card_params uses **symbol keys** with `_shared`/`_items` pattern for widget content:
```json
{{
  "title": "Card Title",
  "subtitle": "Card Subtitle",
  "{dtext}": {{
    "_shared": {{"top_label": "Status"}},
    "_items": [{{"text": "Item 1"}}, {{"text": "Item 2"}}]
  }},
  "{btn}": {{
    "_items": [{{"text": "Button 1", "url": "https://..."}}, {{"text": "Button 2", "url": "https://..."}}]
  }}
}}
```
- Item count in `_items` MUST match the multiplier in DSL (e.g., `{dtext}\u00d72` needs exactly 2 items)
- `{gitem}._items` for GridItem content, `{ccard}._items` for CarouselCard content
- Flat keys also work: `"text"`, `"buttons"`, `"items"` (list of decorated text dicts)

## HTML Styling in card_params
Text fields in card_params (`text`, `top_label`, `bottom_label`) support Google Chat HTML for
rich styling. Use raw HTML tags directly in string values — NOT Jinja template syntax.

### Semantic Colors (use `<font color="HEX">`)
- Green (success): `<font color="#34a853">Online</font>`
- Red (error): `<font color="#ea4335">Error</font>`
- Yellow (warning): `<font color="#fbbc05">Warning</font>`
- Blue (info): `<font color="#4285f4">Info</font>`
- Gray (muted): `<font color="#9aa0a6">Note</font>`
- Custom: `<font color="#FF5733">Custom</font>`

### Text Formatting
- Bold: `<b>Important</b>`
- Italic: `<i>Note</i>`
- Strikethrough: `<s>Removed</s>`
- Link: `<a href="https://example.com">Click</a>`

### Combining (nest tags)
- Green bold: `<font color="#34a853"><b>Online</b></font>`
- Red strikethrough: `<font color="#ea4335"><s>Deprecated</s></font>`
- Yellow bold: `<font color="#fbbc05"><b>Warning</b></font>`

### Usage in card_params
Apply HTML in `text`, `top_label`, or `bottom_label` fields:
```json
{{
  "{dtext}": {{
    "_items": [
      {{"text": "<font color=\\"#34a853\\"><b>Online</b></font>", "top_label": "Server Status"}},
      {{"text": "<font color=\\"#fbbc05\\">Memory Warning</font>", "top_label": "Health"}},
      {{"text": "<font color=\\"#ea4335\\"><s>Deprecated</s></font>", "top_label": "Legacy API"}}
    ]
  }}
}}
```
The **Styled** variation should use colors and formatting heavily to make the card visually rich.

## Your Tools
You have 4 tools available — USE THEM before generating variations:
1. **agent_validate_dsl**: Validate any DSL string you produce. Call this for EACH variation.
2. **agent_search_patterns**: Search historical card patterns for inspiration. Call this first
   with the original description to find successful patterns.
3. **agent_get_relationships**: Get valid parent\u2192child component relationships to ensure
   your DSL hierarchy is correct.
4. **agent_generate_random_structure**: Generate a random valid card structure from the DAG
   containment rules. Pass required_components as comma-separated names
   (e.g. "DecoratedText,ButtonList") to constrain output. Use this for the Creative variation
   to get a guaranteed-valid DSL structure.

## Workflow
1. Call agent_search_patterns with the original description to find inspiration
2. Call agent_generate_random_structure with relevant components for Creative variation ideas
3. Design 3 variations:
   - **Conservative**: Minimal changes from the original — fix issues, keep structure
   - **Enhanced**: Add useful widgets (icons, buttons, labels, dividers) while keeping the same intent
   - **Styled**: Same or similar DSL structure but with heavy Jinja templating — use success_text,
     error_text, warning_text, bold, badge, status_icon, price, color filters in text fields
4. Call agent_validate_dsl for each variation's card_description to verify correctness
5. Return all 3 as structured output

## Response Format
Return a JSON object with this exact schema:
{{
  "variations": [
    {{
      "card_description": "{section}[{dtext}\u00d72, {btnlist}[{btn}\u00d72]]",
      "card_params": {{"title": "...", "subtitle": "...", "{dtext}": {{"_items": [...]}}, "{btn}": {{"_items": [...]}}}},
      "label": "Conservative"
    }},
    {{
      "card_description": "{section}[{dtext}\u00d73, {divider}, {btnlist}[{btn}\u00d72]]",
      "card_params": {{"title": "...", "subtitle": "...", "{dtext}": {{"_items": [...]}}, "{btn}": {{"_items": [...]}}}},
      "label": "Enhanced"
    }},
    {{
      "card_description": "{section}[{dtext}\u00d73, {btnlist}[{btn}\u00d72]]",
      "card_params": {{"title": "...", "subtitle": "...", "{dtext}": {{"_items": [{{"text": "<font color=\\"#34a853\\"><b>Online</b></font>", "top_label": "Status"}}, {{"text": "<font color=\\"#fbbc05\\">Warning</font>", "top_label": "Health"}}, ...]}}, "{btn}": {{"_items": [...]}}}},
      "label": "Styled"
    }}
  ],
  "reasoning": "Brief explanation of design choices"
}}

## Original Input
card_description: {tool_args.get("card_description", "(not provided)")}
card_params: {tool_args.get("card_params", "(not provided)")}
"""
