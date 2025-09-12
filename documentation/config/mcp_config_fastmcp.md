# MCP JSON Configuration 🤝 FastMCP

Generate standard MCP configuration files for any compatible client

> **New in version: 2.10.3**  
> FastMCP can generate standard MCP JSON configuration files that work with any MCP-compatible client including Claude Desktop, VS Code, Cursor, and other applications that support the Model Context Protocol.

## MCP JSON Configuration Standard

The MCP JSON configuration format is an emergent standard that has developed across the MCP ecosystem. This format defines how MCP clients should configure and launch MCP servers, providing a consistent way to specify server commands, arguments, and environment variables.

### Configuration Structure

The standard uses a `mcpServers` object where each key represents a server name and the value contains the server's configuration:

```json
{
  "mcpServers": {
    "server-name": {
      "command": "executable",
      "args": ["arg1", "arg2"],
      "env": {
        "VAR": "value"
      }
    }
  }
}
```

### Server Configuration Fields

#### `command` (required)

The executable command to run the MCP server. This should be an absolute path or a command available in the system PATH.

```json
{
  "command": "python"
}
```

#### `args` (optional)

An array of command-line arguments passed to the server executable. Arguments are passed in order.

```json
{
  "args": ["server.py", "--verbose", "--port", "8080"]
}
```

#### `env` (optional)

An object containing environment variables to set when launching the server. All values must be strings.

```json
{
  "env": {
    "API_KEY": "secret-key",
    "DEBUG": "true",
    "PORT": "8080"
  }
}
```

### Client Adoption

This format is widely adopted across the MCP ecosystem:

- **Claude Desktop**: Uses `~/.claude/claude_desktop_config.json`
- **Cursor**: Uses `~/.cursor/mcp.json`
- **VS Code**: Uses workspace `.vscode/mcp.json`
- **Other clients**: Many MCP-compatible applications follow this standard

## Overview

> **Best Practice**: For the best experience, use FastMCP's first-class integrations: `fastmcp install claude-code`, `fastmcp install claude-desktop`, or `fastmcp install cursor`. Use MCP JSON generation for advanced use cases and unsupported clients.

The `fastmcp install mcp-json` command generates configuration in the standard `mcpServers` format used across the MCP ecosystem. This is useful when:

- **Working with unsupported clients** - Any MCP client not directly integrated with FastMCP
- **CI/CD environments** - Automated configuration generation for deployments
- **Configuration sharing** - Easy distribution of server setups to team members
- **Custom tooling** - Integration with your own MCP management tools
- **Manual setup** - When you prefer to manually configure your MCP client

## Basic Usage

Generate configuration and output to stdout (useful for piping):

```bash
fastmcp install mcp-json server.py
```

This outputs the server configuration JSON with the server name as the root key:

```json
{
  "My Server": {
    "command": "uv",
    "args": [
      "run",
      "--with",
      "fastmcp", 
      "fastmcp",
      "run",
      "/absolute/path/to/server.py"
    ]
  }
}
```

To use this in a client configuration file, add it to the `mcpServers` object in your client's configuration:

```json
{
  "mcpServers": {
    "My Server": {
      "command": "uv",
      "args": [
        "run",
        "--with",
        "fastmcp", 
        "fastmcp",
        "run",
        "/absolute/path/to/server.py"
      ]
    }
  }
}
```

> **Note**: When using `--python`, `--project`, or `--with-requirements`, the generated configuration will include these options in the `uv run` command, ensuring your server runs with the correct Python version and dependencies.

> **Important**: Different MCP clients may have specific configuration requirements or formatting needs. Always consult your client's documentation to ensure proper integration.

## Configuration Options

### Server Naming

```bash
# Use server's built-in name (from FastMCP constructor)
fastmcp install mcp-json server.py

# Override with custom name
fastmcp install mcp-json server.py --name "Custom Server Name"
```

### Dependencies

Add Python packages your server needs:

```bash
# Single package
fastmcp install mcp-json server.py --with pandas

# Multiple packages  
fastmcp install mcp-json server.py --with pandas --with requests --with httpx

# Editable local package
fastmcp install mcp-json server.py --with-editable ./my-package

# From requirements file
fastmcp install mcp-json server.py --with-requirements requirements.txt
```

You can also use a `fastmcp.json` configuration file (recommended):

**fastmcp.json**
```json
{
  "$schema": "https://gofastmcp.com/schemas/fastmcp_config/v1.json",
  "entrypoint": {
    "file": "server.py",
    "object": "mcp"
  },
  "environment": {
    "dependencies": ["pandas", "matplotlib", "seaborn"]
  }
}
```

