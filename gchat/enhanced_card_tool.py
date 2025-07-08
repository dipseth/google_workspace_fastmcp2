"""
Enhanced Card Tool with Content Mapping and Parameter Inference

This module extends the unified_card_tool.py with enhanced content mapping and
parameter inference capabilities, making it easier for LLMs to map content to
card formatting in the Google Chat card creation system.
"""

import logging
import asyncio
from typing import Dict, List, Any, Optional, Union

# Import from unified_card_tool
from fastmcp2_drive_upload.gchat.unified_card_tool import (
    _find_card_component, _create_card_from_component, _convert_card_to_google_format,
    _get_chat_service_with_fallback, setup_unified_card_tool, Message
)

# Import our new components
from fastmcp2_drive_upload.gchat.content_mapping.content_mapping_engine import ContentMappingEngine
from fastmcp2_drive_upload.gchat.content_mapping.parameter_inference_engine import ParameterInferenceEngine
from fastmcp2_drive_upload.gchat.content_mapping.template_manager import TemplateManager
from fastmcp2_drive_upload.gchat.content_mapping.widget_specification_parser import WidgetSpecificationParser
from fastmcp2_drive_upload.gchat.content_mapping.card_validator import CardValidator

# Import FastMCP
from fastmcp import FastMCP

logger = logging.getLogger(__name__)

# Initialize our components
_content_mapping_engine = None
_parameter_inference_engine = None
_template_manager = None
_widget_specification_parser = None
_card_validator = None


def _ensure_components_initialized():
    """Initialize the content mapping and parameter inference engines if needed."""
    global _content_mapping_engine, _parameter_inference_engine, _template_manager, _widget_specification_parser, _card_validator
    
    if _content_mapping_engine is None:
        logger.info("🔍 Initializing ContentMappingEngine...")
        _content_mapping_engine = ContentMappingEngine()
        logger.info("✅ ContentMappingEngine initialized")
    
    if _parameter_inference_engine is None:
        logger.info("🔍 Initializing ParameterInferenceEngine...")
        _parameter_inference_engine = ParameterInferenceEngine()
        logger.info("✅ ParameterInferenceEngine initialized")
    
    if _template_manager is None:
        logger.info("🔍 Initializing TemplateManager...")
        _template_manager = TemplateManager()
        logger.info("✅ TemplateManager initialized")
    
    if _widget_specification_parser is None:
        logger.info("🔍 Initializing WidgetSpecificationParser...")
        _widget_specification_parser = WidgetSpecificationParser(_parameter_inference_engine)
        logger.info("✅ WidgetSpecificationParser initialized")
    
    if _card_validator is None:
        logger.info("🔍 Initializing CardValidator...")
        _card_validator = CardValidator()
        logger.info("✅ CardValidator initialized")


async def _ensure_async_components_initialized():
    """Initialize async components."""
    _ensure_components_initialized()
    
    # Initialize template manager asynchronously
    if _template_manager:
        await _template_manager.initialize()


