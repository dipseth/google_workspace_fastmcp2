"""
MCP Apps Phase 1 — UI resource registration.

Registers ``ui://`` resources that serve self-contained HTML dashboards.
Phase 1 is read-only (no postMessage bridge); the HTML renders a static
snapshot of tool state injected via ``window.__MCP_TOOLS__``.
"""

import json

from fastmcp import FastMCP
from fastmcp.server.apps import AppConfig

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
    
    Also includes session-specific state and service grouping for the UI.
    """
    # Import here to avoid circular imports at module level
    from auth.context import get_session_context_sync, get_session_disabled_tools_sync
    from middleware.qdrant_core.query_parser import extract_service_from_tool
    from tools.server_tools import _get_tool_enabled_state

    tools = []
    session_disabled = set()
    has_session = False

    try:
        session_id = get_session_context_sync()
        if session_id:
            has_session = True
            session_disabled = get_session_disabled_tools_sync(session_id)
    except Exception:
        pass
    
    try:
        components = mcp.local_provider._components
        for key, comp in sorted(components.items()):
            if not key.startswith("tool:"):
                continue
            name = comp.name
            if name.startswith("_"):
                continue
            globally_enabled = _get_tool_enabled_state(comp, mcp)
            is_session_disabled = name in session_disabled
            service = extract_service_from_tool(name)
            
            tools.append(
                {
                    "name": name,
                    "enabled": globally_enabled,
                    "sessionDisabled": is_session_disabled,
                    "isProtected": name in _PROTECTED_TOOLS,
                    "description": comp.description,
                    "service": service,
                }
            )
    except Exception:
        pass
    
    result = {
        "tools": tools,
        "sessionState": {
            "sessionDisabledCount": len(session_disabled),
            "sessionAvailable": has_session,
        } if has_session else None
    }
    return json.dumps(result)


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
    --bg: #1a1b26; --surface: #24283b; --surface2: #292e42; --border: #414868;
    --text: #c0caf5; --text-dim: #565f89; --accent: #7aa2f7;
    --green: #9ece6a; --gray: #565f89; --orange: #ff9e64; --red: #f7768e;
    --purple: #bb9af7; --cyan: #7dcfff; --teal: #73daca;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, monospace;
    background: var(--bg); color: var(--text); padding: 1.5rem;
  }

  /* Header */
  header {
    display: flex; align-items: center; gap: 1rem;
    margin-bottom: 1.25rem; flex-wrap: wrap;
  }
  header h1 { font-size: 1.25rem; font-weight: 600; }
  .header-badge {
    font-size: 0.65rem; padding: 0.2rem 0.55rem; border-radius: 999px;
    background: var(--border); color: var(--text-dim); font-weight: 500;
  }

  /* Stats bar */
  .stats-bar {
    display: flex; gap: 0.5rem; margin-bottom: 1.25rem;
    flex-wrap: wrap;
  }
  .stat-chip {
    font-size: 0.75rem; padding: 0.3rem 0.7rem; border-radius: 6px;
    background: var(--surface); border: 1px solid var(--border);
    color: var(--text-dim); display: flex; align-items: center; gap: 0.35rem;
  }
  .stat-chip strong { font-weight: 600; }
  .stat-chip .dot-sm {
    width: 6px; height: 6px; border-radius: 50%; display: inline-block;
  }

  /* Service filter chips */
  .filter-bar {
    display: flex; gap: 0.4rem; margin-bottom: 1.25rem;
    flex-wrap: wrap; align-items: center;
  }
  .filter-label {
    font-size: 0.7rem; color: var(--text-dim); margin-right: 0.25rem;
    text-transform: uppercase; letter-spacing: 0.05em; font-weight: 600;
  }
  .chip {
    font-size: 0.7rem; padding: 0.25rem 0.65rem; border-radius: 999px;
    border: 1px solid var(--border); background: var(--surface);
    color: var(--text-dim); cursor: pointer; transition: all 0.15s;
    display: flex; align-items: center; gap: 0.35rem;
    user-select: none;
  }
  .chip:hover { border-color: var(--accent); color: var(--text); }
  .chip.active {
    background: rgba(122, 162, 247, 0.15); border-color: var(--accent);
    color: var(--accent); font-weight: 500;
  }
  .chip .svc-icon { font-size: 0.8rem; }
  .chip .chip-count {
    font-size: 0.6rem; background: var(--border); color: var(--text-dim);
    padding: 0.05rem 0.35rem; border-radius: 999px; font-weight: 600;
  }
  .chip.active .chip-count {
    background: rgba(122, 162, 247, 0.25); color: var(--accent);
  }

  /* Service groups */
  .service-group { margin-bottom: 1.5rem; }
  .group-header {
    display: flex; align-items: center; gap: 0.5rem;
    margin-bottom: 0.6rem; padding-bottom: 0.4rem;
    border-bottom: 1px solid var(--border);
  }
  .group-icon { font-size: 1rem; }
  .group-name {
    font-size: 0.85rem; font-weight: 600; text-transform: capitalize;
  }
  .group-count {
    font-size: 0.65rem; color: var(--text-dim);
    background: var(--surface); padding: 0.15rem 0.5rem;
    border-radius: 999px; border: 1px solid var(--border);
  }
  .group-status {
    margin-left: auto; font-size: 0.65rem; color: var(--text-dim);
    display: flex; gap: 0.6rem;
  }

  /* Tool grid */
  .tool-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
    gap: 0.6rem;
  }
  .tool-card {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 8px; padding: 0.75rem 0.85rem;
    display: flex; align-items: flex-start; gap: 0.55rem;
    transition: all 0.15s;
  }
  .tool-card:hover {
    border-color: var(--accent); background: var(--surface2);
    transform: translateY(-1px);
  }
  .tool-card.session-disabled {
    border-left: 2px solid var(--orange);
  }
  .tool-card.globally-disabled { opacity: 0.5; }
  .tool-card.active-tool {
    border-left: 2px solid var(--green);
  }

  /* Status dot */
  .dot {
    width: 8px; height: 8px; border-radius: 50%;
    margin-top: 0.3rem; flex-shrink: 0;
  }
  .dot.enabled  { background: var(--green); box-shadow: 0 0 4px rgba(158,206,106,0.4); }
  .dot.globally-disabled { background: var(--gray); }
  .dot.session-disabled { background: var(--orange); box-shadow: 0 0 4px rgba(255,158,100,0.3); }

  /* Tool info */
  .tool-info { flex: 1; min-width: 0; }
  .tool-name {
    font-size: 0.8rem; font-weight: 600;
    word-break: break-word; line-height: 1.3;
  }
  .tool-desc {
    font-size: 0.7rem; color: var(--text-dim);
    margin-top: 0.2rem; line-height: 1.35;
    display: -webkit-box; -webkit-line-clamp: 2;
    -webkit-box-orient: vertical; overflow: hidden;
  }
  .tool-badges { display: flex; gap: 0.3rem; margin-top: 0.3rem; flex-wrap: wrap; }
  .tbadge {
    font-size: 0.55rem; padding: 0.1rem 0.4rem; border-radius: 4px;
    font-weight: 500; display: inline-block; letter-spacing: 0.02em;
  }
  .tbadge.protected {
    color: var(--accent); background: rgba(122, 162, 247, 0.1);
  }
  .tbadge.session-only {
    color: var(--orange); background: rgba(255, 158, 100, 0.1);
  }
  .tbadge.svc-tag {
    color: var(--cyan); background: rgba(125, 207, 255, 0.08);
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
  <span class="header-badge">Phase 1 &middot; Read-Only</span>
</header>
<div class="stats-bar" id="stats"></div>
<div class="filter-bar" id="filters"></div>
<div id="groups-container"></div>
<script>
  window.__MCP_TOOLS__ = /*__MCP_TOOLS_DATA__*/;

  const SERVICE_META = {
    gmail:    { icon: '\\u2709', label: 'Gmail' },
    drive:    { icon: '\\uD83D\\uDCC1', label: 'Drive' },
    docs:     { icon: '\\uD83D\\uDCC4', label: 'Docs' },
    sheets:   { icon: '\\uD83D\\uDCCA', label: 'Sheets' },
    slides:   { icon: '\\uD83C\\uDFA8', label: 'Slides' },
    calendar: { icon: '\\uD83D\\uDCC5', label: 'Calendar' },
    forms:    { icon: '\\uD83D\\uDCDD', label: 'Forms' },
    chat:     { icon: '\\uD83D\\uDCAC', label: 'Chat' },
    photos:   { icon: '\\uD83D\\uDCF7', label: 'Photos' },
    people:   { icon: '\\uD83D\\uDC64', label: 'People' },
    tasks:    { icon: '\\u2705', label: 'Tasks' },
    unknown:  { icon: '\\u2699', label: 'System' }
  };

  let activeFilter = 'all';

  function render(data) {
    const tools = Array.isArray(data) ? data : (data.tools || []);

    if (!tools.length) {
      document.getElementById('groups-container').innerHTML =
        '<div class="empty">No tool data available.</div>';
      return;
    }

    // Counts
    const enabled = tools.filter(t => t.enabled && !t.sessionDisabled).length;
    const globallyDisabled = tools.filter(t => !t.enabled).length;
    const sessionDisabled = tools.filter(t => t.sessionDisabled && t.enabled).length;

    // Stats chips
    let stats = '<div class="stat-chip"><strong>' + tools.length + '</strong> total</div>';
    stats += '<div class="stat-chip"><span class="dot-sm" style="background:var(--green)"></span><strong>' + enabled + '</strong> enabled</div>';
    if (sessionDisabled > 0)
      stats += '<div class="stat-chip"><span class="dot-sm" style="background:var(--orange)"></span><strong>' + sessionDisabled + '</strong> session-disabled</div>';
    if (globallyDisabled > 0)
      stats += '<div class="stat-chip"><span class="dot-sm" style="background:var(--gray)"></span><strong>' + globallyDisabled + '</strong> globally-disabled</div>';
    document.getElementById('stats').innerHTML = stats;

    // Group by service
    const groups = {};
    tools.forEach(t => {
      const svc = t.service || 'unknown';
      if (!groups[svc]) groups[svc] = [];
      groups[svc].push(t);
    });

    // Sort: services with enabled tools first, then alphabetical
    const sortedKeys = Object.keys(groups).sort((a, b) => {
      const aActive = groups[a].some(t => t.enabled && !t.sessionDisabled);
      const bActive = groups[b].some(t => t.enabled && !t.sessionDisabled);
      if (aActive !== bActive) return bActive - aActive;
      return a.localeCompare(b);
    });

    // Filter chips
    let chips = '<span class="filter-label">Filter</span>';
    chips += '<div class="chip' + (activeFilter === 'all' ? ' active' : '') +
      '" data-svc="all"><span class="svc-icon">\\u2B50</span>All<span class="chip-count">' +
      tools.length + '</span></div>';
    sortedKeys.forEach(svc => {
      const meta = SERVICE_META[svc] || SERVICE_META.unknown;
      const count = groups[svc].length;
      const activeCount = groups[svc].filter(t => t.enabled && !t.sessionDisabled).length;
      chips += '<div class="chip' + (activeFilter === svc ? ' active' : '') +
        '" data-svc="' + svc + '"><span class="svc-icon">' + meta.icon + '</span>' +
        meta.label + '<span class="chip-count">' + activeCount + '/' + count + '</span></div>';
    });
    const filtersEl = document.getElementById('filters');
    filtersEl.innerHTML = chips;

    // Chip click handlers
    filtersEl.querySelectorAll('.chip').forEach(el => {
      el.addEventListener('click', () => {
        activeFilter = el.dataset.svc;
        render(data);
      });
    });

    // Render groups
    const container = document.getElementById('groups-container');
    const visibleKeys = activeFilter === 'all' ? sortedKeys : sortedKeys.filter(k => k === activeFilter);

    container.innerHTML = visibleKeys.map(svc => {
      const meta = SERVICE_META[svc] || SERVICE_META.unknown;
      const svcTools = groups[svc];
      const svcEnabled = svcTools.filter(t => t.enabled && !t.sessionDisabled).length;
      const svcSession = svcTools.filter(t => t.sessionDisabled && t.enabled).length;

      let statusHTML = '<span style="color:var(--green)">' + svcEnabled + ' on</span>';
      if (svcSession > 0) statusHTML += '<span style="color:var(--orange)">' + svcSession + ' session-off</span>';

      const cards = svcTools.map(t => {
        let dotCls, cardCls;
        if (t.sessionDisabled && t.enabled) {
          dotCls = 'session-disabled'; cardCls = 'session-disabled';
        } else if (!t.enabled) {
          dotCls = 'globally-disabled'; cardCls = 'globally-disabled';
        } else {
          dotCls = 'enabled'; cardCls = 'active-tool';
        }

        let badges = '';
        if (t.isProtected) badges += '<span class="tbadge protected">protected</span>';
        if (t.sessionDisabled) badges += '<span class="tbadge session-only">session-disabled</span>';

        const desc = t.description
          ? '<div class="tool-desc">' + t.description.replace(/</g, '&lt;') + '</div>'
          : '';

        return '<div class="tool-card ' + cardCls + '">' +
          '<div class="dot ' + dotCls + '"></div>' +
          '<div class="tool-info"><div class="tool-name">' + t.name.replace(/</g, '&lt;') + '</div>' +
          desc +
          (badges ? '<div class="tool-badges">' + badges + '</div>' : '') +
          '</div></div>';
      }).join('');

      return '<div class="service-group">' +
        '<div class="group-header">' +
        '<span class="group-icon">' + meta.icon + '</span>' +
        '<span class="group-name">' + meta.label + '</span>' +
        '<span class="group-count">' + svcTools.length + ' tools</span>' +
        '<div class="group-status">' + statusHTML + '</div>' +
        '</div>' +
        '<div class="tool-grid">' + cards + '</div>' +
        '</div>';
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
        app=AppConfig(prefers_border=True),
    )
    def manage_tools_dashboard() -> str:
        return _build_manage_tools_html(_collect_tools_json(mcp))

    @mcp.resource(
        "ui://data-dashboard/{tool_name}",
        name="data_dashboard",
        title="Data Dashboard",
        description="Generic data dashboard for list tool results",
        tags={"ui", "dashboard", "data"},
        app=AppConfig(prefers_border=True),
    )
    def data_dashboard(tool_name: str) -> str:
        """Serve a data dashboard populated from the middleware cache.

        :class:`~middleware.dashboard_cache_middleware.DashboardCacheMiddleware`
        intercepts list-tool calls and stores the last result.  This resource
        reads from that cache so the HTML is pre-populated with live data.
        """
        from middleware.dashboard_cache_middleware import get_cached_result

        cached = get_cached_result(tool_name) or {}
        config = get_data_dashboard_config(tool_name)
        payload = json.dumps({"data": cached, "config": config})
        return _build_data_dashboard_html(payload)
# ---------------------------------------------------------------------------
# Generic Data Dashboard — shared template for all list-tool UIs
# ---------------------------------------------------------------------------

_DATA_PLACEHOLDER = "/*__DASHBOARD_DATA__*/"

# Per-tool configuration: tells the generic JS which fields to display and how.
# Keys: items_field, title, icon, columns (list of {key, label, type}).
# Column types: "primary", "text", "timestamp", "link", "numeric", "badge",
#               "color", "nested", "boolean".
# If a tool isn't listed here the JS will auto-detect columns from the data.
_DASHBOARD_CONFIGS: dict = {
    "list_gmail_labels": {
        "itemsField": "labels",
        "title": "Gmail Labels",
        "icon": "\u2709",
        "columns": [
            {"key": "name", "label": "Label", "type": "primary"},
            {"key": "type", "label": "Type", "type": "badge"},
            {"key": "messagesTotal", "label": "Messages", "type": "numeric"},
            {"key": "messagesUnread", "label": "Unread", "type": "numeric"},
            {"key": "threadsTotal", "label": "Threads", "type": "numeric"},
            {"key": "color", "label": "Color", "type": "color"},
        ],
    },
    "list_gmail_filters": {
        "itemsField": "filters",
        "title": "Gmail Filters",
        "icon": "\u2709",
        "columns": [
            {"key": "id", "label": "Filter ID", "type": "primary"},
            {"key": "criteria", "label": "Criteria", "type": "nested"},
            {"key": "action", "label": "Actions", "type": "nested"},
        ],
    },
    "list_spaces": {
        "itemsField": "spaces",
        "title": "Chat Spaces",
        "icon": "\U0001f4ac",
        "columns": [
            {"key": "displayName", "label": "Name", "type": "primary"},
            {"key": "spaceType", "label": "Type", "type": "badge"},
            {"key": "id", "label": "ID", "type": "text"},
            {"key": "threaded", "label": "Threaded", "type": "boolean"},
        ],
    },
    "list_messages": {
        "itemsField": "messages",
        "title": "Chat Messages",
        "icon": "\U0001f4ac",
        "columns": [
            {"key": "senderName", "label": "Sender", "type": "primary"},
            {"key": "text", "label": "Message", "type": "text"},
            {"key": "createTime", "label": "Time", "type": "timestamp"},
            {"key": "threadId", "label": "Thread", "type": "text"},
        ],
    },
    "list_calendars": {
        "itemsField": "calendars",
        "title": "Calendars",
        "icon": "\U0001f4c5",
        "columns": [
            {"key": "summary", "label": "Calendar", "type": "primary"},
            {"key": "description", "label": "Description", "type": "text"},
            {"key": "primary", "label": "Primary", "type": "boolean"},
            {"key": "timeZone", "label": "Timezone", "type": "text"},
            {"key": "backgroundColor", "label": "Color", "type": "color"},
        ],
    },
    "list_events": {
        "itemsField": "events",
        "title": "Calendar Events",
        "icon": "\U0001f4c5",
        "columns": [
            {"key": "summary", "label": "Event", "type": "primary"},
            {"key": "start", "label": "Start", "type": "timestamp"},
            {"key": "end", "label": "End", "type": "timestamp"},
            {"key": "location", "label": "Location", "type": "text"},
            {"key": "status", "label": "Status", "type": "badge"},
            {"key": "htmlLink", "label": "Link", "type": "link"},
        ],
    },
    "list_drive_items": {
        "itemsField": "items",
        "title": "Drive Files",
        "icon": "\U0001f4c1",
        "columns": [
            {"key": "name", "label": "Name", "type": "primary"},
            {"key": "mimeType", "label": "Type", "type": "badge"},
            {"key": "modifiedTime", "label": "Modified", "type": "timestamp"},
            {"key": "size", "label": "Size", "type": "numeric"},
            {"key": "webViewLink", "label": "Link", "type": "link"},
        ],
    },
    "list_docs_in_folder": {
        "itemsField": "docs",
        "title": "Documents",
        "icon": "\U0001f4c4",
        "columns": [
            {"key": "name", "label": "Document", "type": "primary"},
            {"key": "modifiedTime", "label": "Modified", "type": "timestamp"},
            {"key": "webViewLink", "label": "Link", "type": "link"},
        ],
    },
    "list_spreadsheets": {
        "itemsField": "items",
        "title": "Spreadsheets",
        "icon": "\U0001f4ca",
        "columns": [
            {"key": "name", "label": "Spreadsheet", "type": "primary"},
            {"key": "modifiedTime", "label": "Modified", "type": "timestamp"},
            {"key": "webViewLink", "label": "Link", "type": "link"},
        ],
    },
    "list_photos_albums": {
        "itemsField": "albums",
        "title": "Photo Albums",
        "icon": "\U0001f4f7",
        "columns": [
            {"key": "title", "label": "Album", "type": "primary"},
            {"key": "mediaItemsCount", "label": "Photos", "type": "numeric"},
            {"key": "productUrl", "label": "Link", "type": "link"},
        ],
    },
    "list_form_responses": {
        "itemsField": "responses",
        "title": "Form Responses",
        "icon": "\U0001f4dd",
        "columns": [
            {"key": "responseId", "label": "Response ID", "type": "primary"},
            {"key": "respondentEmail", "label": "Email", "type": "text"},
            {"key": "submittedTime", "label": "Submitted", "type": "timestamp"},
            {"key": "answers", "label": "Answers", "type": "nested"},
        ],
    },
    "list_people_contact_labels": {
        "itemsField": "labels",
        "title": "Contact Labels",
        "icon": "\U0001f464",
        "columns": [
            {"key": "name", "label": "Label", "type": "primary"},
            {"key": "memberCount", "label": "Members", "type": "numeric"},
            {"key": "groupType", "label": "Type", "type": "badge"},
        ],
    },
}


def _build_data_dashboard_html(data_json: str = "{}") -> str:
    """Return a generic data dashboard HTML SPA.

    The template is fully data-driven: the JS reads a config object that
    describes columns and an items array extracted from the tool response.
    It reuses the same Tokyonight design language as the manage-tools dashboard.
    """
    html = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Data Dashboard</title>
<style>
  :root {
    --bg: #1a1b26; --surface: #24283b; --surface2: #292e42; --border: #414868;
    --text: #c0caf5; --text-dim: #565f89; --accent: #7aa2f7;
    --green: #9ece6a; --gray: #565f89; --orange: #ff9e64; --red: #f7768e;
    --purple: #bb9af7; --cyan: #7dcfff; --teal: #73daca;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, monospace;
    background: var(--bg); color: var(--text); padding: 1.5rem;
  }
  header {
    display: flex; align-items: center; gap: 0.75rem;
    margin-bottom: 1.25rem; flex-wrap: wrap;
  }
  header .h-icon { font-size: 1.3rem; }
  header h1 { font-size: 1.2rem; font-weight: 600; }
  .header-badge {
    font-size: 0.65rem; padding: 0.2rem 0.55rem; border-radius: 999px;
    background: var(--border); color: var(--text-dim); font-weight: 500;
  }

  /* Stats */
  .stats-bar {
    display: flex; gap: 0.5rem; margin-bottom: 1.25rem; flex-wrap: wrap;
  }
  .stat-chip {
    font-size: 0.75rem; padding: 0.3rem 0.7rem; border-radius: 6px;
    background: var(--surface); border: 1px solid var(--border);
    color: var(--text-dim); display: flex; align-items: center; gap: 0.35rem;
  }
  .stat-chip strong { font-weight: 600; color: var(--text); }

  /* Search */
  .search-bar {
    margin-bottom: 1rem;
  }
  .search-bar input {
    width: 100%; max-width: 360px; padding: 0.45rem 0.75rem;
    border-radius: 6px; border: 1px solid var(--border);
    background: var(--surface); color: var(--text);
    font-family: inherit; font-size: 0.8rem; outline: none;
    transition: border-color 0.15s;
  }
  .search-bar input:focus { border-color: var(--accent); }
  .search-bar input::placeholder { color: var(--text-dim); }

  /* Table */
  .data-table {
    width: 100%; border-collapse: collapse;
    font-size: 0.8rem;
  }
  .data-table th {
    text-align: left; padding: 0.55rem 0.75rem;
    font-size: 0.7rem; text-transform: uppercase;
    letter-spacing: 0.04em; color: var(--text-dim);
    border-bottom: 1px solid var(--border);
    font-weight: 600; cursor: pointer;
    user-select: none; white-space: nowrap;
  }
  .data-table th:hover { color: var(--accent); }
  .data-table th .sort-arrow { font-size: 0.6rem; margin-left: 0.25rem; opacity: 0.4; }
  .data-table th.sorted .sort-arrow { opacity: 1; color: var(--accent); }
  .data-table td {
    padding: 0.5rem 0.75rem;
    border-bottom: 1px solid rgba(65,72,104,0.3);
    max-width: 300px; overflow: hidden;
    text-overflow: ellipsis; white-space: nowrap;
    vertical-align: top;
  }
  .data-table tr:hover td { background: var(--surface2); }

  /* Cell types */
  .cell-primary { font-weight: 600; color: var(--text); }
  .cell-badge {
    display: inline-block; font-size: 0.65rem; padding: 0.1rem 0.45rem;
    border-radius: 4px; background: rgba(122, 162, 247, 0.1);
    color: var(--accent); font-weight: 500;
  }
  .cell-link {
    color: var(--cyan); text-decoration: none; font-size: 0.7rem;
  }
  .cell-link:hover { text-decoration: underline; }
  .cell-timestamp { color: var(--teal); font-size: 0.75rem; }
  .cell-numeric { font-variant-numeric: tabular-nums; color: var(--purple); }
  .cell-bool-true { color: var(--green); }
  .cell-bool-false { color: var(--gray); }
  .cell-nested {
    font-size: 0.65rem; color: var(--text-dim);
    max-width: 250px; cursor: pointer;
  }
  .cell-nested:hover { color: var(--text); }
  .cell-color {
    display: inline-block; width: 14px; height: 14px;
    border-radius: 3px; border: 1px solid var(--border);
    vertical-align: middle;
  }

  /* Card view (small screens) */
  .card-grid {
    display: none;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 0.6rem;
  }
  .data-card {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 8px; padding: 0.75rem 0.85rem;
    transition: all 0.15s;
  }
  .data-card:hover {
    border-color: var(--accent); background: var(--surface2);
    transform: translateY(-1px);
  }
  .data-card .card-primary {
    font-size: 0.85rem; font-weight: 600; margin-bottom: 0.35rem;
  }
  .data-card .card-field {
    font-size: 0.7rem; color: var(--text-dim);
    margin-bottom: 0.15rem; display: flex; gap: 0.35rem;
  }
  .data-card .card-field .field-label {
    color: var(--text-dim); min-width: 65px; flex-shrink: 0;
  }
  .data-card .card-field .field-value {
    color: var(--text); overflow: hidden;
    text-overflow: ellipsis; white-space: nowrap;
  }

  /* View toggle */
  .view-toggle {
    display: flex; gap: 0.25rem; margin-left: auto;
  }
  .view-btn {
    font-size: 0.7rem; padding: 0.2rem 0.5rem; border-radius: 4px;
    border: 1px solid var(--border); background: var(--surface);
    color: var(--text-dim); cursor: pointer; transition: all 0.15s;
  }
  .view-btn:hover { border-color: var(--accent); }
  .view-btn.active {
    background: rgba(122, 162, 247, 0.15); border-color: var(--accent);
    color: var(--accent);
  }

  .empty {
    text-align: center; padding: 3rem;
    color: var(--text-dim); font-size: 0.85rem;
  }

  @media (max-width: 640px) {
    .table-wrap { display: none; }
    .card-grid { display: grid; }
  }
</style>
</head>
<body>
<header>
  <span class="h-icon" id="h-icon"></span>
  <h1 id="h-title">Data Dashboard</h1>
  <span class="header-badge" id="h-count"></span>
  <div class="view-toggle">
    <button class="view-btn active" data-view="table">Table</button>
    <button class="view-btn" data-view="cards">Cards</button>
  </div>
</header>
<div class="stats-bar" id="stats"></div>
<div class="search-bar"><input type="text" id="search" placeholder="Filter items..."></div>
<div class="table-wrap"><table class="data-table"><thead id="thead"></thead><tbody id="tbody"></tbody></table></div>
<div class="card-grid" id="cards"></div>
<script>
  var __DATA__ = /*__DASHBOARD_DATA__*/;
  var DATA = __DATA__.data || {};
  var CFG = __DATA__.config || {};

  // --- Helpers ---
  function esc(s) { return s == null ? '' : String(s).replace(/</g, '&lt;').replace(/>/g, '&gt;'); }

  function fmtTimestamp(v) {
    if (!v) return '';
    try {
      var d = new Date(v);
      if (isNaN(d)) return esc(v);
      return d.toLocaleDateString(undefined, {month:'short',day:'numeric',year:'numeric'}) +
             ' ' + d.toLocaleTimeString(undefined, {hour:'2-digit',minute:'2-digit'});
    } catch(e) { return esc(v); }
  }

  function fmtNested(v) {
    if (v == null) return '';
    if (Array.isArray(v)) return esc(v.length + ' items');
    if (typeof v === 'object') {
      var parts = [];
      for (var k in v) {
        if (v[k] != null && v[k] !== '' && v[k] !== false)
          parts.push(k + ': ' + (typeof v[k] === 'object' ? JSON.stringify(v[k]) : v[k]));
      }
      return esc(parts.join(', ').substring(0, 120));
    }
    return esc(v);
  }

  function renderCell(val, col) {
    var t = col.type || 'text';
    if (val == null || val === '') return '<span style="color:var(--gray)">—</span>';
    switch(t) {
      case 'primary': return '<span class="cell-primary">' + esc(val) + '</span>';
      case 'badge': return '<span class="cell-badge">' + esc(val) + '</span>';
      case 'link':
        var url = String(val);
        return '<a class="cell-link" href="' + esc(url) + '" target="_blank" rel="noopener">Open</a>';
      case 'timestamp': return '<span class="cell-timestamp">' + fmtTimestamp(val) + '</span>';
      case 'numeric':
        var n = val;
        if (typeof n === 'string') n = parseInt(n, 10);
        return '<span class="cell-numeric">' + (isNaN(n) ? esc(val) : n.toLocaleString()) + '</span>';
      case 'boolean':
        return val ? '<span class="cell-bool-true">\\u2713</span>' : '<span class="cell-bool-false">\\u2717</span>';
      case 'color':
        var c = val;
        if (typeof c === 'object') c = c.backgroundColor || c.textColor || '#888';
        return '<span class="cell-color" style="background:' + esc(c) + '"></span>';
      case 'nested': return '<span class="cell-nested" title="' + esc(JSON.stringify(val)) + '">' + fmtNested(val) + '</span>';
      default: return '<span>' + esc(String(val).substring(0, 120)) + '</span>';
    }
  }

  // --- Extract items from response ---
  function findItems(data, cfg) {
    if (cfg.itemsField && data[cfg.itemsField]) return data[cfg.itemsField];
    // Auto-detect: find first array field
    for (var k in data) {
      if (Array.isArray(data[k]) && data[k].length > 0 && typeof data[k][0] === 'object')
        return data[k];
    }
    // If data itself is an array
    if (Array.isArray(data)) return data;
    return [];
  }

  // --- Auto-detect columns if not configured ---
  function detectColumns(items) {
    if (!items.length) return [];
    var sample = items[0];
    var primaryNames = ['name','displayName','summary','title','text','label'];
    var timeNames = ['modifiedTime','createTime','submittedTime','start','end','createdTime','updatedTime'];
    var linkNames = ['webViewLink','htmlLink','productUrl','url','link'];
    var cols = [];
    for (var k in sample) {
      if (k === 'id' || k === 'resourceName') continue; // skip raw IDs
      var v = sample[k];
      var type = 'text';
      if (primaryNames.indexOf(k) >= 0) type = 'primary';
      else if (timeNames.indexOf(k) >= 0) type = 'timestamp';
      else if (linkNames.indexOf(k) >= 0) type = 'link';
      else if (typeof v === 'boolean') type = 'boolean';
      else if (typeof v === 'number') type = 'numeric';
      else if (typeof v === 'object' && v !== null) type = 'nested';
      cols.push({key: k, label: k.replace(/([A-Z])/g, ' $1').replace(/^./, function(s){return s.toUpperCase();}), type: type});
      if (cols.length >= 8) break; // cap at 8 columns
    }
    return cols;
  }

  // --- Sort state ---
  var sortCol = null, sortAsc = true;

  function sortItems(items, col) {
    if (!col) return items;
    var copy = items.slice();
    copy.sort(function(a, b) {
      var va = a[col.key], vb = b[col.key];
      if (va == null) return 1; if (vb == null) return -1;
      if (col.type === 'numeric') {
        va = typeof va === 'string' ? parseFloat(va) : va;
        vb = typeof vb === 'string' ? parseFloat(vb) : vb;
        return sortAsc ? va - vb : vb - va;
      }
      va = String(va).toLowerCase(); vb = String(vb).toLowerCase();
      return sortAsc ? va.localeCompare(vb) : vb.localeCompare(va);
    });
    return copy;
  }

  // --- Render ---
  var currentView = 'table';
  var allItems = findItems(DATA, CFG);
  var columns = (CFG.columns && CFG.columns.length) ? CFG.columns : detectColumns(allItems);

  function render(filter) {
    var items = allItems;
    if (filter) {
      var q = filter.toLowerCase();
      items = items.filter(function(item) {
        return columns.some(function(c) {
          var v = item[c.key];
          return v != null && String(v).toLowerCase().indexOf(q) >= 0;
        });
      });
    }
    items = sortItems(items, sortCol);

    // Header
    document.getElementById('h-icon').textContent = CFG.icon || '\\u2699';
    document.getElementById('h-title').textContent = CFG.title || 'Data Dashboard';
    document.getElementById('h-count').textContent = items.length + ' / ' + allItems.length + ' items';

    // Stats
    var envelope = [];
    var skipKeys = [CFG.itemsField || '', 'error', 'jinjaTemplateApplied', 'jinjaTemplateError'];
    for (var k in DATA) {
      if (skipKeys.indexOf(k) >= 0) continue;
      var v = DATA[k];
      if (v == null || typeof v === 'object') continue;
      envelope.push('<div class="stat-chip"><strong>' + esc(String(v)) + '</strong> ' + esc(k) + '</div>');
    }
    document.getElementById('stats').innerHTML = envelope.join('');

    // Table
    var thead = '<tr>' + columns.map(function(c) {
      var cls = sortCol && sortCol.key === c.key ? ' sorted' : '';
      var arrow = sortCol && sortCol.key === c.key ? (sortAsc ? '\\u25B2' : '\\u25BC') : '\\u25B4';
      return '<th class="' + cls + '" data-key="' + c.key + '">' + esc(c.label) +
             '<span class="sort-arrow">' + arrow + '</span></th>';
    }).join('') + '</tr>';
    document.getElementById('thead').innerHTML = thead;

    var tbody = items.map(function(item) {
      return '<tr>' + columns.map(function(c) {
        return '<td>' + renderCell(item[c.key], c) + '</td>';
      }).join('') + '</tr>';
    }).join('');
    document.getElementById('tbody').innerHTML = tbody || '<tr><td colspan="' + columns.length + '" class="empty">No items match filter</td></tr>';

    // Cards
    var cards = items.map(function(item) {
      var primaryCol = columns.find(function(c) { return c.type === 'primary'; });
      var primaryVal = primaryCol ? (item[primaryCol.key] || '') : '';
      var fields = columns.filter(function(c) { return c.type !== 'primary'; }).map(function(c) {
        return '<div class="card-field"><span class="field-label">' + esc(c.label) + '</span>' +
               '<span class="field-value">' + renderCell(item[c.key], c) + '</span></div>';
      }).join('');
      return '<div class="data-card"><div class="card-primary">' + esc(primaryVal) + '</div>' + fields + '</div>';
    }).join('');
    document.getElementById('cards').innerHTML = cards || '<div class="empty">No items match filter</div>';

    // Sort click handlers
    document.querySelectorAll('#thead th').forEach(function(th) {
      th.onclick = function() {
        var key = th.dataset.key;
        var col = columns.find(function(c) { return c.key === key; });
        if (sortCol && sortCol.key === key) { sortAsc = !sortAsc; }
        else { sortCol = col; sortAsc = true; }
        render(document.getElementById('search').value);
      };
    });
  }

  // View toggle
  document.querySelectorAll('.view-btn').forEach(function(btn) {
    btn.addEventListener('click', function() {
      currentView = btn.dataset.view;
      document.querySelectorAll('.view-btn').forEach(function(b) { b.classList.remove('active'); });
      btn.classList.add('active');
      document.querySelector('.table-wrap').style.display = currentView === 'table' ? '' : 'none';
      document.querySelector('.card-grid').style.display = currentView === 'cards' ? 'grid' : 'none';
    });
  });

  // Search
  document.getElementById('search').addEventListener('input', function(e) {
    render(e.target.value);
  });

  render('');
</script>
</body>
</html>"""
    return html.replace(_DATA_PLACEHOLDER, data_json)


