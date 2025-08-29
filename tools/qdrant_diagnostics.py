#!/usr/bin/env python3
"""
Qdrant Diagnostics Tool
Comprehensive diagnostic utility for debugging Qdrant MCP tools
"""

import json
import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def setup_qdrant_diagnostic_tools(mcp, middleware):
    """Setup enhanced diagnostic tools for Qdrant debugging."""
    
    @mcp.tool(
        name="qdrant_connection_status", 
        description="Check Qdrant connection status, collection info, and configuration details",
        tags={"qdrant", "diagnostics", "debug", "connection", "status"}
    )
    async def qdrant_connection_status() -> str:
        """
        Get comprehensive status of Qdrant connection and configuration.
        
        Returns:
            JSON string with connection details, collection info, and diagnostics
        """
        try:
            status = {
                "timestamp": datetime.now().isoformat(),
                "connection": {},
                "collection": {},
                "configuration": {},
                "middleware_state": {},
                "diagnostics": []
            }
            
            # Check middleware state
            status["middleware_state"] = {
                "enabled": middleware.config.enabled,
                "initialized": middleware._initialized,
                "client_available": middleware.client is not None,
                "embedder_available": middleware.embedder is not None,
                "auto_discovery": middleware.auto_discovery,
                "discovered_url": middleware.discovered_url
            }
            
            # Get configuration
            status["configuration"] = {
                "collection_name": middleware.config.collection_name,
                "host": middleware.config.host,
                "ports": middleware.config.ports,
                "vector_size": middleware.config.vector_size,
                "distance": middleware.config.distance,
                "embedding_model": middleware.config.embedding_model,
                "compression_threshold": middleware.config.compression_threshold,
                "default_search_limit": middleware.config.default_search_limit,
                "score_threshold": middleware.config.score_threshold
            }
            
            if middleware.client:
                try:
                    # Test connection
                    collections = await asyncio.to_thread(middleware.client.get_collections)
                    status["connection"] = {
                        "status": "connected",
                        "url": middleware.discovered_url or f"http://{middleware.config.host}:{middleware.config.ports[0]}",
                        "collections_count": len(collections.collections),
                        "available_collections": [c.name for c in collections.collections]
                    }
                    
                    # Check if our collection exists
                    collection_names = [c.name for c in collections.collections]
                    if middleware.config.collection_name in collection_names:
                        try:
                            # Get collection info
                            collection_info = await asyncio.to_thread(
                                middleware.client.get_collection,
                                collection_name=middleware.config.collection_name
                            )
                            
                            # Get collection stats
                            collection_stats = await asyncio.to_thread(
                                middleware.client.scroll,
                                collection_name=middleware.config.collection_name,
                                limit=1,
                                with_payload=False
                            )
                            
                            status["collection"] = {
                                "exists": True,
                                "name": middleware.config.collection_name,
                                "vector_size": collection_info.config.params.vectors.size,
                                "distance": collection_info.config.params.vectors.distance.name,
                                "points_count": collection_info.points_count,
                                "indexed": collection_info.status.name,
                                "optimizer_status": collection_info.optimizer_status.status.name if collection_info.optimizer_status else "unknown"
                            }
                            
                        except Exception as e:
                            status["collection"] = {
                                "exists": True,
                                "name": middleware.config.collection_name,
                                "error": f"Failed to get collection details: {str(e)}"
                            }
                            status["diagnostics"].append(f"⚠️ Collection exists but can't get details: {e}")
                    else:
                        status["collection"] = {
                            "exists": False,
                            "name": middleware.config.collection_name,
                            "message": "Collection will be created on first use"
                        }
                        status["diagnostics"].append("ℹ️ Target collection doesn't exist yet - will be auto-created")
                        
                except Exception as e:
                    status["connection"] = {
                        "status": "failed",
                        "error": str(e)
                    }
                    status["diagnostics"].append(f"❌ Connection test failed: {e}")
            else:
                status["connection"] = {
                    "status": "not_connected",
                    "message": "Client not initialized"
                }
                status["diagnostics"].append("❌ Qdrant client not initialized")
            
            # Check embedding model
            if middleware.embedder:
                status["embedding_model"] = {
                    "loaded": True,
                    "model": middleware.config.embedding_model,
                    "dimensions": middleware.embedding_dim
                }
            else:
                status["embedding_model"] = {
                    "loaded": False,
                    "model": middleware.config.embedding_model,
                    "message": "Model not loaded yet"
                }
                status["diagnostics"].append("⚠️ Embedding model not loaded")
            
            # Overall health check
            if status["middleware_state"]["enabled"] and status["connection"].get("status") == "connected" and status["embedding_model"].get("loaded"):
                status["overall_status"] = "✅ HEALTHY"
            elif not status["middleware_state"]["enabled"]:
                status["overall_status"] = "❌ DISABLED"
            else:
                status["overall_status"] = "⚠️ PARTIAL"
            
            return json.dumps(status, indent=2)
            
        except Exception as e:
            return json.dumps({
                "error": f"Diagnostic failed: {str(e)}",
                "timestamp": datetime.now().isoformat()
            }, indent=2)

    @mcp.tool(
        name="qdrant_collection_info",
        description="Get detailed information about the Qdrant collection including sample data",
        tags={"qdrant", "collection", "debug", "inspect"}
    )
    async def qdrant_collection_info() -> str:
        """
        Get detailed information about the current collection and sample data.
        
        Returns:
            JSON string with collection details and sample entries
        """
        try:
            if not middleware.client:
                return json.dumps({"error": "Qdrant client not available"})
            
            collection_name = middleware.config.collection_name
            
            # Get collection info
            collection_info = await asyncio.to_thread(
                middleware.client.get_collection,
                collection_name=collection_name
            )
            
            # Get sample points
            sample_points = await asyncio.to_thread(
                middleware.client.scroll,
                collection_name=collection_name,
                limit=5,
                with_payload=True,
                with_vector=False
            )
            
            # Get recent points (last 24 hours if possible)
            from datetime import datetime, timedelta
            yesterday = (datetime.now() - timedelta(days=1)).isoformat()
            
            result = {
                "collection_name": collection_name,
                "status": collection_info.status.name,
                "points_count": collection_info.points_count,
                "config": {
                    "vector_size": collection_info.config.params.vectors.size,
                    "distance": collection_info.config.params.vectors.distance.name
                },
                "sample_points": [],
                "recent_activity": {
                    "sample_count": len(sample_points[0]),
                    "points": []
                }
            }
            
            # Process sample points
            for point in sample_points[0][:3]:  # Just show first 3 for brevity
                payload = point.payload or {}
                result["sample_points"].append({
                    "id": str(point.id),
                    "tool_name": payload.get("tool_name", "unknown"),
                    "timestamp": payload.get("timestamp", "unknown"),
                    "user_email": payload.get("user_email", "unknown"),
                    "payload_type": payload.get("payload_type", "unknown"),
                    "compressed": payload.get("compressed", False)
                })
            
            # Add recent activity analysis
            tool_counts = {}
            user_counts = {}
            
            for point in sample_points[0]:
                payload = point.payload or {}
                tool_name = payload.get("tool_name", "unknown")
                user_email = payload.get("user_email", "unknown")
                
                tool_counts[tool_name] = tool_counts.get(tool_name, 0) + 1
                user_counts[user_email] = user_counts.get(user_email, 0) + 1
            
            result["activity_summary"] = {
                "top_tools": dict(sorted(tool_counts.items(), key=lambda x: x[1], reverse=True)[:5]),
                "active_users": dict(sorted(user_counts.items(), key=lambda x: x[1], reverse=True)[:5])
            }
            
            return json.dumps(result, indent=2)
            
        except Exception as e:
            return json.dumps({
                "error": f"Failed to get collection info: {str(e)}",
                "collection_name": middleware.config.collection_name
            })

    @mcp.tool(
        name="qdrant_test_search",
        description="Test search functionality with a sample query and return detailed results",
        tags={"qdrant", "search", "test", "debug"}
    )
    async def qdrant_test_search(
        test_query: str = "test search",
        limit: int = 5
    ) -> str:
        """
        Test the search functionality with detailed debugging information.
        
        Args:
            test_query: Query to test with
            limit: Maximum results to return
            
        Returns:
            JSON with search results and debugging info
        """
        try:
            if not middleware.client or not middleware.embedder:
                return json.dumps({
                    "error": "Middleware not fully initialized",
                    "client_available": middleware.client is not None,
                    "embedder_available": middleware.embedder is not None
                })
            
            # Test the search with full debugging
            start_time = datetime.now()
            
            # Parse query
            from middleware.qdrant_unified import _parse_search_query
            parsed_query = _parse_search_query(test_query)
            
            # Perform search
            results = await middleware.search(test_query, limit=limit)
            
            end_time = datetime.now()
            search_duration = (end_time - start_time).total_seconds()
            
            debug_info = {
                "test_query": test_query,
                "parsed_query": parsed_query,
                "search_duration_seconds": search_duration,
                "results_count": len(results),
                "collection_name": middleware.config.collection_name,
                "embedding_model": middleware.config.embedding_model,
                "results": results[:3] if results else [],  # Show first 3 results
                "summary": {
                    "successful": True,
                    "has_results": len(results) > 0,
                    "query_type": parsed_query.get("query_type", "unknown")
                }
            }
            
            if results:
                debug_info["result_analysis"] = {
                    "top_score": max(r.get("score", 0) for r in results),
                    "avg_score": sum(r.get("score", 0) for r in results) / len(results),
                    "tools_found": list(set(r.get("tool_name") for r in results if r.get("tool_name"))),
                    "users_found": list(set(r.get("user_email") for r in results if r.get("user_email")))
                }
            
            return json.dumps(debug_info, indent=2)
            
        except Exception as e:
            return json.dumps({
                "error": f"Search test failed: {str(e)}",
                "test_query": test_query,
                "successful": False
            })

    @mcp.tool(
        name="qdrant_reset_connection",
        description="Reset and reinitialize the Qdrant connection (useful for troubleshooting)",
        tags={"qdrant", "reset", "reconnect", "admin"}
    )
    async def qdrant_reset_connection() -> str:
        """
        Reset and reinitialize the Qdrant middleware connection.
        
        Returns:
            Status of the reset operation
        """
        try:
            # Reset connection state
            middleware.client = None
            middleware.embedder = None
            middleware.embedding_dim = None
            middleware.discovered_url = None
            middleware._initialized = False
            
            # Reinitialize
            if middleware.config.enabled:
                middleware._initialize_sync()
                await middleware.initialize()
            
            # Check new status
            status = {
                "reset_completed": True,
                "timestamp": datetime.now().isoformat(),
                "new_state": {
                    "client_available": middleware.client is not None,
                    "embedder_available": middleware.embedder is not None,
                    "discovered_url": middleware.discovered_url,
                    "initialized": middleware._initialized
                }
            }
            
            if middleware.client and middleware.embedder:
                status["result"] = "✅ Successfully reset and reconnected"
            else:
                status["result"] = "⚠️ Reset completed but connection issues remain"
            
            return json.dumps(status, indent=2)
            
        except Exception as e:
            return json.dumps({
                "error": f"Reset failed: {str(e)}",
                "timestamp": datetime.now().isoformat()
            })

    logger.info("✅ Qdrant diagnostic tools registered")