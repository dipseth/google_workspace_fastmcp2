#!/usr/bin/env python3
"""
Relationship Validation & Warm-Start Pipeline

This script:
1. Extracts component relationships from card_framework type hints
2. Attempts to instantiate and render each relationship combination
3. ACTUALLY SENDS TO WEBHOOK to validate against real Google Chat API
4. Stores successful combinations as positive form_feedback patterns
5. Logs failures for investigation

The key insight: local rendering may pass but API may reject (like GridItem onClick).
Real validation requires sending to the webhook.

Usage:
    python scripts/validate_relationships.py [--dry-run] [--verbose]
    python scripts/validate_relationships.py --send-to-webhook  # Actually test against API
    python scripts/validate_relationships.py --random-combos 10 --send-to-webhook
"""

import argparse
import dataclasses
import inspect
import json
import os
import random
import sys
import time
from typing import (
    Any,
    Dict,
    List,
    Optional,
    Set,
    Tuple,
    Union,
    get_args,
    get_origin,
    get_type_hints,
)

import requests

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

from config.enhanced_logging import setup_logger

# Import universal styling system for random colors
from middleware.filters.styling_filters import (
    COLOR_SCHEMES,
    SEMANTIC_COLORS,
    STYLING_FILTERS,
    ColorCycler,
    ComponentStyler,
    badge_filter,
    bold_filter,
    color_filter,
    price_filter,
    strike_filter,
)

# Import Jinja templating system for rich card styling
from middleware.template_core.jinja_environment import JinjaEnvironmentManager

logger = setup_logger()


# =========================================================================
# JINJA TEMPLATING SETUP
# =========================================================================


def get_jinja_environment():
    """Get configured Jinja environment with all styling filters."""
    jinja_mgr = JinjaEnvironmentManager()
    jinja_mgr.setup_jinja2_environment()
    jinja_mgr.register_filters(STYLING_FILTERS)
    return jinja_mgr.jinja2_env


# Global Jinja environment (lazy-loaded)
_JINJA_ENV = None


def jinja_env():
    """Get or create the global Jinja environment."""
    global _JINJA_ENV
    if _JINJA_ENV is None:
        _JINJA_ENV = get_jinja_environment()
    return _JINJA_ENV


def render_jinja_template(template_str: str, **context) -> str:
    """Render a Jinja template string with styling filters."""
    env = jinja_env()
    template = env.from_string(template_str)
    return template.render(**context)


# =========================================================================
# CONFIGURATION
# =========================================================================

PRIMITIVE_TYPES = {str, int, float, bool, bytes, type(None)}
BUILTIN_PREFIXES = {"builtins", "typing", "collections", "abc"}
TARGET_MODULE = "card_framework"

# Random color scheme for this run
CURRENT_COLOR_SCHEME = random.choice(list(COLOR_SCHEMES.keys()))
STYLER = ComponentStyler(scheme=CURRENT_COLOR_SCHEME, target="gchat")

# =========================================================================
# STYLED CONTENT GENERATORS (Using Jinja Templates)
# =========================================================================

# Pre-defined Jinja templates for various card themes
CARD_THEMES = {
    "status": {
        "name": "System Status",
        "templates": {
            "title": '{{ title | color("#1a73e8") | bold }}',
            "success": "{{ text | success_text }}",
            "warning": "{{ text | warning_text }}",
            "error": "{{ text | error_text }}",
            "metric": '{{ label | muted_text }}: {{ value | color("#34a853") | bold }}',
        },
        "sample_data": {
            "title": "System Health",
            "items": [
                {"text": "API: Online", "type": "success"},
                {"text": "Database: Connected", "type": "success"},
                {"text": "Cache: High Latency", "type": "warning"},
            ],
        },
    },
    "pricing": {
        "name": "Product Pricing",
        "templates": {
            "title": "{{ title | bold }}",
            "price": "{{ amount | price(currency) }}",
            "sale_price": '{{ "SALE" | badge("#ea4335") }} {{ amount | price(currency) }}',
            "original": "Was: {{ amount | price(currency) | strike }}",
            "savings": '{{ text | color("#34a853") | bold }}',
        },
        "sample_data": {
            "title": "Special Offer",
            "currency": "USD",
            "original_price": 149.99,
            "sale_price": 99.99,
        },
    },
    "build": {
        "name": "Build Status",
        "templates": {
            "title": "{{ name | bold }} #{{ number }}",
            "passed": '{{ "PASSED" | success_text }}',
            "failed": '{{ "FAILED" | error_text }}',
            "duration": '{{ "Duration" | muted_text }}: {{ time }}',
            "tests": '{{ "Tests" | muted_text }}: {{ passed | color("#34a853") }}/{{ total }}',
            "coverage": '{{ "Coverage" | muted_text }}: {{ percent | color("#1a73e8") }}%',
        },
        "sample_data": {
            "name": "Build",
            "number": random.randint(1000, 9999),
            "time": f"{random.randint(1, 5)}m {random.randint(0, 59)}s",
            "passed": random.randint(90, 150),
            "total": 150,
            "percent": round(random.uniform(85, 99), 1),
        },
    },
    "alert": {
        "name": "Alert Notification",
        "templates": {
            "title": "{{ severity | badge(color) }} {{ title }}",
            "message": "{{ message }}",
            "timestamp": '{{ "Time" | muted_text }}: {{ time }}',
            "source": '{{ "Source" | muted_text }}: {{ source | color("#1a73e8") }}',
        },
        "sample_data": {
            "severity": "WARNING",
            "color": "#fbbc05",
            "title": "High Memory Usage",
            "message": "Memory usage exceeded 85% threshold",
            "time": "2 minutes ago",
            "source": "monitoring-service",
        },
    },
    "metrics": {
        "name": "Dashboard Metrics",
        "templates": {
            "title": '{{ title | color("#1a73e8") | bold }}',
            "metric_up": '{{ label }}: {{ value | color("#34a853") | bold }} {{ "↑" | color("#34a853") }}',
            "metric_down": '{{ label }}: {{ value | color("#ea4335") | bold }} {{ "↓" | color("#ea4335") }}',
            "metric_neutral": "{{ label }}: {{ value | bold }}",
            "percentage": "{{ label }}: {{ value | color(color) }}%",
        },
        "sample_data": {
            "title": "Performance Metrics",
            "metrics": [
                {"label": "Requests/sec", "value": "2,450", "trend": "up"},
                {"label": "Latency", "value": "45ms", "trend": "down"},
                {"label": "Error Rate", "value": "0.02%", "trend": "neutral"},
            ],
        },
    },
}


def get_random_theme() -> Dict[str, Any]:
    """Get a random card theme with its templates and sample data."""
    theme_name = random.choice(list(CARD_THEMES.keys()))
    return {"name": theme_name, **CARD_THEMES[theme_name]}


def render_themed_text(theme_name: str, template_key: str, **context) -> str:
    """Render text using a theme's template."""
    theme = CARD_THEMES.get(theme_name, CARD_THEMES["status"])
    template_str = theme["templates"].get(template_key, "{{ text }}")
    return render_jinja_template(template_str, **context)


# Styled minimal values - uses random colors for visual variety
def get_styled_text(text: str, component_type: str = "default") -> str:
    """Get styled text with alternating colors."""
    return STYLER.auto_style(component_type, text)


def get_random_styled_title() -> str:
    """Generate a random styled title using Jinja templates."""
    titles = ["Dashboard", "Report", "Status", "Metrics", "Overview", "Summary"]
    colors = ["#1a73e8", "#34a853", "#8430ce", "#00acc1"]
    title = random.choice(titles)
    color = random.choice(colors)
    return render_jinja_template(
        "{{ title | color(color) | bold }}", title=title, color=color
    )


def get_random_styled_text() -> str:
    """Generate random styled sample text using Jinja templates."""
    templates = [
        "{{ text | success_text }}",
        '{{ text | color("#1a73e8") }}',
        "{{ text | muted_text }}",
        "{{ text | warning_text }}",
        "{{ text | bold }}",
    ]
    texts = ["Active", "Connected", "Running", "Healthy", "Online", "Ready"]
    template = random.choice(templates)
    text = random.choice(texts)
    return render_jinja_template(template, text=text)


def get_random_price_text() -> str:
    """Generate random price text using Jinja price filter."""
    prices = [9.99, 19.99, 49.99, 99.99, 149.99, 199.99]
    currencies = ["USD", "EUR", "GBP"]
    price = random.choice(prices)
    currency = random.choice(currencies)

    # Randomly choose sale or regular price
    if random.random() > 0.5:
        return render_jinja_template(
            '{{ "SALE" | badge("#ea4335") }} {{ price | price(currency) }}',
            price=price,
            currency=currency,
        )
    return render_jinja_template(
        "{{ price | price(currency) }}", price=price, currency=currency
    )


def get_random_status_text() -> str:
    """Generate random status text with appropriate styling."""
    statuses = [
        ("Online", "success_text"),
        ("Offline", "error_text"),
        ("Degraded", "warning_text"),
        ("Maintenance", "muted_text"),
        ("Starting", 'color("#1a73e8")'),
    ]
    status, filter_name = random.choice(statuses)
    return render_jinja_template(f"{{{{ status | {filter_name} }}}}", status=status)


def get_random_metric_text() -> str:
    """Generate random metric text with values."""
    metrics = [
        (
            "CPU",
            f"{random.randint(10, 95)}%",
            "#34a853" if random.random() > 0.3 else "#ea4335",
        ),
        (
            "Memory",
            f"{random.randint(20, 90)}%",
            "#34a853" if random.random() > 0.3 else "#fbbc05",
        ),
        ("Disk", f"{random.randint(30, 85)}%", "#34a853"),
        ("Requests", f"{random.randint(100, 5000)}/s", "#1a73e8"),
        (
            "Latency",
            f"{random.randint(5, 200)}ms",
            "#34a853" if random.random() > 0.5 else "#fbbc05",
        ),
    ]
    label, value, color = random.choice(metrics)
    return render_jinja_template(
        "{{ label | muted_text }}: {{ value | color(color) | bold }}",
        label=label,
        value=value,
        color=color,
    )


# Minimal valid values for common field types
MINIMAL_VALUES = {
    "str": "test",
    "int": 1,
    "float": 1.0,
    "bool": True,
    "image_url": "https://example.com/image.png",
    "url": "https://example.com",
    "text": "Sample text",
    "title": "Sample title",
    "alt_text": "Alt text",
    "name": "test_name",
    "label": "Label",
    "action_method_name": "test_action",
}


# Styled versions of minimal values (generated fresh each call)
def get_styled_minimal_values() -> Dict[str, Any]:
    """Get minimal values with random Jinja styling applied to text fields."""
    scheme = random.choice(list(COLOR_SCHEMES.keys()))
    cycler = ColorCycler.from_scheme(scheme)

    return {
        "str": "test",
        "int": 1,
        "float": 1.0,
        "bool": True,
        "image_url": (
            random.choice(VALID_IMAGE_URLS)
            if "VALID_IMAGE_URLS" in dir()
            else "https://example.com/image.png"
        ),
        "url": "https://example.com",
        "text": render_jinja_template(
            "{{ text | color(color) }}", text="Sample text", color=cycler.next()
        ),
        "title": render_jinja_template(
            "{{ title | color(color) | bold }}",
            title="Sample title",
            color=cycler.next(),
        ),
        "alt_text": "Alt text",
        "name": "test_name",
        "label": render_jinja_template(
            "{{ label | color(color) }}", label="Label", color=cycler.next()
        ),
        "action_method_name": "test_action",
    }


