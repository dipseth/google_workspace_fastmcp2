"""
Enhanced Service Dispatcher for FastMCP2

This module provides an enhanced service dispatcher that uses metadata-driven routing
with confidence scoring and intelligent fallbacks.
"""

import logging

from config.enhanced_logging import setup_logger

logger = setup_logger()
from typing import Any, Dict, List, Optional

from fastmcp import FastMCP

from auth.scope_registry import ScopeRegistry
from auth.service_manager import get_google_service
from config.enhanced_logging import setup_logger
from middleware.mcp_metadata_handler import MCPMetadataHandler
from middleware.routing_helper import ServiceRouter, ServiceRoutingDecision
from resources.service_categorization_logic import ServiceCategorizer

logger = setup_logger()


class ServiceDispatchResult:
    """Result of service dispatch operation"""

    def __init__(
        self,
        service: Any,
        service_name: str,
        confidence_score: float,
        routing_decision: ServiceRoutingDecision,
        metadata: Dict[str, Any] = None,
    ):
        """
        Initialize dispatch result.

        Args:
            service: The actual service instance
            service_name: Name of the dispatched service
            confidence_score: Routing confidence score
            routing_decision: Complete routing decision with alternatives
            metadata: Additional metadata about the dispatch
        """
        self.service = service
        self.service_name = service_name
        self.confidence_score = confidence_score
        self.routing_decision = routing_decision
        self.metadata = metadata or {}
        self.is_confident = confidence_score >= 0.8
        self.has_alternatives = len(routing_decision.alternatives) > 0


class ServiceDispatchError(Exception):
    """Custom exception for service dispatch errors"""

    def __init__(
        self,
        message: str,
        suggested_services: List[str] = None,
        available_services: List[str] = None,
    ):
        """
        Initialize dispatch error.

        Args:
            message: Error message
            suggested_services: List of suggested alternative services
            available_services: List of all available services
        """
        super().__init__(message)
        self.suggested_services = suggested_services or []
        self.available_services = available_services or []


