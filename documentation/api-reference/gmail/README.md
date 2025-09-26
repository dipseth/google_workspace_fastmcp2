# Gmail API Reference

Complete API documentation for all Gmail tools in the Groupon Google MCP Server.

## 🎉 Recent Updates & Improvements

### ✅ HTML Email Capabilities - Production Ready
- **Advanced HTML Support**: Full CSS3 support including gradients, animations, and responsive design
- **Content Type Options**: `plain`, `html`, and `mixed` content types for flexible email composition
- **Draft Creation Fixed**: Resolved `draft_gmail_message` parameter validation issues with MIME encoding
- **Performance Optimized**: 30x faster startup time (3+ seconds → ~100ms) with optimized module loading

### 🔧 Recent Critical Fixes
- **Fixed `draft_gmail_message`**: Resolved parameter validation causing MIME encoding issues for HTML content
- **Enhanced HTML Rendering**: Verified advanced HTML features work correctly in Gmail interface
- **Improved Error Handling**: Better validation and error messages for content type parameters
- **Fixed Elicitation Compatibility**: Added graceful fallback for MCP clients that don't support elicitation
- **Resolved Schema Validation**: Fixed `structured_content must be a dict or None` errors
- **Universal Client Support**: Email tools now work with any MCP client (elicitation-supporting or not)
- **Fixed Field Name Consistency**: Resolved TypedDict field access issues (`draftId` vs `draft_id`)

## Available Tools