# Test webhook from environment
TEST_WEBHOOK = os.getenv("TEST_CHAT_WEBHOOK")

# Google-hosted images that actually render (many hosts don't work)
VALID_IMAGE_URLS = [
    "https://www.gstatic.com/images/branding/product/2x/chat_2020q4_48dp.png",
    "https://www.gstatic.com/images/branding/product/2x/drive_2020q4_48dp.png",
    "https://www.gstatic.com/images/branding/product/2x/docs_2020q4_48dp.png",
    "https://www.gstatic.com/images/branding/product/2x/sheets_2020q4_48dp.png",
    "https://www.gstatic.com/images/branding/product/2x/slides_2020q4_48dp.png",
    "https://www.gstatic.com/images/branding/product/2x/gmail_2020q4_48dp.png",
    "https://www.gstatic.com/images/branding/product/2x/calendar_2020q4_48dp.png",
]


# =========================================================================
# WEBHOOK VALIDATION (Real API testing)
# =========================================================================


def send_card_to_webhook(
    card_json: Dict[str, Any], webhook_url: str = None
) -> Tuple[bool, str]:
    """
    Send a card to Google Chat webhook to validate it works with the real API.

    Returns (success, error_message).
    """
    url = webhook_url or TEST_WEBHOOK
    if not url:
        return False, "No webhook URL configured (set TEST_CHAT_WEBHOOK env var)"

    # Wrap in cards_v2 format if needed
    if "cards_v2" not in card_json:
        card_id = f"test-{int(time.time())}-{random.randint(1000, 9999)}"
        payload = {
            "cards_v2": [
                {
                    "cardId": card_id,
                    "card": card_json if "card" not in card_json else card_json["card"],
                }
            ]
        }
    else:
        payload = card_json

    try:
        response = requests.post(
            url, json=payload, headers={"Content-Type": "application/json"}, timeout=10
        )

        if response.status_code == 200:
            return True, ""
        else:
            error_detail = (
                response.text[:500] if response.text else f"HTTP {response.status_code}"
            )
            return False, error_detail

    except requests.RequestException as e:
        return False, str(e)


def convert_to_camel_case(data: Any) -> Any:
    """
    Convert snake_case keys to camelCase for Google Chat API.
    The API expects camelCase for widget properties.
    """
    if isinstance(data, dict):
        result = {}
        for key, value in data.items():
            # Convert snake_case to camelCase
            parts = key.split("_")
            camel_key = parts[0] + "".join(word.capitalize() for word in parts[1:])
            result[camel_key] = convert_to_camel_case(value)
        return result
    elif isinstance(data, list):
        return [convert_to_camel_case(item) for item in data]
    else:
        return data


# =========================================================================
# RELATIONSHIP EXTRACTION (from prototype)
# =========================================================================


def is_dataclass_type(cls: type) -> bool:
    """Check if a class is a dataclass."""
    return dataclasses.is_dataclass(cls) and isinstance(cls, type)


def unwrap_optional(field_type: type) -> Tuple[type, bool]:
    """Unwrap Optional[X] to get X and whether it was optional."""
    origin = get_origin(field_type)
    if origin is Union:
        args = get_args(field_type)
        non_none_args = [t for t in args if t is not type(None)]
        if len(non_none_args) == 1:
            return non_none_args[0], True
        return field_type, False
    return field_type, False


def is_component_type(field_type: type) -> bool:
    """Check if a type represents a component (not primitive or enum)."""
    import enum

    if field_type in PRIMITIVE_TYPES:
        return False
    if not inspect.isclass(field_type):
        return False
    module = getattr(field_type, "__module__", "")
    if any(module.startswith(prefix) for prefix in BUILTIN_PREFIXES):
        return False
    # Skip enums - they're not nestable components
    if issubclass(field_type, enum.Enum):
        return False
    return True


def get_required_fields(cls: type) -> Dict[str, type]:
    """Get required fields for a dataclass (no default value)."""
    required = {}
    if not is_dataclass_type(cls):
        return required

    for field in dataclasses.fields(cls):
        # Field is required if it has no default and no default_factory
        has_default = field.default is not dataclasses.MISSING
        has_factory = field.default_factory is not dataclasses.MISSING

        if not has_default and not has_factory:
            # Get actual type from hints
            hints = get_type_hints(cls)
            field_type = hints.get(field.name, field.type)
            unwrapped, is_optional = unwrap_optional(field_type)

            # Optional fields aren't truly required
            if not is_optional:
                required[field.name] = unwrapped

    return required


def get_minimal_value(field_name: str, field_type: type) -> Any:
    """Get a minimal valid value for a field."""
    # Check specific field names first
    field_lower = field_name.lower()
    for key, value in MINIMAL_VALUES.items():
        if key in field_lower:
            return value

    # Fall back to type-based defaults
    if field_type is str:
        return "test"
    elif field_type is int:
        return 1
    elif field_type is float:
        return 1.0
    elif field_type is bool:
        return True
    elif is_dataclass_type(field_type):
        # Recursively create minimal instance
        return create_minimal_instance(field_type)
    elif hasattr(field_type, "__members__"):  # Enum
        # Return first enum member
        members = list(field_type.__members__.values())
        return members[0] if members else None

    return None


def create_minimal_instance(cls: type) -> Any:
    """Create a minimal valid instance of a dataclass."""
    if not is_dataclass_type(cls):
        return None

    required = get_required_fields(cls)
    kwargs = {}

    for field_name, field_type in required.items():
        value = get_minimal_value(field_name, field_type)
        if value is not None:
            kwargs[field_name] = value

    try:
        return cls(**kwargs)
    except Exception as e:
        logger.debug(f"Could not create minimal {cls.__name__}: {e}")
        return None


# =========================================================================
# RELATIONSHIP VALIDATION
# =========================================================================


class RelationshipValidator:
    """Validates component relationships by attempting to render them."""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.results: List[Dict[str, Any]] = []
        self._module = None
        self._wrapper = None

    def _get_module(self):
        """Lazy load the card_framework module."""
        if self._module is None:
            import importlib

            self._module = importlib.import_module("card_framework.v2")
        return self._module

    def _get_wrapper(self):
        """Get ModuleWrapper for card_framework (consistent with SmartCardBuilder)."""
        if self._wrapper is None:
            try:
                from adapters.module_wrapper import ModuleWrapper

                self._wrapper = ModuleWrapper(
                    module_or_name="card_framework",
                    auto_initialize=True,
                    index_nested=True,
                )
            except Exception as e:
                logger.warning(f"Could not initialize ModuleWrapper: {e}")
        return self._wrapper

    def get_component_by_path(self, path: str) -> Optional[Any]:
        """Get a component class by its full path (uses ModuleWrapper)."""
        wrapper = self._get_wrapper()
        if wrapper:
            return wrapper.get_component_by_path(path)
        return None

    def _get_all_classes(self) -> Dict[str, type]:
        """Get all dataclass types from card_framework."""
        # Try to use ModuleWrapper first (more complete)
        wrapper = self._get_wrapper()
        if wrapper and wrapper.components:
            classes = {}
            for path, component in wrapper.components.items():
                if component.component_type == "class" and component.obj:
                    if is_dataclass_type(component.obj):
                        classes[component.name] = component.obj
            if classes:
                return classes

        # Fallback to direct import
        module = self._get_module()
        classes = {}

        # Get from main module
        for name in dir(module):
            obj = getattr(module, name)
            if is_dataclass_type(obj):
                classes[name] = obj

        # Get from widgets submodule
        try:
            from card_framework.v2 import widgets

            for name in dir(widgets):
                obj = getattr(widgets, name)
                if is_dataclass_type(obj):
                    classes[name] = obj
        except ImportError:
            pass

        return classes

    def _extract_relationships(
        self, cls: type, visited: Set[str] = None, depth: int = 0
    ) -> List[Dict]:
        """Extract relationships from a class's type hints."""
        if visited is None:
            visited = set()

        class_name = cls.__name__
        if class_name in visited or depth > 3:
            return []

        visited.add(class_name)
        relationships = []

        try:
            hints = get_type_hints(cls)
        except Exception:
            return []

        for field_name, field_type in hints.items():
            if field_name.startswith("_"):
                continue

            unwrapped, is_optional = unwrap_optional(field_type)

            if is_component_type(unwrapped):
                child_name = unwrapped.__name__
                relationships.append(
                    {
                        "parent_class": class_name,
                        "parent_type": cls,
                        "child_class": child_name,
                        "child_type": unwrapped,
                        "field_name": field_name,
                        "is_optional": is_optional,
                        "depth": depth + 1,
                    }
                )

                # Recurse into child
                if is_dataclass_type(unwrapped):
                    child_rels = self._extract_relationships(
                        unwrapped, visited.copy(), depth + 1
                    )
                    for rel in child_rels:
                        rel["root_parent"] = class_name
                    relationships.extend(child_rels)

        return relationships

    def validate_relationship(self, rel: Dict) -> Dict[str, Any]:
        """
        Attempt to instantiate and render a relationship.

        Returns validation result with success/failure and details.
        """
        parent_cls = rel["parent_type"]
        child_cls = rel["child_type"]
        field_name = rel["field_name"]

        result = {
            "parent": rel["parent_class"],
            "child": rel["child_class"],
            "field": field_name,
            "is_optional": rel["is_optional"],
            "success": False,
            "error": None,
            "rendered_json": None,
            "structure_description": None,
        }

        try:
            # Create minimal child instance
            child_instance = create_minimal_instance(child_cls)
            if child_instance is None and not rel["is_optional"]:
                result["error"] = f"Could not create minimal {child_cls.__name__}"
                return result

            # Get parent's required fields
            parent_required = get_required_fields(parent_cls)
            parent_kwargs = {}

            for fname, ftype in parent_required.items():
                if fname == field_name:
                    parent_kwargs[fname] = child_instance
                else:
                    value = get_minimal_value(fname, ftype)
                    if value is not None:
                        parent_kwargs[fname] = value

            # If the relationship field is optional and not required, add it anyway
            if field_name not in parent_kwargs and child_instance is not None:
                parent_kwargs[field_name] = child_instance

            # Create parent instance
            parent_instance = parent_cls(**parent_kwargs)

            # Try to render
            if hasattr(parent_instance, "render"):
                rendered = parent_instance.render()
            elif hasattr(parent_instance, "to_dict"):
                rendered = parent_instance.to_dict()
            else:
                rendered = dataclasses.asdict(parent_instance)

            # Validate rendered output is valid JSON
            json_str = json.dumps(rendered, default=str)

            result["success"] = True
            result["rendered_json"] = rendered
            result["structure_description"] = (
                f"{rel['parent_class']} containing {rel['child_class']} via {field_name}"
            )

            if self.verbose:
                logger.info(
                    f"  ✅ {rel['parent_class']}.{field_name} -> {rel['child_class']}"
                )

        except Exception as e:
            result["error"] = str(e)
            if self.verbose:
                logger.warning(
                    f"  ❌ {rel['parent_class']}.{field_name} -> {rel['child_class']}: {e}"
                )

        return result

    def validate_all(self) -> List[Dict[str, Any]]:
        """Validate all relationships in card_framework."""
        logger.info("=" * 70)
        logger.info("RELATIONSHIP VALIDATION PIPELINE")
        logger.info("=" * 70)

        # Get all classes
        classes = self._get_all_classes()
        logger.info(f"Found {len(classes)} dataclass types in card_framework")

        # Extract all relationships
        all_relationships = []
        for name, cls in classes.items():
            rels = self._extract_relationships(cls)
            all_relationships.extend(rels)

        # Deduplicate
        seen = set()
        unique_rels = []
        for rel in all_relationships:
            key = (rel["parent_class"], rel["field_name"], rel["child_class"])
            if key not in seen:
                seen.add(key)
                unique_rels.append(rel)

        logger.info(f"Found {len(unique_rels)} unique relationships")
        logger.info("")

        # Validate each relationship
        logger.info("Validating relationships...")
        results = []
        for rel in unique_rels:
            result = self.validate_relationship(rel)
            results.append(result)

        self.results = results
        return results

    def summary(self) -> Dict[str, Any]:
        """Generate summary statistics."""
        successful = [r for r in self.results if r["success"]]
        failed = [r for r in self.results if not r["success"]]

        summary = {
            "total": len(self.results),
            "successful": len(successful),
            "failed": len(failed),
            "success_rate": (
                len(successful) / len(self.results) * 100 if self.results else 0
            ),
            "failed_relationships": [
                {"parent": r["parent"], "child": r["child"], "error": r["error"]}
                for r in failed
            ],
        }

        return summary


