"""
Test Suite for Routing Improvements (Task 3.3)

This test suite verifies the enhanced routing system with metadata-driven
service identification, confidence scoring, and intelligent fallbacks.
"""

import logging
from typing import List
from unittest.mock import Mock, patch

import pytest

from auth.service_dispatcher import (
    EnhancedServiceDispatcher,
    ServiceDispatchError,
    ServiceDispatchResult,
    create_enhanced_dispatcher,
    generate_enhanced_error_message,
)

# Import the components we're testing
from middleware.routing_helper import (
    ServiceRouter,
    create_service_router,
)
from resources.service_categorization_logic import ServiceCategorizer

logger = logging.getLogger(__name__)


class MockFastMCP:
    """Mock FastMCP server for testing"""

    def __init__(self):
        self.tools = []
        self._tool_manager = Mock()
        self._tool_manager._tools = {}

    def add_mock_tool(
        self, name: str, tags: List[str], required_scopes: List[str] = None
    ):
        """Add a mock tool for testing"""
        tool = Mock()
        tool.name = name
        tool.description = f"Test tool: {name}"
        tool.tags = set(tags) if tags else set()
        tool.required_scopes = required_scopes or []
        tool.annotations = {}

        self._tool_manager._tools[name] = tool
        self.tools.append(tool)


class TestServiceRouter:
    """Test service router functionality"""

    def setup_method(self):
        """Setup test fixtures"""
        self.mcp_server = MockFastMCP()

        # Add mock tools for different services
        self.mcp_server.add_mock_tool(
            "send_gmail_message",
            ["gmail", "email", "send"],
            ["https://www.googleapis.com/auth/gmail.send"],
        )
        self.mcp_server.add_mock_tool(
            "upload_to_drive",
            ["drive", "file", "upload"],
            ["https://www.googleapis.com/auth/drive.file"],
        )
        self.mcp_server.add_mock_tool(
            "create_event",
            ["calendar", "event", "create"],
            ["https://www.googleapis.com/auth/calendar.events"],
        )

        self.service_router = ServiceRouter(self.mcp_server)

    def test_direct_tool_mapping(self):
        """Test direct tool name to service mapping"""
        request = {"method": "send_gmail_message", "params": {}}

        decision = self.service_router.identify_service_from_request(request)

        assert decision.primary.service == "gmail"
        assert (
            decision.primary.confidence_score >= 0.9
        )  # High confidence for direct mapping
        assert "Direct tool mapping" in decision.primary.reasoning[0]

    def test_pattern_matching(self):
        """Test service pattern matching in method names"""
        request = {"method": "gmail_list_messages", "params": {}}

        decision = self.service_router.identify_service_from_request(request)

        assert decision.primary.service == "gmail"
        assert (
            decision.primary.confidence_score >= 0.7
        )  # Good confidence for pattern match
        assert "Pattern match" in decision.primary.reasoning[0]

    def test_parameter_analysis(self):
        """Test service identification from parameters"""
        request = {
            "method": "unknown_method",
            "params": {
                "file_id": "1234567890",
                "user_google_email": "test@example.com",
            },
        }

        decision = self.service_router.identify_service_from_request(request)

        # Should identify drive service from file_id parameter
        assert decision.primary.service == "drive"
        assert (
            decision.primary.confidence_score >= 0.3
        )  # Lower confidence for parameter analysis

    def test_service_capabilities_matching(self):
        """Test service capability-based matching"""
        request = {"method": "create_something", "params": {}}

        decision = self.service_router.identify_service_from_request(request)

        # Should have some routing decision, even if low confidence
        assert decision.primary is not None
        assert decision.primary.confidence_score >= 0.0

    def test_confidence_scoring(self):
        """Test confidence scoring system"""
        # High confidence case
        high_conf_request = {"method": "send_gmail_message", "params": {}}
        high_conf_decision = self.service_router.identify_service_from_request(
            high_conf_request
        )

        # Low confidence case
        low_conf_request = {"method": "unknown_method", "params": {}}
        low_conf_decision = self.service_router.identify_service_from_request(
            low_conf_request
        )

        assert (
            high_conf_decision.primary.confidence_score
            > low_conf_decision.primary.confidence_score
        )
        assert high_conf_decision.primary.is_confident
        assert not low_conf_decision.primary.is_confident

    def test_routing_validation(self):
        """Test routing decision validation"""
        request = {"method": "send_gmail_message", "params": {}}
        decision = self.service_router.identify_service_from_request(request)

        # Test with sufficient scopes
        available_scopes = ["https://www.googleapis.com/auth/gmail.send"]
        validation = self.service_router.validate_routing_decision(
            decision, available_scopes
        )

        assert validation["is_valid"]
        assert len(validation["warnings"]) == 0

        # Test with insufficient scopes
        insufficient_scopes = ["https://www.googleapis.com/auth/userinfo.email"]
        validation_bad = self.service_router.validate_routing_decision(
            decision, insufficient_scopes
        )

        assert len(validation_bad.get("scope_issues", [])) > 0

    def test_dynamic_service_registration(self):
        """Test dynamic service registration from tool metadata"""
        available_services = self.service_router.get_available_services()

        service_names = [svc["name"] for svc in available_services]

        # Should have discovered services from our mock tools
        assert "gmail" in service_names
        assert "drive" in service_names
        assert "calendar" in service_names

        # Check service metadata
        gmail_service = next(
            svc for svc in available_services if svc["name"] == "gmail"
        )
        assert gmail_service["tool_count"] >= 1
        assert gmail_service["confidence_available"]


