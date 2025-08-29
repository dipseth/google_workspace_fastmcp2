"""
MCP tools for managing email templates in FastMCP2.

This module provides tools for:
- Creating and managing email templates
- Assigning templates to users
- Listing and searching templates
- Deleting templates and mappings
"""

import json
import logging
from typing import Optional, Dict, Any, List
from fastmcp import Context

from .templates import EmailTemplateManager, EmailTemplate, TemplateMapping

logger = logging.getLogger(__name__)

# Initialize template manager
template_manager = EmailTemplateManager()


async def create_email_template(
    template_name: str,
    html_content: str,
    description: Optional[str] = None,
    tags: Optional[List[str]] = None
) -> str:
    """
    Creates a new email template with HTML content and placeholders.
    
    Args:
        template_name: Name of the template (e.g., "Professional Newsletter")
        html_content: HTML content with placeholders like {{email_body}}, {{recipient_name}}
        description: Optional description of the template's purpose
        tags: Optional list of tags for categorization
        
    Returns:
        str: Success message with template ID
        
    Examples:
        # Create a simple template
        create_email_template(
            "Welcome Email",
            "<h1>Welcome {{recipient_name}}!</h1><div>{{email_body}}</div>",
            description="Welcome email for new users"
        )
        
        # Create a newsletter template with more placeholders
        create_email_template(
            "Company Newsletter",
            '''<html>
                <body style="font-family: Arial, sans-serif;">
                    <h1>{{subject}}</h1>
                    <p>Dear {{recipient_name}},</p>
                    <div>{{email_body}}</div>
                    <footer>
                        <p>Best regards,<br>{{sender_name}}</p>
                        <p>Sent on {{date}}</p>
                    </footer>
                </body>
            </html>''',
            description="Monthly company newsletter template",
            tags=["newsletter", "monthly", "company"]
        )
    """
    try:
        # Create the template using the manager
        template_id = await template_manager.create_template(
            name=template_name,
            html_content=html_content,
            description=description or "",
            tags=tags or [],
            metadata={}
        )
        
        # Get the created template to confirm
        template = await template_manager.get_template(template_id)
        
        if template:
            placeholders_info = ""
            if template.placeholders:
                placeholders_info = f" with placeholders: {', '.join(template.placeholders)}"
            
            return json.dumps({
                "success": True,
                "template_id": template_id,
                "message": f"✅ Email template '{template_name}' created successfully{placeholders_info}",
                "template": {
                    "id": template.id,
                    "name": template.name,
                    "description": template.description,
                    "placeholders": template.placeholders,
                    "tags": template.tags
                }
            }, indent=2)
        else:
            return json.dumps({
                "success": False,
                "message": "Template creation failed - could not retrieve created template"
            })
            
    except Exception as e:
        logger.error(f"Error creating email template: {e}")
        return json.dumps({
            "success": False,
            "message": f"❌ Failed to create email template: {str(e)}"
        })


async def assign_template_to_user(
    template_id: str,
    user_email: str,
    priority: int = 100
) -> str:
    """
    Assigns an email template to a specific user email address.
    When sending emails to this user, the assigned template will be automatically applied.
    
    Args:
        template_id: ID of the template to assign
        user_email: Email address to assign the template to
        priority: Priority for template selection (higher = preferred)
        
    Returns:
        str: Success message with mapping details
        
    Examples:
        # Assign a welcome template to a new user
        assign_template_to_user(
            "template_abc123",
            "newuser@example.com"
        )
        
        # Assign a VIP template with high priority
        assign_template_to_user(
            "template_vip456",
            "ceo@company.com",
            priority=200
        )
    """
    try:
        # Verify template exists
        template = await template_manager.get_template(template_id)
        if not template:
            return json.dumps({
                "success": False,
                "message": f"❌ Template with ID '{template_id}' not found"
            })
        
        # Map the template to the user
        mapping_id = await template_manager.map_template_to_user(
            template_id=template_id,
            user_email=user_email,
            priority=priority
        )
        
        return json.dumps({
            "success": True,
            "mapping_id": mapping_id,
            "message": f"✅ Template '{template.name}' assigned to {user_email}",
            "details": {
                "template_id": template_id,
                "template_name": template.name,
                "user_email": user_email,
                "priority": priority
            }
        }, indent=2)
        
    except Exception as e:
        logger.error(f"Error assigning template to user: {e}")
        return json.dumps({
            "success": False,
            "message": f"❌ Failed to assign template: {str(e)}"
        })