# =========================================================================
# FEEDBACK LOOP INTEGRATION
# =========================================================================


def store_validated_patterns(results: List[Dict], dry_run: bool = False) -> int:
    """Store validated relationships as positive form_feedback patterns."""
    if dry_run:
        logger.info("DRY RUN: Would store patterns (not actually storing)")
        successful = [r for r in results if r["success"]]
        return len(successful)

    try:
        from gchat.feedback_loop import get_feedback_loop

        feedback_loop = get_feedback_loop()

        # Ensure collection is ready
        if not feedback_loop.ensure_description_vector_exists():
            logger.error("Could not initialize feedback loop collection")
            return 0

        stored = 0
        for result in results:
            if not result["success"]:
                continue

            # Build component paths
            parent_path = f"card_framework.v2.{result['parent']}"
            child_path = f"card_framework.v2.{result['child']}"
            component_paths = [parent_path, child_path]

            # Build instance params from rendered JSON
            instance_params = result.get("rendered_json", {})

            # Create card description
            card_description = (
                f"Card with {result['parent']} containing {result['child']} "
                f"nested via {result['field']} field"
            )

            try:
                point_id = feedback_loop.store_instance_pattern(
                    card_description=card_description,
                    component_paths=component_paths,
                    instance_params=instance_params,
                    content_feedback="positive",  # Valid values
                    form_feedback="positive",  # Valid structure
                    structure_description=result.get("structure_description"),
                    user_email="validation_pipeline@system.local",
                    card_id=f"validation-{result['parent']}-{result['child']}-{result['field']}",
                )

                if point_id:
                    stored += 1
                    logger.debug(
                        f"Stored: {result['parent']}.{result['field']} -> {result['child']}"
                    )

            except Exception as e:
                logger.warning(f"Failed to store pattern: {e}")

        return stored

    except ImportError as e:
        logger.error(f"Could not import feedback_loop: {e}")
        return 0


# =========================================================================
# COMPLEX NESTING VALIDATION
# =========================================================================


