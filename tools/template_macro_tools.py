"""
Template Macro Creation Tool for FastMCP.

This module provides a tool for creating Jinja2 template macros dynamically through the
FastMCP server, leveraging the existing Enhanced Template Middleware architecture.

The macro discovery and listing functionality is handled by the template://macros resources
defined in resources/template_resources.py. This module provides creation and removal.

Key Features:
- Dynamic macro creation with validation
- Integration with existing MacroManager infrastructure
- Optional file persistence for permanent macro storage
- Automatic cache invalidation to update template://macros resources
- Consistent types with template resource system

═══════════════════════════════════════════════════════════════════════════════
                      🔧 THE TOOL THAT FORGES TOOLS 🔧
═══════════════════════════════════════════════════════════════════════════════

    Most tools do a single task,
    answer questions when you ask.
    But this one holds a stranger gift:
    it builds the patterns others lift.

    {% macro new_helper(args) %}
    typed at runtime, not in code—
    the server learns a fresh new mode.
    {% endmacro %} seals the spell,
    and MacroManager knows it well.

    persist_to_file: True or False?
    Ephemeral wisdom, or carved in stone?
    The cache invalidates on cue,
    template://macros shows the new.

    A regex guards the macro name,
    ^[a-zA-Z_] starts the game.
    Fifty thousand characters max,
    room enough for complex stacks.

    The tool that creates is rare indeed,
    meta-programming plants a seed.
    Tomorrow's helpers born today,
    forged by those who pave the way.

                                        — Field Notes, Jan 2026

═══════════════════════════════════════════════════════════════════════════════
"""

from typing import Annotated, Any, Dict, Optional

from fastmcp import Context, FastMCP
from pydantic import BaseModel, Field

from config.enhanced_logging import setup_logger
from resources.template_resources import MacroInfo
from tools.common_types import UserGoogleEmail

logger = setup_logger()


class MacroCreationResponse(BaseModel):
    """Response for macro creation operations."""

    success: bool = Field(description="Whether the macro was created successfully")
    macro: Optional[MacroInfo] = Field(
        description="Created macro information if successful", default=None
    )
    errors: list[str] = Field(
        description="List of error messages if creation failed", default_factory=list
    )
    usage_info: Optional[Dict[str, Any]] = Field(
        description="Usage information for the created macro", default=None
    )


def get_template_middleware_from_registry():
    """
    Get the EnhancedTemplateMiddleware instance from the module-level registry.

    This uses the registry pattern instead of context state to avoid serialization
    issues with non-serializable middleware instances.

    Returns:
        EnhancedTemplateMiddleware instance or None if not found
    """
    try:
        from middleware.template_middleware import get_template_middleware_instance

        return get_template_middleware_instance()
    except Exception as e:
        logger.error(f"❌ Failed to get template middleware from registry: {e}")
        return None


