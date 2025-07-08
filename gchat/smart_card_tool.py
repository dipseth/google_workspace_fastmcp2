"""
Smart Card Tool for MCP

This module sets up the Smart Card API as MCP tools, providing a simplified interface
for LLMs to interact with the Google Chat card creation system.
"""

import logging
import json
from typing import Dict, Any, Optional, List

# Import FastMCP
from fastmcp import FastMCP

# Import Smart Card API
from .content_mapping.smart_card_api import (
    send_smart_card, create_card_from_template, create_card_from_description,
    optimize_card_layout, create_multi_modal_card
)

logger = logging.getLogger(__name__)


def setup_smart_card_tool(mcp: FastMCP) -> None:
    """
    Setup the smart card tool for MCP.
    
    Args:
        mcp: The FastMCP server instance
    """
    logger.info("Setting up smart card tool")
    
    @mcp.tool(
        name="send_smart_card",
        description="Create and send a Google Chat card using natural language content description",
        tags={"chat", "card", "smart", "google", "llm"},
        annotations={
            "title": "Send Smart Card",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True
        }
    )
    async def mcp_send_smart_card(
        user_google_email: str,
        space_id: str,
        content: str,
        style: str = "default",
        auto_format: bool = True,
        thread_key: Optional[str] = None,
        webhook_url: Optional[str] = None
    ) -> str:
        """
        Create and send a Google Chat card using natural language content description.
        
        This tool provides a streamlined interface for creating and sending Google Chat
        cards using natural language content descriptions. It automatically maps the content
        to the appropriate card structure, infers parameters, and handles validation.
        
        Args:
            user_google_email: User's Google email
            space_id: Chat space ID
            content: Natural language content description (e.g., "Title: Meeting Update | Text: Team standup at 2 PM")
            style: Card style (default, announcement, form, report, interactive)
            auto_format: Automatically format and fix issues
            thread_key: Optional thread key for threaded replies
            webhook_url: Optional webhook URL for card delivery
            
        Returns:
            Confirmation message with sent message details
        """
        try:
            return await send_smart_card(
                user_google_email=user_google_email,
                space_id=space_id,
                content=content,
                style=style,
                auto_format=auto_format,
                thread_key=thread_key,
                webhook_url=webhook_url
            )
        except Exception as e:
            logger.error(f"❌ Error in send_smart_card MCP tool: {e}", exc_info=True)
            return f"❌ Error sending smart card: {str(e)}"
    
    @mcp.tool(
        name="create_card_from_template",
        description="Create and send a card using a predefined template",
        tags={"chat", "card", "template", "google", "llm"},
        annotations={
            "title": "Create Card From Template",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True
        }
    )
    async def mcp_create_card_from_template(
        template_name_or_id: str,
        content: Dict[str, str],
        user_google_email: str,
        space_id: str,
        thread_key: Optional[str] = None,
        webhook_url: Optional[str] = None
    ) -> str:
        """
        Create and send a card using a predefined template with content substitution.
        
        This tool creates a card using a predefined template and substitutes the provided
        content into the template placeholders.
        
        Args:
            template_name_or_id: Template name or ID (e.g., "status_report" or UUID like "4e4a2881-8de2-4adf-bcbd-5fa814c8657a")
            content: Content mapping for template placeholders
            user_google_email: User's Google email
            space_id: Chat space ID
            thread_key: Optional thread key for threaded replies
            webhook_url: Optional webhook URL for card delivery
            
        Returns:
            Confirmation message with sent message details
        """
        try:
            return await create_card_from_template(
                template_name_or_id=template_name_or_id,
                content=content,
                user_google_email=user_google_email,
                space_id=space_id,
                thread_key=thread_key,
                webhook_url=webhook_url
            )
        except Exception as e:
            logger.error(f"❌ Error in create_card_from_template MCP tool: {e}", exc_info=True)
            return f"❌ Error creating card from template: {str(e)}"
    
    @mcp.tool(
        name="preview_card_from_description",
        description="Preview a card structure from natural language description without sending",
        tags={"chat", "card", "preview", "google", "llm"},
        annotations={
            "title": "Preview Card From Description",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False
        }
    )
    async def mcp_preview_card_from_description(
        description: str,
        auto_format: bool = True
    ) -> str:
        """
        Preview a card structure from natural language description without sending.
        
        This tool creates a card structure from a natural language description without
        sending it. It's useful for previewing cards or for further processing.
        
        Args:
            description: Natural language description of the card
            auto_format: Automatically format and fix issues
            
        Returns:
            JSON string representing the card structure
        """
        try:
            card_data = await create_card_from_description(
                description=description,
                auto_format=auto_format
            )
            
            # Ensure the card has the expected structure
            if isinstance(card_data, dict):
                # Case 1: Simple key-value pairs with Title but no header
                if "Title" in card_data and "header" not in card_data:
                    # Convert simple key-value pairs to card structure
                    formatted_card = {
                        "header": {
                            "title": card_data.get("Title", "")
                        },
                        "sections": []
                    }
                    
                    # Add text content if available
                    if "Text" in card_data:
                        formatted_card["sections"].append({
                            "widgets": [
                                {
                                    "textParagraph": {
                                        "text": card_data.get("Text", "")
                                    }
                                }
                            ]
                        })
                    
                    # Add other fields as decorated text
                    for key, value in card_data.items():
                        if key not in ["Title", "Text"]:
                            if not formatted_card["sections"]:
                                formatted_card["sections"].append({"widgets": []})
                            
                            formatted_card["sections"][0]["widgets"].append({
                                "decoratedText": {
                                    "topLabel": key,
                                    "text": value
                                }
                            })
                    
                    return json.dumps(formatted_card)
                
                # Case 2: Already has header but no sections
                elif "header" in card_data and "sections" not in card_data:
                    card_data["sections"] = []
                    return json.dumps(card_data)
                
                # Case 3: Already has proper structure
                else:
                    return json.dumps(card_data)
            
            # Case 4: Not a dictionary, wrap in a basic card structure
            else:
                try:
                    # Try to convert to string if not already
                    content = str(card_data)
                    basic_card = {
                        "header": {
                            "title": "Card Preview"
                        },
                        "sections": [
                            {
                                "widgets": [
                                    {
                                        "textParagraph": {
                                            "text": content
                                        }
                                    }
                                ]
                            }
                        ]
                    }
                    return json.dumps(basic_card)
                except Exception as e:
                    # Last resort - return an error card
                    error_card = {
                        "header": {
                            "title": "Error Creating Card"
                        },
                        "sections": [
                            {
                                "widgets": [
                                    {
                                        "textParagraph": {
                                            "text": f"Error: {str(e)}"
                                        }
                                    }
                                ]
                            }
                        ]
                    }
                    return json.dumps(error_card)
        except Exception as e:
            logger.error(f"❌ Error in preview_card_from_description MCP tool: {e}", exc_info=True)
            return json.dumps({"error": f"Error previewing card: {str(e)}"})
    
    @mcp.tool(
        name="optimize_card_layout",
        description="Analyze and optimize a card layout based on engagement metrics",
        tags={"chat", "card", "optimize", "analytics", "google", "llm"},
        annotations={
            "title": "Optimize Card Layout",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False
        }
    )
    async def mcp_optimize_card_layout(
        card_id: str
    ) -> str:
        """
        Analyze and optimize a card layout based on engagement metrics.
        
        This tool analyzes card engagement metrics and suggests layout improvements
        based on user interaction patterns. It provides insights into how users
        are engaging with the card and offers actionable suggestions to improve
        engagement.
        
        Args:
            card_id: ID of the card to optimize
            
        Returns:
            JSON string with metrics and suggested improvements
        """
        try:
            optimization_data = await optimize_card_layout(card_id=card_id)
            
            # Ensure the optimization data has the expected structure
            if isinstance(optimization_data, dict):
                # Case 1: Missing card_id
                if "card_id" not in optimization_data:
                    formatted_data = {
                        "card_id": card_id,
                        "metrics": optimization_data.get("metrics", {}),
                        "improvements": optimization_data.get("improvements", [])
                    }
                    return json.dumps(formatted_data)
                
                # Case 2: Missing metrics or improvements
                if "metrics" not in optimization_data or "improvements" not in optimization_data:
                    if "metrics" not in optimization_data:
                        optimization_data["metrics"] = {}
                    if "improvements" not in optimization_data:
                        optimization_data["improvements"] = []
                    return json.dumps(optimization_data)
                
                # Case 3: Already has proper structure
                return json.dumps(optimization_data)
            
            # Case 4: Not a dictionary, create a basic structure
            else:
                try:
                    # Try to convert to string if not already
                    basic_data = {
                        "card_id": card_id,
                        "metrics": {
                            "engagement_score": 0,
                            "click_rate": 0,
                            "view_time": 0
                        },
                        "improvements": [
                            "Could not analyze card layout properly",
                            "Please check the card ID and try again"
                        ]
                    }
                    return json.dumps(basic_data)
                except Exception as e:
                    # Last resort - return an error structure
                    error_data = {
                        "card_id": card_id,
                        "error": f"Error optimizing card layout: {str(e)}",
                        "metrics": {},
                        "improvements": []
                    }
                    return json.dumps(error_data)
        except Exception as e:
            logger.error(f"❌ Error in optimize_card_layout MCP tool: {e}", exc_info=True)
            return json.dumps({"error": f"Error optimizing card layout: {str(e)}"})
    
    @mcp.tool(
        name="create_multi_modal_card",
        description="Create and send a card with multi-modal content",
        tags={"chat", "card", "multi-modal", "media", "google", "llm"},
        annotations={
            "title": "Create Multi-Modal Card",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True
        }
    )
    async def mcp_create_multi_modal_card(
        user_google_email: str,
        space_id: str,
        content: str,
        data: Dict = None,
        images: List[str] = None,
        video_url: str = None,
        thread_key: Optional[str] = None,
        webhook_url: Optional[str] = None
    ) -> str:
        """
        Create and send a card with multi-modal content.
        
        This tool creates and sends a Google Chat card with rich multi-modal content,
        including text, data visualizations, images, and video. It automatically
        optimizes media content for the best viewing experience.
        
        Args:
            user_google_email: User's Google email
            space_id: Chat space ID
            content: Natural language content description
            data: Optional data for chart generation (e.g., {"labels": ["Q1", "Q2"], "values": [10, 20]})
            images: Optional list of image URLs to include in the card
            video_url: Optional video URL to include in the card
            thread_key: Optional thread key for threaded replies
            webhook_url: Optional webhook URL for card delivery
            
        Returns:
            Confirmation message with sent message details
        """
        try:
            return await create_multi_modal_card(
                user_google_email=user_google_email,
                space_id=space_id,
                content=content,
                data=data,
                images=images,
                video_url=video_url,
                thread_key=thread_key,
                webhook_url=webhook_url
            )
        except Exception as e:
            logger.error(f"❌ Error in create_multi_modal_card MCP tool: {e}", exc_info=True)
            return f"❌ Error creating multi-modal card: {str(e)}"