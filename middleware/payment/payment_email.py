"""Payment request email builder using MJML email blocks.

Generates a payment request email with a "Pay Now" button and QR code
linking to the browser payment page. Uses the existing EmailSpec/block
infrastructure from ``gmail/mjml_types.py``.

The email includes:
- What tool requires payment
- How much USDC is needed
- Which network (Base/Ethereum)
- A prominent "Pay Now" button linking to /pay?token=...
- A QR code for mobile wallet scanning (opens same /pay page)
"""

from __future__ import annotations

import base64
import io
from typing import Optional

from config.enhanced_logging import setup_logger
from config.settings import settings

logger = setup_logger()


def _generate_qr_data_uri(url: str, box_size: int = 8, border: int = 2) -> str:
    """Generate a QR code as a base64 data URI for embedding in emails.

    Args:
        url: The URL to encode in the QR code.
        box_size: Size of each box in the QR grid (pixels).
        border: Border width in boxes.

    Returns:
        A ``data:image/png;base64,...`` string suitable for ``<img src=...>``.
    """
    try:
        import qrcode
        from qrcode.image.pil import PilImage

        qr = qrcode.QRCode(
            version=None,  # auto-size
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=box_size,
            border=border,
        )
        qr.add_data(url)
        qr.make(fit=True)

        img: PilImage = qr.make_image(fill_color="#1a1a2e", back_color="white")

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode()
        return f"data:image/png;base64,{b64}"

    except Exception as exc:
        logger.warning("QR code generation failed: %s", exc)
        return ""


def _generate_qr_png_bytes(url: str, box_size: int = 8, border: int = 2) -> bytes:
    """Generate a QR code as raw PNG bytes.

    Args:
        url: The URL to encode.
        box_size: Size of each box in the QR grid (pixels).
        border: Border width in boxes.

    Returns:
        PNG image bytes, or empty bytes on failure.
    """
    try:
        import qrcode
        from qrcode.image.pil import PilImage

        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=box_size,
            border=border,
        )
        qr.add_data(url)
        qr.make(fit=True)

        img: PilImage = qr.make_image(fill_color="#1a1a2e", back_color="white")

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    except Exception as exc:
        logger.warning("QR PNG generation failed: %s", exc)
        return b""


