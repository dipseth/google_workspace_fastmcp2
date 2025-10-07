#!/usr/bin/env python3
"""
Enhanced Sampling Middleware for FastMCP2 Google Workspace Platform

This middleware provides resource-aware, context-intelligent LLM sampling capabilities
by integrating with the FastMCP2 platform's extensive resource ecosystem, Qdrant knowledge base,
and template system to make the client LLM smart about available resources and capabilities.

Key Features:
- Automatic sampling context injection into tool calls
- Resource-aware prompting with real user data injection
- Qdrant-enhanced historical context and pattern recognition
- Template Parameter Middleware integration for dynamic prompts
- Macro-aware sampling with existing Jinja2 email/document templates
- Multi-level enhancement system (basic, contextual, historical)
- Comprehensive error handling and logging
- Template support for common sampling patterns

Enhanced Features:
- Context-enriched sampling with user profile and workspace data
- Historical pattern recognition via Qdrant search
- Macro-aware assistance with beautiful email templates
- Dynamic resource discovery and suggestion
- Template rendering examples with and without execution

Usage:
    from middleware.sampling_middleware import setup_enhanced_sampling_middleware
    
    # After server creation and other middleware setup:
    sampling_middleware = setup_enhanced_sampling_middleware(
        mcp, 
        qdrant_middleware=qdrant_middleware,
        template_middleware=template_middleware
    )
"""

import json
import logging
import asyncio
from typing import Any, Dict, Optional, List, Union, Annotated
from dataclasses import dataclass
from enum import Enum
from datetime import datetime, timezone

from fastmcp import FastMCP, Context
from fastmcp.server.middleware import Middleware, MiddlewareContext
from fastmcp.tools import Tool
from fastmcp.tools.tool_transform import forward
from fastmcp.exceptions import ToolError
from pydantic import Field

# Configure logging
from config.enhanced_logging import setup_logger
logger = setup_logger()

# ============================================================================
# SAMPLING TYPES AND SCHEMAS
# ============================================================================

@dataclass
class SamplingMessage:
    """Structured message for LLM sampling."""
    role: str  # "user", "assistant", "system"
    content: str

@dataclass  
class ModelPreferences:
    """Model preference configuration for sampling."""
    preferred_models: List[str]
    fallback_models: Optional[List[str]] = None
    
class SamplingTemplate(Enum):
    """Pre-defined sampling templates for common use cases."""
    SENTIMENT_ANALYSIS = "sentiment_analysis"
    SUMMARIZATION = "summarization" 
    CODE_GENERATION = "code_generation"
    CREATIVE_WRITING = "creative_writing"
    TECHNICAL_ANALYSIS = "technical_analysis"
    TRANSLATION = "translation"
    QUESTION_ANSWERING = "question_answering"
    # Enhanced templates for FastMCP2 platform
    CONTEXT_AWARE_ANALYSIS = "context_aware_analysis"
    MACRO_AWARE_EMAIL_ASSISTANT = "macro_aware_email_assistant"
    DOCUMENT_GENERATION_ASSISTANT = "document_generation_assistant"
    WORKFLOW_SUGGESTION = "workflow_suggestion"
    RESOURCE_DISCOVERY = "resource_discovery"
    HISTORICAL_PATTERN_ANALYSIS = "historical_pattern_analysis"

class EnhancementLevel(Enum):
    """Enhancement levels for contextual sampling."""
    BASIC = "basic"           # User profile + available tools
    CONTEXTUAL = "contextual"  # + recent activity + relevant resources
    HISTORICAL = "historical"  # + Qdrant patterns + personalized recommendations

@dataclass
class TextContent:
    """Response content from LLM sampling."""
    text: str
    metadata: Optional[Dict[str, Any]] = None

@dataclass
class ImageContent:
    """Image response content from LLM sampling."""
    data: bytes
    mime_type: str
    metadata: Optional[Dict[str, Any]] = None

# ============================================================================
# ENHANCED SAMPLING CONTEXT CLASSES
# ============================================================================

class ResourceContextManager:
    """Manages dynamic resource context for sampling enhancement."""
    
    def __init__(self, fastmcp_context, enable_debug=False):
        self.fastmcp_context = fastmcp_context
        self.enable_debug = enable_debug
        
    async def get_resource_safely(self, uri: str) -> Optional[Dict[str, Any]]:
        """Safely get a resource with error handling."""
        try:
            if self.enable_debug:
                logger.debug(f"🔍 Fetching resource: {uri}")
            
            # Use the fastmcp_context to read resources
            if hasattr(self.fastmcp_context, 'read_resource'):
                result = await self.fastmcp_context.read_resource(uri)
                if result and result.get('contents'):
                    # Extract the content from the resource response
                    content = result['contents'][0]
                    if content.get('text'):
                        import json
                        return json.loads(content['text'])
                    return content
            return None
        except Exception as e:
            if self.enable_debug:
                logger.debug(f"⚠️ Failed to fetch resource {uri}: {e}")
            return None
    
    async def get_user_context_summary(self, user_email: str = None) -> Dict[str, Any]:
        """Get comprehensive user context for sampling."""
        context = {}
        
        # Try to get user profile and email
        user_profile = await self.get_resource_safely("user://current/profile")
        user_email_resource = await self.get_resource_safely("user://current/email")
        
        if user_profile:
            context['user_profile'] = user_profile
        if user_email_resource:
            context['user_email'] = user_email_resource
            
        # Try to get recent activity across all services - replaces deprecated workspace://content/recent
        workspace_activity = await self.get_resource_safely("recent://all")
        if workspace_activity:
            context['workspace_activity'] = workspace_activity
            
        # Try to get Gmail context
        gmail_labels = await self.get_resource_safely("service://gmail/labels")
        if gmail_labels:
            context['gmail_labels'] = gmail_labels
            
        # Try to get available tools
        available_tools = await self.get_resource_safely("tools://enhanced/list")
        if available_tools:
            context['available_tools'] = available_tools
            
        return context
    
    def get_relevant_resources_for_task(self, task_description: str) -> List[str]:
        """Intelligently determine which resources are relevant for a task."""
        resources = []
        task_lower = task_description.lower()
        
        # Always include user context
        resources.extend([
            "user://current/profile",
            "user://current/email"
        ])
        
        # Email-related tasks
        if any(keyword in task_lower for keyword in ['email', 'gmail', 'message', 'mail']):
            resources.extend([
                "service://gmail/labels",
                "gmail://messages/recent",
                "service://gmail/filters"
            ])
            
        # File/document-related tasks
        if any(keyword in task_lower for keyword in ['file', 'document', 'drive', 'folder']):
            resources.extend([
                "recent://all",  # Replaces deprecated workspace://content/recent
                "service://drive/items"
            ])
            
        # Tool/workflow-related tasks
        if any(keyword in task_lower for keyword in ['tool', 'workflow', 'automate', 'help']):
            resources.append("tools://enhanced/list")
            
        return resources

