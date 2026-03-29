"""Tests for WrapperRegistry and shared DSL helpers."""

import threading

import pytest

from adapters.module_wrapper.wrapper_factory import (
    WrapperRegistry,
    generate_dsl_field_description,
    generate_dsl_quick_reference,
    get_skill_resources_safe,
)

# =============================================================================
# FIXTURES
# =============================================================================


class MockWrapper:
    """Minimal mock wrapper for testing."""

    def __init__(self, name="test"):
        self.name = name
        self.symbol_mapping = {
            "Section": "§",
            "Button": "ᵬ",
            "DecoratedText": "đ",
        }

    def get_skill_resources_annotation(self, skill_name, resource_hints):
        return [
            {"name": f"{skill_name}/{k}", **v}
            for k, v in resource_hints.items()
        ]


@pytest.fixture(autouse=True)
def clean_registry():
    """Ensure registry is clean before and after each test."""
    # Save existing state
    saved_factories = dict(WrapperRegistry._factories)
    saved_instances = dict(WrapperRegistry._instances)
    saved_locks = dict(WrapperRegistry._locks)

    # Clear for test
    WrapperRegistry._factories.clear()
    WrapperRegistry._instances.clear()
    WrapperRegistry._locks.clear()

    yield

    # Restore
    WrapperRegistry._factories.clear()
    WrapperRegistry._factories.update(saved_factories)
    WrapperRegistry._instances.clear()
    WrapperRegistry._instances.update(saved_instances)
    WrapperRegistry._locks.clear()
    WrapperRegistry._locks.update(saved_locks)


# =============================================================================
# WRAPPER REGISTRY TESTS
# =============================================================================


class TestWrapperRegistry:
    def test_register_and_get(self):
        """Register a factory and retrieve the wrapper."""
        WrapperRegistry.register("test", lambda: MockWrapper("test"))
        wrapper = WrapperRegistry.get("test")
        assert isinstance(wrapper, MockWrapper)
        assert wrapper.name == "test"

    def test_singleton_behavior(self):
        """Same instance returned on repeated get() calls."""
        call_count = 0

        def factory():
            nonlocal call_count
            call_count += 1
            return MockWrapper(f"v{call_count}")

        WrapperRegistry.register("test", factory)
        w1 = WrapperRegistry.get("test")
        w2 = WrapperRegistry.get("test")
        assert w1 is w2
        assert call_count == 1

    def test_force_reinitialize(self):
        """force_reinitialize creates a new instance."""
        call_count = 0

        def factory():
            nonlocal call_count
            call_count += 1
            return MockWrapper(f"v{call_count}")

        WrapperRegistry.register("test", factory)
        w1 = WrapperRegistry.get("test")
        w2 = WrapperRegistry.get("test", force_reinitialize=True)
        assert w1 is not w2
        assert call_count == 2

    def test_reset(self):
        """Reset clears cached instance, next get() creates new one."""
        call_count = 0

        def factory():
            nonlocal call_count
            call_count += 1
            return MockWrapper(f"v{call_count}")

        WrapperRegistry.register("test", factory)
        w1 = WrapperRegistry.get("test")
        WrapperRegistry.reset("test")
        w2 = WrapperRegistry.get("test")
        assert w1 is not w2
        assert call_count == 2

    def test_reset_all(self):
        """reset_all clears all cached instances."""
        WrapperRegistry.register("a", lambda: MockWrapper("a"))
        WrapperRegistry.register("b", lambda: MockWrapper("b"))
        WrapperRegistry.get("a")
        WrapperRegistry.get("b")
        assert len(WrapperRegistry._instances) == 2

        WrapperRegistry.reset_all()
        assert len(WrapperRegistry._instances) == 0

    def test_get_unregistered_raises(self):
        """KeyError when getting an unregistered wrapper."""
        with pytest.raises(KeyError, match="No wrapper factory"):
            WrapperRegistry.get("nonexistent")

    def test_is_registered(self):
        """is_registered returns correct state."""
        assert not WrapperRegistry.is_registered("test")
        WrapperRegistry.register("test", lambda: MockWrapper())
        assert WrapperRegistry.is_registered("test")

    def test_registered_names(self):
        """registered_names returns list of all registered names."""
        WrapperRegistry.register("a", lambda: MockWrapper())
        WrapperRegistry.register("b", lambda: MockWrapper())
        names = WrapperRegistry.registered_names()
        assert "a" in names
        assert "b" in names

    def test_thread_safety(self):
        """Concurrent get() calls produce the same singleton."""
        call_count = 0
        lock = threading.Lock()

        def factory():
            nonlocal call_count
            with lock:
                call_count += 1
            return MockWrapper(f"v{call_count}")

        WrapperRegistry.register("test", factory)

        results = []
        errors = []

        def get_wrapper():
            try:
                results.append(WrapperRegistry.get("test"))
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=get_wrapper) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert len(results) == 10
        # All should be the same instance
        assert all(r is results[0] for r in results)
        assert call_count == 1


# =============================================================================
# SHARED HELPER TESTS
# =============================================================================


class TestGenerateDSLQuickReference:
    def test_basic_output(self):
        wrapper = MockWrapper()
        categories = {
            "Layout": ["Section"],
            "Interactive": ["Button"],
        }
        result = generate_dsl_quick_reference(
            wrapper, categories, title="Test DSL"
        )
        assert "## Test DSL" in result
        assert "§=Section" in result
        assert "ᵬ=Button" in result

    def test_with_examples(self):
        wrapper = MockWrapper()
        result = generate_dsl_quick_reference(
            wrapper,
            {"Layout": ["Section"]},
            examples=["§[đ]", "§[ᵬ×2]"],
        )
        assert "§[đ]" in result
        assert "§[ᵬ×2]" in result


class TestGenerateDSLFieldDescription:
    def test_basic_output(self):
        wrapper = MockWrapper()
        result = generate_dsl_field_description(
            wrapper,
            key_components=["Section", "Button"],
            skill_uri="skill://test/",
        )
        assert "§=Section" in result
        assert "ᵬ=Button" in result
        assert "skill://test/" in result


class TestGetSkillResourcesSafe:
    def test_with_valid_wrapper(self):
        wrapper = MockWrapper()
        result = get_skill_resources_safe(
            wrapper,
            skill_name="test",
            resource_hints={
                "doc.md": {
                    "purpose": "Test doc",
                    "when_to_read": "Always",
                }
            },
        )
        assert len(result) == 1
        assert result[0]["name"] == "test/doc.md"

    def test_with_none_wrapper(self):
        result = get_skill_resources_safe(
            None,
            skill_name="test",
            resource_hints={"doc.md": {"purpose": "x", "when_to_read": "y"}},
        )
        assert result == []

    def test_with_wrapper_without_method(self):
        """Wrapper that doesn't have get_skill_resources_annotation."""

        class BareWrapper:
            pass

        result = get_skill_resources_safe(
            BareWrapper(),
            skill_name="test",
            resource_hints={"doc.md": {"purpose": "x", "when_to_read": "y"}},
        )
        assert result == []

    def test_with_failing_wrapper(self):
        """Wrapper where get_skill_resources_annotation raises."""

        class FailingWrapper:
            def get_skill_resources_annotation(self, **kwargs):
                raise RuntimeError("boom")

        result = get_skill_resources_safe(
            FailingWrapper(),
            skill_name="test",
            resource_hints={"doc.md": {"purpose": "x", "when_to_read": "y"}},
        )
        assert result == []
