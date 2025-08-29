# Google Service Configuration Resource Metadata in FastMCP

This document outlines the standardized metadata structure for Google service configuration resources within the FastMCP framework. This metadata enhances discoverability, filtering, and seamless integration with other FastMCP components.

## 1. Overview

Google service configuration resources provide a centralized, discoverable source of truth for details about various Google APIs, such as required OAuth scopes, API versions, base URLs, and supported features. By exposing this information as MCP resources, FastMCP can dynamically adapt to service requirements and simplify tool development.

## 2. URI Template Patterns

The following URI patterns are used to access Google service configuration resources:

-   `google://services/{service_type}/config`
    -   **Description**: Provides comprehensive configuration details for a specific Google API service.
    -   **Example**: `google://services/gmail/config`
-   `google://services/{service_type}/scopes/{scope_group}`
    -   **Description**: Lists specific OAuth scopes required for a Google API service, categorized by group (e.g., 'read', 'write', 'full').
    -   **Example**: `google://services/drive/scopes/full`
-   `google://services/{service_type}/versions`
    -   **Description**: Lists available API versions for a specific Google service.
    -   **Example**: `google://services/sheets/versions`
-   `google://services/{service_type}/quota`
    -   **Description**: Provides information about API quota limits for a specific Google service.
    -   **Example**: `google://services/calendar/quota`
-   `google://services/{service_type}/endpoints`
    -   **Description**: Lists base API endpoints for a specific Google service.
    -   **Example**: `google://services/docs/endpoints`

## 3. Core Metadata Fields (Standard FastMCP)

All Google service configuration resources adhere to the standard FastMCP resource metadata fields:

-   **`uri`**: The unique resource identifier, often including template parameters.
-   **`name`**: A human-readable name for the resource (e.g., "Gmail Service Configuration").
-   **`description`**: A detailed explanation of what the resource provides, aiding discoverability.
-   **`mime_type`**: Always `application/json` for these configuration resources.
-   **`tags`**: A set of strings for categorization and filtering.

## 4. Google-Specific Metadata Extensions

Beyond the core fields, each `google://services/{service_type}/config` resource includes a `configuration` and `metadata` object with Google-specific attributes:

```json
{
  "service": "gmail",
  "configuration": {
    "api_name": "gmail",
    "api_version": "v1",
    "base_url": "https://gmail.googleapis.com",
    "discovery_url": "https://gmail.googleapis.com/$discovery/rest?version=v1",
    "scopes": {
      "read": ["https://www.googleapis.com/auth/gmail.readonly"],
      "write": ["https://www.googleapis.com/auth/gmail.send"],
      "full": ["https://mail.google.com/"]
    },
    "features": {
      "batch_requests": true,
      "watch_notifications": true,
      "delegation": false
    },
    "limits": {
      "requests_per_minute": 1000,
      "requests_per_day": 1000000,
      "attachment_size_mb": 25
    }
  },
  "metadata": {
    "last_updated": "2025-07-11T00:00:00Z",
    "documentation_url": "https://developers.google.com/gmail/api",
    "authentication_required": true,
    "tags": ["google", "gmail", "email", "communication", "oauth2", "stable", "batch-support"],
    "deprecated_after": "2026-01-01",
    "requires_domain_admin": false
  }
}
```

### Key Attributes:

-   **`service` (string)**: The canonical name of the Google service (e.g., "gmail", "drive").
-   **`configuration` (object)**:
    -   **`api_name` (string)**: The official API name used by `googleapiclient.discovery.build`.
    -   **`api_version` (string)**: The default or recommended API version.
    -   **`base_url` (string, uri format)**: The base URL for the service's API.
    -   **`discovery_url` (string, uri format)**: URL to the API's discovery document.
    -   **`scopes` (object)**: Categorized OAuth scopes. Keys are scope groups (e.g., `read`, `write`, `full`), values are arrays of full OAuth scope URIs.
    -   **`features` (object)**: Boolean flags indicating supported features (e.g., `batch_requests`, `watch_notifications`, `delegation`).
    -   **`limits` (object)**: API quota limits and other operational limits (e.g., `requests_per_minute`, `attachment_size_mb`).
-   **`metadata` (object)**:
    -   **`last_updated` (string, date-time format)**: Timestamp of the last update to this configuration.
    -   **`documentation_url` (string, uri format)**: URL to the official Google API documentation.
    -   **`authentication_required` (boolean)**: Indicates if authentication is required.
    -   **`tags` (array of strings)**: Inherited and extended tags for the specific service.
    -   **`deprecated_after` (string, date format, optional)**: Date after which the service version is deprecated.
    -   **`requires_domain_admin` (boolean, optional)**: Indicates if the service requires domain-wide administration privileges.

## 5. Tagging Taxonomy

The `tags` field supports a structured taxonomy for better discoverability and filtering:

-   **Service Category**: `workspace`, `communication`, `storage`, `productivity`, `collaboration`
-   **Authentication**: `oauth2`, `service-account`, `api-key`
-   **Access Level**: `read`, `write`, `admin`, `metadata`
-   **Feature Tags**: `batch-support`, `realtime`, `webhooks`, `versioned`
-   **Status**: `stable`, `beta`, `deprecated`, `experimental`

## 6. Integration Points

The new resource metadata system integrates with key FastMCP components:

-   **Authentication Middleware (`auth/middleware.py`)**:
    -   Dynamically fetches required scopes based on tool tags by reading `google://services/{service_type}/scopes/{scope_group}` resources.
    -   Uses the `service_resources_mcp` instance to retrieve tool metadata and service configurations.
-   **Service Manager (`auth/service_manager.py`)**:
    -   Replaces hardcoded service configurations with dynamic lookups from `google://services/{service_type}/config` resources.
    -   Uses the `service_resources_mcp` instance to fetch service details for building API clients.
    -   `get_available_services()` and `get_available_scope_groups()` now dynamically list available services and scopes by querying the resource system.
-   **Tool Discovery**: Tools can query these resources to understand available services, their capabilities, and required permissions.
-   **Client Applications**: Can use the FastMCP client to `read_resource` and retrieve service configurations, enabling dynamic UI generation or feature adaptation.

## 7. Validation

All generated service configuration resources are validated against the `fastmcp2_drive_upload/schemas/google_service_config_schema.json` JSON schema. This ensures data consistency and adherence to the defined structure. Any resource response that fails validation will raise a `ValidationError`.

## 8. Usage Example (Python Client)

```python
import asyncio
from fastmcp import Client

async def get_gmail_config():
    client = Client("http://localhost:8002/mcp/") # Assuming FastMCP server is running
    async with client:
        try:
            gmail_config = await client.read_resource("google://services/gmail/config")
            print("Gmail Service Configuration:")
            print(json.dumps(gmail_config, indent=2))

            gmail_full_scopes = await client.read_resource("google://services/gmail/scopes/full")
            print("\nGmail Full Scopes:")
            print(json.dumps(gmail_full_scopes, indent=2))

        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(get_gmail_config())