async def list_email_templates(
    search_query: Optional[str] = None,
    limit: int = 20
) -> str:
    """
    Lists available email templates with optional search filtering.
    
    Args:
        search_query: Optional search query to filter templates
        limit: Maximum number of templates to return
        
    Returns:
        str: JSON list of templates with details
        
    Examples:
        # List all templates
        list_email_templates()
        
        # Search for newsletter templates
        list_email_templates(search_query="newsletter")
        
        # Search for templates with specific tags
        list_email_templates(search_query="monthly company")
    """
    try:
        if search_query:
            # Search for templates
            templates = await template_manager.search_templates(
                query=search_query,
                limit=limit
            )
        else:
            # List all templates (using empty query)
            templates = await template_manager.search_templates(
                query="",
                limit=limit
            )
        
        # Format templates for output
        template_list = []
        for template in templates:
            # Get user mappings for this template
            mappings = await template_manager.get_template_mappings(template.id)
            
            template_info = {
                "id": template.id,
                "name": template.name,
                "description": template.description,
                "placeholders": template.placeholders,
                "tags": template.tags,
                "created_at": template.created_at,
                "assigned_users": [m.user_email for m in mappings] if mappings else []
            }
            template_list.append(template_info)
        
        return json.dumps({
            "success": True,
            "count": len(template_list),
            "templates": template_list
        }, indent=2)
        
    except Exception as e:
        logger.error(f"Error listing email templates: {e}")
        return json.dumps({
            "success": False,
            "message": f"❌ Failed to list templates: {str(e)}"
        })


async def remove_template_assignment(
    user_email: str,
    template_id: Optional[str] = None
) -> str:
    """
    Removes template assignment from a user.
    If template_id is provided, removes only that specific assignment.
    If not provided, removes all template assignments for the user.
    
    Args:
        user_email: Email address to remove template assignment from
        template_id: Optional specific template ID to remove
        
    Returns:
        str: Success message with details
        
    Examples:
        # Remove all template assignments from a user
        remove_template_assignment("user@example.com")
        
        # Remove specific template assignment
        remove_template_assignment("user@example.com", "template_abc123")
    """
    try:
        if template_id:
            # Remove specific template assignment
            success = await template_manager.unmap_template_from_user(
                template_id=template_id,
                user_email=user_email
            )
            
            if success:
                return json.dumps({
                    "success": True,
                    "message": f"✅ Template assignment removed from {user_email}"
                })
            else:
                return json.dumps({
                    "success": False,
                    "message": f"No template assignment found for {user_email}"
                })
        else:
            # Remove all template assignments for the user
            removed_count = 0
            # Get all templates and check their mappings
            templates = await template_manager.search_templates("", limit=100)
            
            for template in templates:
                success = await template_manager.unmap_template_from_user(
                    template_id=template.id,
                    user_email=user_email
                )
                if success:
                    removed_count += 1
            
            if removed_count > 0:
                return json.dumps({
                    "success": True,
                    "message": f"✅ Removed {removed_count} template assignment(s) from {user_email}"
                })
            else:
                return json.dumps({
                    "success": False,
                    "message": f"No template assignments found for {user_email}"
                })
                
    except Exception as e:
        logger.error(f"Error removing template assignment: {e}")
        return json.dumps({
            "success": False,
            "message": f"❌ Failed to remove template assignment: {str(e)}"
        })


