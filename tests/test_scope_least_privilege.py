"""
Least-privilege scope invariants for Google OAuth verification.

Google's verification review requires (a) the app to request only the
narrowest scopes needed, flagging redundant narrow+full pairs of the
same resource, and (b) every scope a tool requests to be granted by an
OAuth flow, so Cloud Console / consent screen / API traffic all match.

These tests are pure registry logic and run in every environment.
"""

import pytest

from auth.scope_registry import ScopeRegistry

# For each full scope the app requests, the narrower scopes it covers at
# the API level. Requesting both is redundant and Google flags it.
REDUNDANT_UNDER_FULL = {
    "https://www.googleapis.com/auth/drive": [
        "https://www.googleapis.com/auth/drive.readonly",
        "https://www.googleapis.com/auth/drive.file",
    ],
    "https://www.googleapis.com/auth/gmail.modify": [
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/gmail.send",
        "https://www.googleapis.com/auth/gmail.compose",
        "https://www.googleapis.com/auth/gmail.labels",
    ],
    "https://www.googleapis.com/auth/calendar": [
        "https://www.googleapis.com/auth/calendar.readonly",
        "https://www.googleapis.com/auth/calendar.events",
    ],
    "https://www.googleapis.com/auth/documents": [
        "https://www.googleapis.com/auth/documents.readonly",
    ],
    "https://www.googleapis.com/auth/spreadsheets": [
        "https://www.googleapis.com/auth/spreadsheets.readonly",
    ],
    "https://www.googleapis.com/auth/presentations": [
        "https://www.googleapis.com/auth/presentations.readonly",
    ],
    "https://www.googleapis.com/auth/forms.body": [
        "https://www.googleapis.com/auth/forms.body.readonly",
    ],
    "https://www.googleapis.com/auth/tasks": [
        "https://www.googleapis.com/auth/tasks.readonly",
    ],
    "https://www.googleapis.com/auth/contacts": [
        "https://www.googleapis.com/auth/contacts.readonly",
    ],
    "https://www.googleapis.com/auth/chat.messages": [
        "https://www.googleapis.com/auth/chat.messages.readonly",
    ],
    "https://www.googleapis.com/auth/chat.memberships": [
        "https://www.googleapis.com/auth/chat.memberships.readonly",
    ],
}

# Narrow scopes that MUST stay: no requested full scope covers them.
REQUIRED_NARROW_SCOPES = {
    "https://www.googleapis.com/auth/forms.responses.readonly",
    "https://www.googleapis.com/auth/directory.readonly",
}

# Scope groups used only by the Chat service account (domain-wide
# delegation / app identity), not by the user OAuth consent flow.
SERVICE_ACCOUNT_GROUPS = {"chat_bot", "chat_app", "admin_suite"}


def _granted_workspace_scopes() -> set:
    return set(ScopeRegistry.resolve_scope_group("oauth_comprehensive"))


def _granted_photos_scopes() -> set:
    return set(ScopeRegistry.resolve_scope_group("photos_basic"))


class TestNoRedundantScopePairs:
    def test_oauth_comprehensive_has_no_redundant_pairs(self):
        granted = _granted_workspace_scopes()
        for full, narrows in REDUNDANT_UNDER_FULL.items():
            if full in granted:
                overlap = granted & set(narrows)
                assert not overlap, (
                    f"oauth_comprehensive requests {sorted(overlap)} alongside "
                    f"{full}, which already covers them — Google's verification "
                    f"flags redundant narrow+full pairs"
                )

    def test_required_narrow_scopes_survive_the_trim(self):
        granted = _granted_workspace_scopes()
        missing = REQUIRED_NARROW_SCOPES - granted
        assert not missing, (
            f"These scopes have no covering full scope and must stay: {missing}"
        )

    def test_photos_flow_untouched(self):
        assert _granted_photos_scopes() >= {
            "https://www.googleapis.com/auth/photoslibrary.appendonly",
            "https://www.googleapis.com/auth/photoslibrary.readonly.appcreateddata",
            "https://www.googleapis.com/auth/photoslibrary.edit.appcreateddata",
        }


class TestRequestedScopesAreGranted:
    """Every scope tools request by default must be granted by an OAuth flow.

    Otherwise service requests log 'missing scopes' warnings and the
    consent screen / Cloud Console / API traffic drift apart — the exact
    mismatch Google's verification review rejects.
    """

    def test_service_defaults_are_subset_of_granted(self):
        granted = _granted_workspace_scopes() | _granted_photos_scopes()
        for service in ScopeRegistry.SERVICE_METADATA:
            if service in ScopeRegistry.SEPARATE_AUTH_SERVICES:
                requested = set(ScopeRegistry.get_service_scopes(service, "basic"))
                extra = requested - _granted_photos_scopes()
            else:
                requested = set(ScopeRegistry.get_service_scopes(service, "basic"))
                extra = requested - granted
            assert not extra, (
                f"Service '{service}' requests scopes no OAuth flow grants: "
                f"{sorted(extra)}"
            )

    def test_user_scope_groups_are_subset_of_granted(self):
        granted = _granted_workspace_scopes() | _granted_photos_scopes()
        skip = SERVICE_ACCOUNT_GROUPS | {"oauth_comprehensive"}
        failures = {}
        for group in ScopeRegistry.SERVICE_SCOPE_GROUPS:
            if group in skip or group.endswith("_full"):
                continue
            extra = set(ScopeRegistry.resolve_scope_group(group)) - granted
            if extra:
                failures[group] = sorted(extra)
        assert not failures, (
            f"User-flow scope groups request scopes no OAuth flow grants: {failures}"
        )

    def test_settings_fallback_matches_registry(self):
        from config.settings import settings

        fallback = set(settings._fallback_drive_scopes)
        registry = _granted_workspace_scopes()
        assert fallback == registry, (
            "settings._fallback_drive_scopes drifted from the registry's "
            f"oauth_comprehensive group. Only in fallback: "
            f"{sorted(fallback - registry)}; only in registry: "
            f"{sorted(registry - fallback)}"
        )

    def test_dcr_defaults_are_subset_of_granted(self):
        from auth.compatibility_shim import CompatibilityShim

        dcr = set(CompatibilityShim.get_legacy_dcr_scope_defaults().split())
        assert dcr <= _granted_workspace_scopes(), (
            f"DCR default scopes not granted by the Workspace flow: "
            f"{sorted(dcr - _granted_workspace_scopes())}"
        )
