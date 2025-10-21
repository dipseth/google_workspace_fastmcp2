# Google Chat API Reference

Complete API documentation for all Google Chat tools in the FastMCP Google MCP Server.

## Overview

The Google Chat service provides comprehensive messaging, space management, rich card framework integration, and webhook delivery capabilities. This service includes advanced card creation tools, Chat app development framework, and seamless integration with other Google services.

## Available Tools

### Core Chat Operations
| Tool Name | Description |
|-----------|-------------|
| [`list_spaces`](#list_spaces) | List accessible Google Chat spaces |
| [`list_messages`](#list_messages) | Retrieve messages from Chat spaces |
| [`send_message`](#send_message) | Send text messages to spaces |
| [`search_messages`](#search_messages) | Search for messages across spaces |

### Advanced Card Framework
| Tool Name | Description |
|-----------|-------------|
| [`send_card_message`](#send_card_message) | Send rich card messages with complex layouts |
| [`send_simple_card`](#send_simple_card) | Send basic card messages quickly |
| [`send_interactive_card`](#send_interactive_card) | Send cards with buttons and interactions |
| [`send_form_card`](#send_form_card) | Send form-based cards for input collection |
| [`send_rich_card`](#send_rich_card) | Send advanced cards with multiple sections |
| [`send_dynamic_card`](#send_dynamic_card) | AI-powered card creation from natural language |

### Card Framework Management
| Tool Name | Description |
|-----------|-------------|
| [`get_card_framework_status`](#get_card_framework_status) | Check Card Framework v2 availability |
| [`list_available_card_types`](#list_available_card_types) | List supported card types and components |
| [`list_available_card_components`](#list_available_card_components) | List card components with search capability |
| [`get_adapter_system_status`](#get_adapter_system_status) | Check adapter system operational status |

### Chat App Development
| Tool Name | Description |
|-----------|-------------|
| [`initialize_chat_app_manager`](#initialize_chat_app_manager) | Initialize Chat app development environment |
| [`create_chat_app_manifest`](#create_chat_app_manifest) | Generate Chat app configuration manifests |
| [`generate_webhook_template`](#generate_webhook_template) | Create FastAPI webhook handler templates |
| [`list_chat_app_resources`](#list_chat_app_resources) | Browse app development resources |

---

## Tool Details

### Core Chat Operations

#### `list_spaces`

List all Google Chat spaces accessible to the authenticated user.

**Parameters:**
- `user_google_email` (string, required): User's Google email for authentication
- `page_size` (integer, optional, default: 100): Number of spaces to return
- `page_token` (string, optional): Pagination token for large result sets

**Response:**
- Array of space information including names, types, and IDs
- Space membership details and permissions
- Pagination information for large datasets

#### `send_message`

Send text messages to Google Chat spaces with optional threading support.

**Parameters:**
- `user_google_email` (string, required): User's Google email
- `space_id` (string, required): Target Chat space ID
- `text` (string, required): Message content
- `thread_key` (string, optional): Thread identifier for threaded messages

**Features:**
- Rich text formatting support
- @mention capability
- Thread-based conversations
- Webhook delivery integration

### Advanced Card Framework

#### `send_dynamic_card`

Revolutionary AI-powered card creation from natural language descriptions.

**Parameters:**
- `user_google_email` (string, required): User's Google email
- `space_id` (string, required): Target Chat space
- `card_description` (string, required): Natural language card description
- `webhook_url` (string, optional): Webhook URL for card interactions

**AI-Powered Features:**
- Natural language processing for card structure
- Automatic component selection and layout
- Intelligent button and interaction setup
- Context-aware card generation

**Example Usage:**
```
"Create an announcement card with red header saying 'System Maintenance' 
and buttons for 'More Info' and 'Schedule'"
```

#### `send_card_message`

Send sophisticated card messages with advanced layouts and interactive components.

**Parameters:**
- `user_google_email` (string, required): User's Google email
- `space_id` (string, required): Target space ID
- `card_data` (object, required): Card configuration object
- `webhook_url` (string, optional): Webhook for button interactions

**Card Components:**
- Headers with custom styling
- Rich text sections with formatting
- Interactive buttons with callbacks
- Images and media elements
- Form inputs and selections

#### `send_interactive_card`

Create cards with button interactions and user input capabilities.

**Parameters:**
- `user_google_email` (string, required): User's Google email
- `space_id` (string, required): Target space
- `title` (string, required): Card title
- `text` (string, required): Card content
- `buttons` (array, required): Array of button configurations
- `webhook_url` (string, optional): Interaction webhook

**Button Styles:**
- `FILLED`: Solid background buttons
- `OUTLINED`: Border-only buttons
- `TEXT`: Plain text buttons
- Custom colors and icons

### Chat App Development

#### `create_chat_app_manifest`

Generate complete Google Chat app manifests for app development.

**Parameters:**
- `app_name` (string, required): Application name
- `description` (string, required): App description
- `avatar_url` (string, optional): App avatar image URL
- `home_url` (string, optional): App homepage URL
- `scopes` (array, optional): Required OAuth scopes

**Generated Manifest Features:**
- Complete OAuth scope configuration
- Event subscription setup
- Slash command definitions
- Interactive card configurations
- Webhook endpoint specifications

#### `generate_webhook_template`

Create FastAPI webhook handler templates with Card Framework integration.

**Parameters:**
- `app_name` (string, required): Application name
- `include_card_examples` (boolean, optional, default: true): Include card examples
- `include_auth_handling` (boolean, optional, default: true): Include authentication

**Template Features:**
- Complete FastAPI application structure
- Card Framework v2 integration
- Event handling for all Chat events
- Authentication middleware
- Docker deployment configuration

---

## Authentication & Scopes

Required Google API scopes:
- `https://www.googleapis.com/auth/chat.messages`: Send and manage messages
- `https://www.googleapis.com/auth/chat.messages.readonly`: Read messages
- `https://www.googleapis.com/auth/chat.spaces`: Manage spaces
- `https://www.googleapis.com/auth/chat.spaces.readonly`: Read space information

### Service Account Authentication
For Chat apps, service account authentication is supported:
- Automated message sending without user interaction
- Bot-like functionality for automated workflows
- Enterprise integration capabilities

## Card Framework v2 Integration

### Advanced Widget Support
The platform includes comprehensive Card Framework v2 integration:

**Widget Types:**
- `TextParagraph`: Rich text content with formatting
- `DecoratedText`: Text with icons and styling
- `ButtonList`: Interactive button collections
- `Image`: Images with custom sizing and positioning
- `Divider`: Visual section separators
- `Grid`: Multi-column layouts
- `Columns`: Flexible column arrangements

**Button Styling:**
```json
{
  "text": "Action Button",
  "style": "FILLED",
  "color": {
    "red": 0.2,
    "green": 0.6,
    "blue": 1.0
  },
  "onClick": {
    "openLink": {"url": "https://example.com"}
  }
}
```

### Natural Language Card Creation
Revolutionary NLP-powered card generation:
- Parse natural language descriptions
- Extract card structure and components
- Generate appropriate widgets and layouts
- Apply intelligent styling and formatting

## Integration Capabilities

### Multi-Service Coordination
Google Chat integrates seamlessly with other Google services:

**Gmail Integration:**
- Email notification for Chat messages
- Email-to-Chat bridging
- Automated reporting via both channels

**Drive Integration:**
- File sharing in Chat messages
- Document collaboration notifications
- Automatic file access management

**Calendar Integration:**
- Meeting notifications in Chat
- Event scheduling through Chat commands
- Calendar-based Chat reminders

## Best Practices

### Message Design
1. **Clear Communication**: Use concise, actionable language
2. **Rich Formatting**: Leverage cards for complex information
3. **Interactive Elements**: Use buttons for user actions
4. **Thread Management**: Organize related messages in threads

### Card Development
1. **User Experience**: Design intuitive, accessible interfaces
2. **Performance**: Optimize card loading and interaction speed
3. **Error Handling**: Provide clear feedback for user actions
4. **Mobile Compatibility**: Ensure cards work on mobile devices

### App Development
1. **Webhook Security**: Implement proper authentication and validation
2. **Event Handling**: Process all relevant Chat events appropriately
3. **Scalability**: Design for enterprise-scale usage
4. **Monitoring**: Implement comprehensive logging and analytics

## Common Use Cases

### Automated Notifications
```python
# Send system alert with interactive options
await send_interactive_card(
    user_google_email="system@company.com",
    space_id="spaces/AAAA...",
    title="🚨 System Alert",
    text="Database maintenance scheduled for tonight",
    buttons=[
        {"text": "Acknowledge", "style": "FILLED"},
        {"text": "Reschedule", "style": "OUTLINED"},
        {"text": "Details", "style": "TEXT"}
    ],
    webhook_url="https://api.company.com/chat/webhooks"
)
```

### Team Collaboration
- Project status updates with rich cards
- Interactive polls and surveys
- Document sharing and collaboration
- Meeting scheduling and coordination

### Business Process Automation
- Approval workflows with interactive cards
- Status reporting and dashboards
- Alert systems with escalation
- Customer service integration

## Error Handling

### Common Issues
- **Permission Denied**: Verify Chat API permissions and space access
- **Invalid Space**: Ensure space IDs are current and accessible
- **Card Rendering**: Validate card JSON structure and components
- **Webhook Failures**: Check webhook URL accessibility and authentication

### Troubleshooting
- **Authentication**: Use `get_adapter_system_status` for auth diagnostics
- **Card Framework**: Check `get_card_framework_status` for component availability
- **Message Delivery**: Verify space membership and permissions
- **App Integration**: Validate Chat app configuration and scopes

## Performance Optimization

### Message Efficiency
- **Batch Operations**: Group related messages when possible
- **Card Caching**: Cache frequently used card templates
- **Webhook Performance**: Optimize webhook response times
- **Rate Limiting**: Respect Google Chat API rate limits

### Development Best Practices
- **Template Reuse**: Leverage card templates for consistent design
- **Component Libraries**: Build reusable card component libraries
- **Testing**: Implement comprehensive Chat app testing
- **Monitoring**: Track message delivery and interaction metrics

---

For more information, see:
- [Card Framework v2 Documentation](../../CARD_FRAMEWORK_V2.md)
- [Chat App Development Guide](../../CHAT_APP_DEVELOPMENT.md)
- [Authentication Guide](../auth/README.md)
- [Main API Reference](../README.md)