"""Payment flow HTTP endpoints for browser-based x402 payment UX.

Provides endpoints for:
- /pay: Serves the x402 SDK paywall page (wallet connect → sign → submit)
- /api/payment-complete: Receives signed payment from browser, signals waiting middleware
- /payment-status: Returns payment status for a given token (polling fallback)
"""

import html
from decimal import Decimal, InvalidOperation
from typing import Any

from fastmcp import FastMCP

from config.enhanced_logging import setup_logger
from config.settings import settings as _settings

logger = setup_logger()


def setup_payment_endpoints(mcp: FastMCP):
    """Register payment flow HTTP endpoints.

    Args:
        mcp: FastMCP application instance
    """

    @mcp.custom_route("/pay", methods=["GET"])
    async def payment_page(request: Any):
        """Serve the x402 SDK paywall page for browser-based payment.

        Query params:
            sid: Session ID prefix (for display/binding)
            tool: Tool name that triggered payment
            amt: USDC amount required
            net: CAIP-2 network identifier
            to: Recipient wallet address
            cid: Chain ID
            exp: Expiry timestamp
            sig: HMAC signature
        """
        from starlette.responses import HTMLResponse

        try:
            query_params = dict(request.query_params)
            session_prefix = query_params.get("sid", "")
            tool_name = query_params.get("tool", "")
            amount = query_params.get("amt", "")
            network = query_params.get("net", "")
            recipient = query_params.get("to", "")
            chain_id_str = query_params.get("cid", "")
            exp = query_params.get("exp", "")
            sig = query_params.get("sig", "")

            logger.info(
                "Payment page requested: tool=%s, amount=%s USDC, session=%s...",
                tool_name,
                amount,
                session_prefix[:8] if session_prefix else "?",
            )

            # Validate required params
            if not all([tool_name, amount, network, recipient, exp, sig]):
                return HTMLResponse(
                    status_code=400,
                    content=_render_error_page("Missing required payment parameters"),
                )

            # Verify the signed URL
            from middleware.payment.payment_flow import verify_payment_token

            is_valid, error = verify_payment_token(
                session_id=session_prefix,
                tool_name=tool_name,
                amount=amount,
                network=network,
                exp=exp,
                sig=sig,
                recipient_wallet=recipient,
                chain_id=chain_id_str,
                consume=False,  # Don't consume yet — consume on completion
            )
            if not is_valid:
                return HTMLResponse(
                    status_code=403,
                    content=_render_error_page(
                        f"Invalid payment link: {html.escape(error)}"
                    ),
                )

            # Try to serve the x402 SDK paywall page
            page_html = _build_paywall_html(
                tool_name=tool_name,
                amount=amount,
                network=network,
                recipient=recipient,
                chain_id=int(chain_id_str)
                if chain_id_str
                else _settings.payment_chain_id,
                session_prefix=session_prefix,
                sig=sig,
            )
            return HTMLResponse(content=page_html)

        except Exception as exc:
            logger.error("Payment page error: %s", exc, exc_info=True)
            return HTMLResponse(
                status_code=500,
                content=_render_error_page(
                    "An internal error occurred. Please try again or contact support."
                ),
            )

    @mcp.custom_route("/api/payment-complete", methods=["POST"])
    async def payment_complete(request: Any):
        """Receive payment completion from browser.

        The paywall page posts here after the user signs the EIP-3009
        authorization. This signals the waiting middleware to proceed.

        Body (JSON):
            token: The payment token (sig from the /pay URL)
            payload_b64: Base64-encoded x402 signed payment payload
        """
        from starlette.responses import JSONResponse

        try:
            body = await request.json()
            token = body.get("token", "")
            payload_b64 = body.get("payload_b64", "")

            if not token or not payload_b64:
                return JSONResponse(
                    status_code=400,
                    content={"error": "Missing token or payload_b64"},
                )

            from middleware.payment.payment_flow import complete_pending_payment

            success = complete_pending_payment(token, payload_b64)
            if not success:
                return JSONResponse(
                    status_code=404,
                    content={"error": "Unknown or expired payment token"},
                )

            logger.info("Payment completion received for token %s...", token[:16])
            return JSONResponse(
                content={
                    "status": "completed",
                    "message": "Payment received. Your tool access is being unlocked.",
                },
            )

        except Exception as exc:
            logger.error("Payment completion error: %s", exc, exc_info=True)
            return JSONResponse(
                status_code=500,
                content={"error": "An internal error occurred"},
            )

    @mcp.custom_route("/payment-status", methods=["GET"])
    async def payment_status(request: Any):
        """Check payment status for a given token (polling fallback).

        Query params:
            token: The payment token (sig from the /pay URL)
        """
        from starlette.responses import JSONResponse

        token = request.query_params.get("token", "")
        if not token:
            return JSONResponse(
                status_code=400,
                content={"error": "Missing token parameter"},
            )

        from middleware.payment.payment_flow import get_pending_payment

        pending = get_pending_payment(token)
        if not pending:
            return JSONResponse(
                status_code=404,
                content={"status": "unknown", "message": "No pending payment found"},
            )

        if pending.get("completed_at"):
            return JSONResponse(
                content={
                    "status": "completed",
                    "completed_at": pending["completed_at"],
                },
            )

        return JSONResponse(
            content={"status": "pending", "message": "Waiting for payment..."},
        )

    @mcp.custom_route("/pay/qr", methods=["GET"])
    async def payment_qr_code(request: Any):
        """Generate a QR code PNG for a payment URL.

        Accepts the same query params as /pay. Returns a PNG image
        containing a QR code that encodes the full /pay URL.
        Suitable for embedding in emails via <img src="/pay/qr?...">.
        """
        from starlette.responses import Response

        try:
            # Reconstruct the /pay URL from query params
            query_string = str(request.url.query)
            base_url = _settings.payment_base_url
            pay_url = f"{base_url}/pay?{query_string}"

            from middleware.payment.payment_email import _generate_qr_png_bytes

            png_bytes = _generate_qr_png_bytes(pay_url)
            if not png_bytes:
                return Response(
                    content=b"QR generation failed",
                    status_code=500,
                    media_type="text/plain",
                )

            return Response(
                content=png_bytes,
                media_type="image/png",
                headers={
                    "Cache-Control": "public, max-age=900",
                },
            )

        except Exception as exc:
            logger.error("QR code generation error: %s", exc, exc_info=True)
            return Response(
                content=b"QR generation error",
                status_code=500,
                media_type="text/plain",
            )


