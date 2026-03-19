import html
from typing import Any, Dict


def generate_error_html(title: str, message: str) -> str:
    """Generate a simple error page HTML."""
    return f"""<!DOCTYPE html><html><head><title>{html.escape(title)}</title>
    <style>body{{font-family:sans-serif;text-align:center;padding:60px}}
    .error{{color:#dc3545;font-size:48px}}</style></head><body>
    <div class="error">❌</div><h1>{html.escape(title)}</h1>
    <p>{html.escape(message)}</p><p>Please try again.</p></body></html>"""


def generate_access_denied_html(user_email: str) -> str:
    """Generate access denied HTML."""
    return f"""<!DOCTYPE html><html><head><title>Access Denied</title>
    <style>body{{font-family:sans-serif;text-align:center;padding:60px}}
    h1{{color:#dc3545}}</style></head><body>
    <h1>Access Denied</h1><p>User <b>{html.escape(user_email)}</b> is not authorized.</p>
    </body></html>"""


def generate_success_html(
    user_email: str,
    api_key_section: str = "",
    security_viz_section: str = "",
    envelope_inventory_section: str = "",
    revoke_section: str = "",
    page_mode: str = "authenticated",
    requested_email: str = "",
) -> str:
    """Generate success page HTML.

    page_mode controls header text:
      "authenticated" — green checkmark, "Authentication Successful!"
      "status_check"  — blue info icon, "Credential Status"

    requested_email: LLM-guessed email from start_google_auth (if any).
      Shows match/mismatch indicator when provided.
    """
    if page_mode == "status_check":
        _icon = '<div class="success-icon" style="filter:hue-rotate(200deg)">&#x2139;&#xFE0F;</div>'
        _title_color = "#007bff"
        _title_text = "Credential Status"
        _saved_text = "<b>&#x1F50D; Existing credentials verified</b><br>All encrypted envelopes intact."
        _page_title = "Credential Status"
    else:
        _icon = '<div class="success-icon">&#x2705;</div>'
        _title_color = "#28a745"
        _title_text = "Authentication Successful!"
        _saved_text = "<b>&#x1F510; Credentials Saved!</b><br>Ready to use."
        _page_title = "Authentication Successful"

    # Build requested email match/mismatch indicator
    _requested_section = ""
    if requested_email:
        _req_norm = requested_email.lower().strip()
        _auth_norm = user_email.lower().strip()
        if _req_norm == _auth_norm:
            _requested_section = (
                '<div style="background:#d4edda;color:#155724;padding:10px 15px;border-radius:8px;'
                'margin:10px 0;border:1px solid #c3e6cb;font-size:13px">'
                f'<span style="background:#28a745;color:white;padding:2px 8px;border-radius:4px;'
                f'font-size:11px;font-weight:600;margin-right:6px">MATCHES</span>'
                f'Requested: <code>{html.escape(requested_email)}</code></div>'
            )
        else:
            _requested_section = (
                '<div style="background:#fff3cd;color:#856404;padding:10px 15px;border-radius:8px;'
                'margin:10px 0;border:1px solid #ffc107;font-size:13px">'
                f'<span style="background:#ffc107;color:#856404;padding:2px 8px;border-radius:4px;'
                f'font-size:11px;font-weight:600;margin-right:6px">CORRECTED</span>'
                f'Originally requested: <code>{html.escape(requested_email)}</code>'
                f'<br><small style="color:#6c757d">Session identity updated to match your actual Google account</small></div>'
            )

    return f"""<!DOCTYPE html><html><head><title>{_page_title}</title>
    <style>
        body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
              margin:0;background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);
              min-height:100vh;display:flex;align-items:center;justify-content:center}}
        .container{{max-width:560px;background:white;border-radius:20px;padding:50px;
                   text-align:center;box-shadow:0 20px 40px rgba(0,0,0,0.1)}}
        .success-icon{{font-size:72px;margin-bottom:20px}}
        h1{{color:#28a745;margin-bottom:10px;font-size:32px}}
        .email{{color:#6c757d;font-size:18px;margin:20px 0}}
        .saved{{background:#d4edda;color:#155724;padding:15px;border-radius:8px;margin:20px 0;border:1px solid #c3e6cb}}
        .api-key{{background:#fff3cd;color:#856404;padding:15px;border-radius:8px;margin:20px 0;border:1px solid #ffc107;text-align:left}}
        .api-key small{{display:block;margin-bottom:10px}}
        .key-value{{font-family:monospace;font-size:13px;background:#f8f9fa;padding:10px;border-radius:4px;
                   word-break:break-all;margin:10px 0;user-select:all;border:1px solid #dee2e6}}
        .key-value.hidden{{filter:blur(8px);user-select:none;pointer-events:none}}
        .api-key button{{background:#856404;color:white;border:none;padding:8px 16px;border-radius:4px;cursor:pointer;font-size:13px}}
        .api-key button:hover{{background:#6c5200}}
        .linked-accounts{{background:#e8f4fd;color:#0c5460;padding:15px;border-radius:8px;margin:20px 0;border:1px solid #bee5eb;text-align:left}}
        .linked-accounts small{{display:block;margin-bottom:8px}}
        .linked-accounts ul{{margin:8px 0 0 0;padding-left:20px}}
        .linked-accounts li{{margin:4px 0;font-family:monospace;font-size:14px}}
        .linked-accounts.solo{{background:#f8f9fa;color:#6c757d;border-color:#dee2e6}}
        .services{{background:#f8f9fa;padding:20px;border-radius:10px;margin:20px 0}}
        /* Security visualization */
        .sec-panel{{background:linear-gradient(135deg,#1a1a2e 0%,#16213e 100%);color:#e0e0e0;
                   padding:24px;border-radius:12px;margin:24px 0;text-align:left}}
        .sec-title{{font-size:16px;font-weight:700;color:#fff;margin-bottom:4px}}
        .sec-subtitle{{font-size:11px;color:#8892b0;margin-bottom:16px}}
        .sec-diagram{{display:flex;gap:8px;align-items:stretch;margin-bottom:16px}}
        .sec-col{{flex:1;display:flex;flex-direction:column;gap:6px}}
        .sec-col-label{{font-size:9px;text-transform:uppercase;letter-spacing:1px;color:#64ffda;
                       font-weight:600;margin-bottom:4px;text-align:center}}
        .sec-node{{background:rgba(255,255,255,0.06);border:1px solid rgba(255,255,255,0.1);
                  border-radius:8px;padding:8px 6px;text-align:center;display:flex;
                  flex-direction:column;align-items:center;gap:2px}}
        .sec-node.current{{border-color:#64ffda;background:rgba(100,255,218,0.08)}}
        .sec-icon{{font-size:18px}}
        .sec-label{{font-size:9px;font-family:monospace;word-break:break-all;line-height:1.2;color:#ccd6f6}}
        .sec-method{{font-size:7px;padding:1px 5px;border-radius:3px;margin-top:2px;
                    background:rgba(255,255,255,0.08);color:#8892b0}}
        .sec-method.oauth{{background:rgba(100,255,218,0.12);color:#64ffda}}
        .sec-method.session{{background:rgba(255,183,77,0.12);color:#ffb74d}}
        .sec-method.both{{background:rgba(129,212,250,0.12);color:#81d4fa}}
        .sec-method.api_key{{background:rgba(206,147,255,0.12);color:#ce93ff}}
        .sec-col-keys{{flex:0.7;justify-content:center;gap:8px}}
        .sec-flow-row{{display:flex;align-items:center;gap:3px;justify-content:center}}
        .sec-flow-row.current .sec-key-badge{{background:#64ffda;color:#1a1a2e}}
        .sec-key-badge{{background:rgba(255,255,255,0.12);color:#ccd6f6;font-size:8px;font-weight:600;
                      padding:3px 6px;border-radius:4px;white-space:nowrap}}
        .sec-arrow{{width:28px;height:12px;color:#64ffda;flex-shrink:0}}
        .sec-cek-wrap{{font-size:8px;color:#8892b0;white-space:nowrap}}
        .sec-col-envelope{{flex:1.1}}
        .sec-envelope{{background:rgba(255,255,255,0.04);border:1.5px solid #64ffda;
                      border-radius:10px;padding:10px;display:flex;flex-direction:column;gap:5px}}
        .sec-env-header{{font-size:10px;font-weight:700;color:#64ffda;text-align:center;
                        letter-spacing:1px;text-transform:uppercase}}
        .sec-env-row{{text-align:center}}
        .sec-env-badge{{display:inline-block;font-size:9px;padding:3px 8px;border-radius:4px;
                      font-weight:500}}
        .sec-env-badge.rec{{background:rgba(255,183,77,0.15);color:#ffb74d}}
        .sec-env-badge.data{{background:rgba(100,255,218,0.1);color:#64ffda}}
        .sec-env-badge.hmac{{background:rgba(129,212,250,0.1);color:#81d4fa}}
        .sec-features{{display:grid;grid-template-columns:1fr 1fr;gap:6px}}
        .sec-feat{{font-size:10px;color:#8892b0;display:flex;align-items:start;gap:5px;line-height:1.3}}
        .sec-feat span:first-child{{flex-shrink:0}}
        .sec-feat b{{color:#ccd6f6}}
    </style></head><body><div class="container">
        {_icon}
        <h1 style="color:{_title_color}">{_title_text}</h1>
        <div class="email">Authenticated: <b>{html.escape(user_email)}</b></div>
        {_requested_section}
        <div class="saved">{_saved_text}</div>
        {api_key_section}
        {security_viz_section}
        {envelope_inventory_section}
        {revoke_section}
        <div class="services"><h3>&#x1F680; Services Available</h3>
            <div>Drive &middot; Gmail &middot; Calendar &middot; Docs &middot; Sheets &middot; Slides &middot; Photos &middot; Chat &middot; Forms</div>
        </div>
        <p>You can close this window and return to your application.</p>
    </div></body></html>"""


