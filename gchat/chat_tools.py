"""
Google Chat MCP Tools for FastMCP2.

This module provides MCP tools for interacting with Google Chat API.
Enhanced with Card Framework integration and adapter system support.
Migrated from decorator-based pattern to FastMCP2 architecture.
"""
import logging
import asyncio
import json
from typing import Optional, Dict, Any, List, Union
from googleapiclient.errors import HttpError
from fastmcp import FastMCP

from auth.service_helpers import get_service, request_service
from auth.context import get_injected_service
from resources.user_resources import get_current_user_email_simple

# Card Framework integration
try:
    from card_framework.v2 import Message # Import Message class
    from .chat_cards_optimized import GoogleChatCardManager
    CARDS_AVAILABLE = True
except ImportError:
    CARDS_AVAILABLE = False

# Adapter system integration
try:
    from adapters import AdapterFactory, AdapterRegistry, DiscoveryManager
    ADAPTERS_AVAILABLE = True
except ImportError:
    ADAPTERS_AVAILABLE = False

logger = logging.getLogger(__name__)

# Initialize card manager if available
if CARDS_AVAILABLE:
    card_manager = GoogleChatCardManager()
    logger.info("Google Chat Card Manager initialized")
else:
    card_manager = None
    logger.warning("Card Manager not available - cards will use fallback format")

# Initialize adapter system if available
if ADAPTERS_AVAILABLE:
    try:
        discovery_manager = DiscoveryManager()
        adapter_factory = AdapterFactory(discovery_manager)
        adapter_registry = AdapterRegistry(adapter_factory)
        
        # Properly register card manager with adapter system
        if card_manager and hasattr(adapter_registry, 'register_adapter'):
            adapter_registry.register_adapter('chat_cards', card_manager)
            logger.info("Card manager registered with adapter system")
        
        logger.info("Adapter system initialized for Google Chat")
    except Exception as e:
        logger.error(f"Error initializing adapter system: {e}")
        discovery_manager = None
        adapter_factory = None
        adapter_registry = None
else:
    discovery_manager = None
    adapter_factory = None
    adapter_registry = None
    logger.warning("Adapter system not available")



async def _get_chat_service_with_fallback(user_google_email: str):
    """
    Get Google Chat service with fallback to direct creation if middleware injection fails.
    
    Args:
        user_google_email: User's Google email address
        
    Returns:
        Authenticated Google Chat service instance or None if unavailable
    """
    # First, try middleware injection
    service_key = request_service("chat")
    
    try:
        # Try to get the injected service from middleware
        chat_service = get_injected_service(service_key)
        logger.info(f"Successfully retrieved injected Chat service for {user_google_email}")
        return chat_service
        
    except RuntimeError as e:
        if "not yet fulfilled" in str(e).lower() or "service injection" in str(e).lower():
            # Middleware injection failed, fall back to direct service creation
            logger.warning(f"Middleware injection unavailable, falling back to direct service creation for {user_google_email}")
            
            try:
                # Use the same helper function pattern as Gmail
                chat_service = await get_service("chat", user_google_email)
                logger.info(f"Successfully created Chat service directly for {user_google_email}")
                return chat_service
                
            except Exception as direct_error:
                logger.error(f"Direct Chat service creation failed for {user_google_email}: {direct_error}")
                return None
        else:
            # Different type of RuntimeError, log and return None
            logger.error(f"Chat service injection error for {user_google_email}: {e}")
            return None
            
    except Exception as e:
        logger.error(f"Unexpected error getting Chat service for {user_google_email}: {e}")
        return None


async def _send_text_message_helper(
    user_google_email: str,
    space_id: str,
    message_text: str,
    thread_key: Optional[str] = None
) -> str:
    """
    Helper function to send a text message to Google Chat.
    Can be called by other functions within the module.
    """
    try:
        chat_service = await _get_chat_service_with_fallback(user_google_email)
        
        if chat_service is None:
            error_msg = f"❌ Failed to create Google Chat service for {user_google_email}. Please check your credentials and permissions."
            logger.error(f"[_send_text_message_helper] {error_msg}")
            return error_msg
        
        message_body = {
            'text': message_text
        }

        # Add thread key if provided (for threaded replies)
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

        msg = f"Message sent to space '{space_id}' by {user_google_email}. Message ID: {message_name}, Time: {create_time}"
        logger.info(f"Successfully sent message to space '{space_id}' by {user_google_email}")
        return msg
        
    except HttpError as e:
        error_msg = f"❌ Failed to send message: {e}"
        logger.error(f"[_send_text_message_helper] HTTP error: {e}")
        return error_msg
    except Exception as e:
        error_msg = f"❌ Unexpected error: {str(e)}"
        logger.error(f"[_send_text_message_helper] {error_msg}")
        return error_msg