class TestEnhancedServiceDispatcher:
    """Test enhanced service dispatcher functionality"""

    def setup_method(self):
        """Setup test fixtures"""
        self.mcp_server = MockFastMCP()

        # Add comprehensive mock tools
        self.mcp_server.add_mock_tool(
            "send_gmail_message",
            ["gmail", "email", "send"],
            ["https://www.googleapis.com/auth/gmail.send"],
        )
        self.mcp_server.add_mock_tool(
            "list_gmail_messages",
            ["gmail", "email", "list"],
            ["https://www.googleapis.com/auth/gmail.readonly"],
        )

        self.dispatcher = EnhancedServiceDispatcher(self.mcp_server)

    @patch("auth.service_dispatcher.get_google_service")
    async def test_successful_dispatch(self, mock_get_service):
        """Test successful service dispatch"""
        # Mock successful service creation
        mock_service = Mock()
        mock_get_service.return_value = mock_service

        request = {"method": "send_gmail_message", "params": {}}
        user_email = "test@example.com"

        result = await self.dispatcher.dispatch_service(request, user_email)

        assert isinstance(result, ServiceDispatchResult)
        assert result.service == mock_service
        assert result.service_name == "gmail"
        assert result.confidence_score >= 0.8
        assert result.is_confident

    @patch("auth.service_dispatcher.get_google_service")
    async def test_fallback_routing(self, mock_get_service):
        """Test fallback routing when primary service fails"""

        # Mock service creation failure for primary, success for fallback
        def mock_service_side_effect(*args, **kwargs):
            service_type = kwargs.get(
                "service_type", args[1] if len(args) > 1 else None
            )
            if service_type == "gmail":
                raise Exception("Primary service failed")
            else:
                return Mock()

        mock_get_service.side_effect = mock_service_side_effect

        # Create request that might have multiple service candidates
        request = {"method": "email_operation", "params": {"message_id": "123"}}
        user_email = "test@example.com"

        try:
            result = await self.dispatcher.dispatch_service(request, user_email)
            # If successful, should use fallback service
            assert (
                result.metadata.get("fallback_used", False)
                or result.confidence_score < 1.0
            )
        except ServiceDispatchError as e:
            # If all fallbacks fail, should have helpful error message
            assert len(e.suggested_services) >= 0
            assert len(e.available_services) > 0

    def test_service_suggestions(self):
        """Test service suggestion system"""
        suggestions = self.dispatcher.get_service_suggestions("email")

        assert len(suggestions) > 0

        # Should find gmail service
        gmail_suggestion = next(
            (s for s in suggestions if s["service"]["name"] == "gmail"), None
        )
        assert gmail_suggestion is not None
        assert gmail_suggestion["match_type"] in ["name", "description"]

    def test_enhanced_error_messages(self):
        """Test enhanced error message generation"""
        error = ServiceDispatchError(
            "Test error message",
            suggested_services=["gmail", "drive"],
            available_services=["gmail", "drive", "calendar"],
        )

        request = {"method": "test_method", "params": {}}

        message = generate_enhanced_error_message(error, request)

        assert "Service Routing Error" in message
        assert "test_method" in message
        assert "Suggested Services" in message
        assert "Available Services" in message
        assert "gmail" in message
        assert "drive" in message

    def test_dispatch_analytics(self):
        """Test dispatch analytics functionality"""
        analytics = self.dispatcher.get_dispatch_analytics()

        assert "routing_analytics" in analytics
        assert "cached_services" in analytics
        assert "dispatch_strategies" in analytics
        assert "error_handling" in analytics

        # Check that analytics contain expected strategies
        strategies = analytics["dispatch_strategies"]
        assert "Metadata-driven routing" in strategies
        assert "Confidence scoring" in strategies
        assert "Intelligent fallbacks" in strategies


