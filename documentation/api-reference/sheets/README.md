# Google Sheets API Reference

Complete API documentation for all Google Sheets tools in the Groupon Google MCP Server.

## Overview

The Google Sheets service provides comprehensive spreadsheet operations including creation, data manipulation, range handling, and batch updates. This service integrates with Google Drive for file management and supports complex data operations.

## Available Tools

| Tool Name | Description |
|-----------|-------------|
| [`list_spreadsheets`](#list_spreadsheets) | List user's spreadsheets with filtering options |
| [`get_spreadsheet_info`](#get_spreadsheet_info) | Get detailed spreadsheet information and sheet structure |
| [`read_sheet_values`](#read_sheet_values) | Read data from specific ranges in spreadsheets |
| [`modify_sheet_values`](#modify_sheet_values) | Update cell values in spreadsheet ranges |
| [`create_spreadsheet`](#create_spreadsheet) | Create new spreadsheets with custom sheet configuration |
| [`create_sheet`](#create_sheet) | Add new sheets to existing spreadsheets |

---

## Tool Details

### `list_spreadsheets`

List all spreadsheets accessible to the authenticated user with filtering capabilities.

**Parameters:**
- `user_google_email` (string, required): User's Google email for authentication
- `max_results` (integer, optional, default: 100): Maximum number of spreadsheets to return
- `page_token` (string, optional): Token for pagination
- `query` (string, optional): Search query to filter spreadsheets

**Response:**
- Array of spreadsheet information
- Pagination tokens
- Total count information
- File metadata including creation and modification dates

**Integration Features:**
- Uses Drive API for comprehensive file listing
- Includes shared spreadsheets and team drives
- Provides file permissions and sharing information

### `get_spreadsheet_info`

Retrieve detailed information about a specific spreadsheet including all sheets and their properties.

**Parameters:**
- `user_google_email` (string, required): User's Google email
- `spreadsheet_id` (string, required): Spreadsheet ID to analyze
- `include_sheets` (boolean, optional, default: true): Include detailed sheet information

**Response:**
- Complete spreadsheet metadata
- Array of all sheets with properties
- Spreadsheet settings and formatting
- Permission and sharing information

**Sheet Information Includes:**
- Sheet names and IDs
- Grid properties (row/column counts)
- Sheet type and visibility
- Protected ranges
- Conditional formatting rules

### `read_sheet_values`

Read data from specific cell ranges within a spreadsheet.

**Parameters:**
- `user_google_email` (string, required): User's Google email
- `spreadsheet_id` (string, required): Target spreadsheet ID
- `range` (string, required): A1 notation range (e.g., "Sheet1!A1:Z100")
- `value_render_option` (string, optional): How values should be rendered
- `date_time_render_option` (string, optional): How dates/times should be formatted

**Range Formats:**
- Single cell: `A1`
- Range: `A1:C3`
- Entire column: `A:A`
- Entire row: `1:1`
- Named range: `MyNamedRange`
- Multiple sheets: `Sheet1!A1:B2,Sheet2!A1:B2`

**Response:**
- Cell values in specified format
- Range metadata
- Major dimension information
- Empty cell handling

### `modify_sheet_values`

Update cell values in specified ranges with support for various data types and formatting.

**Parameters:**
- `user_google_email` (string, required): User's Google email
- `spreadsheet_id` (string, required): Target spreadsheet ID
- `range` (string, required): A1 notation range to update
- `values` (array, required): 2D array of values to insert
- `value_input_option` (string, optional): How input data should be interpreted
- `include_values_in_response` (boolean, optional): Return updated values

**Value Input Options:**
- `RAW`: Values are stored as-is
- `USER_ENTERED`: Values are parsed as if typed by user (formulas, dates, etc.)

**Batch Operations:**
- Supports multiple range updates in single request
- Automatic cell format detection
- Formula and function support
- Data validation compliance

**Response:**
- Update confirmation
- Affected cell count
- Updated range information
- New values (if requested)

### `create_spreadsheet`

Create new Google Spreadsheets with custom sheet configuration and initial data.

**Parameters:**
- `user_google_email` (string, required): User's Google email
- `title` (string, required): Spreadsheet title
- `sheet_names` (array, optional): Names for initial sheets
- `locale` (string, optional): Spreadsheet locale setting
- `auto_recalc` (string, optional): Recalculation setting
- `time_zone` (string, optional): Spreadsheet timezone

**Default Configuration:**
- Creates one sheet named "Sheet1" if no sheet names provided
- Sets appropriate locale and timezone
- Configures automatic recalculation
- Applies default formatting and grid properties

**Response:**
- New spreadsheet ID and URL
- Created sheet information
- Spreadsheet properties
- Access permissions

### `create_sheet`

Add new sheets to existing spreadsheets with custom properties and configuration.

**Parameters:**
- `user_google_email` (string, required): User's Google email
- `spreadsheet_id` (string, required): Target spreadsheet ID
- `sheet_name` (string, required): Name for new sheet
- `grid_properties` (object, optional): Grid size and properties
- `tab_color` (object, optional): Sheet tab color configuration

**Sheet Configuration:**
- Customizable grid dimensions
- Tab color and visibility settings
- Protected range setup
- Conditional formatting rules
- Data validation configuration

**Response:**
- New sheet ID and properties
- Sheet creation confirmation
- Updated spreadsheet information

---

## Authentication & Scopes

Required Google API scopes:
- `https://www.googleapis.com/auth/spreadsheets`: Full access to spreadsheets
- `https://www.googleapis.com/auth/spreadsheets.readonly`: Read-only access
- `https://www.googleapis.com/auth/drive.readonly`: Drive integration for listing

## Advanced Features

### Range Operations
Support for complex range operations including:
- Named ranges
- Cross-sheet references  
- Dynamic range expansion
- Batch range updates

### Data Types & Formatting
Comprehensive support for:
- Numbers with custom formatting
- Dates and times in various formats
- Formulas and functions
- Rich text formatting
- Data validation rules

### Integration Capabilities
Seamless integration with other Google services:
- **Drive**: File management and sharing
- **Gmail**: Automated reporting and data distribution
- **Docs**: Data export to document formats

## Best Practices

1. **Range Selection**: Use specific ranges instead of entire sheets for better performance
2. **Batch Operations**: Group multiple updates into single requests
3. **Data Validation**: Implement proper input validation before sheet updates
4. **Error Handling**: Handle quota limits and API rate limiting gracefully
5. **Formula Usage**: Leverage Google Sheets functions for dynamic calculations

## Common Use Cases

### Data Analysis Workflows
```python
# Create analysis spreadsheet
spreadsheet = await create_spreadsheet(
    user_google_email="analyst@company.com",
    title="Q4 Sales Analysis",
    sheet_names=["Raw Data", "Analysis", "Charts"]
)

# Import data
await modify_sheet_values(
    user_google_email="analyst@company.com",
    spreadsheet_id=spreadsheet["spreadsheet_id"],
    range="Raw Data!A1:Z1000",
    values=sales_data
)

# Read processed results
results = await read_sheet_values(
    user_google_email="analyst@company.com", 
    spreadsheet_id=spreadsheet["spreadsheet_id"],
    range="Analysis!A1:D50"
)
```

### Reporting Automation
Integration with other services for automated reporting:
- Collect data from various sources
- Process and analyze in Sheets
- Generate reports and share via Gmail
- Store results in Drive folders

## Error Handling

Common error scenarios and solutions:

- **Invalid Range**: Validate A1 notation format before requests
- **Permission Denied**: Ensure proper spreadsheet access permissions
- **Quota Exceeded**: Implement exponential backoff for rate limiting
- **Large Datasets**: Use pagination for large data operations
- **Formula Errors**: Validate formulas before batch operations

## Performance Optimization

- **Batch Operations**: Group related updates into single requests
- **Range Optimization**: Use specific ranges instead of entire sheets
- **Caching**: Cache frequently accessed spreadsheet metadata
- **Parallel Processing**: Execute independent operations concurrently

---

For more information, see:
- [Authentication Guide](../auth/README.md)
- [Multi-Service Integration](../../MULTI_SERVICE_INTEGRATION.md)
- [Main API Reference](../README.md)