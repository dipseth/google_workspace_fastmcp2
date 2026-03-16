"""Unit tests for the sampling middleware — focused on real bug-risk areas.

Tests cover:
- Template contract: every SamplingTemplate enum member has a working cache entry
  (catches forgotten cache entries when new templates are added)
- DSL error diagnostics: the _build_dsl_error_diagnostics function that enriches
  error results with actionable fix suggestions
- Resource routing: keyword-based resource selection for sampling context
- Qdrant null safety: history enhancer gracefully handles missing/uninitialized Qdrant
- Message coercion: 4 input types (str, list[str], SamplingMessage, MCPSamplingMessage)
  all correctly convert to MCP wire format
- DSL enrichment: post-call error enrichment appends diagnostics to tool results
- Pre-validation: DSL detection and routing in the middleware on_call_tool path
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mcp.types import SamplingMessage as MCPSamplingMessage
from mcp.types import TextContent as MCPTextContent

from middleware.sampling_middleware import (
    DSLToolConfig,
    EnhancedSamplingMiddleware,
    QdrantHistoryEnhancer,
    ResourceContextManager,
    SamplingContext,
    SamplingMessage,
    SamplingTemplate,
    _build_dsl_error_diagnostics,
)

# ---------------------------------------------------------------------------
# Helpers — mock DSLToolConfig for tests that need registered tools
# ---------------------------------------------------------------------------


def _make_mock_config(
    dsl_type_label: str = "card",
    arg_key: str = "card_description",
    error_keywords: list | None = None,
) -> DSLToolConfig:
    """Build a minimal DSLToolConfig with mock callables for testing."""
    mock_parse = MagicMock(
        return_value=MagicMock(is_valid=True, issues=[], suggestions=[], root_nodes=[])
    )
    mock_extract = MagicMock(return_value=None)
    return DSLToolConfig(
        arg_key=arg_key,
        parse_fn=mock_parse,
        extract_fn=mock_extract,
        result_type=MagicMock,
        description_attr=f"{dsl_type_label}_description",
        params_attr=f"{dsl_type_label}_params",
        params_arg_key=f"{dsl_type_label}_params",
        get_docs_fn=lambda: f"Mock {dsl_type_label} DSL docs",
        dsl_type_label=dsl_type_label,
        error_keywords=error_keywords,
    )


def _make_middleware_with_configs() -> EnhancedSamplingMiddleware:
    """Build middleware with both card and email DSL configs registered."""
    return EnhancedSamplingMiddleware(
        dsl_tool_configs={
            "send_dynamic_card": _make_mock_config(
                "card", "card_description", ["card_description"]
            ),
            "compose_dynamic_email": _make_mock_config(
                "email", "email_description", ["email_description"]
            ),
        }
    )


# ===========================================================================
# Template contract — catches forgotten cache entries for new enum members
# ===========================================================================


class TestTemplateContract:
    """Every SamplingTemplate member must have a complete cache entry.

    This is a real contract test — when someone adds a new SamplingTemplate
    enum value but forgets to add its config to _template_cache, sampling
    silently falls back to bare defaults (no system prompt, wrong temperature).
    """

    @pytest.fixture()
    def template_cache(self):
        mock_ctx = MagicMock()
        sctx = SamplingContext(fastmcp_context=mock_ctx, tool_name="test")
        return sctx._template_cache

    def test_every_enum_member_has_cache_entry(self, template_cache):
        missing = [m.name for m in SamplingTemplate if m not in template_cache]
        assert not missing, (
            f"SamplingTemplate members missing from _template_cache: {missing}"
        )

    def test_every_entry_has_system_prompt_or_fn(self, template_cache):
        """Templates without a system_prompt or system_prompt_fn produce empty LLM instructions."""
        for member, config in template_cache.items():
            has_prompt = "system_prompt" in config
            has_fn = "system_prompt_fn" in config
            assert has_prompt or has_fn, (
                f"{member.name} has no system_prompt — sampling will run without instructions"
            )

    def test_lazy_system_prompt_fn_is_callable(self, template_cache):
        """DSL_ERROR_RECOVERY uses a lazy loader; verify it's actually callable."""
        dsl_config = template_cache[SamplingTemplate.DSL_ERROR_RECOVERY]
        assert callable(dsl_config["system_prompt_fn"])
        # Actually call it to verify it doesn't crash at runtime
        result = dsl_config["system_prompt_fn"]()
        assert isinstance(result, str) and len(result) > 50


# ===========================================================================
# DSL error diagnostics — the error enrichment that helps LLMs fix DSL
# ===========================================================================


