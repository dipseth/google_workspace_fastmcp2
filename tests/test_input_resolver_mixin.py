"""
Tests for InputResolverMixin.

Verifies that the upstream mixin correctly handles:
- normalize_shared_items (shared/items merging)
- resolve_symbol_params (symbol -> flat key resolution)
- consume_from_context (sequential resource consumption with field extractors)
- Overflow handlers for exhausted resource pools
"""

import pytest

from adapters.module_wrapper.input_resolver_mixin import InputResolverMixin


class MockWrapper(InputResolverMixin):
    """Minimal mock that satisfies InputResolverMixin requirements."""

    def __init__(self):
        self._context_resources = {
            "Button": ("buttons", "_button_index"),
            "Chip": ("chips", "_chip_index"),
            "DecoratedText": ("content_texts", "_text_index"),
            "TextParagraph": ("content_texts", "_text_index"),
            "GridItem": ("grid_items", "_grid_item_index"),
            "CarouselCard": ("carousel_cards", "_carousel_card_index"),
        }
        self.reverse_symbol_mapping = {
            "§": "Section",
            "δ": "DecoratedText",
            "Ƀ": "ButtonList",
            "ᵬ": "Button",
            "ℊ": "Grid",
            "ǵ": "GridItem",
            "◦": "Carousel",
            "▲": "CarouselCard",
        }
        # Manually init the mixin registries (normally done by super().__init__)
        self._field_extractors = {}
        self._overflow_handlers = {}
        self._param_key_overrides = {}
        self._scalar_param_keys = set()


def make_wrapper(**overrides):
    """Create a MockWrapper with optional overrides."""
    w = MockWrapper()
    for k, v in overrides.items():
        setattr(w, k, v)
    return w


def make_registered_wrapper():
    """Create a wrapper with card-domain extractors registered."""
    from gchat.card_builder.field_extractors import (
        CARD_FIELD_EXTRACTORS,
        CARD_OVERFLOW_HANDLERS,
        CARD_PARAM_KEY_OVERRIDES,
        CARD_SCALAR_PARAMS,
    )

    w = MockWrapper()
    w.register_input_resolution_batch(
        extractors=CARD_FIELD_EXTRACTORS,
        overflow_handlers=CARD_OVERFLOW_HANDLERS,
        param_key_overrides=CARD_PARAM_KEY_OVERRIDES,
        scalar_params=CARD_SCALAR_PARAMS,
    )
    return w


# =============================================================================
# normalize_shared_items
# =============================================================================


class TestNormalizeSharedItems:
    def setup_method(self):
        self.w = make_wrapper()

    def test_list_passthrough(self):
        value = [{"text": "a"}, {"text": "b"}]
        assert self.w.normalize_shared_items(value, "items") is value

    def test_shared_items_merge(self):
        value = {
            "_shared": {"top_label": "X"},
            "_items": [{"text": "A"}, {"text": "B"}],
        }
        result = self.w.normalize_shared_items(value, "items")
        assert result == [
            {"top_label": "X", "text": "A"},
            {"top_label": "X", "text": "B"},
        ]

    def test_items_override_shared(self):
        value = {
            "_shared": {"top_label": "Default"},
            "_items": [{"text": "A", "top_label": "Override"}],
        }
        result = self.w.normalize_shared_items(value, "items")
        assert result == [{"top_label": "Override", "text": "A"}]

    def test_items_without_shared(self):
        value = {"_items": [{"text": "A"}]}
        result = self.w.normalize_shared_items(value, "items")
        assert result == [{"text": "A"}]

    def test_single_dict_wrapped_in_list(self):
        value = {"text": "Solo"}
        result = self.w.normalize_shared_items(value, "buttons")
        assert result == [{"text": "Solo"}]

    def test_scalar_dict_not_wrapped(self):
        self.w._scalar_param_keys = {"image_url"}
        value = {"uri": "https://example.com/img.png"}
        result = self.w.normalize_shared_items(value, "image_url")
        assert result == {"uri": "https://example.com/img.png"}

    def test_string_passthrough(self):
        assert self.w.normalize_shared_items("hello", "items") == "hello"


# =============================================================================
# resolve_symbol_params
# =============================================================================


