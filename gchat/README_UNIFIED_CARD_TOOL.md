# Google Chat Unified Card Tool

A robust, production-ready MCP tool for Google Chat Cards v2 with comprehensive features for creating and sending dynamic cards.

## 🎯 **Current Status: PRODUCTION READY**

✅ **Blank Message Issue**: RESOLVED - Added pre-send content validation
✅ **Button Styling**: FIXED - Proper `type` field usage for Google Chat API
✅ **Comprehensive Testing**: 14+ test scenarios covering edge cases
✅ **Error Handling**: Robust validation and graceful fallbacks
✅ **Debugging Tools**: Enhanced logging and troubleshooting capabilities

## 🚀 **Key Features**

### **Core Capabilities**
- **Hybrid Card Creation**: ModuleWrapper integration + fallback card structure building
- **Content Validation**: Pre-send validation prevents blank/empty cards
- **Button Styling**: Full support for Google Chat button types (`FILLED`, `FILLED_TONAL`, `OUTLINED`, `BORDERLESS`)
- **Webhook Delivery**: Direct webhook support for card delivery
- **Enhanced Logging**: Comprehensive debugging with payload inspection
- **Error Boundaries**: Graceful handling of malformed inputs

### **Card Types Supported**
- Simple text cards with titles and descriptions
- Interactive cards with styled buttons
- Cards with images and media content
- Form cards with input fields
- Complex layouts with columns and sections
- Cards with natural language descriptions

## 🛠️ **Tools**

### `send_dynamic_card`

**Primary tool** for sending any type of card to Google Chat using natural language descriptions.

```python
await client.call_tool("send_dynamic_card", {
    "user_google_email": "user@gmail.com",
    "space_id": "spaces/AAAAAAAAAAA",
    "card_description": "simple card with styled buttons",
    "card_params": {
        "title": "Hello World",
        "text": "This card demonstrates button styling",
        "buttons": [
            {
                "text": "Filled Button",
                "type": "FILLED",
                "onclick_action": "https://example.com/filled"
            },
            {
                "text": "Outlined Button",
                "type": "OUTLINED",
                "onclick_action": "https://example.com/outlined"
            }
        ]
    },
    "webhook_url": "https://chat.googleapis.com/v1/spaces/.../messages?..."
})
```

#### **Parameters**
- **`user_google_email`** *(string, required)*: User's Google email address
- **`space_id`** *(string, required)*: Google Chat space ID (e.g., `spaces/AAAAAAAAAAA`)
- **`card_description`** *(string, required)*: Natural language description of the desired card
- **`card_params`** *(object, optional)*: Structured card parameters (title, text, buttons, etc.)
- **`thread_key`** *(string, optional)*: Thread key for replies
- **`webhook_url`** *(string, optional)*: Webhook URL for card delivery

### `list_available_card_components`

**Discovery tool** for finding available card components and their capabilities.

```python
await client.call_tool("list_available_card_components", {
    "query": "button styling card",  # Optional
    "limit": 10  # Optional
})
```

#### **Parameters**
- **`query`** *(string, optional)*: Search query to filter components
- **`limit`** *(number, optional)*: Maximum number of components to return

## 📋 **Button Styling Reference**

Google Chat Cards v2 supports four button types using the `type` field:

```python
"buttons": [
    {"text": "Primary Action", "type": "FILLED", "onclick_action": "https://..."},
    {"text": "Secondary Action", "type": "FILLED_TONAL", "onclick_action": "https://..."},
    {"text": "Tertiary Action", "type": "OUTLINED", "onclick_action": "https://..."},
    {"text": "Subtle Action", "type": "BORDERLESS", "onclick_action": "https://..."}
]
```

## 🧪 **Testing & Validation**

The tool includes comprehensive test coverage:

### **Core Functionality Tests**
- ✅ Simple cards (title + text)
- ✅ Interactive cards with buttons
- ✅ Cards with images and media
- ✅ Form cards with input fields
- ✅ Complex layouts with columns
- ✅ Natural language card generation

### **Button Styling Tests**
- ✅ All button types (`FILLED`, `FILLED_TONAL`, `OUTLINED`, `BORDERLESS`)
- ✅ Mixed button styling in single card
- ✅ Button validation and error handling

### **Error Boundary Tests**
- ✅ Empty card parameters handling
- ✅ Malformed button configurations
- ✅ Large content handling
- ✅ Invalid input validation
- ✅ Pre-send content validation

