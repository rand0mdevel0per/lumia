"""
Plugin Manager.

This module provides plugin lifecycle management.

Key features:
- Plugin registry and state tracking
- Load/unload operations
- Dependency resolution with topological sort
- Unique domain conflict detection
- Version constraint checking
"""

import threading
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from lumia.plugin.manifest import Manifest, parse_manifest


class PluginError(Exception):
    """Base exception for plugin-related errors."""

    pass


class DependencyError(PluginError):
    """Raised when dependency resolution fails."""

    pass


class ConflictError(PluginError):
    """Raised when unique domain conflicts are detected."""

    pass


class PluginState(Enum):
    """Plugin state enumeration."""

    UNLOADED = "unloaded"
    LOADING = "loading"
    LOADED = "loaded"
    UNLOADING = "unloading"
    ERROR = "error"


@dataclass
class PluginInfo:
    """
    Information about a plugin.

    Attributes:
        name: Plugin name
        version: Plugin version
        path: Plugin directory path
        manifest: Parsed manifest
        state: Current plugin state
        module: Loaded module (None if not loaded)
        error: Error message if state is ERROR
    """

    name: str
    version: str
    path: Path
    manifest: Manifest
    state: PluginState = PluginState.UNLOADED
    module: Any = None
    error: str | None = None


