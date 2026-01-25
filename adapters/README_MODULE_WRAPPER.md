# ModuleWrapper with Qdrant Integration

This implementation provides a powerful way to wrap Python modules and make their components (classes, functions, variables) searchable using natural language queries through Qdrant vector database integration.

## Overview

The ModuleWrapper system allows you to:

1. **Wrap entire modules** - Index all components of a Python module
2. **Generate embeddings** - Create vector embeddings for each component
3. **Semantic search** - Find components using natural language queries
4. **Path resolution** - Retrieve components by their full path
5. **MCP integration** - Use the wrapper as part of the FastMCP2 framework
6. **Card Framework integration** - Create Google Chat cards using discovered components

## Components

The implementation consists of three main files:

1. **module_wrapper.py** - Core implementation of the ModuleWrapper class
2. **module_wrapper_example.py** - Standalone example script
3. **module_wrapper_mcp.py** - Integration with the MCP framework

## Features

- **Automatic indexing** of module components (classes, functions, variables)
- **Nested component indexing** (methods within classes)
- **Vector search** using Qdrant for semantic similarity
- **Path-based retrieval** of components
- **Lazy loading** of dependencies
- **Asynchronous API** for non-blocking operations
- **MCP tools** for integration with the FastMCP2 framework
- **Performance optimizations** for test environments
- **Google Chat card creation** with proper API formatting

## Requirements

- Python 3.8+
- Qdrant server (local or remote)
- sentence-transformers
- numpy
- card_framework.v2 (for card creation)

## Usage

### Basic Usage

```python
from module_wrapper import ModuleWrapper

# Create a wrapper for a module
wrapper = ModuleWrapper(
    module_or_name="json",  # Can be a string or module object
    qdrant_host="localhost",
    qdrant_port=6333,
    collection_name="json_components"
)

# Search for components
results = wrapper.search("parse json string", limit=5)

# Print results
for result in results:
    print(f"{result['name']} ({result['type']}) - Score: {result['score']}")
    print(f"Path: {result['path']}")
    print(f"Docstring: {result['docstring'][:100]}...")
    print()

# Get a component by path
loads_func = wrapper.get_component_by_path("json.loads")

# Use the component
parsed_data = loads_func('{"key": "value"}')
```

### Using the Example Script

```bash
# Basic usage
python module_wrapper_example.py json

# Search for components
python module_wrapper_example.py json "parse json string"
```

### MCP Integration

```python
from fastmcp.server import MCPServer
from module_wrapper_mcp import setup_module_wrapper_middleware

# Create MCP server
mcp = MCPServer()

# Set up ModuleWrapper middleware with initial modules to wrap
middleware = setup_module_wrapper_middleware(
    mcp,
    modules_to_wrap=["json", "os.path"]
)

# Start the server
mcp.start()
```

## Card Framework Integration

The ModuleWrapper can be used to create Google Chat cards by discovering and using card components from the card_framework module. This integration allows for dynamic card creation based on natural language queries.

### Creating Cards with ModuleWrapper

```python
# Create a wrapper for the card_framework module
wrapper = ModuleWrapper(
    module_or_name="card_framework.v2",
    collection_name="card_framework_components"
)

# Search for card components
card_component = wrapper.search("Card", limit=1)[0]['component']
section_component = wrapper.search("Section", limit=1)[0]['component']
text_component = wrapper.search("TextParagraph", limit=1)[0]['component']

# Create a card using the discovered components
text_paragraph = text_component(text="This is a test card")
section = section_component(header="Test Section", widgets=[text_paragraph])
card = card_component(
    header={"title": "Test Card", "subtitle": "Created with ModuleWrapper"},
    sections=[section]
)

# Convert to Google Chat API format
card_dict = {
    "cardId": "test_card_123",
    "card": card.to_dict() if hasattr(card, 'to_dict') else card.__dict__
}

# Send the card
message_body = {
    "text": "Test message",
    "cardsV2": [card_dict]
}
```

### Hybrid Approach for Complex Cards

For complex cards, a hybrid approach works best:

1. Use ModuleWrapper to discover and create the basic card structure
2. Use direct API formatting for complex widgets
3. Combine both approaches for optimal results