class TestResolveSymbolParams:
    def setup_method(self):
        self.w = make_registered_wrapper()

    def test_passthrough_no_symbols(self):
        params = {"title": "Dashboard", "items": [{"text": "Hello"}]}
        result = self.w.resolve_symbol_params(params)
        assert result == params
        assert result is params  # same object

    def test_passthrough_empty(self):
        assert self.w.resolve_symbol_params({}) == {}
        assert self.w.resolve_symbol_params(None) is None

    def test_symbol_list_value(self):
        params = {
            "title": "Test",
            "ᵬ": [{"text": "OK", "url": "https://ok.com"}],
        }
        result = self.w.resolve_symbol_params(params)
        assert result == {
            "title": "Test",
            "buttons": [{"text": "OK", "url": "https://ok.com"}],
        }

    def test_symbol_shared_items_merging(self):
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
        result = self.w.resolve_symbol_params(params)
        assert result == {
            "title": "Dashboard",
            "items": [
                {"top_label": "Service", "text": "Google Drive", "icon": "folder"},
                {"top_label": "Service", "text": "Gmail API", "icon": "mail"},
            ],
        }

    def test_single_dict_wrapped(self):
        params = {"ᵬ": {"text": "Solo", "url": "https://example.com"}}
        result = self.w.resolve_symbol_params(params)
        assert result == {
            "buttons": [{"text": "Solo", "url": "https://example.com"}],
        }

    def test_symbol_overrides_flat_key(self):
        params = {
            "items": [{"text": "flat"}],
            "δ": [{"text": "symbol wins"}],
        }
        result = self.w.resolve_symbol_params(params)
        assert result["items"] == [{"text": "symbol wins"}]

    def test_multiple_symbols(self):
        params = {
            "title": "Multi",
            "δ": [{"text": "Item 1"}, {"text": "Item 2"}],
            "ᵬ": [{"text": "Btn", "url": "https://x.com"}],
        }
        result = self.w.resolve_symbol_params(params)
        assert result == {
            "title": "Multi",
            "items": [{"text": "Item 1"}, {"text": "Item 2"}],
            "buttons": [{"text": "Btn", "url": "https://x.com"}],
        }

    def test_grid_item_symbol(self):
        params = {"ǵ": [{"title": "Cell 1"}, {"title": "Cell 2"}]}
        result = self.w.resolve_symbol_params(params)
        assert result == {"grid_items": [{"title": "Cell 1"}, {"title": "Cell 2"}]}

    def test_carousel_card_symbol(self):
        params = {"▲": [{"title": "Card 1"}, {"title": "Card 2"}]}
        result = self.w.resolve_symbol_params(params)
        assert result == {"cards": [{"title": "Card 1"}, {"title": "Card 2"}]}

    def test_unknown_component_skipped(self):
        params = {"title": "Test", "§": {"something": True}}
        result = self.w.resolve_symbol_params(params)
        assert result == {"title": "Test"}

    def test_explicit_reverse_mapping(self):
        """Can override reverse_symbol_mapping via argument."""
        params = {"X": [{"text": "hi"}]}
        custom_mapping = {"X": "Button"}
        result = self.w.resolve_symbol_params(params, reverse_mapping=custom_mapping)
        assert result == {"buttons": [{"text": "hi"}]}


# =============================================================================
# consume_from_context
# =============================================================================