def build_payment_email(
    tool_name: str,
    amount: str,
    network: str,
    recipient_wallet: str,
    payment_url: str,
    recipient_email: Optional[str] = None,
    session_prefix: str = "",
) -> dict:
    """Build a payment request email using MJML blocks.

    Args:
        tool_name: The tool that requires payment.
        amount: USDC amount (e.g., "0.01").
        network: CAIP-2 network (e.g., "eip155:8453").
        recipient_wallet: Wallet address receiving payment.
        payment_url: Full signed URL to the /pay page.
        recipient_email: Email address to send to (if known from session).
        session_prefix: Session ID prefix for display.

    Returns:
        Dict with keys: subject, blocks (list of EmailBlock instances),
        and recipient_email (if provided).
    """
    from gmail.mjml_types import (
        ButtonBlock,
        DividerBlock,
        EmailSpec,
        HeroBlock,
        ImageBlock,
        TextBlock,
    )

    chain_id = settings.payment_chain_id
    testnet = chain_id in (84532,)
    network_name = "Base Sepolia (Testnet)" if testnet else "Base"

    subject = f"Payment Required: ${amount} USDC for {tool_name}"

    blocks = [
        HeroBlock(
            title="Payment Required",
            subtitle=f"${amount} USDC to access {tool_name}",
            background_color="#1a1a2e",
        ),
        TextBlock(
            text=(
                f"A tool you're using (<strong>{tool_name}</strong>) requires a "
                f"<strong>${amount} USDC</strong> payment on <strong>{network_name}</strong> "
                f"to continue."
            ),
            padding="16px 24px 8px 24px",
        ),
        TextBlock(
            text=(
                "Click the button below to open the payment page. "
                "You'll connect your wallet (MetaMask, Coinbase Wallet, etc.), "
                "review the details, and sign a gasless authorization. "
                "<strong>You won't pay any gas fees.</strong>"
            ),
            padding="8px 24px",
            color="#888888",
        ),
        DividerBlock(),
        TextBlock(
            text="<strong>Payment Details</strong>",
            padding="8px 24px 4px 24px",
        ),
        TextBlock(
            text=(
                f"&bull; <strong>Amount:</strong> ${amount} USDC<br/>"
                f"&bull; <strong>Network:</strong> {network_name}<br/>"
                f"&bull; <strong>Recipient:</strong> {recipient_wallet[:10]}...{recipient_wallet[-6:]}<br/>"
                f"&bull; <strong>Protocol:</strong> x402 (EIP-3009, gasless)<br/>"
                + (
                    "&bull; <strong>Mode:</strong> <span style='color:#f59e0b;'>TESTNET</span><br/>"
                    if testnet
                    else ""
                )
            ),
            padding="4px 24px 16px 24px",
            font_size="13px",
        ),
        ButtonBlock(
            text=f"Pay ${amount} USDC Now",
            url=payment_url,
            background_color="#3b82f6",
            border_radius="12px",
            padding="16px 24px",
        ),
        TextBlock(
            text=("<strong>Or scan with your mobile wallet:</strong>"),
            padding="16px 24px 4px 24px",
            color="#888888",
            font_size="13px",
        ),
    ]

    # Build QR code URL — served by /pay/qr endpoint with same params
    # Extract query string from payment_url to build /pay/qr URL
    from urllib.parse import urlparse

    parsed_pay = urlparse(payment_url)
    base = payment_url.split("/pay?")[0] if "/pay?" in payment_url else ""
    qr_url = f"{base}/pay/qr?{parsed_pay.query}" if base and parsed_pay.query else ""

    if qr_url:
        blocks.append(
            ImageBlock(
                src=qr_url,
                alt=f"QR code to pay ${amount} USDC for {tool_name}",
                width="200px",
                href=payment_url,
                padding="4px 24px 8px 24px",
            )
        )
        blocks.append(
            TextBlock(
                text=(
                    "Scan this QR code with Coinbase Wallet or MetaMask mobile "
                    "to open the payment page on your phone."
                ),
                padding="0 24px 8px 24px",
                color="#666666",
                font_size="11px",
            )
        )

    blocks += [
        TextBlock(
            text=(
                "This link expires in 15 minutes. If it expires, "
                "the tool will generate a new payment request."
            ),
            padding="8px 24px",
            color="#666666",
            font_size="12px",
        ),
        DividerBlock(),
        TextBlock(
            text=(
                '<span style="font-size:11px;color:#555;">'
                'Powered by <a href="https://x402.org" style="color:#3b82f6;">x402 Protocol</a> '
                'on <a href="https://base.org" style="color:#3b82f6;">Base</a>. '
                "Your payment is a signed authorization — no gas fees, "
                "no on-chain transaction from your wallet."
                "</span>"
            ),
            padding="8px 24px 24px 24px",
        ),
    ]

    return {
        "subject": subject,
        "blocks": blocks,
        "recipient_email": recipient_email,
        "spec": EmailSpec(subject=subject, blocks=blocks),
    }


async def send_payment_email(
    tool_name: str,
    amount: str,
    network: str,
    recipient_wallet: str,
    payment_url: str,
    recipient_email: str,
    session_prefix: str = "",
) -> bool:
    """Build and send a payment request email.

    Uses the Gmail tools to send the rendered MJML email.

    Args:
        tool_name: The tool requiring payment.
        amount: USDC amount.
        network: CAIP-2 network.
        recipient_wallet: Wallet receiving payment.
        payment_url: Signed /pay URL.
        recipient_email: Email to send to.
        session_prefix: Session prefix for logging.

    Returns:
        True if email was sent successfully, False otherwise.
    """
    try:
        email_data = build_payment_email(
            tool_name=tool_name,
            amount=amount,
            network=network,
            recipient_wallet=recipient_wallet,
            payment_url=payment_url,
            recipient_email=recipient_email,
            session_prefix=session_prefix,
        )

        spec = email_data["spec"]
        render_result = spec.render()

        if not render_result.success:
            logger.error(
                "Failed to render payment email MJML: %s",
                render_result.diagnostics,
            )
            return False

        # Send via Gmail API (requires auth context)
        from gmail.gmail_tools import _get_gmail_service

        service = await _get_gmail_service()
        if not service:
            logger.error("Cannot send payment email: no Gmail service available")
            return False

        import base64
        from email.mime.text import MIMEText

        message = MIMEText(render_result.html, "html")
        message["to"] = recipient_email
        message["subject"] = email_data["subject"]
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()

        service.users().messages().send(userId="me", body={"raw": raw}).execute()

        logger.info(
            "Payment email sent to %s for tool %s ($%s USDC)",
            recipient_email,
            tool_name,
            amount,
        )
        return True

    except Exception as exc:
        logger.error("Failed to send payment email: %s", exc, exc_info=True)
        return False


__all__ = [
    "build_payment_email",
    "send_payment_email",
]
