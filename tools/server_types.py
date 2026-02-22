"""
Type definitions for server management tool responses.

These Pydantic BaseModel classes define the structure of data returned by server
management tools (health_check, manage_credentials, manage_tools),
enabling FastMCP to automatically generate JSON schemas with rich field descriptions
for better MCP client integration.
"""

from pydantic import BaseModel, Field
from typing_extensions import Dict, List, Literal, Optional

# =============================================================================
# Health Check Response Types
# =============================================================================


class OAuthFlowStatus(BaseModel):
    """Status information for OAuth authentication flows."""

    unified_flow_enabled: bool = Field(
        ..., description="Whether the unified OAuth flow is enabled"
    )
    legacy_flow_enabled: bool = Field(
        ..., description="Whether the legacy OAuth flow is enabled"
    )
    mode: str = Field(
        ...,
        description="Current OAuth mode: 'dual' (both flows), 'unified' (new only), or 'legacy' (old only)",
    )


class HealthCheckResponse(BaseModel):
    """Response structure for health_check tool."""

    status: str = Field(
        ...,
        description="Overall health status: 'healthy', 'degraded', or 'unhealthy'",
    )
    healthy: bool = Field(..., description="Whether the server is in a healthy state")
    serverName: str = Field(..., description="Name of the MCP server")
    serverVersion: str = Field(..., description="Version of the MCP server")
    host: str = Field(..., description="Server host address")
    port: int = Field(..., description="Server port number")
    oauthConfigured: bool = Field(
        ..., description="Whether OAuth credentials are configured"
    )
    credentialsDirectoryAccessible: bool = Field(
        ..., description="Whether the credentials directory exists and is accessible"
    )
    credentialsDirectory: str = Field(
        ..., description="Path to the credentials directory"
    )
    activeSessions: int = Field(
        ..., description="Number of currently active user sessions"
    )
    logLevel: str = Field(..., description="Current logging level")
    oauthFlowStatus: Optional[OAuthFlowStatus] = Field(
        None, description="Status of OAuth authentication flows"
    )
    oauthCallbackUrl: str = Field(
        ..., description="OAuth callback URL for authentication redirects"
    )
    error: Optional[str] = Field(
        None, description="Error message if health check failed"
    )


# =============================================================================
# Credential Management Response Types
# =============================================================================


class CredentialInfo(BaseModel):
    """Information about a user's stored credentials."""

    storageMode: str = Field(
        ...,
        description="Credential storage mode: 'FILE_PLAINTEXT', 'FILE_ENCRYPTED', 'MEMORY_ONLY', or 'MEMORY_WITH_BACKUP'",
    )
    filePath: Optional[str] = Field(
        None, description="Path to credential file (if file-based storage)"
    )
    fileExists: bool = Field(
        ..., description="Whether the credential file exists on disk"
    )
    inMemory: bool = Field(
        ..., description="Whether credentials are currently loaded in memory"
    )
    isEncrypted: bool = Field(
        ..., description="Whether the stored credentials are encrypted"
    )
    lastModified: Optional[str] = Field(
        None, description="Last modification timestamp of credential file"
    )
    fileSize: Optional[int] = Field(
        None, description="Size of credential file in bytes"
    )


class ManageCredentialsResponse(BaseModel):
    """Response structure for manage_credentials tool."""

    success: bool = Field(
        ..., description="Whether the credential management operation succeeded"
    )
    action: str = Field(
        ...,
        description="Action performed: 'status', 'migrate', 'summary', or 'delete'",
    )
    email: str = Field(
        ..., description="Email address of the user whose credentials were managed"
    )
    credentialInfo: Optional[CredentialInfo] = Field(
        None, description="Credential details (for 'status' action)"
    )
    previousStorageMode: Optional[str] = Field(
        None, description="Previous storage mode (for 'migrate' action)"
    )
    newStorageMode: Optional[str] = Field(
        None, description="New storage mode after migration (for 'migrate' action)"
    )
    message: str = Field(
        ..., description="Human-readable message describing the operation result"
    )
    error: Optional[str] = Field(None, description="Error message if operation failed")


# =============================================================================
# Tool Management Response Types
# =============================================================================


class ToolInfo(BaseModel):
    """Information about a single registered tool."""

    name: str = Field(..., description="Name of the tool")
    enabled: bool = Field(..., description="Whether the tool is currently enabled")
    isProtected: bool = Field(
        ..., description="Whether the tool is protected from being disabled"
    )
    description: Optional[str] = Field(
        None, description="Tool description if available"
    )


