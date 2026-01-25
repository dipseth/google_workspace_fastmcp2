"""
Query Parsing Module for Qdrant Middleware

This module handles all query parsing and formatting functionality for the
Qdrant vector database middleware, including:
- Search query parsing with filter extraction
- Unified query parsing with intelligent routing
- Search result formatting
- Service extraction from tool names

═══════════════════════════════════════════════════════════════════════════════
                      🔍 THE INTERPRETER'S DANCE 🔍
═══════════════════════════════════════════════════════════════════════════════

    "id:12345"—the user spoke plain,
    a direct lookup, no semantic rain.
    "user:alice budget reports"—
    ah, filters mixed with search of sorts.

    The parser reads the cryptic tongue,
    field:value patterns, colon-strung.
    Regex sweeps the query whole,
    extracting structure from the soul.

    user: becomes user_email,
    service: transforms to tool_name's trail.
    Field mapping smooths the rough intent,
    aligning what the searcher meant.

    What remains when filters fall?
    The semantic query, heart of all.
    Vector search takes this last phrase,
    navigating meaning's maze.

    Three paths diverge: id_lookup straight,
    filtered_search with hybrid weight,
    or pure semantic, unrestrained—
    the parser routes what's ascertained.

                                        — Field Notes, Jan 2026

═══════════════════════════════════════════════════════════════════════════════
"""

import re
from typing import Any, Dict, List

from config.enhanced_logging import setup_logger

logger = setup_logger()


def parse_search_query(query: str) -> Dict[str, Any]:
    """
    Parse search query to extract filters and semantic search terms.

    Supports formats:
    - "id:12345" -> Direct ID lookup
    - "field:value semantic query" -> Filtered semantic search
    - "field1:value1 field2:value2 semantic query" -> Multiple filters + semantic search
    - "plain text" -> Pure semantic search

    Field mapping for common search patterns:
    - "user:email" -> "user_email:email"
    - "service:name" -> "tool_name:name"
    - "tool:name" -> "tool_name:name"

    Args:
        query: Search query string

    Returns:
        Dict with parsed components: {
            "query_type": "id_lookup" | "filtered_search" | "semantic_search",
            "filters": {"field": "value", ...},
            "semantic_query": "remaining text for semantic search",
            "id": "target_id" (only for id_lookup)
        }
    """
    # Initialize result
    result = {
        "query_type": "semantic_search",
        "filters": {},
        "semantic_query": "",
        "id": None,
    }

    # Check for direct ID lookup
    if query.startswith("id:"):
        result["query_type"] = "id_lookup"
        result["id"] = query[3:].strip()
        return result

    # Field mapping for common search patterns to indexed fields
    field_mapping = {
        "user": "user_email",  # user:email -> user_email:email
        "service": "tool_name",  # service:gmail -> tool_name:gmail
        "tool": "tool_name",  # tool:search -> tool_name:search
        "email": "user_email",  # email:user@domain -> user_email:user@domain
        "session": "session_id",  # session:123 -> session_id:123
        "type": "payload_type",  # type:response -> payload_type:response
    }

    # Parse field:value patterns
    filter_pattern = r"(\w+):([^\s]+)"
    filters = {}
    remaining_text = query

    # Extract all field:value pairs
    for match in re.finditer(filter_pattern, query):
        field = match.group(1)
        value = match.group(2)

        # Map common field names to indexed field names
        mapped_field = field_mapping.get(field, field)
        filters[mapped_field] = value

        # Remove this filter from the remaining text
        remaining_text = remaining_text.replace(match.group(0), "", 1)

    # Clean up remaining text for semantic search
    semantic_query = remaining_text.strip()

    # Update result based on what we found
    if filters:
        result["query_type"] = "filtered_search"
        result["filters"] = filters
        result["semantic_query"] = semantic_query
    else:
        result["query_type"] = "semantic_search"
        result["semantic_query"] = query

    return result


