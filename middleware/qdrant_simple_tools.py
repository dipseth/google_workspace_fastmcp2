"""Simplified Qdrant tools to debug ListToolsRequest hang."""

import json
from typing import Optional
from datetime import datetime

def setup_simple_qdrant_tools(mcp, middleware):
    """Setup simplified Qdrant tools for debugging."""
    
    @mcp.tool
    async def search_tool_history_simple(query: str) -> str:
        """
        Simple search tool for debugging.
        
        Args:
            query: Search query
            
        Returns:
            JSON string with results
        """
        return json.dumps({"status": "search_disabled", "query": query})
    
    @mcp.tool
    async def get_tool_analytics_simple() -> str:
        """
        Simple analytics tool for debugging.
        
        Returns:
            JSON string with analytics
        """
        return json.dumps({"status": "analytics_disabled"})
    
    @mcp.tool
    async def get_response_details_simple(response_id: str) -> str:
        """
        Simple response details tool for debugging.
        
        Args:
            response_id: Response ID
            
        Returns:
            JSON string with details
        """
        return json.dumps({"status": "details_disabled", "id": response_id})