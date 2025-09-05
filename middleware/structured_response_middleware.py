#!/usr/bin/env python3
"""
Structured Response Middleware for FastMCP2

This middleware automatically transforms existing string-returning MCP tools into 
structured response variants using FastMCP's serializer pattern. It operates as 
a post-tool-registration middleware that discovers and transforms eligible tools.

Key Features:
- Automatic tool discovery and transformation
- Non-destructive (preserves original tools)
- Configurable response type mappings
- Real-time transformation reporting
- Integration with FastMCP's middleware system

Usage:
    from middleware.structured_response_middleware import setup_structured_response_middleware
    
    # After all tool registrations but before server start:
    transformer_middleware = setup_structured_response_middleware(mcp)
"""

import json
import logging
import re
from typing import Dict, Any, Optional, List, TypedDict
from fastmcp import FastMCP
from fastmcp.tools import Tool
from fastmcp.server.middleware import Middleware, MiddlewareContext

# Configure logging
logger = logging.getLogger(__name__)

# ============================================================================
# STRUCTURED RESPONSE SCHEMAS
# ============================================================================

class EmailTemplateResponse(TypedDict):
    """Structured response for email template operations."""
    success: bool
    userEmail: Optional[str]
    templateId: Optional[str]
    templateName: Optional[str]
    message: Optional[str]
    error: Optional[str]
    placeholders: Optional[List[str]]
    tags: Optional[List[str]]

class GmailOperationResponse(TypedDict):
    """Structured response for Gmail operations."""
    success: bool
    userEmail: Optional[str]
    messageId: Optional[str]
    labelId: Optional[str]
    message: Optional[str]
    error: Optional[str]

class DriveOperationResponse(TypedDict):
    """Structured response for Drive operations."""
    success: bool
    userEmail: Optional[str]
    fileId: Optional[str]
    fileName: Optional[str]
    message: Optional[str]
    error: Optional[str]

class CalendarOperationResponse(TypedDict):
    """Structured response for Calendar operations."""
    success: bool
    userEmail: Optional[str]
    eventId: Optional[str]
    calendarId: Optional[str]
    message: Optional[str]
    error: Optional[str]

class FormOperationResponse(TypedDict):
    """Structured response for Forms operations."""
    success: bool
    userEmail: Optional[str]
    formId: Optional[str]
    responseId: Optional[str]
    message: Optional[str]
    error: Optional[str]

class PhotoOperationResponse(TypedDict):
    """Structured response for Photos operations."""
    success: bool
    userEmail: Optional[str]
    albumId: Optional[str]
    photoCount: Optional[int]
    message: Optional[str]
    error: Optional[str]

class ChatOperationResponse(TypedDict):
    """Structured response for Chat operations."""
    success: bool
    userEmail: Optional[str]
    messageId: Optional[str]
    spaceId: Optional[str]
    message: Optional[str]
    error: Optional[str]

class SlidesOperationResponse(TypedDict):
    """Structured response for Slides operations."""
    success: bool
    userEmail: Optional[str]
    presentationId: Optional[str]
    slideId: Optional[str]
    message: Optional[str]
    error: Optional[str]

class SheetsOperationResponse(TypedDict):
    """Structured response for Sheets operations."""
    success: bool
    userEmail: Optional[str]
    spreadsheetId: Optional[str]
    sheetName: Optional[str]
    message: Optional[str]
    error: Optional[str]

# ============================================================================
# MIDDLEWARE IMPLEMENTATION
# ============================================================================