class PluginManager:
    """
    Plugin lifecycle manager.

    Manages plugin loading, unloading, dependency resolution, and conflict detection.
    """

    def __init__(self, plugins_dir: Path):
        """
        Initialize PluginManager.

        Args:
            plugins_dir: Directory containing plugins
        """
        self.plugins_dir = plugins_dir
        self._plugins: dict[str, PluginInfo] = {}
        self._domain_map: dict[str, str] = {}  # domain -> plugin_name
        self._lock = threading.Lock()

        # Ensure plugins directory exists
        self.plugins_dir.mkdir(parents=True, exist_ok=True)

    def discover_plugins(self) -> list[str]:
        """
        Discover all plugins in plugins directory.

        Returns:
            List of discovered plugin names

        Raises:
            PluginError: If discovery fails
        """
        discovered = []

        try:
            for plugin_dir in self.plugins_dir.iterdir():
                if not plugin_dir.is_dir():
                    continue

                manifest_path = plugin_dir / "manifest.json"
                if not manifest_path.exists():
                    continue

                try:
                    manifest = parse_manifest(manifest_path)
                    plugin_info = PluginInfo(
                        name=manifest.name,
                        version=manifest.version,
                        path=plugin_dir,
                        manifest=manifest,
                    )

                    with self._lock:
                        self._plugins[manifest.name] = plugin_info

                    discovered.append(manifest.name)

                except Exception as e:
                    # Log error but continue discovery
                    print(f"Warning: Failed to parse manifest for {plugin_dir.name}: {e}")

            return discovered

        except Exception as e:
            raise PluginError(f"Failed to discover plugins: {e}") from e

    def load_plugin(self, plugin_name: str) -> None:
        """
        Load a plugin and its dependencies.

        Args:
            plugin_name: Name of plugin to load

        Raises:
            PluginError: If plugin not found or loading fails
            DependencyError: If dependency resolution fails
            ConflictError: If unique domain conflicts detected
        """
        with self._lock:
            if plugin_name not in self._plugins:
                raise PluginError(f"Plugin not found: {plugin_name}")

            plugin_info = self._plugins[plugin_name]

            # Check if already loaded
            if plugin_info.state == PluginState.LOADED:
                return

            # Check if in error state
            if plugin_info.state == PluginState.ERROR:
                raise PluginError(
                    f"Plugin {plugin_name} is in error state: {plugin_info.error}"
                )

            # Check if currently loading (circular dependency)
            if plugin_info.state == PluginState.LOADING:
                raise DependencyError(
                    f"Circular dependency detected involving {plugin_name}"
                )

        # Resolve dependencies and get load order
        load_order = self._resolve_dependencies(plugin_name)

        # Check for unique domain conflicts
        self._check_domain_conflicts(load_order)

        # Load plugins in order
        for name in load_order:
            self._load_single_plugin(name)

    def _load_single_plugin(self, plugin_name: str) -> None:
        """
        Load a single plugin without dependency resolution.

        Args:
            plugin_name: Name of plugin to load

        Raises:
            PluginError: If loading fails
        """
        with self._lock:
            plugin_info = self._plugins[plugin_name]

            # Skip if already loaded
            if plugin_info.state == PluginState.LOADED:
                return

            # Mark as loading
            plugin_info.state = PluginState.LOADING

        try:
            # Import the plugin module
            from lumia.plugin.loader import load_plugin_module

            module = load_plugin_module(plugin_info.path, plugin_info.manifest)

            with self._lock:
                plugin_info.module = module
                plugin_info.state = PluginState.LOADED

                # Register unique domains
                for domain in plugin_info.manifest.unique:
                    self._domain_map[domain] = plugin_name

        except Exception as e:
            with self._lock:
                plugin_info.state = PluginState.ERROR
                plugin_info.error = str(e)
            raise PluginError(f"Failed to load plugin {plugin_name}: {e}") from e

    def unload_plugin(self, plugin_name: str) -> None:
        """
        Unload a plugin.

        Args:
            plugin_name: Name of plugin to unload

        Raises:
            PluginError: If plugin not found or unloading fails
        """
        with self._lock:
            if plugin_name not in self._plugins:
                raise PluginError(f"Plugin not found: {plugin_name}")

            plugin_info = self._plugins[plugin_name]

            # Check if already unloaded
            if plugin_info.state == PluginState.UNLOADED:
                return

            # Mark as unloading
            plugin_info.state = PluginState.UNLOADING

        try:
            # Unregister unique domains
            with self._lock:
                for domain in plugin_info.manifest.unique:
                    if domain in self._domain_map:
                        del self._domain_map[domain]

                # Clear module reference
                plugin_info.module = None
                plugin_info.state = PluginState.UNLOADED

        except Exception as e:
            with self._lock:
                plugin_info.state = PluginState.ERROR
                plugin_info.error = str(e)
            raise PluginError(f"Failed to unload plugin {plugin_name}: {e}") from e

    def _resolve_dependencies(self, plugin_name: str) -> list[str]:
        """
        Resolve plugin dependencies using topological sort.

        Args:
            plugin_name: Name of plugin to resolve dependencies for

        Returns:
            List of plugin names in load order (dependencies first)

        Raises:
            DependencyError: If dependency resolution fails
        """
        # Build dependency graph
        graph: dict[str, list[str]] = {}
        in_degree: dict[str, int] = {}

        # Start with requested plugin
        to_process = [plugin_name]
        processed = set()

        while to_process:
            current = to_process.pop(0)

            if current in processed:
                continue

            processed.add(current)

            # Check if plugin exists
            if current not in self._plugins:
                raise DependencyError(f"Dependency not found: {current}")

            plugin_info = self._plugins[current]

            # Initialize graph nodes
            if current not in graph:
                graph[current] = []
                in_degree[current] = 0

            # Process dependencies
            for dep_name, constraint in plugin_info.manifest.dependencies.items():
                # Check if dependency exists
                if dep_name not in self._plugins:
                    raise DependencyError(
                        f"Plugin {current} depends on {dep_name}, but it is not installed"
                    )

                dep_info = self._plugins[dep_name]

                # Check version constraint
                if not constraint.matches(dep_info.version):
                    raise DependencyError(
                        f"Plugin {current} requires {dep_name} {constraint.operator}{constraint.version}, "
                        f"but version {dep_info.version} is installed"
                    )

                # Add edge: current depends on dep_name
                if dep_name not in graph:
                    graph[dep_name] = []
                    in_degree[dep_name] = 0

                graph[dep_name].append(current)
                in_degree[current] = in_degree.get(current, 0) + 1

                # Add dependency to processing queue
                to_process.append(dep_name)

        # Topological sort using Kahn's algorithm
        queue = [node for node in graph if in_degree[node] == 0]
        result = []

        while queue:
            # Sort by name for deterministic order
            queue.sort()
            node = queue.pop(0)
            result.append(node)

            # Process dependents
            for dependent in graph[node]:
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)

        # Check for cycles
        if len(result) != len(graph):
            raise DependencyError("Circular dependency detected")

        return result

    def _check_domain_conflicts(self, plugin_names: list[str]) -> None:
        """
        Check for unique domain conflicts among plugins.

        Args:
            plugin_names: List of plugin names to check

        Raises:
            ConflictError: If domain conflicts detected
        """
        # Build temporary domain map for plugins to be loaded
        temp_domain_map: dict[str, str] = {}

        for plugin_name in plugin_names:
            plugin_info = self._plugins[plugin_name]

            # Skip if already loaded (domains already registered)
            if plugin_info.state == PluginState.LOADED:
                continue

            for domain in plugin_info.manifest.unique:
                # Check against existing domains
                if domain in self._domain_map:
                    existing_plugin = self._domain_map[domain]
                    raise ConflictError(
                        f"Domain conflict: '{domain}' is already claimed by plugin '{existing_plugin}'"
                    )

                # Check against other plugins being loaded
                if domain in temp_domain_map:
                    conflicting_plugin = temp_domain_map[domain]
                    raise ConflictError(
                        f"Domain conflict: '{domain}' is claimed by both '{plugin_name}' and '{conflicting_plugin}'"
                    )

                temp_domain_map[domain] = plugin_name

    def get_plugin_info(self, plugin_name: str) -> PluginInfo | None:
        """
        Get plugin information.

        Args:
            plugin_name: Name of plugin

        Returns:
            PluginInfo object, or None if not found
        """
        with self._lock:
            return self._plugins.get(plugin_name)

    def list_plugins(self) -> list[PluginInfo]:
        """
        List all discovered plugins.

        Returns:
            List of PluginInfo objects
        """
        with self._lock:
            return list(self._plugins.values())

    def is_loaded(self, plugin_name: str) -> bool:
        """
        Check if plugin is loaded.

        Args:
            plugin_name: Name of plugin

        Returns:
            True if plugin is loaded
        """
        with self._lock:
            if plugin_name not in self._plugins:
                return False
            return self._plugins[plugin_name].state == PluginState.LOADED

    def get_loaded_plugins(self) -> list[str]:
        """
        Get list of loaded plugin names.

        Returns:
            List of loaded plugin names
        """
        with self._lock:
            return [
                name
                for name, info in self._plugins.items()
                if info.state == PluginState.LOADED
            ]
