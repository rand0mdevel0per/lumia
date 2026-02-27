"""
Lumia Configuration System - TOML-based configuration management.

This module provides:
- Schema declaration and validation
- Runtime typed access with auto-flush
- Config file generation from schemas

Example usage:
    import lumia.config

    # Declare schema
    lumia.config.declare('my-plugin', {
        'threshold': lumia.config.field(float, 0.5, "Detection threshold"),
        'max_retries': lumia.config.field(int, 3, "Maximum retry attempts", min=1, max=10),
    })

    # Access config
    cfg = lumia.config.get('my-plugin')
    print(cfg.threshold)  # Read
    cfg.threshold = 0.7   # Write (auto-flushes)
"""

from pathlib import Path
from typing import Any

from lumia.config.runtime import ConfigProxy
from lumia.config.schema import ConfigField

# Global registry for plugin schemas
_schemas: dict[str, dict[str, ConfigField]] = {}

# Default config file path
_config_file = Path("config/lumia.toml")


class ConfigError(Exception):
    """Base exception for config API errors."""

    pass


def field(
    type_: type,
    default: Any,
    description: str = "",
    min: Any = None,
    max: Any = None,
    choices: list[Any] | None = None,
) -> ConfigField:
    """
    Helper function to create a ConfigField.

    Args:
        type_: The expected type of the field value
        default: Default value for the field
        description: Human-readable description
        min: Minimum value (for numbers) or minimum length (for strings/lists)
        max: Maximum value (for numbers) or maximum length (for strings/lists)
        choices: List of allowed values (optional)

    Returns:
        ConfigField instance

    Example:
        field(int, 42, "The answer", min=0, max=100)
    """
    return ConfigField(
        type_=type_,
        default=default,
        description=description,
        min=min,
        max=max,
        choices=choices,
    )


def declare(plugin_name: str, schema: dict[str, ConfigField]) -> None:
    """
    Declare configuration schema for a plugin.

    Args:
        plugin_name: Name of the plugin
        schema: Schema dictionary (field_name -> ConfigField)

    Raises:
        ConfigError: If plugin already has a schema declared
    """
    if plugin_name in _schemas:
        raise ConfigError(f"Schema for plugin '{plugin_name}' already declared")

    _schemas[plugin_name] = schema


def get(plugin_name: str) -> ConfigProxy:
    """
    Get runtime configuration accessor for a plugin.

    Args:
        plugin_name: Name of the plugin

    Returns:
        ConfigProxy instance for runtime access

    Raises:
        ConfigError: If plugin schema not declared
    """
    if plugin_name not in _schemas:
        raise ConfigError(
            f"Schema for plugin '{plugin_name}' not declared. Call declare() first."
        )

    schema = _schemas[plugin_name]
    return ConfigProxy(plugin_name, schema, _config_file)


__all__ = ["field", "declare", "get", "ConfigError"]
