#!/usr/bin/env python3
"""
POC: Form Component Loading via Vector DB

Tests that form components (TextInput, SelectionInput, DateTimePicker) can be:
1. Found via Qdrant vector search
2. Loaded via ModuleWrapper.get_component_by_path()
3. Instantiated with form field data
4. Rendered to valid Google Chat JSON

This ensures form cards use the SAME flow as all other components:
Vector DB → ModuleWrapper → Instantiate → Render
"""

import json
import os
import sys

from dotenv import load_dotenv

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()


def get_qdrant_client():
    """Get Qdrant client using .env credentials."""
    from qdrant_client import QdrantClient

    url = os.getenv("QDRANT_URL")
    key = os.getenv("QDRANT_KEY")

    if not url or not key:
        raise ValueError("QDRANT_URL and QDRANT_KEY must be set in .env")

    return QdrantClient(url=url, api_key=key, prefer_grpc=True)


def get_embedder(use_colbert: bool = True):
    """Get ColBERT embedder for multi-vector search."""
    if use_colbert:
        from fastembed import LateInteractionTextEmbedding

        return LateInteractionTextEmbedding(model_name="colbert-ir/colbertv2.0")
    else:
        from fastembed import TextEmbedding

        return TextEmbedding(model_name="sentence-transformers/all-MiniLM-L6-v2")


def search_components(
    client, embedder, query: str, limit: int = 10, use_colbert: bool = True
):
    """Search for components in vector DB."""
    collection_name = (
        "card_framework_components_colbert"
        if use_colbert
        else "card_framework_components_fastembed"
    )

    if use_colbert:
        query_vectors_raw = list(embedder.query_embed(query))[0]
        query_vectors = [vec.tolist() for vec in query_vectors_raw]

        results = client.query_points(
            collection_name=collection_name,
            query=query_vectors,
            using="colbert",
            limit=limit,
            with_payload=True,
        )
    else:
        embedding = list(embedder.embed([query]))[0].tolist()
        results = client.query_points(
            collection_name=collection_name,
            query=embedding,
            limit=limit,
            with_payload=True,
        )

    return results.points


def get_module_wrapper():
    """Get ModuleWrapper for card_framework."""
    from adapters.module_wrapper import ModuleWrapper

    wrapper = ModuleWrapper(
        module_or_name="card_framework",
        qdrant_url=os.getenv("QDRANT_URL"),
        qdrant_api_key=os.getenv("QDRANT_KEY"),
        collection_name="card_framework_components_fastembed",
        auto_initialize=False,
    )

    return wrapper


