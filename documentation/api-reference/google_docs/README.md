# Google Docs MCP Tools

This module provides comprehensive Google Docs integration tools for FastMCP2 servers, enabling rich document creation and management through the Model Context Protocol (MCP).

## Overview

The Google Docs MCP tools leverage Google's APIs to provide seamless document operations with automatic rich content formatting. The tools use a sophisticated approach that combines Google Drive API's HTML-to-Docs conversion with intelligent content type detection for optimal formatting results.

## Key Features

- ✅ **Rich Content Support**: Automatic conversion of Markdown and HTML to properly formatted Google Docs
- ✅ **Intelligent Content Detection**: Automatically detects plain text, Markdown, and HTML content types  
- ✅ **Google's Native Conversion**: Uses Google Drive API's built-in HTML-to-Docs conversion for reliable formatting
- ✅ **Comprehensive Search**: Search documents by name with flexible filtering
- ✅ **Multi-format Support**: Read content from Google Docs and Office files (.docx, etc.)
- ✅ **Folder Organization**: List and organize documents within Drive folders
- ✅ **Fallback Authentication**: Robust authentication with middleware injection and direct service fallback

## Architecture

### Authentication Pattern
- **Primary**: Middleware-based service injection (no decorators required)
- **Fallback**: Direct service creation when middleware unavailable
- **Automatic**: Google service authentication and token refresh
- **User-friendly**: Comprehensive error handling with clear guidance

### Content Processing Pipeline
1. **Content Type Detection**: Uses regex patterns to identify Markdown, HTML, or plain text
2. **Format Conversion**: Converts Markdown to HTML using lightweight converter
3. **Drive API Upload**: Uploads HTML content with `mimeType: 'application/vnd.google-apps.document'`
4. **Google Conversion**: Google automatically converts HTML to formatted Google Doc
5. **Result**: Properly formatted document with headings, lists, tables, links, and styling

## Available Tools

### 1. `create_doc` - Create Rich Google Documents

Creates new Google Docs with automatic rich formatting support.

**Parameters:**
- `user_google_email` (string): User's Google email for authentication
- `title` (string): Document title
- `content` (string, optional): Initial content with automatic format detection

**Supported Content Types:**
- **Plain Text**: Simple text insertion
- **Markdown**: Full Markdown support including:
  - Headers (`# ## ###`)
  - Bold/Italic (`**bold** *italic*`)
  - Links (`[text](url)`)
  - Lists (`- item` or `1. item`)
- **HTML**: Complete HTML support including:
  - All heading levels (`<h1>` to `<h6>`)
  - Text formatting (`<strong>`, `<em>`, `<u>`)
  - Lists (`<ul>`, `<ol>`, `<li>`)
  - Tables (`<table>`, `<tr>`, `<td>`)
  - Links (`<a href="">`)
  - Styled content with CSS

**Example Usage:**
```python
# Markdown content
result = await create_doc(
    user_google_email="user@example.com",
    title="Project Report",
    content="""
# Executive Summary

This report covers **key findings** and *recommendations*.

## Key Points
- Revenue increased by 25%
- Customer satisfaction improved
- [Detailed metrics](https://example.com)

## Next Steps
1. Implement feedback system
2. Expand to new markets
3. Review quarterly results
"""
)

# HTML content
result = await create_doc(
    user_google_email="user@example.com", 
    title="Formatted Document",
    content="""
<h1>Professional Report</h1>
<p>This document contains <strong>rich formatting</strong> with <em>proper styling</em>.</p>
<table border="1">
    <tr><th>Metric</th><th>Value</th></tr>
    <tr><td>Revenue</td><td>$1.2M</td></tr>
</table>
"""
)
```

**Returns:**
```
Created Google Doc 'Project Report' (ID: 1abc...) for user@example.com with markdown formatting. 
Link: https://docs.google.com/document/d/1abc.../edit
```

### 2. `search_docs` - Find Documents by Name

Searches for Google Docs using name-based filtering.

**Parameters:**
- `user_google_email` (string): User's Google email
- `query` (string): Search query (partial name matching)
- `page_size` (int, optional): Max results to return (default: 10)

**Example Usage:**
```python
result = await search_docs(
    user_google_email="user@example.com",
    query="project report",
    page_size=20
)
```

**Returns:**
```
Found 3 Google Docs matching 'project report':
- Q3 Project Report (ID: 1abc...) Modified: 2025-08-30T14:30:00Z Link: https://docs.google.com/...
- Annual Project Summary (ID: 1def...) Modified: 2025-08-29T09:15:00Z Link: https://docs.google.com/...
- Project Status Report (ID: 1ghi...) Modified: 2025-08-28T16:45:00Z Link: https://docs.google.com/...
```

### 3. `get_doc_content` - Read Document Content

Retrieves content from Google Docs and other Drive files with format detection.

**Parameters:**
- `user_google_email` (string): User's Google email
- `document_id` (string): Google Doc or Drive file ID

**Supported File Types:**
- Native Google Docs (`application/vnd.google-apps.document`)
- Microsoft Word files (`.docx`)
- Other text-based formats

**Example Usage:**
```python
content = await get_doc_content(
    user_google_email="user@example.com",
    document_id="1abc123def456ghi789"
)
```

