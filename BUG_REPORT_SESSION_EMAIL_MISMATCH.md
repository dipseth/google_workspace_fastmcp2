# Bug Report: Session Email Identity Mismatch

## Symptom

After server restart (triggered by OOM watchdog at RSS 2182MB), all MCP tool calls fail with:

```
Email mismatch: you are authenticated as 'dipseth@gmail.com' but tool '...' was called with 'sethrivers@gmail.com'.
Use your authenticated email or 'me'/'myself' instead.
```

Or when called without explicit email:

```
No valid credentials found for dipseth@gmail.com. Please authenticate first using the start_google_auth tool.
```

The actual authenticated Google account is `sethrivers@gmail.com`, but the session resolves to `dipseth@gmail.com`.

## Impact

- **All tool calls blocked** - cannot send email, check auth, or use any Google service
- Reconnecting MCP (`/mcp`) does not fix it
- Re-authenticating OAuth does not fix it (credentials stored under `sethrivers@gmail.com` but session identity is `dipseth@gmail.com`)

## Root Cause Analysis

The session email identity (`dipseth@gmail.com`) is resolved through this chain:

### 1. API Key Lookup (`server.py:382-398`)
When a per-user API key is used, `lookup_key(token)` checks `~/.credentials/.user_api_keys.json` and returns the email bound to that key hash.

### 2. Auth Middleware Email Extraction (`auth/middleware.py:248-350`)
Multi-step fallback:
1. JWT token claims
2. FastMCP GoogleProvider
3. Session storage
4. `.oauth_authentication.json` file
5. Tool arguments (last resort)

### 3. Email Mismatch Enforcement (`auth/middleware.py:2654-2729, 2813-2817`)
`_auto_inject_email_parameter()` sets `final_email` from the resolved identity and rejects any tool call where the `user_google_email` param doesn't match.

### Likely Failure Point

The API key in `~/.credentials/.user_api_keys.json` is bound to `dipseth@gmail.com` (possibly generated during an earlier OAuth flow or derived from the system username `dipseth`). When the key was generated (`auth/user_api_keys.py:233-279`), it was associated with `dipseth@gmail.com`, but the actual Google OAuth credentials were created for `sethrivers@gmail.com`.

**The disconnect**: The API key registry maps `key_hash -> dipseth@gmail.com`, but the credential store has tokens for `sethrivers@gmail.com`. These two systems are out of sync.

## Files Involved

| File | Lines | Role |
|------|-------|------|
| `server.py` | 382-398 | API key lookup, token claims creation |
| `auth/middleware.py` | 248-350 | Email extraction fallback chain |
| `auth/middleware.py` | 2654-2729 | Email auto-injection and validation |
| `auth/middleware.py` | 2813-2817 | "Email mismatch" error generation |
| `auth/user_api_keys.py` | 233-279 | API key generation (binds email) |
| `auth/user_api_keys.py` | 313-332 | API key registry lookup |
| `~/.credentials/.user_api_keys.json` | - | Persistent key-to-email registry |

## Possible Fixes

1. **Immediate**: Update the API key registry entry to map to `sethrivers@gmail.com` instead of `dipseth@gmail.com`
2. **Short-term**: Add a `MCP_USER_EMAIL` env var override that takes precedence over the registry-stored email
3. **Long-term**: When the API key lookup returns an email that has no credentials, check if credentials exist for other emails and either auto-link or surface a clear error saying "key is bound to X but credentials exist for Y"

## Reproduction

1. Have API key registered under `dipseth@gmail.com` in `~/.credentials/.user_api_keys.json`
2. OAuth authenticate as `sethrivers@gmail.com`
3. Restart server (or trigger OOM watchdog)
4. Reconnect MCP client
5. Any tool call fails with email mismatch

## Key Observation: LLM-Triggered Email Guess May Be the Root Cause

The bug appears to only surface **after the LLM incorrectly guesses an email address** for an auth call (e.g., calling `start_google_auth` with `dipseth@gmail.com` inferred from system username), and then the user re-authenticates with their real email (`sethrivers@gmail.com`).

**Investigate**: The incorrect `start_google_auth` call with the wrong email may be persisting that wrong email into the session state or API key registry, poisoning subsequent identity resolution even after the user successfully authenticates with the correct email. The auth flow may be:

1. LLM calls `start_google_auth` with guessed email `dipseth@gmail.com`
2. Server creates/updates session state or key binding for `dipseth@gmail.com`
3. User completes OAuth in browser as `sethrivers@gmail.com`
4. Credentials are stored under `sethrivers@gmail.com`, but the session/key identity remains `dipseth@gmail.com`
5. All subsequent calls resolve identity as `dipseth@gmail.com` and fail to find credentials

**The fix should ensure** that if OAuth completes with a different email than was originally passed to `start_google_auth`, the session identity and any key bindings are updated to match the actual authenticated Google account.

## Context

- Occurred on 2026-03-19
- Server crashed due to RSS exceeding 2048MB critical threshold
- After restart, session identity was wrong
- Previously working fine (suggesting the key registry or session state got corrupted during the crash)
