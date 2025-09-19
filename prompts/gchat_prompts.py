"""
Google Chat Prompts for FastMCP2 - Resource-Driven Template System.

This module provides 3 comprehensive Google Chat prompts: Advanced, Medium, and Simple.
Leverages the Template Parameter Middleware to automatically populate real Chat data like
space IDs, webhook URLs, member lists, and room configurations.

Key Features:
- Advanced: Smart contextual cards using real Chat spaces and member data
- Medium: Professional dashboard cards with live Chat room integration  
- Simple: Instant demo cards for quick testing and demonstrations

Resource Integration:
- Uses {{chat://spaces/list}} for real space IDs
- Uses {{chat://spaces/{space_id}/members}} for member data
- Uses {{chat://webhooks/active}} for webhook configurations
- Uses {{user://current/profile}} for user context
"""

import logging
from typing_extensions import Optional
from datetime import datetime, timezone
from pydantic import Field
from fastmcp import FastMCP, Context
from fastmcp.prompts.prompt import Message, PromptMessage, TextContent

from config.enhanced_logging import setup_logger
logger = setup_logger()

def setup_gchat_prompts(mcp: FastMCP):
    """
    Register Google Chat prompts: Advanced, Medium, Simple.
    
    Args:
        mcp: The FastMCP server instance
    """

    # ========== ADVANCED PROMPT ==========
    @mcp.prompt(
        name="smart_contextual_chat_card",
        description="Advanced: Generate intelligent Chat cards using real space data (IDs, members, webhooks)",
        tags={"gchat", "chat", "advanced", "contextual", "dynamic", "cards"},
        meta={
            "version": "3.0",
            "author": "FastMCP2-StreamlinedChat",
            "uses_resources": True,
            "resource_dependencies": [
                "service://chat/spaces",
                "chat://spaces/list", 
                "chat://webhooks/active",
                "user://current/profile"
            ]
        }
    )
    def smart_contextual_chat_card(
        context: Context,
        card_title: str = Field(
            default="Smart Chat Dashboard",
            description="Title for the contextual Chat card"
        ),
        target_space: str = Field(
            default="team workspace",
            description="Description of the target Chat space (e.g., 'engineering team', 'project updates')"
        ),
        card_purpose: str = Field(
            default="status update",
            description="Purpose of the card (e.g., 'dashboard', 'report', 'notification', 'announcement')"
        )
    ) -> PromptMessage:
        """
        ADVANCED: Generate intelligent Google Chat cards that adapt to real space configurations.
        Uses real-time Chat space data for contextual, professional communication.
        """
        
        request_id = context.request_id
        current_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        
        # Resolve Field values
        card_title_str = str(card_title) if hasattr(card_title, 'default') else card_title
        target_space_str = str(target_space) if hasattr(target_space, 'default') else target_space
        card_purpose_str = str(card_purpose) if hasattr(card_purpose, 'default') else card_purpose
        
        advanced_content = f"""
# 🤖 Smart Contextual Google Chat Card (Advanced)
*Request ID: {request_id} | Generated: {current_time}*

## ⚡ Advanced Chat Intelligence Integration

### Configuration
- **Card Title**: {card_title_str}
- **Target Space**: {target_space_str}  
- **Purpose**: {card_purpose_str}
- **Level**: Advanced with real-time Google Chat data integration

## 📊 Step 1: Gather Real Chat Space Context

```python
# Get live Google Chat data for intelligent card generation
chat_spaces = await mcp.read_resource("service://chat/spaces")
active_webhooks = await mcp.read_resource("chat://webhooks/active")  
user_profile = await mcp.read_resource("user://current/profile")

print("🏢 Available Chat Spaces:", chat_spaces)
print("🔗 Active Webhooks:", active_webhooks)
print("👤 User Context:", user_profile)

# Extract real space data for contextual cards
chat_context = {{
    "spaces": chat_spaces,
    "webhooks": active_webhooks,
    "user": user_profile,
    "timestamp": "{current_time}",
    "request_id": "{request_id}"
}}

# Example extracted data from resources:
space_examples = {{
    "engineering_team": {{
        "space_id": "spaces/AAAA1234567890",
        "display_name": "Engineering Team",
        "member_count": 15,
        "webhook_url": "https://chat.googleapis.com/v1/spaces/AAAA1234567890/messages?key=xyz&token=abc"
    }},
    "project_alpha": {{
        "space_id": "spaces/BBBB0987654321", 
        "display_name": "Project Alpha Updates",
        "member_count": 8,
        "webhook_url": "https://chat.googleapis.com/v1/spaces/BBBB0987654321/messages?key=def&token=ghi"
    }}
}}
```

## 🎯 Step 2: Generate Context-Aware Chat Card

```python
# Advanced contextual Chat card with real space intelligence
result = await send_dynamic_card(
    user_google_email="{{{{user://current/profile}}}}['email']",
    space_id="{{{{chat://spaces/list}}}}['{target_space_str}']['space_id']",
    webhook_url="{{{{chat://webhooks/active}}}}['{target_space_str}']['webhook_url']",
    card_description='''
    Create a comprehensive {card_purpose_str} dashboard card titled '{card_title_str}' with subtitle 'Live Chat Intelligence'.
    
    Add dynamic sections using real Chat space data:
    - 'Space Status' section with decoratedText showing space info with chat icon
    - 'Team Members' section with member count using person icon  
    - 'Recent Activity' section showing latest updates with clock icon
    - 'Actions' section with context-aware buttons based on user permissions
    ''',
    card_params={{
        "title": "{card_title_str}",
        "subtitle": "🤖 Powered by Real Chat Data | {{{{chat://spaces/list}}}}['{target_space_str}']['display_name']",
        "sections": [
            {{
                "header": "📊 Space Intelligence",
                "widgets": [
                    {{
                        "decoratedText": {{
                            "icon": {{"knownIcon": "CHAT"}},
                            "topLabel": "Active Space",
                            "text": "<b>{{{{chat://spaces/list}}}}['{target_space_str}']['display_name']</b><br/><font color='#1a73e8'>Space ID: {{{{chat://spaces/list}}}}['{target_space_str}']['space_id']</font>",
                            "bottomLabel": "Connected and monitored"
                        }}
                    }}
                ]
            }},
            {{
                "header": "👥 Team Overview", 
                "widgets": [
                    {{
                        "decoratedText": {{
                            "icon": {{"knownIcon": "PERSON"}},
                            "topLabel": "Team Size",
                            "text": "<b>{{{{chat://spaces/list}}}}['{target_space_str}']['member_count'] Active Members</b><br/><font color='#34a853'>All members have access</font>",
                            "bottomLabel": "Updated automatically"
                        }}
                    }}
                ]
            }},
            {{
                "header": "🔗 Integration Status",
                "widgets": [
                    {{
                        "decoratedText": {{
                            "icon": {{"knownIcon": "SETTINGS"}},
                            "topLabel": "Webhook Status", 
                            "text": "<b><font color='#34a853'>Active & Configured</font></b><br/>Webhook URL validated and operational",
                            "bottomLabel": "Last verified: {{{{user://current/profile}}}}['last_activity']",
                            "endIcon": {{"knownIcon": "CHECK_CIRCLE"}}
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
                                    "text": "📈 View Analytics",
                                    "onClick": {{
                                        "openLink": {{
                                            "url": "https://chat.google.com/room/{{{{chat://spaces/list}}}}['{target_space_str}']['space_id']}}"
                                        }}
                                    }}
                                }},
                                {{
                                    "text": "⚙️ Manage Space",
                                    "onClick": {{
                                        "action": {{
                                            "function": "manage_chat_space",
                                            "parameters": [
                                                {{
                                                    "key": "space_id",
                                                    "value": "{{{{chat://spaces/list}}}}['{target_space_str}']['space_id']"
                                                }}
                                            ]
                                        }}
                                    }}
                                }}
                            ]
                        }}
                    }}
                ]
            }}
        ]
    }}
)

print(f"✅ Advanced contextual Chat card sent: {{result}}")
```

## 🌟 Advanced Features & Real Data Integration

### Live Chat Space Data
When the resource `service://chat/spaces` is accessed, you get real data like:
```json
{{
  "spaces": [
    {{
      "name": "spaces/AAAA1234567890",
      "displayName": "Engineering Team",
      "type": "ROOM",
      "membershipCount": 15,
      "createTime": "2024-01-15T10:30:00Z",
      "adminInstalled": true
    }},
    {{
      "name": "spaces/BBBB0987654321", 
      "displayName": "Project Alpha Updates",
      "type": "ROOM",
      "membershipCount": 8,
      "createTime": "2024-02-01T14:20:00Z",
      "adminInstalled": true
    }}
  ]
}}
```

### Webhook Configuration Data
The `chat://webhooks/active` resource returns:
```json
{{
  "webhooks": [
    {{
      "space_id": "spaces/AAAA1234567890",
      "space_name": "Engineering Team",
      "webhook_url": "https://chat.googleapis.com/v1/spaces/AAAA1234567890/messages?key=AIza...&token=abc123",
      "status": "active",
      "last_used": "2024-08-29T10:15:30Z"
    }},
    {{
      "space_id": "spaces/BBBB0987654321",
      "space_name": "Project Alpha Updates", 
      "webhook_url": "https://chat.googleapis.com/v1/spaces/BBBB0987654321/messages?key=AIza...&token=def456",
      "status": "active",
      "last_used": "2024-08-29T09:45:12Z"
    }}
  ]
}}
```

### Smart Template Resolution Examples

```python
# Template expressions that resolve automatically:
space_info = "{{{{chat://spaces/list}}}}['engineering_team']['display_name']"
# → Resolves to: "Engineering Team"

webhook_url = "{{{{chat://webhooks/active}}}}['engineering_team']['webhook_url']"
# → Resolves to: "https://chat.googleapis.com/v1/spaces/AAAA1234567890/messages?key=..."

member_count = "{{{{chat://spaces/list}}}}['engineering_team']['member_count']"
# → Resolves to: 15

user_email = "{{{{user://current/profile}}}}['email']"
# → Resolves to: "john.doe@company.com"
```

### Context-Aware Card Generation

The advanced system creates cards that:
- **Auto-populate** with real space IDs and webhook URLs
- **Display actual** member counts and space names
- **Include working links** to Chat rooms and management interfaces
- **Show current status** of webhooks and integrations
- **Adapt content** based on user permissions and space type

### Professional Integration Benefits
- **Zero Manual Configuration**: All IDs and URLs populated automatically
- **Real-time Accuracy**: Data reflects current Chat space status
- **Workflow Integration**: Cards work seamlessly with existing Chat rooms
- **Permission Awareness**: Actions adapt to user access levels
- **Scalable**: Works across multiple spaces and configurations

### Testing with Real Data
```python
# Test the advanced Chat integration
spaces_resource = await mcp.read_resource("service://chat/spaces")
print("Available Chat spaces for card generation:")
for space in spaces_resource.get('spaces', []):
    print(f"  - {{space['displayName']}} ({{space['name']}})")
    print(f"    Members: {{space.get('membershipCount', 'Unknown')}}")

# Use real space data in card content
if spaces_resource.get('spaces'):
    first_space = spaces_resource['spaces'][0]
    card_content = f"Card for {{first_space['displayName']}} with {{first_space.get('membershipCount', 0)}} members"
    print(f"Sample card content: {{card_content}}")
```

This advanced prompt showcases FastMCP2's sophisticated resource integration capabilities with real Google Chat data!
"""
        
        return PromptMessage(
            content=TextContent(type="text", text=advanced_content),
            role="assistant"
        )

    # ========== MEDIUM PROMPT ==========
    @mcp.prompt(
        name="professional_chat_dashboard",
        description="Medium: Create beautiful Chat dashboard cards with live space integration",
        tags={"gchat", "chat", "medium", "dashboard", "professional"},
        meta={
            "version": "3.0",
            "author": "FastMCP2-StreamlinedChat"
        }
    )
    def professional_chat_dashboard(
        context: Context,
        dashboard_title: str = Field(
            default="Team Dashboard",
            description="Title for the Chat dashboard card"
        ),
        team_name: str = Field(
            default="Development Team",
            description="Name of the team or group"
        ),
        dashboard_theme: str = Field(
            default="status overview",
            description="Theme of the dashboard (e.g., 'weekly report', 'project status', 'team metrics')"
        )
    ) -> PromptMessage:
        """
        MEDIUM: Generate professional Chat dashboard cards with modern design and live space data.
        Perfect balance of functionality, visual appeal, and Chat integration.
        """
        
        request_id = context.request_id
        current_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        
        # Resolve Field values
        dashboard_title_str = str(dashboard_title) if hasattr(dashboard_title, 'default') else dashboard_title
        team_name_str = str(team_name) if hasattr(team_name, 'default') else team_name
        dashboard_theme_str = str(dashboard_theme) if hasattr(dashboard_theme, 'default') else dashboard_theme
        
        medium_content = f"""
# 📊 Professional Chat Dashboard (Medium)
*Request ID: {request_id} | Generated: {current_time}*

## ✨ Professional Dashboard Features with Chat Integration

### Configuration
- **Dashboard Title**: {dashboard_title_str}
- **Team**: {team_name_str}
- **Theme**: {dashboard_theme_str}
- **Level**: Medium complexity with professional Chat space integration

## 📋 Ready-to-Send Professional Chat Dashboard

```python
# Generate beautiful professional Chat dashboard card
result = await send_dynamic_card(
    user_google_email="your-email@gmail.com",
    space_id="{{{{chat://spaces/list}}}}['primary']['space_id']",
    webhook_url="{{{{chat://webhooks/active}}}}['primary']['webhook_url']",
    card_description='''
    Create a professional {dashboard_theme_str} dashboard titled '{dashboard_title_str}' with subtitle '{team_name_str} Overview'.
    
    Add professional sections:
    - 'Team Status' section with decoratedText showing member activity with person icon
    - 'Key Metrics' section with performance indicators using chart icon  
    - 'Recent Updates' section displaying latest activities with clock icon
    - 'Quick Actions' section with professional action buttons
    ''',
    card_params={{
        "title": "{dashboard_title_str}",
        "subtitle": "📊 {team_name_str} • Live Dashboard",
        "sections": [
            {{
                "header": "👥 Team Status",
                "widgets": [
                    {{
                        "decoratedText": {{
                            "icon": {{"knownIcon": "PERSON"}},
                            "topLabel": "Active Members",
                            "text": "<b>{{{{chat://spaces/list}}}}['primary']['member_count'] Team Members</b><br/><font color='#34a853'>{{{{chat://spaces/list}}}}['primary']['active_today'] active today</font>",
                            "bottomLabel": "Space: {{{{chat://spaces/list}}}}['primary']['display_name']"
                        }}
                    }}
                ]
            }},
            {{
                "header": "📈 Key Metrics",
                "collapsible": false,
                "widgets": [
                    {{
                        "decoratedText": {{
                            "icon": {{"knownIcon": "DESCRIPTION"}},
                            "topLabel": "Activity Summary",
                            "text": "<b><font color='#1a73e8'>High Engagement</font></b><br/>15 messages today • 8 participants<br/><font color='#34a853'>↑ 25% from yesterday</font>",
                            "bottomLabel": "Trending upward"
                        }}
                    }},
                    {{
                        "decoratedText": {{
                            "icon": {{"knownIcon": "STAR"}},
                            "topLabel": "Team Performance",
                            "text": "<b>Excellent Rating</b><br/><font color='#34a853'>4.8/5.0 collaboration score</font><br/>Based on recent project deliveries",
                            "bottomLabel": "Updated hourly"
                        }}
                    }}
                ]
            }},
            {{
                "header": "🕒 Recent Activity", 
                "widgets": [
                    {{
                        "decoratedText": {{
                            "icon": {{"knownIcon": "CLOCK"}},
                            "topLabel": "Latest Updates",
                            "text": "<b>Sarah Chen</b> shared project milestone<br/><b>Mike Johnson</b> updated sprint board<br/><b>Lisa Wang</b> completed code review",
                            "bottomLabel": "Last 2 hours • Space activity feed"
                        }}
                    }}
                ]
            }},
            {{
                "header": "🚀 Quick Actions",
                "widgets": [
                    {{
                        "buttonList": {{
                            "buttons": [
                                {{
                                    "text": "📊 View Full Dashboard",
                                    "onClick": {{
                                        "openLink": {{
                                            "url": "https://chat.google.com/room/{{{{chat://spaces/list}}}}['primary']['space_id']}}"
                                        }}
                                    }},
                                    "type": "FILLED"
                                }},
                                {{
                                    "text": "⚙️ Team Settings",
                                    "onClick": {{
                                        "action": {{
                                            "function": "open_team_settings"
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

print(f"✅ Professional Chat dashboard sent: {{result}}")
```

## 🎨 Dashboard Design Highlights

### Visual Excellence
- **Professional Layout**: Clean sections with logical information hierarchy
- **Live Data Integration**: Real space member counts and activity feeds
- **Modern Icons**: Contextual icons that enhance readability
- **Status Indicators**: Color-coded metrics with trend information

### Chat-Specific Features  
- **Space Awareness**: Automatically includes space names and IDs
- **Member Context**: Shows actual member counts and activity
- **Working Links**: Direct links to Chat rooms and interfaces
- **Action Buttons**: Context-aware actions based on Chat permissions

### Content Structure
- **Team Status**: Live member count and activity indicators
- **Key Metrics**: Performance indicators with trend analysis
- **Recent Activity**: Real-time feed of space activities
- **Quick Actions**: Direct access to common Chat functions

### Technical Integration
- **Space ID Resolution**: `{{{{chat://spaces/list}}}}['primary']['space_id']` 
- **Member Count**: `{{{{chat://spaces/list}}}}['primary']['member_count']`
- **Webhook URLs**: `{{{{chat://webhooks/active}}}}['primary']['webhook_url']`
- **Display Names**: `{{{{chat://spaces/list}}}}['primary']['display_name']`

## 📊 Perfect For:
- **Team Updates**: Regular status updates with live data
- **Project Dashboards**: Visual project overviews with Chat integration
- **Management Reports**: Executive summaries with team metrics  
- **Daily Standups**: Quick team status cards with real activity

This medium-complexity prompt delivers professional Chat dashboards with smart space integration!
"""
        
        return PromptMessage(
            content=TextContent(type="text", text=medium_content),
            role="assistant"
        )

    # ========== SIMPLE PROMPT ==========
    @mcp.prompt(
        name="quick_chat_card_demo",
        description="Simple: Zero-config instant Chat card demo - ready to send immediately",
        tags={"gchat", "chat", "simple", "demo", "instant", "cards"},
        meta={
            "version": "3.0",
            "author": "FastMCP2-StreamlinedChat"
        }
    )
    def quick_chat_card_demo(context: Context) -> PromptMessage:
        """
        SIMPLE: Zero-configuration Chat card demo. Perfect for instant testing and demonstrations.
        No parameters needed - works immediately out of the box with sample space data.
        """
        
        request_id = context.request_id
        current_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        
        simple_content = f"""
# ⚡ Quick Chat Card Demo (Simple)
*Request ID: {request_id} | Generated: {current_time}*

## 🎯 Zero-Configuration Chat Card Demo

### Features
- **Level**: Simple - No parameters required
- **Ready**: Instant send to any Chat space
- **Design**: Clean and professional with Chat branding
- **Testing**: Perfect for quick Chat integration demos

## 📱 Instant Send Chat Card Example

```python
# Ready to send immediately to any Google Chat space!
result = await send_dynamic_card(
    user_google_email="your-email@gmail.com",
    space_id="spaces/AAAA1234567890",  # Use your actual space ID
    webhook_url="https://chat.googleapis.com/v1/spaces/AAAA1234567890/messages?key=your-key&token=your-token",
    card_description='''
    Create a demo card titled 'FastMCP2 Chat Demo' with subtitle 'Instant Integration Test'.
    
    Add sections:
    - 'Demo Status' section with decoratedText showing 'System Ready' with check circle icon
    - 'Features' section showing integration capabilities  
    - 'Actions' section with 'Learn More' and 'Get Started' buttons
    ''',
    card_params={{
        "title": "⚡ FastMCP2 Chat Demo",
        "subtitle": "Instant Google Chat Integration",
        "sections": [
            {{
                "header": "✅ Demo Status",
                "widgets": [
                    {{
                        "decoratedText": {{
                            "icon": {{"knownIcon": "CHECK_CIRCLE"}},
                            "topLabel": "Integration Status",
                            "text": "<b><font color='#34a853'>System Ready</font></b><br/>FastMCP2 Chat integration is working perfectly",
                            "bottomLabel": "All systems operational"
                        }}
                    }}
                ]
            }},
            {{
                "header": "🚀 Key Features",
                "widgets": [
                    {{
                        "decoratedText": {{
                            "icon": {{"knownIcon": "STAR"}},
                            "text": "<b>✓ Zero-config setup</b><br/>✓ Professional card design<br/>✓ Real-time Chat integration<br/>✓ Cross-platform compatibility",
                            "bottomLabel": "Ready to use immediately"
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
                                    "text": "📚 Learn More",
                                    "onClick": {{
                                        "openLink": {{
                                            "url": "https://github.com/fastmcp/fastmcp2"
                                        }}
                                    }},
                                    "type": "FILLED"
                                }},
                                {{
                                    "text": "🚀 Get Started",
                                    "onClick": {{
                                        "action": {{
                                            "function": "start_setup"
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

print(f"✅ Demo Chat card sent successfully: {{result}}")
```

## 🚀 Simple & Effective Chat Integration

### Zero Configuration Benefits
- **Instant Results**: Works immediately in any Google Chat space
- **Professional Look**: Clean design optimized for Chat interface
- **Perfect Testing**: Ideal for verifying Chat card functionality
- **Easy Customization**: Simple to modify space IDs and content

### Chat-Optimized Design Features  
- **Chat Branding**: Colors and styling that work well in Google Chat
- **Mobile Responsive**: Looks great on mobile Chat apps
- **Fast Loading**: Optimized card structure for quick Chat rendering
- **Cross-Space Compatible**: Works in DMs, rooms, and spaces

### Use Cases
- **Quick Demos**: Show Chat card capabilities instantly
- **Integration Testing**: Verify Chat webhook functionality
- **Prototype Development**: Rapid Chat card template creation
- **Training Examples**: Simple examples for learning Chat cards

## 💡 Sample Space Integration

```python
# Example of adapting for different Chat spaces
demo_spaces = {{
    "engineering": {{
        "space_id": "spaces/AAAA1234567890",
        "webhook": "https://chat.googleapis.com/v1/spaces/AAAA1234567890/messages?key=abc&token=123"
    }},
    "marketing": {{
        "space_id": "spaces/BBBB0987654321", 
        "webhook": "https://chat.googleapis.com/v1/spaces/BBBB0987654321/messages?key=def&token=456"
    }},
    "general": {{
        "space_id": "spaces/CCCC1122334455",
        "webhook": "https://chat.googleapis.com/v1/spaces/CCCC1122334455/messages?key=ghi&token=789"
    }}
}}

# Send to engineering space
result = await send_dynamic_card(
    space_id=demo_spaces["engineering"]["space_id"],
    webhook_url=demo_spaces["engineering"]["webhook"],
    # ... rest of card parameters
)
```

## ✨ Perfect For:
- **First-time Testing**: Verify FastMCP2 Chat card integration
- **Client Demos**: Quick capability demonstrations in Chat rooms
- **Development**: Test Chat card functionality during development
- **Learning**: Understand basic Chat card structure and deployment

This simple prompt proves that FastMCP2 can create professional Chat cards with zero complexity!
"""
        
        return PromptMessage(
            content=TextContent(type="text", text=simple_content),
            role="assistant"
        )

    logger.info("✅ Google Chat prompts registered successfully")
    logger.info("   • smart_contextual_chat_card: Advanced with real-time Chat space data")
    logger.info("   • professional_chat_dashboard: Medium complexity professional dashboard")
    logger.info("   • quick_chat_card_demo: Simple zero-config instant demo")

# Export the setup function
__all__ = ['setup_gchat_prompts']