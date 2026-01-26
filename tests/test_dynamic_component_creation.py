"""
Test: Dynamic Component Creation via ModuleWrapper and Qdrant Relationships

This test file demonstrates how to:
1. Query Qdrant for component relationships
2. Load components via ModuleWrapper
3. Dynamically instantiate and render complex widgets
4. Build cards from relationship data

KEY CONCEPTS:
=============

1. COMPONENT LOADING via ModuleWrapper:
   - Components are loaded by path: wrapper.get_component_by_path("card_framework.v2.widgets.Grid")
   - ComponentRegistry provides a cache and fallback path resolution

2. RELATIONSHIP DATA in Qdrant:
   - Each component has indexed relationships (child_classes, json_path, etc.)
   - Example: Grid has children [OnClick, BorderStyle]
   - This tells us Grid can have on_click and border_style attributes

3. INSTANTIATION PATTERNS:
   - Nested components: Grid(items=[GridItem(...), GridItem(...)])
   - Action components: OnClick(open_link=OpenLink(url="..."))
   - Enums are often nested: SelectionInput.SelectionType.CHECK_BOX

4. RENDERING:
   - All components have .render() method
   - Returns Google Chat JSON format (snake_case internally, camelCase for API)

5. API LIMITATIONS (verified via curl):
   - GridItem does NOT support onClick (whole Grid does)
   - Image widget supports onClick
   - ChipList/Chip support onClick

6. CARD_FRAMEWORK vs GOOGLE CHAT API GAPS:
   The card_framework library does NOT cover all Google Chat API features:

   SelectionType enum has: SWITCH, CHECK_BOX, RADIO_BUTTON, DROPDOWN
   API also supports: MULTI_SELECT (with platformDataSource, externalDataSource)

   Missing/incomplete widgets in card_framework:
   - Columns layout (columnItems with horizontalSizeStyle, verticalAlignment)
   - DateTimePicker (DATE_AND_TIME, DATE_ONLY, TIME_ONLY)
   - TextInput autoCompleteAction & initialSuggestions
   - Material icon params: fill, weight, grade, opticalSize
   - Grid borderStyle with strokeColor RGBA and cornerRadius
   - Grid item cropStyle (CIRCLE, SQUARE, RECTANGLE_4_3, RECTANGLE_CUSTOM)
   - Button types: FILLED, OUTLINED, FILLED_TONAL with custom color RGBA
   - OverflowMenu with nested items
   - fixedFooter with primaryButton/secondaryButton
   - cardActions array
   - peekCardHeader
   - DecoratedText switchControl (inline switch/checkbox)

   For advanced features, use raw JSON dicts passed to sections parameter.

Usage:
    pytest tests/test_dynamic_component_creation.py -v -s
"""

import json
import os
from typing import Any, Dict, List, Optional, Type

import pytest
from qdrant_client import models

from adapters.module_wrapper import ModuleWrapper
from config.qdrant_client import get_qdrant_client
from config.settings import settings


@pytest.fixture(scope="module")
def wrapper():
    """Get ModuleWrapper instance for loading components."""
    return ModuleWrapper(
        module_or_name="card_framework",
        qdrant_url=os.getenv("QDRANT_URL"),
        qdrant_api_key=os.getenv("QDRANT_KEY"),
        collection_name=settings.card_collection,
        auto_initialize=False,
    )


@pytest.fixture(scope="module")
def qdrant_client():
    """Get Qdrant client for querying relationships."""
    return get_qdrant_client()


