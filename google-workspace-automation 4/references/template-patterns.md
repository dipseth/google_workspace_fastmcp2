# Template Patterns

## Overview

RiversUnlimited includes a sophisticated Jinja2 templating system with reusable macros for creating beautiful, token-efficient output. The system enables dynamic content generation, visual formatting, and runtime macro creation.

## Pre-Built Macros

### 1. Gmail Label Chips

Creates visual Gmail label chips with color coding:

```jinja2
{{ render_gmail_labels_chips(service://gmail/labels, 'Label summary for: ' + user://current/email.email) }}
```

**Features:**
- Color-coded label indicators
- Unread count statistics
- Visual hierarchy

### 2. Report Generation

Generates comprehensive report documents:

```jinja2
{{ generate_report_doc() }}
```

**Use Cases:**
- Project status reports
- Analytics summaries
- Executive briefings

### 3. Meeting Notes

Creates formatted meeting notes templates:

```jinja2
{{ generate_meeting_notes_doc() }}
```

**Includes:**
- Agenda sections
- Participant lists
- Action items tracking
- Decision points

### 4. Calendar Dashboard

Builds comprehensive calendar views:

```jinja2
{{ render_calendar_dashboard(service://calendar/calendars, service://calendar/events, 'Calendar Summary') }}
```

**Features:**
- Event summaries
- Timezone handling
- Visual layouts
- Conflict detection

### 5. Beautiful Emails

Creates styled HTML email templates:

```jinja2
{{ render_beautiful_email1(title="Hello World") }}
```

**Features:**
- Modern HTML formatting
- Responsive design
- Brand consistency
- Cross-client compatibility

### 6. Gmail Filters Dashboard

Organizes Gmail filters with visualization:

```jinja2
{{ render_gmail_filters_dashboard(service://gmail/filters, 'Email Organization Dashboard') }}
```

**Includes:**
- Category grouping
- Rule visualization
- Performance insights
- Filter recommendations

## Creating Custom Macros

### Dynamic Macro Creation

Create macros at runtime that persist across sessions:

```python
riversunlimited:create_template_macro(
    macro_name="my_custom_macro",
    macro_content="""{% macro my_custom_macro(data, title="Default Title") %}
<div class="custom-format">
  <h2>{{ title }}</h2>
  <ul>
    {% for item in data %}
    <li>{{ item.name }}: {{ item.value }}</li>
    {% endfor %}
  </ul>
</div>
{% endmacro %}""",
    description="Custom macro for formatting data items",
    usage_example='{{ my_custom_macro([{"name": "Item", "value": "123"}]) }}',
    persist_to_file=true,  # Saves for future use
    user_google_email="me"
)
```

**Returns:**
- Macro registration confirmation
- Usage instructions
- Template path
- Immediate availability status

### Macro Design Patterns

#### Pattern 1: List Formatting

```jinja2
{% macro format_list(items, title) %}
<div class="list-container">
  <h3>{{ title }}</h3>
  <ul>
    {% for item in items %}
    <li>{{ item }}</li>
    {% endfor %}
  </ul>
</div>
{% endmacro %}
```

#### Pattern 2: Conditional Styling

```jinja2
{% macro status_badge(status) %}
<span style="background: {% if status == 'complete' %}green{% elif status == 'pending' %}yellow{% else %}red{% endif %}; padding: 4px 8px; border-radius: 3px;">
  {{ status | upper }}
</span>
{% endmacro %}
```

#### Pattern 3: Data Tables

```jinja2
{% macro data_table(rows, headers) %}
<table style="border-collapse: collapse; width: 100%;">
  <thead>
    <tr>
      {% for header in headers %}
      <th style="border: 1px solid #ddd; padding: 8px; background: #f2f2f2;">{{ header }}</th>
      {% endfor %}
    </tr>
  </thead>
  <tbody>
    {% for row in rows %}
    <tr>
      {% for cell in row %}
      <td style="border: 1px solid #ddd; padding: 8px;">{{ cell }}</td>
      {% endfor %}
    </tr>
    {% endfor %}
  </tbody>
</table>
{% endmacro %}
```

#### Pattern 4: Dashboard Cards

```jinja2
{% macro dashboard_card(title, value, trend, color="#3498db") %}
<div style="background: white; border-left: 4px solid {{ color }}; padding: 20px; margin: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
  <h4 style="margin: 0; color: #7f8c8d; font-size: 14px;">{{ title }}</h4>
  <div style="font-size: 32px; font-weight: bold; margin: 10px 0; color: #2c3e50;">{{ value }}</div>
  {% if trend %}
  <div style="color: {% if trend > 0 %}#27ae60{% else %}#e74c3c{% endif %}; font-size: 14px;">
    {{ "▲" if trend > 0 else "▼" }} {{ trend }}%
  </div>
  {% endif %}
</div>
{% endmacro %}
```

## URI-Based Resources

### Resource Patterns

Macros can access URI-based resources directly:

