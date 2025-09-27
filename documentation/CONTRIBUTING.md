# Contributing to Groupon Google MCP Server

Welcome to the Groupon Google MCP Server! We're excited you're interested in contributing to this comprehensive Google service integration platform. This guide provides everything you need to get started.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Environment Setup](#development-environment-setup)
- [Project Structure](#project-structure)
- [How to Add New Services](#how-to-add-new-services)
- [How to Add New Tools](#how-to-add-new-tools)
- [Testing Requirements](#testing-requirements)
- [Code Standards](#code-standards)
- [Commit Guidelines](#commit-guidelines)
- [Pull Request Process](#pull-request-process)
- [Documentation Standards](#documentation-standards)
- [Security Guidelines](#security-guidelines)
- [Release Process](#release-process)

## Code of Conduct

We are committed to providing a welcoming and inspiring community for all. Please read and follow our Code of Conduct:

- Be respectful and inclusive
- Welcome newcomers and help them get started
- Focus on constructive criticism
- Respect differing viewpoints and experiences
- Show empathy towards other community members

## Getting Started

### Prerequisites

- Python 3.11 or higher
- [uv package manager](https://github.com/astral-sh/uv) 
- Docker (for Qdrant integration)
- Google Cloud Console project with APIs enabled
- Git for version control

### Quick Setup

```bash
# Clone the repository
git clone git@github.groupondev.com:srivers/google_mcp.git
cd google_mcp

# Create a virtual environment with uv
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies including dev requirements
uv sync --dev

# Copy environment template
cp .env.example .env

# Configure your Google OAuth credentials
# Edit .env with your credentials path
```

## Development Environment Setup

### 1. Google Cloud Console Configuration

```bash
# Required APIs to enable in Google Cloud Console:
- Gmail API
- Google Drive API
- Google Docs API
- Google Sheets API
- Google Slides API
- Google Calendar API
- Google Forms API
- Google Chat API

# Create OAuth 2.0 credentials (Web application)
# Add redirect URIs:
- http://localhost:8002/oauth/callback
- http://localhost:8002/oauth2callback
- http://127.0.0.1:6274/oauth/callback/debug
```

### 2. Local Development Server

```bash
# Start Qdrant for semantic search (optional but recommended)
docker run -p 6333:6333 -v ./qdrant_storage:/qdrant/storage qdrant/qdrant

# Start the development server with hot reload
uv run python server.py --dev

# The server will be available at http://localhost:8002
```

### 3. Development Tools

```bash
# Install pre-commit hooks
pre-commit install

# Run formatters
uv run black .
uv run isort .

# Run linters
uv run ruff check .
uv run mypy .

# Run security checks
uv run bandit -r .
uv run safety check
```

## Project Structure

```
fastmcp2_google_workspace/
├── auth/                    # Authentication modules
│   ├── google_auth.py      # OAuth implementation
│   ├── mcp_auth_middleware.py  # MCP middleware
│   └── service_helpers.py  # Service configurations
├── gcalendar/              # Calendar service tools
│   └── calendar_tools.py
├── gchat/                  # Chat service tools
│   ├── chat_tools.py
│   └── card_framework.py
├── gdocs/                  # Docs service tools
│   └── docs_tools.py
├── gdrive/                 # Drive service tools
│   └── drive_tools.py
├── gforms/                 # Forms service tools
│   └── forms_tools.py
├── gmail/                  # Gmail service tools
│   └── gmail_tools.py
├── gsheets/                # Sheets service tools
│   └── sheets_tools.py
├── gslides/                # Slides service tools
│   └── slides_tools.py
├── resources/              # MCP resources
│   ├── user_resources.py
│   └── service_resources.py
├── tests/                  # Test suite
│   ├── test_*.py          # Service-specific tests
│   └── README.md          # Testing documentation
├── docs/                   # Documentation
│   ├── api-reference/     # API documentation
│   ├── SECURITY_IMPLEMENTATION.md
│   └── CONFIGURATION_GUIDE.md
└── server.py              # Main server entry point
```

## How to Add New Services

### Step 1: Service Configuration

```python
# auth/service_helpers.py - Add service configuration
SERVICE_CONFIGS = {
    "your_service": {
        "service": "your_api_name",
        "version": "v1",
        "discovery_url": "https://your-api.googleapis.com/$discovery/rest?version=v1"
    }
}

SERVICE_DEFAULTS = {
    "your_service": {
        "default_scopes": [
            "https://www.googleapis.com/auth/your_service.read",
            "https://www.googleapis.com/auth/your_service.write"
        ],
        "version": "v1",
        "description": "Your Google Service description"
    }
}

# auth/scope_registry.py - Register scopes
SCOPE_REGISTRY = {
    "your_service_read": "https://www.googleapis.com/auth/your_service.read",
    "your_service_write": "https://www.googleapis.com/auth/your_service.write"
}
```

### Step 2: Create Service Directory

```bash
# Create service directory structure
mkdir -p gyourservice
touch gyourservice/__init__.py
touch gyourservice/yourservice_tools.py
```

### Step 3: Implement Service Tools

```python
# gyourservice/yourservice_tools.py
from typing_extensions import Optional
from fastmcp import mcp
from auth.service_helpers import request_service, get_injected_service
import json

@mcp.tool()
async def list_your_items(
    user_google_email: str,
    page_size: Optional[int] = 10
) -> str:
    """
    List items from Your Service.
    
    Args:
        user_google_email: User's Google email for authentication
        page_size: Number of items to return (1-100)
        
    Returns:
        JSON string with list of items
    """
    try:
        # Request service with middleware
        service_key = request_service(
            "your_service",
            ["your_service_read"]
        )
        
        # Get injected service
        service = get_injected_service(service_key)
        
        # Make API call
        response = service.items().list(
            pageSize=page_size
        ).execute()
        
        return json.dumps(response, indent=2)
        
    except Exception as e:
        return json.dumps({
            "error": str(e),
            "suggestion": "Check authentication and permissions"
        })

def setup_yourservice_tools(mcp_instance):
    """Register all Your Service tools with MCP."""
    # Tools are auto-registered via decorators
    pass
```

### Step 4: Add Tests

```python
# tests/test_yourservice_tools.py
import pytest
from unittest.mock import Mock, patch
from gyourservice.yourservice_tools import list_your_items

class TestYourServiceTools:
    
    @pytest.fixture
    def mock_service(self):
        """Create mock service for testing."""
        mock = Mock()
        mock.items().list().execute.return_value = {
            "items": [{"id": "1", "name": "Test Item"}]
        }
        return mock
    
    @pytest.mark.asyncio
    async def test_list_your_items(self, mock_service):
        """Test listing items from Your Service."""
        with patch('gyourservice.yourservice_tools.get_injected_service', 
                   return_value=mock_service):
            result = await list_your_items(
                user_google_email="test@gmail.com",
                page_size=10
            )
            
            assert "items" in result
            assert len(json.loads(result)["items"]) > 0
```

### Step 5: Register in Server

```python
# server.py - Add import and registration
from gyourservice.yourservice_tools import setup_yourservice_tools

# In the setup section
setup_yourservice_tools(mcp)
```

### Step 6: Update Documentation

```markdown
# docs/api-reference/yourservice/README.md
# Your Service API Reference

## Overview
Description of Your Service integration...

## Available Tools
- [`list_your_items`](#list_your_items) - List items from Your Service

## Tool Documentation
...
```

## How to Add New Tools

### 1. Tool Implementation Pattern

```python
@mcp.tool()
async def your_new_tool(
    user_google_email: str,
    required_param: str,
    optional_param: Optional[str] = None
) -> str:
    """
    Clear, concise description of what the tool does.
    
    Args:
        user_google_email: User's Google email for authentication
        required_param: Description of required parameter
        optional_param: Description of optional parameter
        
    Returns:
        JSON string with operation result
        
    Raises:
        ValueError: When required parameters are invalid
        AuthenticationError: When authentication fails
    """
    # Input validation
    if not required_param:
        return json.dumps({"error": "required_param is required"})
    
    try:
        # Service request
        service_key = request_service("service_name", ["scope"])
        service = get_injected_service(service_key)
        
        # API operation
        result = service.resource().method(
            param=required_param
        ).execute()
        
        # Return formatted result
        return json.dumps(result, indent=2)
        
    except HttpError as e:
        # Handle specific API errors
        return json.dumps({
            "error": f"API Error: {e.resp.status}",
            "details": str(e)
        })
    except Exception as e:
        # Handle general errors
        return json.dumps({
            "error": str(e),
            "suggestion": "Check parameters and authentication"
        })
```

### 2. Tool Naming Conventions

- Use descriptive, action-based names: `create_`, `list_`, `update_`, `delete_`, `get_`
- Include service context: `send_gmail_message`, not just `send_message`
- Be consistent with existing patterns

### 3. Parameter Guidelines

- Always include `user_google_email` as first parameter
- Use Optional[] for optional parameters with sensible defaults
- Validate all inputs before API calls
- Document parameter formats clearly (e.g., RFC3339 for dates)

### 4. Error Handling

```python
# Standard error response format
error_response = {
    "error": {
        "code": "ERROR_CODE",
        "message": "Human-readable error message",
        "details": {
            "field": "problem_field",
            "value": "invalid_value"
        }
    },
    "suggestion": "How to fix the error"
}
```

## Testing Requirements

### Unit Tests

Every new tool must have comprehensive unit tests:

```python
class TestYourTool:
    @pytest.mark.asyncio
    async def test_success_case(self):
        """Test successful execution."""
        
    @pytest.mark.asyncio  
    async def test_missing_required_param(self):
        """Test with missing required parameter."""
        
    @pytest.mark.asyncio
    async def test_invalid_param_format(self):
        """Test with invalid parameter format."""
        
    @pytest.mark.asyncio
    async def test_api_error_handling(self):
        """Test API error handling."""
```

### Integration Tests

```python
# tests/test_mcp_client.py
async def test_your_tool_integration(client):
    """Test tool through MCP client."""
    tools = await client.list_tools()
    assert "your_new_tool" in [t.name for t in tools]
    
    result = await client.call_tool(
        "your_new_tool",
        {"user_google_email": "test@gmail.com", ...}
    )
    assert result is not None
```

### Test Coverage

- Maintain minimum 80% code coverage
- All new code must include tests
- Run coverage reports: `uv run pytest --cov=. --cov-report=html`

## Code Standards

### Python Style Guide

- Follow PEP 8 with 88-character line limit (Black default)
- Use type hints for all functions
- Docstrings for all public functions (Google style)
- Meaningful variable names (avoid single letters except in comprehensions)

### Async/Await Best Practices

```python
# Good
async def process_items(items: list) -> list:
    results = []
    for item in items:
        result = await process_single_item(item)
        results.append(result)
    return results

# Better - concurrent processing
async def process_items(items: list) -> list:
    tasks = [process_single_item(item) for item in items]
    return await asyncio.gather(*tasks)
```

### Import Organization

```python
# Standard library imports
import json
import os
from typing_extensions import Optional, List, Dict

# Third-party imports
import aiohttp
from fastmcp import mcp

# Local imports
from auth.service_helpers import request_service
from utils.formatters import format_response
```

## Commit Guidelines

### Commit Message Format

```
<type>(<scope>): <subject>

<body>

<footer>
```

### Types

- **feat**: New feature
- **fix**: Bug fix
- **docs**: Documentation changes
- **style**: Code style changes (formatting, etc.)
- **refactor**: Code refactoring
- **test**: Adding or updating tests
- **chore**: Maintenance tasks

### Examples

```bash
# Good commit messages
git commit -m "feat(gmail): add batch email sending support"
git commit -m "fix(drive): handle large file uploads correctly"
git commit -m "docs(api): update Forms API reference"
git commit -m "test(calendar): add RFC3339 format validation tests"

# Bad commit messages (avoid these)
git commit -m "fixed stuff"
git commit -m "WIP"
git commit -m "updates"
```

## Pull Request Process

### 1. Fork and Branch

```bash
# Fork the repository on GitHub
# Clone your fork
git clone git@github.groupondev.com:srivers/google_mcp.git

# Create feature branch
git checkout -b feature/your-feature-name

# Make changes and commit
git add .
git commit -m "feat(service): add new functionality"

# Push to your fork
git push origin feature/your-feature-name
```

### 2. PR Requirements

Before submitting a PR, ensure:

- [ ] All tests pass: `uv run pytest`
- [ ] Code is formatted: `uv run black .`
- [ ] Linting passes: `uv run ruff check .`
- [ ] Documentation is updated
- [ ] Commit messages follow guidelines
- [ ] Branch is up-to-date with main

### 3. PR Template

```markdown
## Description
Brief description of changes

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation update

## Testing
- [ ] Unit tests pass
- [ ] Integration tests pass
- [ ] Manual testing completed

## Checklist
- [ ] Code follows project style
- [ ] Self-review completed
- [ ] Documentation updated
- [ ] Tests added/updated
```

### 4. Review Process

1. Automated checks run (tests, linting, coverage)
2. Code review by maintainers
3. Address feedback
4. Approval and merge

## Documentation Standards

### API Documentation

```python
@mcp.tool()
async def your_tool(params) -> str:
    """
    One-line summary of the tool.
    
    Detailed description explaining what the tool does,
    when to use it, and any important considerations.
    
    Args:
        param1: Description with type and format info
        param2: Optional parameter with default value
        
    Returns:
        JSON string containing:
        - field1: Description
        - field2: Description
        
    Raises:
        ValueError: When validation fails
        AuthenticationError: When auth fails
        
    Example:
        ```python
        result = await your_tool(
            user_google_email="user@gmail.com",
            param1="value"
        )
        ```
    """
```

### README Updates

When adding new features, update:
- Main README.md with feature description
- Service-specific documentation
- API reference in docs/api-reference/
- Configuration guide if new env vars added

## Security Guidelines

### Credential Handling

```python
# Never hardcode credentials
# Bad
API_KEY = "abc123xyz"

# Good
API_KEY = os.getenv("API_KEY")
if not API_KEY:
    raise ValueError("API_KEY environment variable required")
```

### Input Validation

```python
# Always validate and sanitize inputs
def validate_email(email: str) -> bool:
    """Validate email format."""
    import re
    pattern = r'^[\w\.-]+@[\w\.-]+\.\w+$'
    return bool(re.match(pattern, email))

# Prevent path traversal
def safe_path(user_input: str) -> str:
    """Sanitize file paths."""
    return os.path.basename(user_input)
```

### Error Messages

```python
# Don't expose sensitive information in errors
# Bad
except Exception as e:
    return f"Database error: {connection_string} - {e}"

# Good  
except Exception as e:
    logger.error(f"Database error: {e}")  # Log full error
    return "Database connection failed"   # Generic user message
```

## Release Process

### Version Numbering

We follow Semantic Versioning (MAJOR.MINOR.PATCH):
- MAJOR: Breaking changes
- MINOR: New features (backward compatible)
- PATCH: Bug fixes

### Release Checklist

1. Update version in `pyproject.toml`
2. Update CHANGELOG.md
3. Run full test suite
4. Build and test package: `uv build`
5. Create GitHub release with tag
6. Deploy documentation updates

### Deployment

```bash
# Build package
uv build

# Test installation
uv pip install dist/*.whl

# Publish to PyPI (maintainers only)
uv publish
```

## Getting Help

### Resources

- [Documentation](docs/): Complete platform documentation
- [API Reference](docs/api-reference/): Detailed tool documentation
- Issue Tracker: Contact your Groupon development team for bug reports
- Discussions: Contact your Groupon development team for Q&A

### Contact

- Contact your Groupon development team for support and collaboration
- Stack Overflow: Tag with `fastmcp2`

## Recognition

Contributors are recognized in:
- CONTRIBUTORS.md file
- Release notes
- Project documentation

Thank you for contributing to Groupon Google MCP! 🚀