class QdrantHistoryEnhancer:
    """Enhances sampling with historical context from Qdrant."""
    
    def __init__(self, qdrant_middleware, enable_debug=False):
        self.qdrant_middleware = qdrant_middleware
        self.enable_debug = enable_debug
        
    async def get_relevant_history(
        self, 
        user_email: str, 
        query: str, 
        limit: int = 3
    ) -> List[Dict[str, Any]]:
        """Search Qdrant for relevant historical responses."""
        
        if not self.qdrant_middleware or not self.qdrant_middleware.is_initialized:
            if self.enable_debug:
                logger.debug("⚠️ Qdrant middleware not available for history enhancement")
            return []
        
        try:
            # Build search query with user filter
            search_query = f"user_email:{user_email} {query}"
            
            if self.enable_debug:
                logger.debug(f"🔍 Searching Qdrant for: {search_query}")
                
            # Use the existing search method from QdrantUnifiedMiddleware
            results = await self.qdrant_middleware.search(
                query=search_query,
                limit=limit,
                score_threshold=0.3  # Slightly lower threshold for broader context
            )
            
            if self.enable_debug:
                logger.debug(f"📊 Found {len(results)} historical patterns")
            
            # Format results for sampling context
            formatted_results = []
            for result in results:
                formatted_results.append({
                    "tool_name": result.get("tool_name", "unknown"),
                    "timestamp": result.get("timestamp", "unknown"),
                    "score": result.get("score", 0.0),
                    "response_summary": str(result.get("response_data", ""))[:200] + "...",
                    "success_indicators": self._extract_success_indicators(result)
                })
                
            return formatted_results
            
        except Exception as e:
            if self.enable_debug:
                logger.warning(f"⚠️ Failed to get historical context: {e}")
            return []
    
    def _extract_success_indicators(self, result: Dict[str, Any]) -> List[str]:
        """Extract indicators of successful patterns from historical data."""
        indicators = []
        
        # Look for positive indicators in the response
        response_data = result.get("response_data", {})
        if isinstance(response_data, dict):
            # Check for successful outcomes
            if "success" in str(response_data).lower():
                indicators.append("successful_execution")
            if "error" not in str(response_data).lower():
                indicators.append("error_free")
            if result.get("score", 0) > 0.8:
                indicators.append("high_relevance")
                
        return indicators

class EnhancedSamplingContext:
    """
    Enhanced sampling context with resource awareness and historical intelligence.
    
    This context provides LLM sampling capabilities enhanced with:
    - Real user data from FastMCP resources  
    - Historical context from Qdrant
    - Macro-aware template suggestions
    - Multi-level enhancement capabilities
    """
    
    def __init__(
        self, 
        fastmcp_context, 
        tool_name: str, 
        enable_debug: bool = False,
        resource_manager: Optional[ResourceContextManager] = None,
        history_enhancer: Optional[QdrantHistoryEnhancer] = None,
        template_middleware = None
    ):
        """
        Initialize enhanced sampling context.
        
        Args:
            fastmcp_context: FastMCP context for sampling operations
            tool_name: Name of the tool using this context  
            enable_debug: Enable debug logging
            resource_manager: Resource context manager for user data
            history_enhancer: Qdrant history enhancer for historical patterns
            template_middleware: Template middleware for macro support
        """
        self.fastmcp_context = fastmcp_context
        self.tool_name = tool_name
        self.enable_debug = enable_debug
        self.resource_manager = resource_manager
        self.history_enhancer = history_enhancer
        self.template_middleware = template_middleware
        
        # Available macro categories
        self.available_macros = {
            'email': ['render_beautiful_email', 'render_gmail_labels_chips', 'quick_photo_email_from_drive'],
            'document': ['generate_report_doc'],
            'display': ['render_gmail_labels_chips']
        }

    async def enhanced_sample(
        self,
        messages: Union[str, List[Union[str, SamplingMessage]]],
        enhancement_level: EnhancementLevel = EnhancementLevel.BASIC,
        relevant_resources: Optional[List[str]] = None,
        include_historical: bool = True,
        macro_category: Optional[str] = None,
        template: Optional[SamplingTemplate] = None,
        **kwargs
    ) -> Union[TextContent, ImageContent]:
        """
        Enhanced sampling with resource awareness and historical context.
        
        Args:
            messages: Original sampling messages
            enhancement_level: Level of context enhancement to apply
            relevant_resources: Specific resources to include
            include_historical: Whether to include historical context from Qdrant
            macro_category: Macro category to suggest ('email', 'document', 'display')  
            template: Sampling template to use
            **kwargs: Additional sampling parameters
        
        Returns:
            Enhanced sampling response with context and suggestions
        """
        try:
            if self.enable_debug:
                logger.debug(f"🎯 Enhanced sampling for tool: {self.tool_name}, level: {enhancement_level.value}")
            
            # 1. Build base context information
            enhanced_message = await self._build_enhanced_message(
                messages, enhancement_level, relevant_resources, include_historical, macro_category
            )
            
            # 2. Use enhanced sampling context
            return await self._perform_sampling(enhanced_message, template, **kwargs)
            
        except Exception as e:
            logger.error(f"❌ Enhanced sampling failed for tool {self.tool_name}: {e}")
            # Fallback to basic sampling
            return await self._perform_sampling(messages, template, **kwargs)
    
    async def _build_enhanced_message(
        self,
        original_message: Union[str, List[Union[str, SamplingMessage]]],
        enhancement_level: EnhancementLevel,
        relevant_resources: Optional[List[str]],
        include_historical: bool,
        macro_category: Optional[str]
    ) -> str:
        """Build enhanced message with context information."""
        
        # Convert messages to string for processing
        if isinstance(original_message, list):
            message_text = "\n".join([
                msg.content if isinstance(msg, SamplingMessage) else str(msg) 
                for msg in original_message
            ])
        else:
            message_text = str(original_message)
        
        context_parts = []
        
        # Add macro context if specified
        if macro_category and macro_category in self.available_macros:
            macros = self.available_macros[macro_category]
            context_parts.append(f"""
Available {macro_category} macros: {', '.join(macros)}
Consider suggesting specific macro usage with user's actual data.
""")
        
        # Add resource context based on enhancement level
        if enhancement_level in [EnhancementLevel.BASIC, EnhancementLevel.CONTEXTUAL, EnhancementLevel.HISTORICAL]:
            resource_context = await self._gather_resource_context(relevant_resources or [])
            if resource_context:
                context_parts.append("**Available User Context:**")
                context_parts.append(self._format_resource_context(resource_context))
        
        # Add historical context for HISTORICAL level
        if enhancement_level == EnhancementLevel.HISTORICAL and include_historical and self.history_enhancer:
            historical_context = await self._gather_historical_context(message_text)
            if historical_context:
                context_parts.append("**Historical Patterns:**")
                context_parts.append(self._format_historical_context(historical_context))
        
        # Combine everything
        enhanced_parts = []
        if context_parts:
            enhanced_parts.extend(context_parts)
            enhanced_parts.append("**User Request:**")
        
        enhanced_parts.append(message_text)
        
        if context_parts:
            enhanced_parts.append("""
Provide practical solutions using available resources and tools.
Include working examples with real user data when appropriate.
""")
        
        return "\n".join(enhanced_parts)
    
    async def _gather_resource_context(self, relevant_resources: List[str]) -> Dict[str, Any]:
        """Gather resource context for sampling enhancement."""
        if not self.resource_manager:
            return {}
            
        try:
            # Get comprehensive user context
            user_context = await self.resource_manager.get_user_context_summary()
            
            # Add any additional requested resources
            additional_context = {}
            for resource_uri in relevant_resources:
                resource_data = await self.resource_manager.get_resource_safely(resource_uri)
                if resource_data:
                    additional_context[resource_uri] = resource_data
            
            return {
                "user_context": user_context,
                "additional_resources": additional_context
            }
            
        except Exception as e:
            if self.enable_debug:
                logger.warning(f"⚠️ Failed to gather resource context: {e}")
            return {}
    
    async def _gather_historical_context(self, query: str) -> List[Dict[str, Any]]:
        """Gather historical context from Qdrant."""
        if not self.history_enhancer:
            return []
            
        try:
            # Extract user email from resource context if available
            user_email = "unknown"
            if self.resource_manager:
                user_context = await self.resource_manager.get_user_context_summary()
                user_email_data = user_context.get("user_email", {})
                if isinstance(user_email_data, dict):
                    user_email = user_email_data.get("email", "unknown")
                elif isinstance(user_email_data, str):
                    user_email = user_email_data
            
            # Get relevant historical patterns
            return await self.history_enhancer.get_relevant_history(user_email, query, limit=3)
            
        except Exception as e:
            if self.enable_debug:
                logger.warning(f"⚠️ Failed to gather historical context: {e}")
            return []
    
    def _format_resource_context(self, resource_context: Dict[str, Any]) -> str:
        """Format resource context for sampling prompt."""
        formatted_parts = []
        
        user_context = resource_context.get("user_context", {})
        
        # Format user information
        if "user_email" in user_context:
            email_data = user_context["user_email"]
            if isinstance(email_data, dict):
                name = email_data.get("name", "")
                email = email_data.get("email", "")
                if name and email:
                    formatted_parts.append(f"- User: {name} ({email})")
                elif email:
                    formatted_parts.append(f"- User: {email}")
        
        # Format workspace activity
        if "workspace_activity" in user_context:
            workspace = user_context["workspace_activity"]
            if isinstance(workspace, dict) and "total_files" in workspace:
                formatted_parts.append(f"- Workspace: {workspace['total_files']} recent files")
        
        # Format Gmail context
        if "gmail_labels" in user_context:
            labels = user_context["gmail_labels"]
            if isinstance(labels, dict):
                label_count = len(labels.get("labels", []))
                if label_count > 0:
                    formatted_parts.append(f"- Gmail: {label_count} labels configured")
        
        # Format available tools
        if "available_tools" in user_context:
            tools = user_context["available_tools"]
            if isinstance(tools, dict):
                tool_count = len(tools.get("enhanced_tools", []))
                if tool_count > 0:
                    formatted_parts.append(f"- Tools: {tool_count} enhanced tools available")
        
        return "\n".join(formatted_parts) if formatted_parts else "No specific context available"
    
    def _format_historical_context(self, historical_data: List[Dict[str, Any]]) -> str:
        """Format historical context for sampling prompt."""
        if not historical_data:
            return "No relevant historical patterns found"
        
        formatted_parts = []
        for i, pattern in enumerate(historical_data, 1):
            tool_name = pattern.get("tool_name", "unknown")
            score = pattern.get("score", 0.0)
            summary = pattern.get("response_summary", "")
            success_indicators = pattern.get("success_indicators", [])
            
            formatted_parts.append(f"{i}. Tool '{tool_name}' (relevance: {score:.2f})")
            if summary:
                formatted_parts.append(f"   Summary: {summary}")
            if success_indicators:
                formatted_parts.append(f"   Success factors: {', '.join(success_indicators)}")
        
        return "\n".join(formatted_parts)
    
    async def _perform_sampling(
        self,
        messages: Union[str, List[Union[str, SamplingMessage]]],
        template: Optional[SamplingTemplate] = None,
        **kwargs
    ) -> Union[TextContent, ImageContent]:
        """Perform the actual sampling with the enhanced template cache."""
        
        # Create a basic sampling context to handle the actual sampling
        basic_context = SamplingContext(
            fastmcp_context=self.fastmcp_context,
            tool_name=self.tool_name,
            enable_debug=self.enable_debug
        )
        
        return await basic_context.sample(messages, template=template, **kwargs)

    async def demo_template_rendering(
        self,
        template_name: str,
        user_data: Dict[str, Any] = None,
        render: bool = False
    ) -> Dict[str, Any]:
        """Demonstrate template usage with and without rendering."""
        
        demo_results = {
            "template_name": template_name,
            "render_requested": render,
            "examples": {}
        }
        
        # Show macro examples based on template name
        if "email" in template_name.lower():
            demo_results["examples"] = {
                "beautiful_email_template": """
{{ render_beautiful_email(
    title="Weekly Status Update", 
    content_sections=[{
        'type': 'text', 
        'content': 'Hi team! Here's our weekly update...'
    }],
    user_name="{{user://current/email.name}}",
    user_email="{{user://current/email.email}}",
    signature_style="professional"
) }}
""",
                "gmail_labels_template": """
{{ render_gmail_labels_chips(
    service://gmail/labels,
    'Gmail Organization for: ' + user://current/email.email
) }}
"""
            }
        elif "document" in template_name.lower():
            demo_results["examples"] = {
                "report_template": """
{{ generate_report_doc(
    report_title="Monthly Metrics Report",
    metrics=[{
        "value": "{{recent://all.total_items_across_services}}",
        "label": "Total Items",
        "change": 15
    }],
    table_data=[["Metric", "Value"], ["Items", "{{recent://all.total_items_across_services}}"]]
) }}
"""
            }
        
        # If rendering is requested and we have template middleware, try to render
        if render and self.template_middleware and user_data:
            try:
                rendered_examples = {}
                for key, template_text in demo_results["examples"].items():
                    # This would use the template middleware to render with real data
                    # For now, show what the rendered output structure would look like
                    rendered_examples[key] = {
                        "template": template_text,
                        "note": "Would be rendered with actual user data via TemplateParameterMiddleware"
                    }
                demo_results["rendered_examples"] = rendered_examples
            except Exception as e:
                demo_results["render_error"] = str(e)
        
        return demo_results

