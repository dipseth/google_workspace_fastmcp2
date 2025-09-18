"""
Enhanced Unified Card Tool with ModuleWrapper and Qdrant Integration

This module provides a unified MCP tool for Google Chat cards that leverages
the ModuleWrapper adapter to handle inputs for any type of card dynamically.
It implements the hybrid approach for complex cards, improves widget formatting,
and integrates with Qdrant for storing and retrieving card templates.

This enhanced version replaces the separate card tools in chat_tools.py,
chat_cards_optimized.py, and enhanced_card_adapter.py with a single,
more powerful approach that can handle any card type.

## Key Technical Insights from Testing:

### Google Chat Cards v2 API Requirements:
1. **Structure**: Cards must have nested structure: {header: {...}, sections: [{widgets: [...]}]}
2. **Images**: Cannot be placed in header.imageUrl - must be widgets in sections
3. **Flat Parameters**: Direct flat params like {"title": "Hello"} cause 400 errors
4. **Error Fields**: Any "error" field in card structure causes API rejection

### Card Creation Approaches:
- **Simple Cards**: Use direct parameter transformation for basic title/text cards
- **Complex Cards**: Use component-based creation via ModuleWrapper search
- **Fallback**: Always provide valid card structure even on transformation errors

### Testing Patterns:
- Simple cards (title/text): Always use "variable" type transformation
- Complex descriptions: Trigger component search, return "class" type
- Image handling: Requires widget placement, not header placement
- Error handling: Must return valid card structure, never error objects
"""

import logging
import asyncio
import json
import inspect
import uuid
import time
import hashlib
from datetime import datetime
from typing_extensions import Dict, List, Optional, Any, Union, Tuple, Callable

# Import MCP-related components
from fastmcp import FastMCP

# Import auth helpers
from auth.service_helpers import get_service, request_service
from auth.context import get_injected_service
from resources.user_resources import get_current_user_email_simple

# Template middleware integration handled at server level - no imports needed here

# Import ModuleWrapper
from adapters.module_wrapper import ModuleWrapper

# Import enhanced NLP parser
from .nlp_card_parser import parse_enhanced_natural_language_description

# Import TypedDict response types for structured responses
from gchat.chat_types import (
    CardComponentsResponse,
    CardComponentInfo,
    CardTemplatesResponse,
    CardTemplateInfo
)

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

# Field conversion caches for performance optimization
_camel_to_snake_cache = {}
_snake_to_camel_cache = {}

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
            # Import settings to get proper Qdrant configuration
            from config.settings import settings
            
            logger.info("🔗 Initializing Qdrant client...")
            logger.info(f"📊 SETTINGS DEBUG - Using Qdrant config: URL={settings.qdrant_url}, Host={settings.qdrant_host}, Port={settings.qdrant_port}, API Key={'***' if settings.qdrant_api_key else 'None'}")
            
            # Use settings-based configuration instead of hardcoded localhost
            if settings.qdrant_url:
                # Use URL-based initialization for cloud instances
                if settings.qdrant_api_key:
                    _qdrant_client = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key)
                    logger.info(f"🌐 Connected to Qdrant cloud: {settings.qdrant_url} (API Key: ***)")
                else:
                    _qdrant_client = QdrantClient(url=settings.qdrant_url)
                    logger.info(f"🌐 Connected to Qdrant: {settings.qdrant_url} (No API Key)")
            else:
                # Fallback to host/port configuration
                if settings.qdrant_api_key:
                    _qdrant_client = QdrantClient(
                        host=settings.qdrant_host or "localhost",
                        port=settings.qdrant_port or 6333,
                        api_key=settings.qdrant_api_key
                    )
                else:
                    _qdrant_client = QdrantClient(
                        host=settings.qdrant_host or "localhost",
                        port=settings.qdrant_port or 6333
                    )
                logger.info(f"🌐 Connected to Qdrant: {settings.qdrant_host}:{settings.qdrant_port} (API Key: {'***' if settings.qdrant_api_key else 'None'})")
            
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

def _reset_card_framework_wrapper():
    """Reset the card framework wrapper to force reinitialization."""
    global _card_framework_wrapper, _card_types_cache
    _card_framework_wrapper = None
    _card_types_cache = {}
    logger.info("🔄 Card framework wrapper reset")

def _initialize_card_framework_wrapper(force_reset: bool = False):
    """Initialize the ModuleWrapper for the card_framework module."""
    global _card_framework_wrapper
    
    if not CARD_FRAMEWORK_AVAILABLE:
        logger.warning("Card Framework not available - cannot initialize wrapper")
        return None
    
    if force_reset:
        _reset_card_framework_wrapper()
    
    if _card_framework_wrapper is None:
        try:
            import card_framework
            
            logger.info("🔍 Initializing ModuleWrapper for card_framework...")
            
            # Import settings to pass Qdrant configuration
            from config.settings import settings
            
            # Create wrapper with optimized settings - use FastEmbed-compatible collection
            # Pass Qdrant configuration from settings to ensure cloud connection
            _card_framework_wrapper = ModuleWrapper(
                module_or_name="card_framework.v2",
                qdrant_url=settings.qdrant_url,  # Pass cloud URL from settings
                qdrant_api_key=settings.qdrant_api_key,  # Pass API key from settings
                collection_name="card_framework_components_fastembed",
                index_nested=True,  # Index methods within classes
                index_private=False,  # Skip private components
                max_depth=2,  # Limit recursion depth for better performance
                skip_standard_library=True,  # Skip standard library modules
                include_modules=["card_framework", "gchat"],  # Only include relevant modules
                exclude_modules=["numpy", "pandas", "matplotlib", "scipy"],  # Exclude irrelevant modules
                force_reindex=False,  # Don't force reindex if collection has data
                clear_collection=False  # Set to True to clear duplicates on restart
            )
            
            logger.info(f"✅ ModuleWrapper configured with Qdrant: {settings.qdrant_url or f'{settings.qdrant_host}:{settings.qdrant_port}'}")
            
            # Initialize Qdrant (but don't cache card types - defer until first use)
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
    """Cache available card types and setup template parameter support."""
    global _card_types_cache
    
    # Deferred caching approach - cache on first use
    logger.debug("Card type caching deferred until first use")
    
    # Template parameter support is now available - card tools can use:
    # - {{template://user_email}} for automatic user email
    # - {{user://current/profile}} for user context
    # - {{workspace://content/recent}} for workspace data
    # - {{gmail://content/suggestions}} for dynamic content
    
    logger.info("🎭 Template parameter support enabled for Google Chat cards")
    return

