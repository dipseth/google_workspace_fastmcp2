# Test Cleanup Audit Report

**Generated:** 2026-01-18  
**Purpose:** Identify tests that create Google Workspace resources without cleanup

---

## Summary

This audit identified **42+ test functions** across **10 test files** that create resources in Google Workspace without corresponding cleanup logic. These orphaned resources can accumulate over time, cluttering test accounts.

---

## 🔴 HIGH PRIORITY - Creates Real Resources

### 1. Calendar Tests (`test_calendar_tools.py`)

| Test Name | Line | Resource Created | Cleanup Status |
|-----------|------|------------------|----------------|
| `test_create_event` | 305-360 | Calendar event "Test Event from MCP" | ❌ No cleanup |
| `test_create_all_day_event` | 363-406 | All-day event "All Day Test Event" | ❌ No cleanup |
| `test_create_event_with_attendees` | 409-451 | Event "Meeting with Team" | ❌ No cleanup |
| `test_create_event_with_attachments` | 454-499 | Event "Event with Attachments" | ❌ No cleanup |
| `test_create_bulk_events` | 502-658 | 2 events "🎈 First/🎉 Second Bulk Test Event" | ❌ No cleanup |
| `test_create_bulk_events_comprehensive` | 661-732 | 3 events "🎯 Bulk Event 1/2/3" | ❌ No cleanup |
| `test_create_bulk_events_json_string_birthday_reminders` | 775-874 | Birthday reminder events | ❌ No cleanup |
| `test_create_bulk_events_backward_compatibility` | 877-921 | "Legacy Mode Test Event" | ❌ No cleanup |
| `test_create_bulk_events_parameter_conflict_validation` | 924-982 | Event during conflict testing | ❌ No cleanup |

**Notes:**
- Class has `_created_event_id` variable but no teardown/cleanup
- Each test run can create 10+ calendar events
- Events have future dates so they persist in calendars

**Recommended Fix:**
```python
@pytest.fixture(autouse=True)
async def cleanup_events(self, client):
    created_ids = []
    yield created_ids
    for event_id in created_ids:
        await client.call_tool("delete_event", {
            "user_google_email": TEST_EMAIL,
            "event_id": event_id
        })
```

---

### 2. Photos Tests (`test_photos_tools_improved.py`)

| Test Name | Line | Resource Created | Cleanup Status |
|-----------|------|------------------|----------------|
| `test_create_photos_album` | 369-442 | Album "Test Album {timestamp}" | ❌ No cleanup |
| `test_upload_photos_with_album_creation` | 860-954 | Album + uploaded photos | ❌ No cleanup |

**Notes:**
- Albums persist indefinitely
- Uploaded photos consume storage quota
- Class variables `created_album_id`, `created_album_name` track but don't clean

---

### 3. Gmail Filter Tests (`test_enhanced_gmail_filters.py`)

| Test Name | Line | Resource Created | Cleanup Status |
|-----------|------|------------------|----------------|
| `_test_create_gmail_filter_no_auth` | 81-105 | Filter with `from:@starbucks-test-{timestamp}.com` | ❌ No cleanup |
| `test_enhanced_retroactive_filter_creation` | 150-198 | Filter with `from:@starbucks-retro-{timestamp}.com` | ❌ No cleanup |
| `test_enhanced_filter_features_parameters` | 244-282 | Complex filter with `from:@starbucks-complex-{timestamp}.com` | ❌ No cleanup |
| `test_filter_creation_response_structure` | 345-404 | Filter with `from:@example-perf-{timestamp}.com` | ❌ No cleanup |
| `test_starbucks_filter_creation_comprehensive` | 433-545 | Filter with `from:@starbucks-scenario-{timestamp}.com` | ❌ No cleanup |

**Notes:**
- Uses timestamps for uniqueness but filters accumulate
- Filters can affect incoming email processing

---

### 4. Slides Tests (`test_slides_tools.py`)

| Test Name | Line | Resource Created | Cleanup Status |
|-----------|------|------------------|----------------|
| `test_create_presentation` | 188-200+ | "Test Presentation from MCP" | ❌ No cleanup |
| `shared_test_presentation` fixture | 46-160 | "Shared Test Presentation for MCP Tests" | ❌ No cleanup |

