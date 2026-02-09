"""
Tests for symbol-keyed card_params resolution.

Verifies that resolve_symbol_params correctly translates DSL symbol keys
(δ, ᵬ, ǵ, etc.) in card_params to the flat builder keys the card builder expects.

Uses metadata fallback (no wrapper) so tests run without the full card framework.
"""

import pytest

from gchat.card_builder.symbol_params import _resolve_param_key, resolve_symbol_params

# Realistic reverse_symbol_mapping (symbol → component name)
REVERSE_SYMBOLS = {
    "§": "Section",
    "δ": "DecoratedText",
    "Ƀ": "ButtonList",
    "ᵬ": "Button",
    "ℊ": "Grid",
    "ǵ": "GridItem",
    "◦": "Carousel",
    "▲": "CarouselCard",
}


class TestResolveParamKey:
    """Tests for _resolve_param_key (dynamic component → flat key resolution)."""

    def test_button_resolves_to_buttons(self):
        assert _resolve_param_key("Button") == "buttons"

    def test_decorated_text_resolves_to_items(self):
        assert _resolve_param_key("DecoratedText") == "items"

    def test_text_paragraph_resolves_to_items(self):
        assert _resolve_param_key("TextParagraph") == "items"

    def test_chip_resolves_to_chips(self):
        assert _resolve_param_key("Chip") == "chips"

    def test_grid_item_resolves_to_items(self):
        assert _resolve_param_key("GridItem") == "items"

    def test_carousel_card_resolves_to_cards(self):
        assert _resolve_param_key("CarouselCard") == "cards"

    def test_unknown_component_returns_none(self):
        assert _resolve_param_key("Section") is None
        assert _resolve_param_key("NonExistent") is None