async def delete_email_template(
    template_id: str,
    confirm: bool = False
) -> str:
    """
    Deletes an email template and all its user assignments.
    
    Args:
        template_id: ID of the template to delete
        confirm: Safety confirmation flag (must be True to delete)
        
    Returns:
        str: Success message with details
        
    Examples:
        # Attempt deletion without confirmation (will fail)
        delete_email_template("template_abc123")
        
        # Confirm and delete template
        delete_email_template("template_abc123", confirm=True)
    """
    try:
        if not confirm:
            return json.dumps({
                "success": False,
                "message": "⚠️ Deletion requires confirmation. Set confirm=True to proceed.",
                "warning": "This will delete the template and all user assignments permanently."
            })
        
        # Get template details before deletion
        template = await template_manager.get_template(template_id)
        if not template:
            return json.dumps({
                "success": False,
                "message": f"❌ Template with ID '{template_id}' not found"
            })
        
        # Get mappings before deletion
        mappings = await template_manager.get_template_mappings(template_id)
        affected_users = [m.user_email for m in mappings] if mappings else []
        
        # Delete the template
        success = await template_manager.delete_template(template_id)
        
        if success:
            result = {
                "success": True,
                "message": f"✅ Template '{template.name}' deleted successfully",
                "deleted_template": {
                    "id": template_id,
                    "name": template.name
                }
            }
            
            if affected_users:
                result["affected_users"] = affected_users
                result["message"] += f" ({len(affected_users)} user assignments removed)"
            
            return json.dumps(result, indent=2)
        else:
            return json.dumps({
                "success": False,
                "message": "Failed to delete template"
            })
            
    except Exception as e:
        logger.error(f"Error deleting email template: {e}")
        return json.dumps({
            "success": False,
            "message": f"❌ Failed to delete template: {str(e)}"
        })


async def preview_email_template(
    template_id: str,
    sample_data: Optional[Dict[str, str]] = None
) -> str:
    """
    Preview an email template with sample data to see how it will look.
    
    Args:
        template_id: ID of the template to preview
        sample_data: Optional dictionary of placeholder values
        
    Returns:
        str: JSON with template preview including rendered HTML
        
    Examples:
        # Preview with default sample data
        preview_email_template("template_abc123")
        
        # Preview with custom sample data
        preview_email_template(
            "template_abc123",
            sample_data={
                "recipient_name": "John Doe",
                "email_body": "This is the main content of the email.",
                "sender_name": "Jane Smith",
                "subject": "Important Update",
                "date": "January 1, 2025"
            }
        )
    """
    try:
        # Get the template
        template = await template_manager.get_template(template_id)
        if not template:
            return json.dumps({
                "success": False,
                "message": f"❌ Template with ID '{template_id}' not found"
            })
        
        # Prepare sample data with defaults
        default_sample_data = {
            "recipient_email": "recipient@example.com",
            "recipient_name": "Sample Recipient",
            "sender_email": "sender@example.com",
            "sender_name": "Sample Sender",
            "email_body": "<p>This is the main content of your email. It can contain <b>HTML formatting</b> and will be inserted into your template.</p>",
            "content": "This is the plain text version of the email content.",
            "subject": "Sample Email Subject",
            "date": "January 1, 2025"
        }
        
        # Merge with provided sample data
        if sample_data:
            default_sample_data.update(sample_data)
        
        # Apply the template with sample data
        rendered_html = await template_manager.apply_template(
            template_id=template_id,
            placeholders=default_sample_data
        )
        
        # Find which placeholders were actually used
        used_placeholders = []
        for placeholder in template.placeholders:
            if placeholder in default_sample_data:
                used_placeholders.append({
                    "placeholder": f"{{{{{placeholder}}}}}",
                    "value": default_sample_data[placeholder]
                })
        
        return json.dumps({
            "success": True,
            "template": {
                "id": template.id,
                "name": template.name,
                "description": template.description,
                "placeholders": template.placeholders
            },
            "preview": {
                "rendered_html": rendered_html,
                "sample_data_used": used_placeholders
            },
            "note": "This is a preview with sample data. Actual values will be inserted when sending emails."
        }, indent=2)
        
    except Exception as e:
        logger.error(f"Error previewing email template: {e}")
        return json.dumps({
            "success": False,
            "message": f"❌ Failed to preview template: {str(e)}"
        })


