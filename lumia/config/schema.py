"""
Configuration Schema System.

This module provides schema declaration and validation for plugin configurations.

Key features:
- Type-safe field definitions with constraints
- Validation of values against schema
- Support for basic types (int, float, str, bool, list, dict)
"""

from dataclasses import dataclass
from typing import Any


class SchemaError(Exception):
    """Base exception for schema-related errors."""

    pass


class ValidationError(SchemaError):
    """Raised when value validation fails."""

    pass


@dataclass
class ConfigField:
    """
    Represents a configuration field with type and constraints.

    Attributes:
        type_: The expected type of the field value
        default: Default value for the field
        description: Human-readable description
        min: Minimum value (for numbers) or minimum length (for strings/lists)
        max: Maximum value (for numbers) or maximum length (for strings/lists)
        choices: List of allowed values (optional)
    """

    type_: type
    default: Any
    description: str = ""
    min: Any = None
    max: Any = None
    choices: list[Any] | None = None

    def __post_init__(self):
        """Validate field definition."""
        # Validate that default value matches type
        if not isinstance(self.default, self.type_):
            raise SchemaError(
                f"Default value {self.default!r} does not match type {self.type_.__name__}"
            )

        # Validate constraints
        if (self.min is not None or self.max is not None) and self.type_ not in (
            int,
            float,
            str,
            list,
        ):
            raise SchemaError(
                f"min/max constraints only supported for int, float, str, list. Got {self.type_.__name__}"
            )

        # Validate choices
        if self.choices is not None:
            if not isinstance(self.choices, list):
                raise SchemaError("choices must be a list")
            for choice in self.choices:
                if not isinstance(choice, self.type_):
                    raise SchemaError(
                        f"Choice {choice!r} does not match type {self.type_.__name__}"
                    )
            # Validate default is in choices
            if self.default not in self.choices:
                raise SchemaError(
                    f"Default value {self.default!r} not in choices {self.choices}"
                )

    def validate(self, value: Any) -> None:
        """
        Validate a value against this field's constraints.

        Args:
            value: The value to validate

        Raises:
            ValidationError: If validation fails
        """
        # Type check
        if not isinstance(value, self.type_):
            raise ValidationError(
                f"Expected type {self.type_.__name__}, got {type(value).__name__}"
            )

        # Choices constraint
        if self.choices is not None and value not in self.choices:
            raise ValidationError(
                f"Value {value!r} not in allowed choices {self.choices}"
            )

        # Min/max constraints for numbers
        if self.type_ in (int, float):
            if self.min is not None and value < self.min:
                raise ValidationError(f"Value {value} is less than minimum {self.min}")
            if self.max is not None and value > self.max:
                raise ValidationError(
                    f"Value {value} is greater than maximum {self.max}"
                )

        # Min/max constraints for strings (length)
        if self.type_ is str:
            if self.min is not None and len(value) < self.min:
                raise ValidationError(
                    f"String length {len(value)} is less than minimum {self.min}"
                )
            if self.max is not None and len(value) > self.max:
                raise ValidationError(
                    f"String length {len(value)} is greater than maximum {self.max}"
                )

        # Min/max constraints for lists (length)
        if self.type_ is list:
            if self.min is not None and len(value) < self.min:
                raise ValidationError(
                    f"List length {len(value)} is less than minimum {self.min}"
                )
            if self.max is not None and len(value) > self.max:
                raise ValidationError(
                    f"List length {len(value)} is greater than maximum {self.max}"
                )


def validate_config(config: dict[str, Any], schema: dict[str, ConfigField]) -> None:
    """
    Validate a configuration dictionary against a schema.

    Args:
        config: The configuration dictionary to validate
        schema: The schema dictionary (field_name -> ConfigField)

    Raises:
        ValidationError: If validation fails
    """
    # Check for unknown fields
    for key in config:
        if key not in schema:
            raise ValidationError(f"Unknown configuration field: {key}")

    # Validate each field
    for field_name, field in schema.items():
        if field_name not in config:
            raise ValidationError(f"Missing required field: {field_name}")

        try:
            field.validate(config[field_name])
        except ValidationError as e:
            raise ValidationError(f"Field '{field_name}': {e}") from e


def generate_default_config(schema: dict[str, ConfigField]) -> dict[str, Any]:
    """
    Generate a default configuration from a schema.

    Args:
        schema: The schema dictionary (field_name -> ConfigField)

    Returns:
        A dictionary with default values for all fields
    """
    return {field_name: field.default for field_name, field in schema.items()}