class EnhancedServiceDispatcher:
    """Enhanced service dispatcher with metadata-driven routing"""

    def __init__(self, mcp_server: FastMCP):
        """
        Initialize service dispatcher.

        Args:
            mcp_server: FastMCP server instance
        """
        self.mcp_server = mcp_server
        self.service_router = ServiceRouter(mcp_server)
        self.categorizer = ServiceCategorizer(mcp_server)
        self.metadata_handler = MCPMetadataHandler(mcp_server)
        self.logger = logging.getLogger(f"{__name__}.EnhancedServiceDispatcher")

        # Service instance cache
        self._service_instances = {}

        # Initialize service registry
        self._initialize_dispatcher()

    def _initialize_dispatcher(self):
        """Initialize the dispatcher with service registry"""
        try:
            # Refresh service registry
            self.service_router.refresh_service_registry()

            # Get available services
            available = self.service_router.get_available_services()
            self.logger.info(f"Initialized dispatcher with {len(available)} services")

        except Exception as e:
            self.logger.error(f"Failed to initialize dispatcher: {e}")

    async def dispatch_service(
        self,
        request: Dict[str, Any],
        user_email: str,
        available_scopes: List[str] = None,
    ) -> ServiceDispatchResult:
        """
        Dispatch request to appropriate service with confidence scoring.

        Args:
            request: Request data with method and parameters
            user_email: User's email address
            available_scopes: Currently available OAuth scopes

        Returns:
            ServiceDispatchResult with service instance and metadata

        Raises:
            ServiceDispatchError: If service dispatch fails
        """
        self.logger.info(f"Dispatching request: {request.get('method', 'unknown')}")

        # Step 1: Identify service using service router
        routing_decision = self.service_router.identify_service_from_request(request)

        # Step 2: Validate routing decision
        validation = self.service_router.validate_routing_decision(
            routing_decision, available_scopes
        )

        if not validation["is_valid"]:
            # Try fallback options
            if routing_decision.fallback_available:
                self.logger.warning("Primary routing failed, trying alternatives")
                return await self._try_fallback_routing(
                    routing_decision, user_email, available_scopes, request
                )
            else:
                # No alternatives available
                available_services = [
                    svc["name"] for svc in self.service_router.get_available_services()
                ]
                raise ServiceDispatchError(
                    f"Cannot dispatch request: {'; '.join(validation['warnings'])}",
                    suggested_services=[
                        alt.service for alt in routing_decision.alternatives
                    ],
                    available_services=available_services,
                )

        # Step 3: Get service instance
        primary_service = routing_decision.primary.service

        try:
            service_instance = await self._get_service_instance(
                primary_service, user_email, available_scopes
            )

            # Step 4: Create successful dispatch result
            result = ServiceDispatchResult(
                service=service_instance,
                service_name=primary_service,
                confidence_score=routing_decision.primary.confidence_score,
                routing_decision=routing_decision,
                metadata={
                    "routing_reasoning": routing_decision.primary.reasoning,
                    "validation_warnings": validation.get("warnings", []),
                    "fallback_available": routing_decision.fallback_available,
                    "service_metadata": self._get_service_registry_info(
                        primary_service
                    ),
                },
            )

            self.logger.info(
                f"Successfully dispatched to {primary_service} (confidence: {result.confidence_score:.2f})"
            )
            return result

        except Exception as e:
            self.logger.error(
                f"Failed to get service instance for {primary_service}: {e}"
            )

            # Try fallback if available
            if routing_decision.fallback_available:
                return await self._try_fallback_routing(
                    routing_decision, user_email, available_scopes, request
                )
            else:
                raise ServiceDispatchError(
                    f"Failed to dispatch to {primary_service}: {str(e)}",
                    suggested_services=[
                        alt.service for alt in routing_decision.alternatives
                    ],
                )

    async def _try_fallback_routing(
        self,
        routing_decision: ServiceRoutingDecision,
        user_email: str,
        available_scopes: List[str],
        request: Dict[str, Any],
    ) -> ServiceDispatchResult:
        """Try fallback routing options"""
        self.logger.info("Attempting fallback routing")

        for alternative in routing_decision.alternatives:
            try:
                self.logger.info(f"Trying fallback service: {alternative.service}")

                service_instance = await self._get_service_instance(
                    alternative.service, user_email, available_scopes
                )

                result = ServiceDispatchResult(
                    service=service_instance,
                    service_name=alternative.service,
                    confidence_score=alternative.confidence_score,
                    routing_decision=routing_decision,
                    metadata={
                        "routing_reasoning": alternative.reasoning,
                        "fallback_used": True,
                        "original_target": routing_decision.primary.service,
                        "service_metadata": self._get_service_registry_info(
                            alternative.service
                        ),
                    },
                )

                self.logger.info(f"Fallback successful: {alternative.service}")
                return result

            except Exception as e:
                self.logger.warning(f"Fallback to {alternative.service} failed: {e}")
                continue

        # All fallbacks failed
        available_services = [
            svc["name"] for svc in self.service_router.get_available_services()
        ]
        raise ServiceDispatchError(
            f"All routing options failed. Primary: {routing_decision.primary.service}, "
            f"Alternatives: {[alt.service for alt in routing_decision.alternatives]}",
            available_services=available_services,
        )

    async def _get_service_instance(
        self, service_name: str, user_email: str, available_scopes: List[str] = None
    ) -> Any:
        """
        Get or create service instance with proper scopes.

        Args:
            service_name: Name of the service
            user_email: User's email address
            available_scopes: Currently available scopes

        Returns:
            Service instance
        """
        # Check cache first
        cache_key = f"{user_email}:{service_name}"
        if cache_key in self._service_instances:
            self.logger.debug(f"Using cached service instance for {service_name}")
            return self._service_instances[cache_key]

        # Determine required scopes
        if available_scopes:
            # Use available scopes
            service_scopes = available_scopes
        else:
            # Get default scopes for service
            try:
                service_scopes = ScopeRegistry.get_service_scopes(service_name, "basic")
            except ValueError:
                # Unknown service, use minimal scopes
                service_scopes = ScopeRegistry.get_service_scopes("base", "basic")

        # Create service instance
        service_instance = await get_google_service(
            user_email=user_email, service_type=service_name, scopes=service_scopes
        )

        # Cache the instance
        self._service_instances[cache_key] = service_instance

        return service_instance

    def _get_service_registry_info(self, service_name: str) -> Optional[Dict[str, Any]]:
        """Get service information from registry"""
        service_map = self.categorizer.generate_service_map()
        return service_map.get(service_name)

    def get_dispatch_analytics(self) -> Dict[str, Any]:
        """
        Get analytics about dispatch operations.

        Returns:
            Analytics data
        """
        routing_analytics = self.service_router.get_routing_analytics()

        return {
            "routing_analytics": routing_analytics,
            "cached_services": len(self._service_instances),
            "dispatch_strategies": [
                "Metadata-driven routing",
                "Confidence scoring",
                "Intelligent fallbacks",
                "Scope validation",
            ],
            "error_handling": [
                "Service suggestions",
                "Alternative routing",
                "Availability checking",
            ],
        }

    def clear_service_cache(self, user_email: str = None):
        """
        Clear service instance cache.

        Args:
            user_email: If provided, only clear cache for this user
        """
        if user_email:
            keys_to_remove = [
                key
                for key in self._service_instances.keys()
                if key.startswith(f"{user_email}:")
            ]
            for key in keys_to_remove:
                del self._service_instances[key]
            self.logger.info(
                f"Cleared {len(keys_to_remove)} cached services for {user_email}"
            )
        else:
            count = len(self._service_instances)
            self._service_instances.clear()
            self.logger.info(f"Cleared all {count} cached services")

    def get_service_suggestions(self, partial_name: str) -> List[Dict[str, Any]]:
        """
        Get service suggestions based on partial name or pattern.

        Args:
            partial_name: Partial service name or pattern

        Returns:
            List of matching services with metadata
        """
        available_services = self.service_router.get_available_services()
        suggestions = []

        partial_lower = partial_name.lower()

        for service in available_services:
            # Check name matches
            if partial_lower in service["name"].lower():
                suggestions.append(
                    {"service": service, "match_type": "name", "relevance": 0.9}
                )

            # Check description matches
            elif partial_lower in service["description"].lower():
                suggestions.append(
                    {"service": service, "match_type": "description", "relevance": 0.7}
                )

            # Check operation matches
            elif any(
                partial_lower in op.lower() for op in service.get("operations", [])
            ):
                suggestions.append(
                    {"service": service, "match_type": "operations", "relevance": 0.6}
                )

        # Sort by relevance
        suggestions.sort(key=lambda x: x["relevance"], reverse=True)

        return suggestions[:5]  # Top 5 suggestions

    def refresh_dispatcher(self):
        """Refresh the dispatcher registry and clear caches"""
        self.logger.info("Refreshing service dispatcher")
        self._initialize_dispatcher()
        self.clear_service_cache()