```jinja2
{# Gmail resources #}
service://gmail/labels
service://gmail/filters
service://gmail/messages

{# Drive resources #}
service://drive/files
service://drive/folders

{# Calendar resources #}
service://calendar/calendars
service://calendar/events

{# User context #}
user://current/email
user://current/profile
```

### Resource Usage Example

```jinja2
{% macro user_summary() %}
<div>
  <h2>User: {{ user://current/email.email }}</h2>
  <p>Labels: {{ service://gmail/labels | length }}</p>
  <p>Calendars: {{ service://calendar/calendars | length }}</p>
</div>
{% endmacro %}
```

## Token Efficiency

### Benefits

Templates provide 60-80% token reduction:

**Without Template:**
```
Manually describe each label with color, name, count...
Result: 500+ tokens
```

**With Template:**
```jinja2
{{ render_gmail_labels_chips(service://gmail/labels) }}
Result: 50 tokens, beautiful output
```

### Best Practices

1. **Reuse Macros:** Create once, use everywhere
2. **Parameterize:** Make macros flexible with parameters
3. **Compose:** Build complex macros from simple ones
4. **Cache:** Store frequently used macros permanently

## Styling Guidelines

### HTML Email-Safe Styles

Always use inline styles for emails:

```html
<div style="font-family: Arial, sans-serif; padding: 20px;">
  <!-- Content -->
</div>
```

### Responsive Patterns

```html
<div style="max-width: 600px; margin: 0 auto;">
  <!-- Mobile-friendly content -->
</div>
```

### Color Schemes

Standard colors for consistency:

- Success: `#27ae60` (green)
- Warning: `#f39c12` (orange)
- Error: `#e74c3c` (red)
- Primary: `#3498db` (blue)
- Secondary: `#7f8c8d` (gray)
- Dark: `#2c3e50`
- Light: `#ecf0f1`

## Advanced Features

### Macro Composition

Build complex macros from simpler ones:

```jinja2
{% macro project_dashboard(project_data) %}
{{ dashboard_card("Tasks", project_data.tasks_count, project_data.tasks_trend) }}
{{ dashboard_card("Issues", project_data.issues_count, project_data.issues_trend, "#e74c3c") }}
{{ data_table(project_data.recent_activities, ["Date", "Activity", "User"]) }}
{% endmacro %}
```

### Conditional Logic

```jinja2
{% macro smart_summary(data) %}
{% if data.type == "email" %}
  {{ render_beautiful_email1(title=data.subject) }}
{% elif data.type == "calendar" %}
  {{ render_calendar_dashboard(data.calendars, data.events) }}
{% else %}
  {{ generate_report_doc() }}
{% endif %}
{% endmacro %}
```

### Filters and Functions

Jinja2 built-in filters:

```jinja2
{{ name | upper }}
{{ count | string }}
{{ items | length }}
{{ date | date_format }}
{{ text | truncate(100) }}
{{ list | join(", ") }}
```

## Testing Macros

### Quick Test

After creating a macro, test immediately:

```python
# Create test data
test_data = [
    {"name": "Task 1", "status": "complete"},
    {"name": "Task 2", "status": "pending"}
]

# Use macro (it's immediately available)
# In next tool call or output generation, reference it
```

### Iteration

1. Create initial macro version
2. Test with real data
3. Identify improvements
4. Update macro (create new version or modify)
5. Set `persist_to_file=true` when satisfied

## Macro Registry

### Listing Available Macros

All macros are automatically registered and discoverable via:
- Template middleware
- Macro discovery system
- Dynamic loading at runtime

### Macro Metadata

Each macro stores:
- Name and description
- Usage examples
- Creation timestamp
- Template file path
- Parameters and defaults

### Discovery Pattern

```python
# Macros are auto-discovered and loaded
# Reference them directly in tool outputs
# Use {{ macro_name(...) }} syntax
```

## Production Tips

### 1. Design for Reusability

Create generic macros with parameters:

```jinja2
{% macro card(title, content, color="#3498db") %}
<!-- Generic card that works for many use cases -->
{% endmacro %}
```

### 2. Document Parameters

Include clear parameter descriptions:

```python
description="Creates a status card with title, content, and custom color (default: blue)"
usage_example='{{ card("Title", "Content", "#27ae60") }}'
```

### 3. Persist Important Macros

Set `persist_to_file=true` for macros you'll reuse:

```python
persist_to_file=true  # Saves across sessions
```

### 4. Version Control

When updating macros, consider:
- Creating new version with different name
- Testing before overwriting
- Documenting changes in description

## Integration with Other Tools

### Drive Documents

Use macros to format Drive document content:

```python
riversunlimited:create_doc(
    title="Project Report",
    content="{{ generate_report_doc() }}",  # Macro generates content
    content_mime_type="text/html"
)
```

### Gmail Messages

Beautiful emails with macros:

```python
riversunlimited:send_gmail_message(
    to="user@example.com",
    subject="Weekly Update",
    body="{{ render_beautiful_email1(title='Weekly Report') }}",
    content_type="html"
)
```

### Sheets Reports

Format cell content with macros:

```python
# Generate formatted content
formatted = render_macro(data)
# Write to sheet
modify_sheet_values(values=formatted)
```
