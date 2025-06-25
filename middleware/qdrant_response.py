"""Qdrant Response Middleware for storing and summarizing tool responses."""

import json
import logging
import hashlib
import uuid
from datetime import datetime
from typing import Any, Dict, Optional, List
import asyncio

from fastmcp.server.middleware import Middleware, MiddlewareContext
from qdrant_client import QdrantClient, models
from qdrant_client.models import Distance, VectorParams, PointStruct
from sentence_transformers import SentenceTransformer
import numpy as np

logger = logging.getLogger(__name__)


class QdrantResponseMiddleware(Middleware):
    """
    Middleware that stores tool responses in Qdrant and returns summaries.
    
    This middleware intercepts all tool responses, stores them in a Qdrant
    vector database with embeddings, and returns summarized versions to
    reduce token usage unless verbose mode is requested.
    """
    
    def __init__(
        self,
        qdrant_host: str = "localhost",
        qdrant_port: int = 6333,
        collection_name: str = "mcp_tool_responses",
        embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2",
        summary_max_tokens: int = 500,
        verbose_param: str = "verbose",
        enabled: bool = True
    ):
        """
        Initialize the Qdrant response middleware.
        
        Args:
            qdrant_host: Qdrant server hostname
            qdrant_port: Qdrant server port
            collection_name: Name of the collection to store responses
            embedding_model: Model to use for generating embeddings
            summary_max_tokens: Maximum tokens in summarized response
            verbose_param: Parameter name to check for verbose mode
            enabled: Whether the middleware is enabled
        """
        self.enabled = enabled
        self.qdrant_host = qdrant_host
        self.qdrant_port = qdrant_port
        self.collection_name = collection_name
        self.summary_max_tokens = summary_max_tokens
        self.verbose_param = verbose_param
        
        if self.enabled:
            try:
                # Initialize Qdrant client
                self.client = QdrantClient(host=qdrant_host, port=qdrant_port)
                
                # Initialize embedding model
                logger.info(f"Loading embedding model: {embedding_model}")
                self.embedder = SentenceTransformer(embedding_model)
                self.embedding_dim = self.embedder.get_sentence_embedding_dimension()
                
                # Ensure collection exists
                self._ensure_collection()
                
                logger.info(f"QdrantResponseMiddleware initialized successfully")
                
            except Exception as e:
                logger.error(f"Failed to initialize QdrantResponseMiddleware: {e}")
                logger.warning("Middleware will be disabled")
                self.enabled = False
    
    def _ensure_collection(self):
        """Ensure the Qdrant collection exists with proper configuration."""
        try:
            # Check if collection exists
            collections = self.client.get_collections()
            collection_names = [c.name for c in collections.collections]
            
            if self.collection_name not in collection_names:
                # Create collection
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(
                        size=self.embedding_dim,
                        distance=Distance.COSINE
                    )
                )
                logger.info(f"Created Qdrant collection: {self.collection_name}")
            else:
                logger.info(f"Using existing Qdrant collection: {self.collection_name}")
                
        except Exception as e:
            logger.error(f"Failed to ensure collection exists: {e}")
            raise
    
    async def on_call_tool(self, context: MiddlewareContext, call_next):
        """
        Intercept tool calls to store responses in Qdrant.
        
        Args:
            context: Middleware context containing tool information
            call_next: Function to call the next middleware/handler
        """
        if not self.enabled:
            return await call_next(context)
        
        # Extract tool information
        tool_name = getattr(context.message, 'name', 'unknown')
        tool_args = getattr(context.message, 'arguments', {})
        
        # Check if verbose mode is requested
        is_verbose = tool_args.get(self.verbose_param, False)
        
        # Record start time
        start_time = datetime.utcnow()
        
        try:
            # Execute the tool
            result = await call_next(context)
            
            # Calculate execution time
            execution_time_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            
            # Store response in Qdrant (async)
            asyncio.create_task(self._store_response(
                tool_name=tool_name,
                tool_args=tool_args,
                response=result,
                execution_time_ms=execution_time_ms,
                context=context
            ))
            
            # Return full response if verbose, otherwise summarize
            if is_verbose:
                logger.debug(f"Verbose mode requested for {tool_name}, returning full response")
                return result
            
            # Generate summary
            summary = self._generate_summary(tool_name, result)
            
            # Create summarized response
            if hasattr(result, 'content'):
                # For standard tool responses
                result.content = summary
            elif isinstance(result, dict) and 'content' in result:
                # For dict responses
                result['content'] = summary
            elif isinstance(result, str):
                # For string responses
                result = summary
            
            return result
            
        except Exception as e:
            # Log error but don't break tool execution
            logger.error(f"Error in QdrantResponseMiddleware for {tool_name}: {e}")
            # Re-raise the original error
            raise
    
    async def _store_response(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        response: Any,
        execution_time_ms: int,
        context: MiddlewareContext
    ):
        """
        Store the tool response in Qdrant.
        
        Args:
            tool_name: Name of the tool
            tool_args: Arguments passed to the tool
            response: The tool's response
            execution_time_ms: Execution time in milliseconds
            context: Middleware context
        """
        try:
            # Convert response to string for embedding
            response_text = self._response_to_text(response)
            
            # Generate embedding
            embedding = self.embedder.encode(response_text).tolist()
            
            # Extract session and user info
            session_id = None
            user_email = None
            
            if context.fastmcp_context:
                session_id = context.fastmcp_context.session_id
                # Try to extract user email from args
                for key in ['user_email', 'user_google_email', 'email']:
                    if key in tool_args:
                        user_email = tool_args[key]
                        break
            
            # Create unique ID
            point_id = str(uuid.uuid4())
            
            # Prepare payload
            payload = {
                "tool_name": tool_name,
                "timestamp": datetime.utcnow().isoformat(),
                "user_email": user_email,
                "session_id": session_id,
                "request_args": json.dumps(tool_args),
                "full_response": json.dumps(self._serialize_response(response)),
                "summary": self._generate_summary(tool_name, response),
                "response_size": len(response_text),
                "execution_time_ms": execution_time_ms
            }
            
            # Store in Qdrant
            self.client.upsert(
                collection_name=self.collection_name,
                points=[
                    PointStruct(
                        id=point_id,
                        vector=embedding,
                        payload=payload
                    )
                ]
            )
            
            logger.debug(f"Stored response for {tool_name} in Qdrant (ID: {point_id})")
            
        except Exception as e:
            logger.error(f"Failed to store response in Qdrant: {e}")
    
    def _response_to_text(self, response: Any) -> str:
        """Convert a response to text for embedding."""
        if isinstance(response, str):
            return response
        elif hasattr(response, 'content'):
            return str(response.content)
        elif isinstance(response, dict):
            return json.dumps(response, indent=2)
        elif isinstance(response, list):
            return json.dumps(response, indent=2)
        else:
            return str(response)
    
    def _serialize_response(self, response: Any) -> Any:
        """Serialize response for JSON storage."""
        if isinstance(response, (str, int, float, bool, type(None))):
            return response
        elif isinstance(response, (list, dict)):
            return response
        elif hasattr(response, '__dict__'):
            return response.__dict__
        else:
            return str(response)
    
    def _generate_summary(self, tool_name: str, response: Any) -> str:
        """
        Generate a summary of the response based on its type and size.
        
        Args:
            tool_name: Name of the tool
            response: The response to summarize
            
        Returns:
            Summarized version of the response
        """
        response_text = self._response_to_text(response)
        response_len = len(response_text)
        
        # Small responses - return as is
        if response_len < 1000:
            return response_text
        
        # Handle different response types
        if hasattr(response, 'content'):
            content = response.content
        elif isinstance(response, dict) and 'content' in response:
            content = response['content']
        else:
            content = response
        
        # List responses
        if isinstance(content, list):
            count = len(content)
            if count == 0:
                return f"Empty list returned by {tool_name}"
            
            # Show first few items
            preview_items = content[:3]
            preview_str = json.dumps(preview_items, indent=2)[:500]
            
            if count > 3:
                return f"List with {count} items from {tool_name}:\n{preview_str}\n... and {count - 3} more items"
            else:
                return f"List with {count} items from {tool_name}:\n{preview_str}"
        
        # Dictionary responses
        elif isinstance(content, dict):
            keys = list(content.keys())
            key_count = len(keys)
            
            if key_count == 0:
                return f"Empty dictionary returned by {tool_name}"
            
            # Show structure with some values
            summary_dict = {}
            char_count = 0
            
            for key in keys:
                value = content[key]
                if isinstance(value, (list, dict)):
                    if isinstance(value, list):
                        summary_dict[key] = f"<list with {len(value)} items>"
                    else:
                        summary_dict[key] = f"<dict with {len(value)} keys>"
                else:
                    value_str = str(value)[:100]
                    summary_dict[key] = value_str + "..." if len(str(value)) > 100 else value_str
                
                char_count += len(key) + len(str(summary_dict[key]))
                if char_count > 500:
                    remaining = key_count - len(summary_dict)
                    if remaining > 0:
                        summary_dict["..."] = f"and {remaining} more keys"
                    break
            
            return f"Dictionary response from {tool_name}:\n{json.dumps(summary_dict, indent=2)}"
        
        # String responses
        elif isinstance(content, str):
            lines = content.split('\n')
            line_count = len(lines)
            
            if line_count > 10:
                preview = '\n'.join(lines[:5])
                return f"Text response from {tool_name} ({line_count} lines, {response_len} chars):\n{preview}\n... and {line_count - 5} more lines"
            else:
                if response_len > 1000:
                    return f"Text response from {tool_name} ({response_len} chars):\n{content[:500]}..."
                else:
                    return content
        
        # Default case
        else:
            content_str = str(content)
            if len(content_str) > 500:
                return f"Response from {tool_name} ({type(content).__name__}):\n{content_str[:500]}..."
            else:
                return f"Response from {tool_name}: {content_str}"


