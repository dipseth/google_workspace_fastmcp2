# Google OAuth HTTPS Fix Guide

## Problem
After switching to HTTPS, Google OAuth authentication fails because Google requires exact redirect URI matching.

## Current Configuration
- Current redirect URI: `http://localhost:8002/oauth2callback` (HTTP)
- Server now running: `https://localhost:8002` (HTTPS)
- **Result:** OAuth fails because URIs don't match

## Solution Steps

### 1. Update Your .env File
Change your redirect URI to HTTPS:
```env
OAUTH_REDIRECT_URI=https://localhost:8002/oauth2callback
```

### 2. Update Google Cloud Console
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Navigate to **APIs & Services** > **Credentials**
3. Find your OAuth 2.0 Client ID and click **Edit**
4. In the **Authorized redirect URIs** section, add:
   ```
   https://localhost:8002/oauth2callback
   ```
5. **Keep the old HTTP URI** for backward compatibility:
   ```
   http://localhost:8002/oauth2callback
   https://localhost:8002/oauth2callback
   ```
6. Click **Save**

### 3. Test OAuth Flow
1. Restart your server
2. Navigate to your OAuth endpoint
3. Complete the Google authentication flow
4. Verify successful redirect to HTTPS callback

## Why This Happens
Google OAuth security requires exact URI matching:
- `http://localhost:8002/oauth2callback` ≠ `https://localhost:8002/oauth2callback`
- Different protocols are treated as completely different URIs
- Even port numbers must match exactly

## Pro Tip
Keep both HTTP and HTTPS redirect URIs configured in Google Cloud Console for flexibility during development.