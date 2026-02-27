"""
TOML File I/O Handler.

This module provides TOML parsing and writing with comment preservation.

Key features:
- Parse TOML files using tomllib (Python 3.11+)
- Write TOML files using tomlkit (preserves comments and formatting)
- Generate TOML from schema with descriptive comments
"""

import tomllib
from pathlib import Path
from typing import Any

import tomlkit


class TOMLError(Exception):
    """Base exception for TOML-related errors."""

    pass


def read_toml(file_path: Path) -> dict[str, Any]:
    """
    Read and parse a TOML file.

    Args:
        file_path: Path to the TOML file

    Returns:
        Parsed TOML data as dictionary

    Raises:
        TOMLError: If file cannot be read or parsed
    """
    try:
        with open(file_path, "rb") as f:
            return tomllib.load(f)
    except FileNotFoundError as e:
        raise TOMLError(f"TOML file not found: {file_path}") from e
    except tomllib.TOMLDecodeError as e:
        raise TOMLError(f"Failed to parse TOML file {file_path}: {e}") from e
    except Exception as e:
        raise TOMLError(f"Failed to read TOML file {file_path}: {e}") from e


def write_toml(file_path: Path, data: dict[str, Any]) -> None:
    """
    Write data to a TOML file using tomlkit (preserves formatting).

    Args:
        file_path: Path to the TOML file
        data: Data to write

    Raises:
        TOMLError: If file cannot be written
    """
    try:
        # Ensure parent directory exists
        file_path.parent.mkdir(parents=True, exist_ok=True)

        with open(file_path, "w", encoding="utf-8") as f:
            tomlkit.dump(data, f)
    except Exception as e:
        raise TOMLError(f"Failed to write TOML file {file_path}: {e}") from e


def generate_toml_from_schema(
    plugin_name: str, schema: dict[str, Any], config_data: dict[str, Any]
) -> str:
    """
    Generate TOML content from schema with descriptive comments.

    Args:
        plugin_name: Name of the plugin (used as section header)
        schema: Schema dictionary (field_name -> ConfigField)
        config_data: Configuration data (field_name -> value)

    Returns:
        TOML string with comments
    """
    from lumia.config.schema import ConfigField

    doc = tomlkit.document()

    # Add plugin section with comment
    doc.add(tomlkit.comment(f"Configuration for {plugin_name}"))
    doc.add(tomlkit.nl())

    # Create plugin table
    plugin_table = tomlkit.table()

    for field_name, field in schema.items():
        # Add field description as comment
        if field.description:
            plugin_table.add(tomlkit.comment(field.description))

        # Add constraint information as comment
        constraints = []
        if isinstance(field, ConfigField):
            if field.min is not None:
                constraints.append(f"min: {field.min}")
            if field.max is not None:
                constraints.append(f"max: {field.max}")
            if field.choices is not None:
                constraints.append(f"choices: {field.choices}")

        if constraints:
            plugin_table.add(tomlkit.comment(f"Constraints: {', '.join(constraints)}"))

        # Add the field value
        value = config_data.get(field_name, field.default)
        plugin_table.add(field_name, value)
        plugin_table.add(tomlkit.nl())

    doc.add(plugin_name, plugin_table)

    return tomlkit.dumps(doc)

