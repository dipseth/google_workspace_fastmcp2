# FastMCP 4 Phase 3 plan: per-principal state, cache hints, completion, tool auth

Prepared 2026-09-03 against FastMCP 4.0.1 as installed in `.venv`, on branch `feat/fastmcp-v4` (draft PR #73). Detail for Phase 3 of [fastmcp4_migration_plan.md](fastmcp4_migration_plan.md). Every API claim below was read out of the installed package, not the changelog.

## 0. Corrections to the premise

Verified against the code before planning; these change the shape of the work.

1. **Most `set_state` sites still work under 2026-07-28.** Of the ~30 `ctx.set_state` calls, the tag-based resource, Qdrant, template, and module-wrapper middleware sites are same-request hand-offs: `on_read_resource` stores, the registered resource function reads back in the same request, and `ctx.session_id` is stable within one request even when it is fresh per request. Only two are cross-request caches: `service_list_raw_{service}_{list_type}_{email}` (item reads reuse a prior list; misses fall back to a refetch at [tag_based_resource_middleware.py:880](../middleware/tag_based_resource_middleware.py#L880)) and `custom_client_id_{state}` at [context.py:1115](../auth/context.py#L1115). The real casualty is not `ctx.set_state` at all. It is the module-level `_session_store` dict in [auth/context.py](../auth/context.py) keyed by transport session id, which carries disabled tools, user email, auth provenance, payment verification, privacy mode, sampling config, and the client record.
2. **The shared API key does have a principal.** [sso_google_provider.py:245](../auth/sso_google_provider.py#L245) mints an `AccessToken` with `client_id="api-key-client"` and `sub="api-key-user"`, so `principal_components()` yields a principal. The problem is that every holder of the shared key maps to the same bucket, which is a collision, not an absence. A key-hash fallback produces the identical single bucket. Per-user API keys and Google tokeninfo tokens already carry the email as `sub`, so they isolate correctly.
3. **`UserSession` is injected into handlers, not middleware.** Tools, resources, and prompts get `session: UserSession` by dependency injection. `SessionToolFilteringMiddleware`, the payment and privacy middleware, and the sampling handler are middleware and must build the bucket themselves from `current_principal()` and the server's state store. FastMCP's `_current_user_session()` does exactly that but is private; we wrap it once.
4. **Cache hints are one constructor knob** (`FastMCP(cache_ttl=, cache_scope=)`), applied uniformly to `tools/list`, `prompts/list`, `resources/list`, `resources/templates/list`, `resources/read`, and `server/discover`. There is no decorator kwarg. Per-result override exists only by setting `ttl_ms`/`cache_scope` on the low-level result model, which FastMCP's `ResourceResult`/`ToolResult` do not expose. Because `resources/read` is covered, the TTL has to suit the most volatile resource, not the list endpoints.
5. **Tool-level `auth=` hides and denies; it does not step up.** Component checks at [server.py:879](../.venv/lib/python3.12/site-packages/fastmcp/server/server.py#L879) filter the tool from lists and make `call_tool` raise `NotFoundError`. Only the global `fastmcp.server.middleware.authorization.AuthMiddleware` raises `InsufficientScopeError` with the missing scopes, and in 4.0.1 that error reaches a `tools/call` as a plain JSON-RPC error whose message names the scopes. There is no HTTP 403 `WWW-Authenticate: insufficient_scope` on a tool call; the SDK only emits that for server-wide `required_scopes`. So an automatic client re-authorization is not wired end to end in 4.0.1. The scope step-up we can ship today is: catch the shortfall and return our existing url-mode elicitation carrying a targeted authorize link.
6. **`ctx.set_state` and `UserSession` share one store and Redis is safe for both.** `Context.set_state` writes to `fastmcp._state_store` with a built-in TTL (`_STATE_TTL_SECONDS`, confirm the value), so per-request orphan keys from stateless clients expire. `Session` writes carry no TTL, so the user bucket needs a ceiling from the store side.

## 1. Workstream A: per-principal state with `UserSession` (do first)

Goal: state that today lives in `_session_store` keyed by transport session id moves to the FastMCP state store keyed by the authenticated principal. Same code path for handshake and 2026-07-28 clients, survives replicas when the store is Redis.

### A1. Store wiring

- In [server.py:270](../server.py#L270), pass `session_state_store=`. When `settings.redis_io_url_string` is set, reuse the `RedisStore` plus `PrefixCollectionsWrapper` pattern from [server_middleware_setup.py:441](../middleware/server_middleware_setup.py#L441) with its own prefix (`gw-mcp-state`). Otherwise use `DiskStore` under `credentials_dir/fastmcp-state/` for single-container deploys (Glama and the prod CT have no Redis; the JSON file gave restart survival today and the memory store would lose it). `MemoryStore` only for tests.
- Wrap with `TTLClampWrapper(min_ttl=60, max_ttl=30d, missing_ttl=30d)` so `Session` writes get a retention ceiling and `ctx.set_state` writes keep their own TTL.
- Add `FASTMCP_STATE_STORE=redis|disk|memory` to settings with auto-detection defaulting as above; document in CONFIGURATION_GUIDE.

### A2. Helper module `auth/user_state.py`

- `user_bucket() -> Session | None`: wraps `fastmcp.server.sessions._current_user_session()`; returns `None` with no token. Pin to 4.0.1 in a comment and cover with a test so a private-API break is caught by CI.
- `principal_email() -> str | None`: reads `email`, then `sub`, from `get_access_token().claims`. This replaces the JWT, GitHub, GoogleProvider, and session-storage email walk in [auth/middleware.py:404-470](../auth/middleware.py#L404-L470) for every request that has a token. The OAuth-file fallback stays only for tokenless local dev.
- `is_shared_key() -> bool`: `claims.auth_method == AuthProvenance.API_KEY`.
- Shared key policy: one admin bucket by design. Privacy mode and sampling config already refuse `API_KEY` provenance and keep doing so. If a deployment wants multiple people on the shared key with separate state, register `SessionProvider` and have those clients pass `session_id: SessionId`; not in scope here.

### A3. Migrate keys, in this order

| Key | Writer | Reader | Change |
|---|---|---|---|
| `SESSION_DISABLED_TOOLS`, `minimal_startup_applied` | `manage_tools` scope=session ([server_tools.py:1085](../tools/server_tools.py#L1085)), `_apply_minimal_startup_for_session` | `SessionToolFilteringMiddleware.on_list_tools` / `on_call_tool` ([session_tool_filtering_middleware.py:918](../middleware/session_tool_filtering_middleware.py#L918)) | Read and write the user bucket. `on_call_tool` then blocks a modern client's direct call to a disabled tool, which is the bug in the 2026-09-02 plan-doc note. |
| `SAMPLING_CONFIG` | `/api/sampling-config` ([fastmcp_oauth_endpoints.py:2067](../auth/fastmcp_oauth_endpoints.py#L2067)), intro screen | `_get_session_sampling_config` ([session_sampling_handler.py:100](../middleware/session_sampling_handler.py#L100)) | Handler reads the bucket, then lazy-loads from the encrypted file by `principal_email()`. The route resolves the principal from its bearer token instead of `target_session`. |
| `PRIVACY_MODE`, `PRIVACY_ADDITIONAL_FIELDS` | `/api/privacy-mode`, intro screen | privacy middleware | Bucket. |
| `PAYMENT_VERIFIED`, `PAYMENT_VERIFIED_AT`, `PAYMENT_RECEIPT` | [payment/middleware.py:417](../middleware/payment/middleware.py#L417) | `_is_payment_verified` | Bucket. A paid principal stays paid across stateless requests, which is the intended behavior. |
| `CLIENT` record | `AuthMiddleware.on_request` / `on_initialize` | `client_capabilities`, persisted file | Bucket, one record per principal, last writer wins. |
| `USER_EMAIL`, `AUTH_PROVENANCE`, `GOOGLE_SUB` | `AuthMiddleware.on_call_tool` | everywhere | Derive from token claims per request via A2; stop storing. |
| `PER_USER_ENCRYPTION_KEY` | OAuth callback | sampling and credential decrypt | Decide: re-derive per request from the JWT (preferred), or store in the bucket only when the store is Redis over TLS. Do not write a Fernet key to the disk store. |

Each row is its own commit with a test. `store_session_data`/`get_session_data` stay as thin shims over the bucket during the migration so untouched call sites keep working, then get deleted.

### A4. The two cross-request `ctx.set_state` caches

- `service_list_raw_*`: move to the bucket under a `cache:` prefix with a stored timestamp and a 5-minute check on read. The refetch fallback already exists, so this is a performance change only.
- `custom_client_id_{state}`: key by the OAuth `state` string directly in the state store (`oauth-state:{state}`) with a 10-minute TTL. It was never per-session.

### A5. Retire

- `find_session_id_by_email`, `restore_session_tool_state_by_email`, `is_known_session`, `restore_session_tool_state`, the `?uuid=` resume path, `_processed_sessions`, and `AuthMiddleware._active_sessions`.
- `session_tool_states.json` becomes a one-time import: on the first request for a principal whose bucket is empty, copy `disabled_tools` from the most recent file entry with that email, then never read it again. Remove the writer, the lifespan persist hook at [server_lifespans.py:200](../lifespans/server_lifespans.py#L200), and `scripts/cleanup_session_states.py` one minor later.
- `tests/test_session_tool_state_persistence.py` is replaced by bucket tests.

### A6. Behavior change to call out

Handshake-era clients keep working, but state becomes per user rather than per connection. Two Claude Desktop windows on one account now share disabled tools and privacy mode. This matches what `restore_session_tool_state_by_email` already tried to do and is the intended semantics, so document it in the release notes rather than preserving per-connection state.

### A7. Tests

- In-process `Client(mcp)` negotiates 2026-07-28 by default; `Client(mcp, mode="legacy")` forces the handshake. Every test below runs under both.
- Disable a tool on connection 1, open connection 2 with the same token: `tools/list` omits it and `tools/call` is rejected.
- Different tokens do not see each other's disabled tools; shared key and an OAuth user are distinct buckets.
- Sampling config set through the route is used by `SessionAwareSamplingHandler` on a later request with no shared transport session.
- Payment verified on request N is honored on request N+1.
- A `task=True` tool reading the bucket in the Docket worker leg (`get_server()` is task-aware and the worker restores the token).

### A8. When

Immediately after #73 merges, as release 3.1.0. It touches `auth/context.py` and `auth/middleware.py` broadly; folding it into the draft PR would make the tests/client runs harder to attribute.

## 2. Workstream B: cache hints (half a day)

- `FastMCP(cache_ttl=30, cache_scope="private")` in [server.py:270](../server.py#L270). Private because `tools/list` varies by principal after Workstream A and by session before it. Thirty seconds because `resources/read` is hinted too: `user://current/email` flips after auth, `chat://digest` and Qdrant search results are live data, and the Gmail draft app reads drafts.
- A hinted server is inert unless the client passes `cache=` and negotiated 2026-07-28, so there is no legacy risk.
- Server-side `ResponseCachingMiddleware` stays as configured (list_prompts only). Its partition key is a hash of the access token, which after Workstream A is the same boundary as the client-side private scope.
- Test: `Client(mcp, cache=CacheConfig(...))` lists tools twice and the server sees one call.
- Fix Phase 3 item 3 in the migration plan doc: the API is constructor-level, not per-tool kwargs, and it covers reads.

## 3. Workstream C: argument completion (one day)

- New `resources/completions.py` registering one `@mcp.completion` handler. Registering it declares the `completions` capability; works on both eras.
- `ResourceTemplateReference` for `chat://digest/space/{space_code}{?hours,limit}` ([chat_digest_resources.py:259](../resources/chat_digest_resources.py#L259)): `space_code` from the user's spaces, `hours` from `["1","4","12","24","48","168"]`, `limit` from `["5","10","25","50"]`.
- `PromptReference`: `smart_contextual_chat_card.target_space` from spaces, `card_purpose` from the documented set; `professional_chat_dashboard` and the gsheets prompt arguments get static lists.
- Completion fires per keystroke, so cache the space list in the user bucket for five minutes (`cache:chat_spaces`). Identity comes from `principal_email()`; `AuthMiddleware.on_call_tool` does not run for `completion/complete`, so nothing else resolves the user there.
- Prefix-filter on `argument.value`, cap at 100, return `[]` on any auth or API failure. Never raise from the handler.
- Test with `client.complete()` for one template and one prompt.

## 4. Workstream D: tool-level auth and scope step-up

### D1. Roles for admin gating (half a day)

- Add a `roles` claim in `_FastMCPAccessToken` at [sso_google_provider.py:250](../auth/sso_google_provider.py#L250): `["admin"]` for the shared key, `["user"]` for per-user keys, OAuth JWTs, and tokeninfo tokens.
- `ADMIN = require_roles("admin", extract=lambda c: c.get("roles", []))` in `auth/access_control.py`.
- Apply `auth=ADMIN` to tools that are admin-only in full. `manage_tools` is not one: its `session` scope is for everyone, so it keeps an in-body check that reads the same `roles` claim, replacing the `provenance == API_KEY` test at [server_tools.py:1538](../tools/server_tools.py#L1538). The `/api/*` routes are Starlette routes, not MCP components, so tool-level auth does not apply; they switch to the same claim read.
- `require_roles` denials are plain `AuthorizationError`, which is right for admin: there is nothing to step up to.

### D2. Per-service scopes and the Photos step-up (two days)

- Make the JWT `scopes` reflect granted token groups instead of always `comprehensive_scopes`: workspace scopes after the Workspace consent, Photos scopes only once `token_groups/photos/` holds credentials for that email. Both mint sites in `sso_google_provider.py` and the exchange path in `google_auth.py` change.
- Tag Photos tools `photos` and add `AuthMiddleware(auth=restrict_tag("photos", scopes=PHOTOS_SCOPES))` from `fastmcp.server.middleware.authorization`. A caller without the Photos group gets `InsufficientScopeError` naming exactly the missing scopes.
- Bridge the step-up ourselves, since 4.0.1 delivers that error as a plain JSON-RPC error: an outer middleware catches `InsufficientScopeError` on `tools/call` and returns the existing url-mode or form-mode elicitation from `tools/elicitation.py` carrying a Photos-only authorize URL (token group `photos`, services preselected). Handshake clients get the pushed `elicitation/create`; 2026-07-28 clients get `InputRequiredResult`; clients with no elicitation get the clickable link. This replaces the `/auth/services/select` detour that does not preselect Photos.
- Fix the preselect bug in the selection page regardless, since the page stays as the fallback.
- Verify live against `riversunlimited-local` on :8002 with Claude Code and Claude Desktop: the Photos tool call should surface the link, and a later call should succeed with no re-prompt. Watch for whether either client reacts to the scope text on its own.

## 5. Sequencing and releases

| Release | Contents | Estimate |
|---|---|---|
| 3.1.0 | Workstream A, Workstream B, plan-doc corrections | 4 days |
| 3.2.0 | Workstream C, D1 | 1.5 days |
| 3.3.0 | D2 | 2 days |

Each bumps `pyproject.toml` and `uv.lock` together. Regenerate plugin skills if any tool description changes (`manage_tools` describes session scope). Run `ruff check .` and `ruff format --check .` before each push.

## 6. Open questions

- Confirm `_STATE_TTL_SECONDS` on `Context` so the ceiling in A1 does not undercut it.
- `PER_USER_ENCRYPTION_KEY` placement (A3): re-derive from the JWT or store in Redis only.
- Whether Glama's container can mount a persistent path for the disk store; if not, per-principal state there resets on redeploy, which is still better than today's per-request reset for modern clients.
- Whether Claude Code or Claude.ai act on the `insufficient scope` error text without our bridge. If they do, D2's bridge can become a fallback only.

## 7. Implementation status (2026-09-03, branch `feat/fastmcp-v4-phase3`)

### Workstream A — done, with three deviations from §1

- **Bucket principal is the identity, not FastMCP's triple.** `auth/user_state.py` builds the bucket over FastMCP's public `Session` key layout (`session:{sha256(principal)}:_user`, state under `"state"`) but with its own principal string: `user:<email>` for OAuth JWTs, per-user keys and tokeninfo tokens, one `apikey:shared` admin bucket, one anonymous bucket with no token. Two reasons, found while wiring it: FastMCP's `current_principal()` includes the OAuth `client_id`, which is the DCR registration and differs between Claude Desktop, Claude Code and claude.ai, so one person would get one bucket per client; and the OAuth success page and `/api/*` routes have to address the bucket by email with no MCP bearer token in hand. `_current_user_session()` is therefore not wrapped; `tests/test_user_state.py::test_fastmcp_private_layout_pins` pins the two layout constants instead.
- **The sampling `api_key` never enters the state store.** The bucket holds only `{model, api_base, has_api_key}`; the handler decrypts the per-user file with key material the request carries (per-user key bearer, or the OAuth `sub` from claims) and caches the result in-process per principal. When nothing on the request can decrypt it, the handler routes by the bucket's model and leaves credentials to the provider. This also answers the `PER_USER_ENCRYPTION_KEY` open question: it is not written to the store; the per-user-key path already re-derives it from the bearer each request, and the OAuth-callback stash stays in memory.
- **`AuthMiddleware._active_sessions` stays.** It is request-scoped plumbing (request id → transport session id) for the same-request hand-offs, not cross-request state, so retiring it bought nothing and touched ~40 sites.

Retired as planned: `find_session_id_by_email`, `restore_session_tool_state_by_email`, `is_known_session`, `restore_session_tool_state`, the `?uuid=` resume path, `_processed_sessions`, the `*_sync` disabled-tool helpers, `set/get_effective_session_id`, the persist hook in `session_state_lifespan`, `tests/test_session_tool_state_persistence.py`. `session_tool_states.json` is imported once per user (newest entry for their email) and never written. `scripts/cleanup_session_states.py` is left for the next minor.

Store wiring: `middleware/state_store.py` picks Redis (`PrefixCollectionsWrapper` prefix `gw-mcp-state`) or a file-tree store under `credentials_dir/fastmcp-state/` (`DiskStore` needs the `diskcache` extra, which is not installed; `FileTreeStore` honors TTLs and needs nothing), wrapped in `TTLClampWrapper(60 s, 30 d, missing=30 d)`. `Context._STATE_TTL_SECONDS` is 86400, inside the clamp. `FASTMCP_STATE_STORE` / `FASTMCP_STATE_DIR` documented in `documentation/config/CONFIGURATION_GUIDE.md`.

Other changes that fell out: `SessionToolFilteringMiddleware.on_call_tool` raises `ToolError` (a bare `ValueError` from middleware is masked to "Internal server error" by the 2026-07-28 runner); the two copies of `/api/privacy-mode` and `/api/sampling-config` collapsed into `setup_config_api_routes`, which the legacy registrar now calls too (so `/api/models` and `/api/revoke` exist in legacy mode); `GOOGLE_SUB` is stashed on the current request's session instead of "the most recent session"; `custom_client_id_{state}` lives under `oauth-state:{state}` with a 10-minute TTL. Follow-up not in scope: the privacy vault registry is still keyed by transport session, so `[PRIVATE:token_N]` references do not resolve across 2026-07-28 requests.

Tests: `tests/test_user_state.py` (both eras: disable on one connection hides and blocks on another; principals isolated; shared key distinct; minimal startup once per user; legacy import; sampling config on a later request; payment on request N+1; cache hints) plus the updated payment tests. The `task=True` worker-leg test is not written.

### Workstream B — done

`FastMCP(cache_ttl=30, cache_scope="private")` in `server.py`; `test_cache_hints_let_a_modern_client_skip_refetch` shows a `Client(mcp, cache=CacheConfig())` listing twice with one server call, and a legacy client with two.

### Workstream C — done

`resources/completions.py`, `tests/test_completions.py` (both eras). Space listing cached five minutes in the bucket-side cache (`cache:{principal}:chat_spaces`).

### Workstream D1 — done

`auth/access_control.py` gained `ADMIN` (`require_roles("admin", extract=roles_from_claims)`), `is_admin()` (claim first, shared-key provenance fallback for pre-3.1.0 JWTs), `roles_for_provenance()`; `tests/test_roles.py` covers hide-and-deny on both eras. The claim is minted at the four token sites in `sso_google_provider.py` (shared key → `["admin"]`; per-user key, tokeninfo and OAuth JWT → `["user"]`, the JWT's verified claims widened after validation). `set_privacy_mode` reads `is_admin()`. No tool turned out to be admin-only in full, so `auth=ADMIN` is applied nowhere yet; `manage_tools(scope="global")` is deliberately left open because on a single-user OAuth deploy the owner is not the shared key. The `/api/*` routes keep rejecting shared-key *sessions* by provenance: they have no token context of their own.

### Workstream D2 — done, verified live

- Token scopes reflect token groups: `auth/scope_step_up.py::scopes_for_principal` adds the Photos scopes (`photos_basic`, the `photoslibrary.*` URLs) only when `credentials/token_groups/photos/<email>_credentials.{json,enc}` exists; the shared key always carries them. Applied at all four mint sites; the OAuth JWT's `scopes` are widened on every `load_access_token`, so the consent lands on the very next request.
- **Deviation:** the check is our own `ScopeStepUpMiddleware`, not `AuthMiddleware(auth=restrict_tag("photos", ...))`. FastMCP's global auth middleware also filters `tools/list` by the same check, which would hide the Photos tools from everyone who has not consented yet — the client could never make the call that triggers the step-up. Ours runs on `tools/call` only, reads the tool's tags through `get_tool`, and raises the same `InsufficientScopeError` shape internally.
- Bridge: on a shortfall the middleware builds a Photos-only authorize URL (`initiate_oauth_flow(selected_services=["photos"], show_service_selection=False)`) and answers with `prompt_for_oauth`: url-mode `InputRequiredResult` for 2026-07-28 clients, a pushed `elicitation/create` for handshake clients (on `completed` the token is widened in place and the tool runs), the link in a `ToolError` for clients with no elicitation. A re-run whose token still lacks Photos never re-prompts: it returns the link (`accept` without a stored credential) or the cancellation.
- The selection page now honors the preselection `start_google_auth` always computed and never passed: `initiate_oauth_flow(preselected_services=…)` → `_service_selection_cache[state]["preselected_services"]` → `generate_service_selection_html(preselected_services=…)`.
- Tests: `tests/test_scope_step_up.py` (scope minting on both credential file kinds; pass-through for non-Photos tools and tokenless calls; suspend with the Photos-only link and request state; link-in-error; handshake completion; declined and unfinished re-run do not loop).
- **Verified live (2026-09-03, `riversunlimited-local` on :8002, Claude Code under Code Mode, Redis state store).** With `credentials/token_groups/photos/` empty, `list_photos_albums` for the signed-in account produced the url-mode ask; the elicitation hook opened the Photos-only authorize link; the consent was stored as `token_groups/photos/<email>_credentials.enc`; the next call ran (`success: true`, zero app-created albums) with no re-prompt. The live run caught one bug the unit tests could not: a middleware must return FastMCP's `InputRequiredToolResult` wrapper, not the bare `InputRequiredResult` a tool body returns — the bare value fails in the Code Mode bridge (`structured_content`) and at the wire handler. Whether Claude Code reacts to the `insufficient scope` text on its own was not observable: the bridge answers first.

### Release

Everything above is one branch and one version bump (3.0.0 → 3.1.0). The plan's three-release split (3.1.0 / 3.2.0 / 3.3.0) was not reproduced as separate branches; if you want it, split at the workstream boundaries listed here.