class ComponentRegistry:
    """
    Registry for loading and caching components from ModuleWrapper.

    Uses Qdrant relationship data to understand component structure.
    """

    # Known working paths for common components
    # NOTE: Some enums (like SelectionType) are NESTED within their parent class
    #       and cannot be loaded separately. Access via: SelectionInput.SelectionType
    KNOWN_PATHS = {
        # Core widgets
        "Grid": "card_framework.v2.widgets.Grid",
        "GridItem": "card_framework.v2.widgets.grid.GridItem",
        "ImageComponent": "card_framework.v2.widgets.grid.ImageComponent",
        "Image": "card_framework.v2.widgets.Image",
        "ChipList": "card_framework.v2.widgets.ChipList",
        "Chip": "card_framework.v2.widgets.chip_list.Chip",
        "SelectionInput": "card_framework.v2.widgets.SelectionInput",
        "SelectionItem": "card_framework.v2.widgets.selection_input.SelectionItem",
        # SelectionType is NESTED: use SelectionInput.SelectionType.MULTI_SELECT
        "TextInput": "card_framework.v2.widgets.TextInput",
        "ButtonList": "card_framework.v2.widgets.ButtonList",
        "Button": "card_framework.v2.widgets.button.Button",
        "DecoratedText": "card_framework.v2.widgets.DecoratedText",
        "TextParagraph": "card_framework.v2.widgets.TextParagraph",
        # Action components
        "OnClick": "card_framework.v2.widgets.on_click.OnClick",
        "OpenLink": "card_framework.v2.widgets.on_click.OpenLink",
        "Action": "card_framework.v2.widgets.on_click.Action",
        # Icon components
        "Icon": "card_framework.v2.widgets.icon.Icon",
        # Card structure
        "Card": "card_framework.v2.card.Card",
        "CardHeader": "card_framework.v2.card.CardHeader",
        "Section": "card_framework.v2.section.Section",
    }

    def __init__(self, wrapper: ModuleWrapper):
        self.wrapper = wrapper
        self._cache: Dict[str, Type] = {}

    def get(self, name: str) -> Optional[Type]:
        """Get a component class by name."""
        if name in self._cache:
            return self._cache[name]

        # Try known path first
        if name in self.KNOWN_PATHS:
            component = self.wrapper.get_component_by_path(self.KNOWN_PATHS[name])
            if component:
                self._cache[name] = component
                return component

        # Try common path patterns
        patterns = [
            f"card_framework.v2.widgets.{name}",
            f"card_framework.v2.widgets.{name.lower()}.{name}",
            f"card_framework.{name}",
        ]

        for path in patterns:
            try:
                component = self.wrapper.get_component_by_path(path)
                if component:
                    self._cache[name] = component
                    return component
            except Exception:
                continue

        return None


def get_component_relationships(client, component_name: str) -> Dict[str, Any]:
    """Query Qdrant for a component's relationship data."""
    results, _ = client.scroll(
        collection_name=settings.card_collection,
        scroll_filter=models.Filter(
            must=[
                models.FieldCondition(
                    key="type", match=models.MatchValue(value="class")
                ),
                models.FieldCondition(
                    key="name", match=models.MatchValue(value=component_name)
                ),
            ]
        ),
        limit=1,
        with_payload=True,
    )

    if results:
        return results[0].payload.get("relationships", {})
    return {}


class TestComponentLoading:
    """Test that we can load components via ModuleWrapper."""

    def test_load_grid_components(self, wrapper):
        """Test loading Grid and related components."""
        registry = ComponentRegistry(wrapper)

        Grid = registry.get("Grid")
        GridItem = registry.get("GridItem")
        ImageComponent = registry.get("ImageComponent")

        assert Grid is not None, "Grid should be loadable"
        assert GridItem is not None, "GridItem should be loadable"
        assert ImageComponent is not None, "ImageComponent should be loadable"

    def test_load_chip_components(self, wrapper):
        """Test loading ChipList and Chip components."""
        registry = ComponentRegistry(wrapper)

        ChipList = registry.get("ChipList")
        Chip = registry.get("Chip")

        assert ChipList is not None, "ChipList should be loadable"
        assert Chip is not None, "Chip should be loadable"

    def test_load_selection_components(self, wrapper):
        """Test loading SelectionInput components.

        NOTE: SelectionType is a NESTED ENUM within SelectionInput, not a separate class.
        Access pattern: SelectionInput.SelectionType.MULTI_SELECT
        """
        registry = ComponentRegistry(wrapper)

        SelectionInput = registry.get("SelectionInput")
        SelectionItem = registry.get("SelectionItem")

        assert SelectionInput is not None, "SelectionInput should be loadable"
        assert SelectionItem is not None, "SelectionItem should be loadable"

        # SelectionType is a nested enum - access via SelectionInput
        assert hasattr(
            SelectionInput, "SelectionType"
        ), "SelectionInput should have SelectionType enum"
        SelectionType = SelectionInput.SelectionType

        # Available types: SWITCH, CHECK_BOX, RADIO_BUTTON, DROPDOWN
        assert hasattr(
            SelectionType, "CHECK_BOX"
        ), "SelectionType should have CHECK_BOX"
        assert hasattr(SelectionType, "DROPDOWN"), "SelectionType should have DROPDOWN"
        print(f"\n✅ SelectionType enum values: {[m.name for m in SelectionType]}")

    def test_load_action_components(self, wrapper):
        """Test loading OnClick and OpenLink."""
        registry = ComponentRegistry(wrapper)

        OnClick = registry.get("OnClick")
        OpenLink = registry.get("OpenLink")

        assert OnClick is not None, "OnClick should be loadable"
        assert OpenLink is not None, "OpenLink should be loadable"


