"""
Gmail UI tools for FastMCP - MCP Apps (SEP-1865) compliant implementation.

This module provides UI-enhanced Gmail tools following the MCP Apps pattern:
- UI Resources registered with ui:// scheme
- Tools with _meta pointing to UI resources
- structuredContent passed to UI for rendering
"""

from fastmcp import FastMCP
from fastmcp.resources import ResourceContent
from fastmcp.tools.tool import ToolResult
from pydantic import Field
from typing_extensions import Annotated, Optional

from config.enhanced_logging import setup_logger
from tools.common_types import UserGoogleEmail

from .messages import search_gmail_messages

logger = setup_logger()

# Simple test HTML to verify MCPJam can render anything
SIMPLE_TEST_HTML = """<!DOCTYPE html>
<html>
<head><title>Test</title></head>
<body style="font-family: sans-serif; padding: 20px;">
  <h1>MCP App Working!</h1>
  <p>If you see this, the HTML is rendering correctly.</p>
</body>
</html>"""

# HTML template for the MCP Apps UI resource
# This is a self-contained HTML app that receives data via MCP Apps protocol
GMAIL_SEARCH_UI_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Gmail Search Results</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      font-size: 14px; line-height: 1.5; color: #202124; background: #fff; padding: 16px;
    }
    .loading { text-align: center; padding: 48px; color: #5f6368; }
    .email-card {
      border: 1px solid #dadce0; border-radius: 8px; margin-bottom: 12px;
      overflow: hidden; transition: box-shadow 0.2s;
    }
    .email-card:hover { box-shadow: 0 1px 3px rgba(60,64,67,0.3); }
    .email-header { padding: 12px 16px; background: #f8f9fa; border-bottom: 1px solid #dadce0; }
    .email-subject { font-size: 16px; font-weight: 500; color: #202124; margin-bottom: 4px; }
    .email-meta { display: flex; flex-wrap: wrap; gap: 12px; font-size: 12px; color: #5f6368; }
    .email-snippet { padding: 12px 16px; color: #5f6368; font-size: 13px; }
    .email-actions { padding: 8px 16px; background: #f8f9fa; border-top: 1px solid #dadce0; }
    .btn {
      display: inline-flex; align-items: center; padding: 8px 16px; border-radius: 4px;
      font-size: 13px; font-weight: 500; text-decoration: none; background: #fff;
      color: #1a73e8; border: 1px solid #dadce0;
    }
    .btn:hover { background: #f8f9fa; }
    .search-header { padding: 12px 0; border-bottom: 1px solid #dadce0; margin-bottom: 16px; }
    .result-count { font-size: 18px; font-weight: 500; }
    .search-query { font-size: 12px; color: #5f6368; margin-top: 4px; }
    .label {
      display: inline-block; padding: 2px 8px; border-radius: 4px;
      font-size: 11px; font-weight: 500; background: #e8f0fe; color: #1967d2; margin-right: 4px;
    }
    .empty-state { text-align: center; padding: 48px 16px; color: #5f6368; }
  </style>
</head>
<body>
  <div id="app">
    <div class="loading">Loading Gmail search results...</div>
  </div>
  <script>
    // MCP Apps UI - Gmail Search Results
    // Implements SEP-1865 MCP Apps lifecycle

    let nextId = 1;
    let hostContext = null;
    let initialized = false;

    function escapeHtml(text) {
      if (!text) return '';
      const div = document.createElement('div');
      div.textContent = text;
      return div.innerHTML;
    }

    function renderResults(data) {
      const app = document.getElementById('app');
      if (!data || !data.success) {
        app.innerHTML = '<div class="empty-state">Error loading results</div>';
        return;
      }

      const messages = data.messages || [];
      const query = data.query || '';
      const total = data.total_found || 0;
      const userEmail = data.userEmail || '';

      if (messages.length === 0) {
        app.innerHTML = `
          <div class="search-header">
            <div class="result-count">No results found</div>
            <div class="search-query">Query: ${escapeHtml(query)}</div>
          </div>
          <div class="empty-state">No emails match your search criteria.</div>
        `;
        return;
      }

      let html = `
        <div class="search-header">
          <div class="result-count">${total} result${total !== 1 ? 's' : ''}</div>
          <div class="search-query">Query: ${escapeHtml(query)} • Account: ${escapeHtml(userEmail)}</div>
        </div>
      `;

      messages.forEach(msg => {
        const labels = (msg.label_names || []).slice(0, 3).map(l =>
          `<span class="label">${escapeHtml(l)}</span>`
        ).join('');

        html += `
          <div class="email-card">
            <div class="email-header">
              <div class="email-subject">${escapeHtml(msg.subject || '(no subject)')}</div>
              <div class="email-meta">
                <span><strong>From:</strong> ${escapeHtml(msg.sender || '(unknown)')}</span>
                <span><strong>Date:</strong> ${escapeHtml(msg.date || '')}</span>
              </div>
              ${labels ? '<div style="margin-top: 8px;">' + labels + '</div>' : ''}
            </div>
            <div class="email-snippet">${escapeHtml(msg.snippet || '')}</div>
            <div class="email-actions">
              <a href="${escapeHtml(msg.web_url || '#')}" target="_blank" rel="noopener" class="btn">Open in Gmail</a>
            </div>
          </div>
        `;
      });

      app.innerHTML = html;
    }

    // JSON-RPC 2.0 request helper
    function sendRequest(method, params) {
      const id = nextId++;
      window.parent.postMessage({ jsonrpc: '2.0', id, method, params }, '*');
      return new Promise((resolve, reject) => {
        const listener = (event) => {
          if (event.data?.id === id) {
            window.removeEventListener('message', listener);
            if (event.data?.result !== undefined) {
              resolve(event.data.result);
            } else if (event.data?.error) {
              reject(new Error(event.data.error.message || 'Unknown error'));
            }
          }
        };
        window.addEventListener('message', listener);
        // Timeout after 10 seconds
        setTimeout(() => {
          window.removeEventListener('message', listener);
          reject(new Error('Request timeout'));
        }, 10000);
      });
    }

    // JSON-RPC 2.0 notification helper
    function sendNotification(method, params) {
      window.parent.postMessage({ jsonrpc: '2.0', method, params }, '*');
    }

    // Handle incoming messages
    window.addEventListener('message', (event) => {
      const data = event.data;
      if (!data || !data.jsonrpc) return;

      // Handle JSON-RPC 2.0 responses (handled by sendRequest promises)
      if (data.id !== undefined) return;

      // Handle notifications
      if (data.method) {
        // Tool result notification
        if (data.method === 'ui/notifications/tool-result') {
          const params = data.params || {};
          renderResults(params.structuredContent || params);
        }
        // Host context update
        else if (data.method === 'ui/notifications/context-changed') {
          hostContext = data.params;
        }
      }
    });

    // Initialize MCP Apps lifecycle
    async function initializeMcpApp() {
      try {
        // Send ui/initialize request per SEP-1865 spec
        const result = await sendRequest('ui/initialize', {
          capabilities: {},
          clientInfo: { name: 'Gmail Search UI', version: '1.0.0' },
          protocolVersion: '2025-06-18'
        });

        hostContext = result.hostContext || {};
        initialized = true;

        // Send initialized notification
        sendNotification('ui/notifications/initialized', {});

        // Check if tool result is in hostContext (initial render)
        if (hostContext.toolInfo?.tool?.structuredContent) {
          renderResults(hostContext.toolInfo.tool.structuredContent);
        }
        // Also check for structuredContent directly in result
        if (result.structuredContent) {
          renderResults(result.structuredContent);
        }
      } catch (err) {
        console.log('MCP Apps init failed:', err.message);
        // Show fallback message
        document.getElementById('app').innerHTML =
          '<div class="empty-state">Waiting for data from host...</div>';
      }
    }

    // Also handle raw postMessage data that doesn't follow JSON-RPC
    window.addEventListener('message', (event) => {
      const data = event.data;
      if (!data) return;

      // Skip JSON-RPC responses (handled elsewhere)
      if (data.jsonrpc === '2.0' && data.id !== undefined) return;

      // Handle any structuredContent we receive
      if (data.structuredContent) {
        renderResults(data.structuredContent);
        return;
      }

      // Handle tool result in various formats
      if (data.result?.structuredContent) {
        renderResults(data.result.structuredContent);
        return;
      }

      // Handle OpenAI/ChatGPT Apps format
      if (data.toolOutput?.structuredContent) {
        renderResults(data.toolOutput.structuredContent);
        return;
      }
    });

    // Start initialization when DOM is ready
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', initializeMcpApp);
    } else {
      initializeMcpApp();
    }
  </script>
</body>
</html>"""


def setup_gmail_ui_tools(mcp: FastMCP) -> None:
    """
    Register Gmail UI tools and resources following MCP Apps (SEP-1865) pattern.
    """
    logger.info("Setting up Gmail UI tools with MCP Apps pattern...")

    # MCP Apps resource URI (SEP-1865 standard)
    UI_RESOURCE_URI = "ui://gmail/search-results"
    # MIME type per SEP-1865: text/html;profile=mcp-app (RFC 6906 profile parameter)
    UI_MIME_TYPE = "text/html;profile=mcp-app"

    # UI resource metadata per SEP-1865 spec
    UI_RESOURCE_META = {
        "ui": {
            "csp": {
                # No external connections needed for this UI
                "connectDomains": [],
                "resourceDomains": [],
                "frameDomains": [],
                "baseUriDomains": [],
            },
            "prefersBorder": True,
        }
    }

    # Register UI Resource with ui:// scheme
    @mcp.resource(
        uri=UI_RESOURCE_URI,
        name="Gmail Search Results UI",
        description="Interactive HTML UI for displaying Gmail search results",
        mime_type=UI_MIME_TYPE,
    )
    def gmail_search_ui_resource() -> list[ResourceContent]:
        """Returns the HTML template for Gmail search results UI with _meta.ui config."""
        return [
            ResourceContent(
                GMAIL_SEARCH_UI_TEMPLATE,
                mime_type=UI_MIME_TYPE,
                meta=UI_RESOURCE_META,
            )
        ]

    # Register tool with meta pointing to UI resource (SEP-1865 requirement)
    # The meta field on tool definition tells hosts this tool has UI support
    # Use nested format: _meta.ui.resourceUri (flat "ui/resourceUri" is deprecated)
    @mcp.tool(
        name="search_gmail_ui",
        description="Search Gmail messages with interactive UI. Returns structured results that render in a visual interface showing email cards with subject, sender, date, and labels.",
        tags={"gmail", "ui", "search", "visualization"},
        annotations={
            "title": "Gmail Search with UI",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
        meta={"ui": {"resourceUri": UI_RESOURCE_URI}},
    )
    async def search_gmail_ui_tool(
        query: Annotated[
            str,
            Field(
                description="Gmail search query (e.g., 'from:sender@example.com', 'subject:important', 'is:unread')"
            ),
        ],
        user_google_email: UserGoogleEmail = None,
        page_size: Annotated[
            int,
            Field(description="Maximum number of messages to return", ge=1, le=50),
        ] = 10,
    ) -> ToolResult:
        """
        Search Gmail messages with UI visualization.

        Returns ToolResult with structured_content and meta for MCP Apps hosts
        to render using the ui://gmail/search-results resource.
        """
        # Get search results
        result = await search_gmail_messages(query, user_google_email, page_size)

        if not result.get("success"):
            error_data = {
                "success": False,
                "error": result.get("error", "Unknown error"),
            }
            return ToolResult(
                content=f"Error: {error_data['error']}",
                structured_content=error_data,
                meta={"ui": {"resourceUri": UI_RESOURCE_URI}},
            )

        messages = result.get("messages", [])
        total_found = result.get("total_found", 0)
        user_email = result.get("userEmail", "")

        # Generate text summary for LLM (content)
        text_summary = f"Found {total_found} message(s) for query: {query}\n\n"
        for msg in messages[:5]:
            text_summary += (
                f"- {msg.get('subject', '(no subject)')}\n"
                f"  From: {msg.get('sender', '(unknown)')} | {msg.get('date', '')}\n"
            )
        if len(messages) > 5:
            text_summary += f"\n... and {len(messages) - 5} more results"

        # structured_content for UI (hidden from LLM)
        structured_data = {
            "success": True,
            "query": query,
            "total_found": total_found,
            "messages": [dict(m) for m in messages],
            "userEmail": user_email,
            "page_size": page_size,
        }

        # Return MCP Apps compliant ToolResult
        return ToolResult(
            content=text_summary,
            structured_content=structured_data,
            meta={"ui": {"resourceUri": UI_RESOURCE_URI}},
        )

    logger.info("Gmail UI tools setup completed:")
    logger.info("  📦 Resource: ui://gmail/search-results")
    logger.info("  🔍 Tool: search_gmail_ui")
