"""
MJML rendering pipeline for EmailSpec.

Provides:
- email_spec_to_mjml() — convert EmailSpec to MJML markup
- render_email_spec() — render EmailSpec to HTML (tries Python mjml, then CLI)
- normalize_html_for_snapshot() — normalize HTML for snapshot testing
"""

import logging
import re
import subprocess
from typing import Optional

from gmail.mjml_types import (
    EmailSpec,
    MjmlDiagnostic,
    MjmlRenderOptions,
    MjmlRenderResult,
)

logger = logging.getLogger(__name__)


def email_spec_to_mjml(spec: EmailSpec) -> str:
    """Convert EmailSpec to MJML markup string.

    This is a pure function — same input always produces same output.
    """
    return spec.to_mjml()


def render_email_spec(
    spec: EmailSpec,
    options: Optional[MjmlRenderOptions] = None,
) -> MjmlRenderResult:
    """Render EmailSpec to HTML.

    Attempts rendering via:
    1. mjml Python package (pure Python MJML implementation)
    2. MJML CLI (subprocess: mjml --stdin)
    3. Returns structured error with diagnostics on failure
    """
    options = options or MjmlRenderOptions()
    mjml_source = email_spec_to_mjml(spec)

    # Strategy 1: Python mjml package
    try:
        from mjml import mjml_to_html

        result = mjml_to_html(mjml_source)
        html = result.html
        if result.errors:
            return MjmlRenderResult(
                success=False,
                mjml_source=mjml_source,
                diagnostics=[MjmlDiagnostic(message=str(e)) for e in result.errors],
            )
        return MjmlRenderResult(
            success=True,
            html=html,
            normalized_html=normalize_html_for_snapshot(html),
            mjml_source=mjml_source,
        )
    except ImportError:
        logger.debug("mjml Python package not available, trying CLI")
    except Exception as e:
        logger.warning(f"mjml Python render error: {e}")
        return MjmlRenderResult(
            success=False,
            mjml_source=mjml_source,
            diagnostics=[MjmlDiagnostic(message=f"mjml Python render error: {e}")],
        )

    # Strategy 2: MJML CLI
    try:
        result = subprocess.run(
            ["mjml", "--stdin", "--stdout"],
            input=mjml_source,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            html = result.stdout
            return MjmlRenderResult(
                success=True,
                html=html,
                normalized_html=normalize_html_for_snapshot(html),
                mjml_source=mjml_source,
            )
        else:
            return MjmlRenderResult(
                success=False,
                mjml_source=mjml_source,
                diagnostics=[
                    MjmlDiagnostic(message=f"MJML CLI error: {result.stderr}")
                ],
            )
    except FileNotFoundError:
        logger.debug("MJML CLI not found")
    except subprocess.TimeoutExpired:
        return MjmlRenderResult(
            success=False,
            mjml_source=mjml_source,
            diagnostics=[MjmlDiagnostic(message="MJML CLI timed out")],
        )
    except Exception as e:
        return MjmlRenderResult(
            success=False,
            mjml_source=mjml_source,
            diagnostics=[MjmlDiagnostic(message=f"MJML CLI error: {e}")],
        )

    # Neither available
    return MjmlRenderResult(
        success=False,
        mjml_source=mjml_source,
        diagnostics=[
            MjmlDiagnostic(
                message="MJML CLI not found. Install with: pip install mjml OR npm install -g mjml"
            )
        ],
    )


def normalize_html_for_snapshot(html: str) -> str:
    """Normalize HTML for snapshot testing.

    - Strip HTML comments
    - Collapse whitespace
    - Remove blank lines
    """
    # Remove HTML comments
    html = re.sub(r"<!--.*?-->", "", html, flags=re.DOTALL)
    # Collapse whitespace between tags
    html = re.sub(r">\s+<", "><", html)
    # Collapse runs of whitespace to single space
    html = re.sub(r"\s+", " ", html)
    return html.strip()