class TestBuildDslErrorDiagnostics:
    def test_no_dsl_string_returns_minimal_diag(self):
        """Without a DSL fragment, diagnostics just echo the error — no parser called."""
        diag = _build_dsl_error_diagnostics(Exception("boom"), "card", dsl_string=None)
        assert diag == {"dsl_type": "card", "error": "boom"}

    def test_config_based_no_dsl_string(self):
        """DSLToolConfig path: no dsl_string still returns minimal diag."""
        config = _make_mock_config("card")
        diag = _build_dsl_error_diagnostics(Exception("boom"), config, dsl_string=None)
        assert diag == {"dsl_type": "card", "error": "boom"}

    def test_card_dsl_produces_structured_issues(self):
        """With a real DSL string, the parser should find issues and add hints."""
        try:
            from gchat.wrapper_api import parse_dsl  # noqa: F401
        except ImportError:
            pytest.skip("gchat.wrapper_api not available")

        diag = _build_dsl_error_diagnostics(
            Exception("bad symbol"), "card", dsl_string="§[INVALID_SYMBOL]"
        )
        assert diag["dsl_type"] == "card"
        # Parser should have analyzed the string and added hints
        assert "hint" in diag

    def test_config_based_card_dsl(self):
        """DSLToolConfig path with a DSL string invokes parse_fn from config."""
        mock_parse = MagicMock(
            return_value=MagicMock(
                issues=["bad symbol"],
                suggestions=["use δ"],
                root_nodes=[],
            )
        )
        config = _make_mock_config("card")
        config.parse_fn = mock_parse
        diag = _build_dsl_error_diagnostics(
            Exception("bad"), config, dsl_string="§[X]", tool_name="send_dynamic_card"
        )
        assert diag["dsl_type"] == "card"
        assert diag["issues"] == ["bad symbol"]
        assert "hint" in diag
        mock_parse.assert_called_once_with("§[X]")

    def test_email_type_routes_to_email_parser(self):
        """dsl_type='email' should invoke the email parser, not card parser."""
        diag = _build_dsl_error_diagnostics(
            Exception("email error"), "email", dsl_string="ε[Ħ]"
        )
        assert diag["dsl_type"] == "email"
        # Even if parser fails, should not crash
        assert "error" in diag


# ===========================================================================
# Resource routing — determines what user data gets injected into sampling
# ===========================================================================


class TestResourceContextManager:
    def test_email_keywords_trigger_gmail_resources(self):
        rcm = ResourceContextManager(fastmcp_context=MagicMock())
        resources = rcm.get_relevant_resources_for_task("compose an email to John")
        gmail_uris = [r for r in resources if "gmail" in r]
        assert len(gmail_uris) >= 1, (
            "Email task should include at least one Gmail resource"
        )

    def test_file_keywords_trigger_drive_resources(self):
        rcm = ResourceContextManager(fastmcp_context=MagicMock())
        resources = rcm.get_relevant_resources_for_task("find my document in drive")
        drive_uris = [r for r in resources if "drive" in r or "recent" in r]
        assert len(drive_uris) >= 1, "File task should include Drive/recent resources"

    def test_no_keyword_match_excludes_service_resources(self):
        """A generic message should not inject Gmail or Drive resources (irrelevant noise)."""
        rcm = ResourceContextManager(fastmcp_context=MagicMock())
        resources = rcm.get_relevant_resources_for_task("hello")
        assert not any("gmail" in r for r in resources)
        assert not any("drive" in r for r in resources)

    def test_user_context_always_included(self):
        """User profile/email URIs must be present regardless of task keywords."""
        rcm = ResourceContextManager(fastmcp_context=MagicMock())
        for task in ["compose email", "find file", "random task"]:
            resources = rcm.get_relevant_resources_for_task(task)
            assert "user://current/profile" in resources
            assert "user://current/email" in resources

    @pytest.mark.asyncio
    async def test_get_resource_safely_returns_none_on_failure(self):
        """Resource fetches that fail should return None, not crash the sampling pipeline."""
        mock_ctx = MagicMock()
        mock_ctx.read_resource = AsyncMock(side_effect=Exception("network error"))
        rcm = ResourceContextManager(fastmcp_context=mock_ctx)
        result = await rcm.get_resource_safely("user://current/profile")
        assert result is None


# ===========================================================================
# Qdrant null safety — history enhancer gracefully handles edge cases
# ===========================================================================


