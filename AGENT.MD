# RiversUnlimited Google Workspace MCP Agent

## Dev environment tips
- Use `ls gmail/` or `ls drive/` to explore specific Google service modules instead of scanning the entire project.
- Run `uv run fastmcp dev` to start the MCP server in development mode with hot reloading for testing tools.
- Use `uv run python -m <service_name>.main` to test individual service implementations (e.g., `uv run python -m gmail.main`).
- Check each service's `__init__.py` to understand the available tools and their capabilities - there are 60+ tools across all services.
- For authentication testing, use `uv run python scripts/auth_test.py <service_name>` to validate OAuth flows.
- Explore middleware templates with `ls middleware/templates/` for available Jinja2 macros and email templates.

## Testing instructions
- Find the comprehensive testing framework in `tests/client/TESTING_FRAMEWORK.md` with standardized patterns for all FastMCP2 Google Workspace client tests.
- Run `uv run pytest tests/client/` to execute the full standardized test suite across all Google services (gmail, drive, calendar, etc.).
- From the project root, use `uv run pytest tests/<service_name>/` to run tests for specific Google services.
- To focus on specific test patterns, use: `uv run pytest -k "<test_pattern>"` (e.g., `uv run pytest -k "gmail and send"`).
- For authentication pattern testing, run `uv run pytest tests/client/ -m "auth_required"` to validate both explicit email and middleware injection patterns.
- Fix any authentication, API, or integration errors until all service tests pass green - the framework handles real resource ID fetching automatically.
- After adding new tools or changing service implementations, run `uv run pytest tests/test_service_integration.py` to verify cross-service workflows.
- Add or update tests for any new MCP tools or Google API integrations using the standardized framework in `tests/client/test_template.py`.
- Use service markers: `uv run pytest tests/client/ -m "service('gmail')"` to test specific Google services.

## PR instructions
- Title format: [<service_name>] <Title> (e.g., "[Gmail] Add filter management tools" or "[Drive] Fix file sharing permissions")
- Always run `uv run black .` and `uv run pytest tests/client/` before committing to ensure code quality and test compliance.
- For multi-service changes, use: [Multi] <Title> (e.g., "[Multi] Add OAuth token refresh across all services")
- Test authentication flows for any services you modify using the standardized testing framework detailed in `tests/client/TESTING_FRAMEWORK.md`.
- Reference the testing framework when adding new service integrations to maintain consistency across all 60+ Google Workspace tools.

## Agent Configuration Files

### .roomodes
Defines the `riversunlimited-google` mode with comprehensive Google Workspace integration across Gmail, Drive, Docs, Sheets, Slides, Calendar, Forms, Chat, and Photos - featuring 60+ tools, resource discovery patterns, and template macros.

### .cursorrules
Contains expertise definitions for Google Workspace MCP operations including authentication flows, testing framework mastery with real resource ID integration, multi-service workflows, and Chat app development with Card Framework v2.

---

*RiversUnlimited Google Workspace MCP Agent - Ready for whatever protocol catches on*