def parse_unified_query(query: str) -> Dict[str, Any]:
    """
    Enhanced query parser for unified search tool supporting intelligent query routing.

    Capability Detection Patterns:
    1. Overview/Analytics: "overview", "analytics", "dashboard", "summary", "usage", "stats"
    2. Service History: "service:gmail", "gmail history", "tool:search_drive_files", "last week"
    3. General Search: Natural language queries, semantic search

    Args:
        query: User query string

    Returns:
        Dict with parsed components: {
            "capability": "overview" | "service_history" | "general_search",
            "confidence": float (0.0-1.0),
            "filters": {"field": "value", ...},
            "semantic_query": "remaining text for semantic search",
            "service_name": "service" (for service_history),
            "time_range": "timespec" (for service_history)
        }
    """
    # Initialize result
    result = {
        "capability": "general_search",
        "confidence": 0.5,
        "filters": {},
        "semantic_query": query.lower().strip(),
        "service_name": None,
        "time_range": None,
    }

    query_lower = query.lower().strip()

    # 1. Overview/Analytics Detection
    overview_keywords = [
        "overview",
        "analytics",
        "dashboard",
        "summary",
        "usage",
        "stats",
        "statistics",
        "metrics",
        "performance",
        "report",
        "total",
        "count",
        "all tools",
        "tool usage",
    ]

    overview_score = sum(1 for keyword in overview_keywords if keyword in query_lower)
    if overview_score > 0 or query_lower in [
        "overview",
        "analytics",
        "dashboard",
        "stats",
    ]:
        result["capability"] = "overview"
        result["confidence"] = min(0.9, 0.6 + (overview_score * 0.1))
        return result

    # 2. Service History Detection
    service_patterns = [
        r"service:(\w+)",  # service:gmail
        r"tool:(\w+)",  # tool:search_gmail
        r"(\w+)\s+(?:history|recent|last|past)",  # "gmail history", "drive recent"
        r"(?:history|recent|last|past)\s+(\w+)",  # "recent gmail", "last drive"
    ]

    # Check for time-related keywords
    time_keywords = [
        "today",
        "yesterday",
        "week",
        "month",
        "hour",
        "day",
        "recent",
        "last",
        "past",
    ]
    has_time_context = any(keyword in query_lower for keyword in time_keywords)

    # Import service metadata for service detection
    try:
        from auth.scope_registry import ScopeRegistry

        known_services = set(ScopeRegistry.SERVICE_METADATA.keys())
    except ImportError:
        known_services = {
            "gmail",
            "drive",
            "calendar",
            "docs",
            "sheets",
            "photos",
            "chat",
            "forms",
            "slides",
        }

    service_matches = []
    for pattern in service_patterns:
        matches = re.findall(pattern, query_lower)
        service_matches.extend(matches)

    # Also check for direct service mentions
    mentioned_services = [svc for svc in known_services if svc in query_lower]
    service_matches.extend(mentioned_services)

    if service_matches or has_time_context:
        result["capability"] = "service_history"
        confidence_base = 0.7 if service_matches else 0.6
        time_bonus = 0.1 if has_time_context else 0.0
        result["confidence"] = min(0.9, confidence_base + time_bonus)

        if service_matches:
            result["service_name"] = service_matches[0]  # Take first match

        # Extract time range if present
        time_patterns = [
            r"last\s+(\d+)\s+(hours?|days?|weeks?|months?)",
            r"past\s+(\d+)\s+(hours?|days?|weeks?|months?)",
            r"(today|yesterday|this\s+week|last\s+week|this\s+month|last\s+month)",
        ]

        for pattern in time_patterns:
            match = re.search(pattern, query_lower)
            if match:
                result["time_range"] = match.group(0)
                break

        return result

    # 3. General Search (Default)
    # Remove any detected filters from semantic query
    filter_pattern = r"(\w+):([^\s]+)"
    filters = {}
    remaining_text = query

    for match in re.finditer(filter_pattern, query):
        field = match.group(1)
        value = match.group(2)
        filters[field] = value
        remaining_text = remaining_text.replace(match.group(0), "", 1)

    result["filters"] = filters
    result["semantic_query"] = (
        remaining_text.strip() if remaining_text.strip() else query
    )

    return result