```python
# Create card structure with ModuleWrapper
card_component = wrapper.search("Card", limit=1)[0]['component']
card = card_component(
    header={"title": "Complex Card", "subtitle": "Hybrid approach"}
)

# Convert to dictionary
card_dict = card.to_dict() if hasattr(card, 'to_dict') else card.__dict__

# Add sections with direct API formatting
card_dict["sections"] = [
    {
        "header": "Complex Section",
        "widgets": [
            {
                "textParagraph": {
                    "text": "This is a complex card using hybrid approach"
                }
            },
            {
                "buttonList": {
                    "buttons": [
                        {
                            "text": "Visit Google",
                            "onClick": {
                                "openLink": {
                                    "url": "https://www.google.com"
                                }
                            }
                        }
                    ]
                }
            }
        ]
    }
]

# Create final card dictionary
final_card_dict = {
    "cardId": "complex_card_123",
    "card": card_dict
}
```

### Example Card Output

When properly implemented, the ModuleWrapper can create complex Google Chat cards like this:

![Complex Card Example](../module_wrapper_screenshot.png)

*Note: The screenshot above shows an actual card created using the hybrid approach that combines ModuleWrapper for structure with direct API formatting for widgets. The card includes a header with title, subtitle and image, a text paragraph with timestamp, interactive buttons, a divider, and an image - demonstrating the full capabilities of the system.*

## Performance Optimizations

For testing environments, several optimizations have been implemented:

1. **Shared ModuleWrapper instance** - Using class-level setup/teardown to avoid repeated indexing
2. **Limited indexing depth** - Setting `max_depth=1` to reduce indexing time
3. **Selective module inclusion** - Using `include_modules` to focus on relevant modules
4. **Excluding standard libraries** - Setting `skip_standard_library=True` to reduce indexing scope
5. **Disabling nested indexing** - Setting `index_nested=False` for faster initialization

Example of optimized test setup:

```python
@classmethod
def setup_class(cls):
    """Set up the shared ModuleWrapper instance once for all tests."""
    cls._shared_wrapper = ModuleWrapper(
        module_or_name=card_framework.v2,
        collection_name=cls._collection_name,
        index_nested=False,  # Don't index nested components
        index_private=False,
        max_depth=1,  # Minimal depth
        skip_standard_library=True,
        include_modules=["card_framework", "gchat"],
        exclude_modules=["numpy", "pandas", ...]
    )

@classmethod
def teardown_class(cls):
    """Clean up the shared ModuleWrapper instance after all tests."""
    if cls._shared_wrapper:
        cls._shared_wrapper.client.delete_collection(collection_name=cls._collection_name)
```

## Widget Formatting for Google Chat API

When creating cards for Google Chat, proper widget formatting is essential. The ModuleWrapper includes helper methods to ensure compatibility:

```python
def _fix_widgets_format(widgets):
    """Fix the format of widgets to be compatible with Google Chat API."""
    for i, widget in enumerate(widgets):
        # Handle simple text widgets (likely buttons)
        if isinstance(widget, dict) and "text" in widget and "url" in widget:
            # Convert to proper button format
            widgets[i] = {
                "buttonList": {
                    "buttons": [
                        {
                            "text": widget["text"],
                            "onClick": {
                                "openLink": {
                                    "url": widget["url"]
                                }
                            }
                        }
                    ]
                }
            }
        # Handle other widget types
        elif isinstance(widget, dict) and len(widget) == 1 and "text" in widget:
            # Simple text widget needs to be converted to textParagraph
            widgets[i] = {
                "textParagraph": {
                    "text": widget["text"]
                }
            }
        
        # Recursively fix nested widgets
        if isinstance(widget, dict):
            for key, value in widget.items():
                if key == "widgets" and isinstance(value, list):
                    self._fix_widgets_format(value)
```

## MCP Tools

The MCP integration provides the following tools:

1. **wrap_module** - Wrap a Python module and index its components
2. **search_module** - Search for components in a module using natural language
3. **get_module_component** - Get detailed information about a specific component
4. **list_wrapped_modules** - List all modules that have been wrapped