Then simply install with:

```bash
fastmcp install mcp-json fastmcp.json
```

### Environment Variables

```bash
# Individual environment variables
fastmcp install mcp-json server.py \
  --env API_KEY=your-secret-key \
  --env DEBUG=true

# Load from .env file
fastmcp install mcp-json server.py --env-file .env
```

### Python Version and Project Directory

Specify Python version or run within a specific project:

```bash
# Use specific Python version
fastmcp install mcp-json server.py --python 3.11

# Run within a project directory
fastmcp install mcp-json server.py --project /path/to/project
```

### Server Object Selection

Use the same `file.py:object` notation as other FastMCP commands:

```bash
# Auto-detects server object (looks for 'mcp', 'server', or 'app')
fastmcp install mcp-json server.py

# Explicit server object
fastmcp install mcp-json server.py:my_custom_server
```

### Clipboard Integration

Copy configuration directly to your clipboard for easy pasting:

```bash
fastmcp install mcp-json server.py --copy
```

> **Note**: The `--copy` flag requires the `pyperclip` Python package. If not installed, you'll see an error message with installation instructions.

## Usage Examples

### Basic Server

```bash
fastmcp install mcp-json dice_server.py
```

Output:

```json
{
  "Dice Server": {
    "command": "uv",
    "args": [
      "run",
      "--with",
      "fastmcp",
      "fastmcp", 
      "run",
      "/home/user/dice_server.py"
    ]
  }
}
```

### Production Server with Dependencies

```bash
fastmcp install mcp-json api_server.py \
  --name "Production API Server" \
  --with requests \
  --with python-dotenv \
  --env API_BASE_URL=https://api.example.com \
  --env TIMEOUT=30
```

### Advanced Configuration

```bash
fastmcp install mcp-json ml_server.py \
  --name "ML Analysis Server" \
  --python 3.11 \
  --with-requirements requirements.txt \
  --project /home/user/ml-project \
  --env GPU_DEVICE=0
```

Output:

```json
{
  "Production API Server": {
    "command": "uv",
    "args": [
      "run",
      "--with",
      "fastmcp",
      "--with",
      "python-dotenv", 
      "--with",
      "requests",
      "fastmcp",
      "run", 
      "/home/user/api_server.py"
    ],
    "env": {
      "API_BASE_URL": "https://api.example.com",
      "TIMEOUT": "30"
    }
  }
}
```

The advanced configuration example generates:

```json
{
  "ML Analysis Server": {
    "command": "uv",
    "args": [
      "run",
      "--python",
      "3.11",
      "--project",
      "/home/user/ml-project",
      "--with",
      "fastmcp",
      "--with-requirements",
      "requirements.txt",
      "fastmcp",
      "run",
      "/home/user/ml_server.py"
    ],
    "env": {
      "GPU_DEVICE": "0"
    }
  }
}
```

### Pipeline Usage

Save configuration to file:

```bash
fastmcp install mcp-json server.py > mcp-config.json
```

Use in shell scripts:

```bash
#!/bin/bash
CONFIG=$(fastmcp install mcp-json server.py --name "CI Server")
echo "$CONFIG" | jq '."CI Server".command'
# Output: "uv"
```

## Integration with MCP Clients

The generated configuration works with any MCP-compatible application:

### Claude Desktop

> **Recommended**: Prefer `fastmcp install claude-desktop` for automatic installation. Use MCP JSON for advanced configuration needs.

Copy the `mcpServers` object into `~/.claude/claude_desktop_config.json`

### Cursor

> **Recommended**: Prefer `fastmcp install cursor` for automatic installation. Use MCP JSON for advanced configuration needs.

Add to `~/.cursor/mcp.json`

### VS Code

Add to your workspace's `.vscode/mcp.json` file

### Custom Applications

Use the JSON configuration with any application that supports the MCP protocol

## Configuration Format

The generated configuration outputs a server object with the server name as the root key:

```json
{
  "<server-name>": {
    "command": "<executable>",
    "args": ["<arg1>", "<arg2>", "..."],
    "env": {
      "<ENV_VAR>": "<value>"
    }
  }
}
```

To use this in an MCP client, add it to the client's `mcpServers` configuration object.

**Fields:**

- **`command`**: The executable to run (always `uv` for FastMCP servers)
- **`args`**: Command-line arguments including dependencies and server path
- **`env`**: Environment variables (only included if specified)

> **Important**: All file paths in the generated configuration are absolute paths. This ensures the configuration works regardless of the working directory when the MCP client starts the server.

## Requirements

- **uv**: Must be installed and available in your system PATH
- **pyperclip** (optional): Required only for `--copy` functionality

