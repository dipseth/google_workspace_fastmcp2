"""
Enhanced Unified Card Tool with ModuleWrapper and Qdrant Integration

This module provides a unified MCP tool for Google Chat cards that leverages
the ModuleWrapper adapter to handle inputs for any type of card dynamically.
It implements the hybrid approach for complex cards, improves widget formatting,
and integrates with Qdrant for storing and retrieving card templates.

This enhanced version replaces the separate card tools in chat_tools.py,
chat_cards_optimized.py, and enhanced_card_adapter.py with a single,
more powerful approach that can handle any card type.
"""

import logging
import asyncio
import json
import inspect
import uuid
import time
from datetime import datetime
from typing import Dict, List, Optional, Any, Union, Tuple, Callable

# Import MCP-related components
from fastmcp import FastMCP

# Import auth helpers
from auth.service_helpers import get_service, request_service
from auth.context import get_injected_service
from resources.user_resources import get_current_user_email_simple

# Import ModuleWrapper
from adapters.module_wrapper import ModuleWrapper

# Try to import Card Framework with graceful fallback
try:
    from card_framework.v2 import Card, Section, Widget, CardHeader, Message
    from card_framework.v2.card import CardWithId
    from card_framework.v2.widgets import (
        Button, TextInput, Image, Divider, SelectionInput, TextParagraph,
        DecoratedText, Icon, Column, Columns, OpenLink, OnClick, ButtonList
    )
    CARD_FRAMEWORK_AVAILABLE = True
    logger = logging.getLogger(__name__)
    logger.info("Card Framework v2 is available for rich card creation")
except ImportError:
    CARD_FRAMEWORK_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning("Card Framework v2 not available. Falling back to REST API format.")
    
    # Define placeholder classes for type hints when Card Framework is not available
    class Card:
        pass
    class Section:
        pass
    class Widget:
        pass

# Global variables for module wrappers and caches
_card_framework_wrapper = None
_card_types_cache = {}
_card_templates_cache = {}
_qdrant_client = None
_card_templates_collection = "card_templates"

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

def _get_qdrant_client():
    """Get or initialize the Qdrant client."""
    global _qdrant_client
    
    if _qdrant_client is None:
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.models import Distance, VectorParams
            
            logger.info("🔗 Initializing Qdrant client...")
            _qdrant_client = QdrantClient(host="localhost", port=6333)
            
            # Ensure card templates collection exists
            collections = _qdrant_client.get_collections()
            collection_names = [c.name for c in collections.collections]
            
            if _card_templates_collection not in collection_names:
                # Create collection for card templates
                _qdrant_client.create_collection(
                    collection_name=_card_templates_collection,
                    vectors_config=VectorParams(
                        size=384,  # Default size for all-MiniLM-L6-v2
                        distance=Distance.COSINE
                    )
                )
                logger.info(f"✅ Created Qdrant collection: {_card_templates_collection}")
            else:
                logger.info(f"✅ Using existing collection: {_card_templates_collection}")
                
            logger.info("✅ Qdrant client initialized")
            
        except ImportError:
            logger.warning("⚠️ Qdrant client not available - template storage disabled")
            return None
        except Exception as e:
            logger.error(f"❌ Failed to initialize Qdrant client: {e}", exc_info=True)
            return None
    
    return _qdrant_client

def _initialize_card_framework_wrapper():
    """Initialize the ModuleWrapper for the card_framework module."""
    global _card_framework_wrapper
    
    if not CARD_FRAMEWORK_AVAILABLE:
        logger.warning("Card Framework not available - cannot initialize wrapper")
        return None
    
    if _card_framework_wrapper is None:
        try:
            import card_framework
            
            logger.info("🔍 Initializing ModuleWrapper for card_framework...")
            
            # Create wrapper with optimized settings
            _card_framework_wrapper = ModuleWrapper(
                module_or_name=card_framework,
                collection_name="card_framework_components",
                index_nested=True,  # Index methods within classes
                index_private=False,  # Skip private components
                max_depth=2,  # Limit recursion depth for better performance
                skip_standard_library=True,  # Skip standard library modules
                include_modules=["card_framework", "gchat"],  # Only include relevant modules
                exclude_modules=["numpy", "pandas", "matplotlib", "scipy"]  # Exclude irrelevant modules
            )
            
            # Cache card types and initialize Qdrant
            _cache_card_types()
            _get_qdrant_client()
            
            logger.info("✅ ModuleWrapper initialized for card_framework")
            
        except ImportError:
            logger.error("❌ Could not import card_framework module")
            return None
        except Exception as e:
            logger.error(f"❌ Failed to initialize ModuleWrapper: {e}", exc_info=True)
            return None
    
    return _card_framework_wrapper