def setup_enhanced_card_tool(mcp: FastMCP) -> None:
    """
    Setup the enhanced card tool for MCP.
    
    This function extends the unified card tool with enhanced content mapping
    and parameter inference capabilities.
    
    Args:
        mcp: The FastMCP server instance
    """
    logger.info("Setting up enhanced card tool")
    
    # Initialize the original unified card tool
    setup_unified_card_tool(mcp)
    
    # Initialize our components
    _ensure_components_initialized()
    
    @mcp.tool(
        name="send_enhanced_card",
        description="Send any type of card to Google Chat with enhanced content mapping and parameter inference",
        tags={"chat", "card", "dynamic", "google", "enhanced", "content-mapping"},
        annotations={
            "title": "Send Enhanced Card",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True
        }
    )
    async def send_enhanced_card(
        user_google_email: str,
        space_id: str,
        content_spec: str,
        card_params: Optional[Dict[str, Any]] = None,
        use_template: Optional[str] = None,
        thread_key: Optional[str] = None,
        webhook_url: Optional[str] = None,
        widget_description: Optional[str] = None,
        validate_card: bool = True
    ) -> str:
        """
        Send any type of card to Google Chat using enhanced content mapping.
        
        This enhanced tool uses ContentMappingEngine, ParameterInferenceEngine,
        WidgetSpecificationParser, and CardValidator to dynamically map content
        to card structures, infer parameters from natural language descriptions,
        parse natural language widget specifications, and validate card content.
        
        Args:
            user_google_email: The user's Google email address
            space_id: The space ID to send the message to
            content_spec: Content specification in any supported format (structured, markdown, etc.)
            card_params: Optional parameters for the card (will be merged with inferred parameters)
            use_template: Optional template ID to use
            thread_key: Optional thread key for threaded replies
            webhook_url: Optional webhook URL for card delivery
            widget_description: Optional natural language description of a widget to add to the card
            validate_card: Whether to validate and auto-fix the card structure (default: True)
            
        Returns:
            Confirmation message with sent message details
        """
        try:
            # Ensure async components are initialized
            await _ensure_async_components_initialized()
            
            logger.info(f"🔍 Processing content specification: {content_spec[:100]}...")
            
            # Default parameters if not provided
            if card_params is None:
                card_params = {}
            
            # If a template is specified, retrieve it
            template = None
            if use_template:
                template = await _template_manager.get_template(use_template)
                if not template:
                    logger.warning(f"⚠️ Template not found: {use_template}")
            
            # Parse content specification using ContentMappingEngine
            parsed_content = _content_mapping_engine.parse_content(content_spec)
            
            # Determine card type using ParameterInferenceEngine
            card_type = _parameter_inference_engine.infer_card_type(content_spec)
            logger.info(f"✅ Inferred card type: {card_type}")
            
            # Find card components using the original method
            results = await _find_card_component(f"{card_type} card")
            
            if not results:
                return f"❌ No matching card components found for: {card_type} card"
            
            # Get the best match
            best_match = results[0]
            component = best_match.get("component")
            
            if not component:
                return f"❌ Could not get component for: {best_match.get('path')}"
            
            logger.info(f"✅ Found component: {best_match.get('path')} (score: {best_match.get('score'):.4f})")
            
            # Merge parameters from different sources with priority:
            # 1. Explicit card_params (highest priority)
            # 2. Parsed content from ContentMappingEngine
            # 3. Inferred parameters from ParameterInferenceEngine
            
            # Start with inferred parameters
            widget_type = best_match.get("type", "unknown")
            inferred_params = _parameter_inference_engine.infer_parameters(widget_type, content_spec)
            
            # Merge with parsed content
            merged_params = {**inferred_params, **parsed_content}
            
            # Process natural language widget description if provided
            if widget_description:
                logger.info(f"🔍 Processing widget description: {widget_description[:100]}...")
                widget_object = _widget_specification_parser.parse_widget_description(widget_description)
                
                # Add the widget to the card
                if "sections" not in merged_params:
                    merged_params["sections"] = [{"widgets": []}]
                elif not merged_params["sections"]:
                    merged_params["sections"] = [{"widgets": []}]
                
                # Add to the first section's widgets
                if "widgets" not in merged_params["sections"][0]:
                    merged_params["sections"][0]["widgets"] = []
                
                merged_params["sections"][0]["widgets"].append(widget_object)
                logger.info(f"✅ Added widget from natural language description")
            
            # Merge with explicit card_params (highest priority)
            merged_params = {**merged_params, **card_params}
            
            # Validate parameters
            validated_params = _parameter_inference_engine.validate_parameters(widget_type, merged_params)
            
            # Apply template if provided
            if template:
                final_params = _template_manager.apply_template(template, validated_params)
            else:
                final_params = validated_params
            
            # Create card using the original method
            card = _create_card_from_component(component, final_params)
            
            if not card:
                return f"❌ Failed to create card using: {best_match.get('path')}"
            
            # Validate and auto-fix card if requested
            if validate_card:
                logger.info("🔍 Validating card structure...")
                is_valid, issues = _card_validator.validate_card_structure(card)
                
                if not is_valid:
                    logger.warning(f"⚠️ Card validation issues: {', '.join(issues)}")
                    logger.info("🔧 Auto-fixing card structure...")
                    card = _card_validator.auto_fix_common_issues(card)
                    
                    # Get improvement suggestions
                    suggestions = _card_validator.suggest_improvements(card)
                    if suggestions:
                        logger.info(f"💡 Card improvement suggestions: {', '.join(suggestions)}")
            
            # Convert to Google format
            google_format_card = _convert_card_to_google_format(card)
            
            # Create message payload
            message_obj = Message()
            
            # Add text if provided
            if "text" in final_params:
                message_obj.text = final_params["text"]
            
            # Add card to message
            message_obj.cards_v2.append(google_format_card)
            
            # Render message
            message_body = message_obj.render()
            
            # Fix Card Framework v2 field name issue: cards_v_2 -> cardsV2
            if "cards_v_2" in message_body:
                message_body["cardsV2"] = message_body.pop("cards_v_2")
            
            # Choose delivery method based on webhook_url
            if webhook_url:
                # Use webhook delivery
                logger.info("Sending via webhook URL...")
                import requests
                
                response = requests.post(
                    webhook_url,
                    json=message_body,
                    headers={'Content-Type': 'application/json'}
                )
                
                if response.status_code == 200:
                    return f"✅ Enhanced card message sent successfully via webhook! Status: {response.status_code}, Card Type: {card_type}"
                else:
                    return f"❌ Webhook delivery failed. Status: {response.status_code}, Response: {response.text}"
            else:
                # Send via API
                chat_service = await _get_chat_service_with_fallback(user_google_email)
                
                if not chat_service:
                    return f"❌ Failed to create Google Chat service for {user_google_email}"
                
                # Add thread key if provided
                request_params = {
                    'parent': space_id,
                    'body': message_body
                }
                if thread_key:
                    request_params['threadKey'] = thread_key
                
                message = await asyncio.to_thread(
                    chat_service.spaces().messages().create(**request_params).execute
                )
                
                message_name = message.get('name', '')
                create_time = message.get('createTime', '')
                
                return f"✅ Enhanced card message sent to space '{space_id}' by {user_google_email}. Message ID: {message_name}, Time: {create_time}, Card Type: {card_type}"
        
        except Exception as e:
            logger.error(f"❌ Error sending enhanced card: {e}", exc_info=True)
            return f"❌ Error sending enhanced card: {str(e)}"
    
    @mcp.tool(
        name="save_card_template",
        description="Save a card template for reuse",
        tags={"chat", "card", "template", "save"},
        annotations={
            "title": "Save Card Template",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True
        }
    )
    async def save_card_template(
        name: str,
        description: str,
        template: Dict[str, Any],
        placeholders: Optional[Dict[str, str]] = None
    ) -> str:
        """
        Save a card template for future use.
        
        Args:
            name: Template name
            description: Template description
            template: The card template (dictionary)
            placeholders: Optional mapping of placeholder names to paths in the template
            
        Returns:
            Template ID if successful
        """
        try:
            # Ensure async components are initialized
            await _ensure_async_components_initialized()
            
            # Store the template
            template_id = await _template_manager.store_template(
                name=name,
                description=description,
                template=template,
                placeholders=placeholders
            )
            
            if not template_id:
                return "❌ Failed to save template"
            
            return f"✅ Template saved successfully! ID: {template_id}"
            
        except Exception as e:
            logger.error(f"❌ Error saving card template: {e}", exc_info=True)
            return f"❌ Error saving card template: {str(e)}"
    
    @mcp.tool(
        name="find_card_templates",
        description="Find card templates matching a query",
        tags={"chat", "card", "template", "find", "search"},
        annotations={
            "title": "Find Card Templates",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False
        }
    )
    async def find_card_templates(
        query: str,
        limit: int = 5
    ) -> str:
        """
        Find card templates matching a query.
        
        Args:
            query: Search query
            limit: Maximum number of results
            
        Returns:
            JSON string with matching templates
        """
        try:
            # Ensure async components are initialized
            await _ensure_async_components_initialized()
            
            # Find templates
            templates = await _template_manager.find_templates(query, limit)
            
            # Format results
            import json
            return json.dumps({
                "query": query,
                "templates": templates,
                "count": len(templates)
            }, indent=2)
            
        except Exception as e:
            logger.error(f"❌ Error finding card templates: {e}", exc_info=True)
            return f"❌ Error finding card templates: {str(e)}"
    
    @mcp.tool(
        name="validate_card",
        description="Validate and auto-fix a card structure for Google Chat",
        tags={"chat", "card", "validation", "fix", "google"},
        annotations={
            "title": "Validate Card",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False
        }
    )
    async def validate_card(
        card: Dict[str, Any],
        auto_fix: bool = True,
        get_suggestions: bool = True
    ) -> Dict[str, Any]:
        """
        Validate and optionally auto-fix a card structure for Google Chat.
        
        Args:
            card: Card structure to validate
            auto_fix: Whether to automatically fix common issues
            get_suggestions: Whether to include improvement suggestions
            
        Returns:
            Dictionary with validation results and fixed card
        """
        try:
            # Ensure components are initialized
            _ensure_components_initialized()
            
            # Validate card structure
            is_valid, issues = _card_validator.validate_card_structure(card)
            
            result = {
                "is_valid": is_valid,
                "issues": issues,
                "card": card
            }
            
            # Auto-fix if requested and there are issues
            if auto_fix and not is_valid:
                fixed_card = _card_validator.auto_fix_common_issues(card)
                result["fixed_card"] = fixed_card
                
                # Validate the fixed card
                is_fixed_valid, fixed_issues = _card_validator.validate_card_structure(fixed_card)
                result["is_fixed_valid"] = is_fixed_valid
                result["fixed_issues"] = fixed_issues
            
            # Get improvement suggestions if requested
            if get_suggestions:
                target_card = result.get("fixed_card", card) if auto_fix else card
                suggestions = _card_validator.suggest_improvements(target_card)
                result["suggestions"] = suggestions
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Error validating card: {e}", exc_info=True)
            return {
                "is_valid": False,
                "error": str(e),
                "card": card
            }