async def _find_card_component(query: str, limit: int = 5, score_threshold: float = 0.1):
    """
    Find card components using ModuleWrapper semantic search.
    
    REFACTORED: Now properly leverages ModuleWrapper.search() instead of duplicating functionality.
    
    Args:
        query: Natural language query describing the card
        limit: Maximum number of results
        score_threshold: Minimum similarity score threshold
        
    Returns:
        List of matching components
    """
    # Initialize wrapper if needed
    if not _card_framework_wrapper:
        _initialize_card_framework_wrapper(force_reset=True)
        
    if not _card_framework_wrapper:
        logger.error("❌ ModuleWrapper not available")
        return []
    
    # Check if we have components, if not, force reinitialize
    if len(_card_framework_wrapper.components) == 0:
        logger.info("🔄 Existing wrapper has no components, forcing reinitialization...")
        _initialize_card_framework_wrapper(force_reset=True)
    
    # On-demand caching: check if query matches a common card type
    common_card_types = [
        "simple", "interactive", "form", "rich",
        "text", "button", "image", "decorated",
        "header", "section", "widget", "divider",
        "selection", "chip", "grid", "column"
    ]
    
    # Check if query matches a card type we might want to cache
    query_lower = query.lower()
    for card_type in common_card_types:
        if card_type in query_lower:
            # Check if already cached
            if card_type in _card_types_cache:
                logger.info(f"Using cached results for card type: {card_type}")
                return _card_types_cache[card_type]
            
            # Not cached yet - search and cache now
            logger.info(f"On-demand caching for card type: {card_type}")
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
                logger.info(f"✅ Cached {len(formatted_results)} results for card type: {card_type}")
                return formatted_results
    
    try:
        # LEVERAGE MODULEWRAPPER: Use existing search functionality
        try:
            results = await _card_framework_wrapper.search_async(query, limit=limit, score_threshold=score_threshold)
            logger.info(f"✅ ModuleWrapper async search for '{query}' returned {len(results)} results")
        except (AttributeError, NotImplementedError):
            # Fall back to sync search if async not available
            results = _card_framework_wrapper.search(query, limit=limit, score_threshold=score_threshold)
            logger.info(f"✅ ModuleWrapper sync search for '{query}' returned {len(results)} results")
        
        # FIXED: Resolve component paths using direct access pattern
        def _map_search_path_to_actual_path(search_path: str) -> str:
            """Map search index path to actual component path."""
            if not search_path:
                return search_path
                
            # Strategy 1: Direct match (path exists as-is)
            if search_path in _card_framework_wrapper.components:
                return search_path
            
            # Strategy 2: Map to v2.widgets path (most common case)
            if search_path.startswith('card_framework.'):
                component_name = search_path.split('.')[-1]
                v2_path = f'card_framework.v2.widgets.{component_name}'
                if v2_path in _card_framework_wrapper.components:
                    return v2_path
            
            # Strategy 3: Look for paths ending with same component name in v2
            component_name = search_path.split('.')[-1]
            for path in _card_framework_wrapper.components.keys():
                if path.endswith(f'.{component_name}') and 'v2' in path and 'widgets' in path:
                    return path
            
            # Strategy 4: Fallback - return original path
            return search_path
        
        # Resolve component objects using direct access pattern
        filtered_results = []
        for result in results:
            search_path = result.get("path", "")
            component = result.get("component")
            
            # CRITICAL FIX: Use ModuleWrapper's built-in component resolution instead of manual extraction
            if not component and search_path:
                # Map search path to actual component path
                actual_path = _map_search_path_to_actual_path(search_path)
                
                if actual_path != search_path:
                    logger.info(f"🔧 Mapped search path: {search_path} → {actual_path}")
                    result["path"] = actual_path  # Update result with correct path
                
                # TRUST THE WRAPPER: Use ModuleWrapper's get_component_by_path method
                try:
                    component = _card_framework_wrapper.get_component_by_path(actual_path)
                    if component:
                        result["component"] = component
                        logger.info(f"✅ ModuleWrapper resolved component: {actual_path} -> {type(component).__name__}")
                    else:
                        logger.warning(f"⚠️ ModuleWrapper could not resolve component: {actual_path}")
                        
                        # FALLBACK: Try direct access pattern only if wrapper method fails
                        if actual_path in _card_framework_wrapper.components:
                            component_data = _card_framework_wrapper.components[actual_path]
                            if hasattr(component_data, 'obj') and component_data.obj:
                                module = component_data.obj
                                
                                # Check if it's already a class/callable we can use directly
                                if inspect.isclass(module) or callable(module):
                                    component = module
                                    result["component"] = component
                                    logger.info(f"✅ Direct fallback resolution: {type(module).__name__}")
                                else:
                                    logger.warning(f"⚠️ Component data object is not usable: {type(module)}")
                            else:
                                logger.warning(f"⚠️ Component data has no usable obj: {component_data}")
                        else:
                            logger.warning(f"⚠️ Component path not in wrapper.components: {actual_path}")
                
                except Exception as resolution_error:
                    logger.error(f"❌ Error resolving component via wrapper: {resolution_error}")
                    # Don't let resolution errors break the search
                    component = None
            
            # Now filter for instantiable components
            if component and (inspect.isclass(component) or callable(component)):
                # Additional filtering for methods (keep the UI filtering logic)
                component_path = result.get("path", "")
                if inspect.ismethod(component) or (hasattr(component, '__self__') and component.__self__ is not None):
                    logger.debug(f"❌ Skipping method reference: {component_path}")
                    continue
                    
                if any(method_pattern in component_path.lower() for method_pattern in ['.add_', '.set_', '.get_', '.remove_', '.update_', '.create_']):
                    logger.debug(f"❌ Skipping likely method: {component_path}")
                    continue
                
                filtered_results.append(result)
                logger.debug(f"✅ Added resolved component: {component_path}")
            else:
                # Keep results for fallback but log the issue
                logger.debug(f"⚠️ No component resolved for: {search_path}")
                filtered_results.append(result)
        
        # Log top results for debugging
        if filtered_results:
            logger.info(f"Top result: {filtered_results[0]['name']} (score: {filtered_results[0]['score']:.4f})")
            
        return filtered_results
        
    except Exception as e:
        logger.error(f"❌ ModuleWrapper search failed: {e}", exc_info=True)
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
    
    # Check if the input looks like a template ID
    is_template_id = False
    if query_or_id.startswith("template_") or (len(query_or_id) == 36 and query_or_id.count('-') == 4):
        is_template_id = True
        
    # Try payload-based search first if it looks like a template ID
    if is_template_id:
        try:
            # Import required modules for filtering
            from qdrant_client.models import Filter, FieldCondition, MatchValue
            
            # Create filter for template_id in payload
            template_id_filter = Filter(
                must=[
                    FieldCondition(
                        key="payload_type",
                        match=MatchValue(value="template")
                    ),
                    FieldCondition(
                        key="template_id",
                        match=MatchValue(value=query_or_id)
                    )
                ]
            )
            
            # Search with filter
            search_results = client.scroll(
                collection_name=_card_templates_collection,
                scroll_filter=template_id_filter,
                limit=1,
                with_payload=True
            )
            
            if search_results and len(search_results[0]) > 0:
                # Format the result
                point = search_results[0][0]
                template = point.payload
                return [{
                    "score": 1.0,  # Perfect match
                    "template_id": template.get("template_id"),
                    "name": template.get("name"),
                    "description": template.get("description"),
                    "template": template.get("template"),
                    "created_at": template.get("created_at")
                }]
        except Exception as e:
            logger.warning(f"⚠️ Template ID lookup failed, falling back to semantic search: {e}")
    
    # Fall back to semantic search
    try:
        # Import required modules
        from fastembed import TextEmbedding
        
        # Get embedding model
        model = TextEmbedding(model_name="sentence-transformers/all-MiniLM-L6-v2")
        
        # Generate embedding for query
        embedding_list = list(model.embed([query_or_id]))
        query_embedding = embedding_list[0] if embedding_list else None
        
        if query_embedding is None:
            logger.error(f"Failed to generate embedding for query: {query_or_id}")
            return []
        
        # Convert to list if needed
        if hasattr(query_embedding, 'tolist'):
            query_vector = query_embedding.tolist()
        else:
            query_vector = list(query_embedding)
        
        # Search in Qdrant using query_points (new API)
        search_results = client.query_points(
            collection_name=_card_templates_collection,
            query=query_vector,
            limit=limit
        )
        
        # Process results
        templates = []
        for result in search_results.points:
            templates.append({
                "score": result.score,
                "template_id": result.payload.get("template_id"),
                "name": result.payload.get("name"),
                "description": result.payload.get("description"),
                "template": result.payload.get("template"),
                "created_at": result.payload.get("created_at")
            })
        
        logger.info(f"Found {len(templates)} matching templates for '{query_or_id}'")
        return templates
        
    except ImportError:
        logger.warning("⚠️ FastEmbed not available - template search disabled")
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
        from fastembed import TextEmbedding
        from qdrant_client.models import PointStruct
        
        # Generate a deterministic template ID based on name and content
        # This ensures consistency with TemplateManager implementation
        template_id = f"template_{hashlib.md5(f'{name}:{json.dumps(template, sort_keys=True)}'.encode('utf-8')).hexdigest()}"
        
        # Create payload
        payload = {
            "template_id": template_id,
            "name": name,
            "description": description,
            "template": template,
            "created_at": datetime.now().isoformat(),
            "payload_type": "template"  # Add payload_type for consistency with TemplateManager
        }
        
        # Get embedding model
        model = TextEmbedding(model_name="sentence-transformers/all-MiniLM-L6-v2")
        
        # Generate embedding for template
        text_to_embed = f"Template: {name}\nDescription: {description}\nType: card template"
        embedding_list = list(model.embed([text_to_embed]))
        embedding = embedding_list[0] if embedding_list else None
        
        if embedding is None:
            logger.error(f"Failed to generate embedding for template: {name}")
            return None
        
        # Convert embedding to list if needed
        if hasattr(embedding, 'tolist'):
            vector_list = embedding.tolist()
        else:
            vector_list = list(embedding)
        
        # Store in Qdrant with random UUID as point ID for consistency with TemplateManager
        client.upsert(
            collection_name=_card_templates_collection,
            points=[
                PointStruct(
                    id=str(uuid.uuid4()),  # Use random UUID as point ID
                    vector=vector_list,
                    payload=payload
                )
            ]
        )
        
        logger.info(f"✅ Stored card template: {name} (ID: {template_id})")
        return template_id
        
    except ImportError:
        logger.warning("⚠️ FastEmbed not available - template storage disabled")
        return None
    except Exception as e:
        logger.error(f"❌ Template storage failed: {e}", exc_info=True)
        return None

def _create_card_from_component(component: Any, params: Dict[str, Any]) -> Optional[Union[Card, Dict[str, Any]]]:
    """
    Create a card using a component found by the ModuleWrapper.
    
    ENHANCED: Now includes post-construction configuration for DecoratedText widgets.
    
    Args:
        component: The component to use (class or function)
        params: Parameters to pass to the component
        
    Returns:
        Card object or dictionary
    """
    if not component or not _card_framework_wrapper:
        return None
    
    # TRUST MODULEWRAPPER: Use create_card_component functionality
    logger.info(f"🔧 Using trusted ModuleWrapper.create_card_component for: {type(component).__name__}")
    
    result = _card_framework_wrapper.create_card_component(component, params)
    
    # POST-CONSTRUCTION ENHANCEMENT: Handle DecoratedText widgets specifically
    if result and hasattr(result, '__class__') and 'DecoratedText' in result.__class__.__name__:
        logger.info(f"🎯 Post-construction configuration for DecoratedText widget")
        
        # Apply DecoratedText-specific configurations after creation
        try:
            # Handle topLabel/top_label
            top_label = params.get('topLabel') or params.get('top_label')
            if top_label and hasattr(result, 'top_label'):
                result.top_label = top_label
                logger.info(f"✅ Set DecoratedText top_label: {top_label}")
            
            # Handle bottomLabel/bottom_label
            bottom_label = params.get('bottomLabel') or params.get('bottom_label')
            if bottom_label and hasattr(result, 'bottom_label'):
                result.bottom_label = bottom_label
                logger.info(f"✅ Set DecoratedText bottom_label: {bottom_label}")
            
            # Handle wrap_text
            if 'wrap_text' in params and hasattr(result, 'wrap_text'):
                result.wrap_text = params['wrap_text']
                logger.info(f"✅ Set DecoratedText wrap_text: {params['wrap_text']}")
            
            # Handle horizontal_alignment
            if 'horizontal_alignment' in params and hasattr(result, 'horizontal_alignment'):
                result.horizontal_alignment = params['horizontal_alignment']
                logger.info(f"✅ Set DecoratedText horizontal_alignment: {params['horizontal_alignment']}")
            
            # Handle switch_control
            if 'switch_control' in params and hasattr(result, 'switch_control'):
                result.switch_control = params['switch_control']
                logger.info(f"✅ Set DecoratedText switch_control")
            
            # Handle button configuration
            if 'button' in params and hasattr(result, 'button'):
                button_data = params['button']
                if isinstance(button_data, dict):
                    # Try to create button using Card Framework
                    try:
                        from card_framework.v2.widgets import Button, OnClick, OpenLink
                        
                        # Create button with proper configuration
                        button_text = button_data.get('text', 'Button')
                        button = Button(text=button_text)
                        
                        # Handle onClick action
                        action_url = (button_data.get('onClick', {}).get('openLink', {}).get('url') or
                                    button_data.get('onclick_action') or
                                    button_data.get('url') or
                                    button_data.get('action'))
                        if action_url:
                            button.on_click = OnClick(open_link=OpenLink(url=action_url))
                            logger.info(f"✅ Set DecoratedText button onClick: {action_url}")
                        
                        # Handle button type/style
                        btn_type = button_data.get('type')
                        if btn_type and hasattr(button, 'type'):
                            button.type = btn_type
                            logger.info(f"✅ Set DecoratedText button type: {btn_type}")
                        
                        result.button = button
                        logger.info(f"✅ Set DecoratedText button: {button_text}")
                        
                    except ImportError:
                        # Fallback to direct assignment
                        result.button = button_data
                        logger.info(f"✅ Set DecoratedText button (fallback): {button_data}")
            
            # Handle icon configuration
            if 'icon' in params and hasattr(result, 'icon'):
                icon_data = params['icon']
                if isinstance(icon_data, dict):
                    try:
                        from card_framework.v2.widgets import Icon
                        
                        # Create icon with proper configuration
                        if 'icon_url' in icon_data:
                            icon = Icon(icon_url=icon_data['icon_url'])
                        elif 'known_icon' in icon_data:
                            icon = Icon(known_icon=icon_data['known_icon'])
                        else:
                            icon = icon_data
                        
                        result.icon = icon
                        logger.info(f"✅ Set DecoratedText icon")
                        
                    except ImportError:
                        # Fallback to direct assignment
                        result.icon = icon_data
                        logger.info(f"✅ Set DecoratedText icon (fallback)")
            
        except Exception as config_error:
            logger.warning(f"⚠️ DecoratedText post-construction configuration failed: {config_error}")
            # Don't fail the entire creation process due to configuration issues
    
    if result:
        logger.info(f"✅ ModuleWrapper created component: {type(result).__name__}")
        
    return result

