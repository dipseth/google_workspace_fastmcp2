#!/usr/bin/env python3
"""Regenerate the Claude Code plugin's bundled skills from source.

The plugin at plugins/google-workspace-unlimited bundles the same skills the
server generates at startup (skills/skills_provider.py): gchat-cards,
mjml-email, and qdrant-search from ModuleWrapper introspection, plus the
cross-module google-workspace-mcp server skill. The committed copies are
generated artifacts — never edit them by hand; edit the source models or
generators and re-run this script.

Generation is pure introspection: no Qdrant, no credentials, no network.
`generated_at` in each _manifest.json is nulled so output is byte-for-byte
deterministic and CI can gate on `--check`.

Usage:
    uv run python scripts/generate_plugin_skills.py           # regenerate in place
    uv run python scripts/generate_plugin_skills.py --check   # exit 1 if committed
                                                              # skills are stale

Exit codes:
    0 - Success (or --check found no drift)
    1 - Generation failure, or --check found drift

::

    Before the wheel, before the tag,
    before the merge to main —
    regenerate, or CI's flag
    will stop the deploy train.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

# Hermetic generation: canonical skills are what a FRESH install produces.
# A live dev Qdrant carries legacy symbol state that changes symbol
# assignment and component discovery, so force it unreachable — don't just
# skip auto-launch. Same for HF downloads.
os.environ["QDRANT_URL"] = "http://127.0.0.1:1"
os.environ["QDRANT_AUTO_LAUNCH"] = "false"
os.environ.setdefault("HF_HUB_OFFLINE", "1")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

PLUGIN_SKILLS_DIR = PROJECT_ROOT / "plugins" / "google-workspace-unlimited" / "skills"


def _normalize_manifest(manifest_path: Path) -> None:
    """Null the generated_at timestamp so regeneration is deterministic."""
    if not manifest_path.exists():
        return
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    data["generated_at"] = None
    manifest_path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def generate(skills_root: Path) -> None:
    """Generate all plugin skills into skills_root (same set as server.py)."""
    from adapters.module_wrapper.skill_types import SkillGeneratorConfig
    from gchat.wrapper_setup import get_card_framework_wrapper
    from gmail.email_wrapper_setup import get_email_wrapper
    from middleware.qdrant_core.qdrant_models_wrapper import (
        get_qdrant_models_wrapper,
    )
    from skills.server_skill_generator import write_server_skill
    from skills.skills_provider import (
        _get_skill_description,
        _get_skill_name,
        _get_skill_title,
    )

    card_wrapper = get_card_framework_wrapper()
    email_wrapper = get_email_wrapper()
    qdrant_wrapper = get_qdrant_models_wrapper()

    skills_root.mkdir(parents=True, exist_ok=True)

    for wrapper in (card_wrapper, email_wrapper, qdrant_wrapper):
        module_name = wrapper.module_name
        skill_name = _get_skill_name(module_name)
        skill_dir = skills_root / skill_name

        # Full rebuild so files for removed/renamed components don't linger
        if skill_dir.exists():
            shutil.rmtree(skill_dir)

        config = SkillGeneratorConfig(
            output_dir=str(skill_dir),
            skill_name=skill_name,
            skill_title=_get_skill_title(module_name),
            skill_description=_get_skill_description(module_name),
            include_examples=True,
            include_hierarchy=True,
            include_components=True,
        )
        wrapper.export_skills_to_directory(skill_dir, config)
        _normalize_manifest(skill_dir / "_manifest.json")
        print(f"Generated: {skill_dir}")

    server_skill_dir = write_server_skill(skills_root, card_wrapper, email_wrapper)
    print(f"Generated: {server_skill_dir}")


def compare_trees(generated: Path, committed: Path) -> list[str]:
    """Return human-readable drift entries between two skill trees."""
    gen_files = {p.relative_to(generated) for p in generated.rglob("*") if p.is_file()}
    com_files = {p.relative_to(committed) for p in committed.rglob("*") if p.is_file()}

    drift = []
    for rel in sorted(gen_files - com_files):
        drift.append(f"missing from committed skills: {rel}")
    for rel in sorted(com_files - gen_files):
        drift.append(f"stale committed file (no longer generated): {rel}")
    for rel in sorted(gen_files & com_files):
        if (generated / rel).read_bytes() != (committed / rel).read_bytes():
            drift.append(f"content differs: {rel}")
    return drift


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Generate into a temp dir and fail if the committed plugin "
        "skills differ (for CI)",
    )
    args = parser.parse_args()

    if not args.check:
        generate(PLUGIN_SKILLS_DIR)
        return 0

    with tempfile.TemporaryDirectory(prefix="plugin-skills-") as tmp:
        tmp_root = Path(tmp)
        generate(tmp_root)
        drift = compare_trees(tmp_root, PLUGIN_SKILLS_DIR)

    if drift:
        print(
            f"\nPlugin skills are out of date ({len(drift)} file(s)):",
            file=sys.stderr,
        )
        for entry in drift[:40]:
            print(f"  {entry}", file=sys.stderr)
        if len(drift) > 40:
            print(f"  ... and {len(drift) - 40} more", file=sys.stderr)
        print(
            "\nRun: uv run python scripts/generate_plugin_skills.py "
            "and commit the result.",
            file=sys.stderr,
        )
        return 1

    print("Plugin skills are up to date.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