class SessionToolState(BaseModel):
    """Information about session-specific tool state."""

    sessionId: Optional[str] = Field(
        None, description="Session identifier (truncated for privacy)"
    )
    sessionAvailable: bool = Field(
        ..., description="Whether session context was available for the operation"
    )
    sessionDisabledTools: List[str] = Field(
        default_factory=list,
        description="Tools disabled for this session only (not affecting global state)",
    )
    sessionDisabledCount: int = Field(
        0, description="Number of tools disabled for this session"
    )


class ManageToolsResponse(BaseModel):
    """Response structure for manage_tools tool."""

    success: bool = Field(
        ..., description="Whether the tool management operation succeeded"
    )
    action: str = Field(
        ...,
        description="Action performed: 'list', 'enable', 'disable', 'disable_all_except', or 'enable_all'",
    )
    scope: str = Field(
        "global",
        description="Scope of the operation: 'global' affects all clients, 'session' affects only the current session",
    )
    totalTools: int = Field(..., description="Total number of tools in the registry")
    enabledCount: int = Field(
        ..., description="Number of currently enabled tools (global state)"
    )
    disabledCount: int = Field(
        ..., description="Number of currently disabled tools (global state)"
    )
    toolsAffected: Optional[List[str]] = Field(
        None,
        description="List of tool names that were enabled/disabled by this operation",
    )
    toolsSkipped: Optional[List[str]] = Field(
        None,
        description="List of tool names that were skipped (protected or not found)",
    )
    toolList: Optional[List[ToolInfo]] = Field(
        None, description="Full list of tools with their status (for 'list' action)"
    )
    enabledToolNames: Optional[List[str]] = Field(
        None,
        description="List of tool names currently enabled for this session. "
        "Returned after modify actions (enable/disable) to allow clients to update "
        "their tool list without requiring a separate list_tools call or notification handling.",
    )
    protectedTools: List[str] = Field(
        ..., description="List of tool names that are protected from being disabled"
    )
    sessionState: Optional[SessionToolState] = Field(
        None,
        description="Session-specific tool state (included when scope='session' or action='list')",
    )
    clientSupportsUI: Optional[bool] = Field(
        None,
        description="Whether the connected client supports the MCP Apps UI extension",
    )
    message: str = Field(..., description="Human-readable summary of the operation")
    errors: Optional[List[str]] = Field(
        None,
        description="List of error messages for individual tool operations that failed",
    )
    error: Optional[str] = Field(
        None, description="Error message if the overall operation failed"
    )


# =============================================================================
# Analytics-Based Tool Management Response Types
# =============================================================================


class ToolUsageInfo(BaseModel):
    """Usage analytics for a single tool."""

    name: str = Field(..., description="Name of the tool")
    usageCount: int = Field(..., description="Number of times the tool has been used")
    service: Optional[str] = Field(
        None,
        description="Service category the tool belongs to (e.g., 'gmail', 'drive')",
    )
    lastUsed: Optional[str] = Field(
        None, description="Timestamp of the most recent usage"
    )
    currentlyEnabled: bool = Field(
        ..., description="Whether the tool is currently enabled"
    )


class ManageToolsByAnalyticsResponse(BaseModel):
    """Response structure for manage_tools_by_analytics tool."""

    success: bool = Field(
        ..., description="Whether the analytics-based management operation succeeded"
    )
    action: str = Field(
        ...,
        description="Action performed: 'preview', 'disable', or 'enable'",
    )
    serviceFilter: Optional[str] = Field(
        None, description="Service filter that was applied (e.g., 'gmail', 'drive')"
    )
    minUsageCount: int = Field(
        ..., description="Minimum usage count threshold that was applied"
    )
    limit: int = Field(..., description="Maximum number of tools that were considered")
    toolsMatched: int = Field(
        ..., description="Number of tools that matched the filter criteria"
    )
    toolsAffected: Optional[List[str]] = Field(
        None, description="List of tool names that were enabled/disabled"
    )
    toolsSkipped: Optional[List[str]] = Field(
        None, description="List of tool names that were skipped (protected or errors)"
    )
    usageAnalytics: Optional[List[ToolUsageInfo]] = Field(
        None, description="Usage analytics for matched tools (for 'preview' action)"
    )
    message: str = Field(..., description="Human-readable summary of the operation")
    errors: Optional[List[str]] = Field(
        None,
        description="List of error messages for individual tool operations that failed",
    )
    error: Optional[str] = Field(
        None, description="Error message if the overall operation failed"
    )
