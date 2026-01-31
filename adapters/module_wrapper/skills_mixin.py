"""
Generic SkillsMixin for Dynamic Skill Document Generation

Provides skill document generation by introspecting the wrapped module's:
- Components (via self.components from ModuleWrapperBase)
- Symbols (via self.symbol_mapping from SymbolsMixin)
- Relationships (via self.relationships from RelationshipsMixin)
- Graph structure (via self._relationship_graph from GraphMixin)

IMPORTANT: This mixin must remain 100% generic. NO references to card_framework,
gchat, or any specific module. Module-specific content is added via
register_skill_template() which allows wrapper implementations to inject
custom templates and examples.

Usage:
    # Generic skill generation (from ModuleWrapper methods)
    wrapper = ModuleWrapper("some_module")
    wrapper.register_skill_template("custom-guide", my_template_fn)
    wrapper.export_skills_to_directory("~/.claude/skills/my-module")

    # Module-specific registration (in wrapper file like card_framework_wrapper.py)
    def _register_gchat_skill_templates(wrapper):
        wrapper.register_skill_template("dsl-syntax", _gchat_dsl_template)
        wrapper.register_skill_examples("dsl-syntax", ["example1", "example2"])
"""

import json
import logging
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

from adapters.module_wrapper.skill_types import (
    SkillDocument,
    SkillGeneratorConfig,
    SkillInfo,
    SkillManifest,
)

logger = logging.getLogger(__name__)


