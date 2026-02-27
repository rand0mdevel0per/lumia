"""
Dynamic Plugin Loader.

This module provides dynamic loading of plugin modules.

Key features:
- importlib integration for dynamic loading
- Module caching
- Reload support for development
- .pyc support for closed-source plugins
"""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

from lumia.plugin.manifest import Manifest


class LoaderError(Exception):
    """Base exception for loader-related errors."""

    pass


# Module cache: plugin_name -> module
_module_cache: dict[str, ModuleType] = {}


def load_plugin_module(plugin_dir: Path, manifest: Manifest) -> ModuleType:
    """
    Load a plugin module dynamically.

    Args:
        plugin_dir: Plugin directory path
        manifest: Plugin manifest

    Returns:
        Loaded module

    Raises:
        LoaderError: If loading fails
    """
    plugin_name = manifest.name
    entry_point = plugin_dir / manifest.main

    # Check if entry point exists
    if not entry_point.exists():
        raise LoaderError(f"Entry point not found: {entry_point}")

    # Check if module is already cached
    if plugin_name in _module_cache:
        return _module_cache[plugin_name]

    try:
        # Create module spec
        module_name = f"lumia_plugin_{plugin_name}"
        spec = importlib.util.spec_from_file_location(module_name, entry_point)

        if spec is None or spec.loader is None:
            raise LoaderError(f"Failed to create module spec for {entry_point}")

        # Create module from spec
        module = importlib.util.module_from_spec(spec)

        # Add to sys.modules before execution
        sys.modules[module_name] = module

        # Execute module
        spec.loader.exec_module(module)

        # Cache module
        _module_cache[plugin_name] = module

        return module

    except Exception as e:
        # Clean up sys.modules on failure
        module_name = f"lumia_plugin_{plugin_name}"
        if module_name in sys.modules:
            del sys.modules[module_name]

        raise LoaderError(f"Failed to load plugin module: {e}") from e


def reload_plugin_module(plugin_dir: Path, manifest: Manifest) -> ModuleType:
    """
    Reload a plugin module (for development).

    Args:
        plugin_dir: Plugin directory path
        manifest: Plugin manifest

    Returns:
        Reloaded module

    Raises:
        LoaderError: If reloading fails
    """
    plugin_name = manifest.name

    # Unload existing module
    unload_plugin_module(plugin_name)

    # Load fresh module
    return load_plugin_module(plugin_dir, manifest)


def unload_plugin_module(plugin_name: str) -> None:
    """
    Unload a plugin module and clear from cache.

    Args:
        plugin_name: Name of plugin to unload
    """
    # Remove from cache
    if plugin_name in _module_cache:
        del _module_cache[plugin_name]

    # Remove from sys.modules
    module_name = f"lumia_plugin_{plugin_name}"
    if module_name in sys.modules:
        del sys.modules[module_name]


def is_module_cached(plugin_name: str) -> bool:
    """
    Check if plugin module is cached.

    Args:
        plugin_name: Name of plugin

    Returns:
        True if module is cached
    """
    return plugin_name in _module_cache


def get_cached_module(plugin_name: str) -> ModuleType | None:
    """
    Get cached plugin module.

    Args:
        plugin_name: Name of plugin

    Returns:
        Cached module, or None if not cached
    """
    return _module_cache.get(plugin_name)


def clear_cache() -> None:
    """Clear all cached plugin modules."""
    for plugin_name in list(_module_cache.keys()):
        unload_plugin_module(plugin_name)