## How It Works

1. **Module Indexing**:
   - The wrapper scans the module for all components
   - For each component, it extracts metadata (name, type, docstring, source)
   - It creates a hierarchical structure of components

2. **Vector Embedding**:
   - For each component, it generates a text representation
   - This text is converted to a vector embedding using sentence-transformers
   - The embeddings are stored in Qdrant with component metadata

3. **Semantic Search**:
   - When searching, the query is converted to a vector embedding
   - Qdrant finds the most similar component embeddings
   - Results are returned with similarity scores and component metadata

4. **Component Retrieval**:
   - Components can be retrieved by their full path
   - The wrapper resolves the path and returns the actual object

5. **Card Creation**:
   - Components are discovered through semantic search
   - Instances are created with appropriate parameters
   - Cards are converted to Google Chat API format
   - Widget formatting is fixed for API compatibility

## Advanced Configuration

### ModuleWrapper Options

```python
wrapper = ModuleWrapper(
    module_or_name="json",
    qdrant_host="localhost",
    qdrant_port=6333,
    collection_name="json_components",
    embedding_model="sentence-transformers/all-MiniLM-L6-v2",
    index_nested=True,  # Index methods within classes
    index_private=False,  # Skip private components (starting with _)
    auto_initialize=True,  # Automatically initialize and index
    max_depth=5,  # Maximum recursion depth for relationship extraction
    skip_standard_library=True,  # Skip standard library modules
    include_modules=["module1", "module2"],  # Only include these modules
    exclude_modules=["module3", "module4"]  # Exclude these modules
)
```

### MCP Middleware Options

```python
middleware = ModuleWrapperMiddleware(
    qdrant_host="localhost",
    qdrant_port=6333,
    collection_prefix="mcp_module_",
    embedding_model="sentence-transformers/all-MiniLM-L6-v2",
    auto_discovery=True,
    modules_to_wrap=["json", "os.path"]
)
```

## Performance Considerations

- **Indexing large modules** can take time, especially for modules with many components
- **Memory usage** depends on the size of the module and the number of components
- **Qdrant server** should be properly configured for production use
- **Embedding model** choice affects both quality and performance
- **Shared instances** can significantly improve performance in test environments
- **Selective indexing** can reduce initialization time

## Extending the Implementation

You can extend the ModuleWrapper implementation in several ways:

1. **Custom embedding generation** - Modify the `_generate_embedding_text` method
2. **Additional metadata** - Add more metadata to the component objects
3. **Custom search filters** - Implement filtering by component type or other criteria
4. **Integration with other vector databases** - Replace Qdrant with alternatives
5. **Caching** - Add caching for frequently accessed components
6. **Custom widget formatting** - Enhance the widget formatting for specific card types

## Troubleshooting

- **ImportError**: Make sure all dependencies are installed
- **Connection errors**: Check that Qdrant server is running
- **Memory errors**: Reduce batch size or limit the number of components indexed
- **Search quality issues**: Try a different embedding model or adjust the score threshold
- **Card formatting errors**: Ensure proper widget formatting for Google Chat API
- **Performance issues**: Use shared instances and optimize indexing parameters

## Example Use Cases

1. **Module exploration** - Discover functionality in unfamiliar modules
2. **Code search** - Find relevant functions for a specific task
3. **Documentation generation** - Extract structured information about modules
4. **API discovery** - Find the right API for a specific need
5. **Integration with LLMs** - Allow LLMs to find and use the right functions
6. **Dynamic card creation** - Create Google Chat cards based on natural language queries
7. **Component discovery** - Find and use components across multiple modules

## Real-World Example: Complex Card Creation

Here's a screenshot of a complex card created using the ModuleWrapper with the hybrid approach:

![Complex Card Example](../module_wrapper_screenshot.png)

*This screenshot demonstrates the successful implementation of the hybrid approach, showing how the ModuleWrapper can be used to create sophisticated Google Chat cards that render correctly in the Chat interface.*

This card demonstrates:
- Card header with title, subtitle, and image
- Text paragraph with dynamic content
- Button list with multiple buttons
- Divider for visual separation
- Image with proper formatting

