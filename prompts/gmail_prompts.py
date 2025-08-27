"""
Gmail-related prompts for FastMCP2 server.

This module provides comprehensive prompt templates for Gmail operations,
helping users compose emails, search effectively, manage labels, and work with filters.
Based on successful usage patterns including advanced HTML email generation.
"""

import logging
from typing import Optional, List, Literal
from pydantic import Field
from fastmcp import FastMCP, Context
from fastmcp.prompts.prompt import Message, PromptMessage, TextContent

logger = logging.getLogger(__name__)


def setup_gmail_prompts(mcp: FastMCP):
    """
    Register all Gmail prompts with the FastMCP server.
    
    Args:
        mcp: The FastMCP server instance
    """

    @mcp.prompt(
        name="compose_html_email",
        description="Generate sophisticated HTML email with professional styling, gradients, buttons, and mixed content using dynamic workspace content",
        tags={"gmail", "email", "html", "styling", "professional", "dynamic", "workspace"},
        meta={"version": "2.0", "author": "FastMCP2-Gmail"}
    )
    def compose_html_email(
        context: Context,
        email_purpose: str = Field(
            default="business_communication",
            description="Purpose of the email (business_communication, marketing, notification, newsletter, etc.)"
        ),
        recipient_type: str = Field(
            default="professional",
            description="Type of recipient (professional, client, team, customer, etc.)"
        ),
        main_message: str = Field(
            default="Important project update with next steps",
            description="The main message or content to convey in the email"
        ),
        branding_colors: str = Field(
            default="#667eea,#764ba2",
            description="Comma-separated hex colors for gradients and branding (e.g., '#667eea,#764ba2')"
        ),
        include_call_to_action: bool = Field(
            default=True,
            description="Include a call-to-action button in the email"
        ),
        cta_text: str = Field(
            default="View Details",
            description="Text for the call-to-action button"
        ),
        cta_url: str = Field(
            default="https://example.com",
            description="URL for the call-to-action button"
        ),
        company_name: str = Field(
            default="Your Company",
            description="Company or sender name for branding"
        ),
        email_tone: str = Field(
            default="professional_friendly",
            description="Tone of the email (professional_friendly, formal, casual, urgent, celebratory)"
        ),
        include_workspace_content: bool = Field(
            default=True,
            description="Include dynamic content from user's Google Workspace (Docs, Sheets, Drive files)"
        ),
        content_search_query: str = Field(
            default="",
            description="Optional search query to find specific workspace content to include"
        ),
        include_technical_details: bool = Field(
            default=False,
            description="Include technical implementation details in the email"
        )
    ) -> PromptMessage:
        """
        Generate professional HTML email with advanced styling, gradients, and interactive elements.
        Now enhanced with dynamic workspace content integration and user context awareness.
        """
        
        request_id = context.request_id
        
                # Resolve Field values to strings
        branding_colors_str = str(branding_colors) if hasattr(branding_colors, 'default') else branding_colors
        email_purpose_str = str(email_purpose) if hasattr(email_purpose, 'default') else email_purpose
        recipient_type_str = str(recipient_type) if hasattr(recipient_type, 'default') else recipient_type
        email_tone_str = str(email_tone) if hasattr(email_tone, 'default') else email_tone
        company_name_str = str(company_name) if hasattr(company_name, 'default') else company_name
        
        # Parse branding colors
        colors = [c.strip() for c in branding_colors_str.split(',')]
        primary_color = colors[0] if colors else "#667eea"
        secondary_color = colors[1] if len(colors) > 1 else "#764ba2"
        
        # Generate tone-appropriate content
        tone_mapping = {
            "professional_friendly": "professional yet approachable",
            "formal": "formal and respectful",
            "casual": "casual and friendly",
            "urgent": "urgent and action-oriented",
            "celebratory": "celebratory and enthusiastic"
        }
        tone_description = tone_mapping.get(email_tone_str, "professional")
        
        # Create comprehensive email template with resource integration
        email_guide = f"""
# Professional HTML Email Template Generator (Enhanced)
*Request ID: {request_id}*

## Email Configuration
- **Purpose**: {email_purpose_str.replace('_', ' ').title()}
- **Recipient Type**: {recipient_type_str.title()}
- **Tone**: {tone_description.title()}
- **Branding**: {primary_color} → {secondary_color} gradient
- **CTA Included**: {'Yes' if include_call_to_action else 'No'}
- **Workspace Integration**: {'Enabled' if include_workspace_content else 'Disabled'}

## 🔗 Resource Integration Setup

### Step 1: Get User Context & Recent Content
```python
# Get authenticated user information
user_profile = await mcp.get_resource("user://current/profile")
user_email = user_profile["email"]

{"# Get recent workspace content for dynamic suggestions" if include_workspace_content else "# Workspace content disabled"}
{f'recent_content = await mcp.get_resource("workspace://content/recent")' if include_workspace_content else ""}

{"# Get Gmail-specific content suggestions" if include_workspace_content else ""}
{f'content_suggestions = await mcp.get_resource("gmail://content/suggestions")' if include_workspace_content else ""}

{f'# Search for specific content if query provided: "{content_search_query}"' if content_search_query else "# No specific content search"}
{f'search_results = await mcp.get_resource("workspace://content/search/{content_search_query}")' if content_search_query else ""}
```

### Step 2: Dynamic Content Variables
```python
# Extract dynamic content for email personalization
dynamic_vars = {{
    "user_email": user_email,
    "user_name": user_email.split('@')[0].replace('.', ' ').title(),
    "user_domain": user_email.split('@')[1],
    "current_date": datetime.now().strftime("%B %d, %Y"),
}}

{f'''# Recent workspace files for email content
recent_docs = recent_content.get("content_by_type", {{}}).get("documents", [])[:3]
recent_sheets = recent_content.get("content_by_type", {{}}).get("spreadsheets", [])[:3]
recent_presentations = recent_content.get("content_by_type", {{}}).get("presentations", [])[:2]

# Quick links for email body
quick_links = [
    {{"name": doc["name"], "url": doc["web_view_link"]}}
    for doc in (recent_docs + recent_sheets + recent_presentations)
]''' if include_workspace_content else '# Workspace content integration disabled'}
```

## Generated Email Structure

### Enhanced Parameters for send_gmail_message():
```json
{{
  "user_google_email": "{{dynamic_vars['user_email']}}",
  "to": "{{recipient_email}}",
  "subject": "{email_purpose_str.replace('_', ' ').title()} - {{dynamic_vars['user_domain'].replace('.com', '').title()}}",
  "body": "{{plain_text_version}}",
  "content_type": "mixed",
  "html_body": "{{enhanced_html_content}}"
}}
```

### Alternative: Create Draft Instead (draft_gmail_message):
```json
{{
  "user_google_email": "{{dynamic_vars['user_email']}}",
  "subject": "{email_purpose_str.replace('_', ' ').title()} - {{dynamic_vars['user_domain'].replace('.com', '').title()}}",
  "body": "{{plain_text_version}}",
  "to": "{{recipient_email}}",
  "content_type": "mixed",
  "html_body": "{{enhanced_html_content}}"
}}
```

### Complete HTML Body Content:
```html
<html>
<head>
<style>
body {{ 
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, Arial, sans-serif; 
    line-height: 1.6; 
    color: #333; 
    margin: 0; 
    padding: 20px;
    background-color: #f5f5f5;
}}
.email-container {{
    max-width: 600px;
    margin: 0 auto;
    background: white;
    border-radius: 12px;
    overflow: hidden;
    box-shadow: 0 4px 20px rgba(0,0,0,0.1);
}}
.header {{ 
    background: linear-gradient(135deg, {primary_color} 0%, {secondary_color} 100%); 
    color: white; 
    padding: 30px 20px; 
    text-align: center; 
    border-radius: 12px 12px 0 0;
}}
.header h1 {{
    margin: 0;
    font-size: 28px;
    font-weight: 600;
    text-shadow: 0 2px 4px rgba(0,0,0,0.2);
}}
.header p {{
    margin: 10px 0 0 0;
    opacity: 0.9;
    font-size: 16px;
}}
.content {{ 
    padding: 30px; 
    background: white;
}}
.highlight {{ 
    background: linear-gradient(120deg, #fff3cd 0%, #ffeaa7 100%); 
    padding: 15px; 
    border-radius: 8px; 
    border-left: 4px solid {primary_color};
    margin: 20px 0;
}}
.success {{ 
    color: #28a745; 
    font-weight: 600;
    display: inline-flex;
    align-items: center;
}}
.success::before {{
    content: "✅";
    margin-right: 8px;
}}
.info-section {{
    background: #f8f9fa;
    padding: 20px;
    border-radius: 8px;
    margin: 20px 0;
    border: 1px solid #e9ecef;
}}
.button {{ 
    display: inline-block; 
    background: linear-gradient(135deg, {primary_color} 0%, {secondary_color} 100%);
    color: white !important; 
    padding: 15px 30px; 
    text-decoration: none; 
    border-radius: 25px; 
    margin: 15px 0;
    font-weight: 600;
    text-align: center;
    transition: all 0.3s ease;
    box-shadow: 0 4px 15px rgba(102, 126, 234, 0.3);
}}
.button:hover {{
    transform: translateY(-2px);
    box-shadow: 0 6px 20px rgba(102, 126, 234, 0.4);
}}
.tech-details {{
    background: #f1f3f4;
    padding: 15px;
    border-radius: 6px;
    font-family: 'Courier New', monospace;
    font-size: 14px;
    border-left: 3px solid {primary_color};
    margin: 20px 0;
}}
.footer {{
    background: #f8f9fa;
    padding: 20px;
    text-align: center;
    color: #6c757d;
    border-top: 1px solid #e9ecef;
}}
.feature-list {{
    list-style: none;
    padding: 0;
}}
.feature-list li {{
    padding: 8px 0;
    border-bottom: 1px solid #f0f0f0;
}}
.feature-list li:before {{
    content: "🎯";
    margin-right: 10px;
}}
.stats-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: 15px;
    margin: 20px 0;
}}
.stat-card {{
    background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
    padding: 15px;
    border-radius: 8px;
    text-align: center;
    border: 1px solid #dee2e6;
}}
.stat-number {{
    font-size: 24px;
    font-weight: bold;
    color: {primary_color};
}}
.stat-label {{
    font-size: 12px;
    color: #6c757d;
    text-transform: uppercase;
}}
</style>
</head>
<body>
<div class="email-container">
  <div class="header">
    <h1>🎉 {email_purpose_str.replace('_', ' ').title()}</h1>
    <p>{company_name_str} - Excellence in Communication</p>
  </div>

  <div class="content">
    <h2>Hello!</h2>
    <p>Hope this message finds you well. {main_message}</p>

    <div class="highlight">
      <strong>Key Highlights:</strong>
      <ul class="feature-list">
        <li><strong>Professional Design:</strong> Clean, modern layout with gradient styling</li>
        <li><strong>Multi-Device Support:</strong> Responsive design for all devices</li>
        <li><strong>Brand Consistency:</strong> {company_name_str} branded experience</li>
        <li><strong>Interactive Elements:</strong> Professional call-to-action buttons</li>
      </ul>
    </div>

    <div class="stats-grid">
      <div class="stat-card">
        <div class="stat-number">100%</div>
        <div class="stat-label">Professional</div>
      </div>
      <div class="stat-card">
        <div class="stat-number">Fast</div>
        <div class="stat-label">Delivery</div>
      </div>
      <div class="stat-card">
        <div class="stat-number">24/7</div>
        <div class="stat-label">Support</div>
      </div>
    </div>

    <div class="info-section">
      <h3>📧 Content Details</h3>
      <p><strong>Email Type:</strong> {email_purpose_str.replace('_', ' ').title()}</p>
      <p><strong>Audience:</strong> {recipient_type_str.title()}</p>
      <p><strong>Content Type:</strong> Mixed (HTML + Plain Text)</p>
      <p><strong>Delivery Method:</strong> FastMCP2 Gmail Integration</p>
    </div>

    {f'''<div class="tech-details">
      <h4>⚡ Technical Implementation</h4>
      <p><strong>From:</strong> {sender_email}</p>
      <p><strong>To:</strong> {recipient_email}</p>
      <p><strong>Content-Type:</strong> multipart/alternative</p>
      <p><strong>Styling:</strong> Embedded CSS with gradient support</p>
      <p><strong>Compatibility:</strong> Gmail, Outlook, Apple Mail optimized</p>
    </div>''' if include_technical_details else ''}

    {f'''<div style="text-align: center; margin: 30px 0;">
      <a href="{cta_url}" class="button">{cta_text}</a>
    </div>''' if include_call_to_action else ''}

    <div class="success">
      Successfully generated with FastMCP2 advanced capabilities!
    </div>

    <hr style="margin: 30px 0; border: none; height: 2px; background: linear-gradient(to right, {primary_color}, {secondary_color});">

  </div>

  <div class="footer">
    <p><small>This email was crafted with ❤️ using FastMCP2 Gmail Integration.<br>
    Featuring advanced HTML styling, responsive design, and professional branding.</small></p>
  </div>
</div>
</body>
</html>
```

## Implementation Example

### Using the Generated Template - Send Immediately:
```python
# Send the email using FastMCP2 Gmail tools
await send_gmail_message(
    user_google_email="{sender_email}",
    to="{recipient_email}",
    subject="{email_purpose_str.replace('_', ' ').title()} - {company_name_str}",
    body="This is the plain text version of the email for clients that don't support HTML.\\n\\nThe HTML version should display with formatting, colors, and styling.\\n\\n{main_message}",
    content_type="mixed",
    html_body="{{FULL_HTML_CONTENT_FROM_ABOVE}}"
)
```

### Alternative: Create as Draft First:
```python
# Create draft using FastMCP2 Gmail tools (note different parameter order)
await draft_gmail_message(
    user_google_email="{sender_email}",
    subject="{email_purpose_str.replace('_', ' ').title()} - {company_name_str}",
    body="This is the plain text version of the email for clients that don't support HTML.\\n\\nThe HTML version should display with formatting, colors, and styling.\\n\\n{main_message}",
    to="{recipient_email}",  # Optional for drafts
    content_type="mixed",
    html_body="{{FULL_HTML_CONTENT_FROM_ABOVE}}"
)
```

## 📅 Advanced Calendar Integration

### Google Calendar "Add Event" URL Format:
```python
# Dynamic calendar event URL generation
def generate_calendar_url(event_title, start_datetime, end_datetime, description="", location="", timezone="UTC"):
    base_url = "https://www.google.com/calendar/render"
    params = {{
        "action": "TEMPLATE",
        "text": event_title,
        "dates": f"{{start_datetime}}/{{end_datetime}}",  # Format: 20241225T120000Z
        "details": description,
        "location": location,
        "ctz": timezone
    }}
    return f"{{base_url}}?{{'&'.join([f'{{k}}={{v}}' for k, v in params.items()])}}"

# Example usage:
meeting_url = generate_calendar_url(
    event_title="Team Meeting - Q4 Planning",
    start_datetime="20241225T140000Z",
    end_datetime="20241225T150000Z",
    description="Quarterly planning session with team leads",
    location="Conference Room A",
    timezone="America/New_York"
)
```

### Multi-Platform Calendar Integration HTML:
```html
<div style="background: #f8f9fa; padding: 20px; border-radius: 8px; margin: 20px 0; border-left: 4px solid {primary_color};">
    <h3 style="margin: 0 0 15px 0; color: {primary_color};">📅 Save This Event</h3>
    <div style="display: flex; gap: 10px; flex-wrap: wrap;">
        <a href="{{google_calendar_url}}"
           style="display: inline-block; background: #4285f4; color: white; padding: 10px 20px;
                  text-decoration: none; border-radius: 5px; font-weight: 500;">
            📅 Google Calendar
        </a>
        <a href="{{outlook_calendar_url}}"
           style="display: inline-block; background: #0078d4; color: white; padding: 10px 20px;
                  text-decoration: none; border-radius: 5px; font-weight: 500;">
            📅 Outlook
        </a>
        <a href="{{ics_download_url}}"
           style="display: inline-block; background: #28a745; color: white; padding: 10px 20px;
                  text-decoration: none; border-radius: 5px; font-weight: 500;">
            📥 Download ICS
        </a>
    </div>
    <p style="margin: 15px 0 0 0; font-size: 12px; color: #666;">
        Choose your preferred calendar app to automatically add this event
    </p>
</div>
```

### ICS File Generation (Best Practice):
```python
def generate_ics_content(event_title, start_datetime, end_datetime, description="", location=""):
    ics_content = f'''BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//FastMCP2//Gmail Integration//EN
BEGIN:VEVENT
UID:{{uuid.uuid4()}}@fastmcp2.com
DTSTART:{{start_datetime}}
DTEND:{{end_datetime}}
SUMMARY:{{event_title}}
DESCRIPTION:{{description}}
LOCATION:{{location}}
STATUS:CONFIRMED
SEQUENCE:0
END:VEVENT
END:VCALENDAR'''
    return ics_content

# Create downloadable ICS file
ics_data = generate_ics_content(
    event_title="Team Meeting - Q4 Planning",
    start_datetime="20241225T140000Z",
    end_datetime="20241225T150000Z",
    description="Quarterly planning session",
    location="Conference Room A"
)
```

### Calendar Integration Best Practices:
1. **Multiple Options**: Always provide Google Calendar + ICS file options
2. **Clear CTAs**: Use recognizable calendar icons and clear button text
3. **Event Details**: Include all relevant information (title, time, location, description)
4. **Timezone Handling**: Specify timezone or use UTC with clear conversion
5. **Mobile-Friendly**: Ensure calendar links work on mobile devices
6. **Fallback Options**: Provide manual event details if links fail

## Customization Options

### Color Schemes:
- **Professional Blue**: `{primary_color}, {secondary_color}`
- **Corporate Green**: `#28a745, #20c997`
- **Modern Purple**: `#6f42c1, #e83e8c`
- **Elegant Gray**: `#495057, #6c757d`

### Tone Variations:
- **Current Tone**: {tone_description}
- **Alternative Approaches**: Formal, casual, urgent, celebratory

### Content Sections:
- Header with gradient branding
- Main content area with highlighting
- Statistics grid for key metrics
- Technical details (optional)
- Call-to-action button
- Professional footer
- **NEW**: Multi-platform calendar integration

This template demonstrates advanced HTML email capabilities with mixed content support, professional styling, comprehensive branding options, and seamless calendar integration.
"""
        
        return PromptMessage(
            content=TextContent(type="text", text=email_guide),
            role="assistant"
        )

    @mcp.prompt(
        name="gmail_search_optimizer",
        description="Generate effective Gmail search queries and organization strategies",
        tags={"gmail", "search", "organization", "productivity"},
        meta={"version": "1.0", "author": "FastMCP2-Gmail"}
    )
    def gmail_search_optimizer(
        context: Context,
        search_goal: str = Field(
            default="find_project_emails",
            description="What you're trying to find (find_project_emails, locate_attachments, filter_by_sender, etc.)"
        ),
        time_range: str = Field(
            default="last_month",
            description="Time range for search (today, yesterday, last_week, last_month, last_year, specific_date)"
        ),
        email_type: str = Field(
            default="any",
            description="Type of emails to find (any, with_attachments, unread, important, starred, from_specific_sender)"
        ),
        keywords: str = Field(
            default="",
            description="Comma-separated keywords to include in search"
        ),
        sender_domain: str = Field(
            default="",
            description="Specific sender domain to filter by (e.g., 'company.com')"
        ),
        exclude_terms: str = Field(
            default="",
            description="Comma-separated terms to exclude from search"
        ),
        advanced_filters: bool = Field(
            default=True,
            description="Include advanced Gmail search operators and techniques"
        )
    ) -> PromptMessage:
        """
        Generate comprehensive Gmail search strategies with advanced operators and organization tips.
        """
        
        request_id = context.request_id
        
        # Resolve Field values to strings
        keywords_str = str(keywords) if hasattr(keywords, 'default') else keywords
        exclude_terms_str = str(exclude_terms) if hasattr(exclude_terms, 'default') else exclude_terms
        
        # Parse keywords and exclusions
        keyword_list = [k.strip() for k in keywords_str.split(',') if k.strip()]
        exclude_list = [e.strip() for e in exclude_terms_str.split(',') if e.strip()]
        
        # Generate time-specific operators
        time_operators = {
            "today": "newer_than:1d",
            "yesterday": "older_than:1d newer_than:2d", 
            "last_week": "newer_than:7d",
            "last_month": "newer_than:1m",
            "last_year": "newer_than:1y",
            "specific_date": "after:YYYY/MM/DD before:YYYY/MM/DD"
        }
        
        time_query = time_operators.get(time_range, "newer_than:1m")
        
        # Resolve more Field values to strings
        search_goal_str = str(search_goal) if hasattr(search_goal, 'default') else search_goal
        time_range_str = str(time_range) if hasattr(time_range, 'default') else time_range
        email_type_str = str(email_type) if hasattr(email_type, 'default') else email_type
        sender_domain_str = str(sender_domain) if hasattr(sender_domain, 'default') else sender_domain
        
        search_guide = f"""
# Gmail Search Optimization Guide
*Request ID: {request_id}*

## Search Configuration
- **Goal**: {search_goal_str.replace('_', ' ').title()}
- **Time Range**: {time_range_str.replace('_', ' ').title()}
- **Email Type**: {email_type_str.replace('_', ' ').title()}
- **Keywords**: {', '.join(keyword_list) if keyword_list else 'None specified'}
- **Exclude**: {', '.join(exclude_list) if exclude_list else 'None'}

## Optimized Search Query

### Basic Query for Your Goal:
```python
# Basic search query construction
query_parts = []
if keyword_list:
    query_parts.append(' OR '.join(f'"{k}"' for k in keyword_list))
if sender_domain_str:
    query_parts.append(f"from:{sender_domain_str}")
if email_type_str == "with_attachments":
    query_parts.append("has:attachment")
elif email_type_str == "unread":
    query_parts.append("is:unread")
elif email_type_str == "important":
    query_parts.append("is:important")
query_parts.append("{time_query}")
if exclude_list:
    query_parts.extend(f"-{exc}" for exc in exclude_list)

basic_query = ' '.join(query_parts)
```

### Advanced Query with Operators:
```python
# Advanced search with goal-specific logic
if "{search_goal_str}" == "find_project_emails":
    base = '(project OR milestone OR deliverable OR "status update")'
elif "{search_goal_str}" == "locate_attachments":
    base = 'has:attachment (filename:pdf OR filename:doc OR filename:xlsx)'
elif "{search_goal_str}" == "filter_by_sender":
    base = f'from:{sender_domain_str if sender_domain_str else "important-sender.com"}'
else:
    base = ' OR '.join(f'"{k}"' for k in keyword_list) if keyword_list else 'important'
    
advanced_query = f"({base}) {time_query}"
if email_type_str == "with_attachments":
    advanced_query += " has:attachment"
elif email_type_str == "unread":
    advanced_query += " is:unread"
if exclude_list:
    advanced_query += " " + " ".join(f"-{exc}" for exc in exclude_list)
```

## Gmail Search Operators Reference

### Time-Based Filters:
- `newer_than:1d` - Emails from last 24 hours
- `older_than:1w` - Emails older than 1 week
- `after:2024/01/01` - Emails after specific date
- `before:2024/12/31` - Emails before specific date

### Content Filters:
- `has:attachment` - Emails with any attachments
- `filename:pdf` - Emails with PDF attachments
- `has:drive` - Emails with Google Drive links
- `has:youtube` - Emails with YouTube links

### Sender/Recipient Filters:
- `from:sender@domain.com` - From specific sender
- `to:recipient@domain.com` - To specific recipient
- `cc:person@domain.com` - CC'd to someone
- `list:mailing-list` - From mailing lists

### Status Filters:
- `is:unread` - Unread emails
- `is:important` - Important emails
- `is:starred` - Starred emails
- `is:snoozed` - Snoozed emails

### Label and Category Filters:
- `label:work` - Emails with 'work' label
- `category:social` - Social category emails
- `category:updates` - Update notifications
- `category:promotions` - Promotional emails

### Advanced Operators:
- `"exact phrase"` - Exact phrase search
- `word1 OR word2` - Either word
- `word1 AND word2` - Both words
- `-exclude` - Exclude this term
- `subject:keyword` - Keyword in subject
- `size:10M` - Emails larger than 10MB

## Use Case Examples

### Finding Project Emails:
```
(project OR "project name" OR milestone) {time_query} {'-spam -trash' if exclude_list else ''}
```

### Locating Attachments:
```
has:attachment filename:pdf OR filename:doc OR filename:xlsx {time_query}
```

### Filtering by Importance:
```
is:important from:{sender_domain if sender_domain else 'important-domain.com'} {time_query}
```

### Finding Large Emails:
```
size:5M {time_query} has:attachment
```

## Organization Strategy

### Step 1: Use Optimized Search
1. Start with the basic query above
2. Refine using advanced operators
3. Save useful searches as filters

### Step 2: Label Management
```python
# Create labels for organization
await manage_gmail_label(
    user_google_email="your@email.com",
    action="create", 
    name="Project-{search_goal.replace('_', '-').title()}",
    background_color="#4285f4",
    text_color="#ffffff"
)
```

### Step 3: Filter Creation
```python
# Auto-organize future emails
await create_gmail_filter(
    user_google_email="your@email.com",
    query="{{OPTIMIZED_QUERY_FROM_ABOVE}}",
    add_label_ids=["LABEL_ID_FROM_STEP_2"],
    mark_as_important=True
)
```

### Step 4: Batch Processing
```python
# Process found emails
search_results = await search_gmail_messages(
    user_google_email="your@email.com",
    query="{{OPTIMIZED_QUERY}}",
    page_size=50
)

# Get content for analysis
email_content = await get_gmail_messages_content_batch(
    user_google_email="your@email.com", 
    message_ids=[msg_id for msg_id in search_results]
)
```

## Advanced Techniques

### Complex Boolean Logic:
```
(urgent OR priority) AND (project OR client) -spam -newsletter {time_query}
```

### Date Range Combinations:
```
after:2024/01/01 before:2024/06/30 has:attachment size:1M
```

### Multi-Criteria Search:
```
from:({sender_domain}) subject:(report OR update OR status) has:attachment newer_than:7d
```

## Productivity Tips

### 1. Save Frequent Searches
- Create Gmail filters for recurring searches
- Use labels to categorize automatically
- Set up notifications for important matches

### 2. Search Refinement Process
1. Start broad, then narrow down
2. Use exclusions to filter noise
3. Combine multiple operators for precision
4. Test queries before creating filters

### 3. Batch Operations
- Use search results for bulk label application
- Archive or delete in batches
- Export search results for external processing

This search optimization guide leverages Gmail's powerful query language to help you find exactly what you're looking for efficiently.
"""
        
        return PromptMessage(
            content=TextContent(type="text", text=search_guide),
            role="assistant"
        )

    def _generate_basic_query(self, goal, time_query, email_type, keywords, sender_domain, exclusions):
        """Helper to generate basic search query"""
        query_parts = []
        
        if keywords:
            query_parts.append(' OR '.join(f'"{k}"' for k in keywords))
        
        if sender_domain:
            query_parts.append(f"from:{sender_domain}")
            
        if email_type == "with_attachments":
            query_parts.append("has:attachment")
        elif email_type == "unread":
            query_parts.append("is:unread")
        elif email_type == "important":
            query_parts.append("is:important")
            
        query_parts.append(time_query)
        
        if exclusions:
            query_parts.extend(f"-{exc}" for exc in exclusions)
            
        return ' '.join(query_parts)
    
    def _generate_advanced_query(self, goal, time_query, email_type, keywords, sender_domain, exclusions):
        """Helper to generate advanced search query"""
        # More sophisticated query building based on goal
        if goal == "find_project_emails":
            base = '(project OR milestone OR deliverable OR "status update")'
        elif goal == "locate_attachments":
            base = 'has:attachment (filename:pdf OR filename:doc OR filename:xlsx)'
        elif goal == "filter_by_sender":
            base = f'from:{sender_domain}' if sender_domain else 'from:important-sender.com'
        else:
            base = ' OR '.join(f'"{k}"' for k in keywords) if keywords else 'important'
            
        query_parts = [f"({base})", time_query]
        
        if email_type == "with_attachments":
            query_parts.append("has:attachment")
        elif email_type == "unread":
            query_parts.append("is:unread")
            
        if exclusions:
            query_parts.extend(f"-{exc}" for exc in exclusions)
            
        return ' '.join(query_parts)

    @mcp.prompt(
        name="gmail_automation_builder",
        description="Create comprehensive Gmail automation workflows with filters, labels, and smart organization",
        tags={"gmail", "automation", "filters", "workflows", "productivity"},
        meta={"version": "1.0", "author": "FastMCP2-Gmail"}
    )
    def gmail_automation_builder(
        context: Context,
        automation_goal: str = Field(
            default="organize_project_emails",
            description="Main automation goal (organize_project_emails, auto_label_clients, filter_newsletters, etc.)"
        ),
        trigger_conditions: str = Field(
            default="from_domain,has_keywords",
            description="Comma-separated trigger conditions (from_domain, has_keywords, has_attachment, subject_contains, etc.)"
        ),
        actions_to_take: str = Field(
            default="add_label,mark_important",
            description="Comma-separated actions (add_label, remove_label, mark_important, archive, forward, etc.)"
        ),
        primary_keywords: str = Field(
            default="project,milestone,deliverable",
            description="Comma-separated primary keywords that trigger the automation"
        ),
        sender_criteria: str = Field(
            default="company.com",
            description="Sender domain or email pattern to match"
        ),
        label_name: str = Field(
            default="Auto-Project",
            description="Name for the label to create/use in automation"
        ),
        label_color: str = Field(
            default="#4285f4",
            description="Hex color for the automation label"
        ),
        automation_scope: str = Field(
            default="future_emails",
            description="Scope of automation (future_emails, existing_emails, both)"
        ),
        include_monitoring: bool = Field(
            default=True,
            description="Include monitoring and reporting for the automation"
        )
    ) -> PromptMessage:
        """
        Generate comprehensive Gmail automation setup with filters, labels, and monitoring.
        """
        
        request_id = context.request_id
        
        # Parse configuration - resolve Field values to strings
        trigger_conditions_str = str(trigger_conditions) if hasattr(trigger_conditions, 'default') else trigger_conditions
        actions_to_take_str = str(actions_to_take) if hasattr(actions_to_take, 'default') else actions_to_take
        primary_keywords_str = str(primary_keywords) if hasattr(primary_keywords, 'default') else primary_keywords
        automation_goal_str = str(automation_goal) if hasattr(automation_goal, 'default') else automation_goal
        automation_scope_str = str(automation_scope) if hasattr(automation_scope, 'default') else automation_scope
        sender_criteria_str = str(sender_criteria) if hasattr(sender_criteria, 'default') else sender_criteria
        label_name_str = str(label_name) if hasattr(label_name, 'default') else label_name
        label_color_str = str(label_color) if hasattr(label_color, 'default') else label_color
        
        triggers = [t.strip() for t in trigger_conditions_str.split(',')]
        actions = [a.strip() for a in actions_to_take_str.split(',')]
        keywords = [k.strip() for k in primary_keywords_str.split(',')]
        
        automation_guide = f"""
# Gmail Automation Builder
*Request ID: {request_id}*

## Automation Configuration
- **Goal**: {automation_goal_str.replace('_', ' ').title()}
- **Scope**: {automation_scope_str.replace('_', ' ').title()}
- **Triggers**: {', '.join(triggers)}
- **Actions**: {', '.join(actions)}
- **Keywords**: {', '.join(keywords)}

## Step 1: Create Automation Label

### Label Creation:
```python
# Create the automation label
label_result = await manage_gmail_label(
    user_google_email="your@email.com",
    action="create",
    name="{label_name_str}",
    background_color="{label_color_str}",
    text_color="#ffffff",
    label_list_visibility="labelShow",
    message_list_visibility="show"
)
print(f"Created label: {{label_result}}")
```

### Expected Result:
- **Label Name**: {label_name_str}
- **Color**: {label_color_str} background with white text
- **Visibility**: Shown in label list and message list

## Step 2: Build Filter Criteria

### Advanced Filter Logic:
```python
# Build the automation filter
filter_criteria = {{
    "query": "({' OR '.join(f'"{k}"' for k in keywords)}) AND from:{sender_criteria_str}",
    "from_address": "{sender_criteria_str}",
    "subject_contains": "{keywords[0] if keywords else 'important'}",
    "has_attachment": {"true" if "has_attachment" in triggers else "false"}
}}
```

### Human-Readable Criteria:
- **From**: Emails from domain `{sender_criteria_str}`
- **Keywords**: Contains any of: {', '.join(keywords)}
- **Attachments**: {'Required' if 'has_attachment' in triggers else 'Optional'}
- **Subject**: Must contain project-related terms

## Step 3: Create Gmail Filter

### Filter Implementation:
```python
# Create the Gmail filter with all actions
filter_result = await create_gmail_filter(
    user_google_email="your@email.com",
    # Criteria
    from_address="{sender_criteria_str}",
    subject_contains="{keywords[0] if keywords else ''}",
    query="({' OR '.join(f'"{k}"' for k in keywords)}) newer_than:1d",
    {"has_attachment=True," if "has_attachment" in triggers else ""}
    
    # Actions
    add_label_ids=["{label_name_str}"],  # Will be resolved to actual label ID
    {"mark_as_important=True," if "mark_important" in actions else ""}
    {"never_mark_as_spam=True," if "mark_important" in actions else ""}
)
print(f"Filter created: {{filter_result}}")
```

### Action Breakdown:
{chr(10).join([f"- **{action.replace('_', ' ').title()}**: Automatically applied to matching emails" for action in actions])}

## Step 4: Test the Automation

### Testing Strategy:
```python
# Test with existing emails first
test_search = await search_gmail_messages(
    user_google_email="your@email.com",
    query="({' OR '.join(f'"{k}"' for k in keywords)}) from:{sender_criteria_str} newer_than:7d",
    page_size=5
)

print(f"Found {{len(test_search)}} emails matching criteria")

# Apply labels to test emails
if test_search:
    for message in test_search:
        await modify_gmail_message_labels(
            user_google_email="your@email.com",
            message_id=message['id'],
            add_label_ids=["{label_name_str}"]
        )
```

## Step 5: Monitor and Optimize

{'### Monitoring Setup:' if include_monitoring else '### Basic Monitoring:'}
```python
# Regular monitoring function
async def check_automation_performance():
    # Count emails processed
    labeled_emails = await search_gmail_messages(
        user_google_email="your@email.com",
        query="label:{label_name_str} newer_than:7d",
        page_size=100
    )
    
    # Check for false positives
    manual_review = await search_gmail_messages(
        user_google_email="your@email.com",
        query="label:{label_name_str} -({' OR '.join(f'"{k}"' for k in keywords)})",
        page_size=10
    )
    
    return {{
        "processed_count": len(labeled_emails),
        "potential_false_positives": len(manual_review),
        "accuracy": (len(labeled_emails) - len(manual_review)) / len(labeled_emails) * 100
    }}

# Run weekly
performance = await check_automation_performance()
print(f"Automation Performance: {{performance}}")
```

## Advanced Automation Patterns

### Pattern 1: Multi-Stage Workflow
```python
# Create multiple filters for different priority levels
priority_levels = [
    {{"keywords": ["urgent", "asap"], "label": "High-Priority-{label_name_str}", "color": "#ea4335"}},
    {{"keywords": ["review", "feedback"], "label": "Review-{label_name_str}", "color": "#fbbc04"}},
    {{"keywords": ["fyi", "info"], "label": "Info-{label_name_str}", "color": "#34a853"}}
]

for level in priority_levels:
    # Create label
    await manage_gmail_label(
        user_google_email="your@email.com",
        action="create",
        name=level["label"],
        background_color=level["color"]
    )
    
    # Create filter
    await create_gmail_filter(
        user_google_email="your@email.com",
        subject_contains=' OR '.join(level["keywords"]),
        from_address="{sender_criteria_str}",
        add_label_ids=[level["label"]],
        mark_as_important=True if "urgent" in level["keywords"] else False
    )
```

### Pattern 2: Smart Forwarding
```python
# Auto-forward important emails
await create_gmail_filter(
    user_google_email="your@email.com",
    from_address="{sender_criteria_str}",
    subject_contains="urgent OR critical OR asap",
    forward_to="manager@company.com",
    add_label_ids=["Forwarded-Urgent"]
)
```

### Pattern 3: Archive and Organize
```python
# Auto-archive newsletters but keep them organized
await create_gmail_filter(
    user_google_email="your@email.com",
    from_address="newsletter@company.com",
    add_label_ids=["Newsletters"],
    remove_label_ids=["INBOX"]  # Auto-archive
)
```

## Automation Maintenance

### Weekly Review Checklist:
- [ ] Check filter performance metrics
- [ ] Review false positives/negatives
- [ ] Update keywords based on new patterns
- [ ] Adjust label colors and organization
- [ ] Monitor storage usage and cleanup old emails

### Monthly Optimization:
- [ ] Analyze email patterns and update criteria
- [ ] Create new filters for emerging needs
- [ ] Archive or delete unnecessary automated labels
- [ ] Export automation performance reports
- [ ] Update sender whitelists/blacklists

### Troubleshooting Common Issues:
1. **Too Many False Positives**: Refine keywords, add exclusions
2. **Missing Important Emails**: Broaden criteria, check spam folder
3. **Label Clutter**: Consolidate similar labels, use nested structure
4. **Performance Issues**: Limit filter complexity, use batch operations

This automation framework provides comprehensive Gmail workflow management with built-in monitoring and optimization capabilities.
"""
        
        return PromptMessage(
            content=TextContent(type="text", text=automation_guide),
            role="assistant"
        )

    @mcp.prompt(
        name="gmail_template_library",
        description="Generate a comprehensive library of email templates for different business scenarios",
        tags={"gmail", "templates", "business", "communication"},
        meta={"version": "1.0", "author": "FastMCP2-Gmail"}
    )
    def gmail_template_library(
        context: Context,
        template_category: str = Field(
            default="business_communication",
            description="Category of templates (business_communication, project_management, customer_service, marketing, etc.)"
        ),
        company_info: str = Field(
            default="Your Company,contact@company.com,https://company.com",
            description="Comma-separated company info: name,email,website"
        ),
        brand_colors: str = Field(
            default="#2c3e50,#3498db",
            description="Comma-separated brand colors for templates"
        ),
        include_examples: bool = Field(
            default=True,
            description="Include example usage with sample data"
        ),
        template_count: float = Field(
            default=5.0,
            ge=3.0,
            le=10.0,
            description="Number of templates to generate (3-10)"
        )
    ) -> PromptMessage:
        """
        Generate a comprehensive library of professional email templates for various business scenarios.
        """
        
        request_id = context.request_id
        
        # Resolve Field values to strings
        template_category_str = str(template_category) if hasattr(template_category, 'default') else template_category
        company_info_str = str(company_info) if hasattr(company_info, 'default') else company_info
        brand_colors_str = str(brand_colors) if hasattr(brand_colors, 'default') else brand_colors
        
        # Parse company info
        company_parts = company_info_str.split(',')
        company_name = company_parts[0].strip() if company_parts else "Your Company"
        company_email = company_parts[1].strip() if len(company_parts) > 1 else "contact@company.com"
        company_website = company_parts[2].strip() if len(company_parts) > 2 else "https://company.com"
        
        # Parse colors
        colors = [c.strip() for c in brand_colors_str.split(',')]
        primary_color = colors[0] if colors else "#2c3e50"
        accent_color = colors[1] if len(colors) > 1 else "#3498db"
        
        template_count_int = int(template_count)
        
        template_library = f"""
# Gmail Template Library
*Request ID: {request_id}*

## Template Collection Configuration
- **Category**: {template_category_str.replace('_', ' ').title()}
- **Company**: {company_name}
- **Brand Colors**: {primary_color} / {accent_color}
- **Template Count**: {template_count_int}

## Company Branding Elements
- **Name**: {company_name}
- **Email**: {company_email}
- **Website**: {company_website}

## Template Library

### Template 1: Project Status Update
```python
# Usage: Project milestone communication
project_status_template = {{
    "subject": "Project {{project_name}} - {{status}} Update",
    "content_type": "mixed",
    "html_body": '''
<html>
<head>
<style>
{self._get_base_email_styles(primary_color, accent_color)}
.status-{{}} {{ background: linear-gradient(135deg, #28a745 0%, #20c997 100%); }}
.status-at-risk {{ background: linear-gradient(135deg, #ffc107 0%, #fd7e14 100%); }}  
.status-delayed {{ background: linear-gradient(135deg, #dc3545 0%, #e83e8c 100%); }}
.milestone {{ background: #f8f9fa; padding: 15px; border-left: 4px solid {accent_color}; margin: 15px 0; }}
</style>
</head>
<body>
<div class="email-container">
    <div class="header">
        <h1>📊 Project Status Update</h1>
        <p>{company_name} - Project Management</p>
    </div>
    <div class="content">
        <h2>{{project_name}} Progress Report</h2>
        
        <div class="status-{{status_class}}">
            <h3>Status: {{status}}</h3>
            <p>{{status_description}}</p>
        </div>
        
        <div class="milestone">
            <h4>Current Milestone</h4>
            <p><strong>{{milestone_name}}</strong></p>
            <p>Progress: {{progress_percentage}}% complete</p>
            <p>Expected Completion: {{expected_date}}</p>
        </div>
        
        <h3>Key Achievements</h3>
        <ul>
            <li>{{achievement_1}}</li>
            <li>{{achievement_2}}</li>
            <li>{{achievement_3}}</li>
        </ul>
        
        <h3>Next Steps</h3>
        <ol>
            <li>{{next_step_1}}</li>
            <li>{{next_step_2}}</li>
            <li>{{next_step_3}}</li>
        </ol>
        
        <div style="text-align: center; margin: 20px 0;">
            <a href="{{project_dashboard_url}}" class="button">View Full Dashboard</a>
        </div>
    </div>
</div>
</body>
</html>''',
    "plain_body": '''
Project {{project_name}} Status Update

Status: {{status}}
{{status_description}}

Current Milestone: {{milestone_name}}  
Progress: {{progress_percentage}}% complete
Expected Completion: {{expected_date}}

Key Achievements:
- {{achievement_1}}
- {{achievement_2}} 
- {{achievement_3}}

Next Steps:
1. {{next_step_1}}
2. {{next_step_2}}
3. {{next_step_3}}

View Dashboard: {{project_dashboard_url}}
'''
}}

# Example usage:
await send_gmail_message(
    user_google_email="{company_email}",
    to="team@company.com",
    subject=project_status_template["subject"].format(
        project_name="Website Redesign",
        status="On Track"
    ),
    body=project_status_template["plain_body"].format(
        project_name="Website Redesign",
        status="On Track", 
        status_description="All milestones on schedule",
        # ... other variables
    ),
    html_body=project_status_template["html_body"],
    content_type="mixed"
)
```

### Template 2: Client Proposal
```python
client_proposal_template = {{
    "subject": "Proposal: {{project_title}} - {company_name}",
    "content_type": "mixed", 
    "html_body": '''
<html>
<head>
<style>
{self._get_base_email_styles(primary_color, accent_color)}
.proposal-section {{ background: #f8f9fa; padding: 20px; border-radius: 8px; margin: 20px 0; }}
.pricing {{ background: linear-gradient(135deg, {primary_color} 0%, {accent_color} 100%); color: white; padding: 20px; border-radius: 8px; }}
.timeline {{ border: 1px solid #dee2e6; padding: 15px; border-radius: 8px; }}
</style>
</head>
<body>
<div class="email-container">
    <div class="header">
        <h1>💼 Project Proposal</h1>
        <p>{company_name} - Professional Services</p>
    </div>
    <div class="content">
        <h2>Dear {{client_name}},</h2>
        <p>Thank you for considering {company_name} for your {{project_type}} needs. We're excited to present our proposal for {{project_title}}.</p>
        
        <div class="proposal-section">
            <h3>Project Overview</h3>
            <p>{{project_description}}</p>
            
            <h4>Key Deliverables:</h4>
            <ul>
                <li>{{deliverable_1}}</li>
                <li>{{deliverable_2}}</li> 
                <li>{{deliverable_3}}</li>
            </ul>
        </div>
        
        <div class="timeline">
            <h3>Project Timeline</h3>
            <p><strong>Start Date:</strong> {{start_date}}</p>
            <p><strong>Completion:</strong> {{end_date}}</p>
            <p><strong>Duration:</strong> {{duration}} weeks</p>
        </div>
        
        <div class="pricing">
            <h3>Investment</h3>
            <p><strong>Total Project Cost:</strong> ${{total_cost:,.2f}}</p>
            <p><strong>Payment Terms:</strong> {{payment_terms}}</p>
        </div>
        
        <p>We're confident this proposal meets your requirements and budget. Let's schedule a call to discuss any questions.</p>
        
        <div style="text-align: center; margin: 30px 0;">
            <a href="{{meeting_link}}" class="button">Schedule Discussion</a>
        </div>
    </div>
</div>
</body>
</html>'''
}}
```

### Template 3: Team Meeting Invitation
```python
meeting_invite_template = {{
    "subject": "📅 {{meeting_type}}: {{meeting_topic}} - {{date}}",
    "content_type": "mixed",
    "html_body": '''
<html>
<head>
<style>
body {{
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, Arial, sans-serif;
    line-height: 1.6;
    color: #333;
    margin: 0;
    padding: 20px;
    background-color: #f5f5f5;
}}
.email-container {{
    max-width: 600px;
    margin: 0 auto;
    background: white;
    border-radius: 12px;
    overflow: hidden;
    box-shadow: 0 4px 20px rgba(0,0,0,0.1);
}}
.header {{
    background: linear-gradient(135deg, {primary_color} 0%, {accent_color} 100%);
    color: white;
    padding: 30px 20px;
    text-align: center;
}}
.content {{
    padding: 30px;
}}
.button {{
    display: inline-block;
    background: linear-gradient(135deg, {primary_color} 0%, {accent_color} 100%);
    color: white !important;
    padding: 15px 30px;
    text-decoration: none;
    border-radius: 25px;
    margin: 15px 0;
    font-weight: 600;
}}
.meeting-details {{ background: #e8f4f8; padding: 20px; border-radius: 8px; border-left: 4px solid {accent_color}; }}
.agenda-item {{ padding: 10px 0; border-bottom: 1px solid #e9ecef; }}
.prep-materials {{ background: #fff3cd; padding: 15px; border-radius: 6px; }}
</style>
</head>
<body>
<div class="email-container">
    <div class="header">
        <h1>📅 Meeting Invitation</h1>
        <p>{company_name} - {{meeting_type}}</p>
    </div>
    <div class="content">
        <h2>{{meeting_topic}}</h2>
        
        <div class="meeting-details">
            <h3>Meeting Details</h3>
            <p><strong>📅 Date:</strong> {{date}}</p>
            <p><strong>🕐 Time:</strong> {{time}} ({{timezone}})</p>
            <p><strong>⏱️ Duration:</strong> {{duration}} minutes</p>
            <p><strong>📍 Location:</strong> {{location}}</p>
            <p><strong>👥 Attendees:</strong> {{attendee_count}} people</p>
        </div>
        
        <h3>Agenda</h3>
        <div class="agenda-item">
            <strong>1. {{agenda_item_1}}</strong> ({{duration_1}} min)
        </div>
        <div class="agenda-item">
            <strong>2. {{agenda_item_2}}</strong> ({{duration_2}} min)
        </div>
        <div class="agenda-item">
            <strong>3. {{agenda_item_3}}</strong> ({{duration_3}} min)
        </div>
        
        <div class="prep-materials">
            <h4>📋 Preparation Materials</h4>
            <ul>
                <li><a href="{{doc_1_url}}">{{doc_1_name}}</a></li>
                <li><a href="{{doc_2_url}}">{{doc_2_name}}</a></li>
            </ul>
        </div>
        
        <div style="text-align: center; margin: 20px 0;">
            <a href="{{meeting_link}}" class="button">Join Meeting</a>
            <a href="{{calendar_link}}" class="button" style="margin-left: 10px;">Add to Calendar</a>
        </div>
        
        <div style="background: #e8f5e8; padding: 15px; border-radius: 6px; margin: 20px 0;">
            <h4>📅 Calendar Integration Options</h4>
            <p><strong>Google Calendar:</strong> <a href="https://www.google.com/calendar/render?action=TEMPLATE&text={{meeting_topic|urlencode}}&dates={{start_datetime}}/{{end_datetime}}&details={{meeting_description|urlencode}}&location={{location|urlencode}}">Add to Google Calendar</a></p>
            <p><strong>Other Calendars:</strong> <a href="{{ics_file_url}}">Download ICS File</a></p>
        </div>
    </div>
</div>
</body>
</html>'''
}}
```

## Implementation Helper Functions

### Template Usage Function:
```python
async def send_template_email(template_name, variables, recipient, sender_email):
    \"\"\"
    Send an email using one of the predefined templates
    \"\"\"
    templates = {{
        "project_status": project_status_template,
        "client_proposal": client_proposal_template, 
        "meeting_invite": meeting_invite_template
    }}
    
    template = templates.get(template_name)
    if not template:
        raise ValueError(f"Template '{{template_name}}' not found")
        
    # Format the template with variables
    subject = template["subject"].format(**variables)
    html_body = template["html_body"].format(**variables)
    plain_body = template.get("plain_body", "").format(**variables)
    
    # Send the email
    return await send_gmail_message(
        user_google_email=sender_email,
        to=recipient,
        subject=subject,
        body=plain_body,
        html_body=html_body,
        content_type=template["content_type"]
    )

# Example usage:
await send_template_email(
    template_name="project_status",
    variables={{
        "project_name": "Website Redesign",
        "status": "On Track",
        "progress_percentage": 75,
        # ... other variables
    }},
    recipient="client@company.com",
    sender_email="{company_email}"
)
```

## Template Categories Available

### Business Communication:
- Project status updates
- Client proposals  
- Meeting invitations
- Progress reports
- Contract notifications

### Customer Service:
- Welcome messages
- Support ticket responses
- Follow-up surveys
- Issue resolution
- Service updates

### Marketing:
- Newsletter templates
- Product announcements
- Event invitations
- Promotional campaigns
- Customer testimonials

This template library provides a foundation for consistent, professional email communication across your organization.
"""
        
        return PromptMessage(
            content=TextContent(type="text", text=template_library),
            role="assistant"
        )

    @mcp.prompt(
        name="create_showcase_email",
        description="Generate advanced showcase emails with dynamic workspace content integration, professional styling, and resource-aware URL generation",
        tags={"gmail", "showcase", "advanced", "workspace", "dynamic", "resources"},
        meta={"version": "2.0", "author": "FastMCP2-Gmail"}
    )
    def create_showcase_email(
        context: Context,
        showcase_type: str = Field(
            default="product_demo",
            description="Type of showcase (product_demo, portfolio_review, capability_presentation, client_showcase, etc.)"
        ),
        primary_color: str = Field(
            default="#667eea",
            description="Primary brand color (hex format)"
        ),
        secondary_color: str = Field(
            default="#764ba2",
            description="Secondary brand color for gradients (hex format)"
        ),
        company_name: str = Field(
            default="FastMCP2 Platform",
            description="Company or project name for branding"
        ),
        recipient_name: str = Field(
            default="Valued Client",
            description="Name of the email recipient for personalization"
        ),
        include_recent_work: bool = Field(
            default=True,
            description="Include recent documents and projects from workspace"
        ),
        content_focus: str = Field(
            default="comprehensive",
            description="Focus of content (comprehensive, technical, business, creative)"
        ),
        call_to_action: str = Field(
            default="Schedule a Demo",
            description="Main call-to-action text"
        ),
        cta_url: str = Field(
            default="https://calendar.app/meeting",
            description="URL for the main call-to-action"
        )
    ) -> PromptMessage:
        """
        Generate advanced showcase emails that demonstrate the power of dynamic workspace integration
        and resource-aware content generation, like the user's successful working example.
        """
        
        request_id = context.request_id
        
        # Resolve Field values to strings
        showcase_type_str = str(showcase_type) if hasattr(showcase_type, 'default') else showcase_type
        content_focus_str = str(content_focus) if hasattr(content_focus, 'default') else content_focus
        primary_color_str = str(primary_color) if hasattr(primary_color, 'default') else primary_color
        secondary_color_str = str(secondary_color) if hasattr(secondary_color, 'default') else secondary_color
        company_name_str = str(company_name) if hasattr(company_name, 'default') else company_name
        recipient_name_str = str(recipient_name) if hasattr(recipient_name, 'default') else recipient_name
        call_to_action_str = str(call_to_action) if hasattr(call_to_action, 'default') else call_to_action
        cta_url_str = str(cta_url) if hasattr(cta_url, 'default') else cta_url
        
        showcase_guide = f"""
# Advanced Showcase Email Generator
*Request ID: {request_id}*

## Showcase Configuration
- **Type**: {showcase_type_str.replace('_', ' ').title()}
- **Focus**: {content_focus_str.title()}
- **Branding**: {primary_color_str} → {secondary_color_str}
- **Workspace Integration**: {'Enabled' if include_recent_work else 'Disabled'}

## 🚀 Resource-Aware Email Generation

### Step 1: Gather Dynamic Content
```python
# Get user profile and workspace context
user_profile = await mcp.get_resource("user://current/profile")
user_email = user_profile["email"]
user_name = user_email.split('@')[0].replace('.', ' ').title()

# Get recent workspace content for showcase
recent_content = await mcp.get_resource("workspace://content/recent")
content_suggestions = await mcp.get_resource("gmail://content/suggestions")

# Extract showcase-worthy items
showcase_items = {{
    "recent_docs": recent_content.get("content_by_type", {{}}).get("documents", [])[:4],
    "key_presentations": recent_content.get("content_by_type", {{}}).get("presentations", [])[:3],
    "data_insights": recent_content.get("content_by_type", {{}}).get("spreadsheets", [])[:2],
    "total_files": recent_content.get("content_summary", {{}}).get("total_files", 0)
}}
```

### Step 2: Generate Showcase Email
```python
# Create the showcase email with dynamic content
showcase_email = await send_gmail_message(
    user_google_email=user_email,  # Dynamic from user profile
    to="{recipient_name_str.lower().replace(' ', '.')}@company.com",
    subject=f"🌟 {showcase_type_str.replace('_', ' ').title()}: {company_name_str} Capabilities",
    content_type="mixed",
    body=f'''
{company_name_str} Showcase - {showcase_type_str.replace('_', ' ').title()}

Dear {recipient_name_str},

We're excited to showcase our latest capabilities and recent work.

Recent Projects:
• {{item['name'] for item in recent_docs}}

Key Presentations:
• {{item['name'] for item in key_presentations}}

Data Insights:
• {{item['name'] for item in data_insights}}

Total Portfolio Items: {{total_files}}

Let's connect to discuss how we can help your organization.

Best regards,
{{user_name}}
{company_name_str}
    ''',
    html_body=f'''
<html>
<head>
<style>
body {{
    font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, sans-serif;
    margin: 0;
    padding: 0;
    background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
    color: #333;
}}
.showcase-container {{
    max-width: 700px;
    margin: 20px auto;
    background: white;
    border-radius: 16px;
    overflow: hidden;
    box-shadow: 0 20px 40px rgba(0,0,0,0.1);
}}
.hero-header {{
    background: linear-gradient(135deg, {primary_color_str} 0%, {secondary_color_str} 100%);
    color: white;
    padding: 40px 30px;
    text-align: center;
    position: relative;
}}
.hero-header::before {{
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: url('data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><defs><pattern id="grain" width="100" height="100" patternUnits="userSpaceOnUse"><circle cx="25" cy="25" r="1" fill="white" opacity="0.1"/><circle cx="75" cy="75" r="1" fill="white" opacity="0.1"/></pattern></defs><rect width="100" height="100" fill="url(%23grain)"/></svg>');
    opacity: 0.3;
}}
.hero-content {{
    position: relative;
    z-index: 2;
}}
.hero-title {{
    font-size: 32px;
    font-weight: 700;
    margin: 0 0 10px 0;
    text-shadow: 0 2px 4px rgba(0,0,0,0.2);
}}
.hero-subtitle {{
    font-size: 18px;
    opacity: 0.95;
    margin: 0;
}}
.content-section {{
    padding: 40px 30px;
}}
.section-title {{
    font-size: 24px;
    font-weight: 600;
    color: {primary_color_str};
    margin: 0 0 20px 0;
    display: flex;
    align-items: center;
}}
.section-title::before {{
    content: '✨';
    margin-right: 10px;
}}
.showcase-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
    gap: 25px;
    margin: 30px 0;
}}
.showcase-card {{
    background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
    border: 1px solid #dee2e6;
    border-radius: 12px;
    padding: 25px;
    transition: transform 0.3s ease, box-shadow 0.3s ease;
}}
.showcase-card:hover {{
    transform: translateY(-5px);
    box-shadow: 0 15px 30px rgba(0,0,0,0.15);
}}
.card-header {{
    display: flex;
    align-items: center;
    margin-bottom: 15px;
}}
.card-icon {{
    width: 40px;
    height: 40px;
    border-radius: 8px;
    background: linear-gradient(135deg, {primary_color_str} 0%, {secondary_color_str} 100%);
    display: flex;
    align-items: center;
    justify-content: center;
    color: white;
    font-weight: bold;
    margin-right: 15px;
}}
.card-title {{
    font-size: 18px;
    font-weight: 600;
    margin: 0;
    color: #333;
}}
.card-content {{
    color: #666;
    line-height: 1.6;
}}
.workspace-items {{
    background: #f8f9fa;
    border-radius: 8px;
    padding: 20px;
    margin: 20px 0;
}}
.workspace-item {{
    display: flex;
    align-items: center;
    padding: 10px 0;
    border-bottom: 1px solid #e9ecef;
}}
.workspace-item:last-child {{
    border-bottom: none;
}}
.item-icon {{
    font-size: 20px;
    margin-right: 12px;
    width: 24px;
}}
.item-details {{
    flex: 1;
}}
.item-name {{
    font-weight: 500;
    color: #333;
    margin: 0 0 4px 0;
}}
.item-meta {{
    font-size: 12px;
    color: #888;
    margin: 0;
}}
.stats-showcase {{
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 20px;
    margin: 30px 0;
    text-align: center;
}}
.stat-item {{
    background: white;
    border: 2px solid #f1f3f4;
    border-radius: 12px;
    padding: 20px 10px;
}}
.stat-number {{
    font-size: 28px;
    font-weight: 700;
    color: {primary_color_str};
    margin: 0 0 5px 0;
}}
.stat-label {{
    font-size: 12px;
    color: #666;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin: 0;
}}
.cta-section {{
    background: linear-gradient(135deg, {primary_color_str} 0%, {secondary_color_str} 100%);
    color: white;
    padding: 40px 30px;
    text-align: center;
    margin: 30px 0 0 0;
}}
.cta-button {{
    display: inline-block;
    background: white;
    color: {primary_color_str} !important;
    padding: 18px 36px;
    text-decoration: none;
    border-radius: 30px;
    font-weight: 600;
    font-size: 16px;
    margin: 20px 0 0 0;
    transition: all 0.3s ease;
    box-shadow: 0 4px 15px rgba(0,0,0,0.2);
}}
.cta-button:hover {{
    transform: translateY(-2px);
    box-shadow: 0 8px 25px rgba(0,0,0,0.25);
}}
.footer {{
    background: #f8f9fa;
    padding: 20px 30px;
    text-align: center;
    color: #666;
    font-size: 14px;
}}
</style>
</head>
<body>
<div class="showcase-container">
    <div class="hero-header">
        <div class="hero-content">
            <h1 class="hero-title">🌟 {showcase_type_str.replace('_', ' ').title()}</h1>
            <p class="hero-subtitle">{company_name_str} - Advanced Capabilities Showcase</p>
        </div>
    </div>
    
    <div class="content-section">
        <h2>Dear {recipient_name_str},</h2>
        <p>We're excited to showcase our latest capabilities and the dynamic integration features that make our platform unique.</p>
        
        <h3 class="section-title">Recent Portfolio Highlights</h3>
        
        <div class="workspace-items">
            <div class="workspace-item">
                <span class="item-icon">📄</span>
                <div class="item-details">
                    <p class="item-name">{{{{recent_docs[0]['name'] if recent_docs else 'Strategic Planning Document'}}}}</p>
                    <p class="item-meta">Document • {{{{recent_docs[0]['modified_time'][:10] if recent_docs else 'Recently updated'}}}}</p>
                </div>
            </div>
            <div class="workspace-item">
                <span class="item-icon">📊</span>
                <div class="item-details">
                    <p class="item-name">{{{{key_presentations[0]['name'] if key_presentations else 'Executive Presentation'}}}}</p>
                    <p class="item-meta">Presentation • {{{{key_presentations[0]['modified_time'][:10] if key_presentations else 'Recently updated'}}}}</p>
                </div>
            </div>
            <div class="workspace-item">
                <span class="item-icon">📈</span>
                <div class="item-details">
                    <p class="item-name">{{{{data_insights[0]['name'] if data_insights else 'Analytics Dashboard'}}}}</p>
                    <p class="item-meta">Spreadsheet • {{{{data_insights[0]['modified_time'][:10] if data_insights else 'Recently updated'}}}}</p>
                </div>
            </div>
        </div>
        
        <div class="showcase-grid">
            <div class="showcase-card">
                <div class="card-header">
                    <div class="card-icon">🔗</div>
                    <h4 class="card-title">Dynamic Integration</h4>
                </div>
                <div class="card-content">
                    Real-time access to Google Workspace content with automatic link generation and context awareness.
                </div>
            </div>
            
            <div class="showcase-card">
                <div class="card-header">
                    <div class="card-icon">⚡</div>
                    <h4 class="card-title">Smart Automation</h4>
                </div>
                <div class="card-content">
                    Intelligent email composition using user profile data and recent activity patterns.
                </div>
            </div>
            
            <div class="showcase-card">
                <div class="card-header">
                    <div class="card-icon">🎯</div>
                    <h4 class="card-title">Resource Awareness</h4>
                </div>
                <div class="card-content">
                    Contextual content suggestions based on workspace analysis and user behavior.
                </div>
            </div>
            
            <div class="showcase-card">
                <div class="card-header">
                    <div class="card-icon">🚀</div>
                    <h4 class="card-title">Advanced Styling</h4>
                </div>
                <div class="card-content">
                    Professional HTML emails with gradients, animations, and responsive design.
                </div>
            </div>
        </div>
        
        <div class="stats-showcase">
            <div class="stat-item">
                <p class="stat-number">{{{{total_files}}}}</p>
                <p class="stat-label">Portfolio Items</p>
            </div>
            <div class="stat-item">
                <p class="stat-number">100%</p>
                <p class="stat-label">Dynamic</p>
            </div>
            <div class="stat-item">
                <p class="stat-number">Real-time</p>
                <p class="stat-label">Integration</p>
            </div>
            <div class="stat-item">
                <p class="stat-number">AI-Powered</p>
                <p class="stat-label">Suggestions</p>
            </div>
        </div>
    </div>
    
    <div class="cta-section">
        <h3>Ready to Experience This Power?</h3>
        <p>Let's discuss how this dynamic integration can transform your workflow.</p>
        <a href="{cta_url_str}" class="cta-button">{call_to_action_str}</a>
    </div>
    
    <div class="footer">
        <p>This showcase email was dynamically generated using FastMCP2 resource integration.<br>
        All content and links are contextually aware and automatically personalized.</p>
    </div>
</div>
</body>
</html>
    '''
)
```

### Alternative: Create as Draft First (draft_gmail_message):
```python
# Create draft using FastMCP2 Gmail tools (note different parameter order)
showcase_draft = await draft_gmail_message(
    user_google_email=user_email,  # Dynamic from user profile
    subject=f"🌟 {showcase_type_str.replace('_', ' ').title()}: {company_name_str} Capabilities",
    body=f'''
{company_name_str} Showcase - {showcase_type_str.replace('_', ' ').title()}

Dear {recipient_name_str},

We're excited to showcase our latest capabilities and recent work.

Recent Projects:
• {{{{item['name'] for item in recent_docs}}}}

Key Presentations:
• {{{{item['name'] for item in key_presentations}}}}

Data Insights:
• {{{{item['name'] for item in data_insights}}}}

Total Portfolio Items: {{{{total_files}}}}

Let's connect to discuss how we can help your organization.

Best regards,
{{{{user_name}}}}
{company_name_str}
    ''',
    to="{recipient_name_str.lower().replace(' ', '.')}@company.com",  # Optional for drafts
    content_type="mixed",
    html_body=f'''[FULL_HTML_CONTENT_FROM_ABOVE]'''
)
```

## 🎯 Key Features Demonstrated

### Dynamic Content Integration
- **User Profile Awareness**: Automatically uses authenticated user's email and name
- **Workspace Content**: Pulls recent documents, presentations, and spreadsheets
- **Smart Suggestions**: Contextual content recommendations
- **Real-time Links**: Direct links to Google Workspace files

### Advanced Styling Features
- **Gradient Backgrounds**: Professional color schemes
- **Interactive Elements**: Hover effects and animations
- **Responsive Design**: Optimized for all devices
- **Modern Typography**: Clean, readable fonts

### Resource-Aware Generation
- **Content Discovery**: Automatic workspace scanning
- **URL Generation**: Dynamic link creation
- **Context Sensitivity**: User-specific personalization
- **Real-time Updates**: Fresh content integration

## Implementation Example

### Complete Working Example:
```python
# This replicates your successful working example but with resource integration
async def create_advanced_showcase():
    # Get user context
    user_profile = await mcp.get_resource("user://current/profile")
    recent_content = await mcp.get_resource("workspace://content/recent")
    
    # Create showcase email
    result = await send_gmail_message(
        user_google_email=user_profile["email"],
        to="{recipient_name_str.lower().replace(' ', '.')}@company.com",
        subject="🌟 Advanced Capabilities Showcase - {company_name_str}",
        content_type="mixed",
        body="[Plain text version with dynamic content]",
        html_body="[Full HTML from above with all styling and dynamic variables]"
    )
    
    return result

# Usage
showcase_result = await create_advanced_showcase()
print(f"Showcase email sent: {{showcase_result}}")
```

This showcase email demonstrates the same advanced capabilities as your working example, but now with full resource integration for dynamic content, user context awareness, and automatic workspace file discovery.
"""
        
        return PromptMessage(
            content=TextContent(type="text", text=showcase_guide),
            role="assistant"
        )

    @mcp.prompt(
        name="gmail_calendar_integration",
        description="Generate Gmail templates with advanced Google Calendar integration, event creation links, and multi-platform calendar support",
        tags={"gmail", "calendar", "events", "scheduling", "integration"},
        meta={"version": "1.0", "author": "FastMCP2-Gmail"}
    )
    def gmail_calendar_integration(
        context: Context,
        event_type: str = Field(
            default="meeting",
            description="Type of event (meeting, webinar, appointment, conference, social_event, etc.)"
        ),
        event_title: str = Field(
            default="Team Meeting",
            description="Title of the calendar event"
        ),
        event_date: str = Field(
            default="2024-12-25",
            description="Event date in YYYY-MM-DD format"
        ),
        start_time: str = Field(
            default="14:00",
            description="Start time in HH:MM format (24-hour)"
        ),
        duration_minutes: int = Field(
            default=60,
            description="Duration of event in minutes"
        ),
        timezone: str = Field(
            default="America/New_York",
            description="Timezone for the event (e.g., America/New_York, UTC, Europe/London)"
        ),
        location: str = Field(
            default="Conference Room A",
            description="Event location (physical address or virtual meeting link)"
        ),
        event_description: str = Field(
            default="Important team meeting to discuss upcoming projects",
            description="Detailed description of the event"
        ),
        include_reminder: bool = Field(
            default=True,
            description="Include reminder information in the email"
        ),
        brand_colors: str = Field(
            default="#4285f4,#34a853",
            description="Comma-separated hex colors for calendar integration styling"
        )
    ) -> PromptMessage:
        """
        Generate professional email templates with seamless Google Calendar integration,
        including proper event URLs, ICS file generation, and multi-platform support.
        """
        
        request_id = context.request_id
        
        # Resolve Field values to strings
        event_type_str = str(event_type) if hasattr(event_type, 'default') else event_type
        event_title_str = str(event_title) if hasattr(event_title, 'default') else event_title
        event_date_str = str(event_date) if hasattr(event_date, 'default') else event_date
        timezone_str = str(timezone) if hasattr(timezone, 'default') else timezone
        location_str = str(location) if hasattr(location, 'default') else location
        event_description_str = str(event_description) if hasattr(event_description, 'default') else event_description
        brand_colors_str = str(brand_colors) if hasattr(brand_colors, 'default') else brand_colors
        start_time_str = str(start_time) if hasattr(start_time, 'default') else start_time
        
        # Parse colors
        colors = [c.strip() for c in brand_colors_str.split(',')]
        primary_color = colors[0] if colors else "#4285f4"
        secondary_color = colors[1] if len(colors) > 1 else "#34a853"
        
        # Calculate end time
        start_hour, start_minute = map(int, start_time_str.split(':'))
        start_minutes_total = start_hour * 60 + start_minute
        end_minutes_total = start_minutes_total + duration_minutes
        end_hour = (end_minutes_total // 60) % 24
        end_minute = end_minutes_total % 60
        end_time = f"{end_hour:02d}:{end_minute:02d}"
        
        calendar_guide = f"""
# Gmail Calendar Integration Templates
*Request ID: {request_id}*

## Event Configuration
- **Event Type**: {event_type_str.replace('_', ' ').title()}
- **Title**: {event_title_str}
- **Date**: {event_date_str}
- **Time**: {start_time_str} - {end_time} ({timezone_str})
- **Duration**: {duration_minutes} minutes
- **Location**: {location_str}

## 📅 Calendar Integration Setup

### Step 1: Generate Calendar URLs
```python
import urllib.parse
from datetime import datetime, timedelta

# Event details
event_title = "{event_title_str}"
event_date = "{event_date_str}"
start_time = "{start_time_str}"
end_time = "{end_time}"
timezone = "{timezone_str}"
location = "{location_str}"
description = "{event_description_str}"

# Convert to Google Calendar format (YYYYMMDDTHHMMSSZ)
def format_datetime_for_calendar(date_str, time_str, tz="UTC"):
    dt_str = f"{{date_str}}T{{time_str.replace(':', '')}}00"
    if tz == "UTC":
        dt_str += "Z"
    return dt_str

start_datetime = format_datetime_for_calendar(event_date, start_time)
end_datetime = format_datetime_for_calendar(event_date, end_time)

# Google Calendar URL
google_params = {{
    'action': 'TEMPLATE',
    'text': event_title,
    'dates': f'{{start_datetime}}/{{end_datetime}}',
    'details': description,
    'location': location,
    'ctz': timezone
}}

google_calendar_url = f"https://www.google.com/calendar/render?{{'&'.join([f'{{k}}={{urllib.parse.quote(str(v))}}' for k, v in google_params.items()])}}"

# Outlook Calendar URL
outlook_params = {{
    'path': '/calendar/action/compose',
    'rru': 'addevent',
    'subject': event_title,
    'startdt': start_datetime,
    'enddt': end_datetime,
    'body': description,
    'location': location
}}

outlook_calendar_url = f"https://outlook.live.com/calendar/0/deeplink/compose?{{'&'.join([f'{{k}}={{urllib.parse.quote(str(v))}}' for k, v in outlook_params.items()])}}"
```

### Step 2: Create ICS File Content
```python
def generate_ics_file(title, start_dt, end_dt, desc, loc):
    import uuid
    
    ics_content = f'''BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//FastMCP2//Gmail Calendar Integration//EN
CALSCALE:GREGORIAN
METHOD:PUBLISH
BEGIN:VEVENT
UID:{{uuid.uuid4()}}@fastmcp2.com
DTSTART:{{start_dt}}
DTEND:{{end_dt}}
SUMMARY:{{title}}
DESCRIPTION:{{desc}}
LOCATION:{{loc}}
STATUS:CONFIRMED
TRANSP:OPAQUE
SEQUENCE:0
BEGIN:VALARM
TRIGGER:-PT15M
ACTION:DISPLAY
DESCRIPTION:Reminder: {{title}}
END:VALARM
END:VEVENT
END:VCALENDAR'''
    return ics_content

# Generate ICS content
ics_content = generate_ics_file(
    event_title, start_datetime, end_datetime,
    description, location
)

# In a real implementation, save this to a file and provide download URL
ics_download_url = "https://yourserver.com/events/meeting.ics"
```

### Step 3: Professional Calendar Email Template
```python
# Send calendar-integrated email
calendar_email = await send_gmail_message(
    user_google_email="{{user_email}}",
    to="{{recipient_email}}",
    subject=f"📅 {{event_type_str.replace('_', ' ').title()}}: {{event_title_str}} - {{event_date_str}}",
    content_type="mixed",
    body=f'''
{event_type_str.replace('_', ' ').title()}: {event_title_str}

Date: {event_date_str}
Time: {start_time_str} - {end_time} ({timezone_str})
Location: {location_str}

{event_description_str}

{"📅 SAVE THE DATE - Add to your calendar:" if include_reminder else ""}

Google Calendar: {{google_calendar_url}}
Outlook Calendar: {{outlook_calendar_url}}
Download ICS: {{ics_download_url}}

See you there!
    ''',
    html_body=f'''
<html>
<head>
<style>
body {{
    font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, sans-serif;
    line-height: 1.6;
    color: #333;
    margin: 0;
    padding: 20px;
    background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
}}
.calendar-email {{
    max-width: 600px;
    margin: 0 auto;
    background: white;
    border-radius: 16px;
    overflow: hidden;
    box-shadow: 0 10px 30px rgba(0,0,0,0.1);
}}
.event-header {{
    background: linear-gradient(135deg, {primary_color} 0%, {secondary_color} 100%);
    color: white;
    padding: 30px;
    text-align: center;
}}
.event-title {{
    font-size: 28px;
    font-weight: 700;
    margin: 0 0 10px 0;
}}
.event-type {{
    font-size: 16px;
    opacity: 0.9;
    margin: 0;
}}
.event-details {{
    padding: 30px;
}}
.detail-item {{
    display: flex;
    align-items: center;
    margin: 15px 0;
    padding: 12px;
    background: #f8f9fa;
    border-radius: 8px;
    border-left: 4px solid {primary_color};
}}
.detail-icon {{
    font-size: 20px;
    margin-right: 15px;
    width: 25px;
}}
.detail-content {{
    flex: 1;
}}
.detail-label {{
    font-weight: 600;
    color: #333;
    margin: 0 0 4px 0;
}}
.detail-value {{
    color: #666;
    margin: 0;
}}
.calendar-actions {{
    background: linear-gradient(135deg, #e3f2fd 0%, #f3e5f5 100%);
    padding: 25px;
    text-align: center;
    margin: 20px 0;
    border-radius: 12px;
    border: 1px solid #e1e5e9;
}}
.calendar-title {{
    font-size: 20px;
    font-weight: 600;
    margin: 0 0 20px 0;
    color: {primary_color};
}}
.calendar-buttons {{
    display: flex;
    gap: 12px;
    flex-wrap: wrap;
    justify-content: center;
}}
.cal-button {{
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 12px 24px;
    border-radius: 8px;
    text-decoration: none;
    font-weight: 600;
    font-size: 14px;
    transition: all 0.3s ease;
    min-width: 140px;
}}
.google-cal {{
    background: #4285f4;
    color: white !important;
}}
.google-cal:hover {{
    background: #3367d6;
    transform: translateY(-2px);
}}
.outlook-cal {{
    background: #0078d4;
    color: white !important;
}}
.outlook-cal:hover {{
    background: #106ebe;
    transform: translateY(-2px);
}}
.ics-download {{
    background: #28a745;
    color: white !important;
}}
.ics-download:hover {{
    background: #218838;
    transform: translateY(-2px);
}}
.event-description {{
    background: #f8f9fa;
    padding: 20px;
    border-radius: 8px;
    margin: 20px 0;
    border-left: 4px solid {secondary_color};
}}
{'.reminder-section {{ background: #fff3cd; padding: 15px; border-radius: 6px; margin: 20px 0; border-left: 4px solid #ffc107; }}' if include_reminder else ''}
</style>
</head>
<body>
<div class="calendar-email">
    <div class="event-header">
        <h1 class="event-title">📅 {event_title_str}</h1>
        <p class="event-type">{event_type_str.replace('_', ' ').title()}</p>
    </div>
    
    <div class="event-details">
        <div class="detail-item">
            <span class="detail-icon">📅</span>
            <div class="detail-content">
                <p class="detail-label">Date</p>
                <p class="detail-value">{event_date}</p>
            </div>
        </div>
        
        <div class="detail-item">
            <span class="detail-icon">🕐</span>
            <div class="detail-content">
                <p class="detail-label">Time</p>
                <p class="detail-value">{start_time} - {end_time} ({timezone})</p>
            </div>
        </div>
        
        <div class="detail-item">
            <span class="detail-icon">📍</span>
            <div class="detail-content">
                <p class="detail-label">Location</p>
                <p class="detail-value">{location}</p>
            </div>
        </div>
        
        <div class="detail-item">
            <span class="detail-icon">⏱️</span>
            <div class="detail-content">
                <p class="detail-label">Duration</p>
                <p class="detail-value">{duration_minutes} minutes</p>
            </div>
        </div>
    </div>
    
    <div class="event-description">
        <h3>Event Details</h3>
        <p>{event_description}</p>
    </div>
    
    <div class="calendar-actions">
        <h3 class="calendar-title">📅 Add to Your Calendar</h3>
        <div class="calendar-buttons">
            <a href="{{google_calendar_url}}" class="cal-button google-cal">
                📅 Google Calendar
            </a>
            <a href="{{outlook_calendar_url}}" class="cal-button outlook-cal">
                📅 Outlook
            </a>
            <a href="{{ics_download_url}}" class="cal-button ics-download">
                📥 Download ICS
            </a>
        </div>
        <p style="margin: 15px 0 0 0; font-size: 12px; color: #666;">
            Choose your preferred calendar app to automatically save this event
        </p>
    </div>
    
    {f'''<div class="reminder-section">
        <h4>⏰ Reminder Set</h4>
        <p>This event includes a 15-minute reminder. You'll be notified before the event starts.</p>
    </div>''' if include_reminder else ''}
    
    <div style="padding: 20px; text-align: center; background: #f8f9fa; color: #666; font-size: 14px;">
        <p>This calendar invitation was generated using FastMCP2 Gmail integration.<br>
        All calendar links are tested and compatible with major calendar applications.</p>
    </div>
</div>
</body>
</html>
    '''
)
```

## 🎯 Advanced Calendar Features

### Dynamic Calendar Integration:
- ✅ **Live Event Data** - Leverage `calendar://events/today` resource for real event details
- ✅ **Event ID Integration** - Use actual Google Calendar event IDs for actions
- ✅ **Attendee Population** - Automatically include real attendee lists
- ✅ **Meeting Link Integration** - Extract video conference links from event locations

### Multi-Platform Compatibility:
- ✅ **Google Calendar** - Direct "Add to Calendar" links with real event IDs
- ✅ **Outlook/Office 365** - Native integration URLs
- ✅ **Apple Calendar** - ICS file support with real event data
- ✅ **Mobile Devices** - Responsive calendar buttons

### Resource-Powered Features:
```python
# Example: Access today's events for email templates
events_resource = await access_resource("calendar://events/today")
events_data = events_resource["data"]["events"]

# Use real calendar data in emails
for event in events_data:
    event_id = event["id"]           # "abc123xyz789" - Real Google Calendar event ID
    title = event["summary"]         # "Team Standup Meeting"
    start_time = event["start"]      # {"dateTime": "2025-01-27T10:00:00-05:00", "timeZone": "America/New_York"}
    attendees = event["attendees"]   # ["john@company.com", "sarah@company.com"]
    location = event["location"]     # "https://meet.google.com/abc-defg-hij"
    html_link = event["htmlLink"]    # "https://calendar.google.com/calendar/event?eid=..."

# Practical Usage: Create meeting reminder emails with real data
async def send_meeting_reminders():
    events_resource = await access_resource("calendar://events/today")
    if "error" not in events_resource:
        events = events_resource["data"]["events"]
        
        # Filter for upcoming meetings in next 2 hours
        from datetime import datetime, timedelta
        now = datetime.now()
        upcoming_cutoff = now + timedelta(hours=2)
        
        for event in events:
            event_start = event["start"].get("dateTime")
            if event_start:
                # Parse event time and check if it's upcoming
                event_datetime = datetime.fromisoformat(event_start.replace('Z', '+00:00'))
                
                if now < event_datetime < upcoming_cutoff:
                    # Send reminder using real event data
                    await send_gmail_message(
                        user_google_email=user_email,
                        to=", ".join(event["attendees"]),  # Real attendee list
                        subject=f"⏰ Meeting Reminder: {event['summary']} in 2 hours",
                        content_type="mixed",
                        body=f"Reminder: {event['summary']} starts at {event_start}",
                        html_body=f'''
                        <div style="padding: 20px; background: #f8f9fa; border-left: 4px solid #4285f4;">
                            <h3>📅 Meeting Reminder</h3>
                            <p><strong>{event["summary"]}</strong></p>
                            <p>🕐 Starts: {event_start}</p>
                            <p>📍 Location: {event["location"]}</p>
                            <p><a href="{event["htmlLink"]}" style="background: #4285f4; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">Open in Calendar</a></p>
                        </div>
                        '''
                    )

# Advanced: Use calendar tools with resource data
async def update_meeting_with_agenda():
    events_resource = await access_resource("calendar://events/today")
    if "error" not in events_resource:
        for event in events_resource["data"]["events"]:
            if "standup" in event["summary"].lower():
                # Use real event ID with calendar tools
                await modify_event(
                    user_google_email=user_email,
                    event_id=event["id"],  # Real Google Calendar event ID from resource
                    description=f"{event.get('description', '')} \n\nAgenda:\n• Project updates\n• Blockers discussion\n• Sprint planning"
                )
```

### Event Enhancement Options:
- **Recurring Events**: Modify ICS to include RRULE parameters
- **Multiple Attendees**: Add attendee information to ICS file
- **Video Conferencing**: Include meeting links in location field
- **Attachments**: Reference documents in event description
- **Custom Reminders**: Modify VALARM settings for different reminder times

### Best Practices Implemented:
1. **URL Encoding**: All parameters properly encoded for special characters
2. **Timezone Support**: Accurate timezone handling and display
3. **Resource Integration**: Dynamic content from `calendar://events/today` cache
4. **Performance Optimization**: 5-minute cached event data for fast template generation
3. **Fallback Options**: Multiple ways to add events (links + ICS file)
4. **Mobile Optimization**: Touch-friendly calendar buttons
5. **Visual Hierarchy**: Clear event information layout
6. **Professional Styling**: Branded calendar integration design

This calendar integration template provides comprehensive event scheduling capabilities with seamless multi-platform calendar support, ensuring maximum compatibility and user experience.
"""
        
        return PromptMessage(
            content=TextContent(type="text", text=calendar_guide),
            role="assistant"
        )

    def _get_base_email_styles(self, primary_color, accent_color):
        """Helper to generate base email CSS styles"""
        return f"""
body {{
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, Arial, sans-serif;
    line-height: 1.6;
    color: #333;
    margin: 0;
    padding: 20px;
    background-color: #f5f5f5;
}}
.email-container {{
    max-width: 600px;
    margin: 0 auto;
    background: white;
    border-radius: 12px;
    overflow: hidden;
    box-shadow: 0 4px 20px rgba(0,0,0,0.1);
}}
.header {{
    background: linear-gradient(135deg, {primary_color} 0%, {accent_color} 100%);
    color: white;
    padding: 30px 20px;
    text-align: center;
}}
.content {{
    padding: 30px;
}}
.button {{
    display: inline-block;
    background: linear-gradient(135deg, {primary_color} 0%, {accent_color} 100%);
    color: white !important;
    padding: 15px 30px;
    text-decoration: none;
    border-radius: 25px;
    margin: 15px 0;
    font-weight: 600;
}}
"""