def create_enhanced_dispatcher(mcp_server: FastMCP) -> EnhancedServiceDispatcher:
    """
    Factory function to create enhanced service dispatcher.

    Args:
        mcp_server: FastMCP server instance

    Returns:
        Configured service dispatcher
    """
    return EnhancedServiceDispatcher(mcp_server)


def generate_enhanced_error_message(
    error: ServiceDispatchError, request: Dict[str, Any]
) -> str:
    """
    Generate enhanced error message with service suggestions.

    Args:
        error: ServiceDispatchError with suggestions
        request: Original request data

    Returns:
        Enhanced error message
    """
    message = "**Service Routing Error**\n\n"
    message += f"Request: `{request.get('method', 'unknown')}`\n"
    message += f"Error: {str(error)}\n\n"

    if error.suggested_services:
        message += "**Suggested Services:**\n"
        for service in error.suggested_services:
            message += f"- `{service}`\n"
        message += "\n"

    if error.available_services:
        message += f"**Available Services ({len(error.available_services)}):**\n"
        for service in error.available_services[:10]:  # Limit to first 10
            message += f"- `{service}`\n"

        if len(error.available_services) > 10:
            message += f"... and {len(error.available_services) - 10} more\n"

    message += "\n**💡 Tip:** Use the service name as a prefix in your method name for better routing."

    return message