def validate_complex_nestings(
    validator: RelationshipValidator,
    verbose: bool = False,
    use_styled_content: bool = True,
) -> List[Dict]:
    """
    Validate complex multi-level nesting scenarios.

    Based on field notes from SMART_CARD_BUILDER_ARCHITECTURE.md:
    - System Health Dashboard (status rows)
    - Product Showcase (image + price + buttons)
    - Multi-section cards (RAG Evaluation Summary style)
    - Form cards (inputs + selection + date picker)
    - Grid cards (image gallery)

    Args:
        validator: RelationshipValidator instance
        verbose: Print detailed output
        use_styled_content: Apply random colors/styles to text content
    """
    logger.info("")
    logger.info("=" * 70)
    logger.info("COMPLEX NESTING VALIDATION (Field Notes Patterns)")
    logger.info("=" * 70)

    # Pick random color scheme for this validation run
    scheme_name = random.choice(list(COLOR_SCHEMES.keys()))
    styler = ComponentStyler(scheme=scheme_name, target="gchat")
    logger.info(f"Using color scheme: {scheme_name}")

    def styled_text(
        text: str, component_type: str = "default", bold: bool = False
    ) -> str:
        """Apply random styling to text if enabled."""
        if use_styled_content:
            return styler.auto_style(component_type, text, bold=bold)
        return text

    def random_color_text(text: str, bold: bool = False) -> str:
        """Apply a random semantic color to text."""
        if use_styled_content:
            color = random.choice(["success", "info", "primary", "warning", "accent"])
            return color_filter(text, color, target="gchat", bold=bold)
        return text

    complex_scenarios = []

    try:
        from card_framework.v2 import Card, CardHeader, Section
        from card_framework.v2.widgets import (
            Button,
            ButtonList,
            Chip,
            ChipList,
            Column,
            Columns,
            DateTimePicker,
            DecoratedText,
            Grid,
            GridItem,
            Icon,
            Image,
            OnClick,
            OpenLink,
            SelectionInput,
            SelectionItem,
            TextInput,
            TextParagraph,
        )

        # Scenario 1: Clickable Image
        try:
            onclick = OnClick(open_link=OpenLink(url="https://example.com"))
            image = Image(
                image_url="https://example.com/img.png",
                on_click=onclick,
                alt_text="Test",
            )
            rendered = image.render()

            complex_scenarios.append(
                {
                    "scenario": "Clickable Image",
                    "components": ["Image", "OnClick", "OpenLink"],
                    "success": True,
                    "rendered_json": rendered,
                    "structure_description": "Image with clickable link action",
                    "color_scheme": scheme_name,
                }
            )
            if verbose:
                logger.info("  ✅ Clickable Image")
        except Exception as e:
            complex_scenarios.append(
                {
                    "scenario": "Clickable Image",
                    "components": ["Image", "OnClick", "OpenLink"],
                    "success": False,
                    "error": str(e),
                }
            )
            if verbose:
                logger.warning(f"  ❌ Clickable Image: {e}")

        # Scenario 2: Button with Icon (with styled text)
        try:
            # KnownIcon is a nested class inside Icon
            icon = Icon(known_icon=Icon.KnownIcon.STAR)
            onclick = OnClick(open_link=OpenLink(url="https://example.com"))
            button_text = styled_text("Click me", "button", bold=True)
            button = Button(text=button_text, icon=icon, on_click=onclick)
            rendered = button.render()

            complex_scenarios.append(
                {
                    "scenario": "Button with Icon",
                    "components": ["Button", "Icon", "OnClick", "OpenLink"],
                    "success": True,
                    "rendered_json": rendered,
                    "structure_description": "Button with icon and click action",
                    "color_scheme": scheme_name,
                }
            )
            if verbose:
                logger.info("  ✅ Button with Icon")
        except Exception as e:
            complex_scenarios.append(
                {
                    "scenario": "Button with Icon",
                    "components": ["Button", "Icon", "OnClick", "OpenLink"],
                    "success": False,
                    "error": str(e),
                }
            )
            if verbose:
                logger.warning(f"  ❌ Button with Icon: {e}")

        # Scenario 3: DecoratedText with Icon and Button (styled content)
        try:
            # KnownIcon is a nested class inside Icon
            icon = Icon(known_icon=Icon.KnownIcon.DESCRIPTION)
            action_text = styled_text("Action", "button")
            button = Button(text=action_text)
            content_text = random_color_text("Sample content with styling")
            text = DecoratedText(text=content_text, start_icon=icon, button=button)
            rendered = text.render()

            complex_scenarios.append(
                {
                    "scenario": "DecoratedText with Icon and Button",
                    "components": ["DecoratedText", "Icon", "Button"],
                    "success": True,
                    "rendered_json": rendered,
                    "structure_description": "Decorated text with leading icon and action button",
                    "color_scheme": scheme_name,
                }
            )
            if verbose:
                logger.info("  ✅ DecoratedText with Icon and Button")
        except Exception as e:
            complex_scenarios.append(
                {
                    "scenario": "DecoratedText with Icon and Button",
                    "components": ["DecoratedText", "Icon", "Button"],
                    "success": False,
                    "error": str(e),
                }
            )
            if verbose:
                logger.warning(f"  ❌ DecoratedText with Icon and Button: {e}")

        # Scenario 4: Grid with clickable items (styled titles)
        try:
            onclick = OnClick(open_link=OpenLink(url="https://example.com"))
            item1_title = styled_text("Item 1", "grid_item", bold=True)
            item2_title = styled_text("Item 2", "grid_item", bold=True)
            item1 = GridItem(id="item1", title=item1_title)
            item2 = GridItem(id="item2", title=item2_title)
            grid_title = random_color_text("My Grid", bold=True)
            grid = Grid(title=grid_title, items=[item1, item2], on_click=onclick)
            rendered = grid.render()

            complex_scenarios.append(
                {
                    "scenario": "Grid with Clickable Items",
                    "components": ["Grid", "GridItem", "OnClick", "OpenLink"],
                    "success": True,
                    "rendered_json": rendered,
                    "structure_description": "Grid layout with clickable grid items",
                }
            )
            if verbose:
                logger.info("  ✅ Grid with Clickable Items")
        except Exception as e:
            complex_scenarios.append(
                {
                    "scenario": "Grid with Clickable Items",
                    "components": ["Grid", "GridItem", "OnClick", "OpenLink"],
                    "success": False,
                    "error": str(e),
                }
            )
            if verbose:
                logger.warning(f"  ❌ Grid with Clickable Items: {e}")

        # Scenario 5: Section with multiple widget types (styled)
        try:
            info_text = random_color_text("Info text with random styling")
            text = DecoratedText(text=info_text)
            image = Image(image_url="https://example.com/img.png", alt_text="Image")
            section_header = styled_text("Mixed Section", "section", bold=True)
            section = Section(header=section_header, widgets=[text, image])
            rendered = section.render()

            complex_scenarios.append(
                {
                    "scenario": "Section with Mixed Widgets",
                    "components": ["Section", "DecoratedText", "Image"],
                    "success": True,
                    "rendered_json": rendered,
                    "structure_description": "Section containing text and image widgets",
                    "color_scheme": scheme_name,
                }
            )
            if verbose:
                logger.info("  ✅ Section with Mixed Widgets")
        except Exception as e:
            complex_scenarios.append(
                {
                    "scenario": "Section with Mixed Widgets",
                    "components": ["Section", "DecoratedText", "Image"],
                    "success": False,
                    "error": str(e),
                }
            )
            if verbose:
                logger.warning(f"  ❌ Section with Mixed Widgets: {e}")

        # Scenario 6: ButtonList with multiple styled buttons (alternating colors)
        try:
            btn1_text = styled_text("Primary", "button", bold=True)
            btn2_text = styled_text("Secondary", "button")
            btn1 = Button(text=btn1_text, color={"red": 0.2, "green": 0.6, "blue": 0.9})
            btn2 = Button(text=btn2_text)
            button_list = ButtonList(buttons=[btn1, btn2])
            rendered = button_list.render()

            complex_scenarios.append(
                {
                    "scenario": "ButtonList with Styled Buttons",
                    "components": ["ButtonList", "Button"],
                    "success": True,
                    "rendered_json": rendered,
                    "structure_description": "Button list with multiple styled buttons",
                    "color_scheme": scheme_name,
                }
            )
            if verbose:
                logger.info("  ✅ ButtonList with Styled Buttons")
        except Exception as e:
            complex_scenarios.append(
                {
                    "scenario": "ButtonList with Styled Buttons",
                    "components": ["ButtonList", "Button"],
                    "success": False,
                    "error": str(e),
                }
            )
            if verbose:
                logger.warning(f"  ❌ ButtonList with Styled Buttons: {e}")

        # =====================================================================
        # FIELD NOTES PATTERNS (from SMART_CARD_BUILDER_ARCHITECTURE.md)
        # =====================================================================

        # Scenario 7: Teen Titans Power Systems - Multi-section with HTML styling
        try:
            section1 = Section(
                header='<font color="#00FFFF">⚡ POWER SYSTEMS</font>',
                widgets=[
                    DecoratedText(
                        text='✓ <font color="#00FF00">Main Reactor: ONLINE</font>'
                    ),
                    DecoratedText(
                        text='⚠ <font color="#FFFF00">Snack Storage: LOW</font>'
                    ),
                ],
            )
            section2 = Section(
                header='<font color="#FF0000">🚨 ALERT LEVEL</font>',
                widgets=[
                    DecoratedText(
                        text='Current: <font color="#00FF00">GREEN - ALL CLEAR</font>'
                    ),
                ],
            )
            card = Card(sections=[section1, section2])
            rendered = card.render()

            complex_scenarios.append(
                {
                    "scenario": "Teen Titans Power Systems (Multi-Section HTML)",
                    "components": ["Card", "Section", "DecoratedText"],
                    "success": True,
                    "rendered_json": rendered,
                    "structure_description": "Multi-section card with HTML-styled headers and status text",
                }
            )
            if verbose:
                logger.info("  ✅ Teen Titans Power Systems (Multi-Section HTML)")
        except Exception as e:
            complex_scenarios.append(
                {
                    "scenario": "Teen Titans Power Systems (Multi-Section HTML)",
                    "components": ["Card", "Section", "DecoratedText"],
                    "success": False,
                    "error": str(e),
                }
            )
            if verbose:
                logger.warning(f"  ❌ Teen Titans Power Systems: {e}")

        # Scenario 8: System Health Dashboard - Status rows with buttons
        try:
            status_section = Section(
                header="System Health",
                widgets=[
                    DecoratedText(text="API Server", bottom_label="Online"),
                    DecoratedText(text="Database", bottom_label="Connected"),
                    DecoratedText(text="Cache", bottom_label="High Latency 250ms"),
                ],
            )
            action_section = Section(
                widgets=[
                    ButtonList(
                        buttons=[
                            Button(
                                text="View Details",
                                on_click=OnClick(
                                    open_link=OpenLink(
                                        url="https://example.com/dashboard"
                                    )
                                ),
                            ),
                            Button(
                                text="Refresh",
                                on_click=OnClick(
                                    open_link=OpenLink(
                                        url="https://example.com/refresh"
                                    )
                                ),
                            ),
                        ]
                    )
                ]
            )
            card = Card(sections=[status_section, action_section])
            rendered = card.render()

            complex_scenarios.append(
                {
                    "scenario": "System Health Dashboard",
                    "components": [
                        "Card",
                        "Section",
                        "DecoratedText",
                        "ButtonList",
                        "Button",
                        "OnClick",
                        "OpenLink",
                    ],
                    "success": True,
                    "rendered_json": rendered,
                    "structure_description": "Dashboard with status rows and action buttons",
                }
            )
            if verbose:
                logger.info("  ✅ System Health Dashboard")
        except Exception as e:
            complex_scenarios.append(
                {
                    "scenario": "System Health Dashboard",
                    "components": [
                        "Card",
                        "Section",
                        "DecoratedText",
                        "ButtonList",
                        "Button",
                        "OnClick",
                        "OpenLink",
                    ],
                    "success": False,
                    "error": str(e),
                }
            )
            if verbose:
                logger.warning(f"  ❌ System Health Dashboard: {e}")

        # Scenario 9: Product Showcase - Image + price + buttons
        try:
            header = CardHeader(title="New Release", subtitle="MacBook Pro M4")
            product_section = Section(
                widgets=[
                    Image(
                        image_url="https://picsum.photos/400/200",
                        alt_text="Product image",
                    ),
                    DecoratedText(text="$2,499", top_label="Price"),
                    DecoratedText(text="The most powerful laptop ever built"),
                ]
            )
            button_section = Section(
                widgets=[
                    ButtonList(
                        buttons=[
                            Button(
                                text="Buy Now",
                                on_click=OnClick(
                                    open_link=OpenLink(url="https://apple.com/buy")
                                ),
                            ),
                            Button(
                                text="Learn More",
                                on_click=OnClick(
                                    open_link=OpenLink(url="https://apple.com/macbook")
                                ),
                            ),
                            Button(
                                text="Compare",
                                on_click=OnClick(
                                    open_link=OpenLink(url="https://apple.com/compare")
                                ),
                            ),
                        ]
                    )
                ]
            )
            card = Card(header=header, sections=[product_section, button_section])
            rendered = card.render()

            complex_scenarios.append(
                {
                    "scenario": "Product Showcase Card",
                    "components": [
                        "Card",
                        "CardHeader",
                        "Section",
                        "Image",
                        "DecoratedText",
                        "ButtonList",
                        "Button",
                        "OnClick",
                        "OpenLink",
                    ],
                    "success": True,
                    "rendered_json": rendered,
                    "structure_description": "Product card with header, image, price, description and multiple action buttons",
                }
            )
            if verbose:
                logger.info("  ✅ Product Showcase Card")
        except Exception as e:
            complex_scenarios.append(
                {
                    "scenario": "Product Showcase Card",
                    "components": [
                        "Card",
                        "CardHeader",
                        "Section",
                        "Image",
                        "DecoratedText",
                        "ButtonList",
                        "Button",
                        "OnClick",
                        "OpenLink",
                    ],
                    "success": False,
                    "error": str(e),
                }
            )
            if verbose:
                logger.warning(f"  ❌ Product Showcase Card: {e}")

        # Scenario 10: Form Card - TextInput + SelectionInput + DateTimePicker
        try:
            form_section = Section(
                header="Bug Report Form",
                widgets=[
                    TextInput(name="bug_title", label="Bug Title"),
                    TextInput(
                        name="description",
                        label="Description",
                        type=TextInput.Type.MULTIPLE_LINE,
                    ),
                    SelectionInput(
                        name="severity",
                        label="Severity",
                        type=SelectionInput.SelectionType.DROPDOWN,  # Note: SelectionType, not Type
                        items=[
                            SelectionItem(text="Low", value="low"),
                            SelectionItem(text="Medium", value="medium"),
                            SelectionItem(text="High", value="high"),
                        ],
                    ),
                    DateTimePicker(name="found_date", label="Date Found"),
                ],
            )
            card = Card(sections=[form_section])
            rendered = card.render()

            complex_scenarios.append(
                {
                    "scenario": "Form Card (Bug Report)",
                    "components": [
                        "Card",
                        "Section",
                        "TextInput",
                        "SelectionInput",
                        "SelectionItem",
                        "DateTimePicker",
                    ],
                    "success": True,
                    "rendered_json": rendered,
                    "structure_description": "Form card with text inputs, dropdown selection, and date picker",
                }
            )
            if verbose:
                logger.info("  ✅ Form Card (Bug Report)")
        except Exception as e:
            complex_scenarios.append(
                {
                    "scenario": "Form Card (Bug Report)",
                    "components": [
                        "Card",
                        "Section",
                        "TextInput",
                        "SelectionInput",
                        "SelectionItem",
                        "DateTimePicker",
                    ],
                    "success": False,
                    "error": str(e),
                }
            )
            if verbose:
                logger.warning(f"  ❌ Form Card (Bug Report): {e}")

        # Scenario 11: RAG Evaluation Summary - 6 sections with varied content
        try:
            sections = [
                Section(
                    header="Experiment 1: Original 27 Questions",
                    widgets=[
                        DecoratedText(text="Avg Confidence: 0.77 | High (≥0.9): 4%"),
                        ButtonList(
                            buttons=[
                                Button(
                                    text="View Langfuse Run",
                                    on_click=OnClick(
                                        open_link=OpenLink(
                                            url="https://langfuse.example.com/run1"
                                        )
                                    ),
                                )
                            ]
                        ),
                    ],
                ),
                Section(
                    header="Experiment 2: Gotcha Questions",
                    widgets=[
                        DecoratedText(text="Avg Confidence: 0.92 | High (≥0.9): 65%"),
                        ButtonList(
                            buttons=[
                                Button(
                                    text="View Langfuse Run",
                                    on_click=OnClick(
                                        open_link=OpenLink(
                                            url="https://langfuse.example.com/run2"
                                        )
                                    ),
                                )
                            ]
                        ),
                    ],
                ),
                Section(
                    header="🔍 Key Finding: 11 RAG Mismatches",
                    widgets=[
                        DecoratedText(
                            text="RAG retrieved section headers instead of precise policy rules"
                        ),
                    ],
                ),
                Section(
                    header="💡 Recommendations",
                    widgets=[
                        DecoratedText(text="1. Chunk boundary tuning"),
                        DecoratedText(text="2. Metadata boosting"),
                        DecoratedText(text="3. Cross-encoder re-ranking"),
                    ],
                ),
            ]
            card = Card(
                header=CardHeader(
                    title="📊 RAG Evaluation Summary", subtitle="Jan 23, 2026"
                ),
                sections=sections,
            )
            rendered = card.render()

            complex_scenarios.append(
                {
                    "scenario": "RAG Evaluation Summary (Multi-Section Report)",
                    "components": [
                        "Card",
                        "CardHeader",
                        "Section",
                        "DecoratedText",
                        "ButtonList",
                        "Button",
                        "OnClick",
                        "OpenLink",
                    ],
                    "success": True,
                    "rendered_json": rendered,
                    "structure_description": "Multi-section report card with metrics, findings, and action buttons",
                }
            )
            if verbose:
                logger.info("  ✅ RAG Evaluation Summary (Multi-Section Report)")
        except Exception as e:
            complex_scenarios.append(
                {
                    "scenario": "RAG Evaluation Summary (Multi-Section Report)",
                    "components": [
                        "Card",
                        "CardHeader",
                        "Section",
                        "DecoratedText",
                        "ButtonList",
                        "Button",
                        "OnClick",
                        "OpenLink",
                    ],
                    "success": False,
                    "error": str(e),
                }
            )
            if verbose:
                logger.warning(f"  ❌ RAG Evaluation Summary: {e}")

        # Scenario 12: ChipList with clickable chips
        try:
            chip_list = ChipList(
                chips=[
                    Chip(
                        label="Python",
                        on_click=OnClick(open_link=OpenLink(url="https://python.org")),
                    ),
                    Chip(
                        label="JavaScript",
                        on_click=OnClick(open_link=OpenLink(url="https://js.org")),
                    ),
                    Chip(
                        label="Rust",
                        on_click=OnClick(
                            open_link=OpenLink(url="https://rust-lang.org")
                        ),
                    ),
                ]
            )
            rendered = chip_list.render()

            complex_scenarios.append(
                {
                    "scenario": "ChipList with Clickable Chips",
                    "components": ["ChipList", "Chip", "OnClick", "OpenLink"],
                    "success": True,
                    "rendered_json": rendered,
                    "structure_description": "Chip list with clickable tag-style chips",
                }
            )
            if verbose:
                logger.info("  ✅ ChipList with Clickable Chips")
        except Exception as e:
            complex_scenarios.append(
                {
                    "scenario": "ChipList with Clickable Chips",
                    "components": ["ChipList", "Chip", "OnClick", "OpenLink"],
                    "success": False,
                    "error": str(e),
                }
            )
            if verbose:
                logger.warning(f"  ❌ ChipList with Clickable Chips: {e}")

    except ImportError as e:
        logger.error(f"Could not import card_framework components: {e}")

    return complex_scenarios


