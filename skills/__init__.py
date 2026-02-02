"""
Skills Provider Package

Provides FastMCP skill document generation and provider setup for ModuleWrapper.

This package enables dynamic skill generation from wrapped Python modules,
exposing skill documents via FastMCP's SkillsDirectoryProvider.

Usage:
    from skills import setup_skills_provider
    from gchat.card_framework_wrapper import get_card_framework_wrapper

    # In server.py
    setup_skills_provider(
        mcp=mcp,
        wrappers=[get_card_framework_wrapper()],
        enabled_modules=["card_framework"],
    )
"""

from skills.skills_provider import setup_skills_provider

__all__ = [
    "setup_skills_provider",
]
