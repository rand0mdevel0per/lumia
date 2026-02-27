"""
Plugin Lifecycle Hooks.

This module provides lifecycle hook execution for plugins.

Key features:
- Hook discovery in hooks/ directory
- Environment variable injection
- Subprocess execution with timeout
- Exit code handling
- Hook types: install, uninstall, upgrade, load, unload
"""

import os
import subprocess
from enum import Enum
from pathlib import Path


class HookError(Exception):
    """Base exception for hook-related errors."""

    pass


class HookType(Enum):
    """Hook type enumeration."""

    INSTALL = "install"
    UNINSTALL = "uninstall"
    UPGRADE = "upgrade"
    LOAD = "load"
    UNLOAD = "unload"


def execute_hook(
    plugin_dir: Path,
    hook_type: HookType,
    env_vars: dict[str, str] | None = None,
    timeout: int = 60,
) -> None:
    """
    Execute a lifecycle hook for a plugin.

    Args:
        plugin_dir: Plugin directory path
        hook_type: Type of hook to execute
        env_vars: Additional environment variables to inject
        timeout: Timeout in seconds (default: 60)

    Raises:
        HookError: If hook execution fails
    """
    # Find hook script
    hook_path = _find_hook(plugin_dir, hook_type)

    if hook_path is None:
        # No hook found, skip silently
        return

    # Prepare environment
    env = os.environ.copy()
    if env_vars:
        env.update(env_vars)

    # Add plugin-specific environment variables
    env["LUMIA_PLUGIN_DIR"] = str(plugin_dir)
    env["LUMIA_HOOK_TYPE"] = hook_type.value

    try:
        # Build command based on file extension
        cmd = (
            ["python", str(hook_path)]
            if hook_path.suffix == ".py"
            else [str(hook_path)]
        )

        # Execute hook script
        result = subprocess.run(
            cmd,
            cwd=plugin_dir,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )

        # Check exit code
        if result.returncode != 0:
            raise HookError(
                f"Hook {hook_type.value} failed with exit code {result.returncode}:\n"
                f"stdout: {result.stdout}\n"
                f"stderr: {result.stderr}"
            )

    except subprocess.TimeoutExpired as e:
        raise HookError(
            f"Hook {hook_type.value} timed out after {timeout} seconds"
        ) from e
    except Exception as e:
        raise HookError(f"Failed to execute hook {hook_type.value}: {e}") from e


def _find_hook(plugin_dir: Path, hook_type: HookType) -> Path | None:
    """
    Find hook script in plugin hooks/ directory.

    Looks for scripts in the following order:
    1. hooks/{hook_type}.sh (Unix shell script)
    2. hooks/{hook_type}.bat (Windows batch script)
    3. hooks/{hook_type}.ps1 (PowerShell script)
    4. hooks/{hook_type}.py (Python script)

    Args:
        plugin_dir: Plugin directory path
        hook_type: Type of hook to find

    Returns:
        Path to hook script, or None if not found
    """
    hooks_dir = plugin_dir / "hooks"

    if not hooks_dir.exists() or not hooks_dir.is_dir():
        return None

    # Check for different script types
    hook_name = hook_type.value
    extensions = [".sh", ".bat", ".ps1", ".py"]

    for ext in extensions:
        hook_path = hooks_dir / f"{hook_name}{ext}"
        if hook_path.exists() and hook_path.is_file():
            # Make script executable on Unix systems
            if ext == ".sh":
                try:
                    import stat
                    hook_path.chmod(hook_path.stat().st_mode | stat.S_IEXEC)
                except Exception:
                    pass  # Ignore chmod errors on Windows

            return hook_path

    return None


def has_hook(plugin_dir: Path, hook_type: HookType) -> bool:
    """
    Check if plugin has a specific hook.

    Args:
        plugin_dir: Plugin directory path
        hook_type: Type of hook to check

    Returns:
        True if hook exists
    """
    return _find_hook(plugin_dir, hook_type) is not None
