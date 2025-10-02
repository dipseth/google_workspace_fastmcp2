# Google Drive API Reference

Complete API documentation for all Google Drive tools in the FastMCP2 platform.

## Available Tools

| Tool Name | Description |
|-----------|-------------|
| [`upload_file_to_drive`](#upload_file_to_drive) | Upload local files to Google Drive |
| [`search_drive_files`](#search_drive_files) | Search for files and folders using query syntax |
| [`get_drive_file_content`](#get_drive_file_content) | Retrieve content of any Drive file |
| [`list_drive_items`](#list_drive_items) | List files and folders in a directory |
| [`create_drive_file`](#create_drive_file) | Create new files directly in Drive |
| [`manage_drive_files`](#manage_drive_files) | Move, copy, rename, or delete files (unified file operations) |
| [`share_drive_files`](#share_drive_files) | Share files with specific users |
| [`make_drive_files_public`](#make_drive_files_public) | Make files publicly accessible |
| [`start_google_auth`](#start_google_auth) | Initiate OAuth authentication |
| [`check_drive_auth`](#check_drive_auth) | Check authentication status |

---

## upload_file_to_drive

Upload a local file to Google Drive with authentication and folder management.

### Parameters

| Parameter | Type | Required | Description | Default |
|-----------|------|----------|-------------|---------|
| `user_google_email` | string | Yes | User's Google email address | - |
| `filepath` | string | Yes | Path to the local file to upload | - |
| `folder_id` | string | No | Google Drive folder ID | `"root"` |
| `filename` | string | No | Custom filename for the uploaded file | Original filename |

### Returns

```json
{
  "file_id": "1234567890abcdef",
  "file_name": "document.pdf",
  "web_view_link": "https://drive.google.com/file/d/1234567890abcdef/view",
  "download_link": "https://drive.google.com/uc?export=download&id=1234567890abcdef",
  "size": "2.5 MB",
  "mime_type": "application/pdf",
  "folder_id": "root",
  "created_time": "2024-01-15T10:30:00Z"
}
```

### Example Usage

```python
result = await upload_file_to_drive(
    user_google_email="user@gmail.com",
    filepath="/home/user/documents/report.pdf",
    folder_id="1ABC2DEF3GHI",
    filename="Q4_Report_2024.pdf"
)
```

### Error Scenarios

- `AUTH_REQUIRED`: User hasn't authenticated or token expired
- `FILE_NOT_FOUND`: Local file doesn't exist
- `FOLDER_NOT_FOUND`: Specified folder_id doesn't exist or not accessible
- `QUOTA_EXCEEDED`: Drive storage quota exceeded
- `FILE_TOO_LARGE`: File exceeds Google Drive size limits

---

## search_drive_files

Search for files and folders in Google Drive using advanced query syntax.

### Parameters

| Parameter | Type | Required | Description | Default |
|-----------|------|----------|-------------|---------|
| `user_google_email` | string | Yes | User's Google email address | - |
| `query` | string | Yes | Google Drive query string (see query syntax below) | - |
| `page_size` | integer | No | Number of results to return (1-100) | 10 |
| `drive_id` | string | No | Specific shared drive ID to search | - |
| `include_items_from_all_drives` | boolean | No | Include shared drive items | true |
| `corpora` | string | No | Corpus to search (`user`, `allDrives`, `domain`) | - |

### Query Syntax Examples

```
# Search by name
name contains 'report'
name = 'Exact Report Name.pdf'

# Search by type
mimeType = 'application/pdf'
mimeType = 'application/vnd.google-apps.folder'

# Search by modification date
modifiedTime > '2024-01-01T00:00:00'
modifiedTime >= '2024-01-01' and modifiedTime <= '2024-12-31'

# Search in specific folder
'folder_id' in parents

# Search for files owned by specific user
'user@example.com' in owners

# Complex queries
name contains 'report' and mimeType = 'application/pdf' and modifiedTime > '2024-01-01'
```

### Returns

```json
{
  "files": [
    {
      "id": "1234567890abcdef",
      "name": "Q4 Report.pdf",
      "mimeType": "application/pdf",
      "size": "2048576",
      "createdTime": "2024-01-10T08:00:00Z",
      "modifiedTime": "2024-01-15T10:30:00Z",
      "webViewLink": "https://drive.google.com/file/d/1234567890abcdef/view",
      "parents": ["folder_id"],
      "owners": [{"emailAddress": "owner@gmail.com", "displayName": "Owner Name"}],
      "shared": false
    }
  ],
  "nextPageToken": "token_for_next_page"
}
```

### Example Usage

```python
# Search for PDF reports modified this year
result = await search_drive_files(
    user_google_email="user@gmail.com",
    query="name contains 'report' and mimeType = 'application/pdf' and modifiedTime > '2024-01-01'",
    page_size=20
)

# Search in a specific folder
result = await search_drive_files(
    user_google_email="user@gmail.com",
    query="'1ABC2DEF3GHI' in parents",
    page_size=50
)
```

---

## get_drive_file_content

Retrieve the content of a Google Drive file, supporting multiple formats including Google Docs, Sheets, Office files, PDFs, and text files.

### Parameters

| Parameter | Type | Required | Description | Default |
|-----------|------|----------|-------------|---------|
| `user_google_email` | string | Yes | User's Google email address | - |
| `file_id` | string | Yes | Google Drive file ID | - |

### Returns

Content format varies by file type:

**Text/Document files:**
```json
{
  "content": "File content as text...",
  "metadata": {
    "name": "document.txt",
    "mimeType": "text/plain",
    "size": "1024",
    "modifiedTime": "2024-01-15T10:30:00Z"
  }
}
```

**Google Docs/Sheets:**
```json
{
  "content": "Exported content as plain text...",
  "format": "text/plain",
  "original_type": "application/vnd.google-apps.document",
  "metadata": {...}
}
```

**Binary files (PDFs, images):**
```json
{
  "content_type": "binary",
  "download_url": "https://drive.google.com/uc?export=download&id=...",
  "web_view_link": "https://drive.google.com/file/d/.../view",
  "metadata": {...}
}
```

### Supported File Types

- **Google Workspace**: Docs, Sheets, Slides, Forms (exported as text/HTML)
- **Microsoft Office**: .docx, .xlsx, .pptx (converted and extracted)
- **Text files**: .txt, .md, .csv, .json, .xml, .yaml
- **PDFs**: Metadata returned with download link
- **Images**: Metadata with view/download links
- **Other**: Binary files return download links

### Example Usage

```python
# Get content of a Google Doc
content = await get_drive_file_content(
    user_google_email="user@gmail.com",
    file_id="1ABC2DEF3GHI4JKL"
)
```

---

## list_drive_items

List files and folders in a Google Drive directory, including shared drives.

### Parameters

| Parameter | Type | Required | Description | Default |
|-----------|------|----------|-------------|---------|
| `user_google_email` | string | Yes | User's Google email address | - |
| `folder_id` | string | No | Folder ID to list contents | `"root"` |
| `page_size` | integer | No | Number of items to return (1-100) | 100 |
| `drive_id` | string | No | Specific shared drive ID | - |
| `include_items_from_all_drives` | boolean | No | Include shared drive items | true |
| `corpora` | string | No | Corpus to search | - |

### Returns

```json
{
  "items": [
    {
      "id": "folder_123",
      "name": "Documents",
      "type": "folder",
      "mimeType": "application/vnd.google-apps.folder",
      "createdTime": "2024-01-01T00:00:00Z",
      "modifiedTime": "2024-01-15T10:30:00Z"
    },
    {
      "id": "file_456",
      "name": "Report.pdf",
      "type": "file",
      "mimeType": "application/pdf",
      "size": "2048576",
      "webViewLink": "https://drive.google.com/file/d/file_456/view"
    }
  ],
  "folder_name": "My Drive",
  "total_items": 25,
  "nextPageToken": "next_page_token"
}
```

### Example Usage

```python
# List root directory
items = await list_drive_items(
    user_google_email="user@gmail.com",
    folder_id="root",
    page_size=50
)

# List specific folder
items = await list_drive_items(
    user_google_email="user@gmail.com",
    folder_id="1ABC2DEF3GHI",
    page_size=100
)
```

---

## create_drive_file

Create a new file in Google Drive from content or URL.

### Parameters

| Parameter | Type | Required | Description | Default |
|-----------|------|----------|-------------|---------|
| `user_google_email` | string | Yes | User's Google email address | - |
| `file_name` | string | Yes | Name for the new file | - |
| `content` | string | No* | Text content for the file | - |
| `folder_id` | string | No | Parent folder ID | `"root"` |
| `mime_type` | string | No | MIME type of the content | `"text/plain"` |
| `fileUrl` | string | No* | URL to download file content from | - |

\* Either `content` or `fileUrl` must be provided

### Returns

```json
{
  "file_id": "1234567890abcdef",
  "name": "new_document.txt",
  "mimeType": "text/plain",
  "webViewLink": "https://drive.google.com/file/d/1234567890abcdef/view",
  "createdTime": "2024-01-15T10:30:00Z",
  "size": "1024"
}
```

### Example Usage

```python
# Create from text content
result = await create_drive_file(
    user_google_email="user@gmail.com",
    file_name="notes.txt",
    content="Meeting notes from today...",
    mime_type="text/plain"
)

# Create from URL
result = await create_drive_file(
    user_google_email="user@gmail.com",
    file_name="downloaded_image.jpg",
    fileUrl="https://example.com/image.jpg",
    mime_type="image/jpeg"
)

# Create Google Doc
result = await create_drive_file(
    user_google_email="user@gmail.com",
    file_name="New Document",
    content="Document content...",
    mime_type="application/vnd.google-apps.document"
)
```

---

## manage_drive_files

Unified tool for Google Drive file management: move, copy, rename, or delete files in a single operation.

### Parameters

| Parameter | Type | Required | Description | Default |
|-----------|------|----------|-------------|---------|
| `user_google_email` | string | Yes | User's Google email address | - |
| `operation` | string | Yes | Operation: `move`, `copy`, `rename`, or `delete` | - |
| `file_ids` | array[string] | Conditional* | List of file IDs to operate on | - |
| `target_folder_id` | string | Conditional** | Target folder ID for move/copy | - |
| `remove_from_all_parents` | boolean | No | Remove file from ALL parent folders (move only) | true |
| `name_prefix` | string | No | Prefix for copied file names (copy only) | `"Copy of "` |
| `new_name` | string | Conditional*** | New filename (rename only) | - |
| `permanent` | boolean | No | Permanently delete vs. move to trash (delete only) | false |

\* Required for all operations
\*\* Required for `move` operation, optional for `copy`
\*\*\* Required for `rename` operation

### Returns

**Move/Copy/Rename Success:**
```json
{
  "operation": "move",
  "success": true,
  "results": [
    {
      "file_id": "1ABC2DEF3GHI",
      "file_name": "document.pdf",
      "status": "success",
      "new_location": "folder_id_123"
    }
  ],
  "summary": {
    "total": 5,
    "successful": 4,
    "failed": 1
  }
}
```

**Delete Success:**
```json
{
  "operation": "delete",
  "success": true,
  "deleted_files": [
    {
      "file_id": "1ABC2DEF3GHI",
      "file_name": "old_document.pdf",
      "permanently_deleted": false
    }
  ],
  "total_deleted": 3
}
```

### Permission Errors

Common permission errors encountered with shared drives:

| Error Code | Description | When It Occurs |
|------------|-------------|----------------|
| `insufficientFilePermissions` | Insufficient permissions to modify file | File owned by another user in shared drive |
| `cannotAddParent` | Cannot add parent folder | File already has multiple parents |
| `teamDrivesParentLimit` | Shared drive parent limit | Shared drive files must have exactly one parent |

**Important:** Most shared drive files cannot be moved by non-owners. These files should remain in their current locations for proper team collaboration.

### Example Usage

```python
# Move files to a new folder (removing from all current locations)
result = await manage_drive_files(
    user_google_email="user@gmail.com",
    operation="move",
    file_ids=["file_id_1", "file_id_2", "file_id_3"],
    target_folder_id="new_folder_id",
    remove_from_all_parents=True
)

# Copy files with custom prefix
result = await manage_drive_files(
    user_google_email="user@gmail.com",
    operation="copy",
    file_ids=["file_id_1"],
    target_folder_id="backup_folder_id",
    name_prefix="Backup - "
)

# Rename a single file
result = await manage_drive_files(
    user_google_email="user@gmail.com",
    operation="rename",
    file_ids=["file_id_1"],
    new_name="Updated Document Name.pdf"
)

# Move to trash (recoverable)
result = await manage_drive_files(
    user_google_email="user@gmail.com",
    operation="delete",
    file_ids=["file_id_1", "file_id_2"],
    permanent=False
)

# Permanently delete files
result = await manage_drive_files(
    user_google_email="user@gmail.com",
    operation="delete",
    file_ids=["file_id_1"],
    permanent=True
)
```

### Real-World Insights

From production use organizing 100+ files:
- ✅ **90% of files** in shared drives have permission restrictions
- ✅ **Only owner-created files** can typically be moved/renamed
- ✅ **Shared drive files** should stay in their current locations for collaboration
- ✅ **Use `remove_from_all_parents=True`** for clean folder reorganization
- ⚠️ **Always handle permission errors gracefully** - they're expected for team files

---

## share_drive_files

Share Google Drive files with specific people via email addresses.

### Parameters

| Parameter | Type | Required | Description | Default |
|-----------|------|----------|-------------|---------|
| `user_google_email` | string | Yes | User's Google email address | - |
| `file_ids` | array[string] | Yes | List of file IDs to share | - |
| `email_addresses` | array[string] | Yes | Email addresses to share with | - |
| `role` | string | No | Permission role (`reader`, `writer`, `commenter`) | `"reader"` |
| `send_notification` | boolean | No | Send email notification | true |
| `message` | string | No | Custom message for notification | - |

### Returns

```json
{
  "shared_files": [
    {
      "file_id": "1234567890abcdef",
      "file_name": "document.pdf",
      "shared_with": ["user1@gmail.com", "user2@gmail.com"],
      "role": "reader",
      "notification_sent": true
    }
  ],
  "errors": []
}
```

### Example Usage

```python
result = await share_drive_files(
    user_google_email="owner@gmail.com",
    file_ids=["file_id_1", "file_id_2"],
    email_addresses=["colleague@gmail.com", "partner@company.com"],
    role="writer",
    send_notification=true,
    message="Please review these documents"
)
```

---

## make_drive_files_public

Make Google Drive files publicly accessible (anyone with the link can view).

### Parameters

| Parameter | Type | Required | Description | Default |
|-----------|------|----------|-------------|---------|
| `user_google_email` | string | Yes | User's Google email address | - |
| `file_ids` | array[string] | Yes | List of file IDs to make public | - |
| `public` | boolean | No | True to make public, false to revoke | true |
| `role` | string | No | Permission role (`reader`, `writer`) | `"reader"` |

### Returns

```json
{
  "updated_files": [
    {
      "file_id": "1234567890abcdef",
      "file_name": "public_document.pdf",
      "is_public": true,
      "public_link": "https://drive.google.com/file/d/1234567890abcdef/view?usp=sharing",
      "role": "reader"
    }
  ],
  "errors": []
}
```

### Example Usage

```python
# Make files public
result = await make_drive_files_public(
    user_google_email="user@gmail.com",
    file_ids=["file_id_1", "file_id_2"],
    public=true,
    role="reader"
)

# Revoke public access
result = await make_drive_files_public(
    user_google_email="user@gmail.com",
    file_ids=["file_id_1"],
    public=false
)
```

---

## start_google_auth

Initiate Google OAuth2 authentication flow for Google services.

### Parameters

| Parameter | Type | Required | Description | Default |
|-----------|------|----------|-------------|---------|
| `user_google_email` | string | Yes | User's Google email address | - |
| `service_name` | string | No | Display name for the service | `"Google Services"` |

### Returns

```json
{
  "auth_url": "https://accounts.google.com/o/oauth2/v2/auth?...",
  "message": "Please visit the URL to complete authentication",
  "session_id": "session_123",
  "expires_in": 600
}
```

### Example Usage

```python
auth_info = await start_google_auth(
    user_google_email="user@gmail.com",
    service_name="Google Drive"
)
# User visits auth_url to complete OAuth flow
```

---

## check_drive_auth

Verify Google Drive authentication status for a specific user account.

### Parameters

| Parameter | Type | Required | Description | Default |
|-----------|------|----------|-------------|---------|
| `user_google_email` | string | Yes | User's Google email address | - |

### Returns

```json
{
  "authenticated": true,
  "user_email": "user@gmail.com",
  "scopes": [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/drive.file"
  ],
  "token_expiry": "2024-01-15T12:30:00Z",
  "quota_info": {
    "storage_used": "5.2 GB",
    "storage_limit": "15 GB",
    "storage_percentage": 34.67
  }
}
```

### Example Usage

```python
status = await check_drive_auth(
    user_google_email="user@gmail.com"
)

if not status["authenticated"]:
    # Need to run start_google_auth
    pass
```

---

## Common Error Codes

| Error Code | Description | Resolution |
|------------|-------------|------------|
| `AUTH_REQUIRED` | User needs to authenticate | Run `start_google_auth` |
| `TOKEN_EXPIRED` | OAuth token has expired | Automatic refresh attempted, may need re-auth |
| `PERMISSION_DENIED` | Insufficient permissions for operation | Check file ownership/sharing settings |
| `insufficientFilePermissions` | Cannot modify file (shared drive) | File owned by another user - leave in current location |
| `cannotAddParent` | Cannot add parent folder | File has multiple parents or is in shared drive |
| `teamDrivesParentLimit` | Shared drive parent limit exceeded | Shared drive files must have exactly one parent |
| `NOT_FOUND` | File or folder not found | Verify ID exists and is accessible |
| `QUOTA_EXCEEDED` | API quota or storage limit exceeded | Wait for quota reset or upgrade storage |
| `INVALID_PARAMETER` | Invalid parameter value | Check parameter format and requirements |
| `RATE_LIMITED` | Too many requests | Wait before retrying |

## Best Practices

### Authentication & Authorization
1. **Authentication**: Always check auth status before operations using `check_drive_auth`
2. **Permissions**: Be aware that 90%+ of shared drive files have permission restrictions
3. **Ownership**: Only file owners can typically move, rename, or delete files in shared drives

### File Operations
4. **Batch Operations**: Use `share_drive_files` and `manage_drive_files` for multiple files instead of individual calls
5. **Move vs Copy**: Use `remove_from_all_parents=True` when moving files to avoid duplicate parent relationships
6. **Permission Errors**: Always handle `insufficientFilePermissions`, `cannotAddParent`, and `teamDrivesParentLimit` errors gracefully
7. **Shared Drive Files**: Keep team collaboration files in their current shared drive locations - moving them can break workflows

### Search & Organization
8. **Query Optimization**: Use specific queries to reduce API calls and improve search accuracy
9. **Free-text Search**: For year-based searches (e.g., "2025"), free-text queries often work better than structured date queries
10. **File Verification**: Use `get_drive_file_content` to verify file categorization before bulk operations
11. **Test First**: Always test file operations with a small subset before bulk processing

### API Efficiency
12. **Error Handling**: Implement retry logic for transient errors with exponential backoff
13. **Pagination**: Handle `nextPageToken` for large result sets (100+ files)
14. **MIME Types**: Use Google MIME types for native Google Workspace files
15. **Rate Limiting**: Tools handle rate limiting automatically, but be mindful of quota limits

### Real-World Lessons
16. **Organization Strategy**: Focus on personally-owned files; shared drive files are already organized by teams
17. **Documentation**: Create summary documents to track file organization and decisions
18. **Incremental Approach**: Process files in batches and verify results before proceeding
19. **Permission Awareness**: ~90% of modern workplace files are in shared drives with restricted permissions

## Rate Limits

Google Drive API has the following limits:
- **Queries per day**: 1,000,000,000
- **Queries per 100 seconds per user**: 1,000
- **Queries per 100 seconds**: 10,000

Tools automatically handle rate limiting with exponential backoff.

---

For more information, see the [main API documentation](../README.md) or [Google Drive API documentation](https://developers.google.com/drive/api/v3/reference).