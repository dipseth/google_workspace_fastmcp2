# Tunnel Services API Reference

Complete API documentation for all tunnel management tools in the Groupon Google MCP Server.

## Overview

The Tunnel Services provide Cloudflare tunnel management capabilities for secure, persistent connections to Google Workspace services and Chat app deployments. This service enables secure public access to local development servers and production deployments.

## Available Tools

| Tool Name | Description |
|-----------|-------------|
| [`create_cloudflare_tunnel`](#create_cloudflare_tunnel) | Create new Cloudflare tunnels for secure access |
| [`list_active_tunnels`](#list_active_tunnels) | List currently active tunnel connections |
| [`terminate_tunnel`](#terminate_tunnel) | Terminate specific tunnel connections |

---

## Tool Details

### `create_cloudflare_tunnel`

Create new Cloudflare tunnels for secure public access to local services.

**Parameters:**
- `service_name` (string, required): Name identifier for the tunnel
- `local_port` (integer, required): Local port to expose through tunnel
- `subdomain` (string, optional): Custom subdomain for tunnel URL
- `tunnel_config` (object, optional): Advanced tunnel configuration options

**Tunnel Configuration Options:**
- **Protocol**: HTTP, HTTPS, TCP, UDP support
- **Authentication**: Built-in access control
- **Load Balancing**: Multi-origin support
- **SSL/TLS**: Automatic certificate management
- **Compression**: Built-in response optimization

**Use Cases:**
- **Chat App Development**: Expose local webhook endpoints
- **API Testing**: Secure public access to development APIs
- **Collaboration**: Share local development instances
- **Production Deployment**: Secure tunnel-based deployments

**Response:**
- Tunnel URL for public access
- Tunnel ID and management information
- Connection status and health metrics
- Security and access control settings

### `list_active_tunnels`

List all currently active tunnel connections with status information.

**Parameters:**
- `filter_by_service` (string, optional): Filter tunnels by service name
- `include_metrics` (boolean, optional, default: true): Include performance metrics

**Response Information:**
- Active tunnel URLs and endpoints
- Connection status and uptime
- Traffic metrics and performance data
- Service routing and configuration
- Health check results

**Metrics Include:**
- Request count and response times
- Data transfer volumes
- Error rates and availability
- Geographic distribution of requests
- Performance benchmarks

### `terminate_tunnel`

Terminate specific tunnel connections and clean up resources.

**Parameters:**
- `tunnel_id` (string, required): Tunnel identifier to terminate
- `force_disconnect` (boolean, optional, default: false): Force immediate disconnection
- `cleanup_resources` (boolean, optional, default: true): Clean up associated resources

**Termination Process:**
1. Graceful connection closure
2. Active request completion
3. Resource cleanup and deallocation
4. DNS record removal
5. Certificate cleanup

**Response:**
- Termination status and confirmation
- Resource cleanup results
- Final connection statistics
- Any cleanup warnings or errors

---

## Cloudflare Integration

### Tunnel Technology

Cloudflare Tunnel provides:
- **Zero-Trust Security**: No open inbound ports required
- **Global Network**: 270+ edge locations worldwide
- **Automatic SSL**: Built-in certificate management
- **DDoS Protection**: Enterprise-grade security
- **Performance Optimization**: Edge caching and compression

### Authentication Methods

Multiple authentication options:
- **API Tokens**: Service-specific authentication
- **Account Keys**: Full account access
- **Service Auth**: Tunnel-specific credentials
- **OAuth Integration**: Google Workspace SSO

### Configuration Management

Tunnels support comprehensive configuration:
```json
{
  "tunnel_config": {
    "protocol": "https",
    "compression": "gzip",
    "authentication": {
      "method": "oauth",
      "provider": "google"
    },
    "access_control": {
      "allowed_emails": ["team@company.com"],
      "ip_restrictions": ["10.0.0.0/8"]
    },
    "performance": {
      "caching": "aggressive",
      "compression": "enabled",
      "http2": true
    }
  }
}
```

## Chat App Development Integration

### Webhook Tunneling

Perfect for Google Chat app development:

```python
# Create tunnel for Chat app webhook
tunnel = await create_cloudflare_tunnel(
    service_name="chat_app_webhook",
    local_port=8080,
    subdomain="my-chat-app",
    tunnel_config={
        "protocol": "https",
        "authentication": {"method": "none"},  # For Google Chat webhooks
        "headers": {
            "X-Forwarded-Proto": "https"
        }
    }
)

# Use tunnel URL in Chat app manifest
webhook_url = tunnel["public_url"] + "/webhook"
```

### Development Workflow

1. **Local Development**: Run Chat app locally on port 8080
2. **Tunnel Creation**: Create secure tunnel to local server
3. **Webhook Configuration**: Use tunnel URL in Chat app settings
4. **Testing**: Google Chat can now reach local development server
5. **Debugging**: Real-time webhook debugging with local tools

### Production Deployment

Tunnels can also serve production deployments:
- **Container Deployments**: Tunnel to containerized applications
- **Kubernetes Integration**: Service mesh connectivity
- **Load Balancing**: Multi-origin tunnel configurations
- **High Availability**: Redundant tunnel setups

## Security Features

### Zero-Trust Architecture
- **No Inbound Ports**: Eliminates firewall configuration
- **Outbound-Only**: Connections initiated from secure environment
- **Encrypted Transit**: All traffic encrypted in transit
- **Identity Verification**: Authentication before access

### Access Control
- **Email-based Access**: Google Workspace integration
- **IP Restrictions**: Geographic and network-based controls
- **Time-based Access**: Temporary tunnel configurations
- **Audit Logging**: Comprehensive access logging

### Certificate Management
- **Automatic SSL/TLS**: Zero-configuration HTTPS
- **Certificate Rotation**: Automatic renewal and updates
- **Custom Certificates**: Support for organization certificates
- **Multi-domain Support**: Wildcard and SAN certificates

## Performance Optimization

### Edge Network Benefits
- **Global CDN**: 270+ edge locations
- **Intelligent Routing**: Optimal path selection
- **Protocol Optimization**: HTTP/2, HTTP/3 support
- **Compression**: Automatic content compression

### Monitoring and Analytics
- **Real-time Metrics**: Connection and performance data
- **Traffic Analysis**: Request patterns and trends
- **Error Tracking**: Comprehensive error logging
- **Performance Benchmarks**: Latency and throughput metrics

## Best Practices

### Development Usage
1. **Service Naming**: Use descriptive tunnel names
2. **Port Management**: Avoid port conflicts
3. **Authentication**: Implement appropriate access controls
4. **Resource Cleanup**: Terminate unused tunnels promptly

### Production Deployment
1. **High Availability**: Configure redundant tunnels
2. **Load Balancing**: Distribute traffic across origins
3. **Monitoring**: Implement comprehensive health checks
4. **Security**: Enable all appropriate access controls

### Cost Optimization
1. **Resource Management**: Monitor tunnel usage
2. **Connection Pooling**: Reuse tunnels where possible
3. **Cleanup Automation**: Implement automatic tunnel cleanup
4. **Usage Analysis**: Regular review of tunnel necessity

## Common Use Cases

### Google Chat App Development
```python
# Development setup for Chat app
webhook_tunnel = await create_cloudflare_tunnel(
    service_name="chat_webhook_dev",
    local_port=5000,
    tunnel_config={
        "protocol": "https",
        "headers": {"X-Forwarded-Proto": "https"}
    }
)

# Use in Chat app manifest
print(f"Webhook URL: {webhook_tunnel['public_url']}/google_chat_webhook")
```

### API Gateway Deployment
```python
# Secure API access
api_tunnel = await create_cloudflare_tunnel(
    service_name="api_gateway",
    local_port=8000,
    tunnel_config={
        "authentication": {"method": "oauth"},
        "access_control": {
            "allowed_emails": ["api-users@company.com"]
        }
    }
)
```

### Collaborative Development
```python
# Share development environment
dev_tunnel = await create_cloudflare_tunnel(
    service_name="dev_sharing",
    local_port=3000,
    subdomain="team-dev",
    tunnel_config={
        "access_control": {
            "allowed_emails": ["team@company.com"]
        }
    }
)
```

## Error Handling

### Connection Failures
```json
{
  "error": {
    "code": "TUNNEL_CONNECTION_FAILED",
    "message": "Unable to establish tunnel connection",
    "details": {
      "local_port": 8080,
      "cloudflare_status": "unreachable",
      "retry_available": true
    }
  }
}
```

### Authentication Issues
```json
{
  "error": {
    "code": "TUNNEL_AUTH_FAILED",
    "message": "Cloudflare authentication failed",
    "details": {
      "auth_method": "api_token",
      "token_status": "expired",
      "renewal_required": true
    }
  }
}
```

### Configuration Errors
- **Port Conflicts**: Verify local port availability
- **DNS Resolution**: Check subdomain configurations
- **Certificate Issues**: Validate SSL/TLS settings
- **Access Control**: Verify authentication settings

## Configuration

### Environment Variables
```bash
# Cloudflare Configuration
CLOUDFLARE_API_TOKEN=your_api_token
CLOUDFLARE_ACCOUNT_ID=your_account_id
CLOUDFLARE_ZONE_ID=your_zone_id

# Tunnel Settings
TUNNEL_SUBDOMAIN=your-app
TUNNEL_PROTOCOL=https
TUNNEL_COMPRESSION=gzip
```

### Account Setup
1. **Cloudflare Account**: Create or use existing account
2. **API Token**: Generate token with tunnel permissions
3. **Domain Configuration**: Set up domain for tunnel usage
4. **Zone Settings**: Configure DNS and security settings

---

For more information, see:
- [Cloudflare Tunnel Documentation](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/)
- [Chat App Development Guide](../../CHAT_APP_DEVELOPMENT.md)
- [Security Best Practices](../../SECURITY.md)
- [Main API Reference](../README.md)