"""
Pipeline - Breakable message flow dispatcher.

Pipeline is the ONLY breakable message flow in Lumia. A handler either:
- Calls lumia.utils.next() → execution passes to next lower-priority handler
- Returns without calling next() → chain breaks, no further handlers execute

Key differences from Event/EventChain:
- Pipeline is breakable (Event/EventChain are uninterruptible)
- Handlers control flow explicitly via next()
- Used for message processing chains where early handlers may filter/reject
"""

import re
from collections.abc import Callable
from dataclasses import dataclass

from lumia.core.box import Box
from lumia.core.utils import (
    PipelineContext,
    _set_pipeline_context,
)


class PipelineError(Exception):
    """Base exception for pipeline errors."""

    pass


class RegistrationError(PipelineError):
    """Raised when handler registration fails."""

    pass


@dataclass
class PipelineHandler:
    """
    Represents a registered pipeline handler.

    Attributes:
        callback: The handler function
        priv: Priority (higher = executes earlier)
        registration_order: Tie-breaker for same priority
        requires_src: Whether handler expects 'src' parameter (for regex variants)
    """

    callback: Callable
    priv: int
    registration_order: int
    requires_src: bool = False

    def __call__(self, pipeline_id: str, content: Box) -> None:
        """Execute the handler."""
        if self.requires_src:
            self.callback(pipeline_id, content)
        else:
            self.callback(content)


class Pipeline:
    """
    Pipeline dispatcher implementation.

    Manages registration and dispatch of breakable message flows.
    """

    def __init__(self):
        # Exact route storage: pipeline_id -> list of handlers
        self._exact_routes: dict[str, list[PipelineHandler]] = {}

        # Pattern route storage: compiled regex -> list of handlers
        self._pattern_routes: list[tuple[re.Pattern, list[PipelineHandler]]] = []

        # Registration order counter
        self._registration_counter = 0

    def _next_registration_order(self) -> int:
        """Get next registration order number."""
        order = self._registration_counter
        self._registration_counter += 1
        return order

    def _glob_to_regex(self, pattern: str) -> re.Pattern:
        """
        Convert glob pattern to compiled regex.

        * matches any characters within a segment (not across dots).
        """
        escaped = re.escape(pattern)
        # Replace escaped \* with [^.]* to match within segments only
        regex_pattern = escaped.replace(r"\*", "[^.]*")
        return re.compile(f"^{regex_pattern}$")

    def _sort_handlers(self, handlers: list[PipelineHandler]) -> list[PipelineHandler]:
        """
        Sort handlers by priv (descending) and registration order (ascending).

        Higher priv executes first. Same priv uses registration order as tie-breaker.
        """
        return sorted(handlers, key=lambda h: (-h.priv, h.registration_order))

    def register_handler(
        self, pipeline_id: str, callback: Callable, priv: int = 0
    ) -> None:
        """
        Register a pipeline handler for exact pipeline ID match.

        Args:
            pipeline_id: Exact pipeline ID to match
            callback: Handler function taking (content: Box)
            priv: Execution priority (higher = earlier)
        """
        handler = PipelineHandler(
            callback=callback,
            priv=priv,
            registration_order=self._next_registration_order(),
            requires_src=False,
        )
        if pipeline_id not in self._exact_routes:
            self._exact_routes[pipeline_id] = []
        self._exact_routes[pipeline_id].append(handler)

    def register_handler_re(
        self, pattern: str, callback: Callable, priv: int = 0
    ) -> None:
        """
        Register a pipeline handler for pattern match.

        Args:
            pattern: Glob pattern to match pipeline IDs
            callback: Handler function taking (src: str, content: Box)
            priv: Execution priority (higher = earlier)

        Raises:
            RegistrationError: If callback doesn't accept 'src' parameter
        """
        import inspect

        sig = inspect.signature(callback)
        params = list(sig.parameters.keys())
        if len(params) < 1 or params[0] != "src":
            raise RegistrationError(
                f"Pattern-based handler must have 'src' as first parameter. Got: {params}"
            )

        handler = PipelineHandler(
            callback=callback,
            priv=priv,
            registration_order=self._next_registration_order(),
            requires_src=True,
        )
        regex = self._glob_to_regex(pattern)
        self._pattern_routes.append((regex, [handler]))

    def _find_handlers(self, pipeline_id: str) -> list[PipelineHandler]:
        """Find all handlers matching the pipeline ID."""
        handlers = []

        # Exact match
        if pipeline_id in self._exact_routes:
            handlers.extend(self._exact_routes[pipeline_id])

        # Pattern matches
        for pattern, pattern_handlers in self._pattern_routes:
            if pattern.match(pipeline_id):
                handlers.extend(pattern_handlers)

        # Sort by priv and registration order
        return self._sort_handlers(handlers)

    def start(self, id: str, content: Box) -> None:
        """
        Start a pipeline execution.

        Handlers execute in priority order. Each handler must call lumia.utils.next()
        to continue to the next handler. If next() is not called, the chain breaks.

        Args:
            id: The pipeline identifier
            content: The pipeline payload (Box container)
        """
        handlers = self._find_handlers(id)
        if not handlers:
            return

        # Create pipeline context
        ctx = PipelineContext()
        _set_pipeline_context(ctx)

        try:
            for idx, handler in enumerate(handlers):
                ctx.handler_index = idx
                ctx.should_continue = False

                try:
                    handler(id, content)
                except Exception as e:
                    # Log but break chain on error
                    import warnings

                    warnings.warn(
                        f"Pipeline handler failed for '{id}': {e}",
                        RuntimeWarning,
                        stacklevel=2,
                    )
                    break

                # Check if next() was called
                if not ctx.should_continue:
                    # Chain breaks here
                    break
        finally:
            # Clear context
            _set_pipeline_context(None)


# Global pipeline instance
_global_pipeline = Pipeline()


# Public API functions
def on(pipeline_id: str, priv: int = 0):
    """
    Decorator to register a pipeline handler.

    Example:
        @lumia.pipe.on('msg', priv=50)
        def handle_msg(content: Box):
            # process...
            lumia.utils.next()  # continue to next handler
    """

    def decorator(func: Callable) -> Callable:
        _global_pipeline.register_handler(pipeline_id, func, priv)
        return func

    return decorator


def on_re(pattern: str, priv: int = 0):
    """
    Decorator to register a pipeline handler with pattern matching.

    Example:
        @lumia.pipe.on_re('bus.adapters.qq.exp.*', priv=120)
        def explore(src: str, content: Box):
            if not ready:
                lumia.utils.next()
                return
            NapcatClient.initialize()
            lumia.utils.next()
    """

    def decorator(func: Callable) -> Callable:
        _global_pipeline.register_handler_re(pattern, func, priv)
        return func

    return decorator


def start(id: str, content: Box) -> None:
    """
    Start a pipeline execution.

    Example:
        lumia.pipe.start('msg', Box.any(raw_msg))
    """
    _global_pipeline.start(id, content)
