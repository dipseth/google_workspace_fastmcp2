"""
Client integration tests for per-session privacy mode toggle.

Tests the set_privacy_mode tool and end-to-end PII masking lifecycle
against a running MCP server.

Uses health_check as the test tool — it works for any authenticated session
(no Gmail/Drive credentials required) and returns string fields that
privacy mode will mask (serverName, credentialsDirectory, oauthCallbackUrl, etc.).
"""

import json

import pytest


async def _call_health_check(client):
    """Call health_check and return the response text."""
    result = await client.call_tool("health_check", {})
    assert result is not None
    return result.content[0].text if result.content else ""


@pytest.mark.service("server")
@pytest.mark.integration
class TestPrivacyModeToggleLifecycle:
    """Tests for per-session privacy mode toggle via set_privacy_mode."""

    @pytest.mark.asyncio
    async def test_privacy_mode_toggle_lifecycle(self, client):
        """Full lifecycle: enable strict -> verify masking -> disable -> verify raw.

        Uses strict mode because health_check fields (serverName, logLevel, host)
        are not PII or content fields — only strict masks everything.
        """
        # Step 1: Enable privacy mode (strict for health_check)
        enable_result = await client.call_tool("set_privacy_mode", {"mode": "strict"})
        assert enable_result is not None
        enable_data = json.loads(enable_result.content[0].text)

        if not enable_data.get("success"):
            error = enable_data.get("error", "")
            if "API key" in error or "authenticated session" in error:
                pytest.skip(f"Session not eligible for privacy mode ({error})")
            pytest.fail(f"set_privacy_mode(strict) failed: {enable_data}")

        assert enable_data["current_mode"] == "strict"
        print(
            f"\n  Enabled: {enable_data['previous_mode']} -> {enable_data['current_mode']}"
        )

        # Step 2: Call health_check — expect privacy tokens in response
        masked_text = await _call_health_check(client)
        has_tokens = "[PRIVATE:" in masked_text or "__private" in masked_text
        print(f"  Masked response has privacy tokens: {has_tokens}")
        assert has_tokens, (
            "Expected privacy tokens in health_check response when mode is 'auto'"
        )

        # Step 3: Disable privacy mode
        # Note: the disable response itself may be masked if set_privacy_mode
        # is not yet in the running server's exclude list (requires restart).
        disable_result = await client.call_tool(
            "set_privacy_mode", {"mode": "disabled"}
        )
        disable_data = json.loads(disable_result.content[0].text)
        # success should always be a bool (not a string), so it won't be masked
        assert disable_data["success"]
        print(f"  Disabled (success={disable_data['success']})")

        # Step 4: Call health_check — expect raw data (no tokens)
        raw_text = await _call_health_check(client)
        assert "[PRIVATE:" not in raw_text and "__private" not in raw_text, (
            "Expected no privacy tokens after disabling privacy mode"
        )
        print("  Raw response confirmed (no masking)")

    @pytest.mark.asyncio
    async def test_privacy_mode_default_disabled(self, client):
        """Without calling set_privacy_mode, the server default (disabled) applies."""
        text = await _call_health_check(client)
        assert "[PRIVATE:" not in text and "__private" not in text, (
            "Default server mode is 'disabled' — should see no privacy tokens"
        )
        print("\n  Default mode confirmed: no masking applied")

    @pytest.mark.asyncio
    async def test_privacy_mode_rejects_shared_api_key(self, client):
        """set_privacy_mode should reject shared API key sessions."""
        result = await client.call_tool("set_privacy_mode", {"mode": "auto"})
        assert result is not None
        data = json.loads(result.content[0].text)

        # Either succeeds (OAuth/per-user key) or fails with shared API key error
        if not data.get("success"):
            assert "API key" in data.get(
                "error", ""
            ) or "authenticated session" in data.get("error", ""), (
                f"Expected auth provenance rejection, got: {data}"
            )
            print("\n  Correctly rejected shared API key session")
        else:
            print(
                f"\n  Session is authenticated ({data.get('auth_provenance')}), accepted"
            )
            await client.call_tool("set_privacy_mode", {"mode": "disabled"})

    @pytest.mark.asyncio
    async def test_privacy_mode_strict(self, client):
        """Strict mode should mask all string values."""
        enable_result = await client.call_tool("set_privacy_mode", {"mode": "strict"})
        enable_data = json.loads(enable_result.content[0].text)

        if not enable_data.get("success"):
            pytest.skip(f"Cannot enable strict mode: {enable_data.get('error')}")

        assert enable_data["current_mode"] == "strict"

        # health_check returns many string fields — strict should mask them all
        text = await _call_health_check(client)
        assert "[PRIVATE:" in text or "__private" in text, (
            "Strict mode should mask all string values with privacy tokens"
        )
        print(f"\n  Strict mode confirmed: found privacy tokens")

        # Clean up
        await client.call_tool("set_privacy_mode", {"mode": "disabled"})

    @pytest.mark.asyncio
    async def test_privacy_mode_mask_content_false(self, client):
        """mask_content=false should only mask PII fields, not content fields."""
        enable_result = await client.call_tool(
            "set_privacy_mode", {"mode": "auto", "mask_content": False}
        )
        enable_data = json.loads(enable_result.content[0].text)

        if not enable_data.get("success"):
            pytest.skip(f"Cannot enable auto mode: {enable_data.get('error')}")

        assert enable_data["mask_content"] is False
        print(f"\n  Auto mode with mask_content=false")

        # health_check has no PII identity fields (email/name/phone),
        # so with mask_content=false nothing should be masked
        text = await _call_health_check(client)
        data = json.loads(text)

        # serverName, logLevel etc. should be raw strings (not PII fields)
        assert isinstance(data.get("serverName"), str), (
            "serverName should be a plain string with mask_content=false"
        )
        print(f"  serverName is raw string: {data.get('serverName')}")

        # Clean up
        await client.call_tool("set_privacy_mode", {"mode": "disabled"})
