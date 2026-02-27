"""
Tests for Box Container - Smart parameter container with dual transport modes.

This test suite covers:
1. Serializable types (dill path)
2. Non-serializable types (arc path)
3. Arc reference counting
4. Destructor invocation
5. Type introspection
6. Error cases
"""

import pytest
import socket
import tempfile
from pathlib import Path

from lumia.core.box import Box, BoxError, TypeMismatchError, _is_serializable


class TestSerializableDetection:
    """Test the _is_serializable helper function."""

    def test_basic_types_are_serializable(self):
        """Basic Python types should be serializable."""
        assert _is_serializable(42)
        assert _is_serializable("hello")
        assert _is_serializable(3.14)
        assert _is_serializable(True)
        assert _is_serializable(None)

    def test_collections_are_serializable(self):
        """Collections should be serializable."""
        assert _is_serializable([1, 2, 3])
        assert _is_serializable({"key": "value"})
        assert _is_serializable((1, 2, 3))
        assert _is_serializable({1, 2, 3})

    def test_custom_classes_are_serializable(self):
        """Custom classes should be serializable."""
        class CustomClass:
            def __init__(self, value):
                self.value = value

        obj = CustomClass(42)
        assert _is_serializable(obj)

    def test_sockets_not_serializable(self):
        """Sockets should not be serializable."""
        sock = socket.socket()
        try:
            assert not _is_serializable(sock)
        finally:
            sock.close()

    def test_file_handles_use_arc_path(self):
        """File handles should use Arc path due to close() method."""
        with tempfile.NamedTemporaryFile() as f:
            # File handles are technically serializable, but should use Arc path
            # because they have a close() destructor method
            box = Box.any(f)
            assert box._mode == 'arc'


class TestBoxSerializablePath:
    """Test Box with serializable objects (dill path)."""

    def test_box_any_with_int(self):
        """Box should handle integers."""
        box = Box.any(42)
        assert box.inner_type() == int
        assert box.into() == 42

    def test_box_any_with_string(self):
        """Box should handle strings."""
        box = Box.any("hello")
        assert box.inner_type() == str
        assert box.into() == "hello"

    def test_box_any_with_dict(self):
        """Box should handle dictionaries."""
        data = {"key": "value", "number": 42}
        box = Box.any(data)
        assert box.inner_type() == dict
        assert box.into() == data

    def test_box_any_with_list(self):
        """Box should handle lists."""
        data = [1, 2, 3, "four"]
        box = Box.any(data)
        assert box.inner_type() == list
        assert box.into() == data

    def test_box_any_with_custom_class(self):
        """Box should handle custom classes."""
        class Person:
            def __init__(self, name, age):
                self.name = name
                self.age = age

        person = Person("Alice", 30)
        box = Box.any(person)
        assert box.inner_type() == Person

        unpacked = box.into()
        assert unpacked.name == "Alice"
        assert unpacked.age == 30

    def test_dill_path_returns_copy(self):
        """Dill path should return a new copy, not the same object."""
        data = {"key": "value"}
        box = Box.any(data)

        unpacked1 = box.into()
        unpacked2 = box.into()

        # Should be equal but not the same object
        assert unpacked1 == unpacked2
        assert unpacked1 is not unpacked2

        # Modifying one should not affect the other
        unpacked1["new_key"] = "new_value"
        assert "new_key" not in unpacked2

    def test_clone_dill_path(self):
        """Clone should work correctly for dill path."""
        box1 = Box.any({"key": "value"})
        box2 = box1.clone()

        # Both should unpack to equal values
        assert box1.into() == box2.into()

        # But they should be independent copies
        data1 = box1.into()
        data2 = box2.into()
        data1["new_key"] = "new_value"
        assert "new_key" not in data2