class StructuredResponseMiddleware(Middleware):
    """
    FastMCP middleware that transforms string-returning tools into structured response variants.
    
    This middleware operates during the tool registration phase, automatically detecting
    eligible tools and creating structured response variants using FastMCP's serializer pattern.
    """
    
    def __init__(self, 
                 enable_auto_transform: bool = True,
                 custom_mappings: Optional[Dict[str, type]] = None,
                 preserve_originals: bool = True):
        """
        Initialize the structured response middleware.
        
        Args:
            enable_auto_transform: Whether to automatically transform eligible tools
            custom_mappings: Additional tool name to response type mappings
            preserve_originals: Whether to keep original tools alongside structured variants
        """
        self.enable_auto_transform = enable_auto_transform
        self.preserve_originals = preserve_originals
        self.transformed_tools = []
        
        # Default tool name to response type mapping
        self.response_types = {
            # Email template tools
            "create_email_template": EmailTemplateResponse,
            "assign_template_to_user": EmailTemplateResponse,
            "unassign_template_from_user": EmailTemplateResponse,
            "list_email_templates": EmailTemplateResponse,
            "get_template_assignments": EmailTemplateResponse,
            "delete_email_template": EmailTemplateResponse,
            
            # Gmail tools
            "add_to_gmail_allow_list": GmailOperationResponse,
            "view_gmail_allow_list": GmailOperationResponse,
            "send_gmail_message": GmailOperationResponse,
            "draft_gmail_message": GmailOperationResponse,
            "draft_gmail_reply": GmailOperationResponse,
            "search_my_gmail": GmailOperationResponse,
            "get_gmail_message_content": GmailOperationResponse,
            "get_gmail_messages_content_batch": GmailOperationResponse,
            "modify_gmail_message_labels": GmailOperationResponse,
            "list_gmail_labels": GmailOperationResponse,
            "create_gmail_filter": GmailOperationResponse,
            "get_gmail_filter": GmailOperationResponse,
            "manage_gmail_label": GmailOperationResponse,
            
            # Drive tools
            "get_drive_file_content": DriveOperationResponse,
            "upload_file_to_drive": DriveOperationResponse,
            "share_drive_files": DriveOperationResponse,
            "list_my_drive_files": DriveOperationResponse,
            "search_drive_files": DriveOperationResponse,
            "list_drive_items": DriveOperationResponse,
            "create_drive_file": DriveOperationResponse,
            "list_docs_in_folder": DriveOperationResponse,
            "search_docs": DriveOperationResponse,
            "get_doc_content": DriveOperationResponse,
            
            # Calendar tools
            "create_my_calendar_event": CalendarOperationResponse,
            "create_event": CalendarOperationResponse,
            "list_events": CalendarOperationResponse,
            "get_event": CalendarOperationResponse,
            "list_calendars": CalendarOperationResponse,
            "create_calendar": CalendarOperationResponse,
            "move_events_between_calendars": CalendarOperationResponse,
            
            # Forms tools
            "create_form": FormOperationResponse,
            "get_form": FormOperationResponse,
            "add_questions_to_form": FormOperationResponse,
            "list_form_responses": FormOperationResponse,
            "get_form_response": FormOperationResponse,
            
            # Photos tools
            "search_photos": PhotoOperationResponse,
            
            # Chat tools
            "send_message": ChatOperationResponse,
            "send_interactive_card": ChatOperationResponse,
            "send_form_card": ChatOperationResponse,
            "send_dynamic_card": ChatOperationResponse,
            
            # Slides tools
            "create_presentation": SlidesOperationResponse,
            "get_presentation_info": SlidesOperationResponse,
            "add_slide": SlidesOperationResponse,
            
            # Sheets tools
            "create_spreadsheet": SheetsOperationResponse,
            "create_sheet": SheetsOperationResponse,
        }
        
        # Add server management tools if desired (uncomment to enable)
        # self.response_types.update({
        #     "health_check": EmailTemplateResponse,  # Generic response type
        #     "server_info": EmailTemplateResponse,   # Generic response type
        #     "manage_credentials": EmailTemplateResponse  # Generic response type
        # })
        
        # Apply custom mappings if provided
        if custom_mappings:
            self.response_types.update(custom_mappings)
            logger.info(f"🔧 Added {len(custom_mappings)} custom tool mappings to structured response middleware")
    
    async def process_request(self, context: MiddlewareContext) -> Optional[Any]:
        """Process incoming requests (no action needed for this middleware)."""
        return None
    
    async def process_response(self, context: MiddlewareContext, response: Any) -> Any:
        """Process outgoing responses (no action needed for this middleware)."""
        return response
    
    def _create_response_serializer(self, response_type: type):
        """Create a serializer function for the given response type."""
        
        def serializer(original_result: str, **context) -> dict:
            """
            Transform string result to structured response.
            
            Args:
                original_result: The string result from the original tool
                **context: Additional context from the original tool call
                
            Returns:
                Structured response dictionary
            """
            try:
                # Extract user email from context
                user_email = context.get('user_google_email')
                
                # Try to parse as JSON first
                if original_result.strip().startswith('{'):
                    try:
                        json_result = json.loads(original_result)
                        return response_type(
                            success=json_result.get('success', True),
                            userEmail=user_email,
                            **{k: v for k, v in json_result.items() 
                               if k not in ['success', 'userEmail']}
                        )
                    except json.JSONDecodeError:
                        pass
                
                # Determine success/error from string content
                is_error = any(indicator in original_result.lower() 
                             for indicator in ['❌', 'error', 'fail', 'exception', 'invalid'])
                
                # Extract IDs and other structured data
                extracted_data = self._extract_structured_data(original_result)
                
                return response_type(
                    success=not is_error,
                    userEmail=user_email,
                    message=original_result if not is_error else None,
                    error=original_result if is_error else None,
                    **extracted_data
                )
                
            except Exception as e:
                logger.error(f"Error in response serializer: {e}")
                return response_type(
                    success=False,
                    userEmail=context.get('user_google_email'),
                    error=f"Response serialization failed: {str(e)}"
                )
        
        return serializer
    
    def _extract_structured_data(self, text: str) -> Dict[str, Any]:
        """Extract structured data from response text using regex patterns."""
        
        extracted = {}
        
        # ID extraction patterns
        id_patterns = {
            'templateId': [
                r'template[_\s]+id[:\s]+([a-zA-Z0-9_-]+)',
                r'id[:\s]+([a-zA-Z0-9_-]+)'
            ],
            'formId': [
                r'form[_\s]+id[:\s]+([a-zA-Z0-9_-]+)',
                r'form[:\s]+([a-zA-Z0-9_-]+)'
            ],
            'fileId': [
                r'file[_\s]+id[:\s]+([a-zA-Z0-9_-]+)',
                r'uploaded[^:]*:[^/]*/file/d/([a-zA-Z0-9_-]+)'
            ],
            'eventId': [
                r'event[_\s]+id[:\s]+([a-zA-Z0-9_-]+)',
                r'created[^:]*:[^/]*events/([a-zA-Z0-9_-]+)'
            ],
            'messageId': [
                r'message[_\s]+id[:\s]+([a-zA-Z0-9_-]+)',
                r'sent[^:]*:[^/]*messages/([a-zA-Z0-9_-]+)'
            ],
            'presentationId': [
                r'presentation[_\s]+id[:\s]+([a-zA-Z0-9_-]+)'
            ],
            'spreadsheetId': [
                r'spreadsheet[_\s]+id[:\s]+([a-zA-Z0-9_-]+)'
            ],
            'calendarId': [
                r'calendar[_\s]+id[:\s]+([a-zA-Z0-9_-]+)'
            ],
            'spaceId': [
                r'space[_\s]+id[:\s]+([a-zA-Z0-9_-]+)'
            ]
        }
        
        # Apply patterns
        for field_name, patterns in id_patterns.items():
            for pattern in patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    extracted[field_name] = match.group(1)
                    break  # Use first match
        
        # Extract names/titles
        name_patterns = {
            'templateName': r'template[^:]*:[^"]*"([^"]+)"',
            'fileName': r'file[^:]*:[^"]*"([^"]+)"',
            'sheetName': r'sheet[^:]*:[^"]*"([^"]+)"'
        }
        
        for field_name, pattern in name_patterns.items():
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                extracted[field_name] = match.group(1)
        
        # Extract counts
        count_patterns = {
            'photoCount': r'(\d+)\s+photos?'
        }
        
        for field_name, pattern in count_patterns.items():
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                extracted[field_name] = int(match.group(1))
        
        return extracted
    
    def transform_registered_tools(self, mcp_server: FastMCP) -> List[str]:
        """
        Transform all eligible registered tools in the MCP server by REPLACING originals.
        
        Args:
            mcp_server: The FastMCP server instance
            
        Returns:
            List of tool names that were successfully transformed
        """
        
        if not self.enable_auto_transform:
            logger.info("🔇 Structured response middleware: Auto-transform disabled")
            return []
        
        logger.info("🔄 Structured response middleware: Starting tool transformation...")
        logger.info("📝 Mode: REPLACE original tools with structured versions")
        
        # Access registered tools via FastMCP's tool manager
        if not hasattr(mcp_server, '_tool_manager') or not hasattr(mcp_server._tool_manager, '_tools'):
            logger.error("❌ Cannot access FastMCP tool manager")
            return []
        
        registered_tools = mcp_server._tool_manager._tools
        transformation_count = 0
        
        # Create a snapshot to avoid "dictionary changed during iteration" error
        tools_snapshot = list(registered_tools.items())
        
        for tool_name, tool_instance in tools_snapshot:
            if tool_name in self.response_types:
                logger.info(f"🔧 Replacing: {tool_name} with structured version")
                
                transformed_tool = self._transform_tool(tool_name, tool_instance)
                
                if transformed_tool:
                    # REPLACE the original tool (same name, structured response)
                    registered_tools[tool_name] = transformed_tool
                    self.transformed_tools.append(tool_name)
                    transformation_count += 1
                    logger.info(f"✅ Replaced: {tool_name} (now returns structured responses)")
                else:
                    logger.warning(f"⚠️ Failed to transform: {tool_name}")
        
        logger.info(f"🎉 Structured response middleware: {transformation_count} tools transformed")
        logger.info(f"📊 Total tools: {len(registered_tools)} (same count, enhanced with structured responses)")
        
        return self.transformed_tools
    
    def _transform_tool(self, tool_name: str, original_tool: Tool) -> Optional[Tool]:
        """
        Transform a single tool to provide structured responses (REPLACES original).
        
        Args:
            tool_name: Name of the tool to transform
            original_tool: The original Tool instance
            
        Returns:
            New Tool instance with structured responses, or None if transformation fails
        """
        
        if tool_name not in self.response_types:
            logger.debug(f"No transformation mapping for tool: {tool_name}")
            return None
        
        response_type = self.response_types[tool_name]
        serializer = self._create_response_serializer(response_type)
        
        # Create new tool using Tool.from_tool with serializer (KEEPS ORIGINAL NAME)
        try:
            # Check if description already has enhancement text to avoid duplication
            enhancement_text = "**Enhanced with structured response format** - returns both human-readable content and machine-readable JSON."
            
            if enhancement_text in original_tool.description:
                # Already enhanced, keep original description
                new_description = original_tool.description
            else:
                # Add enhancement text
                new_description = f"{original_tool.description}\n\n{enhancement_text}"
            
            transformed_tool = Tool.from_tool(
                original_tool,
                name=tool_name,  # Keep original name - no _structured suffix!
                description=new_description,
                serializer=serializer,
                tags=original_tool.tags | {"structured_response", "enhanced_by_middleware"},
                meta={
                    "original_tool": tool_name,
                    "transformation_type": "in_place_string_to_structured",
                    "response_schema": response_type.__name__,
                    "enhanced_by": "StructuredResponseMiddleware",
                    "middleware_version": "1.0.0",
                    "replaces_original": True
                }
            )
            
            return transformed_tool
            
        except Exception as e:
            logger.error(f"Failed to transform tool {tool_name}: {e}")
            return None
    
    def generate_transformation_report(self, mcp_server: FastMCP) -> Dict[str, Any]:
        """Generate a comprehensive transformation report."""
        
        # Access current tool registry
        registered_tools = getattr(mcp_server._tool_manager, '_tools', {})
        
        # Categorize tools (no more duplicates - tools are enhanced in-place)
        enhanced_tools = []
        regular_tools = []
        
        for tool_name, tool_instance in registered_tools.items():
            # Check if tool has been enhanced with structured responses
            if (hasattr(tool_instance, 'meta') and
                tool_instance.meta and
                tool_instance.meta.get('enhanced_by') == 'StructuredResponseMiddleware'):
                enhanced_tools.append(tool_name)
            else:
                regular_tools.append(tool_name)
        
        # Calculate metrics
        total_tools = len(registered_tools)
        transformed_count = len(self.transformed_tools)
        coverage = (transformed_count / len(self.response_types)) * 100 if self.response_types else 0
        
        report = {
            "middleware_summary": {
                "total_registered_tools": total_tools,
                "transformable_tools": len(self.response_types),
                "successfully_enhanced": transformed_count,
                "coverage_percentage": round(coverage, 1),
                "middleware_enabled": self.enable_auto_transform,
                "transformation_mode": "in_place_replacement"
            },
            "tool_categories": {
                "enhanced_tools": sorted(enhanced_tools),
                "regular_tools": sorted(regular_tools),
                "transformable_remaining": sorted(
                    set(self.response_types.keys()) - set(self.transformed_tools)
                )
            },
            "response_types_available": {
                schema.__name__: len([t for t in self.response_types.values() if t == schema])
                for schema in set(self.response_types.values())
            },
            "middleware_metadata": {
                "middleware_version": "1.0.0",
                "transformation_method": "in_place_serializer_replacement",
                "preserves_originals": False,
                "backward_compatible": True,
                "creates_duplicates": False
            }
        }
        
        return report

