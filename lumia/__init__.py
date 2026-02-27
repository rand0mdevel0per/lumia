"""
Lumia Framework - Event-driven, plugin-first framework for LLM-powered IM bots.

This is the main package that exports the public API for the Lumia framework.
"""

__version__ = "0.1.0"

# Import core components
from lumia.core.box import Box
from lumia.core import event_bus, pipeline, utils as utils_module

# Create namespace objects for clean API using types.SimpleNamespace
from types import SimpleNamespace

# Event bus API namespace
event = SimpleNamespace(
    consumer=event_bus.consumer,
    consumer_re=event_bus.consumer_re,
    interceptor=event_bus.interceptor,
    interceptor_re=event_bus.interceptor_re,
    start=event_bus.start,
    start_chain=event_bus.start_chain,
)

# Pipeline API namespace
pipe = SimpleNamespace(
    on=pipeline.on,
    on_re=pipeline.on_re,
    start=pipeline.start,
)

# Utils API namespace
utils = SimpleNamespace(
    next=utils_module.next,
    intercept=utils_module.intercept,
)

__all__ = [
    "__version__",
    "Box",
    "event",
    "pipe",
    "utils",
]