**Returns:**
```
File: "Project Report" (ID: 1abc123..., Type: application/vnd.google-apps.document)
Link: https://docs.google.com/document/d/1abc123.../edit

--- CONTENT ---
Executive Summary
This report covers key findings and recommendations.

Key Points
Revenue increased by 25%
Customer satisfaction improved
Detailed metrics

Next Steps
Implement feedback system
Expand to new markets
Review quarterly results
```

### 4. `list_docs_in_folder` - Browse Folder Contents

Lists Google Docs within a specific Drive folder with structured output.

**Parameters:**
- `user_google_email` (string): User's Google email
- `folder_id` (string, optional): Drive folder ID (default: 'root')
- `page_size` (int, optional): Max results (default: 100)

**Example Usage:**
```python
docs_list = await list_docs_in_folder(
    user_google_email="user@example.com",
    folder_id="1BxY2CzD3EfG4HiJ5KlM6",
    page_size=50
)
```

**Returns Structured Object:**
```json
{
  "docs": [
    {
      "id": "1abc123def456",
      "name": "Q3 Report",
      "modifiedTime": "2025-08-30T14:30:00Z",
      "webViewLink": "https://docs.google.com/document/d/1abc123def456/edit"
    }
  ],
  "count": 1,
  "folderId": "1BxY2CzD3EfG4HiJ5KlM6",
  "folderName": null,
  "userEmail": "user@example.com",
  "error": null
}
```

## Content Formatting Examples

### Markdown to Google Docs
The tool automatically converts Markdown syntax to proper Google Docs formatting:

**Input Markdown:**
```markdown
# Main Title
## Subtitle
This is **bold text** and *italic text*.
- Bullet point 1
- Bullet point 2
[Link to Google](https://google.com)
```

**Result:** Properly formatted Google Doc with:
- H1 heading "Main Title"
- H2 heading "Subtitle" 
- Bold and italic text formatting
- Bulleted list
- Clickable link

### HTML to Google Docs
Full HTML support with advanced formatting:

**Input HTML:**
```html
<h1 style="color: blue;">Professional Report</h1>
<p>This contains <strong>bold</strong> and <em>italic</em> formatting.</p>
<table border="1">
  <tr><th>Name</th><th>Score</th></tr>
  <tr><td>Alice</td><td>95%</td></tr>
</table>
<blockquote>Important note in blockquote format</blockquote>
```

**Result:** Google Doc with:
- Styled blue heading
- Formatted text with bold/italic
- Properly formatted table
- Blockquote styling

## Error Handling

The tools provide comprehensive error handling with user-friendly messages:

### Authentication Issues
```
❌ No Credentials Found

No authentication credentials found for user@example.com.

To authenticate:
1. Run `start_google_auth` with your email: user@example.com
2. Follow the authentication flow in your browser
3. Grant Drive permissions when prompted
4. Return here after seeing the success page
```

### Permission Problems
```
❌ Permission denied. Make sure you have access to Google Drive.
```

### Invalid Document IDs
```
❌ Document not found: 1invalid_id_here
```

## Technical Implementation

### Why This Approach Works Better

Instead of manually parsing Markdown/HTML and converting to Google Docs API requests, this implementation:

1. **Leverages Google's Conversion Engine**: Uses Google Drive API's built-in HTML-to-Docs conversion
2. **Simpler Code**: ~150 lines vs 400+ lines of manual parsing
3. **Better Results**: Google's converter handles edge cases and complex formatting
4. **More Reliable**: Battle-tested conversion logic maintained by Google
5. **Comprehensive Support**: Tables, lists, styling, special characters all work

### Content Processing Flow
```
User Content Input
       ↓
Content Type Detection (regex patterns)
       ↓
Markdown → HTML Conversion (if needed)
       ↓
Drive API Upload (HTML → Google Doc)
       ↓
Google's Conversion Engine
       ↓
Formatted Google Document
```

## Dependencies

- `google-api-python-client`: Google APIs integration
- `fastmcp`: FastMCP server framework  
- `auth.service_helpers`: Authentication utilities
- `googleapiclient.http`: Media upload support

## Authentication Requirements

The tools require Google OAuth2 authentication with the following scopes:
- `https://www.googleapis.com/auth/documents` - Google Docs access
- `https://www.googleapis.com/auth/drive` - Google Drive access
- `https://www.googleapis.com/auth/drive.file` - File creation/modification

## Best Practices

1. **Content Formatting**: Use Markdown for simple formatting, HTML for complex layouts
2. **Error Handling**: Always check return messages for authentication issues
3. **File Organization**: Use `list_docs_in_folder` to organize documents by folder
4. **Search Efficiency**: Use specific search terms with `search_docs` for better results
5. **Content Size**: Keep content reasonable size for optimal conversion performance

## Changelog

### Latest Version Features
- ✅ **Automatic Content Detection**: Intelligently detects Markdown, HTML, and plain text
- ✅ **Drive API Conversion**: Uses Google's native HTML-to-Docs conversion
- ✅ **Enhanced Error Handling**: User-friendly authentication guidance
- ✅ **Structured Responses**: JSON responses for `list_docs_in_folder`
- ✅ **Fallback Authentication**: Robust middleware + direct service patterns

---

*This documentation covers the Google Docs MCP tools in FastMCP2. For more information about setting up authentication or other MCP tools, see the main FastMCP2 documentation.*