# Utility functions for creating search tools
async def create_qdrant_search_tool(mcp, collection_name: str = "mcp_tool_responses"):
    """
    Create a tool for searching historical tool responses in Qdrant.
    
    Args:
        mcp: FastMCP instance
        collection_name: Qdrant collection name
    """
    
    @mcp.tool
    async def search_tool_history(
        query: str,
        limit: int = 10,
        tool_name: Optional[str] = None,
        user_email: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Search through historical tool responses stored in Qdrant.
        
        Args:
            query: Search query text
            limit: Maximum number of results to return
            tool_name: Filter by specific tool name
            user_email: Filter by user email
            
        Returns:
            Search results with relevant tool responses
        """
        try:
            # Initialize client and embedder
            client = QdrantClient(host="localhost", port=6333)
            embedder = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
            
            # Generate query embedding
            query_vector = embedder.encode(query).tolist()
            
            # Build filter conditions
            filter_conditions = []
            if tool_name:
                filter_conditions.append(
                    models.FieldCondition(
                        key="tool_name",
                        match=models.MatchValue(value=tool_name)
                    )
                )
            if user_email:
                filter_conditions.append(
                    models.FieldCondition(
                        key="user_email",
                        match=models.MatchValue(value=user_email)
                    )
                )
            
            # Search
            search_result = client.search(
                collection_name=collection_name,
                query_vector=query_vector,
                limit=limit,
                query_filter=models.Filter(
                    must=filter_conditions
                ) if filter_conditions else None
            )
            
            # Format results
            results = []
            for hit in search_result:
                payload = hit.payload
                results.append({
                    "score": hit.score,
                    "tool_name": payload.get("tool_name"),
                    "timestamp": payload.get("timestamp"),
                    "user_email": payload.get("user_email"),
                    "summary": payload.get("summary"),
                    "execution_time_ms": payload.get("execution_time_ms"),
                    "request_args": json.loads(payload.get("request_args", "{}")),
                })
            
            return {
                "query": query,
                "results_count": len(results),
                "results": results
            }
            
        except Exception as e:
            logger.error(f"Error searching tool history: {e}")
            return {
                "error": str(e),
                "query": query,
                "results": []
            }
    
    return search_tool_history


async def create_qdrant_analytics_tool(mcp, collection_name: str = "mcp_tool_responses"):
    """
    Create a tool for getting analytics on tool usage.
    
    Args:
        mcp: FastMCP instance
        collection_name: Qdrant collection name
    """
    
    @mcp.tool
    async def get_tool_analytics(
        tool_name: Optional[str] = None,
        user_email: Optional[str] = None,
        days: int = 7
    ) -> Dict[str, Any]:
        """
        Get usage analytics for tools.
        
        Args:
            tool_name: Filter by specific tool name
            user_email: Filter by user email
            days: Number of days to look back
            
        Returns:
            Analytics data including usage counts and performance metrics
        """
        try:
            # Initialize client
            client = QdrantClient(host="localhost", port=6333)
            
            # Calculate date filter
            cutoff_date = (datetime.utcnow() - timedelta(days=days)).isoformat()
            
            # Build filter
            filter_conditions = [
                models.FieldCondition(
                    key="timestamp",
                    range=models.Range(gte=cutoff_date)
                )
            ]
            
            if tool_name:
                filter_conditions.append(
                    models.FieldCondition(
                        key="tool_name",
                        match=models.MatchValue(value=tool_name)
                    )
                )
            if user_email:
                filter_conditions.append(
                    models.FieldCondition(
                        key="user_email",
                        match=models.MatchValue(value=user_email)
                    )
                )
            
            # Get all matching points (limited to 1000 for performance)
            points = client.scroll(
                collection_name=collection_name,
                scroll_filter=models.Filter(must=filter_conditions),
                limit=1000
            )[0]
            
            # Analyze data
            tool_stats = {}
            user_stats = {}
            total_executions = 0
            total_time = 0
            
            for point in points:
                payload = point.payload
                tool = payload.get("tool_name", "unknown")
                user = payload.get("user_email", "anonymous")
                exec_time = payload.get("execution_time_ms", 0)
                
                # Update tool stats
                if tool not in tool_stats:
                    tool_stats[tool] = {
                        "count": 0,
                        "total_time_ms": 0,
                        "avg_time_ms": 0
                    }
                
                tool_stats[tool]["count"] += 1
                tool_stats[tool]["total_time_ms"] += exec_time
                
                # Update user stats
                if user not in user_stats:
                    user_stats[user] = {"count": 0}
                user_stats[user]["count"] += 1
                
                total_executions += 1
                total_time += exec_time
            
            # Calculate averages
            for tool, stats in tool_stats.items():
                if stats["count"] > 0:
                    stats["avg_time_ms"] = stats["total_time_ms"] / stats["count"]
            
            return {
                "period_days": days,
                "total_executions": total_executions,
                "total_time_ms": total_time,
                "avg_time_ms": total_time / total_executions if total_executions > 0 else 0,
                "unique_tools": len(tool_stats),
                "unique_users": len(user_stats),
                "tool_stats": tool_stats,
                "user_stats": user_stats,
                "filters": {
                    "tool_name": tool_name,
                    "user_email": user_email
                }
            }
            
        except Exception as e:
            logger.error(f"Error getting tool analytics: {e}")
            return {
                "error": str(e),
                "period_days": days
            }
    
    return get_tool_analytics