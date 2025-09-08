"""
Routing Helper for FastMCP2

This utility provides routing intelligence and service identification based on
metadata-driven analysis, using ServiceCategorizer and confidence scoring.
It serves as a routing engine component for the service dispatcher.
"""

import logging
from typing import Dict, List, Optional, Any, Tuple
from fastmcp import FastMCP
from resources.service_categorization_logic import ServiceCategorizer
from middleware.mcp_metadata_handler import MCPMetadataHandler
from auth.scope_registry import ScopeRegistry

logger = logging.getLogger(__name__)


class RoutingConfidence:
    """Represents routing confidence with scoring details"""
    
    def __init__(self, service: str, confidence_score: float, reasoning: List[str]):
        """
        Initialize routing confidence.
        
        Args:
            service: Identified service name
            confidence_score: Confidence score (0.0-1.0)
            reasoning: List of reasoning factors that contributed to the score
        """
        self.service = service
        self.confidence_score = confidence_score
        self.reasoning = reasoning
        self.is_confident = confidence_score >= 0.8  # High confidence threshold
        self.needs_fallback = confidence_score < 0.5  # Low confidence threshold


class ServiceRoutingDecision:
    """Represents a complete routing decision with alternatives"""
    
    def __init__(self, primary: RoutingConfidence, alternatives: List[RoutingConfidence] = None):
        """
        Initialize routing decision.
        
        Args:
            primary: Primary routing choice
            alternatives: Alternative routing options
        """
        self.primary = primary
        self.alternatives = alternatives or []
        self.fallback_available = len(self.alternatives) > 0


