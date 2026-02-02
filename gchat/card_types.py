"""
Type definitions for unified card tool responses.

These Pydantic BaseModel classes define the structure of data returned by the
send_dynamic_card tool, enabling FastMCP to automatically generate JSON schemas
with rich field descriptions for better MCP client integration.

The types capture the complex NLP-extracted card structures including sections,
widgets, icons, and buttons that the unified card tool supports.
"""

from pydantic import BaseModel, Field
from typing_extensions import Any, Dict, List, Literal, Optional

# =============================================================================
# Widget Types - Building blocks for card sections
# =============================================================================


class ButtonConfig(BaseModel):
    """Configuration for a card button widget.

    Buttons can open URLs, trigger actions, or submit forms. They support
    different visual styles through the 'type' field.
    """

    text: str = Field(
        ...,
        description="Button label text displayed to users",
        max_length=100,
    )
    url: Optional[str] = Field(
        None,
        description="URL to open when button is clicked (creates openLink onClick action)",
    )
    action: Optional[str] = Field(
        None,
        description="Alternative to 'url' - action identifier or URL for onClick",
    )
    type: Optional[Literal["FILLED", "FILLED_TONAL", "OUTLINED", "BORDERLESS"]] = Field(
        None,
        description="Button visual style. FILLED: solid primary color, FILLED_TONAL: lighter fill, OUTLINED: border only, BORDERLESS: text only",
    )


class IconConfig(BaseModel):
    """Configuration for Google Chat card icons.

    Icons can be specified as known Google icons (by name) or custom icons (by URL).
    The unified card tool supports natural language icon descriptions that map to
    known icons (e.g., 'green check' -> CHECK_CIRCLE).
    """

    knownIcon: Optional[str] = Field(
        None,
        description="Google Chat known icon name (e.g., CHECK_CIRCLE, STAR, ERROR, WARNING, INFO, PERSON, EMAIL, CLOCK). Natural language mappings: 'check/success' -> CHECK_CIRCLE, 'error/failure' -> ERROR, 'warning' -> WARNING, 'info' -> INFO, 'star/favorite' -> STAR, 'person/user' -> PERSON, 'email/mail' -> EMAIL, 'clock/time' -> CLOCK",
    )
    iconUrl: Optional[str] = Field(
        None,
        description="URL to a custom icon image (mutually exclusive with knownIcon)",
    )


class DecoratedTextConfig(BaseModel):
    """Configuration for a decoratedText widget.

    DecoratedText is a rich text widget that supports labels, icons, buttons,
    and switches. It's commonly used for displaying structured information
    like status indicators, metrics, or settings.
    """

    text: str = Field(
        ...,
        description="Main text content of the decorated text widget",
        max_length=4000,
    )
    topLabel: Optional[str] = Field(
        None,
        description="Label displayed above the main text (e.g., 'Status', 'Response Time')",
        max_length=200,
    )
    bottomLabel: Optional[str] = Field(
        None,
        description="Label displayed below the main text",
        max_length=200,
    )
    icon: Optional[IconConfig] = Field(
        None,
        description="Icon displayed alongside the text (startIcon position)",
    )
    button: Optional[ButtonConfig] = Field(
        None,
        description="Optional button displayed at the end of the widget",
    )
    wrapText: Optional[bool] = Field(
        None,
        description="Whether to wrap long text content",
    )


class TextParagraphConfig(BaseModel):
    """Configuration for a textParagraph widget."""

    text: str = Field(
        ...,
        description="Text content, supports HTML formatting (max 4000 chars)",
        max_length=4000,
    )


class ImageConfig(BaseModel):
    """Configuration for an image widget.

    Note: Images cannot be placed in card headers - they must be widgets in sections.
    """

    imageUrl: str = Field(
        ...,
        description="URL of the image to display",
    )
    altText: Optional[str] = Field(
        None,
        description="Alt text for accessibility",
    )


class WidgetConfig(BaseModel):
    """Union type for any widget that can appear in a card section.

    Each card section contains a list of widgets. Only one widget type
    should be populated per WidgetConfig instance.
    """

    textParagraph: Optional[TextParagraphConfig] = Field(
        None,
        description="Simple text paragraph widget",
    )
    decoratedText: Optional[DecoratedTextConfig] = Field(
        None,
        description="Rich text with labels, icons, and buttons",
    )
    image: Optional[ImageConfig] = Field(
        None,
        description="Image widget (cannot be in header, must be in section)",
    )
    buttonList: Optional[Dict[str, List[ButtonConfig]]] = Field(
        None,
        description="List of buttons (max 6 per buttonList). Format: {'buttons': [...]}",
    )
    divider: Optional[Dict[str, Any]] = Field(
        None,
        description="Horizontal divider line between widgets",
    )


