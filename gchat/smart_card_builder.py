"""
Smart Card Builder

Builds Google Chat cards by:
1. Searching Qdrant vector DB for relevant card components (ColBERT)
2. Getting full_path from search results
3. Loading actual Python classes via ModuleWrapper
4. Using smart inference to map content to component parameters
5. Detecting composition hints from natural language
6. Rendering via component .render() methods

This implements the POC flow: Vector DB → ModuleWrapper → Instantiate → Render
"""

import importlib
import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class SmartCardBuilder:
    """
    Builds cards using card_framework components found via Qdrant vector search.

    Flow:
    1. Natural language description → ColBERT search → Get component paths
    2. Load classes via ModuleWrapper.get_component_by_path()
    3. Instantiate with content using smart inference
    4. Render to Google Chat JSON
    """

    # Fallback component paths (used only if Qdrant is unavailable)
    FALLBACK_PATHS = {
        "Section": "card_framework.v2.section.Section",
        "Card": "card_framework.v2.card.Card",
        "CardHeader": "card_framework.v2.card.CardHeader",
        "Columns": "card_framework.v2.widgets.columns.Columns",
        "Column": "card_framework.v2.widgets.columns.Column",
        "DecoratedText": "card_framework.v2.widgets.decorated_text.DecoratedText",
        "TextParagraph": "card_framework.v2.widgets.text_paragraph.TextParagraph",
        "Image": "card_framework.v2.widgets.image.Image",
        "Button": "card_framework.v2.widgets.decorated_text.Button",
        "ButtonList": "card_framework.v2.widgets.button_list.ButtonList",
        "Divider": "card_framework.v2.widgets.divider.Divider",
        "Icon": "card_framework.v2.widgets.decorated_text.Icon",
        "OnClick": "card_framework.v2.widgets.decorated_text.OnClick",
        # Form input components
        "TextInput": "card_framework.v2.widgets.text_input.TextInput",
        "SelectionInput": "card_framework.v2.widgets.selection_input.SelectionInput",
        "DateTimePicker": "card_framework.v2.widgets.date_time_picker.DateTimePicker",
        # Grid components
        "Grid": "card_framework.v2.widgets.grid.Grid",
        "GridItem": "card_framework.v2.widgets.grid.GridItem",
        "ImageComponent": "card_framework.v2.widgets.grid.ImageComponent",
    }

    # Ordinal words for section parsing (borrowed from nlp_parser)
    ORDINAL_WORDS = {
        "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5,
        "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10,
        "1st": 1, "2nd": 2, "3rd": 3, "4th": 4, "5th": 5,
    }
    ORDINAL_PATTERN = r"(?:first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|1st|2nd|3rd|4th|5th)"

    # Icon mappings - ONLY valid KnownIcon enum values from card_framework
    # Valid: AIRPLANE, BOOKMARK, BUS, CAR, CLOCK, CONFIRMATION_NUMBER_ICON, DESCRIPTION,
    #        DOLLAR, EMAIL, EVENT_SEAT, FLIGHT_ARRIVAL, FLIGHT_DEPARTURE, HOTEL,
    #        HOTEL_ROOM_TYPE, INVITE, MAP_PIN, MEMBERSHIP, MULTIPLE_PEOPLE, PERSON,
    #        PHONE, RESTAURANT_ICON, SHOPPING_CART, STAR, STORE, TICKET, TRAIN,
    #        VIDEO_CAMERA, VIDEO_PLAY
    KNOWN_ICONS = {
        # People & Communication
        "person": "PERSON", "user": "PERSON", "profile": "PERSON", "account": "PERSON",
        "people": "MULTIPLE_PEOPLE", "team": "MULTIPLE_PEOPLE", "group": "MULTIPLE_PEOPLE",
        "email": "EMAIL", "mail": "EMAIL", "message": "EMAIL",
        "phone": "PHONE", "call": "PHONE",
        # Status & Actions (using available icons)
        "star": "STAR", "favorite": "STAR", "rating": "STAR",
        "check": "CONFIRMATION_NUMBER_ICON", "complete": "CONFIRMATION_NUMBER_ICON",
        "done": "CONFIRMATION_NUMBER_ICON", "success": "CONFIRMATION_NUMBER_ICON",
        "warning": "STAR", "alert": "STAR", "caution": "STAR",
        "info": "DESCRIPTION", "information": "DESCRIPTION", "details": "DESCRIPTION",
        # Business & Finance
        "dollar": "DOLLAR", "money": "DOLLAR", "price": "DOLLAR", "cost": "DOLLAR",
        "store": "STORE", "shop": "STORE", "deployment": "STORE",
        "cart": "SHOPPING_CART", "shopping": "SHOPPING_CART",
        "membership": "MEMBERSHIP", "subscription": "MEMBERSHIP",
        # Time & Travel
        "clock": "CLOCK", "time": "CLOCK", "schedule": "CLOCK",
        "calendar": "EVENT_SEAT", "date": "EVENT_SEAT", "event": "EVENT_SEAT",
        "plane": "AIRPLANE", "flight": "AIRPLANE", "travel": "AIRPLANE",
        "car": "CAR", "drive": "CAR", "vehicle": "CAR",
        "bus": "BUS", "transit": "BUS",
        "train": "TRAIN", "rail": "TRAIN",
        "hotel": "HOTEL", "lodging": "HOTEL", "stay": "HOTEL",
        "location": "MAP_PIN", "map": "MAP_PIN", "place": "MAP_PIN", "pin": "MAP_PIN",
        # Content & Media
        "bookmark": "BOOKMARK", "save": "BOOKMARK", "saved": "BOOKMARK",
        "description": "DESCRIPTION", "document": "DESCRIPTION", "file": "DESCRIPTION", "doc": "DESCRIPTION",
        "video": "VIDEO_CAMERA", "camera": "VIDEO_CAMERA", "meeting": "VIDEO_CAMERA",
        "play": "VIDEO_PLAY", "media": "VIDEO_PLAY",
        "ticket": "TICKET", "pass": "TICKET", "admission": "TICKET",
        "invite": "INVITE", "invitation": "INVITE",
        "restaurant": "RESTAURANT_ICON", "food": "RESTAURANT_ICON", "dining": "RESTAURANT_ICON",
    }

    # Patterns for smart inference
    LAYOUT_PATTERNS = {
        "columns": re.compile(
            r"\b(columns?|side.?by.?side|two.?column|split)\b", re.I
        ),
        "image_right": re.compile(
            r"\b(image\s+(on\s+)?(the\s+)?right|right\s+(side\s+)?image|with\s+image\s+on\s+right|image\s+on\s+right)\b", re.I
        ),
        "image_left": re.compile(
            r"\b(image\s+(on\s+)?(the\s+)?left|left\s+(side\s+)?image|with\s+image\s+on\s+left|image\s+on\s+left)\b", re.I
        ),
    }

    # Patterns for content type inference
    CONTENT_PATTERNS = {
        "price": re.compile(r"\$[\d,]+\.?\d*", re.I),
        "url": re.compile(r"https?://[^\s]+", re.I),
        "image_url": re.compile(r"https?://[^\s]+\.(jpg|jpeg|png|gif|webp)", re.I),
        "email": re.compile(r"[\w.-]+@[\w.-]+\.\w+", re.I),
        "date": re.compile(r"\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4}", re.I),
        "id": re.compile(r"\b(id|ID):\s*[\w-]+", re.I),
        "colored_price": re.compile(
            r'<font\s+color=["\']#[0-9a-fA-F]+["\']>\$[\d,]+\.?\d*</font>', re.I
        ),
    }

    # Color mappings for semantic colors
    COLOR_MAP = {
        "success": "#34a853",  # Green
        "error": "#ea4335",    # Red
        "warning": "#fbbc04",  # Yellow
        "info": "#1a73e8",     # Blue
        "green": "#34a853",
        "red": "#ea4335",
        "blue": "#1a73e8",
        "yellow": "#fbbc04",
        "orange": "#ff6d01",
    }

    def __init__(self):
        """Initialize the smart card builder."""
        self._qdrant_client = None
        self._embedder = None
        self._wrapper = None
        self._components: Dict[str, Any] = {}
        self._initialized = False
        self._qdrant_available = False

    def _get_qdrant_client(self):
        """Get Qdrant client from centralized singleton."""
        if self._qdrant_client is None:
            try:
                # Use centralized Qdrant client singleton
                from config.qdrant_client import get_qdrant_client

                self._qdrant_client = get_qdrant_client()
                if self._qdrant_client:
                    self._qdrant_available = True
                    logger.info("SmartCardBuilder using centralized Qdrant client")
                else:
                    logger.warning("Qdrant client not available, using fallback paths")
                    self._qdrant_available = False
            except Exception as e:
                logger.warning(f"Could not get Qdrant client: {e}")
                self._qdrant_available = False

        return self._qdrant_client

    def _get_embedder(self):
        """Get ColBERT embedder for semantic search."""
        if self._embedder is None:
            try:
                from fastembed import LateInteractionTextEmbedding

                self._embedder = LateInteractionTextEmbedding(
                    model_name="colbert-ir/colbertv2.0"
                )
                logger.debug("ColBERT embedder loaded")
            except Exception as e:
                logger.warning(f"Could not load ColBERT embedder: {e}")

        return self._embedder

    def _get_wrapper(self):
        """Get ModuleWrapper for loading components by path."""
        if self._wrapper is None:
            from adapters.module_wrapper import ModuleWrapper

            # Initialize without Qdrant indexing (we handle search ourselves)
            self._wrapper = ModuleWrapper(
                module_or_name="card_framework",
                qdrant_url=os.getenv("QDRANT_URL"),
                qdrant_api_key=os.getenv("QDRANT_KEY"),
                collection_name="card_framework_components_colbert",
                auto_initialize=False,  # Don't re-index, just load module
            )

        return self._wrapper

    def _search_component(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Search for components in Qdrant using ColBERT.

        Args:
            query: Semantic search query
            limit: Max results

        Returns:
            List of {name, type, full_path, score} dicts
        """
        client = self._get_qdrant_client()
        embedder = self._get_embedder()

        if not client or not embedder:
            logger.warning("Qdrant or embedder not available")
            return []

        try:
            # ColBERT multi-vector embedding
            query_vectors_raw = list(embedder.query_embed(query))[0]
            query_vectors = [vec.tolist() for vec in query_vectors_raw]

            results = client.query_points(
                collection_name="card_framework_components_colbert",
                query=query_vectors,
                using="colbert",
                limit=limit,
                with_payload=True,
            )

            # Extract results
            components = []
            for r in results.points:
                p = r.payload
                components.append({
                    "name": p.get("name"),
                    "type": p.get("type"),
                    "full_path": p.get("full_path"),
                    "score": r.score,
                })

            return components

        except Exception as e:
            logger.warning(f"Qdrant search failed: {e}")
            return []

    def _load_component_by_path(self, path: str) -> Optional[Any]:
        """
        Load a component class by its full path.

        Args:
            path: Full path like "card_framework.v2.section.Section"

        Returns:
            The component class or None
        """
        wrapper = self._get_wrapper()
        if wrapper:
            try:
                return wrapper.get_component_by_path(path)
            except Exception as e:
                logger.debug(f"ModuleWrapper load failed for {path}: {e}")

        # Fallback: direct import
        try:
            parts = path.rsplit(".", 1)
            if len(parts) == 2:
                module_path, class_name = parts
                module = importlib.import_module(module_path)
                return getattr(module, class_name, None)
        except Exception as e:
            logger.warning(f"Direct import failed for {path}: {e}")

        return None

    def _find_and_load_component(self, name: str, query: str) -> Optional[Any]:
        """
        Search Qdrant for a component and load it.

        Args:
            name: Component name (e.g., "Columns")
            query: Search query (e.g., "v2.widgets.columns.Columns class")

        Returns:
            The loaded component class or None
        """
        # Check cache first
        if name in self._components:
            return self._components[name]

        # Search Qdrant
        if self._qdrant_available:
            results = self._search_component(query, limit=10)
            for r in results:
                if r["name"] == name and r["type"] == "class" and "v2" in r["full_path"]:
                    cls = self._load_component_by_path(r["full_path"])
                    if cls:
                        self._components[name] = cls
                        logger.debug(f"Loaded {name} from Qdrant: {r['full_path']}")
                        return cls

        # Fallback to hardcoded path
        if name in self.FALLBACK_PATHS:
            cls = self._load_component_by_path(self.FALLBACK_PATHS[name])
            if cls:
                self._components[name] = cls
                logger.debug(f"Loaded {name} from fallback path")
                return cls

        return None

    def initialize(self):
        """Initialize Qdrant connection and load core components."""
        if self._initialized:
            return

        # Test Qdrant connection
        self._get_qdrant_client()
        self._get_embedder()

        # Pre-load commonly used components via Qdrant search
        core_components = {
            "Section": "v2.section.Section class widgets header",
            "Columns": "v2.widgets.columns.Columns class column_items",
            "Column": "v2.widgets.columns.Column class HorizontalSizeStyle widgets",
            "DecoratedText": "v2.widgets.decorated_text.DecoratedText class text topLabel",
            "Image": "v2.widgets.image.Image class imageUrl",
            "TextParagraph": "v2.widgets.text_paragraph.TextParagraph class text",
            "ButtonList": "v2.widgets.button_list.ButtonList class buttons",
            "Button": "v2.widgets.decorated_text.Button class text onClick",
            "OnClick": "v2.widgets.decorated_text.OnClick class openLink",
            # Form input components
            "TextInput": "v2.widgets.text_input.TextInput class name label",
            "SelectionInput": "v2.widgets.selection_input.SelectionInput class name type items",
            "DateTimePicker": "v2.widgets.date_time_picker.DateTimePicker class name label",
            # Grid components
            "Grid": "v2.widgets.grid.Grid class items column_count",
            "GridItem": "v2.widgets.grid.GridItem class title subtitle image",
        }

        for name, query in core_components.items():
            self._find_and_load_component(name, query)

        self._initialized = True
        logger.info(f"SmartCardBuilder initialized with {len(self._components)} components (Qdrant: {self._qdrant_available})")

    def get_component(self, name: str) -> Optional[Any]:
        """Get a loaded component class by name."""
        if not self._initialized:
            self.initialize()

        # Return cached or search for it
        if name in self._components:
            return self._components[name]

        # Try to find via Qdrant
        query = f"v2.widgets.{name.lower()}.{name} class" if name not in ["Section", "Card", "CardHeader"] else f"v2.{name.lower()}.{name} class"
        return self._find_and_load_component(name, query)

    # =========================================================================
    # SMART INFERENCE - Maps content to component parameters
    # =========================================================================

    def infer_content_type(self, text: str) -> Dict[str, Any]:
        """
        Smart inference: Analyze text to determine what type of content it is.

        Returns dict with:
            - type: 'price', 'id', 'date', 'email', 'url', 'image', 'text', 'colored_price'
            - suggested_component: Component name to use
            - suggested_params: Suggested parameters for the component
        """
        # Check for colored price first (most specific)
        if self.CONTENT_PATTERNS["colored_price"].search(text):
            return {
                "type": "colored_price",
                "suggested_component": "DecoratedText",
                "suggested_params": {
                    "text": text,
                    "top_label": "Price",
                    "wrap_text": True,
                },
            }

        # Check for image URLs
        if self.CONTENT_PATTERNS["image_url"].search(text):
            return {
                "type": "image",
                "suggested_component": "Image",
                "suggested_params": {
                    "image_url": text,
                },
            }

        # Check for regular URLs
        if self.CONTENT_PATTERNS["url"].search(text):
            return {
                "type": "url",
                "suggested_component": "DecoratedText",
                "suggested_params": {
                    "text": text,
                    "wrap_text": True,
                    "button": {"text": "Open", "url": text},
                },
            }

        # Check for prices
        if self.CONTENT_PATTERNS["price"].search(text):
            return {
                "type": "price",
                "suggested_component": "DecoratedText",
                "suggested_params": {
                    "text": text,
                    "top_label": "Price",
                    "wrap_text": True,
                },
            }

        # Check for IDs
        if self.CONTENT_PATTERNS["id"].search(text):
            return {
                "type": "id",
                "suggested_component": "DecoratedText",
                "suggested_params": {
                    "text": text.split(":", 1)[-1].strip() if ":" in text else text,
                    "top_label": "ID",
                    "wrap_text": True,
                },
            }

        # Check for dates
        if self.CONTENT_PATTERNS["date"].search(text):
            return {
                "type": "date",
                "suggested_component": "DecoratedText",
                "suggested_params": {
                    "text": text,
                    "top_label": "Date",
                    "wrap_text": True,
                },
            }

        # Check for emails
        if self.CONTENT_PATTERNS["email"].search(text):
            return {
                "type": "email",
                "suggested_component": "DecoratedText",
                "suggested_params": {
                    "text": text,
                    "top_label": "Email",
                    "wrap_text": True,
                },
            }

        # Default to plain text
        return {
            "type": "text",
            "suggested_component": "TextParagraph",
            "suggested_params": {
                "text": text,
            },
        }

    # =========================================================================
    # LAYOUT INFERENCE - Detects composition hints from natural language
    # =========================================================================

    def infer_layout(self, description: str) -> Dict[str, Any]:
        """
        Infer layout from natural language description.

        Returns dict with:
            - layout_type: 'standard', 'columns', 'columns_image_right', 'columns_image_left'
            - column_config: Column configuration if applicable
        """
        # Check for image_left BEFORE image_right (more specific first)
        if self.LAYOUT_PATTERNS["image_left"].search(description):
            return {
                "layout_type": "columns_image_left",
                "column_config": {
                    "left": {"size": "FILL_MINIMUM_SPACE", "content": "image"},
                    "right": {"size": "FILL_AVAILABLE_SPACE", "content": "text"},
                },
            }

        # Check for image on right
        if self.LAYOUT_PATTERNS["image_right"].search(description):
            return {
                "layout_type": "columns_image_right",
                "column_config": {
                    "left": {"size": "FILL_AVAILABLE_SPACE", "content": "text"},
                    "right": {"size": "FILL_MINIMUM_SPACE", "content": "image"},
                },
            }

        # Check for generic columns
        if self.LAYOUT_PATTERNS["columns"].search(description):
            return {
                "layout_type": "columns",
                "column_config": {
                    "left": {"size": "FILL_AVAILABLE_SPACE", "content": "mixed"},
                    "right": {"size": "FILL_AVAILABLE_SPACE", "content": "mixed"},
                },
            }

        # Default to standard layout
        return {
            "layout_type": "standard",
            "column_config": None,
        }

    # =========================================================================
    # COMPONENT BUILDING - Create actual card_framework instances
    # =========================================================================

    def build_decorated_text(
        self,
        text: str,
        top_label: str = None,
        bottom_label: str = None,
        icon: str = None,
        button_url: str = None,
        button_text: str = None,
        wrap_text: bool = True,
    ) -> Optional[Any]:
        """Build a DecoratedText component."""
        DecoratedText = self.get_component("DecoratedText")
        if not DecoratedText:
            return None

        kwargs = {"text": text, "wrap_text": wrap_text}
        if top_label:
            kwargs["top_label"] = top_label
        if bottom_label:
            kwargs["bottom_label"] = bottom_label

        # Handle button
        if button_url:
            Button = self.get_component("Button")
            OnClick = self.get_component("OnClick")
            if Button and OnClick:
                on_click = OnClick(open_link={"url": button_url})
                kwargs["button"] = Button(text=button_text or "Open", on_click=on_click)

        return DecoratedText(**kwargs)

    def build_image(self, image_url: str, alt_text: str = None) -> Optional[Any]:
        """Build an Image component."""
        Image = self.get_component("Image")
        if not Image:
            return None

        kwargs = {"image_url": image_url}
        if alt_text:
            kwargs["alt_text"] = alt_text

        return Image(**kwargs)

    def build_columns(
        self,
        left_widgets: List[Any],
        right_widgets: List[Any],
        left_size: str = "FILL_AVAILABLE_SPACE",
        right_size: str = "FILL_AVAILABLE_SPACE",
    ) -> Optional[Any]:
        """Build a Columns component with two columns."""
        Columns = self.get_component("Columns")
        Column = self.get_component("Column")

        if not Columns or not Column:
            return None

        try:
            left_col = Column(
                horizontal_size_style=getattr(Column.HorizontalSizeStyle, left_size),
                widgets=left_widgets,
            )
            right_col = Column(
                horizontal_size_style=getattr(Column.HorizontalSizeStyle, right_size),
                widgets=right_widgets,
            )

            return Columns(column_items=[left_col, right_col])
        except Exception as e:
            logger.warning(f"Error building columns: {e}")
            return None

    def build_section(
        self,
        header: str = None,
        widgets: List[Any] = None,
    ) -> Optional[Any]:
        """Build a Section component."""
        Section = self.get_component("Section")
        if not Section:
            return None

        kwargs = {}
        if header:
            kwargs["header"] = header
        if widgets:
            kwargs["widgets"] = widgets

        return Section(**kwargs)

    # =========================================================================
    # FORM COMPONENT BUILDING
    # =========================================================================

    def build_text_input(
        self,
        name: str,
        label: str = None,
        hint_text: str = None,
        value: str = None,
        type_: str = "SINGLE_LINE",
    ) -> Optional[Any]:
        """
        Build a TextInput component for form cards.

        Args:
            name: Input field name (required for form submission)
            label: Display label above the input
            hint_text: Placeholder/hint text inside the input
            value: Pre-filled value
            type_: Input type - "SINGLE_LINE" or "MULTIPLE_LINE"

        Returns:
            TextInput component or None
        """
        TextInput = self.get_component("TextInput")
        if not TextInput:
            logger.warning("TextInput component not available")
            return None

        kwargs = {"name": name}
        if label:
            kwargs["label"] = label
        if hint_text:
            kwargs["hint_text"] = hint_text
        if value:
            kwargs["value"] = value

        # Handle type enum
        try:
            if hasattr(TextInput, "Type"):
                kwargs["type"] = getattr(TextInput.Type, type_, TextInput.Type.SINGLE_LINE)
        except Exception as e:
            logger.debug(f"Could not set TextInput type: {e}")

        return TextInput(**kwargs)

    def build_selection_input(
        self,
        name: str,
        label: str = None,
        type_: str = "DROPDOWN",
        items: List[Dict[str, str]] = None,
    ) -> Optional[Any]:
        """
        Build a SelectionInput component for form cards.

        Args:
            name: Input field name (required for form submission)
            label: Display label above the selection
            type_: Selection type - "DROPDOWN", "RADIO_BUTTON", "CHECK_BOX", "SWITCH"
            items: List of {text, value, selected} dicts for options

        Returns:
            SelectionInput component or None
        """
        SelectionInput = self.get_component("SelectionInput")
        if not SelectionInput:
            logger.warning("SelectionInput component not available")
            return None

        kwargs = {"name": name}
        if label:
            kwargs["label"] = label

        # Handle type enum
        try:
            if hasattr(SelectionInput, "Type"):
                kwargs["type"] = getattr(SelectionInput.Type, type_, SelectionInput.Type.DROPDOWN)
        except Exception as e:
            logger.debug(f"Could not set SelectionInput type: {e}")

        # Handle items - need to convert to SelectionItem objects if available
        if items:
            try:
                if hasattr(SelectionInput, "SelectionItem"):
                    selection_items = []
                    for item in items:
                        si = SelectionInput.SelectionItem(
                            text=item.get("text", ""),
                            value=item.get("value", ""),
                            selected=item.get("selected", False),
                        )
                        selection_items.append(si)
                    kwargs["items"] = selection_items
                else:
                    # Fallback to raw dict format
                    kwargs["items"] = items
            except Exception as e:
                logger.debug(f"Could not create SelectionItems: {e}")
                kwargs["items"] = items

        return SelectionInput(**kwargs)

    def build_date_time_picker(
        self,
        name: str,
        label: str = None,
        type_: str = "DATE_AND_TIME",
        value_ms_epoch: int = None,
    ) -> Optional[Any]:
        """
        Build a DateTimePicker component for form cards.

        Args:
            name: Input field name (required for form submission)
            label: Display label above the picker
            type_: Picker type - "DATE_AND_TIME", "DATE_ONLY", "TIME_ONLY"
            value_ms_epoch: Pre-selected value in milliseconds since epoch

        Returns:
            DateTimePicker component or None
        """
        DateTimePicker = self.get_component("DateTimePicker")
        if not DateTimePicker:
            logger.warning("DateTimePicker component not available")
            return None

        kwargs = {"name": name}
        if label:
            kwargs["label"] = label
        if value_ms_epoch:
            kwargs["value_ms_epoch"] = value_ms_epoch

        # Handle type enum
        try:
            if hasattr(DateTimePicker, "Type"):
                kwargs["type"] = getattr(DateTimePicker.Type, type_, DateTimePicker.Type.DATE_AND_TIME)
        except Exception as e:
            logger.debug(f"Could not set DateTimePicker type: {e}")

        return DateTimePicker(**kwargs)

    # =========================================================================
    # GRID COMPONENT BUILDING
    # =========================================================================

    def build_grid(
        self,
        items: List[Dict[str, Any]],
        title: str = None,
        column_count: int = 2,
    ) -> Optional[Dict[str, Any]]:
        """
        Build a Grid widget for displaying items in a grid layout.

        Args:
            items: List of grid item dicts with {title, subtitle, image_url}
            title: Optional grid title
            column_count: Number of columns (default 2)

        Returns:
            Grid widget dict in Google Chat format
        """
        if not items:
            logger.warning("No items provided for grid")
            return None

        grid_items = []
        for i, item in enumerate(items):
            grid_item = {
                "id": item.get("id", f"item_{i}"),
                "title": item.get("title", ""),
            }
            if item.get("subtitle"):
                grid_item["subtitle"] = item["subtitle"]

            if item.get("image_url"):
                grid_item["image"] = {
                    "imageUri": item["image_url"],
                    "altText": item.get("alt_text", item.get("title", "")),
                }

            # Handle click action
            if item.get("url"):
                grid_item["layout"] = "TEXT_BELOW"

            grid_items.append(grid_item)

        grid_widget = {
            "grid": {
                "columnCount": column_count,
                "items": grid_items,
            }
        }

        if title:
            grid_widget["grid"]["title"] = title

        logger.info(f"✅ Built grid with {len(grid_items)} items, {column_count} columns")
        return grid_widget

    def build_grid_from_images(
        self,
        image_urls: List[str],
        titles: List[str] = None,
        column_count: int = 2,
    ) -> Optional[Dict[str, Any]]:
        """
        Build a Grid widget from a list of image URLs.

        Args:
            image_urls: List of image URLs
            titles: Optional list of titles for each image
            column_count: Number of columns (default 2)

        Returns:
            Grid widget dict in Google Chat format
        """
        items = []
        for i, url in enumerate(image_urls):
            item = {
                "image_url": url,
                "title": titles[i] if titles and i < len(titles) else f"Image {i + 1}",
            }
            items.append(item)

        return self.build_grid(items, column_count=column_count)

    # =========================================================================
    # NATURAL LANGUAGE DESCRIPTION PARSING
    # =========================================================================

    def parse_description(self, description: str) -> Dict[str, Any]:
        """
        Parse a natural language description into structured content.

        Extracts sections, items, buttons, and icons from patterns like:
        - "First section titled 'X' showing Y. Second section titled 'Z' showing W."
        - "A status card with check icon showing 'Success' and warning showing 'Alert'"
        - "Include buttons for 'View' linking to https://..."

        Args:
            description: Natural language card description

        Returns:
            Dict with: sections, items, buttons ready for build_card()
        """
        logger.info(f"📝 Parsing description: {description[:100]}...")

        result: Dict[str, Any] = {
            "sections": [],
            "items": [],
            "buttons": [],
        }

        # Try to extract sections first (most structured format)
        sections = self._extract_sections(description)
        if sections:
            result["sections"] = sections
            logger.info(f"✅ Extracted {len(sections)} section(s)")
            return result

        # If no sections, extract items from the description
        items = self._extract_items(description)
        if items:
            result["items"] = items
            logger.info(f"✅ Extracted {len(items)} item(s)")

        # Extract buttons
        buttons = self._extract_buttons(description)
        if buttons:
            result["buttons"] = buttons
            logger.info(f"✅ Extracted {len(buttons)} button(s)")

        return result

    def _extract_sections(self, description: str) -> List[Dict[str, Any]]:
        """
        Extract sections from natural language using ordinal patterns.

        Handles patterns like:
        - "First section titled 'X' showing Y"
        - "Second section titled 'Z' with W"
        """
        sections = []

        # Pattern: "First section titled 'Name' showing/with content"
        ordinal_titled_pattern = re.compile(
            rf"({self.ORDINAL_PATTERN})\s+section\s+titled\s+['\"]([^'\"]+)['\"]?\s*"
            rf"(?:showing|with|containing|displaying)?\s*(.+?)(?=(?:{self.ORDINAL_PATTERN})\s+section|$)",
            re.IGNORECASE | re.DOTALL,
        )

        matches = ordinal_titled_pattern.findall(description)
        if matches:
            for ordinal_word, section_name, section_content in matches:
                logger.info(f"  📋 Section '{section_name}' (ordinal: {ordinal_word})")

                # Parse section content into widgets
                widgets = self._parse_section_content(section_content.strip())

                sections.append({
                    "header": section_name.strip(),
                    "widgets": widgets,
                })

        return sections

    def _extract_items(self, description: str) -> List[Dict[str, Any]]:
        """
        Extract content items from description when no explicit sections.

        Looks for:
        - Icon + text patterns: "check icon showing 'Success'"
        - Quoted text: "showing 'X'"
        - URLs
        - Status messages
        """
        items = []
        description_lower = description.lower()

        # Pattern: icon + text ("check icon showing 'Success'")
        icon_text_pattern = re.compile(
            r"(\w+)\s+icon\s+(?:showing|with|displaying)?\s*['\"]([^'\"]+)['\"]",
            re.IGNORECASE,
        )
        for icon_name, text in icon_text_pattern.findall(description):
            icon_key = icon_name.lower()
            known_icon = self.KNOWN_ICONS.get(icon_key)
            items.append({
                "text": text,
                "icon": known_icon,
                "top_label": icon_name.capitalize() if not known_icon else None,
            })

        # Pattern: labeled content ("Status: Active", "Memory usage at 78%")
        labeled_pattern = re.compile(
            r"['\"]([^'\"]+)['\"]",
            re.IGNORECASE,
        )
        for quoted_text in labeled_pattern.findall(description):
            # Skip if already captured by icon pattern
            if not any(item.get("text") == quoted_text for item in items):
                items.append({"text": quoted_text})

        # Extract URLs with associated text
        url_pattern = re.compile(r"(https?://[^\s\[\]<>\"']+)")
        for url in url_pattern.findall(description):
            # Find text before the URL
            url_pos = description.find(url)
            text_before = description[:url_pos].strip()
            # Get last phrase before URL
            phrases = re.split(r"[.,;]", text_before)
            label = phrases[-1].strip() if phrases else "Link"
            # Clean label
            label = re.sub(r"^\s*(for|to|at|linking|opens?)\s+", "", label, flags=re.IGNORECASE)
            label = re.sub(r"['\"]", "", label).strip()
            if len(label) < 3:
                label = url

            items.append({
                "text": label,
                "button_url": url,
                "button_text": "Open",
            })

        return items

    def _extract_buttons(self, description: str) -> List[Dict[str, str]]:
        """
        Extract button definitions from description.

        Handles patterns like:
        - "button for 'View' linking to https://..."
        - "buttons: 'Join Meeting' -> https://..., 'View Agenda' -> https://..."
        """
        buttons = []

        # Pattern: "button/buttons for 'Text' linking to URL"
        button_pattern = re.compile(
            r"['\"]([^'\"]+)['\"]?\s+(?:button\s+)?(?:linking|links?|opens?|goes?)\s+(?:to\s+)?(https?://[^\s,]+)",
            re.IGNORECASE,
        )
        for text, url in button_pattern.findall(description):
            buttons.append({"text": text.strip(), "url": url.strip()})

        return buttons

    def _parse_section_content(self, content: str) -> List[Dict[str, Any]]:
        """
        Parse section content into widget dictionaries.

        Args:
            content: Raw text content for a section

        Returns:
            List of widget dicts ready for rendering
        """
        widgets = []
        content = content.strip()

        # Clean instructional phrases
        instructional_patterns = [
            r"\bdecorated\s+text\s+(?:showing|with|displaying)\s*",
            r"\bwith\s+(?:a\s+)?(?:link|open)\s+button\b[,.]?\s*",
            r"\bwith\s+(?:a\s+)?(\w+)\s+icon\b[,.]?\s*",
        ]
        mentioned_icons = []
        for pattern in instructional_patterns:
            matches = re.finditer(pattern, content, re.IGNORECASE)
            for match in matches:
                if match.lastindex and match.group(1):
                    mentioned_icons.append(match.group(1).lower())
            content = re.sub(pattern, "", content, flags=re.IGNORECASE)

        # Clean up whitespace
        content = re.sub(r"\s+", " ", content).strip()

        # Extract URLs
        url_pattern = re.compile(r"(https?://[^\s\[\]<>\"']+(?<![.,;:!?\)]))")
        urls = url_pattern.findall(content)

        # Detect content type
        content_lower = content.lower()
        is_warning = any(w in content_lower for w in ["warning", "stale", "inactive", "alert"])
        is_status = any(w in content_lower for w in ["success", "complete", "done", "active", "running"])

        if urls:
            # Content with URLs - create decoratedText with button
            for url in urls:
                # Get text before URL
                url_pos = content.find(url)
                text_before = content[:url_pos].strip() if url_pos > 0 else ""
                text_before = re.sub(r"^\s*(and|at|,|;)\s*", "", text_before, flags=re.IGNORECASE).strip()

                display_text = text_before if len(text_before) > 3 else url

                widget = {
                    "decoratedText": {
                        "text": display_text,
                        "wrapText": True,
                        "button": {
                            "text": "Open",
                            "onClick": {"openLink": {"url": url}}
                        }
                    }
                }

                # Add icon if mentioned
                if mentioned_icons:
                    icon_key = mentioned_icons[0]
                    if icon_key in self.KNOWN_ICONS:
                        widget["decoratedText"]["startIcon"] = {"knownIcon": self.KNOWN_ICONS[icon_key]}

                widgets.append(widget)
                # Update content to process remaining
                content = content[url_pos + len(url):].strip()

        elif is_warning or is_status:
            # Status/warning content (use valid KnownIcon enum values)
            icon = "CONFIRMATION_NUMBER_ICON" if is_status else "STAR"
            widgets.append({
                "decoratedText": {
                    "text": content,
                    "wrapText": True,
                    "startIcon": {"knownIcon": icon},
                }
            })

        elif content:
            # Plain text - check for quoted segments
            quoted_pattern = re.compile(r"['\"]([^'\"]+)['\"]")
            quoted_matches = quoted_pattern.findall(content)

            if quoted_matches:
                for text in quoted_matches:
                    widget = {"decoratedText": {"text": text, "wrapText": True}}
                    if mentioned_icons and mentioned_icons[0] in self.KNOWN_ICONS:
                        widget["decoratedText"]["startIcon"] = {"knownIcon": self.KNOWN_ICONS[mentioned_icons[0]]}
                    widgets.append(widget)
            else:
                # Just use the whole content as text
                widgets.append({"textParagraph": {"text": content}})

        return widgets

    def build_card_from_description(
        self,
        description: str,
        title: str = None,
        subtitle: str = None,
        image_url: str = None,
        text: str = None,
        buttons: List[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Build a complete card by parsing natural language description.

        This is the main entry point that:
        1. Parses description into sections/items
        2. Uses Qdrant to find/load components
        3. Infers layout from description (columns, image positioning)
        4. Renders using component .render() methods

        Args:
            description: Natural language description of card content
            title: Optional card header title
            subtitle: Optional card header subtitle
            image_url: Optional image URL
            text: Optional explicit text content (used in layout inference)
            buttons: Optional list of button dicts [{text, url/onclick_action, type}]

        Returns:
            Rendered card JSON in Google Chat API format
        """
        if not self._initialized:
            self.initialize()

        # Parse description into structured content
        parsed = self.parse_description(description)

        # If we have sections from NLP parsing, build multi-section card
        if parsed.get("sections"):
            return self._build_multi_section_card(
                sections=parsed["sections"],
                title=title,
                subtitle=subtitle,
                image_url=image_url,
                text=text,
                buttons=buttons,
            )

        # Otherwise, build single-section card with items
        # Include explicit text as an item so it participates in layout inference
        items = parsed.get("items", [])
        if text:
            # Convert markdown and add text as first item so it becomes part of text_widgets in build_card()
            converted_text = self.convert_markdown_to_chat(text)
            items.insert(0, converted_text)

        # Merge parsed buttons with explicit buttons
        all_buttons = parsed.get("buttons", [])
        if buttons:
            # Convert button format from card_params to internal format
            for btn in buttons:
                if isinstance(btn, dict):
                    btn_entry = {
                        "text": btn.get("text", "Button"),
                        "url": btn.get("onclick_action") or btn.get("url") or btn.get("action", "#"),
                    }
                    all_buttons.append(btn_entry)

        content = {
            "title": title,
            "subtitle": subtitle,
            "image_url": image_url,
            "items": items,
            "buttons": all_buttons,
        }

        return self.build_card(description, content)

    def _build_multi_section_card(
        self,
        sections: List[Dict[str, Any]],
        title: str = None,
        subtitle: str = None,
        image_url: str = None,
        text: str = None,
        buttons: List[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Build a card with multiple sections.

        Args:
            sections: List of section dicts with 'header' and 'widgets'
            title: Card header title
            subtitle: Card header subtitle
            image_url: Optional image URL (added as widget, NOT in header)
            text: Optional explicit text content (added to first section)
            buttons: Optional list of button dicts (added to last section)

        Returns:
            Rendered card JSON in Google Chat API format (camelCase)

        Note:
            Google Chat does NOT render images in header.imageUrl.
            Images must be placed as widgets in sections.
        """
        rendered_sections = []

        for section_data in sections:
            header = section_data.get("header", "")
            widgets_data = section_data.get("widgets", [])

            # Use the widget dicts directly - they're already in camelCase format
            # Don't convert to component instances as Section.render() outputs snake_case
            if widgets_data:
                section_dict = {"widgets": widgets_data}
                if header:
                    section_dict["header"] = header
                rendered_sections.append(section_dict)

        # Build card structure
        card = {}

        if title:
            card["header"] = {
                "title": title,
                "subtitle": subtitle or "",
            }
            # NOTE: Do NOT put image_url in header - Google Chat doesn't render it there

        # Ensure we have at least one section
        if not rendered_sections:
            rendered_sections = [{"widgets": []}]

        # Add explicit text to first section if provided
        if text:
            # Convert markdown to Google Chat format
            converted_text = self.convert_markdown_to_chat(text)
            text_widget = {"textParagraph": {"text": converted_text}}
            if rendered_sections[0].get("widgets"):
                rendered_sections[0]["widgets"].insert(0, text_widget)
            else:
                rendered_sections[0]["widgets"] = [text_widget]
            logger.info(f"✅ Added text widget to first section: {converted_text[:50]}...")

        # Add image as widget in first section (Google Chat requires images as widgets, not in header)
        if image_url:
            image_widget = {"image": {"imageUrl": image_url}}
            # Insert after text if text was added, otherwise at beginning
            insert_pos = 1 if text else 0
            if rendered_sections[0].get("widgets"):
                rendered_sections[0]["widgets"].insert(insert_pos, image_widget)
            else:
                rendered_sections[0]["widgets"] = [image_widget]
            logger.info(f"✅ Added image widget to first section: {image_url}")

        # Add buttons to last section if provided
        if buttons and isinstance(buttons, list):
            button_widgets = []
            for btn in buttons:
                if isinstance(btn, dict):
                    btn_widget = {"text": btn.get("text", "Button")}
                    onclick = btn.get("onclick_action") or btn.get("url") or btn.get("action")
                    if onclick:
                        btn_widget["onClick"] = {"openLink": {"url": onclick}}
                    btn_type = btn.get("type")
                    if btn_type in ["FILLED", "FILLED_TONAL", "OUTLINED", "BORDERLESS"]:
                        btn_widget["type"] = btn_type
                    button_widgets.append(btn_widget)

            if button_widgets:
                last_section = rendered_sections[-1]
                if "widgets" not in last_section:
                    last_section["widgets"] = []
                last_section["widgets"].append({"buttonList": {"buttons": button_widgets}})
                logger.info(f"✅ Added {len(button_widgets)} button(s) to last section")

        card["sections"] = rendered_sections

        return card

    def _dict_to_widget(self, widget_dict: Dict[str, Any]) -> Optional[Any]:
        """
        Convert a widget dictionary to an actual component instance.

        Args:
            widget_dict: Dict like {"decoratedText": {...}} or {"textParagraph": {...}}

        Returns:
            Instantiated widget component
        """
        if "decoratedText" in widget_dict:
            data = widget_dict["decoratedText"]
            DecoratedText = self.get_component("DecoratedText")
            if not DecoratedText:
                return None

            kwargs = {
                "text": data.get("text", ""),
                "wrap_text": data.get("wrapText", True),
            }

            if data.get("topLabel"):
                kwargs["top_label"] = data["topLabel"]

            if data.get("startIcon"):
                # Convert icon dict to Icon component with enum value
                icon_data = data["startIcon"]
                if "knownIcon" in icon_data:
                    try:
                        Icon = self.get_component("Icon")
                        if Icon and hasattr(Icon, "KnownIcon"):
                            # Convert string to KnownIcon enum value
                            icon_name = icon_data["knownIcon"]
                            known_icon_enum = getattr(Icon.KnownIcon, icon_name, None)
                            if known_icon_enum:
                                kwargs["start_icon"] = Icon(known_icon=known_icon_enum)
                    except Exception as e:
                        logger.debug(f"Could not create icon: {e}")

            if data.get("button"):
                btn_data = data["button"]
                Button = self.get_component("Button")
                OnClick = self.get_component("OnClick")
                if Button and OnClick and btn_data.get("onClick", {}).get("openLink", {}).get("url"):
                    url = btn_data["onClick"]["openLink"]["url"]
                    on_click = OnClick(open_link={"url": url})
                    kwargs["button"] = Button(text=btn_data.get("text", "Open"), on_click=on_click)

            return DecoratedText(**kwargs)

        elif "textParagraph" in widget_dict:
            data = widget_dict["textParagraph"]
            TextParagraph = self.get_component("TextParagraph")
            if TextParagraph:
                return TextParagraph(text=data.get("text", ""))

        elif "buttonList" in widget_dict:
            data = widget_dict["buttonList"]
            ButtonList = self.get_component("ButtonList")
            Button = self.get_component("Button")
            OnClick = self.get_component("OnClick")

            if ButtonList and Button and OnClick:
                buttons = []
                for btn_data in data.get("buttons", []):
                    url = btn_data.get("onClick", {}).get("openLink", {}).get("url", "#")
                    on_click = OnClick(open_link={"url": url})
                    buttons.append(Button(text=btn_data.get("text", "Click"), on_click=on_click))
                if buttons:
                    return ButtonList(buttons=buttons)

        return None

    # =========================================================================
    # MAIN CARD BUILDING
    # =========================================================================

    def build_card(
        self,
        description: str,
        content: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Build a complete card from description and content.

        Args:
            description: Natural language description (used for layout inference)
            content: Dict with card content:
                - title: Card title
                - subtitle: Card subtitle
                - section_header: Section header
                - items: List of content items (text, prices, etc.)
                - image_url: Optional image URL
                - buttons: Optional list of {text, url} dicts

        Returns:
            Rendered card JSON ready for Google Chat API
        """
        if not self._initialized:
            self.initialize()

        # Infer layout from description
        layout = self.infer_layout(description)
        logger.info(f"Inferred layout: {layout['layout_type']}")

        # Build widgets based on content
        widgets = []
        text_widgets = []
        image_widget = None

        # Process items with smart inference
        for item in content.get("items", []):
            if isinstance(item, str):
                inference = self.infer_content_type(item)
                logger.debug(f"Inferred '{item[:30]}...' as {inference['type']}")

                if inference["suggested_component"] == "Image":
                    image_widget = self.build_image(inference["suggested_params"]["image_url"])
                elif inference["suggested_component"] == "DecoratedText":
                    params = inference["suggested_params"]
                    widget = self.build_decorated_text(
                        text=params.get("text", item),
                        top_label=params.get("top_label"),
                        wrap_text=params.get("wrap_text", True),
                    )
                    if widget:
                        text_widgets.append(widget)
                else:
                    # Default to TextParagraph
                    TextParagraph = self.get_component("TextParagraph")
                    if TextParagraph:
                        text_widgets.append(TextParagraph(text=item))

            elif isinstance(item, dict):
                # Explicit widget specification
                if "text" in item:
                    widget = self.build_decorated_text(
                        text=item["text"],
                        top_label=item.get("top_label") or item.get("label"),
                        bottom_label=item.get("bottom_label"),
                        button_url=item.get("button_url") or item.get("url"),
                        button_text=item.get("button_text"),
                        icon=item.get("icon"),
                    )
                    if widget:
                        text_widgets.append(widget)
                elif "image_url" in item:
                    image_widget = self.build_image(
                        item["image_url"],
                        item.get("alt_text"),
                    )

        # Handle explicit image_url in content
        if content.get("image_url") and not image_widget:
            image_widget = self.build_image(content["image_url"])

        # Build layout based on inference
        if layout["layout_type"] == "columns_image_right" and image_widget:
            # Text on left, image on right
            columns = self.build_columns(
                left_widgets=text_widgets,
                right_widgets=[image_widget],
                left_size="FILL_AVAILABLE_SPACE",
                right_size="FILL_MINIMUM_SPACE",
            )
            if columns:
                widgets.append(columns)
            else:
                widgets.extend(text_widgets)
                widgets.append(image_widget)

        elif layout["layout_type"] == "columns_image_left" and image_widget:
            # Image on left, text on right
            columns = self.build_columns(
                left_widgets=[image_widget],
                right_widgets=text_widgets,
                left_size="FILL_MINIMUM_SPACE",
                right_size="FILL_AVAILABLE_SPACE",
            )
            if columns:
                widgets.append(columns)
            else:
                widgets.append(image_widget)
                widgets.extend(text_widgets)

        elif layout["layout_type"] == "columns":
            # Generic two-column layout - split widgets evenly
            mid = len(text_widgets) // 2
            columns = self.build_columns(
                left_widgets=text_widgets[:mid] or text_widgets,
                right_widgets=text_widgets[mid:] if mid > 0 else [],
            )
            if columns:
                widgets.append(columns)
                if image_widget:
                    widgets.append(image_widget)
            else:
                widgets.extend(text_widgets)
                if image_widget:
                    widgets.append(image_widget)

        else:
            # Standard layout - widgets stacked vertically
            widgets.extend(text_widgets)
            if image_widget:
                widgets.append(image_widget)

        # Add buttons if provided
        if content.get("buttons"):
            ButtonList = self.get_component("ButtonList")
            Button = self.get_component("Button")
            OnClick = self.get_component("OnClick")

            if ButtonList and Button and OnClick:
                buttons = []
                for btn in content["buttons"]:
                    on_click = OnClick(open_link={"url": btn.get("url", "#")})
                    buttons.append(Button(text=btn.get("text", "Click"), on_click=on_click))

                if buttons:
                    widgets.append(ButtonList(buttons=buttons))

        # Build section
        section = self.build_section(
            header=content.get("section_header", ""),
            widgets=widgets,
        )

        if not section:
            logger.error("Failed to build section")
            return {}

        # Render to JSON
        rendered = section.render()

        # Wrap in card structure if title provided
        if content.get("title"):
            return {
                "header": {
                    "title": content["title"],
                    "subtitle": content.get("subtitle", ""),
                },
                "sections": [rendered],
            }

        return rendered

    # =========================================================================
    # HELPER: Format colored price
    # =========================================================================

    def format_price(
        self,
        original_price: str,
        sale_price: str,
        original_color: str = "red",
        sale_color: str = "green",
    ) -> str:
        """
        Format a price with colors for display.

        Example:
            format_price("$199.00", "$99.00")
            Returns: '<font color="#34a853">$99.00</font> <s>$199.00</s>'
        """
        original_hex = self.COLOR_MAP.get(original_color, original_color)
        sale_hex = self.COLOR_MAP.get(sale_color, sale_color)

        return f'<font color="{sale_hex}">{sale_price}</font> <s>{original_price}</s>'

    def format_colored_text(self, text: str, color: str) -> str:
        """
        Wrap text in font color tag.

        Example:
            format_colored_text("Success!", "green")
            Returns: '<font color="#34a853">Success!</font>'
        """
        hex_color = self.COLOR_MAP.get(color, color)
        return f'<font color="{hex_color}">{text}</font>'

    # =========================================================================
    # HELPER: Markdown conversion for Google Chat
    # =========================================================================

    @staticmethod
    def convert_markdown_to_chat(text: str) -> str:
        """
        Convert standard markdown to Google Chat HTML format.

        Google Chat textParagraph supports HTML tags:
        - <b>bold</b>
        - <i>italic</i>
        - <s>strikethrough</s>
        - <u>underline</u>
        - <font color="#hex">colored text</font>
        - <a href="url">link</a>

        Args:
            text: Text with standard markdown

        Returns:
            Text converted to HTML for Google Chat
        """
        if not text:
            return text

        # Convert **bold** to <b>bold</b>
        text = re.sub(r'\*\*([^*]+)\*\*', r'<b>\1</b>', text)

        # Convert *bold* (single asterisk) to <b>bold</b> - but not if part of bullet
        # Only match *text* where text doesn't start with space (to avoid matching "• *")
        text = re.sub(r'(?<!\*)\*([^*\s][^*]*[^*\s])\*(?!\*)', r'<b>\1</b>', text)
        # Also handle single-word bold like *word*
        text = re.sub(r'(?<!\*)\*(\w+)\*(?!\*)', r'<b>\1</b>', text)

        # Convert ~~strikethrough~~ to <s>strikethrough</s>
        text = re.sub(r'~~([^~]+)~~', r'<s>\1</s>', text)

        # Convert ~strikethrough~ (single tilde) to <s>strikethrough</s>
        text = re.sub(r'(?<!~)~([^~\s][^~]*[^~\s])~(?!~)', r'<s>\1</s>', text)

        # Convert _italic_ to <i>italic</i>
        text = re.sub(r'(?<!_)_([^_\s][^_]*[^_\s])_(?!_)', r'<i>\1</i>', text)
        # Also handle single-word italic like _word_
        text = re.sub(r'(?<!_)_(\w+)_(?!_)', r'<i>\1</i>', text)

        # Convert __bold__ (double underscore sometimes used for bold)
        text = re.sub(r'__([^_]+)__', r'<b>\1</b>', text)

        # Convert `code` to monospace (Google Chat doesn't have code tag, use as-is)
        # text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)

        return text


# Global instance for convenience
_builder: Optional[SmartCardBuilder] = None


def get_smart_card_builder() -> SmartCardBuilder:
    """Get the global SmartCardBuilder instance."""
    global _builder
    if _builder is None:
        _builder = SmartCardBuilder()
        _builder.initialize()
    return _builder


def build_card(description: str, content: Dict[str, Any]) -> Dict[str, Any]:
    """Convenience function to build a card."""
    builder = get_smart_card_builder()
    return builder.build_card(description, content)
