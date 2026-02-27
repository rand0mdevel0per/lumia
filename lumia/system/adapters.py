"""
Adapter System API.

This module provides system APIs for adapter plugins.

Key features:
- Adapter registration
- Heartbeat mechanism
- Adapter state tracking
"""

import threading
import time
from dataclasses import dataclass
from typing import Any


class AdapterError(Exception):
    """Base exception for adapter-related errors."""

    pass


@dataclass
class AdapterInfo:
    """
    Information about a registered adapter.

    Attributes:
        adapter_id: Unique adapter identifier
        adapter_version: Adapter version
        registered_at: Registration timestamp
        last_heartbeat: Last heartbeat timestamp
        metadata: Additional adapter metadata
    """

    adapter_id: str
    adapter_version: str
    registered_at: float
    last_heartbeat: float
    metadata: dict[str, Any]


class AdapterRegistry:
    """
    Registry for adapter plugins.

    Manages adapter registration and heartbeat tracking.
    """

    def __init__(self):
        """Initialize AdapterRegistry."""
        self._adapters: dict[str, AdapterInfo] = {}
        self._lock = threading.Lock()

    def register(
        self,
        adapter_id: str,
        adapter_version: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """
        Register an adapter.

        Args:
            adapter_id: Unique adapter identifier
            adapter_version: Adapter version
            metadata: Additional adapter metadata

        Raises:
            AdapterError: If adapter is already registered
        """
        with self._lock:
            if adapter_id in self._adapters:
                raise AdapterError(f"Adapter already registered: {adapter_id}")

            now = time.time()
            self._adapters[adapter_id] = AdapterInfo(
                adapter_id=adapter_id,
                adapter_version=adapter_version,
                registered_at=now,
                last_heartbeat=now,
                metadata=metadata or {},
            )

    def heartbeat(self, adapter_id: str, adapter_version: str) -> None:
        """
        Update adapter heartbeat.

        Args:
            adapter_id: Adapter identifier
            adapter_version: Adapter version

        Raises:
            AdapterError: If adapter not registered or version mismatch
        """
        with self._lock:
            if adapter_id not in self._adapters:
                raise AdapterError(f"Adapter not registered: {adapter_id}")

            adapter_info = self._adapters[adapter_id]

            # Check version match
            if adapter_info.adapter_version != adapter_version:
                raise AdapterError(
                    f"Adapter version mismatch: expected {adapter_info.adapter_version}, "
                    f"got {adapter_version}"
                )

            # Update heartbeat timestamp
            adapter_info.last_heartbeat = time.time()

    def unregister(self, adapter_id: str) -> None:
        """
        Unregister an adapter.

        Args:
            adapter_id: Adapter identifier

        Raises:
            AdapterError: If adapter not registered
        """
        with self._lock:
            if adapter_id not in self._adapters:
                raise AdapterError(f"Adapter not registered: {adapter_id}")

            del self._adapters[adapter_id]

    def get_adapter(self, adapter_id: str) -> AdapterInfo | None:
        """
        Get adapter information.

        Args:
            adapter_id: Adapter identifier

        Returns:
            AdapterInfo object, or None if not registered
        """
        with self._lock:
            return self._adapters.get(adapter_id)

    def list_adapters(self) -> list[AdapterInfo]:
        """
        List all registered adapters.

        Returns:
            List of AdapterInfo objects
        """
        with self._lock:
            return list(self._adapters.values())

    def is_registered(self, adapter_id: str) -> bool:
        """
        Check if adapter is registered.

        Args:
            adapter_id: Adapter identifier

        Returns:
            True if adapter is registered
        """
        with self._lock:
            return adapter_id in self._adapters

    def get_active_adapters(self, timeout: float = 60.0) -> list[str]:
        """
        Get list of active adapters (heartbeat within timeout).

        Args:
            timeout: Heartbeat timeout in seconds (default: 60)

        Returns:
            List of active adapter IDs
        """
        now = time.time()
        with self._lock:
            return [
                adapter_id
                for adapter_id, info in self._adapters.items()
                if (now - info.last_heartbeat) < timeout
            ]


# Global adapter registry
_adapter_registry = AdapterRegistry()


def reg(
    adapter_id: str, adapter_version: str, metadata: dict[str, Any] | None = None
) -> None:
    """
    Register an adapter (public API).

    Args:
        adapter_id: Unique adapter identifier
        adapter_version: Adapter version
        metadata: Additional adapter metadata

    Raises:
        AdapterError: If adapter is already registered
    """
    _adapter_registry.register(adapter_id, adapter_version, metadata)


def heartbeat(adapter_id: str, adapter_version: str) -> None:
    """
    Update adapter heartbeat (public API).

    Args:
        adapter_id: Adapter identifier
        adapter_version: Adapter version

    Raises:
        AdapterError: If adapter not registered or version mismatch
    """
    _adapter_registry.heartbeat(adapter_id, adapter_version)


def get_registry() -> AdapterRegistry:
    """
    Get the global adapter registry.

    Returns:
        AdapterRegistry instance
    """
    return _adapter_registry