class SkillsMixin:
    """
    Generic mixin for dynamic skill document generation from any wrapped module.

    This mixin generates skill documentation by introspecting the wrapped module's:
    - Components (via self.components from ModuleWrapperBase)
    - Symbols (via self.symbol_mapping from SymbolsMixin)
    - Relationships (via self.relationships from RelationshipsMixin)
    - Graph structure (via self._relationship_graph from GraphMixin)

    Module-specific content is added via register_skill_template() which allows
    wrapper implementations (e.g., card_framework_wrapper.py) to inject custom
    templates and examples.
    """

    def __init__(self, *args, **kwargs):
        """Initialize skills-related attributes."""
        super().__init__(*args, **kwargs)
        self._skills_cache: Dict[str, SkillDocument] = {}
        self._skills_directory: Optional[Path] = None
        self._skill_templates: Dict[str, Callable] = {}  # Pluggable templates
        self._skill_examples: Dict[str, List[str]] = {}  # Example content per skill type
        self._skill_metadata: Dict[str, Dict[str, Any]] = {}  # Additional metadata

    # =========================================================================
    # TEMPLATE REGISTRATION (Extensibility Hooks)
    # =========================================================================

    def register_skill_template(
        self,
        name: str,
        template_fn: Callable[["SkillsMixin"], str],
    ) -> None:
        """
        Register a custom skill template generator.

        This allows module-specific wrappers to inject custom skill content.

        Args:
            name: Template name (e.g., "dsl-syntax", "jinja-filters")
            template_fn: Function that takes the wrapper and returns markdown content

        Example:
            def _my_custom_template(wrapper):
                return f"# Custom Guide\\n\\n{wrapper.get_symbol_table_text()}"

            wrapper.register_skill_template("custom-guide", _my_custom_template)
        """
        self._skill_templates[name] = template_fn
        logger.debug(f"Registered skill template: {name}")

    def register_skill_examples(
        self,
        skill_type: str,
        examples: List[str],
    ) -> None:
        """
        Register example content for a skill type.

        Args:
            skill_type: The skill type (e.g., "dsl-syntax")
            examples: List of example strings

        Example:
            wrapper.register_skill_examples("dsl-syntax", [
                "§[δ] - Simple section with one DecoratedText",
                "§[δ×3, Ƀ[ᵬ×2]] - Section with 3 texts and 2 buttons",
            ])
        """
        if skill_type not in self._skill_examples:
            self._skill_examples[skill_type] = []
        self._skill_examples[skill_type].extend(examples)
        logger.debug(f"Registered {len(examples)} examples for skill: {skill_type}")

    def register_skill_metadata(
        self,
        skill_type: str,
        metadata: Dict[str, Any],
    ) -> None:
        """
        Register additional metadata for a skill type.

        Args:
            skill_type: The skill type (e.g., "dsl-syntax")
            metadata: Dict of metadata key-value pairs
        """
        if skill_type not in self._skill_metadata:
            self._skill_metadata[skill_type] = {}
        self._skill_metadata[skill_type].update(metadata)

    def get_skill_template(self, name: str) -> Optional[Callable]:
        """Get a registered skill template by name."""
        return self._skill_templates.get(name)

    def get_skill_examples(self, skill_type: str) -> List[str]:
        """Get registered examples for a skill type."""
        return self._skill_examples.get(skill_type, [])

    def get_registered_templates(self) -> List[str]:
        """Get list of all registered template names."""
        return list(self._skill_templates.keys())

    # =========================================================================
    # GENERIC SKILL GENERATORS (Use introspected module data)
    # =========================================================================

    def generate_symbol_reference(self) -> SkillDocument:
        """
        Generate a symbol reference skill document from self.symbol_mapping.

        Returns:
            SkillDocument with symbol table content
        """
        symbol_mapping = getattr(self, "symbol_mapping", {})
        module_name = getattr(self, "module_name", "module")

        if not symbol_mapping:
            logger.warning("No symbol_mapping available for symbol reference")
            content = "# Symbol Reference\n\nNo symbols available."
            return SkillDocument(
                name="symbols",
                title="Symbol Reference",
                description="Component symbol reference table",
                content=content,
                tags={"symbols", "reference"},
            )

        # Group symbols by first letter
        by_letter: Dict[str, List[tuple]] = defaultdict(list)
        for comp, sym in symbol_mapping.items():
            by_letter[comp[0].upper()].append((sym, comp))

        lines = [
            f"# Symbol Reference for {module_name}\n",
            "This document maps component symbols to their names.\n",
            "## Symbol Table\n",
        ]

        for letter in sorted(by_letter.keys()):
            items = by_letter[letter]
            mappings = [f"`{sym}` = {comp}" for sym, comp in sorted(items, key=lambda x: x[1])]
            lines.append(f"**{letter}:** {', '.join(mappings)}")
            lines.append("")  # Blank line

        # Add reverse lookup section
        lines.append("\n## Quick Lookup\n")
        lines.append("| Symbol | Component |")
        lines.append("|--------|-----------|")
        for comp, sym in sorted(symbol_mapping.items()):
            lines.append(f"| `{sym}` | {comp} |")

        content = "\n".join(lines)

        return SkillDocument(
            name="symbols",
            title=f"Symbol Reference for {module_name}",
            description="Component symbol reference table",
            content=content,
            tags={"symbols", "reference", module_name},
        )

    def generate_component_docs(
        self,
        component_name: Optional[str] = None,
    ) -> Dict[str, SkillDocument]:
        """
        Generate documentation for components from self.components.

        Args:
            component_name: Optional specific component to document (None = all)

        Returns:
            Dict mapping component name to SkillDocument
        """
        components = getattr(self, "components", {})
        symbol_mapping = getattr(self, "symbol_mapping", {})
        relationships = getattr(self, "relationships", {})

        docs = {}

        for path, comp in components.items():
            # Skip if filtering to specific component
            if component_name and comp.name != component_name:
                continue

            # Skip non-class components
            if comp.component_type != "class":
                continue

            name = comp.name
            symbol = symbol_mapping.get(name, "")
            children = relationships.get(name, [])

            lines = [
                f"# {name}",
                "",
            ]

            if symbol:
                lines.append(f"**Symbol:** `{symbol}`\n")

            if comp.docstring:
                lines.append("## Description\n")
                lines.append(comp.docstring)
                lines.append("")

            if children:
                lines.append("## Valid Children\n")
                child_items = []
                for child in children[:10]:  # Limit for readability
                    child_sym = symbol_mapping.get(child, "")
                    if child_sym:
                        child_items.append(f"- `{child_sym}` {child}")
                    else:
                        child_items.append(f"- {child}")
                lines.extend(child_items)
                if len(children) > 10:
                    lines.append(f"- ... and {len(children) - 10} more")
                lines.append("")

            # Add field information if available
            if hasattr(comp, "fields") and comp.fields:
                lines.append("## Fields\n")
                lines.append("| Field | Type | Required |")
                lines.append("|-------|------|----------|")
                for field_name, field_info in comp.fields.items():
                    required = "Yes" if field_info.get("required") else "No"
                    field_type = field_info.get("type", "unknown")
                    lines.append(f"| `{field_name}` | {field_type} | {required} |")
                lines.append("")

            content = "\n".join(lines)

            docs[name] = SkillDocument(
                name=name,
                title=f"{name} Component",
                description=comp.docstring[:100] if comp.docstring else f"{name} component documentation",
                content=content,
                tags={"component", name.lower()},
            )

        return docs

    def generate_containment_rules(self) -> SkillDocument:
        """
        Generate containment rules documentation from self._relationship_graph.

        Returns:
            SkillDocument with containment rules
        """
        relationships = getattr(self, "relationships", {})
        symbol_mapping = getattr(self, "symbol_mapping", {})
        module_name = getattr(self, "module_name", "module")

        lines = [
            f"# Containment Rules for {module_name}\n",
            "This document describes which components can contain which.\n",
            "## Parent → Children Relationships\n",
        ]

        if not relationships:
            lines.append("No containment relationships defined.")
        else:
            lines.append("| Parent | Symbol | Children |")
            lines.append("|--------|--------|----------|")

            for parent, children in sorted(relationships.items()):
                parent_sym = symbol_mapping.get(parent, "-")
                if children:
                    child_syms = [
                        f"`{symbol_mapping.get(c, c[0])}`={c}"
                        for c in children[:5]
                    ]
                    if len(children) > 5:
                        child_syms.append(f"+{len(children) - 5} more")
                    children_str = ", ".join(child_syms)
                else:
                    children_str = "(leaf)"
                lines.append(f"| {parent} | `{parent_sym}` | {children_str} |")

        content = "\n".join(lines)

        return SkillDocument(
            name="containment-rules",
            title=f"Containment Rules for {module_name}",
            description="What components can contain what",
            content=content,
            tags={"containment", "hierarchy", "rules"},
        )

    def generate_main_skill(
        self,
        skill_name: str,
        skill_title: str,
        description: str = "",
    ) -> SkillDocument:
        """
        Generate the main SKILL.md document.

        Args:
            skill_name: Skill directory name (e.g., "gchat-cards")
            skill_title: Human-readable title
            description: Optional description

        Returns:
            SkillDocument for the main SKILL.md file
        """
        module_name = getattr(self, "module_name", "module")

        lines = [
            f"# {skill_title}\n",
        ]

        if description:
            lines.append(f"{description}\n")

        # Quick start section
        lines.append("## Quick Start\n")
        lines.append(f"This skill provides documentation for the {module_name} module.\n")

        # Available resources section
        lines.append("## Available Resources\n")

        resources = [
            ("symbols.md", "Complete symbol reference table"),
            ("containment-rules.md", "What components can contain what"),
        ]

        # Add custom templates
        for template_name in self._skill_templates.keys():
            resources.append((f"{template_name}.md", f"Custom guide: {template_name}"))

        # Add component docs
        components = getattr(self, "components", {})
        class_count = sum(1 for c in components.values() if c.component_type == "class")
        if class_count > 0:
            resources.append(("components/", f"Per-component documentation ({class_count} components)"))

        for filename, desc in resources:
            lines.append(f"- `{filename}` - {desc}")

        lines.append("")

        content = "\n".join(lines)

        return SkillDocument(
            name="SKILL",
            title=skill_title,
            description=description or f"Skills for {module_name}",
            content=content,
            tags={skill_name, module_name},
        )

    # =========================================================================
    # SKILL GENERATION ORCHESTRATION
    # =========================================================================

    def generate_all_skills(
        self,
        config: Optional[SkillGeneratorConfig] = None,
    ) -> Dict[str, SkillDocument]:
        """
        Generate all skill documents for the wrapped module.

        Args:
            config: Optional configuration for generation

        Returns:
            Dict mapping skill name to SkillDocument
        """
        config = config or SkillGeneratorConfig()
        module_name = getattr(self, "module_name", "module")

        skills: Dict[str, SkillDocument] = {}

        # Generate main skill document
        skill_name = config.skill_name or module_name.replace("_", "-")
        skill_title = config.skill_title or f"{module_name} Skills"

        skills["SKILL"] = self.generate_main_skill(
            skill_name=skill_name,
            skill_title=skill_title,
        )

        # Generate symbol reference
        skills["symbols"] = self.generate_symbol_reference()

        # Generate containment rules
        if config.include_hierarchy:
            skills["containment-rules"] = self.generate_containment_rules()

        # Generate component docs
        if config.include_components:
            component_docs = self.generate_component_docs()
            for comp_name, doc in component_docs.items():
                skills[f"components/{comp_name}"] = doc

        # Generate custom templates
        for template_name, template_fn in self._skill_templates.items():
            try:
                content = template_fn(self)
                examples = self.get_skill_examples(template_name)

                # Append examples if any
                if examples and config.include_examples:
                    content += "\n\n## Examples\n\n"
                    for ex in examples[:config.max_example_count]:
                        content += f"- `{ex}`\n"

                skills[template_name] = SkillDocument(
                    name=template_name,
                    title=template_name.replace("-", " ").title(),
                    description=f"Custom guide: {template_name}",
                    content=content,
                    tags={template_name},
                )
            except Exception as e:
                logger.error(f"Failed to generate template '{template_name}': {e}")

        # Cache the generated skills
        self._skills_cache = skills

        logger.info(f"Generated {len(skills)} skill documents for {module_name}")
        return skills

    def export_skills_to_directory(
        self,
        path: str | Path,
        config: Optional[SkillGeneratorConfig] = None,
    ) -> Path:
        """
        Export skill documents to a filesystem directory.

        Args:
            path: Directory path to write skills to
            config: Optional configuration for generation

        Returns:
            Path to the skills directory
        """
        path = Path(path).expanduser().resolve()
        path.mkdir(parents=True, exist_ok=True)

        config = config or SkillGeneratorConfig(output_dir=str(path))
        module_name = getattr(self, "module_name", "module")

        # Generate all skills
        skills = self.generate_all_skills(config)

        # Track written files for manifest
        skill_infos: List[SkillInfo] = []

        # Write each skill document
        for skill_name, doc in skills.items():
            # Determine file path
            if "/" in skill_name:
                # Nested path (e.g., "components/Button")
                parts = skill_name.split("/")
                subdir = path / "/".join(parts[:-1])
                subdir.mkdir(parents=True, exist_ok=True)
                filename = f"{parts[-1]}.md"
                file_path = subdir / filename
            else:
                # Top-level file
                filename = f"{skill_name}.md"
                file_path = path / filename

            # Write content
            file_path.write_text(doc.content, encoding="utf-8")

            # Write supporting files
            for support_name, support_content in doc.supporting_files.items():
                support_path = path / support_name
                support_path.parent.mkdir(parents=True, exist_ok=True)
                support_path.write_text(support_content, encoding="utf-8")

            # Track for manifest (skip nested component docs)
            if "/" not in skill_name:
                skill_infos.append(SkillInfo(
                    name=doc.name,
                    title=doc.title,
                    description=doc.description,
                    filename=filename,
                    tags=list(doc.tags),
                ))

        # Write manifest
        manifest = SkillManifest(
            name=config.skill_name or module_name.replace("_", "-"),
            description=f"Skills for {module_name}",
            skills=skill_infos,
            generated_at=datetime.utcnow(),
            source_module=module_name,
            version=config.version,
        )

        manifest_path = path / "_manifest.json"
        manifest_path.write_text(
            json.dumps(manifest.to_dict(), indent=2),
            encoding="utf-8",
        )

        self._skills_directory = path
        logger.info(f"Exported {len(skills)} skills to {path}")

        return path

    def get_skill_manifest(
        self,
        config: Optional[SkillGeneratorConfig] = None,
    ) -> SkillManifest:
        """
        Generate a manifest describing all skills.

        Args:
            config: Optional configuration

        Returns:
            SkillManifest object
        """
        config = config or SkillGeneratorConfig()
        module_name = getattr(self, "module_name", "module")

        # Generate skills if not cached
        if not self._skills_cache:
            self.generate_all_skills(config)

        skill_infos = []
        for skill_name, doc in self._skills_cache.items():
            if "/" not in skill_name:  # Skip nested docs
                skill_infos.append(SkillInfo(
                    name=doc.name,
                    title=doc.title,
                    description=doc.description,
                    filename=f"{skill_name}.md",
                    tags=list(doc.tags),
                ))

        return SkillManifest(
            name=config.skill_name or module_name.replace("_", "-"),
            description=f"Skills for {module_name}",
            skills=skill_infos,
            generated_at=datetime.utcnow(),
            source_module=module_name,
            version=config.version,
        )

    def invalidate_skills_cache(self) -> None:
        """Clear the cached skill documents."""
        self._skills_cache.clear()
        logger.debug("Invalidated skills cache")


# Export for convenience
__all__ = [
    "SkillsMixin",
]
