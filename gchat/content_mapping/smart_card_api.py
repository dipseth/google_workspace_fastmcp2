"""
Smart Card API for Google Chat Card Creation

This module provides a simplified API for creating and sending Google Chat cards
using natural language content descriptions, templates, and advanced features.
"""

import logging
import json
from typing import Dict, List, Any, Optional, Tuple, Union

# Import content mapping components
from .content_mapping_engine import ContentMappingEngine
from .parameter_inference_engine import ParameterInferenceEngine
from .template_manager import TemplateManager
from .widget_specification_parser import WidgetSpecificationParser
from .layout_optimizer import LayoutOptimizer, MetricsClient
from .multi_modal_support import MultiModalSupport

# Import card validator (placeholder - would be implemented in a real system)
class CardValidator:
    """Validates and auto-corrects card structures."""
    
    async def validate_and_fix(self, card: Dict, auto_format: bool = True) -> Dict:
        """
        Validate a card structure and optionally fix issues.
        
        Args:
            card: Card structure to validate
            auto_format: Whether to automatically fix issues
            
        Returns:
            Validated and potentially fixed card structure
        """
        # In a real implementation, this would check for structural issues
        # and fix them according to the Google Chat card format requirements
        return card

logger = logging.getLogger(__name__)

# Initialize components
_content_mapping_engine = ContentMappingEngine()
_parameter_inference_engine = ParameterInferenceEngine()
_template_manager = TemplateManager()
_widget_specification_parser = WidgetSpecificationParser(_parameter_inference_engine)
_card_validator = CardValidator()
_layout_optimizer = LayoutOptimizer()
_multi_modal = MultiModalSupport()


async def parse_natural_language_content(content: str) -> Dict[str, Any]:
    """
    Parse natural language content into a structured card representation.
    
    Args:
        content: Natural language content description
        
    Returns:
        Dictionary representing the parsed content as a card structure
    """
    logger.info(f"Parsing natural language content: {content[:50]}...")
    return _content_mapping_engine.parse_content(content)


async def create_card_from_description(description: str, auto_format: bool = True) -> Dict[str, Any]:
    """
    Create a card structure from a natural language description.
    
    Args:
        description: Natural language description of the card
        auto_format: Whether to automatically format and fix issues
        
    Returns:
        Dictionary representing the card structure
    """
    logger.info(f"Creating card from description: {description[:50]}...")
    
    # Parse the description into a card structure
    card = await parse_natural_language_content(description)
    
    # Validate and fix issues if auto_format is enabled
    if auto_format:
        card = await _card_validator.validate_and_fix(card, auto_format=True)
    
    return card


async def create_card_from_template(
    template_name_or_id: str,
    content: Dict[str, str],
    user_google_email: str,
    space_id: str,
    thread_key: Optional[str] = None,
    webhook_url: Optional[str] = None
) -> str:
    """
    Create and send a card using a predefined template with content substitution.
    
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
    logger.info(f"Creating card from template '{template_name_or_id}' for space {space_id}")
    
    template_data = None
    
    # Check if the input looks like a UUID (template ID)
    is_uuid = False
    if len(template_name_or_id) == 36 and template_name_or_id.count('-') == 4:
        is_uuid = True
        
    # Try to get template directly by ID if it looks like a UUID
    if is_uuid:
        try:
            direct_template = await _template_manager.get_template(template_name_or_id)
            if direct_template:
                template_data = direct_template
                logger.info(f"Found template directly by ID: {template_name_or_id}")
        except Exception as e:
            logger.warning(f"Failed to get template by ID, falling back to name search: {e}")
    
    # If we don't have a template yet, try the name search approach
    if not template_data:
        templates = await _template_manager.find_templates(template_name_or_id, limit=1)
        if not templates:
            raise ValueError(f"Template '{template_name_or_id}' not found")
        template_data = templates[0]
    
    # Apply content to template
    card = _template_manager.apply_template(template_data, content)
    
    # Validate and fix issues
    card = await _card_validator.validate_and_fix(card, auto_format=True)
    
    # Send the card
    return await _send_card_to_chat(
        user_google_email=user_google_email,
        space_id=space_id,
        card=card,
        thread_key=thread_key,
        webhook_url=webhook_url
    )


async def send_smart_card(
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
    
    Args:
        user_google_email: User's Google email
        space_id: Chat space ID
        content: Natural language content description
        style: Card style (default, announcement, form, report, interactive)
        auto_format: Automatically format and fix issues
        thread_key: Optional thread key for threaded replies
        webhook_url: Optional webhook URL for card delivery
        
    Returns:
        Confirmation message with sent message details
    """
    logger.info(f"Sending smart card to space {space_id}")
    
    # Create card from description
    card = await create_card_from_description(content, auto_format=auto_format)
    
    # Apply style if specified
    if style and style != "default":
        card = _apply_card_style(card, style)
    
    # Send the card
    return await _send_card_to_chat(
        user_google_email=user_google_email,
        space_id=space_id,
        card=card,
        thread_key=thread_key,
        webhook_url=webhook_url
    )