def store_complex_patterns(scenarios: List[Dict], dry_run: bool = False) -> int:
    """Store complex nesting scenarios as patterns."""
    if dry_run:
        logger.info("DRY RUN: Would store complex patterns (not actually storing)")
        successful = [s for s in scenarios if s.get("success")]
        return len(successful)

    try:
        from gchat.feedback_loop import get_feedback_loop

        feedback_loop = get_feedback_loop()

        stored = 0
        for scenario in scenarios:
            if not scenario.get("success"):
                continue

            component_paths = [
                (
                    f"card_framework.v2.widgets.{comp}"
                    if comp != "Section"
                    else f"card_framework.v2.{comp}"
                )
                for comp in scenario["components"]
            ]

            card_description = f"Complex card: {scenario['scenario']}"

            try:
                point_id = feedback_loop.store_instance_pattern(
                    card_description=card_description,
                    component_paths=component_paths,
                    instance_params=scenario.get("rendered_json", {}),
                    content_feedback="positive",
                    form_feedback="positive",
                    structure_description=scenario.get("structure_description"),
                    user_email="validation_pipeline@system.local",
                    card_id=f"complex-{scenario['scenario'].replace(' ', '-').lower()}",
                )

                if point_id:
                    stored += 1
                    logger.debug(f"Stored complex pattern: {scenario['scenario']}")

            except Exception as e:
                logger.warning(f"Failed to store complex pattern: {e}")

        return stored

    except ImportError as e:
        logger.error(f"Could not import feedback_loop: {e}")
        return 0


# =========================================================================
# RANDOM COMBINATION GENERATOR
# =========================================================================


