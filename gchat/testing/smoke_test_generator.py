"""
Smoke Test Generator for Google Chat Cards

Generates random card configurations that satisfy minimum requirements:
- At least 6 components total
- 2 text components (DecoratedText, TextParagraph)
- 4 clickable components (Buttons with webhook callbacks)

Uses ModuleWrapper's component hierarchy to ensure valid card structures.
"""

import random
import uuid
import httpx
import asyncio
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime

from config.enhanced_logging import setup_logger

logger = setup_logger()


# =============================================================================
# COMPONENT POOLS
# =============================================================================

# Text components that can display content
TEXT_COMPONENTS = [
    "DecoratedText",
    "TextParagraph",
]

# Clickable/interactive components
CLICKABLE_COMPONENTS = [
    "Button",
]

# Optional extra components for variety (no free-form text inputs)
OPTIONAL_COMPONENTS = [
    "Image",
    "Divider",
    "Icon",
    "Grid",
    "SelectionInput",
    "DateTimePicker",
]

# Sample content for text components
SAMPLE_TEXT_CONTENT = [
    "Welcome to the smoke test",
    "This card was randomly generated",
    "Testing component rendering",
    "All systems operational",
    "Component validation in progress",
    "Random card #{random_id}",
    "Generated at {timestamp}",
    "Smoke test iteration #{iteration}",
]

# =============================================================================
# FEEDBACK CARD CONTENT POOLS (imported from SmartCardBuilder - Single Source of Truth)
# =============================================================================
from gchat.smart_card_builder import (
    CONTENT_FEEDBACK_PROMPTS,
    FORM_FEEDBACK_PROMPTS,
    POSITIVE_LABELS,
    NEGATIVE_LABELS,
)

# Random card titles for feedback testing
FEEDBACK_CARD_TITLES = [
    "Product Details",
    "Order Summary",
    "Event Information",
    "Task Status",
    "Meeting Notes",
    "Report Summary",
    "Update Notification",
    "Alert Details",
]

# Random card content themes
CONTENT_THEMES = [
    {
        "title": "Product Update",
        "items": ["New features released", "Bug fixes applied", "Performance improved"],
        "icon": "STAR",
    },
    {
        "title": "Order Status",
        "items": ["Order #12345 confirmed", "Shipping in progress", "Estimated delivery: Tomorrow"],
        "icon": "SHOPPING_BAG",
    },
    {
        "title": "Meeting Reminder",
        "items": ["Team Sync at 3pm", "Conference Room A", "Agenda: Q1 Review"],
        "icon": "CLOCK",
    },
    {
        "title": "Task Complete",
        "items": ["Code review done", "Tests passing", "Ready for merge"],
        "icon": "CONFIRMATION_NUMBER",
    },
    {
        "title": "Alert Summary",
        "items": ["3 new notifications", "1 high priority", "Action required"],
        "icon": "NOTIFICATIONS",
    },
]

# Sample button labels
SAMPLE_BUTTON_LABELS = [
    "Action 1",
    "Action 2",
    "Action 3",
    "Action 4",
    "Click Me",
    "Submit",
    "Confirm",
    "Cancel",
    "Next",
    "Previous",
    "Test Button",
    "Webhook Test",
]

# Sample images (reliable placeholder URLs from picsum.photos)
# Using specific image IDs for consistent, working images
SAMPLE_IMAGES = [
    "https://picsum.photos/id/1/200/200",   # Laptop on desk
    "https://picsum.photos/id/20/200/200",  # Cup of coffee
    "https://picsum.photos/id/42/200/200",  # Camera
    "https://picsum.photos/id/60/200/200",  # Office desk
    "https://picsum.photos/id/180/200/200", # Workspace
    "https://picsum.photos/id/237/200/200", # Dog
]


@dataclass
class SmokeTestConfig:
    """Configuration for smoke test generation."""
    min_text_components: int = 2
    min_clickable_components: int = 4
    max_extra_components: int = 2
    webhook_url: Optional[str] = None
    include_image: bool = False
    include_divider: bool = True
    test_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])


@dataclass
class SmokeTestResult:
    """Result of a smoke test execution."""
    test_id: str
    card_json: Dict[str, Any]
    component_count: int
    text_count: int
    clickable_count: int
    webhook_responses: List[Dict[str, Any]] = field(default_factory=list)
    success: bool = False
    error: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


