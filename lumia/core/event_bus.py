"""
Event Bus - Core messaging infrastructure with three primitives.

This module implements:
1. Event: Uninterruptible notification (all subscribers execute)
2. EventChain: Ordered transform (subscribers may mutate Box content)
3. Interceptor: Pre-dispatch blocking (can prevent event from reaching consumers)

All three primitives support:
- Priority-based execution (higher priority = earlier execution)
- Glob/regex pattern matching for event IDs
- Thread-safe concurrent dispatch
"""

import re
from collections.abc import Callable
from dataclasses import dataclass

from lumia.core.box import Box
from lumia.core.utils import (
    InterceptorContext,
    _set_interceptor_context,
)


class EventBusError(Exception):
    """Base exception for event bus errors."""

    pass


class RegistrationError(EventBusError):
    """Raised when handler registration fails."""

    pass


@dataclass
class Handler:
    """
    Represents a registered event handler.

    Attributes:
        callback: The handler function
        priority: Higher priority executes first
        registration_order: Tie-breaker for same priority (lower = earlier)
        requires_src: Whether handler expects 'src' parameter (for regex variants)
    """

    callback: Callable
    priority: int
    registration_order: int
    requires_src: bool = False

    def __call__(self, event_id: str, content: Box) -> None:
        """Execute the handler."""
        if self.requires_src:
            self.callback(event_id, content)
        else:
            self.callback(content)


@dataclass
class Interceptor:
    """
    Represents a registered interceptor.

    Interceptors execute before any Event consumers or EventChain handlers.
    """

    callback: Callable
    priority: int
    registration_order: int
    requires_src: bool = False

    def __call__(self, event_id: str, content: Box) -> None:
        """Execute the interceptor."""
        if self.requires_src:
            self.callback(event_id, content)
        else:
            self.callback(content)


