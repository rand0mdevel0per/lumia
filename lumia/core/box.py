"""
Box Container - Smart parameter container with dual transport modes.

The Box is the ONLY permitted parameter type for pipeline and event handlers.
It provides two transport modes:
1. Dill serialization path: For serializable objects (value semantics)
2. Arc reference counting path: For non-serializable resources (shared ownership)

This prevents type-chaos from untyped Any passing across plugin boundaries.
"""

import pickle
from typing import Any, TypeVar

import dill

T = TypeVar("T")


class BoxError(Exception):
    """Base exception for Box-related errors."""
    pass


class TypeMismatchError(BoxError):
    """Raised when .into() is called with mismatched type."""
    pass


class _ArcInner:
    """
    Internal Arc reference counter for non-serializable resources.

    Implements Arc<T> semantics: reference count tracked, destructor called on zero.
    """

    def __init__(self, value: Any):
        self.value = value
        self.refcount = 1
        self.destructor = self._get_destructor(value)
        self._refs = []  # Track weak references

    def _get_destructor(self, value: Any):
        """Find appropriate destructor method for the resource."""
        # Check for common destructor methods in priority order
        for method_name in ['close', 'release', '__exit__', 'cleanup', 'shutdown']:
            if hasattr(value, method_name):
                method = getattr(value, method_name)
                if callable(method):
                    return method
        return None

    def incref(self):
        """Increment reference count."""
        self.refcount += 1

    def decref(self):
        """Decrement reference count and call destructor if zero."""
        self.refcount -= 1
        if self.refcount == 0:
            self._cleanup()

    def _cleanup(self):
        """Call destructor if available."""
        if self.destructor is not None:
            try:
                # Handle context manager __exit__ specially
                if self.destructor.__name__ == '__exit__':
                    self.destructor(None, None, None)
                else:
                    self.destructor()
            except Exception as e:
                # Log but don't raise - cleanup should be best-effort
                import warnings
                warnings.warn(f"Box Arc destructor failed: {e}", RuntimeWarning, stacklevel=2)


def _has_destructor(obj: Any) -> bool:
    """Check if object has a destructor method that should be called."""
    for method_name in ['close', 'release', '__exit__', 'cleanup', 'shutdown']:
        if hasattr(obj, method_name) and callable(getattr(obj, method_name)):
            return True
    return False


def _is_serializable(obj: Any) -> bool:
    """
    Detect if object can be dill-serialized.

    Trade-off: Try-except is slower than type checking, but more accurate.
    This is acceptable since Box creation is not in the hot path.
    """
    try:
        dill.dumps(obj)
        return True
    except (TypeError, AttributeError, pickle.PicklingError):
        return False


class Box:
    """
    Smart container for parameter passing across plugin boundaries.

    Automatically detects whether to use dill serialization (for serializable objects)
    or Arc reference counting (for non-serializable resources like sockets, file handles).

    Usage:
        # Serializable path
        box = Box.any({"key": "value"})
        data = box.into()  # Returns deserialized copy

        # Arc path (non-serializable)
        import socket
        sock = socket.socket()
        box = Box.any(sock)
        sock2 = box.into()  # Returns same object, refcount+1
        del box  # Triggers destructor when refcount reaches 0
    """

    def __init__(self, inner_type: type, transport_mode: str, data: Any):
        """
        Internal constructor. Use Box.any() instead.

        Args:
            inner_type: The type of the contained value
            transport_mode: Either 'dill' or 'arc'
            data: Either serialized bytes (dill) or _ArcInner (arc)
        """
        self._inner_type = inner_type
        self._mode = transport_mode
        self._data = data

    @classmethod
    def any(cls, value: Any) -> "Box":
        """
        Create a Box from any value, auto-detecting transport mode.

        Args:
            value: The value to box

        Returns:
            Box instance with appropriate transport mode
        """
        inner_type = type(value)

        # Check for cycle: value should not have _box_ref attribute
        if hasattr(value, '_box_ref'):
            raise BoxError(
                "Resource objects MUST NOT hold a back-reference to their Box "
                "(prevents refcount cycle → leak)"
            )

        # Force Arc path for objects with destructors, even if serializable
        # This ensures destructors are called when refcount reaches zero
        if _has_destructor(value):
            arc_inner = _ArcInner(value)
            return cls(inner_type, 'arc', arc_inner)

        # Detect serializable vs non-serializable
        if _is_serializable(value):
            # Dill path: serialize immediately
            serialized = dill.dumps(value)
            return cls(inner_type, 'dill', serialized)
        else:
            # Arc path: wrap in reference counter
            arc_inner = _ArcInner(value)
            return cls(inner_type, 'arc', arc_inner)

    def into(self) -> Any:
        """
        Unpack the Box and return the contained value.

        For dill mode: deserializes and returns a new copy
        For arc mode: returns the same object and increments refcount

        Returns:
            The contained value

        Raises:
            TypeMismatchError: If type assertion fails (future enhancement)
        """
        if self._mode == 'dill':
            # Deserialize and return new copy
            return dill.loads(self._data)
        else:  # arc mode
            # Return same object, increment refcount
            arc_inner: _ArcInner = self._data
            arc_inner.incref()
            return arc_inner.value

    def clone(self) -> "Box":
        """
        Clone the Box.

        For dill mode: creates new Box with same serialized data (new deserialized copy on into())
        For arc mode: creates new Box sharing the same Arc (refcount+1)

        Returns:
            New Box instance
        """
        if self._mode == 'dill':
            # Dill path: share serialized data (cheap)
            return Box(self._inner_type, 'dill', self._data)
        else:  # arc mode
            # Arc path: increment refcount and share Arc
            arc_inner: _ArcInner = self._data
            arc_inner.incref()
            return Box(self._inner_type, 'arc', arc_inner)

    def inner_type(self) -> type:
        """
        Get the type of the contained value.

        Used by validator for static type checking.

        Returns:
            The type of the contained value
        """
        return self._inner_type

    def __del__(self):
        """
        Destructor: decrement Arc refcount if in arc mode.
        """
        if self._mode == 'arc':
            arc_inner: _ArcInner = self._data
            arc_inner.decref()

    def __repr__(self) -> str:
        return f"Box<{self._inner_type.__name__}, mode={self._mode}>"