class RandomCardGenerator:
    """
    Generate random valid card combinations based on Qdrant relationship data.

    Uses relationship data to understand what can nest inside what, then
    randomly assembles valid cards.

    COMPONENTS FROM QDRANT (matching Google Chat Card Builder):
    ============================================================
    📦 Widgets (in Section):
      - Image -> [OnClick]
      - DecoratedText -> [Icon, OnClick, SwitchControl, Button]
      - TextParagraph
      - ButtonList -> [Button]
      - Grid -> [OnClick, BorderStyle, GridItem]
      - ChipList -> [Chip, Layout]
      - TextInput -> [Action, Type, Validation, Suggestions]
      - SelectionInput -> [SelectionType, PlatformDataSource, Action]
      - DateTimePicker -> [Action, Type]
      - Divider
      - Columns -> [Column -> [Widget, VerticalAlignment, HorizontalSizeStyle]]

    🏗️ Structures:
      - Card -> [CardHeader, CardFixedFooter, DisplayStyle, Section]
      - Section -> [CollapseControl, Widget]
      - CardHeader -> [ImageType]
      - CardFixedFooter -> [Button] (Footer!)

    ⚡ Actions:
      - OnClick -> [Action, OpenLink, OverflowMenu]
      - OverflowMenu -> [OverflowMenuItem]
      - OverflowMenuItem -> [Widget, Icon]
    """

    def __init__(self, verbose: bool = False, use_jinja_styling: bool = True):
        self.verbose = verbose
        self._use_jinja_styling = use_jinja_styling
        self._components = {}
        self._relationships = {}
        # Coverage tracking - ensure we use all parents and children
        self._used_parents: Set[str] = set()
        self._used_children: Set[str] = set()
        self._all_parents: Set[str] = set()
        self._all_children: Set[str] = set()
        # Current theme for styled content
        self._current_theme = get_random_theme() if use_jinja_styling else None
        self._load_components()

    def _track_usage(self, parent: str = None, child: str = None):
        """Track which components have been used."""
        if parent:
            self._used_parents.add(parent)
        if child:
            self._used_children.add(child)

    def get_coverage_report(self) -> Dict[str, Any]:
        """Get coverage report showing which components have/haven't been used."""
        unused_parents = self._all_parents - self._used_parents
        unused_children = self._all_children - self._used_children

        return {
            "total_parents": len(self._all_parents),
            "used_parents": len(self._used_parents),
            "unused_parents": list(unused_parents),
            "total_children": len(self._all_children),
            "used_children": len(self._used_children),
            "unused_children": list(unused_children),
            "parent_coverage": (
                len(self._used_parents) / len(self._all_parents) * 100
                if self._all_parents
                else 0
            ),
            "child_coverage": (
                len(self._used_children) / len(self._all_children) * 100
                if self._all_children
                else 0
            ),
        }

    def get_uncovered_widget(self) -> Optional[str]:
        """Get a widget type that hasn't been used yet, prioritizing coverage."""
        # Widgets that can go in sections
        section_widgets = [
            "Image",
            "DecoratedText",
            "TextParagraph",
            "ButtonList",
            "Grid",
            "ChipList",
            "SelectionInput",
            "TextInput",
            "DateTimePicker",
            "Divider",
            "Columns",
            "OverflowMenu",
        ]

        # Find unused ones first
        for widget in section_widgets:
            if widget not in self._used_parents and widget in self._components:
                return widget

        # All covered, return random
        return None

    def _load_components(self):
        """Load all components and their relationships from card_framework."""
        try:
            from card_framework.v2 import Card, CardHeader, Section
            from card_framework.v2.widgets import (
                Button,
                ButtonList,
                Chip,
                ChipList,
                DateTimePicker,
                DecoratedText,
                Divider,
                Grid,
                GridItem,
                Icon,
                Image,
                ImageComponent,
                OnClick,
                OpenLink,
                SelectionInput,
                SelectionItem,
                TextInput,
                TextParagraph,
            )

            self._components = {
                # =====================================================
                # WIDGETS (can go in a Section)
                # Matching Google Chat Card Builder element list
                # =====================================================
                "Image": Image,
                "DecoratedText": DecoratedText,
                "TextParagraph": TextParagraph,
                "ButtonList": ButtonList,
                "Grid": Grid,
                "ChipList": ChipList,
                "TextInput": TextInput,
                "SelectionInput": SelectionInput,
                "DateTimePicker": DateTimePicker,
                "Divider": Divider,
                # =====================================================
                # BUILDING BLOCKS (children of widgets)
                # =====================================================
                "Button": Button,
                "GridItem": GridItem,
                "ImageComponent": ImageComponent,
                "Chip": Chip,
                "SelectionItem": SelectionItem,
                "OnClick": OnClick,
                "OpenLink": OpenLink,
                "Icon": Icon,
                # =====================================================
                # STRUCTURE
                # =====================================================
                "Section": Section,
                "Card": Card,
                "CardHeader": CardHeader,
            }

            # Try to load advanced components (may not exist in all versions)
            try:
                from card_framework.v2.widgets import Column, Columns

                self._components["Columns"] = Columns
                self._components["Column"] = Column
                logger.info("  ✅ Loaded Columns/Column widgets")
            except ImportError:
                logger.debug("  ⚠️ Columns widget not available")

            try:
                from card_framework.v2.widgets import OverflowMenu, OverflowMenuItem

                self._components["OverflowMenu"] = OverflowMenu
                self._components["OverflowMenuItem"] = OverflowMenuItem
                logger.info("  ✅ Loaded OverflowMenu widgets")
            except ImportError:
                logger.debug("  ⚠️ OverflowMenu widget not available")

            try:
                from card_framework.v2.widgets import SwitchControl

                self._components["SwitchControl"] = SwitchControl
                logger.info("  ✅ Loaded SwitchControl widget")
            except ImportError:
                logger.debug("  ⚠️ SwitchControl widget not available")

            try:
                from card_framework.v2.card import CardFixedFooter

                self._components["CardFixedFooter"] = CardFixedFooter
                logger.info("  ✅ Loaded CardFixedFooter (Footer)")
            except ImportError:
                logger.debug("  ⚠️ CardFixedFooter not available")

            # =====================================================
            # RELATIONSHIPS - Load from Qdrant (REQUIRED)
            # No fallback - we MUST use the indexed relationships
            # =====================================================
            self._relationships = self._load_relationships_from_qdrant()

            if not self._relationships:
                raise RuntimeError(
                    "❌ No relationships loaded from Qdrant! "
                    "Ensure ModuleWrapper has indexed card_framework with relationships. "
                    "Run: wrapper.enrich_components_with_relationships()"
                )

            logger.info(f"  📦 Loaded {len(self._components)} components")
            logger.info(
                f"  🔗 Loaded {len(self._relationships)} relationship mappings from Qdrant"
            )

        except ImportError as e:
            logger.error(f"Could not import components: {e}")

    def _load_relationships_from_qdrant(self) -> Dict[str, List[str]]:
        """
        Load component relationships dynamically from Qdrant collection.

        This pulls the ACTUAL relationships indexed during module ingestion,
        ensuring we test combinations that match our indexed schema.
        """
        try:
            from qdrant_client import models

            from config.qdrant_client import get_qdrant_client
            from config.settings import settings

            client = get_qdrant_client()
            if not client:
                return {}

            # Query all class components with relationships
            results, _ = client.scroll(
                collection_name=settings.card_collection,
                scroll_filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="type", match=models.MatchValue(value="class")
                        ),
                    ]
                ),
                limit=500,
                with_payload=["name", "relationships"],
            )

            # Build relationship map from Qdrant data
            relationships = {}
            for point in results:
                name = point.payload.get("name", "")
                rels = point.payload.get("relationships", {})
                children = rels.get("child_classes", [])

                if name and children:
                    # Deduplicate - some components appear multiple times
                    if name not in relationships:
                        relationships[name] = []
                    for child in children:
                        if child not in relationships[name]:
                            relationships[name].append(child)

            # Populate coverage tracking sets
            for parent, children in relationships.items():
                self._all_parents.add(parent)
                for child in children:
                    self._all_children.add(child)

            logger.info(f"  ✅ Loaded {len(relationships)} relationships from Qdrant")
            logger.info(
                f"  📊 Coverage targets: {len(self._all_parents)} parents, {len(self._all_children)} children"
            )
            return relationships

        except Exception as e:
            logger.warning(f"  ⚠️ Could not load relationships from Qdrant: {e}")
            return {}

    # NOTE: _get_default_relationships() REMOVED
    # We intentionally have NO FALLBACK - relationships MUST come from Qdrant
    # This ensures we're testing against the actual indexed schema

    def _random_image_url(self) -> str:
        """Get a random Google-hosted image URL that actually works."""
        return random.choice(VALID_IMAGE_URLS)

    def _random_text(self, field: str = "text", styled: bool = True) -> str:
        """Generate random text content with optional Jinja styling."""
        texts = {
            "title": [
                "Dashboard",
                "Report",
                "Summary",
                "Overview",
                "Status",
                "Metrics",
            ],
            "subtitle": ["Generated", "Updated", "Live Data", "Real-time"],
            "text": ["Item content", "Description here", "Status: Active", "Details"],
            "label": ["Option A", "Choice B", "Selection C", "Item D"],
            "name": [f"field_{random.randint(100, 999)}"],
        }
        options = texts.get(field, texts["text"])
        base_text = random.choice(options)

        if not styled or not self._use_jinja_styling:
            return base_text

        # Apply Jinja styling based on field type
        if field == "title":
            return get_random_styled_title()
        elif field == "text":
            # Randomly choose between different styled text generators
            generators = [
                get_random_styled_text,
                get_random_status_text,
                get_random_metric_text,
            ]
            return random.choice(generators)()
        elif field == "label":
            colors = ["#1a73e8", "#34a853", "#8430ce", "#00acc1", "#fbbc05"]
            return render_jinja_template(
                "{{ label | color(color) }}",
                label=base_text,
                color=random.choice(colors),
            )
        elif field == "subtitle":
            return render_jinja_template("{{ text | muted_text }}", text=base_text)

        return base_text

    def _random_styled_content(self, content_type: str = "status") -> str:
        """Generate random styled content using Jinja templates based on content type."""
        if content_type == "status":
            return get_random_status_text()
        elif content_type == "metric":
            return get_random_metric_text()
        elif content_type == "price":
            return get_random_price_text()
        else:
            return get_random_styled_text()

    def _random_url(self) -> str:
        """Generate a random valid URL."""
        domains = ["google.com", "github.com", "developers.google.com/chat"]
        return f"https://{random.choice(domains)}"

    def _build_onclick(self) -> Any:
        """Build a random OnClick action."""
        OnClick = self._components.get("OnClick")
        OpenLink = self._components.get("OpenLink")
        if OnClick and OpenLink:
            self._track_usage(child="OpenLink")
            return OnClick(open_link=OpenLink(url=self._random_url()))
        return None

    def _build_icon(self) -> Any:
        """Build a random Icon."""
        Icon = self._components.get("Icon")
        if Icon and hasattr(Icon, "KnownIcon"):
            icons = ["STAR", "DESCRIPTION", "EMAIL", "PHONE", "BOOKMARK"]
            icon_name = random.choice(icons)
            if hasattr(Icon.KnownIcon, icon_name):
                return Icon(known_icon=getattr(Icon.KnownIcon, icon_name))
        return None

    def _build_button(self, with_icon: bool = False, with_onclick: bool = True) -> Any:
        """Build a random Button. Note: Button text does NOT support HTML styling."""
        Button = self._components["Button"]
        # Button text does NOT support HTML - use plain text only
        kwargs = {"text": self._random_text("label", styled=False)}

        if with_icon and random.random() > 0.5:
            icon = self._build_icon()
            if icon:
                kwargs["icon"] = icon
                self._track_usage(child="Icon")

        if with_onclick:
            onclick = self._build_onclick()
            if onclick:
                kwargs["on_click"] = onclick
                self._track_usage(child="OnClick")

        self._track_usage(child="Button")
        return Button(**kwargs)

    def _build_chip(self) -> Any:
        """Build a random Chip. Note: Chip label does NOT support HTML styling."""
        Chip = self._components["Chip"]
        # Chip label does NOT support HTML - use plain text only
        kwargs = {"label": self._random_text("label", styled=False)}

        if random.random() > 0.5:
            icon = self._build_icon()
            if icon:
                kwargs["icon"] = icon
                self._track_usage(child="Icon")

        onclick = self._build_onclick()
        if onclick:
            kwargs["on_click"] = onclick
            self._track_usage(child="OnClick")

        self._track_usage(child="Chip")
        return Chip(**kwargs)

    def _build_grid_item(self, index: int) -> Any:
        """Build a GridItem (no onClick - that's on Grid level)."""
        GridItem = self._components["GridItem"]
        ImageComponent = self._components.get("ImageComponent")

        kwargs = {
            "id": f"item_{index}",
            "title": f"Item {index + 1}",
        }

        if ImageComponent:
            kwargs["image"] = ImageComponent(image_uri=self._random_image_url())
            self._track_usage(child="ImageComponent")

        self._track_usage(child="GridItem")
        return GridItem(**kwargs)

    def _build_selection_item(self, index: int) -> Any:
        """Build a SelectionItem."""
        SelectionItem = self._components["SelectionItem"]
        self._track_usage(child="SelectionItem")
        return SelectionItem(
            text=f"Option {index + 1}",
            value=f"opt_{index}",
            bottom_text=f"Description for option {index + 1}",
        )

    def build_random_widget(self, prefer_uncovered: bool = True) -> Tuple[Any, str]:
        """
        Build a random widget with random children.

        Args:
            prefer_uncovered: If True, prioritize widgets that haven't been used yet

        Returns (widget_instance, description).

        ALL available widget types from card_framework:
        - Image: Standalone image with optional onClick
        - DecoratedText: Rich text with labels, icons, buttons
        - TextParagraph: HTML-formatted text
        - ButtonList: Multiple buttons
        - Grid: Image grid with items
        - ChipList: Tag-style chips
        - SelectionInput: Dropdowns, checkboxes, radio buttons
        - TextInput: Single/multi-line text input
        - DateTimePicker: Date and time selection
        - Divider: Horizontal line separator
        """
        # ALL widget types matching Google Chat Card Builder
        widget_types = [
            # Basic widgets
            "Image",
            "DecoratedText",
            "TextParagraph",
            "ButtonList",
            "Grid",
            "ChipList",
            "Divider",
            # Form widgets
            "SelectionInput",
            "TextInput",
            "DateTimePicker",
            # Layout widgets
            "Columns",
            # Advanced (inside buttons)
            "OverflowMenu",
        ]

        # Filter to available components
        available = [w for w in widget_types if w in self._components]

        # Prioritize uncovered widgets for better diversity
        if prefer_uncovered:
            uncovered = [w for w in available if w not in self._used_parents]
            if uncovered:
                widget_type = random.choice(uncovered)
            else:
                widget_type = random.choice(available)
        else:
            widget_type = random.choice(available)

        # Track this widget as used
        self._track_usage(parent=widget_type)

        description = f"Random {widget_type}"

        if widget_type == "Image":
            Image = self._components["Image"]
            onclick = self._build_onclick() if random.random() > 0.3 else None
            kwargs = {"image_url": self._random_image_url(), "alt_text": "Random image"}
            if onclick:
                kwargs["on_click"] = onclick
                description += " with onClick"
            return Image(**kwargs), description

        elif widget_type == "DecoratedText":
            DecoratedText = self._components["DecoratedText"]

            # Use Jinja-styled content based on random content type
            if self._use_jinja_styling:
                content_types = ["status", "metric", "text"]
                content_type = random.choice(content_types)
                kwargs = {"text": self._random_styled_content(content_type)}
                description += f" ({content_type} styled)"
            else:
                kwargs = {"text": self._random_text()}

            if random.random() > 0.5:
                # DecoratedText top_label does NOT support HTML - use plain text only
                labels = ["Status", "Metric", "Info", "Value", "Result"]
                kwargs["top_label"] = random.choice(labels)
            if random.random() > 0.5:
                # DecoratedText bottom_label does NOT support HTML - use plain text only
                kwargs["bottom_label"] = "Details"
            if random.random() > 0.5:
                icon = self._build_icon()
                if icon:
                    kwargs["start_icon"] = icon
                    description += " with Icon"
            if random.random() > 0.5:
                kwargs["button"] = self._build_button(with_onclick=True)
                description += " with Button"

            return DecoratedText(**kwargs), description

        elif widget_type == "TextParagraph":
            TextParagraph = self._components["TextParagraph"]

            if self._use_jinja_styling:
                # Generate rich styled text paragraphs using Jinja templates
                styled_templates = [
                    # Status-style paragraphs
                    '{{ "System Status" | bold }}: {{ status | success_text }}',
                    '{{ label | muted_text }}: {{ value | color("#1a73e8") | bold }}',
                    '{{ "Alert" | badge("#fbbc05") }} {{ message }}',
                    # Price-style paragraphs
                    '{{ "Price" | muted_text }}: {{ price | price("USD") }}',
                    '{{ "SALE" | badge("#ea4335") }} {{ price | price("USD") }} (was {{ original | price("USD") | strike }})',
                    # Metric-style paragraphs
                    "{{ metric | bold }}: {{ value | color(color) }}%",
                    '{{ "Build" | bold }} #{{ number }}: {{ status | success_text }}',
                    # Rich text combinations
                    '{{ title | color("#1a73e8") | bold }}\n{{ description | muted_text }}',
                ]
                template = random.choice(styled_templates)

                # Generate context values
                context = {
                    "status": random.choice(["Online", "Active", "Healthy", "Running"]),
                    "label": random.choice(["CPU", "Memory", "Latency", "Requests"]),
                    "value": str(random.randint(10, 99)),
                    "message": "Check system status",
                    "price": round(random.uniform(9.99, 199.99), 2),
                    "original": round(random.uniform(100, 299.99), 2),
                    "metric": random.choice(["Coverage", "Success Rate", "Uptime"]),
                    "color": random.choice(["#34a853", "#1a73e8", "#fbbc05"]),
                    "number": random.randint(1000, 9999),
                    "title": random.choice(["Overview", "Summary", "Report"]),
                    "description": "Generated with Jinja templating",
                }

                try:
                    styled_text = render_jinja_template(template, **context)
                    description += " (Jinja styled)"
                except Exception:
                    styled_text = '<font color="#1a73e8">Styled text content</font>'

                return TextParagraph(text=styled_text), description
            else:
                html_texts = [
                    "<b>Bold text</b> and <i>italic</i>",
                    '<font color="#1a73e8">Colored text</font>',
                    "Plain text content here",
                ]
                return TextParagraph(text=random.choice(html_texts)), description

        elif widget_type == "ButtonList":
            ButtonList = self._components["ButtonList"]
            num_buttons = random.randint(1, 3)
            buttons = [self._build_button(with_icon=True) for _ in range(num_buttons)]
            description += f" with {num_buttons} buttons"
            return ButtonList(buttons=buttons), description

        elif widget_type == "Grid":
            Grid = self._components["Grid"]
            num_items = random.randint(2, 4)
            items = [self._build_grid_item(i) for i in range(num_items)]
            # Grid title does NOT support HTML - use plain text only
            kwargs = {
                "title": self._random_text("title", styled=False),
                "column_count": random.choice([2, 3]),
                "items": items,
            }
            # Grid-level onClick (not per item!)
            if random.random() > 0.5:
                onclick = self._build_onclick()
                if onclick:
                    kwargs["on_click"] = onclick
                    description += " with grid-level onClick"
            description += f" ({num_items} items)"
            return Grid(**kwargs), description

        elif widget_type == "ChipList":
            ChipList = self._components["ChipList"]
            num_chips = random.randint(2, 4)
            chips = [self._build_chip() for _ in range(num_chips)]
            description += f" with {num_chips} chips"
            return ChipList(chips=chips), description

        elif widget_type == "SelectionInput":
            SelectionInput = self._components["SelectionInput"]
            SelectionItem = self._components.get("SelectionItem")

            if not SelectionItem:
                # Fallback if SelectionItem not available
                TextParagraph = self._components["TextParagraph"]
                return (
                    TextParagraph(text="Selection placeholder"),
                    "Fallback TextParagraph",
                )

            # Get SelectionType enum (nested inside SelectionInput)
            SelectionType = getattr(SelectionInput, "SelectionType", None)
            if SelectionType:
                selection_types = ["DROPDOWN", "RADIO_BUTTON", "CHECK_BOX"]
                type_name = random.choice(selection_types)
                sel_type = getattr(SelectionType, type_name, SelectionType.DROPDOWN)
            else:
                sel_type = None

            num_items = random.randint(2, 4)
            items = []
            for i in range(num_items):
                items.append(
                    SelectionItem(
                        text=f"Option {i + 1}",
                        value=f"opt_{i}",
                        bottom_text=(
                            f"Description {i + 1}" if random.random() > 0.5 else None
                        ),
                    )
                )
                self._track_usage(child="SelectionItem")

            # SelectionInput label does NOT support HTML - use plain text only
            kwargs = {
                "name": f"selection_{random.randint(100, 999)}",
                "label": self._random_text("label", styled=False),
                "items": items,
            }
            if sel_type:
                kwargs["type"] = sel_type
                description += f" ({type_name})"

            return SelectionInput(**kwargs), description

        elif widget_type == "TextInput":
            TextInput = self._components["TextInput"]

            # Get Type enum (nested inside TextInput)
            InputType = getattr(TextInput, "Type", None)
            is_multiline = random.random() > 0.5

            # TextInput label does NOT support HTML - use plain text only
            kwargs = {
                "name": f"input_{random.randint(100, 999)}",
                "label": self._random_text("label", styled=False),
            }

            if InputType:
                if is_multiline and hasattr(InputType, "MULTIPLE_LINE"):
                    kwargs["type"] = InputType.MULTIPLE_LINE
                    description += " (multiline)"
                elif hasattr(InputType, "SINGLE_LINE"):
                    kwargs["type"] = InputType.SINGLE_LINE

            if random.random() > 0.5:
                kwargs["hint_text"] = "Enter value..."

            return TextInput(**kwargs), description

        elif widget_type == "DateTimePicker":
            DateTimePicker = self._components["DateTimePicker"]

            # DateTimePicker label does NOT support HTML - use plain text only
            kwargs = {
                "name": f"date_{random.randint(100, 999)}",
                "label": self._random_text("label", styled=False),
            }

            # Get Type enum if available
            PickerType = getattr(DateTimePicker, "DateTimePickerType", None)
            if PickerType:
                type_names = ["DATE_AND_TIME", "DATE_ONLY", "TIME_ONLY"]
                type_name = random.choice(type_names)
                if hasattr(PickerType, type_name):
                    kwargs["type"] = getattr(PickerType, type_name)
                    description += f" ({type_name})"

            return DateTimePicker(**kwargs), description

        elif widget_type == "Divider":
            Divider = self._components["Divider"]
            return Divider(), description

        elif widget_type == "Columns":
            Columns = self._components.get("Columns")
            Column = self._components.get("Column")

            if not Columns or not Column:
                # Fallback if Columns not available
                TextParagraph = self._components["TextParagraph"]
                return (
                    TextParagraph(text="Columns placeholder"),
                    "Fallback TextParagraph",
                )

            # Build 2 columns with random widgets
            columns = []
            for col_idx in range(2):
                # Each column gets 1-2 widgets
                col_widgets = []
                num_widgets = random.randint(1, 2)

                for _ in range(num_widgets):
                    # Column supports: DecoratedText, TextParagraph, Image, ButtonList
                    widget_type_for_col = random.choice(
                        ["DecoratedText", "TextParagraph", "Image"]
                    )
                    if widget_type_for_col == "DecoratedText":
                        DecoratedText = self._components["DecoratedText"]
                        col_widgets.append(
                            DecoratedText(
                                text=self._random_text(), top_label=f"COL {col_idx + 1}"
                            )
                        )
                        self._track_usage(child="DecoratedText")
                    elif widget_type_for_col == "Image":
                        Image = self._components["Image"]
                        col_widgets.append(
                            Image(
                                image_url=self._random_image_url(),
                                alt_text="Column image",
                            )
                        )
                        self._track_usage(child="Image")
                    else:
                        TextParagraph = self._components["TextParagraph"]
                        col_widgets.append(TextParagraph(text=self._random_text()))
                        self._track_usage(child="TextParagraph")

                self._track_usage(child="Column")
                columns.append(Column(widgets=col_widgets))

            description += " (2 columns)"
            return Columns(column_items=columns), description

        elif widget_type == "OverflowMenu":
            # OverflowMenu is typically inside a Button's onClick
            # Build a ButtonList with overflow menu
            ButtonList = self._components["ButtonList"]
            Button = self._components["Button"]
            OnClick = self._components["OnClick"]
            OpenLink = self._components["OpenLink"]
            OverflowMenu = self._components.get("OverflowMenu")
            OverflowMenuItem = self._components.get("OverflowMenuItem")

            if not OverflowMenu or not OverflowMenuItem:
                # Fallback to regular button
                return (
                    ButtonList(buttons=[self._build_button()]),
                    "ButtonList (overflow not available)",
                )

            # Build overflow menu items
            menu_items = []
            for i in range(random.randint(2, 4)):
                menu_items.append(
                    OverflowMenuItem(
                        text=f"Menu Item {i + 1}",
                        start_icon=self._build_icon(),
                        on_click=OnClick(open_link=OpenLink(url=self._random_url())),
                    )
                )
                self._track_usage(child="OverflowMenuItem")
                self._track_usage(child="OpenLink")

            self._track_usage(child="OverflowMenu")
            overflow_menu = OverflowMenu(items=menu_items)
            self._track_usage(child="Button")
            self._track_usage(child="OnClick")
            button = Button(text="More", on_click=OnClick(overflow_menu=overflow_menu))

            description = "ButtonList with OverflowMenu"
            return ButtonList(buttons=[button]), description

        # Fallback
        TextParagraph = self._components["TextParagraph"]
        return TextParagraph(text="Fallback content"), "Fallback TextParagraph"

    def build_random_section(self, num_widgets: int = None) -> Tuple[Any, str]:
        """Build a random section with random widgets."""
        Section = self._components["Section"]

        if num_widgets is None:
            num_widgets = random.randint(1, 4)

        widgets = []
        descriptions = []
        for _ in range(num_widgets):
            widget, desc = self.build_random_widget()
            widgets.append(widget)
            descriptions.append(desc)

        # Section header DOES support HTML styling
        section = Section(
            header=self._random_text("title", styled=True), widgets=widgets
        )

        return section, f"Section with: {', '.join(descriptions)}"

    def _build_footer(self) -> Tuple[Any, str]:
        """Build a random footer with primary and optional secondary button."""
        CardFixedFooter = self._components.get("CardFixedFooter")
        Button = self._components["Button"]

        if not CardFixedFooter:
            return None, ""

        primary_btn = self._build_button(with_icon=True, with_onclick=True)

        kwargs = {"primary_button": primary_btn}

        # Random secondary button
        if random.random() > 0.5:
            secondary_btn = Button(text="Cancel")
            kwargs["secondary_button"] = secondary_btn

        return CardFixedFooter(**kwargs), "Footer with buttons"

    def build_random_card(self, num_sections: int = None) -> Tuple[Dict, str]:
        """
        Build a random complete card.

        Returns (rendered_json, description).

        Card structure from Qdrant relationships:
        - Card -> [CardHeader, CardFixedFooter, DisplayStyle, Section]
        """
        Card = self._components["Card"]
        CardHeader = self._components.get("CardHeader")

        if num_sections is None:
            num_sections = random.randint(1, 3)

        sections = []
        all_descriptions = []
        for _ in range(num_sections):
            section, desc = self.build_random_section()
            sections.append(section)
            all_descriptions.append(desc)

        kwargs = {"sections": sections}

        # Random header (70% chance)
        # CardHeader title/subtitle do NOT support HTML - use plain text only
        if CardHeader and random.random() > 0.3:
            kwargs["header"] = CardHeader(
                title=self._random_text("title", styled=False),
                subtitle=self._random_text("subtitle", styled=False),
                image_url=self._random_image_url(),
            )

        # Random footer (30% chance)
        if random.random() > 0.7:
            footer, footer_desc = self._build_footer()
            if footer:
                kwargs["fixed_footer"] = footer
                all_descriptions.append(footer_desc)

        card = Card(**kwargs)
        rendered = card.render()

        # Convert to camelCase for API
        rendered_camel = convert_to_camel_case(rendered)

        description = f"Card with {num_sections} sections: " + " | ".join(
            all_descriptions
        )
        return rendered_camel, description