# =============================================================================
# Section and Card Structure Types
# =============================================================================


class SectionConfig(BaseModel):
    """Configuration for a card section.

    Cards are organized into sections, each containing a list of widgets.
    Sections can have headers and can be collapsible.
    """

    header: Optional[str] = Field(
        None,
        description="Section header text (displayed as section title)",
    )
    collapsible: Optional[bool] = Field(
        None,
        description="Whether the section can be collapsed/expanded by users",
    )
    uncollapsibleWidgetsCount: Optional[int] = Field(
        None,
        description="Number of widgets to show when collapsed (rest hidden until expanded)",
    )
    widgets: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="List of widgets in this section. Each widget is a dict with a widget type key (textParagraph, decoratedText, buttonList, image, divider)",
    )


class CardHeaderConfig(BaseModel):
    """Configuration for a card header."""

    title: str = Field(
        ...,
        description="Card title (max 200 chars)",
        max_length=200,
    )
    subtitle: Optional[str] = Field(
        None,
        description="Card subtitle displayed below title (max 200 chars)",
        max_length=200,
    )
    imageUrl: Optional[str] = Field(
        None,
        description="Note: Header imageUrl often doesn't render - use image widgets in sections instead",
    )
    imageType: Optional[Literal["CIRCLE", "SQUARE"]] = Field(
        None,
        description="Shape of header image if provided",
    )


class CardParams(BaseModel):
    """Parameters for card creation passed to send_dynamic_card.

    These explicit parameters override any NLP-extracted parameters from card_description.
    You can provide structured card data here for precise control, or rely on the
    NLP parser to extract structure from natural language descriptions.
    """

    title: Optional[str] = Field(
        None,
        description="Card header title (overrides NLP-extracted title)",
        max_length=200,
    )
    subtitle: Optional[str] = Field(
        None,
        description="Card header subtitle (overrides NLP-extracted subtitle)",
        max_length=200,
    )
    text: Optional[str] = Field(
        None,
        description="Simple text content for single-widget cards (overrides NLP-extracted text)",
        max_length=4000,
    )
    image_url: Optional[str] = Field(
        None,
        description="Image URL for image widget (images go in sections, not headers)",
    )
    image_alt_text: Optional[str] = Field(
        None,
        description="Alt text for the image widget",
    )
    buttons: Optional[List[ButtonConfig]] = Field(
        None,
        description="List of button configurations (max 6 per buttonList)",
    )
    sections: Optional[List[SectionConfig]] = Field(
        None,
        description="Explicit section structure with widgets. When provided, gives full control over card layout. NLP can also extract sections from numbered/bulleted lists in card_description.",
    )


# =============================================================================
# NLP Extraction Info Types
# =============================================================================


class NLPExtractionInfo(BaseModel):
    """Information about what was extracted from natural language description."""

    extractedTitle: Optional[str] = Field(
        None,
        description="Title extracted from natural language description",
    )
    extractedSubtitle: Optional[str] = Field(
        None,
        description="Subtitle extracted from natural language description",
    )
    extractedSectionCount: int = Field(
        0,
        description="Number of sections extracted from description (from numbered/bulleted lists)",
    )
    extractedButtonCount: int = Field(
        0,
        description="Number of buttons extracted from description",
    )
    extractedIconCount: int = Field(
        0,
        description="Number of icons mapped from natural language (e.g., 'green check' -> CHECK_CIRCLE)",
    )
    decoratedTextCount: int = Field(
        0,
        description="Number of decoratedText widgets created from description",
    )
    parsingSuccessful: bool = Field(
        True,
        description="Whether NLP parsing completed without errors",
    )
    parsingWarnings: Optional[List[str]] = Field(
        None,
        description="Any warnings during NLP extraction",
    )


class DSLValidationInfo(BaseModel):
    """DSL structure validation results."""

    is_valid: bool = Field(..., description="Whether DSL structure is valid")
    dsl_input: Optional[str] = Field(None, description="The extracted DSL string")
    expanded_notation: Optional[str] = Field(
        None,
        description="Human-readable expansion: Section[DecoratedText×3, ButtonList[Button×2]]",
    )
    component_counts: Dict[str, int] = Field(
        default_factory=dict,
        description="Count per component: {'DecoratedText': 3, 'Button': 2}",
    )
    issues: List[str] = Field(default_factory=list, description="Validation issues found")
    suggestions: List[str] = Field(default_factory=list, description="Suggested fixes")


