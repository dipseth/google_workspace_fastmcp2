# Unified Card Tool with ModuleWrapper Integration

This module provides a unified MCP tool for Google Chat cards that leverages the ModuleWrapper adapter to handle inputs for any type of card dynamically. It replaces the separate card tools with a single, more flexible approach.

## Overview

The Unified Card Tool allows you to:

1. **Send any type of card** using natural language descriptions
2. **Discover available card components** through semantic search
3. **Get detailed information** about card components
4. **Use a single tool** instead of multiple specific card tools

## Features

- **Natural language interface** - Describe the card you want in plain English
- **Dynamic component discovery** - Finds the right card component based on your description
- **Semantic search** - Uses vector embeddings for intelligent matching
- **Automatic parameter filtering** - Only passes relevant parameters to components
- **Graceful fallbacks** - Falls back to simpler cards if needed
- **Webhook support** - Supports webhook delivery for cards

## Tools

### send_dynamic_card

Send any type of card to Google Chat using natural language description.

```python
await client.use_tool(
    "send_dynamic_card",
    {
        "user_google_email": "user@gmail.com",
        "space_id": "spaces/AAAAAAAAAAA",
        "card_description": "simple card with title and text",
        "card_params": {
            "title": "Hello World",
            "text": "This is a simple card created with the unified card tool",
            "subtitle": "Optional subtitle"
        },
        "thread_key": None,  # Optional
        "webhook_url": None  # Optional
    }
)
```

#### Parameters

- **user_google_email** (str): The user's Google email address
- **space_id** (str): The space ID to send the message to
- **card_description** (str): Natural language description of the card you want
- **card_params** (dict, optional): Parameters for the card (title, text, etc.)
- **thread_key** (str, optional): Thread key for threaded replies
- **webhook_url** (str, optional): Webhook URL for card delivery

### list_available_card_components

List available card components that can be used with send_dynamic_card.

```python
await client.use_tool(
    "list_available_card_components",
    {
        "query": "interactive card with buttons",  # Optional
        "limit": 10  # Optional
    }
)
```

#### Parameters

- **query** (str, optional): Search query to filter components