class TestQdrantHistoryEnhancer:
    @pytest.mark.asyncio
    async def test_returns_empty_when_no_qdrant(self):
        """None middleware should not crash — returns empty list."""
        enhancer = QdrantHistoryEnhancer(qdrant_middleware=None)
        result = await enhancer.get_relevant_history("user@test.com", "query")
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_empty_when_not_initialized(self):
        """Qdrant present but not ready — should not crash."""
        mock_qm = MagicMock()
        mock_qm.is_initialized = False
        enhancer = QdrantHistoryEnhancer(qdrant_middleware=mock_qm)
        result = await enhancer.get_relevant_history("user@test.com", "query")
        assert result == []

    @pytest.mark.asyncio
    async def test_formats_search_results_correctly(self):
        """When Qdrant returns results, they should be formatted with expected keys."""
        mock_qm = MagicMock()
        mock_qm.is_initialized = True
        mock_qm.search = AsyncMock(
            return_value=[
                {
                    "tool_name": "search_drive",
                    "timestamp": "2026-01-01",
                    "score": 0.85,
                    "response_data": {"message": "Found 3 files"},
                },
            ]
        )
        enhancer = QdrantHistoryEnhancer(qdrant_middleware=mock_qm)
        result = await enhancer.get_relevant_history("user@test.com", "find files")
        assert len(result) == 1
        assert result[0]["tool_name"] == "search_drive"
        assert result[0]["score"] == 0.85
        assert "success_indicators" in result[0]

    def test_success_indicator_extraction(self):
        """Non-dict response_data should not crash indicator extraction."""
        enhancer = QdrantHistoryEnhancer(qdrant_middleware=None)
        # Non-dict response — should return empty, not crash
        assert (
            enhancer._extract_success_indicators(
                {"response_data": "string", "score": 0.5}
            )
            == []
        )
        # Dict with "success" — should detect it
        assert "successful_execution" in enhancer._extract_success_indicators(
            {"response_data": {"msg": "operation success"}, "score": 0.5}
        )
        # High score — should detect high_relevance
        assert "high_relevance" in enhancer._extract_success_indicators(
            {"response_data": {"data": "clean"}, "score": 0.9}
        )


# ===========================================================================
# Message coercion — 4 input types into MCP wire format
# ===========================================================================


class TestSamplingContextPrepareMessages:
    """Tests the _prepare_messages method that coerces various input types.

    This is real logic — the method handles str, list[str], SamplingMessage,
    and MCPSamplingMessage inputs. Getting the role wrong or wrapping incorrectly
    causes silent sampling failures.
    """

    @pytest.fixture()
    def sctx(self):
        return SamplingContext(fastmcp_context=MagicMock(), tool_name="test")

    def test_string_becomes_user_message(self, sctx):
        result = sctx._prepare_messages("hello world")
        assert len(result) == 1
        assert isinstance(result[0], MCPSamplingMessage)
        assert result[0].role == "user"
        assert result[0].content.text == "hello world"

    def test_list_of_strings(self, sctx):
        result = sctx._prepare_messages(["first", "second"])
        assert len(result) == 2
        assert result[0].content.text == "first"
        assert result[1].content.text == "second"

    def test_sampling_message_role_preserved(self, sctx):
        """SamplingMessage(role='assistant') must keep its role — not coerce to 'user'."""
        msg = SamplingMessage(role="assistant", content="I can help")
        result = sctx._prepare_messages([msg])
        assert result[0].role == "assistant"
        assert result[0].content.text == "I can help"

    def test_mcp_message_passthrough_no_wrapping(self, sctx):
        """MCPSamplingMessage objects should pass through without re-wrapping."""
        mcp_msg = MCPSamplingMessage(
            role="user", content=MCPTextContent(type="text", text="native")
        )
        result = sctx._prepare_messages([mcp_msg])
        assert result[0] is mcp_msg  # same object reference

    def test_mixed_input_types(self, sctx):
        """A list with mixed types should handle each correctly."""
        mcp_msg = MCPSamplingMessage(
            role="user", content=MCPTextContent(type="text", text="native")
        )
        result = sctx._prepare_messages(
            [
                "plain string",
                SamplingMessage(role="assistant", content="assist"),
                mcp_msg,
            ]
        )
        assert len(result) == 3
        assert result[0].role == "user"
        assert result[1].role == "assistant"
        assert result[2] is mcp_msg


# ===========================================================================
# DSL enrichment — post-call error enrichment adds diagnostics
# ===========================================================================