async def optimize_card_layout(card_id: str) -> Dict:
    """
    Analyze and optimize a card layout based on engagement metrics.
    
    Args:
        card_id: ID of the card to optimize
        
    Returns:
        Dictionary with metrics and suggested improvements
    """
    logger.info(f"Optimizing card layout for card {card_id}")
    
    # Get the card (in a real implementation, this would fetch from a database)
    # For now, we'll use a placeholder card structure
    card = await _get_card_by_id(card_id)
    
    # Analyze engagement metrics
    metrics = await _layout_optimizer.analyze_card_engagement(card_id)
    
    # Get layout improvement suggestions
    improvements = await _layout_optimizer.suggest_layout_improvements(card)
    
    return {
        "card_id": card_id,
        "metrics": metrics,
        "improvements": improvements
    }


async def create_multi_modal_card(
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
    
    Args:
        user_google_email: User's Google email
        space_id: Chat space ID
        content: Natural language content description
        data: Optional data for chart generation
        images: Optional list of image URLs
        video_url: Optional video URL
        thread_key: Optional thread key for threaded replies
        webhook_url: Optional webhook URL for card delivery
        
    Returns:
        Confirmation message with sent message details
    """
    logger.info(f"Creating multi-modal card for space {space_id}")
    
    # Create base card from content description
    card = await create_card_from_description(content, auto_format=True)
    
    # Process multi-modal content
    if data:
        # Generate chart from data
        chart_url = await _multi_modal.generate_chart(data)
        
        # Add chart image to card
        if "sections" not in card:
            card["sections"] = []
        
        card["sections"].append({
            "widgets": [
                {
                    "image": {
                        "imageUrl": chart_url,
                        "altText": "Data visualization chart"
                    }
                }
            ]
        })
    
    if images:
        # Optimize images
        optimized_images = []
        for image_url in images:
            optimized_url = await _multi_modal.optimize_image(image_url)
            optimized_images.append(optimized_url)
        
        # Create image grid
        image_grid = await _multi_modal.create_image_grid(optimized_images)
        
        # Add image grid to card
        if "sections" not in card:
            card["sections"] = []
        
        card["sections"].append(image_grid["section"])
    
    if video_url:
        # Extract video thumbnail
        thumbnail_url = await _multi_modal.extract_video_thumbnail(video_url)
        
        # Add video thumbnail with button to card
        if "sections" not in card:
            card["sections"] = []
        
        card["sections"].append({
            "widgets": [
                {
                    "image": {
                        "imageUrl": thumbnail_url,
                        "altText": "Video thumbnail"
                    }
                },
                {
                    "buttonList": {
                        "buttons": [
                            {
                                "text": "Watch Video",
                                "onClick": {
                                    "openLink": {
                                        "url": video_url
                                    }
                                }
                            }
                        ]
                    }
                }
            ]
        })
    
    # Send the card
    return await _send_card_to_chat(
        user_google_email=user_google_email,
        space_id=space_id,
        card=card,
        thread_key=thread_key,
        webhook_url=webhook_url
    )


# Helper functions

async def _get_card_by_id(card_id: str) -> Dict:
    """
    Get a card by ID.
    
    Args:
        card_id: ID of the card to retrieve
        
    Returns:
        Card structure
    """
    # In a real implementation, this would fetch from a database
    # For now, return a placeholder card
    return {
        "header": {
            "title": "Sample Card"
        },
        "sections": [
            {
                "widgets": [
                    {
                        "textParagraph": {
                            "text": "This is a sample card for optimization testing."
                        }
                    }
                ]
            }
        ]
    }


def _apply_card_style(card: Dict, style: str) -> Dict:
    """
    Apply a predefined style to a card.
    
    Args:
        card: Card structure to style
        style: Style name (announcement, form, report, interactive)
        
    Returns:
        Styled card structure
    """
    styled_card = card.copy()
    
    if style == "announcement":
        # Add announcement styling (e.g., prominent header, accent color)
        # Note: imageStyle field was removed as it's not supported by Google Chat Cards v2 API
        if "header" in styled_card:
            styled_card["header"]["subtitle"] = styled_card["header"].get("subtitle", "Announcement")
            
            # Add a different visual indicator that is supported
            if "sections" not in styled_card:
                styled_card["sections"] = []
            
            # Add a decorative divider at the top to make announcements stand out
            if not styled_card["sections"]:
                styled_card["sections"].append({"widgets": []})
            
            # Add a color indicator using decoratedText instead
            styled_card["sections"][0]["widgets"].insert(0, {
                "decoratedText": {
                    "topLabel": "ANNOUNCEMENT",
                    "text": " ",  # Minimal text
                    "wrapText": False
                }
            })
    
    elif style == "form":
        # Add form styling (e.g., input fields, submit button)
        if "sections" not in styled_card:
            styled_card["sections"] = []
        
        # Add a submit button if not present
        has_button = False
        for section in styled_card.get("sections", []):
            for widget in section.get("widgets", []):
                if "buttonList" in widget:
                    has_button = True
                    break
        
        if not has_button:
            styled_card["sections"].append({
                "widgets": [
                    {
                        "buttonList": {
                            "buttons": [
                                {
                                    "text": "Submit",
                                    "onClick": {
                                        "action": {
                                            "function": "submit_form"
                                        }
                                    }
                                }
                            ]
                        }
                    }
                ]
            })
    
    elif style == "report":
        # Add report styling (e.g., structured sections, dividers)
        if "header" in styled_card and "subtitle" not in styled_card["header"]:
            styled_card["header"]["subtitle"] = "Report"
    
    elif style == "interactive":
        # Add interactive styling (e.g., buttons, interactive elements)
        pass
    
    return styled_card


async def _send_card_to_chat(
    user_google_email: str,
    space_id: str,
    card: Dict,
    thread_key: Optional[str] = None,
    webhook_url: Optional[str] = None
) -> str:
    """
    Send a card to Google Chat.
    
    Args:
        user_google_email: User's Google email
        space_id: Chat space ID
        card: Card structure to send
        thread_key: Optional thread key for threaded replies
        webhook_url: Optional webhook URL for card delivery
        
    Returns:
        Confirmation message with sent message details
    """
    logger.info(f"Sending card to space {space_id} for user {user_google_email}")
    logger.debug(f"Card content: {json.dumps(card, indent=2)}")
    
    # Check if webhook URL is provided
    if webhook_url:
        try:
            import requests
            
            # Ensure card has the proper Google Chat format
            # If card doesn't have the expected structure, wrap it
            if "card" not in card and "header" in card:
                google_format_card = {"card": card}
            else:
                google_format_card = card
            
            # Create message payload
            rendered_message = {
                "text": f"Card message from {user_google_email}",
                "cardsV2": [google_format_card]
            }
            
            # Add thread key if provided
            if thread_key:
                rendered_message["threadKey"] = thread_key
            
            logger.debug(f"Sending webhook payload: {json.dumps(rendered_message, indent=2)}")
            
            # Send via webhook
            response = requests.post(
                webhook_url,
                json=rendered_message,
                headers={'Content-Type': 'application/json'}
            )
            
            logger.info(f"Webhook response status: {response.status_code}")
            
            if response.status_code == 200:
                return f"✅ Card sent successfully via webhook! Status: {response.status_code}"
            else:
                error_msg = f"❌ Webhook delivery failed. Status: {response.status_code}, Response: {response.text}"
                logger.error(error_msg)
                return error_msg
                
        except Exception as e:
            error_msg = f"❌ Error sending card via webhook: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return error_msg
    else:
        # No webhook URL provided - log a warning
        logger.warning("No webhook URL provided. Cannot send card to Google Chat.")
        return "❌ No webhook URL provided. Card cannot be sent to Google Chat. Please provide a webhook URL."