class SamplingContext:
    """
    Basic sampling context that provides LLM sampling capabilities to tools.
    
    This context is injected into tool calls and provides the sample() method
    that tools can use to request text generation from the client's LLM.
    """
    
    def __init__(self, fastmcp_context, tool_name: str, enable_debug: bool = False):
        """
        Initialize sampling context.
        
        Args:
            fastmcp_context: FastMCP context for sampling operations
            tool_name: Name of the tool using this context
            enable_debug: Enable debug logging
        """
        self.fastmcp_context = fastmcp_context
        self.tool_name = tool_name
        self.enable_debug = enable_debug
        
        # Template cache for common sampling patterns
        self._template_cache = {
            SamplingTemplate.SENTIMENT_ANALYSIS: {
                "system_prompt": "You are a sentiment analysis expert. Analyze text sentiment as positive, negative, or neutral.",
                "temperature": 0.1,
                "max_tokens": 100
            },
            SamplingTemplate.SUMMARIZATION: {
                "system_prompt": "You are an expert at creating concise, informative summaries. Focus on key points and main ideas.",
                "temperature": 0.3,
                "max_tokens": 300
            },
            SamplingTemplate.CODE_GENERATION: {
                "system_prompt": "You are an expert programmer. Generate clean, working code with minimal explanation unless requested.",
                "temperature": 0.2,
                "max_tokens": 500
            },
            SamplingTemplate.CREATIVE_WRITING: {
                "system_prompt": "You are a creative writer. Generate engaging, imaginative content with rich descriptions.",
                "temperature": 0.8,
                "max_tokens": 800
            },
            SamplingTemplate.TECHNICAL_ANALYSIS: {
                "system_prompt": "You are a technical analysis expert. Provide detailed, accurate technical insights based on data.",
                "temperature": 0.1,
                "max_tokens": 600
            },
            SamplingTemplate.TRANSLATION: {
                "system_prompt": "You are an expert translator. Provide accurate, natural translations preserving meaning and tone.",
                "temperature": 0.2,
                "max_tokens": 400
            },
            SamplingTemplate.QUESTION_ANSWERING: {
                "system_prompt": "You are a knowledgeable assistant. Provide accurate, helpful answers based on the given information.",
                "temperature": 0.3,
                "max_tokens": 400
            },
            
            # Enhanced FastMCP2-specific templates
            SamplingTemplate.CONTEXT_AWARE_ANALYSIS: {
                "system_prompt": """You are an intelligent assistant with access to the user's Google Workspace data and tools.

When analyzing requests, consider:
1. The user's current context and recent activity
2. What tools/resources could help achieve their goals  
3. Relevant patterns from their workspace usage
4. Actionable next steps using available capabilities

Always be specific about available tools and resources that could help.""",
                "temperature": 0.3,
                "max_tokens": 600,
                "include_context": "thisServer"
            },
            
            SamplingTemplate.MACRO_AWARE_EMAIL_ASSISTANT: {
                "system_prompt": """You are an intelligent email assistant with access to sophisticated email templates.

Available Email Macros:
1. render_beautiful_email() - Professional HTML emails with gradients and signatures
2. render_gmail_labels_chips() - Visual Gmail label management  
3. quick_photo_email_from_drive() - Photo-rich emails from Drive folders

When helping with emails:
1. Suggest specific macro usage with actual user data
2. Use the beautiful_email macro for professional formatting
3. Include Gmail label chips when relevant for organization
4. Suggest Drive photo emails when user mentions sharing images

Example responses should include working macro calls with real user data.""",
                "temperature": 0.3,
                "max_tokens": 800
            },
            
            SamplingTemplate.DOCUMENT_GENERATION_ASSISTANT: {
                "system_prompt": """You are a document generation expert with access to professional template macros.

Available Document Macros:
- generate_report_doc() - Professional reports with metrics, tables, and charts

When generating documents:
1. Use the generate_report_doc macro for professional formatting
2. Extract real metrics from user's workspace data
3. Create meaningful tables and charts based on actual user data
4. Include company branding when available

Always provide working macro calls with real data substitution.""",
                "temperature": 0.2,
                "max_tokens": 600
            },
            
            SamplingTemplate.WORKFLOW_SUGGESTION: {
                "system_prompt": """You are a workflow optimization expert with access to the user's workspace and tools.

When suggesting workflows:
1. Reference specific available tools by name
2. Use actual user data (file counts, label names, etc.)
3. Suggest realistic automation using FastMCP capabilities
4. Consider user's historical patterns and preferences

Provide step-by-step workflows with specific tool recommendations.""",
                "temperature": 0.4,
                "max_tokens": 800
            },
            
            SamplingTemplate.RESOURCE_DISCOVERY: {
                "system_prompt": """You are a resource discovery expert for the FastMCP2 platform.

Help users discover and utilize available resources:
1. Explain what resources are available for their use case
2. Show how to access user data, Gmail, Drive, and workspace content
3. Suggest resource combinations for complex tasks
4. Provide working resource URI examples

Focus on practical resource usage with real examples.""",
                "temperature": 0.2,
                "max_tokens": 600
            },
            
            SamplingTemplate.HISTORICAL_PATTERN_ANALYSIS: {
                "system_prompt": """You have access to the user's historical interaction patterns via Qdrant search.

Use this historical context to provide:
- How similar requests were handled before
- What tools were successful
- User preferences and patterns
- Common follow-up actions

Provide personalized recommendations based on historical success patterns.""",
                "temperature": 0.2,
                "max_tokens": 700
            }
        }
    
    async def sample(
        self,
        messages: Union[str, List[Union[str, SamplingMessage]]],
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: int = 512,
        model_preferences: Optional[Union[str, List[str], ModelPreferences]] = None,
        template: Optional[SamplingTemplate] = None,
        include_context: Optional[str] = None
    ) -> Union[TextContent, ImageContent]:
        """
        Request text generation from the client's LLM.
        
        Args:
            messages: String or list of strings/message objects to send to the LLM
            system_prompt: Optional system prompt to guide LLM behavior
            temperature: Optional sampling temperature (0.0-1.0)
            max_tokens: Maximum number of tokens to generate
            model_preferences: Model selection preferences
            template: Pre-defined template for common use cases
            include_context: Include server context ("thisServer" or None)
            
        Returns:
            TextContent or ImageContent with the LLM's response
            
        Raises:
            ToolError: If sampling fails or client doesn't support sampling
        """
        try:
            if self.enable_debug:
                logger.debug(f"🎯 Starting LLM sampling for tool: {self.tool_name}")
            
            # Apply template if specified
            if template:
                template_config = self._template_cache.get(template, {})
                if system_prompt is None:
                    system_prompt = template_config.get("system_prompt")
                if temperature is None:
                    temperature = template_config.get("temperature")
                if max_tokens == 512:  # Default value
                    max_tokens = template_config.get("max_tokens", max_tokens)
                
                if self.enable_debug:
                    logger.debug(f"📋 Applied template: {template.value}")
            
            # Prepare sampling parameters
            sampling_params = {
                "messages": self._prepare_messages(messages),
                "max_tokens": max_tokens
            }
            
            # Add optional parameters
            if system_prompt:
                sampling_params["system_prompt"] = system_prompt
            if temperature is not None:
                sampling_params["temperature"] = temperature
            if model_preferences:
                sampling_params["model_preferences"] = self._prepare_model_preferences(model_preferences)
            if include_context:
                sampling_params["include_context"] = include_context
            
            if self.enable_debug:
                logger.debug(f"🔧 Sampling parameters: {json.dumps({k: str(v)[:100] + '...' if len(str(v)) > 100 else str(v) for k, v in sampling_params.items()}, indent=2)}")
            
            # Perform the sampling using FastMCP context
            if not hasattr(self.fastmcp_context, 'sample'):
                raise ToolError("Client does not support LLM sampling")
            
            response = await self.fastmcp_context.sample(**sampling_params)
            
            if self.enable_debug:
                logger.debug(f"✅ Sampling completed for tool: {self.tool_name}")
            
            # Return structured response
            if hasattr(response, 'text'):
                return TextContent(
                    text=response.text,
                    metadata={
                        "tool_name": self.tool_name,
                        "sampling_params": sampling_params,
                        "template_used": template.value if template else None
                    }
                )
            elif hasattr(response, 'data'):
                return ImageContent(
                    data=response.data,
                    mime_type=getattr(response, 'mime_type', 'image/png'),
                    metadata={
                        "tool_name": self.tool_name,
                        "sampling_params": sampling_params,
                        "template_used": template.value if template else None
                    }
                )
            else:
                # Fallback for unexpected response types
                return TextContent(
                    text=str(response),
                    metadata={
                        "tool_name": self.tool_name,
                        "sampling_params": sampling_params,
                        "template_used": template.value if template else None,
                        "response_type": type(response).__name__
                    }
                )
                
        except Exception as e:
            logger.error(f"❌ LLM sampling failed for tool {self.tool_name}: {e}")
            raise ToolError(f"LLM sampling failed: {str(e)}")
    
    def _prepare_messages(self, messages: Union[str, List[Union[str, SamplingMessage]]]) -> List[Dict[str, str]]:
        """Prepare messages for sampling request."""
        if isinstance(messages, str):
            return [{"role": "user", "content": messages}]
        
        prepared = []
        for msg in messages:
            if isinstance(msg, str):
                prepared.append({"role": "user", "content": msg})
            elif isinstance(msg, SamplingMessage):
                prepared.append({"role": msg.role, "content": msg.content})
            elif isinstance(msg, dict):
                prepared.append(msg)
            else:
                prepared.append({"role": "user", "content": str(msg)})
        
        return prepared
    
    def _prepare_model_preferences(self, preferences: Union[str, List[str], ModelPreferences]) -> Union[str, List[str]]:
        """Prepare model preferences for sampling request."""
        if isinstance(preferences, str):
            return preferences
        elif isinstance(preferences, list):
            return preferences
        elif isinstance(preferences, ModelPreferences):
            return preferences.preferred_models
        else:
            return str(preferences)