def test_search_text_input():
    """
    Test: Search for TextInput component via Qdrant, load, instantiate, render.
    """
    print("\n" + "=" * 60)
    print("TEST: TextInput Component via Qdrant")
    print("=" * 60)

    client = get_qdrant_client()
    embedder = get_embedder(use_colbert=True)
    wrapper = get_module_wrapper()

    # Search for TextInput
    print("\n1. Searching Qdrant for TextInput...")
    results = search_components(
        client,
        embedder,
        "v2.widgets.text_input.TextInput class name label hint_text",
        limit=10,
    )

    print(f"   Found {len(results)} results:")
    for r in results[:5]:
        p = r.payload
        print(
            f"   [{r.score:.2f}] {p.get('name')} ({p.get('type')}) @ {p.get('full_path')}"
        )

    # Find TextInput class
    text_input_path = None
    for r in results:
        path = r.payload.get("full_path", "")
        name = r.payload.get("name", "")
        rtype = r.payload.get("type", "")
        if name == "TextInput" and rtype == "class" and "v2.widgets" in path:
            text_input_path = path
            break

    if not text_input_path:
        print("   ERROR: TextInput class not found in Qdrant")
        return False

    print(f"\n2. Found TextInput at: {text_input_path}")

    # Load via ModuleWrapper
    print("\n3. Loading via ModuleWrapper.get_component_by_path()...")
    TextInput = wrapper.get_component_by_path(text_input_path)
    print(f"   Loaded: {TextInput}")

    if not TextInput:
        print("   ERROR: Could not load TextInput class")
        return False

    # Check available attributes
    print("\n4. Inspecting TextInput class...")
    if hasattr(TextInput, "Type"):
        print(f"   TextInput.Type enum: {list(TextInput.Type.__members__.keys())}")

    # Instantiate
    print("\n5. Instantiating TextInput with form data...")
    try:
        text_input = TextInput(
            name="user_name",
            label="Your Name",
            hint_text="Enter your full name",
            type=TextInput.Type.SINGLE_LINE if hasattr(TextInput, "Type") else None,
        )
        print(f"   Created: {text_input}")

        # Render
        print("\n6. Rendering to Google Chat JSON...")
        rendered = text_input.render()
        print(json.dumps(rendered, indent=2))

        return True

    except Exception as e:
        print(f"   ERROR during instantiation: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_search_selection_input():
    """
    Test: Search for SelectionInput component via Qdrant, load, instantiate, render.
    """
    print("\n" + "=" * 60)
    print("TEST: SelectionInput Component via Qdrant")
    print("=" * 60)

    client = get_qdrant_client()
    embedder = get_embedder(use_colbert=True)
    wrapper = get_module_wrapper()

    # Search for SelectionInput
    print("\n1. Searching Qdrant for SelectionInput...")
    results = search_components(
        client,
        embedder,
        "v2.widgets.selection_input.SelectionInput class name label items type DROPDOWN",
        limit=10,
    )

    print(f"   Found {len(results)} results:")
    for r in results[:5]:
        p = r.payload
        print(
            f"   [{r.score:.2f}] {p.get('name')} ({p.get('type')}) @ {p.get('full_path')}"
        )

    # Find SelectionInput class
    selection_input_path = None
    for r in results:
        path = r.payload.get("full_path", "")
        name = r.payload.get("name", "")
        rtype = r.payload.get("type", "")
        if name == "SelectionInput" and rtype == "class" and "v2.widgets" in path:
            selection_input_path = path
            break

    if not selection_input_path:
        print("   ERROR: SelectionInput class not found in Qdrant")
        return False

    print(f"\n2. Found SelectionInput at: {selection_input_path}")

    # Load via ModuleWrapper
    print("\n3. Loading via ModuleWrapper.get_component_by_path()...")
    SelectionInput = wrapper.get_component_by_path(selection_input_path)
    print(f"   Loaded: {SelectionInput}")

    if not SelectionInput:
        print("   ERROR: Could not load SelectionInput class")
        return False

    # Check available attributes
    print("\n4. Inspecting SelectionInput class...")
    if hasattr(SelectionInput, "Type"):
        print(
            f"   SelectionInput.Type enum: {list(SelectionInput.Type.__members__.keys())}"
        )
    if hasattr(SelectionInput, "SelectionItem"):
        print(f"   SelectionInput.SelectionItem: {SelectionInput.SelectionItem}")

    # Instantiate
    print("\n5. Instantiating SelectionInput with dropdown options...")
    try:
        # Create selection items
        items = []
        if hasattr(SelectionInput, "SelectionItem"):
            items = [
                SelectionInput.SelectionItem(
                    text="Excellent", value="excellent", selected=True
                ),
                SelectionInput.SelectionItem(text="Good", value="good", selected=False),
                SelectionInput.SelectionItem(
                    text="Needs Improvement", value="needs_improvement", selected=False
                ),
            ]
        else:
            # Fallback to dict format
            items = [
                {"text": "Excellent", "value": "excellent", "selected": True},
                {"text": "Good", "value": "good", "selected": False},
                {
                    "text": "Needs Improvement",
                    "value": "needs_improvement",
                    "selected": False,
                },
            ]

        selection_input = SelectionInput(
            name="rating",
            label="How would you rate this?",
            type=(
                SelectionInput.Type.DROPDOWN
                if hasattr(SelectionInput, "Type")
                else None
            ),
            items=items,
        )
        print(f"   Created: {selection_input}")

        # Render
        print("\n6. Rendering to Google Chat JSON...")
        rendered = selection_input.render()
        print(json.dumps(rendered, indent=2))

        return True

    except Exception as e:
        print(f"   ERROR during instantiation: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_build_form_card_via_qdrant():
    """
    Test: Build a complete form card using components loaded via Qdrant.

    This demonstrates the CORRECT flow for form cards:
    1. Search Qdrant for Section, TextInput, SelectionInput, ButtonList
    2. Load each via ModuleWrapper.get_component_by_path()
    3. Instantiate with form field data
    4. Compose into Section
    5. Render to Google Chat JSON
    """
    print("\n" + "=" * 60)
    print("TEST: Full Form Card via Qdrant Flow")
    print("=" * 60)

    client = get_qdrant_client()
    embedder = get_embedder(use_colbert=True)
    wrapper = get_module_wrapper()

    # Components to find - path-style queries work better with ColBERT
    components_to_find = {
        "Section": "card_framework.v2.section.Section",
        "TextInput": "card_framework.v2.widgets.text_input.TextInput",
        "SelectionInput": "card_framework.v2.widgets.selection_input.SelectionInput",
        "ButtonList": "card_framework.v2.widgets.button_list.ButtonList",
        "Button": "card_framework.v2.widgets.decorated_text.Button onClick",
    }

    loaded = {}

    print("\n1. Loading components via Qdrant search...")
    for name, query in components_to_find.items():
        results = search_components(client, embedder, query, limit=10)
        for r in results:
            path = r.payload.get("full_path", "")
            rname = r.payload.get("name", "")
            rtype = r.payload.get("type", "")

            if rname == name and rtype == "class" and "v2" in path:
                cls = wrapper.get_component_by_path(path)
                if cls:
                    loaded[name] = cls
                    print(f"   {name}: {path} (score: {r.score:.2f})")
                    break

    print(f"\n   Loaded {len(loaded)} components: {list(loaded.keys())}")

    # Build form card
    print("\n2. Building form card...")
    try:
        Section = loaded.get("Section")
        TextInput = loaded.get("TextInput")
        SelectionInput = loaded.get("SelectionInput")
        ButtonList = loaded.get("ButtonList")
        Button = loaded.get("Button")

        if not all([Section, TextInput, SelectionInput]):
            print(f"   Missing required components")
            return False

        # Create form widgets
        widgets = []

        # Text input: Name
        name_input = TextInput(
            name="user_name",
            label="Your Name",
            hint_text="Enter your full name",
        )
        widgets.append(name_input)

        # Selection input: Rating dropdown
        if hasattr(SelectionInput, "SelectionItem"):
            items = [
                SelectionInput.SelectionItem(
                    text="Excellent", value="excellent", selected=True
                ),
                SelectionInput.SelectionItem(text="Good", value="good", selected=False),
                SelectionInput.SelectionItem(
                    text="Needs Improvement", value="needs_improvement", selected=False
                ),
            ]
        else:
            items = [
                {"text": "Excellent", "value": "excellent", "selected": True},
                {"text": "Good", "value": "good"},
                {"text": "Needs Improvement", "value": "needs_improvement"},
            ]

        rating_input = SelectionInput(
            name="rating",
            label="How would you rate this?",
            type=(
                SelectionInput.Type.DROPDOWN
                if hasattr(SelectionInput, "Type")
                else None
            ),
            items=items,
        )
        widgets.append(rating_input)

        # Text input: Comments
        comments_input = TextInput(
            name="comments",
            label="Additional Comments",
            hint_text="Any feedback?",
            type=TextInput.Type.MULTIPLE_LINE if hasattr(TextInput, "Type") else None,
        )
        widgets.append(comments_input)

        # Submit button
        if ButtonList and Button:
            submit_button = Button(
                text="Submit Feedback",
                on_click={"openLink": {"url": "https://example.com/submit"}},
            )
            button_list = ButtonList(buttons=[submit_button])
            widgets.append(button_list)

        # Create section
        section = Section(
            header="Feedback Form",
            widgets=widgets,
        )

        print(f"   Created section with {len(widgets)} widgets")

        # Render
        print("\n3. Rendering form card to Google Chat JSON...")
        rendered = section.render()
        print(json.dumps(rendered, indent=2))

        return True

    except Exception as e:
        print(f"   ERROR: {e}")
        import traceback

        traceback.print_exc()
        return False


def main():
    """Run form component POC tests."""
    print("=" * 60)
    print("POC: Form Components via Qdrant → ModuleWrapper → Render")
    print("=" * 60)
    print(
        "\nThis POC verifies form components use the SAME flow as all other components:"
    )
    print("  1. Search Qdrant for TextInput, SelectionInput, etc.")
    print("  2. Load via ModuleWrapper.get_component_by_path()")
    print("  3. Instantiate with form field data")
    print("  4. Call .render() for Google Chat JSON")
    print()

    results = []

    # Test 1: TextInput via Qdrant
    results.append(("TextInput via Qdrant", test_search_text_input()))

    # Test 2: SelectionInput via Qdrant
    results.append(("SelectionInput via Qdrant", test_search_selection_input()))

    # Test 3: Full form card via Qdrant
    results.append(("Full Form Card via Qdrant", test_build_form_card_via_qdrant()))

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for name, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"   {name}: {status}")

    all_passed = all(r[1] for r in results)
    print(f"\n   Overall: {'ALL TESTS PASSED' if all_passed else 'SOME TESTS FAILED'}")

    if all_passed:
        print("\n" + "=" * 60)
        print("KEY FINDINGS")
        print("=" * 60)
        print("  - TextInput can be found and loaded via Qdrant → ModuleWrapper")
        print("  - SelectionInput can be found and loaded via Qdrant → ModuleWrapper")
        print("  - Form cards should use the SAME component loading flow")
        print("  - No special NLP parsing needed - just search for form components")

    return all_passed


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