class TestBoxArcPath:
    """Test Box with non-serializable resources (arc path)."""

    def test_box_any_with_socket(self):
        """Box should handle sockets via Arc path."""
        sock = socket.socket()
        try:
            box = Box.any(sock)
            assert box.inner_type() == socket.socket

            # Should return the same object
            unpacked = box.into()
            assert unpacked is sock
        finally:
            sock.close()

    def test_box_any_with_file_handle(self):
        """Box should handle file handles via Arc path."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            temp_path = f.name
            box = Box.any(f)
            assert box.inner_type() == type(f)

            # Should return the same object
            unpacked = box.into()
            assert unpacked is f

        # Cleanup
        Path(temp_path).unlink()

    def test_arc_path_returns_same_object(self):
        """Arc path should return the same object, not a copy."""
        sock = socket.socket()
        try:
            box = Box.any(sock)

            unpacked1 = box.into()
            unpacked2 = box.into()

            # Should be the exact same object
            assert unpacked1 is unpacked2
            assert unpacked1 is sock
        finally:
            sock.close()

    def test_clone_arc_path(self):
        """Clone should work correctly for arc path."""
        sock = socket.socket()
        try:
            box1 = Box.any(sock)
            box2 = box1.clone()

            # Both should return the same socket object
            unpacked1 = box1.into()
            unpacked2 = box2.into()
            assert unpacked1 is unpacked2
            assert unpacked1 is sock
        finally:
            sock.close()


class TestArcReferenceCount:
    """Test Arc reference counting behavior."""

    def test_refcount_increments_on_into(self):
        """Refcount should increment when into() is called."""
        sock = socket.socket()
        try:
            box = Box.any(sock)
            # Initial refcount is 1
            assert box._data.refcount == 1

            # Each into() increments refcount
            _ = box.into()
            assert box._data.refcount == 2

            _ = box.into()
            assert box._data.refcount == 3
        finally:
            sock.close()

    def test_refcount_increments_on_clone(self):
        """Refcount should increment when clone() is called."""
        sock = socket.socket()
        try:
            box1 = Box.any(sock)
            assert box1._data.refcount == 1

            box2 = box1.clone()
            assert box1._data.refcount == 2
            assert box2._data.refcount == 2  # Same Arc

            box3 = box1.clone()
            assert box1._data.refcount == 3
        finally:
            sock.close()

    def test_refcount_decrements_on_del(self):
        """Refcount should decrement when Box is deleted."""
        sock = socket.socket()
        try:
            box1 = Box.any(sock)
            box2 = box1.clone()
            assert box1._data.refcount == 2

            del box2
            assert box1._data.refcount == 1
        finally:
            sock.close()


class TestDestructorInvocation:
    """Test that destructors are called when refcount reaches zero."""

    def test_destructor_called_on_zero_refcount(self):
        """Destructor should be called when refcount reaches zero."""
        class MockResource:
            def __init__(self):
                self.closed = False

            def close(self):
                self.closed = True

        resource = MockResource()
        box = Box.any(resource)

        # Resource should not be closed yet
        assert not resource.closed

        # Delete box, refcount goes to 0, destructor called
        del box
        assert resource.closed

    def test_destructor_not_called_while_refs_exist(self):
        """Destructor should not be called while references exist."""
        class MockResource:
            def __init__(self):
                self.closed = False

            def close(self):
                self.closed = True

        resource = MockResource()
        box1 = Box.any(resource)
        box2 = box1.clone()

        # Delete one box, refcount goes to 1, destructor not called
        del box1
        assert not resource.closed

        # Delete second box, refcount goes to 0, destructor called
        del box2
        assert resource.closed

    def test_destructor_methods_priority(self):
        """Test that destructor methods are tried in priority order."""
        class ResourceWithRelease:
            def __init__(self):
                self.released = False

            def release(self):
                self.released = True

        resource = ResourceWithRelease()
        box = Box.any(resource)
        del box
        assert resource.released

    def test_context_manager_exit_called(self):
        """Test that __exit__ is called for context managers."""
        class ContextResource:
            def __init__(self):
                self.exited = False

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_val, exc_tb):
                self.exited = True

        resource = ContextResource()
        box = Box.any(resource)
        del box
        assert resource.exited


class TestErrorCases:
    """Test error handling and edge cases."""

    def test_cycle_detection(self):
        """Box should detect and reject resources with _box_ref attribute."""
        class ResourceWithCycle:
            def __init__(self):
                self._box_ref = None  # This creates a cycle

        resource = ResourceWithCycle()
        with pytest.raises(BoxError, match="back-reference"):
            Box.any(resource)

    def test_repr(self):
        """Test Box string representation."""
        box_int = Box.any(42)
        assert "Box<int" in repr(box_int)
        assert "mode=dill" in repr(box_int)

        sock = socket.socket()
        try:
            box_sock = Box.any(sock)
            assert "Box<socket" in repr(box_sock)
            assert "mode=arc" in repr(box_sock)
        finally:
            sock.close()


class TestTypeIntrospection:
    """Test type introspection API."""

    def test_inner_type_basic_types(self):
        """inner_type() should return correct type for basic types."""
        assert Box.any(42).inner_type() == int
        assert Box.any("hello").inner_type() == str
        assert Box.any(3.14).inner_type() == float
        assert Box.any(True).inner_type() == bool
        assert Box.any([1, 2, 3]).inner_type() == list
        assert Box.any({"key": "value"}).inner_type() == dict

    def test_inner_type_custom_class(self):
        """inner_type() should return correct type for custom classes."""
        class CustomClass:
            pass

        obj = CustomClass()
        box = Box.any(obj)
        assert box.inner_type() == CustomClass

    def test_inner_type_socket(self):
        """inner_type() should return correct type for sockets."""
        sock = socket.socket()
        try:
            box = Box.any(sock)
            assert box.inner_type() == socket.socket
        finally:
            sock.close()

