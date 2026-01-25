"""
Template Component System

Wraps approved card patterns as first-class components that participate in the
Qdrant → ModuleWrapper → render() flow.

Architecture:
- TemplateComponent: Wraps template data and implements .render()
- TemplateRegistry: Loads templates from YAML files and Qdrant
- Templates can be "promoted" from instance_patterns when they get enough positive feedback
"""

import importlib
import logging
import os
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)

# Directory for promoted template YAML files
TEMPLATES_DIR = os.path.join(
    os.path.dirname(__file__), "..", "card_framework", "patterns"
)


class TemplateComponent:
    """
    A component that wraps an approved card pattern.

    Implements the same interface as card_framework components:
    - Instantiate with params
    - Call .render() to get Google Chat JSON

    This allows templates to participate in the same flow as real components:
    Qdrant search → ModuleWrapper load → instantiate → render()
    """

    def __init__(
        self,
        template_data: Dict[str, Any],
        module_wrapper: Optional[Any] = None,
        **override_params,
    ):
        """
        Initialize a template component.

        Args:
            template_data: Template definition with:
                - name: Template name
                - components: List of {path, params} dicts
                - defaults: Default parameter values
                - layout: Optional layout hints (columns, sections, etc.)
                - render_cache: Optional pre-rendered JSON
            module_wrapper: ModuleWrapper instance for loading real components
            **override_params: Parameters to override defaults
        """
        self.template_data = template_data
        self.name = template_data.get("name", "unnamed_template")
        self.components = template_data.get("components", [])
        self.defaults = template_data.get("defaults", {})
        self.layout = template_data.get("layout", {})
        self.render_cache = template_data.get("render_cache")
        self._module_wrapper = module_wrapper

        # Merge defaults with overrides
        self.params = {**self.defaults, **override_params}

        logger.debug(f"TemplateComponent initialized: {self.name}")

    def _get_module_wrapper(self):
        """Get ModuleWrapper instance (uses singleton)."""
        if self._module_wrapper is None:
            try:
                from gchat.card_framework_wrapper import get_card_framework_wrapper

                self._module_wrapper = get_card_framework_wrapper()
            except Exception as e:
                logger.warning(f"Could not get ModuleWrapper singleton: {e}")
        return self._module_wrapper

    def _load_component_class(self, path: str) -> Optional[Any]:
        """Load a component class by its full path."""
        wrapper = self._get_module_wrapper()
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

    def _substitute_params(self, value: Any) -> Any:
        """
        Substitute ${param_name} placeholders with actual values.

        Args:
            value: Value that may contain placeholders

        Returns:
            Value with placeholders substituted
        """
        if isinstance(value, str):
            # Handle ${param_name} substitution
            import re

            pattern = r"\$\{(\w+)\}"

            def replace(match):
                param_name = match.group(1)
                return str(self.params.get(param_name, match.group(0)))

            return re.sub(pattern, replace, value)

        elif isinstance(value, dict):
            return {k: self._substitute_params(v) for k, v in value.items()}

        elif isinstance(value, list):
            return [self._substitute_params(item) for item in value]

        return value

    def render(self) -> Dict[str, Any]:
        """
        Render the template to Google Chat JSON.

        This method:
        1. Checks for render_cache (fast path)
        2. Otherwise, instantiates each component and renders it
        3. Assembles into final card structure

        Returns:
            Google Chat card JSON
        """
        # Fast path: use cached render if available and no param overrides
        if self.render_cache and self.params == self.defaults:
            logger.debug(f"Using render_cache for template: {self.name}")
            return self.render_cache

        # Build widgets by instantiating each component
        widgets = []

        for comp_def in self.components:
            path = comp_def.get("path")
            params = comp_def.get("params", {})

            if not path:
                continue

            # Substitute parameters
            params = self._substitute_params(params)

            # Load the component class
            component_class = self._load_component_class(path)
            if not component_class:
                logger.warning(f"Could not load component: {path}")
                continue

            try:
                # Instantiate and render
                instance = component_class(**params)
                rendered = instance.render()
                widgets.append(rendered)
                logger.debug(f"Rendered component: {path}")
            except Exception as e:
                logger.warning(f"Failed to render {path}: {e}")

        # Assemble into card structure based on layout
        card = self._assemble_card(widgets)

        return card

    def _assemble_card(self, widgets: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Assemble widgets into a card structure based on layout hints.

        Args:
            widgets: List of rendered widget dicts

        Returns:
            Complete card JSON
        """
        card = {}

        # Add header if specified
        if self.params.get("title"):
            card["header"] = {
                "title": self.params["title"],
                "subtitle": self.params.get("subtitle", ""),
            }

        # Handle layout
        layout_type = self.layout.get("type", "standard")

        if layout_type == "sections":
            # Multiple sections as defined in layout
            sections = []
            section_defs = self.layout.get("sections", [{"widgets": "all"}])

            for section_def in section_defs:
                section = {}
                if section_def.get("header"):
                    section["header"] = self._substitute_params(section_def["header"])

                # Determine which widgets go in this section
                widget_spec = section_def.get("widgets", "all")
                if widget_spec == "all":
                    section["widgets"] = widgets
                elif isinstance(widget_spec, list):
                    # Indices of widgets for this section
                    section["widgets"] = [
                        widgets[i] for i in widget_spec if i < len(widgets)
                    ]

                sections.append(section)

            card["sections"] = sections

        else:
            # Standard: all widgets in one section
            card["sections"] = [{"widgets": widgets}]

        return card


class TemplateRegistry:
    """
    Registry for loading and managing templates.

    Templates can come from:
    1. YAML files in card_framework/patterns/ (promoted templates)
    2. Qdrant points with type="template" (intermediate templates)
    """

    def __init__(self, templates_dir: str = None):
        self.templates_dir = templates_dir or TEMPLATES_DIR
        self._templates: Dict[str, Dict[str, Any]] = {}
        self._loaded = False

    def _ensure_loaded(self):
        """Load templates from YAML files if not already loaded."""
        if self._loaded:
            return

        self._load_from_files()
        self._loaded = True

    def _load_from_files(self):
        """Load all template YAML files from the templates directory."""
        if not os.path.exists(self.templates_dir):
            logger.debug(f"Templates directory does not exist: {self.templates_dir}")
            return

        for filename in os.listdir(self.templates_dir):
            if filename.endswith((".yaml", ".yml")):
                filepath = os.path.join(self.templates_dir, filename)
                try:
                    with open(filepath, "r") as f:
                        data = yaml.safe_load(f)

                    if isinstance(data, dict):
                        # Single template per file
                        if "name" in data:
                            self._templates[data["name"]] = data
                            logger.info(
                                f"Loaded template: {data['name']} from {filename}"
                            )
                        # Multiple templates per file
                        else:
                            for name, template_data in data.items():
                                template_data["name"] = name
                                self._templates[name] = template_data
                                logger.info(f"Loaded template: {name} from {filename}")

                except Exception as e:
                    logger.warning(f"Failed to load template file {filepath}: {e}")

    def get_template(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Get a template by name.

        Args:
            name: Template name

        Returns:
            Template data dict or None
        """
        self._ensure_loaded()
        return self._templates.get(name)

    def register_template(self, name: str, template_data: Dict[str, Any]):
        """
        Register a template programmatically.

        Args:
            name: Template name
            template_data: Template definition
        """
        template_data["name"] = name
        self._templates[name] = template_data
        logger.info(f"Registered template: {name}")

    def save_template_to_file(self, name: str, template_data: Dict[str, Any]) -> str:
        """
        Save a template to a YAML file (promotion).

        Args:
            name: Template name
            template_data: Template definition

        Returns:
            Path to saved file
        """
        # Ensure templates directory exists
        os.makedirs(self.templates_dir, exist_ok=True)

        # Clean name for filename
        safe_name = "".join(c if c.isalnum() or c in "_-" else "_" for c in name)
        filepath = os.path.join(self.templates_dir, f"{safe_name}.yaml")

        # Add metadata
        template_data["name"] = name

        with open(filepath, "w") as f:
            yaml.dump(template_data, f, default_flow_style=False, sort_keys=False)

        # Register in memory too
        self._templates[name] = template_data

        logger.info(f"Saved template to file: {filepath}")
        return filepath

    def list_templates(self) -> List[str]:
        """List all available template names."""
        self._ensure_loaded()
        return list(self._templates.keys())

    def create_component(
        self, name: str, module_wrapper: Optional[Any] = None, **params
    ) -> Optional[TemplateComponent]:
        """
        Create a TemplateComponent instance from a registered template.

        Args:
            name: Template name
            module_wrapper: Optional ModuleWrapper instance
            **params: Override parameters

        Returns:
            TemplateComponent instance or None
        """
        template_data = self.get_template(name)
        if not template_data:
            logger.warning(f"Template not found: {name}")
            return None

        return TemplateComponent(template_data, module_wrapper, **params)


# Global registry instance
_registry: Optional[TemplateRegistry] = None


def get_template_registry() -> TemplateRegistry:
    """Get the global TemplateRegistry instance."""
    global _registry
    if _registry is None:
        _registry = TemplateRegistry()
    return _registry