class TestComponentRendering:
    """Test that we can instantiate and render components."""

    def test_render_grid(self, wrapper):
        """Test rendering a Grid with items."""
        registry = ComponentRegistry(wrapper)

        Grid = registry.get("Grid")
        GridItem = registry.get("GridItem")
        ImageComponent = registry.get("ImageComponent")

        items = [
            GridItem(
                title="Item 1",
                image=ImageComponent(image_uri="https://example.com/1.png"),
            ),
            GridItem(
                title="Item 2",
                image=ImageComponent(image_uri="https://example.com/2.png"),
            ),
        ]

        grid = Grid(title="Test Grid", column_count=2, items=items)
        rendered = grid.render()

        assert "grid" in rendered
        assert rendered["grid"]["title"] == "Test Grid"
        assert len(rendered["grid"]["items"]) == 2
        print(f"\n✅ Grid rendered:\n{json.dumps(rendered, indent=2)}")

    def test_render_grid_with_onclick(self, wrapper):
        """Test rendering a Grid with onClick (verified to work in API)."""
        registry = ComponentRegistry(wrapper)

        Grid = registry.get("Grid")
        GridItem = registry.get("GridItem")
        ImageComponent = registry.get("ImageComponent")
        OnClick = registry.get("OnClick")
        OpenLink = registry.get("OpenLink")

        items = [
            GridItem(
                title="Item 1",
                image=ImageComponent(image_uri="https://example.com/1.png"),
            ),
            GridItem(
                title="Item 2",
                image=ImageComponent(image_uri="https://example.com/2.png"),
            ),
        ]

        # Grid-level onClick (NOT per-item - API doesn't support that)
        on_click = OnClick(open_link=OpenLink(url="https://developers.google.com/chat"))
        grid = Grid(
            title="Clickable Grid", column_count=2, items=items, on_click=on_click
        )

        rendered = grid.render()
        assert "onClick" in rendered["grid"] or "on_click" in rendered["grid"]
        print(f"\n✅ Grid with onClick rendered:\n{json.dumps(rendered, indent=2)}")

    def test_render_chiplist(self, wrapper):
        """Test rendering a ChipList with chips."""
        registry = ComponentRegistry(wrapper)

        ChipList = registry.get("ChipList")
        Chip = registry.get("Chip")
        OnClick = registry.get("OnClick")
        OpenLink = registry.get("OpenLink")

        if not all([ChipList, Chip, OnClick, OpenLink]):
            pytest.skip("Required components not available")

        chips = [
            Chip(
                label="Chip 1",
                on_click=OnClick(open_link=OpenLink(url="https://google.com")),
            ),
            Chip(
                label="Chip 2",
                on_click=OnClick(open_link=OpenLink(url="https://github.com")),
            ),
        ]

        chip_list = ChipList(chips=chips)
        rendered = chip_list.render()

        assert "chipList" in rendered or "chip_list" in rendered
        print(f"\n✅ ChipList rendered:\n{json.dumps(rendered, indent=2)}")

    def test_render_selection_input(self, wrapper):
        """Test rendering a SelectionInput with items.

        IMPORTANT: SelectionType is a nested enum within SelectionInput.
        Access pattern: SelectionInput.SelectionType.CHECK_BOX

        card_framework enum has: SWITCH, CHECK_BOX, RADIO_BUTTON, DROPDOWN

        NOTE: Google Chat API also supports MULTI_SELECT (with platformDataSource,
        externalDataSource, multiSelectMaxSelectedItems, multiSelectMinQueryLength)
        but this is NOT in the card_framework enum. Use raw string "MULTI_SELECT" if needed.
        """
        registry = ComponentRegistry(wrapper)

        SelectionInput = registry.get("SelectionInput")
        SelectionItem = registry.get("SelectionItem")

        if not all([SelectionInput, SelectionItem]):
            pytest.skip("Required components not available")

        # SelectionType is nested - access via SelectionInput class
        if not hasattr(SelectionInput, "SelectionType"):
            pytest.skip("SelectionInput doesn't have SelectionType enum")

        SelectionType = SelectionInput.SelectionType

        items = [
            SelectionItem(text="Option 1", value="opt1", bottom_text="Description 1"),
            SelectionItem(text="Option 2", value="opt2", bottom_text="Description 2"),
        ]

        # Use nested enum for type (CHECK_BOX allows multiple selections)
        selection = SelectionInput(
            name="test_selection",
            label="Select an option",
            type=SelectionType.CHECK_BOX,
            items=items,
        )

        rendered = selection.render()
        assert "selectionInput" in rendered or "selection_input" in rendered
        print(f"\n✅ SelectionInput rendered:\n{json.dumps(rendered, indent=2)}")


