# Cross-Service Automation Recipes

## Overview

The real power of RiversUnlimited comes from combining multiple Google Workspace services into intelligent workflows. This reference provides proven recipes for common automation scenarios.

## Email → Drive Workflows

### Recipe 1: Save Email Attachments to Drive

**Scenario:** Automatically save all invoice attachments to a Drive folder

```python
# Step 1: Search for invoice emails
messages = riversunlimited:search_gmail_messages(
    query="has:attachment subject:invoice",
    page_size=20
)

# Step 2: For each message, get full content
for msg_id in message_ids:
    content = riversunlimited:get_gmail_message_content(message_id=msg_id)
    
    # Step 3: Extract attachments (via Drive API)
    # Step 4: Upload to specific folder
    riversunlimited:upload_to_drive(
        path=attachment_path,
        folder_id="invoices_folder_id"
    )
    
    # Step 5: Label email as processed
    riversunlimited:modify_gmail_message_labels(
        message_id=msg_id,
        add_label_ids=["processed"],
        remove_label_ids=["inbox"]
    )
```

### Recipe 2: Email Summary to Document

**Scenario:** Create a weekly summary document from important emails

```python
# Step 1: Search recent important emails
emails = riversunlimited:search_gmail_messages(
    query="is:important newer_than:7d",
    page_size=50
)

# Step 2: Get full content batch
contents = riversunlimited:get_gmail_messages_content_batch(
    message_ids=email_ids,
    format="full"
)

# Step 3: Generate summary using template
summary = format_email_summary(contents)

# Step 4: Create Drive document
doc = riversunlimited:create_doc(
    title=f"Email Summary - Week {week_number}",
    content=summary,
    content_mime_type="text/html"
)

# Step 5: Share with team
riversunlimited:share_drive_files(
    file_ids=[doc.document_id],
    email_addresses=["team@company.com"],
    role="reader"
)
```

## Calendar → Email Workflows

### Recipe 3: Meeting Preparation Assistant

**Scenario:** Send preparation materials before meetings

```python
# Step 1: Get upcoming events (next 24 hours)
events = riversunlimited:list_events(
    calendar_id="primary",
    time_min="now",
    time_max="now+24hours",
    max_results=10
)

# Step 2: For each meeting with attachments
for event in events:
    if event.attachments:
        # Step 3: Get Drive document content
        doc_content = riversunlimited:get_doc_content(
            document_id=attachment.fileId
        )
        
        # Step 4: Send reminder email with summary
        riversunlimited:send_gmail_message(
            to=event.organizer,
            subject=f"Prep for: {event.summary}",
            body=f"Meeting in {hours} hours. Document summary: {summary}",
            content_type="html"
        )
```

### Recipe 4: Post-Meeting Action Items

**Scenario:** Create tasks from meeting notes

```python
# Step 1: Get today's completed meetings
meetings = riversunlimited:list_events(
    time_min="today_start",
    time_max="now"
)

# Step 2: For meetings with notes attachments
for meeting in meetings:
    # Step 3: Get meeting notes
    notes = riversunlimited:get_doc_content(
        document_id=meeting.notes_doc_id
    )
    
    # Step 4: Extract action items (parse notes)
    action_items = extract_action_items(notes)
    
    # Step 5: Create spreadsheet tracker
    tracker = riversunlimited:create_spreadsheet(
        title=f"Action Items - {meeting.summary}",
        sheet_names=["Tasks", "Owners"]
    )
    
    # Step 6: Populate with action items
    riversunlimited:modify_sheet_values(
        spreadsheet_id=tracker.spreadsheet_id,
        range_name="Tasks!A1:D100",
        values=format_action_items(action_items)
    )
    
    # Step 7: Share with attendees
    riversunlimited:share_drive_files(
        file_ids=[tracker.spreadsheet_id],
        email_addresses=meeting.attendees
    )
```

## Drive → Email Workflows

### Recipe 5: Document Review Reminder

**Scenario:** Send reminders for pending document reviews

```python
# Step 1: Find documents awaiting review
docs = riversunlimited:search_drive_files(
    query="name contains 'REVIEW' and modifiedTime > '7daysAgo'",
    mime_type="GOOGLE_DOCS",
    page_size=50
)

# Step 2: Check document status
for doc in docs:
    content = riversunlimited:get_doc_content(document_id=doc.id)
    
    # Step 3: If not reviewed, send reminder
    if not is_reviewed(content):
        riversunlimited:send_gmail_message(
            to=doc.owner,
            subject=f"Review Pending: {doc.name}",
            body=f"Document link: {doc.webViewLink}"
        )
```

### Recipe 6: Shared Folder Activity Digest

**Scenario:** Daily summary of changes in shared folders

