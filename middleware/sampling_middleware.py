#!/usr/bin/env python3
"""
Sampling Middleware for FastMCP2

This middleware provides LLM sampling capabilities to MCP tools by injecting
a sampling context that tools can use to request text generation from the 
client's LLM. It follows FastMCP's sampling pattern for context-aware AI assistance.

Key Features:
- Automatic sampling context injection into tool calls
- Support for various sampling parameters (temperature, max_tokens, etc.)
- Model preference handling
- System prompt support  
- Structured message handling
- Comprehensive error handling and logging
- Template support for common sampling patterns

Usage:
    from middleware.sampling_middleware import setup_sampling_middleware
    
    # After server creation but before tool registrations:
    sampling_middleware = setup_sampling_middleware(mcp)
"""

import json
import logging
from typing import Any, Dict, Optional, List, Union
from dataclasses import dataclass
from enum import Enum

from fastmcp import FastMCP
from fastmcp.server.middleware import Middleware, MiddlewareContext
from fastmcp.exceptions import ToolError

# Configure logging
logger = logging.getLogger(__name__)

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
# SAMPLING CONTEXT CLASS
# ============================================================================

class SamplingContext:
    """
    Sampling context that provides LLM sampling capabilities to tools.
    
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
# SAMPLING MIDDLEWARE CLASS
# ============================================================================

class SamplingMiddleware(Middleware):
    """
    Middleware that provides LLM sampling capabilities to MCP tools.
    
    This middleware intercepts tool calls and injects a SamplingContext
    that tools can use to request text generation from the client's LLM.
    It follows FastMCP's sampling pattern and provides comprehensive
    error handling and logging.
    """
    
    def __init__(
        self,
        enable_debug: bool = False,
        auto_inject_context: bool = True,
        allowed_tools: Optional[List[str]] = None,
        blocked_tools: Optional[List[str]] = None
    ):
        """
        Initialize sampling middleware.
        
        Args:
            enable_debug: Enable detailed debug logging
            auto_inject_context: Automatically inject sampling context into all tools
            allowed_tools: List of tool names that can use sampling (None = all allowed)
            blocked_tools: List of tool names that cannot use sampling
        """
        self.enable_debug = enable_debug
        self.auto_inject_context = auto_inject_context
        self.allowed_tools = allowed_tools
        self.blocked_tools = blocked_tools or []
        
        logger.info("🎯 SamplingMiddleware initialized")
        logger.info(f"   Debug logging: {'enabled' if enable_debug else 'disabled'}")
        logger.info(f"   Auto-inject context: {'enabled' if auto_inject_context else 'disabled'}")
        logger.info(f"   Allowed tools: {allowed_tools or 'all'}")
        logger.info(f"   Blocked tools: {blocked_tools or 'none'}")
    
    async def on_call_tool(self, context: MiddlewareContext, call_next):
        """
        Intercept tool calls and inject sampling context.
        
        This hook is called when a tool is being executed. We:
        1. Check if sampling is allowed for this tool
        2. Create a SamplingContext if FastMCP context is available  
        3. Inject the context into the tool arguments
        4. Continue with the tool execution
        """
        tool_name = getattr(context.message, 'name', 'unknown')
        
        if self.enable_debug:
            logger.debug(f"🔧 Processing tool call for sampling: {tool_name}")
        
        # Check if this tool is allowed to use sampling
        if not self._is_sampling_allowed(tool_name):
            if self.enable_debug:
                logger.debug(f"🚫 Sampling not allowed for tool: {tool_name}")
            return await call_next(context)
        
        # Check if we have FastMCP context for sampling
        if not hasattr(context, 'fastmcp_context') or not context.fastmcp_context:
            if self.enable_debug:
                logger.debug(f"⚠️ No FastMCP context available for sampling in tool: {tool_name}")
            return await call_next(context)
        
        try:
            # Create sampling context
            sampling_context = SamplingContext(
                fastmcp_context=context.fastmcp_context,
                tool_name=tool_name,
                enable_debug=self.enable_debug
            )
            
            # Inject sampling context into tool arguments if auto-injection is enabled
            if self.auto_inject_context:
                original_args = getattr(context.message, 'arguments', {})
                
                # Add sampling context as 'ctx' parameter if not already present
                if 'ctx' not in original_args:
                    context.message.arguments = {**original_args, 'ctx': sampling_context}
                    if self.enable_debug:
                        logger.debug(f"✅ Injected sampling context into tool: {tool_name}")
            
            # Continue with the tool execution
            return await call_next(context)
            
        except Exception as e:
            logger.error(f"❌ Failed to inject sampling context for tool {tool_name}: {e}")
            # Continue without sampling context on error
            return await call_next(context)
    
    def _is_sampling_allowed(self, tool_name: str) -> bool:
        """Check if sampling is allowed for the given tool."""
        
        # Check blocked list first
        if tool_name in self.blocked_tools:
            return False
            
        # Check allowed list if specified
        if self.allowed_tools is not None:
            return tool_name in self.allowed_tools
            
        # Default: allow all tools not explicitly blocked
        return True

# ============================================================================
# SETUP FUNCTIONS
# ============================================================================

def setup_sampling_middleware(
    mcp: FastMCP,
    enable_debug: bool = False,
    auto_inject_context: bool = True,
    allowed_tools: Optional[List[str]] = None,
    blocked_tools: Optional[List[str]] = None
) -> SamplingMiddleware:
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