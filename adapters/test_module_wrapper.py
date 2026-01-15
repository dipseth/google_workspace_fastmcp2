#!/usr/bin/env python3
"""
Test script for ModuleWrapper

This script demonstrates the ModuleWrapper in action by wrapping
the 'json' module and performing various operations on it.
"""

import logging
import sys
import time

# Import the ModuleWrapper
from module_wrapper import ModuleWrapper

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def test_basic_wrapping():
    """Test basic module wrapping and component listing."""
    logger.info("🧪 Testing basic module wrapping...")

    # Create wrapper for json module
    wrapper = ModuleWrapper("json")

    # List all components
    components = wrapper.list_components()
    logger.info(f"Found {len(components)} components in json module")

    # Count by type
    type_counts = {}
    for path in components:
        info = wrapper.get_component_info(path)
        if info:
            component_type = info["type"]
            type_counts[component_type] = type_counts.get(component_type, 0) + 1

    # Print counts
    for component_type, count in sorted(type_counts.items()):
        logger.info(f"{component_type}: {count}")

    return wrapper


def test_search(wrapper):
    """Test searching for components."""
    logger.info("\n🧪 Testing component search...")

    # Search for json parsing
    query = "parse json string"
    logger.info(f"Searching for: '{query}'")

    results = wrapper.search(query, limit=3)

    # Print results
    logger.info(f"Found {len(results)} results:")
    for i, result in enumerate(results):
        logger.info(
            f"{i+1}. {result['path']} ({result['type']}) - Score: {result['score']:.4f}"
        )
        if result["docstring"]:
            logger.info(f"   {result['docstring'][:100]}...")


def test_component_retrieval(wrapper):
    """Test retrieving and using components."""
    logger.info("\n🧪 Testing component retrieval...")

    # Get json.loads function
    loads_path = "json.loads"
    logger.info(f"Retrieving component: {loads_path}")

    loads_func = wrapper.get_component_by_path(loads_path)

    if loads_func:
        logger.info(f"Successfully retrieved {loads_path}")

        # Use the function
        test_json = '{"name": "Test", "value": 42}'
        logger.info(f"Parsing JSON: {test_json}")

        parsed = loads_func(test_json)
        logger.info(f"Parsed result: {parsed}")
    else:
        logger.error(f"Failed to retrieve {loads_path}")


def test_nested_components(wrapper):
    """Test accessing nested components."""
    logger.info("\n🧪 Testing nested components...")

    # Get JSONEncoder class
    encoder_path = "json.JSONEncoder"
    logger.info(f"Retrieving component: {encoder_path}")

    encoder_class = wrapper.get_component_by_path(encoder_path)

    if encoder_class:
        logger.info(f"Successfully retrieved {encoder_path}")

        # Get encode method
        encode_path = "json.JSONEncoder.encode"
        logger.info(f"Retrieving nested component: {encode_path}")

        encode_method = wrapper.get_component_by_path(encode_path)

        if encode_method:
            logger.info(f"Successfully retrieved {encode_path}")

            # Create encoder instance
            encoder = encoder_class()

            # Use the method
            test_obj = {"name": "Test", "value": 42}
            logger.info(f"Encoding object: {test_obj}")

            # Note: We need to call the method on the instance
            encoded = encoder.encode(test_obj)
            logger.info(f"Encoded result: {encoded}")
        else:
            logger.error(f"Failed to retrieve {encode_path}")
    else:
        logger.error(f"Failed to retrieve {encoder_path}")


def test_performance(module_name="json"):
    """Test performance of wrapping and searching."""
    logger.info(f"\n🧪 Testing performance with module: {module_name}...")

    # Measure wrapping time
    start_time = time.time()
    wrapper = ModuleWrapper(module_name)
    wrap_time = time.time() - start_time

    # Count components
    components = wrapper.list_components()
    component_count = len(components)

    logger.info(f"Wrapped {component_count} components in {wrap_time:.2f} seconds")
    logger.info(
        f"Average time per component: {(wrap_time / component_count) * 1000:.2f} ms"
    )

    # Measure search time
    queries = ["parse json string", "convert object to json", "handle json errors"]

    total_search_time = 0
    for query in queries:
        start_time = time.time()
        results = wrapper.search(query, limit=5)
        search_time = time.time() - start_time
        total_search_time += search_time

        logger.info(
            f"Search for '{query}' took {search_time:.4f} seconds, found {len(results)} results"
        )

    logger.info(
        f"Average search time: {(total_search_time / len(queries)):.4f} seconds"
    )

    return wrapper


def main():
    """Main test function."""
    logger.info("🚀 Starting ModuleWrapper tests...")

    # Get module name from command line or use default
    module_name = sys.argv[1] if len(sys.argv) > 1 else "json"

    try:
        # Test basic wrapping
        wrapper = test_basic_wrapping()

        # Test search
        test_search(wrapper)

        # Test component retrieval
        test_component_retrieval(wrapper)

        # Test nested components
        test_nested_components(wrapper)

        # Test performance
        test_performance(module_name)

        logger.info("\n✅ All tests completed successfully!")

    except Exception as e:
        logger.error(f"❌ Test failed: {e}", exc_info=True)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