def build_api_key_section(
    user_email: str,
    user_api_key: str | None,
    user_api_key_exists: bool,
) -> str:
    """Build the API key + linked accounts HTML for the OAuth success page."""
    accessible_section = ""
    if user_api_key or user_api_key_exists:
        try:
            from auth.user_api_keys import get_accessible_emails

            accessible = get_accessible_emails(user_email)
            linked = sorted(e for e in accessible if e != user_email.lower().strip())
            if linked:
                linked_items = "".join(f"<li>{html.escape(e)}</li>" for e in linked)
                accessible_section = f"""
                <div class="linked-accounts">
                    <b>🔗 Linked Accounts</b>
                    <small>This key can also access credentials for:</small>
                    <ul>{linked_items}</ul>
                </div>"""
            else:
                accessible_section = """
                <div class="linked-accounts solo">
                    <b>🔒 Single Account</b>
                    <small>This key only has access to the email above.<br>
                    Authenticate additional emails in the same session to link them.</small>
                </div>"""
        except Exception:
            pass

    if user_api_key:
        # Key is being rendered — mark it as revealed so future
        # re-auths won't force-regenerate and invalidate it.
        try:
            from auth.user_api_keys import mark_key_revealed

            mark_key_revealed(user_email)
        except Exception:
            pass
        return f"""
        <div class="api-key">
            <b>🔑 Your Personal API Key</b><br>
            <small>Use this as a Bearer token to connect without re-authenticating.<br>
            This key is shown <b>once</b> — save it now!</small>
            <div class="key-value hidden" id="apiKey">{html.escape(user_api_key)}</div>
            <button id="revealBtn" onclick="document.getElementById('apiKey').classList.remove('hidden');this.style.display='none';document.getElementById('copyBtn').style.display=''">
                Click to Reveal Key
            </button>
            <button id="copyBtn" style="display:none" onclick="navigator.clipboard.writeText(document.getElementById('apiKey').textContent).then(()=>this.textContent='Copied!')">
                Copy to Clipboard
            </button>
        </div>
        {accessible_section}"""
    elif user_api_key_exists:
        return f"""
        <div class="api-key" style="background:#d1ecf1;color:#0c5460;border-color:#bee5eb">
            <b>🔑 API Key Active</b><br>
            <small>Your existing per-user API key is still valid.<br>
            Credentials have been refreshed — no need to update your key.</small>
        </div>
        {accessible_section}"""
    return ""


def build_security_viz_section(user_email: str) -> str:
    """Build the security visualization HTML for the OAuth success page."""
    import json as _json
    from pathlib import Path

    from config.settings import settings

    num_recipients = 0
    has_hmac = False
    is_encrypted = False
    try:
        from auth.google_auth import _normalize_email

        safe_email = _normalize_email(user_email).replace("@", "_at_").replace(".", "_")
        enc_path = Path(settings.credentials_dir) / f"{safe_email}_credentials.enc"
        if enc_path.exists():
            is_encrypted = True
            try:
                _env = _json.load(open(enc_path))
                num_recipients = len(_env.get("recipients", {}))
                has_hmac = "hmac" in _env
            except (ValueError, KeyError):
                num_recipients = 1
                has_hmac = False
    except Exception:
        pass

    if not is_encrypted:
        return ""

    _cur = user_email.lower().strip()
    _all_emails = [_cur]
    try:
        from auth.user_api_keys import get_accessible_emails

        _all_emails = sorted(get_accessible_emails(_cur))
    except Exception:
        pass

    try:
        from auth.user_api_keys import get_link_method
    except Exception:

        def get_link_method(a, b):
            return ""

    _recipient_nodes = ""
    for em in _all_emails:
        _is_current = em == _cur
        _highlight = "current" if _is_current else ""
        _method_badge = ""
        if not _is_current:
            _m = get_link_method(_cur, em)
            if _m == "oauth":
                _method_badge = '<span class="sec-method oauth">via OAuth</span>'
            elif _m == "api_key":
                _method_badge = '<span class="sec-method api_key">via API key</span>'
            elif _m == "session":
                _method_badge = '<span class="sec-method session">via session</span>'
            elif _m == "both":
                _method_badge = '<span class="sec-method both">OAuth + session</span>'
            else:
                _method_badge = '<span class="sec-method">linked</span>'
        _recipient_nodes += f'<div class="sec-node sec-user {_highlight}"><span class="sec-icon">👤</span><span class="sec-label">{html.escape(em)}</span>{_method_badge}</div>'

    _key_lines = ""
    for em in _all_emails:
        _cls = "current" if (em == _cur) else ""
        _key_lines += f'<div class="sec-flow-row {_cls}"><div class="sec-key-badge">🔑 Key</div><svg class="sec-arrow" viewBox="0 0 40 12"><path d="M0 6h32l-5-4M32 6l-5 4" stroke="currentColor" stroke-width="1.5" fill="none"/></svg><div class="sec-cek-wrap">Wrapped CEK</div></div>'

    _subtitle = (
        "Your Google Workspace credentials are protected by multi-recipient envelope encryption"
        if num_recipients > 1
        else "Your Google Workspace credentials are protected by split-key encryption"
    )

    return f"""
    <div class="sec-panel">
        <div class="sec-title">🛡️ Credential Security Model</div>
        <div class="sec-subtitle">{_subtitle}</div>
        <div class="sec-diagram">
            <div class="sec-col sec-col-users">
                <div class="sec-col-label">Authorized Users</div>
                {_recipient_nodes}
            </div>
            <div class="sec-col sec-col-keys">
                <div class="sec-col-label">Key Wrapping</div>
                {_key_lines}
            </div>
            <div class="sec-col sec-col-envelope">
                <div class="sec-col-label">Encrypted Envelope</div>
                <div class="sec-envelope">
                    <div class="sec-env-header">Sealed Envelope</div>
                    <div class="sec-env-row"><span class="sec-env-badge rec">🔐 {num_recipients} Wrapped CEK(s)</span></div>
                    <div class="sec-env-row"><span class="sec-env-badge data">🔒 Gmail · Drive · Calendar · Docs · Sheets</span></div>
                    <div class="sec-env-row"><span class="sec-env-badge hmac">{"✅" if has_hmac else "⚠️"} HMAC Integrity Seal</span></div>
                </div>
            </div>
        </div>
        <div class="sec-features">
            <div class="sec-feat"><span>🔀</span> Split-Key: requires <b>your key + server secret</b></div>
            <div class="sec-feat"><span>🚫</span> Server alone <b>cannot</b> decrypt your credentials</div>
            <div class="sec-feat"><span>🔗</span> Link accounts via <b>OAuth</b>, <b>session</b>, or <b>API key</b></div>
            <div class="sec-feat"><span>🛡️</span> HMAC detects tampering or unauthorized changes</div>
        </div>
    </div>"""


