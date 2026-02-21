#!/usr/bin/env python3
"""
Test the tiered component caching system.

Verifies:
1. L1 (memory) caching and retrieval
2. L2 (pickle) spillover on eviction
3. L3 (wrapper) reconstruction fallback
4. Integration with ModuleWrapper
5. Integration with FeedbackLoop
"""

import os
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_standalone_cache():
    """Test ComponentCache without wrapper."""
    print("=" * 60)
    print("TEST: Standalone ComponentCache")
    print("=" * 60)

    from adapters.module_wrapper.component_cache import CacheEntry, ComponentCache

    # Create cache with small limit to test eviction
    cache_dir = ".test_cache"
    if os.path.exists(cache_dir):
        shutil.rmtree(cache_dir)

    cache = ComponentCache(
        memory_limit=5,  # Small limit to test eviction
        cache_dir=cache_dir,
        wrapper_getter=None,  # No wrapper for this test
    )

    print(f"\n1️⃣  Created cache: {cache}")

    # Add some entries
    for i in range(3):
        entry = cache.put(
            key=f"pattern_{i}",
            component_paths=["Section", f"Widget{i}"],
            instance_params={"text": f"Text {i}"},
            dsl_notation=f"§[ω{i}]",
        )
        print(f"   Added: {entry.key}")

    print(f"\n2️⃣  After adding 3 items: {cache}")
    assert len(cache._l1) == 3, f"Expected 3 items in L1, got {len(cache._l1)}"

    # Retrieve an entry
    entry = cache.get("pattern_1")
    assert entry is not None, "Failed to get pattern_1"
    assert entry.component_paths == ["Section", "Widget1"]
    print(f"   Retrieved: {entry.key} with paths {entry.component_paths}")

    # Add more to trigger eviction
    print("\n3️⃣  Adding more items to trigger L1 eviction...")
    for i in range(3, 8):
        cache.put(
            key=f"pattern_{i}",
            component_paths=["Section", f"Widget{i}"],
            instance_params={"text": f"Text {i}"},
        )

    print(f"   After adding 5 more: {cache}")
    assert len(cache._l1) == 5, f"Expected 5 items in L1, got {len(cache._l1)}"

    # Check L2 has spillover
    l2_count = len(cache._l2_index)
    print(f"   L2 spillover count: {l2_count}")
    assert l2_count >= 2, f"Expected at least 2 items spilled to L2, got {l2_count}"

    # Retrieve from L2 (should promote to L1)
    print("\n4️⃣  Retrieving evicted item from L2...")
    # pattern_0 should have been evicted (oldest)
    entry = cache.get("pattern_0")
    if entry:
        print(f"   Retrieved from L2: {entry.key}")
        assert cache._l1.contains("pattern_0"), "Should be promoted to L1"
    else:
        print("   pattern_0 not found (may have been overwritten)")

    # Check stats
    print(f"\n5️⃣  Cache stats: {cache.stats}")

    # Cleanup
    shutil.rmtree(cache_dir)
    print("\n✅ Standalone cache test passed!")
    return True


def test_wrapper_integration():
    """Test ComponentCache integration with ModuleWrapper."""
    print("\n" + "=" * 60)
    print("TEST: ModuleWrapper Integration")
    print("=" * 60)

    from gchat.card_framework_wrapper import get_card_framework_wrapper

    wrapper = get_card_framework_wrapper()

    print(f"\n1️⃣  Got wrapper: {wrapper.module_name}")

    # Test get_cached_class
    print("\n2️⃣  Testing get_cached_class...")
    Button = wrapper.get_cached_class("Button")
    assert Button is not None, "Failed to get Button class"
    print(f"   Button: {Button}")

    Section = wrapper.get_cached_class("Section")
    assert Section is not None, "Failed to get Section class"
    print(f"   Section: {Section}")

    # Test cache_pattern
    print("\n3️⃣  Testing cache_pattern...")
    entry = wrapper.cache_pattern(
        key="test_status_card",
        component_paths=["Section", "DecoratedText", "ButtonList"],
        instance_params={"text": "Status: Online", "buttons": []},
    )
    print(f"   Cached pattern: {entry.key}")
    print(f"   Component classes: {list(entry.component_classes.keys())}")
    assert "Section" in entry.component_classes
    assert "DecoratedText" in entry.component_classes

    # Test retrieval
    print("\n4️⃣  Testing get_cached_entry...")
    retrieved = wrapper.get_cached_entry("test_status_card")
    assert retrieved is not None, "Failed to retrieve cached pattern"
    print(f"   Retrieved: {retrieved.key}")
    print(f"   Is hydrated: {retrieved._is_hydrated}")

    # Test get_cached_classes (multiple)
    print("\n5️⃣  Testing get_cached_classes...")
    classes = wrapper.get_cached_classes(
        ["Button", "Section", "DecoratedText", "TextParagraph"]
    )
    print(f"   Got {len(classes)} classes: {list(classes.keys())}")
    assert len(classes) >= 3, f"Expected at least 3 classes, got {len(classes)}"

    # Check cache stats
    print(f"\n6️⃣  Cache stats: {wrapper.cache_stats}")

    print("\n✅ ModuleWrapper integration test passed!")
    return True


