"""
MCP Client Implementation.

This module provides a client for the Model Context Protocol (MCP).

Key features:
- JSON-RPC 2.0 protocol
- stdio transport
- Request/response handling
- Error handling and retries
- Tool call interface
"""

import asyncio
import contextlib
import json
import uuid
from dataclasses import dataclass
from typing import Any


class MCPError(Exception):
    """Base exception for MCP-related errors."""

    pass


class MCPTimeoutError(MCPError):
    """Timeout error for MCP operations."""

    pass


class MCPProtocolError(MCPError):
    """Protocol error for MCP operations."""

    pass


@dataclass
class MCPRequest:
    """
    MCP request.

    Attributes:
        id: Request ID
        method: Method name
        params: Method parameters
    """

    id: str
    method: str
    params: dict[str, Any] | None = None

    def to_jsonrpc(self) -> dict[str, Any]:
        """Convert to JSON-RPC 2.0 format."""
        request = {
            "jsonrpc": "2.0",
            "id": self.id,
            "method": self.method,
        }
        if self.params is not None:
            request["params"] = self.params
        return request


@dataclass
class MCPResponse:
    """
    MCP response.

    Attributes:
        id: Request ID
        result: Result data (if success)
        error: Error data (if error)
    """

    id: str
    result: Any | None = None
    error: dict[str, Any] | None = None

    @classmethod
    def from_jsonrpc(cls, data: dict[str, Any]) -> "MCPResponse":
        """Parse from JSON-RPC 2.0 format."""
        return cls(
            id=data.get("id", ""),
            result=data.get("result"),
            error=data.get("error"),
        )

    def is_error(self) -> bool:
        """Check if response is an error."""
        return self.error is not None


class MCPClient:
    """
    MCP client with stdio transport.

    Provides JSON-RPC 2.0 communication over stdin/stdout.
    """

    def __init__(self, command: list[str], timeout: float = 30.0, max_retries: int = 3):
        """
        Initialize MCPClient.

        Args:
            command: Command to start MCP server
            timeout: Request timeout in seconds
            max_retries: Maximum number of retries on failure
        """
        self.command = command
        self.timeout = timeout
        self.max_retries = max_retries
        self._process: asyncio.subprocess.Process | None = None
        self._pending_requests: dict[str, asyncio.Future] = {}
        self._reader_task: asyncio.Task | None = None
        self._running = False

    async def start(self) -> None:
        """
        Start MCP server process and begin reading responses.

        Raises:
            MCPError: If server fails to start
        """
        if self._running:
            return

        try:
            # Start server process
            self._process = await asyncio.create_subprocess_exec(
                *self.command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            # Start response reader
            self._reader_task = asyncio.create_task(self._read_responses())
            self._running = True

        except Exception as e:
            raise MCPError(f"Failed to start MCP server: {e}") from e

    async def stop(self) -> None:
        """Stop MCP server process and cleanup."""
        if not self._running:
            return

        self._running = False

        # Cancel reader task
        if self._reader_task:
            self._reader_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._reader_task

        # Terminate process
        if self._process:
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=5.0)
            except TimeoutError:
                self._process.kill()
                await self._process.wait()

        # Cancel pending requests
        for future in self._pending_requests.values():
            if not future.done():
                future.set_exception(MCPError("Client stopped"))
        self._pending_requests.clear()

    async def _read_responses(self) -> None:
        """Read responses from server stdout."""
        if not self._process or not self._process.stdout:
            return

        try:
            while self._running:
                # Read line from stdout
                line = await self._process.stdout.readline()
                if not line:
                    break

                # Parse JSON-RPC response
                try:
                    data = json.loads(line.decode())
                    response = MCPResponse.from_jsonrpc(data)

                    # Resolve pending request
                    if response.id in self._pending_requests:
                        future = self._pending_requests.pop(response.id)
                        if response.is_error():
                            future.set_exception(
                                MCPProtocolError(
                                    f"MCP error: {response.error}"
                                )
                            )
                        else:
                            future.set_result(response.result)

                except json.JSONDecodeError:
                    # Log error but continue reading
                    pass

        except Exception as e:
            # Fail all pending requests
            for future in self._pending_requests.values():
                if not future.done():
                    future.set_exception(MCPError(f"Reader error: {e}"))
            self._pending_requests.clear()

    async def request(
        self, method: str, params: dict[str, Any] | None = None, retry: int = 0
    ) -> Any:
        """
        Send request to MCP server.

        Args:
            method: Method name
            params: Method parameters
            retry: Current retry count

        Returns:
            Response result

        Raises:
            MCPError: If request fails
            MCPTimeoutError: If request times out
        """
        if not self._running or not self._process or not self._process.stdin:
            raise MCPError("Client not running")

        # Generate request ID
        request_id = str(uuid.uuid4())

        # Create request
        request = MCPRequest(id=request_id, method=method, params=params)

        # Create future for response
        future: asyncio.Future = asyncio.Future()
        self._pending_requests[request_id] = future

        try:
            # Send request
            request_data = json.dumps(request.to_jsonrpc()) + "\n"
            self._process.stdin.write(request_data.encode())
            await self._process.stdin.drain()

            # Wait for response with timeout
            result = await asyncio.wait_for(future, timeout=self.timeout)
            return result

        except TimeoutError:
            # Remove pending request
            self._pending_requests.pop(request_id, None)

            # Retry if possible
            if retry < self.max_retries:
                return await self.request(method, params, retry + 1)

            raise MCPTimeoutError(f"Request timed out after {self.timeout}s") from None

        except Exception as e:
            # Remove pending request
            self._pending_requests.pop(request_id, None)

            # Retry if possible
            if retry < self.max_retries and not isinstance(e, MCPProtocolError):
                return await self.request(method, params, retry + 1)

            raise

    async def call_tool(
        self, tool_name: str, arguments: dict[str, Any] | None = None
    ) -> Any:
        """
        Call MCP tool.

        Args:
            tool_name: Tool name
            arguments: Tool arguments

        Returns:
            Tool result

        Raises:
            MCPError: If tool call fails
        """
        params = {"name": tool_name}
        if arguments:
            params["arguments"] = arguments

        return await self.request("tools/call", params)

    async def list_tools(self) -> list[dict[str, Any]]:
        """
        List available tools.

        Returns:
            List of tool definitions

        Raises:
            MCPError: If listing fails
        """
        result = await self.request("tools/list")
        return result.get("tools", []) if isinstance(result, dict) else []

    async def __aenter__(self):
        """Async context manager entry."""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.stop()