class TestEnrichDslErrors:
    """Tests the _enrich_dsl_errors method that appends diagnostic blocks to error results.

    This is a real post-processing path — when send_dynamic_card fails with an
    unknown symbol, the diagnostics block tells the LLM what went wrong and how to fix it.
    """

    def test_appends_diagnostic_block_on_error(self):
        mw = _make_middleware_with_configs()
        mock_result = MagicMock()
        mock_result.content = [
            MCPTextContent(
                type="text", text="ToolError: unknown symbol 'X' in card_description"
            )
        ]
        enriched = mw._enrich_dsl_errors(mock_result, "send_dynamic_card")
        assert len(enriched.content) == 2
        diag_text = enriched.content[1].text
        assert "DSL Diagnostics" in diag_text
        parsed = json.loads(diag_text.split("--- DSL Diagnostics ---\n")[1])
        assert parsed["dsl_type"] == "card"

    def test_noop_when_no_error_keywords(self):
        mw = _make_middleware_with_configs()
        mock_result = MagicMock()
        mock_result.content = [
            MCPTextContent(type="text", text="Card sent successfully!")
        ]
        enriched = mw._enrich_dsl_errors(mock_result, "send_dynamic_card")
        assert len(enriched.content) == 1

    def test_noop_when_no_content(self):
        """Result with no content blocks should not crash."""
        mw = _make_middleware_with_configs()
        mock_result = MagicMock()
        mock_result.content = []
        enriched = mw._enrich_dsl_errors(mock_result, "send_dynamic_card")
        assert len(enriched.content) == 0

    def test_email_tool_gets_email_dsl_type(self):
        """compose_dynamic_email errors should produce dsl_type='email' diagnostics."""
        mw = _make_middleware_with_configs()
        mock_result = MagicMock()
        mock_result.content = [
            MCPTextContent(
                type="text", text="ToolError: invalid dsl in email_description"
            )
        ]
        enriched = mw._enrich_dsl_errors(mock_result, "compose_dynamic_email")
        diag_text = enriched.content[1].text
        parsed = json.loads(diag_text.split("--- DSL Diagnostics ---\n")[1])
        assert parsed["dsl_type"] == "email"

    def test_noop_for_unregistered_tool(self):
        """Unregistered tool names should pass through unchanged."""
        mw = _make_middleware_with_configs()
        mock_result = MagicMock()
        mock_result.content = [
            MCPTextContent(type="text", text="ToolError: something broke")
        ]
        enriched = mw._enrich_dsl_errors(mock_result, "unknown_tool")
        assert len(enriched.content) == 1


# ===========================================================================
# DSL tool detection — routing for pre/post-validation
# ===========================================================================


class TestDslToolDetection:
    """The _is_dsl_tool and _dsl_configs control which tools get
    pre-validation and post-enrichment. Getting these wrong means DSL errors
    go undiagnosed or non-DSL tools get incorrectly processed.
    """

    def test_dsl_tools_are_recognized(self):
        mw = _make_middleware_with_configs()
        assert mw._is_dsl_tool("send_dynamic_card")
        assert mw._is_dsl_tool("compose_dynamic_email")

    def test_non_dsl_tools_excluded(self):
        mw = _make_middleware_with_configs()
        for tool in [
            "list_drive_files",
            "search_gmail",
            "health_check",
            "start_google_auth",
        ]:
            assert not mw._is_dsl_tool(tool), f"{tool} should not be a DSL tool"

    def test_dsl_configs_have_correct_arg_keys(self):
        """_dsl_configs[tool_name].arg_key maps to the right argument. Wrong arg_key = silent skip."""
        mw = _make_middleware_with_configs()
        assert mw._dsl_configs["send_dynamic_card"].arg_key == "card_description"
        assert mw._dsl_configs["compose_dynamic_email"].arg_key == "email_description"

    def test_no_configs_means_no_dsl_tools(self):
        """Middleware with no configs should not recognize any DSL tools."""
        mw = EnhancedSamplingMiddleware()
        assert not mw._is_dsl_tool("send_dynamic_card")
        assert not mw._is_dsl_tool("compose_dynamic_email")

    def test_register_dsl_tool_post_init(self):
        """register_dsl_tool adds a config after construction."""
        mw = EnhancedSamplingMiddleware()
        assert not mw._is_dsl_tool("new_dsl_tool")
        mw.register_dsl_tool("new_dsl_tool", _make_mock_config("custom", "custom_dsl"))
        assert mw._is_dsl_tool("new_dsl_tool")
        assert mw._dsl_configs["new_dsl_tool"].arg_key == "custom_dsl"


# ===========================================================================
# DSL recovery system prompt — built from registered configs
# ===========================================================================


class TestBuildDslRecoverySystemPrompt:
    def test_includes_all_registered_domains(self):
        mw = _make_middleware_with_configs()
        prompt = mw._build_dsl_recovery_system_prompt()
        assert "Card DSL Reference" in prompt
        assert "Email DSL Reference" in prompt
        assert "Mock card DSL docs" in prompt
        assert "Mock email DSL docs" in prompt

    def test_empty_configs_returns_generic_only(self):
        mw = EnhancedSamplingMiddleware()
        prompt = mw._build_dsl_recovery_system_prompt()
        assert "DSL error recovery expert" in prompt
        assert "Reference" not in prompt

    def test_tolerates_failing_docs_fn(self):
        """If one domain's get_docs_fn raises, it's skipped gracefully."""
        config = _make_mock_config("broken")
        config.get_docs_fn = MagicMock(side_effect=RuntimeError("docs unavailable"))
        mw = EnhancedSamplingMiddleware(dsl_tool_configs={"broken_tool": config})
        prompt = mw._build_dsl_recovery_system_prompt()
        # Should not raise, and should still have generic preamble
        assert "DSL error recovery expert" in prompt