# ============================================================================
# ENHANCED SAMPLING MIDDLEWARE CLASS
# ============================================================================

class EnhancedSamplingMiddleware(Middleware):
    """
    Enhanced middleware that adds elicitation capabilities to tools with specific tags.
    
    This middleware:
    1. Detects tools with target tags ("gmail", "compose", "elicitation")
    2. Transforms those tools to add ctx: Context parameter using FastMCP's Tool.from_tool()
    3. Enhances ctx.sample() calls with user data, historical patterns, and templates
    """
    
    def __init__(
        self,
        enable_debug: bool = False,
        target_tags: Optional[List[str]] = None,
        blocked_tools: Optional[List[str]] = None,
        qdrant_middleware = None,
        template_middleware = None,
        default_enhancement_level: EnhancementLevel = EnhancementLevel.CONTEXTUAL
    ):
        """
        Initialize enhanced sampling middleware.
        
        Args:
            enable_debug: Enable detailed debug logging
            target_tags: Tags that trigger elicitation transformation (default: ["gmail", "compose", "elicitation"])
            blocked_tools: List of tool names that cannot use sampling
            qdrant_middleware: QdrantUnifiedMiddleware instance for historical context
            template_middleware: Template middleware for macro support
            default_enhancement_level: Default enhancement level for sampling
        """
        self.enable_debug = enable_debug
        self.target_tags = set(target_tags or ["gmail", "compose", "elicitation"])
        self.blocked_tools = blocked_tools or []
        self.qdrant_middleware = qdrant_middleware
        self.template_middleware = template_middleware
        self.default_enhancement_level = default_enhancement_level
        self.transformed_tools = set()  # Track which tools we've transformed
        
        logger.info("🎯 Enhanced SamplingMiddleware initialized")
        logger.info(f"   Debug logging: {'enabled' if enable_debug else 'disabled'}")
        logger.info(f"   Target tags: {list(self.target_tags)}")
        logger.info(f"   Blocked tools: {blocked_tools or 'none'}")
        logger.info(f"   Qdrant integration: {'enabled' if qdrant_middleware else 'disabled'}")
        logger.info(f"   Template integration: {'enabled' if template_middleware else 'disabled'}")
        logger.info(f"   Default enhancement level: {default_enhancement_level.value}")
    
    async def on_call_tool(self, context: MiddlewareContext, call_next):
        """
        Intercept tool calls and add elicitation capabilities to tools with specific tags.
        
        This hook:
        1. Checks if the tool has target tags ("gmail", "compose", "elicitation")
        2. Transforms the tool to add ctx: Context parameter for sampling
        3. Provides enhanced sampling capabilities when ctx.sample() is called
        """
        tool_name = getattr(context.message, 'name', 'unknown')
        
        if self.enable_debug:
            logger.debug(f"🔧 Processing tool call for elicitation: {tool_name}")
        
        # Check if we have FastMCP context
        if not hasattr(context, 'fastmcp_context') or not context.fastmcp_context:
            if self.enable_debug:
                logger.debug(f"⚠️ No FastMCP context available for tool: {tool_name}")
            return await call_next(context)
        
        try:
            # Get the tool object to check its tags
            tool = await context.fastmcp_context.fastmcp.get_tool(tool_name)
            
            # Check if this tool should have elicitation capabilities
            target_tags = {"gmail", "compose", "elicitation"}
            tool_tags = set(tool.tags) if tool.tags else set()
            
            has_target_tags = bool(target_tags.intersection(tool_tags))
            
            if self.enable_debug:
                logger.debug(f"🏷️ Tool '{tool_name}' tags: {tool_tags}")
                logger.debug(f"🎯 Has elicitation tags: {has_target_tags}")
            
            if has_target_tags:
                # Store enhanced context for this tool call
                self._store_enhanced_context(context, tool_name)
                if self.enable_debug:
                    logger.debug(f"✅ Enhanced context stored for elicitation-enabled tool: {tool_name}")
            
            # Continue with normal tool execution
            return await call_next(context)
            
        except Exception as e:
            if self.enable_debug:
                logger.debug(f"⚠️ Could not check tool tags for {tool_name}: {e}")
            # Continue without elicitation on error
            return await call_next(context)
    
    def _store_enhanced_context(self, context: MiddlewareContext, tool_name: str):
        """Store enhanced sampling context for tools that support elicitation."""
        try:
            # Create resource context manager
            resource_manager = ResourceContextManager(
                fastmcp_context=context.fastmcp_context,
                enable_debug=self.enable_debug
            )
            
            # Create history enhancer if Qdrant is available
            history_enhancer = QdrantHistoryEnhancer(
                qdrant_middleware=self.qdrant_middleware,
                enable_debug=self.enable_debug
            ) if self.qdrant_middleware else None
            
            # Create enhanced sampling context
            enhanced_context = EnhancedSamplingContext(
                fastmcp_context=context.fastmcp_context,
                tool_name=tool_name,
                enable_debug=self.enable_debug,
                resource_manager=resource_manager,
                history_enhancer=history_enhancer,
                template_middleware=self.template_middleware
            )
            
            # Store in context state for tools to access
            context.fastmcp_context.set_state(f"enhanced_sampling_{tool_name}", enhanced_context)
            
        except Exception as e:
            logger.error(f"❌ Failed to store enhanced context for {tool_name}: {e}")
    
    async def on_startup(self, mcp: FastMCP):
        """Transform tools with target tags to add elicitation capabilities."""
        if self.enable_debug:
            logger.debug("🔄 Starting tool transformation for elicitation capabilities...")
        
        # Get all registered tools
        tools = mcp._tool_manager.tools
        transformed_count = 0
        
        for tool_name, tool in tools.items():
            if tool_name in self.blocked_tools:
                continue
                
            # Check if tool has target tags
            tool_tags = set(tool.tags) if tool.tags else set()
            has_target_tags = bool(self.target_tags.intersection(tool_tags))
            
            if has_target_tags and tool_name not in self.transformed_tools:
                try:
                    # Create transform function that adds ctx parameter
                    transformed_tool = await self._create_elicitation_tool(tool)
                    
                    # Replace the original tool
                    mcp._tool_manager.tools[tool_name] = transformed_tool
                    self.transformed_tools.add(tool_name)
                    transformed_count += 1
                    
                    if self.enable_debug:
                        logger.debug(f"✅ Transformed tool '{tool_name}' to add elicitation capabilities")
                        
                except Exception as e:
                    logger.error(f"❌ Failed to transform tool '{tool_name}': {e}")
        
        logger.info(f"🎯 Transformed {transformed_count} tools to support elicitation")
    
    async def _create_elicitation_tool(self, original_tool: Tool) -> Tool:
        """Create a transformed tool that adds ctx: Context parameter for sampling."""
        
        async def elicitation_transform_fn(ctx: Annotated[Context, Field(description="FastMCP context for elicitation support and enhanced LLM sampling")], **kwargs):
            """
            Transform function that adds elicitation capabilities to the original tool.
            
            This function:
            1. Receives the ctx: Context parameter
            2. Enhances the context with our additional capabilities
            3. Calls the original tool with the enhanced context
            4. Post-processes the result if needed
            """
            try:
                # Store enhanced context for potential use
                if hasattr(ctx, 'set_state'):
                    enhanced_context = await self._create_enhanced_context(ctx, original_tool.name)
                    ctx.set_state(f"enhanced_sampling_{original_tool.name}", enhanced_context)
                
                # Call the original tool with all arguments
                result = await forward(**kwargs)
                
                # Optionally enhance the result based on tool tags
                if "compose" in (original_tool.tags or []):
                    # For compose tools, we could add elicitation prompts here
                    if self.enable_debug:
                        logger.debug(f"✨ Enhanced compose tool result for: {original_tool.name}")
                
                return result
                
            except Exception as e:
                logger.error(f"❌ Error in elicitation transform for {original_tool.name}: {e}")
                # Fallback to original tool behavior
                return await forward(**kwargs)
        
        # Create transformed tool using FastMCP's Tool.from_tool()
        transformed_tool = Tool.from_tool(
            original_tool,
            transform_fn=elicitation_transform_fn,
            name=original_tool.name,  # Keep same name
            description=f"{original_tool.description} [Enhanced with elicitation support]",
            # Tags remain the same to preserve functionality
        )
        
        return transformed_tool
    
    async def _create_enhanced_context(self, fastmcp_context: Context, tool_name: str):
        """Create enhanced sampling context with resource awareness."""
        try:
            # Create resource context manager
            resource_manager = ResourceContextManager(
                fastmcp_context=fastmcp_context,
                enable_debug=self.enable_debug
            )
            
            # Create history enhancer if Qdrant is available
            history_enhancer = QdrantHistoryEnhancer(
                qdrant_middleware=self.qdrant_middleware,
                enable_debug=self.enable_debug
            ) if self.qdrant_middleware else None
            
            # Create enhanced sampling context
            return EnhancedSamplingContext(
                fastmcp_context=fastmcp_context,
                tool_name=tool_name,
                enable_debug=self.enable_debug,
                resource_manager=resource_manager,
                history_enhancer=history_enhancer,
                template_middleware=self.template_middleware
            )
            
        except Exception as e:
            logger.error(f"❌ Failed to create enhanced context for {tool_name}: {e}")
            return None