def _cache_card_types():
    """Cache available card types for quick lookup."""
    global _card_types_cache
    
    if not _card_framework_wrapper:
        return
    
    # Search for card types with expanded list
    card_types = [
        "simple", "interactive", "form", "rich",
        "text", "button", "image", "decorated",
        "header", "section", "widget", "divider",
        "selection", "chip", "grid", "column"
    ]
    
    for card_type in card_types:
        results = _card_framework_wrapper.search(f"{card_type} card", limit=5)
        if results:
            # Store only relevant information from the search results
            formatted_results = []
            for result in results:
                formatted_results.append({
                    "name": result.get("name"),
                    "path": result.get("path"),
                    "type": result.get("type"),
                    "score": result.get("score"),
                    "docstring": result.get("docstring", "")[:200]
                })
            _card_types_cache[card_type] = formatted_results
    
    logger.info(f"✅ Cached {len(_card_types_cache)} card types")

async def _find_card_component(query: str, limit: int = 5, score_threshold: float = 0.5):
    """
    Find card components using semantic search with improved matching.
    
    Args:
        query: Natural language query describing the card
        limit: Maximum number of results
        score_threshold: Minimum similarity score threshold
        
    Returns:
        List of matching components
    """
    # Initialize wrapper if needed
    if not _card_framework_wrapper:
        _initialize_card_framework_wrapper()
        
    if not _card_framework_wrapper:
        return []
    
    # Check if query matches any cached card types first
    for card_type, cached_results in _card_types_cache.items():
        if card_type.lower() in query.lower():
            logger.info(f"Using cached results for card type: {card_type}")
            return cached_results
    
    # Search for components
    try:
        # Try async search first
        try:
            results = await _card_framework_wrapper.search_async(query, limit=limit, score_threshold=score_threshold)
            logger.info(f"Async search for '{query}' returned {len(results)} results")
        except (AttributeError, NotImplementedError):
            # Fall back to sync search if async not available
            results = _card_framework_wrapper.search(query, limit=limit, score_threshold=score_threshold)
            logger.info(f"Sync search for '{query}' returned {len(results)} results")
        
        # Log top results for debugging
        if results:
            logger.info(f"Top result: {results[0]['name']} (score: {results[0]['score']:.4f})")
            
        return results
    except Exception as e:
        logger.error(f"❌ Search failed: {e}", exc_info=True)
        return []

async def _find_card_template(query_or_id: str, limit: int = 3):
    """
    Find card templates in Qdrant using semantic search or direct ID lookup.
    
    Args:
        query_or_id: Natural language query or template ID
        limit: Maximum number of results
        
    Returns:
        List of matching templates
    """
    client = _get_qdrant_client()
    if not client:
        return []
    
    # Check if the input looks like a UUID (template ID)
    is_uuid = False
    if len(query_or_id) == 36 and query_or_id.count('-') == 4:
        is_uuid = True
        
    # Try direct ID lookup first if it looks like a UUID
    if is_uuid:
        try:
            # Get template by ID
            points = client.retrieve(
                collection_name=_card_templates_collection,
                ids=[query_or_id]
            )
            
            if points and len(points) > 0:
                # Format the result
                template = points[0].payload
                return [{
                    "score": 1.0,  # Perfect match
                    "template_id": template.get("template_id"),
                    "name": template.get("name"),
                    "description": template.get("description"),
                    "template": template.get("template"),
                    "created_at": template.get("created_at")
                }]
        except Exception as e:
            logger.warning(f"⚠️ Direct template lookup failed, falling back to search: {e}")
    
    # Fall back to semantic search
    try:
        # Import required modules
        from sentence_transformers import SentenceTransformer
        
        # Get embedding model
        model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
        
        # Generate embedding for query
        query_embedding = model.encode(query_or_id)
        
        # Search in Qdrant
        search_results = client.search(
            collection_name=_card_templates_collection,
            query_vector=query_embedding.tolist(),
            limit=limit
        )
        
        # Process results
        templates = []
        for result in search_results:
            templates.append({
                "score": result.score,
                "template_id": result.payload.get("template_id"),
                "name": result.payload.get("name"),
                "description": result.payload.get("description"),
                "template": result.payload.get("template"),
                "created_at": result.payload.get("created_at")
            })
        
        logger.info(f"Found {len(templates)} matching templates for '{query}'")
        return templates
        
    except ImportError:
        logger.warning("⚠️ SentenceTransformer not available - template search disabled")
        return []
    except Exception as e:
        logger.error(f"❌ Template search failed: {e}", exc_info=True)
        return []