def run_random_webhook_tests(
    num_tests: int = 10,
    webhook_url: str = None,
    verbose: bool = False,
    delay: float = 1.0,
    ensure_coverage: bool = True,
    use_jinja_styling: bool = True,
) -> List[Dict[str, Any]]:
    """
    Generate random cards and send them to the webhook to validate.

    Args:
        num_tests: Number of random cards to generate
        webhook_url: Webhook URL (uses TEST_CHAT_WEBHOOK env if None)
        verbose: Show detailed output
        delay: Delay between webhook requests in seconds
        ensure_coverage: If True, ensure ALL parents and children are used at least once
        use_jinja_styling: If True, apply Jinja template styling to text content

    Returns list of test results.
    """
    logger.info("")
    logger.info("=" * 70)
    logger.info(f"RANDOM WEBHOOK VALIDATION ({num_tests} tests)")
    if use_jinja_styling:
        logger.info(f"  Jinja styling: ENABLED (rich HTML styling)")
    logger.info("=" * 70)

    if not webhook_url and not TEST_WEBHOOK:
        logger.error("No webhook URL! Set TEST_CHAT_WEBHOOK env var or pass --webhook")
        return []

    generator = RandomCardGenerator(
        verbose=verbose, use_jinja_styling=use_jinja_styling
    )
    results = []

    for i in range(num_tests):
        logger.info(f"\nTest {i + 1}/{num_tests}:")

        try:
            card_json, description = generator.build_random_card()

            if verbose:
                logger.info(f"  Description: {description}")
                logger.info(
                    f"  JSON preview: {json.dumps(card_json, indent=2)[:300]}..."
                )

            # Send to webhook
            success, error = send_card_to_webhook(card_json, webhook_url)

            result = {
                "test_num": i + 1,
                "description": description,
                "success": success,
                "error": error if not success else None,
                "card_json": card_json,
            }
            results.append(result)

            if success:
                logger.info(f"  ✅ SUCCESS: Card sent to webhook")
            else:
                # Parse error to get actual message
                try:
                    error_json = (
                        json.loads(error)
                        if error.startswith("{")
                        else {"message": error}
                    )
                    error_msg = error_json.get("error", {}).get("message", error[:300])
                except:
                    error_msg = error[:300]
                logger.warning(f"  ❌ FAILED: {error_msg}")

            # Rate limit
            if i < num_tests - 1:
                time.sleep(delay)

        except Exception as e:
            logger.error(f"  ❌ BUILD ERROR: {e}")
            results.append(
                {
                    "test_num": i + 1,
                    "description": "Build failed",
                    "success": False,
                    "error": str(e),
                }
            )

    # Summary
    successful = sum(1 for r in results if r["success"])
    failed = sum(1 for r in results if not r["success"])

    logger.info("")
    logger.info("=" * 70)
    logger.info("RANDOM TEST SUMMARY")
    logger.info("=" * 70)
    logger.info(f"Total: {len(results)}")
    logger.info(f"Successful: {successful}")
    logger.info(f"Failed: {failed}")
    logger.info(
        f"Success rate: {successful / len(results) * 100:.1f}%" if results else "N/A"
    )

    if failed > 0:
        logger.info("\nFailed tests:")
        for r in results:
            if not r["success"]:
                logger.info(f"  Test {r['test_num']}: {r['error'][:100]}")

    # Coverage report
    if ensure_coverage:
        coverage = generator.get_coverage_report()
        logger.info("")
        logger.info("=" * 70)
        logger.info("COMPONENT COVERAGE REPORT")
        logger.info("=" * 70)
        logger.info(
            f"Parents used: {coverage['used_parents']}/{coverage['total_parents']} ({coverage['parent_coverage']:.1f}%)"
        )
        logger.info(
            f"Children used: {coverage['used_children']}/{coverage['total_children']} ({coverage['child_coverage']:.1f}%)"
        )

        if coverage["unused_parents"]:
            logger.info(f"\n⚠️ Unused parents ({len(coverage['unused_parents'])}):")
            for p in sorted(coverage["unused_parents"])[:20]:
                logger.info(f"  - {p}")

        if coverage["unused_children"]:
            logger.info(f"\n⚠️ Unused children ({len(coverage['unused_children'])}):")
            for c in sorted(coverage["unused_children"])[:20]:
                logger.info(f"  - {c}")

    return results


