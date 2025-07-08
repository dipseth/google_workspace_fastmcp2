# Smart Card API for Google Chat

This document provides an overview of the Smart Card API for Google Chat, including the advanced features for card creation.

## Overview

The Smart Card API provides a simplified interface for creating and sending Google Chat cards using natural language content descriptions, templates, and advanced features. It leverages content mapping, parameter inference, and template management to create rich, interactive cards with minimal effort.

## Basic Features

The Smart Card API includes the following basic features:

1. **Enhanced Content-to-Structure Mapping**: Automatically maps natural language content descriptions to structured card components.
2. **Smart Parameter Inference**: Intelligently infers parameter values from context and content.
3. **Template-Driven Generation**: Creates cards from predefined templates with content substitution.
4. **Natural Language Widget Specification**: Parses natural language descriptions of widgets into properly formatted widget objects.
5. **Content Validation and Auto-Correction**: Validates card structures and automatically fixes issues.
6. **Simplified API for LLM Interface Optimization**: Provides a streamlined interface for LLMs to interact with the Google Chat card creation system.

## Advanced Features

The Smart Card API now includes the following advanced features:

### 1. AI-Powered Layout Optimization

The layout optimization feature analyzes card engagement metrics and suggests layout improvements based on user interaction patterns. It provides insights into how users are engaging with cards and offers actionable suggestions to improve engagement.

Key capabilities:
- **Engagement Analysis**: Analyzes metrics like impressions, clicks, and time spent.
- **Layout Improvement Suggestions**: Suggests changes to improve engagement based on patterns.
- **A/B Testing**: Creates and analyzes A/B tests for different card designs.

Example usage:
```python
# Optimize a card layout
optimization_results = await optimize_card_layout("card_123")
print(f"Engagement metrics: {optimization_results['metrics']}")
print(f"Suggested improvements: {optimization_results['improvements']}")
```

### 2. Multi-Modal Content Support

The multi-modal content support feature enables the creation of rich, media-enhanced cards with optimized images, data visualizations, and video content.

Key capabilities:
- **Automatic Image Optimization**: Resizes and optimizes images for the best viewing experience.
- **Chart Generation**: Creates visual charts from data.
- **Video Thumbnail Extraction**: Extracts thumbnails from video URLs.
- **Data Table Conversion**: Converts data to formatted table widgets.
- **Image Grid Creation**: Creates grid layouts from multiple images.

Example usage:
```python
# Create a multi-modal card
await create_multi_modal_card(
    user_google_email="user@example.com",
    space_id="spaces/123",
    content="Title: Quarterly Results | Text: Here are the Q2 results",
    data={
        "labels": ["Q1", "Q2", "Q3", "Q4"],
        "values": [10, 20, 15, 25]
    },
    images=["https://example.com/image1.jpg", "https://example.com/image2.jpg"],
    video_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ"
)
```

## API Reference

### Basic Functions

#### `send_smart_card`

Create and send a Google Chat card using natural language content description.

```python
async def send_smart_card(
    user_google_email: str,
    space_id: str,
    content: str,
    style: str = "default",
    auto_format: bool = True,
    thread_key: Optional[str] = None,
    webhook_url: Optional[str] = None
) -> str:
    """
    Create and send a Google Chat card using natural language content description.
    
    Args:
        user_google_email: User's Google email
        space_id: Chat space ID
        content: Natural language content description
        style: Card style (default, announcement, form, report, interactive)
        auto_format: Automatically format and fix issues
        thread_key: Optional thread key for threaded replies
        webhook_url: Optional webhook URL for card delivery
        
    Returns:
        Confirmation message with sent message details
    """
```

#### `create_card_from_template`

Create and send a card using a predefined template with content substitution.

```python
async def create_card_from_template(
    template_name: str,
    content: Dict[str, str],
    user_google_email: str,
    space_id: str,
    thread_key: Optional[str] = None,
    webhook_url: Optional[str] = None
) -> str:
    """
    Create and send a card using a predefined template with content substitution.
    
    Args:
        template_name: Template name (e.g., status_report, announcement, form_request)
        content: Content mapping for template placeholders
        user_google_email: User's Google email
        space_id: Chat space ID
        thread_key: Optional thread key for threaded replies
        webhook_url: Optional webhook URL for card delivery
        
    Returns:
        Confirmation message with sent message details
    """
```

#### `create_card_from_description`

Create a card structure from a natural language description.

```python
async def create_card_from_description(
    description: str,
    auto_format: bool = True
) -> Dict[str, Any]:
    """
    Create a card structure from a natural language description.
    
    Args:
        description: Natural language description of the card
        auto_format: Whether to automatically format and fix issues
        
    Returns:
        Dictionary representing the card structure
    """
```

### Advanced Functions

#### `optimize_card_layout`

Analyze and optimize a card layout based on engagement metrics.

```python
async def optimize_card_layout(card_id: str) -> Dict:
    """
    Analyze and optimize a card layout based on engagement metrics.
    
    Args:
        card_id: ID of the card to optimize
        
    Returns:
        Dictionary with metrics and suggested improvements
    """
```

#### `create_multi_modal_card`

Create and send a card with multi-modal content.

```python
async def create_multi_modal_card(
    user_google_email: str,
    space_id: str,
    content: str,
    data: Dict = None,
    images: List[str] = None,
    video_url: str = None,
    thread_key: Optional[str] = None,
    webhook_url: Optional[str] = None
) -> str:
    """
    Create and send a card with multi-modal content.
    
    Args:
        user_google_email: User's Google email
        space_id: Chat space ID
        content: Natural language content description
        data: Optional data for chart generation
        images: Optional list of image URLs
        video_url: Optional video URL
        thread_key: Optional thread key for threaded replies
        webhook_url: Optional webhook URL for card delivery
        
    Returns:
        Confirmation message with sent message details
    """
```

## MCP Tools

The Smart Card API is exposed as MCP tools for easy integration with LLMs:

1. `send_smart_card`: Create and send a Google Chat card using natural language content description.
2. `create_card_from_template`: Create and send a card using a predefined template.
3. `preview_card_from_description`: Preview a card structure from natural language description without sending.
4. `optimize_card_layout`: Analyze and optimize a card layout based on engagement metrics.
5. `create_multi_modal_card`: Create and send a card with multi-modal content.

## Implementation Details

The Smart Card API is implemented using the following components:

- **ContentMappingEngine**: Maps natural language content to card structures.
- **ParameterInferenceEngine**: Infers parameter values from context and content.
- **TemplateManager**: Manages card templates and applies content to templates.
- **WidgetSpecificationParser**: Parses natural language widget descriptions.
- **CardValidator**: Validates and auto-corrects card structures.
- **LayoutOptimizer**: Analyzes engagement metrics and suggests layout improvements.
- **MultiModalSupport**: Handles multi-modal content like images, charts, and videos.

These components work together to provide a comprehensive solution for creating and sending Google Chat cards with rich, interactive content.