class InputMappingInfo(BaseModel):
    """How inputs were mapped to components."""

    mappings: List[Dict[str, str]] = Field(
        default_factory=list,
        description="List of {input, value_preview, component, field}",
    )
    unconsumed: Dict[str, int] = Field(
        default_factory=dict,
        description="Count of unconsumed inputs: {'buttons': 1, 'texts': 0}",
    )


class ExpectedParamsInfo(BaseModel):
    """Expected parameters for detected components."""

    by_component: Dict[str, Dict[str, str]] = Field(
        default_factory=dict,
        description="Params per component: {'DecoratedText': {'text': 'Main text'}}",
    )
    common_params: Dict[str, str] = Field(
        default_factory=dict,
        description="Cross-component params: {'title': 'Card title', 'buttons': '...'}",
    )


class ComponentSearchInfo(BaseModel):
    """Information about ModuleWrapper component search results."""

    componentFound: bool = Field(
        ...,
        description="Whether a matching component was found via semantic search",
    )
    componentName: Optional[str] = Field(
        None,
        description="Name of the matched component (e.g., 'Card', 'DecoratedText')",
    )
    componentPath: Optional[str] = Field(
        None,
        description="Full module path of the matched component",
    )
    componentType: Optional[
        Literal[
            "class",
            "function",
            "module",
            "simple_fallback",
            "fallback",
            "nlp_sections",
            "smart_builder",
            "card_builder_v2",
            "dsl_builder",
        ]
    ] = Field(
        None,
        description="Type of component found: 'class' for Card/Widget classes, 'function' for factory functions, 'module' for module-level components, 'simple_fallback' when no match found, 'nlp_sections' for NLP-parsed multi-section cards, 'smart_builder' for SmartCardBuilder with Qdrant vector search, 'card_builder_v2' for DSL-based card construction, 'dsl_builder' for structure DSL parsing",
    )
    searchScore: Optional[float] = Field(
        None,
        description="Semantic search similarity score (0.0-1.0, higher is better match)",
    )
    extractedFromModule: Optional[str] = Field(
        None,
        description="If component was extracted from a module, the module name",
    )


# =============================================================================
# Response Types
# =============================================================================


class SendDynamicCardResponse(BaseModel):
    """Response structure for send_dynamic_card tool.

    This response provides comprehensive information about the card creation
    and delivery process, including NLP extraction details, component search
    results, and delivery status.
    """

    success: bool = Field(
        ...,
        description="Whether the card was successfully created and sent",
    )
    messageId: Optional[str] = Field(
        None,
        description="Google Chat message ID (format: spaces/{space}/messages/{message})",
    )
    spaceId: Optional[str] = Field(
        None,
        description="Target Google Chat space ID (optional for webhook delivery)",
    )
    deliveryMethod: Literal["api", "webhook"] = Field(
        ...,
        description="How the card was delivered: 'api' for authenticated Chat API, 'webhook' for webhook URL",
    )
    cardType: str = Field(
        ...,
        description="Type of card component used: 'class', 'function', 'simple_fallback', etc.",
    )
    componentInfo: Optional[ComponentSearchInfo] = Field(
        None,
        description="Details about the ModuleWrapper component search and matching",
    )
    nlpExtraction: Optional[NLPExtractionInfo] = Field(
        None,
        description="Details about what was extracted from the natural language card_description",
    )
    cardDescription: str = Field(
        ...,
        description="The original card_description input that was processed",
    )
    threadKey: Optional[str] = Field(
        None,
        description="Thread key if message was sent as a thread reply",
    )
    webhookUrl: Optional[str] = Field(
        None,
        description="Webhook URL used for delivery (if webhook method)",
    )
    createTime: Optional[str] = Field(
        None,
        description="Timestamp when the message was created (from API response)",
    )
    userEmail: str = Field(
        ...,
        description="Google email address used for authentication",
    )
    httpStatus: Optional[int] = Field(
        None,
        description="HTTP status code from webhook delivery (200=success, 429=rate limited)",
    )
    validationPassed: bool = Field(
        True,
        description="Whether pre-send card content validation passed (prevents blank cards)",
    )
    validationIssues: Optional[List[str]] = Field(
        None,
        description="List of validation issues if validation failed",
    )
    jinjaTemplateApplied: bool = Field(
        False,
        description="Whether Jinja2 template styling was applied to card content",
    )
    dslDetected: Optional[str] = Field(
        None,
        description="DSL structure detected in card_description (if any)",
    )
    renderedDslNotation: Optional[str] = Field(
        None,
        description="DSL symbol notation representing the rendered card structure. "
        "Use this to learn the DSL syntax for future calls. "
        "Format: §[components] where § is Section, δ is DecoratedText, Ƀ is ButtonList, etc.",
    )
    dslValidation: Optional[DSLValidationInfo] = Field(
        None, description="DSL validation results if DSL detected in description"
    )
    inputMapping: Optional[InputMappingInfo] = Field(
        None, description="How card_params inputs were distributed to components"
    )
    expectedParams: Optional[ExpectedParamsInfo] = Field(
        None, description="What card_params this DSL structure accepts"
    )
    suggestedDsl: Optional[str] = Field(
        None, description="Suggested DSL when params provided but no DSL in description"
    )
    alternativeDsl: Optional[List[str]] = Field(
        None,
        description="Alternative valid DSL patterns using similar components. "
        "Use these for inspiration on different card structures.",
    )
    message: str = Field(
        ...,
        description="Human-readable status message describing the result",
    )
    error: Optional[str] = Field(
        None,
        description="Error message if the operation failed",
    )