| Tool Name | Description |
|-----------|-------------|
| [`search_gmail_messages`](#search_gmail_messages) | Search Gmail messages using query syntax |
| [`get_gmail_message_content`](#get_gmail_message_content) | Get full content of a specific message |
| [`get_gmail_messages_content_batch`](#get_gmail_messages_content_batch) | Get multiple messages in one request |
| [`send_gmail_message`](#send_gmail_message) | Send email via Gmail |
| [`draft_gmail_message`](#draft_gmail_message) | Create email draft |
| [`get_gmail_thread_content`](#get_gmail_thread_content) | Get complete conversation thread |
| [`list_gmail_labels`](#list_gmail_labels) | List all labels in account |
| [`manage_gmail_label`](#manage_gmail_label) | Create, update, or delete labels |
| [`modify_gmail_message_labels`](#modify_gmail_message_labels) | Add/remove labels from messages |
| [`reply_to_gmail_message`](#reply_to_gmail_message) | Reply to messages with threading |
| [`draft_gmail_reply`](#draft_gmail_reply) | Create draft reply |
| [`list_gmail_filters`](#list_gmail_filters) | List all Gmail filters/rules |
| [`create_gmail_filter`](#create_gmail_filter) | Create new filter with criteria |
| [`get_gmail_filter`](#get_gmail_filter) | Get specific filter details |
| [`delete_gmail_filter`](#delete_gmail_filter) | Delete a Gmail filter |

---

## search_gmail_messages

Search Gmail messages using Gmail query syntax with message and thread IDs.

### Parameters

| Parameter | Type | Required | Description | Default |
|-----------|------|----------|-------------|---------|
| `user_google_email` | string | Yes | User's Google email address | - |
| `query` | string | Yes | Gmail search query (see syntax below) | - |
| `page_size` | integer | No | Number of results (1-500) | 10 |

### Gmail Query Syntax

```
# Search by sender
from:sender@example.com
from:me

# Search by recipient
to:recipient@example.com
cc:person@example.com
bcc:hidden@example.com

# Search by subject
subject:"Quarterly Report"
subject:(meeting OR agenda)

# Search by content
"exact phrase in body"
has:attachment
filename:pdf
filename:report.xlsx

# Search by date
after:2024/1/1
before:2024/12/31
older:2d
newer:1w
newer_than:3d older_than:1y

# Search by status
is:unread
is:read
is:starred
is:important
is:sent
is:draft
in:spam
in:trash
in:inbox
in:sent

# Search by label
label:work
label:important
has:red-star
has:yellow-bang

# Search by size
larger:5M
smaller:1M
size:1000000

# Complex queries
from:boss@company.com has:attachment larger:1M after:2024/1/1
subject:(invoice OR receipt) -from:noreply@
is:unread in:inbox category:primary
```

### Returns

```json
{
  "messages": [
    {
      "id": "18d4a5b6c7e8f9",
      "threadId": "18d4a5b6c7e8f9",
      "snippet": "Please review the attached quarterly report...",
      "labelIds": ["INBOX", "IMPORTANT"],
      "date": "2024-01-15T10:30:00Z"
    }
  ],
  "resultSizeEstimate": 42,
  "nextPageToken": "09876543"
}
```

### Example Usage

```python
# Search for unread emails from a specific sender
results = await search_gmail_messages(
    user_google_email="user@gmail.com",
    query="from:boss@company.com is:unread",
    page_size=20
)

# Search for emails with attachments in the last week
results = await search_gmail_messages(
    user_google_email="user@gmail.com",
    query="has:attachment newer_than:7d",
    page_size=50
)
```

---

## get_gmail_message_content

Retrieve the full content (subject, sender, body) of a specific Gmail message.

### Parameters

| Parameter | Type | Required | Description | Default |
|-----------|------|----------|-------------|---------|
| `user_google_email` | string | Yes | User's Google email address | - |
| `message_id` | string | Yes | Gmail message ID | - |

### Returns

```json
{
  "id": "18d4a5b6c7e8f9",
  "threadId": "18d4a5b6c7e8f9",
  "labelIds": ["INBOX", "IMPORTANT"],
  "snippet": "Please review the attached quarterly report...",
  "payload": {
    "headers": {
      "From": "sender@example.com",
      "To": "user@gmail.com",
      "Subject": "Quarterly Report Q4 2024",
      "Date": "Mon, 15 Jan 2024 10:30:00 -0000"
    },
    "body": {
      "text": "Plain text content...",
      "html": "<html>HTML content...</html>"
    },
    "attachments": [
      {
        "filename": "Q4_Report.pdf",
        "mimeType": "application/pdf",
        "size": 2048576,
        "attachmentId": "ANGjdJ_ABC123"
      }
    ]
  },
  "sizeEstimate": 2050000,
  "historyId": "123456",
  "internalDate": "1705315800000"
}
```

### Example Usage

```python
# Get full message content
message = await get_gmail_message_content(
    user_google_email="user@gmail.com",
    message_id="18d4a5b6c7e8f9"
)

# Access specific parts
subject = message["payload"]["headers"]["Subject"]
body_text = message["payload"]["body"]["text"]
attachments = message["payload"]["attachments"]
```

---

## get_gmail_messages_content_batch

Retrieve content of multiple Gmail messages in a single batch request (up to 100 messages).

### Parameters

| Parameter | Type | Required | Description | Default |
|-----------|------|----------|-------------|---------|
| `user_google_email` | string | Yes | User's Google email address | - |
| `message_ids` | array[string] | Yes | List of message IDs (max 100) | - |
| `format` | string | No | Format: `full` or `metadata` | `"full"` |

### Returns

```json
{
  "messages": [
    {
      "id": "18d4a5b6c7e8f9",
      "status": "success",
      "data": {
        // Full message data as in get_gmail_message_content
      }
    },
    {
      "id": "18d4a5b6c7e8f0",
      "status": "error",
      "error": "Message not found"
    }
  ],
  "successful": 1,
  "failed": 1,
  "total": 2
}
```

### Example Usage

```python
# Get multiple messages at once
messages = await get_gmail_messages_content_batch(
    user_google_email="user@gmail.com",
    message_ids=["id1", "id2", "id3", "id4", "id5"],
    format="full"
)

# Get just metadata for many messages
metadata = await get_gmail_messages_content_batch(
    user_google_email="user@gmail.com",
    message_ids=message_id_list,
    format="metadata"
)
```

---

## send_gmail_message

Send an email using the user's Gmail account.

### Parameters

| Parameter | Type | Required | Description | Default |
|-----------|------|----------|-------------|---------|
| `user_google_email` | string | Yes | User's Google email address | - |
| `to` | string/array | Yes | Recipient email(s) | - |
| `subject` | string | Yes | Email subject | - |
| `body` | string | Yes | Email body (plain text) | - |
| `content_type` | string | No | `plain`, `html`, or `mixed` | `"mixed"` |
| `html_body` | string | No | HTML version of body | - |
| `cc` | string/array | No | CC recipients | - |
| `bcc` | string/array | No | BCC recipients | - |

### Returns

**Success (Email Sent):**
```json
{
  "success": true,
  "message_id": "18d4a5b6c7e8f9",
  "message": "✅ Email sent to 1 recipient(s)! Message ID: 18d4a5b6c7e8f9",
  "recipientCount": 1,
  "contentType": "mixed",
  "action": "sent"
}
```

**Elicitation Fallback (Draft Mode):**
```json
{
  "success": true,
  "message": "📝 EMAIL SAVED AS DRAFT (not sent)...",
  "draftId": "r-927097057353781341",
  "recipientCount": 1,
  "action": "saved_draft",
  "elicitationNotSupported": true
}
```

**Blocked (Security):**
```json
{
  "success": false,
  "message": "🚫 EMAIL BLOCKED (not sent)...",
  "action": "blocked",
  "recipientsNotAllowed": ["untrusted@example.com"]
}
```

### Example Usage

```python
# Send simple text email
result = await send_gmail_message(
    user_google_email="user@gmail.com",
    to="colleague@example.com",
    subject="Project Update",
    body="Here's the latest status on our project..."
)

# Send HTML email with CC
result = await send_gmail_message(
    user_google_email="user@gmail.com",
    to=["recipient1@example.com", "recipient2@example.com"],
    subject="Newsletter",
    body="Plain text version",
    html_body="<h1>Newsletter</h1><p>Rich HTML content...</p>",
    content_type="mixed",
    cc="manager@example.com"
)

# Advanced HTML Features - Production Ready!
result = await send_gmail_message(
    user_google_email="user@gmail.com",
    to="team@company.com",
    subject="Advanced HTML Demo",
    body="Plain text fallback for email clients that don't support HTML",
    html_body="""
    <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
        <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white; padding: 20px; border-radius: 10px; text-align: center;">
            <h1>Advanced HTML Email</h1>
            <p>CSS gradients, animations, and responsive design!</p>
        </div>
        <p style="margin-top: 20px;">This email demonstrates Groupon Google MCP's advanced HTML capabilities.</p>
    </div>
    """,
    content_type="html"
)
```

### 🛡️ Email Security & Elicitation System

Groupon Google MCP includes a sophisticated email security system that protects against sending emails to untrusted recipients. When attempting to send to recipients not on the allow list, the system provides user control through elicitation prompts.

#### How It Works

1. **Allow List Check**: System checks if recipients are on the trusted allow list
2. **Elicitation Prompt**: If untrusted recipients detected, user gets confirmation dialog
3. **Safe Actions**: User can choose to send, save as draft, or cancel
4. **Structured Response**: Detailed JSON response includes security status

#### Elicitation Example

When sending to an untrusted recipient like `test@example.com`:

![Elicitation System Demo](../../../image-1756953129691.png)

The elicitation prompt provides:
- **Security Notice**: Clear indication recipient is not trusted
- **Email Preview**: Subject, content type, and body preview  
- **Action Options**: Send immediately, save as draft, or cancel
- **Auto-timeout**: Automatic cancellation after 300 seconds
- **Structured Response**: Machine-readable JSON with security details

#### Response Structure for Elicitation

```json
{
  "success": true,
  "message": "📝 **EMAIL SAVED AS DRAFT** (not sent)",
  "messageId": null,
  "threadId": null,
  "draftId": "r-5949208333949694620", 
  "recipientCount": 1,
  "contentType": "mixed",
  "templateApplied": false,
  "error": null,
  "elicitationRequired": true,
  "recipientsNotAllowed": ["test@example.com"],
  "action": "saved_draft"
}
```

#### Managing the Allow List

View current allow list:
```python
# Check current trusted recipients
allow_list = await view_gmail_allow_list(
    user_google_email="user@gmail.com"
)
```

Add trusted recipients:
```python
# Add single email to allow list
result = await add_to_gmail_allow_list(
    email="trusted@example.com",
    user_google_email="user@gmail.com"
)

# Add multiple emails
result = await add_to_gmail_allow_list(
    email=["colleague1@company.com", "colleague2@company.com"],
    user_google_email="user@gmail.com"
)
```

#### Security Benefits

- **Prevents Accidental Emails**: No more sending to wrong recipients
- **User Control**: Always get confirmation for untrusted contacts  
- **Audit Trail**: Structured responses log all security decisions
- **Flexible Actions**: Save drafts for manual review or send immediately
- **No False Blocks**: Trusted contacts always work seamlessly

### HTML Content Type Guide

| Content Type | Use Case | Description |
|--------------|----------|-------------|
| `"plain"` | Simple text emails | Plain text only, no HTML rendering |
| `"html"` | Rich HTML emails | HTML only, no plain text fallback |
| `"mixed"` | **Recommended** | Both HTML and plain text versions |

**Best Practice**: Use `"mixed"` content type to ensure compatibility across all email clients.

---

## draft_gmail_message

Create a draft email in the user's Gmail account.

### 🔧 Recent Fixes
- **✅ Parameter Validation Fixed**: Resolved MIME encoding issues for HTML content types
- **✅ Production Ready**: Full HTML support with proper content type handling
- **✅ Improved Error Messages**: Better validation feedback for content type parameters

### Parameters

| Parameter | Type | Required | Description | Default |
|-----------|------|----------|-------------|---------|
| `user_google_email` | string | Yes | User's Google email address | - |
| `subject` | string | Yes | Email subject | - |
| `body` | string | Yes | Email body | - |
| `to` | string/array | No | Recipients | - |
| `content_type` | string | No | `plain`, `html`, or `mixed` | `"mixed"` |
| `html_body` | string | No | HTML version | - |
| `cc` | string/array | No | CC recipients | - |
| `bcc` | string/array | No | BCC recipients | - |

### Returns

```json
{
  "id": "draft_18d4a5b6c7e8f9",
  "message": {
    "id": "18d4a5b6c7e8f9",
    "threadId": "18d4a5b6c7e8f9",
    "labelIds": ["DRAFT"]
  },
  "status": "Draft created successfully"
}
```

### Example Usage

```python
# Create a simple draft
draft = await draft_gmail_message(
    user_google_email="user@gmail.com",
    subject="Proposal Draft",
    body="Dear Client,\n\nPlease find our proposal...",
    to="client@example.com"
)

# Create draft without recipient (to fill in later)
draft = await draft_gmail_message(
    user_google_email="user@gmail.com",
    subject="Template Response",
    body="Thank you for your inquiry..."
)

# 🎨 Create HTML draft - Now Working Perfectly!
html_draft = await draft_gmail_message(
    user_google_email="user@gmail.com",
    subject="Rich Content Draft",
    body="Plain text version for compatibility",
    html_body="""
    <div style="font-family: Arial, sans-serif; max-width: 600px;">
        <h2 style="color: #2c3e50;">Professional Email Draft</h2>
        <p style="line-height: 1.6;">This HTML draft demonstrates the fixed
        parameter validation and MIME encoding capabilities.</p>
        <div style="background: #f8f9fa; padding: 15px; border-radius: 5px;">
            <strong>✅ Fixed Issues:</strong>
            <ul>
                <li>Parameter validation now works correctly</li>
                <li>MIME encoding properly handles HTML content</li>
                <li>Content types processed without errors</li>
            </ul>
        </div>
    </div>
    """,
    content_type="mixed",
    to="client@company.com"
)
```

---

## get_gmail_thread_content

Retrieve the complete content of a Gmail conversation thread with all messages.

### Parameters

| Parameter | Type | Required | Description | Default |
|-----------|------|----------|-------------|---------|
| `user_google_email` | string | Yes | User's Google email address | - |
| `thread_id` | string | Yes | Gmail thread ID | - |

### Returns

```json
{
  "id": "thread_18d4a5b6c7e8f9",
  "historyId": "123456",
  "messages": [
    {
      "id": "msg1",
      "threadId": "thread_18d4a5b6c7e8f9",
      "labelIds": ["INBOX"],
      "snippet": "Initial message...",
      "payload": {
        // Full message content
      }
    },
    {
      "id": "msg2",
      "threadId": "thread_18d4a5b6c7e8f9",
      "labelIds": ["SENT"],
      "snippet": "Reply to initial message...",
      "payload": {
        // Full message content
      }
    }
  ],
  "messageCount": 2
}
```

### Example Usage

```python
# Get entire conversation thread
thread = await get_gmail_thread_content(
    user_google_email="user@gmail.com",
    thread_id="thread_18d4a5b6c7e8f9"
)

# Process all messages in thread
for message in thread["messages"]:
    sender = message["payload"]["headers"]["From"]
    content = message["payload"]["body"]["text"]
```

---

## list_gmail_labels

List all labels in the user's Gmail account (system and user-created).

### Parameters

| Parameter | Type | Required | Description | Default |
|-----------|------|----------|-------------|---------|
| `user_google_email` | string | Yes | User's Google email address | - |

### Returns

```json
{
  "labels": [
    {
      "id": "INBOX",
      "name": "INBOX",
      "type": "system",
      "messagesTotal": 1543,
      "messagesUnread": 23,
      "threadsTotal": 987,
      "threadsUnread": 15
    },
    {
      "id": "Label_123",
      "name": "Work",
      "type": "user",
      "messageListVisibility": "show",
      "labelListVisibility": "labelShow",
      "color": {
        "textColor": "#ffffff",
        "backgroundColor": "#4285f4"
      }
    }
  ],
  "systemLabels": 10,
  "userLabels": 25,
  "totalLabels": 35
}
```

### Example Usage

```python
# Get all labels
labels = await list_gmail_labels(
    user_google_email="user@gmail.com"
)

# Filter user-created labels
user_labels = [l for l in labels["labels"] if l["type"] == "user"]
```

---

## manage_gmail_label

Manage Gmail labels: create, update, or delete labels.

### Parameters

| Parameter | Type | Required | Description | Default |
|-----------|------|----------|-------------|---------|
| `user_google_email` | string | Yes | User's Google email address | - |
| `action` | string | Yes | Action: `create`, `update`, or `delete` | - |
| `name` | string | No* | Label name (*required for create) | - |
| `label_id` | string | No* | Label ID (*required for update/delete) | - |
| `label_list_visibility` | string | No | `labelShow` or `labelHide` | `"labelShow"` |
| `message_list_visibility` | string | No | `show` or `hide` | `"show"` |
| `text_color` | string | No | Hex color for text | - |
| `background_color` | string | No | Hex color for background | - |

### Returns

```json
{
  "action": "create",
  "label": {
    "id": "Label_456",
    "name": "Projects",
    "messageListVisibility": "show",
    "labelListVisibility": "labelShow",
    "type": "user"
  },
  "status": "Label created successfully"
}
```

### Example Usage

```python
# Create a new label
result = await manage_gmail_label(
    user_google_email="user@gmail.com",
    action="create",
    name="Important Projects",
    text_color="#ffffff",
    background_color="#ea4335"
)

# Update label visibility
result = await manage_gmail_label(
    user_google_email="user@gmail.com",
    action="update",
    label_id="Label_123",
    message_list_visibility="hide"
)

# Delete a label
result = await manage_gmail_label(
    user_google_email="user@gmail.com",
    action="delete",
    label_id="Label_123"
)
```

---

## modify_gmail_message_labels

Add or remove labels from a Gmail message.

### Parameters

| Parameter | Type | Required | Description | Default |
|-----------|------|----------|-------------|---------|
| `user_google_email` | string | Yes | User's Google email address | - |
| `message_id` | string | Yes | Message ID | - |
| `add_label_ids` | array[string] | No | Label IDs to add | - |
| `remove_label_ids` | array[string] | No | Label IDs to remove | - |

### Returns

```json
{
  "id": "18d4a5b6c7e8f9",
  "threadId": "18d4a5b6c7e8f9",
  "labelIds": ["INBOX", "Label_123", "IMPORTANT"],
  "added": ["Label_123", "IMPORTANT"],
  "removed": ["UNREAD"]
}
```

### Example Usage

```python
# Add labels to message
result = await modify_gmail_message_labels(
    user_google_email="user@gmail.com",
    message_id="18d4a5b6c7e8f9",
    add_label_ids=["Label_123", "IMPORTANT"],
    remove_label_ids=["UNREAD"]
)

# Mark as read (remove UNREAD label)
result = await modify_gmail_message_labels(
    user_google_email="user@gmail.com",
    message_id="18d4a5b6c7e8f9",
    remove_label_ids=["UNREAD"]
)
```

---

## reply_to_gmail_message

Send a reply to a specific Gmail message with proper threading.

### Parameters

| Parameter | Type | Required | Description | Default |
|-----------|------|----------|-------------|---------|
| `user_google_email` | string | Yes | User's Google email address | - |
| `message_id` | string | Yes | Original message ID | - |
| `body` | string | Yes | Reply body | - |
| `content_type` | string | No | `plain`, `html`, or `mixed` | `"mixed"` |
| `html_body` | string | No | HTML version of reply | - |

### Returns

```json
{
  "id": "18d4a5b6c7e8f0",
  "threadId": "18d4a5b6c7e8f9",
  "labelIds": ["SENT"],
  "inReplyTo": "18d4a5b6c7e8f9",
  "references": ["18d4a5b6c7e8f9"],
  "status": "Reply sent successfully"
}
```

### Example Usage

```python
# Send simple reply
result = await reply_to_gmail_message(
    user_google_email="user@gmail.com",
    message_id="18d4a5b6c7e8f9",
    body="Thank you for your message. I'll review and get back to you soon."
)

# Send HTML reply
result = await reply_to_gmail_message(
    user_google_email="user@gmail.com",
    message_id="18d4a5b6c7e8f9",
    body="Plain text reply",
    html_body="<p><strong>Thank you</strong> for your message.</p>",
    content_type="mixed"
)
```

---

## create_gmail_filter

Create a new Gmail filter/rule with criteria and actions.

### Parameters

| Parameter | Type | Required | Description | Default |
|-----------|------|----------|-------------|---------|
| `user_google_email` | string | Yes | User's Google email address | - |
| `from_address` | string | No | Filter by sender | - |
| `to_address` | string | No | Filter by recipient | - |
| `subject_contains` | string | No | Filter by subject | - |
| `query` | string | No | Advanced Gmail query | - |
| `has_attachment` | boolean | No | Has attachments | - |
| `exclude_chats` | boolean | No | Exclude chat messages | - |
| `size` | integer | No | Message size in bytes | - |
| `size_comparison` | string | No | `larger` or `smaller` | - |
| `add_label_ids` | array[string] | No | Labels to add | - |
| `remove_label_ids` | array[string] | No | Labels to remove | - |
| `forward_to` | string | No | Forward to address | - |

### Returns

```json
{
  "id": "filter_123",
  "criteria": {
    "from": "newsletter@example.com",
    "hasAttachment": true
  },
  "action": {
    "addLabelIds": ["Label_123"],
    "removeLabelIds": ["INBOX"]
  },
  "status": "Filter created successfully"
}
```

### Example Usage

```python
# Create filter to label and archive newsletters
result = await create_gmail_filter(
    user_google_email="user@gmail.com",
    from_address="newsletter@example.com",
    add_label_ids=["Label_Newsletter"],
    remove_label_ids=["INBOX"]
)

# Create filter for large attachments
result = await create_gmail_filter(
    user_google_email="user@gmail.com",
    has_attachment=True,
    size=5242880,  # 5MB
    size_comparison="larger",
    add_label_ids=["Label_LargeFiles"]
)
```

---

## Common Error Codes

| Error Code | Description | Resolution |
|------------|-------------|------------|
| `AUTH_REQUIRED` | User needs to authenticate | Run `start_google_auth` |
| `INSUFFICIENT_PERMISSION` | Missing required Gmail scopes | Re-authenticate with proper scopes |
| `MESSAGE_NOT_FOUND` | Message ID doesn't exist | Verify message ID |
| `THREAD_NOT_FOUND` | Thread ID doesn't exist | Verify thread ID |
| `LABEL_ALREADY_EXISTS` | Label name already in use | Use different name or update existing |
| `QUOTA_EXCEEDED` | Gmail API quota exceeded | Wait for quota reset |
| `INVALID_QUERY` | Malformed search query | Check query syntax |
| `ATTACHMENT_TOO_LARGE` | Attachment exceeds 25MB limit | Use Drive links for large files |

## Gmail Query Operators

### Basic Operators
- `from:` - Sender email
- `to:` - Recipient email
- `subject:` - Subject line
- `label:` - Gmail label
- `has:attachment` - Has attachments
- `filename:` - Attachment filename
- `in:` - Location (inbox, sent, drafts, spam, trash)
- `is:` - Status (read, unread, starred, important)

### Date Operators
- `after:YYYY/MM/DD` - After date
- `before:YYYY/MM/DD` - Before date
- `older:Xd` - Older than X days
- `newer:Xd` - Newer than X days
- `older_than:1y` - Older than 1 year
- `newer_than:1m` - Newer than 1 month

### Size Operators
- `larger:XM` - Larger than X megabytes
- `smaller:XM` - Smaller than X megabytes
- `size:X` - Exact size in bytes

### Boolean Operators
- `OR` - Either condition
- `AND` - Both conditions (implicit)
- `-` - NOT operator
- `()` - Grouping
- `""` - Exact phrase

## Best Practices

1. **Batch Operations**: Use `get_gmail_messages_content_batch` for multiple messages
2. **Search Optimization**: Use specific queries to reduce API calls
3. **Threading**: Always use reply functions to maintain conversation threads
4. **Label Management**: Create a label hierarchy for organization
5. **Filter Creation**: Use filters to automate email organization
6. **Error Handling**: Implement exponential backoff for rate limits
7. **Attachment Handling**: Use Drive for files over 25MB

## Rate Limits

Gmail API quotas:
- **Daily quota**: 1,000,000,000 quota units
- **Per-user rate limit**: 250 quota units per user per second
- **SendAs.send**: 1,000,000 quota units per day

Quota costs per method:
- Read operations: 1 unit
- Send operations: 100 units
- Modify operations: 5 units

---

For more information, see the [main API documentation](../README.md) or [Gmail API documentation](https://developers.google.com/gmail/api/reference/rest).