Install `uv` if not already available:

```bash
# macOS
brew install uv

# Linux/Windows  
curl -LsSf https://astral.sh/uv/install.sh | sh
```

---

# Claude Desktop 🤝 FastMCP

Call FastMCP servers from Claude Desktop

> **Note**: This integration focuses on running local FastMCP server files with STDIO transport. For remote servers running with HTTP or SSE transport, use your client's native configuration - FastMCP's integrations focus on simplifying the complex local setup with dependencies and uv commands.

Claude Desktop supports MCP servers through local STDIO connections and remote servers (beta), allowing you to extend Claude's capabilities with custom tools, resources, and prompts from your FastMCP servers.

> **Beta Feature**: Remote MCP server support is currently in beta and available for users on Claude Pro, Max, Team, and Enterprise plans (as of June 2025). Most users will still need to use local STDIO connections.

> **Further Reading**: This guide focuses specifically on using FastMCP servers with Claude Desktop. For general Claude Desktop MCP setup and official examples, see the [official Claude Desktop quickstart guide](https://modelcontextprotocol.io/quickstart/user).

## Requirements

Claude Desktop traditionally requires MCP servers to run locally using STDIO transport, where your server communicates with Claude through standard input/output rather than HTTP. However, users on certain plans now have access to remote server support as well.

> **Proxy Option**: If you don't have access to remote server support or need to connect to remote servers, you can create a proxy server that runs locally via STDIO and forwards requests to remote HTTP servers. See the [Proxy Servers](#proxy-servers) section below.

## Create a Server

The examples in this guide will use the following simple dice-rolling server, saved as `server.py`.

**server.py**
```python
import random
from fastmcp import FastMCP

mcp = FastMCP(name="Dice Roller")

@mcp.tool
def roll_dice(n_dice: int) -> list[int]:
    """Roll `n_dice` 6-sided dice and return the results."""
    return [random.randint(1, 6) for _ in range(n_dice)]

if __name__ == "__main__":
    mcp.run()
```

## Install the Server

### FastMCP CLI

> **New in version: 2.10.3**  
> The easiest way to install a FastMCP server in Claude Desktop is using the `fastmcp install claude-desktop` command. This automatically handles the configuration and dependency management.

> **Legacy Note**: Prior to version 2.10.3, Claude Desktop could be managed by running `fastmcp install <path>` without specifying the client.

```bash
fastmcp install claude-desktop server.py
```

The install command supports the same `file.py:object` notation as the run command. If no object is specified, it will automatically look for a FastMCP server object named `mcp`, `server`, or `app` in your file:

```bash
# These are equivalent if your server object is named 'mcp'
fastmcp install claude-desktop server.py
fastmcp install claude-desktop server.py:mcp

# Use explicit object name if your server has a different name
fastmcp install claude-desktop server.py:my_custom_server
```

> **Important**: After installation, restart Claude Desktop completely. You should see a hammer icon (🔨) in the bottom left of the input box, indicating that MCP tools are available.

### Dependencies

FastMCP provides several ways to manage your server's dependencies when installing in Claude Desktop:

**Individual packages:** Use the `--with` flag to specify packages your server needs. You can use this flag multiple times:

```bash
fastmcp install claude-desktop server.py --with pandas --with requests
```

**Requirements file:** If you have a `requirements.txt` file listing all your dependencies, use `--with-requirements` to install them all at once:

```bash
fastmcp install claude-desktop server.py --with-requirements requirements.txt
```

**Editable packages:** For local packages in development, use `--with-editable` to install them in editable mode:

```bash
fastmcp install claude-desktop server.py --with-editable ./my-local-package
```

Alternatively, you can use a `fastmcp.json` configuration file (recommended):

**fastmcp.json**
```json
{
  "$schema": "https://gofastmcp.com/schemas/fastmcp_config/v1.json",
  "entrypoint": {
    "file": "server.py",
    "object": "mcp"
  },
  "environment": {
    "dependencies": ["pandas", "requests"]
  }
}
```

### Python Version and Project Directory

FastMCP allows you to control the Python environment for your server:

**Python version:** Use `--python` to specify which Python version your server should run with. This is particularly useful when your server requires a specific Python version:

```bash
fastmcp install claude-desktop server.py --python 3.11
```

**Project directory:** Use `--project` to run your server within a specific project directory. This ensures that uv will discover all `pyproject.toml`, `uv.toml`, and `.python-version` files from that project:

```bash
fastmcp install claude-desktop server.py --project /path/to/my-project
```

> **Note**: When you specify a project directory, all relative paths in your server will be resolved from that directory, and the project's virtual environment will be used.

### Environment Variables

> **Security Note**: Claude Desktop runs servers in a completely isolated environment with no access to your shell environment or locally installed applications. You must explicitly pass any environment variables your server needs.

If your server needs environment variables (like API keys), you must include them:

```bash
fastmcp install claude-desktop server.py --server-name "Weather Server" \
  --env API_KEY=your-api-key \
  --env DEBUG=true
```

Or load them from a `.env` file:

```bash
fastmcp install claude-desktop server.py --server-name "Weather Server" --env-file .env
```

> **Requirement**: `uv` must be installed and available in your system PATH. Claude Desktop runs in its own isolated environment and needs uv to manage dependencies.

> **macOS Tip**: On macOS, it is recommended to install `uv` globally with Homebrew so that Claude Desktop will detect it: `brew install uv`. Installing `uv` with other methods may not make it accessible to Claude Desktop.

## Manual Configuration

For more control over the configuration, you can manually edit Claude Desktop's configuration file. You can open the configuration file from Claude's developer settings, or find it in the following locations:

- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

The configuration file is a JSON object with a `mcpServers` key, which contains the configuration for each MCP server.

```json
{
  "mcpServers": {
    "dice-roller": {
      "command": "python",
      "args": ["path/to/your/server.py"]
    }
  }
}
```

> **Important**: After updating the configuration file, restart Claude Desktop completely. Look for the hammer icon (🔨) to confirm your server is loaded.

### Dependencies

If your server has dependencies, you can use `uv` or another package manager to set up the environment.

When manually configuring dependencies, the recommended approach is to use `uv` with FastMCP. The configuration uses `uv run` to create an isolated environment with your specified packages:

```json
{
  "mcpServers": {
    "dice-roller": {
      "command": "uv",
      "args": [
        "run",
        "--with", "fastmcp",
        "--with", "pandas",
        "--with", "requests", 
        "fastmcp",
        "run",
        "path/to/your/server.py"
      ]
    }
  }
}
```

You can also manually specify Python versions and project directories in your configuration. Add `--python` to use a specific Python version, or `--project` to run within a project directory:

```json
{
  "mcpServers": {
    "dice-roller": {
      "command": "uv",
      "args": [
        "run",
        "--python", "3.11",
        "--project", "/path/to/project",
        "--with", "fastmcp",
        "fastmcp",
        "run",
        "path/to/your/server.py"
      ]
    }
  }
}
```

> **Note**: The order of arguments matters: Python version and project settings come before package specifications, which come before the actual command to run.

> **Requirement**: `uv` must be installed and available in your system PATH. Claude Desktop runs in its own isolated environment and needs uv to manage dependencies.

> **macOS Tip**: On macOS, it is recommended to install `uv` globally with Homebrew so that Claude Desktop will detect it: `brew install uv`. Installing `uv` with other methods may not make it accessible to Claude Desktop.

### Environment Variables

You can also specify environment variables in the configuration:

```json
{
  "mcpServers": {
    "weather-server": {
      "command": "python",
      "args": ["path/to/weather_server.py"],
      "env": {
        "API_KEY": "your-api-key",
        "DEBUG": "true"
      }
    }
  }
}
```

> **Security Note**: Claude Desktop runs servers in a completely isolated environment with no access to your shell environment or locally installed applications. You must explicitly pass any environment variables your server needs.

## Remote Servers

Users on Claude Pro, Max, Team, and Enterprise plans have first-class remote server support via integrations. For other users, or as an alternative approach, FastMCP can create a proxy server that forwards requests to a remote HTTP server. You can install the proxy server in Claude Desktop.

Create a proxy server that connects to a remote HTTP server:

**proxy_server.py**
```python
from fastmcp import FastMCP

# Create a proxy to a remote server
proxy = FastMCP.as_proxy(
    "https://example.com/mcp/sse", 
    name="Remote Server Proxy"
)

if __name__ == "__main__":
    proxy.run()  # Runs via STDIO for Claude Desktop
```

### Authentication

For authenticated remote servers, create an authenticated client following the guidance in the [client auth documentation](https://docs.fastmcp.com/client/auth) and pass it to the proxy:

**auth_proxy_server.py**
```python
from fastmcp import FastMCP, Client
from fastmcp.client.auth import BearerAuth

# Create authenticated client
client = Client(
    "https://api.example.com/mcp/sse",
    auth=BearerAuth(token="your-access-token")
)

# Create proxy using the authenticated client
proxy = FastMCP.as_proxy(client, name="Authenticated Proxy")

if __name__ == "__main__":
    proxy.run()