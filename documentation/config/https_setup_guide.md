# 🔒 HTTPS Setup Guide for FastMCP Google MCP Server

## ✅ SSL Certificates Generated
Your SSL certificates have been created successfully:
- `cert.pem` - SSL certificate (1988 bytes)
- `key.pem` - Private key (3272 bytes, properly secured)

## 🔧 Configuration Steps

### 1. Update your `.env` file
Add these lines to your `.env` file:

```bash
# Enable HTTPS
ENABLE_HTTPS=true
SSL_CERT_FILE=cert.pem
SSL_KEY_FILE=key.pem

# Update FastMCP GoogleProvider base URL to use HTTPS
FASTMCP_SERVER_AUTH_GOOGLE_BASE_URL=https://localhost:8002/mcp
```

### 2. Restart your server
After updating the `.env` file, restart your FastMCP server.

## 🌐 Access URLs (HTTPS Enabled)

- **MCP Server**: `https://localhost:8002/mcp`
- **OAuth Discovery**: `https://localhost:8002/.well-known/oauth-protected-resource/mcp`
- **OAuth Registration**: `https://localhost:8002/oauth/register`
- **Health Check**: `https://localhost:8002/health_check` (if you have a health endpoint)

## 🔍 Testing HTTPS Setup

### Test OAuth Registration Endpoint
```bash
curl -k -X POST https://localhost:8002/oauth/register -H "Content-Type: application/json" -d '{}'
```

### Test Discovery Endpoint
```bash
curl -k https://localhost:8002/.well-known/oauth-protected-resource/mcp
```

**Note**: The `-k` flag bypasses SSL certificate verification for self-signed certificates.

## 🛡️ Security Considerations

### For Local Development:
✅ **Self-signed certificates are PERFECT** - they provide encryption without the need for a certificate authority

### Browser Warnings:
- Your browser will show a security warning for self-signed certificates
- Click "Advanced" → "Proceed to localhost (unsafe)" to continue
- This is normal and safe for local development

### MCP Inspector Usage:
- Use `https://localhost:8002/mcp` as your server URL
- You may need to accept the certificate warning in your browser first

## 🔄 Switching Back to HTTP (if needed)
To disable HTTPS, simply set in your `.env`:
```bash
ENABLE_HTTPS=false
FASTMCP_SERVER_AUTH_GOOGLE_BASE_URL=http://localhost:8002/mcp
```

## 📋 Expected Server Logs
When HTTPS is enabled, you should see:
```
INFO: SSL configuration validated
SSL Certificate: cert.pem
SSL Private Key: key.pem
🔒 Starting server with HTTPS/SSL support
```

## 🎯 OAuth Flow Changes
With HTTPS enabled:
1. All OAuth redirects will use HTTPS URLs
2. MCP Inspector will connect via HTTPS
3. OAuth discovery endpoints serve HTTPS metadata
4. Better security for OAuth token exchange

## 🆘 Troubleshooting

### Certificate Errors:
- Ensure `cert.pem` and `key.pem` are in your project root
- Check file permissions: `key.pem` should be readable only by owner

### Port Already in Use:
- Stop any existing server instances
- Check for other applications using port 8002

### Browser Issues:
- Clear browser cache
- Try incognito/private mode
- Accept certificate warnings for localhost