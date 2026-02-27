"""
Git Operations for Plugin Management.

This module provides git operations for plugin installation and updates.

Key features:
- Clone plugins from git repositories
- Fetch and checkout specific tags
- List available tags
- Version resolution
"""

import subprocess
from pathlib import Path


class GitError(Exception):
    """Base exception for git-related errors."""

    pass


def clone_plugin(repo_url: str, target_dir: Path, tag: str | None = None) -> None:
    """
    Clone a plugin repository.

    Args:
        repo_url: Git repository URL
        target_dir: Target directory for clone
        tag: Optional tag to checkout (uses --branch for shallow clone)

    Raises:
        GitError: If clone operation fails
    """
    try:
        # Ensure parent directory exists
        target_dir.parent.mkdir(parents=True, exist_ok=True)

        # Build clone command
        cmd = ["git", "clone"]

        if tag:
            # Shallow clone with specific tag
            cmd.extend(["--branch", tag, "--depth", "1"])

        cmd.extend([repo_url, str(target_dir)])

        # Execute clone
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode != 0:
            raise GitError(
                f"Failed to clone repository: {result.stderr or result.stdout}"
            )

    except FileNotFoundError as e:
        raise GitError("git command not found. Please install git.") from e
    except Exception as e:
        raise GitError(f"Failed to clone repository: {e}") from e


def fetch_tags(repo_dir: Path) -> None:
    """
    Fetch all tags from remote repository.

    Args:
        repo_dir: Plugin repository directory

    Raises:
        GitError: If fetch operation fails
    """
    try:
        result = subprocess.run(
            ["git", "fetch", "--tags"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode != 0:
            raise GitError(f"Failed to fetch tags: {result.stderr or result.stdout}")

    except FileNotFoundError as e:
        raise GitError("git command not found. Please install git.") from e
    except Exception as e:
        raise GitError(f"Failed to fetch tags: {e}") from e


def checkout_tag(repo_dir: Path, tag: str) -> None:
    """
    Checkout a specific tag.

    Args:
        repo_dir: Plugin repository directory
        tag: Tag name to checkout

    Raises:
        GitError: If checkout operation fails
    """
    try:
        result = subprocess.run(
            ["git", "checkout", tag],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode != 0:
            raise GitError(f"Failed to checkout tag {tag}: {result.stderr or result.stdout}")

    except FileNotFoundError as e:
        raise GitError("git command not found. Please install git.") from e
    except Exception as e:
        raise GitError(f"Failed to checkout tag: {e}") from e


def list_tags(repo_dir: Path) -> list[str]:
    """
    List all tags in repository.

    Args:
        repo_dir: Plugin repository directory

    Returns:
        List of tag names

    Raises:
        GitError: If list operation fails
    """
    try:
        result = subprocess.run(
            ["git", "tag", "-l"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode != 0:
            raise GitError(f"Failed to list tags: {result.stderr or result.stdout}")

        # Parse tags from output
        tags = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        return tags

    except FileNotFoundError as e:
        raise GitError("git command not found. Please install git.") from e
    except Exception as e:
        raise GitError(f"Failed to list tags: {e}") from e


def get_latest_tag(repo_dir: Path, prefix: str = "v") -> str | None:
    """
    Get the latest semantic version tag.

    Args:
        repo_dir: Plugin repository directory
        prefix: Tag prefix (default: "v")

    Returns:
        Latest tag name, or None if no tags found

    Raises:
        GitError: If operation fails
    """
    tags = list_tags(repo_dir)

    # Filter tags with prefix and valid semantic version
    version_tags = []
    for tag in tags:
        if tag.startswith(prefix):
            version_str = tag[len(prefix):]
            if _is_valid_semver(version_str):
                version_tags.append((tag, version_str))

    if not version_tags:
        return None

    # Sort by semantic version (descending)
    version_tags.sort(key=lambda x: _parse_semver(x[1]), reverse=True)

    return version_tags[0][0]


def _is_valid_semver(version: str) -> bool:
    """
    Check if string is a valid semantic version.

    Args:
        version: Version string

    Returns:
        True if valid semantic version
    """
    import re
    return bool(re.match(r"^\d+\.\d+\.\d+$", version))


def _parse_semver(version: str) -> tuple[int, int, int]:
    """
    Parse semantic version string into tuple.

    Args:
        version: Version string (e.g., "1.2.3")

    Returns:
        Tuple of (major, minor, patch)
    """
    parts = version.split(".")
    return (int(parts[0]), int(parts[1]), int(parts[2]))