def build_envelope_inventory_section(user_email: str) -> str:
    """Build the envelope inventory HTML panel showing encrypted file metadata."""
    try:
        from auth.context import get_auth_middleware

        auth_mw = get_auth_middleware()
        if not auth_mw:
            return ""
        inventory = auth_mw.get_envelope_inventory(user_email)
    except Exception:
        return ""

    if not inventory:
        return ""

    rows = ""
    for item in inventory:
        version = html.escape(str(item["version"])) if item["version"] else "—"
        enc_type = html.escape(str(item["enc_type"])) if item["enc_type"] else "—"
        hmac_badge = (
            '<span style="color:#64ffda">&#x2705;</span>'
            if item["has_hmac"]
            else '<span style="color:#ff6b6b">&#x26A0;&#xFE0F;</span>'
        )
        size_kb = item["file_size"] / 1024
        size_str = f"{size_kb:.1f} KB" if size_kb >= 1 else f"{item['file_size']} B"
        # Calculate age
        age_str = ""
        try:
            from datetime import datetime, timezone

            modified = datetime.fromisoformat(item["last_modified"])
            delta = datetime.now(timezone.utc) - modified
            if delta.days > 0:
                age_str = f"{delta.days}d ago"
            elif delta.seconds >= 3600:
                age_str = f"{delta.seconds // 3600}h ago"
            else:
                age_str = f"{max(1, delta.seconds // 60)}m ago"
        except Exception:
            age_str = "—"

        # Token expiry display
        expiry_str = "—"
        try:
            from datetime import datetime, timezone

            raw_expiry = item.get("token_expiry")
            if raw_expiry:
                expiry_dt = datetime.fromisoformat(raw_expiry)
                now = datetime.now(timezone.utc)
                # Make expiry tz-aware if naive (assume UTC)
                if expiry_dt.tzinfo is None:
                    expiry_dt = expiry_dt.replace(tzinfo=timezone.utc)
                delta_exp = expiry_dt - now
                if delta_exp.total_seconds() <= 0:
                    expiry_str = '<span style="color:#ff6b6b">expired</span>'
                elif delta_exp.total_seconds() < 3600:
                    expiry_str = f'<span style="color:#ffd93d">{int(delta_exp.total_seconds() // 60)}m</span>'
                else:
                    expiry_str = f'<span style="color:#64ffda">{int(delta_exp.total_seconds() // 3600)}h</span>'
        except Exception:
            pass

        rows += f"""<tr>
            <td style="padding:6px 8px;border-bottom:1px solid rgba(255,255,255,0.06)">
                {html.escape(item["label"])}</td>
            <td style="padding:6px 8px;border-bottom:1px solid rgba(255,255,255,0.06);
                font-family:monospace;font-size:11px">v{version}</td>
            <td style="padding:6px 8px;border-bottom:1px solid rgba(255,255,255,0.06);
                font-family:monospace;font-size:11px">{enc_type}</td>
            <td style="padding:6px 8px;border-bottom:1px solid rgba(255,255,255,0.06);
                text-align:center">{item["recipient_count"]}</td>
            <td style="padding:6px 8px;border-bottom:1px solid rgba(255,255,255,0.06);
                text-align:center">{hmac_badge}</td>
            <td style="padding:6px 8px;border-bottom:1px solid rgba(255,255,255,0.06);
                font-size:11px;color:#8892b0">{size_str}</td>
            <td style="padding:6px 8px;border-bottom:1px solid rgba(255,255,255,0.06);
                font-size:11px;color:#8892b0">{age_str}</td>
            <td style="padding:6px 8px;border-bottom:1px solid rgba(255,255,255,0.06);
                font-size:11px;text-align:center">{expiry_str}</td>
        </tr>"""

    return f"""
    <div class="sec-panel" style="margin-top:24px">
        <div class="sec-title">&#x1F4E6; Encrypted Envelope Inventory</div>
        <div class="sec-subtitle">Metadata only — no secrets are displayed</div>
        <table style="width:100%;border-collapse:collapse;font-size:12px;color:#ccd6f6;margin-top:12px">
            <thead><tr style="border-bottom:2px solid rgba(100,255,218,0.3)">
                <th style="padding:6px 8px;text-align:left;color:#64ffda;font-size:10px;
                    text-transform:uppercase;letter-spacing:1px">Type</th>
                <th style="padding:6px 8px;text-align:left;color:#64ffda;font-size:10px;
                    text-transform:uppercase;letter-spacing:1px">Ver</th>
                <th style="padding:6px 8px;text-align:left;color:#64ffda;font-size:10px;
                    text-transform:uppercase;letter-spacing:1px">Enc</th>
                <th style="padding:6px 8px;text-align:center;color:#64ffda;font-size:10px;
                    text-transform:uppercase;letter-spacing:1px">Recipients</th>
                <th style="padding:6px 8px;text-align:center;color:#64ffda;font-size:10px;
                    text-transform:uppercase;letter-spacing:1px">HMAC</th>
                <th style="padding:6px 8px;text-align:left;color:#64ffda;font-size:10px;
                    text-transform:uppercase;letter-spacing:1px">Size</th>
                <th style="padding:6px 8px;text-align:left;color:#64ffda;font-size:10px;
                    text-transform:uppercase;letter-spacing:1px">Age</th>
                <th style="padding:6px 8px;text-align:center;color:#64ffda;font-size:10px;
                    text-transform:uppercase;letter-spacing:1px">Expires</th>
            </tr></thead>
            <tbody>{rows}</tbody>
        </table>
    </div>"""