# ============================================================================
# SETUP FUNCTIONS
# ============================================================================

def setup_enhanced_sampling_middleware(
    mcp: FastMCP,
    enable_debug: bool = False,
    target_tags: Optional[List[str]] = None,
    blocked_tools: Optional[List[str]] = None,
    qdrant_middleware = None,
    template_middleware = None,
    default_enhancement_level: EnhancementLevel = EnhancementLevel.CONTEXTUAL
) -> EnhancedSamplingMiddleware:
    """
    Set up enhanced sampling middleware for FastMCP server.
    
    This middleware enhances tools with specific tags ("gmail", "compose", "elicitation")
    to provide resource-aware LLM sampling capabilities via standard FastMCP Context.
    
    Args:
        mcp: FastMCP server instance
        enable_debug: Enable detailed debug logging
        target_tags: Tags that trigger elicitation enhancement (default: ["gmail", "compose", "elicitation"])
        blocked_tools: List of tool names that cannot use enhanced sampling
        qdrant_middleware: QdrantUnifiedMiddleware instance for historical context
        template_middleware: Template middleware for macro support
        default_enhancement_level: Default enhancement level for sampling
        
    Returns:
        EnhancedSamplingMiddleware: The configured middleware instance
        
    Example:
        ```python
        # Tools with target tags automatically get enhanced sampling capabilities
        @mcp.tool(tags={"gmail", "compose"})
        async def send_smart_email(recipient: str, topic: str, ctx: Context) -> str:
            '''Send email with LLM assistance.'''
            # Standard FastMCP sampling
            response = await ctx.sample(f"Compose an email to {recipient} about {topic}")
            
            # Enhanced sampling (if available via our middleware)
            enhanced_ctx = ctx.get_state("enhanced_sampling_send_smart_email")
            if enhanced_ctx:
                response = await enhanced_ctx.enhanced_sample(
                    f"Compose email with user context",
                    enhancement_level=EnhancementLevel.CONTEXTUAL
                )
            
            return response.text
        ```
    """
    # Create the enhanced middleware
    middleware = EnhancedSamplingMiddleware(
        enable_debug=enable_debug,
        target_tags=target_tags,
        blocked_tools=blocked_tools,
        qdrant_middleware=qdrant_middleware,
        template_middleware=template_middleware,
        default_enhancement_level=default_enhancement_level
    )
    
    # Register with the server
    mcp.add_middleware(middleware)
    
    logger.info(f"✅ Enhanced sampling middleware registered with server: {mcp.name}")
    return middleware

