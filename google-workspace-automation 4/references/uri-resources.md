# URI Resources

## Overview

RiversUnlimited provides URI-based resource access patterns that are 30x faster than traditional API calls. These URIs enable instant access to cached data through the TagBasedResourceMiddleware.

## URI Patterns

### Service Resources

Access Google Workspace service data via URI syntax:

```
service://<service_name>/<resource_type>
```

### User Resources

Access current user context:

```
user://current/<attribute>
```

## Gmail Resources

### Labels

```jinja2
service://gmail/labels
```

**Returns:** Complete list of Gmail labels with metadata including label ID, name, type, color information, message counts (total, unread), and visibility settings.

**Usage:**
```jinja2
{{ render_gmail_labels_chips(service://gmail/labels) }}

{% for label in service://gmail/labels %}
  Label: {{ label.name }}, Unread: {{ label.messagesUnread }}
{% endfor %}
```

### Filters

```jinja2
service://gmail/filters
```

**Returns:** All Gmail filters/rules with filter ID, criteria, actions (labels, forwarding, etc.), and creation metadata.

## Calendar Resources

### Calendars

```jinja2
service://calendar/calendars
```

**Returns:** All accessible calendars with calendar ID, summary, time zone, access roles, and color settings.

### Events

```jinja2
service://calendar/events
```

**Returns:** Recent/upcoming calendar events with event ID, summary, description, start/end times with timezone, location, attendees, organizer information, and attachments.

## User Context

### Current Email

```jinja2
user://current/email
```

**Returns:** Authenticated user's email address.

**Usage:**
```jinja2
<p>Welcome, {{ user://current/email }}</p>
```

## Performance

**Traditional API call:** ~200-500ms  
**URI-based access:** ~10-20ms (30x faster)

URIs are cached after first API call and persist for session duration with automatic refresh on updates.

## When to Use

**Use URIs when:**
- Accessing data for display/templates
- Data already fetched this session
- Performance is critical
- Working within templates/macros

**Use Tools when:**
- First-time data access
- Performing mutations (create, update, delete)
- Need specific filters or parameters
- Requiring latest real-time data

## Template Usage

```jinja2
{% macro user_stats() %}
<div class="stats">
  <h2>Stats for {{ user://current/email }}</h2>
  <ul>
    <li>Labels: {{ service://gmail/labels | length }}</li>
    <li>Calendars: {{ service://calendar/calendars | length }}</li>
  </ul>
</div>
{% endmacro %}
```