async def create_template_macro(
    ctx: Context,
    macro_name: Annotated[
        str,
        Field(
            description="Name of the macro to create (must be a valid Python identifier)",
            pattern=r"^[a-zA-Z_][a-zA-Z0-9_]*$",
            min_length=1,
            max_length=100,
        ),
    ],
    macro_content: Annotated[
        str,
        Field(
            description="Complete Jinja2 macro definition including {% macro %} and {% endmacro %} tags",
            min_length=10,
            max_length=50000,
        ),
    ],
    description: Annotated[
        str,
        Field(
            description="Optional description of the macro's purpose and functionality",
            max_length=1000,
        ),
    ] = "",
    usage_example: Annotated[
        str,
        Field(
            description="Optional usage example showing how to call the macro",
            max_length=500,
        ),
    ] = "",
    persist_to_file: Annotated[
        bool,
        Field(
            description="Whether to save the macro to a .j2 file for permanent availability"
        ),
    ] = False,
) -> MacroCreationResponse:
    """
    Create and register a new Jinja2 template macro dynamically.

    This tool allows LLMs to create custom template macros that are immediately available
    for use in any tool parameter that supports Jinja2 templating. The macro is registered
    in the existing template system and can optionally be persisted to disk.

    Args:
        ctx: FastMCP Context for accessing middleware
        macro_name: Name of the macro (must be valid Python identifier)
        macro_content: Complete Jinja2 macro definition with {% macro %} and {% endmacro %}
        description: Optional description of macro purpose
        usage_example: Optional example showing how to use the macro
        persist_to_file: Whether to save macro to templates/dynamic/ directory

    Returns:
        MacroCreationResponse with creation status, macro info, and any errors

    Example:
        create_template_macro(
            macro_name="render_task_list",
            macro_content='''
            {% macro render_task_list(tasks, title="My Tasks") %}
            <div class="task-dashboard">
                <h2>{{ title }} ({{ tasks|length }})</h2>
                {% for task in tasks %}
                <div class="task-item">
                    <strong>{{ task.name }}</strong>
                    {% if task.status %}- {{ task.status }}{% endif %}
                </div>
                {% endfor %}
            </div>
            {% endmacro %}
            ''',
            description="Creates a visual dashboard for task lists",
            usage_example="{{ render_task_list(service://asana/tasks, 'Today Tasks') }}",
            persist_to_file=True
        )
    """
    try:
        await ctx.info(f"Creating template macro '{macro_name}'...")

        # Get the template middleware from registry
        template_middleware = get_template_middleware_from_registry()
        if not template_middleware:
            error_msg = "Template middleware not available - cannot create macros"
            await ctx.error(error_msg)
            return {"success": False, "macro_name": macro_name, "errors": [error_msg]}

        # Access the macro manager
        macro_manager = template_middleware.macro_manager

        await ctx.info(f"Validating macro syntax for '{macro_name}'...")

        # Create the macro using the extended MacroManager
        result = macro_manager.add_dynamic_macro(
            macro_name=macro_name,
            macro_content=macro_content,
            description=description,
            usage_example=usage_example,
            persist_to_file=persist_to_file,
        )

        if result["success"]:
            success_msg = f"✅ Macro '{macro_name}' created successfully!"
            await ctx.info(success_msg)

            if persist_to_file:
                await ctx.info(
                    f"💾 Macro persisted to templates/dynamic/{macro_name}.j2"
                )

            await ctx.info(
                f"🔍 Macro immediately available via: template://macros/{macro_name}"
            )

            # Add usage information to result
            result["usage_info"] = {
                "immediate_availability": f"template://macros/{macro_name}",
                "template_usage": result.get("macro_info", {}).get(
                    "usage_example", f"{{{{ {macro_name}() }}}}"
                ),
                "persisted": persist_to_file,
            }

            logger.info(
                f"🎉 Successfully created macro '{macro_name}' via FastMCP tool"
            )

        else:
            error_msg = f"❌ Failed to create macro '{macro_name}': {'; '.join(result.get('errors', []))}"
            await ctx.warning(error_msg)
            logger.warning(f"⚠️ Macro creation failed: {macro_name}")

        return result

    except Exception as e:
        error_msg = f"Unexpected error creating macro '{macro_name}': {str(e)}"
        await ctx.error(error_msg)
        logger.error(f"❌ Template macro creation error: {e}", exc_info=True)

        return {"success": False, "macro_name": macro_name, "errors": [error_msg]}


class MacroRemovalResponse(BaseModel):
    """Response for macro removal operations."""

    success: bool = Field(description="Whether the macro was removed successfully")
    macro_name: str = Field(description="Name of the macro targeted for removal")
    errors: list[str] = Field(
        description="List of error messages if removal failed", default_factory=list
    )


async def remove_template_macro(
    ctx: Context,
    macro_name: Annotated[
        str,
        Field(
            description="Name of the dynamic macro to remove",
            pattern=r"^[a-zA-Z_][a-zA-Z0-9_]*$",
            min_length=1,
            max_length=100,
        ),
    ],
) -> MacroRemovalResponse:
    """
    Remove a dynamically created Jinja2 template macro.

    Unregisters the macro from the Jinja2 environment and the macro registry,
    and deletes its persisted templates/dynamic/<name>.j2 file if one exists.
    Only macros created via create_template_macro can be removed — file-based
    macros shipped with the server are protected.

    Args:
        ctx: FastMCP Context for accessing middleware
        macro_name: Name of the dynamic macro to remove

    Returns:
        MacroRemovalResponse with removal status and any errors
    """
    try:
        await ctx.info(f"Removing template macro '{macro_name}'...")

        template_middleware = get_template_middleware_from_registry()
        if not template_middleware:
            error_msg = "Template middleware not available - cannot remove macros"
            await ctx.error(error_msg)
            return MacroRemovalResponse(
                success=False, macro_name=macro_name, errors=[error_msg]
            )

        removed = template_middleware.macro_manager.remove_dynamic_macro(macro_name)
        if removed:
            await ctx.info(f"🗑️ Macro '{macro_name}' removed")
            return MacroRemovalResponse(success=True, macro_name=macro_name)

        error_msg = (
            f"Macro '{macro_name}' was not removed: it does not exist or is a "
            "file-based macro (only dynamic macros created via "
            "create_template_macro can be removed)"
        )
        await ctx.warning(error_msg)
        return MacroRemovalResponse(
            success=False, macro_name=macro_name, errors=[error_msg]
        )

    except Exception as e:
        error_msg = f"Unexpected error removing macro '{macro_name}': {str(e)}"
        await ctx.error(error_msg)
        logger.error(f"❌ Template macro removal error: {e}", exc_info=True)
        return MacroRemovalResponse(
            success=False, macro_name=macro_name, errors=[error_msg]
        )


