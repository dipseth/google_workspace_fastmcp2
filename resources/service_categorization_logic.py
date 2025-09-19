"""
Service Categorization Logic

This module provides logic for categorizing tools and discovering services
based on MCP tool tags and metadata.
"""

import logging
from typing import Dict, List, Set, Optional, Any
from fastmcp import FastMCP
from auth.scope_registry import ScopeRegistry
from middleware.mcp_metadata_handler import MCPMetadataHandler

from config.enhanced_logging import setup_logger
logger = setup_logger()


class ServiceCategorizer:
    """Categorizes tools and discovers services from MCP metadata"""
    
    def __init__(self, mcp_server: FastMCP):
        """
        Initialize service categorizer.
        
        Args:
            mcp_server: FastMCP server instance
        """
        self.mcp_server = mcp_server
        self.metadata_handler = MCPMetadataHandler(mcp_server)
        self.logger = logging.getLogger(f"{__name__}.ServiceCategorizer")
    
    def discover_services_from_tools(self) -> Dict[str, Any]:
        """
        Discover available services from registered tools.
        
        Returns:
            Dictionary of discovered services with metadata
        """
        tools = self.metadata_handler.get_registered_tools()
        discovered_services = {}
        
        for tool_name in tools:
            metadata = self.metadata_handler.get_tool_metadata(tool_name)
            if not metadata:
                continue
            
            service = metadata.get('service_category')
            if not service:
                continue
            
            if service not in discovered_services:
                service_metadata = ScopeRegistry.get_service_metadata(service)
                discovered_services[service] = {
                    'name': service,
                    'tools': [],
                    'operations': set(),
                    'required_scopes': set(),
                    'metadata': service_metadata
                }
            
            # Add tool info
            discovered_services[service]['tools'].append({
                'name': tool_name,
                'description': metadata.get('description', ''),
                'operation_type': metadata.get('operation_type', 'unknown'),
                'required_scopes': metadata.get('required_scopes', [])
            })
            
            # Track operations and scopes
            discovered_services[service]['operations'].add(metadata.get('operation_type', 'unknown'))
            for scope in metadata.get('required_scopes', []):
                discovered_services[service]['required_scopes'].add(scope)
        
        # Convert sets to lists for JSON serialization
        for service_info in discovered_services.values():
            service_info['operations'] = list(service_info['operations'])
            service_info['required_scopes'] = list(service_info['required_scopes'])
        
        self.logger.info(f"Discovered {len(discovered_services)} services from {len(tools)} tools")
        return discovered_services
    
    def categorize_tools_by_tags(self) -> Dict[str, List[str]]:
        """
        Categorize tools by their tags.
        
        Returns:
            Dictionary mapping categories to tool lists
        """
        tools = self.metadata_handler.get_registered_tools()
        categorized = {}
        
        for tool_name in tools:
            metadata = self.metadata_handler.get_tool_metadata(tool_name)
            if not metadata:
                continue
            
            tags = metadata.get('tags', set())
            if isinstance(tags, set):
                tags = list(tags)
            
            for tag in tags:
                if tag not in categorized:
                    categorized[tag] = []
                categorized[tag].append(tool_name)
        
        return categorized
    
    def get_tools_requiring_scopes(self, required_scopes: List[str]) -> List[Dict[str, Any]]:
        """
        Get tools that require specific scopes.
        
        Args:
            required_scopes: List of scope URLs to check
            
        Returns:
            List of matching tools with metadata
        """
        tools = self.metadata_handler.get_registered_tools()
        matching_tools = []
        
        for tool_name in tools:
            tool_scopes = self.metadata_handler.get_required_scopes_for_tool(tool_name)
            
            # Check if tool requires any of the specified scopes
            if any(scope in tool_scopes for scope in required_scopes):
                metadata = self.metadata_handler.get_tool_metadata(tool_name)
                matching_tools.append({
                    'name': tool_name,
                    'required_scopes': tool_scopes,
                    'metadata': metadata
                })
        
        return matching_tools
    
    def get_service_capabilities(self, service: str) -> Dict[str, Any]:
        """
        Get capabilities for a specific service based on its tools.
        
        Args:
            service: Service name
            
        Returns:
            Service capabilities information
        """
        tools = self.metadata_handler.get_tools_by_service(service)
        service_metadata = ScopeRegistry.get_service_metadata(service)
        
        capabilities = {
            'service': service,
            'total_tools': len(tools),
            'operations': set(),
            'features': set(),
            'scopes_used': set(),
            'metadata': service_metadata
        }
        
        for tool_name in tools:
            metadata = self.metadata_handler.get_tool_metadata(tool_name)
            if not metadata:
                continue
            
            # Extract capabilities from metadata
            capabilities['operations'].add(metadata.get('operation_type', 'unknown'))
            
            # Extract features from tags
            tags = metadata.get('tags', set())
            if isinstance(tags, set):
                tags = list(tags)
            
            for tag in tags:
                if tag != service:  # Don't include the service name itself
                    capabilities['features'].add(tag)
            
            # Track scopes
            for scope in metadata.get('required_scopes', []):
                capabilities['scopes_used'].add(scope)
        
        # Convert sets to lists
        capabilities['operations'] = list(capabilities['operations'])
        capabilities['features'] = list(capabilities['features'])
        capabilities['scopes_used'] = list(capabilities['scopes_used'])
        
        return capabilities
    
    def generate_service_map(self) -> Dict[str, Dict[str, Any]]:
        """
        Generate a comprehensive service map with all discovered services.
        
        Returns:
            Complete service map with metadata
        """
        discovered_services = self.discover_services_from_tools()
        service_map = {}
        
        for service_name, service_info in discovered_services.items():
            capabilities = self.get_service_capabilities(service_name)
            
            service_map[service_name] = {
                'name': service_name,
                'display_name': capabilities['metadata'].name if capabilities['metadata'] else service_name.title(),
                'icon': capabilities['metadata'].icon if capabilities['metadata'] else '🔧',
                'description': capabilities['metadata'].description if capabilities['metadata'] else f'{service_name.title()} service',
                'version': capabilities['metadata'].version if capabilities['metadata'] else 'v1',
                'total_tools': capabilities['total_tools'],
                'operations': capabilities['operations'],
                'features': capabilities['features'],
                'scopes_used': capabilities['scopes_used'],
                'tools': service_info['tools'],
                'api_endpoint': capabilities['metadata'].api_endpoint if capabilities['metadata'] else None,
                'documentation_url': capabilities['metadata'].documentation_url if capabilities['metadata'] else None
            }
        
        return service_map


