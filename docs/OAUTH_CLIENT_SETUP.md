# OAuth Client Setup Guide

## Problem: Custom OAuth Client "invalid_client" Error

When using custom OAuth credentials, you may encounter the error:
```
(invalid_client) Unauthorized
```

This happens during token exchange, even though authorization (consent screen) works fine.

## Root Cause: Redirect URI Mismatch

The most common cause is that your Google Cloud Console OAuth client doesn't have the correct redirect URI configured.

**FastMCP expects this exact redirect URI:**
```
https://localhost:8002/oauth2callback
```

## Step-by-Step Fix

### 1. Access Google Cloud Console
1. Go to [Google Cloud Console](https://console.cloud.google.com/apis/credentials)
2. Select your project
3. Navigate to **APIs & Services** → **Credentials**

### 2. Configure OAuth Client
1. Find your **OAuth 2.0 Client ID** (or create a new one)
2. Click to edit it
3. In **Authorized redirect URIs**, add:
   ```
   https://localhost:8002/oauth2callback
   ```
4. **Save** the changes

### 3. Enable Required APIs
Ensure these APIs are enabled in your project:
- Google Drive API
- Gmail API  
- Google Calendar API
- Google Docs API
- Google Sheets API
- Google Slides API
- Google Photos Library API
- Google Chat API
- Google Forms API

### 4. Configure OAuth Consent Screen
1. Go to **OAuth consent screen**
2. Configure app information
3. Add your email to test users (for internal use)
4. Verify app status is not "In review"

## Common Issues & Solutions

### Issue: "invalid_client" during token exchange
**Cause:** Redirect URI mismatch  
**Solution:** Add `https://localhost:8002/oauth2callback` to authorized redirect URIs

### Issue: "access_denied" during authorization
**Cause:** OAuth consent screen not configured or app in review  
**Solution:** Complete OAuth consent screen setup and ensure app is not under review

### Issue: "scope_denied" errors
**Cause:** Required APIs not enabled  
**Solution:** Enable all Google Workspace APIs listed above

### Issue: Client ID format validation
**Cause:** Invalid client ID format  
**Expected format:** `123456789012-abcdefghijk.apps.googleusercontent.com`

## Testing Your OAuth Client

After configuration, test with these steps:

1. Start FastMCP: `uv run fastmcp dev`
2. Navigate to OAuth flow
3. Check "Use custom Google OAuth credentials"
4. Enter your client ID (and optionally client secret for non-PKCE)
5. Complete authentication
6. Verify success without "invalid_client" errors

## Security Best Practices

### For Development
- ✅ Use PKCE flow (recommended)
- ✅ Don't enter client_secret in UI for PKCE
- ✅ Use localhost redirect URIs

### For Production
- ✅ Use environment variables for credentials
- ✅ Use HTTPS redirect URIs
- ✅ Implement proper secret management
- ❌ Never expose client_secret in browser forms

## Advanced Configuration

### Custom Port Usage
If using a different port, update redirect URI accordingly:
- Port 8002: `https://localhost:8002/oauth2callback`
- Port 3000: `https://localhost:3000/oauth2callback`
- Custom: `https://localhost:{PORT}/oauth2callback`

### Multiple Environments
Configure separate OAuth clients for:
- Development (localhost URIs)
- Staging (staging domain URIs)  
- Production (production domain URIs)

## Debugging Steps

1. **Check server logs** for detailed error information
2. **Verify redirect URI** matches exactly (including protocol and port)
3. **Test with default credentials** first to isolate the issue
4. **Use browser developer tools** to inspect OAuth redirect flow
5. **Check Google Cloud Console audit logs** for API access issues

## Enhanced Error Messages

The updated OAuth flow now provides detailed error messages including:
- Specific error type identification
- Step-by-step troubleshooting guides
- Common solution patterns
- Configuration verification steps

## Contact Support

If issues persist after following this guide:
1. Check server logs for detailed error traces
2. Verify all steps were completed correctly
3. Test with a fresh OAuth client
4. Ensure no browser caching issues (try incognito mode)