def build_revoke_section(user_email: str, base_url: str) -> str:
    """Build the revoke/danger-zone section with granular deletion controls."""
    safe_email = html.escape(user_email)
    safe_base = html.escape(base_url)

    # Determine which items exist for this user
    items_available: list[dict] = []
    try:
        from auth.context import get_auth_middleware

        auth_mw = get_auth_middleware()
        if auth_mw:
            inventory = auth_mw.get_envelope_inventory(user_email)
            type_to_item = {
                "credentials": ("credentials", "OAuth Credentials"),
                "chat_sa": ("chat_sa", "Chat Service Account"),
                "sampling_config": ("sampling_config", "Sampling Config"),
                "backup": ("backup", "Credential Backup"),
            }
            for inv in inventory:
                key = type_to_item.get(inv["file_type"])
                if key:
                    items_available.append({"id": key[0], "label": key[1]})
    except Exception:
        pass

    # Always offer API key revocation
    try:
        from auth.user_api_keys import was_key_revealed

        if was_key_revealed(user_email):
            items_available.insert(0, {"id": "api_key", "label": "API Key"})
    except Exception:
        pass

    # Check for linked accounts
    has_links = False
    try:
        from auth.user_api_keys import get_accessible_emails

        accessible = get_accessible_emails(user_email)
        linked = [e for e in accessible if e != user_email.lower().strip()]
        if linked:
            has_links = True
            items_available.append(
                {"id": "links", "label": f"Account Links ({len(linked)})"}
            )
    except Exception:
        pass

    if not items_available:
        return ""

    checkboxes = ""
    for item in items_available:
        checkboxes += (
            f'<label style="display:flex;align-items:center;gap:8px;padding:4px 0;cursor:pointer;color:#e0e0e0">'
            f'<input type="checkbox" class="revoke-item" value="{item["id"]}" '
            f'style="accent-color:#dc3545">'
            f"<span>{html.escape(item['label'])}</span></label>\n"
        )

    return f"""
    <div style="background:#2d1215;border:1.5px solid #dc3545;border-radius:12px;
                padding:24px;margin:24px 0;text-align:left">
        <div style="font-size:16px;font-weight:700;color:#dc3545;margin-bottom:4px">
            &#x26A0;&#xFE0F; Danger Zone</div>
        <div style="font-size:11px;color:#ff9999;margin-bottom:16px">
            Revoke credentials and encrypted envelopes. This action cannot be undone.</div>

        <label style="display:flex;align-items:center;gap:8px;padding:6px 0;cursor:pointer;
                      border-bottom:1px solid rgba(220,53,69,0.2);margin-bottom:8px;font-weight:600;color:#ff6b6b">
            <input type="checkbox" id="selectAll" style="accent-color:#dc3545"
                   onchange="document.querySelectorAll('.revoke-item').forEach(c=>c.checked=this.checked)">
            <span>Select All</span>
        </label>

        {checkboxes}

        <div style="margin-top:16px">
            <label style="font-size:11px;color:#ffb3b3;display:block;margin-bottom:4px">
                Type your email to confirm: <b style="color:#ffd6d6">{safe_email}</b></label>
            <input type="text" id="confirmEmail" placeholder="{safe_email}"
                   style="width:100%;box-sizing:border-box;padding:8px 12px;border-radius:6px;
                          border:1px solid rgba(220,53,69,0.4);background:#1a0a0c;color:#f0f0f0;
                          font-family:monospace;font-size:13px"
                   oninput="document.getElementById('revokeBtn').disabled=
                       this.value.trim().toLowerCase()!=='{user_email.lower().strip()}'.toLowerCase()">
        </div>

        <button id="revokeBtn" disabled
                style="margin-top:12px;background:#dc3545;color:#fff;border:none;padding:10px 24px;
                       border-radius:6px;cursor:pointer;font-size:14px;font-weight:700;width:100%;
                       opacity:0.5;transition:opacity 0.2s;letter-spacing:0.5px"
                onmouseover="if(!this.disabled)this.style.opacity='0.9'"
                onmouseout="this.style.opacity=this.disabled?'0.5':'1'"
                onclick="doRevoke()">
            Revoke Selected
        </button>

        <div id="revokeResult" style="margin-top:12px;display:none"></div>

        <script>
        document.getElementById('revokeBtn').addEventListener('mouseenter', function() {{
            if(!this.disabled) this.style.opacity='0.9';
        }});
        document.getElementById('confirmEmail').addEventListener('input', function() {{
            var btn = document.getElementById('revokeBtn');
            var match = this.value.trim().toLowerCase() === '{user_email.lower().strip()}'.toLowerCase();
            btn.disabled = !match;
            btn.style.opacity = match ? '1' : '0.5';
        }});

        function doRevoke() {{
            var items = Array.from(document.querySelectorAll('.revoke-item:checked')).map(c => c.value);
            if (items.length === 0) {{ alert('Select at least one item to revoke.'); return; }}
            var confirmEmail = document.getElementById('confirmEmail').value.trim();
            var btn = document.getElementById('revokeBtn');
            btn.disabled = true;
            btn.textContent = 'Revoking...';

            fetch('{safe_base}/api/revoke', {{
                method: 'POST',
                headers: {{'Content-Type': 'application/json'}},
                body: JSON.stringify({{
                    user_email: '{user_email.lower().strip()}',
                    items: items,
                    confirmation_email: confirmEmail
                }})
            }})
            .then(r => r.json())
            .then(data => {{
                var result = document.getElementById('revokeResult');
                result.style.display = 'block';
                if (data.success) {{
                    result.innerHTML = '<div style="color:#64ffda;padding:8px;background:rgba(100,255,218,0.08);border-radius:6px">' +
                        '&#x2705; Revoked: ' + data.revoked.join(', ') +
                        (data.errors && data.errors.length ? '<br>&#x26A0;&#xFE0F; Errors: ' + data.errors.join(', ') : '') +
                        '</div>';
                    // Grey out revoked checkboxes
                    data.revoked.forEach(function(id) {{
                        var cb = document.querySelector('.revoke-item[value="'+id+'"]');
                        if (cb) {{
                            cb.checked = false;
                            cb.disabled = true;
                            cb.parentElement.style.opacity = '0.4';
                            cb.parentElement.style.textDecoration = 'line-through';
                        }}
                    }});
                }} else {{
                    result.innerHTML = '<div style="color:#dc3545;padding:8px">&#x274C; ' +
                        (data.error || 'Unknown error') + '</div>';
                }}
                btn.textContent = 'Revoke Selected';
                btn.disabled = false;
            }})
            .catch(err => {{
                document.getElementById('revokeResult').style.display = 'block';
                document.getElementById('revokeResult').innerHTML =
                    '<div style="color:#dc3545;padding:8px">&#x274C; Network error: ' + err.message + '</div>';
                btn.textContent = 'Revoke Selected';
                btn.disabled = false;
            }});
        }}
        </script>
    </div>"""


