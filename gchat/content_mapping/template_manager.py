"""
Template Manager for Google Chat Card Creation

This module provides the TemplateManager class, which manages card templates
for Google Chat card creation by leveraging the existing Qdrant infrastructure.
"""

import json
import logging
import uuid
import hashlib
import sys
import os
from datetime import datetime
from typing import Dict, List, Any, Optional, Union

# Add the project root to the path to enable absolute imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

# Import from existing middleware to leverage centralized Qdrant implementation
from middleware.qdrant_unified import QdrantUnifiedMiddleware

logger = logging.getLogger(__name__)


class TemplateManager:
    """
    Manager for card templates that leverages the existing Qdrant infrastructure.
    
    The TemplateManager provides functionality for storing, retrieving, and applying
    card templates for Google Chat cards. It uses the centralized Qdrant implementation
    to avoid reinventing the wheel and ensure consistency across the application.
    """
    
    def __init__(
        self,
        collection_name: str = "card_framework_components",
        qdrant_middleware: Optional[QdrantUnifiedMiddleware] = None
    ):
        """
        Initialize the TemplateManager.
        
        Args:
            collection_name: Name of the Qdrant collection to use (should match ModuleWrapper)
            qdrant_middleware: Optional existing QdrantUnifiedMiddleware instance to reuse
        """
        self.collection_name = collection_name
        self.qdrant_middleware = qdrant_middleware
        self.templates_cache = {}
        
        # Initialize Qdrant middleware if not provided
        if self.qdrant_middleware is None:
            try:
                logger.info("🔗 Initializing Qdrant middleware for TemplateManager...")
                self.qdrant_middleware = QdrantUnifiedMiddleware(
                    collection_name=self.collection_name
                )
                logger.info("✅ Qdrant middleware initialized")
            except Exception as e:
                logger.error(f"❌ Failed to initialize Qdrant middleware: {e}", exc_info=True)
                self.qdrant_middleware = None
    
    async def initialize(self):
        """Initialize the TemplateManager asynchronously."""
        if self.qdrant_middleware:
            await self.qdrant_middleware.initialize()
    
    def _generate_template_id(self, name: str, template: Dict[str, Any]) -> str:
        """
        Generate a deterministic template ID based on name and content.
        
        This ensures that identical templates get the same ID, preventing duplicates.
        
        Args:
            name: Template name
            template: Template content
            
        Returns:
            Deterministic template ID
        """
        # Create a string representation of the template
        template_str = f"{name}:{json.dumps(template, sort_keys=True)}"
        
        # Generate a hash
        template_hash = hashlib.md5(template_str.encode('utf-8')).hexdigest()
        
        # Return a prefixed ID
        return f"template_{template_hash}"
    
    async def get_template(self, template_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a template by ID.
        
        Args:
            template_id: ID of the template to retrieve
            
        Returns:
            Template object if found, None otherwise
        """
        # Check cache first
        if template_id in self.templates_cache:
            return self.templates_cache[template_id]
        
        # If not in cache and Qdrant middleware is available, search there
        if self.qdrant_middleware:
            try:
                # Use direct ID lookup query format
                results = await self.qdrant_middleware.search(f"id:{template_id}")
                
                if results and len(results) > 0:
                    template_data = results[0].get("response_data", {})
                    
                    # Cache the result
                    self.templates_cache[template_id] = template_data
                    
                    return template_data
            
            except Exception as e:
                logger.error(f"❌ Error retrieving template from Qdrant: {e}", exc_info=True)
        
        return None
    
    async def find_templates(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Find templates matching a query.
        
        Args:
            query: Search query
            limit: Maximum number of results
            
        Returns:
            List of matching templates
        """
        if not self.qdrant_middleware:
            return []
        
        try:
            # Add payload_type filter to only search for templates
            filter_query = f"payload_type:template {query}"
            
            # Search in Qdrant
            results = await self.qdrant_middleware.search(filter_query, limit=limit)
            
            # Process results
            templates = []
            for result in results:
                template_data = result.get("response_data", {})
                
                # Skip non-template results
                if template_data.get("payload_type") != "template":
                    continue
                
                # Add to templates list
                templates.append({
                    "template_id": result.get("id"),
                    "score": result.get("score"),
                    "name": template_data.get("name"),
                    "description": template_data.get("description"),
                    "template": template_data.get("template"),
                    "created_at": template_data.get("created_at")
                })
            
            return templates
            
        except Exception as e:
            logger.error(f"❌ Template search failed: {e}", exc_info=True)
            return []
    
    async def store_template(
        self,
        name: str,
        description: str,
        template: Dict[str, Any],
        placeholders: Dict[str, str] = None
    ) -> Optional[str]:
        """
        Store a card template.
        
        Args:
            name: Template name
            description: Template description
            template: The card template (dictionary)
            placeholders: Optional mapping of placeholder names to paths in the template
            
        Returns:
            Template ID if successful, None otherwise
        """
        if not self.qdrant_middleware:
            logger.error("❌ Cannot store template: Qdrant middleware not available")
            return None
        
        try:
            # Generate a deterministic ID for the template
            template_id = self._generate_template_id(name, template)
            
            # Create payload
            template_data = {
                "template_id": template_id,
                "name": name,
                "description": description,
                "template": template,
                "placeholders": placeholders or {},
                "created_at": datetime.now().isoformat(),
                "payload_type": "template"  # Mark as template for filtering
            }
            
            # Generate text for embedding
            embed_text = f"Template: {name}\nDescription: {description}\nType: card template"
            
            # Store in Qdrant using the middleware's _store_response method
            await self.qdrant_middleware._store_response(
                tool_name="store_template",
                tool_args={
                    "name": name,
                    "description": description
                },
                response=template_data,
                execution_time_ms=0,
                session_id=None,
                user_email=None
            )
            
            # Cache the template
            self.templates_cache[template_id] = template_data
            
            logger.info(f"✅ Stored card template: {name} (ID: {template_id})")
            return template_id
            
        except Exception as e:
            logger.error(f"❌ Template storage failed: {e}", exc_info=True)
            return None
    
    def apply_template(
        self,
        template: Dict[str, Any],
        content: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Apply content to a template.
        
        Args:
            template: Template to apply
            content: Content to apply to the template
            
        Returns:
            Populated template as a dictionary
        """
        # Make a deep copy of the template to avoid modifying the original
        result = json.loads(json.dumps(template.get("template", {})))
        
        # Get placeholders
        placeholders = template.get("placeholders", {})
        
        # Replace placeholders in the template
        for placeholder, path in placeholders.items():
            if placeholder in content:
                # Parse the path and set the value
                parts = path.split('.')
                target = result
                
                # Navigate to the target location
                for i, part in enumerate(parts):
                    if i == len(parts) - 1:
                        # Set the value at the final location
                        target[part] = content[placeholder]
                    else:
                        # Create nested dictionaries if they don't exist
                        if part not in target:
                            target[part] = {}
                        target = target[part]
        
        return result