class SmokeTestGenerator:
    """
    Generates random Google Chat cards for smoke testing.

    Uses SmartCardBuilder and ModuleWrapper to ensure valid card structures.
    """

    def __init__(self):
        self._builder = None
        self._wrapper = None
        self._relationships = None

    def _get_builder(self):
        """Get SmartCardBuilder singleton."""
        if self._builder is None:
            from gchat.smart_card_builder import SmartCardBuilder
            self._builder = SmartCardBuilder()
        return self._builder

    def _get_wrapper(self):
        """Get ModuleWrapper singleton."""
        if self._wrapper is None:
            from gchat.card_framework_wrapper import get_card_framework_wrapper
            self._wrapper = get_card_framework_wrapper()
        return self._wrapper

    def _get_relationships(self) -> Dict[str, List[str]]:
        """Get component relationships from ModuleWrapper."""
        if self._relationships is None:
            wrapper = self._get_wrapper()
            self._relationships = wrapper.relationships
        return self._relationships

    # =========================================================================
    # RANDOM CONTENT GENERATORS
    # =========================================================================

    def _random_text_content(self, iteration: int = 0) -> str:
        """Generate random text content."""
        template = random.choice(SAMPLE_TEXT_CONTENT)
        return template.format(
            random_id=random.randint(1000, 9999),
            timestamp=datetime.now().strftime("%H:%M:%S"),
            iteration=iteration,
        )

    def _random_button_label(self, index: int = 0) -> str:
        """Generate random button label."""
        labels = SAMPLE_BUTTON_LABELS.copy()
        random.shuffle(labels)
        return labels[index % len(labels)]

    def _random_image_url(self) -> str:
        """Get a random sample image URL."""
        return random.choice(SAMPLE_IMAGES)

    # =========================================================================
    # COMPONENT BUILDERS
    # =========================================================================

    def _build_text_widget(
        self,
        component_type: str,
        content: str,
        with_icon: bool = False,
    ) -> Dict[str, Any]:
        """Build a text component widget."""
        if component_type == "DecoratedText":
            widget = {
                "decoratedText": {
                    "text": content,
                    "wrapText": True,
                }
            }
            if with_icon:
                widget["decoratedText"]["startIcon"] = {
                    "knownIcon": random.choice(["STAR", "BOOKMARK", "DESCRIPTION", "EMAIL"])
                }
            return widget
        elif component_type == "TextParagraph":
            return {
                "textParagraph": {
                    "text": content,
                }
            }
        else:
            # Fallback to decorated text
            return {
                "decoratedText": {
                    "text": content,
                    "wrapText": True,
                }
            }

    def _build_button_widget(
        self,
        label: str,
        webhook_url: Optional[str] = None,
        button_index: int = 0,
        test_id: str = "",
    ) -> Dict[str, Any]:
        """Build a single button."""
        button = {"text": label}

        if webhook_url:
            # Add webhook callback URL with test metadata
            callback_url = f"{webhook_url}?test_id={test_id}&button_index={button_index}&action={label.lower().replace(' ', '_')}"
            button["onClick"] = {
                "openLink": {"url": callback_url}
            }

        return button

    def _build_button_list(
        self,
        buttons: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Wrap buttons in a buttonList widget."""
        return {
            "buttonList": {
                "buttons": buttons
            }
        }

    def _build_divider(self) -> Dict[str, Any]:
        """Build a divider widget."""
        return {"divider": {}}

    def _build_image(self, url: str, alt_text: str = "Test image") -> Dict[str, Any]:
        """Build an image widget."""
        return {
            "image": {
                "imageUrl": url,
                "altText": alt_text,
            }
        }

    # =========================================================================
    # CARD GENERATION
    # =========================================================================

    def generate_card(
        self,
        config: SmokeTestConfig,
        iteration: int = 0,
    ) -> Dict[str, Any]:
        """
        Generate a random card that satisfies the smoke test requirements.

        Args:
            config: Smoke test configuration
            iteration: Test iteration number (for content variation)

        Returns:
            Complete card JSON structure
        """
        widgets = []
        text_count = 0
        clickable_count = 0

        # 1. Add title text (counts as text component #1)
        title_text = f"<b>Smoke Test #{config.test_id}</b>"
        widgets.append(self._build_text_widget("DecoratedText", title_text, with_icon=True))
        text_count += 1

        # 2. Add subtitle text (counts as text component #2)
        subtitle_text = self._random_text_content(iteration)
        widgets.append(self._build_text_widget(
            random.choice(TEXT_COMPONENTS),
            subtitle_text
        ))
        text_count += 1

        # 3. Optionally add divider
        if config.include_divider:
            widgets.append(self._build_divider())

        # 4. Optionally add image
        if config.include_image:
            widgets.append(self._build_image(
                self._random_image_url(),
                f"Test image for {config.test_id}"
            ))

        # 5. Add 4 clickable buttons
        buttons = []
        for i in range(config.min_clickable_components):
            label = self._random_button_label(i)
            button = self._build_button_widget(
                label=label,
                webhook_url=config.webhook_url,
                button_index=i,
                test_id=config.test_id,
            )
            buttons.append(button)
            clickable_count += 1

        # Wrap buttons in buttonList
        widgets.append(self._build_button_list(buttons))

        # 6. Build the card structure
        card = {
            "cardsV2": [{
                "cardId": f"smoke-test-{config.test_id}",
                "card": {
                    "header": {
                        "title": "Smoke Test Card",
                        "subtitle": f"ID: {config.test_id} | Iteration: {iteration}",
                    },
                    "sections": [{
                        "widgets": widgets
                    }]
                }
            }]
        }

        # Store metadata for validation
        card["_smoke_test_meta"] = {
            "test_id": config.test_id,
            "text_count": text_count,
            "clickable_count": clickable_count,
            "total_components": text_count + clickable_count + (1 if config.include_image else 0),
            "timestamp": datetime.now().isoformat(),
        }

        return card

    def generate_variant_card(
        self,
        config: SmokeTestConfig,
        variant: str = "standard",
        iteration: int = 0,
    ) -> Dict[str, Any]:
        """
        Generate different card layout variants for testing.

        Variants:
        - standard: Title + Subtitle + 4 buttons
        - split_buttons: Title + Subtitle + 2 button rows (2+2)
        - with_form: Title + 2 SelectionInputs (dropdown + radio) + 4 buttons
        - with_grid: Title + 2x2 Grid with clickable items
        """
        widgets = []
        text_count = 0
        clickable_count = 0

        # Title (always)
        title_text = f"<b>Smoke Test: {variant.title()}</b>"
        widgets.append(self._build_text_widget("DecoratedText", title_text, with_icon=True))
        text_count += 1

        if variant == "standard":
            # Standard: subtitle + 4 buttons
            widgets.append(self._build_text_widget("TextParagraph", self._random_text_content(iteration)))
            text_count += 1

            buttons = [
                self._build_button_widget(self._random_button_label(i), config.webhook_url, i, config.test_id)
                for i in range(4)
            ]
            widgets.append(self._build_button_list(buttons))
            clickable_count = 4

        elif variant == "split_buttons":
            # Split: subtitle + 2 rows of 2 buttons each
            widgets.append(self._build_text_widget("DecoratedText", self._random_text_content(iteration)))
            text_count += 1

            # First row
            buttons1 = [
                self._build_button_widget(self._random_button_label(i), config.webhook_url, i, config.test_id)
                for i in range(2)
            ]
            widgets.append(self._build_button_list(buttons1))

            # Second row
            buttons2 = [
                self._build_button_widget(self._random_button_label(i+2), config.webhook_url, i+2, config.test_id)
                for i in range(2)
            ]
            widgets.append(self._build_button_list(buttons2))
            clickable_count = 4

        elif variant == "with_form":
            # Form: subtitle + 2 SelectionInputs (no free-form text) + 4 submit buttons
            widgets.append(self._build_text_widget("TextParagraph", "Please make your selections below:"))
            text_count += 1

            # Dropdown selection
            widgets.append({
                "selectionInput": {
                    "name": "category_select",
                    "label": "Select a category",
                    "type": "DROPDOWN",
                    "items": [
                        {"text": "Category A", "value": "cat_a", "selected": True},
                        {"text": "Category B", "value": "cat_b"},
                        {"text": "Category C", "value": "cat_c"},
                    ]
                }
            })

            # Radio button selection
            widgets.append({
                "selectionInput": {
                    "name": "priority_select",
                    "label": "Select priority",
                    "type": "RADIO_BUTTON",
                    "items": [
                        {"text": "High", "value": "high"},
                        {"text": "Medium", "value": "medium", "selected": True},
                        {"text": "Low", "value": "low"},
                    ]
                }
            })

            # Submit buttons
            buttons = [
                self._build_button_widget("Submit", config.webhook_url, 0, config.test_id),
                self._build_button_widget("Cancel", config.webhook_url, 1, config.test_id),
                self._build_button_widget("Reset", config.webhook_url, 2, config.test_id),
                self._build_button_widget("Help", config.webhook_url, 3, config.test_id),
            ]
            widgets.append(self._build_button_list(buttons))
            clickable_count = 4

        elif variant == "with_grid":
            # Grid: subtitle + 2x2 grid with clickable items
            widgets.append(self._build_text_widget("DecoratedText", "Select an item from the grid:"))
            text_count += 1

            # Grid with clickable items
            grid_items = []
            for i in range(4):
                item = {
                    "title": f"Item {i+1}",
                    "subtitle": f"Click to test #{i+1}",
                    "image": {
                        "imageUri": self._random_image_url(),
                        "altText": f"Grid item {i+1}",
                    },
                }
                if config.webhook_url:
                    item["id"] = f"grid_item_{i}"
                grid_items.append(item)

            widgets.append({
                "grid": {
                    "title": "Test Grid",
                    "columnCount": 2,
                    "items": grid_items,
                }
            })
            clickable_count = 4  # Grid items are clickable

        else:
            # Fallback to standard
            return self.generate_card(config, iteration)

        # Build card
        card = {
            "cardsV2": [{
                "cardId": f"smoke-test-{variant}-{config.test_id}",
                "card": {
                    "header": {
                        "title": f"Smoke Test: {variant.title()}",
                        "subtitle": f"ID: {config.test_id}",
                    },
                    "sections": [{
                        "widgets": widgets
                    }]
                }
            }]
        }

        card["_smoke_test_meta"] = {
            "test_id": config.test_id,
            "variant": variant,
            "text_count": text_count,
            "clickable_count": clickable_count,
            "total_components": text_count + clickable_count,
            "timestamp": datetime.now().isoformat(),
        }

        return card

    # =========================================================================
    # FEEDBACK CARD GENERATOR
    # =========================================================================

    def generate_feedback_card(
        self,
        config: SmokeTestConfig,
        randomize_labels: bool = True,
        include_content_section: bool = True,
    ) -> Dict[str, Any]:
        """
        Generate a feedback card with randomized content.

        Structure:
        - Section 1: Main content (randomized theme)
          - Title text (text component #1)
          - Content items (text component #2)
        - Section 2: Feedback prompts + buttons
          - Content feedback prompt (asking about data/values)
          - Content feedback buttons (👍/👎) (clickable #1, #2)
          - Form feedback prompt (asking about layout)
          - Form feedback buttons (👍/👎) (clickable #3, #4)

        Total: 2 text + 4 clickable = 6 components (meets requirement)

        Args:
            config: Smoke test configuration
            randomize_labels: Whether to randomize button labels
            include_content_section: Whether to include the content section

        Returns:
            Complete feedback card JSON
        """
        # Pick a random content theme
        theme = random.choice(CONTENT_THEMES)

        # Build content section widgets
        content_widgets = []
        text_count = 0

        if include_content_section:
            # Title with icon (text component #1)
            content_widgets.append({
                "decoratedText": {
                    "startIcon": {"knownIcon": theme["icon"]},
                    "text": f"<b>{theme['title']}</b>",
                    "wrapText": True,
                }
            })
            text_count += 1

            # Content items as text paragraph (text component #2)
            items_html = "<br>".join(f"• {item}" for item in theme["items"])
            content_widgets.append({
                "textParagraph": {
                    "text": items_html,
                }
            })
            text_count += 1

        # Build feedback section widgets
        feedback_widgets = []
        clickable_count = 0

        # Pick random prompts
        content_prompt = random.choice(CONTENT_FEEDBACK_PROMPTS)
        form_prompt = random.choice(FORM_FEEDBACK_PROMPTS)

        # Pick random button labels
        if randomize_labels:
            pos_label_1 = random.choice(POSITIVE_LABELS)
            neg_label_1 = random.choice(NEGATIVE_LABELS)
            pos_label_2 = random.choice(POSITIVE_LABELS)
            neg_label_2 = random.choice(NEGATIVE_LABELS)
        else:
            pos_label_1 = pos_label_2 = "👍 Good"
            neg_label_1 = neg_label_2 = "👎 Bad"

        # Content feedback prompt
        feedback_widgets.append({
            "decoratedText": {
                "text": f"<i>{content_prompt}</i>",
                "wrapText": True,
            }
        })

        # Content feedback buttons (clickable #1, #2)
        content_buttons = []
        for i, (label, feedback_val) in enumerate([(pos_label_1, "positive"), (neg_label_1, "negative")]):
            btn = {"text": label}
            if config.webhook_url:
                btn["onClick"] = {
                    "openLink": {
                        "url": f"{config.webhook_url}?card_id={config.test_id}&feedback={feedback_val}&feedback_type=content&btn={i}"
                    }
                }
            content_buttons.append(btn)
            clickable_count += 1

        feedback_widgets.append({"buttonList": {"buttons": content_buttons}})

        # Form feedback prompt
        feedback_widgets.append({
            "decoratedText": {
                "text": f"<i>{form_prompt}</i>",
                "wrapText": True,
            }
        })

        # Form feedback buttons (clickable #3, #4)
        form_buttons = []
        for i, (label, feedback_val) in enumerate([(pos_label_2, "positive"), (neg_label_2, "negative")]):
            btn = {"text": label}
            if config.webhook_url:
                btn["onClick"] = {
                    "openLink": {
                        "url": f"{config.webhook_url}?card_id={config.test_id}&feedback={feedback_val}&feedback_type=form&btn={i+2}"
                    }
                }
            form_buttons.append(btn)
            clickable_count += 1

        feedback_widgets.append({"buttonList": {"buttons": form_buttons}})

        # Build sections
        sections = []
        if include_content_section and content_widgets:
            sections.append({"widgets": content_widgets})
        sections.append({
            "header": "Feedback",
            "widgets": feedback_widgets,
        })

        # Build card
        card = {
            "cardsV2": [{
                "cardId": f"feedback-{config.test_id}",
                "card": {
                    "header": {
                        "title": random.choice(FEEDBACK_CARD_TITLES),
                        "subtitle": f"Test ID: {config.test_id}",
                    },
                    "sections": sections,
                }
            }]
        }

        card["_smoke_test_meta"] = {
            "test_id": config.test_id,
            "variant": "feedback",
            "theme": theme["title"],
            "text_count": text_count,
            "clickable_count": clickable_count,
            "total_components": text_count + clickable_count,
            "content_prompt": content_prompt,
            "form_prompt": form_prompt,
            "timestamp": datetime.now().isoformat(),
        }

        return card

    def generate_random_feedback_cards(
        self,
        count: int = 5,
        webhook_url: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Generate multiple random feedback cards for testing variety.

        Args:
            count: Number of cards to generate
            webhook_url: Optional webhook URL for button callbacks

        Returns:
            List of card JSON structures
        """
        cards = []
        for i in range(count):
            config = SmokeTestConfig(
                webhook_url=webhook_url,
                test_id=f"{i:03d}-{str(uuid.uuid4())[:4]}",
            )
            card = self.generate_feedback_card(config)
            cards.append(card)
        return cards

    # =========================================================================
    # TEST EXECUTION
    # =========================================================================

    async def run_smoke_test(
        self,
        webhook_url: str,
        num_iterations: int = 1,
        variants: Optional[List[str]] = None,
        verify_ssl: bool = False,
    ) -> List[SmokeTestResult]:
        """
        Run smoke tests by posting generated cards to a webhook.

        Args:
            webhook_url: Google Chat webhook URL
            num_iterations: Number of test iterations
            variants: Card variants to test (default: all)
            verify_ssl: Whether to verify SSL certificates

        Returns:
            List of test results
        """
        if variants is None:
            variants = ["standard", "split_buttons", "with_form", "with_grid"]

        results = []

        async with httpx.AsyncClient(verify=verify_ssl) as client:
            for iteration in range(num_iterations):
                for variant in variants:
                    config = SmokeTestConfig(
                        webhook_url=webhook_url,
                        include_image=(variant == "with_grid"),
                    )

                    # Generate card
                    card = self.generate_variant_card(config, variant, iteration)
                    meta = card.pop("_smoke_test_meta", {})

                    result = SmokeTestResult(
                        test_id=config.test_id,
                        card_json=card,
                        component_count=meta.get("total_components", 0),
                        text_count=meta.get("text_count", 0),
                        clickable_count=meta.get("clickable_count", 0),
                    )

                    try:
                        # Post to webhook
                        response = await client.post(
                            webhook_url,
                            json=card,
                            timeout=30.0,
                        )

                        if response.status_code == 200:
                            result.success = True
                            result.webhook_responses.append({
                                "status": response.status_code,
                                "body": response.json() if response.text else None,
                            })
                            logger.info(f"✅ Smoke test {variant}/{config.test_id}: SUCCESS")
                        else:
                            result.error = f"HTTP {response.status_code}: {response.text}"
                            logger.error(f"❌ Smoke test {variant}/{config.test_id}: {result.error}")

                    except Exception as e:
                        result.error = str(e)
                        logger.error(f"❌ Smoke test {variant}/{config.test_id}: {e}")

                    results.append(result)

                    # Small delay between tests
                    await asyncio.sleep(0.5)

        return results

    def validate_card(self, card: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Validate that a card meets smoke test requirements.

        Returns:
            Tuple of (is_valid, list of validation errors)
        """
        errors = []

        # Check structure
        if "cardsV2" not in card:
            errors.append("Missing cardsV2 key")
            return False, errors

        cards_v2 = card["cardsV2"]
        if not cards_v2 or not isinstance(cards_v2, list):
            errors.append("cardsV2 must be a non-empty list")
            return False, errors

        inner_card = cards_v2[0].get("card", {})
        sections = inner_card.get("sections", [])

        if not sections:
            errors.append("Card must have at least one section")
            return False, errors

        # Count components
        text_count = 0
        clickable_count = 0

        for section in sections:
            for widget in section.get("widgets", []):
                # Check for text components
                if "decoratedText" in widget or "textParagraph" in widget:
                    text_count += 1

                # Check for clickable components
                if "buttonList" in widget:
                    buttons = widget["buttonList"].get("buttons", [])
                    clickable_count += len(buttons)

                if "grid" in widget:
                    items = widget["grid"].get("items", [])
                    clickable_count += len(items)

        # Validate minimums
        if text_count < 2:
            errors.append(f"Need at least 2 text components, found {text_count}")

        if clickable_count < 4:
            errors.append(f"Need at least 4 clickable components, found {clickable_count}")

        return len(errors) == 0, errors


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def generate_smoke_test_card(
    webhook_url: Optional[str] = None,
    variant: str = "standard",
) -> Dict[str, Any]:
    """
    Generate a single smoke test card.

    Args:
        webhook_url: Optional webhook URL for button callbacks
        variant: Card variant (standard, split_buttons, with_form, with_grid)

    Returns:
        Card JSON structure
    """
    generator = SmokeTestGenerator()
    config = SmokeTestConfig(webhook_url=webhook_url)
    return generator.generate_variant_card(config, variant)


async def run_smoke_tests(
    webhook_url: str,
    num_iterations: int = 1,
    variants: Optional[List[str]] = None,
) -> List[SmokeTestResult]:
    """
    Run smoke tests against a webhook.

    Args:
        webhook_url: Google Chat webhook URL
        num_iterations: Number of test iterations
        variants: Card variants to test

    Returns:
        List of test results
    """
    generator = SmokeTestGenerator()
    return await generator.run_smoke_test(webhook_url, num_iterations, variants)


# =============================================================================
# CLI ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python smoke_test_generator.py <webhook_url> [num_iterations]")
        print("\nExample:")
        print("  python smoke_test_generator.py 'https://chat.googleapis.com/v1/spaces/...' 3")
        sys.exit(1)

    webhook_url = sys.argv[1]
    num_iterations = int(sys.argv[2]) if len(sys.argv) > 2 else 1

    print(f"Running smoke tests against: {webhook_url[:50]}...")
    print(f"Iterations: {num_iterations}")
    print()

    results = asyncio.run(run_smoke_tests(webhook_url, num_iterations))

    # Summary
    success_count = sum(1 for r in results if r.success)
    print()
    print("=" * 60)
    print(f"SMOKE TEST SUMMARY: {success_count}/{len(results)} passed")
    print("=" * 60)

    for r in results:
        status = "✅" if r.success else "❌"
        print(f"  {status} {r.test_id}: text={r.text_count}, clickable={r.clickable_count}")
        if r.error:
            print(f"      Error: {r.error[:80]}")
