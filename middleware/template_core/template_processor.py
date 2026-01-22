"""
Template processing logic for the Enhanced Template Middleware.

Handles template detection, routing, and processing using both simple
regex-based templates and full Jinja2 template engine capabilities.
"""

import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

from config.enhanced_logging import setup_logger

from ..namespace_converter import convert_to_namespace
from .jinja_environment import JinjaEnvironmentManager
from .resource_handler import ResourceHandler
from .utils import TemplateResolutionError

logger = setup_logger()


class TemplateProcessor:
    """
    Handles template detection, routing, and processing.

    Provides the core template processing functionality including:
    - Template type detection (simple vs Jinja2)
    - Template routing to appropriate processing engine
    - Resource URI preprocessing and variable substitution
    - Context building for template rendering
    - Mixed template support (simple + Jinja2 in same template)
    """

    # Pattern to match simple template expressions like {{user://current/email.email}}
    SIMPLE_TEMPLATE_PATTERN = re.compile(r"\{\{([a-zA-Z][a-zA-Z0-9]*://[^}]+)\}\}")

    # Enhanced pattern to match resource URIs in ALL contexts (expressions, loops, conditionals, etc.)
    RESOURCE_URI_PATTERN = re.compile(
        r"([a-zA-Z][a-zA-Z0-9]*://[a-zA-Z0-9/_-]+)((?:\.\w+)*)"
    )

    # Pattern to detect Jinja2 syntax (control structures, filters, etc.)
    JINJA2_DETECTION_PATTERNS = [
        re.compile(r"\{%\s*\w+"),  # {% if, {% for, etc.
        re.compile(r"\{\{[^}]*\|[^}]*\}\}"),  # {{ var | filter }} - complete pattern
        re.compile(r"\{\{[^}]*\([^}]*\}\}"),  # {{ function() }} - function calls
        re.compile(r"\{#.*?#\}"),  # {# comments #}
        # Also detect resource URIs in Jinja2 contexts
        re.compile(
            r"\{%[^%]*[a-zA-Z][a-zA-Z0-9]*://[^%]*%\}"
        ),  # {% for item in resource://uri %}
        re.compile(
            r"\{\{[^}]*[a-zA-Z][a-zA-Z0-9]*://[^}]*\}\}"
        ),  # {{ resource://uri.property }}
        re.compile(
            r"\{\{[^}]*[a-zA-Z][a-zA-Z0-9]*://[^}]*\.[^}]*\}\}"
        ),  # {{ resource://uri.property }}
    ]

    def __init__(
        self,
        resource_handler: ResourceHandler,
        jinja_env_manager: JinjaEnvironmentManager,
        enable_debug_logging: bool = False,
    ):
        """
        Initialize the template processor.

        Args:
            resource_handler: ResourceHandler for fetching resources
            jinja_env_manager: JinjaEnvironmentManager for Jinja2 processing
            enable_debug_logging: Enable detailed debug logging
        """
        self.resource_handler = resource_handler
        self.jinja_env_manager = jinja_env_manager
        self.enable_debug_logging = enable_debug_logging

    async def resolve_string_templates(
        self, text: str, fastmcp_context, param_path: str
    ) -> Tuple[Any, Optional[str]]:
        """
        Resolve template expressions in a string using the appropriate engine.

        Detection logic:
        1. If contains Jinja2 syntax -> use Jinja2
        2. If contains only simple templates -> use simple resolver
        3. If mixed -> use Jinja2 (it can handle simple syntax too via custom functions)

        Args:
            text: Text containing template expressions
            fastmcp_context: FastMCP context for resource access
            param_path: Path identifier for debugging

        Returns:
            Tuple of (resolved_text, error_message)
            - resolved_text: Resolved text with template expressions substituted
            - error_message: Error message if template resolution failed, None if successful
        """
        if not text or not isinstance(text, str):
            return text, None

        # Detect template type
        has_jinja2 = self._has_jinja2_syntax(text)
        has_simple = bool(self.SIMPLE_TEMPLATE_PATTERN.search(text))

        if self.enable_debug_logging:
            logger.debug(
                f"🔍 Template detection for '{param_path}': "
                f"Jinja2={'✅' if has_jinja2 else '❌'}, "
                f"Simple={'✅' if has_simple else '❌'}"
            )

        if has_jinja2 and self.jinja_env_manager.is_available():
            # Use Jinja2 engine (can handle both simple and complex)
            return await self._resolve_jinja2_template(
                text, fastmcp_context, param_path
            )
        elif has_simple:
            # Use simple resolver (v2 compatibility)
            return await self._resolve_simple_template(
                text, fastmcp_context, param_path
            )
        else:
            # No templates found
            return text, None

    def _has_jinja2_syntax(self, text: str) -> bool:
        """
        Detect if text contains Jinja2 syntax.

        Args:
            text: Text to analyze for Jinja2 patterns

        Returns:
            True if Jinja2 syntax detected, False otherwise
        """
        # First check for standard Jinja2 patterns
        if any(pattern.search(text) for pattern in self.JINJA2_DETECTION_PATTERNS):
            return True

        # Also treat resource URIs with property access as Jinja2
        if self.SIMPLE_TEMPLATE_PATTERN.search(text):
            # Check if any of the simple templates have property access after the URI
            for match in self.SIMPLE_TEMPLATE_PATTERN.finditer(text):
                template_expr = match.group(1)
                # If the expression has a dot after the URI path, it needs Jinja2
                if "://" in template_expr and "." in template_expr:
                    scheme_end = template_expr.index("://")
                    if template_expr.find(".", scheme_end) != -1:
                        return True

        return False

    async def _resolve_jinja2_template(
        self, template_text: str, fastmcp_context, param_path: str
    ) -> Tuple[Any, Optional[str]]:
        """
        Resolve template using Jinja2 engine.

        This provides full Jinja2 functionality including:
        - Control structures (if/for/etc.)
        - Filters and functions
        - Custom resource resolution functions
        - Variable assignments
        - Macros and includes

        Args:
            template_text: Template text to process
            fastmcp_context: FastMCP context for resource access
            param_path: Path identifier for debugging

        Returns:
            Tuple of (rendered_result, error_message)
        """
        jinja_env = self.jinja_env_manager.get_environment()
        if not jinja_env:
            error_msg = "Jinja2 not available - falling back to simple template"
            logger.error(f"❌ {error_msg}")
            return await self._resolve_simple_template(
                template_text, fastmcp_context, param_path
            )

        try:
            if self.enable_debug_logging:
                logger.debug(f"🎭 Resolving Jinja2 template: {param_path}")

            # IMPORTANT: Process resource URIs FIRST before mixed template processing
            processed_template_text, resource_context = (
                await self._preprocess_resource_uris(template_text, fastmcp_context)
            )

            # Then pre-process any remaining v2 syntax to Jinja2-compatible syntax
            processed_template_text = await self._preprocess_mixed_template(
                processed_template_text, fastmcp_context
            )

            # Create template with better error handling
            try:
                template = jinja_env.from_string(processed_template_text)
            except Exception as template_error:
                if self.enable_debug_logging:
                    logger.debug(
                        f"🔧 Template syntax error in processed template: {template_error}"
                    )
                    logger.debug(
                        f"🔧 Processed template: {repr(processed_template_text)}"
                    )
                # Try with original template text if preprocessing failed
                try:
                    template = jinja_env.from_string(template_text)
                except Exception as original_error:
                    if self.enable_debug_logging:
                        logger.debug(
                            f"🔧 Original template also failed: {original_error}"
                        )
                        logger.debug(f"🔧 Original template: {repr(template_text)}")
                    raise original_error

            # Build template context with resource resolution capabilities
            context = await self._build_template_context(fastmcp_context)
            context.update(resource_context)

            # Debug logging to verify context contains our resources
            if self.enable_debug_logging or resource_context:
                logger.info(
                    f"🎭 Rendering template with context keys: {list(context.keys())}"
                )
                if resource_context:
                    logger.info(
                        f"📦 Resource context keys added: {list(resource_context.keys())}"
                    )
                    # Show first few items from each resource for debugging
                    for key, value in list(resource_context.items())[:3]:
                        value_type = type(value).__name__
                        if isinstance(value, dict):
                            value_preview = (
                                f"dict with {len(value)} keys: {list(value.keys())[:3]}"
                            )
                        elif isinstance(value, list):
                            value_preview = f"list with {len(value)} items"
                        else:
                            value_preview = f"{value_type}"
                        logger.info(f"   - {key}: {value_preview}")

            # Render template
            result = template.render(**context)

            if self.enable_debug_logging:
                logger.debug(f"✅ Jinja2 template resolved: {param_path}")

            return result, None

        except Exception as e:
            error_msg = f"Jinja2 template resolution failed for {param_path}: {e}"
            logger.error(f"❌ {error_msg}")
            if self.enable_debug_logging:
                logger.debug("🔄 Falling back to simple template resolution")
            # Fall back to simple template resolution but preserve the Jinja2 error
            fallback_result, fallback_error = await self._resolve_simple_template(
                template_text, fastmcp_context, param_path
            )
            # Return the fallback result but with the original Jinja2 error (since it was detected first)
            return fallback_result, error_msg

    async def _preprocess_mixed_template(
        self, template_text: str, fastmcp_context
    ) -> str:
        """
        Pre-process template to convert v2 {{resource://...}} syntax to resolved values.

        Args:
            template_text: Template text to preprocess
            fastmcp_context: FastMCP context for resource access

        Returns:
            Preprocessed template text with resolved values
        """
        if not template_text:
            return template_text

        # Find and resolve all v2 template expressions first
        matches = list(self.SIMPLE_TEMPLATE_PATTERN.finditer(template_text))

        if not matches:
            return template_text

        if self.enable_debug_logging:
            logger.debug(
                f"🔄 Pre-processing mixed template with {len(matches)} v2 expressions"
            )
            logger.debug(f"🔍 Original template: {repr(template_text)}")

        processed_text = template_text

        # Process in reverse order to maintain positions
        for match in reversed(matches):
            template_expr = match.group(1)

            if self.enable_debug_logging:
                logger.debug(f"🎯 Processing v2 expression: {repr(template_expr)}")

            try:
                # Resolve the v2 expression
                resolved = await self._resolve_simple_template_expression(
                    template_expr, fastmcp_context, "preprocess"
                )

                if self.enable_debug_logging:
                    logger.debug(f"✅ Resolved to: {repr(resolved)}")

                # Convert to string representation
                if isinstance(resolved, str):
                    replacement = f'"{resolved}"'  # Quote strings for Jinja2
                elif isinstance(resolved, bool):
                    replacement = str(resolved).lower()  # true/false
                elif resolved is None:
                    replacement = '""'  # Empty string
                elif isinstance(resolved, (int, float)):
                    replacement = str(resolved)  # Numbers as-is
                else:
                    # Complex objects - convert to JSON string
                    json_str = json.dumps(resolved).replace('"', r"\"")
                    replacement = f'"{json_str}"'

                # Replace the v2 expression with the resolved value
                processed_text = (
                    processed_text[: match.start()]
                    + replacement
                    + processed_text[match.end() :]
                )

            except Exception as e:
                logger.error(f"⚠️ Failed to resolve v2 expression {template_expr}: {e}")
                # Leave the original expression if resolution fails
                continue

        if self.enable_debug_logging:
            logger.debug(f"🔄 Processed template: {repr(processed_text)}")

        return processed_text

    async def _preprocess_resource_uris(
        self, template_text: str, fastmcp_context
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Pre-process resource URIs in Jinja2 templates by resolving them and
        replacing with generated variable names.

        Args:
            template_text: Template text containing resource URIs
            fastmcp_context: FastMCP context for resource access

        Returns:
            Tuple of (processed_template_text, resource_context_dict)
        """
        if not template_text:
            return template_text, {}

        # Find all resource URIs in the template
        matches = list(self.RESOURCE_URI_PATTERN.finditer(template_text))

        if self.enable_debug_logging:
            logger.debug(f"🔍 Checking template: {template_text}")
            logger.debug(f"🔍 Found {len(matches)} resource URI matches")
            for i, match in enumerate(matches):
                uri = match.group(1)
                prop = match.group(2) if match.group(2) else ""
                logger.debug(
                    f"🔍 Match {i}: {repr(uri + prop)} at position {match.start()}-{match.end()}"
                )

        if not matches:
            return template_text, {}

        if self.enable_debug_logging:
            logger.debug(
                f"🔄 Pre-processing {len(matches)} resource URIs in Jinja2 template"
            )

        processed_text = template_text
        resource_context = {}

        # Process in reverse order to maintain positions
        for match in reversed(matches):
            uri = match.group(1)
            property_path = match.group(2) if match.group(2) else None

            try:
                if self.enable_debug_logging:
                    logger.debug(f"🎯 Resolving resource URI: {uri}")
                    if property_path:
                        logger.debug(f"   Property path: {property_path}")

                # Resolve the resource with improved error handling
                try:
                    resolved_data = await self.resource_handler.fetch_resource(
                        uri, fastmcp_context
                    )
                except TemplateResolutionError:
                    # If resource resolution fails, try to extract from existing context
                    state_key = f"resource_cache_{uri}"
                    resolved_data = await fastmcp_context.get_state(state_key)
                    if not resolved_data:
                        # Final fallback - use empty data structure
                        if uri.endswith("/email"):
                            resolved_data = {"email": ""}
                        else:
                            resolved_data = {}
                        if self.enable_debug_logging:
                            logger.debug(f"🔄 Using fallback empty data for {uri}")

                # Generate a meaningful variable name from URI
                # Convert user://current/email → user_current_email
                # Also replace hyphens (from UUIDs) to avoid Jinja2 syntax errors
                var_name = (
                    uri.replace("://", "_")
                    .replace("/", "_")
                    .replace(":", "")
                    .replace(".", "_")
                    .replace("-", "_")
                )  # Critical for UUID support!

                # Convert to SimpleNamespace ONLY for small objects to preserve dot notation
                # Keep large/complex objects (like Qdrant resources) as plain dicts for Jinja2 compatibility
                if isinstance(resolved_data, dict):
                    # Check if this is a large/complex Qdrant resource
                    is_qdrant_resource = (
                        "qdrant://" in uri
                        or resolved_data.get("qdrant_enabled") is not None
                        or resolved_data.get("collection_name") is not None
                        or resolved_data.get("point_id") is not None
                    )

                    if is_qdrant_resource:
                        # Keep as plain dict - Jinja2 handles dicts natively
                        logger.info(
                            f"📦 Adding Qdrant resource to context: {var_name} (keys: {list(resolved_data.keys())[:5]}...)"
                        )
                        resource_context[var_name] = resolved_data
                    else:
                        # Convert to SimpleNamespace for dot notation
                        logger.debug(f"📦 Converting to namespace: {var_name}")
                        resource_context[var_name] = convert_to_namespace(resolved_data)
                else:
                    # Non-dict data - keep as-is
                    logger.debug(
                        f"📦 Adding non-dict data: {var_name} = {type(resolved_data).__name__}"
                    )
                    resource_context[var_name] = resolved_data

                # Also add direct email value if this is an email resource
                if uri.endswith("/email") and hasattr(resolved_data, "email"):
                    resource_context[f"{var_name}_value"] = getattr(
                        resolved_data, "email", ""
                    )
                elif (
                    uri.endswith("/email")
                    and isinstance(resolved_data, dict)
                    and "email" in resolved_data
                ):
                    resource_context[f"{var_name}_value"] = resolved_data["email"]

                # Replace URI with variable name in template
                # IMPORTANT: Need to preserve {{ }} for Jinja2 variable reference
                replacement = var_name
                if property_path:
                    replacement += property_path

                # Check if the match is already wrapped in {{ }}
                match_start = match.start()
                match_end = match.end()

                # Search backwards for {{ (allowing spaces/newlines)
                jinja_start = None
                for i in range(max(0, match_start - 10), match_start):
                    if processed_text[i : i + 2] == "{{":
                        # Found opening braces - check if there's only whitespace between them and our match
                        between = processed_text[i + 2 : match_start]
                        if between.strip() == "":
                            jinja_start = i
                            break

                # Search forwards for }} (allowing spaces/newlines)
                jinja_end = None
                if jinja_start is not None:
                    for i in range(match_end, min(len(processed_text), match_end + 10)):
                        if processed_text[i : i + 2] == "}}":
                            # Found closing braces - check if there's only whitespace between match and them
                            between = processed_text[match_end:i]
                            if between.strip() == "":
                                jinja_end = i + 2
                                break

                if jinja_start is not None and jinja_end is not None:
                    # Already wrapped in {{ }} - replace everything including wrappers
                    processed_text = (
                        processed_text[:jinja_start]
                        + "{{ "
                        + replacement
                        + " }}"
                        + processed_text[jinja_end:]
                    )

                    if self.enable_debug_logging:
                        logger.debug(
                            f"✅ Replaced wrapped URI {uri} with {{ {replacement} }}"
                        )
                else:
                    # Not wrapped - this URI is probably in a string literal or other context
                    # Just replace the URI itself without adding wrappers
                    processed_text = (
                        processed_text[:match_start]
                        + replacement
                        + processed_text[match_end:]
                    )

                    if self.enable_debug_logging:
                        logger.debug(
                            f"⚠️ Replaced unwrapped URI {uri} with {replacement} (no Jinja2 wrappers)"
                        )

                if self.enable_debug_logging:
                    logger.debug(
                        f"✅ Replaced {uri}{property_path or ''} with {replacement}"
                    )
                    logger.debug(
                        f"📦 Added to context: {var_name} = {type(resolved_data)}"
                    )
                    if f"{var_name}_value" in resource_context:
                        logger.debug(
                            f"📧 Also added direct value: {var_name}_value = {resource_context[f'{var_name}_value']}"
                        )

            except Exception as e:
                logger.error(f"⚠️ Failed to resolve resource URI {uri}: {e}")
                # Leave the original URI if resolution fails
                continue

        return processed_text, resource_context

    async def _build_template_context(self, fastmcp_context) -> Dict[str, Any]:
        """
        Build a rich template context for Jinja2.

        Provides:
        - Pre-resolved common resources
        - Helper functions
        - Utility objects
        - Current datetime/user context

        Args:
            fastmcp_context: FastMCP context for resource access

        Returns:
            Dictionary containing template context variables and functions
        """
        context = {
            # Basic context - MUST be functions for Jinja2 compatibility
            "now": lambda: datetime.now(timezone.utc),
            "utcnow": lambda: datetime.now(timezone.utc),
            # Utility functions available in templates
            "len": len,
            "str": str,
            "int": int,
            "float": float,
            "bool": bool,
            "list": list,
            "dict": dict,
            "max": max,
            "min": min,
            "sum": sum,
            "sorted": sorted,
            "reversed": reversed,
            "enumerate": enumerate,
            "zip": zip,
            "range": range,
            # Custom utilities
            "json": json,
            "datetime": datetime,
            "timedelta": timedelta,
        }

        # Pre-resolve common resources synchronously for template context
        await self._populate_common_resources(context, fastmcp_context)

        return context

    async def _populate_common_resources(
        self, context: Dict[str, Any], fastmcp_context
    ):
        """
        Populate template context with commonly used resources.

        Args:
            context: Template context dictionary to populate
            fastmcp_context: FastMCP context for resource access
        """
        # User email - both as data and function
        try:
            user_data = await self.resource_handler.fetch_resource(
                "user://current/email", fastmcp_context
            )
            if user_data:
                context["user"] = user_data
                if isinstance(user_data, dict):
                    user_email_str = user_data.get("email", "")
                else:
                    user_email_str = str(user_data)

                # Don't overwrite - provide both string value and function
                context["user_email_str"] = user_email_str
                context["user_email"] = lambda: user_email_str

            else:
                context["user"] = {}
                context["user_email_str"] = ""
                context["user_email"] = lambda: ""
        except Exception as e:
            if self.enable_debug_logging:
                logger.debug(f"⚠️ Failed to populate user context: {e}")
            context["user"] = {}
            context["user_email_str"] = ""
            context["user_email"] = lambda: ""

        # Gmail labels - both as data and function
        try:
            labels_data = await self.resource_handler.fetch_resource(
                "service://gmail/labels", fastmcp_context
            )
            labels_list = labels_data if labels_data else []
            context["gmail_labels"] = lambda: labels_list
        except Exception:
            context["gmail_labels"] = lambda: []

        # User profile - both as data and function
        try:
            profile_data = await self.resource_handler.fetch_resource(
                "user://current/profile", fastmcp_context
            )
            profile_dict = profile_data if profile_data else {}
            context["user_profile"] = lambda: profile_dict
        except Exception:
            context["user_profile"] = lambda: {}

        # Recent content across all services
        try:
            workspace_data = await self.resource_handler.fetch_resource(
                "recent://all", fastmcp_context
            )
            workspace_list = workspace_data if workspace_data else []
            context["workspace_content"] = lambda: workspace_list
        except Exception:
            context["workspace_content"] = lambda: []

    async def _resolve_simple_template(
        self, text: str, fastmcp_context, param_path: str
    ) -> Tuple[Any, Optional[str]]:
        """
        Resolve template using the simple regex-based engine (v2 compatibility).

        This maintains full backward compatibility with existing templates.

        Args:
            text: Text containing simple template expressions
            fastmcp_context: FastMCP context for resource access
            param_path: Path identifier for debugging

        Returns:
            Tuple of (resolved_text, error_message)
        """
        # Find all template expressions
        matches = list(self.SIMPLE_TEMPLATE_PATTERN.finditer(text))

        if not matches:
            return text, None

        if self.enable_debug_logging:
            logger.debug(f"🔧 Resolving simple template: {param_path}")

        try:
            # Special case: if the entire string is a single template,
            # we might return a non-string value
            if len(matches) == 1 and matches[0].group(0) == text.strip():
                # The entire string is a single template
                template_expr = matches[0].group(1)
                resolved, error = await self._resolve_simple_template_expression(
                    template_expr, fastmcp_context, param_path
                )
                return resolved, error

            # Multiple templates or template is part of a larger string
            result = text
            for match in reversed(matches):  # Process in reverse to maintain positions
                template_expr = match.group(1)
                resolved, error = await self._resolve_simple_template_expression(
                    template_expr, fastmcp_context, param_path
                )

                # If any expression fails, return the error
                if error:
                    return result, error

                # Convert to string for replacement
                if isinstance(resolved, str):
                    replacement = resolved
                elif isinstance(resolved, bool):
                    replacement = str(
                        resolved
                    ).lower()  # Convert True/False to 'true'/'false'
                elif resolved is None:
                    replacement = ""
                else:
                    replacement = json.dumps(resolved)

                # Replace the template expression
                result = result[: match.start()] + replacement + result[match.end() :]

            return result, None

        except Exception as e:
            error_msg = f"Simple template resolution failed for {param_path}: {e}"
            logger.error(f"❌ {error_msg}")
            return text, error_msg

    async def _resolve_simple_template_expression(
        self, expression: str, fastmcp_context, param_path: str
    ) -> Tuple[Any, Optional[str]]:
        """
        Resolve a single simple template expression.

        Args:
            expression: Template expression (without {{ }})
            fastmcp_context: FastMCP context for resource access
            param_path: Path identifier for debugging

        Returns:
            Tuple of (resolved_value, error_message)
        """
        try:
            # Split expression into resource URI and property path
            if "." in expression and "://" in expression:
                scheme_end = expression.index("://")
                first_dot_after_scheme = expression.find(".", scheme_end)

                if first_dot_after_scheme != -1:
                    resource_uri = expression[:first_dot_after_scheme]
                    property_path = expression[first_dot_after_scheme + 1 :]
                else:
                    resource_uri = expression
                    property_path = None
            else:
                resource_uri = expression
                property_path = None

            if self.enable_debug_logging:
                logger.debug(f"📍 Resolving: {resource_uri}")
                if property_path:
                    logger.debug(f"   Property path: {property_path}")

            # Fetch the resource
            resource_data = await self.resource_handler.fetch_resource(
                resource_uri, fastmcp_context
            )

            # Extract property if specified
            if property_path:
                result = self.resource_handler.extract_property(
                    resource_data, property_path
                )
                if self.enable_debug_logging:
                    logger.debug(f"   Extracted value: {repr(result)}")
            else:
                result = resource_data

            return result, None

        except Exception as e:
            error_msg = f"Failed to resolve template expression '{expression}': {e}"
            logger.error(f"❌ {error_msg}")
            return None, error_msg
