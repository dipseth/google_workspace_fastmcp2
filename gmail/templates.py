"""
Email Template Manager for Gmail

This module provides the EmailTemplateManager class, which manages HTML email templates
for Gmail messages by leveraging the existing Qdrant infrastructure.

Features:
- Store and retrieve HTML email templates
- Map templates to specific email addresses
- Replace placeholders in templates with dynamic content
- Automatic template application when sending emails
"""

import json
import logging
import hashlib
import re
from datetime import datetime
from typing_extensions import Dict, List, Any, Optional, Union
from dataclasses import dataclass, asdict

# Import from existing middleware to leverage centralized Qdrant implementation
from middleware.qdrant_unified import QdrantUnifiedMiddleware

logger = logging.getLogger(__name__)


@dataclass
class EmailTemplate:
    """Email template data structure."""
    template_id: str
    name: str
    description: str
    html_content: str
    placeholders: List[str]
    created_at: str
    updated_at: Optional[str] = None
    tags: List[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert template to dictionary."""
        return asdict(self)


@dataclass
class TemplateMapping:
    """Template to user/domain mapping."""
    mapping_id: str
    template_id: str
    target: str  # email address or domain
    target_type: str  # 'user', 'domain', or 'global'
    priority: int  # for fallback ordering
    created_at: str
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert mapping to dictionary."""
        return asdict(self)


class EmailTemplateManager:
    """
    Manager for email templates that leverages the existing Qdrant infrastructure.
    
    The EmailTemplateManager provides functionality for storing, retrieving, and applying
    HTML email templates for Gmail messages. It uses the centralized Qdrant implementation
    to ensure consistency across the application.
    """
    
    def __init__(
        self,
        collection_name: str = "email_templates",
        qdrant_middleware: Optional[QdrantUnifiedMiddleware] = None
    ):
        """
        Initialize the EmailTemplateManager.
        
        Args:
            collection_name: Name of the Qdrant collection to use for templates
            qdrant_middleware: Optional existing QdrantUnifiedMiddleware instance to reuse
        """
        self.collection_name = collection_name
        self.qdrant_middleware = qdrant_middleware
        self.templates_cache = {}
        self.mappings_cache = {}
        
        # Initialize Qdrant middleware if not provided
        if self.qdrant_middleware is None:
            try:
                logger.info("🔗 Initializing Qdrant middleware for EmailTemplateManager...")
                self.qdrant_middleware = QdrantUnifiedMiddleware(
                    collection_name=self.collection_name
                )
                logger.info("✅ Qdrant middleware initialized")
            except Exception as e:
                logger.error(f"❌ Failed to initialize Qdrant middleware: {e}", exc_info=True)
                self.qdrant_middleware = None
    
    async def initialize(self):
        """Initialize the EmailTemplateManager asynchronously."""
        if self.qdrant_middleware:
            await self.qdrant_middleware.initialize()
    
    def _generate_template_id(self, name: str) -> str:
        """
        Generate a deterministic template ID based on name and timestamp.
        
        Args:
            name: Template name
            
        Returns:
            Deterministic template ID
        """
        # Create a unique ID with timestamp for versioning
        timestamp = datetime.now().isoformat()
        template_str = f"{name}:{timestamp}"
        template_hash = hashlib.md5(template_str.encode('utf-8')).hexdigest()[:8]
        return f"email_template_{template_hash}"
    
    def _generate_mapping_id(self, template_id: str, target: str) -> str:
        """
        Generate a deterministic mapping ID.
        
        Args:
            template_id: Template ID
            target: Target email or domain
            
        Returns:
            Deterministic mapping ID
        """
        mapping_str = f"{template_id}:{target}"
        mapping_hash = hashlib.md5(mapping_str.encode('utf-8')).hexdigest()[:8]
        return f"mapping_{mapping_hash}"
    
    def _extract_placeholders(self, html_content: str) -> List[str]:
        """
        Extract placeholder names from HTML content.
        
        Args:
            html_content: HTML template content
            
        Returns:
            List of placeholder names
        """
        # Find all {{placeholder_name}} patterns
        pattern = r'\{\{([^}]+)\}\}'
        placeholders = re.findall(pattern, html_content)
        return list(set(placeholders))  # Remove duplicates
    
    def _replace_placeholders(self, html_content: str, values: Dict[str, str]) -> str:
        """
        Replace placeholders in HTML content with provided values.
        
        Args:
            html_content: HTML template content with placeholders
            values: Dictionary of placeholder names to values
            
        Returns:
            HTML content with placeholders replaced
        """
        result = html_content
        for placeholder, value in values.items():
            pattern = f'{{{{{placeholder}}}}}'
            result = result.replace(pattern, str(value))
        return result
    
    def _validate_html(self, html_content: str) -> bool:
        """
        Basic validation of HTML content.
        
        Args:
            html_content: HTML content to validate
            
        Returns:
            True if valid, False otherwise
        """
        # Check for basic HTML structure
        if not html_content.strip():
            return False
        
        # Check for unclosed placeholders
        if html_content.count('{{') != html_content.count('}}'):
            return False
        
        # Check for basic HTML tags (optional but recommended)
        has_html = '<html' in html_content.lower() or '<!doctype' in html_content.lower()
        has_body = '<body' in html_content.lower()
        
        # Allow templates without full HTML structure (for embedding in existing emails)
        # But warn if missing
        if not has_html and not has_body:
            logger.warning("Template missing <html> or <body> tags - will be embedded as fragment")
        
        return True
    
    async def create_template(
        self,
        name: str,
        description: str,
        html_content: str,
        tags: List[str] = None
    ) -> Optional[str]:
        """
        Create a new email template.
        
        Args:
            name: Template name
            description: Template description
            html_content: HTML content with placeholders
            tags: Optional tags for categorization
            
        Returns:
            Template ID if successful, None otherwise
        """
        if not self.qdrant_middleware:
            logger.error("❌ Cannot create template: Qdrant middleware not available")
            return None
        
        # Validate HTML
        if not self._validate_html(html_content):
            logger.error("❌ Invalid HTML content")
            return None
        
        try:
            # Generate template ID
            template_id = self._generate_template_id(name)
            
            # Extract placeholders
            placeholders = self._extract_placeholders(html_content)
            
            # Create template object
            template = EmailTemplate(
                template_id=template_id,
                name=name,
                description=description,
                html_content=html_content,
                placeholders=placeholders,
                tags=tags or [],
                created_at=datetime.now().isoformat()
            )
            
            # Create payload for storage
            template_data = template.to_dict()
            template_data['payload_type'] = 'email_template'
            
            # Generate text for embedding
            embed_text = f"Email Template: {name}\nDescription: {description}\n"
            embed_text += f"Placeholders: {', '.join(placeholders)}\n"
            embed_text += f"Tags: {', '.join(tags or [])}"
            
            # Store in Qdrant using the middleware's _store_response method
            await self.qdrant_middleware._store_response(
                tool_name="create_email_template",
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
            self.templates_cache[template_id] = template
            
            logger.info(f"✅ Created email template: {name} (ID: {template_id})")
            return template_id
            
        except Exception as e:
            logger.error(f"❌ Template creation failed: {e}", exc_info=True)
            return None
    
    async def get_template(self, template_id: str) -> Optional[EmailTemplate]:
        """
        Get a template by ID.
        
        Args:
            template_id: ID of the template to retrieve
            
        Returns:
            EmailTemplate object if found, None otherwise
        """
        # Check cache first
        if template_id in self.templates_cache:
            return self.templates_cache[template_id]
        
        # If not in cache and Qdrant middleware is available, search there
        if self.qdrant_middleware:
            try:
                # Search for template by template_id in payload
                results = await self.qdrant_middleware.search(
                    f"payload_type:email_template template_id:{template_id}"
                )
                
                if results and len(results) > 0:
                    template_data = results[0].get("response_data", {})
                    
                    # Convert to EmailTemplate object
                    template = EmailTemplate(**{
                        k: v for k, v in template_data.items()
                        if k in EmailTemplate.__dataclass_fields__
                    })
                    
                    # Cache the result
                    self.templates_cache[template_id] = template
                    
                    return template
            
            except Exception as e:
                logger.error(f"❌ Error retrieving template from Qdrant: {e}", exc_info=True)
        
        return None
    
    async def find_templates(
        self,
        query: str = "",
        tags: List[str] = None,
        limit: int = 10
    ) -> List[EmailTemplate]:
        """
        Find templates matching a query or tags.
        
        Args:
            query: Search query
            tags: Tags to filter by
            limit: Maximum number of results
            
        Returns:
            List of matching EmailTemplate objects
        """
        if not self.qdrant_middleware:
            return []
        
        try:
            # Build filter query
            filter_query = "payload_type:email_template"
            if query:
                filter_query += f" {query}"
            
            # Search in Qdrant
            results = await self.qdrant_middleware.search(filter_query, limit=limit)
            
            # Process results
            templates = []
            for result in results:
                template_data = result.get("response_data", {})
                
                # Skip non-email-template results
                if template_data.get("payload_type") != "email_template":
                    continue
                
                # Filter by tags if specified
                if tags:
                    template_tags = template_data.get("tags", [])
                    if not any(tag in template_tags for tag in tags):
                        continue
                
                # Convert to EmailTemplate object
                template = EmailTemplate(**{
                    k: v for k, v in template_data.items()
                    if k in EmailTemplate.__dataclass_fields__
                })
                templates.append(template)
            
            return templates
            
        except Exception as e:
            logger.error(f"❌ Template search failed: {e}", exc_info=True)
            return []
    
    async def assign_template_to_user(
        self,
        email_address: str,
        template_id: str,
        priority: int = 1
    ) -> Optional[str]:
        """
        Assign a template to a specific email address.
        
        Args:
            email_address: Email address to assign template to
            template_id: Template ID to assign
            priority: Priority for fallback ordering (lower = higher priority)
            
        Returns:
            Mapping ID if successful, None otherwise
        """
        if not self.qdrant_middleware:
            logger.error("❌ Cannot assign template: Qdrant middleware not available")
            return None
        
        try:
            # Verify template exists
            template = await self.get_template(template_id)
            if not template:
                logger.error(f"❌ Template {template_id} not found")
                return None
            
            # Generate mapping ID
            mapping_id = self._generate_mapping_id(template_id, email_address)
            
            # Create mapping object
            mapping = TemplateMapping(
                mapping_id=mapping_id,
                template_id=template_id,
                target=email_address.lower(),
                target_type='user',
                priority=priority,
                created_at=datetime.now().isoformat()
            )
            
            # Create payload for storage
            mapping_data = mapping.to_dict()
            mapping_data['payload_type'] = 'template_mapping'
            
            # Generate text for embedding
            embed_text = f"Template Mapping: {email_address} → {template.name}\n"
            embed_text += f"Template: {template_id}\nType: user mapping"
            
            # Store in Qdrant
            await self.qdrant_middleware._store_response(
                tool_name="assign_template_to_user",
                tool_args={
                    "email_address": email_address,
                    "template_id": template_id
                },
                response=mapping_data,
                execution_time_ms=0,
                session_id=None,
                user_email=None
            )
            
            # Cache the mapping
            self.mappings_cache[email_address.lower()] = mapping
            
            logger.info(f"✅ Assigned template {template.name} to {email_address}")
            return mapping_id
            
        except Exception as e:
            logger.error(f"❌ Template assignment failed: {e}", exc_info=True)
            return None
    
    async def get_template_for_recipient(self, email_address: str) -> Optional[EmailTemplate]:
        """
        Get the template assigned to a specific recipient.
        
        Implements fallback hierarchy:
        1. User-specific template
        2. Domain-based template
        3. Global default template
        
        Args:
            email_address: Recipient's email address
            
        Returns:
            EmailTemplate if found, None otherwise
        """
        if not self.qdrant_middleware:
            return None
        
        email_lower = email_address.lower()
        
        # Check cache first
        if email_lower in self.mappings_cache:
            mapping = self.mappings_cache[email_lower]
            return await self.get_template(mapping.template_id)
        
        try:
            # Search for user-specific mapping
            results = await self.qdrant_middleware.search(
                f"payload_type:template_mapping target:{email_lower} target_type:user",
                limit=1
            )
            
            if results:
                mapping_data = results[0].get("response_data", {})
                template_id = mapping_data.get("template_id")
                if template_id:
                    # Cache the mapping
                    mapping = TemplateMapping(**{
                        k: v for k, v in mapping_data.items()
                        if k in TemplateMapping.__dataclass_fields__
                    })
                    self.mappings_cache[email_lower] = mapping
                    return await self.get_template(template_id)
            
            # If no user-specific template, try domain-based
            domain = email_lower.split('@')[1] if '@' in email_lower else None
            if domain:
                results = await self.qdrant_middleware.search(
                    f"payload_type:template_mapping target:{domain} target_type:domain",
                    limit=1
                )
                
                if results:
                    mapping_data = results[0].get("response_data", {})
                    template_id = mapping_data.get("template_id")
                    if template_id:
                        return await self.get_template(template_id)
            
            # Finally, try global default
            results = await self.qdrant_middleware.search(
                f"payload_type:template_mapping target_type:global",
                limit=1
            )
            
            if results:
                mapping_data = results[0].get("response_data", {})
                template_id = mapping_data.get("template_id")
                if template_id:
                    return await self.get_template(template_id)
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Error getting template for recipient: {e}", exc_info=True)
            return None
    
    async def apply_template(
        self,
        template: EmailTemplate,
        content: Dict[str, str]
    ) -> str:
        """
        Apply content to a template.
        
        Args:
            template: EmailTemplate to apply
            content: Dictionary of placeholder names to values
            
        Returns:
            Populated HTML content
        """
        # Replace placeholders with provided content
        html_result = self._replace_placeholders(template.html_content, content)
        
        # Replace any remaining placeholders with empty strings or defaults
        for placeholder in template.placeholders:
            if placeholder not in content:
                logger.warning(f"Placeholder {{{{placeholder}}}} not provided, using empty string")
                html_result = html_result.replace(f'{{{{{placeholder}}}}}', '')
        
        return html_result
    
    async def delete_template(self, template_id: str) -> bool:
        """
        Delete a template and its mappings.
        
        Args:
            template_id: Template ID to delete
            
        Returns:
            True if successful, False otherwise
        """
        # Note: Qdrant doesn't have direct delete by query, so we mark as deleted
        # In production, you would implement proper deletion or use a status field
        try:
            # Remove from cache
            if template_id in self.templates_cache:
                del self.templates_cache[template_id]
            
            # Remove mappings from cache
            to_remove = [
                k for k, v in self.mappings_cache.items()
                if v.template_id == template_id
            ]
            for k in to_remove:
                del self.mappings_cache[k]
            
            logger.info(f"✅ Deleted template {template_id} from cache")
            return True
            
        except Exception as e:
            logger.error(f"❌ Template deletion failed: {e}", exc_info=True)
            return False
    
    async def list_user_mappings(self) -> List[Dict[str, str]]:
        """
        List all user-to-template mappings.
        
        Returns:
            List of mappings with email, template name, and ID
        """
        if not self.qdrant_middleware:
            return []
        
        try:
            # Search for all user mappings
            results = await self.qdrant_middleware.search(
                "payload_type:template_mapping target_type:user",
                limit=100
            )
            
            mappings = []
            for result in results:
                mapping_data = result.get("response_data", {})
                template_id = mapping_data.get("template_id")
                
                # Get template details
                template = await self.get_template(template_id) if template_id else None
                
                mappings.append({
                    "email": mapping_data.get("target"),
                    "template_name": template.name if template else "Unknown",
                    "template_id": template_id,
                    "created_at": mapping_data.get("created_at")
                })
            
            return mappings
            
        except Exception as e:
            logger.error(f"❌ Failed to list user mappings: {e}", exc_info=True)
            return []