def generate_service_selection_html(
    state: str, flow_type: str, use_pkce: bool = True, requested_email: str = ""
) -> str:
    """Generate the service selection page HTML with authentication method choice."""
    import logging

    from config.settings import settings as _settings

    _env_client_id = (
        _settings.google_client_id or _settings.fastmcp_server_auth_google_client_id
    )
    _env_client_secret = (
        _settings.google_client_secret
        or _settings.fastmcp_server_auth_google_client_secret
    )
    _env_has_creds = bool(_env_client_id and _env_client_secret)
    _env_client_id_display = (_env_client_id[:20] + "...") if _env_client_id else ""
    _redirect_uri = getattr(
        _settings, "dynamic_oauth_redirect_uri", "https://localhost:8002/oauth2callback"
    )
    _sa_file_configured = bool(_settings.chat_service_account_file)

    try:
        from auth.scope_registry import ScopeRegistry

        services_catalog = ScopeRegistry.get_service_catalog()

        # Group services by category
        categories = {}
        for key, service in services_catalog.items():
            category = service.get("category", "Other")
            if category not in categories:
                categories[category] = []
            categories[category].append((key, service))

        # Build env-configured credentials banner or empty state
        if _env_has_creds:
            creds_status_html = f"""
                <div style="display:flex;align-items:center;gap:10px;background:rgba(52,168,83,0.08);
                            border:1px solid rgba(52,168,83,0.3);border-radius:10px;padding:12px 16px;margin-bottom:12px;">
                    <span style="font-size:20px">✅</span>
                    <div>
                        <div style="font-size:13px;font-weight:600;color:#137333">Environment credentials configured</div>
                        <div style="font-size:11px;color:#5f6368;font-family:monospace;margin-top:2px">{_env_client_id_display}</div>
                    </div>
                    <div style="margin-left:auto;font-size:11px;color:#137333;background:rgba(52,168,83,0.12);
                                padding:3px 10px;border-radius:12px;font-weight:600">AUTO</div>
                </div>"""
            creds_hint = "Override below only if you need different credentials for this session."
        else:
            creds_status_html = f"""
                <div style="display:flex;align-items:center;gap:10px;background:rgba(234,67,53,0.06);
                            border:1px solid rgba(234,67,53,0.2);border-radius:10px;padding:12px 16px;margin-bottom:12px;">
                    <span style="font-size:20px">⚠️</span>
                    <div>
                        <div style="font-size:13px;font-weight:600;color:#c5221f">No environment credentials found</div>
                        <div style="font-size:11px;color:#5f6368;margin-top:2px">Set GOOGLE_CLIENT_ID + GOOGLE_CLIENT_SECRET or enter below</div>
                    </div>
                </div>"""
            creds_hint = "Enter your Google OAuth credentials to continue."

        html_out = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Google Authentication — FastMCP</title>
    <style>
        *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            align-items: flex-start;
            justify-content: center;
            padding: 40px 20px;
        }}
        .card {{
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.18);
            width: 100%;
            max-width: 680px;
            overflow: hidden;
        }}
        /* Header — matches success screen gradient treatment */
        .card-header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 36px 40px 30px;
            text-align: center;
            color: white;
        }}
        .card-header .icon {{ font-size: 52px; margin-bottom: 12px; }}
        .card-header h1 {{ font-size: 26px; font-weight: 700; margin-bottom: 6px; }}
        .card-header p {{ font-size: 14px; opacity: 0.85; }}
        .card-body {{ padding: 32px 40px 40px; }}

        /* Section panels */
        .panel {{
            border: 1.5px solid #e8eaed;
            border-radius: 12px;
            margin-bottom: 20px;
            overflow: hidden;
        }}
        .panel-header {{
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 14px 18px;
            background: #f8f9fa;
            border-bottom: 1px solid #e8eaed;
            cursor: pointer;
            user-select: none;
        }}
        .panel-header .panel-icon {{ font-size: 18px; }}
        .panel-header .panel-title {{ font-size: 14px; font-weight: 600; color: #202124; flex: 1; }}
        .panel-header .panel-badge {{
            font-size: 11px; font-weight: 600; padding: 2px 10px;
            border-radius: 12px; background: #e8f0fe; color: #1a73e8;
        }}
        .panel-header .panel-badge.green {{ background: rgba(52,168,83,0.1); color: #137333; }}
        .panel-header .chevron {{
            font-size: 12px; color: #9aa0a6; transition: transform 0.2s;
        }}
        .panel-header.collapsed .chevron {{ transform: rotate(-90deg); }}
        .panel-body {{ padding: 18px; }}

        /* Auth method cards */
        .auth-options {{ display: flex; gap: 12px; }}
        .auth-option {{
            flex: 1; padding: 16px; border: 2px solid #e8eaed; border-radius: 10px;
            cursor: pointer; transition: all 0.15s ease; background: white;
        }}
        .auth-option:hover {{ border-color: #764ba2; background: #f8f5ff; }}
        .auth-option.selected {{ border-color: #667eea; background: #f0eeff; }}
        .auth-option input[type="radio"] {{ display: none; }}
        .auth-option-name {{ font-size: 13px; font-weight: 600; color: #202124; margin-bottom: 5px; }}
        .auth-option-desc {{ font-size: 12px; color: #5f6368; line-height: 1.4; }}
        .auth-option-pros {{ font-size: 11px; color: #137333; margin-top: 6px; }}
        .auth-option-cons {{ font-size: 11px; color: #d93025; margin-top: 3px; }}

        /* Service chips */
        .services-grid {{ display: flex; flex-wrap: wrap; gap: 6px; }}
        .service-chip {{
            display: flex; align-items: center; gap: 5px;
            padding: 5px 10px; border: 1.5px solid #e8eaed; border-radius: 20px;
            cursor: pointer; transition: all 0.15s ease; background: white;
            font-size: 12px; color: #202124;
        }}
        .service-chip:hover {{ border-color: #764ba2; background: #f8f5ff; }}
        .service-chip.checked {{ border-color: #667eea; background: #f0eeff; color: #4527a0; }}
        .service-chip.required {{ border-color: #34a853; background: #e8f5e9; color: #1b5e20; cursor: default; }}
        .service-chip input {{ display: none; }}
        .service-chip .chip-check {{ font-size: 11px; }}
        .category-label {{
            font-size: 10px; font-weight: 600; text-transform: uppercase;
            letter-spacing: 0.8px; color: #9aa0a6; margin: 10px 0 5px;
        }}
        .category-label:first-child {{ margin-top: 0; }}

        /* Credential inputs */
        .field-group {{ display: flex; flex-direction: column; gap: 10px; }}
        .field-input {{
            width: 100%; padding: 11px 14px; border: 1.5px solid #dadce0;
            border-radius: 8px; font-size: 13px; color: #202124;
            transition: border-color 0.15s; outline: none; font-family: monospace;
        }}
        .field-input:focus {{ border-color: #667eea; box-shadow: 0 0 0 3px rgba(102,126,234,0.12); }}
        .field-label {{ font-size: 12px; color: #5f6368; margin-bottom: 4px; font-weight: 500; }}
        .field-hint {{ font-size: 11px; color: #9aa0a6; margin-top: 4px; }}
        .redirect-uri {{
            font-family: monospace; font-size: 12px; background: #f8f9fa;
            padding: 8px 12px; border-radius: 6px; border: 1px solid #e8eaed;
            color: #5f6368; word-break: break-all;
        }}

        /* Toggle row */
        .toggle-row {{
            display: flex; align-items: center; gap: 12px; padding: 4px 0;
        }}
        .toggle-label {{ font-size: 13px; color: #202124; flex: 1; }}
        .toggle-desc {{ font-size: 11px; color: #9aa0a6; margin-top: 2px; }}
        /* Native checkbox styled */
        .toggle-row input[type="checkbox"] {{ transform: scale(1.25); accent-color: #667eea; cursor: pointer; }}

        /* Passphrase field */
        .passphrase-wrap {{ margin-top: 14px; padding-top: 14px; border-top: 1px solid #f1f3f4; }}

        /* Info/warning boxes */
        .info-box {{
            border-radius: 8px; padding: 12px 14px; font-size: 12px; line-height: 1.5;
            margin-bottom: 12px;
        }}
        .info-box.blue {{ background: #e8f0fe; color: #1a56a0; border: 1px solid #c5d8f8; }}
        .info-box.amber {{ background: #fff8e1; color: #795700; border: 1px solid #ffe08a; }}
        .info-box.red {{ background: #fce8e6; color: #c5221f; border: 1px solid #f5c6c3; }}
        .info-box a {{ color: inherit; }}

        /* Hint bar */
        .hint-bar {{
            display: flex; align-items: center; gap: 8px;
            background: #f0eeff; border-radius: 8px; padding: 10px 14px;
            margin-bottom: 20px; font-size: 12px; color: #4527a0;
        }}

        /* Actions */
        .actions {{
            display: flex; align-items: center; gap: 12px;
            padding-top: 24px; border-top: 1px solid #f1f3f4; margin-top: 4px;
        }}
        .btn-primary {{
            flex: 1; padding: 14px; border: none; border-radius: 10px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white; font-size: 15px; font-weight: 600; cursor: pointer;
            transition: opacity 0.15s; letter-spacing: 0.2px;
        }}
        .btn-primary:hover {{ opacity: 0.92; }}
        .btn-secondary {{
            padding: 14px 18px; border: 1.5px solid #dadce0; border-radius: 10px;
            background: white; color: #3c4043; font-size: 14px; font-weight: 500;
            cursor: pointer; transition: background 0.15s; white-space: nowrap;
        }}
        .btn-secondary:hover {{ background: #f8f9fa; }}
    </style>
</head>
<body>
<div class="card">
    <div class="card-header">
        <div class="icon">🔐</div>
        <h1>Google Authentication</h1>
        <p>Select services and configure your auth method for FastMCP</p>
    </div>
    <div class="card-body">
        {"" if not requested_email else (
            '<div style="display:flex;align-items:center;gap:10px;background:#e8f4fd;'
            'border:1px solid #bee5eb;border-radius:10px;padding:12px 16px;margin-bottom:16px">'
            '<span style="font-size:18px">&#x1F916;</span>'
            '<div>'
            '<div style="font-size:13px;font-weight:600;color:#0c5460">Requested by assistant</div>'
            f'<div style="font-size:12px;color:#5f6368;font-family:monospace;margin-top:2px">{html.escape(requested_email)}</div>'
            '<div style="font-size:11px;color:#6c757d;margin-top:2px">Sign in with your actual Google account below</div>'
            '</div></div>'
        )}
        <form method="POST" action="/auth/services/selected" id="auth-form">
            <input type="hidden" name="state" value="{state}">
            <input type="hidden" name="flow_type" value="{flow_type}">

            <!-- Auth Method -->
            <div class="panel">
                <div class="panel-header" onclick="togglePanel('auth-method-body', this)">
                    <span class="panel-icon">🔒</span>
                    <span class="panel-title">Authentication Method</span>
                    <span class="panel-badge">{"PKCE (Recommended)" if use_pkce else "Legacy OAuth"}</span>
                    <span class="chevron">▼</span>
                </div>
                <div class="panel-body" id="auth-method-body">
                    <div class="auth-options">
                        <div class="auth-option {"selected" if use_pkce else ""}" onclick="selectAuthMethod('pkce', this)">
                            <input type="radio" name="auth_method" value="pkce" {"checked" if use_pkce else ""}>
                            <div class="auth-option-name">🔐 PKCE Flow</div>
                            <div class="auth-option-desc">OAuth 2.1 with Proof Key for Code Exchange — enhanced security</div>
                            <div class="auth-option-pros">✅ Best security · Code verifier protection · Encrypted storage</div>
                            <div class="auth-option-cons">⚠️ Requires client secret for web apps</div>
                        </div>
                        <div class="auth-option {"selected" if not use_pkce else ""}" onclick="selectAuthMethod('credentials', this)">
                            <input type="radio" name="auth_method" value="credentials" {"checked" if not use_pkce else ""}>
                            <div class="auth-option-name">📁 Legacy OAuth 2.0</div>
                            <div class="auth-option-desc">Traditional OAuth flow with encrypted credential storage</div>
                            <div class="auth-option-pros">✅ Multi-account support · Persists across restarts</div>
                            <div class="auth-option-cons">⚠️ No PKCE enhancement</div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- OAuth Credentials (optional override) -->
            <div class="panel">
                <div class="panel-header" onclick="togglePanel('creds-body', this)">
                    <span class="panel-icon">🔑</span>
                    <span class="panel-title">OAuth Credentials</span>
                    <span class="panel-badge {"green" if _env_has_creds else ""}">{"Env configured" if _env_has_creds else "Manual entry"}</span>
                    <span class="chevron">▼</span>
                </div>
                <div class="panel-body" id="creds-body">
                    {creds_status_html}
                    <label style="display:flex;align-items:center;gap:10px;margin-bottom:14px;cursor:pointer;">
                        <input type="checkbox" id="use_custom_creds" name="use_custom_creds"
                               style="transform:scale(1.2);accent-color:#667eea;">
                        <span style="font-size:13px;color:#202124;font-weight:500;">
                            Override with custom credentials
                        </span>
                    </label>
                    <div id="custom-creds-fields" style="display:none;">
                        <div class="info-box amber" style="margin-bottom:12px;">
                            <strong>Redirect URI required in Google Cloud Console:</strong><br>
                            <div class="redirect-uri" style="margin-top:6px;">{_redirect_uri}</div>
                        </div>
                        <div class="field-group">
                            <div>
                                <div class="field-label">Client ID</div>
                                <input type="text" name="custom_client_id" class="field-input"
                                       placeholder="xxxxxx.apps.googleusercontent.com"
                                       value="{_env_client_id if _env_has_creds else ""}">
                                <div class="field-hint">From Google Cloud Console → APIs & Services → Credentials</div>
                            </div>
                            <div>
                                <div class="field-label">Client Secret</div>
                                <input type="text" name="custom_client_secret" class="field-input"
                                       placeholder="GOCSPX-..."
                                       value="{_env_client_secret if _env_has_creds else ""}">
                                <div class="field-hint">Optional for PKCE flow · Not recommended to enter in production UI</div>
                            </div>
                        </div>
                        <div class="info-box blue" style="margin-top:12px;">
                            <strong>🔧 Cloud Console setup:</strong>
                            <a href="https://console.cloud.google.com/apis/credentials" target="_blank">
                                APIs & Services → Credentials
                            </a> · Create/edit OAuth 2.0 Client ID · Add redirect URI above · Enable required APIs
                        </div>
                    </div>
                    <div style="font-size:11px;color:#9aa0a6;margin-top:4px;">{creds_hint}</div>
                </div>
            </div>

            <!-- Cross-OAuth Linkage -->
            <div class="panel">
                <div class="panel-header" onclick="togglePanel('linkage-body', this)">
                    <span class="panel-icon">🔗</span>
                    <span class="panel-title">Cross-OAuth Account Access</span>
                    <span class="panel-badge green">Enabled</span>
                    <span class="chevron">▼</span>
                </div>
                <div class="panel-body" id="linkage-body">
                    <div class="toggle-row">
                        <div>
                            <div class="toggle-label">Allow cross-OAuth access to this account</div>
                            <div class="toggle-desc">Linked accounts can access credentials without a per-user API key</div>
                        </div>
                        <input type="checkbox" id="oauth_linkage_enabled" name="oauth_linkage_enabled" checked
                               onchange="document.getElementById('oauth-password-field').style.display=this.checked?'block':'none';">
                    </div>
                    <div id="oauth-password-field" class="passphrase-wrap">
                        <div class="field-label">Optional passphrase (alphanumeric, _, - only)</div>
                        <input type="text" name="oauth_linkage_password" class="field-input"
                               placeholder="Leave blank for no passphrase"
                               pattern="[0-9A-Za-z_-]*"
                               title="Only 0-9, A-Z, a-z, underscore, and hyphen allowed"
                               style="max-width:320px;margin-top:6px;">
                        <div class="field-hint">If set, OAuth sessions require this passphrase to access your credentials.</div>
                    </div>
                </div>
            </div>

            <!-- Chat Bot Service Account (Optional) -->
            <div class="panel">
                <div class="panel-header collapsed" onclick="togglePanel('chat-sa-body', this)">
                    <span class="panel-icon">🤖</span>
                    <span class="panel-title">Chat Bot Service Account</span>
                    <span class="panel-badge {"green" if _sa_file_configured else ""}" id="chat-sa-badge">{"Env configured" if _sa_file_configured else "Optional"}</span>
                    <span class="chevron">▼</span>
                </div>
                <div class="panel-body" id="chat-sa-body" style="display:none;">
                    {"" if not _sa_file_configured else '<div style="display:flex;align-items:center;gap:10px;background:rgba(52,168,83,0.08);border:1px solid rgba(52,168,83,0.3);border-radius:10px;padding:12px 16px;margin-bottom:12px;"><span style="font-size:20px">✅</span><div><div style="font-size:13px;font-weight:600;color:#137333">Global service account configured via environment</div><div style="font-size:11px;color:#5f6368;margin-top:2px">Upload below only to use a different SA for your account</div></div></div>'}
                    <div class="info-box blue" style="line-height:1.7;">
                        <strong>What is this?</strong><br>
                        A Google Chat service account lets the MCP server act as a Chat bot &mdash;
                        sending messages, managing spaces, and performing reactions via Domain-Wide
                        Delegation (DWD).
                        <br><br>
                        <strong>Setup steps:</strong>
                        <ol style="margin:6px 0 0 16px;padding:0;">
                            <li>Create a service account in
                                <a href="https://console.cloud.google.com/iam-admin/serviceaccounts/create"
                                   target="_blank" rel="noopener">Cloud Console &rarr; Service Accounts</a></li>
                            <li>Enable the
                                <a href="https://console.cloud.google.com/apis/library/chat.googleapis.com"
                                   target="_blank" rel="noopener">Google Chat API</a></li>
                            <li>Create & download a JSON key from
                                <a href="https://console.cloud.google.com/apis/credentials"
                                   target="_blank" rel="noopener">APIs & Services &rarr; Credentials</a></li>
                            <li>In <a href="https://admin.google.com/ac/owl/domainwidedelegation"
                                      target="_blank" rel="noopener">Admin Console &rarr; Domain-wide Delegation</a>,
                                add the SA client ID with these scopes:</li>
                        </ol>
                        <div style="position:relative;margin-top:8px;">
                            <div id="dwd-scopes-display" style="background:rgba(0,0,0,0.04);border-radius:6px;padding:8px 10px 8px 10px;
                                        font-family:monospace;font-size:10px;word-break:break-all;">
                                https://www.googleapis.com/auth/chat.spaces,<br>
                                https://www.googleapis.com/auth/chat.spaces.create,<br>
                                https://www.googleapis.com/auth/chat.delete,<br>
                                https://www.googleapis.com/auth/chat.app.delete,<br>
                                https://www.googleapis.com/auth/chat.memberships,<br>
                                https://www.googleapis.com/auth/chat.memberships.readonly,<br>
                                https://www.googleapis.com/auth/chat.memberships.app,<br>
                                https://www.googleapis.com/auth/chat.messages,<br>
                                https://www.googleapis.com/auth/chat.messages.readonly,<br>
                                https://www.googleapis.com/auth/chat.messages.create,<br>
                                https://www.googleapis.com/auth/chat.app.memberships,<br>
                                https://www.googleapis.com/auth/chat.app.spaces,<br>
                                https://www.googleapis.com/auth/chat.app.spaces.create,<br>
                                https://www.googleapis.com/auth/chat.messages.reactions,<br>
                                https://www.googleapis.com/auth/chat.messages.reactions.create,<br>
                                https://www.googleapis.com/auth/chat.messages.reactions.readonly
                            </div>
                            <button type="button" onclick="copyDwdScopes(this)"
                                    style="position:absolute;top:6px;right:6px;background:#fff;border:1px solid #dadce0;
                                           border-radius:6px;padding:4px 10px;font-size:11px;cursor:pointer;
                                           color:#1a73e8;font-weight:500;transition:all 0.15s;">
                                📋 Copy scopes
                            </button>
                        </div>
                    </div>
                    <div style="margin-top:14px;">
                        <div class="field-label">Service Account JSON Key</div>
                        <textarea name="chat_sa_json" id="chat_sa_json"
                                  class="field-input" rows="6"
                                  placeholder="Paste the full JSON key here, or use the file picker below..."
                                  style="font-family:monospace;font-size:11px;resize:vertical;"></textarea>
                        <div style="margin-top:8px;display:flex;align-items:center;gap:10px;">
                            <label class="btn-secondary" style="padding:8px 14px;font-size:12px;cursor:pointer;">
                                📁 Choose JSON file
                                <input type="file" id="chat_sa_file" accept=".json"
                                       style="display:none;"
                                       onchange="handleSAFileUpload(this)">
                            </label>
                            <span id="chat-sa-filename" style="font-size:11px;color:#5f6368;"></span>
                        </div>
                        <div class="field-hint">
                            The JSON key will be encrypted and bound to the email you authenticate with.
                            It is never stored in plaintext.
                        </div>
                    </div>
                </div>
            </div>

            <!-- Privacy Mode -->
            <div class="panel">
                <div class="panel-header collapsed" onclick="togglePanel('privacy-body', this)">
                    <span class="panel-icon">🛡️</span>
                    <span class="panel-title">Privacy Mode</span>
                    <span class="panel-badge">Off</span>
                    <span class="chevron">▼</span>
                </div>
                <div class="panel-body" id="privacy-body" style="display:none;">
                    <div class="toggle-row">
                        <div>
                            <div class="toggle-label">Enable privacy mode for this session</div>
                            <div class="toggle-desc">
                                When enabled, personal information (emails, names, phone numbers)
                                in tool responses is replaced with <code>[PRIVATE:token]</code>
                                placeholders before the AI sees it. Your data stays encrypted on
                                the server and can be revealed when needed.
                            </div>
                        </div>
                        <input type="checkbox" name="privacy_mode" value="on"
                               onchange="this.closest('.panel').querySelector('.panel-badge').textContent=this.checked?'On':'Off';">
                    </div>
                </div>
            </div>

            <!-- LLM Sampling Configuration -->
            <div class="panel">
                <div class="panel-header collapsed" onclick="togglePanel('sampling-body', this)">
                    <span class="panel-icon">🤖</span>
                    <span class="panel-title">LLM Sampling Configuration</span>
                    <span class="panel-badge">Server Default</span>
                    <span class="chevron">▼</span>
                </div>
                <div class="panel-body" id="sampling-body" style="display:none;">
                    <div style="font-size:12px;color:#5f6368;line-height:1.5;margin-bottom:14px;">
                        Configure your own LLM provider for sampling calls. Supports any
                        <a href="https://docs.litellm.ai/docs/providers" target="_blank" rel="noopener">LiteLLM-compatible provider</a>
                        (Venice AI, OpenAI, Anthropic, Groq, Together, etc.) using <code>provider/model</code> format.
                        API keys are encrypted with split-key envelope encryption. Leave blank to use the server
                        default (<code>{html.escape(_settings.litellm_model or "openai/gpt-4")}</code>).
                    </div>
                    <div class="field-group">
                        <div>
                            <div class="field-label">Model</div>
                            <input type="text" name="sampling_model" class="field-input"
                                   placeholder="{html.escape(_settings.litellm_model or "openai/gpt-4")}">
                        </div>
                        <div>
                            <div class="field-label">API Key</div>
                            <input type="password" name="sampling_api_key" class="field-input"
                                   placeholder="Optional — provider API key">
                        </div>
                        <div>
                            <div class="field-label">API Base URL</div>
                            <input type="text" name="sampling_api_base" class="field-input"
                                   placeholder="Optional — e.g. https://api.venice.ai/api/v1">
                        </div>
                    </div>
                </div>
            </div>

            <!-- Service Selection -->
            <div class="panel">
                <div class="panel-header collapsed" onclick="togglePanel('services-body', this)">
                    <span class="panel-icon">🚀</span>
                    <span class="panel-title">Google Services</span>
                    <span class="panel-badge" id="services-badge">Loading...</span>
                    <span class="chevron">▼</span>
                </div>
                <div class="panel-body" id="services-body" style="display:none;">
                    <div class="hint-bar" style="font-size:11px;padding:8px 12px;">
                        💡 Common services pre-selected — expand to change
                    </div>
                    <div class="services-grid" id="services-grid">
"""

        # Sort categories
        category_order = [
            "Core Services",
            "Storage & Files",
            "Communication",
            "Productivity",
            "Office Suite",
            "Other",
        ]
        sorted_categories = sorted(
            categories.items(),
            key=lambda x: category_order.index(x[0])
            if x[0] in category_order
            else len(category_order),
        )

        for category_name, services in sorted_categories:
            html_out += (
                f'<div class="category-label" style="width:100%">{category_name}</div>'
            )
            for service_key, service_info in services:
                required = service_info.get("required", False)
                chip_class = "service-chip required" if required else "service-chip"
                disabled_attr = "disabled" if required else ""
                check_icon = "✅" if required else "◻"
                html_out += f"""
                        <label class="{chip_class}" title="{service_info["description"]}">
                            <input type="checkbox" name="services" value="{service_key}" {disabled_attr}
                                   onchange="updateChip(this);updateBadge();">
                            <span class="chip-check">{check_icon}</span>
                            <span>{service_info["name"]}{"&nbsp;🔒" if required else ""}</span>
                        </label>"""

        html_out += f"""
                    </div>
                    <div style="display:flex;gap:6px;margin-top:10px;">
                        <button type="button" onclick="selectAll()" class="btn-secondary" style="font-size:11px;padding:6px 12px;">Toggle All</button>
                        <button type="button" onclick="selectCommon()" class="btn-secondary" style="font-size:11px;padding:6px 12px;">Reset to Common</button>
                    </div>
                </div>
            </div>

            <div class="actions">
                <button type="submit" class="btn-primary">Continue with Selected Configuration</button>
                <button type="button" class="btn-secondary" onclick="selectCommon()">Reset</button>
            </div>
        </form>
    </div>
</div>

<script>
    const COMMON_SERVICES = ['drive','gmail','calendar','docs','sheets','slides','photos','chat','forms','people'];

    function copyDwdScopes(btn) {{
        const scopes = 'https://www.googleapis.com/auth/chat.spaces,https://www.googleapis.com/auth/chat.spaces.create,https://www.googleapis.com/auth/chat.delete,https://www.googleapis.com/auth/chat.app.delete,https://www.googleapis.com/auth/chat.memberships,https://www.googleapis.com/auth/chat.memberships.readonly,https://www.googleapis.com/auth/chat.memberships.app,https://www.googleapis.com/auth/chat.messages,https://www.googleapis.com/auth/chat.messages.readonly,https://www.googleapis.com/auth/chat.messages.create,https://www.googleapis.com/auth/chat.app.memberships,https://www.googleapis.com/auth/chat.app.spaces,https://www.googleapis.com/auth/chat.app.spaces.create,https://www.googleapis.com/auth/chat.messages.reactions,https://www.googleapis.com/auth/chat.messages.reactions.create,https://www.googleapis.com/auth/chat.messages.reactions.readonly';
        navigator.clipboard.writeText(scopes).then(function() {{
            btn.textContent = '✅ Copied!';
            btn.style.color = '#137333';
            btn.style.borderColor = '#34a853';
            setTimeout(function() {{
                btn.textContent = '📋 Copy scopes';
                btn.style.color = '#1a73e8';
                btn.style.borderColor = '#dadce0';
            }}, 2000);
        }});
    }}

    function handleSAFileUpload(input) {{
        const file = input.files[0];
        if (!file) return;
        const reader = new FileReader();
        reader.onload = function(e) {{
            try {{
                const parsed = JSON.parse(e.target.result);
                if (!parsed.type || parsed.type !== 'service_account') {{
                    alert('This does not appear to be a Google service account JSON key (missing "type": "service_account").');
                    return;
                }}
                document.getElementById('chat_sa_json').value = e.target.result;
                document.getElementById('chat-sa-filename').textContent = file.name;
                const badge = document.getElementById('chat-sa-badge');
                if (badge) {{ badge.textContent = 'Provided'; badge.classList.add('green'); }}
            }} catch(err) {{
                alert('Invalid JSON file: ' + err.message);
            }}
        }};
        reader.readAsText(file);
    }}

    function updateChip(checkbox) {{
        const chip = checkbox.closest('.service-chip');
        if (!chip || chip.classList.contains('required')) return;
        const icon = chip.querySelector('.chip-check');
        if (checkbox.checked) {{
            chip.classList.add('checked');
            if (icon) icon.textContent = '✅';
        }} else {{
            chip.classList.remove('checked');
            if (icon) icon.textContent = '◻';
        }}
    }}

    function updateBadge() {{
        const checked = document.querySelectorAll('input[name="services"]:checked').length;
        const badge = document.getElementById('services-badge');
        if (badge) badge.textContent = checked + ' selected';
    }}

    function selectCommon() {{
        document.querySelectorAll('input[name="services"]:not(:disabled)').forEach(cb => {{
            cb.checked = COMMON_SERVICES.includes(cb.value);
            updateChip(cb);
        }});
        updateBadge();
    }}

    function selectAll() {{
        const boxes = document.querySelectorAll('input[name="services"]:not(:disabled)');
        const allChecked = Array.from(boxes).every(cb => cb.checked);
        boxes.forEach(cb => {{ cb.checked = !allChecked; updateChip(cb); }});
        updateBadge();
    }}

    function selectAuthMethod(method, element) {{
        document.querySelectorAll('.auth-option').forEach(o => o.classList.remove('selected'));
        element.classList.add('selected');
        element.querySelector('input[type="radio"]').checked = true;
        // Update badge
        const badge = element.closest('.panel').querySelector('.panel-badge');
        if (badge) badge.textContent = method === 'pkce' ? 'PKCE (Recommended)' : 'Legacy OAuth';
    }}

    function togglePanel(bodyId, headerEl) {{
        const body = document.getElementById(bodyId);
        if (!body) return;
        const hidden = body.style.display === 'none';
        body.style.display = hidden ? '' : 'none';
        if (headerEl) headerEl.classList.toggle('collapsed', !hidden);
    }}

    document.addEventListener('DOMContentLoaded', function() {{
        // Pre-select common services
        selectCommon();
        // Required checkboxes always checked
        document.querySelectorAll('input[name="services"]:disabled').forEach(cb => {{
            cb.checked = true; updateChip(cb);
        }});
        updateBadge();

        // Custom creds toggle
        const customCheck = document.getElementById('use_custom_creds');
        const customFields = document.getElementById('custom-creds-fields');
        if (customCheck && customFields) {{
            customCheck.addEventListener('change', function() {{
                customFields.style.display = this.checked ? 'block' : 'none';
                if (!this.checked) {{
                    customFields.querySelectorAll('input[type="text"]').forEach(i => i.value = '');
                }}
            }});
        }}

        // Form validation
        document.getElementById('auth-form').addEventListener('submit', function(e) {{
            const useCustom = customCheck && customCheck.checked;
            if (useCustom) {{
                const clientId = document.querySelector('input[name="custom_client_id"]');
                if (!clientId || !clientId.value.trim()) {{
                    e.preventDefault();
                    alert('Please provide a Client ID when using custom credentials.');
                    if (clientId) clientId.focus();
                    return;
                }}
                if (!clientId.value.includes('.apps.googleusercontent.com')) {{
                    if (!confirm('Client ID doesn\\'t look like a Google OAuth ID (should end in .apps.googleusercontent.com). Continue anyway?')) {{
                        e.preventDefault();
                    }}
                }}
            }}
            // Validate Chat SA JSON if provided
            const saJson = document.getElementById('chat_sa_json');
            if (saJson && saJson.value.trim()) {{
                try {{
                    const parsed = JSON.parse(saJson.value.trim());
                    if (parsed.type !== 'service_account') {{
                        e.preventDefault();
                        alert('The Chat service account JSON must have "type": "service_account". Please check the file.');
                        saJson.focus();
                        return;
                    }}
                }} catch(err) {{
                    e.preventDefault();
                    alert('The Chat service account JSON is not valid JSON: ' + err.message);
                    saJson.focus();
                    return;
                }}
            }}
        }});

        // Auth method click handlers
        document.querySelectorAll('.auth-option').forEach(opt => {{
            opt.addEventListener('click', function() {{
                selectAuthMethod(this.querySelector('input').value, this);
            }});
        }});
    }});
</script>
</body>
</html>"""

        return html_out

    except Exception as e:
        import logging

        logging.getLogger(__name__).error(
            f"Error generating service selection HTML: {e}"
        )
        return f"""<!DOCTYPE html>
<html><head><title>Error</title></head>
<body style="font-family:sans-serif;padding:40px">
<h1>Service Selection Error</h1><p>{html.escape(str(e))}</p>
</body></html>"""


def generate_oauth_client_error_html(error: str) -> str:
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>OAuth Client Configuration Error</title>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; background: #fff5f5; min-height: 100vh; display: flex; align-items: center; justify-content: center; }}
            .container {{ max-width: 700px; background: white; padding: 40px; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.1); }}
            .error {{ color: #dc3545; font-size: 48px; margin-bottom: 20px; text-align: center; }}
            h1 {{ color: #333; margin-bottom: 20px; text-align: center; }}
            .error-details {{ background: #f8d7da; border: 1px solid #f5c6cb; color: #721c24; padding: 15px; border-radius: 8px; margin: 20px 0; }}
            .solution-steps {{ background: #d4edda; border: 1px solid #c3e6cb; color: #155724; padding: 20px; border-radius: 8px; margin: 20px 0; }}
            .solution-steps h3 {{ margin-top: 0; color: #155724; }}
            .solution-steps ol {{ text-align: left; padding-left: 20px; }}
            .solution-steps li {{ margin: 8px 0; }}
            .redirect-uri {{ background: #f8f9fa; padding: 8px 12px; border-radius: 4px; font-family: monospace; border: 1px solid #dee2e6; }}
            .important {{ font-weight: bold; color: #dc3545; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="error">❌</div>
            <h1>OAuth Client Configuration Error</h1>
            
            <div class="error-details">
                <strong>Error:</strong> {html.escape(error)}<br><br>
                <strong>Most Likely Cause:</strong> Your OAuth client's redirect URI configuration doesn't match what the authentication system expects.
            </div>
            
            <div class="solution-steps">
                <h3>🔧 How to Fix This:</h3>
                <ol>
                    <li>Go to <a href="https://console.cloud.google.com/apis/credentials" target="_blank">Google Cloud Console → APIs & Services → Credentials</a></li>
                    <li>Find and click on your OAuth 2.0 Client ID</li>
                    <li>In the "Authorized redirect URIs" section, add this exact URI:</li>
                    <div class="redirect-uri">https://localhost:8002/oauth2callback</div>
                    <li>Click "Save" to update your OAuth client configuration</li>
                    <li>Wait a few minutes for changes to propagate</li>
                    <li class="important">Try the authentication process again</li>
                </ol>
            </div>
            
            <div style="text-align: center; margin-top: 30px;">
                <p>If you continue having issues, verify that:</p>
                <ul style="text-align: left; display: inline-block;">
                    <li>Your OAuth consent screen is configured</li>
                    <li>Required APIs are enabled (Drive, Gmail, Calendar, etc.)</li>
                    <li>Your client ID and secret are correct</li>
                    <li>You're using the latest client credentials</li>
                </ul>
            </div>
        </div>
    </body>
    </html>
    """


def generate_debug_success_html(auth_code: str, state: str = "") -> str:
    state_html = f"<p><strong>State:</strong> {html.escape(state)}</p>" if state else ""
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>OAuth Callback Success</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 40px; text-align: center; }}
            .success {{ color: #28a745; }}
            .container {{ max-width: 600px; margin: 0 auto; }}
            .code {{
                background: #f8f9fa;
                padding: 15px;
                border-radius: 5px;
                margin: 20px 0;
                font-family: monospace;
                word-break: break-all;
                border: 1px solid #dee2e6;
            }}
            .params {{
                text-align: left;
                background: #e9ecef;
                padding: 15px;
                border-radius: 5px;
                margin: 20px 0;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1 class="success">✅ OAuth Callback Successful!</h1>
            <p>Authorization code received from Google OAuth.</p>
            
            <div class="params">
                <h3>Callback Parameters:</h3>
                <p><strong>Authorization Code:</strong></p>
                <div class="code">{html.escape(auth_code)}</div>
                {state_html}
            </div>
            
            <p><em>You can now close this window or use the authorization code for token exchange.</em></p>
        </div>
    </body>
    </html>
    """
