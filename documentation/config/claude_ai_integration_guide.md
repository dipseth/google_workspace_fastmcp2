# Claude.ai Integration Guide

## Overview

This guide explains how to configure your MCP server to work with Claude.ai as a remote MCP server.

## Requirements for Claude.ai Integration

Based on Claude.ai's MCP documentation:

### 1. HTTPS and Domain Requirements
- **Real SSL Certificate**: Claude.ai requires a publicly trusted SSL certificate
- **Public Domain**: Your server must be accessible from the internet
- **OAuth Callback URL**: Must match `https://claude.ai/api/mcp/auth_callback`

### 2. Supported Features
- ✅ OAuth-based authentication with Dynamic Client Registration (DCR)
- ✅ SSE and Streamable HTTP transport
- ✅ Tools, prompts, and resources
- ✅ Token expiry and refresh

## Deployment Options

### Option 1: Cloudflare Workers (Recommended)
Cloudflare provides built-in MCP server hosting with OAuth management:

```bash
# Install Cloudflare CLI
npm install -g wrangler

# Deploy your MCP server
wrangler deploy
```

### Option 2: ngrok Tunnel (Development/Testing)
Expose your localhost server with HTTPS:

```bash
# Install ngrok
brew install ngrok

# Create a tunnel with custom domain (requires ngrok account)
ngrok http 8002 --domain=your-app.ngrok-free.app

# Your server will be available at:
# https://your-app.ngrok-free.app
```

### Option 3: Cloud Deployment
Deploy to any cloud service with HTTPS:

- **Railway**: Automatic HTTPS with custom domains
- **Render**: Free tier with HTTPS
- **Heroku**: Built-in HTTPS support
- **DigitalOcean App Platform**: Managed HTTPS
- **AWS/GCP/Azure**: With load balancer and certificates

## Configuration for Claude.ai

### 1. Update Environment Variables

Create a production `.env` file:

```env
# Production Configuration
ENVIRONMENT=production
DEBUG=false

# Server Configuration
HOST=0.0.0.0
PORT=8002
SERVER_NAME=your-domain.com

# HTTPS Configuration (for cloud deployment)
USE_HTTPS=true
SSL_CERT_PATH=""  # Let cloud provider handle certificates
SSL_KEY_PATH=""

# OAuth Configuration for Claude.ai
OAUTH_BASE_URL=https://your-domain.com
OAUTH_CLIENT_NAME=Claude
OAUTH_ALLOWED_REDIRECT_URIS=https://claude.ai/api/mcp/auth_callback,https://claude.com/api/mcp/auth_callback

# Google OAuth Configuration
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret
GOOGLE_PROJECT_ID=your-project-id

# Phase 1 Feature Flags
PHASE1_ENABLE_FASTMCP_PROVIDER=true
PHASE1_DUAL_FLOW_MODE=true
PHASE1_FASTMCP_PRIMARY=false
```

### 2. Update Google OAuth Configuration

In your Google Cloud Console:

1. Add Claude.ai callback URLs to authorized redirect URIs:
   - `https://claude.ai/api/mcp/auth_callback`
   - `https://claude.com/api/mcp/auth_callback`

2. Add your production domain to authorized JavaScript origins:
   - `https://your-domain.com`

### 3. Configure OAuth Endpoints

Update `auth/fastmcp_oauth_endpoints.py` for Claude.ai compatibility:

```python
# Ensure OAuth discovery endpoints return production URLs
OAUTH_BASE_URL = settings.oauth_base_url or f"https://{settings.server_name}"
MCP_RESOURCE_URL = f"{OAUTH_BASE_URL}/mcp"
```

## Local Development Setup

For local development and testing:

### 1. Create Development Certificates

```bash
# Create localhost certificates with mkcert
mkcert localhost 127.0.0.1 ::1
```

### 2. Local Environment Configuration

```env
# Development Configuration
ENVIRONMENT=development
DEBUG=true

# Server Configuration
HOST=localhost
PORT=8002
SERVER_NAME=localhost

# HTTPS Configuration (local)
USE_HTTPS=true
SSL_CERT_PATH=./localhost+2.pem
SSL_KEY_PATH=./localhost+2-key.pem

# OAuth Configuration (local testing)
OAUTH_BASE_URL=https://localhost:8002
```

## Testing Your Server

### 1. Local Testing
1. Start your server: `python server.py`
2. Test with MCP Inspector: `npx @modelcontextprotocol/inspector https://localhost:8002/mcp`
3. Verify OAuth flow works

### 2. Claude.ai Testing
1. Deploy your server to a public domain with HTTPS
2. In Claude.ai, go to Settings > Connectors
3. Add your server URL: `https://your-domain.com/mcp`
4. Complete OAuth authentication flow
5. Test MCP tools and resources

## Security Considerations

### IP Whitelisting (Optional)
If you want to restrict access to Claude.ai only, whitelist these IP addresses:
- Check Claude.ai documentation for current IP ranges
- Configure your firewall/load balancer accordingly

### OAuth Security
- Use strong, unique client secrets
- Enable token refresh for better security
- Monitor OAuth logs for unauthorized access attempts

## Troubleshooting

### Common Issues

1. **Certificate Errors**
   - Ensure your domain has a valid SSL certificate
   - Check certificate expiration dates
   - Verify certificate chain is complete

2. **OAuth Flow Issues**
   - Verify redirect URIs match exactly
   - Check client ID and secret configuration
   - Ensure Dynamic Client Registration is working

3. **Connection Timeouts**
   - Verify server is publicly accessible
   - Check firewall rules
   - Ensure server is running on correct port

### Debug Endpoints

Your server exposes these debug endpoints:
- `GET /health` - Server health check
- `GET /oauth/discovery` - OAuth configuration
- `GET /mcp` - MCP server endpoint

## Migration from Local to Production

1. **Update DNS**: Point your domain to your server
2. **Configure HTTPS**: Set up SSL certificates
3. **Update OAuth**: Add production redirect URIs
4. **Environment Variables**: Switch to production config
5. **Test**: Verify all functionality works
6. **Claude.ai**: Add your server in Claude.ai settings

## Support

For issues:
1. Check server logs for detailed error messages
2. Test with MCP Inspector first
3. Verify OAuth flow with curl/Postman
4. Check Claude.ai connector status in settings