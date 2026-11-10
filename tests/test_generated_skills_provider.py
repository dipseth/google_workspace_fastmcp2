"""GeneratedSkillsProvider serves the folders it is given and nothing beside them."""

from pathlib import Path

import pytest
from fastmcp import Client, FastMCP
from fastmcp.skills import SkillsClientExtension

from skills.skills_provider import GeneratedSkillsProvider


def _write_skill(root: Path, name: str, body: str = "Body.") -> Path:
    skill_dir = root / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: The {name} skill.\n---\n\n{body}\n"
    )
    (skill_dir / "extra.md").write_text("supporting file")
    return skill_dir


async def _skill_uris(mcp: FastMCP) -> set[str]:
    async with Client(mcp) as client:
        return {str(r.uri) for r in await client.list_resources()}


async def test_serves_only_the_given_folders(tmp_path):
    ours = _write_skill(tmp_path, "ours")
    _write_skill(tmp_path, "someone-elses")
    _write_skill(tmp_path / "synced" / "abc", "nested")

    mcp = FastMCP("t")
    mcp.add_provider(GeneratedSkillsProvider([ours]))

    uris = await _skill_uris(mcp)
    assert "skill://ours/SKILL.md" in uris
    assert "skill://ours/extra.md" in uris
    assert all(uri.startswith("skill://ours/") for uri in uris)


async def test_skills_extension_lists_the_skill(tmp_path):
    mcp = FastMCP("t")
    mcp.add_provider(GeneratedSkillsProvider([_write_skill(tmp_path, "ours")]))

    async with Client(mcp, extensions=[SkillsClientExtension()]) as client:
        skills = await client.list_skills()
    assert [s.uri for s in skills] == ["skill://ours/SKILL.md"]


async def test_reload_serves_regenerated_content(tmp_path):
    ours = _write_skill(tmp_path, "ours", body="first")
    mcp = FastMCP("t")
    mcp.add_provider(GeneratedSkillsProvider([ours], reload=True))

    async with Client(mcp) as client:
        (ours / "SKILL.md").write_text(
            "---\nname: ours\ndescription: The ours skill.\n---\n\nsecond\n"
        )
        content = await client.read_resource("skill://ours/SKILL.md")
    assert "second" in content[0].text


async def test_reload_keeps_last_good_skills_when_a_folder_breaks(tmp_path):
    ours = _write_skill(tmp_path, "ours", body="first")
    mcp = FastMCP("t")
    mcp.add_provider(GeneratedSkillsProvider([ours], reload=True))

    async with Client(mcp) as client:
        (ours / "SKILL.md").write_text("no frontmatter")
        content = await client.read_resource("skill://ours/SKILL.md")
    assert "first" in content[0].text


def test_invalid_folder_fails_at_construction(tmp_path):
    bad = tmp_path / "bad"
    bad.mkdir()
    (bad / "SKILL.md").write_text("no frontmatter")
    with pytest.raises(ValueError):
        GeneratedSkillsProvider([bad])