def setup_sampling_middleware(
    mcp: FastMCP,
    enable_debug: bool = False,
    auto_inject_context: bool = True,
    allowed_tools: Optional[List[str]] = None,
    blocked_tools: Optional[List[str]] = None
) -> 'SamplingMiddleware':
    """
    Set up sampling middleware for the FastMCP server.
    
    This function creates and registers the sampling middleware with the server,
    enabling tools to use LLM sampling capabilities via the injected context.
    
    Args:
        mcp: FastMCP server instance
        enable_debug: Enable detailed debug logging
        auto_inject_context: Automatically inject sampling context into all tools
        allowed_tools: List of tool names that can use sampling (None = all allowed)
        blocked_tools: List of tool names that cannot use sampling
        
    Returns:
        SamplingMiddleware: The configured middleware instance
        
    Example:
        ```python
        from fastmcp import FastMCP
        from middleware.sampling_middleware import setup_sampling_middleware
        
        mcp = FastMCP("My Server")
        
        # Set up sampling middleware
        sampling_middleware = setup_sampling_middleware(
            mcp,
            enable_debug=True,
            allowed_tools=["analyze_sentiment", "generate_summary"]
        )
        
        # Define a tool that uses sampling
        @mcp.tool
        async def analyze_sentiment(text: str, ctx) -> dict:
            '''Analyze sentiment using LLM sampling.'''
            response = await ctx.sample(
                f"Analyze the sentiment of this text: {text}",
                template=SamplingTemplate.SENTIMENT_ANALYSIS
            )
            return {"sentiment": response.text.strip(), "original_text": text}
        ```
    """
    # Create the middleware
    middleware = SamplingMiddleware(
        enable_debug=enable_debug,
        auto_inject_context=auto_inject_context,
        allowed_tools=allowed_tools,
        blocked_tools=blocked_tools
    )
    
    # Register with the server
    mcp.add_middleware(middleware)
    
    logger.info(f"✅ Sampling middleware registered with server: {mcp.name}")
    return middleware

# Backward compatibility alias
SamplingMiddleware = EnhancedSamplingMiddleware

def create_sampling_context(
    fastmcp_context,
    tool_name: str,
    enable_debug: bool = False
) -> SamplingContext:
    """
    Create a standalone sampling context for manual injection.
    
    This function can be used when you need to manually create a sampling
    context instead of using the automatic middleware injection.
    
    Args:
        fastmcp_context: FastMCP context for sampling operations
        tool_name: Name of the tool using this context
        enable_debug: Enable debug logging
        
    Returns:
        SamplingContext: Configured sampling context
    """
    return SamplingContext(
        fastmcp_context=fastmcp_context,
        tool_name=tool_name,
        enable_debug=enable_debug
    )

# ============================================================================
# SAMPLING UTILITIES
# ============================================================================

