# Google Workspace Unlimited — Claude Code plugin

One-command install of the [google-workspace-unlimited](https://github.com/dipseth/google_workspace_fastmcp2) MCP server plus the skills that teach Claude its card/email DSL, code mode, and Qdrant search.

## What you get

- **MCP server** — runs locally via `uvx google-workspace-unlimited` (fetched from PyPI on demand). Code Mode is on by default, so Claude sees 7 lean meta-tools instead of 90+ schemas. Covers Gmail, Drive, Docs, Sheets, Slides, Calendar, Forms, Chat, Photos, and Contacts.
- **Skills**
  - `google-workspace-mcp` — overall guide: DSL notation, code mode, macros, tool map
  - `gchat-cards` — Google Chat card builder DSL (components, containment rules, Jinja filters)
  - `mjml-email` — MJML email composer DSL
  - `qdrant-search` — vector search over past tool responses (filters, recommendation, query DSL)

## Install

```
/plugin marketplace add dipseth/google_workspace_fastmcp2
/plugin install google-workspace-unlimited@riversunlimited
```

Requires [uv](https://docs.astral.sh/uv/) (`uvx`) on your PATH and Python 3.11–3.12.

## First-time authentication

The server starts with zero configuration. Before your **first** OAuth flow you need Google OAuth credentials — either enter them in the plugin's config when prompted (client ID + secret, or a path to the downloaded client secrets JSON), or skip them if your credentials are already stored from a previous installation.

Then, in a conversation, ask Claude to authenticate:

> "Authenticate my Google account (you@example.com)"

A browser window opens for consent. Credentials are stored encrypted under the plugin's data directory and survive plugin updates.

## Maintenance

Everything under `skills/` is **generated** — the same ModuleWrapper introspection the server runs at startup produces these files. Never edit them by hand: run `uv run python scripts/generate_plugin_skills.py` from the repo root and commit the result. CI (`--check`) fails any PR where the committed skills drift from the generators.

## Notes

- Stored credentials live in `~/.claude/plugins/data/<plugin-id>/credentials`. Delete that directory to sign out completely, and revoke access at <https://myaccount.google.com/permissions>.
- The optional Qdrant-backed history features auto-launch a local Qdrant via Docker when available; without Docker the server still runs, just without response history/search.
- Privacy policy: see [PRIVACY.md](https://github.com/dipseth/google_workspace_fastmcp2/blob/main/PRIVACY.md) — the server is self-hosted; your data is processed on your machine and Google's APIs only.