async def format_search_results(
    middleware, results: List[Dict], parsed_query: Dict
) -> Dict:
    """
    Format search results in OpenAI MCP standard format with service metadata.

    Args:
        middleware: Qdrant middleware instance
        results: Raw search results from Qdrant
        parsed_query: Parsed query information

    Returns:
        Formatted results dict with 'results' array containing id, title, url
    """
    try:
        # Import service metadata
        from auth.scope_registry import ScopeRegistry

        service_metadata = ScopeRegistry.SERVICE_METADATA
    except ImportError:
        service_metadata = {}

    formatted_results = []

    for result in results:
        # Extract basic information
        result_id = result.get("id", "unknown")
        tool_name = result.get("tool_name", "unknown_tool")
        timestamp = result.get("timestamp", "unknown")
        user_email = result.get("user_email", "unknown")
        score = result.get("score", 0.0)

        # Determine service from tool name
        service_name = extract_service_from_tool(tool_name)
        service_meta = service_metadata.get(service_name, {})
        service_icon = getattr(service_meta, "icon", "🔧") if service_meta else "🔧"

        # Create title with service context
        if parsed_query.get("capability") == "overview":
            title = f"{service_icon} {tool_name} - {user_email} ({timestamp})"
        elif parsed_query.get("capability") == "service_history":
            title = f"{service_icon} {service_name.title()} Tool Usage - {tool_name}"
        else:
            # General search - include relevance score
            title = f"{service_icon} {tool_name} (Score: {score:.2f}) - {timestamp}"

        # Create URL for citation (using point ID for retrieval)
        url = f"qdrant://point/{result_id}"

        formatted_results.append({"id": result_id, "title": title, "url": url})

    return {"results": formatted_results}


def extract_service_from_tool(tool_name: str) -> str:
    """Extract service name from tool name."""
    service_prefixes = [
        "search_",
        "get_",
        "list_",
        "create_",
        "update_",
        "delete_",
        "send_",
        "upload_",
        "download_",
        "manage_",
    ]

    tool_lower = tool_name.lower()

    # Remove common prefixes
    for prefix in service_prefixes:
        if tool_lower.startswith(prefix):
            tool_lower = tool_lower[len(prefix) :]
            break

    # Check for service names in remaining text
    # Maps keywords to ScopeRegistry service names
    service_keywords = {
        "gmail": "gmail",
        "mail": "gmail",
        "email": "gmail",
        "drive": "drive",
        "file": "drive",
        "folder": "drive",
        "calendar": "calendar",
        "event": "calendar",
        "schedule": "calendar",
        "docs": "docs",
        "document": "docs",
        "doc": "docs",
        "sheets": "sheets",
        "spreadsheet": "sheets",
        "sheet": "sheets",
        "slides": "slides",
        "presentation": "slides",
        "slide": "slides",
        "photos": "photos",
        "photo": "photos",
        "image": "photos",
        "album": "photos",
        "chat": "chat",
        "message": "chat",
        "space": "chat",
        "card": "chat",
        "forms": "forms",
        "form": "forms",
        "survey": "forms",
        "question": "forms",
        "people": "people",
        "contact": "people",
        "label": "people",
        "tasks": "tasks",
        "task": "tasks",
    }

    for keyword, service in service_keywords.items():
        if keyword in tool_lower:
            return service

    return "unknown"


# Legacy aliases for backward compatibility
_parse_search_query = parse_search_query
_parse_unified_query = parse_unified_query
_format_search_results = format_search_results
_extract_service_from_tool = extract_service_from_tool