class SamplingUtils:
    """Utility functions for common sampling operations."""
    
    @staticmethod
    async def analyze_sentiment(
        ctx: SamplingContext,
        text: str,
        detailed: bool = False
    ) -> Dict[str, Any]:
        """
        Analyze sentiment using LLM sampling.
        
        Args:
            ctx: Sampling context
            text: Text to analyze
            detailed: Return detailed analysis
            
        Returns:
            Dictionary with sentiment analysis results
        """
        prompt = f"Analyze the sentiment of this text: {text}"
        if detailed:
            prompt += "\nProvide a detailed explanation of the sentiment indicators."
            
        response = await ctx.sample(
            prompt,
            template=SamplingTemplate.SENTIMENT_ANALYSIS,
            max_tokens=200 if detailed else 50
        )
        
        return {
            "text": text,
            "sentiment": response.text.strip(),
            "detailed": detailed
        }
    
    @staticmethod
    async def generate_summary(
        ctx: SamplingContext,
        content: str,
        max_length: int = 300
    ) -> Dict[str, Any]:
        """
        Generate summary using LLM sampling.
        
        Args:
            ctx: Sampling context
            content: Content to summarize
            max_length: Maximum summary length in characters
            
        Returns:
            Dictionary with summary results
        """
        response = await ctx.sample(
            f"Summarize this content in about {max_length} characters: {content}",
            template=SamplingTemplate.SUMMARIZATION,
            max_tokens=max_length // 3  # Rough token estimation
        )
        
        return {
            "original_content": content,
            "summary": response.text.strip(),
            "requested_length": max_length,
            "actual_length": len(response.text)
        }
    
    @staticmethod
    async def generate_code(
        ctx: SamplingContext,
        description: str,
        language: str = "python",
        include_comments: bool = True
    ) -> Dict[str, Any]:
        """
        Generate code using LLM sampling.
        
        Args:
            ctx: Sampling context
            description: Description of what the code should do
            language: Programming language
            include_comments: Include code comments
            
        Returns:
            Dictionary with code generation results
        """
        prompt = f"Generate {language} code for: {description}"
        if include_comments:
            prompt += " Include helpful comments."
            
        response = await ctx.sample(
            prompt,
            template=SamplingTemplate.CODE_GENERATION,
            max_tokens=600
        )
        
        return {
            "description": description,
            "language": language,
            "code": response.text.strip(),
            "includes_comments": include_comments
        }

# ============================================================================
# DEMO TOOLS FOR ENHANCED SAMPLING
# ============================================================================

