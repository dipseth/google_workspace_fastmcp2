from pathlib import Path

import pytest


def _sample_email_spec():
    from gmail.mjml_types import (
        EmailSpec,
        FooterBlock,
        HeroBlock,
        SpacerBlock,
        TextBlock,
    )

    return EmailSpec(
        subject="Welcome!",
        preheader="Thanks for joining",
        blocks=[
            HeroBlock(
                title="Welcome to RiversUnlimited",
                subtitle="We’re glad you’re here.",
                cta_text="Get started",
                cta_url="https://example.com/start",
            ),
            SpacerBlock(height_px=8),
            TextBlock(text="This email was generated from an EmailSpec."),
            FooterBlock(
                text="You received this because you signed up.",
                unsubscribe_url="https://example.com/unsub",
            ),
        ],
    )


def test_email_spec_to_mjml_is_deterministic():
    from gmail.mjml_wrapper import email_spec_to_mjml

    spec = _sample_email_spec()
    mjml1 = email_spec_to_mjml(spec)
    mjml2 = email_spec_to_mjml(spec)
    assert mjml1 == mjml2
    assert "<mjml>" in mjml1
    assert "<mj-button" in mjml1


def test_normalize_html_for_snapshot_is_stable():
    from gmail.mjml_wrapper import normalize_html_for_snapshot

    raw = """<!doctype html>
    <!-- comment -->
    <div>
      <span> hi </span>
    </div>
    """
    normalized = normalize_html_for_snapshot(raw)
    assert "comment" not in normalized
    assert "><" in normalized
    assert "  " not in normalized


def test_render_returns_structured_error_when_mjml_missing():
    from gmail.mjml_types import MjmlRenderOptions
    from gmail.mjml_wrapper import email_spec_to_mjml, render_email_spec

    spec = _sample_email_spec()

    # Always create artifacts directory and save the MJML source
    artifacts_dir = Path(__file__).parent / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    # Always save the MJML source so it can be previewed (e.g., at https://mjml.io/try-it-live)
    mjml_source = email_spec_to_mjml(spec)
    mjml_path = artifacts_dir / "mjml_sample_email.mjml"
    mjml_path.write_text(mjml_source, encoding="utf-8")
    print(f"\n[MJML source saved to: {mjml_path}]")

    result = render_email_spec(spec, options=MjmlRenderOptions())

    # If MJML is installed locally, persist the rendered HTML so it can be viewed.
    # This makes it easy to iterate on output quality while developing.
    if result.success and result.html:
        html_path = artifacts_dir / "mjml_sample_email.html"
        html_path.write_text(result.html, encoding="utf-8")
        print(f"[HTML output saved to: {html_path}]")

        normalized_path = artifacts_dir / "mjml_sample_email.normalized.html"
        normalized_path.write_text(result.normalized_html or "", encoding="utf-8")
    else:
        print(
            f"[MJML CLI not installed - only MJML source saved. Install with: npm install -g mjml]"
        )

    # In CI/dev environments without MJML installed, we expect a structured failure.
    # If MJML is installed, rendering will succeed; accept either outcome.
    if result.success:
        assert result.html
        assert result.normalized_html
    else:
        assert result.diagnostics
        assert any("MJML CLI not found" in d.message for d in result.diagnostics)