def get_data_dashboard_config(tool_name: str) -> dict:
    """Return the dashboard config for a given tool, or empty dict for auto-detect."""
    return _DASHBOARD_CONFIGS.get(tool_name, {})


def build_data_dashboard_for_tool(tool_name: str, tool_result: dict) -> str:
    """Build a data dashboard HTML string for any list tool's result.

    Args:
        tool_name: The tool that produced the data (e.g. ``"list_gmail_labels"``).
        tool_result: The dict/JSON-serializable result from the tool.

    Returns:
        Complete HTML string ready to serve as a ``ui://`` resource.
    """
    config = get_data_dashboard_config(tool_name)
    payload = json.dumps({"data": tool_result, "config": config})
    return _build_data_dashboard_html(payload)


def wire_dashboard_to_list_tools(mcp: FastMCP) -> int:
    """Patch ``meta["ui"]`` on every known list tool and register cache watchers.

    This must be called **after** all service tools have been registered.
    It does two things:

    1. Iterates :data:`_DASHBOARD_CONFIGS` and patches each tool's
       ``meta["ui"]["resourceUri"]`` to ``"ui://data-dashboard/{tool_name}"``.
    2. Registers those tool names with
       :func:`~middleware.dashboard_cache_middleware.register_watched_tools`
       so the cache middleware knows which tool calls to intercept.

    Returns:
        Number of tools patched.
    """
    from fastmcp.server.apps import app_config_to_meta_dict

    from middleware.dashboard_cache_middleware import register_watched_tools

    patched = 0
    lp = mcp.local_provider
    for key, component in lp._components.items():
        if not key.startswith("tool:"):
            continue
        tool_name = component.name
        if tool_name not in _DASHBOARD_CONFIGS:
            continue
        component.meta = component.meta or {}
        component.meta["ui"] = app_config_to_meta_dict(
            AppConfig(resource_uri=f"ui://data-dashboard/{tool_name}")
        )
        patched += 1

    # Tell the cache middleware which tools to watch
    register_watched_tools(set(_DASHBOARD_CONFIGS.keys()))

    return patched
