# Natural Language Card Patterns for Google Chat

## Overview

The `send_dynamic_card` tool now supports enhanced natural language processing (NLP) for creating Google Chat cards. You can describe what you want in plain English, and the NLP parser will extract and structure the card parameters automatically.

## Basic Card Elements

### Title, Subtitle, and Text

**Patterns:**
- `titled 'Your Title'` or `with title 'Your Title'`
- `with subtitle 'Your Subtitle'` or `subtitled 'Your Subtitle'`
- `with text 'Your text content'` or `saying 'Your text content'`
- `with body 'Your body text'` or `with content 'Your content'`

**Examples:**
```
"Create a card titled 'Project Status' with subtitle 'Weekly Update' and text 'All systems operational'"

"Make a card with title 'Alert' and body 'System maintenance scheduled for tonight'"
```

### Images

**Patterns:**
- `with image {url}` or `showing image {url}`
- `with image of {description}` (triggers image search)
- `with picture {url}` or `with photo {url}`
- `with {description} image` (e.g., "with cat image")

**Examples:**
```
"Create a card with an image https://example.com/logo.png"

"Make a card showing a picture of a sunset"
```

## Buttons

### Basic Buttons

**Patterns:**
- `with button 'Button Text'` or `with buttons: Button1, Button2, Button3`
- `with {color} button 'Text'` (e.g., "with green button 'Approve'")
- `buttons: 'Text1' and 'Text2'` or `buttons 'Text1', 'Text2', 'Text3'`

### Button Styles

**Color Mappings:**
- Green → FILLED style with green color
- Red → FILLED style with red color
- Blue → FILLED style with blue color
- Gray/Grey → OUTLINED style
- Transparent → BORDERLESS style

**Style Keywords:**
- `filled` → FILLED button style
- `outlined` → OUTLINED button style
- `borderless` or `text` → BORDERLESS button style
- `tonal` → FILLED_TONAL button style

**Examples:**
```
"Create a card with buttons: 'Approve' in green filled style, 'Reject' in red outlined style"

"Add buttons: a green 'Submit' button and a red 'Cancel' button"
```

### Button Actions

**Patterns:**
- `'Button Text' linking to {url}`
- `'Button Text' that opens {url}`
- `'Button Text' ({url})`
- Default action if URL not specified: `https://example.com`

**Examples:**
```
"Create a card with button 'View Details' linking to https://docs.example.com"

"Add a button 'GitHub' that opens https://github.com"
```

## Sections

### Basic Sections

**Patterns:**
- `with section 'Section Name'` or `with sections: 'Section1' and 'Section2'`
- `sections: 'Name1', 'Name2', 'Name3'`
- `with {description} section` (e.g., "with User Info section")

**Examples:**
```
"Create a card with sections: 'Overview', 'Details', and 'Actions'"

"Make a card with a 'Statistics' section and a 'User Info' section"
```

### Collapsible Sections

**Patterns:**
- `collapsible section 'Name'`
- `expandable section 'Name'`
- `section 'Name' that can be collapsed`
- `with {n} uncollapsible widgets` (specifies how many widgets are always visible)

**Examples:**
```
"Create a card with a collapsible section 'Advanced Options' showing 2 uncollapsible widgets"

"Add an expandable 'Details' section"
```

## DecoratedText Widgets

### Basic DecoratedText

**Patterns:**
- `decoratedText with {icon} icon and '{text}'`
- `decoratedText showing '{text}' with {icon} icon`
- `decoratedText: '{text}' with top label '{label}'`

### Icons

**Supported Icon Names:**
- **Person/User:** `person`, `people`, `user`
- **Email:** `email`, `mail`, `inbox`
- **Calendar:** `calendar`, `event`, `schedule`
- **Clock/Time:** `clock`, `time`, `schedule`
- **Location:** `location`, `map`, `place`
- **Phone:** `phone`, `call`
- **Star:** `star`, `bookmark`
- **Check:** `check`, `check_circle`, `done`, `complete`
- **Warning:** `warning`, `alert`, `error`
- **Info:** `info`, `information`
- **Chart:** `chart`, `graph`, `analytics`
- **Document:** `document`, `file`, `description`
- **Settings:** `settings`, `gear`, `config`
- **Dollar:** `dollar`, `money`, `payment`
- **Home:** `home`, `house`
- **Database:** `database`, `storage`

### Labels and Additional Elements

**Patterns:**
- `with top label '{label}'`
- `with bottom label '{label}'`
- `with button '{text}'` (adds button to decoratedText)
- `with switch control` or `with toggle`

**Examples:**
```
"Create decoratedText with person icon, top label 'User', text 'John Doe', bottom label 'Administrator'"

"Add decoratedText showing 'Notifications Enabled' with a switch control that is checked"
```