```python
# Step 1: List items in shared folder
items = riversunlimited:list_drive_items(
    folder_id="shared_folder_id",
    page_size=100
)

# Step 2: Filter recently modified (last 24h)
recent_changes = filter_by_time(items, "24h")

# Step 3: Create formatted summary
summary = format_folder_digest(recent_changes)

# Step 4: Send to team
riversunlimited:send_gmail_message(
    to=["team@company.com"],
    subject="Daily Folder Digest",
    body=summary,
    content_type="html"
)
```

## Multi-Service Dashboard

### Recipe 7: Executive Dashboard

**Scenario:** Comprehensive workspace activity dashboard

```python
# Step 1: Gather data from all services

# Email metrics
email_stats = riversunlimited:search_gmail_messages(
    query="newer_than:7d",
    page_size=100
)
unread = riversunlimited:search_gmail_messages(query="is:unread")

# Calendar metrics
events = riversunlimited:list_events(
    time_min="7daysAgo",
    time_max="now",
    max_results=100
)

# Drive metrics
recent_docs = riversunlimited:search_drive_files(
    query="modifiedTime > '7daysAgo'",
    page_size=100
)

# Forms metrics (if using Forms)
# ... gather form responses

# Step 2: Generate visual dashboard using template
dashboard = render_executive_dashboard(
    email_stats=email_stats,
    calendar_stats=events,
    drive_stats=recent_docs
)

# Step 3: Create presentation
presentation = riversunlimited:create_presentation(
    title=f"Executive Dashboard - Week {week}"
)

# Step 4: Add slides with visualizations
riversunlimited:add_slide(
    presentation_id=presentation.presentation_id,
    # Content from dashboard template
)

# Step 5: Share with leadership
riversunlimited:share_drive_files(
    file_ids=[presentation.presentation_id],
    email_addresses=leadership_emails
)
```

## Email + Calendar + Drive

### Recipe 8: Project Status Reporter

**Scenario:** Automated weekly project status report

```python
# Step 1: Search for project-related emails
project_emails = riversunlimited:search_gmail_messages(
    query="label:project-alpha newer_than:7d"
)

# Step 2: Get project meetings from calendar
project_meetings = riversunlimited:list_events(
    time_min="7daysAgo",
    time_max="now"
    # Filter by project-related events
)

# Step 3: Get project documents from Drive
project_docs = riversunlimited:search_drive_files(
    query="fullText contains 'Project Alpha' and modifiedTime > '7daysAgo'"
)

# Step 4: Aggregate and analyze
report_data = {
    "email_count": len(project_emails),
    "meetings_count": len(project_meetings),
    "documents_updated": len(project_docs),
    "key_discussions": extract_key_topics(project_emails),
    "upcoming_milestones": extract_milestones(project_meetings)
}

# Step 5: Create comprehensive report
report = riversunlimited:create_doc(
    title="Project Alpha - Weekly Status",
    content=render_project_report(report_data),
    content_mime_type="text/html"
)

# Step 6: Store report in Qdrant for future reference
# (Automatic - creation is logged)

# Step 7: Email report to stakeholders
riversunlimited:send_gmail_message(
    to=stakeholder_emails,
    subject="Project Alpha Weekly Status",
    body=f"Report available: {report.webViewLink}"
)
```

## Forms + Sheets + Email

### Recipe 9: Survey Response Processor

**Scenario:** Process survey responses and send thank-you emails

```python
# Step 1: Get form responses
responses = riversunlimited:list_form_responses(
    form_id="survey_form_id",
    page_size=100
)

# Step 2: Create analysis spreadsheet
sheet = riversunlimited:create_spreadsheet(
    title="Survey Analysis",
    sheet_names=["Responses", "Analysis", "Charts"]
)

# Step 3: Populate responses
riversunlimited:modify_sheet_values(
    spreadsheet_id=sheet.spreadsheet_id,
    range_name="Responses!A1:Z1000",
    values=format_responses(responses)
)

# Step 4: Send thank you emails
for response in responses:
    riversunlimited:send_gmail_message(
        to=response.respondent_email,
        subject="Thank you for your feedback",
        body=render_thank_you_email(response),
        content_type="html"
    )

# Step 5: Create summary report
summary = analyze_responses(responses)
riversunlimited:create_doc(
    title="Survey Summary",
    content=render_survey_summary(summary)
)
```

## Qdrant Integration Patterns

### Recipe 10: Historical Context Assistant

**Scenario:** Use past interactions to inform current work

