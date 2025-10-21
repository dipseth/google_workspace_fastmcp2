# Google Forms API Reference

Complete API documentation for all Google Forms tools in the FastMCP Google MCP Server with comprehensive documentation enhancements, structured return types, and extensive LLM-friendly examples.

## Overview

The Google Forms service provides a complete form lifecycle management system with enhanced documentation, structured responses, and comprehensive workflow guidance. This service offers:

- **8 Comprehensive Tools**: Full form creation, question management, response handling, and publishing
- **Structured TypedDict Responses**: 6 specialized response classes for reliable data handling
- **Multi-Service Integration**: Seamless Forms + Drive + Gmail coordination
- **Enhanced LLM Documentation**: Detailed examples, parameter descriptions, and workflow guidance
- **HTML Formatting Support**: Clear guidance on Forms API capabilities and limitations
- **Authentication Flexibility**: Supports both explicit email and middleware injection patterns

## Key Features

### **COMPREHENSIVE WORKFLOW SUPPORT**
1. **CREATE FORM** → **ADD QUESTIONS** → **PUBLISH** → **COLLECT RESPONSES** → **ANALYZE**
2. Forms can be shared publicly or with specific users via email
3. Responses can be retrieved individually or in batches with pagination
4. Questions support 8+ types with rich formatting options

### **STRUCTURED RETURN TYPES**
All tools now return structured TypedDict responses instead of strings:
- `FormCreationResult` - Form creation responses
- `FormUpdateResult` - Question and form update responses  
- `FormDetails` - Comprehensive form structure data
- `FormPublishResult` - Publishing and sharing operation results
- `FormResponseDetails` - Individual response analysis
- `FormResponsesListResponse` - Paginated response collections

### **ENHANCED QUESTION TYPES**
- `TEXT_QUESTION` - Short/long text responses with paragraph options
- `MULTIPLE_CHOICE_QUESTION` - Radio button selections with shuffle options
- `CHECKBOX_QUESTION` - Multiple selection checkboxes
- `SCALE_QUESTION` - Numeric rating scales (1-5, 1-10, custom ranges)
- `DATE_QUESTION` - Date picker with optional time and year
- `TIME_QUESTION` - Time picker with optional duration
- `RATING_QUESTION` - Star rating systems
- `FILE_UPLOAD_QUESTION` - File attachment uploads with size limits

## Available Tools