# =============================================================================
# Icon Mapping Reference (for documentation)
# =============================================================================


class IconMapping(BaseModel):
    """Reference for natural language to Google Chat icon mappings.

    The NLP parser supports these mappings from natural language descriptions
    to Google Chat known icons. Use these descriptions in card_description
    for automatic icon resolution.
    """

    naturalLanguage: List[str] = Field(
        ...,
        description="Natural language terms that map to this icon",
    )
    googleChatIcon: str = Field(
        ...,
        description="Google Chat knownIcon value",
    )


# Pre-defined icon mappings for reference
ICON_MAPPINGS: List[IconMapping] = [
    IconMapping(
        naturalLanguage=["check", "green check", "success", "complete", "done"],
        googleChatIcon="CHECK_CIRCLE",
    ),
    IconMapping(
        naturalLanguage=["error", "red x", "failure", "failed", "x"],
        googleChatIcon="ERROR",
    ),
    IconMapping(
        naturalLanguage=["warning", "yellow warning", "caution", "alert"],
        googleChatIcon="WARNING",
    ),
    IconMapping(
        naturalLanguage=["info", "information", "details", "about"],
        googleChatIcon="INFO",
    ),
    IconMapping(
        naturalLanguage=["star", "favorite", "starred", "important"],
        googleChatIcon="STAR",
    ),
    IconMapping(
        naturalLanguage=["person", "user", "profile", "account"],
        googleChatIcon="PERSON",
    ),
    IconMapping(
        naturalLanguage=["email", "mail", "envelope", "message"], googleChatIcon="EMAIL"
    ),
    IconMapping(
        naturalLanguage=["clock", "time", "schedule", "timer"], googleChatIcon="CLOCK"
    ),
    IconMapping(
        naturalLanguage=["calendar", "date", "event"], googleChatIcon="EVENT_SEAT"
    ),
    IconMapping(naturalLanguage=["phone", "call", "telephone"], googleChatIcon="PHONE"),
    IconMapping(
        naturalLanguage=["video", "camera", "meeting"], googleChatIcon="VIDEO_CAMERA"
    ),
    IconMapping(
        naturalLanguage=["location", "map", "place", "pin"], googleChatIcon="MAP_PIN"
    ),
    IconMapping(naturalLanguage=["link", "chain", "url"], googleChatIcon="LINK"),
    IconMapping(
        naturalLanguage=["file", "document", "doc"], googleChatIcon="DESCRIPTION"
    ),
    IconMapping(naturalLanguage=["folder", "directory"], googleChatIcon="FOLDER"),
    IconMapping(
        naturalLanguage=["settings", "gear", "config"], googleChatIcon="SETTINGS"
    ),
    IconMapping(
        naturalLanguage=["chart", "graph", "analytics"], googleChatIcon="TRENDING_UP"
    ),
    IconMapping(naturalLanguage=["cloud", "upload", "sync"], googleChatIcon="CLOUD"),
    IconMapping(naturalLanguage=["lock", "secure", "private"], googleChatIcon="LOCK"),
    IconMapping(
        naturalLanguage=["unlock", "open", "public"], googleChatIcon="LOCK_OPEN"
    ),
]
