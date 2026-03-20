"""Application configuration using Pydantic Settings."""

import logging
import os
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing_extensions import List, Optional

from config.enhanced_logging import setup_logger

logger = setup_logger()
from urllib.parse import urlparse

# Lazy import for compatibility shim to avoid circular imports
_COMPATIBILITY_AVAILABLE = None  # Will be checked lazily


class Settings(BaseSettings):
    """Application configuration using Pydantic Settings"""

    # OAuth Configuration (either use JSON file OR individual credentials)
    google_client_secrets_file: str = ""  # Path to client_secret.json file
    google_client_id: str = ""
    google_client_secret: str = ""
    oauth_redirect_uri: str = "http://localhost:8002/oauth2callback"

    # Server Configuration
    server_port: int = 8002
    server_host: str = "localhost"
    server_name: str = "Google Drive Upload Server"

    # HTTPS/SSL Configuration
    # Default to False for Docker compatibility - explicitly enable via .env when needed
    enable_https: bool = False
    ssl_cert_file: str = ""  # Path to SSL certificate (e.g., "./localhost+2.pem")
    ssl_key_file: str = ""  # Path to SSL private key (e.g., "./localhost+2-key.pem")
    ssl_ca_file: str = ""  # Optional CA file for client certificate verification

    # Storage Configuration
    credentials_dir: str = str(Path(__file__).parent.parent / "credentials")
    credential_storage_mode: str = "FILE_ENCRYPTED"
    chat_service_account_file: str = ""

    @property
    def is_cloud_deployment(self) -> bool:
        """Detect if running in FastMCP Cloud."""
        return os.getenv("FASTMCP_CLOUD", "false").lower() in ("true", "1", "yes", "on")

    # Qdrant Configuration
    qdrant_url: str = "http://localhost:6333"
    qdrant_key: str = "NONE"
    qdrant_host: Optional[str] = None  # Will be set from qdrant_url
    qdrant_port: Optional[int] = None  # Will be set from qdrant_url
    qdrant_api_key: Optional[str] = None  # Will be set from qdrant_key
    qdrant_prefer_grpc: bool = (
        True  # Use gRPC to avoid SSL certificate issues with cloud Qdrant
    )

    # Primary Qdrant collection for MCP tool responses / analytics
    tool_collection: str = Field(
        default="mcp_tool_responses",
        description="Primary Qdrant collection for MCP tool responses and analytics",
        json_schema_extra={"env": "TOOL_COLLECTION"},
    )

    # Qdrant Docker Auto-Launch Configuration
    # When enabled, automatically launches Qdrant via Docker if not reachable
    qdrant_auto_launch: bool = Field(
        default=True,
        description="Automatically launch Qdrant via Docker if not reachable (local URLs only)",
        json_schema_extra={"env": "QDRANT_AUTO_LAUNCH"},
    )
    qdrant_docker_image: str = Field(
        default="qdrant/qdrant:latest",
        description="Docker image for Qdrant container",
        json_schema_extra={"env": "QDRANT_DOCKER_IMAGE"},
    )
    qdrant_docker_container_name: str = Field(
        default="mcp-qdrant",
        description="Name for the Qdrant Docker container",
        json_schema_extra={"env": "QDRANT_DOCKER_CONTAINER_NAME"},
    )
    qdrant_docker_grpc_port: int = Field(
        default=6334,
        description="gRPC port to expose for Qdrant container",
        json_schema_extra={"env": "QDRANT_DOCKER_GRPC_PORT"},
    )
    qdrant_docker_data_dir: str = Field(
        default="",
        description="Persistent data directory for Qdrant. If empty, uses credentials_dir/qdrant_data",
        json_schema_extra={"env": "QDRANT_DOCKER_DATA_DIR"},
    )
    qdrant_docker_startup_timeout: int = Field(
        default=30,
        description="Seconds to wait for Qdrant container to become ready",
        json_schema_extra={"env": "QDRANT_DOCKER_STARTUP_TIMEOUT"},
    )
    qdrant_docker_stop_on_exit: bool = Field(
        default=False,
        description="Stop Qdrant container when MCP server exits (only if we started it)",
        json_schema_extra={"env": "QDRANT_DOCKER_STOP_ON_EXIT"},
    )

    # Logging
    log_level: str = "INFO"

    # Security
    session_timeout_minutes: int = 60

    # Gmail Allow List Configuration
    gmail_allow_list: str = ""  # Comma-separated list of email addresses

    # Gmail Elicitation Configuration (for MCP client compatibility)
    gmail_enable_elicitation: bool = True  # Enable elicitation for untrusted recipients
    gmail_elicitation_fallback: str = (
        "block"  # What to do if elicitation fails: "block", "allow", "draft"
    )

    # Qdrant Tool Response Collection Cache Configuration
    mcp_tool_responses_collection_cache_days: int = 5  # Default to 14 days retention

    # Sampling Tools Configuration
    sampling_tools: bool = False  # Enable sampling middleware tools (default: False)
    sampling_validation_enabled: bool = Field(
        default=True,
        description="Enable per-tool validation agents for semantic input validation via sampling",
        json_schema_extra={"env": "SAMPLING_VALIDATION_ENABLED"},
    )
    anthropic_api_key: Optional[str] = None  # For sampling fallback handler

    # LiteLLM Sampling Configuration
    litellm_model: str = Field(
        default="openai/zai-org-glm-4.6",
        description="LiteLLM model identifier (provider/model format, e.g. 'openai/zai-org-glm-4.6' for Venice AI, 'anthropic/claude-sonnet-4-6')",
        json_schema_extra={"env": "LITELLM_MODEL"},
    )
    litellm_api_key: Optional[str] = Field(
        default=None,
        description="API key for the LiteLLM provider. Falls back to VENICE_INFERENCE_KEY or provider-specific env vars.",
        json_schema_extra={"env": "LITELLM_API_KEY"},
    )
    litellm_api_base: Optional[str] = Field(
        default=None,
        description="Custom API base URL for OpenAI-compatible providers (e.g. 'https://api.venice.ai/api/v1')",
        json_schema_extra={"env": "LITELLM_API_BASE"},
    )
    venice_inference_key: Optional[str] = Field(
        default=None,
        description="Venice AI API key (used as LiteLLM api_key when model targets Venice)",
        json_schema_extra={"env": "VENICE_INFERENCE_KEY"},
    )
    sampling_provider: str = Field(
        default="auto",
        description="Sampling provider: 'auto' (LiteLLM if configured, else Anthropic), 'litellm', or 'anthropic'",
        json_schema_extra={"env": "SAMPLING_PROVIDER"},
    )

    # MCP List Page Size Configuration
    # Controls pagination of tools/resources/prompts listing responses.
    # Set to 0 or None to disable pagination (return all items in one response).
    # IMPORTANT: If this value is smaller than the number of enabled tools for a
    # session, clients that don't handle MCP pagination will miss tools on later pages.
    list_page_size: int = Field(
        default=0,
        description="Page size for MCP list operations (tools, resources, prompts). 0 = no pagination.",
        json_schema_extra={"env": "LIST_PAGE_SIZE"},
    )

    # Minimal Tools Startup Configuration
    # When enabled, server starts with only essential tools (protected infra tools)
    # Clients can enable tools as needed, and their state persists across reconnects
    minimal_tools_startup: bool = Field(
        default=False,
        description="Start server with minimal tools enabled. New sessions get bare minimum, reconnecting sessions restore their previous tool state.",
        json_schema_extra={"env": "MINIMAL_TOOLS_STARTUP"},
    )

    # Session tool state persistence file location
    session_tool_state_file: str = Field(
        default="",
        description="Path to JSON file for persisting session tool states across server restarts. If empty, uses credentials_dir/session_tool_states.json",
        json_schema_extra={"env": "SESSION_TOOL_STATE_FILE"},
    )

    # Default enabled services for minimal startup mode
    # Comma-separated list of service names from ScopeRegistry (e.g., "drive,gmail,calendar")
    # When minimal_tools_startup is enabled, tools for these services will be enabled by default
    # If empty, only protected infrastructure tools are enabled
    minimal_startup_services: str = Field(
        default="",
        description="Comma-separated list of services to enable by default in minimal startup mode (e.g., 'drive,gmail'). Empty = only protected tools.",
        json_schema_extra={"env": "MINIMAL_STARTUP_SERVICES"},
    )

    # Centralized Embedding Service Configuration
    embedding_minilm_model: str = Field(
        default="sentence-transformers/all-MiniLM-L6-v2",
        description="MiniLM model for dense 384-dim embeddings",
        json_schema_extra={"env": "EMBEDDING_MINILM_MODEL"},
    )
    embedding_colbert_model: str = Field(
        default="colbert-ir/colbertv2.0",
        description="ColBERT model for multi-vector 128-dim embeddings",
        json_schema_extra={"env": "EMBEDDING_COLBERT_MODEL"},
    )
    embedding_bge_model: str = Field(
        default="BAAI/bge-small-en-v1.5",
        description="BGE-small model for icon search embeddings",
        json_schema_extra={"env": "EMBEDDING_BGE_MODEL"},
    )
    embedding_eager_load: str = Field(
        default="",
        description="Comma-separated embedding slots to preload on startup (e.g. 'minilm,colbert')",
        json_schema_extra={"env": "EMBEDDING_EAGER_LOAD"},
    )

    # ColBERT Embedding Configuration (Development/Testing)
    colbert_embedding_dev: bool = Field(
        default=False,
        description="Enable ColBERT multi-vector embeddings initialization on startup for development/testing",
        json_schema_extra={"env": "COLBERT_EMBEDDING_DEV"},
    )

    # Skills Provider Configuration
    # When enabled, generates skill documents from ModuleWrapper and serves via FastMCP
    enable_skills_provider: bool = Field(
        default=False,
        description="Enable FastMCP SkillsDirectoryProvider for dynamic skill generation",
        json_schema_extra={"env": "ENABLE_SKILLS_PROVIDER"},
    )
    skills_directory: str = Field(
        default="",
        description="Directory for skill documents. If empty, uses ~/.claude/skills",
        json_schema_extra={"env": "SKILLS_DIRECTORY"},
    )
    skills_auto_regenerate: bool = Field(
        default=True,
        description="Regenerate skill documents on startup",
        json_schema_extra={"env": "SKILLS_AUTO_REGENERATE"},
    )

    # Google Chat Card Collection Configuration
    # Collection uses three named vectors:
    #   - components: Identity (Name + Type + Path + Docstring)
    #   - inputs: Values (defaults, enums, instance_params)
    #   - relationships: Graph (parent-child connections)
    card_collection: str = Field(
        default="mcp_gchat_cards",
        description="Qdrant collection for Google Chat card components, templates, and feedback patterns",
        json_schema_extra={"env": "CARD_COLLECTION"},
    )

    # Component Relationship Collection Configuration
    relationship_collection: str = Field(
        default="mcp_component_relationships",
        description="Qdrant collection for card component relationships (parent→child paths)",
        json_schema_extra={"env": "RELATIONSHIP_COLLECTION"},
    )

    # Google Chat Default Webhook URL
    # When set, this becomes the default webhook for all card tools (send_dynamic_card, etc.)
    # Useful for development/testing when you always want to send to the same space
    mcp_chat_webhook: str = Field(
        default="",
        description="Default Google Chat webhook URL for card tools. When set, card tools use this as the default webhook_url parameter.",
        json_schema_extra={"env": "MCP_CHAT_WEBHOOK"},
    )

    # Phase 1 OAuth Migration Feature Flags
    enable_unified_auth: bool = True
    legacy_compat_mode: bool = True
    credential_migration: bool = True
    service_caching: bool = True
    enhanced_logging: bool = True

    # Security Configuration
    auth_security_level: str = Field(
        default="standard",
        description="Authentication security level: 'standard', 'high', or 'custom'",
        json_schema_extra={"env": "AUTH_SECURITY_LEVEL"},
    )

    # Calendar Configuration
    default_timezone: str = Field(
        default="UTC",
        description="Default IANA timezone for calendar events when no timezone is specified (e.g., 'America/Chicago')",
        json_schema_extra={"env": "DEFAULT_TIMEZONE"},
    )

    # Template Configuration
    jinja_template_strict_mode: bool = Field(
        default=True,
        description="When enabled, template processing errors will cause tool execution to fail instead of just logging the error",
        json_schema_extra={"env": "JINJA_TEMPLATE_STRICT_MODE"},
    )

    # Code Mode Configuration
    # When enabled, replaces the full tool catalog with BM25 search + sandboxed execution
    # LLMs discover tools via search instead of loading all schemas upfront
    enable_code_mode: bool = Field(
        default=False,
        description="Enable CodeMode transform for BM25 tool discovery",
        json_schema_extra={"env": "ENABLE_CODE_MODE"},
    )

    # Response Limiting Configuration
    response_limit_max_size: int = Field(
        default=500_000,
        description="Maximum tool response size in bytes before truncation (0 = disabled). Default 500KB.",
        json_schema_extra={"env": "RESPONSE_LIMIT_MAX_SIZE"},
    )
    response_limit_tools: str = Field(
        default="",
        description="Comma-separated tool names to limit. Empty = all tools.",
        json_schema_extra={"env": "RESPONSE_LIMIT_TOOLS"},
    )

    # Privacy Mode Configuration
    privacy_mode: str = Field(
        default="disabled",
        description="Privacy mode: 'disabled', 'auto' (field heuristics + value patterns), or 'strict' (encrypt all strings)",
        json_schema_extra={"env": "PRIVACY_MODE"},
    )
    privacy_field_patterns: str = Field(
        default="",
        description="Comma-separated additional field names to treat as PII",
        json_schema_extra={"env": "PRIVACY_FIELD_PATTERNS"},
    )
    privacy_exclude_tools: str = Field(
        default="manage_tools,check_drive_auth,get_server_info,set_privacy_mode",
        description="Comma-separated tool names to exclude from privacy processing",
        json_schema_extra={"env": "PRIVACY_EXCLUDE_TOOLS"},
    )

    # X402 Payment Protocol Configuration
    payment_enabled: bool = Field(
        default=False,
        description="Enable x402 payment protocol for tool access gating",
        json_schema_extra={"env": "PAYMENT_ENABLED"},
    )
    payment_recipient_wallet: str = Field(
        default="",
        description="Wallet address to receive USDC payments",
        json_schema_extra={"env": "PAYMENT_RECIPIENT_WALLET"},
    )
    payment_usdc_amount: str = Field(
        default="0.01",
        description="Required USDC payment amount",
        json_schema_extra={"env": "PAYMENT_USDC_AMOUNT"},
    )
    payment_chain_id: int = Field(
        default=84532,
        description="Blockchain chain ID (derived from payment_network for backward compat)",
        json_schema_extra={"env": "PAYMENT_CHAIN_ID"},
    )
    payment_network: str = Field(
        default="eip155:84532",
        description="CAIP-2 network identifier (Base Sepolia default = testnet-safe)",
        json_schema_extra={"env": "PAYMENT_NETWORK"},
    )
    payment_facilitator_url: str = Field(
        default="https://x402.org/facilitator",
        description="x402 facilitator service URL for payment verification/settlement",
        json_schema_extra={"env": "PAYMENT_FACILITATOR_URL"},
    )
    payment_scheme: str = Field(
        default="exact",
        description="x402 payment scheme (exact = EIP-3009 signature-based)",
        json_schema_extra={"env": "PAYMENT_SCHEME"},
    )
    payment_rpc_url: str = Field(
        default="",
        description="RPC URL for on-chain verification (legacy, kept for backward compat)",
        json_schema_extra={"env": "PAYMENT_RPC_URL"},
    )
    payment_verification_url: str = Field(
        default="",
        description="External verification service URL (legacy, kept for backward compat)",
        json_schema_extra={"env": "PAYMENT_VERIFICATION_URL"},
    )
    payment_session_ttl_minutes: int = Field(
        default=60,
        description="Minutes a payment verification remains valid",
        json_schema_extra={"env": "PAYMENT_SESSION_TTL_MINUTES"},
    )
    payment_gated_tools: str = Field(
        default="",
        description="Comma-separated tool names to gate. Empty = all tools.",
        json_schema_extra={"env": "PAYMENT_GATED_TOOLS"},
    )
    payment_free_for_oauth: bool = Field(
        default=True,
        description="OAuth and per-user API key sessions bypass payment",
        json_schema_extra={"env": "PAYMENT_FREE_FOR_OAUTH"},
    )
    receipt_collection: str = Field(
        default="mcp_payment_receipts",
        description="Qdrant collection for payment receipt storage",
        json_schema_extra={"env": "RECEIPT_COLLECTION"},
    )

    # Payment Flow UX Configuration
    payment_auto_open_browser: bool = Field(
        default=True,
        description="Automatically open browser payment page on 402 Payment Required",
        json_schema_extra={"env": "PAYMENT_AUTO_OPEN_BROWSER"},
    )
    payment_send_email: bool = Field(
        default=False,
        description="Send payment request email on 402 Payment Required",
        json_schema_extra={"env": "PAYMENT_SEND_EMAIL"},
    )
    payment_poll_timeout_seconds: int = Field(
        default=300,
        description="Max seconds to wait for browser/email payment completion",
        json_schema_extra={"env": "PAYMENT_POLL_TIMEOUT_SECONDS"},
    )
    payment_poll_interval_seconds: int = Field(
        default=2,
        description="Seconds between payment completion polls",
        json_schema_extra={"env": "PAYMENT_POLL_INTERVAL_SECONDS"},
    )
    payment_token_ttl_seconds: int = Field(
        default=900,
        description="TTL for HMAC-signed payment tokens (default: 15 minutes)",
        json_schema_extra={"env": "PAYMENT_TOKEN_TTL_SECONDS"},
    )

    # Cost Tracking Rates (USD)
    sampling_input_token_rate: float = Field(
        default=0.000003,
        description="Cost per input token in USD (default: Claude Sonnet rate)",
        json_schema_extra={"env": "SAMPLING_INPUT_TOKEN_RATE"},
    )
    sampling_output_token_rate: float = Field(
        default=0.000015,
        description="Cost per output token in USD (default: Claude Sonnet rate)",
        json_schema_extra={"env": "SAMPLING_OUTPUT_TOKEN_RATE"},
    )
    sampling_default_model: str = Field(
        default="claude-sonnet-4-6",
        description="Default model identifier for cost tracking",
        json_schema_extra={"env": "SAMPLING_DEFAULT_MODEL"},
    )
    qdrant_cost_per_upsert: float = Field(
        default=0.0001,
        description="Estimated USD cost per Qdrant upsert operation",
        json_schema_extra={"env": "QDRANT_COST_PER_UPSERT"},
    )
    qdrant_cost_per_search: float = Field(
        default=0.00005,
        description="Estimated USD cost per Qdrant search operation",
        json_schema_extra={"env": "QDRANT_COST_PER_SEARCH"},
    )

    # Redis Cloud Configuration
    redis_io_url_string: Optional[str] = Field(
        default=None,
        description="Redis Cloud connection URL (redis://user:pass@host:port). Used for response caching and dashboard cache offloading.",
        json_schema_extra={"env": "REDIS_IO_URL_STRING"},
    )

    # Sampling Cache Configuration
    sampling_cache_enabled: bool = Field(
        default=False,
        description="Enable Qdrant semantic response cache for sampling calls",
        json_schema_extra={"env": "SAMPLING_CACHE_ENABLED"},
    )
    sampling_cache_collection: str = Field(
        default="mcp_sampling_cache",
        description="Qdrant collection for semantic sampling cache",
        json_schema_extra={"env": "SAMPLING_CACHE_COLLECTION"},
    )
    sampling_cache_similarity_threshold: float = Field(
        default=0.85,
        description="Similarity threshold for cache hits (0.0-1.0). Higher = stricter matching.",
        json_schema_extra={"env": "SAMPLING_CACHE_SIMILARITY_THRESHOLD"},
    )
    sampling_cache_fastembed_model: str = Field(
        default="sentence-transformers/all-MiniLM-L6-v2",
        description="FastEmbed model for semantic cache embeddings",
        json_schema_extra={"env": "SAMPLING_CACHE_FASTEMBED_MODEL"},
    )

    # Prompt Cache Keepalive Configuration
    cache_keepalive_enabled: bool = Field(
        default=False,
        description="Enable periodic keepalive to keep Anthropic prompt cache warm",
        json_schema_extra={"env": "CACHE_KEEPALIVE_ENABLED"},
    )
    cache_keepalive_interval_seconds: int = Field(
        default=240,
        description="Seconds between keepalive calls per module (4 min default for 5-min TTL)",
        json_schema_extra={"env": "CACHE_KEEPALIVE_INTERVAL_SECONDS"},
    )
    cache_keepalive_modules: str = Field(
        default="gchat,email,qdrant",
        description="Comma-separated module names to keep warm",
        json_schema_extra={"env": "CACHE_KEEPALIVE_MODULES"},
    )
    cache_keepalive_mode: str = Field(
        default="explore",
        description="'ping' (minimal output) or 'explore' (generate DSL variations)",
        json_schema_extra={"env": "CACHE_KEEPALIVE_MODE"},
    )
    cache_keepalive_max_tokens: int = Field(
        default=100,
        description="Max output tokens for keepalive calls",
        json_schema_extra={"env": "CACHE_KEEPALIVE_MAX_TOKENS"},
    )
    cache_keepalive_index_results: bool = Field(
        default=True,
        description="Index exploration results into Qdrant",
        json_schema_extra={"env": "CACHE_KEEPALIVE_INDEX_RESULTS"},
    )

    # Langfuse Observability Configuration
    langfuse_public_key: str = Field(
        default="",
        description="Langfuse public key for LLM observability",
        json_schema_extra={"env": "LANGFUSE_PUBLIC_KEY"},
    )
    langfuse_secret_key: str = Field(
        default="",
        description="Langfuse secret key for LLM observability",
        json_schema_extra={"env": "LANGFUSE_SECRET_KEY"},
    )
    langfuse_host: str = Field(
        default="https://us.cloud.langfuse.com",
        description="Langfuse host URL",
        json_schema_extra={"env": "LANGFUSE_HOST"},
    )

    @property
    def langfuse_enabled(self) -> bool:
        """Check if Langfuse credentials are configured."""
        return bool(self.langfuse_public_key and self.langfuse_secret_key)

    # FastMCP 2.12.0 GoogleProvider Configuration
    fastmcp_server_auth: str = ""
    fastmcp_server_auth_google_client_id: str = ""
    fastmcp_server_auth_google_client_secret: str = ""
    fastmcp_server_auth_google_base_url: str = ""

    # Legacy OAuth scopes - maintained for backward compatibility
    # These are now managed through the centralized scope registry
    _fallback_drive_scopes: list[str] = [
        # Base OAuth scopes for user identification
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/userinfo.profile",
        "openid",
        # Google Drive scopes
        "https://www.googleapis.com/auth/drive",
        "https://www.googleapis.com/auth/drive.readonly",
        "https://www.googleapis.com/auth/drive.file",
        # Google Docs scopes
        "https://www.googleapis.com/auth/documents.readonly",
        "https://www.googleapis.com/auth/documents",
        # Gmail API scopes
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/gmail.send",
        "https://www.googleapis.com/auth/gmail.compose",
        "https://www.googleapis.com/auth/gmail.modify",
        "https://www.googleapis.com/auth/gmail.labels",
        # Gmail Settings scopes (CRITICAL for filters/forwarding)
        "https://www.googleapis.com/auth/gmail.settings.basic",
        "https://www.googleapis.com/auth/gmail.settings.sharing",
        # Google Chat API scopes
        "https://www.googleapis.com/auth/chat.messages.readonly",
        "https://www.googleapis.com/auth/chat.messages",
        "https://www.googleapis.com/auth/chat.spaces",
        # Google Sheets API scopes
        "https://www.googleapis.com/auth/spreadsheets.readonly",
        "https://www.googleapis.com/auth/spreadsheets",
        # Google Forms API scopes
        "https://www.googleapis.com/auth/forms.body",
        "https://www.googleapis.com/auth/forms.body.readonly",
        "https://www.googleapis.com/auth/forms.responses.readonly",
        # Google Slides API scopes
        "https://www.googleapis.com/auth/presentations",
        "https://www.googleapis.com/auth/presentations.readonly",
        # Calendar scopes
        "https://www.googleapis.com/auth/calendar.readonly",
        "https://www.googleapis.com/auth/calendar.events",
        "https://www.googleapis.com/auth/calendar",
        # Google Photos Library API scopes
        "https://www.googleapis.com/auth/photoslibrary.readonly",
        "https://www.googleapis.com/auth/photoslibrary.appendonly",
        "https://www.googleapis.com/auth/photoslibrary",
        "https://www.googleapis.com/auth/photoslibrary.sharing",
        "https://www.googleapis.com/auth/photoslibrary.readonly.appcreateddata",
        "https://www.googleapis.com/auth/photoslibrary.edit.appcreateddata",
        # Cloud Platform scopes (for broader Google services)
        "https://www.googleapis.com/auth/cloud-platform",
        "https://www.googleapis.com/auth/cloudfunctions",
        "https://www.googleapis.com/auth/pubsub",
        "https://www.googleapis.com/auth/iam",
    ]

    @property
    def drive_scopes(self) -> list[str]:
        """
        Get OAuth scopes for Google services.

        This property uses the centralized scope registry as the single source of truth,
        ensuring consistency across the application and avoiding problematic scopes.

        Returns:
            List of OAuth scope URLs from oauth_comprehensive group
        """
        try:
            # Use the scope registry directly as single source of truth
            from auth.scope_registry import ScopeRegistry

            scopes = ScopeRegistry.resolve_scope_group("oauth_comprehensive")
            logging.debug(
                f"SCOPE_DEBUG: Retrieved {len(scopes)} scopes from oauth_comprehensive group"
            )

            # Verify no problematic scopes are included
            problematic_patterns = [
                "photoslibrary.sharing",
                "cloud-platform",
                "cloudfunctions",
                "pubsub",
                "iam",
            ]
            problematic_scopes = [
                scope
                for scope in scopes
                if any(bad in scope for bad in problematic_patterns)
            ]

            if problematic_scopes:
                logging.error(
                    f"SCOPE_DEBUG: Found {len(problematic_scopes)} problematic scopes in oauth_comprehensive"
                )
                for scope in problematic_scopes:
                    logging.error(f"SCOPE_DEBUG: Problematic scope: {scope}")
            else:
                logging.debug(
                    "SCOPE_DEBUG: No problematic scopes found - using clean oauth_comprehensive group"
                )

            # Check if Gmail settings scopes are included
            gmail_settings_basic = (
                "https://www.googleapis.com/auth/gmail.settings.basic"
            )
            gmail_settings_sharing = (
                "https://www.googleapis.com/auth/gmail.settings.sharing"
            )
            has_settings_basic = gmail_settings_basic in scopes
            has_settings_sharing = gmail_settings_sharing in scopes
            logging.debug(
                f"SCOPE_DEBUG: Gmail settings.basic included: {has_settings_basic}"
            )
            logging.debug(
                f"SCOPE_DEBUG: Gmail settings.sharing included: {has_settings_sharing}"
            )

            return scopes

        except Exception as e:
            logging.error(
                f"SCOPE_DEBUG: Error getting scopes from registry, using minimal fallback: {e}"
            )
            # Use a minimal fallback that excludes problematic scopes
            minimal_scopes = [
                "https://www.googleapis.com/auth/userinfo.email",
                "https://www.googleapis.com/auth/userinfo.profile",
                "openid",
                "https://www.googleapis.com/auth/drive",
                "https://www.googleapis.com/auth/gmail.readonly",
                "https://www.googleapis.com/auth/gmail.send",
                "https://www.googleapis.com/auth/calendar",
                "https://www.googleapis.com/auth/documents",
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/presentations",
            ]
            logging.warning(
                f"SCOPE_DEBUG: Using minimal fallback with {len(minimal_scopes)} scopes"
            )
            return minimal_scopes
            return self._fallback_drive_scopes

    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).parent.parent / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # Ignore extra fields like TEST_EMAIL_ADDRESS
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # DEBUG: Log environment variable loading
        import os

        env_qdrant_url = os.getenv("QDRANT_URL")
        env_qdrant_key = os.getenv("QDRANT_KEY")
        logging.debug(
            f"🔧 SETTINGS DEBUG - Environment variables: QDRANT_URL='{env_qdrant_url}', QDRANT_KEY={'***' if env_qdrant_key else 'None'}"
        )
        logging.debug(
            f"🔧 SETTINGS DEBUG - Settings fields: qdrant_url='{self.qdrant_url}', qdrant_key={'***' if self.qdrant_key and self.qdrant_key != 'NONE' else 'None'}"
        )

        # DEBUG: Log FastMCP GoogleProvider environment variable loading
        env_fastmcp_auth = os.getenv("FASTMCP_SERVER_AUTH")
        env_fastmcp_client_id = os.getenv("FASTMCP_SERVER_AUTH_GOOGLE_CLIENT_ID")
        env_fastmcp_client_secret = os.getenv(
            "FASTMCP_SERVER_AUTH_GOOGLE_CLIENT_SECRET"
        )
        env_fastmcp_base_url = os.getenv("FASTMCP_SERVER_AUTH_GOOGLE_BASE_URL")
        logging.debug("🔧 FASTMCP DEBUG - Environment variables:")
        logging.debug(f"🔧   FASTMCP_SERVER_AUTH='{env_fastmcp_auth}'")
        logging.debug(
            f"🔧   FASTMCP_SERVER_AUTH_GOOGLE_CLIENT_ID={'***' if env_fastmcp_client_id else 'None'}"
        )
        logging.debug(
            f"🔧   FASTMCP_SERVER_AUTH_GOOGLE_CLIENT_SECRET={'***' if env_fastmcp_client_secret else 'None'}"
        )
        logging.debug(
            f"🔧   FASTMCP_SERVER_AUTH_GOOGLE_BASE_URL='{env_fastmcp_base_url}'"
        )
        logging.debug("🔧 FASTMCP DEBUG - Settings fields:")
        logging.debug(f"🔧   fastmcp_server_auth='{self.fastmcp_server_auth}'")
        logging.debug(
            f"🔧   fastmcp_server_auth_google_client_id={'***' if self.fastmcp_server_auth_google_client_id else 'None'}"
        )
        logging.debug(
            f"🔧   fastmcp_server_auth_google_client_secret={'***' if self.fastmcp_server_auth_google_client_secret else 'None'}"
        )
        logging.debug(
            f"🔧   fastmcp_server_auth_google_base_url='{self.fastmcp_server_auth_google_base_url}'"
        )

        # Cloud-aware configuration
        if self.is_cloud_deployment:
            # Use cloud-optimized settings
            self.credentials_dir = os.getenv("CREDENTIALS_DIR", "/tmp/credentials")
            if (
                not self.credential_storage_mode
                or self.credential_storage_mode == "FILE_ENCRYPTED"
            ):
                self.credential_storage_mode = os.getenv(
                    "CREDENTIAL_STORAGE_MODE", "MEMORY_WITH_BACKUP"
                )
            logging.debug(
                f"☁️ Cloud deployment detected - using credentials_dir='{self.credentials_dir}', storage_mode='{self.credential_storage_mode}'"
            )
        else:
            # Use environment variable override if provided, otherwise keep current value
            self.credentials_dir = os.getenv("CREDENTIALS_DIR", self.credentials_dir)
            self.credential_storage_mode = os.getenv(
                "CREDENTIAL_STORAGE_MODE", self.credential_storage_mode
            )

        # Ensure credentials directory exists
        Path(self.credentials_dir).mkdir(parents=True, exist_ok=True)

        # Parse Qdrant URL to get host and port
        parsed_url = urlparse(self.qdrant_url)
        self.qdrant_host = parsed_url.hostname or "localhost"
        self.qdrant_port = parsed_url.port or 6333
        # If QDRANT_KEY is "NONE" or empty, treat as no authentication
        self.qdrant_api_key = (
            None if self.qdrant_key in ["NONE", "", None] else self.qdrant_key
        )

        # DEBUG: Log final parsed values
        logging.debug(
            f"🔧 SETTINGS DEBUG - Parsed values: host='{self.qdrant_host}', port={self.qdrant_port}, api_key={'***' if self.qdrant_api_key else 'None'}"
        )

    @property
    def session_tool_state_path(self) -> Path:
        """Get the path for session tool state persistence file."""
        if self.session_tool_state_file:
            return Path(self.session_tool_state_file)
        return Path(self.credentials_dir) / "session_tool_states.json"

    @property
    def skills_directory_path(self) -> Path:
        """Get the path for skill documents directory."""
        if self.skills_directory:
            return Path(self.skills_directory).expanduser().resolve()
        return Path.home() / ".claude" / "skills"

    def get_minimal_startup_services(self) -> List[str]:
        """
        Parse and return the list of services enabled by default in minimal startup mode.

        Returns:
            List[str]: List of service names (e.g., ['drive', 'gmail']).
                       Returns empty list if not configured.
        """
        if (
            not self.minimal_startup_services
            or self.minimal_startup_services.strip() == ""
        ):
            return []

        # Parse comma-separated list, strip whitespace, filter empty strings
        services = [
            service.strip().lower()
            for service in self.minimal_startup_services.split(",")
            if service.strip()
        ]

        # Validate against ScopeRegistry services
        try:
            from auth.scope_registry import ScopeRegistry

            valid_services = ScopeRegistry.get_all_services()
            validated = [s for s in services if s in valid_services]

            invalid = [s for s in services if s not in valid_services]
            if invalid:
                logging.warning(
                    f"Invalid services in MINIMAL_STARTUP_SERVICES: {invalid}. "
                    f"Valid services: {valid_services}"
                )

            return validated
        except ImportError:
            # ScopeRegistry not available - return as-is
            return services

    def get_gmail_allow_list(self) -> List[str]:
        """
        Parse and return the Gmail allow list from the configuration.

        Returns:
            List[str]: List of email addresses in the allow list.
                       Returns empty list if not configured or empty.
        """
        if not self.gmail_allow_list or self.gmail_allow_list.strip() == "":
            return []

        # Parse comma-separated list, strip whitespace, filter empty strings
        emails = [
            email.strip().lower()
            for email in self.gmail_allow_list.split(",")
            if email.strip()
        ]

        # Log the parsed allow list for debugging (without exposing full emails)
        if emails:
            masked_emails = [
                f"{email[:3]}...{email[-10:]}" if len(email) > 13 else email
                for email in emails
            ]
            logging.debug(
                f"Gmail allow list contains {len(emails)} email(s): {masked_emails}"
            )

        return emails

    def is_oauth_configured(self) -> bool:
        """Check if OAuth credentials are properly configured."""
        # Check if JSON file is provided and exists
        if self.google_client_secrets_file:
            return Path(self.google_client_secrets_file).exists()

        # Fallback to individual credentials
        return bool(self.google_client_id and self.google_client_secret)

    def validate_oauth_config(self) -> None:
        """Validate that OAuth configuration is complete."""
        if not self.is_oauth_configured():
            if self.google_client_secrets_file:
                raise ValueError(
                    f"OAuth client secrets file not found: {self.google_client_secrets_file}. "
                    "Please check the path to your Google OAuth JSON file."
                )
            else:
                raise ValueError(
                    "OAuth configuration is incomplete. Please either:\n"
                    "1. Set GOOGLE_CLIENT_SECRETS_FILE environment variable to point to your OAuth JSON file, OR\n"
                    "2. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET environment variables"
                )

    def get_oauth_client_config(self) -> dict:
        """Get OAuth client configuration from JSON file or environment variables."""
        if self.google_client_secrets_file:
            secrets_path = Path(self.google_client_secrets_file)
            if not secrets_path.exists():
                # Log the full path for debugging
                logging.error(
                    f"OAuth client secrets file not found at: {secrets_path.absolute()}"
                )
                raise FileNotFoundError(
                    f"OAuth client secrets file not found: {self.google_client_secrets_file}"
                )

            import json

            try:
                with open(secrets_path, "r") as f:
                    config = json.load(f)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON in OAuth client secrets file: {e}")
            except Exception as e:
                raise ValueError(f"Error reading OAuth client secrets file: {e}")

            # Extract from Google OAuth JSON format
            if "web" in config:
                web_config = config["web"]
                return {
                    "client_id": web_config.get("client_id"),
                    "client_secret": web_config.get("client_secret"),
                    "auth_uri": web_config.get(
                        "auth_uri", "https://accounts.google.com/o/oauth2/auth"
                    ),
                    "token_uri": web_config.get(
                        "token_uri", "https://oauth2.googleapis.com/token"
                    ),
                    "redirect_uris": web_config.get(
                        "redirect_uris", [self.dynamic_oauth_redirect_uri]
                    ),
                }
            elif "installed" in config:
                installed_config = config["installed"]
                return {
                    "client_id": installed_config.get("client_id"),
                    "client_secret": installed_config.get("client_secret"),
                    "auth_uri": installed_config.get(
                        "auth_uri", "https://accounts.google.com/o/oauth2/auth"
                    ),
                    "token_uri": installed_config.get(
                        "token_uri", "https://oauth2.googleapis.com/token"
                    ),
                    "redirect_uris": installed_config.get(
                        "redirect_uris", [self.dynamic_oauth_redirect_uri]
                    ),
                }
            else:
                raise ValueError(
                    "OAuth client secrets JSON must contain either 'web' or 'installed' configuration"
                )

        # Fallback to environment variables
        if not self.google_client_id or not self.google_client_secret:
            raise ValueError(
                "OAuth configuration incomplete: Please set either GOOGLE_CLIENT_SECRETS_FILE or both GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET"
            )

        return {
            "client_id": self.google_client_id,
            "client_secret": self.google_client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [self.dynamic_oauth_redirect_uri],
        }

    def get_credentials_path(self, user_email: str) -> Path:
        """Get the path to store credentials for a specific user."""
        creds_dir = Path(self.credentials_dir)
        creds_dir.mkdir(exist_ok=True)
        return creds_dir / f"{user_email}_credentials.json"

    @property
    def protocol(self) -> str:
        """Get the protocol (http or https) based on SSL configuration."""
        return "https" if self.enable_https else "http"

    @property
    def feedback_base_url(self) -> str:
        """Get the base URL for feedback webhook callbacks.

        Uses FEEDBACK_BASE_URL env var if set, otherwise falls back to base_url.
        Useful when BASE_URL points to a proxy that doesn't forward /card-feedback.
        """
        explicit = os.getenv("FEEDBACK_BASE_URL")
        if explicit:
            return explicit
        return self.base_url

    @property
    def payment_base_url(self) -> str:
        """Get the base URL for payment flow pages (/pay, /api/payment-complete).

        Uses PAYMENT_BASE_URL env var if set, otherwise falls back to base_url.
        Same pattern as feedback_base_url.
        """
        explicit = os.getenv("PAYMENT_BASE_URL")
        if explicit:
            return explicit
        return self.base_url

    @property
    def base_url(self) -> str:
        """Get the base URL for the server."""
        # For OAuth flows, always use localhost if OAUTH_REDIRECT_URI points to localhost
        # This is needed because FastMCP Cloud only hosts the MCP endpoint, not OAuth endpoints
        env_oauth_uri = os.getenv("OAUTH_REDIRECT_URI", self.oauth_redirect_uri)
        if env_oauth_uri and "localhost" in env_oauth_uri:
            # In cloud deployment, use HTTPS for client-facing URLs even if enable_https=false
            # (CloudFlare handles HTTPS, but clients need HTTPS URLs)
            protocol = "https" if self.is_cloud_deployment else self.protocol
            # Extract port from OAuth redirect URI for consistency
            if ":8002" in env_oauth_uri:
                return f"{protocol}://localhost:8002"
            elif ":8000" in env_oauth_uri:
                return f"{protocol}://localhost:8000"
            else:
                return f"{protocol}://localhost:{self.server_port}"

        # Check if we have an explicit BASE_URL environment variable for cloud MCP endpoint
        explicit_base_url = os.getenv("BASE_URL")
        if explicit_base_url:
            return explicit_base_url

        # In cloud deployment, use HTTPS for client-facing URLs even if enable_https=false
        protocol = "https" if self.is_cloud_deployment else self.protocol
        return f"{protocol}://{self.server_host}:{self.server_port}"

    @property
    def dynamic_oauth_redirect_uri(self) -> str:
        """Get the OAuth redirect URI that dynamically switches between HTTP and HTTPS."""
        # Always use explicit OAUTH_REDIRECT_URI if it's been set via environment variable
        env_oauth_uri = os.getenv("OAUTH_REDIRECT_URI")
        if env_oauth_uri:
            # CRITICAL FIX: Automatically adjust protocol to match server configuration
            if self.enable_https and env_oauth_uri.startswith("http://localhost"):
                # Convert HTTP to HTTPS for localhost when HTTPS is enabled
                https_uri = env_oauth_uri.replace(
                    "http://localhost", "https://localhost"
                )
                logging.debug(
                    f"🔧 PROTOCOL FIX: Converted OAuth redirect URI from HTTP to HTTPS: {env_oauth_uri} → {https_uri}"
                )
                return https_uri
            elif not self.enable_https and env_oauth_uri.startswith(
                "https://localhost"
            ):
                # Convert HTTPS to HTTP for localhost when HTTPS is disabled
                http_uri = env_oauth_uri.replace(
                    "https://localhost", "http://localhost"
                )
                logging.debug(
                    f"🔧 PROTOCOL FIX: Converted OAuth redirect URI from HTTPS to HTTP: {env_oauth_uri} → {http_uri}"
                )
                return http_uri
            else:
                # Use as-is for non-localhost or already correct protocol
                return env_oauth_uri
        # Otherwise, use the configured value or construct from base_url
        if self.oauth_redirect_uri:
            return self.oauth_redirect_uri
        return f"{self.base_url}/oauth2callback"

    def get_uvicorn_ssl_config(self) -> Optional[dict]:
        """Get uvicorn SSL configuration for FastMCP if HTTPS is enabled."""
        if self.is_cloud_deployment:
            # FastMCP Cloud handles SSL automatically
            logging.debug("☁️ Cloud deployment detected - SSL handled by FastMCP Cloud")
            return None

        if not self.enable_https:
            return None

        # Return uvicorn-compatible SSL configuration for local deployment
        uvicorn_config = {
            "ssl_keyfile": self.ssl_key_file,
            "ssl_certfile": self.ssl_cert_file,
        }

        if self.ssl_ca_file:
            uvicorn_config["ssl_ca_certs"] = self.ssl_ca_file

        return uvicorn_config

    def validate_ssl_config(self) -> None:
        """Validate that SSL certificate files exist if HTTPS is enabled."""
        if not self.enable_https:
            return

        cert_path = Path(self.ssl_cert_file)
        key_path = Path(self.ssl_key_file)

        if not cert_path.exists():
            raise ValueError(f"SSL certificate file not found: {self.ssl_cert_file}")

        if not key_path.exists():
            raise ValueError(f"SSL private key file not found: {self.ssl_key_file}")

        if self.ssl_ca_file:
            ca_path = Path(self.ssl_ca_file)
            if not ca_path.exists():
                raise ValueError(f"SSL CA file not found: {self.ssl_ca_file}")


# Global settings instance
settings = Settings()
