"""
Utils Module - Helper functions for pipeline and event bus control flow.

This module provides:
- next(): Continue pipeline execution to next handler
- intercept(): Block event from reaching consumers

These functions use contextvars for thread-safe context management.
"""

from contextvars import ContextVar


class UtilsError(Exception):
    """Base exception for utils-related errors."""

    pass


class PipelineContext:
    """Context for pipeline execution."""

    def __init__(self):
        self.should_continue = False
        self.handler_index = 0


class InterceptorContext:
    """Context for interceptor execution."""

    def __init__(self):
        self.should_intercept = False


# Context variables for thread-safe state management
_pipeline_context: ContextVar[PipelineContext | None] = ContextVar(
    "pipeline_context", default=None
)
_interceptor_context: ContextVar[InterceptorContext | None] = ContextVar(
    "interceptor_context", default=None
)


def next() -> None:
    """
    Signal that pipeline execution should continue to the next handler.

    This function MUST be called from within a pipeline handler to pass
    control to the next lower-priority handler. If not called, the pipeline
    chain breaks and no further handlers execute.

    Raises:
        UtilsError: If called outside of a pipeline context

    Example:
        @lumia.pipe.on('msg', priv=100)
        def filter(content: Box):
            if should_process(content):
                lumia.utils.next()  # Continue to next handler
            # Otherwise, chain breaks here
    """
    ctx = _pipeline_context.get()
    if ctx is None:
        raise UtilsError(
            "next() called outside of pipeline context. "
            "This function can only be called from within a pipeline handler."
        )
    ctx.should_continue = True


def intercept() -> None:
    """
    Block an event from reaching any consumers.

    This function MUST be called from within an interceptor to prevent
    the event from being dispatched to any Event consumers or EventChain
    handlers. If not called, the event proceeds normally.

    Raises:
        UtilsError: If called outside of an interceptor context

    Example:
        @lumia.event.interceptor('bus.adapters.qq.find_old.*', priv=9999)
        def stop_old(src: str, content: Box):
            if str(content.into()) < '1.0.29':
                lumia.utils.intercept()  # Block this event
    """
    ctx = _interceptor_context.get()
    if ctx is None:
        raise UtilsError(
            "intercept() called outside of interceptor context. "
            "This function can only be called from within an interceptor."
        )
    ctx.should_intercept = True


# Internal API for Event Bus and Pipeline to manage contexts
def _set_pipeline_context(ctx: PipelineContext | None) -> None:
    """Set the current pipeline context (internal use only)."""
    _pipeline_context.set(ctx)


def _get_pipeline_context() -> PipelineContext | None:
    """Get the current pipeline context (internal use only)."""
    return _pipeline_context.get()


def _set_interceptor_context(ctx: InterceptorContext | None) -> None:
    """Set the current interceptor context (internal use only)."""
    _interceptor_context.set(ctx)


def _get_interceptor_context() -> InterceptorContext | None:
    """Get the current interceptor context (internal use only)."""
    return _interceptor_context.get()