| Tool Name | Description | Return Type |
|-----------|-------------|-------------|
| [`create_form`](#create_form) | Create new Google Forms with customizable title, description, and document title | `FormCreationResult` |
| [`add_questions_to_form`](#add_questions_to_form) | Add multiple interactive questions with comprehensive formatting options | `FormUpdateResult` |
| [`get_form`](#get_form) | Retrieve comprehensive form details including metadata and all questions | `FormDetails` |
| [`set_form_publish_state`](#set_form_publish_state) | Control form response acceptance with basic settings configuration | `FormPublishResult` |
| [`publish_form_publicly`](#publish_form_publicly) | Make forms publicly accessible using Forms + Drive APIs | `FormPublishResult` |
| [`get_form_response`](#get_form_response) | Retrieve detailed individual response with answer-question mapping | `FormResponseDetails` |
| [`list_form_responses`](#list_form_responses) | List all responses with efficient pagination and structured data | `FormResponsesListResponse` |
| [`update_form_questions`](#update_form_questions) | Modify existing questions using efficient batch operations | `FormUpdateResult` |

---

## Tool Details

### `create_form`

Create a new Google Form with customizable properties and automatic document title handling.

**Parameters:**
- `title` (string, required): The main title displayed at the top of the form
- `description` (string, optional): Optional description explaining the form's purpose
- `document_title` (string, optional): Title shown in browser tab (defaults to main title)
- `user_google_email` (UserGoogleEmailForms, optional): Google account email (uses middleware injection if omitted)

**Enhanced Features:**
- Automatic documentTitle handling (read-only after creation)
- HTML formatting support in descriptions
- Structured FormCreationResult response
- Immediate edit and response URLs

**Response Structure (FormCreationResult):**
```json
{
  "success": true,
  "message": "✅ Successfully created form 'Form Title'",
  "formId": "1ABC...",
  "title": "Form Title",
  "editUrl": "https://docs.google.com/forms/d/.../edit",
  "responseUrl": "https://docs.google.com/forms/d/e/.../viewform"
}
```

### `add_questions_to_form`

Add multiple interactive questions to an existing Google Form using efficient batch operations.

**Parameters:**
- `form_id` (string, required): The ID of the form to add questions to
- `questions` (List[Dict], required): List of question dictionaries with type and configuration
- `user_google_email` (UserGoogleEmailForms, optional): Google account email

**Comprehensive Question Examples:**

**Text Questions:**
```python
{
  "type": "TEXT_QUESTION",
  "title": "What's your name?",
  "required": True,
  "paragraph": False  # False = short text, True = long text
}
```

**Multiple Choice with HTML:**
```python
{
  "type": "MULTIPLE_CHOICE_QUESTION", 
  "title": "Which <b>best describes</b> your role?",
  "options": ["Manager", "Developer", "Designer", "Other"],
  "required": True,
  "shuffle": False
}
```

**Rating Scales:**
```python
{
  "type": "SCALE_QUESTION",
  "title": "Rate your satisfaction (1-5)",
  "low": 1,
  "high": 5,
  "low_label": "Very Dissatisfied",
  "high_label": "Very Satisfied",
  "required": True
}
```

**File Uploads:**
```python
{
  "type": "FILE_UPLOAD_QUESTION",
  "title": "Please upload your resume",
  "max_files": 1,
  "max_file_size": 10485760,  # 10MB in bytes
  "required": True
}
```

### `get_form`

Retrieve comprehensive details and structure of a Google Form with complete question analysis.

**Parameters:**
- `form_id` (string, required): The unique ID of the form to retrieve
- `user_google_email` (UserGoogleEmailForms, optional): Google account email

**Response Structure (FormDetails):**
```json
{
  "success": true,
  "formId": "1ABC...",
  "title": "Customer Survey",
  "description": "Please help us improve",
  "documentTitle": "Customer Survey",
  "editUrl": "https://docs.google.com/forms/d/.../edit",
  "responseUrl": "https://docs.google.com/forms/d/e/.../viewform",
  "questions": [
    {
      "itemId": "12345",
      "title": "What's your name?",
      "type": "TEXT_QUESTION",
      "required": true,
      "details": "- \"What's your name?\" (ID: 12345, Type: TEXT_QUESTION, Required: Yes, Paragraph: No)"
    }
  ],
  "questionCount": 1
}
```

### `set_form_publish_state`

Control basic form settings and response acceptance state with guidance for complete configuration.

**Parameters:**
- `form_id` (string, required): The unique ID of the form to configure
- `accepting_responses` (boolean, optional): Desired response acceptance state (default: True)
- `user_google_email` (UserGoogleEmailForms, optional): Google account email

**Important:** Complete response control requires manual configuration in the Google Forms web interface under Settings > Responses.

### `publish_form_publicly`

Make a Google Form publicly accessible using both Forms and Drive APIs for comprehensive permission management.

**Parameters:**
- `form_id` (string, required): The unique ID of the form to publish
- `anyone_can_respond` (boolean, optional): Enable public access (default: True)
- `share_with_emails` (List[str], optional): List of email addresses to share with
- `user_google_email` (UserGoogleEmailForms, optional): Google account email

**Multi-Service Integration:**
- Uses Forms API for form metadata
- Uses Drive API for sharing permissions
- Handles both public access and individual user sharing
- Sends notification emails to shared users

**Response Structure (FormPublishResult):**
```json
{
  "success": true,
  "message": "✅ Successfully published form",
  "formId": "1ABC...",
  "title": "My Form",
  "editUrl": "https://docs.google.com/forms/d/.../edit",
  "responseUrl": "https://docs.google.com/forms/d/e/.../viewform",
  "publishState": "published",
  "publicAccess": true,
  "sharedWith": ["colleague@company.com"],
  "sharingResults": ["✅ Form is now publicly accessible"]
}
```

### `get_form_response`

Retrieve detailed information about a specific form response with comprehensive answer-question mapping.

**Parameters:**
- `form_id` (string, required): The unique ID of the form containing the response
- `response_id` (string, required): The unique ID of the specific response to retrieve
- `user_google_email` (UserGoogleEmailForms, optional): Google account email

**Response Structure (FormResponseDetails):**
```json
{
  "success": true,
  "responseId": "response123",
  "formId": "1ABC...",
  "submittedTime": "2024-01-15T10:30:00.000Z",
  "respondentEmail": "user@example.com",
  "answers": [
    {
      "questionId": "12345",
      "questionTitle": "What's your name?",
      "answer": "John Smith"
    }
  ],
  "answerCount": 1
}
```

### `list_form_responses`

Retrieve all form responses with efficient pagination support and structured answer mapping.

**Parameters:**
- `form_id` (string, required): The unique ID of the form to retrieve responses from
- `page_size` (integer, optional): Number of responses per page (1-100, default: 10)
- `page_token` (string, optional): Token for pagination continuation
- `user_google_email` (UserGoogleEmailForms, optional): Google account email

**Pagination Workflow:**
```python
# Get first page
page1 = list_form_responses(form_id="your_form", page_size=25)

# Check if more pages exist
if page1.nextPageToken:
    page2 = list_form_responses(
        form_id="your_form",
        page_size=25, 
        page_token=page1.nextPageToken
    )
```

**Response Structure (FormResponsesListResponse):**
```json
{
  "responses": [...],
  "count": 10,
  "formId": "1ABC...",
  "formTitle": "Customer Survey", 
  "userEmail": "user@example.com",
  "pageToken": null,
  "nextPageToken": "next_page_token",
  "error": null
}
```

### `update_form_questions`

Modify existing questions in a Google Form using efficient batch operations with comprehensive validation.

**Parameters:**
- `form_id` (string, required): The unique ID of the form containing questions to update
- `questions_to_update` (List[Dict], required): List of update dictionaries with item_id + changes
- `user_google_email` (UserGoogleEmailForms, optional): Google account email

**Update Structure Examples:**
```python
# Update question titles and required status
questions_to_update = [
    {
        "item_id": "12345",  # Get from get_form output
        "title": "Updated: What's your full name?",
        "required": True
    },
    {
        "item_id": "12346",
        "title": "Updated: Rate your satisfaction", 
        "required": False
    }
]
```

**Workflow:** Use `get_form` first to get question item_ids, then use those IDs in your updates.

---

## HTML Formatting Support

Google Forms API has **LIMITED** HTML support for rich content:

### **SUPPORTED HTML ELEMENTS:**
- **Form/Question Descriptions**: Basic HTML tags like `<b>`, `<i>`, `<u>`, `<br>`, `<p>`
- **Links**: `<a href="...">text</a>` for clickable links
- **Lists**: `<ul>`, `<ol>`, `<li>` for bullet and numbered lists

### **RICH CONTENT ALTERNATIVES:**
- **Images**: Use imageItem type (not HTML `<img>` tags)
- **Videos**: Use videoItem type (YouTube videos)
- **Formatted Text**: Use textItem type for rich text sections
- **HTML limitations**: No CSS, JavaScript, or complex HTML structures

### **FORMATTING EXAMPLES:**
```python
# Description with HTML
description = "Please fill out <b>all required</b> fields.<br>Visit <a href='https://example.com'>our website</a> for help."

# Question with HTML formatting
{
    "type": "TEXT_QUESTION",
    "title": "Please provide your <b>full legal name</b> as it appears on your ID",
    "description": "<i>Note:</i> This information will be used for verification.<br>Visit <a href='https://help.company.com'>our help page</a> for guidelines."
}
```

## Authentication & Scopes

**Required Google API Scopes:**
- `https://www.googleapis.com/auth/forms.body`
- `https://www.googleapis.com/auth/forms.body.readonly`  
- `https://www.googleapis.com/auth/forms.responses.readonly`
- `https://www.googleapis.com/auth/drive.file` (for public publishing)

**Authentication Flexibility:**
- **Explicit Email**: Provide `user_google_email` parameter
- **Middleware Injection**: Omit `user_google_email` for automatic authentication

## Multi-Service Integration

Google Forms tools integrate seamlessly with other Google services:

**Drive Integration:**
- Automatic public sharing for published forms
- File permission management via Drive API
- Response export capabilities

**Gmail Integration:** 
- Automated form distribution via email
- Response notifications
- Form sharing workflows

## Workflow Examples

### **Complete Form Creation Workflow:**
```python
# 1. Create form
form = create_form(
    title="Customer Feedback Survey",
    description="Help us improve our services"
)

# 2. Add questions
add_questions_to_form(form.formId, [
    {
        "type": "TEXT_QUESTION",
        "title": "What's your name?",
        "required": True
    },
    {
        "type": "SCALE_QUESTION", 
        "title": "Rate your satisfaction",
        "low": 1,
        "high": 5,
        "required": True
    }
])

# 3. Publish publicly
publish_form_publicly(
    form_id=form.formId,
    anyone_can_respond=True
)

# 4. Collect responses
responses = list_form_responses(form_id=form.formId)
```

## Best Practices

1. **Form Structure**: Design clear, logical question flow with proper HTML formatting
2. **Question Types**: Choose appropriate input types for effective data collection
3. **Response Handling**: Implement proper pagination for large response datasets
4. **Public Publishing**: Use Drive integration for maximum accessibility
5. **Multi-Service Workflows**: Leverage Forms + Drive + Gmail coordination
6. **Structured Responses**: Utilize TypedDict responses for reliable data processing

## Error Handling

All tools return structured error responses with meaningful messages:

**Common Error Scenarios:**
- **Permission Denied**: Ensure proper Google Forms API permissions
- **Form Not Found**: Validate form IDs before operations (404 errors)
- **Invalid Questions**: Use proper question structure validation
- **Publishing Errors**: Check Drive API permissions for public sharing
- **Validation Errors**: All TypedDict field mismatches have been resolved

**Error Response Example:**
```json
{
  "success": false,
  "message": "❌ Failed to create form: Permission denied",
  "error": "Permission denied error details",
  "formId": null,
  "editUrl": null
}
```

---

## Recent Improvements

**Enhanced Documentation & Structured Responses (Latest Update):**
- ✅ Comprehensive tool documentation with 15+ detailed examples
- ✅ 6 new TypedDict response classes for structured data handling
- ✅ Fixed all field validation errors (publishState, sharedWith, answerCount)
- ✅ Enhanced parameter descriptions with Field annotations
- ✅ HTML formatting guidance and limitations documentation
- ✅ Complete workflow integration examples
- ✅ Live testing validation with MCP server compatibility

For more information, see:
- [Authentication Guide](../auth/README.md)
- [Multi-Service Integration](../../MULTI_SERVICE_INTEGRATION.md)
- [Main API Reference](../README.md)