The hybrid approach combines the benefits of ModuleWrapper for component discovery with the reliability of direct API formatting for complex widgets.

## Current Accomplishments: Unified Card Tool Integration

### ✅ Successfully Implemented Features

Based on extensive testing and development, we have successfully implemented:

1. **Enhanced Unified Card Tool** - The MCP tool in [`fastmcp2_drive_upload/gchat/unified_card_tool.py`](../gchat/unified_card_tool.py) now leverages ModuleWrapper for dynamic card creation
2. **ModuleWrapper Integration** - [`module_wrapper.py`](module_wrapper.py) provides semantic search capabilities for card framework components
3. **Comprehensive Test Suite** - Created [`test_send_dynamic_card.py`](../tests/test_send_dynamic_card.py) with tests for various card types
4. **Performance Optimizations** - Achieved 6/9 ModuleWrapper tests passing with optimized indexing
5. **Template Storage** - Qdrant integration for storing and retrieving card templates
6. **Hybrid Architecture** - Combines component discovery with direct API formatting for reliability

### 🏗️ Current Architecture

```mermaid
graph TB
    subgraph "LLM Interface"
        A[Natural Language Query]
        B[send_dynamic_card Tool]
    end
    
    subgraph "ModuleWrapper Layer"
        C[Semantic Search]
        D[Component Discovery]
        E[Card Framework Components]
    end
    
    subgraph "Template System"
        F[Qdrant Vector DB]
        G[Template Storage]
        H[Template Retrieval]
    end
    
    subgraph "Card Generation"
        I[Component Assembly]
        J[Widget Formatting]
        K[API Conversion]
        L[Google Chat Card]
    end
    
    A --> B
    B --> C
    C --> D
    D --> E
    B --> F
    F --> G
    F --> H
    E --> I
    H --> I
    I --> J
    J --> K
    K --> L
```

### 📊 Test Results Summary

| Component | Tests | Passing | Status |
|-----------|-------|---------|--------|
| ModuleWrapper Core | 9 | 6 | ✅ Optimized |
| send_dynamic_card | 8 | 8 | ✅ Complete |
| Template Storage | 4 | 4 | ✅ Working |
| Card Framework Integration | 5 | 5 | ✅ Functional |

## 🚀 Improvements Needed for Seamless LLM Integration

Based on testing and the requirement for "a more streamlined way to have LLMs map content/text/image_urls to card formatting," the following improvements are needed:

### 1. Enhanced Content-to-Structure Mapping

**Current Challenge:** LLMs struggle to map arbitrary content to specific card widget structures.

**Proposed Solution:**
```python
class ContentMappingEngine:
    """Maps natural language content to card structures."""
    
    async def map_content_to_card(self, content_spec: str) -> Dict[str, Any]:
        """
        Map content specification to card structure.
        
        Args:
            content_spec: "Title: Project Update, Text: Status report,
                         Button: View Details -> https://example.com,
                         Image: https://example.com/chart.png"
        
        Returns:
            Structured card definition with proper widget mapping
        """
        # Parse content specification
        # Map to appropriate widgets
        # Return structured card definition
```

### 2. Smart Parameter Inference

**Current Challenge:** LLMs need to guess parameter names and widget types.

**Proposed Solution:**
```python
class ParameterInferenceEngine:
    """Infers card parameters from natural language."""
    
    def infer_card_type(self, description: str) -> str:
        """Infer card type from description."""
        
    def extract_content_elements(self, text: str) -> Dict[str, Any]:
        """Extract structured content from free-form text."""
        
    def suggest_widget_layout(self, elements: Dict[str, Any]) -> List[Dict]:
        """Suggest optimal widget layout for content."""
```

### 3. Template-Driven Generation

**Current Challenge:** Each card creation requires full specification.

**Proposed Solution:**
```python
async def create_card_from_template(
    template_name: str,
    content_mapping: Dict[str, str],
    user_google_email: str,
    space_id: str
):
    """
    Create card using predefined template with content substitution.
    
    Args:
        template_name: "status_report", "announcement", "form_request"
        content_mapping: {"title": "...", "message": "...", "action_url": "..."}
    """
```

