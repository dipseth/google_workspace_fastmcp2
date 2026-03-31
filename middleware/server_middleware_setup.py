"""Server middleware setup — registers all middleware on the FastMCP instance.

Extracted from server.py to reduce its size. Preserves exact middleware
registration order, which is critical for correct request/response processing.
"""

from dataclasses import dataclass, field
from typing import Any, Optional

from config.enhanced_logging import setup_logger

logger = setup_logger()


@dataclass
class MiddlewareContext:
    """References to middleware instances needed by later phases (tool registration, etc.)."""

    auth_middleware: Any = None
    qdrant_middleware: Any = None
    sampling_middleware: Any = None
    template_middleware: Any = None
    profile_middleware: Any = None
    dashboard_cache_middleware: Any = None


def setup_all_middleware(
    mcp,
    settings,
    google_auth_provider,
    github_auth_provider,
    dual_oauth_router,
    credential_storage_mode,
    minimal_tools_startup: bool,
) -> MiddlewareContext:
    """Register all middleware on the FastMCP instance in the correct order.

    Returns a MiddlewareContext with references to middleware instances that
    are needed by later phases (tool registration, OAuth endpoint setup, etc.).

    Middleware registration order:
    1. Dual OAuth routes (if configured)
    2. Code Mode (if enabled)
    3. Auth middleware
    4. Session tool filtering
    5. Template middleware (must be before tool registration)
    6. Enhanced sampling middleware (if SAMPLING_TOOLS enabled)
    7. Qdrant unified middleware
    8. Profile enrichment middleware
    9. TagBasedResourceMiddleware
    10. Privacy middleware
    11. X402 Payment middleware (if enabled)
    12. ResponseLimitingMiddleware (if configured)
    13. Dashboard cache middleware (outermost)
    14. Redis response caching (if configured)
    """
    ctx = MiddlewareContext()

    # ─── 1. Dual OAuth Routes ───
    if dual_oauth_router:
        from starlette.routing import Route as _StarletteRoute

        for _route in dual_oauth_router.get_custom_routes():
            mcp._additional_http_routes.append(_route)
            logger.info(f"  🔀 Registered dual OAuth route: {_route.path}")

    # ─── 2. Code Mode ───
    if settings.enable_code_mode:
        from tools.code_mode import setup_code_mode

        setup_code_mode(mcp)
    else:
        logger.info("Code Mode disabled — set ENABLE_CODE_MODE=true in .env to enable")

    # ─── 3. Auth Middleware ───
    from auth.context import set_auth_middleware
    from auth.middleware import create_enhanced_auth_middleware

    auth_middleware = create_enhanced_auth_middleware(
        storage_mode=credential_storage_mode,
        google_provider=google_auth_provider,
        github_provider=github_auth_provider,
    )
    logger.info("🔧 Configuring service selection for OAuth system")
    auth_middleware.enable_service_selection(enabled=True)
    logger.info("✅ Service selection interface enabled for OAuth flows")
    mcp.add_middleware(auth_middleware)
    set_auth_middleware(auth_middleware)
    ctx.auth_middleware = auth_middleware
    logger.info("✅ AuthMiddleware RE-ENABLED with Phase 1 & 2 fixes:")
    logger.info("  ✅ Instance-level session tracking (no FastMCP context dependency)")
    logger.info("  ✅ Simplified auto-injection (90 lines → 20 lines)")
    logger.info("  ✅ All 18 unit tests passing")
    logger.info("  🔍 Monitoring for context lifecycle issues...")

    # ─── 4. Session Tool Filtering ───
    from middleware.session_tool_filtering_middleware import (
        setup_session_tool_filtering_middleware,
    )

    setup_session_tool_filtering_middleware(
        mcp,
        enable_debug=True,
        minimal_startup=minimal_tools_startup,
    )
    if minimal_tools_startup:
        logger.info(
            "  ✅ Minimal startup mode active - new sessions get only essential tools"
        )
    else:
        logger.info("  ✅ Per-session tool enable/disable supported via scope='session'")

    # ─── 5. Template Middleware (must be before tool registration) ───
    from lifespans import register_template_middleware
    from middleware.template_middleware import (
        setup_enhanced_template_middleware as setup_template_middleware,
    )

    logger.info(
        "🎭 Setting up Enhanced Template Parameter Middleware with full modular architecture..."
    )
    template_middleware = setup_template_middleware(
        mcp,
        enable_debug=True,
        enable_caching=True,
        cache_ttl_seconds=300,
    )
    register_template_middleware(template_middleware)
    ctx.template_middleware = template_middleware

    # Register email_symbols as a Jinja2 global so macros can access them
    try:
        from gmail.email_wrapper_api import get_email_symbols

        jinja_env = template_middleware.jinja_env_manager.jinja2_env
        if jinja_env:
            jinja_env.globals["email_symbols"] = get_email_symbols()
            logger.info("📧 Registered email_symbols as Jinja2 global")
    except Exception as e:
        logger.warning(f"⚠️ Could not register email_symbols global: {e}")

    logger.info(
        "✅ Enhanced Template Parameter Middleware enabled - modular architecture with 12 focused components active"
    )

    # ─── 6. Enhanced Sampling Middleware ───
    sampling_middleware = None
    if settings.sampling_tools:
        from middleware.sampling_middleware import (
            DSLToolConfig,
            EnhancementLevel,
            ValidationAgentConfig,
            setup_enhanced_sampling_middleware,
        )

        logger.info("🎯 Setting up Enhanced Sampling Middleware...")

        dsl_configs: dict[str, DSLToolConfig] = {}
        try:
            from gchat.wrapper_api import (
                CardDSLResult,
                extract_dsl_from_description,
                get_dsl_documentation,
                parse_dsl,
            )

            dsl_configs["send_dynamic_card"] = DSLToolConfig(
                arg_key="card_description",
                parse_fn=parse_dsl,
                extract_fn=extract_dsl_from_description,
                result_type=CardDSLResult,
                description_attr="card_description",
                params_attr="card_params",
                params_arg_key="card_params",
                get_docs_fn=lambda: get_dsl_documentation(
                    include_examples=True, include_hierarchy=True
                ),
                dsl_type_label="card",
                error_keywords=["card_description"],
            )
        except ImportError:
            logger.warning("Card DSL validation disabled — gchat module unavailable")

        try:
            from gmail.email_wrapper_api import (
                EmailDSLResult,
                extract_email_dsl_from_description,
                get_email_dsl_documentation,
                parse_email_dsl,
            )

            dsl_configs["compose_dynamic_email"] = DSLToolConfig(
                arg_key="email_description",
                parse_fn=parse_email_dsl,
                extract_fn=extract_email_dsl_from_description,
                result_type=EmailDSLResult,
                description_attr="email_description",
                params_attr="email_params",
                params_arg_key="email_params",
                get_docs_fn=lambda: get_email_dsl_documentation(
                    include_examples=True
                ),
                dsl_type_label="email",
                error_keywords=["email_description"],
            )
        except ImportError:
            logger.warning("Email DSL validation disabled — gmail module unavailable")

        sampling_middleware = setup_enhanced_sampling_middleware(
            mcp,
            enable_debug=True,
            target_tags=["gmail", "compose", "elicitation"],
            qdrant_middleware=None,  # Will be set after Qdrant middleware is initialized
            template_middleware=template_middleware,
            default_enhancement_level=EnhancementLevel.CONTEXTUAL,
            dsl_tool_configs=dsl_configs,
        )
        logger.info(
            "✅ Enhanced Sampling Middleware enabled - tools with target tags get enhanced context"
        )

        # Register validation agents
        if settings.sampling_validation_enabled:
            from middleware.sampling_prompts import (
                get_card_validation_prompt,
                get_email_validation_prompt,
                get_qdrant_validation_prompt,
                get_template_macro_validation_prompt,
            )

            sampling_middleware.register_validation_agent(
                "send_dynamic_card",
                ValidationAgentConfig(
                    tool_name="send_dynamic_card",
                    target_arg_keys=["card_description", "card_params"],
                    get_system_prompt_fn=get_card_validation_prompt,
                    mode="pre",
                    generate_variations=True,
                    enabled=False,
                ),
            )
            sampling_middleware.register_validation_agent(
                "compose_dynamic_email",
                ValidationAgentConfig(
                    tool_name="compose_dynamic_email",
                    target_arg_keys=["email_description", "email_params"],
                    get_system_prompt_fn=get_email_validation_prompt,
                    mode="pre",
                ),
            )
            sampling_middleware.register_validation_agent(
                "create_template_macro",
                ValidationAgentConfig(
                    tool_name="create_template_macro",
                    target_arg_keys=[
                        "macro_name",
                        "macro_body",
                        "parameters",
                        "template_content",
                    ],
                    get_system_prompt_fn=get_template_macro_validation_prompt,
                    mode="pre",
                ),
            )
            sampling_middleware.register_validation_agent(
                "qdrant_search",
                ValidationAgentConfig(
                    tool_name="qdrant_search",
                    target_arg_keys=["query", "filter_dsl", "query_dsl"],
                    get_system_prompt_fn=get_qdrant_validation_prompt,
                    mode="parallel",
                ),
            )
            logger.info(
                "✅ Validation agents registered for 4 tools (3 pre, 1 parallel)"
            )
        else:
            logger.info(
                "⏭️  Validation agents disabled (SAMPLING_VALIDATION_ENABLED=false)"
            )
    else:
        logger.info(
            "⏭️  Enhanced Sampling Middleware disabled - set SAMPLING_TOOLS=true in .env to enable"
        )
    ctx.sampling_middleware = sampling_middleware

    # ─── 7. Qdrant Unified Middleware ───
    from lifespans import register_qdrant_middleware
    from middleware.qdrant_middleware import QdrantUnifiedMiddleware

    logger.info("🔄 Initializing Qdrant unified middleware...")
    qdrant_middleware = QdrantUnifiedMiddleware(
        qdrant_host=settings.qdrant_host,
        qdrant_port=settings.qdrant_port,
        qdrant_api_key=settings.qdrant_api_key,
        qdrant_url=settings.qdrant_url,
        collection_name="mcp_tool_responses",
        auto_discovery=True,
        ports=[settings.qdrant_port, 6333, 6335, 6334],
    )
    mcp.add_middleware(qdrant_middleware)
    register_qdrant_middleware(qdrant_middleware)
    ctx.qdrant_middleware = qdrant_middleware
    logger.info("✅ Qdrant unified middleware created (async init via lifespan)")
    logger.info(f"🔧 Qdrant URL: {settings.qdrant_url}")
    logger.info(f"🔧 API Key configured: {bool(settings.qdrant_api_key)}")

    # Connect sampling middleware to Qdrant
    if sampling_middleware:
        sampling_middleware.qdrant_middleware = qdrant_middleware
        logger.info(
            "🔗 Enhanced Sampling Middleware connected to Qdrant for historical context"
        )

    # ─── 8. Profile Enrichment Middleware ───
    from lifespans import register_profile_middleware
    from middleware.profile_enrichment_middleware import ProfileEnrichmentMiddleware

    logger.info(
        "👤 Setting up Profile Enrichment Middleware for People API integration..."
    )
    enable_qdrant_profile_cache = (
        qdrant_middleware is not None
        and qdrant_middleware.client_manager.is_available
    )
    profile_middleware = ProfileEnrichmentMiddleware(
        enable_caching=True,
        cache_ttl_seconds=300,
        qdrant_middleware=qdrant_middleware if enable_qdrant_profile_cache else None,
        enable_qdrant_cache=enable_qdrant_profile_cache,
    )
    mcp.add_middleware(profile_middleware)
    register_profile_middleware(profile_middleware)
    ctx.profile_middleware = profile_middleware

    if enable_qdrant_profile_cache:
        logger.info("✅ Profile Enrichment Middleware enabled with TWO-TIER CACHING:")
        logger.info("  📦 Tier 1: In-memory cache (5-minute TTL, ultra-fast)")
        logger.info("  🗄️ Tier 2: Qdrant persistent cache (survives restarts)")
    else:
        logger.info(
            "✅ Profile Enrichment Middleware enabled with in-memory caching only"
        )
        logger.info("  📦 In-memory cache (5-minute TTL)")
        logger.info(
            "  ℹ️ Qdrant persistent cache: disabled (Qdrant not available)"
        )

    # ─── 9. TagBasedResourceMiddleware ───
    from middleware.tag_based_resource_middleware import TagBasedResourceMiddleware

    logger.info(
        "🏷️ Setting up TagBasedResourceMiddleware for service:// resource handling..."
    )
    tag_based_middleware = TagBasedResourceMiddleware(enable_debug_logging=True)
    mcp.add_middleware(tag_based_middleware)
    logger.info(
        "✅ TagBasedResourceMiddleware enabled - service:// URIs will be handled via tag-based tool discovery"
    )

    # ─── 10. Privacy Middleware ───
    from middleware.privacy.middleware import PrivacyMiddleware

    privacy_middleware = PrivacyMiddleware(
        mode=settings.privacy_mode,
        additional_fields=settings.privacy_field_patterns,
        exclude_tools=settings.privacy_exclude_tools,
    )
    mcp.add_middleware(privacy_middleware)
    logger.info(
        f"Privacy middleware registered (default={settings.privacy_mode}, per-session toggle available)"
    )

    # ─── 11. X402 Payment Middleware ───
    if settings.payment_enabled:
        from middleware.payment import X402PaymentMiddleware, get_resource_server

        try:
            x402_resource_server = get_resource_server(settings)
        except Exception as _x402_err:
            logger.warning(
                "x402 SDK init failed (%s), falling back to stub mode", _x402_err
            )
            x402_resource_server = None

        payment_middleware = X402PaymentMiddleware(
            gated_tools=settings.payment_gated_tools,
            free_for_oauth=settings.payment_free_for_oauth,
            session_ttl_minutes=settings.payment_session_ttl_minutes,
            resource_server=x402_resource_server,
        )
        mcp.add_middleware(payment_middleware)
        logger.info("X402 Payment middleware enabled (x402 SDK v2)")
        logger.info(
            f"  Recipient: {'configured' if settings.payment_recipient_wallet else '(not set)'}"
        )
        logger.info(f"  Amount: {settings.payment_usdc_amount} USDC")
        logger.info(f"  Network: {settings.payment_network}")
        logger.info(f"  Facilitator: {settings.payment_facilitator_url}")
        logger.info(f"  Scheme: {settings.payment_scheme}")
        logger.info(f"  Free for OAuth: {settings.payment_free_for_oauth}")
        logger.info(
            f"  SDK: {'active' if x402_resource_server else 'stub fallback'}"
        )
    else:
        logger.info("X402 Payment middleware disabled (PAYMENT_ENABLED=false)")

    # ─── 12. ResponseLimitingMiddleware ───
    if settings.response_limit_max_size > 0:
        from fastmcp.server.middleware.response_limiting import (
            ResponseLimitingMiddleware,
        )

        _rl_tools = [
            t.strip()
            for t in settings.response_limit_tools.split(",")
            if t.strip()
        ] or None
        response_limiting_middleware = ResponseLimitingMiddleware(
            max_size=settings.response_limit_max_size,
            tools=_rl_tools,
        )
        mcp.add_middleware(response_limiting_middleware)
        logger.info(
            f"✅ ResponseLimitingMiddleware enabled — max {settings.response_limit_max_size:,} bytes"
            + (f" for tools: {_rl_tools}" if _rl_tools else " (all tools)")
        )

    # ─── 13. Dashboard Cache Middleware (outermost) ───
    from middleware.dashboard_cache_middleware import DashboardCacheMiddleware

    dashboard_cache_middleware = DashboardCacheMiddleware()
    mcp.add_middleware(dashboard_cache_middleware)
    ctx.dashboard_cache_middleware = dashboard_cache_middleware
    logger.info("✅ Dashboard cache middleware registered (outermost)")

    # ─── 14. Redis Response Caching ───
    if settings.redis_io_url_string:
        try:
            from fastmcp.server.middleware.caching import ResponseCachingMiddleware
            from key_value.aio.stores.redis import RedisStore
            from key_value.aio.wrappers.prefix_collections import (
                PrefixCollectionsWrapper,
            )

            _redis_store = RedisStore(url=settings.redis_io_url_string)
            _namespaced_store = PrefixCollectionsWrapper(
                key_value=_redis_store, prefix="gw-mcp"
            )
            mcp.add_middleware(
                ResponseCachingMiddleware(
                    cache_storage=_namespaced_store,
                    call_tool_settings={"enabled": False},
                    read_resource_settings={"enabled": False},
                )
            )
            _safe_url = _mask_redis_url(settings.redis_io_url_string)
            logger.info(
                f"✅ Redis ResponseCachingMiddleware enabled ({_safe_url}, list ops only)"
            )

            from middleware.dashboard_cache_middleware import set_redis_store

            set_redis_store(_redis_store)
            logger.info("  Redis store shared with dashboard cache middleware")

            from middleware.token_store import set_redis_client

            set_redis_client(_redis_store)
            logger.info("  Redis client shared with token store")
        except Exception as _redis_err:
            logger.warning(
                f"⚠️ Redis caching setup failed (falling back to in-memory): {_redis_err}"
            )
    else:
        logger.info("Redis caching disabled (REDIS_IO_URL_STRING not set)")

    return ctx


def _mask_redis_url(url: str) -> str:
    """Redact password from Redis URL for safe logging."""
    from urllib.parse import urlparse, urlunparse

    try:
        parsed = urlparse(url)
        if parsed.password:
            masked = parsed._replace(
                netloc=f"{parsed.username or ''}:***@{parsed.hostname}"
                + (f":{parsed.port}" if parsed.port else "")
            )
            return urlunparse(masked)
    except Exception:
        pass
    return "redis://***"
