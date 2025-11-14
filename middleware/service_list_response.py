"""
Pydantic BaseModels for TagBasedResourceMiddleware outputs.

This defines the structures of the JSON responses returned by the various handler methods
in TagBasedResourceMiddleware.
"""

from typing import Any, Optional, Dict
from datetime import datetime
from pydantic import BaseModel, Field


class ServiceListResponse(BaseModel):
    """
    Pydantic BaseModel for the output of TagBasedResourceMiddleware._handle_list_items.
    
    This structure is returned when handling service://{service}/{list_type} URIs,
    which call the appropriate list tools (e.g., list_calendars, list_events, etc.)
    and wrap the results in a consistent format.
    
    Example usage:
        # For service://calendar/calendars
        {
            "result": CalendarListResponse(...),  # The actual tool response
            "service": "calendar",
            "list_type": "calendars", 
            "tool_called": "list_calendars",
            "user_email": "user@example.com",
            "generated_at": "2024-01-15T10:30:00.000Z"
        }
    """
    
    result: Any = Field(
        description="The actual result from the called tool. This can be any serializable data structure such as structured responses (CalendarListResponse, EventListResponse, etc.), dictionaries, lists, or primitive values depending on the tool's output."
    )
    
    service: str = Field(
        description="The service name that was called (e.g., 'gmail', 'calendar', 'drive')"
    )
    
    list_type: str = Field(
        description="The list type name that was requested (e.g., 'calendars', 'events', 'filters', 'labels')"
    )
    
    tool_called: str = Field(
        description="The name of the tool that was actually called (e.g., 'list_calendars', 'list_events', 'list_gmail_filters')"
    )
    
    user_email: str = Field(
        description="The user's Google email address that was auto-injected for authentication"
    )
    
    generated_at: str = Field(
        description="ISO timestamp of when the response was generated"
    )

    class Config:
        """Pydantic configuration."""
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
        
    @classmethod
    def from_middleware_data(
        cls,
        result: Any,
        service: str,
        list_type: str,
        tool_called: str,
        user_email: str,
        generated_at: Optional[str] = None
    ) -> "ServiceListResponse":
        """
        Convenience method to create ServiceListResponse from middleware data.
        
        Args:
            result: The serialized result from the tool
            service: Service name 
            list_type: List type name
            tool_called: Tool name that was called
            user_email: User's email address
            generated_at: Optional timestamp (defaults to current time)
            
        Returns:
            ServiceListResponse instance
        """
        if generated_at is None:
            generated_at = datetime.now().isoformat()
            
        return cls(
            result=result,
            service=service,
            list_type=list_type,
            tool_called=tool_called,
            user_email=user_email,
            generated_at=generated_at
        )


class ServiceMetadata(BaseModel):
    """Metadata for a Google service."""
    display_name: str = Field(description="Human-readable service name")
    icon: str = Field(description="Unicode emoji icon for the service")
    description: str = Field(description="Service description")


class ServiceListsResponse(BaseModel):
    """
    Pydantic BaseModel for the output of TagBasedResourceMiddleware._handle_service_lists.
    
    This structure is returned when handling service://{service}/lists URIs,
    which return available list types for a service with metadata.
    
    Example usage:
        # For service://calendar/lists
        {
            "service": "calendar",
            "service_metadata": {
                "display_name": "Google Calendar",
                "icon": "📅",
                "description": "Time management and scheduling service"
            },
            "list_types": {
                "calendars": {...},
                "events": {...}
            },
            "total_list_types": 2,
            "generated_at": "2024-01-15T10:30:00.000Z"
        }
    """
    
    service: str = Field(description="The service name")
    service_metadata: ServiceMetadata = Field(description="Metadata about the service")
    list_types: Dict[str, Any] = Field(description="Available list types with their configuration")
    total_list_types: int = Field(description="Count of available list types")
    generated_at: str = Field(description="ISO timestamp of when the response was generated")

    @classmethod
    def from_middleware_data(
        cls,
        service: str,
        service_metadata: Dict[str, str],
        list_types: Dict[str, Any],
        generated_at: Optional[str] = None
    ) -> "ServiceListsResponse":
        """
        Convenience method to create ServiceListsResponse from middleware data.
        
        Args:
            service: Service name
            service_metadata: Service metadata dict
            list_types: Available list types dict
            generated_at: Optional timestamp (defaults to current time)
            
        Returns:
            ServiceListsResponse instance
        """
        if generated_at is None:
            generated_at = datetime.now().isoformat()
            
        return cls(
            service=service,
            service_metadata=ServiceMetadata(**service_metadata),
            list_types=list_types,
            total_list_types=len(list_types),
            generated_at=generated_at
        )