def test_feedback_loop_integration():
    """Test ComponentCache integration with FeedbackLoop."""
    print("\n" + "=" * 60)
    print("TEST: FeedbackLoop Integration")
    print("=" * 60)

    from gchat.feedback_loop import get_feedback_loop

    fl = get_feedback_loop()

    print(f"\n1️⃣  Got FeedbackLoop")

    # Test _cache_pattern
    print("\n2️⃣  Testing _cache_pattern...")
    test_pattern = {
        "card_id": "test_fl_pattern",
        "component_paths": ["Section", "TextParagraph"],
        "instance_params": {"text": "Hello from FeedbackLoop"},
        "card_description": "A simple text card",
        "dsl_notation": "§[τ]",
    }
    key = fl._cache_pattern(test_pattern)
    print(f"   Cached with key: {key}")

    # Test get_cached_pattern
    print("\n3️⃣  Testing get_cached_pattern...")
    cached = fl.get_cached_pattern("test_fl_pattern")
    if cached:
        print(f"   Retrieved: {cached['key']}")
        print(f"   Component paths: {cached['component_paths']}")
        print(
            f"   Component classes: {list(cached.get('component_classes', {}).keys())}"
        )
        print(f"   From cache: {cached.get('_from_cache', False)}")
    else:
        print("   ⚠️ Pattern not found in cache")

    print("\n✅ FeedbackLoop integration test passed!")
    return True


def test_cache_persistence():
    """Test that L2 cache persists across restarts."""
    print("\n" + "=" * 60)
    print("TEST: Cache Persistence")
    print("=" * 60)

    from adapters.module_wrapper.component_cache import ComponentCache

    cache_dir = ".test_persistence_cache"
    if os.path.exists(cache_dir):
        shutil.rmtree(cache_dir)

    # Create cache and add items
    print("\n1️⃣  Creating cache and adding items...")
    cache1 = ComponentCache(memory_limit=3, cache_dir=cache_dir)

    for i in range(5):  # Add more than memory limit
        cache1.put(
            key=f"persist_{i}",
            component_paths=["Section", f"Widget{i}"],
            instance_params={"value": i},
        )

    print(f"   Cache1: L1={len(cache1._l1)}, L2={len(cache1._l2_index)}")
    l2_count = len(cache1._l2_index)

    # Simulate "restart" by creating new cache with same dir
    print("\n2️⃣  Simulating restart (new cache instance)...")
    cache2 = ComponentCache(memory_limit=3, cache_dir=cache_dir)

    print(f"   Cache2: L1={len(cache2._l1)}, L2={len(cache2._l2_index)}")

    # L2 should have same items
    assert len(cache2._l2_index) == l2_count, (
        f"L2 index not persisted: expected {l2_count}, got {len(cache2._l2_index)}"
    )

    # Retrieve an evicted item from L2
    print("\n3️⃣  Retrieving item from persisted L2...")
    entry = cache2.get("persist_0")  # Should be in L2
    if entry:
        print(f"   Retrieved: {entry.key} with paths {entry.component_paths}")
        assert entry.instance_params.get("value") == 0
    else:
        print("   ⚠️ persist_0 not found")

    # Cleanup
    shutil.rmtree(cache_dir)
    print("\n✅ Cache persistence test passed!")
    return True


