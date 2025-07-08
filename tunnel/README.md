# Cloudflare Tunnel Integration for FastMCP2

This module provides tools and resources for exposing local MCP servers through Cloudflare tunnels, allowing secure public access to MCP services.

## Overview

The Cloudflare tunnel integration allows you to:

1. Start a Cloudflare tunnel that exposes your local MCP server to the public internet
2. Generate a secure, random subdomain on trycloudflare.com
3. Share this URL with others to access your local MCP server
4. Stop the tunnel when you no longer need public access
5. Monitor the tunnel status and metrics

## Prerequisites

- [cloudflared](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/installation) must be installed on your system
- A running FastMCP2 server (typically on http://localhost:8002/mcp)

## Installation

The Cloudflare tunnel integration is included in the FastMCP2 Google Workspace Platform. No additional installation is required beyond installing the `cloudflared` CLI tool.

### Installing cloudflared

#### macOS

```bash
brew install cloudflare/cloudflare/cloudflared
```

#### Linux

Download the appropriate package for your distribution from the [Cloudflare Developer site](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/installation).

#### Windows

Download the installer from the [Cloudflare Developer site](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/installation).

## Usage

### MCP Tools

The integration provides the following MCP tools:

#### start_tunnel

Start a new Cloudflare tunnel pointing to your local MCP server.

```python
result = await start_tunnel(port=8002, host="localhost", path="/mcp")
print(f"Tunnel URL: {result['url']}")
```

Parameters:
- `port` (optional, default: 8002): The local port where the MCP server is running
- `host` (optional, default: "localhost"): The local host where the MCP server is running
- `path` (optional, default: "/mcp"): The path to the MCP endpoint

Returns:
- A dictionary containing tunnel information including status, URL, and process ID

#### stop_tunnel

Stop the running Cloudflare tunnel.

```python
result = await stop_tunnel()
print(result["message"])
```

Returns:
- A dictionary containing status information

#### get_tunnel_status

Get the current status of the Cloudflare tunnel.

```python
status = await get_tunnel_status()
if status["status"] == "active":
    print(f"Tunnel is active at {status['url']}")
else:
    print("No active tunnel")
```

Returns:
- A dictionary containing status information including status, URL, process ID, and uptime

### MCP Resources

The integration provides the following MCP resources:

#### tunnel://status

Get the current status of the tunnel.

```python
status = await mcp.read_resource("tunnel://status")
print(f"Tunnel status: {status['status']}")
print(f"Active: {status['active']}")
```

#### tunnel://url

Get the public URL of the tunnel.

```python
url_info = await mcp.read_resource("tunnel://url")
if url_info["available"]:
    print(f"Tunnel URL: {url_info['url']}")
else:
    print("No tunnel URL available")
```

#### tunnel://config

Get the configuration details of the tunnel.

```python
config = await mcp.read_resource("tunnel://config")
print(f"Tunnel status: {config['status']}")
print(f"Process ID: {config['pid']}")
print(f"URL: {config['url']}")
print(f"Local URL: {config['local_url']}")
print(f"cloudflared version: {config['cloudflared_version']}")
```

#### tunnel://metrics

Get performance metrics for the tunnel.

```python
metrics = await mcp.read_resource("tunnel://metrics")
print(f"Tunnel status: {metrics['status']}")
print(f"Uptime: {metrics['uptime_seconds']} seconds")
print(f"Active: {metrics['active']}")
```

## Security Considerations

When using Cloudflare tunnels, be aware of the following security considerations:

1. **Public Exposure**: The tunnel exposes your local MCP server to the public internet. Anyone with the URL can access your MCP server.
2. **Temporary Nature**: The tunnel URL is temporary and will be deactivated when the tunnel is stopped or the server is shut down.
3. **No Authentication**: The quick tunnel feature does not provide authentication. For production use, consider using authenticated Cloudflare tunnels.
4. **Limited Protection**: While Cloudflare provides some protection against DDoS attacks, your local server is still accessible through the tunnel.

## Troubleshooting

### Common Issues

#### cloudflared not installed

If you see an error message indicating that cloudflared is not installed, you need to install it first. See the installation instructions above.

#### Port already in use

If you see an error message indicating that the port is already in use, make sure that no other service is using the specified port.

#### Tunnel fails to start

If the tunnel fails to start, check the following:

1. Make sure cloudflared is installed and in your PATH
2. Make sure the MCP server is running on the specified port
3. Check the error message for specific details

#### Tunnel unexpectedly terminates

If the tunnel unexpectedly terminates, check the following:

1. Make sure your internet connection is stable
2. Check if cloudflared was updated or modified
3. Check the server logs for error messages

## Implementation Details

The Cloudflare tunnel integration consists of the following components:

1. **Tunnel Manager**: Coordinates the overall tunnel functionality
2. **Process Controller**: Manages the cloudflared subprocess
3. **Resource Provider**: Exposes tunnel information as MCP resources
4. **Tool Provider**: Registers MCP tools for tunnel management

The integration automatically cleans up tunnel processes when the server shuts down, ensuring that no orphaned processes are left running.