class ServiceRouter:
    """Service router for metadata-driven request routing"""
    
    def __init__(self, mcp_server: FastMCP):
        """
        Initialize service router.
        
        Args:
            mcp_server: FastMCP server instance
        """
        self.mcp_server = mcp_server
        self.categorizer = ServiceCategorizer(mcp_server)
        self.metadata_handler = MCPMetadataHandler(mcp_server)
        self.logger = logging.getLogger(f"{__name__}.ServiceRouter")
        
        # Cache for service mappings
        self._service_cache = {}
        self._tool_service_cache = {}
        
        # Initialize dynamic service registry
        self._initialize_service_registry()
    
    def _initialize_service_registry(self):
        """Initialize dynamic service registry from tool metadata"""
        try:
            discovered_services = self.categorizer.discover_services_from_tools()
            self._service_cache = discovered_services
            
            # Build tool -> service mapping cache
            for service_name, service_info in discovered_services.items():
                for tool_info in service_info.get('tools', []):
                    tool_name = tool_info['name']
                    self._tool_service_cache[tool_name] = service_name
            
            self.logger.info(f"Initialized routing registry with {len(discovered_services)} services")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize service registry: {e}")
            self._service_cache = {}
            self._tool_service_cache = {}
    
    def identify_service_from_request(self, request: Dict[str, Any]) -> ServiceRoutingDecision:
        """
        Identify target service from request with confidence scoring.
        
        Args:
            request: Request data containing method, params, etc.
            
        Returns:
            ServiceRoutingDecision with primary choice and alternatives
        """
        self.logger.debug(f"Identifying service for request: {request.get('method', 'unknown')}")
        
        # Extract request components
        method = request.get('method', '')
        params = request.get('params', {})
        
        # Multiple routing strategies with confidence scores
        routing_candidates = []
        
        # Strategy 1: Direct tool name matching (highest confidence)
        if method:
            direct_service = self._get_service_by_tool_name(method)
            if direct_service:
                routing_candidates.append(RoutingConfidence(
                    service=direct_service,
                    confidence_score=0.95,
                    reasoning=[f"Direct tool mapping: {method} -> {direct_service}"]
                ))
        
        # Strategy 2: Pattern matching in method name (medium confidence)
        pattern_matches = self._match_service_patterns(method)
        for service, score in pattern_matches:
            routing_candidates.append(RoutingConfidence(
                service=service,
                confidence_score=score,
                reasoning=[f"Pattern match in method name: {method}"]
            ))
        
        # Strategy 3: Parameter-based inference (lower confidence)
        param_matches = self._analyze_parameters(params)
        for service, score, reason in param_matches:
            routing_candidates.append(RoutingConfidence(
                service=service,
                confidence_score=score,
                reasoning=[reason]
            ))
        
        # Strategy 4: Service capability matching (lowest confidence)
        capability_matches = self._match_service_capabilities(request)
        for service, score, reason in capability_matches:
            routing_candidates.append(RoutingConfidence(
                service=service,
                confidence_score=score,
                reasoning=[reason]
            ))
        
        # Sort candidates by confidence score
        routing_candidates.sort(key=lambda x: x.confidence_score, reverse=True)
        
        if not routing_candidates:
            # No service identified - create unknown service decision
            unknown = RoutingConfidence(
                service="unknown",
                confidence_score=0.0,
                reasoning=["No service patterns matched"]
            )
            return ServiceRoutingDecision(unknown)
        
        # Return primary choice with alternatives
        primary = routing_candidates[0]
        alternatives = routing_candidates[1:3]  # Top 2 alternatives
        
        self.logger.info(f"Service routing: {primary.service} (confidence: {primary.confidence_score:.2f})")
        
        return ServiceRoutingDecision(primary, alternatives)
    
    def _get_service_by_tool_name(self, tool_name: str) -> Optional[str]:
        """Get service directly from tool name mapping"""
        return self._tool_service_cache.get(tool_name)
    
    def _match_service_patterns(self, method_name: str) -> List[Tuple[str, float]]:
        """Match service patterns in method name"""
        matches = []
        method_lower = method_name.lower()
        
        # Service-specific patterns with confidence scores
        service_patterns = {
            'gmail': (['gmail', 'email', 'message', 'mail'], 0.8),
            'drive': (['drive', 'file', 'folder', 'document', 'upload'], 0.8),
            'calendar': (['calendar', 'event', 'schedule'], 0.8),
            'chat': (['chat', 'space', 'conversation'], 0.8),
            'docs': (['docs', 'document'], 0.7),
            'sheets': (['sheets', 'spreadsheet'], 0.7),
            'slides': (['slides', 'presentation'], 0.7),
            'forms': (['forms', 'form'], 0.7),
            'photos': (['photos', 'photo', 'image'], 0.7)
        }
        
        for service, (patterns, base_confidence) in service_patterns.items():
            for pattern in patterns:
                if pattern in method_lower:
                    # Adjust confidence based on pattern strength
                    if method_lower.startswith(pattern):
                        confidence = base_confidence
                    elif pattern in method_lower:
                        confidence = base_confidence * 0.8
                    else:
                        confidence = base_confidence * 0.6
                    
                    matches.append((service, confidence))
                    break
        
        return matches
    
    def _analyze_parameters(self, params: Dict[str, Any]) -> List[Tuple[str, float, str]]:
        """Analyze request parameters to infer service"""
        matches = []
        
        # Parameter-based service inference
        if 'user_google_email' in params:
            matches.append(('gmail', 0.3, 'Has user_google_email parameter'))
        
        if 'file_id' in params or 'folder_id' in params:
            matches.append(('drive', 0.4, 'Has file/folder ID parameters'))
        
        if 'event_id' in params or 'calendar_id' in params:
            matches.append(('calendar', 0.4, 'Has event/calendar ID parameters'))
        
        if 'space_id' in params or 'message_id' in params:
            matches.append(('chat', 0.4, 'Has space/message ID parameters'))
        
        if 'spreadsheet_id' in params:
            matches.append(('sheets', 0.4, 'Has spreadsheet ID parameter'))
        
        if 'presentation_id' in params:
            matches.append(('slides', 0.4, 'Has presentation ID parameter'))
        
        return matches
    
    def _match_service_capabilities(self, request: Dict[str, Any]) -> List[Tuple[str, float, str]]:
        """Match request to service capabilities"""
        matches = []
        
        # Use service map to check capabilities
        for service_name, service_info in self._service_cache.items():
            capability_score = 0.0
            reasons = []
            
            # Check if request matches service operations
            operations = service_info.get('operations', [])
            method = request.get('method', '').lower()
            
            if any(op in method for op in operations):
                capability_score += 0.2
                reasons.append(f"Method matches {service_name} operations")
            
            # Check feature alignment
            features = service_info.get('features', [])
            if any(feature in method for feature in features):
                capability_score += 0.1
                reasons.append(f"Method matches {service_name} features")
            
            if capability_score > 0:
                matches.append((service_name, capability_score, '; '.join(reasons)))
        
        return matches
    
    def get_routing_confidence(self, service: str, request: Dict[str, Any]) -> float:
        """
        Get confidence score for routing a request to a specific service.
        
        Args:
            service: Target service name
            request: Request data
            
        Returns:
            Confidence score (0.0-1.0)
        """
        decision = self.identify_service_from_request(request)
        
        if decision.primary.service == service:
            return decision.primary.confidence_score
        
        # Check alternatives
        for alt in decision.alternatives:
            if alt.service == service:
                return alt.confidence_score
        
        return 0.0
    
    def get_available_services(self) -> List[Dict[str, Any]]:
        """
        Get list of available services from dynamic registry.
        
        Returns:
            List of service information dictionaries
        """
        services = []
        
        for service_name, service_info in self._service_cache.items():
            service_metadata = service_info.get('metadata')
            
            services.append({
                'name': service_name,
                'display_name': service_metadata.name if service_metadata else service_name.title(),
                'icon': service_metadata.icon if service_metadata else '🔧',
                'description': service_metadata.description if service_metadata else f'{service_name.title()} service',
                'tool_count': len(service_info.get('tools', [])),
                'operations': service_info.get('operations', []),
                'confidence_available': True
            })
        
        return services
    
    def validate_routing_decision(self, decision: ServiceRoutingDecision, available_scopes: List[str] = None) -> Dict[str, Any]:
        """
        Validate routing decision against available scopes and service availability.
        
        Args:
            decision: Routing decision to validate
            available_scopes: Currently available OAuth scopes
            
        Returns:
            Validation result with warnings and recommendations
        """
        validation = {
            'is_valid': True,
            'warnings': [],
            'recommendations': [],
            'scope_issues': []
        }
        
        service = decision.primary.service
        
        # Check if service exists in registry
        if service not in self._service_cache and service != "unknown":
            validation['is_valid'] = False
            validation['warnings'].append(f"Service '{service}' not found in registry")
            
            # Suggest alternatives
            if decision.alternatives:
                alt_names = [alt.service for alt in decision.alternatives]
                validation['recommendations'].append(f"Consider alternatives: {', '.join(alt_names)}")
        
        # Check confidence level
        if not decision.primary.is_confident:
            validation['warnings'].append(f"Low confidence routing ({decision.primary.confidence_score:.2f})")
            
            if decision.fallback_available:
                validation['recommendations'].append("Fallback options available")
        
        # Validate scopes if provided
        if available_scopes and service in self._service_cache:
            service_info = self._service_cache[service]
            required_scopes = set(service_info.get('required_scopes', []))
            available_scopes_set = set(available_scopes)
            
            missing_scopes = required_scopes - available_scopes_set
            if missing_scopes:
                validation['scope_issues'] = list(missing_scopes)
                validation['warnings'].append(f"Missing {len(missing_scopes)} required scopes")
        
        return validation
    
    def get_routing_analytics(self) -> Dict[str, Any]:
        """
        Get analytics about routing performance and service usage.
        
        Returns:
            Analytics data
        """
        return {
            'total_services': len(self._service_cache),
            'total_tools': len(self._tool_service_cache),
            'service_distribution': {
                name: len(info.get('tools', []))
                for name, info in self._service_cache.items()
            },
            'routing_strategies': [
                'Direct tool mapping',
                'Pattern matching',
                'Parameter analysis',
                'Capability matching'
            ],
            'confidence_thresholds': {
                'high_confidence': 0.8,
                'low_confidence': 0.5
            }
        }
    
    def refresh_service_registry(self):
        """Refresh the service registry from current tool metadata"""
        self.logger.info("Refreshing service registry")
        self._initialize_service_registry()


def create_service_router(mcp_server: FastMCP) -> ServiceRouter:
    """
    Factory function to create service router instance.
    
    Args:
        mcp_server: FastMCP server instance
        
    Returns:
        Configured service router
    """
    return ServiceRouter(mcp_server)