## Grid Layouts

**Patterns:**
- `with grid layout` or `in a grid`
- `grid with {n} columns`
- `grid showing: item1, item2, item3`

**Examples:**
```
"Create a card with a grid layout showing 2 columns: Product A and Product B"

"Make a grid with 3 columns displaying different metrics"
```

## Complex Patterns

### Dashboard Cards

```
"Create a status dashboard card titled 'System Health' with subtitle 'Live Status'.
Add sections:
- 'Server Status' section with decoratedText showing 'Online' with check circle icon
- 'Database Status' section with decoratedText showing 'Connected' with database icon
- 'Actions' section with buttons: 'Restart' in red, 'Backup' in blue"
```

### Notification Cards

```
"Create a notification card titled 'Alert' with warning icon.
Add decoratedText with:
- Red text saying 'Critical: High CPU Usage'
- Bottom label 'Detected at 10:45 AM'
- Button 'View Details' linking to monitoring dashboard"
```

### Form-like Cards

```
"Create a form card with sections:
- 'User Information' with decoratedText showing name and email with person icon
- 'Settings' with switch controls for 'Enable Notifications' and 'Auto-backup'
- 'Actions' with buttons: 'Save' in green, 'Cancel' in gray"
```

## HTML Content Support

The NLP parser preserves HTML formatting in text content:

**Supported HTML Tags:**
- `<b>bold</b>` - Bold text
- `<i>italic</i>` - Italic text
- `<u>underline</u>` - Underlined text
- `<font color="#HEX">colored text</font>` - Colored text
- `<br/>` - Line break

**Example:**
```
"Create a card with text: 'Status: <b>Active</b><br/>Priority: <font color="#FF0000">High</font>'"
```

## Validation and Auto-Correction

The NLP parser automatically validates and corrects parameters to meet Google Chat API requirements:

### Field Length Limits
- **Title/Subtitle:** Maximum 200 characters (auto-truncated with "...")
- **Text:** Maximum 4000 characters (auto-truncated with "...")
- **Button text:** Maximum 40 characters

### Count Limits
- **Buttons:** Maximum 6 per card (extras are dropped)
- **Sections:** Maximum 100 per card
- **Widgets per section:** Maximum 100

### URL Validation
- Automatically adds `https://` to bare domain URLs
- Example: `example.com` → `https://example.com`

### Icon Validation
- Unknown icons default to `STAR` icon
- Icon names are case-insensitive

## Integration with card_params

The NLP parser works seamlessly with explicit `card_params`. User-provided parameters always take priority:

```python
{
    "card_description": "Create a card titled 'NLP Title' with text 'NLP Text'",
    "card_params": {
        "title": "Override Title",  # This overrides the NLP-extracted title
        "subtitle": "Added Subtitle"  # This is added since NLP didn't extract a subtitle
    }
}
```

## Best Practices

1. **Be specific** - The more detailed your description, the better the extraction
2. **Use quotes** - Wrap text content in quotes for accurate extraction
3. **Order matters** - List sections and widgets in the order you want them displayed
4. **Color keywords** - Use color names for automatic style mapping
5. **Icon keywords** - Use common icon names for automatic icon selection

## Troubleshooting

### Card shows as "simple_fallback"
- The description might be too simple or ambiguous
- Try adding more specific widget types (decoratedText, sections, buttons)

### Missing elements
- Ensure text is properly quoted
- Check that section names are clearly identified
- Verify button text is within 40 character limit

### Validation errors
- Long text is automatically truncated
- Excess buttons are automatically removed
- Invalid URLs are auto-corrected with https://

## Examples Gallery

### Simple Information Card
```
"Create a card titled 'Welcome' with subtitle 'Getting Started' and text 'Click below to begin your journey' with a green button 'Start Now'"
```

### Status Dashboard
```
"Create a dashboard with sections: 'System Status' showing decoratedText with check icon and 'All Systems Operational', 'Performance' showing decoratedText with chart icon and 'CPU: 45%, Memory: 62%'"
```

### Interactive Form
```
"Create a form card titled 'Settings' with decoratedText widgets: 'Dark Mode' with switch control, 'Notifications' with toggle that is checked, and buttons: 'Save Changes' in green filled style, 'Reset' in red outlined style"
```

### Rich Media Card
```
"Create a card with title 'Product Launch', image https://example.com/product.jpg, text with HTML: '<b>New Features:</b><br/>• Enhanced performance<br/>• Better UI<br/>• Cloud sync', and buttons: 'Learn More' and 'Buy Now' in green"
```

This NLP enhancement makes creating Google Chat cards more intuitive and natural, allowing you to focus on content rather than structure.