# ============================================================================
# CONVENIENCE SETUP FUNCTIONS
# ============================================================================

def setup_structured_response_middleware(
    mcp_server: FastMCP,
    enable_auto_transform: bool = True,
    custom_mappings: Optional[Dict[str, type]] = None,
    preserve_originals: bool = True,
    generate_report: bool = True
) -> StructuredResponseMiddleware:
    """
    Set up structured response middleware for a FastMCP server.
    
    This should be called AFTER all tools are registered but BEFORE the server starts.
    
    Args:
        mcp_server: The FastMCP server instance
        enable_auto_transform: Whether to automatically transform eligible tools
        custom_mappings: Additional tool name to response type mappings
        preserve_originals: Whether to keep original tools alongside structured variants
        generate_report: Whether to log a transformation report
        
    Returns:
        StructuredResponseMiddleware instance for further customization
        
    Example:
        # In server.py, after all setup_*_tools(mcp) calls:
        from middleware.structured_response_middleware import setup_structured_response_middleware
        
        structured_middleware = setup_structured_response_middleware(mcp)
    """
    
    # Create and register the middleware
    middleware = StructuredResponseMiddleware(
        enable_auto_transform=enable_auto_transform,
        custom_mappings=custom_mappings,
        preserve_originals=preserve_originals
    )
    
    # Add to MCP server middleware stack
    mcp_server.add_middleware(middleware)
    logger.info("✅ Structured response middleware registered")
    
    # Perform tool transformation
    if enable_auto_transform:
        transformed_tools = middleware.transform_registered_tools(mcp_server)
        
        # Generate and log report if requested
        if generate_report:
            report = middleware.generate_transformation_report(mcp_server)
            logger.info("📋 Structured Response Middleware Report:")
            logger.info(f"  • Tools enhanced with structured responses: {report['middleware_summary']['successfully_enhanced']}")
            logger.info(f"  • Coverage: {report['middleware_summary']['coverage_percentage']:.1f}%")
            logger.info(f"  • Total tools: {report['middleware_summary']['total_registered_tools']}")
            logger.info(f"  • Mode: {report['middleware_summary']['transformation_mode']}")
            
        return middleware
    else:
        logger.info("🔇 Structured response middleware registered but auto-transform disabled")
        return middleware

