"""
Test examples for search_drive_files function to validate query handling.
This demonstrates how different query types are processed.
"""

from drive.drive_tools import DRIVE_QUERY_PATTERNS

def test_query_detection(query: str) -> tuple[bool, str]:
    """
    Test if a query is detected as structured or free-text.
    Returns (is_structured, processed_query)
    """
    # Check if query matches any structured patterns
    is_structured = any(pattern.search(query) for pattern in DRIVE_QUERY_PATTERNS)
    
    if is_structured:
        final_query = query
    else:
        # Free text - wrap in fullText contains
        escaped_query = query.replace("'", "\\'")
        final_query = f"fullText contains '{escaped_query}'"
    
    return is_structured, final_query

# Test cases for different query types
test_cases = [
    # Free-text searches (will be wrapped in fullText contains)
    {
        "query": "quarterly report",
        "description": "Simple text search",
        "expected_structured": False,
        "expected_output": "fullText contains 'quarterly report'"
    },
    {
        "query": "budget 2024",
        "description": "Text with numbers",
        "expected_structured": False,
        "expected_output": "fullText contains 'budget 2024'"
    },
    {
        "query": "John's presentation",
        "description": "Text with apostrophe (will be escaped)",
        "expected_structured": False,
        "expected_output": "fullText contains 'John\\'s presentation'"
    },
    
    # Structured queries (will pass through unchanged)
    {
        "query": "name contains 'report'",
        "description": "Name contains operator",
        "expected_structured": True,
        "expected_output": "name contains 'report'"
    },
    {
        "query": "mimeType = 'application/pdf'",
        "description": "Search for PDFs only",
        "expected_structured": True,
        "expected_output": "mimeType = 'application/pdf'"
    },
    {
        "query": "mimeType = 'application/vnd.google-apps.document'",
        "description": "Search for Google Docs only",
        "expected_structured": True,
        "expected_output": "mimeType = 'application/vnd.google-apps.document'"
    },
    {
        "query": "mimeType = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'",
        "description": "Search for Word documents",
        "expected_structured": True,
        "expected_output": "mimeType = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'"
    },
    {
        "query": "'1ABC2DEF3GHI' in parents",
        "description": "Search in specific folder",
        "expected_structured": True,
        "expected_output": "'1ABC2DEF3GHI' in parents"
    },
    {
        "query": "modifiedTime > '2024-01-01'",
        "description": "Modified date filter",
        "expected_structured": True,
        "expected_output": "modifiedTime > '2024-01-01'"
    },
    {
        "query": "name = 'Budget Report.xlsx'",
        "description": "Exact name match",
        "expected_structured": True,
        "expected_output": "name = 'Budget Report.xlsx'"
    },
    {
        "query": "fullText contains 'machine learning'",
        "description": "Explicit fullText search",
        "expected_structured": True,
        "expected_output": "fullText contains 'machine learning'"
    },
    {
        "query": "trashed = false",
        "description": "Non-trashed files",
        "expected_structured": True,
        "expected_output": "trashed = false"
    },
    {
        "query": "starred = true",
        "description": "Starred files",
        "expected_structured": True,
        "expected_output": "starred = true"
    },
    
    # Complex structured queries
    {
        "query": "name contains 'report' and mimeType = 'application/pdf' and modifiedTime > '2024-01-01'",
        "description": "Complex multi-condition query",
        "expected_structured": True,
        "expected_output": "name contains 'report' and mimeType = 'application/pdf' and modifiedTime > '2024-01-01'"
    },
    {
        "query": "(name contains 'budget' or name contains 'finance') and mimeType != 'application/vnd.google-apps.folder'",
        "description": "Complex query with OR and NOT conditions",
        "expected_structured": True,
        "expected_output": "(name contains 'budget' or name contains 'finance') and mimeType != 'application/vnd.google-apps.folder'"
    }
]

def run_tests():
    """Run all test cases and print results."""
    print("=" * 80)
    print("SEARCH_DRIVE_FILES QUERY VALIDATION TESTS")
    print("=" * 80)
    print()
    
    passed = 0
    failed = 0
    
    for i, test in enumerate(test_cases, 1):
        query = test["query"]
        description = test["description"]
        expected_structured = test["expected_structured"]
        expected_output = test["expected_output"]
        
        is_structured, final_query = test_query_detection(query)
        
        # Check if detection matches expectation
        detection_pass = is_structured == expected_structured
        output_pass = final_query == expected_output
        test_pass = detection_pass and output_pass
        
        if test_pass:
            passed += 1
            status = "✅ PASS"
        else:
            failed += 1
            status = "❌ FAIL"
        
        print(f"Test {i}: {description}")
        print(f"  Input Query: {query}")
        print(f"  Expected Structured: {expected_structured}, Got: {is_structured} {'✅' if detection_pass else '❌'}")
        print(f"  Expected Output: {expected_output}")
        print(f"  Actual Output:   {final_query}")
        print(f"  Status: {status}")
        print()
    
    print("=" * 80)
    print(f"RESULTS: {passed} passed, {failed} failed out of {len(test_cases)} tests")
    print("=" * 80)
    
    # Document all supported file types
    print("\n" + "=" * 80)
    print("SUPPORTED DOCUMENT TYPES")
    print("=" * 80)
    print("""
The search_drive_files function supports ALL document types stored in Google Drive:

✅ Google Workspace Files:
   - Google Docs: mimeType = 'application/vnd.google-apps.document'
   - Google Sheets: mimeType = 'application/vnd.google-apps.spreadsheet'
   - Google Slides: mimeType = 'application/vnd.google-apps.presentation'
   - Google Forms: mimeType = 'application/vnd.google-apps.form'
   - Google Drawings: mimeType = 'application/vnd.google-apps.drawing'

✅ Microsoft Office Files:
   - Word: mimeType = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
   - Excel: mimeType = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
   - PowerPoint: mimeType = 'application/vnd.openxmlformats-officedocument.presentationml.presentation'

✅ Common File Types:
   - PDF: mimeType = 'application/pdf'
   - Text: mimeType = 'text/plain'
   - CSV: mimeType = 'text/csv'
   - JSON: mimeType = 'application/json'
   - XML: mimeType = 'text/xml'
   - HTML: mimeType = 'text/html'

✅ Media Files:
   - Images: mimeType = 'image/jpeg', 'image/png', 'image/gif', etc.
   - Videos: mimeType = 'video/mp4', 'video/mpeg', etc.
   - Audio: mimeType = 'audio/mpeg', 'audio/wav', etc.

✅ Archives:
   - ZIP: mimeType = 'application/zip'
   - RAR: mimeType = 'application/x-rar-compressed'

✅ Folders:
   - Folder: mimeType = 'application/vnd.google-apps.folder'

NOTE: The function does NOT restrict file types. You can search for ANY file type
      by either using free-text search or by specifying the mimeType in your query.
""")

if __name__ == "__main__":
    run_tests()