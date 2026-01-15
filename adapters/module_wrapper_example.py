"""
Example usage of ModuleWrapper with Qdrant integration.

This script demonstrates how to wrap a module, index its components,
and search for them using natural language queries.
"""

import importlib
import logging
import sys

# Import the ModuleWrapper
from module_wrapper import ModuleWrapper
from typing_extensions import Any, Dict

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
from config.enhanced_logging import setup_logger

logger = setup_logger()


def print_component_details(component: Dict[str, Any]):
    """Print details of a component in a readable format."""
    print(f"📦 {component['name']} ({component['type']})")
    print(f"   Path: {component['path']}")
    print(f"   Score: {component['score']:.4f}")

    if component["docstring"]:
        # Truncate long docstrings
        docstring = component["docstring"]
        if len(docstring) > 200:
            docstring = docstring[:200] + "..."
        print(f"   Docstring: {docstring}")

    print()


def main():
    """Main function to demonstrate ModuleWrapper usage."""
    # Check if module name is provided
    if len(sys.argv) < 2:
        print("Usage: python module_wrapper_example.py <module_name> [query]")
        print("Example: python module_wrapper_example.py json 'parse json string'")
        return

    # Get module name from arguments
    module_name = sys.argv[1]
    logger.info(f"🔍 Wrapping module: {module_name}")

    try:
        # Import the module to ensure it exists
        module = importlib.import_module(module_name)

        # Create the ModuleWrapper
        wrapper = ModuleWrapper(
            module_or_name=module,
            qdrant_host="localhost",
            qdrant_port=6333,
            collection_name=f"{module_name}_components",
            index_nested=True,
            index_private=False,
        )

        # If query is provided, search for it
        if len(sys.argv) > 2:
            query = sys.argv[2]
            logger.info(f"🔎 Searching for: {query}")

            # Perform the search
            results = wrapper.search(query, limit=5)

            # Display results
            print(f"\n🔍 Found {len(results)} results for '{query}':\n")
            for i, result in enumerate(results):
                print(f"Result #{i+1}:")
                print_component_details(result)

                # If the component is callable, show how to use it
                if result["type"] in ("function", "method", "class"):
                    print(f"   Usage: {result['path']}")

                    # Get the actual component
                    component = result["component"]
                    if component:
                        try:
                            signature = str(inspect.signature(component))
                            print(f"   Signature: {signature}")
                        except (ValueError, TypeError):
                            pass

                    print()
        else:
            # List component types and counts
            components = wrapper.list_components()

            # Count by type
            type_counts = {}
            for path in components:
                info = wrapper.get_component_info(path)
                if info:
                    component_type = info["type"]
                    type_counts[component_type] = type_counts.get(component_type, 0) + 1

            # Display summary
            print(f"\n📊 Module {module_name} contains {len(components)} components:\n")
            for component_type, count in sorted(type_counts.items()):
                print(f"   {component_type}: {count}")

            # List some examples of each type
            print("\n📋 Examples of each type:")
            for component_type in type_counts.keys():
                examples = wrapper.list_components(component_type)[
                    :3
                ]  # Get up to 3 examples
                print(f"\n   {component_type.capitalize()} examples:")
                for path in examples:
                    print(f"      - {path}")

            print("\nTry searching with a query:")
            print(f"python module_wrapper_example.py {module_name} 'your search query'")

    except ImportError:
        logger.error(f"❌ Could not import module: {module_name}")
        print(f"Module '{module_name}' not found. Make sure it's installed.")
    except Exception as e:
        logger.error(f"❌ Error: {e}", exc_info=True)
        print(f"An error occurred: {e}")


if __name__ == "__main__":
    import inspect  # Import here to avoid circular import with the example

    main()