def _build_paywall_html(
    tool_name: str,
    amount: str,
    network: str,
    recipient: str,
    chain_id: int,
    session_prefix: str,
    sig: str,
) -> str:
    """Build the payment page HTML.

    Uses our custom payment page with wallet connection via window.ethereum
    (MetaMask, Coinbase Wallet, etc.) and EIP-3009 signing.

    NOTE: The x402 SDK's bundled paywall template (3MB) has rendering issues
    in browsers — raw JS source is displayed instead of the UI. We use our
    own clean implementation instead, which directly integrates EIP-712
    signing and the /api/payment-complete callback.
    """
    return _build_fallback_payment_page(
        tool_name=tool_name,
        amount=amount,
        network=network,
        recipient=recipient,
        chain_id=chain_id,
        session_prefix=session_prefix,
        sig=sig,
    )


def _build_callback_script(
    payment_token: str,
    callback_url: str,
    tool_name: str,
    amount: str,
) -> str:
    """Build JavaScript that intercepts x402 payment completion and posts to our callback."""
    return f"""
<script>
(function() {{
  // Override the x402 paywall's submit to also post to our callback
  const originalFetch = window.fetch;
  window.fetch = async function(...args) {{
    const result = await originalFetch.apply(this, args);

    // If this was a payment submission, also notify our server
    const [url, options] = args;
    if (options && options.headers) {{
      const headers = new Headers(options.headers);
      const paymentSig = headers.get('PAYMENT-SIGNATURE') || headers.get('payment-signature');
      if (paymentSig) {{
        try {{
          await originalFetch('{callback_url}', {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify({{
              token: '{payment_token}',
              payload_b64: paymentSig,
            }}),
          }});
          console.log('[MCP Payment] Callback sent successfully');
        }} catch (e) {{
          console.error('[MCP Payment] Callback failed:', e);
        }}
      }}
    }}
    return result;
  }};

  // Also add a manual completion handler for wallets that redirect
  window.mcpPaymentComplete = function(payloadB64) {{
    fetch('{callback_url}', {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify({{
        token: '{payment_token}',
        payload_b64: payloadB64,
      }}),
    }}).then(() => {{
      document.getElementById('mcp-status').textContent = 'Payment confirmed! You can close this tab.';
    }}).catch(e => {{
      document.getElementById('mcp-status').textContent = 'Error confirming payment: ' + e.message;
    }});
  }};
}})();
</script>
<div id="mcp-status" style="position:fixed;bottom:10px;left:50%;transform:translateX(-50%);
    background:#1a1a2e;color:#e0e0e0;padding:8px 16px;border-radius:8px;font-family:system-ui;
    font-size:14px;z-index:9999;">
    Paying for: <strong>{tool_name}</strong> &mdash; {amount} USDC
</div>
"""