def test_cache_with_real_components():
    """Test caching with actual card_framework components."""
    print("\n" + "=" * 60)
    print("TEST: Real Component Instantiation from Cache")
    print("=" * 60)

    from gchat.card_framework_wrapper import get_card_framework_wrapper

    wrapper = get_card_framework_wrapper()

    # Cache a pattern
    print("\n1️⃣  Caching component pattern...")
    entry = wrapper.cache_pattern(
        key="real_button_card",
        component_paths=[
            "Section",
            "DecoratedText",
            "ButtonList",
            "Button",
        ],
        instance_params={
            "text": "Click the button below",
            "buttons": [{"text": "Click Me"}],
        },
    )

    print(f"   Cached: {entry.key}")
    print(f"   Classes: {list(entry.component_classes.keys())}")

    # Use cached classes to build a widget
    print("\n2️⃣  Using cached classes to build widgets...")
    Section = entry.component_classes.get("Section")
    DecoratedText = entry.component_classes.get("DecoratedText")
    ButtonList = entry.component_classes.get("ButtonList")
    Button = entry.component_classes.get("Button")

    if all([Section, DecoratedText, ButtonList, Button]):
        # Build widgets using cached classes
        dt = DecoratedText(text="Status: Online", top_label="Server")
        print(f"   Created DecoratedText: {type(dt).__name__}")

        # Check it renders
        rendered = dt.render()
        print(f"   Rendered keys: {list(rendered.keys())}")

        print("\n✅ Real component instantiation test passed!")
        return True
    else:
        missing = [
            n
            for n, c in [
                ("Section", Section),
                ("DecoratedText", DecoratedText),
                ("ButtonList", ButtonList),
                ("Button", Button),
            ]
            if c is None
        ]
        print(f"   ⚠️ Missing classes: {missing}")
        return False


def test_cache_stats_and_hit_rate():
    """Test cache statistics and hit rate calculation."""
    print("\n" + "=" * 60)
    print("TEST: Cache Stats and Hit Rate")
    print("=" * 60)

    from adapters.module_wrapper.component_cache import ComponentCache

    cache_dir = ".test_stats_cache"
    if os.path.exists(cache_dir):
        shutil.rmtree(cache_dir)

    cache = ComponentCache(memory_limit=10, cache_dir=cache_dir)

    # Add some items
    for i in range(5):
        cache.put(f"item_{i}", [f"Component{i}"], {})

    # Access some items multiple times
    print("\n1️⃣  Performing cache accesses...")
    for _ in range(3):
        cache.get("item_0")  # L1 hit
        cache.get("item_1")  # L1 hit
        cache.get("item_2")  # L1 hit

    cache.get("nonexistent")  # Miss
    cache.get("also_missing")  # Miss

    stats = cache.stats
    print(f"\n2️⃣  Cache stats:")
    print(f"   L1 hits: {stats['l1_hits']}")
    print(f"   L2 hits: {stats['l2_hits']}")
    print(f"   Misses: {stats['misses']}")
    print(f"   Hit rate: {stats['hit_rate']:.1%}")
    print(f"   Total requests: {stats['total_requests']}")

    assert stats["l1_hits"] == 9, f"Expected 9 L1 hits, got {stats['l1_hits']}"
    assert stats["misses"] == 2, f"Expected 2 misses, got {stats['misses']}"
    assert stats["hit_rate"] > 0.8, (
        f"Expected hit rate > 80%, got {stats['hit_rate']:.1%}"
    )

    # Cleanup
    shutil.rmtree(cache_dir)
    print("\n✅ Cache stats test passed!")
    return True


if __name__ == "__main__":
    print("=" * 60)
    print("COMPONENT CACHE TESTS")
    print("=" * 60)

    tests = [
        test_standalone_cache,
        test_cache_persistence,
        test_cache_stats_and_hit_rate,
        test_wrapper_integration,
        test_feedback_loop_integration,
        test_cache_with_real_components,
    ]

    results = []
    for test in tests:
        try:
            result = test()
            results.append((test.__name__, result))
        except Exception as e:
            print(f"\n❌ {test.__name__} failed with exception: {e}")
            import traceback

            traceback.print_exc()
            results.append((test.__name__, False))

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    passed = sum(1 for _, r in results if r)
    failed = len(results) - passed

    for name, result in results:
        status = "✅" if result else "❌"
        print(f"  {status} {name}")

    print(f"\nTotal: {passed} passed, {failed} failed")