class TestRelationshipQueries:
    """Test querying and using relationship data from Qdrant."""

    def test_grid_relationships(self, qdrant_client):
        """Test that Grid has expected relationships indexed."""
        rels = get_component_relationships(qdrant_client, "Grid")

        assert "child_classes" in rels
        children = rels["child_classes"]

        # Grid should have OnClick and BorderStyle children
        assert "OnClick" in children, "Grid should have OnClick relationship"
        assert "BorderStyle" in children, "Grid should have BorderStyle relationship"

        print(f"\n✅ Grid relationships: {children}")

    def test_chip_relationships(self, qdrant_client):
        """Test that Chip has expected relationships indexed."""
        rels = get_component_relationships(qdrant_client, "Chip")

        assert "child_classes" in rels
        children = rels["child_classes"]

        # Chip should have Icon and OnClick children
        assert "Icon" in children, "Chip should have Icon relationship"
        assert "OnClick" in children, "Chip should have OnClick relationship"

        print(f"\n✅ Chip relationships: {children}")

    def test_selection_input_relationships(self, qdrant_client):
        """Test that SelectionInput has expected relationships indexed."""
        rels = get_component_relationships(qdrant_client, "SelectionInput")

        assert "child_classes" in rels
        children = rels["child_classes"]

        # SelectionInput should have SelectionType
        assert (
            "SelectionType" in children
        ), "SelectionInput should have SelectionType relationship"

        print(f"\n✅ SelectionInput relationships: {children}")


class TestDynamicCardBuilding:
    """Test building complete cards from component composition."""

    def test_build_complex_card(self, wrapper):
        """Test building a card with multiple widget types."""
        registry = ComponentRegistry(wrapper)

        # Load components
        Card = registry.get("Card")
        Section = registry.get("Section")
        Grid = registry.get("Grid")
        GridItem = registry.get("GridItem")
        ImageComponent = registry.get("ImageComponent")

        if not all([Card, Section, Grid, GridItem, ImageComponent]):
            pytest.skip("Required components not available")

        # Build grid
        grid_items = [
            GridItem(
                title="Item 1",
                image=ImageComponent(image_uri="https://example.com/1.png"),
            ),
            GridItem(
                title="Item 2",
                image=ImageComponent(image_uri="https://example.com/2.png"),
            ),
        ]
        grid = Grid(title="My Grid", column_count=2, items=grid_items)

        # Build section
        section = Section(header="Test Section", widgets=[grid])

        # Build card
        card = Card(sections=[section])
        rendered = card.render()

        # Card.render() returns {'card': {'sections': [...]}}
        assert "card" in rendered, "Card should render with 'card' key"
        assert "sections" in rendered["card"], "Card should have sections"
        print(f"\n✅ Complex card rendered:\n{json.dumps(rendered, indent=2)[:500]}...")

    def test_json_to_component_roundtrip(self, wrapper):
        """
        Test that we can take JSON structure, understand its components,
        and rebuild using our component classes.

        This validates that our relationship data is sufficient for reconstruction.
        """
        registry = ComponentRegistry(wrapper)

        # Original JSON structure (simplified)
        target_json = {
            "grid": {
                "title": "A fine collection",
                "columnCount": 2,
                "items": [
                    {
                        "title": "Item 1",
                        "image": {"imageUri": "https://example.com/1.png"},
                    },
                    {
                        "title": "Item 2",
                        "image": {"imageUri": "https://example.com/2.png"},
                    },
                ],
            }
        }

        # Rebuild using components
        Grid = registry.get("Grid")
        GridItem = registry.get("GridItem")
        ImageComponent = registry.get("ImageComponent")

        rebuilt_items = [
            GridItem(
                title=item["title"],
                image=ImageComponent(image_uri=item["image"]["imageUri"]),
            )
            for item in target_json["grid"]["items"]
        ]

        rebuilt_grid = Grid(
            title=target_json["grid"]["title"],
            column_count=target_json["grid"]["columnCount"],
            items=rebuilt_items,
        )

        rendered = rebuilt_grid.render()

        # Verify structure matches (key fields)
        assert rendered["grid"]["title"] == target_json["grid"]["title"]
        assert len(rendered["grid"]["items"]) == len(target_json["grid"]["items"])

        print("\n✅ JSON -> Component -> JSON roundtrip successful!")
        print(f"Original: {json.dumps(target_json, indent=2)[:200]}...")
        print(f"Rebuilt: {json.dumps(rendered, indent=2)[:200]}...")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
