"""Component introspection utilities: get_component_info, list_components, etc."""

import importlib
import inspect
from typing import Any, Dict, List, Optional

from config.enhanced_logging import setup_logger

logger = setup_logger()


def get_component_by_path(self, path: str) -> Optional[Any]:
    """
    Get a component by its path.

    Args:
        path: Path to the component (e.g., "module.submodule.Class")

    Returns:
        The component if found, None otherwise
    """
    # Check for template paths
    if ".templates." in path or ".patterns." in path:
        return self._get_template_component(path)

    # Check if path is in components
    component = self.components.get(path)
    if component and component.obj is not None:
        return component.obj

    # Try to resolve path
    try:
        parts = path.split(".")

        # Normalize paths
        if parts and parts[0] == self.module_name:
            parts = parts[1:]

        if (
            self._module_name
            and parts
            and self._module_name.startswith(self.module_name + ".")
        ):
            subparts = self._module_name.split(".")[1:]
            if parts[: len(subparts)] == subparts:
                parts = parts[len(subparts) :]

        # Start with the module
        obj = self.module

        # Traverse the path
        for part in parts:
            try:
                obj = getattr(obj, part)
            except AttributeError:
                module_candidate = f"{getattr(obj, '__name__', '')}.{part}".lstrip(
                    "."
                )
                try:
                    obj = importlib.import_module(module_candidate)
                except (ImportError, ModuleNotFoundError):
                    return None

        return obj

    except Exception as e:
        logger.warning(f"Could not resolve path {path}: {e}")
        return None


def _get_template_component(self, path: str) -> Optional[Any]:
    """
    Get a template or pattern component by path.

    Args:
        path: Template path like "card_framework.templates.my_template"

    Returns:
        The template component if found
    """
    # Extract template name from path
    parts = path.split(".")
    template_name = parts[-1] if parts else None

    if not template_name:
        return None

    # Try to find in local templates
    try:
        if hasattr(self.module, "templates"):
            templates = getattr(self.module, "templates")
            if hasattr(templates, template_name):
                return getattr(templates, template_name)

        if hasattr(self.module, "patterns"):
            patterns = getattr(self.module, "patterns")
            if hasattr(patterns, template_name):
                return getattr(patterns, template_name)
    except Exception as e:
        logger.debug(f"Error getting template component: {e}")

    return None


def get_component_info(self, path: str) -> Optional[Dict[str, Any]]:
    """
    Get information about a component.

    Args:
        path: Path to the component

    Returns:
        Component information dict or None
    """
    component = self.components.get(path)
    if component:
        return component.to_dict()
    return None


def list_components(self, component_type: Optional[str] = None) -> List[str]:
    """
    List all components, optionally filtered by type.

    Args:
        component_type: Filter by type ('class', 'function', etc.)

    Returns:
        List of component paths
    """
    if component_type:
        return [
            path
            for path, comp in self.components.items()
            if comp.component_type == component_type
        ]
    return list(self.components.keys())


def get_component_source(self, path: str) -> Optional[str]:
    """
    Get the source code of a component.

    Args:
        path: Path to the component

    Returns:
        Source code or None
    """
    component = self.components.get(path)
    if component:
        return component.source
    return None


def create_card_component(self, card_class, params):
    """
    Helper method to create a card component with proper error handling.

    Args:
        card_class: The card class to instantiate
        params: Parameters to pass to the constructor

    Returns:
        The created card component or None if creation failed
    """
    if card_class is None:
        logger.warning("Cannot create card: card_class is None")
        return None

    try:
        if not callable(card_class):
            logger.warning(f"Card class {card_class} is not callable")
            return None

        try:
            if inspect.isclass(card_class):
                sig = inspect.signature(card_class.__init__)
            else:
                sig = inspect.signature(card_class)

            valid_params = {}
            for param_name, param in sig.parameters.items():
                if param_name in params and param_name != "self":
                    valid_params[param_name] = params[param_name]

            component = card_class(**valid_params)
            logger.info(
                f"Successfully created card component: {type(component).__name__}"
            )
            return component

        except (ValueError, TypeError) as e:
            logger.warning(f"Error getting signature for {card_class}: {e}")
            try:
                component = card_class(**params)
                logger.info(
                    f"Created card component with direct instantiation: {type(component).__name__}"
                )
                return component
            except Exception as e2:
                logger.warning(f"Direct instantiation failed: {e2}")
                return None

    except Exception as e:
        logger.warning(f"Failed to create card component: {e}")
        return None


def get_component_fields(self, path: str) -> Optional[Dict[str, Any]]:
    """
    Get the fields/parameters of a component.

    Args:
        path: Path to the component

    Returns:
        Dict of field names to their info, or None
    """
    component = self.components.get(path)
    if component:
        return component.fields if hasattr(component, "fields") else None
    return None


def get_component_children(self, path: str) -> List[str]:
    """
    Get the children of a component in the hierarchy.

    Args:
        path: Path to the component

    Returns:
        List of child component paths
    """
    name = path.rsplit(".", 1)[-1] if "." in path else path
    if hasattr(self, "relationships") and name in self.relationships:
        return self.relationships[name]
    return []


def get_component_hierarchy(self) -> Dict[str, List[str]]:
    """
    Get the full component hierarchy.

    Returns:
        Dict mapping component names to their children
    """
    if hasattr(self, "relationships"):
        return dict(self.relationships)
    return {}
