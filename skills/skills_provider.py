"""
Skills Provider Setup for FastMCP

Provides setup function to register skill documents generated from ModuleWrapper
instances with a FastMCP skill catalog provider.

Usage:
    from skills.skills_provider import setup_skills_provider

    # In server.py, after wrapper initialization
    if settings.enable_skills_provider:
        setup_skills_provider(
            mcp=mcp,
            wrappers=[card_framework_wrapper],
            enabled_modules=["card_framework"],
        )

::

    One source of truth, two places served:
    the server writes them fresh at start,
    the plugin ships the same, preserved —
    scripts/generate keeps them not apart.
    So touch a model, touch a name,
    then run the script before you fly;
    the CI check will call your shame
    if generated skills run dry.
"""

from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional

import anyio
from fastmcp.skills import Skill
from fastmcp.skills.provider import SkillCatalogProvider

from config.enhanced_logging import setup_logger

if TYPE_CHECKING:
    from fastmcp import FastMCP

    from adapters.module_wrapper import ModuleWrapper

logger = setup_logger()

# Module name to skill directory name mapping
SKILL_NAMES = {
    "card_framework": "gchat-cards",
    "gmail.mjml_types": "mjml-email",
    "qdrant_client.models": "qdrant-search",
    "google_drive": "drive-files",
    "google_gmail": "gmail-automation",
}

# Module name to skill title mapping
SKILL_TITLES = {
    "card_framework": "Google Chat Card Builder",
    "gmail.mjml_types": "MJML Email Composer",
    "qdrant_client.models": "Qdrant Vector Search",
    "google_drive": "Google Drive File Operations",
    "google_gmail": "Gmail Automation",
}

# Module name to SKILL.md frontmatter description (required by Claude Code
# for skill discovery)
SKILL_DESCRIPTIONS = {
    "card_framework": (
        "Google Chat Card Builder — DSL symbols, component reference, "
        "containment rules, and Jinja filters for composing Chat cards with "
        "the Google Workspace MCP server"
    ),
    "gmail.mjml_types": (
        "MJML Email Composer — email block symbols, DSL syntax, and "
        "per-component docs for composing rich HTML emails with the Google "
        "Workspace MCP server"
    ),
    "qdrant_client.models": (
        "Qdrant Vector Search — semantic search, filter DSL, recommendation, "
        "and query DSL over past Google Workspace MCP tool responses"
    ),
}


def _get_skill_name(module_name: str) -> str:
    """
    Convert module name to skill directory name.

    Args:
        module_name: Module name (e.g., "card_framework")

    Returns:
        Skill directory name (e.g., "gchat-cards")
    """
    return SKILL_NAMES.get(module_name, module_name.replace("_", "-"))


def _get_skill_description(module_name: str) -> str:
    """Get the SKILL.md frontmatter description for a module."""
    return SKILL_DESCRIPTIONS.get(module_name, "")


def _get_skill_title(module_name: str) -> str:
    """
    Get the skill title for a module.

    Args:
        module_name: Module name

    Returns:
        Human-readable skill title
    """
    return SKILL_TITLES.get(module_name, module_name.replace("_", " ").title())


def _read_skills(skill_dirs: List[Path]) -> Dict[str, Skill]:
    return {d.name: Skill.from_directory(d) for d in skill_dirs}


class GeneratedSkillsProvider(SkillCatalogProvider):
    """Serve the skill folders this server generated, and nothing beside them.

    The skills root defaults to ~/.claude/skills, which also holds the user's
    own skills; a directory scan would publish those too. This provider reads
    only the folders it is given.

    With reload=True the folders are re-read on each request, so a skill
    regenerated at runtime is served without a restart. A folder that fails to
    read mid-rewrite leaves the last good set in place.
    """

    def __init__(self, skill_dirs: List[Path], *, reload: bool = False) -> None:
        self._skill_dirs = list(skill_dirs)
        self._reload = reload
        self._last_good = _read_skills(self._skill_dirs)
        super().__init__(self._last_good)

    async def load_skills(self) -> Dict[str, Skill]:
        if self._reload:
            try:
                self._last_good = await anyio.to_thread.run_sync(
                    _read_skills, self._skill_dirs
                )
            except (OSError, ValueError) as exc:
                logger.error(f"Keeping the last valid skills; {exc}")
        return self._last_good


