# CLAUDE.md

## Release / deployment pattern

- **A release is a version bump merged to `main`.** [.github/workflows/publish.yml](.github/workflows/publish.yml) runs on every push to `main` and publishes to PyPI **only if** `version` in `pyproject.toml` differs from the previous commit (`HEAD~1`). No tags involved.
- **Every PR that should ship must bump the version** in *both* places, kept in sync:
  - `pyproject.toml` → `version = "X.Y.Z"`
  - `uv.lock` → the `google-workspace-unlimited` package entry's `version`
- Title the release PR / merge commit **`Release X.Y.Z — <summary>`** (see git history for examples).
- Semver-ish: patch for fixes, minor for new tools/features or behavior-default changes.
- Downstream consumers: PyPI (`uvx google-workspace-unlimited`) and Glama's Docker build (clones this repo and runs `uv sync`). The wheel must include all runtime packages — check `[tool.hatch.build.targets.wheel]` when adding a new top-level package dir (a missing `lifespans/` broke 2.4.x on PyPI).

## Python version

- `requires-python = ">=3.11,<3.13"`; `.python-version` pins **3.12**. Keep the pin — Glama auto-detects the Docker Python version from it and previously picked an incompatible 3.14 when the file was absent.

## Pre-push checks

- Run **both** `ruff check .` and `ruff format --check .` — CI gates them separately.
- Production code must never import from `research/`; TRM inference definitions live in `adapters/`.