# REMOVED: _recursively_process_components function - redundant with ModuleWrapper functionality

def _create_card_with_hybrid_approach(
    card_component: Any,
    params: Dict[str, Any],
    sections: List[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Create a card using the hybrid approach with RECURSIVE component processing.
    
    This approach recursively processes all parameters to find and convert nested
    components (like buttons, images, etc.) using to_dict() methods before
    creating the main card component.
    
    Args:
        card_component: Any component found by semantic search
        params: Parameters for the card (header, etc.)
        sections: Optional sections to add directly
        
    Returns:
        Card in Google Chat API format
    """
    try:
        logger.info(f"🔧 Hybrid approach with recursive processing: {list(params.keys())}")
        
        # DIRECT BUTTON PROCESSING: Handle button conversion directly in hybrid approach
        processed_params = dict(params)  # Copy params
        
        # Process buttons if they exist
        if "buttons" in params and isinstance(params["buttons"], list):
            processed_buttons = []
            for btn_data in params["buttons"]:
                if isinstance(btn_data, dict):
                    # Convert to proper Google Chat format
                    converted_btn = {
                        'text': btn_data.get('text', 'Button')
                    }
                    
                    # Handle onclick action
                    onclick_action = (btn_data.get('onclick_action') or
                                    btn_data.get('action') or
                                    btn_data.get('url'))
                    if onclick_action:
                        converted_btn['onClick'] = {
                            'openLink': {
                                'url': onclick_action
                            }
                        }
                    
                    # CRITICAL FIX: Use correct 'type' field for button styling (not 'style')
                    btn_type = btn_data.get('type')
                    if btn_type in ['FILLED', 'FILLED_TONAL', 'OUTLINED', 'BORDERLESS']:
                        converted_btn['type'] = btn_type
                        logger.info(f"🎨 Added button type: {btn_type}")
                    
                    processed_buttons.append(converted_btn)
                    logger.info(f"🔄 Converted button: {converted_btn}")
            
            processed_params["buttons"] = processed_buttons
            logger.info(f"✅ Button processing complete: {len(processed_buttons)} buttons")
        
        # TRUST _create_card_from_component - it handles any component type intelligently
        created_component = _create_card_from_component(card_component, processed_params)
        
        if created_component is None:
            logger.info("⚠️ Component creation returned None, building card from processed params")
            # Build card structure from processed params directly
            card_dict = _build_card_structure_from_params(processed_params, sections)
        else:
            logger.info(f"✅ Component created: {type(created_component)}")
            
            # Try to use the component's to_dict() if available
            if hasattr(created_component, 'to_dict'):
                component_dict = created_component.to_dict()
                logger.info("✅ Used component.to_dict() after recursive processing")
                
                # Check if this looks like a full card (has sections) or a widget
                if "sections" in component_dict:
                    # This is a full card - use it directly
                    card_dict = component_dict
                    logger.info("🎯 Component is a full Card, using directly")
                else:
                    # This is a widget - incorporate it into a proper card structure
                    logger.info("🧩 Component is a widget, incorporating into card structure")
                    card_dict = _build_card_with_widget_component(created_component, processed_params, sections)
                    
            elif isinstance(created_component, dict):
                # Component returned a dict - check if it's a full card or widget
                if "sections" in created_component:
                    card_dict = created_component
                    logger.info("🎯 Component dict is a full Card, using directly")
                else:
                    logger.info("🧩 Component dict is a widget, incorporating into card structure")
                    card_dict = _build_card_with_widget_dict(created_component, processed_params, sections)
                    
            else:
                # Component doesn't have to_dict() - try to use it as a widget
                logger.info("🧩 Component has no to_dict(), treating as widget and building card structure")
                card_dict = _build_card_with_raw_component(created_component, processed_params, sections)
        
        # Generate a unique card ID
        card_id = f"hybrid_card_{int(time.time())}_{hash(str(processed_params)) % 10000}"
        
        # Create the final card dictionary
        result = {
            "cardId": card_id,
            "card": card_dict
        }
        
        logger.info(f"✅ Hybrid approach created card with structure: {list(card_dict.keys())}")
        return result
    
    except Exception as e:
        logger.error(f"❌ Failed to create card with hybrid approach: {e}", exc_info=True)
        
        # Create a fallback card using processed_params if available
        fallback_params = locals().get('processed_params', params)
        return {
            "cardId": f"fallback_{int(time.time())}",
            "card": {
                "header": {
                    "title": fallback_params.get("title", "Fallback Card"),
                    "subtitle": fallback_params.get("subtitle", "Error occurred during card creation")
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


def _build_simple_card_structure(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build a simple card structure when no ModuleWrapper components are found.
    
    SIMPLIFIED: This replaces complex transformation logic with a simple, reliable approach.
    
    Args:
        params: Card parameters (title, text, buttons, etc.)
        
    Returns:
        Google Chat API format card with cardId
    """
    card_dict = _build_card_structure_from_params(params)
    
    return {
        "cardId": f"simple_card_{int(time.time())}_{hash(str(params)) % 10000}",
        "card": card_dict
    }

def _validate_card_content(card_dict: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Validate that a card has actual renderable content for Google Chat.
    
    Args:
        card_dict: The card dictionary to validate
        
    Returns:
        Tuple of (is_valid, list_of_issues)
    """
    issues = []
    
    # Check if card has any content at all
    if not card_dict:
        issues.append("Card dictionary is empty")
        return False, issues
    
    # Check header content
    header_has_content = False
    if "header" in card_dict and isinstance(card_dict["header"], dict):
        header = card_dict["header"]
        if header.get("title") and header["title"].strip():
            header_has_content = True
        elif header.get("subtitle") and header["subtitle"].strip():
            header_has_content = True
    
    # Check sections content
    sections_have_content = False
    if "sections" in card_dict and isinstance(card_dict["sections"], list):
        for section_idx, section in enumerate(card_dict["sections"]):
            if not isinstance(section, dict):
                issues.append(f"Section {section_idx} is not a dictionary")
                continue
                
            if "widgets" not in section:
                issues.append(f"Section {section_idx} has no widgets")
                continue
                
            widgets = section["widgets"]
            if not isinstance(widgets, list):
                issues.append(f"Section {section_idx} widgets is not a list")
                continue
                
            if len(widgets) == 0:
                issues.append(f"Section {section_idx} has empty widgets list")
                continue
            
            # Check each widget for actual content
            section_has_content = False
            for widget_idx, widget in enumerate(widgets):
                if not isinstance(widget, dict):
                    issues.append(f"Section {section_idx}, widget {widget_idx} is not a dictionary")
                    continue
                
                # Check for text content
                if "textParagraph" in widget:
                    text_content = widget["textParagraph"].get("text", "").strip()
                    if text_content:
                        section_has_content = True
                
                # Check for image content
                elif "image" in widget:
                    image_url = widget["image"].get("imageUrl", "").strip()
                    if image_url:
                        section_has_content = True
                
                # Check for button content
                elif "buttonList" in widget:
                    buttons = widget["buttonList"].get("buttons", [])
                    if isinstance(buttons, list) and len(buttons) > 0:
                        for button in buttons:
                            if isinstance(button, dict) and button.get("text", "").strip():
                                section_has_content = True
                                break
                
                # Check other widget types
                elif any(key in widget for key in ["decoratedText", "selectionInput", "textInput", "divider"]):
                    section_has_content = True
            
            if section_has_content:
                sections_have_content = True
    else:
        issues.append("Card has no sections or sections is not a list")
    
    # Card must have either header content OR section content
    has_content = header_has_content or sections_have_content
    
    if not has_content:
        issues.append("Card has no renderable content (empty header and empty/missing sections)")
    
    return has_content, issues

def _build_card_structure_from_params(params: Dict[str, Any], sections: List[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Build card structure directly from parameters when no component is available."""
    card_dict = {}
    
    # CRITICAL FIX: Handle both flat and nested header structures
    header = {}
    
    # Check if params has a nested "header" object
    if "header" in params and isinstance(params["header"], dict):
        header_data = params["header"]
        if "title" in header_data:
            header["title"] = header_data["title"]
        if "subtitle" in header_data:
            header["subtitle"] = header_data["subtitle"]
    else:
        # Handle flat structure (title/subtitle directly in params)
        if "title" in params:
            header["title"] = params["title"]
        if "subtitle" in params:
            header["subtitle"] = params["subtitle"]
    
    # Only add header if we have title or subtitle
    if header:
        card_dict["header"] = header
        logger.info(f"✅ Built header: {header}")
    
    # Handle sections
    if sections:
        card_dict["sections"] = sections
    else:
        widgets = []
        
        # Add text widget if provided
        if "text" in params:
            widgets.append({
                "textParagraph": {
                    "text": params["text"]
                }
            })
            logger.info(f"✅ Added text widget: {params['text'][:50]}...")
        
        # Add image widget if provided
        if "image_url" in params:
            image_widget = {
                "image": {
                    "imageUrl": params["image_url"]
                }
            }
            # Add alt text if provided
            if "image_alt_text" in params:
                image_widget["image"]["altText"] = params["image_alt_text"]
            widgets.append(image_widget)
            logger.info(f"✅ Added image widget: {params['image_url']}")
        
        # Add buttons widget if provided
        if "buttons" in params and isinstance(params["buttons"], list):
            button_widgets = []
            for button_data in params["buttons"]:
                if isinstance(button_data, dict):
                    # CRITICAL FIX: Check if button is already processed (has onClick)
                    if "onClick" in button_data:
                        # Button already processed by hybrid approach - use as-is
                        button_widget = button_data.copy()
                        logger.info(f"✅ Using pre-processed button: {button_widget}")
                    else:
                        # Button not processed yet - process it now
                        button_widget = {"text": button_data.get("text", "Button")}
                        
                        # Handle various onclick formats
                        onclick_url = (button_data.get("onclick_action") or
                                     button_data.get("action") or
                                     button_data.get("url"))
                        if onclick_url:
                            button_widget["onClick"] = {
                                "openLink": {"url": onclick_url}
                            }
                        
                        # CRITICAL FIX: Use correct 'type' field for button styling (not 'style')
                        btn_type = button_data.get('type')
                        if btn_type in ['FILLED', 'FILLED_TONAL', 'OUTLINED', 'BORDERLESS']:
                            button_widget['type'] = btn_type
                            logger.info(f"🎨 Added button type: {btn_type}")
                        
                        logger.info(f"✅ Processed new button: {button_widget}")
                    
                    button_widgets.append(button_widget)
            
            if button_widgets:
                widgets.append({
                    "buttonList": {
                        "buttons": button_widgets
                    }
                })
        
        # CRITICAL FIX: Don't create empty sections - ensure we have some content
        if not widgets and not header:
            # Fallback: add a basic text widget to prevent completely empty card
            widgets.append({
                "textParagraph": {
                    "text": "Empty card - no content provided"
                }
            })
            logger.warning("⚠️ Created fallback text widget for empty card")
        
        # Always create sections even if no widgets (required for valid card)
        card_dict["sections"] = [{"widgets": widgets}]
        logger.info(f"✅ Built {len(widgets)} widgets in sections")
    
    # VALIDATE CARD CONTENT before returning
    is_valid, issues = _validate_card_content(card_dict)
    if not is_valid:
        logger.error(f"❌ CARD CONTENT VALIDATION FAILED: {issues}")
        logger.error(f"❌ Invalid card structure: {json.dumps(card_dict, indent=2)}")
        
        # Add error information to card for debugging
        card_dict.setdefault("_debug_info", {})["validation_issues"] = issues
    else:
        logger.info("✅ Card content validation passed")
    
    logger.info(f"✅ Final card structure keys: {list(card_dict.keys())}")
    return card_dict


def _universal_component_unpacker(component_data: Any, context: str = "component") -> List[Dict[str, Any]]:
    """
    Universal component unpacker that recursively extracts all widget data
    from any component's to_dict() output and converts to Google Chat format.
    
    ENHANCED: Now properly handles advanced widgets like DecoratedText, preserving their structure.
    """
    widgets = []
    logger.info(f"🔓 Universal unpacking: {context} data: {component_data}")
    
    if not component_data:
        return widgets
        
    if isinstance(component_data, dict):
        # CRITICAL FIX: Check for already-valid Google Chat widget types FIRST
        # This prevents destructive conversion of advanced widgets to simple text
        valid_widget_types = {
            'textParagraph', 'image', 'decoratedText', 'buttonList', 'selectionInput',
            'textInput', 'dateTimePicker', 'divider', 'grid', 'columns', 'chipList'
        }
        
        # If the component data already contains a valid widget type, preserve it
        widget_type_found = None
        for widget_type in valid_widget_types:
            if widget_type in component_data:
                widget_type_found = widget_type
                break
        
        if widget_type_found:
            # This is already a properly formatted Google Chat widget - use it directly
            widgets.append(component_data)
            logger.info(f"✅ Preserved valid {widget_type_found} widget from {context}")
            return widgets
        
        # ENHANCED: Check for DecoratedText patterns specifically
        # DecoratedText components often have topLabel, bottomLabel, text, button, etc.
        if any(key in component_data for key in ['topLabel', 'top_label', 'bottomLabel', 'bottom_label']):
            decorated_text_widget = {"decoratedText": {}}
            
            # Map common fields to decoratedText format
            if "text" in component_data:
                decorated_text_widget["decoratedText"]["text"] = component_data["text"]
            
            # Handle labels
            top_label = component_data.get("topLabel", component_data.get("top_label"))
            if top_label:
                decorated_text_widget["decoratedText"]["topLabel"] = top_label
                
            bottom_label = component_data.get("bottomLabel", component_data.get("bottom_label"))
            if bottom_label:
                decorated_text_widget["decoratedText"]["bottomLabel"] = bottom_label
            
            # Handle button
            button_data = component_data.get("button")
            if button_data and isinstance(button_data, dict):
                button_widget = {"text": button_data.get("text", "Button")}
                action_url = (button_data.get("onClick", {}).get("openLink", {}).get("url") or
                            button_data.get("onclick_action") or button_data.get("url") or button_data.get("action"))
                if action_url:
                    button_widget["onClick"] = {"openLink": {"url": action_url}}
                decorated_text_widget["decoratedText"]["button"] = button_widget
            
            widgets.append(decorated_text_widget)
            logger.info(f"✅ Created decoratedText widget from {context}")
            return widgets
        
        # Look for button patterns (existing logic)
        if "buttons" in component_data or "button" in component_data:
            buttons_data = component_data.get("buttons", [component_data.get("button")])
            if buttons_data and buttons_data != [None]:
                button_widgets = []
                for btn in buttons_data if isinstance(buttons_data, list) else [buttons_data]:
                    if isinstance(btn, dict):
                        button_widget = {"text": btn.get("text", btn.get("label", "Button"))}
                        # Look for various action patterns
                        action_url = (btn.get("onClick", {}).get("openLink", {}).get("url") or
                                    btn.get("onclick_action") or btn.get("url") or btn.get("action"))
                        if action_url:
                            button_widget["onClick"] = {"openLink": {"url": action_url}}
                        button_widgets.append(button_widget)
                
                if button_widgets:
                    widgets.append({"buttonList": {"buttons": button_widgets}})
                    logger.info(f"✅ Unpacked {len(button_widgets)} buttons from {context}")
        
        # Look for text patterns (ONLY if not already processed as advanced widget)
        elif "text" in component_data and not any(key in component_data for key in ['topLabel', 'top_label', 'bottomLabel', 'bottom_label']):
            widgets.append({"textParagraph": {"text": component_data["text"]}})
            logger.info(f"✅ Unpacked simple text from {context}")
            
        # Look for image patterns
        elif "imageUrl" in component_data or "image_url" in component_data:
            image_url = component_data.get("imageUrl", component_data.get("image_url"))
            image_widget = {"image": {"imageUrl": image_url}}
            alt_text = component_data.get("altText", component_data.get("alt_text"))
            if alt_text:
                image_widget["image"]["altText"] = alt_text
            widgets.append(image_widget)
            logger.info(f"✅ Unpacked image from {context}")
        
        # Recursively process nested structures (but skip already-processed keys)
        processed_keys = {"text", "buttons", "button", "imageUrl", "image_url", "altText", "alt_text",
                         "topLabel", "top_label", "bottomLabel", "bottom_label"}
        for key, value in component_data.items():
            if key not in processed_keys and not any(wtype in key for wtype in valid_widget_types):
                nested_widgets = _universal_component_unpacker(value, f"{context}.{key}")
                widgets.extend(nested_widgets)
    
    elif isinstance(component_data, list):
        # Process list items
        for i, item in enumerate(component_data):
            nested_widgets = _universal_component_unpacker(item, f"{context}[{i}]")
            widgets.extend(nested_widgets)
    
    return widgets

def _build_card_with_widget_component(component: Any, params: Dict[str, Any], sections: List[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Build card structure incorporating a widget component with to_dict()."""
    card_dict = {}
    
    # Handle header from params
    if "title" in params or "subtitle" in params:
        header = {}
        if "title" in params:
            header["title"] = params["title"]
        if "subtitle" in params:
            header["subtitle"] = params["subtitle"]
        card_dict["header"] = header
    
    # Use provided sections or build from widget component
    if sections:
        card_dict["sections"] = sections
    else:
        widgets = []
        
        # Add text first if provided
        if "text" in params:
            widgets.append({
                "textParagraph": {
                    "text": params["text"]
                }
            })
        
        # CRITICAL FIX: Add processed buttons from params BEFORE universal unpacker
        # This ensures that buttons processed in hybrid approach are not lost
        if "buttons" in params and isinstance(params["buttons"], list):
            logger.info(f"🔧 HYBRID APPROACH: Adding {len(params['buttons'])} processed buttons to card structure")
            button_widgets = []
            for button_data in params["buttons"]:
                if isinstance(button_data, dict) and button_data.get("text"):
                    logger.info(f"🔧 Adding processed button: {button_data}")
                    button_widgets.append(button_data)
            
            if button_widgets:
                widgets.append({
                    "buttonList": {
                        "buttons": button_widgets
                    }
                })
                logger.info(f"✅ Added buttonList widget with {len(button_widgets)} buttons from processed params")
        
        # TRUST UNIVERSAL UNPACKER: Extract all widget data from component
        component_dict = component.to_dict()
        component_name = type(component).__name__
        
        logger.info(f"🔓 Using trusted universal unpacker for component: {component_name}")
        unpacked_widgets = _universal_component_unpacker(component_dict, component_name)
        
        # Filter out duplicate widgets if we already have them from processed params
        filtered_unpacked = []
        has_text_from_params = "text" in params
        has_buttons_from_params = "buttons" in params and isinstance(params["buttons"], list) and len(params["buttons"]) > 0
        
        for widget in unpacked_widgets:
            # Skip text widgets from component if we already have text from params
            if has_text_from_params and isinstance(widget, dict) and "textParagraph" in widget:
                logger.info("🔧 Skipping duplicate text widget from component (using params text instead)")
                continue
            
            # CRITICAL FIX: Skip button widgets from component if we already have processed buttons from params
            if has_buttons_from_params and isinstance(widget, dict) and "buttonList" in widget:
                logger.info("🔧 Skipping duplicate button widget from component (using processed params buttons instead)")
                continue
            
            filtered_unpacked.append(widget)
        
        widgets.extend(filtered_unpacked)
        logger.info(f"✅ Universal unpacker extracted {len(filtered_unpacked)} widgets from {component_name} (filtered {len(unpacked_widgets) - len(filtered_unpacked)} duplicates)")
        
        card_dict["sections"] = [{"widgets": widgets}]
    
    return card_dict


def _build_card_with_widget_dict(component_dict: Dict[str, Any], params: Dict[str, Any], sections: List[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Build card structure incorporating a widget dictionary."""
    card_dict = {}
    
    # Handle header from params
    if "title" in params or "subtitle" in params:
        header = {}
        if "title" in params:
            header["title"] = params["title"]
        if "subtitle" in params:
            header["subtitle"] = params["subtitle"]
        card_dict["header"] = header
    
    # Use provided sections or build from widget dict
    if sections:
        card_dict["sections"] = sections
    else:
        widgets = []
        
        # Add text first if provided in params
        if "text" in params:
            widgets.append({
                "textParagraph": {
                    "text": params["text"]
                }
            })
        
        # Validate the component dict and ensure it maps to valid Google Chat widget types
        valid_widget_types = {
            'textParagraph', 'image', 'decoratedText', 'buttonList', 'selectionInput',
            'textInput', 'dateTimePicker', 'divider', 'grid', 'columns'
        }
        
        # Check if the dict looks like a simple text component
        if "text" in component_dict and len(component_dict) <= 2:
            widgets.append({
                "textParagraph": component_dict
            })
        # Check if the dict has a valid widget type as a key
        elif any(key in valid_widget_types for key in component_dict.keys()):
            widgets.append(component_dict)
        else:
            # Unknown component dict - create a safe fallback
            logger.warning(f"⚠️ Unknown component dict structure: {list(component_dict.keys())}, creating fallback")
            widgets.append({
                "textParagraph": {
                    "text": f"Component data: {str(component_dict)[:100]}..."
                }
            })
        
        card_dict["sections"] = [{"widgets": widgets}]
    
    return card_dict


def _build_card_with_raw_component(component: Any, params: Dict[str, Any], sections: List[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Build card structure with a raw component that has no to_dict()."""
    card_dict = {}
    
    # Handle header from params
    if "title" in params or "subtitle" in params:
        header = {}
        if "title" in params:
            header["title"] = params["title"]
        if "subtitle" in params:
            header["subtitle"] = params["subtitle"]
        card_dict["header"] = header
    
    # Use provided sections or build basic structure
    if sections:
        card_dict["sections"] = sections
    else:
        widgets = []
        
        # Add text if provided
        if "text" in params:
            widgets.append({
                "textParagraph": {
                    "text": params["text"]
                }
            })
        
        # Try to extract useful data from the raw component
        if hasattr(component, '__dict__'):
            component_data = component.__dict__
            if component_data:
                # Try to create a widget from component attributes
                if "text" in component_data:
                    widgets.append({
                        "textParagraph": {
                            "text": str(component_data["text"])
                        }
                    })
        
        # Add buttons if provided in params
        if "buttons" in params:
            button_widgets = []
            for button_data in params["buttons"]:
                button_widget = {"text": button_data.get("text", "Button")}
                if "onclick_action" in button_data:
                    button_widget["onClick"] = {
                        "openLink": {"url": button_data["onclick_action"]}
                    }
                button_widgets.append(button_widget)
            
            widgets.append({
                "buttonList": {
                    "buttons": button_widgets
                }
            })
        
        card_dict["sections"] = [{"widgets": widgets}]
    
    return card_dict

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

# REMOVED: _transform_card_params_to_google_format function - replaced with simple _build_simple_card_structure

def _snake_to_camel(snake_str: str) -> str:
    """Convert snake_case string to camelCase with caching for performance."""
    global _snake_to_camel_cache
    
    if snake_str in _snake_to_camel_cache:
        return _snake_to_camel_cache[snake_str]
    
    if "_" not in snake_str:
        result = snake_str
    else:
        components = snake_str.split('_')
        result = components[0] + ''.join(word.capitalize() for word in components[1:])
    
    _snake_to_camel_cache[snake_str] = result
    return result

def _convert_field_names_to_camel_case(obj: Any) -> Any:
    """Convert snake_case field names to camelCase recursively."""
    if isinstance(obj, dict):
        converted = {}
        for key, value in obj.items():
            # Convert snake_case to camelCase
            camel_key = _snake_to_camel(key)
            if camel_key != key:
                logger.info(f"FIELD CONVERSION: {key} -> {camel_key}")
            converted[camel_key] = _convert_field_names_to_camel_case(value)
        return converted
    elif isinstance(obj, list):
        return [_convert_field_names_to_camel_case(item) for item in obj]
    else:
        return obj

def _convert_field_names_to_snake_case(obj: Any) -> Any:
    """Convert camelCase field names to snake_case recursively for webhook API."""
    if isinstance(obj, dict):
        converted = {}
        for key, value in obj.items():
            # Convert camelCase to snake_case
            snake_key = _camel_to_snake(key)
            if snake_key != key:
                logger.info(f"WEBHOOK CONVERSION: {key} -> {snake_key}")
            converted[snake_key] = _convert_field_names_to_snake_case(value)
        return converted
    elif isinstance(obj, list):
        return [_convert_field_names_to_snake_case(item) for item in obj]
    else:
        return obj

def _camel_to_snake(camel_str: str) -> str:
    """Convert camelCase string to snake_case with caching for performance."""
    global _camel_to_snake_cache
    
    if camel_str in _camel_to_snake_cache:
        return _camel_to_snake_cache[camel_str]
    
    import re
    # Insert underscores before capital letters
    snake_str = re.sub('([a-z0-9])([A-Z])', r'\1_\2', camel_str)
    result = snake_str.lower()
    
    _camel_to_snake_cache[camel_str] = result
    return result

# REMOVED: _build_card_with_framework_components function - redundant with ModuleWrapper functionality


# REMOVED: _create_advanced_button_with_framework function - trusting ModuleWrapper for all button creation

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
        description="Send any type of card to Google Chat using natural language description with advanced NLP parameter extraction",
        tags={"chat", "card", "dynamic", "google", "unified", "nlp"},
        annotations={
            "title": "Send Dynamic Card with NLP",
            "description": "Unified tool for sending Google Chat Cards v2 with natural language processing for complex card creation. Automatically extracts card structure from descriptions including sections, decoratedText widgets, icons, and buttons.",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
            "examples": [
                {
                    "description": "Simple text card",
                    "card_description": "simple notification",
                    "card_params": {"title": "Alert", "text": "System update complete"}
                },
                {
                    "description": "Natural language card with sections",
                    "card_description": "Create a monitoring dashboard with title 'Server Status' and three sections: 1. 'Health Check' section with decoratedText 'All Systems Go' with topLabel 'Status' and green check icon 2. 'Performance' section with decoratedText 'Response Time: 120ms' with topLabel 'API Latency' 3. 'Actions' section with a button 'View Logs' linking to https://logs.example.com",
                    "card_params": {}
                },
                {
                    "description": "Dashboard with decoratedText widgets",
                    "card_description": "Create a project dashboard with sections showing metrics: first section 'Build Status' with decoratedText 'Passing' with topLabel 'Latest Build' and green check icon, second section 'Coverage' with decoratedText '92%' with topLabel 'Code Coverage' and chart icon",
                    "card_params": {"title": "Project Dashboard"}
                },
                {
                    "description": "Card with collapsible sections",
                    "card_description": "Create a report card with collapsible sections: 'Summary' section (collapsible) with text about Q4 results, 'Details' section with a grid of metrics, and 'Actions' section with buttons 'Download PDF' and 'Share Report'",
                    "card_params": {}
                }
            ],
            "natural_language_features": [
                "Automatic extraction of card title, subtitle, and text from descriptions",
                "Support for numbered/bulleted sections (e.g., '1. Section Name' or '- Section Name')",
                "DecoratedText widget creation with topLabel, bottomLabel, and icons",
                "Icon mapping from natural language (e.g., 'green check' → CHECK_CIRCLE icon)",
                "Button extraction with text and onClick actions from URLs",
                "Grid layouts and column arrangements from descriptions",
                "Collapsible section headers",
                "HTML content formatting",
                "Switch controls and interactive elements"
            ],
            "limitations": [
                "Images cannot be placed in card headers - they become widgets in sections",
                "Maximum 100 widgets per section, 6 buttons per buttonList",
                "Field length limits: title/subtitle (200 chars), text (4000 chars)",
                "Icon mapping supports 20+ common icons with color modifiers"
            ]
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
        Send any type of card to Google Chat using natural language description with enhanced NLP.
        
        This unified tool combines ModuleWrapper semantic search with advanced NLP parameter extraction
        to create complex Google Chat cards from natural language descriptions. The NLP parser can
        extract complete card structures including sections, decoratedText widgets, icons, and buttons.
        
        ## Enhanced NLP Features:
        - **Automatic parameter extraction** from natural language descriptions
        - **Section parsing** from numbered (1., 2.) or bulleted (-, •) lists
        - **DecoratedText creation** with topLabel, bottomLabel, and icons
        - **Icon mapping** from descriptions like "green check" → CHECK_CIRCLE
        - **Button extraction** with text and onClick actions from URLs
        - **Grid layouts** and column arrangements
        - **Collapsible sections** with header configuration
        - **HTML content** formatting support
        - **Switch controls** and interactive elements
        
        ## Natural Language Examples:
        ```
        "Create a monitoring dashboard with title 'Server Status' and three sections:
        1. 'Health Check' section with decoratedText 'All Systems Go' with topLabel 'Status' and green check icon
        2. 'Performance' section with decoratedText 'Response Time: 120ms' with topLabel 'API Latency'
        3. 'Actions' section with a button 'View Logs' linking to https://logs.example.com"
        ```
        
        ## Supported Card Elements:
        - **Header**: title, subtitle (max 200 chars each)
        - **Sections**: Multiple sections with optional headers and collapsibility
        - **Text widgets**: textParagraph with formatting (max 4000 chars)
        - **DecoratedText**: Rich text with labels, icons, buttons, switches
        - **Buttons**: Up to 6 per buttonList with onClick actions
        - **Images**: Image widgets with URLs and alt text
        - **Icons**: 20+ mapped icons (CHECK_CIRCLE, STAR, ERROR, etc.)
        - **Grids**: Multi-column layouts with nested widgets
        - **HTML**: Formatted HTML content in text widgets
        
        ## Icon Mappings (Natural Language → Google Chat Icon):
        - "check", "green check", "success" → CHECK_CIRCLE
        - "error", "red x", "failure" → ERROR
        - "warning", "yellow warning" → WARNING
        - "info", "information" → INFO
        - "star", "favorite" → STAR
        - "person", "user" → PERSON
        - "clock", "time" → CLOCK
        - "email", "mail" → EMAIL
        - And 12+ more mappings...
        
        ## Technical Implementation:
        - **NLP Parser**: Extracts parameters from card_description using regex patterns
        - **Parameter Merging**: NLP-extracted params merged with user-provided card_params
        - **ModuleWrapper Search**: Finds appropriate card components via semantic search
        - **Hybrid Approach**: Combines component-based and parameter-based creation
        - **Validation**: Automatic field length limits and structure validation
        - **Error Recovery**: Always returns valid card structure with fallbacks
        
        Args:
            user_google_email: The user's Google email address for authentication
            space_id: The Google Chat space ID to send the card to
            card_description: Natural language description of the card structure and content.
                            Can include sections, widgets, icons, buttons, and formatting.
            card_params: Optional dict of explicit parameters (title, text, buttons, etc.).
                        These override any NLP-extracted parameters.
            thread_key: Optional thread key for threaded message replies
            webhook_url: Optional webhook URL for direct delivery (bypasses API auth)
            
        Returns:
            Success/failure message with details about the sent card and extraction type
            
        Examples:
            # Simple card with explicit params
            await send_dynamic_card(
                user_google_email="user@example.com",
                space_id="spaces/AAAAA",
                card_description="simple notification",
                card_params={"title": "Alert", "text": "System update complete"}
            )
            
            # Complex card with NLP extraction
            await send_dynamic_card(
                user_google_email="user@example.com",
                space_id="spaces/AAAAA",
                card_description="Create a dashboard with sections: 1. 'Status' with green check..."
            )
        """
        try:
            logger.info(f"🔍 Finding card component for: {card_description}")
            
            # Default parameters if not provided
            if card_params is None:
                card_params = {}
            
            # ENHANCED NLP INTEGRATION: Parse natural language description to extract parameters
            try:
                logger.info(f"🧠 Parsing natural language description: '{card_description}'")
                nlp_extracted_params = parse_enhanced_natural_language_description(card_description)
                
                if nlp_extracted_params:
                    logger.info(f"✅ NLP extracted parameters: {list(nlp_extracted_params.keys())}")
                    
                    # Merge NLP extracted parameters with user-provided card_params
                    # User-provided card_params take priority over NLP-extracted ones
                    merged_params = {}
                    merged_params.update(nlp_extracted_params)  # Add NLP extracted params first
                    merged_params.update(card_params)  # User params override NLP params
                    
                    card_params = merged_params
                else:
                    logger.info("📝 No parameters extracted from natural language description")
                    
            except Exception as nlp_error:
                logger.warning(f"⚠️ NLP parsing failed, continuing with original card_params: {nlp_error}")
            
            # Initialize default best_match to prevent UnboundLocalError
            best_match = {"type": "fallback", "name": "simple_fallback", "score": 0.0}
            google_format_card = None
            
            # Find card components using ModuleWrapper
            results = await _find_card_component(card_description)
            
            if results:
                # Get the best match component
                best_match = results[0]
                component = best_match.get("component")
                
                # CRITICAL FIX: Check if component is actually usable (not a module)
                if component and not inspect.ismodule(component):
                    logger.info(f"✅ Found valid component: {best_match.get('path')} (score: {best_match.get('score'):.4f})")
                    
                    # TRUST MODULEWRAPPER: Use hybrid approach for component-based card creation
                    logger.info("🔧 Using trusted ModuleWrapper with hybrid approach")
                    google_format_card = _create_card_with_hybrid_approach(
                        card_component=component,
                        params=card_params,
                        sections=None
                    )
                    logger.info("✅ Successfully created card using ModuleWrapper hybrid approach")
                else:
                    logger.warning(f"⚠️ Component is module or invalid, using simple card structure")
                    google_format_card = _build_simple_card_structure(card_params)
                    best_match = {"type": "simple_fallback", "name": "simple_card", "score": 0.0}
            else:
                logger.warning(f"⚠️ No search results found for: {card_description}, using simple card structure")
                google_format_card = _build_simple_card_structure(card_params)
                best_match = {"type": "simple_fallback", "name": "simple_card", "score": 0.0}
            
            if not google_format_card:
                return f"❌ Failed to create card structure"
            
            # Create message payload
            message_obj = Message()
            
            # Add text if provided
            if "text" in card_params:
                message_obj.text = card_params["text"]
            
            # Add card to message - handle both single card object and wrapped format
            if isinstance(google_format_card, dict) and "cardsV2" in google_format_card:
                # Old format with wrapper - extract cards
                for card in google_format_card["cardsV2"]:
                    message_obj.cards_v2.append(card)
            else:
                # New format - single card object
                message_obj.cards_v2.append(google_format_card)
            
            # Render message
            message_body = message_obj.render()
            
            # Fix Card Framework v2 field name issue: ensure proper cards_v2 format for webhook
            # The Google Chat webhook API expects snake_case (cards_v2), NOT camelCase (cardsV2)
            if "cards_v_2" in message_body:
                message_body["cards_v2"] = message_body.pop("cards_v_2")
            # Convert camelCase back to snake_case for webhook delivery (webhook API expects snake_case)
            if "cardsV2" in message_body:
                message_body["cards_v2"] = message_body.pop("cardsV2")
            
            # CRITICAL DEBUGGING: Pre-validate card content before sending
            final_card = google_format_card.get("card", {}) if isinstance(google_format_card, dict) else {}
            is_valid_content, content_issues = _validate_card_content(final_card)
            
            if not is_valid_content:
                logger.error(f"🚨 BLANK MESSAGE PREVENTION: Card has no renderable content!")
                logger.error(f"🚨 Content validation issues: {content_issues}")
                logger.error(f"🚨 Card params received: {json.dumps(card_params, indent=2)}")
                logger.error(f"🚨 Card structure created: {json.dumps(google_format_card, indent=2)}")
                
                # Return an error instead of sending a blank card
                return f"❌ Prevented sending blank card. Issues: {'; '.join(content_issues)}. Check card_params and description."
            
            logger.info("✅ Pre-send validation passed - card has renderable content")

            # Choose delivery method based on webhook_url
            if webhook_url:
                # CRITICAL FIX: Recursively convert ALL field names to snake_case for webhook API
                # The Google Chat webhook API requires snake_case field names throughout the entire payload
                logger.info("🔧 Converting ALL camelCase fields to snake_case for webhook API compatibility")
                webhook_message_body = _convert_field_names_to_snake_case(message_body)
                
                # ENHANCED DEBUGGING: Log everything before sending
                logger.info(f"🔄 ENHANCED DEBUG - Sending via webhook URL: {webhook_url}")
                logger.info(f"🧪 CARD DEBUG INFO:")
                logger.info(f"  - Description: '{card_description}'")
                logger.info(f"  - Params keys: {list(card_params.keys())}")
                logger.info(f"  - Component found: {bool(results)}")
                logger.info(f"  - Best match: {best_match.get('name', 'N/A')} (score: {best_match.get('score', 0):.3f})")
                logger.info(f"  - Card type: {best_match.get('type', 'unknown')}")
                
                # Log original card structure
                logger.info(f"📊 ORIGINAL CARD STRUCTURE:")
                logger.info(f"   Keys: {list(google_format_card.keys()) if isinstance(google_format_card, dict) else 'Not a dict'}")
                if isinstance(google_format_card, dict) and "card" in google_format_card:
                    card_content = google_format_card["card"]
                    logger.info(f"   Card keys: {list(card_content.keys()) if isinstance(card_content, dict) else 'Not a dict'}")
                    if isinstance(card_content, dict):
                        if "header" in card_content:
                            header = card_content["header"]
                            logger.info(f"   Header: title='{header.get('title', 'N/A')}', subtitle='{header.get('subtitle', 'N/A')}'")
                        if "sections" in card_content and isinstance(card_content["sections"], list):
                            logger.info(f"   Sections: {len(card_content['sections'])} section(s)")
                            for i, section in enumerate(card_content["sections"]):
                                if isinstance(section, dict) and "widgets" in section:
                                    widgets = section["widgets"]
                                    logger.info(f"     Section {i}: {len(widgets) if isinstance(widgets, list) else 0} widget(s)")
                                    if isinstance(widgets, list):
                                        for j, widget in enumerate(widgets):
                                            if isinstance(widget, dict):
                                                widget_type = next(iter(widget.keys())) if widget else "empty"
                                                logger.info(f"       Widget {j}: type={widget_type}")

                # Log final webhook payload
                logger.info(f"🔧 FINAL WEBHOOK PAYLOAD:")
                logger.info(f"📋 Message JSON: {json.dumps(webhook_message_body, indent=2)}")
                
                import requests
                
                # Log the request details
                logger.info(f"🌐 Making POST request to webhook:")
                logger.info(f"  URL: {webhook_url}")
                logger.info(f"  Headers: {{'Content-Type': 'application/json'}}")
                logger.info(f"  Payload size: {len(json.dumps(webhook_message_body))} characters")
                
                response = requests.post(
                    webhook_url,
                    json=webhook_message_body,
                    headers={'Content-Type': 'application/json'}
                )
                
                # Enhanced response logging
                logger.info(f"🔍 WEBHOOK RESPONSE - Status: {response.status_code}")
                logger.info(f"🔍 WEBHOOK RESPONSE - Headers: {dict(response.headers)}")
                logger.info(f"🔍 WEBHOOK RESPONSE - Body: {response.text}")
                
                # ANALYZE RESPONSE for content issues
                if response.status_code == 200:
                    # Check if response indicates content issues
                    response_text = response.text.lower()
                    if any(keyword in response_text for keyword in ["empty", "blank", "no content", "invalid"]):
                        logger.warning(f"⚠️ SUCCESS but possible content issue - Response: {response.text}")
                        return f"⚠️ Card sent (Status 200) but may appear blank. Response: {response.text}. Card Type: {best_match.get('type')}"
                    else:
                        logger.info(f"✅ Card sent successfully via webhook. Status: {response.status_code}")
                        return f"✅ Card message sent successfully via webhook! Status: {response.status_code}, Card Type: {best_match.get('type')}"
                elif response.status_code == 429:
                    # Handle rate limiting with helpful message
                    logger.warning(f"⚠️ Rate limited by Google Chat API. This indicates successful card formatting but too many requests.")
                    return f"⚠️ Rate limited (429) - Card format is correct but hitting quota limits. Reduce request frequency. Card Type: {best_match.get('type')}"
                else:
                    error_details = {
                        'status': response.status_code,
                        'headers': dict(response.headers),
                        'body': response.text,
                        'message_sent': message_body,
                        'card_validation_issues': content_issues if not is_valid_content else []
                    }
                    logger.error(f"❌ Failed to send card via webhook: {json.dumps(error_details, indent=2)}")
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
    
#     @mcp.tool(
#         name="list_available_card_components",
#         description="List available card components that can be used with send_dynamic_card",
#         tags={"chat", "card", "list", "components", "google"},
#         annotations={
#             "title": "List Card Components",
#             "readOnlyHint": True,
#             "destructiveHint": False,
#             "idempotentHint": True,
#             "openWorldHint": False
#         }
#     )
#     async def list_available_card_components(
#         query: Optional[str] = None,
#         limit: int = 10
#     ) -> CardComponentsResponse:
#         """
#         List available card components that can be used with send_dynamic_card.
        
#         Args:
#             query: Optional search query to filter components
#             limit: Maximum number of components to return
            
#         Returns:
#             CardComponentsResponse: Structured response with available card components
#         """
#         try:
#             # Initialize wrapper if needed
#             if not _card_framework_wrapper:
#                 _initialize_card_framework_wrapper()
                
#             if not _card_framework_wrapper:
#                 return CardComponentsResponse(
#                     components=[],
#                     count=0,
#                     query=query or "all",
#                     error="Card Framework wrapper not available"
#                 )
            
#             # Search for components or list cached types
#             if query:
#                 results = _card_framework_wrapper.search(query, limit=limit)
#             else:
#                 # Use cached card types
#                 if not _card_types_cache:
#                     _cache_card_types()
                
#                 # Flatten results from cache
#                 results = []
#                 for card_type, type_results in _card_types_cache.items():
#                     for result in type_results[:2]:  # Take top 2 from each type
#                         results.append(result)
                
#                 # Limit results
#                 results = results[:limit]
            
#             # Format results as TypedDict
#             components: List[CardComponentInfo] = []
#             for result in results:
#                 component = CardComponentInfo(
#                     name=result.get("name", ""),
#                     path=result.get("path", ""),
#                     type=result.get("type", ""),
#                     score=result.get("score"),
#                     docstring=result.get("docstring", "")[:200]  # Truncate long docstrings
#                 )
#                 components.append(component)
            
#             return CardComponentsResponse(
#                 components=components,
#                 count=len(components),
#                 query=query or "cached card types",
#                 error=None
#             )
            
#         except Exception as e:
#             logger.error(f"❌ Error listing card components: {e}", exc_info=True)
#             return CardComponentsResponse(
#                 components=[],
#                 count=0,
#                 query=query or "all",
#                 error=str(e)
#             )
    
#     @mcp.tool(
#         name="list_card_templates",
#         description="List available card templates stored in Qdrant",
#         tags={"chat", "card", "template", "list", "qdrant"},
#         annotations={
#             "title": "List Card Templates",
#             "readOnlyHint": True,
#             "destructiveHint": False,
#             "idempotentHint": True,
#             "openWorldHint": False
#         }
#     )
#     async def list_card_templates(
#         query: Optional[str] = None,
#         limit: int = 10
#     ) -> CardTemplatesResponse:
#         """
#         List available card templates stored in Qdrant.
        
#         Args:
#             query: Optional search query to filter templates
#             limit: Maximum number of templates to return
            
#         Returns:
#             CardTemplatesResponse: Structured response with available card templates
#         """
#         try:
#             client = _get_qdrant_client()
#             if not client:
#                 return CardTemplatesResponse(
#                     templates=[],
#                     count=0,
#                     query=query or "all templates",
#                     error="Qdrant client not available - cannot list templates"
#                 )
            
#             # Check if collection exists
#             collections = client.get_collections()
#             collection_names = [c.name for c in collections.collections]
            
#             if _card_templates_collection not in collection_names:
#                 return CardTemplatesResponse(
#                     templates=[],
#                     count=0,
#                     query=query or "all templates",
#                     error=f"Collection {_card_templates_collection} does not exist"
#                 )
            
#             # Search for templates if query is provided
#             template_infos: List[CardTemplateInfo] = []
#             if query:
#                 templates = await _find_card_template(query_or_id=query)
#                 for template in templates:
#                     template_info = CardTemplateInfo(
#                         template_id=template.get("template_id", ""),
#                         name=template.get("name", ""),
#                         description=template.get("description", ""),
#                         created_at=template.get("created_at"),
#                         template=template.get("template")
#                     )
#                     template_infos.append(template_info)
#             else:
#                 # List all templates
#                 try:
#                     # Import required modules
#                     from qdrant_client.models import Filter
                    
#                     # Get all templates
#                     search_results = client.scroll(
#                         collection_name=_card_templates_collection,
#                         limit=limit,
#                         with_payload=True,
#                         with_vectors=False
#                     )
                    
#                     # Process results
#                     for point in search_results[0]:
#                         template_info = CardTemplateInfo(
#                             template_id=point.payload.get("template_id", ""),
#                             name=point.payload.get("name", ""),
#                             description=point.payload.get("description", ""),
#                             created_at=point.payload.get("created_at"),
#                             template=point.payload.get("template")
#                         )
#                         template_infos.append(template_info)
                        
#                 except ImportError:
#                     return CardTemplatesResponse(
#                         templates=[],
#                         count=0,
#                         query=query or "all templates",
#                         error="Qdrant client models not available"
#                     )
#                 except Exception as e:
#                     logger.error(f"❌ Error listing templates: {e}", exc_info=True)
#                     return CardTemplatesResponse(
#                         templates=[],
#                         count=0,
#                         query=query or "all templates",
#                         error=str(e)
#                     )
            
#             return CardTemplatesResponse(
#                 templates=template_infos,
#                 count=len(template_infos),
#                 query=query or "all templates",
#                 #  error=None
#             )
            
#         except Exception as e:
#             logger.error(f"❌ Error listing card templates: {e}", exc_info=True)
#             return CardTemplatesResponse(
#                 templates=[],
#                 count=0,
#                 query=query or "all templates",
#                 error=str(e)
#             )
    
#     @mcp.tool(
#         name="get_card_template",
#         description="Get a specific card template from Qdrant by ID or name",
#         tags={"chat", "card", "template", "get", "qdrant"},
#         annotations={
#             "title": "Get Card Template",
#             "readOnlyHint": True,
#             "destructiveHint": False,
#             "idempotentHint": True,
#             "openWorldHint": False
#         }
#     )
#     async def get_card_template(
#         template_id_or_name: str
#     ) -> str:
#         """
#         Get a specific card template from Qdrant by ID or name.
        
#         Args:
#             template_id_or_name: ID or name of the template to retrieve
#                                 (e.g., "4e4a2881-8de2-4adf-bcbd-5fa814c8657a" or "Bullet List Card")
            
#         Returns:
#             JSON string with the template details
#         """
#         try:
#             client = _get_qdrant_client()
#             if not client:
#                 return "❌ Qdrant client not available - cannot get template"
            
#             # Try to find the template using our enhanced function
#             templates = await _find_card_template(query_or_id=template_id_or_name, limit=1)
            
#             if not templates or len(templates) == 0:
#                 return f"❌ Template not found: {template_id_or_name}"
            
#             # Get the template
#             template = templates[0]
            
#             # Format result
#             return json.dumps(template, indent=2)
            
#         except Exception as e:
#             logger.error(f"❌ Error getting card template: {e}", exc_info=True)
#             return f"❌ Error getting card template: {str(e)}"
    
#     @mcp.tool(
#         name="save_card_template",
#         description="Save a card template to Qdrant",
#         tags={"chat", "card", "template", "save", "qdrant"},
#         annotations={
#             "title": "Save Card Template",
#             "readOnlyHint": False,
#             "destructiveHint": False,
#             "idempotentHint": False,
#             "openWorldHint": True
#         }
#     )
#     async def save_card_template(
#         name: str,
#         description: str,
#         template: Dict[str, Any]
#     ) -> str:
#         """
#         Save a card template to Qdrant for future use.
        
#         Args:
#             name: Template name
#             description: Template description
#             template: The card template (dictionary)
            
#         Returns:
#             Template ID if successful
#         """
#         try:
#             template_id = await _store_card_template(name, description, template)
            
#             if not template_id:
#                 return "❌ Failed to save template"
            
#             return f"✅ Template saved successfully! ID: {template_id}"
            
#         except Exception as e:
#             logger.error(f"❌ Error saving card template: {e}", exc_info=True)
#             return f"❌ Error saving card template: {str(e)}"
    
#     @mcp.tool(
#         name="delete_card_template",
#         description="Delete a card template from Qdrant",
#         tags={"chat", "card", "template", "delete", "qdrant"},
#         annotations={
#             "title": "Delete Card Template",
#             "readOnlyHint": False,
#             "destructiveHint": True,
#             "idempotentHint": False,
#             "openWorldHint": False
#         }
#     )
#     async def delete_card_template(
#         template_id: str
#     ) -> str:
#         """
#         Delete a card template from Qdrant.
        
#         Args:
#             template_id: ID of the template to delete
            
#         Returns:
#             Confirmation message
#         """
#         try:
#             client = _get_qdrant_client()
#             if not client:
#                 return "❌ Qdrant client not available - cannot delete template"
            
#             # Check if collection exists
#             try:
#                 collections = client.get_collections()
#                 collection_names = [c.name for c in collections.collections]
                
#                 if _card_templates_collection not in collection_names:
#                     return f"❌ Collection {_card_templates_collection} does not exist"
#             except Exception as coll_error:
#                 logger.error(f"❌ Error checking collections: {coll_error}", exc_info=True)
#                 return f"❌ Error checking collections: {str(coll_error)}"
            
#             # Check if template exists using payload-based search
#             try:
#                 from qdrant_client.models import Filter, FieldCondition, MatchValue
                
#                 # Create filter for template_id in payload
#                 template_id_filter = Filter(
#                     must=[
#                         FieldCondition(
#                             key="payload_type",
#                             match=MatchValue(value="template")
#                         ),
#                         FieldCondition(
#                             key="template_id",
#                             match=MatchValue(value=template_id)
#                         )
#                     ]
#                 )
                
#                 # Search with filter
#                 search_results = client.scroll(
#                     collection_name=_card_templates_collection,
#                     scroll_filter=template_id_filter,
#                     limit=10,  # Get all matching points (there should be only one, but just in case)
#                     with_payload=True
#                 )
                
#                 if not search_results or len(search_results[0]) == 0:
#                     return f"❌ Template not found: {template_id}"
                
#                 # Get point IDs to delete
#                 point_ids = [point.id for point in search_results[0]]
#                 logger.info(f"Found {len(point_ids)} points to delete for template_id: {template_id}")
                
#             except Exception as retrieve_error:
#                 logger.error(f"❌ Error finding template: {retrieve_error}", exc_info=True)
#                 return f"❌ Error finding template: {str(retrieve_error)}"
            
#             # Delete the template with proper error handling
#             try:
#                 from qdrant_client.models import PointIdsList
                
#                 # Use PointIdsList for more reliable deletion
#                 client.delete(
#                     collection_name=_card_templates_collection,
#                     points_selector=PointIdsList(
#                         points=point_ids
#                     )
#                 )
                
#                 # Verify deletion
#                 verify_results = client.scroll(
#                     collection_name=_card_templates_collection,
#                     scroll_filter=template_id_filter,
#                     limit=1,
#                     with_payload=True
#                 )
                
#                 if not verify_results or len(verify_results[0]) == 0:
#                     return f"✅ Template deleted successfully: {template_id}"
#                 else:
#                     return f"⚠️ Template may not have been deleted: {template_id}"
                
#             except ImportError:
#                 # Fall back to simpler deletion if models not available
#                 for point_id in point_ids:
#                     client.delete(
#                         collection_name=_card_templates_collection,
#                         points_selector=[point_id]
#                     )
#                 return f"✅ Template deleted successfully: {template_id}"
                
#             except Exception as delete_error:
#                 logger.error(f"❌ Error during template deletion: {delete_error}", exc_info=True)
#                 return f"❌ Error during template deletion: {str(delete_error)}"
            
#         except Exception as e:
#             logger.error(f"❌ Error deleting card template: {e}", exc_info=True)
#             return f"❌ Error deleting card template: {str(e)}"
    
#     @mcp.tool(
#         name="get_card_component_info",
#         description="Get detailed information about a specific card component",
#         tags={"chat", "card", "info", "component", "google"},
#         annotations={
#             "title": "Get Card Component Info",
#             "readOnlyHint": True,
#             "destructiveHint": False,
#             "idempotentHint": True,
#             "openWorldHint": False
#         }
#     )
#     async def get_card_component_info(
#         component_path: str,
#         include_source: bool = False
#     ) -> str:
#         """
#         Get detailed information about a specific card component.
        
#         Args:
#             component_path: Path to the component (e.g., "card_framework.v2.Card")
#             include_source: Whether to include source code in the response
            
#         Returns:
#             JSON string with component details
#         """
#         try:
#             # Initialize wrapper if needed
#             if not _card_framework_wrapper:
#                 _initialize_card_framework_wrapper()
                
#             if not _card_framework_wrapper:
#                 return "❌ Card Framework wrapper not available"
            
#             # Get component info
#             info = _card_framework_wrapper.get_component_info(component_path)
            
#             if not info:
#                 return f"❌ Component not found: {component_path}"
            
#             # Get the actual component
#             component = _card_framework_wrapper.get_component_by_path(component_path)
            
#             # Format result
#             result = {
#                 "name": info.get("name"),
#                 "path": info.get("path"),
#                 "type": info.get("type"),
#                 "module_path": info.get("module_path"),
#                 "docstring": info.get("docstring", "")
#             }
            
#             # Add source code if requested
#             if include_source and component:
#                 try:
#                     import inspect
#                     source = inspect.getsource(component)
#                     result["source"] = source
#                 except (TypeError, OSError):
#                     result["source"] = "Source code not available"
            
#             # Add signature for callable components
#             if component and callable(component):
#                 try:
#                     import inspect
#                     sig = inspect.signature(component)
#                     result["signature"] = str(sig)
                    
#                     # Add parameter details
#                     params = {}
#                     for name, param in sig.parameters.items():
#                         params[name] = {
#                             "kind": str(param.kind),
#                             "default": str(param.default) if param.default is not inspect.Parameter.empty else None,
#                             "annotation": str(param.annotation) if param.annotation is not inspect.Parameter.empty else None
#                         }
                    
#                     result["parameters"] = params
#                 except (TypeError, ValueError):
#                     result["signature"] = "Signature not available"
            
#             return json.dumps(result, indent=2)
            
#         except Exception as e:
#             logger.error(f"❌ Error getting card component info: {e}", exc_info=True)
#             return f"❌ Error getting card component info: {str(e)}"
    
#     @mcp.tool(
#         name="create_card_framework_wrapper",
#         description="Create a ModuleWrapper for a specific module",
#         tags={"chat", "card", "wrapper", "module", "qdrant"},
#         annotations={
#             "title": "Create Module Wrapper",
#             "readOnlyHint": False,
#             "destructiveHint": False,
#             "idempotentHint": False,
#             "openWorldHint": True
#         }
#     )
#     async def create_card_framework_wrapper(
#         module_name: str,
#         collection_name: Optional[str] = None,
#         index_nested: bool = True,
#         max_depth: int = 2
#     ) -> str:
#         """
#         Create a ModuleWrapper for a specific module.
        
#         This tool allows you to create a ModuleWrapper for any module,
#         not just card_framework. This can be useful for exploring and
#         using components from other modules.
        
#         Args:
#             module_name: Name of the module to wrap
#             collection_name: Name of the Qdrant collection to use
#             index_nested: Whether to index nested components
#             max_depth: Maximum recursion depth for indexing
            
#         Returns:
#             Confirmation message
#         """
#         try:
#             # Import the module
#             try:
#                 import importlib
#                 module = importlib.import_module(module_name)
#             except ImportError:
#                 return f"❌ Could not import module: {module_name}"
            
#             # Generate collection name if not provided
#             if not collection_name:
#                 collection_name = f"{module_name.replace('.', '_')}_components"
            
#             # Create the wrapper
#             from adapters.module_wrapper import ModuleWrapper
            
#             wrapper = ModuleWrapper(
#                 module_or_name=module,
#                 collection_name=collection_name,
#                 index_nested=index_nested,
#                 index_private=False,
#                 max_depth=max_depth,
#                 skip_standard_library=True
#             )
            
#             # Get component counts
#             component_count = len(wrapper.components)
#             class_count = len(wrapper.list_components("class"))
#             function_count = len(wrapper.list_components("function"))
            
#             return f"""✅ ModuleWrapper created for {module_name}!
# Collection: {collection_name}
# Components: {component_count} total
# Classes: {class_count}
# Functions: {function_count}

# You can now use this wrapper with the send_dynamic_card tool by specifying components from this module.
# """
            
#         except Exception as e:
            logger.error(f"❌ Error creating ModuleWrapper: {e}", exc_info=True)
            return f"❌ Error creating ModuleWrapper: {str(e)}"