```python
# Step 1: Search historical context
past_context = riversunlimited:search(
    query="client communication project timeline",
    limit=10
)

# Step 2: Fetch relevant details
for result in past_context.results:
    details = riversunlimited:fetch(point_id=result.id)
    # Build context from historical data

# Step 3: Use context to inform new response
# Compose email with historical awareness
riversunlimited:send_gmail_message(
    to="client@example.com",
    subject="Project Update",
    body=compose_with_context(past_context, current_update)
)
```

### Recipe 11: Pattern Detection and Automation

**Scenario:** Detect patterns in tool usage and automate

```python
# Step 1: Get analytics
analytics = riversunlimited:get_tool_analytics(
    summary_only=false,
    group_by="tool_name",
    start_date="30daysAgo"
)

# Step 2: Identify frequent patterns
patterns = detect_patterns(analytics)
# E.g., "Every Monday, search for weekly reports and email to team"

# Step 3: Create automation rules
for pattern in patterns:
    if pattern.confidence > 0.8:
        # Create filter, calendar event, or scheduled task
        automate_pattern(pattern)
```

## Template-Enhanced Workflows

### Recipe 12: Beautiful Status Updates

**Scenario:** Generate visually appealing status updates

```python
# Step 1: Gather status data
email_count = get_email_count()
meeting_count = get_meeting_count()
doc_updates = get_document_updates()

# Step 2: Create custom macro for status
riversunlimited:create_template_macro(
    macro_name="status_update",
    macro_content="""
    {% macro status_update(data) %}
    {{ dashboard_card("Emails", data.emails, data.email_trend) }}
    {{ dashboard_card("Meetings", data.meetings, data.meeting_trend) }}
    {{ dashboard_card("Documents", data.docs, data.doc_trend) }}
    {% endmacro %}
    """
)

# Step 3: Generate beautiful update
update = render_status_update({
    "emails": email_count,
    "meetings": meeting_count,
    "docs": doc_updates
})

# Step 4: Distribute via multiple channels
riversunlimited:send_gmail_message(to=team_emails, body=update)
riversunlimited:send_message(space_id=chat_space, message_text=update)
riversunlimited:create_doc(title="Status Update", content=update)
```

## Best Practices

### 1. Error Handling

Always handle potential failures:

```python
try:
    result = riversunlimited:search_gmail_messages(query=query)
    if result.total_found == 0:
        # Handle no results
        pass
except Exception as e:
    # Log to Qdrant for analysis
    # Send alert email
    pass
```

### 2. Rate Limiting

Be mindful of API quotas:

```python
# Use batch operations when possible
riversunlimited:get_gmail_messages_content_batch(message_ids=ids)
# Instead of individual calls in loop
```

### 3. Data Validation

Validate data between services:

```python
# Verify document exists before sharing
doc = riversunlimited:get_drive_file_content(file_id=doc_id)
if doc.found:
    riversunlimited:share_drive_files(file_ids=[doc_id])
```

### 4. Audit Trail

Use Qdrant for audit logging:

```python
# All operations automatically logged
# Query later for compliance or debugging
riversunlimited:search_tool_history(
    query="file shared with external domain"
)
```

### 5. Reusable Components

Extract common patterns into reusable functions:

```python
def send_with_attachment(to, subject, body, drive_file_id):
    # Get Drive file
    # Attach to email
    # Send
    pass

# Reuse across workflows
send_with_attachment(to=user, subject=subj, drive_file_id=doc_id)
```

## Performance Tips

### Parallel Operations

Some operations can be parallelized:

```python
# Search multiple services simultaneously
# (When operations are independent)
```

### Caching

Cache frequently accessed data:

```python
# Cache label list for session
labels = get_gmail_labels()  # Cache result
# Reuse throughout workflow
```

### Selective Loading

Only fetch what you need:

```python
# Use search to filter, then fetch details
# Don't fetch all, then filter in code
```

## Common Pitfalls

### 1. Over-fetching

Don't fetch full content when metadata sufficient:

```python
# Good: Use search to filter
results = riversunlimited:search_gmail_messages(query="specific_query")

# Bad: Fetch all, filter in code
all_messages = riversunlimited:search_gmail_messages(query="", page_size=1000)
filtered = [m for m in all_messages if condition]
```

### 2. Ignoring Batching

Use batch operations for efficiency:

```python
# Good: Batch operation
riversunlimited:get_gmail_messages_content_batch(message_ids=ids)

# Bad: Loop with individual calls
for msg_id in ids:
    content = riversunlimited:get_gmail_message_content(message_id=msg_id)
```

### 3. Missing Error Context

Include context in error handling:

```python
# Good: Contextual error
try:
    create_doc(title=title)
except Exception as e:
    log(f"Failed to create doc '{title}': {e}")

# Bad: Generic error
try:
    create_doc(title=title)
except Exception as e:
    log(f"Error: {e}")
```