def _build_fallback_payment_page(
    tool_name: str,
    amount: str,
    network: str,
    recipient: str,
    chain_id: int,
    session_prefix: str,
    sig: str,
) -> str:
    """Fallback payment page when x402 SDK paywall template is unavailable.

    This page provides instructions and a manual flow using MetaMask/Coinbase Wallet.
    """
    from middleware.payment.constants import USDC_CONTRACTS

    usdc_contract = USDC_CONTRACTS.get(chain_id, "unknown")
    testnet = chain_id in (84532,)
    network_name = "Base Sepolia (Testnet)" if testnet else "Base"
    base_url = _settings.payment_base_url or ""
    callback_url = (
        f"{base_url}/api/payment-complete" if base_url else "/api/payment-complete"
    )

    # Sanitize all values for HTML/JS injection
    safe_amount = html.escape(str(amount))
    safe_tool_name = html.escape(str(tool_name))
    safe_recipient = html.escape(str(recipient))
    safe_usdc_contract = html.escape(str(usdc_contract))
    safe_network = html.escape(str(network))
    safe_sig = html.escape(str(sig))
    safe_callback_url = html.escape(str(callback_url))
    safe_network_name = html.escape(network_name)

    # Use Decimal for precise USDC amount conversion (6 decimals)
    try:
        amount_wei = str(int(Decimal(str(amount)) * 1_000_000))
    except (InvalidOperation, ValueError, ArithmeticError):
        amount_wei = "0"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Payment Required — Google Workspace MCP</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #0f0c29, #302b63, #24243e);
            color: #e0e0e0;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }}
        .card {{
            background: rgba(30, 30, 60, 0.9);
            border: 1px solid rgba(100, 100, 200, 0.3);
            border-radius: 16px;
            padding: 40px;
            max-width: 520px;
            width: 100%;
            backdrop-filter: blur(10px);
        }}
        .header {{ text-align: center; margin-bottom: 32px; }}
        .header h1 {{ font-size: 24px; color: #fff; margin-bottom: 8px; }}
        .header .subtitle {{ color: #888; font-size: 14px; }}
        .amount-display {{
            text-align: center;
            background: rgba(50, 50, 100, 0.5);
            border-radius: 12px;
            padding: 24px;
            margin-bottom: 24px;
        }}
        .amount-display .value {{
            font-size: 48px;
            font-weight: 700;
            color: #3b82f6;
        }}
        .amount-display .currency {{ font-size: 18px; color: #888; margin-left: 4px; }}
        .amount-display .tool-name {{
            margin-top: 8px;
            font-size: 14px;
            color: #aaa;
        }}
        .details {{
            border: 1px solid rgba(100, 100, 200, 0.15);
            border-radius: 8px;
            padding: 16px;
            margin-bottom: 24px;
            font-size: 13px;
        }}
        .details .row {{
            display: flex;
            justify-content: space-between;
            padding: 6px 0;
            border-bottom: 1px solid rgba(100, 100, 200, 0.1);
        }}
        .details .row:last-child {{ border-bottom: none; }}
        .details .label {{ color: #888; }}
        .details .val {{ color: #ccc; font-family: monospace; font-size: 12px; word-break: break-all; }}
        .connect-btn {{
            display: block;
            width: 100%;
            padding: 16px;
            background: linear-gradient(135deg, #3b82f6, #2563eb);
            color: white;
            border: none;
            border-radius: 12px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: transform 0.1s, box-shadow 0.2s;
        }}
        .connect-btn:hover {{ transform: translateY(-1px); box-shadow: 0 4px 20px rgba(59,130,246,0.4); }}
        .connect-btn:disabled {{ opacity: 0.5; cursor: not-allowed; transform: none; }}
        .status {{
            text-align: center;
            margin-top: 16px;
            padding: 12px;
            border-radius: 8px;
            font-size: 14px;
            display: none;
        }}
        .status.show {{ display: block; }}
        .status.success {{ background: rgba(34, 197, 94, 0.15); color: #22c55e; }}
        .status.error {{ background: rgba(239, 68, 68, 0.15); color: #ef4444; }}
        .status.pending {{ background: rgba(59, 130, 246, 0.15); color: #3b82f6; }}
        .powered-by {{
            text-align: center;
            margin-top: 24px;
            font-size: 12px;
            color: #555;
        }}
        .powered-by a {{ color: #3b82f6; text-decoration: none; }}
        {"".join([".testnet-badge { display: inline-block; background: #f59e0b; color: #000; font-size: 11px; padding: 2px 8px; border-radius: 4px; font-weight: 600; }"] if testnet else [])}
    </style>
</head>
<body>
    <div class="card">
        <div class="header">
            <h1>Payment Required</h1>
            <div class="subtitle">
                Google Workspace MCP Server
                {'<span class="testnet-badge">TESTNET</span>' if testnet else ""}
            </div>
        </div>

        <div class="amount-display">
            <span class="value">${safe_amount}</span>
            <span class="currency">USDC</span>
            <div class="tool-name">for access to <strong>{safe_tool_name}</strong></div>
        </div>

        <div class="details">
            <div class="row">
                <span class="label">Network</span>
                <span class="val">{safe_network_name}</span>
            </div>
            <div class="row">
                <span class="label">Recipient</span>
                <span class="val">{html.escape(recipient[:8])}...{html.escape(recipient[-6:])}</span>
            </div>
            <div class="row">
                <span class="label">USDC Contract</span>
                <span class="val">{html.escape(usdc_contract[:8])}...{html.escape(usdc_contract[-6:])}</span>
            </div>
            <div class="row">
                <span class="label">Protocol</span>
                <span class="val">x402 (EIP-3009, gasless)</span>
            </div>
        </div>

        <button class="connect-btn" id="connectBtn" onclick="connectWallet()">
            Connect Wallet & Pay
        </button>

        <div class="status" id="status"></div>

        <div class="powered-by">
            Powered by <a href="https://x402.org" target="_blank">x402 Protocol</a> on
            <a href="https://base.org" target="_blank">Base</a>
        </div>
    </div>

    <script>
    const PAYMENT_CONFIG = {{
        amount: '{safe_amount}',
        amountWei: '{amount_wei}',
        recipient: '{safe_recipient}',
        usdcContract: '{safe_usdc_contract}',
        chainId: {int(chain_id)},
        network: '{safe_network}',
        paymentToken: '{safe_sig}',
        callbackUrl: '{safe_callback_url}',
    }};

    const EIP712_DOMAIN = {{
        name: 'USDC',
        version: '2',
        chainId: PAYMENT_CONFIG.chainId,
        verifyingContract: PAYMENT_CONFIG.usdcContract,
    }};

    const TRANSFER_WITH_AUTH_TYPES = {{
        TransferWithAuthorization: [
            {{ name: 'from', type: 'address' }},
            {{ name: 'to', type: 'address' }},
            {{ name: 'value', type: 'uint256' }},
            {{ name: 'validAfter', type: 'uint256' }},
            {{ name: 'validBefore', type: 'uint256' }},
            {{ name: 'nonce', type: 'bytes32' }},
        ],
    }};

    function setStatus(msg, type) {{
        const el = document.getElementById('status');
        el.textContent = msg;
        el.className = 'status show ' + type;
    }}

    function randomNonce() {{
        const bytes = new Uint8Array(32);
        crypto.getRandomValues(bytes);
        return '0x' + Array.from(bytes).map(b => b.toString(16).padStart(2, '0')).join('');
    }}

    async function connectWallet() {{
        const btn = document.getElementById('connectBtn');
        btn.disabled = true;
        btn.textContent = 'Connecting...';

        try {{
            if (!window.ethereum) {{
                setStatus('No wallet detected. Please install MetaMask or Coinbase Wallet.', 'error');
                btn.disabled = false;
                btn.textContent = 'Connect Wallet & Pay';
                return;
            }}

            // Request wallet connection
            const accounts = await window.ethereum.request({{ method: 'eth_requestAccounts' }});
            const from = accounts[0];
            setStatus('Wallet connected: ' + from.slice(0, 8) + '...', 'pending');

            // Switch to correct chain
            try {{
                await window.ethereum.request({{
                    method: 'wallet_switchEthereumChain',
                    params: [{{ chainId: '0x' + PAYMENT_CONFIG.chainId.toString(16) }}],
                }});
            }} catch (switchErr) {{
                if (switchErr.code === 4902) {{
                    setStatus('Please add the Base network to your wallet.', 'error');
                    btn.disabled = false;
                    btn.textContent = 'Connect Wallet & Pay';
                    return;
                }}
                throw switchErr;
            }}

            btn.textContent = 'Sign Payment...';
            setStatus('Please sign the payment authorization in your wallet...', 'pending');

            // Build EIP-3009 TransferWithAuthorization
            const nonce = randomNonce();
            const validBefore = Math.floor(Date.now() / 1000) + 3600; // 1 hour

            const message = {{
                from: from,
                to: PAYMENT_CONFIG.recipient,
                value: PAYMENT_CONFIG.amountWei,
                validAfter: '0',
                validBefore: String(validBefore),
                nonce: nonce,
            }};

            // EIP-712 typed data signing
            const typedData = JSON.stringify({{
                types: {{
                    EIP712Domain: [
                        {{ name: 'name', type: 'string' }},
                        {{ name: 'version', type: 'string' }},
                        {{ name: 'chainId', type: 'uint256' }},
                        {{ name: 'verifyingContract', type: 'address' }},
                    ],
                    ...TRANSFER_WITH_AUTH_TYPES,
                }},
                primaryType: 'TransferWithAuthorization',
                domain: EIP712_DOMAIN,
                message: message,
            }});

            const signature = await window.ethereum.request({{
                method: 'eth_signTypedData_v4',
                params: [from, typedData],
            }});

            setStatus('Payment signed! Submitting...', 'pending');
            btn.textContent = 'Submitting...';

            // Build x402 payload matching SDK's PaymentPayload format
            const payload = {{
                x402Version: 2,
                payload: {{
                    signature: signature,
                    authorization: {{
                        from: from,
                        to: PAYMENT_CONFIG.recipient,
                        value: PAYMENT_CONFIG.amountWei,
                        validAfter: '0',
                        validBefore: String(validBefore),
                        nonce: nonce,
                    }},
                }},
                accepted: {{
                    scheme: 'exact',
                    network: PAYMENT_CONFIG.network,
                    asset: PAYMENT_CONFIG.usdcContract,
                    amount: PAYMENT_CONFIG.amountWei,
                    payTo: PAYMENT_CONFIG.recipient,
                    maxTimeoutSeconds: 300,
                    extra: {{ name: 'USDC', version: '2' }},
                }},
            }};

            const payloadB64 = btoa(JSON.stringify(payload));

            // Post to our callback endpoint
            const resp = await fetch(PAYMENT_CONFIG.callbackUrl, {{
                method: 'POST',
                headers: {{ 'Content-Type': 'application/json' }},
                body: JSON.stringify({{
                    token: PAYMENT_CONFIG.paymentToken,
                    payload_b64: payloadB64,
                }}),
            }});

            if (resp.ok) {{
                setStatus('Payment confirmed! You can close this tab. Your tool is now unlocked.', 'success');
                btn.textContent = 'Payment Complete';
            }} else {{
                const err = await resp.json();
                setStatus('Payment submission failed: ' + (err.error || 'Unknown error'), 'error');
                btn.disabled = false;
                btn.textContent = 'Retry Payment';
            }}

        }} catch (err) {{
            console.error('Payment error:', err);
            if (err.code === 4001) {{
                setStatus('Payment cancelled by user.', 'error');
            }} else {{
                setStatus('Error: ' + (err.message || err), 'error');
            }}
            btn.disabled = false;
            btn.textContent = 'Connect Wallet & Pay';
        }}
    }}
    </script>
</body>
</html>"""


def _render_error_page(message: str) -> str:
    """Render a simple error page with HTML-escaped message."""
    safe_message = html.escape(message)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Payment Error</title>
</head>
<body style="font-family:system-ui;background:#1a1a2e;color:#e0e0e0;display:flex;
    align-items:center;justify-content:center;min-height:100vh;margin:0;">
    <div style="background:rgba(30,30,60,0.9);border:1px solid rgba(239,68,68,0.3);
        border-radius:16px;padding:40px;max-width:480px;text-align:center;">
        <h1 style="color:#ef4444;margin-bottom:16px;">Payment Error</h1>
        <p>{safe_message}</p>
        <p style="margin-top:24px;color:#666;font-size:13px;">
            If this error persists, please contact the server administrator.
        </p>
    </div>
</body>
</html>"""