def get_dynamic_service_list(mcp_server: FastMCP) -> List[Dict[str, Any]]:
    """
    Get dynamic list of available services based on registered tools.
    
    Args:
        mcp_server: FastMCP server instance
        
    Returns:
        List of available services with metadata
    """
    categorizer = ServiceCategorizer(mcp_server)
    service_map = categorizer.generate_service_map()
    
    return [
        {
            'name': service_name,
            'display_name': service_info['display_name'],
            'icon': service_info['icon'],
            'description': service_info['description'],
            'tool_count': service_info['total_tools'],
            'operations': service_info['operations'],
            'features': service_info['features'][:5]  # Limit features for display
        }
        for service_name, service_info in service_map.items()
    ]


def categorize_tool_by_tags(tags: List[str]) -> Dict[str, Any]:
    """
    Categorize a single tool based on its tags.
    
    Args:
        tags: List of tool tags
        
    Returns:
        Categorization information
    """
    service = None
    operation = 'read'  # Default
    features = []
    
    # Known services
    known_services = ScopeRegistry.get_all_services()
    
    for tag in tags:
        if tag.lower() in known_services:
            service = tag.lower()
        else:
            features.append(tag)
    
    # Determine operation type
    operation_keywords = {
        'read': ['read', 'get', 'list', 'search', 'view'],
        'write': ['write', 'create', 'send', 'post', 'update'],
        'delete': ['delete', 'remove', 'clear'],
        'manage': ['manage', 'admin', 'configure']
    }
    
    for tag in tags:
        for op_type, keywords in operation_keywords.items():
            if any(keyword in tag.lower() for keyword in keywords):
                operation = op_type
                break
    
    return {
        'service': service,
        'operation_type': operation,
        'features': features,
        'inferred': service is None  # Whether service was inferred vs explicit
    }


def validate_service_tool_coverage(mcp_server: FastMCP) -> Dict[str, Any]:
    """
    Validate that all known services have tool coverage.
    
    Args:
        mcp_server: FastMCP server instance
        
    Returns:
        Coverage validation report
    """
    categorizer = ServiceCategorizer(mcp_server)
    discovered_services = categorizer.discover_services_from_tools()
    known_services = ScopeRegistry.get_all_services()
    
    report = {
        'total_known_services': len(known_services),
        'services_with_tools': len(discovered_services),
        'coverage_percentage': (len(discovered_services) / len(known_services)) * 100,
        'services_without_tools': [],
        'tool_distribution': {}
    }
    
    # Find services without tools
    for service in known_services:
        if service not in discovered_services:
            report['services_without_tools'].append(service)
    
    # Tool distribution
    for service, service_info in discovered_services.items():
        report['tool_distribution'][service] = service_info['total_tools']
    
    return report