class ServiceItemDetailsResponse(BaseModel):
    """
    Pydantic BaseModel for the output of TagBasedResourceMiddleware._handle_specific_item.
    
    This structure is returned when handling service://{service}/{list_type}/{item_id} URIs,
    which call the appropriate get tools to retrieve specific item details.
    
    Example usage:
        # For service://gmail/filters/filter123
        {
            "service": "gmail",
            "list_type": "filters", 
            "item_id": "filter123",
            "tool_called": "get_gmail_filter",
            "user_email": "user@example.com",
            "parameters": {"user_google_email": "user@example.com", "filter_id": "filter123"},
            "result": {...},
            "generated_at": "2024-01-15T10:30:00.000Z"
        }
    """
    
    service: str = Field(description="The service name that was called")
    list_type: str = Field(description="The list type that contains the item")
    item_id: str = Field(description="The specific item ID that was requested")
    tool_called: str = Field(description="The name of the get tool that was called")
    user_email: str = Field(description="The user's Google email address used for authentication")
    parameters: Dict[str, Any] = Field(description="Parameters passed to the get tool")
    result: Any = Field(description="The actual result from the get tool")
    generated_at: str = Field(description="ISO timestamp of when the response was generated")

    @classmethod
    def from_middleware_data(
        cls,
        service: str,
        list_type: str,
        item_id: str,
        tool_called: str,
        user_email: str,
        parameters: Dict[str, Any],
        result: Any,
        generated_at: Optional[str] = None
    ) -> "ServiceItemDetailsResponse":
        """
        Convenience method to create ServiceItemDetailsResponse from middleware data.
        
        Args:
            service: Service name
            list_type: List type name
            item_id: Item ID
            tool_called: Tool name that was called
            user_email: User's email address
            parameters: Tool parameters used
            result: Tool result
            generated_at: Optional timestamp (defaults to current time)
            
        Returns:
            ServiceItemDetailsResponse instance
        """
        if generated_at is None:
            generated_at = datetime.now().isoformat()
            
        return cls(
            service=service,
            list_type=list_type,
            item_id=item_id,
            tool_called=tool_called,
            user_email=user_email,
            parameters=parameters,
            result=result,
            generated_at=generated_at
        )


class ServiceErrorResponse(BaseModel):
    """
    Pydantic BaseModel for error responses from TagBasedResourceMiddleware.
    
    This structure is returned when errors occur during resource handling,
    providing consistent error formatting across all service:// URI operations.
    
    Example usage:
        # For invalid URI like service://gmail
        {
            "error": true,
            "message": "Service root access not implemented: service://gmail",
            "help": "Use service://gmail/lists to see available list types",
            "uri": "service://gmail",
            "generated_at": "2024-01-15T10:30:00.000Z"
        }
    """
    
    error: bool = Field(default=True, description="Always true for error responses")
    message: str = Field(description="Main error description")
    help: Optional[str] = Field(default=None, description="Optional help or suggestion message")
    uri: Optional[str] = Field(default=None, description="The URI that caused the error")
    generated_at: str = Field(description="ISO timestamp of when the error occurred")
    
    @classmethod
    def from_error(
        cls,
        message: str,
        help_message: Optional[str] = None,
        uri: Optional[str] = None,
        generated_at: Optional[str] = None
    ) -> "ServiceErrorResponse":
        """
        Convenience method to create ServiceErrorResponse from error data.
        
        Args:
            message: Main error description
            help_message: Optional help or suggestion message
            uri: Optional URI that caused the error
            generated_at: Optional timestamp (defaults to current time)
            
        Returns:
            ServiceErrorResponse instance
        """
        if generated_at is None:
            generated_at = datetime.now().isoformat()
            
        return cls(
            error=True,
            message=message,
            help=help_message,
            uri=uri,
            generated_at=generated_at
        )