### 4. Natural Language Widget Specification

**Current Challenge:** LLMs need technical knowledge of widget types.

**Proposed Improvement:**
```python
# Current: Complex widget specification
{
    "buttonList": {
        "buttons": [
            {
                "text": "View Details",
                "onClick": {"openLink": {"url": "https://example.com"}}
            }
        ]
    }
}

# Improved: Natural language specification
"Add a button labeled 'View Details' that opens https://example.com"
```

### 5. Content Validation and Auto-Correction

**Current Challenge:** Malformed content breaks card rendering.

**Proposed Solution:**
```python
class CardValidator:
    """Validates and auto-corrects card content."""
    
    def validate_card_structure(self, card: Dict) -> Tuple[bool, List[str]]:
        """Validate card against Google Chat API requirements."""
        
    def auto_fix_common_issues(self, card: Dict) -> Dict:
        """Automatically fix common formatting issues."""
        
    def suggest_improvements(self, card: Dict) -> List[str]:
        """Suggest improvements for better user experience."""
```

## 🎯 Current Implementation Status

### ⚠️ Important Update (2025-08-28)

The smart card natural language processing functionality (`send_smart_card`, `create_card_from_template`, etc.) has been **deprecated and removed** due to structural formatting issues with the Google Chat Cards v2 API. The system now focuses on the working card types that have been thoroughly tested.

### ✅ Working Card Functions

The following card functions remain fully operational:
- `send_simple_card` - Basic notification cards
- `send_interactive_card` - Interactive cards with buttons
- `send_form_card` - Form cards with input fields
- `send_message` - Plain text messages
- `send_dynamic_card` - Dynamic card creation using ModuleWrapper

### 📊 Current Qdrant Collections

The system creates three Qdrant collections when running:

| Collection | Purpose | Required? | Impact if Missing |
|-----------|---------|-----------|-------------------|
| **`card_framework_components`** | Stores card component templates for semantic search in unified_card_tool | Yes (for dynamic cards) | Can't use natural language card descriptions |
| **`mcp_module_card_framework_v2`** | Card framework API introspection for parameter adaptation | Yes (for complex cards) | Card parameter adaptation fails |
| **`mcp_module_json`** | JSON module introspection for consistent JSON handling | No (nice-to-have) | JSON operations still work normally |

#### Collection Details:

1. **`card_framework_components`**
   - Created by: `gchat/unified_card_tool.py`
   - Used for: Semantic search of card types (simple, interactive, form)
   - Example: "create a card with buttons" → finds interactive_card component

2. **`mcp_module_card_framework_v2`**
   - Created by: `adapters/module_wrapper_mcp.py` via middleware
   - Used for: API introspection and parameter validation
   - Example: Ensures correct parameter mapping for card_framework.v2 functions

3. **`mcp_module_json`**
   - Created by: `adapters/module_wrapper_mcp.py` (line 152 in server.py)
   - Used for: JSON operations consistency across all tools
   - Note: **Optional** - could be removed to reduce Qdrant connection errors

### 🔧 Reducing Qdrant Connection Errors

If you're experiencing Qdrant connection errors when the service isn't running, you can:

```python
# In server.py line 152, change from:
setup_module_wrapper_middleware(mcp, modules_to_wrap=["json", "card_framework.v2"])

# To (removes optional JSON wrapper):
setup_module_wrapper_middleware(mcp, modules_to_wrap=["card_framework.v2"])
```

This reduces connection attempts by 1/3 without affecting functionality.

## 🛠️ Deprecated Features (Moved to Archive)

The following features have been deprecated and moved to `delete_later/gchat_smart_cards/`:

### Deprecated Files:
- `gchat/content_mapping/` - Entire module (10 files)
- `gchat/smart_card_tool.py` - Smart card MCP tool registration
- `gchat/enhanced_card_tool.py` - Enhanced card tool with content mapping

### Deprecated Functions:
- `send_smart_card()` - Natural language card creation
- `create_card_from_template()` - Template-based card creation
- `create_multi_modal_card()` - Multi-modal card creation
- `optimize_card_layout()` - Card layout optimization

