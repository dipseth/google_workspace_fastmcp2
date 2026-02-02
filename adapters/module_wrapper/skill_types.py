"""
Skill Document Types for ModuleWrapper SkillsMixin

Defines dataclasses for skill documents and manifests that are generated
by the SkillsMixin and consumed by FastMCP's SkillsDirectoryProvider.

These types are 100% generic - no module-specific code.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Set


@dataclass
class SkillDocument:
    """
    Represents a single skill document.

    A skill document is a markdown file that provides documentation,
    examples, or reference material for a skill.
    """

    name: str  # "gchat-dsl-syntax"
    title: str  # "Google Chat Card DSL Syntax"
    description: str  # Brief description
    content: str  # Main markdown content
    supporting_files: Dict[str, str] = field(
        default_factory=dict
    )  # filename -> content
    tags: Set[str] = field(default_factory=set)  # {"gchat", "cards", "dsl"}
    version: str = "1.0.0"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "name": self.name,
            "title": self.title,
            "description": self.description,
            "content": self.content,
            "supporting_files": self.supporting_files,
            "tags": list(self.tags),
            "version": self.version,
        }


@dataclass
class SkillInfo:
    """
    Metadata for a single skill in the manifest.
    """

    name: str  # "dsl-syntax"
    title: str  # "DSL Syntax Reference"
    description: str  # Brief description
    filename: str  # "dsl-syntax.md"
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "name": self.name,
            "title": self.title,
            "description": self.description,
            "filename": self.filename,
            "tags": self.tags,
        }


@dataclass
class SkillManifest:
    """
    Manifest for a skills directory.

    This is written as _manifest.json in the skill directory and provides
    metadata about all skills in the directory.
    """

    name: str  # "gchat-cards"
    description: str  # "Google Chat Card Building Skills"
    skills: List[SkillInfo] = field(default_factory=list)
    generated_at: datetime = field(default_factory=datetime.utcnow)
    source_module: str = ""  # "card_framework"
    version: str = "1.0.0"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "name": self.name,
            "description": self.description,
            "skills": [s.to_dict() for s in self.skills],
            "generated_at": self.generated_at.isoformat(),
            "source_module": self.source_module,
            "version": self.version,
        }


@dataclass
class SkillGeneratorConfig:
    """
    Configuration for skill document generation.
    """

    # Output configuration
    output_dir: Optional[str] = None  # Directory to write skills
    main_file_name: str = "SKILL.md"  # Main skill file name

    # Content configuration
    include_examples: bool = True
    include_hierarchy: bool = True
    include_components: bool = True
    max_example_count: int = 10

    # Metadata
    skill_name: str = ""  # e.g., "gchat-cards"
    skill_title: str = ""  # e.g., "Google Chat Card Builder"
    version: str = "1.0.0"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "output_dir": self.output_dir,
            "main_file_name": self.main_file_name,
            "include_examples": self.include_examples,
            "include_hierarchy": self.include_hierarchy,
            "include_components": self.include_components,
            "max_example_count": self.max_example_count,
            "skill_name": self.skill_name,
            "skill_title": self.skill_title,
            "version": self.version,
        }


# Export types
__all__ = [
    "SkillDocument",
    "SkillInfo",
    "SkillManifest",
    "SkillGeneratorConfig",
]
