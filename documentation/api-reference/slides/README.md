# Google Slides API Reference

Complete API documentation for all Google Slides tools in the Groupon Google MCP Server.

## Overview

The Google Slides service provides comprehensive presentation creation, slide management, content manipulation, and export functionality. This service integrates with Google Drive for file management and supports various export formats.

## Available Tools

| Tool Name | Description |
|-----------|-------------|
| [`create_presentation`](#create_presentation) | Create new Google Slides presentations |
| [`get_presentation_info`](#get_presentation_info) | Get detailed presentation and slide information |
| [`add_slide`](#add_slide) | Add new slides to existing presentations |
| [`update_slide_content`](#update_slide_content) | Modify slide content and layout |
| [`export_presentation`](#export_presentation) | Export presentations in various formats |
| [`get_presentation_file`](#get_presentation_file) | Download presentation files locally |

---

## Tool Details

### `create_presentation`

Create new Google Slides presentations with customizable titles and initial configuration.

**Parameters:**
- `user_google_email` (string, required): User's Google email for authentication
- `title` (string, required): Presentation title
- `slide_count` (integer, optional, default: 1): Number of initial slides to create

**Response:**
- New presentation ID and URL
- Created slide information
- Presentation properties and metadata
- Edit and view URLs

**Features:**
- Automatic title slide creation
- Customizable initial slide layouts
- Integration with Google Drive storage
- Immediate edit access

### `get_presentation_info`

Retrieve comprehensive information about presentations including all slides and their content.

**Parameters:**
- `user_google_email` (string, required): User's Google email
- `presentation_id` (string, required): Presentation ID to analyze
- `include_slides` (boolean, optional, default: true): Include detailed slide information

**Response:**
- Complete presentation metadata
- Array of all slides with content details
- Page size and layout information
- Master and layout references

**Slide Information Includes:**
- Slide IDs and layout types
- Content elements and positioning
- Speaker notes and slide notes
- Transition and animation settings
- Background and theme information

### `add_slide`

Add new slides to existing presentations with specified layouts and positioning.

**Parameters:**
- `user_google_email` (string, required): User's Google email
- `presentation_id` (string, required): Target presentation ID
- `layout_id` (string, optional): Slide layout identifier
- `insertion_index` (integer, optional): Position to insert slide

**Supported Layout Types:**
- `TITLE_AND_BODY`: Standard title with content area
- `TITLE_ONLY`: Title slide layout
- `SECTION_HEADER`: Section divider layout
- `TWO_COLUMNS`: Two-column content layout
- `BIG_NUMBER`: Large number display layout
- `BLANK`: Empty slide layout

**Response:**
- New slide ID and properties
- Slide creation confirmation
- Updated presentation structure
- Layout application results

### `update_slide_content`

Modify slide content through batch update requests supporting various content types.

**Parameters:**
- `user_google_email` (string, required): User's Google email
- `presentation_id` (string, required): Target presentation ID
- `requests` (array, required): Array of update request objects

**Supported Update Types:**
- Text replacement and formatting
- Image insertion and positioning
- Shape creation and modification
- Table creation and data population
- Chart insertion and configuration

**Batch Update Capabilities:**
- Multiple simultaneous updates
- Atomic operation execution
- Element creation and deletion
- Style and formatting changes
- Animation and transition updates

**Response:**
- Batch update reply with operation results
- Object IDs for created elements
- Update confirmation and error details
- Modified slide information

### `export_presentation`

Export presentations in various formats for sharing and distribution.

**Parameters:**
- `user_google_email` (string, required): User's Google email
- `presentation_id` (string, required): Presentation to export
- `export_format` (string, required): Target format for export

**Supported Export Formats:**
- `PDF`: Portable Document Format
- `PPTX`: Microsoft PowerPoint format
- `ODP`: OpenDocument Presentation format
- `TXT`: Plain text extraction
- `JPEG`: Image format (slides as images)
- `PNG`: Image format with transparency

**Export Options:**
- Custom page ranges
- Quality settings for image exports
- Include or exclude speaker notes
- Slide transition preservation

**Response:**
- Export URL for download
- File size and format information
- Export job status and completion
- Access permissions and expiration

### `get_presentation_file`

Download presentation files to local storage with format conversion support.

**Parameters:**
- `user_google_email` (string, required): User's Google email
- `presentation_id` (string, required): Presentation to download
- `export_format` (string, required): Download format
- `local_file_path` (string, required): Local destination path

**Download Features:**
- Automatic format conversion during download
- Progress tracking for large files
- Resumable downloads for reliability
- File integrity verification

**Response:**
- Local file path and size
- Download completion status
- File metadata and properties
- Access information and permissions

---

## Authentication & Scopes

Required Google API scopes:
- `https://www.googleapis.com/auth/presentations`: Full presentation access
- `https://www.googleapis.com/auth/presentations.readonly`: Read-only access
- `https://www.googleapis.com/auth/drive.file`: Drive integration for file management

## Advanced Features

### Content Management
Comprehensive support for various content types:
- Rich text with formatting and styles
- Images with positioning and scaling
- Shapes, lines, and drawing objects
- Tables with data and styling
- Charts and graphs from Sheets integration

### Layout and Design
Professional presentation capabilities:
- Master slide and layout management
- Theme and color scheme application
- Custom fonts and typography
- Background images and patterns
- Slide transitions and animations

### Collaboration Features
Multi-user presentation development:
- Real-time collaborative editing
- Comment and suggestion systems
- Version history and revision tracking
- Sharing and permission management

## Integration Capabilities

Seamless integration with other Google services:

**Drive Integration:**
- File storage and organization
- Sharing and collaboration settings
- Version control and backup

**Sheets Integration:**
- Dynamic chart and data integration
- Automatic data updates in presentations
- Spreadsheet-powered content

**Docs Integration:**
- Content import from documents
- Consistent formatting across services
- Document outline to slide conversion

## Best Practices

1. **Slide Design**: Use consistent layouts and themes for professional appearance
2. **Content Organization**: Structure presentations with clear sections and flow
3. **Batch Updates**: Group content changes into single update requests
4. **Export Strategy**: Choose appropriate formats for target audiences
5. **Collaboration**: Leverage real-time editing for team development

## Common Use Cases

### Automated Report Generation
```python
# Create quarterly report presentation
presentation = await create_presentation(
    user_google_email="manager@company.com",
    title="Q4 Business Review",
    slide_count=10
)

# Add title slide
await add_slide(
    user_google_email="manager@company.com",
    presentation_id=presentation["presentation_id"],
    layout_id="TITLE_AND_BODY"
)

# Update with dynamic content
await update_slide_content(
    user_google_email="manager@company.com",
    presentation_id=presentation["presentation_id"],
    requests=[
        {
            "replaceAllText": {
                "containsText": {"text": "{{QUARTER}}"},
                "replaceText": "Q4 2024"
            }
        }
    ]
)

# Export for distribution
await export_presentation(
    user_google_email="manager@company.com",
    presentation_id=presentation["presentation_id"],
    export_format="PDF"
)
```

### Template-Based Presentations
- Create standardized presentation templates
- Populate templates with dynamic data
- Maintain consistent branding and formatting
- Automate routine presentation creation

## Error Handling

Common error scenarios and solutions:

- **Invalid Presentation ID**: Validate presentation existence before operations
- **Permission Denied**: Ensure proper presentation access permissions
- **Layout Errors**: Verify layout IDs exist in presentation theme
- **Content Limits**: Respect slide content size and element limits
- **Export Failures**: Handle timeout and format compatibility issues

## Performance Optimization

- **Batch Operations**: Combine multiple updates into single requests
- **Content Caching**: Cache frequently used images and assets
- **Lazy Loading**: Load slide content on demand for large presentations
- **Parallel Processing**: Execute independent slide operations concurrently

## Export Format Comparison

| Format | Best For | Features | Limitations |
|--------|----------|----------|-------------|
| **PDF** | Document sharing | Universal compatibility, print-ready | Static content, no animations |
| **PPTX** | PowerPoint users | Full feature compatibility | Requires PowerPoint or compatible software |
| **ODP** | Open source | LibreOffice/OpenOffice compatibility | Some feature limitations |
| **TXT** | Content extraction | Plain text, searchable | No formatting or layout |
| **JPEG/PNG** | Image sharing | High quality images | Individual slide files |

---

For more information, see:
- [Authentication Guide](../auth/README.md)
- [Multi-Service Integration](../../MULTI_SERVICE_INTEGRATION.md)
- [Main API Reference](../README.md)