# =========================================================================
# INGESTION PIPELINE INTEGRATION
# =========================================================================


def validate_after_ingestion(
    num_tests: int = 20,
    webhook_url: str = None,
    store_patterns: bool = True,
    delay: float = 1.0,
) -> Dict[str, Any]:
    """
    Validate component combinations after ModuleWrapper ingestion.

    This function should be called AFTER ModuleWrapper has:
    1. Indexed components from a module
    2. Enriched components with relationships

    It will:
    1. Load ALL components from card_framework
    2. Load relationships FROM QDRANT (not hardcoded!)
    3. Generate diverse random combinations
    4. Validate against real Google Chat API via webhook
    5. Store validated patterns as positive examples

    Args:
        num_tests: Number of random combinations to test
        webhook_url: Webhook URL (uses TEST_CHAT_WEBHOOK env var if None)
        store_patterns: Whether to store validated patterns in feedback loop
        delay: Delay between webhook requests (to avoid rate limiting)

    Returns:
        Summary dict with success/failure counts and stored pattern count

    Usage in ingestion pipeline:
        ```python
        from adapters.module_wrapper import ModuleWrapper
        from scripts.validate_relationships import validate_after_ingestion

        # 1. Index the module
        wrapper = ModuleWrapper(module_or_name="card_framework", auto_initialize=True)

        # 2. Enrich with relationships
        wrapper.enrich_components_with_relationships()

        # 3. Validate combinations against real API
        results = validate_after_ingestion(num_tests=50, store_patterns=True)
        print(f"Validated: {results['successful']}/{results['total']} combinations")
        ```
    """
    logger.info("")
    logger.info("=" * 70)
    logger.info("POST-INGESTION VALIDATION PIPELINE")
    logger.info("=" * 70)

    # Run random webhook tests
    results = run_random_webhook_tests(
        num_tests=num_tests,
        webhook_url=webhook_url,
        verbose=True,
        delay=delay,
    )

    if not results:
        return {"total": 0, "successful": 0, "failed": 0, "stored": 0}

    successful = sum(1 for r in results if r["success"])
    failed = sum(1 for r in results if not r["success"])
    stored = 0

    # Store validated patterns
    if store_patterns and successful > 0:
        try:
            from gchat.feedback_loop import get_feedback_loop

            feedback_loop = get_feedback_loop()

            for r in results:
                if r["success"]:
                    try:
                        point_id = feedback_loop.store_instance_pattern(
                            card_description=r["description"],
                            component_paths=[],  # Dynamic combinations
                            instance_params=r.get("card_json", {}),
                            content_feedback="positive",
                            form_feedback="positive",
                            structure_description=f"Validated via webhook: {r['description']}",
                            user_email="ingestion_validation@system.local",
                            card_id=f"ingestion-{r['test_num']}-{int(time.time())}",
                        )
                        if point_id:
                            stored += 1
                    except Exception as e:
                        logger.warning(f"Failed to store pattern: {e}")

            logger.info(f"✅ Stored {stored} validated patterns in feedback loop")

        except ImportError as e:
            logger.warning(f"Could not import feedback_loop: {e}")

    summary = {
        "total": len(results),
        "successful": successful,
        "failed": failed,
        "stored": stored,
        "success_rate": successful / len(results) * 100 if results else 0,
    }

    logger.info("")
    logger.info("=" * 70)
    logger.info("VALIDATION SUMMARY")
    logger.info("=" * 70)
    logger.info(f"Total tested: {summary['total']}")
    logger.info(f"Successful: {summary['successful']}")
    logger.info(f"Failed: {summary['failed']}")
    logger.info(f"Success rate: {summary['success_rate']:.1f}%")
    logger.info(f"Patterns stored: {summary['stored']}")

    return summary


# =========================================================================
# MAIN
# =========================================================================


def main():
    parser = argparse.ArgumentParser(
        description="Validate component relationships and warm-start feedback patterns"
    )
    parser.add_argument(
        "--dry-run",
        "-n",
        action="store_true",
        help="Don't actually store patterns, just validate",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Show detailed validation output"
    )
    parser.add_argument(
        "--complex-only",
        action="store_true",
        help="Only run complex nesting validation",
    )
    parser.add_argument(
        "--send-to-webhook",
        action="store_true",
        help="Actually send cards to the test webhook for real API validation",
    )
    parser.add_argument(
        "--random-combos",
        type=int,
        default=0,
        metavar="N",
        help="Generate N random card combinations and test them (requires --send-to-webhook)",
    )
    parser.add_argument(
        "--webhook",
        type=str,
        default=None,
        help="Override webhook URL (default: TEST_CHAT_WEBHOOK env var)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Delay between webhook requests in seconds (default: 1.0)",
    )
    parser.add_argument(
        "--styled",
        "-s",
        action="store_true",
        default=True,
        help="Apply random colors/styles to text content (default: enabled)",
    )
    parser.add_argument(
        "--no-styled",
        action="store_true",
        help="Disable random styling (plain text only)",
    )
    parser.add_argument(
        "--color-scheme",
        type=str,
        default=None,
        choices=list(COLOR_SCHEMES.keys()),
        help=f"Use specific color scheme (choices: {', '.join(COLOR_SCHEMES.keys())})",
    )
    args = parser.parse_args()

    # Handle styled flag
    use_styled = args.styled and not args.no_styled

    # Update global styler if specific scheme requested
    global STYLER, CURRENT_COLOR_SCHEME
    if args.color_scheme:
        CURRENT_COLOR_SCHEME = args.color_scheme
        STYLER = ComponentStyler(scheme=args.color_scheme, target="gchat")
        logger.info(f"Using color scheme: {args.color_scheme}")

    total_stored = 0

    # =====================================================================
    # RANDOM WEBHOOK TESTING (--random-combos)
    # =====================================================================
    if args.random_combos > 0:
        if not args.send_to_webhook:
            logger.warning("--random-combos requires --send-to-webhook, enabling it")
            args.send_to_webhook = True

        results = run_random_webhook_tests(
            num_tests=args.random_combos,
            webhook_url=args.webhook,
            verbose=args.verbose,
            delay=args.delay,
            use_jinja_styling=use_styled,
        )

        # Store successful random patterns
        if not args.dry_run:
            from gchat.feedback_loop import get_feedback_loop

            feedback_loop = get_feedback_loop()

            stored = 0
            for r in results:
                if r["success"]:
                    try:
                        point_id = feedback_loop.store_instance_pattern(
                            card_description=r["description"],
                            component_paths=[],  # Dynamic, not tracked
                            instance_params=r["card_json"],
                            content_feedback="positive",
                            form_feedback="positive",
                            structure_description=f"Random validated: {r['description']}",
                            user_email="random_validation@system.local",
                            card_id=f"random-{r['test_num']}-{int(time.time())}",
                        )
                        if point_id:
                            stored += 1
                    except Exception as e:
                        logger.warning(f"Failed to store random pattern: {e}")

            logger.info(f"Stored {stored} validated random patterns")
            total_stored += stored

        return 0

    # =====================================================================
    # BASIC RELATIONSHIP VALIDATION
    # =====================================================================
    if not args.complex_only:
        validator = RelationshipValidator(verbose=args.verbose)
        results = validator.validate_all()

        summary = validator.summary()
        logger.info("")
        logger.info("=" * 70)
        logger.info("VALIDATION SUMMARY")
        logger.info("=" * 70)
        logger.info(f"Total relationships: {summary['total']}")
        logger.info(f"Successful: {summary['successful']}")
        logger.info(f"Failed: {summary['failed']}")
        logger.info(f"Success rate: {summary['success_rate']:.1f}%")

        if summary["failed_relationships"]:
            logger.info("")
            logger.info("Failed relationships:")
            for fail in summary["failed_relationships"][:10]:
                logger.info(f"  - {fail['parent']}.{fail['child']}: {fail['error']}")

        # Store patterns
        logger.info("")
        logger.info("=" * 70)
        logger.info("STORING PATTERNS")
        logger.info("=" * 70)
        stored = store_validated_patterns(results, dry_run=args.dry_run)
        logger.info(f"Stored {stored} validated relationship patterns")
        total_stored += stored

    # Complex nesting validation
    logger.info("")
    validator = RelationshipValidator(verbose=args.verbose)
    complex_results = validate_complex_nestings(
        validator, verbose=args.verbose, use_styled_content=use_styled
    )

    complex_success = sum(1 for r in complex_results if r.get("success"))
    complex_fail = sum(1 for r in complex_results if not r.get("success"))

    logger.info("")
    logger.info(
        f"Complex scenarios: {len(complex_results)} total, "
        f"{complex_success} success, {complex_fail} failed"
    )

    # =====================================================================
    # WEBHOOK VALIDATION FOR COMPLEX SCENARIOS
    # =====================================================================
    if args.send_to_webhook:
        webhook_url = args.webhook or TEST_WEBHOOK
        if not webhook_url:
            logger.error(
                "No webhook URL! Set TEST_CHAT_WEBHOOK env var or pass --webhook"
            )
        else:
            logger.info("")
            logger.info("=" * 70)
            logger.info("WEBHOOK VALIDATION (Complex Scenarios)")
            logger.info("=" * 70)

            webhook_success = 0
            webhook_fail = 0

            for scenario in complex_results:
                if not scenario.get("success") or not scenario.get("rendered_json"):
                    continue

                # Convert to camelCase and wrap for API
                card_json = convert_to_camel_case(scenario["rendered_json"])

                success, error = send_card_to_webhook(card_json, webhook_url)

                if success:
                    webhook_success += 1
                    if args.verbose:
                        logger.info(f"  ✅ {scenario['scenario']}")
                else:
                    webhook_fail += 1
                    logger.warning(f"  ❌ {scenario['scenario']}: {error[:100]}")

                time.sleep(args.delay)

            logger.info("")
            logger.info(
                f"Webhook results: {webhook_success} success, {webhook_fail} failed"
            )

    # Store complex patterns
    stored_complex = store_complex_patterns(complex_results, dry_run=args.dry_run)
    logger.info(f"Stored {stored_complex} complex nesting patterns")
    total_stored += stored_complex

    # Final summary
    logger.info("")
    logger.info("=" * 70)
    logger.info("FINAL SUMMARY")
    logger.info("=" * 70)
    logger.info(f"Total patterns stored: {total_stored}")
    if args.dry_run:
        logger.info("(DRY RUN - no patterns were actually stored)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