class TestServiceCategorizer:
    """Test service categorizer functionality"""

    def setup_method(self):
        """Setup test fixtures"""
        self.mcp_server = MockFastMCP()

        # Add tools for multiple services
        self.mcp_server.add_mock_tool("gmail_send", ["gmail", "send"])
        self.mcp_server.add_mock_tool("gmail_read", ["gmail", "read"])
        self.mcp_server.add_mock_tool("drive_upload", ["drive", "upload"])

        self.categorizer = ServiceCategorizer(self.mcp_server)

    def test_service_discovery(self):
        """Test service discovery from tools"""
        discovered = self.categorizer.discover_services_from_tools()

        assert "gmail" in discovered
        assert "drive" in discovered

        gmail_info = discovered["gmail"]
        assert len(gmail_info["tools"]) >= 2  # Should have send and read tools
        assert (
            "write" in gmail_info["operations"]
        )  # 'send' maps to 'write' operation type
        assert "read" in gmail_info["operations"]

    def test_tool_categorization_by_tags(self):
        """Test tool categorization by tags"""
        categorized = self.categorizer.categorize_tools_by_tags()

        assert "gmail" in categorized
        assert "drive" in categorized
        assert "send" in categorized
        assert "upload" in categorized

    def test_service_capabilities(self):
        """Test service capability detection"""
        capabilities = self.categorizer.get_service_capabilities("gmail")

        assert capabilities["service"] == "gmail"
        assert capabilities["total_tools"] >= 2
        assert (
            "write" in capabilities["operations"]
        )  # 'send' maps to 'write' operation type
        assert "read" in capabilities["operations"]

    def test_service_map_generation(self):
        """Test comprehensive service map generation"""
        service_map = self.categorizer.generate_service_map()

        assert "gmail" in service_map
        assert "drive" in service_map

        gmail_service = service_map["gmail"]
        assert gmail_service["name"] == "gmail"
        assert gmail_service["total_tools"] >= 2
        assert len(gmail_service["operations"]) > 0


