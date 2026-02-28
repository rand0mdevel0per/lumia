"""
MCP System API.

This module provides a high-level API for plugins to interact with MCP servers.

Key functions:
- register(name, command, **kwargs): Register and start MCP server
- call(server_name, tool_name, arguments, timeout): Call MCP tool
"""

import asyncio
from typing import Any

from lumia.mcp.lifecycle import ServerConfig, ServerManager

# Global server manager instance
_manager: ServerManager | None = None


def _get_manager() -> ServerManager:
    """Get or create global server manager."""
    global _manager
    if _manager is None:
        _manager = ServerManager()
    return _manager


async def register(
    name: str,
    command: list[str],
    timeout: float = 30.0,
    max_retries: int = 3,
    restart_on_crash: bool = True,
    max_restarts: int = 3,
    health_check_interval: float = 60.0,
) -> None:
    """
    Register and start MCP server.

    Args:
        name: Server name (unique identifier)
        command: Command to start server (e.g., ['python', '-m', 'lumia.mcp.servers.python_exec'])
        timeout: Request timeout in seconds
        max_retries: Maximum number of retries on failure
        restart_on_crash: Whether to auto-restart on crash
        max_restarts: Maximum number of restarts
        health_check_interval: Health check interval in seconds

    Raises:
        Exception: If server registration or startup fails

    Example:
        >>> await lumia.system.mcp.register(
        ...     'python',
        ...     ['python', '-m', 'lumia.mcp.servers.python_exec'],
        ...     timeout=30.0
        ... )
    """
    manager = _get_manager()

    # Create server config
    config = ServerConfig(
        name=name,
        command=command,
        timeout=timeout,
        max_retries=max_retries,
        restart_on_crash=restart_on_crash,
        max_restarts=max_restarts,
        health_check_interval=health_check_interval,
    )

    # Register server
    manager.register(config)

    # Start server
    await manager.start_server(name)


async def call(
    server_name: str,
    tool_name: str,
    arguments: dict[str, Any] | None = None,
    timeout: float | None = None,
) -> Any:
    """
    Call MCP tool.

    Args:
        server_name: Server name
        tool_name: Tool name
        arguments: Tool arguments
        timeout: Optional timeout override (uses server default if None)

    Returns:
        Tool result

    Raises:
        Exception: If server not found, not running, or tool call fails

    Example:
        >>> result = await lumia.system.mcp.call(
        ...     'python',
        ...     'python_exec',
        ...     {'code': 'print("Hello")', 'session_id': 'test'}
        ... )
        >>> print(result['stdout'])
        Hello
    """
    manager = _get_manager()

    # Get client
    client = manager.get_client(server_name)

    # Call tool with optional timeout
    if timeout is not None:
        return await asyncio.wait_for(
            client.call_tool(tool_name, arguments), timeout=timeout
        )
    else:
        return await client.call_tool(tool_name, arguments)


async def unregister(name: str) -> None:
    """
    Unregister and stop MCP server.

    Args:
        name: Server name

    Raises:
        Exception: If server not found

    Example:
        >>> await lumia.system.mcp.unregister('python')
    """
    manager = _get_manager()
    manager.unregister(name)


async def stop(name: str) -> None:
    """
    Stop MCP server.

    Args:
        name: Server name

    Raises:
        Exception: If server not found

    Example:
        >>> await lumia.system.mcp.stop('python')
    """
    manager = _get_manager()
    await manager.stop_server(name)


def get_status(name: str) -> dict[str, Any]:
    """
    Get server status.

    Args:
        name: Server name

    Returns:
        Server status information

    Raises:
        Exception: If server not found

    Example:
        >>> status = lumia.system.mcp.get_status('python')
        >>> print(status['running'])
        True
    """
    manager = _get_manager()
    status = manager.get_status(name)
    return {
        "name": status.name,
        "running": status.running,
        "restart_count": status.restart_count,
        "last_error": status.last_error,
        "last_health_check": status.last_health_check,
    }


def list_servers() -> list[str]:
    """
    List all registered servers.

    Returns:
        List of server names

    Example:
        >>> servers = lumia.system.mcp.list_servers()
        >>> print(servers)
        ['python', 'shell', 'browser']
    """
    manager = _get_manager()
    return manager.list_servers()


async def stop_all() -> None:
    """
    Stop all running servers.

    Example:
        >>> await lumia.system.mcp.stop_all()
    """
    manager = _get_manager()
    await manager.stop_all()