class EventBus:
    """
    Core event bus implementation.

    Manages registration and dispatch of Event, EventChain, and Interceptor primitives.
    """

    def __init__(self):
        # Exact route storage: event_id -> list of handlers
        # Note: Event and EventChain share the same handler registry
        # The difference is semantic: Event handlers MUST NOT mutate Box,
        # EventChain handlers MAY mutate Box
        self._event_routes: dict[str, list[Handler]] = {}
        self._interceptor_routes: dict[str, list[Interceptor]] = {}

        # Pattern route storage: compiled regex -> list of handlers
        self._event_patterns: list[tuple[re.Pattern, list[Handler]]] = []
        self._interceptor_patterns: list[tuple[re.Pattern, list[Interceptor]]] = []

        # Registration order counter for tie-breaking
        self._registration_counter = 0

        # Index built flag (lazy building)
        self._index_built = False

    def _next_registration_order(self) -> int:
        """Get next registration order number."""
        order = self._registration_counter
        self._registration_counter += 1
        return order

    def _glob_to_regex(self, pattern: str) -> re.Pattern:
        """
        Convert glob pattern to compiled regex.

        Supports:
        - * matches any characters within a segment (not across dots)
        - ** would match across segments (not implemented yet, treat as *)

        Example:
            'msg.send, dest=3.qq.group-*' -> regex matching group IDs
        """
        # Escape special regex characters except *
        escaped = re.escape(pattern)
        # Replace escaped \* with [^.]* to match within segments only
        regex_pattern = escaped.replace(r"\*", "[^.]*")
        return re.compile(f"^{regex_pattern}$")

    def _sort_handlers(self, handlers: list[Handler]) -> list[Handler]:
        """
        Sort handlers by priority (descending) and registration order (ascending).

        Higher priority executes first. Same priority uses registration order as tie-breaker.
        """
        return sorted(handlers, key=lambda h: (-h.priority, h.registration_order))

    def _sort_interceptors(self, interceptors: list[Interceptor]) -> list[Interceptor]:
        """Sort interceptors by priority and registration order."""
        return sorted(interceptors, key=lambda i: (-i.priority, i.registration_order))

    # Event consumer registration
    def register_event_consumer(
        self, event_id: str, callback: Callable, priority: int = 0
    ) -> None:
        """
        Register an Event consumer for exact event ID match.

        Args:
            event_id: Exact event ID to match
            callback: Handler function taking (content: Box)
            priority: Execution priority (higher = earlier)
        """
        handler = Handler(
            callback=callback,
            priority=priority,
            registration_order=self._next_registration_order(),
            requires_src=False,
        )
        if event_id not in self._event_routes:
            self._event_routes[event_id] = []
        self._event_routes[event_id].append(handler)

    def register_event_consumer_re(
        self, pattern: str, callback: Callable, priority: int = 0
    ) -> None:
        """
        Register an Event consumer for pattern match.

        Args:
            pattern: Glob pattern to match event IDs
            callback: Handler function taking (src: str, content: Box)
            priority: Execution priority (higher = earlier)

        Raises:
            RegistrationError: If callback doesn't accept 'src' parameter
        """
        # Validate that callback accepts src parameter
        import inspect

        sig = inspect.signature(callback)
        params = list(sig.parameters.keys())
        if len(params) < 1 or params[0] != "src":
            raise RegistrationError(
                f"Pattern-based consumer must have 'src' as first parameter. "
                f"Got: {params}"
            )

        handler = Handler(
            callback=callback,
            priority=priority,
            registration_order=self._next_registration_order(),
            requires_src=True,
        )
        regex = self._glob_to_regex(pattern)
        self._event_patterns.append((regex, [handler]))

    # EventChain consumer registration
    def register_chain_consumer(
        self, event_id: str, callback: Callable, priority: int = 0
    ) -> None:
        """Register an EventChain consumer for exact event ID match."""
        handler = Handler(
            callback=callback,
            priority=priority,
            registration_order=self._next_registration_order(),
            requires_src=False,
        )
        if event_id not in self._chain_routes:
            self._chain_routes[event_id] = []
        self._chain_routes[event_id].append(handler)

    def register_chain_consumer_re(
        self, pattern: str, callback: Callable, priority: int = 0
    ) -> None:
        """Register an EventChain consumer for pattern match."""
        import inspect

        sig = inspect.signature(callback)
        params = list(sig.parameters.keys())
        if len(params) < 1 or params[0] != "src":
            raise RegistrationError(
                f"Pattern-based chain consumer must have 'src' as first parameter. "
                f"Got: {params}"
            )

        handler = Handler(
            callback=callback,
            priority=priority,
            registration_order=self._next_registration_order(),
            requires_src=True,
        )
        regex = self._glob_to_regex(pattern)
        self._chain_patterns.append((regex, [handler]))

    # Interceptor registration
    def register_interceptor(
        self, event_id: str, callback: Callable, priority: int = 0
    ) -> None:
        """Register an Interceptor for exact event ID match."""
        interceptor = Interceptor(
            callback=callback,
            priority=priority,
            registration_order=self._next_registration_order(),
            requires_src=False,
        )
        if event_id not in self._interceptor_routes:
            self._interceptor_routes[event_id] = []
        self._interceptor_routes[event_id].append(interceptor)

    def register_interceptor_re(
        self, pattern: str, callback: Callable, priority: int = 0
    ) -> None:
        """Register an Interceptor for pattern match."""
        import inspect

        sig = inspect.signature(callback)
        params = list(sig.parameters.keys())
        if len(params) < 1 or params[0] != "src":
            raise RegistrationError(
                f"Pattern-based interceptor must have 'src' as first parameter. "
                f"Got: {params}"
            )

        interceptor = Interceptor(
            callback=callback,
            priority=priority,
            registration_order=self._next_registration_order(),
            requires_src=True,
        )
        regex = self._glob_to_regex(pattern)
        self._interceptor_patterns.append((regex, [interceptor]))

    def _find_handlers(
        self,
        event_id: str,
        exact_routes: dict[str, list[Handler]],
        pattern_routes: list[tuple[re.Pattern, list[Handler]]],
    ) -> list[Handler]:
        """
        Find all handlers matching the event ID.

        Combines exact matches and pattern matches, then sorts by priority.
        """
        handlers = []

        # Exact match
        if event_id in exact_routes:
            handlers.extend(exact_routes[event_id])

        # Pattern matches
        for pattern, pattern_handlers in pattern_routes:
            if pattern.match(event_id):
                handlers.extend(pattern_handlers)

        # Sort by priority and registration order
        return self._sort_handlers(handlers)

    def _find_interceptors(self, event_id: str) -> list[Interceptor]:
        """Find all interceptors matching the event ID."""
        interceptors = []

        # Exact match
        if event_id in self._interceptor_routes:
            interceptors.extend(self._interceptor_routes[event_id])

        # Pattern matches
        for pattern, pattern_interceptors in self._interceptor_patterns:
            if pattern.match(event_id):
                interceptors.extend(pattern_interceptors)

        # Sort by priority and registration order
        return self._sort_interceptors(interceptors)

    def _execute_interceptors(self, event_id: str, content: Box) -> bool:
        """
        Execute interceptors for the event.

        Returns:
            True if event should be intercepted (blocked), False otherwise
        """
        interceptors = self._find_interceptors(event_id)
        if not interceptors:
            return False

        # Create interceptor context
        ctx = InterceptorContext()
        _set_interceptor_context(ctx)

        try:
            for interceptor in interceptors:
                interceptor(event_id, content)
                # Check if intercept() was called
                if ctx.should_intercept:
                    return True
            return False
        finally:
            # Clear context
            _set_interceptor_context(None)

    def dispatch_event(self, event_id: str, content: Box) -> None:
        """
        Dispatch an Event (uninterruptible notification).

        All subscribers execute in priority order. Subscribers MUST NOT mutate Box content.

        Args:
            event_id: The event identifier
            content: The event payload (Box container)
        """
        # Execute interceptors first
        if self._execute_interceptors(event_id, content):
            # Event was intercepted, don't dispatch to consumers
            return

        # Find all matching handlers
        handlers = self._find_handlers(event_id, self._event_routes, self._event_patterns)

        # Execute all handlers (uninterruptible)
        for handler in handlers:
            try:
                handler(event_id, content)
            except Exception as e:
                # Log but don't stop execution
                import warnings

                warnings.warn(
                    f"Event handler failed for '{event_id}': {e}",
                    RuntimeWarning,
                    stacklevel=2,
                )

    def dispatch_chain(self, event_id: str, content: Box) -> None:
        """
        Dispatch an EventChain (ordered transform).

        Subscribers execute in priority order and MAY mutate Box content.
        The same Box instance is passed to all handlers (mutation propagates).

        Note: EventChain uses the same handler registry as Event. The difference
        is semantic - EventChain handlers are expected to mutate Box content,
        while Event handlers should not.

        Args:
            event_id: The event identifier
            content: The event payload (Box container, may be mutated)
        """
        # Execute interceptors first
        if self._execute_interceptors(event_id, content):
            # Event was intercepted, don't dispatch to consumers
            return

        # Find all matching handlers (same registry as Event)
        handlers = self._find_handlers(event_id, self._event_routes, self._event_patterns)

        # Execute all handlers (uninterruptible, but mutation allowed)
        for handler in handlers:
            try:
                handler(event_id, content)
            except Exception as e:
                # Log but don't stop execution
                import warnings

                warnings.warn(
                    f"EventChain handler failed for '{event_id}': {e}",
                    RuntimeWarning,
                    stacklevel=2,
                )


