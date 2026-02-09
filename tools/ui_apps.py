"""
MCP Apps Phase 1 — UI resource registration.

Registers ``ui://`` resources that serve self-contained HTML dashboards.
Phase 1 is read-only (no postMessage bridge); the HTML renders a static
snapshot of tool state injected via ``window.__MCP_TOOLS__``.
"""

import json

from fastmcp import FastMCP
from fastmcp.server.apps import ResourceUI

_TOOLS_PLACEHOLDER = "/*__MCP_TOOLS_DATA__*/"

_PROTECTED_TOOLS = {
    "manage_tools",
    "manage_tools_by_analytics",
    "health_check",
    "start_google_auth",
    "check_drive_auth",
}


def _collect_tools_json(mcp: FastMCP) -> str:
    """Collect tool info from the server registry and return as JSON.

    Reuses the same enabled-state logic as ``manage_tools(action="list")``:
    global disabled state is read from FastMCP transforms, and the protected
    tools set mirrors ``server_tools.py``.
    """
    # Import here to avoid circular imports at module level
    from tools.server_tools import _get_tool_enabled_state

    tools = []
    try:
        components = mcp._local_provider._components
        for key, comp in sorted(components.items()):
            if not key.startswith("tool:"):
                continue
            name = comp.name
            if name.startswith("_"):
                continue
            enabled = _get_tool_enabled_state(comp, mcp)
            tools.append(
                {
                    "name": name,
                    "enabled": enabled,
                    "isProtected": name in _PROTECTED_TOOLS,
                    "description": getattr(comp, "description", None),
                }
            )
    except Exception:
        pass
    return json.dumps(tools)


def _build_manage_tools_html(tools_json: str = "[]") -> str:
    """Return a complete HTML SPA for the manage-tools dashboard."""
    html = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Tool Management Dashboard</title>
<style>
  :root {
    --bg: #1a1b26; --surface: #24283b; --border: #414868;
    --text: #c0caf5; --text-dim: #565f89; --accent: #7aa2f7;
    --green: #9ece6a; --gray: #565f89; --red: #f7768e;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, monospace;
    background: var(--bg); color: var(--text); padding: 1.5rem;
  }
  header {
    display: flex; align-items: center; gap: 1rem;
    margin-bottom: 1.5rem; flex-wrap: wrap;
  }
  header h1 { font-size: 1.25rem; font-weight: 600; }
  .badge {
    font-size: 0.7rem; padding: 0.2rem 0.6rem; border-radius: 999px;
    background: var(--border); color: var(--text-dim); font-weight: 500;
  }
  .stats {
    display: flex; gap: 1.5rem; margin-bottom: 1.5rem;
    font-size: 0.85rem; color: var(--text-dim);
  }
  .stats strong { color: var(--text); }
  #tool-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
    gap: 0.75rem;
  }
  .tool-card {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 8px; padding: 0.85rem 1rem;
    display: flex; align-items: flex-start; gap: 0.65rem;
    transition: border-color 0.15s;
  }
  .tool-card:hover { border-color: var(--accent); }
  .dot {
    width: 8px; height: 8px; border-radius: 50%;
    margin-top: 0.35rem; flex-shrink: 0;
  }
  .dot.enabled  { background: var(--green); }
  .dot.disabled { background: var(--gray); }
  .tool-name {
    font-size: 0.85rem; font-weight: 600;
    word-break: break-word;
  }
  .tool-desc {
    font-size: 0.75rem; color: var(--text-dim);
    margin-top: 0.25rem; line-height: 1.35;
    display: -webkit-box; -webkit-line-clamp: 2;
    -webkit-box-orient: vertical; overflow: hidden;
  }
  .protected-badge {
    font-size: 0.6rem; color: var(--accent);
    background: rgba(122, 162, 247, 0.1);
    padding: 0.1rem 0.4rem; border-radius: 4px;
    margin-top: 0.3rem; display: inline-block;
  }
  .empty {
    text-align: center; padding: 3rem; color: var(--text-dim);
    grid-column: 1 / -1;
  }
</style>
</head>
<body>
<header>
  <h1>Tool Management</h1>
  <span class="badge">Phase 1: Read-Only</span>
</header>
<div class="stats" id="stats"></div>
<div id="tool-grid"></div>
<script>
  // Phase 1: server-side snapshot injected at resource-read time.
  // Phase 2 will update live via postMessage bridge.
  window.__MCP_TOOLS__ = /*__MCP_TOOLS_DATA__*/;

  function render(tools) {
    const grid = document.getElementById('tool-grid');
    const stats = document.getElementById('stats');
    if (!tools.length) {
      grid.innerHTML = '<div class="empty">No tool data available.<br>Phase 2 will stream live state via postMessage.</div>';
      stats.innerHTML = '';
      return;
    }
    const enabled = tools.filter(t => t.enabled).length;
    const disabled = tools.length - enabled;
    stats.innerHTML =
      '<span>Total: <strong>' + tools.length + '</strong></span>' +
      '<span>Enabled: <strong style="color:var(--green)">' + enabled + '</strong></span>' +
      '<span>Disabled: <strong style="color:var(--gray)">' + disabled + '</strong></span>';
    grid.innerHTML = tools.map(t => {
      const dotCls = t.enabled ? 'enabled' : 'disabled';
      const protBadge = t.isProtected ? '<div class="protected-badge">protected</div>' : '';
      const desc = t.description
        ? '<div class="tool-desc">' + t.description.replace(/</g, '&lt;') + '</div>'
        : '';
      return '<div class="tool-card">' +
        '<div class="dot ' + dotCls + '"></div>' +
        '<div><div class="tool-name">' + t.name.replace(/</g, '&lt;') + '</div>' +
        desc + protBadge + '</div></div>';
    }).join('');
  }

  render(window.__MCP_TOOLS__);
</script>
</body>
</html>"""
    return html.replace(_TOOLS_PLACEHOLDER, tools_json)


def setup_ui_apps(mcp: FastMCP) -> None:
    """Register ``ui://`` resources for MCP Apps Phase 1."""

    @mcp.resource(
        "ui://manage-tools-dashboard",
        name="manage_tools_dashboard",
        title="Tool Management Dashboard",
        description="Read-only dashboard showing tool enable/disable state",
        tags={"ui", "dashboard", "tools"},
        ui=ResourceUI(prefers_border=True),
    )
    def manage_tools_dashboard() -> str:
        return _build_manage_tools_html(_collect_tools_json(mcp))