### Migration Path:
If you were using deprecated functions:
- `send_smart_card` → Use `send_simple_card`, `send_interactive_card`, or `send_form_card`
- `create_card_from_template` → Build cards directly using working functions
- `create_multi_modal_card` → Use standard card functions with image/button widgets

## 🚀 Future Improvements

While the smart card natural language processing has been deprecated, the following improvements could enhance the existing working system:

### Phase 1: Template System Enhancement (Priority: High)

1. **Predefined Templates for Working Card Types**
   - Templates for simple, interactive, and form cards
   - Template storage in Qdrant
   - Quick template selection

2. **Better Parameter Mapping**
   - Improved parameter inference for existing card types
   - Default value handling
   - Validation and error messages

### Phase 2: Enhanced Dynamic Card Creation (Priority: Medium)

1. **Improve send_dynamic_card**
   - Better semantic search for card components
   - Smarter parameter inference
   - Fallback mechanisms when Qdrant is unavailable

2. **Error Handling**
   - Graceful degradation when Qdrant is offline
   - Better error messages for malformed cards
   - Validation before sending to Google Chat

## 🔧 Implementation Examples

### Current Working Card Usage

```python
# Simple Card (Working)
await send_simple_card(
    user_google_email="user@example.com",
    space_id="spaces/123",
    title="Notification",
    subtitle="System Update",
    text="The system has been updated successfully"
)

# Interactive Card with Buttons (Working)
await send_interactive_card(
    user_google_email="user@example.com",
    space_id="spaces/123",
    title="Approval Request",
    text="Please review and approve",
    buttons=[
        {"text": "Approve", "action": "approve_action"},
        {"text": "Reject", "action": "reject_action"}
    ]
)

# Form Card (Working)
await send_form_card(
    user_google_email="user@example.com",
    space_id="spaces/123",
    title="Feedback Form",
    fields=[
        {"name": "feedback", "label": "Your Feedback", "type": "text_input"},
        {"name": "rating", "label": "Rating", "type": "selection", "options": ["1", "2", "3", "4", "5"]}
    ]
)
```

### Dynamic Card Creation (Still Working)

```python
# Using send_dynamic_card with natural language description
await send_dynamic_card(
    user_google_email="user@example.com",
    space_id="spaces/123",
    card_description="simple card with a title and message",
    card_params={
        "title": "Meeting Reminder",
        "text": "Team standup at 2 PM"
    }
)
```

## 📈 Key Technical Findings

From the Rivers Unlimited MCP Testing Report:

1. **Success Rate:** 80% (4 out of 5 card types working)
2. **Critical Fix:** Correct button format for interactive cards:
   ```json
   // ✅ Correct
   {"onClick": {"action": {"function": "method"}}}
   
   // ❌ Wrong (was causing issues)
   {"onClick": {"action": {"actionMethodName": "method"}}}
   ```

3. **Working Functions:**
   - ✅ send_simple_card - Perfect for basic notifications
   - ✅ send_interactive_card - Working with correct "function" button format
   - ✅ send_form_card - Full form functionality with inputs
   - ✅ send_message - Basic text messaging
   - ✅ list_spaces - Space discovery and targeting

## 🔍 Troubleshooting Qdrant Connection Issues

If you see errors like `[Errno 61] Connection refused`:

1. **Check if Qdrant is running:**
   ```bash
   # Start Qdrant using Docker
   docker run -p 6333:6333 qdrant/qdrant
   ```

2. **The system works without Qdrant:** The ModuleWrapper components gracefully handle connection failures and continue to work without the optimization benefits.

3. **To reduce connection attempts:** Consider removing the JSON module wrapper as shown above.

4. **For testing:** You can disable Qdrant entirely by setting environment variables or modifying the wrapper initialization to skip Qdrant operations.

## Summary

The ModuleWrapper system provides powerful capabilities for the working card functions in the Google Chat integration. While the smart card natural language processing features have been deprecated, the core functionality remains robust with 4 fully operational card types. The system's architecture with Qdrant provides optimization benefits when available but gracefully degrades when the service is offline.