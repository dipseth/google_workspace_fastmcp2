# 🔗 MCP Client Connection Guide

Complete guide for connecting RiversUnlimited Google Workspace MCP Server to various AI clients and development environments.

## 📋 Table of Contents

- [Overview](#overview)
- [Server Setup](#server-setup)
- [Client Connections](#client-connections)
  - [Claude Code CLI (HTTP & STDIO)](#claude-code-cli-http--stdio)
  - [Claude Desktop](#claude-desktop)
  - [Cursor IDE (STDIO)](#cursor-ide-stdio)
  - [VS Code with Roo Extension (Streamable HTTP)](#vs-code-with-roo-extension-streamable-http)
  - [VS Code/GitHub Copilot (HTTP)](#vs-codegithub-copilot-http)
  - [Claude.ai (Remote HTTP)](#claudeai-remote-http)
  - [HTTP Streamable Connections](#http-streamable-connections)
  - [Remote Access with Cloudflare Tunnel](#remote-access-with-cloudflare-tunnel)
- [Troubleshooting](#troubleshooting)
- [Advanced Configuration](#advanced-configuration)

## 🎯 Overview

RiversUnlimited Google Workspace MCP Server supports multiple connection methods to work with different AI clients and development environments. Choose the method that best fits your setup:

| Client | Connection Type | Best For |
|--------|----------------|----------|
| **Claude Code CLI** | HTTP/STDIO | Command-line AI interactions with flexible transport |
| **Claude Desktop** | Streamable HTTP | Native desktop app with proxy support |
| **Cursor IDE** | STDIO | Local development with full IDE integration |
| **VS Code + Roo** | Streamable HTTP | VS Code users with Roo extension |
| **VS Code/GitHub Copilot** | HTTP | VS Code with native MCP support |
| **Claude.ai** | Remote HTTP | Browser-based AI interactions |
| **Other MCP Clients** | HTTP Streamable | Generic MCP client compatibility |
| **Mobile/Remote** | Cloudflare Tunnel | Remote access from anywhere |

## 🛠️ Server Setup

Before connecting any client, ensure your server is properly set up:

1. **Clone and install dependencies:**
   ```bash
   git clone https://github.com/dipseth/google_workspace_fastmcp2.git
   cd google_workspace_fastmcp2
   uv sync
   ```

2. **Configure Google OAuth credentials:**
   - Visit [Google Cloud Console](https://console.cloud.google.com/)
   - Enable required APIs (Gmail, Drive, Docs, Sheets, etc.)
   - Create OAuth 2.0 credentials
   - Download `client_secrets.json` file

3. **Set up environment variables:**
   ```bash
   cp .env.example .env
   # Edit .env with your Google OAuth credentials path
   ```

## 🔌 Client Connections

### Claude Code CLI (HTTP & STDIO)

Claude Code CLI supports both HTTP and STDIO connections for maximum flexibility.

#### Option 1: HTTP Connection

**Perfect for when you want to start the server separately and connect via HTTP.**

1. **Start the server in HTTP mode:**
   ```bash
   uv run python server.py --transport http --port 8002
   ```

2. **Add the server via Claude Code CLI:**
   ```bash
   claude mcp add --transport http google_workspace https://localhost:8002/mcp
   ```

#### Option 2: STDIO Connection

**For direct local process management with automatic server startup.**

1. **Add a local STDIO server:**
   ```bash
   # Basic syntax
   claude mcp add <name> <command> [args...]
   
   # Real example: Add Google Workspace server
   claude mcp add google_workspace --env GOOGLE_CLIENT_SECRETS_FILE=/path/to/client_secrets.json \
     -- uv --directory /path/to/google_workspace_fastmcp2 run python server.py
   ```

#### Understanding the "--" Parameter

The `--` (double dash) separates Claude's CLI flags from the command and arguments passed to the MCP server:
- **Before `--`**: Options for Claude (like `--env`, `--scope`)
- **After `--`**: The actual command to run the MCP server

**Examples:**
- `claude mcp add myserver -- npx server` → runs `npx server`
- `claude mcp add myserver --env KEY=value -- python server.py --port 8080` → runs `python server.py --port 8080` with `KEY=value` in environment

This prevents conflicts between Claude's flags and the server's flags.

### Claude Desktop

For Claude Desktop app users with HTTPS proxy support:

```json
{
  "mcpServers": {
    "riversunlimited": {
      "command": "/Users/srivers/.local/bin/mcp-proxy",
      "args": [
        "--transport",
        "streamablehttp",
        "https://localhost:8002/mcp"
      ],
      "env": {
        "PYTHONHTTPSVERIFY": "0",
        "SSL_CERT_FILE": "/Users/srivers/Repositories/quick_pr/fastmcp2_drive_upload/localhost+2.pem",
        "SSL_KEY_FILE": "/Users/srivers/Repositories/quick_pr/fastmcp2_drive_upload/localhost+2-key.pem"
      }
    }
  }
}
```

#### Important Notes

- **Requires `mcp-proxy`**: Install the MCP proxy tool for streamable HTTP connections
- **HTTPS certificates**: SSL certificate files are required for secure connections
- **Replace paths**: Update certificate paths to match your setup
- **Start server first**: Ensure your HTTP server is running on port 8002

### Cursor IDE (STDIO)

**✅ Verified Working Configuration** (Thanks to community feedback from AI TRIBE!)

Cursor IDE requires STDIO transport with a crucial `MCP_TRANSPORT` environment variable.

#### Configuration Steps

1. **Open Cursor Settings:**
   - Go to Settings → MCP
   - Or edit `~/.cursor/mcp.json` directly

2. **Add server configuration:**
   ```json
   {
     "mcpServers": {
       "google-workspace": {
         "command": "uv",
         "args": [
           "--directory",
           "/path/to/your/google_workspace_fastmcp2",
           "run",
           "python",
           "server.py"
         ],
         "env": {
           "GOOGLE_CLIENT_SECRETS_FILE": "/path/to/your/client_secrets.json",
           "MCP_TRANSPORT": "stdio"
         }
       }
     }
   }
   ```

#### Important Notes

- ⚠️ **Critical:** `MCP_TRANSPORT: "stdio"` is **required** for Cursor
- Replace `/path/to/your/google_workspace_fastmcp2` with actual project directory
- Replace `/path/to/your/client_secrets.json` with actual credentials path
- Use absolute paths for reliability

#### Example Working Configuration
```json
{
  "mcpServers": {
    "google-workspace": {
      "command": "uv",
      "args": [
        "--directory",
        "/Users/yourname/projects/google_workspace_fastmcp2",
        "run",
        "python",
        "server.py"
      ],
      "env": {
        "GOOGLE_CLIENT_SECRETS_FILE": "/Users/yourname/credentials/client_secrets.json",
        "MCP_TRANSPORT": "stdio"
      }
    }
  }
}
```

### VS Code with Roo Extension (Streamable HTTP)

VS Code users with the Roo extension can connect using Streamable HTTP transport:

1. **Install Roo extension** from VS Code marketplace

2. **Start the server in HTTP mode:**
   ```bash
   uv run python server.py --transport http --port 8002
   ```

3. **Configure MCP settings** in VS Code:
   - Open Command Palette (`Cmd/Ctrl+Shift+P`)
   - Search for "Roo: Configure MCP"
   - Or edit `.vscode/mcp.json` in your workspace

4. **Add configuration:**
   ```json
   {
     "rivers_unlimited": {
       "type": "streamable-http",
       "url": "https://localhost:8002/mcp",
       "note": "For Streamable HTTP connections, add this URL directly in your MCP Client",
       "alwaysAllow": [
         "list_chat_app_resources",
         "share_drive_files",
         "health_check",
         "list_available_card_types1",
         "initialize_chat_app_manager",
         "search_drive_files",
         "preview_card_from_description",
         "create_multi_modal_card",
         "get_messages",
         "save_card_template",
         "list_card_templates",
         "create_card_from_template",
         "send_simple_card",
         "get_card_template",
         "upload_file_to_drive",
         "read_sheet_values",
         "get_spreadsheet_info",
         "server_info",
         "get_my_auth_status",
         "search_my_gmail",
         "get_gmail_message_content",
         "search_gmail_messages",
         "modify_gmail_message_labels",
         "get_gmail_messages_content_batch",
         "create_gmail_filter",
         "manage_gmail_label",
         "check_drive_auth",
         "get_gmail_filter",
         "delete_gmail_filter",
         "draft_gmail_message",
         "send_interactive_card",
         "list_available_card_components",
         "create_card_framework_wrapper",
         "list_wrapped_modules",
         "send_dynamic_card",
         "get_photos_library_info",
         "create_photos_album",
         "create_email_template",
         "add_to_gmail_allow_list",
         "remove_from_gmail_allow_list",
         "view_gmail_allow_list",
         "assign_template_to_user",
         "get_gmail_thread_content",
         "draft_gmail_reply",
         "bulk_calendar_operations",
         "list_messages",
         "search_messages",
         "list_photos_albums",
         "list_album_photos",
         "get_photo_details",
         "photos_batch_details",
         "photos_smart_search",
         "list_gmail_labels",
         "list_drive_items",
         "modify_sheet_values",
         "format_sheet_cells",
         "update_sheet_borders",
         "add_conditional_formatting",
         "format_sheet_range",
         "create_doc",
         "create_spreadsheet",
         "merge_cells",
         "get_drive_file_content",
         "get_form",
         "add_questions_to_form",
         "get_tool_analytics",
         "fetch",
         "list_calendars",
         "create_presentation",
         "create_event",
         "list_events",
         "send_form_card",
         "send_rich_card",
         "list_spreadsheets",
         "move_events_between_calendars",
         "create_template_macro",
         "start_google_auth",
         "get_event",
         "delete_event",
         "modify_event",
         "create_calendar",
         "draft_gmail_forward",
         "forward_gmail_message",
         "reply_to_gmail_message",
         "list_gmail_filters",
         "send_gmail_message",
         "list_spaces"
       ],
       "disabled": false,
       "disabledTools": [
         "search_drive_files",
         "upload_to_drive",
         "get_drive_file_content",
         "create_drive_file",
         "share_drive_files",
         "make_drive_files_public",
         "search_docs",
         "get_doc_content",
         "list_docs_in_folder",
         "create_form",
         "add_questions_to_form",
         "get_form",
         "publish_form_publicly",
         "get_form_response",
         "list_form_responses",
         "update_form_questions",
         "create_presentation",
         "get_presentation_info",
         "add_slide",
         "update_slide_content",
         "manage_credentials",
         "health_check",
         "upload_folder_photos",
         "upload_photos",
         "photos_optimized_album_sync",
         "photos_performance_stats",
         "photos_batch_details",
         "photos_smart_search",
         "get_photos_library_info",
         "create_photos_album",
         "get_photo_details",
         "list_album_photos",
         "search_photos",
         "list_photos_albums",
         "format_sheet_range",
         "create_sheet",
         "create_spreadsheet",
         "modify_sheet_values",
         "read_sheet_values",
         "get_spreadsheet_info",
         "list_spreadsheets",
         "wrap_module",
         "export_and_download_presentation",
         "send_form_card",
         "send_card_message",
         "send_simple_card",
         "send_interactive_card",
         "list_wrapped_modules",
         "list_module_components"
       ]
     }
   }
   ```

### VS Code/GitHub Copilot (HTTP)

For VS Code with native MCP support or GitHub Copilot integration:

1. **Start the server in HTTP mode:**
   ```bash
   uv run python server.py --transport http --port 8002
   ```

2. **Configure VS Code MCP settings:**
   - Open VS Code Settings
   - Search for "MCP" or navigate to Extensions → MCP
   - Or edit your VS Code `settings.json`

3. **Add configuration:**
   ```json
   {
     "mcp.servers": {
       "rivers_unlimited": {
         "type": "http",
         "url": "https://localhost:8002/mcp",
         "note": "For Streamable HTTP connections, add this URL directly in your MCP Client",
         "alwaysAllow": [
           "list_chat_app_resources",
           "share_drive_files",
           "health_check",
           "list_available_card_types1",
           "initialize_chat_app_manager",
           "search_drive_files",
           "preview_card_from_description",
           "create_multi_modal_card",
           "list_spaces",
           "get_messages",
           "save_card_template",
           "list_card_templates",
           "create_card_from_template",
           "send_simple_card",
           "get_card_template",
           "upload_file_to_drive",
           "read_sheet_values",
           "get_spreadsheet_info",
           "list_gmail_labels",
           "server_info",
           "get_my_auth_status",
           "search_my_gmail",
           "get_gmail_message_content",
           "send_gmail_message",
           "list_gmail_filters",
           "search_gmail_messages",
           "modify_gmail_message_labels",
           "get_gmail_messages_content_batch",
           "create_gmail_filter",
           "manage_gmail_label",
           "start_google_auth",
           "check_drive_auth",
           "get_gmail_filter",
           "delete_gmail_filter",
           "draft_gmail_message",
           "send_interactive_card",
           "list_available_card_components",
           "create_card_framework_wrapper",
           "list_wrapped_modules",
           "send_dynamic_card",
           "get_photos_library_info",
           "list_drive_items",
           "create_photos_album"
         ],
         "disabled": false
       }
     }
   }
   ```

#### Important Notes

- **Native HTTP**: Uses standard HTTP transport without proxy requirements
- **Tool allowlists**: Configure specific tools to allow for security
- **Auto-discovery**: VS Code can auto-detect running MCP servers on localhost
- **Restart required**: Restart VS Code after configuration changes

### Claude.ai (Remote HTTP)

For Claude.ai browser access, use HTTP transport with optional tunneling:

#### Local Setup

1. **Start the server in HTTP mode:**
   ```bash
   uv run python server.py --transport http --port 8002
   ```

2. **Configure Claude.ai** to connect to:
   ```
   http://localhost:8002/mcp
   ```

#### With Cloudflare Tunnel (Recommended)

For secure remote access:

1. **Install Cloudflare tunnel:**
   ```bash
   # Install cloudflared if not already installed
   brew install cloudflared  # macOS
   # Or download from: https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/installation/
   ```

2. **Start server locally:**
   ```bash
   uv run python server.py --transport http --port 8002
   ```

3. **Create secure tunnel:**
   ```bash
   cloudflared tunnel --url http://localhost:8002
   ```

4. **Use the tunnel URL** in Claude.ai:
   ```
   https://accurate-receiver-electoral-functional.trycloudflare.com/mcp
   ```

### HTTP Streamable Connections

For other MCP clients that support HTTP streamable transport:

#### Configuration Template
```json
{
  "mcpServers": {
    "google_workspace": {
      "type": "streamable-http",
      "url": "https://localhost:8002/mcp",
      "note": "For Streamable HTTP connections, add this URL directly in your MCP Client",
      "alwaysAllow": [
        "start_google_auth",
        "list_drive_items",
        "search_gmail_messages",
        "create_event",
        "send_gmail_message"
      ]
    }
  }
}
```

#### Starting HTTP Server
```bash
# Start server with HTTP transport
uv run python server.py --transport http --port 8002

# Or with specific host binding
uv run python server.py --transport http --host 0.0.0.0 --port 8002
```

### Remote Access with Cloudflare Tunnel

**Perfect for mobile clients and remote development!**

#### Quick Setup
```bash
# 1. Start your local server
uv run python server.py --transport http --port 8002

# 2. In another terminal, create tunnel
cloudflared tunnel --url http://localhost:8002

# 3. Use the generated HTTPS URL in your client
# Example: https://accurate-receiver-electoral-functional.trycloudflare.com/mcp
```

#### Benefits
- ✅ **Secure HTTPS** connection
- ✅ **Mobile access** from ChatGPT, Claude apps
- ✅ **No firewall configuration** needed
- ✅ **Temporary URLs** for testing
- ✅ **Global accessibility**

## 🔧 Troubleshooting

### Common Issues

#### Cursor IDE Not Detecting Server
- **Check:** `MCP_TRANSPORT: "stdio"` is set in environment
- **Check:** Absolute paths are used for all file references
- **Restart:** Cursor completely after configuration changes
- **Verify:** `uv` is installed and accessible: `which uv`

#### Authentication Errors
- **Check:** `GOOGLE_CLIENT_SECRETS_FILE` path is correct and accessible
- **Check:** OAuth credentials have required scopes enabled
- **Check:** Client secrets file is valid JSON
- **Reset:** Delete cached credentials if authentication flow fails

#### Connection Refused (HTTP)
- **Check:** Server is running: `curl http://localhost:8002/mcp`
- **Check:** Port is not blocked by firewall
- **Check:** Host binding (use `0.0.0.0` for external access)

#### Cloudflare Tunnel Issues
- **Check:** `cloudflared` is installed: `cloudflared version`
- **Check:** Local server is running before creating tunnel
- **Wait:** Tunnel URL generation may take a few seconds

### Debug Commands

```bash
# Test server startup
uv run python server.py --help

# Verify environment
env | grep GOOGLE

# Test HTTP endpoint
curl -X POST http://localhost:8002/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'

# Check port availability
lsof -i :8002
```

## ⚙️ Advanced Configuration

### Custom Environment Variables

```json
{
  "mcpServers": {
    "google-workspace": {
      "command": "uv",
      "args": ["..."],
      "env": {
        "GOOGLE_CLIENT_SECRETS_FILE": "/path/to/credentials.json",
        "MCP_TRANSPORT": "stdio",
        "MCP_LOG_LEVEL": "DEBUG",
        "MCP_TOOL_RESPONSES_COLLECTION_CACHE_DAYS": "30",
        "QDRANT_URL": "http://localhost:6333"
      }
    }
  }
}
```

### Performance Optimization

```bash
# For high-performance scenarios
uv run python server.py \
  --transport http \
  --port 8002 \
  --workers 4 \
  --max-requests 1000
```

### Security Headers (HTTP Mode)

```bash
# Enable CORS and security headers
uv run python server.py \
  --transport http \
  --port 8002 \
  --cors \
  --secure-headers
```

---

## 📞 Support

If you encounter issues:

1. **Check the logs** for specific error messages
2. **Verify all paths** are absolute and accessible
3. **Test authentication** independently: `uv run python scripts/auth_test.py gmail`
4. **Join the community** discussions for real-time help

For more details, see:
- 📚 **[Complete Configuration Guide](CONFIGURATION_GUIDE.md)**
- 🔒 **[HTTPS Setup Guide](https_setup_guide.md)**
- 🤖 **[Claude.ai Integration Guide](claude_ai_integration_guide.md)**