def setup_chat_tools(mcp: FastMCP) -> None:
    """
    Setup and register all Google Chat tools with the MCP server.
    
    Args:
        mcp: The FastMCP server instance to register tools with
    """
    logger.info("Setting up Google Chat tools")

    @mcp.tool(
        name="list_spaces",
        description="Lists Google Chat spaces (rooms and direct messages) accessible to the user",
        tags={"chat", "spaces", "list", "google"},
        annotations={
            "title": "List Chat Spaces",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True
        }
    )
    async def list_spaces(
        user_google_email: Optional[str] = None,
        page_size: int = 100,
        space_type: str = "all"  # "all", "room", "dm"
    ) -> str:
        """
        Lists Google Chat spaces (rooms and direct messages) accessible to the user.

        🎯 ENHANCED: Gets user email automatically from resources if not provided!
        user_google_email parameter is now optional.

        Args:
            user_google_email (str): The user's Google email address (optional - will auto-detect if not provided).
            page_size (int): Number of spaces to return (default: 100).
            space_type (str): Filter by space type: "all", "room", or "dm" (default: "all").

        Returns:
            str: A formatted list of Google Chat spaces accessible to the user.
        """
        try:
            # 🎯 Multi-method email detection
            user_email = None
            auth_method = "unknown"
            
            # Method 1: Use provided email if given
            if user_google_email and user_google_email.strip():
                user_email = user_google_email.strip()
                auth_method = "provided_parameter"
                logger.info(f"🎯 [list_spaces] Using provided email: {user_email}")
            
            # Method 2: Try resource context (primary method)
            if not user_email:
                try:
                    user_email = get_current_user_email_simple()
                    auth_method = "resource_context"
                    logger.info(f"🎯 [list_spaces] Got email from resource context: {user_email}")
                except ValueError:
                    logger.info("🎯 [list_spaces] No resource context available")
            
            # Final check
            if not user_email:
                return "❌ Authentication error: Could not determine user email. Please provide user_google_email parameter or ensure proper authentication is set up."
            
            logger.info(f"🎯 [list_spaces] Using email: {user_email} (method: {auth_method}), Type={space_type}")

            chat_service = await _get_chat_service_with_fallback(user_email)
            
            if chat_service is None:
                error_msg = f"❌ Failed to create Google Chat service for {user_google_email}. Please check your credentials and permissions."
                logger.error(f"[list_spaces] {error_msg}")
                return error_msg
            
            # Build filter based on space_type
            filter_param = None
            if space_type == "room":
                filter_param = "spaceType = SPACE"
            elif space_type == "dm":
                filter_param = "spaceType = DIRECT_MESSAGE"

            request_params = {"pageSize": page_size}
            if filter_param:
                request_params["filter"] = filter_param

            response = await asyncio.to_thread(
                chat_service.spaces().list(**request_params).execute
            )

            spaces = response.get('spaces', [])
            if not spaces:
                return f"No Chat spaces found for type '{space_type}'."

            output = [f"Found {len(spaces)} Chat spaces (type: {space_type}):"]
            for space in spaces:
                space_name = space.get('displayName', 'Unnamed Space')
                space_id = space.get('name', '')
                space_type_actual = space.get('spaceType', 'UNKNOWN')
                output.append(f"- {space_name} (ID: {space_id}, Type: {space_type_actual})")

            return "\n".join(output)
            
        except HttpError as e:
            error_msg = f"❌ Failed to list spaces: {e}"
            logger.error(f"[list_spaces] HTTP error: {e}")
            return error_msg
        except Exception as e:
            error_msg = f"❌ Unexpected error: {str(e)}"
            logger.error(f"[list_spaces] {error_msg}")
            return error_msg

    @mcp.tool(
        name="get_messages",
        description="Retrieves messages from a Google Chat space",
        tags={"chat", "messages", "get", "google"},
        annotations={
            "title": "Get Chat Messages",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True
        }
    )
    async def get_messages(
        user_google_email: str,
        space_id: str,
        page_size: int = 50,
        order_by: str = "createTime desc"
    ) -> str:
        """
        Retrieves messages from a Google Chat space.

        Args:
            user_google_email (str): The user's Google email address. Required.
            space_id (str): The ID of the Chat space. Required.
            page_size (int): Number of messages to return (default: 50).
            order_by (str): Sort order for messages (default: "createTime desc").

        Returns:
            str: Formatted messages from the specified space.
        """
        logger.info(f"[get_messages] Space ID: '{space_id}' for user '{user_google_email}'")

        try:
            chat_service = await _get_chat_service_with_fallback(user_google_email)
            
            # Get space info first
            space_info = await asyncio.to_thread(
                chat_service.spaces().get(name=space_id).execute
            )
            space_name = space_info.get('displayName', 'Unknown Space')

            # Get messages
            response = await asyncio.to_thread(
                chat_service.spaces().messages().list(
                    parent=space_id,
                    pageSize=page_size,
                    orderBy=order_by
                ).execute
            )

            messages = response.get('messages', [])
            if not messages:
                return f"No messages found in space '{space_name}' (ID: {space_id})."

            output = [f"Messages from '{space_name}' (ID: {space_id}):\n"]
            for msg in messages:
                sender = msg.get('sender', {}).get('displayName', 'Unknown Sender')
                create_time = msg.get('createTime', 'Unknown Time')
                text_content = msg.get('text', 'No text content')
                msg_name = msg.get('name', '')

                output.append(f"[{create_time}] {sender}:")
                output.append(f"  {text_content}")
                output.append(f"  (Message ID: {msg_name})\n")

            return "\n".join(output)
            
        except HttpError as e:
            error_msg = f"❌ Failed to get messages: {e}"
            logger.error(f"[get_messages] HTTP error: {e}")
            return error_msg
        except Exception as e:
            error_msg = f"❌ Unexpected error: {str(e)}"
            logger.error(f"[get_messages] {error_msg}")
            return error_msg

    @mcp.tool(
        name="send_message",
        description="Sends a message to a Google Chat space",
        tags={"chat", "message", "send", "google"},
        annotations={
            "title": "Send Chat Message",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True
        }
    )
    async def send_message(
        user_google_email: str,
        space_id: str,
        message_text: str,
        thread_key: Optional[str] = None
    ) -> str:
        """
        Sends a message to a Google Chat space.

        Args:
            user_google_email (str): The user's Google email address. Required.
            space_id (str): The ID of the Chat space. Required.
            message_text (str): The message text to send. Required.
            thread_key (Optional[str]): Thread key for threaded replies.

        Returns:
            str: Confirmation message with sent message details.
        """
        logger.info(f"[send_message] Email: '{user_google_email}', Space: '{space_id}'")
        return await _send_text_message_helper(user_google_email, space_id, message_text, thread_key)

    @mcp.tool(
        name="search_messages",
        description="Searches for messages in Google Chat spaces by text content",
        tags={"chat", "search", "messages", "google"},
        annotations={
            "title": "Search Chat Messages",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True
        }
    )
    async def search_messages(
        user_google_email: str,
        query: str,
        space_id: Optional[str] = None,
        page_size: int = 25
    ) -> str:
        """
        Searches for messages in Google Chat spaces by text content.

        Args:
            user_google_email (str): The user's Google email address. Required.
            query (str): The search query. Required.
            space_id (Optional[str]): Search within a specific space ID (default: search all).
            page_size (int): Number of results per space (default: 25).

        Returns:
            str: A formatted list of messages matching the search query.
        """
        logger.info(f"[search_messages] Email={user_google_email}, Query='{query}'")

        try:
            chat_service = await _get_chat_service_with_fallback(user_google_email)
            
            # If specific space provided, search within that space
            if space_id:
                response = await asyncio.to_thread(
                    chat_service.spaces().messages().list(
                        parent=space_id,
                        pageSize=page_size,
                        filter=f'text:"{query}"'
                    ).execute
                )
                messages = response.get('messages', [])
                context = f"space '{space_id}'"
            else:
                # Search across all accessible spaces (this may require iterating through spaces)
                # For simplicity, we'll search the user's spaces first
                spaces_response = await asyncio.to_thread(
                    chat_service.spaces().list(pageSize=100).execute
                )
                spaces = spaces_response.get('spaces', [])

                messages = []
                for space in spaces[:10]:  # Limit to first 10 spaces to avoid timeout
                    try:
                        space_messages = await asyncio.to_thread(
                            chat_service.spaces().messages().list(
                                parent=space.get('name'),
                                pageSize=5,
                                filter=f'text:"{query}"'
                            ).execute
                        )
                        space_msgs = space_messages.get('messages', [])
                        for msg in space_msgs:
                            msg['_space_name'] = space.get('displayName', 'Unknown')
                        messages.extend(space_msgs)
                    except HttpError:
                        continue  # Skip spaces we can't access
                context = "all accessible spaces"

            if not messages:
                return f"No messages found matching '{query}' in {context}."

            output = [f"Found {len(messages)} messages matching '{query}' in {context}:"]
            for msg in messages:
                sender = msg.get('sender', {}).get('displayName', 'Unknown Sender')
                create_time = msg.get('createTime', 'Unknown Time')
                text_content = msg.get('text', 'No text content')
                space_name = msg.get('_space_name', 'Unknown Space')

                # Truncate long messages
                if len(text_content) > 100:
                    text_content = text_content[:100] + "..."

                output.append(f"- [{create_time}] {sender} in '{space_name}': {text_content}")

            return "\n".join(output)
            
        except HttpError as e:
            error_msg = f"❌ Failed to search messages: {e}"
            logger.error(f"[search_messages] HTTP error: {e}")
            return error_msg
        except Exception as e:
            error_msg = f"❌ Unexpected error: {str(e)}"
            logger.error(f"[search_messages] {error_msg}")
            return error_msg

    @mcp.tool(
        name="send_card_message",
        description="Sends a rich card message to a Google Chat space using Card Framework",
        tags={"chat", "card", "message", "send", "google"},
        annotations={
            "title": "Send Chat Card Message",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True
        }
    )
    async def send_card_message(
        user_google_email: str,
        space_id: str,
        card_type: str = "simple",
        title: str = "",
        text: str = "",
        subtitle: Optional[str] = None,
        image_url: Optional[str] = None,
        buttons: Optional[List[Dict[str, Any]]] = None,
        fields: Optional[List[Dict[str, Any]]] = None,
        submit_action: Optional[Dict[str, Any]] = None,
        thread_key: Optional[str] = None,
        webhook_url: Optional[str] = None
    ) -> str:
        """
        Sends a rich card message to a Google Chat space using Card Framework.
        Falls back to REST API format if Card Framework is not available.

        Args:
            user_google_email: The user's Google email address
            space_id: The space ID to send the message to
            card_type: Type of card ("simple", "interactive", "form")
            title: Card title
            text: Main text content
            subtitle: Optional subtitle for simple cards
            image_url: Optional image URL for simple cards
            buttons: List of button configurations for interactive cards
            fields: List of form field configurations for form cards
            submit_action: Submit button action for form cards
            thread_key: Optional thread key for threaded replies
            webhook_url: Optional webhook URL for card delivery (bypasses API restrictions)

        Returns:
            str: Confirmation message with sent message details
        """
        logger.info(f"[send_card_message] Email: '{user_google_email}', Space: '{space_id}', Type: '{card_type}'")

        if not card_manager:
            # Fallback to text message if card manager is not available
            fallback_text = f"{title}\n{subtitle or ''}\n{text}".strip()
            return await _send_text_message_helper(user_google_email, space_id, fallback_text, thread_key)

        try:
            chat_service = await _get_chat_service_with_fallback(user_google_email)
            
            # Create card based on type
            try:
                # Create a Message object to hold the card(s)
                message_obj = Message()
                logger.debug(f"[DEBUG] Message object created: {type(message_obj)}")
                logger.debug(f"[DEBUG] Message.cards_v2 type: {type(message_obj.cards_v2)}")
                logger.debug(f"[DEBUG] Message.cards_v2 value: {message_obj.cards_v2}")
                
                if text: # Add plain text if provided
                    message_obj.text = text

                if card_type == "simple":
                    card_obj = card_manager.create_simple_card(title, subtitle, text, image_url)
                elif card_type == "interactive":
                    if not buttons:
                        buttons = []
                    card_dict = card_manager.create_interactive_card(title, text, buttons)
                elif card_type == "form":
                    if not fields or not submit_action:
                        raise ValueError("Form cards require 'fields' and 'submit_action' parameters")
                    card_dict = card_manager.create_form_card(title, fields, submit_action)
                elif card_type == "rich":
                    # Support for rich card type
                    # Format sections if provided, otherwise use empty list
                    formatted_sections = []
                    if buttons:
                        # Convert buttons to a section with buttonList widget
                        button_section = {
                            "widgets": [
                                {
                                    "buttonList": {
                                        "buttons": buttons
                                    }
                                }
                            ]
                        }
                        formatted_sections.append(button_section)
                    
                    # Create rich card
                    try:
                        logger.debug(f"Creating rich card with title: {title}, subtitle: {subtitle}, image_url: {image_url}")
                        card_obj = card_manager.create_rich_card(title, subtitle, image_url, formatted_sections)
                        logger.debug(f"Rich card created: {type(card_obj)}")
                        
                        # Convert to dictionary for JSON serialization
                        if hasattr(card_obj, 'to_dict'):
                            card_dict = card_obj.to_dict()
                            logger.debug(f"Converted card to dictionary using to_dict()")
                        elif hasattr(card_obj, '__dict__'):
                            card_dict = card_obj.__dict__
                            logger.debug(f"Converted card to dictionary using __dict__")
                        else:
                            # Use the card manager to convert
                            card_dict = card_manager._convert_card_to_google_format(card_obj)
                            logger.debug(f"Converted card using _convert_card_to_google_format")
                        
                        # Replace card_obj with the dictionary
                        card_obj = card_dict
                        logger.debug(f"Card object replaced with dictionary")
                    except Exception as e:
                        logger.error(f"Error creating rich card: {e}", exc_info=True)
                        # Fallback to simple card
                        card_obj = card_manager.create_simple_card(
                            title=title,
                            subtitle=subtitle or "Error creating rich card",
                            text=f"Could not create rich card: {str(e)}",
                            image_url=image_url
                        )
                        logger.debug(f"Fell back to simple card due to error")
                else:
                    raise ValueError(f"Unsupported card type: {card_type}")

                # Append the created card object to the Message object's cards_v2 list
                # The Message.render() method will handle the final Google Chat API format.
                logger.debug(f"[DEBUG] About to append card_obj: {type(card_obj)}")
                logger.debug(f"[DEBUG] card_obj content: {card_obj}")
                logger.debug(f"[DEBUG] Checking if cards_v2 supports append: {hasattr(message_obj.cards_v2, 'append')}")
                
                try:
                    message_obj.cards_v2.append(card_obj)
                    logger.debug(f"[DEBUG] Successfully appended card to cards_v2")
                except Exception as append_error:
                    logger.error(f"[DEBUG] Error appending to cards_v2: {append_error}")
                    logger.debug(f"[DEBUG] cards_v2 dir: {dir(message_obj.cards_v2)}")
                    raise
                
                # Render the message object to get the final payload
                logger.debug(f"[DEBUG] About to render message object")
                message_body = message_obj.render()
                logger.debug(f"[DEBUG] Message rendered successfully")
                
                # Fix Card Framework v2 field name issue: cards_v_2 -> cardsV2
                if "cards_v_2" in message_body:
                    message_body["cardsV2"] = message_body.pop("cards_v_2")
                    logger.debug(f"[DEBUG] Converted cards_v_2 to cardsV2")

            except Exception as e:
                logger.error(f"Error creating or rendering card: {e}", exc_info=True)
                fallback_text = f"{title}\n{subtitle or ''}\n{text}".strip()
                return await send_message(user_google_email, space_id, fallback_text, thread_key)

            # Choose delivery method based on webhook_url
            if webhook_url:
                # Use webhook delivery (bypasses credential restrictions)
                logger.info("Sending via webhook URL...")
                import requests
                
                # Create message payload
                # Ensure we're using a serializable dictionary, not a Card object
                if isinstance(card_obj, dict):
                    card_dict = card_obj
                    logger.debug(f"Card object is already a dictionary")
                elif hasattr(card_obj, 'to_dict'):
                    card_dict = card_obj.to_dict()
                    logger.debug(f"Converted card to dictionary using to_dict()")
                elif hasattr(card_obj, '__dict__'):
                    card_dict = card_obj.__dict__
                    logger.debug(f"Converted card to dictionary using __dict__")
                else:
                    # Convert to Google format if it's not already a dict
                    card_dict = card_manager._convert_card_to_google_format(card_obj)
                    logger.debug(f"Converted card using _convert_card_to_google_format")
                
                rendered_message = {
                    "text": f"Card message: {title}",
                    "cardsV2": [card_dict]
                }
                
                logger.debug(f"Rendered message: {json.dumps(rendered_message, default=str)}")
                
                logger.debug(f"Sending card message with webhook payload: {json.dumps(rendered_message, indent=2)}")
                
                try:
                    response = requests.post(
                        webhook_url,
                        json=rendered_message,
                        headers={'Content-Type': 'application/json'}
                    )
                    
                    logger.info(f"Webhook response status: {response.status_code}")
                    if response.status_code == 200:
                        return f"✅ Card message sent successfully via webhook! Status: {response.status_code}, Card Type: {card_type}"
                    else:
                        return f"❌ Webhook delivery failed. Status: {response.status_code}, Response: {response.text}"
                except Exception as e:
                    logger.error(f"Error sending card message via webhook: {e}", exc_info=True)
                    # Fallback to text message
                    fallback_text = f"{title}\n{subtitle or ''}\n{text}".strip()
                    return await send_message(user_google_email=user_google_email, space_id=space_id, message_text=fallback_text, thread_key=thread_key)
            else:
                # Send card message via API
                logger.debug(f"Sending card message with body: {json.dumps(message_body, indent=2)}")

                # Add thread key if provided
                request_params = {
                    'parent': space_id,
                    'body': message_body
                }
                if thread_key:
                    request_params['threadKey'] = thread_key

                try:
                    message = await asyncio.to_thread(
                        chat_service.spaces().messages().create(**request_params).execute
                    )
                    logger.debug(f"Google Chat API response: {json.dumps(message, indent=2)}")

                    message_name = message.get('name', '')
                    create_time = message.get('createTime', '')

                    msg = f"Card message sent to space '{space_id}' by {user_google_email}. Message ID: {message_name}, Time: {create_time}, Card Type: {card_type}"
                    logger.info(f"Successfully sent card message to space '{space_id}' by {user_google_email}")
                    return msg

                except Exception as e:
                    logger.error(f"Error sending card message: {e}", exc_info=True)
                    # Fallback to text message
                    fallback_text = f"{title}\n{subtitle or ''}\n{text}".strip()
                    return await send_message(user_google_email=user_google_email, space_id=space_id, message_text=fallback_text, thread_key=thread_key)
                
        except HttpError as e:
            error_msg = f"❌ Failed to send card message: {e}"
            logger.error(f"[send_card_message] HTTP error: {e}")
            return error_msg
        except Exception as e:
            error_msg = f"❌ Unexpected error: {str(e)}"
            logger.error(f"[send_card_message] {error_msg}")
            return error_msg

    @mcp.tool(
        name="send_simple_card",
        description="Sends a simple card message to a Google Chat space",
        tags={"chat", "card", "simple", "google"},
        annotations={
            "title": "Send Simple Chat Card",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True
        }
    )
    async def send_simple_card(
        user_google_email: str,
        space_id: str,
        title: str,
        text: str,
        subtitle: Optional[str] = None,
        image_url: Optional[str] = None,
        thread_key: Optional[str] = None,
        webhook_url: Optional[str] = None
    ) -> str:
        """
        Sends a simple card message to a Google Chat space.

        Args:
            user_google_email: The user's Google email address
            space_id: The space ID to send the message to
            title: Card title
            text: Main text content
            subtitle: Optional subtitle
            image_url: Optional image URL
            thread_key: Optional thread key for threaded replies
            webhook_url: Optional webhook URL for card delivery (bypasses API restrictions)

        Returns:
            str: Confirmation message with sent message details
        """
        if webhook_url:
            # Use webhook delivery like send_rich_card
            try:
                if not card_manager:
                    return "Card Framework not available. Cannot send simple cards via webhook."
                
                # Create simple card using Card Framework
                card = card_manager.create_simple_card(title, subtitle, text, image_url)
                google_format_card = card_manager._convert_card_to_google_format(card)
                
                # Create message payload
                rendered_message = {
                    "text": f"Simple card: {title}",
                    "cardsV2": [google_format_card]
                }
                
                # Send via webhook
                import requests
                response = requests.post(
                    webhook_url,
                    json=rendered_message,
                    headers={'Content-Type': 'application/json'}
                )
                
                if response.status_code == 200:
                    return f"✅ Simple card sent successfully via webhook! Status: {response.status_code}"
                else:
                    return f"❌ Webhook delivery failed. Status: {response.status_code}, Response: {response.text}"
            except Exception as e:
                return f"Failed to send simple card via webhook: {str(e)}"
        else:
            # Fallback to text message since we don't have service parameter
            fallback_text = f"{title}\n{subtitle or ''}\n{text}".strip()
            return f"Simple card fallback (no webhook provided): {fallback_text}"

    @mcp.tool(
        name="send_interactive_card",
        description="Sends an interactive card with buttons to a Google Chat space",
        tags={"chat", "card", "interactive", "buttons", "google"},
        annotations={
            "title": "Send Interactive Chat Card",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True
        }
    )
    async def send_interactive_card(
        user_google_email: str,
        space_id: str,
        title: str,
        text: str,
        buttons: List[Dict[str, Any]],
        thread_key: Optional[str] = None,
        webhook_url: Optional[str] = None
    ) -> str:
        """
        Sends an interactive card with buttons to a Google Chat space.

        Args:
            user_google_email: The user's Google email address
            space_id: The space ID to send the message to
            title: Card title
            text: Main text content
            buttons: List of button configurations. Each button should be a dict with:
                - "text": Button label text (required)
                - "onClick": Action configuration (required), which can be:
                  * For URL links: {"openLink": {"url": "https://example.com"}}
                  * For actions: {"action": {"function": "functionName", "parameters": [...]}}
                  
                Example buttons:
                [
                    {
                        "text": "Open Google",
                        "onClick": {
                            "openLink": {
                                "url": "https://www.google.com"
                            }
                        }
                    },
                    {
                        "text": "Submit",
                        "onClick": {
                            "action": {
                                "function": "handleSubmit",
                                "parameters": [
                                    {"key": "action", "value": "submit"}
                                ]
                            }
                        }
                    }
                ]
                
                NOTE: Do NOT use "actionMethodName" - use "function" instead for action callbacks
                
            thread_key: Optional thread key for threaded replies
            webhook_url: Optional webhook URL for card delivery (bypasses API restrictions)

        Returns:
            str: Confirmation message with sent message details
        """
        if webhook_url:
            # Use webhook delivery like send_rich_card
            try:
                if not card_manager:
                    return "Card Framework not available. Cannot send interactive cards via webhook."
                
                # Create interactive card manually (Card Framework has button format issues)
                # Convert buttons to Google Chat format
                google_buttons = []
                for btn in buttons:
                    google_btn = {
                        "text": btn.get("text", "Button")
                    }
                    if "url" in btn:
                        google_btn["onClick"] = {
                            "openLink": {
                                "url": btn["url"]
                            }
                        }
                    elif "onClick" in btn:
                        google_btn["onClick"] = btn["onClick"]
                    google_buttons.append(google_btn)
                
                # Create card structure manually
                card_dict = {
                    "header": {
                        "title": title
                    },
                    "sections": [
                        {
                            "widgets": [
                                {
                                    "textParagraph": {
                                        "text": text
                                    }
                                },
                                {
                                    "buttonList": {
                                        "buttons": google_buttons
                                    }
                                }
                            ]
                        }
                    ]
                }
                
                # Create message payload
                rendered_message = {
                    "text": f"Interactive card: {title}",
                    "cardsV2": [{"card": card_dict}]
                }
                
                # Send via webhook
                import requests
                response = requests.post(
                    webhook_url,
                    json=rendered_message,
                    headers={'Content-Type': 'application/json'}
                )
                
                if response.status_code == 200:
                    return f"✅ Interactive card sent successfully via webhook! Status: {response.status_code}"
                else:
                    return f"❌ Webhook delivery failed. Status: {response.status_code}, Response: {response.text}"
            except Exception as e:
                return f"Failed to send interactive card via webhook: {str(e)}"
        else:
            # Fallback to text message since we don't have service parameter
            fallback_text = f"{title}\n{text}\nButtons: {', '.join([btn.get('text', 'Button') for btn in buttons])}"
            return f"Interactive card fallback (no webhook provided): {fallback_text}"

    @mcp.tool(
        name="send_form_card",
        description="Sends a form card to a Google Chat space",
        tags={"chat", "card", "form", "google"},
        annotations={
            "title": "Send Form Chat Card",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True
        }
    )
    async def send_form_card(
        user_google_email: str,
        space_id: str,
        title: str,
        fields: List[Dict[str, Any]],
        submit_action: Dict[str, Any],
        thread_key: Optional[str] = None,
        webhook_url: Optional[str] = None
    ) -> str:
        """
        Sends a form card to a Google Chat space.

        Args:
            user_google_email: The user's Google email address
            space_id: The space ID to send the message to
            title: Form title
            fields: List of form field configurations. Each field should have:
                - "name": Field identifier (required)
                - "label": Display label for the field (required)
                - "type": Field type, e.g., "text_input", "selection_input" (required)
                - "required": Boolean indicating if field is required (optional, default: False)
                
                Example fields:
                [
                    {
                        "name": "username",
                        "label": "Username",
                        "type": "text_input",
                        "required": true
                    },
                    {
                        "name": "feedback",
                        "label": "Your Feedback",
                        "type": "text_input",
                        "required": false
                    }
                ]
                
            submit_action: Submit button action configuration. Should be a dict with:
                - "function": Function name to call on submit (required)
                - "parameters": Optional list of parameters
                
                Example:
                {
                    "function": "submitForm",
                    "parameters": [
                        {"key": "action", "value": "submit"}
                    ]
                }
                
                NOTE: Use "function" not "actionMethodName"
                
            thread_key: Optional thread key for threaded replies
            webhook_url: Optional webhook URL for card delivery (bypasses API restrictions)

        Returns:
            str: Confirmation message with sent message details
        """
        if webhook_url:
            # Use webhook delivery like send_rich_card
            try:
                if not card_manager:
                    return "Card Framework not available. Cannot send form cards via webhook."
                
                # Create form card manually (Card Framework has form format issues)
                # Convert fields to Google Chat format
                google_widgets = []
                
                # Add title text
                google_widgets.append({
                    "textParagraph": {
                        "text": f"<b>{title}</b>"
                    }
                })
                
                # Add form fields (Note: Google Chat has limited form support)
                for field in fields:
                    field_widget = {
                        "textParagraph": {
                            "text": f"<b>{field.get('label', field.get('name', 'Field'))}:</b> {field.get('type', 'text_input')}" +
                                   (" (Required)" if field.get('required', False) else " (Optional)")
                        }
                    }
                    google_widgets.append(field_widget)
                
                # Add submit button
                submit_button = {
                    "buttonList": {
                        "buttons": [
                            {
                                "text": "Submit Form",
                                "onClick": {
                                    "action": submit_action
                                }
                            }
                        ]
                    }
                }
                google_widgets.append(submit_button)
                
                # Create card structure manually
                card_dict = {
                    "header": {
                        "title": title
                    },
                    "sections": [
                        {
                            "widgets": google_widgets
                        }
                    ]
                }
                
                # Create message payload
                rendered_message = {
                    "text": f"Form card: {title}",
                    "cardsV2": [{"card": card_dict}]
                }
                
                # Send via webhook
                import requests
                response = requests.post(
                    webhook_url,
                    json=rendered_message,
                    headers={'Content-Type': 'application/json'}
                )
                
                if response.status_code == 200:
                    return f"✅ Form card sent successfully via webhook! Status: {response.status_code}"
                else:
                    return f"❌ Webhook delivery failed. Status: {response.status_code}, Response: {response.text}"
            except Exception as e:
                return f"Failed to send form card via webhook: {str(e)}"
        else:
            # Fallback to text message since we don't have service parameter
            field_names = ', '.join([field.get('name', 'Field') for field in fields])
            fallback_text = f"{title}\nForm fields: {field_names}"
            return f"Form card fallback (no webhook provided): {fallback_text}"

    @mcp.tool(
        name="get_card_framework_status",
        description="Get the status of Card Framework integration",
        tags={"chat", "card", "framework", "status", "google"},
        annotations={
            "title": "Get Card Framework Status",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True
        }
    )
    async def get_card_framework_status() -> str:
        """
        Get the status of Card Framework integration.

        Returns:
            str: Status information about Card Framework availability
        """
        if card_manager:
            status = card_manager.get_framework_status()
            return f"Card Framework Status: {status}"
        else:
            return "Card Framework Status: Not available - using fallback text messaging"

    @mcp.tool(
        name="get_adapter_system_status",
        description="Get the status of the adapter system integration",
        tags={"chat", "adapter", "system", "status", "google"},
        annotations={
            "title": "Get Adapter System Status",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True
        }
    )
    async def get_adapter_system_status() -> str:
        """
        Get the status of the adapter system integration.

        Returns:
            str: Status information about adapter system availability
        """
        if ADAPTERS_AVAILABLE and adapter_registry:
            # Check if methods exist before calling them
            try:
                if hasattr(adapter_registry, 'get_adapter_count'):
                    adapter_count = adapter_registry.get_adapter_count()
                    adapter_names = adapter_registry.get_adapter_names() if hasattr(adapter_registry, 'get_adapter_names') else "Unknown"
                    return f"Adapter System Status: Available - {adapter_count} adapters registered: {adapter_names}"
                else:
                    return f"Adapter System Status: Available - adapter registry loaded (methods not available)"
            except Exception as e:
                return f"Adapter System Status: Available but error accessing details: {e}"
        else:
            return "Adapter System Status: Not available"

    @mcp.tool(
        name="list_available_card_types",
        description="List all available card types and their descriptions",
        tags={"chat", "card", "types", "list", "google"},
        annotations={
            "title": "List Available Card Types",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True
        }
    )
    async def list_available_card_types() -> str:
        """
        List all available card types and their descriptions.

        Returns:
            str: List of available card types
        """
        card_types = {
            "simple": "Basic card with title, text, optional subtitle and image",
            "interactive": "Card with buttons for user interaction",
            "form": "Card with input fields and submit functionality",
            "rich": "Advanced card with multiple sections, columns, decorated text, and complex layouts"
        }
        
        output = ["Available Card Types:"]
        for card_type, description in card_types.items():
            output.append(f"- {card_type}: {description}")
        
        if card_manager:
            framework_status = card_manager.get_framework_status()
            output.append(f"\nCard Framework: {'Available' if framework_status['framework_available'] else 'Fallback mode'}")
        else:
            output.append("\nCard Framework: Not available")
        
        return "\n".join(output)

    
    @mcp.tool(
        name="send_rich_card",
        description="Sends a rich card message to a Google Chat space with advanced formatting",
        tags={"chat", "card", "rich", "advanced", "google"},
        annotations={
            "title": "Send Rich Chat Card",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True
        }
    )
    async def send_rich_card(
        user_google_email: str,
        space_id: str,
        title: str = "Rich Card Test",
        subtitle: Optional[str] = None,
        image_url: Optional[str] = None,
        sections: Optional[List[Any]] = None,
        thread_key: Optional[str] = None,
        webhook_url: Optional[str] = None
    ) -> str:
        """
        Sends a rich card message to a Google Chat space with advanced formatting.
        
        Due to Google Chat API restrictions, cards cannot be sent using human credentials.
        This tool supports two delivery methods:
        1. Webhook URL (recommended for cards) - bypasses credential restrictions
        2. Google Chat API (fallback for text-only messages)

        Args:
            user_google_email: The user's Google email address (used for API fallback)
            space_id: The space ID to send the message to (used for API fallback)
            title: Card title
            subtitle: Optional subtitle
            image_url: Optional image URL
            sections: Optional list of section configurations for advanced layouts
            thread_key: Optional thread key for threaded replies
            webhook_url: Optional webhook URL for card delivery (bypasses API restrictions)

        Returns:
            str: Confirmation message with sent message details
        """
        try:
            logger.info(f"=== RICH CARD CREATION START ===")
            logger.info(f"User: {user_google_email}, Space: {space_id}, Title: {title}")
            logger.info(f"Image URL provided: {image_url}")
            logger.info(f"Webhook URL provided: {bool(webhook_url)}")
            logger.info(f"Sections provided: {len(sections) if sections else 0} sections")
            if sections:
                for i, section in enumerate(sections):
                    section_type = type(section).__name__
                    if isinstance(section, dict):
                        section_keys = list(section.keys())
                        logger.info(f"  Section {i}: type={section_type}, keys={section_keys}")
                    else:
                        logger.info(f"  Section {i}: type={section_type}")
            
            if not card_manager:
                return "Card Framework not available. Cannot send rich cards."
            
            # Create rich card using Card Framework
            logger.info("Creating rich card with Card Framework...")
            
            # Let the card_manager handle section formatting
            logger.debug(f"Passing sections directly to card_manager: {sections}")
            
            try:
                # Log section types for debugging
                if sections:
                    logger.debug(f"Section types before processing:")
                    for i, section in enumerate(sections):
                        section_type = type(section).__name__
                        logger.debug(f"  Section {i}: type={section_type}")
                
                # Use the card_manager to create the rich card with proper section handling
                card = card_manager.create_rich_card(
                    title=title,
                    subtitle=subtitle,
                    image_url=image_url,
                    sections=sections
                )
                logger.info(f"Rich card created: {type(card)}")
            except Exception as e:
                logger.error(f"Error creating rich card: {e}", exc_info=True)
                
                # Create a more detailed error message
                error_details = f"Could not create rich card: {str(e)}"
                
                # Add section information to the error message if available
                if sections:
                    error_details += f"\nProvided {len(sections)} sections:"
                    for i, section in enumerate(sections):
                        section_type = type(section).__name__
                        if isinstance(section, dict):
                            section_keys = list(section.keys())
                            error_details += f"\n  Section {i}: type={section_type}, keys={section_keys}"
                        else:
                            error_details += f"\n  Section {i}: type={section_type}, value={str(section)[:50]}"
                
                # Fallback to simple card with detailed error information
                card = card_manager.create_simple_card(
                    title=title,
                    subtitle=subtitle or "Error creating rich card",
                    text=error_details,
                    image_url=image_url
                )
                logger.info("Fell back to simple card due to error with detailed information")
            
            # Convert card to proper Google format
            google_format_card = card_manager._convert_card_to_google_format(card)
            logger.info(f"Card converted to Google format: {type(google_format_card)}")
            
            # Create message payload
            rendered_message = {
                "text": f"Rich card test: {title}",
                "cardsV2": [google_format_card]
            }
            
            logger.info(f"Final payload keys: {list(rendered_message.keys())}")
            logger.debug(f"Final payload: {json.dumps(rendered_message, indent=2)}")
            
            # Choose delivery method based on webhook_url
            if webhook_url:
                # Use webhook delivery (bypasses credential restrictions)
                logger.info("Sending via webhook URL...")
                import requests
                
                response = requests.post(
                    webhook_url,
                    json=rendered_message,
                    headers={'Content-Type': 'application/json'}
                )
                
                logger.info(f"Webhook response status: {response.status_code}")
                if response.status_code == 200:
                    logger.info(f"=== RICH CARD WEBHOOK SUCCESS ===")
                    return f"✅ Rich card sent successfully via webhook! Status: {response.status_code}"
                else:
                    logger.error(f"Webhook failed: {response.text}")
                    return f"❌ Webhook delivery failed. Status: {response.status_code}, Response: {response.text}"
            else:
                # Use Google Chat API (will fail for cards with human credentials)
                logger.info("Sending via Google Chat API...")
                logger.warning("Note: Google Chat API blocks cards with human credentials. Consider using webhook_url parameter.")
                
                # Get service with fallback
                service = await _get_chat_service_with_fallback(user_google_email)
                if not service:
                    return "❌ Unable to get Google Chat service"
                
                # Handle space_id format - ensure it starts with "spaces/"
                if not space_id.startswith("spaces/"):
                    parent_space = f"spaces/{space_id}"
                else:
                    parent_space = space_id
                    
                result = service.spaces().messages().create(
                    parent=parent_space,
                    body=rendered_message,
                    threadKey=thread_key
                ).execute()
                
                logger.info(f"=== RICH CARD API SUCCESS ===")
                return f"Rich card sent successfully via API! Message ID: {result.get('name', 'Unknown')}"
            
        except Exception as e:
            logger.error(f"=== RICH CARD TEST FAILED ===")
            logger.error(f"Error sending rich card: {e}", exc_info=True)
            return f"Failed to send rich card: {str(e)}"

    logger.info("✅ Google Chat tools setup complete")