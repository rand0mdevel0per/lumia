"""
Runtime Configuration Access.

This module provides runtime access to configuration with auto-flush on write.

Key features:
- ConfigProxy class with attribute-based access
- Auto-flush to TOML file on attribute write
- Thread-safe file writes with locking
- Validation on write
"""

import threading
from pathlib import Path
from typing import Any

from lumia.config.schema import ConfigField, validate_config
from lumia.config.toml_handler import read_toml, write_toml


class RuntimeError(Exception):
    """Base exception for runtime config errors."""

    pass


class ConfigProxy:
    """
    Proxy object for runtime configuration access.

    Provides attribute-based access to configuration values with auto-flush
    on write. All writes are validated against the schema and immediately
    flushed to the TOML file.

    Example:
        cfg = ConfigProxy('my-plugin', schema, config_file)
        value = cfg.my_field  # Read
        cfg.my_field = 42     # Write (auto-flushes to file)
    """

    def __init__(
        self,
        plugin_name: str,
        schema: dict[str, ConfigField],
        config_file: Path,
    ):
        """
        Initialize ConfigProxy.

        Args:
            plugin_name: Name of the plugin
            schema: Schema dictionary (field_name -> ConfigField)
            config_file: Path to the TOML config file
        """
        # Use object.__setattr__ to avoid triggering our custom __setattr__
        object.__setattr__(self, "_plugin_name", plugin_name)
        object.__setattr__(self, "_schema", schema)
        object.__setattr__(self, "_config_file", config_file)
        object.__setattr__(self, "_lock", threading.Lock())
        object.__setattr__(self, "_cache", {})

        # Load initial config
        self._load_config()

    def _load_config(self) -> None:
        """Load configuration from file."""
        try:
            if self._config_file.exists():
                data = read_toml(self._config_file)
                if self._plugin_name in data:
                    plugin_config = data[self._plugin_name]
                    # Validate against schema
                    validate_config(plugin_config, self._schema)
                    object.__setattr__(self, "_cache", plugin_config)
                else:
                    # Plugin section doesn't exist, use defaults
                    object.__setattr__(
                        self,
                        "_cache",
                        {name: field.default for name, field in self._schema.items()},
                    )
            else:
                # File doesn't exist, use defaults
                object.__setattr__(
                    self,
                    "_cache",
                    {name: field.default for name, field in self._schema.items()},
                )
        except Exception as e:
            raise RuntimeError(f"Failed to load config: {e}") from e

    def __getattr__(self, name: str) -> Any:
        """
        Get configuration value by attribute access.

        Args:
            name: Field name

        Returns:
            Field value

        Raises:
            AttributeError: If field doesn't exist in schema
        """
        if name.startswith("_"):
            # Internal attributes
            return object.__getattribute__(self, name)

        if name not in self._schema:
            raise AttributeError(
                f"Configuration field '{name}' not found in schema for {self._plugin_name}"
            )

        return self._cache[name]

    def __setattr__(self, name: str, value: Any) -> None:
        """
        Set configuration value by attribute access with auto-flush.

        Args:
            name: Field name
            value: New value

        Raises:
            AttributeError: If field doesn't exist in schema
            ValidationError: If value fails validation
        """
        if name.startswith("_"):
            # Internal attributes
            object.__setattr__(self, name, value)
            return

        if name not in self._schema:
            raise AttributeError(
                f"Configuration field '{name}' not found in schema for {self._plugin_name}"
            )

        # Validate value against schema
        field = self._schema[name]
        field.validate(value)

        # Update cache
        with self._lock:
            self._cache[name] = value
            # Auto-flush to file
            self._flush()

    def _flush(self) -> None:
        """
        Flush current configuration to TOML file.

        This method is called automatically on every write.
        Thread-safe with file locking.
        """
        try:
            # Read existing file content
            data = read_toml(self._config_file) if self._config_file.exists() else {}

            # Update plugin section
            data[self._plugin_name] = self._cache.copy()

            # Write back to file
            write_toml(self._config_file, data)
        except Exception as e:
            raise RuntimeError(f"Failed to flush config to file: {e}") from e

    def __repr__(self) -> str:
        """String representation of ConfigProxy."""
        return f"ConfigProxy({self._plugin_name}, {self._cache})"