class TestResolveSymbolParams:
    """Tests for resolve_symbol_params()."""

    def test_passthrough_no_symbols(self):
        """Flat keys pass through unchanged when no symbol keys present."""
        params = {
            "title": "Dashboard",
            "items": [{"text": "Hello"}],
            "buttons": [{"text": "Click", "url": "https://example.com"}],
        }
        result = resolve_symbol_params(params, REVERSE_SYMBOLS)
        assert result == params
        assert result is params  # same object, not copied

    def test_passthrough_empty(self):
        """Empty or None params pass through."""
        assert resolve_symbol_params({}, REVERSE_SYMBOLS) == {}
        assert resolve_symbol_params(None, REVERSE_SYMBOLS) is None

    def test_passthrough_no_mapping(self):
        """Returns unchanged if reverse_symbol_mapping is empty or None."""
        params = {"δ": [{"text": "hi"}]}
        assert resolve_symbol_params(params, {}) == params
        assert resolve_symbol_params(params, None) == params

    def test_symbol_list_value(self):
        """Symbol key with list value resolves to flat key."""
        params = {
            "title": "Test",
            "ᵬ": [{"text": "OK", "url": "https://ok.com"}],
        }
        result = resolve_symbol_params(params, REVERSE_SYMBOLS)
        assert result == {
            "title": "Test",
            "buttons": [{"text": "OK", "url": "https://ok.com"}],
        }

    def test_symbol_shared_items_merging(self):
        """Symbol key with _shared/_items merges shared fields into each item."""
        params = {
            "title": "Dashboard",
            "δ": {
                "_shared": {"top_label": "Service"},
                "_items": [
                    {"text": "Google Drive", "icon": "folder"},
                    {"text": "Gmail API", "icon": "mail"},
                ],
            },
        }
        result = resolve_symbol_params(params, REVERSE_SYMBOLS)
        assert result == {
            "title": "Dashboard",
            "items": [
                {"top_label": "Service", "text": "Google Drive", "icon": "folder"},
                {"top_label": "Service", "text": "Gmail API", "icon": "mail"},
            ],
        }

    def test_shared_items_override(self):
        """Per-item fields override _shared fields."""
        params = {
            "δ": {
                "_shared": {"top_label": "Default", "icon": "star"},
                "_items": [
                    {"text": "Custom", "top_label": "Override"},
                ],
            },
        }
        result = resolve_symbol_params(params, REVERSE_SYMBOLS)
        # Per-item "top_label" overrides _shared
        assert result["items"] == [
            {"top_label": "Override", "icon": "star", "text": "Custom"},
        ]

    def test_items_without_shared(self):
        """_items without _shared works (empty shared)."""
        params = {
            "δ": {
                "_items": [{"text": "A"}, {"text": "B"}],
            },
        }
        result = resolve_symbol_params(params, REVERSE_SYMBOLS)
        assert result == {"items": [{"text": "A"}, {"text": "B"}]}

    def test_single_dict_value(self):
        """Single dict without _items is wrapped in a list."""
        params = {
            "ᵬ": {"text": "Solo Button", "url": "https://example.com"},
        }
        result = resolve_symbol_params(params, REVERSE_SYMBOLS)
        assert result == {
            "buttons": [{"text": "Solo Button", "url": "https://example.com"}],
        }

    def test_mixed_symbol_and_flat_keys(self):
        """Symbol and flat keys coexist; symbol keys take precedence on conflict."""
        params = {
            "title": "Mixed",
            "items": [{"text": "flat"}],
            "δ": [{"text": "symbol wins"}],
        }
        result = resolve_symbol_params(params, REVERSE_SYMBOLS)
        assert result["title"] == "Mixed"
        assert result["items"] == [{"text": "symbol wins"}]

    def test_multiple_symbol_keys(self):
        """Multiple symbol keys resolve independently."""
        params = {
            "title": "Multi",
            "δ": [{"text": "Item 1"}, {"text": "Item 2"}],
            "ᵬ": [{"text": "Btn", "url": "https://x.com"}],
        }
        result = resolve_symbol_params(params, REVERSE_SYMBOLS)
        assert result == {
            "title": "Multi",
            "items": [{"text": "Item 1"}, {"text": "Item 2"}],
            "buttons": [{"text": "Btn", "url": "https://x.com"}],
        }

    def test_grid_item_symbol(self):
        """GridItem symbol resolves to 'items' key."""
        params = {
            "ǵ": [{"title": "Cell 1"}, {"title": "Cell 2"}],
        }
        result = resolve_symbol_params(params, REVERSE_SYMBOLS)
        assert result == {
            "items": [{"title": "Cell 1"}, {"title": "Cell 2"}],
        }

    def test_carousel_card_symbol(self):
        """CarouselCard symbol resolves to 'cards' key."""
        params = {
            "▲": [{"title": "Card 1"}, {"title": "Card 2"}],
        }
        result = resolve_symbol_params(params, REVERSE_SYMBOLS)
        assert result == {
            "cards": [{"title": "Card 1"}, {"title": "Card 2"}],
        }

    def test_unknown_component_skipped(self):
        """Symbols mapping to components without a context resource are skipped."""
        params = {
            "title": "Test",
            "§": {"something": True},  # Section has no context resource
        }
        result = resolve_symbol_params(params, REVERSE_SYMBOLS)
        assert result == {"title": "Test"}

    def test_string_value(self):
        """String value is passed through as-is (for scalar param keys)."""
        # Chip symbol resolves to "chips" — string value passes through
        params = {"ᵬ": "just a string"}
        result = resolve_symbol_params(params, REVERSE_SYMBOLS)
        assert result == {"buttons": "just a string"}

    def test_full_example_from_plan(self):
        """End-to-end test matching the plan's 'After' example."""
        params = {
            "title": "Dashboard",
            "δ": {
                "_shared": {"top_label": "Service"},
                "_items": [
                    {"text": "Google Drive", "icon": "folder"},
                    {"text": "Gmail API", "icon": "mail"},
                ],
            },
            "ᵬ": [{"text": "Status Page", "url": "https://status.google.com"}],
        }
        result = resolve_symbol_params(params, REVERSE_SYMBOLS)
        assert result == {
            "title": "Dashboard",
            "items": [
                {"top_label": "Service", "text": "Google Drive", "icon": "folder"},
                {"top_label": "Service", "text": "Gmail API", "icon": "mail"},
            ],
            "buttons": [{"text": "Status Page", "url": "https://status.google.com"}],
        }
