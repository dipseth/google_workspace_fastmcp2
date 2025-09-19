"""
Google Sheets Prompts for FastMCP2 - Resource-Driven Template System.

This module provides 3 comprehensive Google Sheets prompts: Advanced, Medium, and Simple.
Leverages the Template Parameter Middleware to automatically populate real Sheets data like
spreadsheet IDs, sheet names, cell ranges, and URL construction for seamless integration.

Key Features:
- Advanced: Smart contextual spreadsheet cards using real Sheets data and ranges
- Medium: Professional data dashboard cards with live Sheets integration  
- Simple: Instant demo cards for quick Sheets testing and demonstrations

Resource Integration:
- Uses {{sheets://spreadsheets/list}} for real spreadsheet IDs
- Uses {{sheets://spreadsheets/{sheet_id}/sheets}} for sheet tab data
- Uses {{sheets://spreadsheets/{sheet_id}/values/{range}}} for cell data
- Uses {{user://current/profile}} for user context and permissions
"""

import logging
from typing_extensions import Optional
from datetime import datetime, timezone
from pydantic import Field
from fastmcp import FastMCP, Context
from fastmcp.prompts.prompt import Message, PromptMessage, TextContent

from config.enhanced_logging import setup_logger
logger = setup_logger()

def setup_gsheets_prompts(mcp: FastMCP):
    """
    Register Google Sheets prompts: Advanced, Medium, Simple.
    
    Args:
        mcp: The FastMCP server instance
    """

    # ========== ADVANCED PROMPT ==========
    @mcp.prompt(
        name="smart_contextual_sheets_card",
        description="Advanced: Generate intelligent Sheets cards using real spreadsheet data (IDs, ranges, values)",
        tags={"gsheets", "sheets", "advanced", "contextual", "dynamic", "data"},
        meta={
            "version": "3.0",
            "author": "FastMCP2-StreamlinedSheets",
            "uses_resources": True,
            "resource_dependencies": [
                "service://sheets/spreadsheets",
                "sheets://spreadsheets/list", 
                "sheets://data/active",
                "user://current/profile"
            ]
        }
    )
    def smart_contextual_sheets_card(
        context: Context,
        card_title: str = Field(
            default="Smart Sheets Dashboard",
            description="Title for the contextual Sheets card"
        ),
        target_spreadsheet: str = Field(
            default="financial_data",
            description="Description of the target spreadsheet (e.g., 'sales_report', 'budget_2024', 'project_tracker')"
        ),
        data_focus: str = Field(
            default="summary analysis",
            description="Focus of the data presentation (e.g., 'trends', 'performance', 'comparison', 'forecast')"
        )
    ) -> PromptMessage:
        """
        ADVANCED: Generate intelligent Google Sheets cards that adapt to real spreadsheet configurations.
        Uses real-time Sheets data for contextual, data-driven communication.
        """
        
        request_id = context.request_id
        current_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        
        # Resolve Field values
        card_title_str = str(card_title) if hasattr(card_title, 'default') else card_title
        target_spreadsheet_str = str(target_spreadsheet) if hasattr(target_spreadsheet, 'default') else target_spreadsheet
        data_focus_str = str(data_focus) if hasattr(data_focus, 'default') else data_focus
        
        advanced_content = f"""
# 📊 Smart Contextual Google Sheets Card (Advanced)
*Request ID: {request_id} | Generated: {current_time}*

## ⚡ Advanced Sheets Intelligence Integration

### Configuration
- **Card Title**: {card_title_str}
- **Target Spreadsheet**: {target_spreadsheet_str}  
- **Data Focus**: {data_focus_str}
- **Level**: Advanced with real-time Google Sheets data integration

## 📈 Step 1: Gather Real Sheets Context

```python
# Get live Google Sheets data for intelligent card generation
sheets_list = await mcp.read_resource("service://sheets/spreadsheets")
active_sheets = await mcp.read_resource("sheets://data/active")  
user_profile = await mcp.read_resource("user://current/profile")

print("📋 Available Spreadsheets:", sheets_list)
print("📊 Active Sheet Data:", active_sheets)
print("👤 User Context:", user_profile)

# Extract real spreadsheet data for contextual cards
sheets_context = {{
    "spreadsheets": sheets_list,
    "active_data": active_sheets,
    "user": user_profile,
    "timestamp": "{current_time}",
    "request_id": "{request_id}"
}}

# Example extracted data from resources:
spreadsheet_examples = {{
    "financial_data": {{
        "spreadsheet_id": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms",
        "name": "Q4 Financial Analysis",
        "sheets": ["Summary", "Revenue", "Expenses", "Projections"],
        "url": "https://docs.google.com/spreadsheets/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/edit",
        "last_modified": "2024-08-29T10:30:00Z",
        "owner": "finance@company.com"
    }},
    "sales_report": {{
        "spreadsheet_id": "1ABC123XYZ456DEF789GHI012JKL345MNO678PQR901STU",
        "name": "Monthly Sales Dashboard", 
        "sheets": ["Overview", "Regional", "Products", "Trends"],
        "url": "https://docs.google.com/spreadsheets/d/1ABC123XYZ456DEF789GHI012JKL345MNO678PQR901STU/edit",
        "last_modified": "2024-08-29T09:15:00Z",
        "owner": "sales@company.com"
    }}
}}
```

## 🎯 Step 2: Generate Context-Aware Sheets Card

```python
# Advanced contextual Sheets card with real data intelligence
result = await send_dynamic_card(
    user_google_email="{{{{user://current/profile}}}}['email']",
    space_id="{{{{chat://spaces/list}}}}['team_workspace']['space_id']",
    webhook_url="{{{{chat://webhooks/active}}}}['team_workspace']['webhook_url']",
    card_description='''
    Create a comprehensive {data_focus_str} dashboard card titled '{card_title_str}' with subtitle 'Live Sheets Intelligence'.
    
    Add dynamic sections using real Sheets data:
    - 'Spreadsheet Info' section with decoratedText showing spreadsheet details with table icon
    - 'Data Overview' section with key metrics using chart icon  
    - 'Recent Changes' section showing latest updates with clock icon
    - 'Actions' section with context-aware buttons for data access
    ''',
    card_params={{
        "title": "{card_title_str}",
        "subtitle": "📊 Powered by Real Sheets Data | {{{{sheets://spreadsheets/list}}}}['{target_spreadsheet_str}']['name']",
        "sections": [
            {{
                "header": "📋 Spreadsheet Intelligence",
                "widgets": [
                    {{
                        "decoratedText": {{
                            "icon": {{"knownIcon": "DESCRIPTION"}},
                            "topLabel": "Active Spreadsheet",
                            "text": "<b>{{{{sheets://spreadsheets/list}}}}['{target_spreadsheet_str}']['name']</b><br/><font color='#1a73e8'>ID: {{{{sheets://spreadsheets/list}}}}['{target_spreadsheet_str}']['spreadsheet_id']</font>",
                            "bottomLabel": "{{{{sheets://spreadsheets/list}}}}['{target_spreadsheet_str}']['sheets']|length}} sheets • Owner: {{{{sheets://spreadsheets/list}}}}['{target_spreadsheet_str}']['owner']"
                        }}
                    }}
                ]
            }},
            {{
                "header": "📊 Data Overview", 
                "widgets": [
                    {{
                        "decoratedText": {{
                            "icon": {{"knownIcon": "ANALYTICS"}},
                            "topLabel": "Key Metrics",
                            "text": "<b>Sheet Tabs: {{{{sheets://spreadsheets/list}}}}['{target_spreadsheet_str}']['sheets']|join(', ')}}</b><br/><font color='#34a853'>All data current and accessible</font>",
                            "bottomLabel": "Last modified: {{{{sheets://spreadsheets/list}}}}['{target_spreadsheet_str}']['last_modified']"
                        }}
                    }},
                    {{
                        "decoratedText": {{
                            "icon": {{"knownIcon": "TRENDING_UP"}},
                            "topLabel": "Data Status", 
                            "text": "<b><font color='#34a853'>Live & Synchronized</font></b><br/>Real-time access to spreadsheet data<br/>Permissions validated and active",
                            "bottomLabel": "Connected via Google Sheets API",
                            "endIcon": {{"knownIcon": "CHECK_CIRCLE"}}
                        }}
                    }}
                ]
            }},
            {{
                "header": "🔄 Recent Activity",
                "widgets": [
                    {{
                        "decoratedText": {{
                            "icon": {{"knownIcon": "SCHEDULE"}},
                            "topLabel": "Latest Updates",
                            "text": "<b>Data refreshed automatically</b><br/>Last sync: {{{{user://current/profile}}}}['last_activity']<br/><font color='#1a73e8'>Real-time monitoring active</font>",
                            "bottomLabel": "Tracking all sheet modifications"
                        }}
                    }}
                ]
            }},
            {{
                "header": "🚀 Smart Actions",
                "widgets": [
                    {{
                        "buttonList": {{
                            "buttons": [
                                {{
                                    "text": "📊 Open Spreadsheet",
                                    "onClick": {{
                                        "openLink": {{
                                            "url": "{{{{sheets://spreadsheets/list}}}}['{target_spreadsheet_str}']['url']"
                                        }}
                                    }},
                                    "type": "FILLED"
                                }},
                                {{
                                    "text": "📈 View Analytics",
                                    "onClick": {{
                                        "openLink": {{
                                            "url": "{{{{sheets://spreadsheets/list}}}}['{target_spreadsheet_str}']['url']}}/edit#gid=0"
                                        }}
                                    }},
                                    "type": "OUTLINED"
                                }},
                                {{
                                    "text": "🔄 Refresh Data",
                                    "onClick": {{
                                        "action": {{
                                            "function": "refresh_sheets_data",
                                            "parameters": [
                                                {{
                                                    "key": "spreadsheet_id",
                                                    "value": "{{{{sheets://spreadsheets/list}}}}['{target_spreadsheet_str}']['spreadsheet_id']"
                                                }}
                                            ]
                                        }}
                                    }},
                                    "type": "OUTLINED"
                                }}
                            ]
                        }}
                    }}
                ]
            }}
        ]
    }}
)

print(f"✅ Advanced contextual Sheets card sent: {{result}}")
```

## 🌟 Advanced Features & Real Data Integration

### Live Sheets Data Access
When the resource `service://sheets/spreadsheets` is accessed, you get real data like:
```json
{{
  "files": [
    {{
      "id": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms",
      "name": "Q4 Financial Analysis",
      "mimeType": "application/vnd.google-apps.spreadsheet",
      "webViewLink": "https://docs.google.com/spreadsheets/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/edit",
      "modifiedTime": "2024-08-29T10:30:00.000Z",
      "owners": [
        {{
          "displayName": "Finance Team",
          "emailAddress": "finance@company.com"
        }}
      ],
      "sheets": [
        {{"properties": {{"title": "Summary", "sheetId": 0}}}},
        {{"properties": {{"title": "Revenue", "sheetId": 123456}}}},
        {{"properties": {{"title": "Expenses", "sheetId": 789012}}}},
        {{"properties": {{"title": "Projections", "sheetId": 345678}}}}
      ]
    }}
  ]
}}
```

### Sheets Data Range Access
The `sheets://data/active` resource returns:
```json
{{
  "ranges": [
    {{
      "spreadsheet_id": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms",
      "range": "Summary!A1:E10",
      "major_dimension": "ROWS",
      "values": [
        ["Metric", "Q1", "Q2", "Q3", "Q4"],
        ["Revenue", "150000", "175000", "180000", "195000"],
        ["Expenses", "120000", "140000", "145000", "155000"],
        ["Profit", "30000", "35000", "35000", "40000"]
      ]
    }}
  ]
}}
```

### Smart Template Resolution Examples

```python
# Template expressions that resolve automatically:
sheet_name = "{{{{sheets://spreadsheets/list}}}}['financial_data']['name']"
# → Resolves to: "Q4 Financial Analysis"

sheet_url = "{{{{sheets://spreadsheets/list}}}}['financial_data']['url']"
# → Resolves to: "https://docs.google.com/spreadsheets/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/edit"

sheet_tabs = "{{{{sheets://spreadsheets/list}}}}['financial_data']['sheets']"
# → Resolves to: ["Summary", "Revenue", "Expenses", "Projections"]

owner_email = "{{{{sheets://spreadsheets/list}}}}['financial_data']['owner']"
# → Resolves to: "finance@company.com"
```

### Context-Aware Card Generation

The advanced system creates cards that:
- **Auto-populate** with real spreadsheet IDs and URLs
- **Display actual** sheet names and tab structures
- **Include working links** to specific sheets and ranges
- **Show current data** from live spreadsheet cells
- **Adapt content** based on user permissions and sheet access

### Professional Integration Benefits
- **Zero Manual Configuration**: All IDs and URLs populated automatically
- **Real-time Accuracy**: Data reflects current spreadsheet status
- **Workflow Integration**: Cards work seamlessly with existing Sheets
- **Permission Awareness**: Actions adapt to user access levels
- **Scalable**: Works across multiple spreadsheets and workbooks

### Testing with Real Data
```python
# Test the advanced Sheets integration
sheets_resource = await mcp.read_resource("service://sheets/spreadsheets")
print("Available spreadsheets for card generation:")
for sheet in sheets_resource.get('files', []):
    print(f"  - {{sheet['name']}} ({{sheet['id']}})")
    print(f"    URL: {{sheet['webViewLink']}}")
    print(f"    Modified: {{sheet['modifiedTime']}}")

# Use real sheet data in card content
if sheets_resource.get('files'):
    first_sheet = sheets_resource['files'][0]
    card_content = f"Card for {{first_sheet['name']}} with {{len(first_sheet.get('sheets', []))}} tabs"
    print(f"Sample card content: {{card_content}}")
```

### Data Range Integration Examples

```python
# Access specific cell ranges for card content
revenue_data = await mcp.read_resource("sheets://spreadsheets/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/values/Revenue!A1:C10")
summary_metrics = await mcp.read_resource("sheets://spreadsheets/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/values/Summary!A1:E5")

# Use in card generation
card_with_data = f'''
Revenue Q4: ${{revenue_data['values'][1][3]}}
Total Metrics: {{len(summary_metrics['values'])}} data points
Last Update: {{summary_metrics['range']}}
'''
```

This advanced prompt showcases FastMCP2's sophisticated Sheets resource integration capabilities with real spreadsheet data!
"""
        
        return PromptMessage(
            content=TextContent(type="text", text=advanced_content),
            role="assistant"
        )

    # ========== MEDIUM PROMPT ==========
    @mcp.prompt(
        name="professional_sheets_dashboard",
        description="Medium: Create beautiful Sheets dashboard cards with live spreadsheet integration",
        tags={"gsheets", "sheets", "medium", "dashboard", "professional", "data"},
        meta={
            "version": "3.0",
            "author": "FastMCP2-StreamlinedSheets"
        }
    )
    def professional_sheets_dashboard(
        context: Context,
        dashboard_title: str = Field(
            default="Data Dashboard",
            description="Title for the Sheets dashboard card"
        ),
        data_source: str = Field(
            default="Monthly Report",
            description="Name or description of the data source spreadsheet"
        ),
        dashboard_theme: str = Field(
            default="performance analytics",
            description="Theme of the dashboard (e.g., 'financial summary', 'sales metrics', 'project status')"
        )
    ) -> PromptMessage:
        """
        MEDIUM: Generate professional Sheets dashboard cards with modern design and live spreadsheet data.
        Perfect balance of functionality, visual appeal, and Sheets integration.
        """
        
        request_id = context.request_id
        current_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        
        # Resolve Field values
        dashboard_title_str = str(dashboard_title) if hasattr(dashboard_title, 'default') else dashboard_title
        data_source_str = str(data_source) if hasattr(data_source, 'default') else data_source
        dashboard_theme_str = str(dashboard_theme) if hasattr(dashboard_theme, 'default') else dashboard_theme
        
        medium_content = f"""
# 📊 Professional Sheets Dashboard (Medium)
*Request ID: {request_id} | Generated: {current_time}*

## ✨ Professional Dashboard Features with Sheets Integration

### Configuration
- **Dashboard Title**: {dashboard_title_str}
- **Data Source**: {data_source_str}
- **Theme**: {dashboard_theme_str}
- **Level**: Medium complexity with professional Sheets data integration

## 📋 Ready-to-Send Professional Sheets Dashboard

```python
# Generate beautiful professional Sheets dashboard card
result = await send_dynamic_card(
    user_google_email="your-email@gmail.com",
    space_id="{{{{chat://spaces/list}}}}['data_team']['space_id']",
    webhook_url="{{{{chat://webhooks/active}}}}['data_team']['webhook_url']",
    card_description='''
    Create a professional {dashboard_theme_str} dashboard titled '{dashboard_title_str}' with subtitle '{data_source_str} Analytics'.
    
    Add professional sections:
    - 'Data Source' section with decoratedText showing spreadsheet info with table icon
    - 'Key Insights' section with data highlights using analytics icon  
    - 'Recent Updates' section displaying latest data changes with clock icon
    - 'Data Actions' section with professional spreadsheet action buttons
    ''',
    card_params={{
        "title": "{dashboard_title_str}",
        "subtitle": "📈 {data_source_str} • Live Data Analytics",
        "sections": [
            {{
                "header": "📋 Data Source",
                "widgets": [
                    {{
                        "decoratedText": {{
                            "icon": {{"knownIcon": "DESCRIPTION"}},
                            "topLabel": "Active Spreadsheet",
                            "text": "<b>{{{{sheets://spreadsheets/list}}}}['primary']['name']</b><br/><font color='#34a853'>{{{{sheets://spreadsheets/list}}}}['primary']['sheets']|length}} sheets available</font>",
                            "bottomLabel": "ID: {{{{sheets://spreadsheets/list}}}}['primary']['spreadsheet_id']}}"
                        }}
                    }}
                ]
            }},
            {{
                "header": "📈 Key Insights",
                "collapsible": false,
                "widgets": [
                    {{
                        "decoratedText": {{
                            "icon": {{"knownIcon": "ANALYTICS"}},
                            "topLabel": "Data Summary",
                            "text": "<b><font color='#1a73e8'>High Performance Metrics</font></b><br/>5 active data ranges • 12 charts updated<br/><font color='#34a853'>↑ 18% improvement from last period</font>",
                            "bottomLabel": "All data current and verified"
                        }}
                    }},
                    {{
                        "decoratedText": {{
                            "icon": {{"knownIcon": "TRENDING_UP"}},
                            "topLabel": "Trend Analysis",
                            "text": "<b>Positive Growth Trend</b><br/><font color='#34a853'>Strong upward trajectory detected</font><br/>Forecast models show continued improvement",
                            "bottomLabel": "Based on {{{{sheets://data/active}}}}['ranges']|length}} data ranges"
                        }}
                    }}
                ]
            }},
            {{
                "header": "🕒 Recent Updates", 
                "widgets": [
                    {{
                        "decoratedText": {{
                            "icon": {{"knownIcon": "UPDATE"}},
                            "topLabel": "Data Freshness",
                            "text": "<b>Real-time Sync Active</b><br/>Last refresh: {{{{sheets://spreadsheets/list}}}}['primary']['last_modified']<br/><b>Auto-updating</b> every 15 minutes",
                            "bottomLabel": "Data pipeline monitoring active"
                        }}
                    }}
                ]
            }},
            {{
                "header": "🚀 Data Actions",
                "widgets": [
                    {{
                        "buttonList": {{
                            "buttons": [
                                {{
                                    "text": "📊 Open Spreadsheet",
                                    "onClick": {{
                                        "openLink": {{
                                            "url": "{{{{sheets://spreadsheets/list}}}}['primary']['url']}}"
                                        }}
                                    }},
                                    "type": "FILLED"
                                }},
                                {{
                                    "text": "📈 View Charts",
                                    "onClick": {{
                                        "openLink": {{
                                            "url": "{{{{sheets://spreadsheets/list}}}}['primary']['url']}}/edit#gid={{{{sheets://spreadsheets/list}}}}['primary']['sheets'][0]['sheet_id']}}"
                                        }}
                                    }},
                                    "type": "OUTLINED"
                                }},
                                {{
                                    "text": "🔄 Refresh Now",
                                    "onClick": {{
                                        "action": {{
                                            "function": "refresh_spreadsheet_data",
                                            "parameters": [
                                                {{
                                                    "key": "spreadsheet_id",
                                                    "value": "{{{{sheets://spreadsheets/list}}}}['primary']['spreadsheet_id']"
                                                }}
                                            ]
                                        }}
                                    }},
                                    "type": "OUTLINED"
                                }}
                            ]
                        }}
                    }}
                ]
            }}
        ]
    }}
)

print(f"✅ Professional Sheets dashboard sent: {{result}}")
```

## 🎨 Dashboard Design Highlights

### Visual Excellence
- **Professional Layout**: Clean sections with logical data hierarchy
- **Live Data Integration**: Real spreadsheet names, IDs, and sheet counts
- **Modern Icons**: Contextual icons that enhance data readability
- **Status Indicators**: Color-coded metrics with trend information

### Sheets-Specific Features  
- **Spreadsheet Awareness**: Automatically includes sheet names and IDs
- **Data Context**: Shows actual sheet tabs and data ranges
- **Working Links**: Direct links to specific sheets and chart views
- **Action Buttons**: Context-aware actions based on Sheets permissions

### Content Structure
- **Data Source**: Live spreadsheet information and structure
- **Key Insights**: Performance indicators with trend analysis
- **Recent Updates**: Real-time data refresh status and timing
- **Data Actions**: Direct access to spreadsheet functions and views

### Technical Integration
- **Sheet ID Resolution**: `{{{{sheets://spreadsheets/list}}}}['primary']['spreadsheet_id']` 
- **Sheet Count**: `{{{{sheets://spreadsheets/list}}}}['primary']['sheets']|length}}`
- **Spreadsheet URLs**: `{{{{sheets://spreadsheets/list}}}}['primary']['url']`
- **Sheet Names**: `{{{{sheets://spreadsheets/list}}}}['primary']['name']`

## 📊 Data Range Integration

### Cell Range Access Examples
```python
# Access specific data ranges for dashboard content
summary_range = "{{{{sheets://data/active}}}}['ranges'][0]['range']"
data_values = "{{{{sheets://data/active}}}}['ranges'][0]['values']"
row_count = "{{{{sheets://data/active}}}}['ranges'][0]['values']|length"

# Use in card generation for dynamic content
revenue_current = "{{{{sheets://data/active}}}}['ranges'][0]['values'][1][3]"  # Q4 revenue
growth_rate = "{{{{sheets://data/active}}}}['ranges'][0]['values'][2][3]"     # Growth %
```

### Professional URL Construction
```python
# Direct links to specific sheets and views
sheet_base_url = "{{{{sheets://spreadsheets/list}}}}['primary']['url']}}"
charts_view = f"{{sheet_base_url}}/edit#gid={{{{sheets://spreadsheets/list}}}}['primary']['sheets'][1]['sheet_id']}}"
data_view = f"{{sheet_base_url}}/edit#gid={{{{sheets://spreadsheets/list}}}}['primary']['sheets'][0]['sheet_id']}}"
```

## 📊 Perfect For:
- **Business Reports**: Executive dashboards with live business data
- **Project Tracking**: Visual project status with spreadsheet integration  
- **Financial Analysis**: Real-time financial metrics and trend analysis
- **Team Updates**: Data-driven team performance and progress reports

## 🎯 Advanced Integration Features

### Real-time Data Sync
- **Live Updates**: Card content reflects current spreadsheet data
- **Auto-refresh**: Configurable refresh intervals for data freshness
- **Change Detection**: Automatic updates when spreadsheet data changes
- **Permission Validation**: Ensures user has access before displaying data

### Professional Data Presentation
- **Trend Analysis**: Visual indicators for data trends and changes
- **Key Metrics**: Highlighted important data points and KPIs
- **Data Quality**: Status indicators for data completeness and accuracy
- **Interactive Elements**: Clickable links to detailed spreadsheet views

### Workflow Integration
- **Direct Access**: One-click access to source spreadsheets
- **Chart Views**: Links to specific chart and visualization tabs
- **Data Actions**: Context-aware buttons for common spreadsheet tasks
- **Team Collaboration**: Shareable cards with live data for team discussions

This medium-complexity prompt delivers professional Sheets dashboards with smart spreadsheet integration!
"""
        
        return PromptMessage(
            content=TextContent(type="text", text=medium_content),
            role="assistant"
        )

    # ========== SIMPLE PROMPT ==========
    @mcp.prompt(
        name="quick_sheets_card_demo",
        description="Simple: Zero-config instant Sheets card demo - ready to send immediately",
        tags={"gsheets", "sheets", "simple", "demo", "instant", "data"},
        meta={
            "version": "3.0",
            "author": "FastMCP2-StreamlinedSheets"
        }
    )
    def quick_sheets_card_demo(context: Context) -> PromptMessage:
        """
        SIMPLE: Zero-configuration Sheets card demo. Perfect for instant testing and demonstrations.
        No parameters needed - works immediately out of the box with sample spreadsheet data.
        """
        
        request_id = context.request_id
        current_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        
        simple_content = f"""
# ⚡ Quick Sheets Card Demo (Simple)
*Request ID: {request_id} | Generated: {current_time}*

## 🎯 Zero-Configuration Sheets Card Demo

### Features
- **Level**: Simple - No parameters required
- **Ready**: Instant send to any Chat space with Sheets data
- **Design**: Clean and professional with Sheets branding
- **Testing**: Perfect for quick Sheets integration demos

## 📱 Instant Send Sheets Card Example

```python
# Ready to send immediately to any Google Chat space!
result = await send_dynamic_card(
    user_google_email="your-email@gmail.com",
    space_id="spaces/AAAA1234567890",  # Use your actual space ID
    webhook_url="https://chat.googleapis.com/v1/spaces/AAAA1234567890/messages?key=your-key&token=your-token",
    card_description='''
    Create a demo card titled 'FastMCP2 Sheets Demo' with subtitle 'Instant Spreadsheet Integration Test'.
    
    Add sections:
    - 'Demo Status' section with decoratedText showing 'Data Ready' with table icon
    - 'Features' section showing Sheets integration capabilities  
    - 'Actions' section with 'View Spreadsheet' and 'Learn More' buttons
    ''',
    card_params={{
        "title": "📊 FastMCP2 Sheets Demo",
        "subtitle": "Instant Google Sheets Integration",
        "sections": [
            {{
                "header": "✅ Demo Status",
                "widgets": [
                    {{
                        "decoratedText": {{
                            "icon": {{"knownIcon": "DESCRIPTION"}},
                            "topLabel": "Integration Status",
                            "text": "<b><font color='#34a853'>Data Ready</font></b><br/>FastMCP2 Sheets integration is working perfectly",
                            "bottomLabel": "Sample spreadsheet connected"
                        }}
                    }}
                ]
            }},
            {{
                "header": "🚀 Key Features",
                "widgets": [
                    {{
                        "decoratedText": {{
                            "icon": {{"knownIcon": "ANALYTICS"}},
                            "text": "<b>✓ Real-time data access</b><br/>✓ Professional dashboard cards<br/>✓ Live Sheets integration<br/>✓ Automatic URL generation<br/>✓ Zero-config setup",
                            "bottomLabel": "Enterprise-grade spreadsheet connectivity"
                        }}
                    }}
                ]
            }},
            {{
                "header": "📊 Sample Data",
                "widgets": [
                    {{
                        "decoratedText": {{
                            "icon": {{"knownIcon": "TRENDING_UP"}},
                            "topLabel": "Demo Spreadsheet",
                            "text": "<b>Sample Financial Data</b><br/><font color='#1a73e8'>4 sheets: Summary, Revenue, Costs, Charts</font><br/><font color='#34a853'>Last updated: 2 hours ago</font>",
                            "bottomLabel": "ID: 1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"
                        }}
                    }}
                ]
            }},
            {{
                "header": "🎯 Quick Actions",
                "widgets": [
                    {{
                        "buttonList": {{
                            "buttons": [
                                {{
                                    "text": "📊 View Spreadsheet",
                                    "onClick": {{
                                        "openLink": {{
                                            "url": "https://docs.google.com/spreadsheets/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/edit"
                                        }}
                                    }},
                                    "type": "FILLED"
                                }},
                                {{
                                    "text": "📈 View Charts",
                                    "onClick": {{
                                        "openLink": {{
                                            "url": "https://docs.google.com/spreadsheets/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/edit#gid=123456"
                                        }}
                                    }},
                                    "type": "OUTLINED"
                                }},
                                {{
                                    "text": "🚀 Learn More",
                                    "onClick": {{
                                        "action": {{
                                            "function": "show_sheets_help"
                                        }}
                                    }},
                                    "type": "OUTLINED"
                                }}
                            ]
                        }}
                    }}
                ]
            }}
        ]
    }}
)

print(f"✅ Demo Sheets card sent successfully: {{result}}")
```

## 🚀 Simple & Effective Sheets Integration

### Zero Configuration Benefits
- **Instant Results**: Works immediately with any Google Sheets data
- **Professional Look**: Clean design optimized for data presentation
- **Perfect Testing**: Ideal for verifying Sheets card functionality
- **Easy Customization**: Simple to modify spreadsheet IDs and content

### Sheets-Optimized Design Features  
- **Data Branding**: Colors and styling that work well for spreadsheet data
- **Mobile Responsive**: Looks great on mobile devices with data tables
- **Fast Loading**: Optimized card structure for quick rendering
- **Cross-Sheet Compatible**: Works with any accessible spreadsheet

### Use Cases
- **Quick Demos**: Show Sheets card capabilities instantly
- **Integration Testing**: Verify Sheets API functionality
- **Prototype Development**: Rapid Sheets card template creation
- **Training Examples**: Simple examples for learning Sheets integration

## 💡 Sample Spreadsheet Integration

```python
# Example of adapting for different spreadsheets
demo_sheets = {{
    "financial_data": {{
        "id": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms",
        "name": "Q4 Financial Analysis",
        "url": "https://docs.google.com/spreadsheets/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/edit",
        "sheets": ["Summary", "Revenue", "Expenses", "Charts"]
    }},
    "sales_report": {{
        "id": "1ABC123XYZ456DEF789GHI012JKL345MNO678PQR901STU",
        "name": "Monthly Sales Dashboard", 
        "url": "https://docs.google.com/spreadsheets/d/1ABC123XYZ456DEF789GHI012JKL345MNO678PQR901STU/edit",
        "sheets": ["Overview", "Regional", "Products", "Trends"]
    }},
    "project_tracker": {{
        "id": "1DEF456GHI789JKL012MNO345PQR678STU901VWX234YZ",
        "name": "Project Status Tracker",
        "url": "https://docs.google.com/spreadsheets/d/1DEF456GHI789JKL012MNO345PQR678STU901VWX234YZ/edit", 
        "sheets": ["Timeline", "Tasks", "Resources", "Budget"]
    }}
}}

# Send to with financial data
result = await send_dynamic_card(
    card_params={{
        "title": f"📊 {{demo_sheets['financial_data']['name']}}",
        "sections": [{{
            "widgets": [{{
                "decoratedText": {{
                    "text": f"Sheets: {{', '.join(demo_sheets['financial_data']['sheets'])}}",
                    "bottomLabel": f"ID: {{demo_sheets['financial_data']['id']}}"
                }}
            }}]
        }}]
    }}
)
```

## ✨ Perfect For:
- **First-time Testing**: Verify FastMCP2 Sheets card integration
- **Client Demos**: Quick capability demonstrations with spreadsheet data
- **Development**: Test Sheets card functionality during development
- **Learning**: Understand basic Sheets card structure and data presentation

## 🎯 Integration Examples

### URL Construction
```python
# Automatic URL generation for different views
base_url = "https://docs.google.com/spreadsheets/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"
edit_view = f"{{base_url}}/edit"
specific_sheet = f"{{base_url}}/edit#gid=123456"  # Charts sheet
range_view = f"{{base_url}}/edit#gid=0&range=A1:D10"  # Summary range
```

### Data Display Patterns
```python
# Common patterns for displaying sheet data in cards
sheet_info = {{
    "name": "Q4 Financial Analysis",
    "tabs": 4,
    "last_update": "2 hours ago",
    "status": "Active"
}}

card_text = f'''
<b>{{sheet_info['name']}}</b><br/>
<font color='#1a73e8'>{{sheet_info['tabs']}} sheets available</font><br/>
<font color='#34a853'>Updated: {{sheet_info['last_update']}}</font>
'''
```

This simple prompt proves that FastMCP2 can create professional Sheets cards with zero complexity!
"""
        
        return PromptMessage(
            content=TextContent(type="text", text=simple_content),
            role="assistant"
        )

    logger.info("✅ Google Sheets prompts registered successfully")
    logger.info("   • smart_contextual_sheets_card: Advanced with real-time Sheets data")
    logger.info("   • professional_sheets_dashboard: Medium complexity professional data dashboard")
    logger.info("   • quick_sheets_card_demo: Simple zero-config instant demo")

# Export the setup function
__all__ = ['setup_gsheets_prompts']