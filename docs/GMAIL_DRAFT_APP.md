# Gmail draft preview app

An MCP App (`FastMCPApp`) that renders a Gmail draft as an interactive card in
the chat: the fully rendered email in a sandboxed iframe, editable To/Cc/Bcc
fields, and **Send** / **Save draft** / **Discard** buttons.

Source: [`gmail/draft_app.py`](../gmail/draft_app.py). Registered in
[`server.py`](../server.py) alongside the other app providers, behind
`ENABLE_APP_PROVIDERS=true`.

## Tool surface

| Tool | Visibility | Purpose |
|---|---|---|
| `preview_gmail_draft` | model | Entry point. Renders the card. Takes an existing `draft_id`, or `subject`/`body`/`html_body`/`email_spec` to create the draft first. |
| `gmail_draft_send` | app only | Applies recipient edits, then `drafts().send`. |
| `gmail_draft_save` | app only | Applies recipient edits via `drafts().update`. Does not send. |
| `gmail_draft_discard` | app only | `drafts().delete`. |

The three backend tools are invisible to the model — only the card can call
them, addressed through FastMCP's hashed backend names.

## Preview fidelity

The draft is fetched with `format="raw"` and parsed with `email`, so the card
previews the *exact* `text/html` MIME part Gmail will deliver. MJML output
survives verbatim: doctype, VML namespaces, `<style>` blocks, `@media` queries
and `<!--[if mso]>` conditionals are never rewritten or sanitised.

Two deliberate transformations:

- **`cid:` → `data:`** — inline images are base64-inlined so they resolve
  inside the iframe (images over 200 KB are skipped and the card says so).
- **Charset guarantee** — bare fragments get wrapped with `<meta charset>` so
  emoji and non-Latin subjects don't mangle. Documents that already declare a
  charset are passed through untouched.

Everything else degrades visibly rather than silently: unresolved `cid:` refs,
skipped image inlining and oversized-payload truncation each render a banner
inside the preview and a note under it. The draft itself is never modified by
previewing.

**Scripts don't run.** The iframe is sandboxed without `allow-scripts`, which
matches Gmail's own behaviour (Gmail strips `<script>`), so the preview is both
safe and honest. Only popups are allowed, so links stay clickable.

**Remote images.** The Prefab renderer's default CSP only permits
`cdn.jsdelivr.net`. `_widen_preview_csp()` patches the entry tool's
`meta["ui"]["csp"].resourceDomains` to add `https:` and `data:` after
registration, so email images from arbitrary CDNs load.

## Recipient edits are lossless

Editing To/Cc/Bcc rewrites only those headers on the parsed MIME message and
re-uploads via `drafts().update`. The body, attachments, transfer encodings and
`threadId` are preserved byte-for-byte — no re-render, no lossy round-trip.

## Allow list

`gmail_draft_send` runs the same `GMAIL_ALLOW_LIST` check as
`send_gmail_message`. Rather than eliciting, it returns
`needs_confirm: true` and the card reveals a **Send anyway** button — the click
is the human-in-the-loop confirmation.

## Testing it in a real client

MCP Apps only render in clients that advertise the
`io.modelcontextprotocol/ui` extension. **Claude Desktop** and the **MCP
Inspector** do; VS Code Copilot does not.

App entry tools are hidden when Code Mode is on (this is true of the existing
`Approval` / `Choice` / `ToolManager` apps too), so run with:

```bash
MCP_TRANSPORT=http ENABLE_CODE_MODE=false ENABLE_APP_PROVIDERS=true \
  uv run python server.py
```

Then point the client at `https://localhost:8002/mcp` and ask it to draft an
email — for example *"draft an MJML email to me with a hero, a button and a
footer, then preview it"*. The model calls `draft_gmail_message` followed by
`preview_gmail_draft` (or `preview_gmail_draft` alone with an `email_spec`).

What to check in the card:

1. The preview matches what Gmail shows for the same draft (open it in Gmail
   → Drafts side by side).
2. Editing **To** and pressing **Save draft** updates the draft in Gmail while
   leaving the body and any attachments intact.
3. **Discard** asks for confirmation, then the draft disappears from Gmail.
4. **Send** delivers the email, and a non-allow-listed recipient surfaces the
   **Send anyway** path instead of sending.