def setup_skills_provider(
    mcp: "FastMCP",
    wrappers: List["ModuleWrapper"],
    enabled_modules: Optional[List[str]] = None,
    skills_root: Optional[Path] = None,
    auto_regenerate: bool = True,
) -> Optional[Path]:
    """
    Register skills provider with dynamic skill generation.

    This function:
    1. Generates skill documents from each enabled ModuleWrapper
    2. Writes them to the skills directory
    3. Registers a provider that serves exactly those skills

    Args:
        mcp: FastMCP server instance
        wrappers: List of ModuleWrapper instances to generate skills for
        enabled_modules: Module names to enable (None = all). Default: ["card_framework"]
        skills_root: Base directory for skills (default: ~/.claude/skills)
        auto_regenerate: If True, regenerate skills on each startup, and
            re-read them from disk on each request

    Returns:
        Path to skills root directory, or None if no skills were generated

    Example:
        from skills.skills_provider import setup_skills_provider
        from gchat.card_framework_wrapper import get_card_framework_wrapper

        wrapper = get_card_framework_wrapper()
        setup_skills_provider(
            mcp=mcp,
            wrappers=[wrapper],
            enabled_modules=["card_framework"],
        )
    """
    from adapters.module_wrapper.skill_types import (
        SkillGeneratorConfig,
    )

    skills_root = skills_root or Path.home() / ".claude" / "skills"
    skills_root = Path(skills_root).expanduser().resolve()
    skills_root.mkdir(parents=True, exist_ok=True)

    enabled = enabled_modules or ["card_framework"]  # Currently only gchat
    skill_dirs: List[Path] = []

    for wrapper in wrappers:
        module_name = getattr(wrapper, "module_name", "")

        if module_name not in enabled:
            logger.debug(f"Skipping disabled module: {module_name}")
            continue

        # Generate skill directory name
        skill_name = _get_skill_name(module_name)
        skill_title = _get_skill_title(module_name)
        skill_dir = skills_root / skill_name

        # Check if we need to regenerate
        if skill_dir.exists() and not auto_regenerate:
            logger.info(f"Skills directory exists, skipping: {skill_dir}")
            skill_dirs.append(skill_dir)
            continue

        # Generate skills using wrapper's SkillsMixin
        try:
            config = SkillGeneratorConfig(
                output_dir=str(skill_dir),
                skill_name=skill_name,
                skill_title=skill_title,
                skill_description=_get_skill_description(module_name),
                include_examples=True,
                include_hierarchy=True,
                include_components=True,
            )

            wrapper.export_skills_to_directory(skill_dir, config)
            skill_dirs.append(skill_dir)

            logger.info(f"Generated skills for {module_name} -> {skill_dir}")

        except Exception:
            logger.exception(f"Failed to generate skills for {module_name}")
            continue

    # Generate cross-module server skill (combines card + email symbol maps)
    try:
        from skills.server_skill_generator import write_server_skill

        card_w = next(
            (w for w in wrappers if "card_framework" in getattr(w, "module_name", "")),
            None,
        )
        email_w = next(
            (w for w in wrappers if "mjml" in getattr(w, "module_name", "")),
            None,
        )
        if card_w and email_w:
            skill_dirs.append(write_server_skill(skills_root, card_w, email_w))
    except Exception:
        logger.exception("Failed to generate server skill")

    if not skill_dirs:
        logger.warning("No skills were generated")
        return None

    try:
        provider = GeneratedSkillsProvider(skill_dirs, reload=auto_regenerate)
        mcp.add_provider(provider)
        logger.info(
            f"Skills provider registered: {skills_root} "
            f"({', '.join(d.name for d in skill_dirs)})"
        )
    except Exception:
        logger.exception("Failed to register skills provider")
        return None

    return skills_root


def regenerate_skills(
    wrapper: "ModuleWrapper",
    skills_root: Optional[Path] = None,
) -> Optional[Path]:
    """
    Regenerate skills for a single wrapper.

    This can be called at runtime to update skills after changes.

    Args:
        wrapper: ModuleWrapper instance
        skills_root: Base directory for skills

    Returns:
        Path to the skill directory, or None on failure
    """
    from adapters.module_wrapper.skill_types import (
        SkillGeneratorConfig,
    )

    skills_root = skills_root or Path.home() / ".claude" / "skills"
    skills_root = Path(skills_root).expanduser().resolve()

    module_name = getattr(wrapper, "module_name", "")
    skill_name = _get_skill_name(module_name)
    skill_title = _get_skill_title(module_name)
    skill_dir = skills_root / skill_name

    try:
        # Invalidate cache before regenerating
        wrapper.invalidate_skills_cache()

        config = SkillGeneratorConfig(
            output_dir=str(skill_dir),
            skill_name=skill_name,
            skill_title=skill_title,
            skill_description=_get_skill_description(module_name),
            include_examples=True,
            include_hierarchy=True,
            include_components=True,
        )

        wrapper.export_skills_to_directory(skill_dir, config)
        logger.info(f"Regenerated skills for {module_name} -> {skill_dir}")

        return skill_dir

    except Exception as e:
        logger.error(f"Failed to regenerate skills for {module_name}: {e}")
        return None