class TestConsumeFromContext:
    def setup_method(self):
        self.w = make_registered_wrapper()

    def test_consume_button(self):
        context = {
            "buttons": [
                {"text": "Click Me", "url": "https://example.com", "icon": "add"},
            ],
            "_button_index": 0,
        }
        result = self.w.consume_from_context("Button", context)
        assert result == {
            "text": "Click Me",
            "url": "https://example.com",
            "icon": "add",
        }
        assert context["_button_index"] == 1

    def test_consume_decorated_text(self):
        context = {
            "content_texts": [
                {"styled": "<b>Hello</b>", "top_label": "Greeting", "icon": "wave"},
            ],
            "_text_index": 0,
        }
        result = self.w.consume_from_context("DecoratedText", context)
        assert result["text"] == "<b>Hello</b>"
        assert result["top_label"] == "Greeting"
        assert result["icon"] == "wave"
        assert result["wrapText"] is True
        assert context["_text_index"] == 1

    def test_consume_chip(self):
        context = {
            "chips": [{"label": "Tag", "url": "https://tag.com", "icon": "label"}],
            "_chip_index": 0,
        }
        result = self.w.consume_from_context("Chip", context)
        assert result == {"label": "Tag", "url": "https://tag.com", "icon": "label"}

    def test_consume_carousel_card(self):
        context = {
            "carousel_cards": [
                {
                    "title": "Card 1",
                    "subtitle": "Sub",
                    "image_url": "https://img.com/1.png",
                    "text": "Body",
                    "buttons": [{"text": "Go"}],
                }
            ],
            "_carousel_card_index": 0,
        }
        result = self.w.consume_from_context("CarouselCard", context)
        assert result["title"] == "Card 1"
        assert result["subtitle"] == "Sub"
        assert result["image_url"] == "https://img.com/1.png"
        assert result["text"] == "Body"
        assert result["buttons"] == [{"text": "Go"}]

    def test_consume_grid_item(self):
        context = {
            "grid_items": [
                {
                    "title": "Item 1",
                    "subtitle": "Sub",
                    "image_url": "https://img.com/1.png",
                }
            ],
            "_grid_item_index": 0,
        }
        result = self.w.consume_from_context("GridItem", context)
        assert result["title"] == "Item 1"
        assert result["subtitle"] == "Sub"
        assert result["image_url"] == "https://img.com/1.png"

    def test_sequential_consumption(self):
        """Resources are consumed sequentially."""
        context = {
            "buttons": [
                {"text": "First", "url": "https://1.com"},
                {"text": "Second", "url": "https://2.com"},
                {"text": "Third", "url": "https://3.com"},
            ],
            "_button_index": 0,
        }
        r1 = self.w.consume_from_context("Button", context)
        r2 = self.w.consume_from_context("Button", context)
        r3 = self.w.consume_from_context("Button", context)
        assert r1["text"] == "First"
        assert r2["text"] == "Second"
        assert r3["text"] == "Third"
        assert context["_button_index"] == 3

    def test_overflow_button(self):
        """When resources exhausted, overflow handler provides fallback."""
        context = {"buttons": [], "_button_index": 0}
        result = self.w.consume_from_context("Button", context)
        assert result == {"text": "Button 1"}
        assert context["_button_index"] == 1

    def test_overflow_chip(self):
        context = {"chips": [], "_chip_index": 0}
        result = self.w.consume_from_context("Chip", context)
        assert result == {"label": "Chip 1"}

    def test_overflow_carousel_card(self):
        context = {"carousel_cards": [], "_carousel_card_index": 0}
        result = self.w.consume_from_context("CarouselCard", context)
        assert result == {"title": "Card 1"}

    def test_overflow_grid_item(self):
        context = {"grid_items": [], "_grid_item_index": 0}
        result = self.w.consume_from_context("GridItem", context)
        assert result == {"title": "Item 1"}

    def test_overflow_decorated_text_empty(self):
        """DecoratedText has no overflow handler - returns empty dict."""
        context = {"content_texts": [], "_text_index": 0}
        result = self.w.consume_from_context("DecoratedText", context)
        assert result == {}
        assert context["_text_index"] == 1

    def test_unknown_component_returns_empty(self):
        result = self.w.consume_from_context("NonExistent", {})
        assert result == {}

    def test_no_extractor_passthrough(self):
        """Without a registered extractor, all fields pass through."""
        w = make_wrapper()
        context = {
            "buttons": [{"text": "Hi", "url": "https://x.com", "extra": 42}],
            "_button_index": 0,
        }
        result = w.consume_from_context("Button", context)
        assert result == {"text": "Hi", "url": "https://x.com", "extra": 42}


# =============================================================================
# Registration
# =============================================================================


class TestRegistration:
    def test_register_field_extractor(self):
        w = make_wrapper()

        def extractor(resource, idx):
            return {"custom": resource.get("val")}

        w.register_field_extractor("my_key", extractor)
        assert w._field_extractors["my_key"] is extractor

    def test_register_overflow_handler(self):
        w = make_wrapper()

        def handler(name, idx):
            return {"fallback": True}

        w.register_overflow_handler("MyComponent", handler)
        assert w._overflow_handlers["MyComponent"] is handler

    def test_batch_registration(self):
        w = make_wrapper()
        w.register_input_resolution_batch(
            extractors={"k1": lambda r, i: r},
            overflow_handlers={"C1": lambda n, i: {}},
            param_key_overrides={"k1": "flat_k1"},
            scalar_params={"image_url"},
        )
        assert "k1" in w._field_extractors
        assert "C1" in w._overflow_handlers
        assert w._param_key_overrides["k1"] == "flat_k1"
        assert "image_url" in w._scalar_param_keys

    def test_get_param_key_with_override(self):
        w = make_wrapper()
        w._param_key_overrides = {"content_texts": "items"}
        assert w.get_param_key_for_component("DecoratedText") == "items"

    def test_get_param_key_identity(self):
        w = make_wrapper()
        assert w.get_param_key_for_component("Button") == "buttons"

    def test_get_param_key_unknown(self):
        w = make_wrapper()
        assert w.get_param_key_for_component("Section") is None
