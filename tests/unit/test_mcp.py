"""
Unit tests for MCP integration.

Tests cover:
- MCP Client (JSON-RPC 2.0 protocol, stdio transport)
- Server Lifecycle (start, stop, restart, health checks)
- System API (register, call, status)
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from lumia.mcp.client import MCPClient, MCPProtocolError, MCPTimeoutError
from lumia.mcp.lifecycle import LifecycleError, ServerConfig, ServerManager

# Fixtures


@pytest.fixture
def mock_process():
    """Mock subprocess for MCP server."""
    process = MagicMock()
    process.stdin = MagicMock()
    process.stdout = MagicMock()
    process.stderr = MagicMock()
    process.wait = AsyncMock(return_value=0)
    process.terminate = MagicMock()
    process.kill = MagicMock()
    return process


@pytest.fixture
def mock_response_queue():
    """Mock response queue for MCP client."""
    queue = asyncio.Queue()
    return queue


# MCP Client Tests


@pytest.mark.asyncio
async def test_mcp_client_start_stop(mock_process):
    """Test MCP client start and stop."""
    with patch("asyncio.create_subprocess_exec", return_value=mock_process):
        client = MCPClient(command=["python", "-m", "test_server"])

        # Start client
        await client.start()
        assert client._process is not None

        # Stop client
        await client.stop()
        assert client._process is None


@pytest.mark.asyncio
async def test_mcp_client_request_success(mock_process):
    """Test successful MCP request."""
    with patch("asyncio.create_subprocess_exec", return_value=mock_process):
        client = MCPClient(command=["python", "-m", "test_server"])
        await client.start()

        # Mock response
        response = {"jsonrpc": "2.0", "id": 1, "result": {"tools": []}}
        client._responses[1] = asyncio.Future()
        client._responses[1].set_result(response)

        # Make request
        result = await client.request("tools/list")
        assert result == {"tools": []}

        await client.stop()


@pytest.mark.asyncio
async def test_mcp_client_request_timeout(mock_process):
    """Test MCP request timeout."""
    with patch("asyncio.create_subprocess_exec", return_value=mock_process):
        client = MCPClient(command=["python", "-m", "test_server"], timeout=0.1)
        await client.start()

        # Request should timeout
        with pytest.raises(MCPTimeoutError):
            await client.request("tools/list")

        await client.stop()


@pytest.mark.asyncio
async def test_mcp_client_request_error(mock_process):
    """Test MCP request error response."""
    with patch("asyncio.create_subprocess_exec", return_value=mock_process):
        client = MCPClient(command=["python", "-m", "test_server"])
        await client.start()

        # Mock error response
        response = {
            "jsonrpc": "2.0",
            "id": 1,
            "error": {"code": -32601, "message": "Method not found"},
        }
        client._responses[1] = asyncio.Future()
        client._responses[1].set_result(response)

        # Request should raise error
        with pytest.raises(MCPProtocolError):
            await client.request("invalid_method")

        await client.stop()


# Server Lifecycle Tests


@pytest.mark.asyncio
async def test_server_manager_register():
    """Test server registration."""
    manager = ServerManager()
    config = ServerConfig(name="test", command=["python", "-m", "test_server"])

    manager.register(config)
    assert "test" in manager.list_servers()

    # Duplicate registration should fail
    with pytest.raises(LifecycleError):
        manager.register(config)


@pytest.mark.asyncio
async def test_server_manager_start_stop(mock_process):
    """Test server start and stop."""
    with patch("asyncio.create_subprocess_exec", return_value=mock_process):
        manager = ServerManager()
        config = ServerConfig(name="test", command=["python", "-m", "test_server"])

        manager.register(config)

        # Start server
        with patch.object(MCPClient, "start", new_callable=AsyncMock):
            await manager.start_server("test")
            status = manager.get_status("test")
            assert status.running is True

        # Stop server
        with patch.object(MCPClient, "stop", new_callable=AsyncMock):
            await manager.stop_server("test")
            status = manager.get_status("test")
            assert status.running is False


@pytest.mark.asyncio
async def test_server_manager_unregister():
    """Test server unregistration."""
    manager = ServerManager()
    config = ServerConfig(name="test", command=["python", "-m", "test_server"])

    manager.register(config)
    manager.unregister("test")
    assert "test" not in manager.list_servers()

    # Unregister non-existent server should fail
    with pytest.raises(LifecycleError):
        manager.unregister("nonexistent")


@pytest.mark.asyncio
async def test_server_manager_get_client(mock_process):
    """Test getting MCP client."""
    with patch("asyncio.create_subprocess_exec", return_value=mock_process):
        manager = ServerManager()
        config = ServerConfig(name="test", command=["python", "-m", "test_server"])

        manager.register(config)

        # Get client before start should fail
        with pytest.raises(LifecycleError):
            manager.get_client("test")

        # Start server and get client
        with patch.object(MCPClient, "start", new_callable=AsyncMock):
            await manager.start_server("test")
            client = manager.get_client("test")
            assert client is not None

        # Stop server
        with patch.object(MCPClient, "stop", new_callable=AsyncMock):
            await manager.stop_server("test")


# System API Tests


@pytest.mark.asyncio
async def test_system_api_register(mock_process):
    """Test system API register function."""
    from lumia.system import mcp_api

    with patch("asyncio.create_subprocess_exec", return_value=mock_process):
        with patch.object(MCPClient, "start", new_callable=AsyncMock):
            await mcp_api.register(
                "test", ["python", "-m", "test_server"], timeout=30.0
            )

            # Check server is registered and running
            servers = mcp_api.list_servers()
            assert "test" in servers

            status = mcp_api.get_status("test")
            assert status["running"] is True

        # Cleanup
        with patch.object(MCPClient, "stop", new_callable=AsyncMock):
            await mcp_api.stop("test")


@pytest.mark.asyncio
async def test_system_api_call(mock_process):
    """Test system API call function."""
    from lumia.system import mcp_api

    with patch("asyncio.create_subprocess_exec", return_value=mock_process):
        with patch.object(MCPClient, "start", new_callable=AsyncMock):
            await mcp_api.register("test", ["python", "-m", "test_server"])

            # Mock call_tool
            with patch.object(
                MCPClient,
                "call_tool",
                new_callable=AsyncMock,
                return_value={"result": "success"},
            ):
                result = await mcp_api.call("test", "test_tool", {"arg": "value"})
                assert result == {"result": "success"}

        # Cleanup
        with patch.object(MCPClient, "stop", new_callable=AsyncMock):
            await mcp_api.stop("test")


@pytest.mark.asyncio
async def test_system_api_unregister(mock_process):
    """Test system API unregister function."""
    from lumia.system import mcp_api

    with patch("asyncio.create_subprocess_exec", return_value=mock_process):
        with patch.object(MCPClient, "start", new_callable=AsyncMock):
            await mcp_api.register("test", ["python", "-m", "test_server"])

        # Unregister
        with patch.object(MCPClient, "stop", new_callable=AsyncMock):
            await mcp_api.unregister("test")

            # Check server is no longer registered
            servers = mcp_api.list_servers()
            assert "test" not in servers


@pytest.mark.asyncio
async def test_system_api_stop_all(mock_process):
    """Test system API stop_all function."""
    from lumia.system import mcp_api

    with patch("asyncio.create_subprocess_exec", return_value=mock_process):
        with patch.object(MCPClient, "start", new_callable=AsyncMock):
            await mcp_api.register("test1", ["python", "-m", "test_server"])
            await mcp_api.register("test2", ["python", "-m", "test_server"])

        # Stop all
        with patch.object(MCPClient, "stop", new_callable=AsyncMock):
            await mcp_api.stop_all()

            # Check all servers are stopped
            status1 = mcp_api.get_status("test1")
            status2 = mcp_api.get_status("test2")
            assert status1["running"] is False
            assert status2["running"] is False

