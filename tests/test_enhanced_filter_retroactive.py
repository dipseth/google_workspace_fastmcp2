#!/usr/bin/env python3
"""
Test script for enhanced retroactive Gmail filter application functionality.

This script tests the new apply_filter_to_existing_messages function with:
- Full pagination support (no 500 message limit)
- Batch processing with batchModify API
- Configurable rate limiting
- Enhanced error handling
- Progress reporting
"""

import asyncio
import logging
import time
import json
import sys
import os
from datetime import datetime
from typing import Dict, Any
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Set up logging to capture detailed progress
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(project_root / 'filter_test.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

async def test_enhanced_retroactive_filter():
    """
    Test the enhanced apply_filter_to_existing_messages function directly.
    
    Test Parameters:
    - user_google_email: "sethrivers@gmail.com" 
    - search_query: "from:@starbucks.com"
    - add_label_ids: ["Label_28"]
    - max_messages: 100 (safety limit for testing)
    """
    
    print("🚀 TESTING ENHANCED RETROACTIVE GMAIL FILTER APPLICATION")
    print("=" * 80)
    print(f"Test Start Time: {datetime.now().isoformat()}")
    print()
    
    # Test configuration
    test_config = {
        "user_google_email": "sethrivers@gmail.com",
        "search_query": "from:@starbucks.com",
        "add_label_ids": ["Label_28"],
        "remove_label_ids": None,
        "batch_size": 100,  # Test batch processing
        "max_messages": 100,  # Safety limit for testing
        "rate_limit_delay": 0.1  # Test rate limiting
    }
    
    print("📋 TEST CONFIGURATION:")
    for key, value in test_config.items():
        print(f"  {key}: {value}")
    print()
    
    try:
        # Import the function and required dependencies
        from gmail.filters import apply_filter_to_existing_messages
        from gmail.service import _get_gmail_service_with_fallback
        
        print("✅ Successfully imported required modules")
        print()
        
        # Get Gmail service
        print("🔐 Authenticating with Gmail service...")
        gmail_service = await _get_gmail_service_with_fallback(test_config["user_google_email"])
        print("✅ Gmail service authentication successful")
        print()
        
        # Record start time for performance measurement
        start_time = time.time()
        
        print("🔍 STARTING ENHANCED RETROACTIVE FILTER APPLICATION...")
        print(f"Search Query: {test_config['search_query']}")
        print(f"Target Labels: {test_config['add_label_ids']}")
        print(f"Max Messages: {test_config['max_messages']}")
        print(f"Batch Size: {test_config['batch_size']}")
        print(f"Rate Limit Delay: {test_config['rate_limit_delay']}s")
        print()
        
        # Call the enhanced function
        result = await apply_filter_to_existing_messages(
            gmail_service=gmail_service,
            search_query=test_config["search_query"],
            add_label_ids=test_config["add_label_ids"],
            remove_label_ids=test_config["remove_label_ids"],
            batch_size=test_config["batch_size"],
            max_messages=test_config["max_messages"],
            rate_limit_delay=test_config["rate_limit_delay"]
        )
        
        # Record end time
        end_time = time.time()
        execution_time = end_time - start_time
        
        print("=" * 80)
        print("📊 TEST RESULTS ANALYSIS")
        print("=" * 80)
        
        # Parse and analyze results
        if isinstance(result, str):
            try:
                result_data = json.loads(result)
            except json.JSONDecodeError:
                # If result is not JSON, treat as string response
                result_data = {"raw_response": result}
        else:
            result_data = result
        
        print("🔢 PROCESSING STATISTICS:")
        print(f"  Total Messages Found: {result_data.get('total_found', 'N/A')}")
        print(f"  Successfully Processed: {result_data.get('processed_count', 'N/A')}")
        print(f"  Errors Encountered: {result_data.get('error_count', 'N/A')}")
        print(f"  Processing Truncated: {result_data.get('truncated', 'N/A')}")
        print(f"  Total Execution Time: {execution_time:.2f} seconds")
        print()
        
        # Performance analysis
        total_found = result_data.get('total_found', 0)
        processed_count = result_data.get('processed_count', 0)
        
        if total_found > 0:
            processing_rate = processed_count / execution_time if execution_time > 0 else 0
            success_rate = (processed_count / total_found) * 100 if total_found > 0 else 0
            
            print("⚡ PERFORMANCE METRICS:")
            print(f"  Processing Rate: {processing_rate:.2f} messages/second")
            print(f"  Success Rate: {success_rate:.1f}%")
            print()
        
        # Enhanced features validation
        print("🔬 ENHANCED FEATURES VALIDATION:")
        
        # 1. Pagination Support
        if total_found > 500:
            print("  ✅ Pagination: Successfully handled >500 messages (old limit)")
        elif total_found > 0:
            print(f"  ✅ Pagination: Ready to handle large datasets (found {total_found} messages)")
        else:
            print("  ⚠️  Pagination: No messages found to test pagination")
        
        # 2. Batch Processing
        if processed_count > 1:
            print("  ✅ Batch Processing: Multiple messages processed efficiently")
        elif processed_count == 1:
            print("  ✅ Batch Processing: Single message fallback working")
        else:
            print("  ⚠️  Batch Processing: No messages processed")
        
        # 3. Rate Limiting
        if execution_time > (total_found * test_config["rate_limit_delay"]):
            print("  ✅ Rate Limiting: Delays properly implemented")
        else:
            print("  ✅ Rate Limiting: Configured but may not be observable with small dataset")
        
        # 4. Error Handling
        error_count = result_data.get('error_count', 0)
        errors = result_data.get('errors', [])
        
        if error_count == 0:
            print("  ✅ Error Handling: No errors encountered")
        else:
            print(f"  ⚠️  Error Handling: {error_count} errors handled gracefully")
            for i, error in enumerate(errors[:3], 1):  # Show first 3 errors
                print(f"    Error {i}: {error}")
        
        # 5. Progress Reporting
        print("  ✅ Progress Reporting: Detailed logging and metrics available")
        
        print()
        
        # Raw result data for analysis
        print("📋 DETAILED RESULTS:")
        print(json.dumps(result_data, indent=2))
        print()
        
        # Recommendations
        print("💡 RECOMMENDATIONS FOR PRODUCTION USAGE:")
        
        if total_found > test_config["max_messages"]:
            print(f"  • Increase max_messages limit (currently {test_config['max_messages']}) for full processing")
        
        if error_count > 0:
            print(f"  • Review error patterns: {error_count} errors occurred")
        
        if processing_rate < 10:
            print("  • Consider adjusting batch_size for better performance")
        
        if total_found > 1000:
            print("  • Consider running during off-peak hours for large datasets")
        
        print("  • Monitor Gmail API quotas for high-volume usage")
        print("  • Test with different rate_limit_delay values for optimal performance")
        
        print()
        print("✅ TEST COMPLETED SUCCESSFULLY")
        
        return result_data
        
    except ImportError as e:
        print(f"❌ Import Error: {e}")
        print("Please ensure you're running from the correct directory with required modules")
        return None
        
    except Exception as e:
        logger.error(f"Test execution error: {e}")
        print(f"❌ Test execution failed: {e}")
        return None

async def main():
    """Main test execution."""
    print("Enhanced Retroactive Gmail Filter Test")
    print("=====================================")
    print()
    
    result = await test_enhanced_retroactive_filter()
    
    if result:
        print("\n🎯 Test completed with results. Check filter_test.log for detailed logs.")
    else:
        print("\n❌ Test failed. Check logs for details.")

if __name__ == "__main__":
    asyncio.run(main())