async def get_user_template_assignment(
    user_email: str
) -> str:
    """
    Gets the current template assignment for a specific user email.
    
    Args:
        user_email: Email address to check template assignment
        
    Returns:
        str: JSON with template assignment details
        
    Examples:
        # Check template assignment for a user
        get_user_template_assignment("user@example.com")
    """
    try:
        # Get template for the user
        template = await template_manager.get_template_for_user(user_email)
        
        if template:
            return json.dumps({
                "success": True,
                "user_email": user_email,
                "assigned_template": {
                    "id": template.id,
                    "name": template.name,
                    "description": template.description,
                    "placeholders": template.placeholders,
                    "tags": template.tags
                }
            }, indent=2)
        else:
            # Check if there's a domain-level or global template
            domain = user_email.split('@')[1] if '@' in user_email else None
            domain_template = None
            global_template = None
            
            if domain:
                domain_template = await template_manager.get_template_for_user(f"*@{domain}")
            
            global_template = await template_manager.get_template_for_user("*")
            
            result = {
                "success": True,
                "user_email": user_email,
                "assigned_template": None,
                "message": f"No specific template assigned to {user_email}"
            }
            
            if domain_template:
                result["domain_template"] = {
                    "domain": domain,
                    "template": {
                        "id": domain_template.id,
                        "name": domain_template.name
                    }
                }
                
            if global_template:
                result["global_template"] = {
                    "id": global_template.id,
                    "name": global_template.name
                }
            
            return json.dumps(result, indent=2)
            
    except Exception as e:
        logger.error(f"Error getting user template assignment: {e}")
        return json.dumps({
            "success": False,
            "message": f"❌ Failed to get template assignment: {str(e)}"
        })


def setup_template_tools(mcp):
    """Register email template management tools with the FastMCP server."""
    
    @mcp.tool(
        name="create_email_template",
        description="Create a new HTML email template with placeholders",
        tags={"email", "template", "create", "html"},
        annotations={
            "title": "Create Email Template",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": False
        }
    )
    async def create_email_template_tool(
        template_name: str,
        html_content: str,
        description: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> str:
        return await create_email_template(template_name, html_content, description, tags)
    
    @mcp.tool(
        name="assign_template_to_user",
        description="Assign an email template to a specific user email address",
        tags={"email", "template", "assign", "user"},
        annotations={
            "title": "Assign Template to User",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False
        }
    )
    async def assign_template_to_user_tool(
        template_id: str,
        user_email: str,
        priority: int = 100
    ) -> str:
        return await assign_template_to_user(template_id, user_email, priority)
    
    @mcp.tool(
        name="list_email_templates",
        description="List available email templates with optional search",
        tags={"email", "template", "list", "search"},
        annotations={
            "title": "List Email Templates",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False
        }
    )
    async def list_email_templates_tool(
        search_query: Optional[str] = None,
        limit: int = 20
    ) -> str:
        return await list_email_templates(search_query, limit)
    
    @mcp.tool(
        name="remove_template_assignment",
        description="Remove template assignment from a user",
        tags={"email", "template", "remove", "unassign"},
        annotations={
            "title": "Remove Template Assignment",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False
        }
    )
    async def remove_template_assignment_tool(
        user_email: str,
        template_id: Optional[str] = None
    ) -> str:
        return await remove_template_assignment(user_email, template_id)
    
    @mcp.tool(
        name="delete_email_template",
        description="Delete an email template and all its assignments",
        tags={"email", "template", "delete", "remove"},
        annotations={
            "title": "Delete Email Template",
            "readOnlyHint": False,
            "destructiveHint": True,
            "idempotentHint": True,
            "openWorldHint": False
        }
    )
    async def delete_email_template_tool(
        template_id: str,
        confirm: bool = False
    ) -> str:
        return await delete_email_template(template_id, confirm)
    
    @mcp.tool(
        name="preview_email_template",
        description="Preview an email template with sample data",
        tags={"email", "template", "preview", "test"},
        annotations={
            "title": "Preview Email Template",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False
        }
    )
    async def preview_email_template_tool(
        template_id: str,
        sample_data: Optional[Dict[str, str]] = None
    ) -> str:
        return await preview_email_template(template_id, sample_data)
    
    @mcp.tool(
        name="get_user_template_assignment",
        description="Get the template assignment for a specific user email",
        tags={"email", "template", "user", "check"},
        annotations={
            "title": "Get User Template Assignment",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False
        }
    )
    async def get_user_template_assignment_tool(
        user_email: str
    ) -> str:
        return await get_user_template_assignment(user_email)