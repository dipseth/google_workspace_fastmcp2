"""
Common type definitions for MCP tools.

This module provides reusable type annotations for consistent parameter definitions
across all MCP tools, particularly for authentication-related parameters that support
auto-injection by middleware.

IMPORTANT: The AuthMiddleware in auth/middleware.py specifically looks for the 
'user_google_email' parameter name and auto-injects it when the value is None.
This custom type ensures consistency across all tools and maintains compatibility
with the middleware's auto-injection mechanism.
"""

from typing import Optional
from typing_extensions import Annotated, Literal
from pydantic import Field

# Custom annotated type for user_google_email parameter
# This type is used across all Google service MCP tools to ensure consistent
# parameter definition and enable auto-injection by authentication middleware
# 
# The middleware's _auto_inject_email_parameter method checks:
# if 'user_google_email' not in arguments or arguments.get('user_google_email') is None:
#     arguments['user_google_email'] = user_email
#
# So this type with default=None ensures auto-injection works correctly
UserGoogleEmail = Annotated[
    Optional[str], 
    Field(
        default=None,
        description="The user's Google email address for Gmail access. If None, uses the current authenticated user from FastMCP context (auto-injected by middleware)."
    )
]

# You can also create variations for different services if needed
UserGoogleEmailDrive = Annotated[
    Optional[str],
    Field(
        default=None,
        description="The user's Google email address for Drive access. If None, uses the current authenticated user from FastMCP context (auto-injected by middleware)."
    )
]

UserGoogleEmailCalendar = Annotated[
    Optional[str],
    Field(
        default=None,
        description="The user's Google email address for Calendar access. If None, uses the current authenticated user from FastMCP context (auto-injected by middleware)."
    )
]

UserGoogleEmailSheets = Annotated[
    Optional[str],
    Field(
        default=None,
        description="The user's Google email address for Sheets access. If None, uses the current authenticated user from FastMCP context (auto-injected by middleware)."
    )
]

UserGoogleEmailForms = Annotated[
    Optional[str],
    Field(
        default=None,
        description="The user's Google email address for Forms access. If None, uses the current authenticated user from FastMCP context (auto-injected by middleware)."
    )
]

UserGoogleEmailSlides = Annotated[
    Optional[str],
    Field(
        default=None,
        description="The user's Google email address for Slides access. If None, uses the current authenticated user from FastMCP context (auto-injected by middleware)."
    )
]

UserGoogleEmailChat = Annotated[
    Optional[str],
    Field(
        default=None,
        description="The user's Google email address for Chat access. If None, uses the current authenticated user from FastMCP context (auto-injected by middleware)."
    )
]

UserGoogleEmailPhotos = Annotated[
    Optional[str],
    Field(
        default=None,
        description="The user's Google email address for Photos access. If None, uses the current authenticated user from FastMCP context (auto-injected by middleware)."
    )
]

# Generic version for any Google service
UserGoogleEmailGeneric = Annotated[
    Optional[str],
    Field(
        default=None,
        description="The user's Google email address. If None, uses the current authenticated user from FastMCP context (auto-injected by middleware)."
    )
]

# ServiceType literal based on auth/scope_registry.py GOOGLE_API_SCOPES keys
# This provides type safety for service parameters in resource and tool functions
GoogleServiceType = Literal[
    "base",      # Base OAuth scopes
    "drive",     # Google Drive
    "gmail",     # Gmail
    "calendar",  # Google Calendar
    "docs",      # Google Docs
    "sheets",    # Google Sheets
    "chat",      # Google Chat
    "forms",     # Google Forms
    "slides",    # Google Slides
    "photos",    # Google Photos
    "admin",     # Admin Directory API
    "cloud",     # Google Cloud Platform
    "tasks",     # Google Tasks
    "youtube",   # YouTube
    "script"     # Google Apps Script
]

# Annotated service type for tool parameters
ServiceTypeAnnotated = Annotated[
    GoogleServiceType,
    Field(description="Google service type from available services in scope registry")
]

# Service name(s) for authentication - supports both single and multiple services
GoogleServiceNames = Annotated[
    str | list[str],
    Field(
        default=None,
        description="Service name(s) for authentication. Can be a single display name like 'Google Services' or a list of specific services like ['drive', 'gmail', 'calendar']. If None, defaults to all available services from scope registry."
    )
]