async def _store_card_template(name: str, description: str, template: Dict[str, Any]):
    """
    Store a card template in Qdrant for future use.
    
    Args:
        name: Template name
        description: Template description
        template: The card template (dictionary)
        
    Returns:
        Template ID if successful, None otherwise
    """
    client = _get_qdrant_client()
    if not client:
        return None
    
    try:
        # Import required modules
        from sentence_transformers import SentenceTransformer
        from qdrant_client.models import PointStruct
        
        # Generate a unique ID for the template
        template_id = str(uuid.uuid4())
        
        # Create payload
        payload = {
            "template_id": template_id,
            "name": name,
            "description": description,
            "template": template,
            "created_at": datetime.now().isoformat()
        }
        
        # Get embedding model
        model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
        
        # Generate embedding for template
        text_to_embed = f"{name} {description}"
        embedding = model.encode(text_to_embed)
        
        # Store in Qdrant
        client.upsert(
            collection_name=_card_templates_collection,
            points=[
                PointStruct(
                    id=template_id,
                    vector=embedding.tolist(),
                    payload=payload
                )
            ]
        )
        
        logger.info(f"✅ Stored card template: {name} (ID: {template_id})")
        return template_id
        
    except ImportError:
        logger.warning("⚠️ SentenceTransformer not available - template storage disabled")
        return None
    except Exception as e:
        logger.error(f"❌ Template storage failed: {e}", exc_info=True)
        return None

def _create_card_from_component(component: Any, params: Dict[str, Any]) -> Optional[Union[Card, Dict[str, Any]]]:
    """
    Create a card using a component found by the ModuleWrapper with improved error handling.
    
    Args:
        component: The component to use (class or function)
        params: Parameters to pass to the component
        
    Returns:
        Card object or dictionary
    """
    if not component:
        return None
    
    try:
        # Check if component is callable
        if callable(component):
            # Get signature
            sig = inspect.signature(component)
            
            # Filter params to match signature
            valid_params = {}
            for param_name, param in sig.parameters.items():
                if param_name in params:
                    valid_params[param_name] = params[param_name]
            
            # Log what parameters we're using
            logger.info(f"Creating component with parameters: {list(valid_params.keys())}")
            
            # Call component with filtered params
            return component(**valid_params)
        
        # If component is a class, try to instantiate it
        elif inspect.isclass(component):
            # Get signature
            sig = inspect.signature(component.__init__)
            
            # Filter params to match signature
            valid_params = {}
            for param_name, param in sig.parameters.items():
                if param_name in params and param_name != 'self':
                    valid_params[param_name] = params[param_name]
            
            # Log what parameters we're using
            logger.info(f"Instantiating class with parameters: {list(valid_params.keys())}")
            
            # Instantiate class with filtered params
            return component(**valid_params)
        
        logger.warning(f"Component is neither callable nor a class: {type(component)}")
        return None
    
    except Exception as e:
        logger.error(f"❌ Failed to create card from component: {e}", exc_info=True)
        return None