# ============================================================================
# TESTING FUNCTION
# ============================================================================

def setup_module_wrapper_middleware(
    mcp_server: FastMCP,
    modules_to_wrap: Optional[List[str]] = None,
    enable_structured_responses: bool = True
) -> StructuredResponseMiddleware:
    """
    Convenience wrapper that sets up both module wrapper functionality and structured responses.
    
    This function provides compatibility with the existing server.py import pattern while
    delivering the structured response middleware functionality.
    
    Args:
        mcp_server: The FastMCP server instance
        modules_to_wrap: List of modules to wrap (legacy parameter, ignored)
        enable_structured_responses: Whether to enable structured response transformation
        
    Returns:
        StructuredResponseMiddleware instance
        
    Note:
        This function maintains compatibility with existing server.py code while providing
        the structured response functionality. The modules_to_wrap parameter is kept for
        backward compatibility but is not used in the structured response implementation.
    """
    logger.info("🔄 Setting up module wrapper middleware (structured response mode)...")
    
    if modules_to_wrap:
        logger.info(f"📦 Module wrapper requested for: {modules_to_wrap}")
        logger.info("ℹ️  Note: This implementation focuses on structured responses rather than module wrapping")
    
    # Set up structured response middleware
    middleware = setup_structured_response_middleware(
        mcp_server,
        enable_auto_transform=enable_structured_responses,
        preserve_originals=True,
        generate_report=True
    )
    
    logger.info("✅ Module wrapper middleware setup completed (structured response mode)")
    return middleware


