"""
Skills Provider Setup for FastMCP

Provides setup function to register skill documents generated from ModuleWrapper
instances with FastMCP's SkillsDirectoryProvider.

Usage:
    from skills.skills_provider import setup_skills_provider

    # In server.py, after wrapper initialization
    if settings.enable_skills_provider:
        setup_skills_provider(
            mcp=mcp,
            wrappers=[card_framework_wrapper],
            enabled_modules=["card_framework"],
        )
"""

import logging
from pathlib import Path
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    from fastmcp import FastMCP

    from adapters.module_wrapper import ModuleWrapper

logger = logging.getLogger(__name__)

# Module name to skill directory name mapping
SKILL_NAMES = {
    "card_framework": "gchat-cards",
    "google_drive": "drive-files",
    "google_gmail": "gmail-automation",
}

# Module name to skill title mapping
SKILL_TITLES = {
    "card_framework": "Google Chat Card Builder",
    "google_drive": "Google Drive File Operations",
    "google_gmail": "Gmail Automation",
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


def _get_skill_title(module_name: str) -> str:
    """
    Get the skill title for a module.

    Args:
        module_name: Module name

    Returns:
        Human-readable skill title
    """
    return SKILL_TITLES.get(module_name, module_name.replace("_", " ").title())


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
    3. Registers a SkillsDirectoryProvider with FastMCP

    Args:
        mcp: FastMCP server instance
        wrappers: List of ModuleWrapper instances to generate skills for
        enabled_modules: Module names to enable (None = all). Default: ["card_framework"]
        skills_root: Base directory for skills (default: ~/.claude/skills)
        auto_regenerate: If True, regenerate skills on each startup

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
    try:
        from fastmcp.server.providers.skills import SkillsDirectoryProvider
    except ImportError:
        logger.warning(
            "FastMCP skills provider not available. "
            "Upgrade to FastMCP 3.0.0+ to enable skills."
        )
        return None

    from adapters.module_wrapper.skill_types import SkillGeneratorConfig

    skills_root = skills_root or Path.home() / ".claude" / "skills"
    skills_root = Path(skills_root).expanduser().resolve()
    skills_root.mkdir(parents=True, exist_ok=True)

    enabled = enabled_modules or ["card_framework"]  # Currently only gchat
    skills_generated = False

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
            skills_generated = True
            continue

        # Generate skills using wrapper's SkillsMixin
        try:
            config = SkillGeneratorConfig(
                output_dir=str(skill_dir),
                skill_name=skill_name,
                skill_title=skill_title,
                include_examples=True,
                include_hierarchy=True,
                include_components=True,
            )

            wrapper.export_skills_to_directory(skill_dir, config)
            skills_generated = True

            logger.info(f"Generated skills for {module_name} -> {skill_dir}")

        except Exception as e:
            logger.error(f"Failed to generate skills for {module_name}: {e}")
            continue

    if not skills_generated:
        logger.warning("No skills were generated")
        return None

    # Add single provider for all generated skills
    try:
        provider = SkillsDirectoryProvider(
            roots=skills_root,
            reload=auto_regenerate,  # Re-scan on each request if regenerating
        )
        mcp.add_provider(provider)
        logger.info(f"Skills provider registered: {skills_root}")
    except Exception as e:
        logger.error(f"Failed to register skills provider: {e}")
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
    from adapters.module_wrapper.skill_types import SkillGeneratorConfig

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