def setup_template_macro_tools(mcp: FastMCP) -> None:
    """
    Register template macro management tools with the FastMCP server.

    This function registers the template macro tools:
    1. create_template_macro: Create new Jinja2 macros dynamically
    2. remove_template_macro: Remove dynamically created macros

    Macro listing is intentionally resource-based rather than a tool — see
    template://macros and template://macros/{name} in resources/template_resources.py.

    Args:
        mcp: FastMCP server instance to register tools with
    """

    @mcp.tool(
        name="create_template_macro",
        description="Create and register a new Jinja2 template macro dynamically",
        tags={"template", "macro", "jinja2", "creation", "dynamic"},
        annotations={
            "title": "Create Template Macro",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    )
    async def create_template_macro_tool(
        ctx: Context,
        macro_name: Annotated[
            str,
            Field(
                description="Name of the macro to create (must be a valid Python identifier)",
                pattern=r"^[a-zA-Z_][a-zA-Z0-9_]*$",
                min_length=1,
                max_length=100,
                examples=[
                    "render_task_list",
                    "format_user_info",
                    "create_status_badge",
                ],
            ),
        ],
        macro_content: Annotated[
            str,
            Field(
                description="Complete Jinja2 macro definition including {% macro %} and {% endmacro %} tags",
                min_length=10,
                max_length=50000,
                examples=[
                    "{% macro greeting(name) %}Hello {{ name }}!{% endmacro %}",
                    "{% macro task_card(task) %}<div class='task'>{{ task.name }}</div>{% endmacro %}",
                ],
            ),
        ],
        description: Annotated[
            str,
            Field(
                description="Optional description of the macro's purpose and functionality",
                max_length=1000,
                examples=[
                    "Creates a greeting message",
                    "Renders a task card with styling",
                ],
            ),
        ] = "",
        usage_example: Annotated[
            str,
            Field(
                description="Optional usage example showing how to call the macro in templates",
                max_length=500,
                examples=[
                    "{{ greeting('John') }}",
                    "{{ task_card(service://asana/tasks/123) }}",
                ],
            ),
        ] = "",
        persist_to_file: Annotated[
            bool,
            Field(
                description="Whether to save the macro to a .j2 file for permanent availability across server restarts"
            ),
        ] = False,
        user_google_email: UserGoogleEmail = None,
    ) -> MacroCreationResponse:
        """
        Create and register a new Jinja2 template macro dynamically.

        This tool allows you to create custom template macros that become immediately
        available for use in any tool parameter that supports Jinja2 templating.
        Created macros are discoverable via template://macros resources.

        Args:
            ctx: FastMCP Context (automatically injected)
            macro_name: Name of the macro (must be valid Python identifier)
            macro_content: Complete Jinja2 macro definition with {% macro %} and {% endmacro %}
            description: Optional description of macro purpose
            usage_example: Optional example showing how to use the macro
            persist_to_file: Whether to save macro to templates/dynamic/ directory
            user_google_email: The user's Google email address (auto-injected by middleware)

        Returns:
            MacroCreationResponse with creation status, macro info, and any errors
        """
        return await create_template_macro(
            ctx, macro_name, macro_content, description, usage_example, persist_to_file
        )

    @mcp.tool(
        name="remove_template_macro",
        description=(
            "Remove a dynamically created Jinja2 template macro (unregisters it and "
            "deletes its persisted templates/dynamic file). Only macros created via "
            "create_template_macro can be removed; file-based macros are protected"
        ),
        tags={"template", "macro", "jinja2", "removal", "dynamic"},
        annotations={
            "title": "Remove Template Macro",
            "readOnlyHint": False,
            "destructiveHint": True,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def remove_template_macro_tool(
        ctx: Context,
        macro_name: Annotated[
            str,
            Field(
                description="Name of the dynamic macro to remove",
                pattern=r"^[a-zA-Z_][a-zA-Z0-9_]*$",
                min_length=1,
                max_length=100,
                examples=["team_update", "render_task_list"],
            ),
        ],
        user_google_email: UserGoogleEmail = None,
    ) -> MacroRemovalResponse:
        """
        Remove a dynamically created Jinja2 template macro.

        Unregisters the macro and deletes its persisted file if one exists.
        Only dynamic macros (created via create_template_macro) can be removed.

        Args:
            ctx: FastMCP Context (automatically injected)
            macro_name: Name of the dynamic macro to remove
            user_google_email: The user's Google email address (auto-injected by middleware)

        Returns:
            MacroRemovalResponse with removal status and any errors
        """
        return await remove_template_macro(ctx, macro_name)

    logger.info(
        "✅ Template macro tools registered: create_template_macro, remove_template_macro"
    )