def _create_card_with_hybrid_approach(
    card_component: Any,
    params: Dict[str, Any],
    sections: List[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Create a card using the hybrid approach (ModuleWrapper + direct API).
    
    This approach uses ModuleWrapper to create the basic card structure,
    then adds sections and widgets directly using the Google Chat API format.
    
    Args:
        card_component: The Card component to use
        params: Parameters for the card (header, etc.)
        sections: Optional sections to add directly
        
    Returns:
        Card in Google Chat API format
    """
    try:
        # Create the basic card structure using ModuleWrapper
        card = _create_card_from_component(card_component, params)
        
        # Convert to dictionary
        if hasattr(card, 'to_dict'):
            card_dict = card.to_dict()
        elif hasattr(card, '__dict__'):
            card_dict = card.__dict__
        elif isinstance(card, dict):
            card_dict = card
        else:
            logger.warning(f"Unknown card type: {type(card)}")
            card_dict = {}
            
            # Create a minimal card if conversion failed
            if "header" in params:
                card_dict["header"] = params["header"]
        
        # Add sections if provided
        if sections:
            card_dict["sections"] = sections
        
        # Generate a unique card ID
        card_id = getattr(card, 'card_id', None) or f"card_{int(time.time())}_{hash(str(card_dict)) % 10000}"
        
        # Create the final card dictionary
        result = {
            "cardId": card_id,
            "card": card_dict
        }
        
        return result
    
    except Exception as e:
        logger.error(f"❌ Failed to create card with hybrid approach: {e}", exc_info=True)
        
        # Create a fallback card
        return {
            "cardId": f"fallback_{int(time.time())}",
            "card": {
                "header": {
                    "title": params.get("title", "Fallback Card"),
                    "subtitle": params.get("subtitle", "Error occurred during card creation")
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
        }

def _fix_widgets_format(widgets: List[Dict[str, Any]]) -> None:
    """
    Fix widget formatting for Google Chat API compatibility.
    
    This function recursively processes widgets to ensure they are properly
    formatted for the Google Chat API. It handles nested widgets, button lists,
    and other complex structures.
    
    Args:
        widgets: List of widgets to fix
    """
    if not widgets or not isinstance(widgets, list):
        return
    
    for widget in widgets:
        if not isinstance(widget, dict):
            continue
        
        # Handle button lists
        if "buttonList" in widget:
            button_list = widget["buttonList"]
            if "buttons" in button_list and isinstance(button_list["buttons"], list):
                for button in button_list["buttons"]:
                    # Fix onClick format
                    if "onClick" in button and isinstance(button["onClick"], dict):
                        on_click = button["onClick"]
                        
                        # Fix openLink format
                        if "openLink" in on_click and isinstance(on_click["openLink"], dict):
                            open_link = on_click["openLink"]
                            if "url" in open_link and isinstance(open_link["url"], str):
                                # Already in correct format
                                pass
                            elif hasattr(open_link, "url") and isinstance(open_link.url, str):
                                # Convert from object to dict
                                on_click["openLink"] = {"url": open_link.url}
        
        # Handle columns
        if "columns" in widget and isinstance(widget["columns"], list):
            for column in widget["columns"]:
                if "widgets" in column and isinstance(column["widgets"], list):
                    # Recursively fix nested widgets
                    _fix_widgets_format(column["widgets"])
        
        # Handle decoratedText
        if "decoratedText" in widget and isinstance(widget["decoratedText"], dict):
            decorated_text = widget["decoratedText"]
            
            # Fix button format
            if "button" in decorated_text and isinstance(decorated_text["button"], dict):
                button = decorated_text["button"]
                
                # Fix onClick format
                if "onClick" in button and isinstance(button["onClick"], dict):
                    on_click = button["onClick"]
                    
                    # Fix openLink format
                    if "openLink" in on_click and isinstance(on_click["openLink"], dict):
                        open_link = on_click["openLink"]
                        if "url" in open_link and isinstance(open_link["url"], str):
                            # Already in correct format
                            pass
                        elif hasattr(open_link, "url") and isinstance(open_link.url, str):
                            # Convert from object to dict
                            on_click["openLink"] = {"url": open_link.url}

def _convert_card_to_google_format(card: Any) -> Dict[str, Any]:
    """
    Convert Card Framework card to Google Chat format with improved widget formatting.
    
    Args:
        card: Card Framework card object
        
    Returns:
        Dict in Google Chat card format
    """
    try:
        # Handle different card types
        if hasattr(card, 'to_dict'):
            # Card Framework v2 object
            card_dict = card.to_dict()
        elif hasattr(card, '__dict__'):
            # Object with __dict__
            card_dict = card.__dict__
        elif isinstance(card, dict):
            # Already a dictionary
            card_dict = card
        else:
            # Unknown type
            logger.warning(f"Unknown card type: {type(card)}")
            return {"error": f"Unknown card type: {type(card)}"}
        
        # Fix widget formatting for Google Chat API compatibility
        if "sections" in card_dict:
            for section in card_dict["sections"]:
                if "widgets" in section:
                    _fix_widgets_format(section["widgets"])
        
        # Remove unsupported fields that cause API errors
        if "header" in card_dict and isinstance(card_dict["header"], dict):
            # Remove imageStyle field which is not supported by Google Chat Cards v2 API
            if "imageStyle" in card_dict["header"]:
                logger.warning("Removing unsupported 'imageStyle' field from card header")
                del card_dict["header"]["imageStyle"]
        
        # Ensure proper structure for Google Chat API
        card_id = getattr(card, 'card_id', None) or f"card_{int(time.time())}_{hash(str(card_dict)) % 10000}"
        
        result = {
            "cardId": card_id,
            "card": card_dict
        }
        
        return result
    
    except Exception as e:
        logger.error(f"❌ Failed to convert card to Google format: {e}", exc_info=True)
        return {"error": f"Failed to convert card: {str(e)}"}

def setup_unified_card_tool(mcp: FastMCP) -> None:
    """
    Setup the unified card tool for MCP.
    
    Args:
        mcp: The FastMCP server instance
    """
    logger.info("Setting up unified card tool")
    
    # Initialize card framework wrapper
    _initialize_card_framework_wrapper()
    
    @mcp.tool(
        name="send_dynamic_card",
        description="Send any type of card to Google Chat using natural language description",
        tags={"chat", "card", "dynamic", "google", "unified"},
        annotations={
            "title": "Send Dynamic Card",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True
        }
    )
    async def send_dynamic_card(
        user_google_email: str,
        space_id: str,
        card_description: str,
        card_params: Optional[Dict[str, Any]] = None,
        thread_key: Optional[str] = None,
        webhook_url: Optional[str] = None
    ) -> str:
        """
        Send any type of card to Google Chat using natural language description.
        
        This unified tool uses ModuleWrapper to dynamically find and create the
        appropriate card type based on your description. It replaces multiple
        specific card tools with a single, more flexible approach.
        
        Args:
            user_google_email: The user's Google email address
            space_id: The space ID to send the message to
            card_description: Natural language description of the card you want
            card_params: Optional parameters for the card (title, text, etc.)
            thread_key: Optional thread key for threaded replies
            webhook_url: Optional webhook URL for card delivery
            
        Returns:
            Confirmation message with sent message details
        """
        try:
            logger.info(f"🔍 Finding card component for: {card_description}")
            
            # Default parameters if not provided
            if card_params is None:
                card_params = {}
            
            # Find card components
            results = await _find_card_component(card_description)
            
            if not results:
                return f"❌ No matching card components found for: {card_description}"
            
            # Get the best match
            best_match = results[0]
            component = best_match.get("component")
            
            if not component:
                return f"❌ Could not get component for: {best_match.get('path')}"
            
            logger.info(f"✅ Found component: {best_match.get('path')} (score: {best_match.get('score'):.4f})")
            
            # Create card
            card = _create_card_from_component(component, card_params)
            
            if not card:
                return f"❌ Failed to create card using: {best_match.get('path')}"
            
            # Convert to Google format
            google_format_card = _convert_card_to_google_format(card)
            
            # Create message payload
            message_obj = Message()
            
            # Add text if provided
            if "text" in card_params:
                message_obj.text = card_params["text"]
            
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
                    return f"✅ Card message sent successfully via webhook! Status: {response.status_code}, Card Type: {best_match.get('type')}"
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
                
                return f"✅ Card message sent to space '{space_id}' by {user_google_email}. Message ID: {message_name}, Time: {create_time}, Card Type: {best_match.get('type')}"
        
        except Exception as e:
            logger.error(f"❌ Error sending dynamic card: {e}", exc_info=True)
            return f"❌ Error sending dynamic card: {str(e)}"
    
    @mcp.tool(
        name="list_available_card_components",
        description="List available card components that can be used with send_dynamic_card",
        tags={"chat", "card", "list", "components", "google"},
        annotations={
            "title": "List Card Components",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False
        }
    )
    async def list_available_card_components(
        query: Optional[str] = None,
        limit: int = 10
    ) -> str:
        """
        List available card components that can be used with send_dynamic_card.
        
        Args:
            query: Optional search query to filter components
            limit: Maximum number of components to return
            
        Returns:
            JSON string with available card components
        """
        try:
            # Initialize wrapper if needed
            if not _card_framework_wrapper:
                _initialize_card_framework_wrapper()
                
            if not _card_framework_wrapper:
                return "❌ Card Framework wrapper not available"
            
            # Search for components or list cached types
            if query:
                results = _card_framework_wrapper.search(query, limit=limit)
            else:
                # Use cached card types
                if not _card_types_cache:
                    _cache_card_types()
                
                # Flatten results from cache
                results = []
                for card_type, type_results in _card_types_cache.items():
                    for result in type_results[:2]:  # Take top 2 from each type
                        results.append(result)
                
                # Limit results
                results = results[:limit]
            
            # Format results
            formatted_results = []
            for result in results:
                formatted_result = {
                    "name": result.get("name"),
                    "path": result.get("path"),
                    "type": result.get("type"),
                    "score": result.get("score"),
                    "docstring": result.get("docstring", "")[:200]  # Truncate long docstrings
                }
                formatted_results.append(formatted_result)
            
            return json.dumps({
                "query": query or "cached card types",
                "results": formatted_results,
                "count": len(formatted_results)
            }, indent=2)
            
        except Exception as e:
            logger.error(f"❌ Error listing card components: {e}", exc_info=True)
            return f"❌ Error listing card components: {str(e)}"
    
    @mcp.tool(
        name="list_card_templates",
        description="List available card templates stored in Qdrant",
        tags={"chat", "card", "template", "list", "qdrant"},
        annotations={
            "title": "List Card Templates",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False
        }
    )
    async def list_card_templates(
        query: Optional[str] = None,
        limit: int = 10
    ) -> str:
        """
        List available card templates stored in Qdrant.
        
        Args:
            query: Optional search query to filter templates
            limit: Maximum number of templates to return
            
        Returns:
            JSON string with available card templates
        """
        try:
            client = _get_qdrant_client()
            if not client:
                return "❌ Qdrant client not available - cannot list templates"
            
            # Check if collection exists
            collections = client.get_collections()
            collection_names = [c.name for c in collections.collections]
            
            if _card_templates_collection not in collection_names:
                return f"❌ Collection {_card_templates_collection} does not exist"
            
            # Search for templates if query is provided
            if query:
                templates = await _find_card_template(query_or_id=query)
            else:
                # List all templates
                try:
                    # Import required modules
                    from qdrant_client.models import Filter
                    
                    # Get all templates
                    search_results = client.scroll(
                        collection_name=_card_templates_collection,
                        limit=limit,
                        with_payload=True,
                        with_vectors=False
                    )
                    
                    # Process results
                    templates = []
                    for point in search_results[0]:
                        templates.append({
                            "template_id": point.payload.get("template_id"),
                            "name": point.payload.get("name"),
                            "description": point.payload.get("description"),
                            "created_at": point.payload.get("created_at")
                        })
                        
                except ImportError:
                    return "❌ Qdrant client models not available"
                except Exception as e:
                    logger.error(f"❌ Error listing templates: {e}", exc_info=True)
                    return f"❌ Error listing templates: {str(e)}"
            
            # Format results
            return json.dumps({
                "query": query or "all templates",
                "templates": templates,
                "count": len(templates)
            }, indent=2)
            
        except Exception as e:
            logger.error(f"❌ Error listing card templates: {e}", exc_info=True)
            return f"❌ Error listing card templates: {str(e)}"
    
    @mcp.tool(
        name="get_card_template",
        description="Get a specific card template from Qdrant by ID or name",
        tags={"chat", "card", "template", "get", "qdrant"},
        annotations={
            "title": "Get Card Template",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False
        }
    )
    async def get_card_template(
        template_id_or_name: str
    ) -> str:
        """
        Get a specific card template from Qdrant by ID or name.
        
        Args:
            template_id_or_name: ID or name of the template to retrieve
                                (e.g., "4e4a2881-8de2-4adf-bcbd-5fa814c8657a" or "Bullet List Card")
            
        Returns:
            JSON string with the template details
        """
        try:
            client = _get_qdrant_client()
            if not client:
                return "❌ Qdrant client not available - cannot get template"
            
            # Try to find the template using our enhanced function
            templates = await _find_card_template(query_or_id=template_id_or_name, limit=1)
            
            if not templates or len(templates) == 0:
                return f"❌ Template not found: {template_id_or_name}"
            
            # Get the template
            template = templates[0]
            
            # Format result
            return json.dumps(template, indent=2)
            
        except Exception as e:
            logger.error(f"❌ Error getting card template: {e}", exc_info=True)
            return f"❌ Error getting card template: {str(e)}"
    
    @mcp.tool(
        name="save_card_template",
        description="Save a card template to Qdrant",
        tags={"chat", "card", "template", "save", "qdrant"},
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
        template: Dict[str, Any]
    ) -> str:
        """
        Save a card template to Qdrant for future use.
        
        Args:
            name: Template name
            description: Template description
            template: The card template (dictionary)
            
        Returns:
            Template ID if successful
        """
        try:
            template_id = await _store_card_template(name, description, template)
            
            if not template_id:
                return "❌ Failed to save template"
            
            return f"✅ Template saved successfully! ID: {template_id}"
            
        except Exception as e:
            logger.error(f"❌ Error saving card template: {e}", exc_info=True)
            return f"❌ Error saving card template: {str(e)}"
    
    @mcp.tool(
        name="delete_card_template",
        description="Delete a card template from Qdrant",
        tags={"chat", "card", "template", "delete", "qdrant"},
        annotations={
            "title": "Delete Card Template",
            "readOnlyHint": False,
            "destructiveHint": True,
            "idempotentHint": False,
            "openWorldHint": False
        }
    )
    async def delete_card_template(
        template_id: str
    ) -> str:
        """
        Delete a card template from Qdrant.
        
        Args:
            template_id: ID of the template to delete
            
        Returns:
            Confirmation message
        """
        try:
            client = _get_qdrant_client()
            if not client:
                return "❌ Qdrant client not available - cannot delete template"
            
            # Check if collection exists
            try:
                collections = client.get_collections()
                collection_names = [c.name for c in collections.collections]
                
                if _card_templates_collection not in collection_names:
                    return f"❌ Collection {_card_templates_collection} does not exist"
            except Exception as coll_error:
                logger.error(f"❌ Error checking collections: {coll_error}", exc_info=True)
                return f"❌ Error checking collections: {str(coll_error)}"
            
            # Check if template exists
            try:
                points = client.retrieve(
                    collection_name=_card_templates_collection,
                    ids=[template_id]
                )
                
                if not points or len(points) == 0:
                    return f"❌ Template not found: {template_id}"
            except Exception as retrieve_error:
                logger.error(f"❌ Error retrieving template: {retrieve_error}", exc_info=True)
                return f"❌ Error retrieving template: {str(retrieve_error)}"
            
            # Delete the template with proper error handling
            try:
                from qdrant_client.models import PointIdsList
                
                # Use PointIdsList for more reliable deletion
                client.delete(
                    collection_name=_card_templates_collection,
                    points_selector=PointIdsList(
                        points=[template_id]
                    )
                )
                
                # Verify deletion
                verify_points = client.retrieve(
                    collection_name=_card_templates_collection,
                    ids=[template_id]
                )
                
                if not verify_points or len(verify_points) == 0:
                    return f"✅ Template deleted successfully: {template_id}"
                else:
                    return f"⚠️ Template may not have been deleted: {template_id}"
                
            except ImportError:
                # Fall back to simpler deletion if models not available
                client.delete(
                    collection_name=_card_templates_collection,
                    points_selector=[template_id]
                )
                return f"✅ Template deleted successfully: {template_id}"
                
            except Exception as delete_error:
                logger.error(f"❌ Error during template deletion: {delete_error}", exc_info=True)
                return f"❌ Error during template deletion: {str(delete_error)}"
            
        except Exception as e:
            logger.error(f"❌ Error deleting card template: {e}", exc_info=True)
            return f"❌ Error deleting card template: {str(e)}"
    
    @mcp.tool(
        name="get_card_component_info",
        description="Get detailed information about a specific card component",
        tags={"chat", "card", "info", "component", "google"},
        annotations={
            "title": "Get Card Component Info",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False
        }
    )
    async def get_card_component_info(
        component_path: str,
        include_source: bool = False
    ) -> str:
        """
        Get detailed information about a specific card component.
        
        Args:
            component_path: Path to the component (e.g., "card_framework.v2.Card")
            include_source: Whether to include source code in the response
            
        Returns:
            JSON string with component details
        """
        try:
            # Initialize wrapper if needed
            if not _card_framework_wrapper:
                _initialize_card_framework_wrapper()
                
            if not _card_framework_wrapper:
                return "❌ Card Framework wrapper not available"
            
            # Get component info
            info = _card_framework_wrapper.get_component_info(component_path)
            
            if not info:
                return f"❌ Component not found: {component_path}"
            
            # Get the actual component
            component = _card_framework_wrapper.get_component_by_path(component_path)
            
            # Format result
            result = {
                "name": info.get("name"),
                "path": info.get("path"),
                "type": info.get("type"),
                "module_path": info.get("module_path"),
                "docstring": info.get("docstring", "")
            }
            
            # Add source code if requested
            if include_source and component:
                try:
                    import inspect
                    source = inspect.getsource(component)
                    result["source"] = source
                except (TypeError, OSError):
                    result["source"] = "Source code not available"
            
            # Add signature for callable components
            if component and callable(component):
                try:
                    import inspect
                    sig = inspect.signature(component)
                    result["signature"] = str(sig)
                    
                    # Add parameter details
                    params = {}
                    for name, param in sig.parameters.items():
                        params[name] = {
                            "kind": str(param.kind),
                            "default": str(param.default) if param.default is not inspect.Parameter.empty else None,
                            "annotation": str(param.annotation) if param.annotation is not inspect.Parameter.empty else None
                        }
                    
                    result["parameters"] = params
                except (TypeError, ValueError):
                    result["signature"] = "Signature not available"
            
            return json.dumps(result, indent=2)
            
        except Exception as e:
            logger.error(f"❌ Error getting card component info: {e}", exc_info=True)
            return f"❌ Error getting card component info: {str(e)}"
    
    @mcp.tool(
        name="create_card_framework_wrapper",
        description="Create a ModuleWrapper for a specific module",
        tags={"chat", "card", "wrapper", "module", "qdrant"},
        annotations={
            "title": "Create Module Wrapper",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True
        }
    )
    async def create_card_framework_wrapper(
        module_name: str,
        collection_name: Optional[str] = None,
        index_nested: bool = True,
        max_depth: int = 2
    ) -> str:
        """
        Create a ModuleWrapper for a specific module.
        
        This tool allows you to create a ModuleWrapper for any module,
        not just card_framework. This can be useful for exploring and
        using components from other modules.
        
        Args:
            module_name: Name of the module to wrap
            collection_name: Name of the Qdrant collection to use
            index_nested: Whether to index nested components
            max_depth: Maximum recursion depth for indexing
            
        Returns:
            Confirmation message
        """
        try:
            # Import the module
            try:
                import importlib
                module = importlib.import_module(module_name)
            except ImportError:
                return f"❌ Could not import module: {module_name}"
            
            # Generate collection name if not provided
            if not collection_name:
                collection_name = f"{module_name.replace('.', '_')}_components"
            
            # Create the wrapper
            from adapters.module_wrapper import ModuleWrapper
            
            wrapper = ModuleWrapper(
                module_or_name=module,
                collection_name=collection_name,
                index_nested=index_nested,
                index_private=False,
                max_depth=max_depth,
                skip_standard_library=True
            )
            
            # Get component counts
            component_count = len(wrapper.components)
            class_count = len(wrapper.list_components("class"))
            function_count = len(wrapper.list_components("function"))
            
            return f"""✅ ModuleWrapper created for {module_name}!
Collection: {collection_name}
Components: {component_count} total
Classes: {class_count}
Functions: {function_count}

You can now use this wrapper with the send_dynamic_card tool by specifying components from this module.
"""
            
        except Exception as e:
            logger.error(f"❌ Error creating ModuleWrapper: {e}", exc_info=True)
            return f"❌ Error creating ModuleWrapper: {str(e)}"