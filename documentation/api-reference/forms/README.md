# Google Forms API Reference

Complete API documentation for all Google Forms tools in the FastMCP2 platform.

## Overview

The Google Forms service provides comprehensive form creation, question management, response handling, and multi-service publishing capabilities. This service integrates seamlessly with Google Drive for public form publishing.

## Available Tools

| Tool Name | Description |
|-----------|-------------|
| [`create_form`](#create_form) | Create new Google Forms with title and description |
| [`add_questions_to_form`](#add_questions_to_form) | Add various question types to existing forms |
| [`get_form`](#get_form) | Retrieve form details including structure and questions |
| [`set_form_publish_state`](#set_form_publish_state) | Control form publication status |
| [`publish_form_publicly`](#publish_form_publicly) | Publish forms publicly using Forms + Drive integration |
| [`get_form_response`](#get_form_response) | Retrieve individual form response details |
| [`list_form_responses`](#list_form_responses) | List all responses for a form with filtering |
| [`update_form_questions`](#update_form_questions) | Modify existing form questions and structure |

---

## Tool Details

### `create_form`

Create a new Google Form with specified title and description.

**Parameters:**
- `user_google_email` (string, required): User's Google email for authentication
- `title` (string, required): Form title
- `description` (string, optional): Form description

**Response:**
- Form ID and creation details
- Form URL for editing
- Initial form structure

### `add_questions_to_form`

Add questions of various types to an existing Google Form.

**Parameters:**
- `user_google_email` (string, required): User's Google email
- `form_id` (string, required): Target form ID
- `questions` (array, required): Array of question objects with type and configuration

**Supported Question Types:**
- TEXT: Short text input
- PARAGRAPH_TEXT: Long text input
- MULTIPLE_CHOICE: Single selection from options
- CHECKBOXES: Multiple selection from options
- DROPDOWN: Dropdown selection
- LINEAR_SCALE: Rating scale questions
- DATE: Date picker
- TIME: Time picker

### `get_form`

Retrieve comprehensive form information including structure and questions.

**Parameters:**
- `user_google_email` (string, required): User's Google email
- `form_id` (string, required): Form ID to retrieve
- `include_responses` (boolean, optional): Include response summary

**Response:**
- Complete form structure
- All questions with configurations
- Form settings and metadata
- Response summary (if requested)

### `set_form_publish_state`

Control the publication status of a Google Form.

**Parameters:**
- `user_google_email` (string, required): User's Google email
- `form_id` (string, required): Form ID
- `published` (boolean, required): Publication status

### `publish_form_publicly`

Publish form publicly with automatic Drive integration for public access.

**Parameters:**
- `user_google_email` (string, required): User's Google email
- `form_id` (string, required): Form ID to publish

**Multi-Service Integration:**
- Uses Forms API for form management
- Uses Drive API for public sharing
- Returns public URL for form access

### `get_form_response`

Retrieve detailed information about a specific form response.

**Parameters:**
- `user_google_email` (string, required): User's Google email
- `form_id` (string, required): Form ID
- `response_id` (string, required): Response ID

**Response:**
- Complete response data
- Answer mappings to questions
- Submission timestamp
- Respondent information (if available)

### `list_form_responses`

List all responses for a form with optional filtering.

**Parameters:**
- `user_google_email` (string, required): User's Google email
- `form_id` (string, required): Form ID
- `filter` (string, optional): Response filter criteria
- `page_size` (integer, optional): Number of responses per page
- `page_token` (string, optional): Pagination token

**Response:**
- Array of response summaries
- Pagination information
- Total response count
- Response statistics

### `update_form_questions`

Modify existing form questions and structure through batch updates.

**Parameters:**
- `user_google_email` (string, required): User's Google email
- `form_id` (string, required): Form ID
- `questions` (array, required): Updated question configurations

**Capabilities:**
- Add new questions
- Modify existing questions
- Remove questions
- Reorder questions
- Update question settings

---

## Authentication & Scopes

Required Google API scopes:
- `https://www.googleapis.com/auth/forms.body`
- `https://www.googleapis.com/auth/forms.body.readonly`
- `https://www.googleapis.com/auth/forms.responses.readonly`
- `https://www.googleapis.com/auth/drive.file` (for public publishing)

## Multi-Service Integration

Google Forms tools integrate seamlessly with other Google services:

**Drive Integration:**
- Automatic public sharing for published forms
- File management for form assets
- Response export to Drive

**Gmail Integration:**
- Automated form distribution via email
- Response notifications
- Form sharing workflows

## Best Practices

1. **Form Structure**: Design clear, logical question flow
2. **Question Types**: Choose appropriate input types for data collection
3. **Response Handling**: Implement proper response processing
4. **Public Publishing**: Use Drive integration for maximum accessibility
5. **Multi-Service Workflows**: Leverage Forms + Drive + Gmail coordination

## Error Handling

Common error scenarios and solutions:

- **Permission Denied**: Ensure proper Google Forms API permissions
- **Form Not Found**: Validate form IDs before operations
- **Invalid Questions**: Use proper question structure validation
- **Publishing Errors**: Check Drive API permissions for public sharing

---

For more information, see:
- [Authentication Guide](../auth/README.md)
- [Multi-Service Integration](../../MULTI_SERVICE_INTEGRATION.md)
- [Main API Reference](../README.md)