def setup_enhanced_sampling_demo_tools(mcp: FastMCP):
    """Setup demo tools that showcase enhanced sampling capabilities."""
    
    # Import required types
    from typing_extensions import TypedDict, NotRequired
    from typing import Optional, List
    from tools.common_types import UserGoogleEmail
    
    # Define structured response types for all demo tools
    class EmailComposerResponse(TypedDict):
        """Response structure for intelligent_email_composer tool."""
        success: bool
        recipient: str
        topic: str
        style: str
        composed_text: NotRequired[str]
        resources_used: NotRequired[List[str]]
        template_suggestions: NotRequired[List[str]]
        userEmail: NotRequired[str]
        error: NotRequired[Optional[str]]
    
    class WorkflowAssistantResponse(TypedDict):
        """Response structure for smart_workflow_assistant tool."""
        success: bool
        task_description: str
        include_history: bool
        workflow_suggestions: NotRequired[str]
        historical_patterns: NotRequired[List[str]]
        recommended_tools: NotRequired[List[str]]
        userEmail: NotRequired[str]
        error: NotRequired[Optional[str]]
    
    class TemplateRenderingResponse(TypedDict):
        """Response structure for template_rendering_demo tool."""
        success: bool
        template_type: str
        render_examples: bool
        rendered_examples: NotRequired[str]
        available_macros: NotRequired[List[str]]
        usage_tips: NotRequired[List[str]]
        userEmail: NotRequired[str]
        error: NotRequired[Optional[str]]
    
    class ResourceDiscoveryResponse(TypedDict):
        """Response structure for resource_discovery_assistant tool."""
        success: bool
        use_case: str
        discovered_resources: NotRequired[str]
        resource_examples: NotRequired[List[str]]
        integration_patterns: NotRequired[List[str]]
        userEmail: NotRequired[str]
        error: NotRequired[Optional[str]]
    
    @mcp.tool(
        name="intelligent_email_composer",
        description="Compose emails using resource-aware sampling with macro suggestions",
        tags={"sampling", "email", "demo", "macro-aware"},
        annotations={
            "title": "Intelligent Email Composer",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True
        }
    )
    async def intelligent_email_composer(
        recipient: str,
        topic: str,
        style: str = "professional",
        user_google_email: UserGoogleEmail = None,
        ctx: Context = None
    ) -> EmailComposerResponse:
        """
        Compose emails using macro-aware sampling with real user data.
        
        Args:
            recipient: Email recipient
            topic: Email topic
            style: Email style (professional, friendly, formal)
            user_google_email: User's email address (auto-injected if None)
            ctx: Sampling context (automatically injected)
        """
        if not ctx:
            return EmailComposerResponse(
                success=False,
                recipient=recipient,
                topic=topic,
                style=style,
                userEmail=user_google_email or "",
                error="Context not available"
            )
        
        try:
            # Use standard FastMCP ctx.sample() instead of enhanced_sample
            prompt = f"""
I need to compose an email to {recipient} about {topic}.
Style preference: {style}

Please create a complete email using the beautiful_email macro with:
1. My actual name and email from user resources
2. Appropriate signature style ({style})
3. Content relevant to the topic
4. Professional formatting using available gradients

Include the full macro call I can use.
"""
            
            response = await ctx.sample(
                messages=prompt,
                system_prompt="You are an intelligent email assistant with access to sophisticated email templates.",
                temperature=0.3,
                max_tokens=800
            )
            
            return EmailComposerResponse(
                success=True,
                recipient=recipient,
                topic=topic,
                style=style,
                composed_text=response.text,
                resources_used=["user://current/email", "template://macros"],
                template_suggestions=["render_beautiful_email", "render_gmail_labels_chips"],
                userEmail=user_google_email or ""
            )
        except Exception as e:
            logger.error(f"Error in intelligent_email_composer: {e}")
            return EmailComposerResponse(
                success=False,
                recipient=recipient,
                topic=topic,
                style=style,
                userEmail=user_google_email or "",
                error=str(e)
            )
    
    @mcp.tool(
        name="smart_workflow_assistant",
        description="Get workflow suggestions based on user context and historical patterns",
        tags={"sampling", "workflow", "demo", "historical"},
        annotations={
            "title": "Smart Workflow Assistant",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True
        }
    )
    async def smart_workflow_assistant(
        task_description: str,
        include_history: bool = True,
        user_google_email: UserGoogleEmail = None,
        ctx: Context = None
    ) -> WorkflowAssistantResponse:
        """
        Provide smart workflow suggestions using historical patterns and current context.
        
        Args:
            task_description: Description of the task needing workflow help
            include_history: Whether to include historical patterns from Qdrant
            user_google_email: User's email address (auto-injected if None)
            ctx: Sampling context (automatically injected)
        """
        if not ctx:
            return WorkflowAssistantResponse(
                success=False,
                task_description=task_description,
                include_history=include_history,
                userEmail=user_google_email or "",
                error="Context not available"
            )
        
        try:
            # Use standard FastMCP ctx.sample()
            prompt = f"""
I need help creating a workflow for: {task_description}

Please suggest a step-by-step workflow that:
1. Uses my available tools and resources
2. Takes into account my current workspace setup
3. References specific tools by name with working examples
4. Considers my Gmail labels and Drive organization
5. {'Includes patterns from my previous successful workflows' if include_history else 'Focuses on current capabilities'}

Provide actionable steps with specific tool recommendations.
"""
            
            response = await ctx.sample(
                messages=prompt,
                system_prompt="You are a workflow optimization expert with access to the user's workspace and tools.",
                temperature=0.4,
                max_tokens=800
            )
            
            return WorkflowAssistantResponse(
                success=True,
                task_description=task_description,
                include_history=include_history,
                workflow_suggestions=response.text,
                historical_patterns=["Previous successful workflows analyzed"] if include_history else [],
                recommended_tools=["service://gmail/labels", "service://drive/items", "tools://enhanced/list"],
                userEmail=user_google_email or ""
            )
        except Exception as e:
            logger.error(f"Error in smart_workflow_assistant: {e}")
            return WorkflowAssistantResponse(
                success=False,
                task_description=task_description,
                include_history=include_history,
                userEmail=user_google_email or "",
                error=str(e)
            )
    
    @mcp.tool(
        name="template_rendering_demo",
        description="Demonstrate template rendering with and without execution",
        tags={"sampling", "templates", "demo", "rendering"},
        annotations={
            "title": "Template Rendering Demo",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True
        }
    )
    async def template_rendering_demo(
        template_type: str = "email",
        render_examples: bool = False,
        user_google_email: UserGoogleEmail = None,
        ctx: Context = None
    ) -> TemplateRenderingResponse:
        """
        Show template usage examples with rendering demonstrations.
        
        Args:
            template_type: Type of template to demonstrate (email, document)
            render_examples: Whether to show rendered examples
            user_google_email: User's email address (auto-injected if None)
            ctx: Sampling context (automatically injected)
        """
        if not ctx:
            return TemplateRenderingResponse(
                success=False,
                template_type=template_type,
                render_examples=render_examples,
                userEmail=user_google_email or "",
                error="Context not available"
            )
        
        try:
            # Build demo results manually since we're using standard ctx.sample()
            demo_results = {
                "template_name": template_type,
                "render_requested": render_examples,
                "examples": {}
            }
            
            if "email" in template_type.lower():
                demo_results["examples"] = {
                    "beautiful_email_template": """
{{ render_beautiful_email(
    title="Weekly Status Update",
    content_sections=[{
        'type': 'text',
        'content': 'Hi team! Here's our weekly update...'
    }],
    user_name="{{user://current/email.name}}",
    user_email="{{user://current/email.email}}",
    signature_style="professional"
) }}
""",
                    "gmail_labels_template": """
{{ render_gmail_labels_chips(
    service://gmail/labels,
    'Gmail Organization for: ' + user://current/email.email
) }}
"""
                }
            elif "document" in template_type.lower():
                demo_results["examples"] = {
                    "report_template": """
{{ generate_report_doc(
    report_title="Monthly Metrics Report",
    metrics=[{
        "value": "{{recent://all.total_items_across_services}}",
        "label": "Total Items",
        "change": 15
    }],
    table_data=[["Metric", "Value"], ["Items", "{{recent://all.total_items_across_services}}"]]
) }}
"""
                }
            
            # Format the demo results
            formatted_output = [
                f"🎭 **Template Rendering Demo: {demo_results['template_name']}**",
                f"Render requested: {demo_results['render_requested']}",
                "",
                "📋 **Available Template Examples:**"
            ]
            
            available_macros = []
            for name, template_code in demo_results.get("examples", {}).items():
                formatted_output.extend([
                    f"\n**{name.replace('_', ' ').title()}:**",
                    "```jinja2",
                    template_code.strip(),
                    "```"
                ])
                available_macros.append(name)
            
            if demo_results.get("rendered_examples"):
                formatted_output.extend([
                    "",
                    "🎨 **Rendered Examples:**"
                ])
                for name, rendered_data in demo_results["rendered_examples"].items():
                    formatted_output.extend([
                        f"\n**{name}:**",
                        rendered_data.get("note", "Rendered content would appear here")
                    ])
            
            if demo_results.get("render_error"):
                formatted_output.extend([
                    "",
                    f"⚠️ **Render Error:** {demo_results['render_error']}"
                ])
            
            usage_tips = [
                "Use {{ }} for variable interpolation",
                "Access resources via URI patterns like service://gmail/labels",
                "Combine macros for complex templates"
            ]
            
            return TemplateRenderingResponse(
                success=True,
                template_type=template_type,
                render_examples=render_examples,
                rendered_examples="\n".join(formatted_output),
                available_macros=available_macros,
                usage_tips=usage_tips,
                userEmail=user_google_email or ""
            )
        except Exception as e:
            logger.error(f"Error in template_rendering_demo: {e}")
            return TemplateRenderingResponse(
                success=False,
                template_type=template_type,
                render_examples=render_examples,
                userEmail=user_google_email or "",
                error=str(e)
            )
    
    @mcp.tool(
        name="resource_discovery_assistant",
        description="Discover available resources and show usage examples",
        tags={"sampling", "resources", "demo", "discovery"},
        annotations={
            "title": "Resource Discovery Assistant",
            "readOnlyHint": True,  # Only discovers, doesn't modify
            "destructiveHint": False,
            "idempotentHint": True
        }
    )
    async def resource_discovery_assistant(
        use_case: str,
        user_google_email: UserGoogleEmail = None,
        ctx: Context = None
    ) -> ResourceDiscoveryResponse:
        """
        Help discover and utilize available FastMCP resources for specific use cases.
        
        Args:
            use_case: The use case to find resources for
            user_google_email: User's email address (auto-injected if None)
            ctx: Sampling context (automatically injected)
        """
        if not ctx:
            return ResourceDiscoveryResponse(
                success=False,
                use_case=use_case,
                userEmail=user_google_email or "",
                error="Context not available"
            )
        
        try:
            # Use standard FastMCP ctx.sample()
            prompt = f"""
I need help discovering resources for: {use_case}

Please help me understand:
1. What FastMCP resources are available for this use case
2. How to access user data, Gmail, Drive, and workspace content
3. Working resource URI examples I can use
4. Resource combinations for complex workflows
5. Best practices for resource usage

Focus on practical examples with actual resource URIs.
"""
            
            response = await ctx.sample(
                messages=prompt,
                system_prompt="You are a resource discovery expert for the FastMCP2 platform.",
                temperature=0.2,
                max_tokens=600
            )
            
            resource_examples = [
                "user://current/email - Current user email",
                "service://gmail/labels - Gmail labels",
                "recent://drive/7 - Recent Drive files",
                "template://macros - Template macros",
                "qdrant://search/{query} - Vector search"
            ]
            
            integration_patterns = [
                "Email with labels: render_gmail_labels_chips(service://gmail/labels)",
                "Recent files: recent://drive/7 for last 7 days",
                "Calendar dashboard: render_calendar_dashboard(service://calendar/events)"
            ]
            
            return ResourceDiscoveryResponse(
                success=True,
                use_case=use_case,
                discovered_resources=response.text,
                resource_examples=resource_examples,
                integration_patterns=integration_patterns,
                userEmail=user_google_email or ""
            )
        except Exception as e:
            logger.error(f"Error in resource_discovery_assistant: {e}")
            return ResourceDiscoveryResponse(
                success=False,
                use_case=use_case,
                userEmail=user_google_email or "",
                error=str(e)
            )

    logger.info("✅ Enhanced sampling demo tools registered")
    logger.info("   Tools: intelligent_email_composer, smart_workflow_assistant, template_rendering_demo, resource_discovery_assistant")