"""
Type definitions for Google People API tool responses.

These Pydantic BaseModel classes define the structure of data returned by People API
tools (list_people_contact_labels, get_people_contact_group_members, manage_people_contact_labels),
enabling FastMCP to automatically generate JSON schemas with rich field descriptions
for better MCP client integration.
"""

from typing import List, Optional

from pydantic import BaseModel, Field

# =============================================================================
# Contact Label/Group Types
# =============================================================================


class ContactLabelInfo(BaseModel):
    """Information about a single contact group/label."""

    resourceName: str = Field(
        ...,
        description="The resource name of the contact group (e.g., 'contactGroups/abc123')",
    )
    name: Optional[str] = Field(None, description="The name/title of the contact group")
    memberCount: int = Field(0, description="Number of members in the contact group")
    formattedMemberCount: str = Field(
        "0", description="Human-readable member count with formatting (e.g., '1,234')"
    )
    groupType: Optional[str] = Field(
        None,
        description="Type of group: 'USER_CONTACT_GROUP' (user-created), 'SYSTEM_CONTACT_GROUP' (system like 'myContacts')",
    )


class ListPeopleContactLabelsResponse(BaseModel):
    """Response structure for list_people_contact_labels tool."""

    success: bool = Field(
        True, description="Whether the operation completed successfully"
    )
    labels: List[ContactLabelInfo] = Field(
        default_factory=list,
        description="List of contact groups/labels with their metadata",
    )
    total_count: int = Field(
        0, description="Total number of contact groups/labels found"
    )
    user_email: str = Field(
        "", description="Email address of the user whose labels were listed"
    )
    error: Optional[str] = Field(None, description="Error message if operation failed")


# =============================================================================
# Contact Group Members Types
# =============================================================================


class GetPeopleContactGroupMembersResponse(BaseModel):
    """Response structure for get_people_contact_group_members tool."""

    success: bool = Field(
        True, description="Whether the operation completed successfully"
    )
    emails: List[str] = Field(
        default_factory=list,
        description="List of email addresses belonging to members of the contact group",
    )
    member_count: int = Field(
        0, description="Number of unique email addresses found in the group"
    )
    label_name: str = Field(
        "", description="Name of the contact group/label that was queried"
    )
    resourceName: str = Field("", description="Resource name/ID of the contact group")
    error: Optional[str] = Field(None, description="Error message if operation failed")


# =============================================================================
# Manage Contact Labels Types
# =============================================================================


class ManagePeopleContactLabelsResponse(BaseModel):
    """Response structure for manage_people_contact_labels tool."""

    success: bool = Field(
        ..., description="Whether the operation completed successfully"
    )
    action: str = Field(
        ..., description="Action that was performed: 'label_add' or 'label_remove'"
    )
    label_name: str = Field(
        ..., description="Name of the contact group/label that was managed"
    )
    label_resourceName: str = Field(
        "", description="Resource name/ID of the contact group"
    )
    emails_processed: int = Field(
        0, description="Total number of email addresses that were processed"
    )
    contacts_modified: int = Field(
        0, description="Number of contacts that were added to or removed from the label"
    )
    contacts_created: int = Field(
        0, description="Number of new contacts that were created (for label_add action)"
    )
    contacts_existing: int = Field(
        0, description="Number of existing contacts found (for label_add action)"
    )
    contacts_not_found: int = Field(
        0,
        description="Number of emails with no matching contacts (for label_remove action)",
    )
    failed_emails: List[str] = Field(
        default_factory=list,
        description="List of email addresses that failed to process",
    )
    batch_errors: int = Field(
        0, description="Number of batch API operations that encountered errors"
    )
    message: str = Field(
        "", description="Human-readable summary of the operation result"
    )
    error: Optional[str] = Field(None, description="Error message if operation failed")
