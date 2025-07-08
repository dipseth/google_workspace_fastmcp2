# Google Chat Card Fixes Documentation

This document explains the fixes implemented to address issues with Google Chat cards and provides guidance on how to use the improved functionality.

## Issues Fixed

### 1. Announcement Style Issue

**Problem:** The "announcement" style was adding an unsupported `imageStyle` field to the card header, causing a 400 error with the message:
```
"Unknown name "imageStyle" at 'message.cards_v2[0].card.header': Cannot find field."
```

**Fixes Implemented:**
1. In `smart_card_api.py`:
   - Removed the unsupported `imageStyle` field from the `_apply_card_style` function
   - Added alternative styling using supported elements (decoratedText with "ANNOUNCEMENT" label)

2. In `unified_card_tool.py`:
   - Modified the `_convert_card_to_google_format` function to automatically remove any unsupported `imageStyle` fields from card headers

**How to Use:** You can now safely use the "announcement" style with any of the card tools:
```json
{
  "style": "announcement",
  "content": "# Important Announcement\n\nThis is an important announcement."
}
```

### 2. Template Usage Issue

**Problem:** When trying to use templates by name (e.g., "Bullet List Card"), the search was failing because:
- Templates are stored in Qdrant with unique IDs (UUIDs)
- The search was performing a text search rather than an exact ID lookup
- The search query construction wasn't matching the stored template names

**Fixes Implemented:**
1. In `smart_card_api.py`:
   - Modified the `create_card_from_template` function to work with both template names and IDs
   - Added logic to detect if the input looks like a UUID (template ID)
   - If it looks like an ID, tries to get the template directly using `get_template`
   - Falls back to the name search approach if direct lookup fails

2. In `unified_card_tool.py`:
   - Enhanced the `_find_card_template` function to support both direct ID lookup and semantic search
   - Updated the `get_card_template` tool to accept either template IDs or names
   - Updated the `list_card_templates` function to use the improved template finding logic

**How to Use:** You can now use templates by either name or ID:

```json
// Using template name
{
  "template_name_or_id": "Bullet List Card",
  "content": {
    "title": "Smart Card Testing Results",
    "subtitle": "What works and what doesn't"
  }
}

// Using template ID (more reliable)
{
  "template_id_or_name": "4e4a2881-8de2-4adf-bcbd-5fa814c8657a",
  "content": {
    "title": "Smart Card Testing Results",
    "subtitle": "What works and what doesn't"
  }
}
```

## Compatibility Summary

Based on testing, here's what works reliably with Google Chat cards:

✅ **Works Reliably:**
- Simple cards with basic content
- Default and report styles
- Bullet points in all card types
- Basic markdown (bold, italic)
- Webhook delivery for properly formatted cards
- Announcement style (with the new implementation)
- Template usage by ID or name (with improved lookup)

❌ **Known Issues:**
- Numbered lists (cause formatting errors)
- Template retrieval by name may still be less reliable than by ID

## Template IDs

For reference, here are the IDs of the templates created during testing:
- "Reliable Webhook Card" → ID: `4913387a-99d7-4fa7-aa6e-81df68c8a4f8`
- "Bullet List Card" → ID: `4e4a2881-8de2-4adf-bcbd-5fa814c8657a`

## Best Practices

1. **Use Template IDs When Possible**: While template name lookup has been improved, using the template ID is still more reliable.

2. **Avoid Numbered Lists**: Use bullet points instead of numbered lists to avoid formatting errors.

3. **Use Simple Formatting**: Stick to basic markdown (bold, italic, headings) for the most reliable results.

4. **Test Cards**: Always test cards in a development space before sending to production spaces.

5. **Check for Unsupported Fields**: If you encounter API errors, check for unsupported fields in your card structure.

## Available Tools

The following tools are available for working with Google Chat cards:

### Basic Card Tools (smart_card_tool.py)
- `send_smart_card`: Create and send a card using natural language content description
- `create_card_from_template`: Create and send a card using a predefined template
- `preview_card_from_description`: Preview a card structure without sending
- `optimize_card_layout`: Analyze and optimize a card layout
- `create_multi_modal_card`: Create and send a card with multi-modal content

### Advanced Card Tools (unified_card_tool.py)
- `send_dynamic_card`: Send any type of card using natural language description
- `list_available_card_components`: List available card components
- `list_card_templates`: List available card templates
- `get_card_template`: Get a specific template by ID or name
- `save_card_template`: Save a card template
- `delete_card_template`: Delete a card template
- `get_card_component_info`: Get detailed information about a card component
- `create_card_framework_wrapper`: Create a ModuleWrapper for a module