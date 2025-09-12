"""
MCP Tool Metadata Handler

This module provides utilities for extracting, validating, and managing MCP tool metadata,
including required scopes, service categorization, and operation validation.
"""

import logging
from typing import Dict, List, Optional, Set, Any, Union
from fastmcp import FastMCP
from auth.scope_registry import ScopeRegistry, ValidationResult

logger = logging.getLogger(__name__)


class MCPMetadataHandler:
    """Handler for MCP tool metadata operations"""
    
    def __init__(self, mcp_server: FastMCP):
        """
        Initialize metadata handler.
        
        Args:
            mcp_server: FastMCP server instance
        """
        self.mcp_server = mcp_server
        self.logger = logging.getLogger(f"{__name__}.MCPMetadataHandler")
    
    def get_registered_tools(self) -> Dict[str, Any]:
        """
        Get all registered tools from the MCP server.
        
        Returns:
            Dictionary of tool name to tool metadata
        """
        try:
            # Try multiple access patterns for FastMCP tool registry
            if hasattr(self.mcp_server, '_tool_manager') and hasattr(self.mcp_server._tool_manager, '_tools'):
                tools = self.mcp_server._tool_manager._tools
            elif hasattr(self.mcp_server, 'tools'):
                tools = {tool.name: tool for tool in self.mcp_server.tools}
            elif hasattr(self.mcp_server, '_tools'):
                tools = self.mcp_server._tools
            else:
                self.logger.warning("Could not access MCP tool registry")
                return {}
            
            self.logger.info(f"Found {len(tools)} registered tools")
            return tools
            
        except Exception as e:
            self.logger.error(f"Error accessing MCP tool registry: {e}")
            return {}
    
    def get_tool_metadata(self, tool_name: str) -> Optional[Dict[str, Any]]:
        """
        Get metadata for a specific tool.
        
        Args:
            tool_name: Name of the tool
            
        Returns:
            Tool metadata dictionary or None if not found
        """
        tools = self.get_registered_tools()
        if tool_name not in tools:
            self.logger.warning(f"Tool '{tool_name}' not found in registry")
            return None
        
        tool = tools[tool_name]
        
        # Extract metadata from different possible structures
        metadata = {}
        
        # Basic information
        metadata['name'] = getattr(tool, 'name', tool_name)
        metadata['description'] = getattr(tool, 'description', '')
        
        # Tags and annotations
        metadata['tags'] = getattr(tool, 'tags', set())
        metadata['annotations'] = getattr(tool, 'annotations', {})
        
        # Required scopes (new field)
        metadata['required_scopes'] = getattr(tool, 'required_scopes', [])
        
        # Service categorization from tags
        metadata['service_category'] = self.extract_service_from_tags(metadata['tags'])
        metadata['operation_type'] = self.extract_operation_type(metadata['tags'])
        
        return metadata
    
    def extract_service_from_tags(self, tags: Union[Set[str], List[str]]) -> Optional[str]:
        """
        Extract service name from tool tags.
        
        Args:
            tags: Tool tags
            
        Returns:
            Service name or None
        """
        if isinstance(tags, set):
            tag_list = list(tags)
        else:
            tag_list = tags
        
        # Check against known services
        known_services = ScopeRegistry.get_all_services()
        
        for tag in tag_list:
            if tag.lower() in known_services:
                return tag.lower()
        
        # Check for service patterns
        service_patterns = {
            'gmail': ['email', 'message', 'mail'],
            'drive': ['file', 'folder', 'document'],
            'calendar': ['event', 'schedule', 'appointment'],
            'chat': ['message', 'space', 'conversation'],
            'docs': ['document', 'text'],
            'sheets': ['spreadsheet', 'data'],
            'slides': ['presentation', 'slide'],
            'forms': ['form', 'survey'],
            'photos': ['photo', 'image', 'album']
        }
        
        for service, patterns in service_patterns.items():
            if any(pattern in tag.lower() for tag in tag_list for pattern in patterns):
                return service
        
        return None
    
    def extract_operation_type(self, tags: Union[Set[str], List[str]]) -> str:
        """
        Extract operation type from tool tags.
        
        Args:
            tags: Tool tags
            
        Returns:
            Operation type (read, write, delete, etc.)
        """
        if isinstance(tags, set):
            tag_list = list(tags)
        else:
            tag_list = tags
        
        # Operation type mappings
        operation_mappings = {
            'read': ['read', 'get', 'list', 'search', 'view', 'readonly'],
            'write': ['write', 'create', 'update', 'modify', 'edit', 'send', 'post'],
            'delete': ['delete', 'remove', 'clear'],
            'manage': ['manage', 'admin', 'configure'],
            'share': ['share', 'publish', 'collaborate']
        }
        
        for tag in tag_list:
            for op_type, keywords in operation_mappings.items():
                if any(keyword in tag.lower() for keyword in keywords):
                    return op_type
        
        return 'read'  # Default to read operation
    
    def get_required_scopes_for_tool(self, tool_name: str) -> List[str]:
        """
        Get required scopes for a specific tool.
        
        Args:
            tool_name: Name of the tool
            
        Returns:
            List of required scope URLs
        """
        metadata = self.get_tool_metadata(tool_name)
        if not metadata:
            return []
        
        # If tool has explicit required_scopes, use those
        if metadata.get('required_scopes'):
            return metadata['required_scopes']
        
        # Otherwise, infer from service and operation type
        service = metadata.get('service_category')
        operation = metadata.get('operation_type', 'read')
        
        if service:
            try:
                if operation == 'read':
                    return ScopeRegistry.get_service_scopes(service, 'readonly')
                elif operation in ['write', 'manage', 'share']:
                    return ScopeRegistry.get_service_scopes(service, 'full')
                else:
                    return ScopeRegistry.get_service_scopes(service, 'basic')
            except ValueError:
                self.logger.warning(f"Unknown service '{service}' for tool '{tool_name}'")
        
        return []
    
    def validate_tool_execution(self, tool_name: str, available_scopes: List[str]) -> ValidationResult:
        """
        Validate that a tool can be executed with available scopes.
        
        Args:
            tool_name: Name of the tool to validate
            available_scopes: List of currently available scope URLs
            
        Returns:
            ValidationResult with validation details
        """
        required_scopes = self.get_required_scopes_for_tool(tool_name)
        
        if not required_scopes:
            # If no specific scopes required, assume it's executable
            return ValidationResult(is_valid=True)
        
        missing_scopes = []
        for scope in required_scopes:
            if scope not in available_scopes:
                missing_scopes.append(scope)
        
        result = ValidationResult(
            is_valid=len(missing_scopes) == 0,
            missing_scopes=missing_scopes
        )
        
        if not result.is_valid:
            result.warnings.append(f"Tool '{tool_name}' requires {len(missing_scopes)} additional scopes")
        
        return result
    
    def get_tools_by_service(self, service: str) -> List[str]:
        """
        Get all tools that belong to a specific service.
        
        Args:
            service: Service name
            
        Returns:
            List of tool names
        """
        tools = self.get_registered_tools()
        service_tools = []
        
        for tool_name in tools:
            metadata = self.get_tool_metadata(tool_name)
            if metadata and metadata.get('service_category') == service:
                service_tools.append(tool_name)
        
        return service_tools
    
    def get_service_summary(self) -> Dict[str, Dict[str, Any]]:
        """
        Get summary of all services and their tools.
        
        Returns:
            Dictionary mapping service names to service info
        """
        tools = self.get_registered_tools()
        service_summary = {}
        
        for tool_name in tools:
            metadata = self.get_tool_metadata(tool_name)
            if not metadata:
                continue
            
            service = metadata.get('service_category')
            if not service:
                service = 'uncategorized'
            
            if service not in service_summary:
                service_summary[service] = {
                    'tools': [],
                    'total_tools': 0,
                    'operations': set(),
                    'metadata': ScopeRegistry.get_service_metadata(service)
                }
            
            service_summary[service]['tools'].append(tool_name)
            service_summary[service]['total_tools'] += 1
            service_summary[service]['operations'].add(metadata.get('operation_type', 'unknown'))
        
        # Convert sets to lists for JSON serialization
        for service_info in service_summary.values():
            service_info['operations'] = list(service_info['operations'])
        
        return service_summary
    
    def validate_all_tools_metadata(self) -> Dict[str, Any]:
        """
        Validate metadata for all registered tools.
        
        Returns:
            Validation report
        """
        tools = self.get_registered_tools()
        report = {
            'total_tools': len(tools),
            'tools_with_scopes': 0,
            'tools_without_scopes': 0,
            'services_detected': set(),
            'issues': []
        }
        
        for tool_name in tools:
            metadata = self.get_tool_metadata(tool_name)
            if not metadata:
                report['issues'].append(f"Could not extract metadata for tool '{tool_name}'")
                continue
            
            # Check for required_scopes
            if metadata.get('required_scopes'):
                report['tools_with_scopes'] += 1
            else:
                report['tools_without_scopes'] += 1
                report['issues'].append(f"Tool '{tool_name}' missing required_scopes")
            
            # Track detected services
            service = metadata.get('service_category')
            if service:
                report['services_detected'].add(service)
        
        report['services_detected'] = list(report['services_detected'])
        return report


def extract_tool_metadata_from_registry(mcp_server: FastMCP) -> Dict[str, Dict[str, Any]]:
    """
    Extract metadata for all tools in the MCP registry.
    
    Args:
        mcp_server: FastMCP server instance
        
    Returns:
        Dictionary mapping tool names to their metadata
    """
    handler = MCPMetadataHandler(mcp_server)
    tools = handler.get_registered_tools()
    
    tool_metadata = {}
    for tool_name in tools:
        metadata = handler.get_tool_metadata(tool_name)
        if metadata:
            tool_metadata[tool_name] = metadata
    
    return tool_metadata


def validate_tool_scopes_against_registry(mcp_server: FastMCP, available_scopes: List[str]) -> Dict[str, ValidationResult]:
    """
    Validate all tools against available scopes.
    
    Args:
        mcp_server: FastMCP server instance
        available_scopes: List of currently available scope URLs
        
    Returns:
        Dictionary mapping tool names to validation results
    """
    handler = MCPMetadataHandler(mcp_server)
    tools = handler.get_registered_tools()
    
    validation_results = {}
    for tool_name in tools:
        result = handler.validate_tool_execution(tool_name, available_scopes)
        validation_results[tool_name] = result
    
    return validation_results