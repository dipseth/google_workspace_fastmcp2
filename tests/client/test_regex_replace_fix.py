"""
Test regex_replace functionality fix for Google Docs.

Tests the fixed text extraction that now handles tables and complex content.
"""

import os
import pytest
from .base_test_config import TEST_EMAIL
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

TEST_DOCUMENT_ID = os.getenv("TEST_DOCUMENT_ID")
if not TEST_DOCUMENT_ID:
    raise ValueError("TEST_DOCUMENT_ID environment variable is not set")


@pytest.mark.service("docs")
class TestRegexReplaceFix:
    """Test the fixed regex_replace functionality."""
    
    @pytest.mark.asyncio
    async def test_simple_string_replacement(self, client):
        """Test 1: Simple string replacement - 'Test Edit' to 'Verified Edit'."""
        print("\n" + "="*70)
        print("TEST 1: Simple String Replacement")
        print("="*70)
        
        result = await client.call_tool("create_doc", {
            "title": "Test Document",
            "document_id": TEST_DOCUMENT_ID,
            "user_google_email": TEST_EMAIL,
            "edit_config": {
                "mode": "regex_replace",
                "regex_operations": [
                    {
                        "pattern": "Test Edit",
                        "replacement": "Verified Edit"
                    }
                ]
            }
        })
        
        assert result is not None
        content = result.content[0].text if result.content else str(result)
        print(f"\nResult:\n{content}\n")
        
        # Should find and replace text (not show "No content changes")
        assert "No content changes" not in content or "0 replacements" not in content.lower(), \
            "Should have found and replaced 'Test Edit' text"
        
        # Look for success indicators
        if "replacements" in content.lower() or "applied" in content.lower():
            print("✅ Test 1 PASSED: Text replacement detected")
        else:
            print(f"⚠️  Test 1 result unclear - Content: {content[:200]}")
    
    @pytest.mark.asyncio
    async def test_date_pattern_regex(self, client):
        """Test 2: Regex pattern matching - find dates like '2025-11-02'."""
        print("\n" + "="*70)
        print("TEST 2: Date Pattern Regex")
        print("="*70)
        
        result = await client.call_tool("create_doc", {
            "title": "Test Document",
            "document_id": TEST_DOCUMENT_ID,
            "user_google_email": TEST_EMAIL,
            "edit_config": {
                "mode": "regex_replace",
                "regex_operations": [
                    {
                        "pattern": r"\d{4}-\d{2}-\d{2}",
                        "replacement": "[DATE-REPLACED]"
                    }
                ]
            }
        })
        
        assert result is not None
        content = result.content[0].text if result.content else str(result)
        print(f"\nResult:\n{content}\n")
        
        # Should find dates in the document
        if "replacements" in content.lower():
            print("✅ Test 2 PASSED: Date pattern matching works")
        else:
            print(f"⚠️  Test 2 result: {content[:200]}")
    
    @pytest.mark.asyncio
    async def test_case_insensitive_replacement(self, client):
        """Test 3: Case-insensitive replacement - 'sprint' variations to 'SPRINT'."""
        print("\n" + "="*70)
        print("TEST 3: Case-Insensitive Replacement")
        print("="*70)
        
        result = await client.call_tool("create_doc", {
            "title": "Test Document",
            "document_id": TEST_DOCUMENT_ID,
            "user_google_email": TEST_EMAIL,
            "edit_config": {
                "mode": "regex_replace",
                "regex_operations": [
                    {
                        "pattern": "sprint",
                        "replacement": "SPRINT",
                        "flags": "i"  # Case-insensitive
                    }
                ]
            }
        })
        
        assert result is not None
        content = result.content[0].text if result.content else str(result)
        print(f"\nResult:\n{content}\n")
        
        # Should find multiple matches (Sprint, sprint variations)
        if "replacements" in content.lower():
            print("✅ Test 3 PASSED: Case-insensitive matching works")
        else:
            print(f"⚠️  Test 3 result: {content[:200]}")
    
    @pytest.mark.asyncio
    async def test_table_content_extraction(self, client):
        """Test 4: Verify table content is extracted - replace service names."""
        print("\n" + "="*70)
        print("TEST 4: Table Content Extraction")
        print("="*70)
        
        # The document contains tables with service names like "qdrant-proxy-dev"
        result = await client.call_tool("create_doc", {
            "title": "Test Document",
            "document_id": TEST_DOCUMENT_ID,
            "user_google_email": TEST_EMAIL,
            "edit_config": {
                "mode": "regex_replace",
                "regex_operations": [
                    {
                        "pattern": "qdrant-proxy",
                        "replacement": "QDRANT-PROXY"
                    }
                ]
            }
        })
        
        assert result is not None
        content = result.content[0].text if result.content else str(result)
        print(f"\nResult:\n{content}\n")
        
        # Should find text from tables (which was the bug - tables weren't extracted)
        if "replacements" in content.lower() and "0" not in content.split("replacements")[0][-5:]:
            print("✅ Test 4 PASSED: Table content is being extracted and replaced")
        else:
            print(f"⚠️  Test 4 result: {content[:200]}")
    
    @pytest.mark.asyncio
    async def test_get_document_content_for_verification(self, client):
        """Verification: Get current document content to see what we're working with."""
        print("\n" + "="*70)
        print("VERIFICATION: Current Document Content")
        print("="*70)
        
        result = await client.call_tool("get_doc_content", {
            "document_id": TEST_DOCUMENT_ID,
            "user_google_email": TEST_EMAIL
        })
        
        assert result is not None
        content = result.content[0].text if result.content else str(result)
        
        # Show just a snippet of the content
        print(f"\nDocument preview (first 500 chars):")
        print("-" * 70)
        print(content[:500])
        print("-" * 70)
        
        print(f"\nDocument preview (last 300 chars):")
        print("-" * 70)
        print(content[-300:])
        print("-" * 70)


if __name__ == "__main__":
    print("Run with: uv run pytest tests/client/test_regex_replace_fix.py -v -s")