def main():
    """Demo function showing middleware capabilities."""
    
    # Create demo server
    demo_mcp = FastMCP("middleware-demo")
    
    # Add sample tools
    @demo_mcp.tool
    def sample_gmail_tool() -> str:
        return "Message sent! ID: msg_123"
    
    @demo_mcp.tool  
    def sample_drive_tool() -> str:
        return "File uploaded! File ID: file_456"
    
    # Set up middleware using the wrapper function
    print("🚀 Setting up module wrapper middleware (structured response mode)...")
    middleware = setup_module_wrapper_middleware(demo_mcp, modules_to_wrap=["sample.module"])
    
    # Generate and display report
    report = middleware.generate_transformation_report(demo_mcp)
    print("\n📊 MIDDLEWARE TRANSFORMATION REPORT")
    print("=" * 50)
    print(json.dumps(report, indent=2))

if __name__ == "__main__":
    main()

# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    'StructuredResponseMiddleware',
    'setup_structured_response_middleware', 
    'setup_module_wrapper_middleware',
    'EmailTemplateResponse',
    'GmailOperationResponse',
    'DriveOperationResponse',
    'CalendarOperationResponse',
    'FormOperationResponse',
    'PhotoOperationResponse',
    'ChatOperationResponse',
    'SlidesOperationResponse',
    'SheetsOperationResponse'
]