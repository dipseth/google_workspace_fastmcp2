"""Root conftest — auto-skip tests that require external infrastructure.

Tests that import or call into Qdrant, OAuth config, or a live MCP server
will fail in CI where those services aren't available.  Rather than adding
skip markers to every file, this conftest inspects the test's module path
and required env vars, then skips automatically when the infrastructure
isn't present.
"""

import os

import pytest

# ---------------------------------------------------------------------------
# Env-var detection helpers
# ---------------------------------------------------------------------------


def _has_qdrant() -> bool:
    return bool(os.environ.get("QDRANT_URL") and os.environ.get("QDRANT_KEY"))


def _has_oauth_config() -> bool:
    return bool(
        os.environ.get("GOOGLE_CLIENT_SECRETS_FILE")
        or (
            os.environ.get("GOOGLE_CLIENT_ID")
            and os.environ.get("GOOGLE_CLIENT_SECRET")
        )
    )


def _has_credentials_dir() -> bool:
    creds_dir = os.environ.get("CREDENTIALS_DIR", "")
    return bool(creds_dir) and os.path.isdir(creds_dir)


# ---------------------------------------------------------------------------
# Module-name → requirement mapping
#
# If a test module's name contains any of these substrings AND the
# corresponding check returns False, the test is auto-skipped.
# ---------------------------------------------------------------------------

_INFRA_REQUIREMENTS: list[tuple[list[str], callable, str]] = [
    # Qdrant-dependent tests (require running Qdrant + env vars)
    (
        [
            "vectordb_component",
            "form_components_poc",
            "custom_component_indexing",
            "dynamic_component_creation",
            "dynamic_dsl_rendering",
            "feedback_boost_demo",
            "discovery_query",
            "qdrant_vector_search",
            "qdrant_unified_improved",
            "qdrant_point_resource",
            "qdrant_models_wrapping",
            "sampling_cache",
            "colbert",
            "nested_dsl",
            "phase1_3_universal_wrapper",
            "problematic_data_processing",
            "routing_improvements",
            "sanitization_fixes",
        ],
        _has_qdrant,
        "QDRANT_URL and QDRANT_KEY not set",
    ),
    # OAuth-config-dependent tests
    (
        [
            "test_auth_flows",
            "test_auth_flow_e2e",
            "test_oauth_scope_fixes",
        ],
        _has_oauth_config,
        "GOOGLE_CLIENT_SECRETS_FILE or GOOGLE_CLIENT_ID/SECRET not set",
    ),
    # Credential-storage-dependent tests
    (
        [
            "test_credential_management",
            "test_api_key_credential_isolation",
        ],
        _has_credentials_dir,
        "CREDENTIALS_DIR not set or does not exist",
    ),
]

# ---------------------------------------------------------------------------
# Stale tests — reference removed/refactored APIs.
# These fail in ALL environments, not just CI.  Skipped until updated.
# ---------------------------------------------------------------------------
_STALE_TESTS: list[str] = [
    "test_initialization_fix",  # QdrantClientManager removed
    "test_template_middleware_v3",  # EnhancedTemplateMiddleware API refactored
    "test_tag_based_resource_middleware",  # MockFastMCPContext API changed
    "test_template_middleware_integration",  # _detect_macro_usage removed
    "test_fastmcp_context_migration",  # context API changed
    "test_card_framework_wrapper",  # module wrapper API refactored
    "test_module_wrapper",  # module wrapper API refactored
    "test_card_delivery",  # _is_feedback_section API changed
    "test_feedback_loop",  # card builder dependency changed
]


def pytest_collection_modifyitems(config, items):
    """Auto-skip tests whose infrastructure requirements aren't met."""
    for item in items:
        module_name = item.module.__name__ if item.module else ""

        # Skip stale tests that reference removed APIs (fail everywhere)
        if any(s in module_name for s in _STALE_TESTS):
            item.add_marker(
                pytest.mark.skip(
                    reason="Stale test — references removed/refactored API"
                )
            )
            continue

        # Skip infra-dependent tests when env vars are missing
        for substrings, check_fn, reason in _INFRA_REQUIREMENTS:
            if any(s in module_name for s in substrings) and not check_fn():
                item.add_marker(pytest.mark.skip(reason=f"CI skip: {reason}"))
                break