**Notes:**
- Has env var fallback `GOOGLE_SLIDE_PRESENTATION_ID` - GOOD
- Creates new presentations when env var not set

---

### 5. Chat Tests (`test_chat_tools.py`)

| Test Name | Line | Resource Created | Cleanup Status |
|-----------|------|------------------|----------------|
| `real_thread_id` fixture | 43-106 | Thread starter message | ❌ No cleanup |
| `test_send_message` | 226-258 | "Test message from MCP Chat Tools" | ❌ No cleanup |
| `test_send_card_message` | 292-326 | Card "Test Card" | ❌ No cleanup |
| `test_send_simple_card` | 329-365 | "Simple Test Card" | ❌ No cleanup |
| `test_send_interactive_card` | 368-416 | "Interactive Test Card" | ❌ No cleanup |
| `test_send_form_card` | 419-476 | "Feedback Form" card | ❌ No cleanup |
| `test_send_rich_card` | 479-538 | "Rich Test Card" | ❌ No cleanup |
| `test_send_dynamic_card` | 541-576 | Dynamic card | ❌ No cleanup |
| `test_send_message_with_threading` | 579-612 | Threaded message | ❌ No cleanup |
| Integration tests | 616-769 | Multiple real messages/cards | ❌ No cleanup |

**Notes:**
- Chat messages cannot be deleted via MCP currently
- These pollute Chat spaces over time
- Consider using dedicated test spaces

---

### 6. Gmail Label Tests (`test_mcp_client.py`)

| Test Name | Line | Resource Created | Cleanup Status |
|-----------|------|------------------|----------------|
| `_test_create_label_with_colors_no_auth` | 921-965 | Label "Test Label {uuid}" | ❌ No cleanup |

---

### 7. Docs Tests (`test_mcp_client.py`)

| Test Name | Line | Resource Created | Cleanup Status |
|-----------|------|------------------|----------------|
| `_test_create_doc_no_auth` | 534-558 | Google Doc "Test Document" | ❌ No cleanup |

---

### 8. Forms Tests (`test_mcp_client.py`)

| Test Name | Line | Resource Created | Cleanup Status |
|-----------|------|------------------|----------------|
| `_test_create_form_no_auth` | 649-666 | "Test Form" | ❌ No cleanup |

---

## 🟡 MEDIUM PRIORITY - Modifies Existing Resources

### 9. Sheets Tests (`test_sheets_tools.py`)

| Test Name | Line | Resource Modified | Cleanup Status |
|-----------|------|-------------------|----------------|
| `test_create_sheet` | 314-344 | Creates "Test Sheet" tab | ❌ No cleanup |
| `test_modify_sheet_values` | 239-277 | Writes to A1:C3 | ❌ No cleanup |
| Various format tests | 444-866 | Modifies cell formatting | ❌ No cleanup |

**Notes:**
- ✅ Uses `TEST_GOOGLE_SHEET_ID` env var - GOOD pattern
- Modifications accumulate but don't create new files

### 10. Sheets Real Edits (`test_sheets_real_edits.py`)

| Test Name | Line | Resource Modified | Cleanup Status |
|-----------|------|-------------------|----------------|
| `test_modify_then_read_roundtrip` | 41-101 | Writes to X900:Y901 | ❌ No cleanup |

**Notes:**
- ✅ Requires `ENABLE_SHEETS_WRITE_TESTS=1` - GOOD gate
- Writes persist but in isolated area

---

## 🟢 GOOD PATTERNS - Already Well-Designed

### Sheets Tests Pattern
```python
@pytest.fixture(scope="session")
def test_spreadsheet_id() -> str | None:
    """Use a stable, pre-created spreadsheet ID from the environment."""
    return os.getenv("TEST_GOOGLE_SHEET_ID")

# Tests skip when ID not available
if not test_spreadsheet_id:
    pytest.skip("No test spreadsheet ID available")
```

### Slides Tests Pattern (partial)
```python
if GOOGLE_SLIDE_PRESENTATION_ID:
    return GOOGLE_SLIDE_PRESENTATION_ID  # Use existing
# Falls back to creation...
```

---

## Recommended Cleanup Strategies

### Strategy 1: Session-Scoped Cleanup Fixture