# Global event bus instance
_global_event_bus = EventBus()


# Public API functions
def consumer(event_id: str, priority: int = 0):
    """
    Decorator to register an Event consumer.

    Example:
        @lumia.event.consumer('cron.1h', priority=10)
        def cache_refresh(content: Box):
            PlCache.refresh(str(content.into()))
    """

    def decorator(func: Callable) -> Callable:
        _global_event_bus.register_event_consumer(event_id, func, priority)
        return func

    return decorator


def consumer_re(pattern: str, priority: int = 0):
    """
    Decorator to register an Event consumer with pattern matching.

    Example:
        @lumia.event.consumer_re('msg.send, dest=3.qq.group-*', priority=10)
        def send_qq(src: str, content: Box):
            gid = src.split('-')[1]
            qq.send(content.into(), gid)
    """

    def decorator(func: Callable) -> Callable:
        _global_event_bus.register_event_consumer_re(pattern, func, priority)
        return func

    return decorator


def interceptor(event_id: str, priority: int = 0):
    """
    Decorator to register an Interceptor.

    Example:
        @lumia.event.interceptor('bus.adapters.qq.find_active', priority=100)
        def heartbeat(content: Box):
            lumia.system.adapters.heartbeat(str(content.into()), 'napcat-adapter-qq-1.0.29')
    """

    def decorator(func: Callable) -> Callable:
        _global_event_bus.register_interceptor(event_id, func, priority)
        return func

    return decorator


def interceptor_re(pattern: str, priority: int = 0):
    """
    Decorator to register an Interceptor with pattern matching.

    Example:
        @lumia.event.interceptor_re('bus.adapters.qq.find_old.*', priority=9999)
        def stop_old(src: str, content: Box):
            if str(content.into()) < '1.0.29':
                lumia.utils.intercept()
    """

    def decorator(func: Callable) -> Callable:
        _global_event_bus.register_interceptor_re(pattern, func, priority)
        return func

    return decorator


def start(id: str, content: Box) -> None:
    """
    Start an Event dispatch.

    Example:
        lumia.event.start('msg.send, dest=3.qq.group-123', Box.any(msg))
    """
    _global_event_bus.dispatch_event(id, content)


def start_chain(id: str, content: Box) -> None:
    """
    Start an EventChain dispatch.

    Example:
        lumia.event.start_chain('msg.preprocess', Box.any(raw_msg))
    """
    _global_event_bus.dispatch_chain(id, content)

