# CLAUDE.md

## Release / deployment pattern

- **A release is a version bump merged to `main`.** [.github/workflows/publish.yml](.github/workflows/publish.yml) runs on every push to `main` and publishes to PyPI **only if** `version` in `pyproject.toml` differs from the previous commit (`HEAD~1`). You never push a tag to trigger a release.
- **The same workflow then tags and releases.** After the PyPI upload it pushes an annotated tag `vX.Y.Z` and creates a GitHub Release with generated notes. If one of those steps fails, PyPI already has the version, so don't re-run the job (`uv publish` would fail on the existing files). Finish by hand instead: `git tag -a vX.Y.Z <merge-sha> -m vX.Y.Z && git push upstream vX.Y.Z`, then `gh release create vX.Y.Z --title vX.Y.Z --generate-notes --verify-tag`. This happened for 3.5.0, when GitHub rejected the tag push with a server error.
- **Every PR that should ship must bump the version** in *both* places, kept in sync:
  - `pyproject.toml` → `version = "X.Y.Z"`
  - `uv.lock` → the `google-workspace-unlimited` package entry's `version`
- Title the release PR / merge commit **`Release X.Y.Z — <summary>`** (see git history for examples).
- Semver-ish: patch for fixes, minor for new tools/features or behavior-default changes.
- Downstream consumers: PyPI (`uvx google-workspace-unlimited`) and Glama's Docker build (clones this repo and runs `uv sync`). The wheel must include all runtime packages — check `[tool.hatch.build.targets.wheel]` when adding a new top-level package dir (a missing `lifespans/` broke 2.4.x on PyPI).

### Glama hosted deploy (admin build spec)

- `cmdArguments` must use `uv run --no-sync` — plain `uv run` rebuilds the package on every container start (~33s), blowing Glama's ~35s health-check timeout and marking the server "unhealthy" (503s on every request).
- `buildSteps`: `uv sync --compile-bytecode`, then `uv run --no-sync python -c 'import server' || true` to warm imports at build time (~12s cold start, measured).
- Set `QDRANT_AUTO_LAUNCH=false` in hosted env vars (default `true` tries to launch Qdrant via Docker, which doesn't exist in the container).

## Learned model artifacts

- Checkpoints ship via `MODEL_ARTIFACT_URI` (JSON map `{"gchat": gs://…, "email": gs://…}`); servers download them at startup into `credentials/model_cache/<domain>/`.
- **A cached artifact is never re-checked against the bucket** — the checksum only compares the local file with its own registry entry. After re-publishing, delete `credentials/model_cache/<domain>/best_model_unified.pt` (or the deployment's `MODEL_ARTIFACT_CACHE_DIR` copy) on any host that already has it; fresh containers pick it up automatically.
- Before overwriting a published checkpoint, copy it aside in the bucket (e.g. `best_model_unified.pre-<change>-<date>.pt`).
- Offline/local runs: point slot assignment at a file with `UNIFIED_TRN_CHECKPOINT_<DOMAIN>=…` (artifact paths take precedence when present).
- The email checkpoint carries `placement_head` (learned item→block placement); build it with `research/trm/email/build_placement_head.py` (research is gitignored and never imported by production).

## FastMCP pin

- FastMCP is pinned exactly (`fastmcp[...]==4.2.3`); it pins `fastmcp-slim` and `fastmcp-tasks` to the same version itself. Don't release with a prerelease pin: uv and uvx accept a prerelease only for a package the installer names, so 3.5.0 and 3.6.0 (pinned to `4.2.0a4`) could not be resolved from PyPI and a plain `uvx google-workspace-unlimited` fell back to 3.4.0. Naming the split packages in our own `dependencies` only helped `uv sync` inside this repo.
- `execute` in [tools/code_mode.py](tools/code_mode.py) replaces FastMCP's own, so upstream Code Mode changes never arrive by upgrading. On each bump, diff `fastmcp/experimental/transforms/code_mode.py` between the two versions and port what applies, then run `tests/test_code_mode.py`.
- Skills are served by `GeneratedSkillsProvider` ([skills/skills_provider.py](skills/skills_provider.py)), which reads only the folders the server generated. They are listed through the MCP Skills extension (`skills/list`) and readable as `skill://` resources, with Code Mode on or off (before FastMCP 4.2.2 a server with transforms listed none).

## Bring-your-own-module tools

- `wrap_module` / `search_module` / `build_module_object` ([tools/module_tools.py](tools/module_tools.py)) are registered only with `MODULE_TOOLS_ENABLED=true`. Standard-library modules are refused, `MODULE_TOOLS_ALLOWED` (comma-separated prefixes) narrows what can be wrapped, and building is limited to data classes (pydantic models, dataclasses, enums).
- `search_module` reranks its top-25 pool with TypeSafe Jev when `TYPESAFE_API_KEY` is set (`MODULE_TOOLS_RERANK=pool` turns it off); errors fall back to pool order.
- Collections are `mcp_module_v2_<module>`; bump `_INDEX_VERSION` when what gets indexed changes. Class points carry a `description` vector only in collections created since 3.7.0 — older collections keep working without it until recreated.
- **Never index research modules into the cloud Qdrant cluster.** ColBERT multivectors are ~100 KB/point; TRM research filled the 16 GiB cluster (2026-10-29) and a full disk blocks even deletes. Research wrappers default to embedded Qdrant (`research/trm/qdrant_local`).

## Python version

- `requires-python = ">=3.11,<3.13"`; `.python-version` pins **3.12**. Keep the pin — Glama auto-detects the Docker Python version from it and previously picked an incompatible 3.14 when the file was absent.

## Pre-push checks

- Run **both** `ruff check .` and `ruff format --check .` — CI gates them separately.
- **Plugin skills are generated, never hand-edited.** `plugins/google-workspace-unlimited/skills/` is produced by `uv run python scripts/generate_plugin_skills.py` from the same ModuleWrapper introspection the server uses at startup; CI fails if the committed copies drift (`--check`). After changing card/email/qdrant models, skill generators, or `skills/skills_provider.py`, regenerate and commit.
- Production code must never import from `research/`; TRM inference definitions live in `adapters/`.