```python
@pytest.fixture(scope="session")
async def resource_tracker():
    """Track all created resources for cleanup."""
    resources = {
        "calendar_events": [],
        "gmail_filters": [],
        "gmail_labels": [],
        "photos_albums": [],
        "docs": [],
        "forms": [],
        "presentations": [],
    }
    yield resources
    
    # Cleanup all tracked resources
    client = await create_test_client(TEST_EMAIL)
    async with client:
        for event_id in resources["calendar_events"]:
            await client.call_tool("delete_event", {...})
        # ... etc
```

### Strategy 2: Per-Test Cleanup with autouse

```python
@pytest.fixture(autouse=True)
async def cleanup_after_test(self, client, request):
    """Automatic cleanup after each test."""
    yield
    # Cleanup logic based on test markers
```

### Strategy 3: Environment-Based Stable Resources

```python
# Add to base_test_config.py
TEST_CALENDAR_ID = os.getenv("TEST_CALENDAR_ID")  # Dedicated test calendar
TEST_CHAT_SPACE_ID = os.getenv("TEST_CHAT_SPACE_ID")  # Dedicated test space
TEST_PHOTOS_ALBUM_ID = os.getenv("TEST_PHOTOS_ALBUM_ID")  # Dedicated test album
```

### Strategy 4: Standalone Cleanup Script

Create `scripts/cleanup_test_resources.py`:
```python
"""Clean up orphaned test resources from Google Workspace."""

async def cleanup_calendar_events():
    """Delete all events with 'Test' or 'MCP' in summary."""
    
async def cleanup_gmail_filters():
    """Delete filters with test patterns like @starbucks-test-*"""
    
async def cleanup_photos_albums():
    """Delete albums matching 'Test Album *'"""
```

---

## ✅ IMPLEMENTED - Cleanup Infrastructure

### Session-Scoped Cleanup (conftest.py)

A `ResourceCleanupTracker` class and session-scoped cleanup fixture have been added to `conftest.py`. This provides:

1. **Automatic cleanup at session end** - Resources tracked during tests are cleaned up automatically
2. **Manual tracking methods** - Tests can register resources for cleanup:
   ```python
   async def test_create_event(client, cleanup_tracker):
       result = await client.call_tool("create_event", {...})
       event_id = extract_event_id(result)
       cleanup_tracker.track_calendar_event(event_id)  # Will be deleted after session
   ```

3. **Supported resource types** (auto-cleaned):
   - `track_calendar_event(event_id)` - Calendar events
   - `track_gmail_filter(filter_id)` - Gmail filters
   - `track_drive_file(file_id)` - Drive files

4. **Tracked-only resource types** (manual cleanup required):
   - `track_photos_album(album_id)`
   - `track_doc(doc_id)`
   - `track_form(form_id)`
   - `track_presentation(presentation_id)`
   - `track_gmail_label(label_id)`

5. **Environment variables**:
   - `SKIP_TEST_CLEANUP=1` - Disable automatic cleanup (for debugging)

### Standalone Cleanup Script (scripts/cleanup_test_resources.py)

A script for manual/scheduled cleanup of orphaned test resources:

```bash
# Preview what would be deleted (dry run - default)
python scripts/cleanup_test_resources.py

# Actually delete resources
python scripts/cleanup_test_resources.py --execute

# Clean specific resource types
python scripts/cleanup_test_resources.py --execute --calendar --gmail-filters

# Use custom email
python scripts/cleanup_test_resources.py --email user@example.com
```

The script detects test resources by pattern matching:
- Calendar events: "Test Event", "MCP Test", emoji-prefixed events
- Gmail filters: @starbucks-test-*, timestamp-based patterns
- Drive files: "Test Document", "Test Presentation", etc.

---

## Next Steps

1. ~~**Immediate:** Add cleanup fixtures to calendar tests (highest volume)~~ ✅ DONE
2. ~~**Short-term:** Implement resource_tracker pattern for session cleanup~~ ✅ DONE
3. **Medium-term:** Update existing tests to use `cleanup_tracker` fixture
4. **Long-term:** Schedule cleanup script for periodic maintenance

---

## Related Files

- `tests/client/conftest.py` - ✅ Global cleanup fixtures added
- `tests/client/base_test_config.py` - Configuration for cleanup
- `tests/client/test_helpers.py` - Test utilities
- `scripts/cleanup_test_resources.py` - ✅ Standalone cleanup script