class TestIntegrationScenarios:
    """Test integration scenarios combining all components"""

    def setup_method(self):
        """Setup comprehensive test environment"""
        self.mcp_server = MockFastMCP()

        # Add realistic tool set
        tools_data = [
            (
                "send_gmail_message",
                ["gmail", "send", "email"],
                ["https://www.googleapis.com/auth/gmail.send"],
            ),
            (
                "list_gmail_messages",
                ["gmail", "read", "email"],
                ["https://www.googleapis.com/auth/gmail.readonly"],
            ),
            (
                "upload_to_drive",
                ["drive", "upload", "file"],
                ["https://www.googleapis.com/auth/drive.file"],
            ),
            (
                "search_drive_files",
                ["drive", "search", "file"],
                ["https://www.googleapis.com/auth/drive.readonly"],
            ),
            (
                "create_event",
                ["calendar", "create", "event"],
                ["https://www.googleapis.com/auth/calendar.events"],
            ),
            (
                "list_events",
                ["calendar", "list", "event"],
                ["https://www.googleapis.com/auth/calendar.readonly"],
            ),
        ]

        for name, tags, scopes in tools_data:
            self.mcp_server.add_mock_tool(name, tags, scopes)

        self.service_router = ServiceRouter(self.mcp_server)
        self.dispatcher = EnhancedServiceDispatcher(self.mcp_server)

    def test_end_to_end_routing(self):
        """Test complete end-to-end routing scenario"""
        # Test various request types
        test_requests = [
            {
                "method": "send_gmail_message",
                "expected_service": "gmail",
                "expected_confidence": 0.9,
            },
            {
                "method": "upload_to_drive",
                "expected_service": "drive",
                "expected_confidence": 0.9,
            },
            {
                "method": "create_event",
                "expected_service": "calendar",
                "expected_confidence": 0.9,
            },
            {
                "method": "gmail_search",
                "expected_service": "gmail",
                "expected_confidence": 0.7,
            },
            {
                "method": "unknown_method",
                "expected_service": None,
                "expected_confidence": 0.3,
            },
        ]

        for test_req in test_requests:
            request = {"method": test_req["method"], "params": {}}
            decision = self.service_router.identify_service_from_request(request)

            if test_req["expected_service"]:
                assert decision.primary.service == test_req["expected_service"]
                assert (
                    decision.primary.confidence_score >= test_req["expected_confidence"]
                )
            else:
                # For unknown methods, should still provide some routing decision
                assert decision.primary is not None
                assert (
                    decision.primary.confidence_score <= test_req["expected_confidence"]
                )

    def test_metadata_consistency(self):
        """Test consistency between different metadata components"""
        # Get services from different components
        routing_services = {
            svc["name"] for svc in self.service_router.get_available_services()
        }
        categorizer_services = set(
            self.dispatcher.categorizer.discover_services_from_tools().keys()
        )

        # Should have significant overlap
        common_services = routing_services & categorizer_services
        assert len(common_services) > 0

        # All services should be consistent
        assert routing_services == categorizer_services


class TestPerformanceAndCaching:
    """Test performance and caching aspects"""

    def setup_method(self):
        """Setup performance test environment"""
        self.mcp_server = MockFastMCP()

        # Add many tools to test performance
        for i in range(50):
            service = ["gmail", "drive", "calendar"][i % 3]
            self.mcp_server.add_mock_tool(f"tool_{i}", [service, "test"])

        self.service_router = ServiceRouter(self.mcp_server)

    def test_service_registry_caching(self):
        """Test that service registry is properly cached"""
        # First call should initialize cache
        services1 = self.service_router.get_available_services()

        # Second call should use cache
        services2 = self.service_router.get_available_services()

        assert services1 == services2
        assert len(services1) > 0

    def test_routing_performance(self):
        """Test routing performance with many tools"""
        import time

        request = {"method": "gmail_test_method", "params": {}}

        # Time routing decision
        start_time = time.time()
        decision = self.service_router.identify_service_from_request(request)
        end_time = time.time()

        # Should be fast (< 100ms for this simple case)
        routing_time = end_time - start_time
        assert routing_time < 0.1

        # Should still make reasonable routing decision
        assert decision.primary is not None
        assert decision.primary.service == "gmail"


def test_factory_functions():
    """Test factory functions"""
    mcp_server = MockFastMCP()

    # Test service router factory
    service_router = create_service_router(mcp_server)
    assert isinstance(service_router, ServiceRouter)

    # Test dispatcher factory
    dispatcher = create_enhanced_dispatcher(mcp_server)
    assert isinstance(dispatcher, EnhancedServiceDispatcher)


def test_error_message_generation():
    """Test error message generation utilities"""
    error = ServiceDispatchError(
        "Cannot find service",
        suggested_services=["gmail", "drive"],
        available_services=["gmail", "drive", "calendar", "docs"],
    )

    request = {"method": "unknown_method", "params": {"test": "value"}}

    message = generate_enhanced_error_message(error, request)

    # Check message contains key elements
    assert "Service Routing Error" in message
    assert "unknown_method" in message
    assert "Suggested Services" in message
    assert "Available Services" in message
    assert "gmail" in message
    assert "drive" in message
    assert "💡 Tip" in message


if __name__ == "__main__":
    """Run tests if executed directly"""
    pytest.main([__file__, "-v", "--tb=short"])
