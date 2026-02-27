"""
Plugin Manifest System.

This module provides manifest parsing and validation for plugins.

Key features:
- JSON schema validation for manifest.json
- Version constraint parsing (>=, ==, ~=)
- Dependency resolution support
- Unique domain validation
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class ManifestError(Exception):
    """Base exception for manifest-related errors."""

    pass


class ValidationError(ManifestError):
    """Raised when manifest validation fails."""

    pass


@dataclass
class VersionConstraint:
    """
    Represents a version constraint for dependencies.

    Attributes:
        operator: Constraint operator (>=, ==, ~=)
        version: Version string (e.g., "1.0.0")
    """

    operator: str
    version: str

    def matches(self, version: str) -> bool:
        """
        Check if a version satisfies this constraint.

        Args:
            version: Version string to check

        Returns:
            True if version satisfies constraint
        """
        if self.operator == "==":
            return version == self.version
        elif self.operator == ">=":
            return self._compare_versions(version, self.version) >= 0
        elif self.operator == "~=":
            # Compatible release: ~=1.2.3 matches >=1.2.3, <1.3.0
            return self._is_compatible_release(version, self.version)
        else:
            raise ValidationError(f"Unknown version operator: {self.operator}")

    def _compare_versions(self, v1: str, v2: str) -> int:
        """
        Compare two version strings.

        Args:
            v1: First version
            v2: Second version

        Returns:
            -1 if v1 < v2, 0 if v1 == v2, 1 if v1 > v2
        """
        parts1 = [int(x) for x in v1.split(".")]
        parts2 = [int(x) for x in v2.split(".")]

        # Pad shorter version with zeros
        max_len = max(len(parts1), len(parts2))
        parts1.extend([0] * (max_len - len(parts1)))
        parts2.extend([0] * (max_len - len(parts2)))

        for p1, p2 in zip(parts1, parts2, strict=True):
            if p1 < p2:
                return -1
            elif p1 > p2:
                return 1
        return 0

    def _is_compatible_release(self, version: str, base: str) -> bool:
        """
        Check if version is a compatible release of base.

        ~=1.2.3 matches >=1.2.3, <1.3.0

        Args:
            version: Version to check
            base: Base version

        Returns:
            True if compatible
        """
        if self._compare_versions(version, base) < 0:
            return False

        # Get major.minor from base
        base_parts = base.split(".")
        if len(base_parts) < 2:
            raise ValidationError(f"Invalid version for ~= operator: {base}")

        # Increment minor version for upper bound
        upper_parts = base_parts[:-1]
        upper_parts[-1] = str(int(upper_parts[-1]) + 1)
        upper_bound = ".".join(upper_parts) + ".0"

        return self._compare_versions(version, upper_bound) < 0


@dataclass
class Manifest:
    """
    Represents a plugin manifest.

    Attributes:
        name: Plugin name (unique identifier)
        version: Plugin version
        main: Entry point file path
        description: Plugin description
        author: Plugin author
        dependencies: Dict of plugin_name -> version_constraint
        unique: List of unique domain identifiers
        raw_data: Raw manifest data
    """

    name: str
    version: str
    main: str
    description: str
    author: str
    dependencies: dict[str, VersionConstraint]
    unique: list[str]
    raw_data: dict[str, Any]


def parse_version_constraint(constraint_str: str) -> VersionConstraint:
    """
    Parse a version constraint string.

    Args:
        constraint_str: Constraint string (e.g., ">=1.0.0", "==2.1.0", "~=1.2.3")

    Returns:
        VersionConstraint object

    Raises:
        ValidationError: If constraint string is invalid
    """
    # Match operator and version
    match = re.match(r"^(>=|==|~=)(\d+\.\d+\.\d+)$", constraint_str.strip())
    if not match:
        raise ValidationError(
            f"Invalid version constraint: {constraint_str}. "
            f"Expected format: operator + version (e.g., '>=1.0.0')"
        )

    operator, version = match.groups()
    return VersionConstraint(operator=operator, version=version)


def parse_manifest(manifest_path: Path) -> Manifest:
    """
    Parse a manifest.json file.

    Args:
        manifest_path: Path to manifest.json

    Returns:
        Manifest object

    Raises:
        ManifestError: If file cannot be read or parsed
        ValidationError: If manifest is invalid
    """
    try:
        with open(manifest_path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError as e:
        raise ManifestError(f"Manifest file not found: {manifest_path}") from e
    except json.JSONDecodeError as e:
        raise ManifestError(f"Failed to parse manifest JSON: {e}") from e
    except Exception as e:
        raise ManifestError(f"Failed to read manifest file: {e}") from e

    # Validate and extract fields
    validate_manifest_structure(data)

    # Parse dependencies
    dependencies = {}
    if "dependencies" in data:
        for dep_name, constraint_str in data["dependencies"].items():
            try:
                dependencies[dep_name] = parse_version_constraint(constraint_str)
            except ValidationError as e:
                raise ValidationError(
                    f"Invalid dependency constraint for '{dep_name}': {e}"
                ) from e

    # Extract unique domains
    unique = data.get("unique", [])
    if not isinstance(unique, list):
        raise ValidationError("'unique' field must be a list")

    return Manifest(
        name=data["name"],
        version=data["version"],
        main=data["main"],
        description=data.get("description", ""),
        author=data.get("author", ""),
        dependencies=dependencies,
        unique=unique,
        raw_data=data,
    )


def validate_manifest_structure(data: dict[str, Any]) -> None:
    """
    Validate manifest structure and required fields.

    Args:
        data: Parsed manifest data

    Raises:
        ValidationError: If manifest structure is invalid
    """
    # Check required fields
    required_fields = ["name", "version", "main"]
    for field in required_fields:
        if field not in data:
            raise ValidationError(f"Missing required field: {field}")

    # Validate name (alphanumeric + hyphens only)
    name = data["name"]
    if not isinstance(name, str) or not re.match(r"^[a-z0-9-]+$", name):
        raise ValidationError(
            f"Invalid plugin name: {name}. "
            f"Must be lowercase alphanumeric with hyphens only."
        )

    # Validate version (semantic versioning)
    version = data["version"]
    if not isinstance(version, str) or not re.match(r"^\d+\.\d+\.\d+$", version):
        raise ValidationError(
            f"Invalid version: {version}. Must be semantic version (e.g., '1.0.0')"
        )

    # Validate main (must be a .py file)
    main = data["main"]
    if not isinstance(main, str) or not main.endswith(".py"):
        raise ValidationError(f"Invalid main entry point: {main}. Must be a .py file")

    # Validate optional fields
    if "description" in data and not isinstance(data["description"], str):
        raise ValidationError("'description' field must be a string")

    if "author" in data and not isinstance(data["author"], str):
        raise ValidationError("'author' field must be a string")

    if "dependencies" in data:
        if not isinstance(data["dependencies"], dict):
            raise ValidationError("'dependencies' field must be a dictionary")
        for dep_name, constraint in data["dependencies"].items():
            if not isinstance(dep_name, str):
                raise ValidationError(f"Dependency name must be string: {dep_name}")
            if not isinstance(constraint, str):
                raise ValidationError(
                    f"Dependency constraint must be string: {constraint}"
                )

    if "unique" in data:
        if not isinstance(data["unique"], list):
            raise ValidationError("'unique' field must be a list")
        for domain in data["unique"]:
            if not isinstance(domain, str):
                raise ValidationError(f"Unique domain must be string: {domain}")
            # Validate domain format (dot-separated identifiers)
            if not re.match(r"^[a-z0-9]+(\.[a-z0-9]+)*$", domain):
                raise ValidationError(
                    f"Invalid unique domain: {domain}. "
                    f"Must be dot-separated lowercase alphanumeric identifiers."
                )
