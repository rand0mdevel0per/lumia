"""
MCP Server Lifecycle Management.

This module provides lifecycle management for MCP servers.

Key features:
- Server registration
- Process spawning and monitoring
- Auto-restart on crash (max 3 retries)
- Graceful shutdown
- Health checks
"""

import asyncio
import contextlib
import time
from dataclasses import dataclass

from lumia.mcp.client import MCPClient


class LifecycleError(Exception):
    """Base exception for lifecycle-related errors."""

    pass


@dataclass
class ServerConfig:
    """
    MCP server configuration.

    Attributes:
        name: Server name (unique identifier)
        command: Command to start server
        timeout: Request timeout in seconds
        max_retries: Maximum number of retries on failure
        restart_on_crash: Whether to auto-restart on crash
        max_restarts: Maximum number of restarts
        health_check_interval: Health check interval in seconds
    """

    name: str
    command: list[str]
    timeout: float = 30.0
    max_retries: int = 3
    restart_on_crash: bool = True
    max_restarts: int = 3
    health_check_interval: float = 60.0


@dataclass
class ServerStatus:
    """
    Server status information.

    Attributes:
        name: Server name
        running: Whether server is running
        restart_count: Number of restarts
        last_error: Last error message
        last_health_check: Last health check timestamp
    """

    name: str
    running: bool
    restart_count: int = 0
    last_error: str | None = None
    last_health_check: float | None = None


class ServerManager:
    """
    MCP server lifecycle manager.

    Manages multiple MCP servers with automatic restart and health checks.
    """

    def __init__(self):
        """Initialize ServerManager."""
        self._servers: dict[str, ServerConfig] = {}
        self._clients: dict[str, MCPClient] = {}
        self._status: dict[str, ServerStatus] = {}
        self._monitor_tasks: dict[str, asyncio.Task] = {}
        self._health_check_tasks: dict[str, asyncio.Task] = {}
        self._running = False

    def register(self, config: ServerConfig) -> None:
        """
        Register MCP server.

        Args:
            config: Server configuration

        Raises:
            LifecycleError: If server already registered
        """
        if config.name in self._servers:
            raise LifecycleError(f"Server '{config.name}' already registered")

        self._servers[config.name] = config
        self._status[config.name] = ServerStatus(name=config.name, running=False)

    def unregister(self, name: str) -> None:
        """
        Unregister MCP server.

        Args:
            name: Server name

        Raises:
            LifecycleError: If server not found
        """
        if name not in self._servers:
            raise LifecycleError(f"Server '{name}' not found")

        # Stop server if running
        if self._status[name].running:
            asyncio.create_task(self.stop_server(name))

        # Remove from registry
        del self._servers[name]
        del self._status[name]

    async def start_server(self, name: str) -> None:
        """
        Start MCP server.

        Args:
            name: Server name

        Raises:
            LifecycleError: If server not found or already running
        """
        if name not in self._servers:
            raise LifecycleError(f"Server '{name}' not found")

        if self._status[name].running:
            raise LifecycleError(f"Server '{name}' already running")

        config = self._servers[name]

        try:
            # Create client
            client = MCPClient(
                command=config.command,
                timeout=config.timeout,
                max_retries=config.max_retries,
            )

            # Start client
            await client.start()

            # Store client
            self._clients[name] = client
            self._status[name].running = True
            self._status[name].restart_count = 0
            self._status[name].last_error = None

            # Start monitoring
            if config.restart_on_crash:
                self._monitor_tasks[name] = asyncio.create_task(
                    self._monitor_server(name)
                )

            # Start health checks
            self._health_check_tasks[name] = asyncio.create_task(
                self._health_check(name)
            )

        except Exception as e:
            self._status[name].last_error = str(e)
            raise LifecycleError(f"Failed to start server '{name}': {e}") from e

    async def stop_server(self, name: str) -> None:
        """
        Stop MCP server.

        Args:
            name: Server name

        Raises:
            LifecycleError: If server not found
        """
        if name not in self._servers:
            raise LifecycleError(f"Server '{name}' not found")

        if not self._status[name].running:
            return

        # Cancel monitoring
        if name in self._monitor_tasks:
            self._monitor_tasks[name].cancel()
            del self._monitor_tasks[name]

        # Cancel health checks
        if name in self._health_check_tasks:
            self._health_check_tasks[name].cancel()
            del self._health_check_tasks[name]

        # Stop client
        if name in self._clients:
            await self._clients[name].stop()
            del self._clients[name]

        self._status[name].running = False

    async def _monitor_server(self, name: str) -> None:
        """
        Monitor server process and restart on crash.

        Args:
            name: Server name
        """
        config = self._servers[name]
        status = self._status[name]

        while status.running and status.restart_count < config.max_restarts:
            try:
                # Wait for client process to exit
                client = self._clients.get(name)
                if not client or not client._process:
                    break

                await client._process.wait()

                # Process exited, check if we should restart
                if status.running and status.restart_count < config.max_restarts:
                    status.restart_count += 1
                    status.last_error = "Server crashed, restarting..."

                    # Stop current client
                    await client.stop()
                    del self._clients[name]

                    # Wait a bit before restarting
                    await asyncio.sleep(1.0)

                    # Restart server
                    try:
                        new_client = MCPClient(
                            command=config.command,
                            timeout=config.timeout,
                            max_retries=config.max_retries,
                        )
                        await new_client.start()
                        self._clients[name] = new_client

                    except Exception as e:
                        status.last_error = f"Restart failed: {e}"
                        status.running = False
                        break

            except asyncio.CancelledError:
                break
            except Exception as e:
                status.last_error = f"Monitor error: {e}"
                break

    async def _health_check(self, name: str) -> None:
        """
        Perform periodic health checks.

        Args:
            name: Server name
        """
        config = self._servers[name]
        status = self._status[name]

        while status.running:
            try:
                await asyncio.sleep(config.health_check_interval)

                # Perform health check
                client = self._clients.get(name)
                if client:
                    try:
                        # Try to list tools as health check
                        await asyncio.wait_for(
                            client.list_tools(), timeout=config.timeout
                        )
                        status.last_health_check = time.time()
                    except Exception as e:
                        status.last_error = f"Health check failed: {e}"

            except asyncio.CancelledError:
                break
            except Exception:
                pass

    def get_status(self, name: str) -> ServerStatus:
        """
        Get server status.

        Args:
            name: Server name

        Returns:
            Server status

        Raises:
            LifecycleError: If server not found
        """
        if name not in self._servers:
            raise LifecycleError(f"Server '{name}' not found")

        return self._status[name]

    def get_client(self, name: str) -> MCPClient:
        """
        Get MCP client for server.

        Args:
            name: Server name

        Returns:
            MCP client

        Raises:
            LifecycleError: If server not found or not running
        """
        if name not in self._servers:
            raise LifecycleError(f"Server '{name}' not found")

        if not self._status[name].running:
            raise LifecycleError(f"Server '{name}' not running")

        if name not in self._clients:
            raise LifecycleError(f"Client for server '{name}' not available")

        return self._clients[name]

    async def start_all(self) -> None:
        """Start all registered servers."""
        for name in self._servers:
            if not self._status[name].running:
                with contextlib.suppress(Exception):
                    await self.start_server(name)

    async def stop_all(self) -> None:
        """Stop all running servers."""
        for name in list(self._servers.keys()):
            if self._status[name].running:
                with contextlib.suppress(Exception):
                    await self.stop_server(name)

    def list_servers(self) -> list[str]:
        """
        List all registered servers.

        Returns:
            List of server names
        """
        return list(self._servers.keys())