### **Debugging & Monitoring**
- ✅ Individual card debugging tools
- ✅ Payload inspection and logging
- ✅ Response analysis and validation
- ✅ Blank message prevention

## 🔧 **Implementation Details**

### **Content Validation System**
The tool includes robust pre-send validation:

```python
def _validate_card_content(self, card_data: dict) -> tuple[bool, str]:
    """Comprehensive content validation to prevent blank messages"""
    # Checks for:
    # - Header content (title, subtitle, imageUrl)
    # - Section content (widgets, text, buttons)
    # - Fallback content availability
    # - Minimum content requirements
```

### **Hybrid Card Creation**
Two-phase approach for maximum reliability:

1. **ModuleWrapper Phase**: Attempts component-based card creation
2. **Fallback Phase**: Direct card structure building if needed

### **Button Processing**
Proper Google Chat API field mapping:

```python
# ✅ CORRECT: Uses 'type' field
{"text": "Button", "type": "FILLED", "onclick_action": "..."}

# ❌ INCORRECT: Would use 'style' field (old implementation)
{"text": "Button", "style": "FILLED", "onclick_action": "..."}
```

## 🚨 **Known Limitations**

1. **Rate Limiting**: Google Chat API has rate limits - tests include delays
2. **Webhook URLs**: Require valid webhook URLs for actual card delivery
3. **Content Size**: Very large content may be truncated by Google Chat
4. **Field Validation**: Some advanced card features may require specific field combinations

## 📝 **Usage Examples**

### **Quick Start - Simple Card**
```python
result = await client.call_tool("send_dynamic_card", {
    "user_google_email": "user@example.com",
    "space_id": "spaces/AAAAAAAAAAA",
    "card_description": "simple notification",
    "card_params": {
        "title": "Task Complete",
        "text": "Your background task has finished successfully."
    }
})
```

### **Advanced - Styled Buttons**
```python
result = await client.call_tool("send_dynamic_card", {
    "user_google_email": "user@example.com",
    "space_id": "spaces/AAAAAAAAAAA",
    "card_description": "approval request with actions",
    "card_params": {
        "title": "Approval Required",
        "text": "Please review and approve this request.",
        "buttons": [
            {"text": "Approve", "type": "FILLED", "onclick_action": "https://app.com/approve"},
            {"text": "Reject", "type": "OUTLINED", "onclick_action": "https://app.com/reject"},
            {"text": "Details", "type": "BORDERLESS", "onclick_action": "https://app.com/details"}
        ]
    }
})
```

### **Complex - Form Card**
```python
result = await client.call_tool("send_dynamic_card", {
    "user_google_email": "user@example.com",
    "space_id": "spaces/AAAAAAAAAAA",
    "card_description": "feedback form",
    "card_params": {
        "header": {"title": "Feedback Request", "subtitle": "Help us improve"},
        "sections": [{
            "widgets": [
                {"textParagraph": {"text": "How was your experience?"}},
                {"textInput": {"label": "Comments", "name": "feedback"}},
                {"buttonList": {"buttons": [{"text": "Submit", "onClick": {"openLink": {"url": "https://app.com/submit"}}}]}}
            ]
        }]
    }
})
```

## 🔍 **Debugging Tips**

### **Enable Debug Logging**
```python
# Use the debug test for maximum verbosity
pytest tests/test_send_dynamic_card.py::test_debug_single_card -v -s
```

### **Test Individual Components**
```python
# Test specific button styling
pytest tests/test_send_dynamic_card.py::TestSendDynamicCard::test_all_button_types -v -s

# Test error boundaries
pytest tests/test_send_dynamic_card.py::TestSendDynamicCard::test_error_boundary_empty_card -v -s
```

### **Validate Card Content**
The tool automatically validates card content before sending. Look for logs like:
- `🛡️ Content validation passed` - Card has sufficient content
- `❌ Blank message prevention` - Card was blocked due to empty content
- `🎨 Added button type: FILLED` - Button styling applied correctly

---

## 📚 **Additional Resources**

- [Google Chat Cards v2 Documentation](https://developers.google.com/chat/ui/widgets)
- [Google Chat API Reference](https://developers.google.com/chat/api/reference/rest)
- [Button Widget Documentation](https://developers.google.com/chat/ui/widgets/button-list)
