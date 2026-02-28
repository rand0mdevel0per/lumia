"""
File System Operations MCP Server.

This server bridges to Shipyard Bay API for sandboxed file system operations.

MCP Tools:
- fs_read: Read file content
- fs_write: Write file content
- fs_list: List directory contents
- fs_mkdir: Create directory
- fs_delete: Delete file or directory
"""

import asyncio
import json
import sys

import httpx


class FileSystemServer:
    """File system operations MCP server."""

    def __init__(self, bay_url: str = "http://localhost:8000"):
        """
        Initialize file system server.

        Args:
            bay_url: Shipyard Bay API URL
        """
        self.bay_url = bay_url
        self.client = httpx.AsyncClient(base_url=bay_url, timeout=30.0)

    async def read_file(
        self, path: str, session_id: str = "default"
    ) -> dict[str, str]:
        """
        Read file content.

        Args:
            path: File path
            session_id: Session ID

        Returns:
            File content or error
        """
        try:
            response = await self.client.get(
                f"/ship/{session_id}/fs/read",
                params={"path": path},
            )
            response.raise_for_status()
            return response.json()

        except httpx.HTTPError as e:
            return {"content": "", "error": f"HTTP error: {e}"}
        except Exception as e:
            return {"content": "", "error": f"Error: {e}"}

    async def write_file(
        self, path: str, content: str, session_id: str = "default"
    ) -> dict[str, str]:
        """
        Write file content.

        Args:
            path: File path
            content: File content
            session_id: Session ID

        Returns:
            Success status or error
        """
        try:
            response = await self.client.post(
                f"/ship/{session_id}/fs/write",
                json={"path": path, "content": content},
            )
            response.raise_for_status()
            return response.json()

        except httpx.HTTPError as e:
            return {"status": "error", "error": f"HTTP error: {e}"}
        except Exception as e:
            return {"status": "error", "error": f"Error: {e}"}

    async def list_directory(
        self, path: str, session_id: str = "default"
    ) -> dict[str, list]:
        """
        List directory contents.

        Args:
            path: Directory path
            session_id: Session ID

        Returns:
            List of files and directories or error
        """
        try:
            response = await self.client.get(
                f"/ship/{session_id}/fs/list",
                params={"path": path},
            )
            response.raise_for_status()
            return response.json()

        except httpx.HTTPError as e:
            return {"files": [], "error": f"HTTP error: {e}"}
        except Exception as e:
            return {"files": [], "error": f"Error: {e}"}

    async def create_directory(
        self, path: str, session_id: str = "default"
    ) -> dict[str, str]:
        """
        Create directory.

        Args:
            path: Directory path
            session_id: Session ID

        Returns:
            Success status or error
        """
        try:
            response = await self.client.post(
                f"/ship/{session_id}/fs/mkdir",
                json={"path": path},
            )
            response.raise_for_status()
            return response.json()

        except httpx.HTTPError as e:
            return {"status": "error", "error": f"HTTP error: {e}"}
        except Exception as e:
            return {"status": "error", "error": f"Error: {e}"}

    async def delete_path(
        self, path: str, session_id: str = "default"
    ) -> dict[str, str]:
        """
        Delete file or directory.

        Args:
            path: Path to delete
            session_id: Session ID

        Returns:
            Success status or error
        """
        try:
            response = await self.client.delete(
                f"/ship/{session_id}/fs/delete",
                params={"path": path},
            )
            response.raise_for_status()
            return response.json()

        except httpx.HTTPError as e:
            return {"status": "error", "error": f"HTTP error: {e}"}
        except Exception as e:
            return {"status": "error", "error": f"Error: {e}"}

    async def handle_request(self, request: dict) -> dict:
        """Handle MCP request."""
        method = request.get("method")
        params = request.get("params", {})
        request_id = request.get("id")

        # Handle tools/list
        if method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "tools": [
                        {
                            "name": "fs_read",
                            "description": "Read file content",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "path": {"type": "string", "description": "File path"},
                                    "session_id": {"type": "string", "description": "Session ID", "default": "default"},
                                },
                                "required": ["path"],
                            },
                        },
                        {
                            "name": "fs_write",
                            "description": "Write file content",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "path": {"type": "string", "description": "File path"},
                                    "content": {"type": "string", "description": "File content"},
                                    "session_id": {"type": "string", "description": "Session ID", "default": "default"},
                                },
                                "required": ["path", "content"],
                            },
                        },
                        {
                            "name": "fs_list",
                            "description": "List directory contents",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "path": {"type": "string", "description": "Directory path"},
                                    "session_id": {"type": "string", "description": "Session ID", "default": "default"},
                                },
                                "required": ["path"],
                            },
                        },
                        {
                            "name": "fs_mkdir",
                            "description": "Create directory",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "path": {"type": "string", "description": "Directory path"},
                                    "session_id": {"type": "string", "description": "Session ID", "default": "default"},
                                },
                                "required": ["path"],
                            },
                        },
                        {
                            "name": "fs_delete",
                            "description": "Delete file or directory",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "path": {"type": "string", "description": "Path to delete"},
                                    "session_id": {"type": "string", "description": "Session ID", "default": "default"},
                                },
                                "required": ["path"],
                            },
                        },
                    ]
                },
            }

        # Handle tools/call
        if method == "tools/call":
            tool_name = params.get("name")
            arguments = params.get("arguments", {})
            session_id = arguments.get("session_id", "default")

            if tool_name == "fs_read":
                path = arguments.get("path", "")
                result = await self.read_file(path, session_id)
                return {"jsonrpc": "2.0", "id": request_id, "result": result}

            if tool_name == "fs_write":
                path = arguments.get("path", "")
                content = arguments.get("content", "")
                result = await self.write_file(path, content, session_id)
                return {"jsonrpc": "2.0", "id": request_id, "result": result}

            if tool_name == "fs_list":
                path = arguments.get("path", "")
                result = await self.list_directory(path, session_id)
                return {"jsonrpc": "2.0", "id": request_id, "result": result}

            if tool_name == "fs_mkdir":
                path = arguments.get("path", "")
                result = await self.create_directory(path, session_id)
                return {"jsonrpc": "2.0", "id": request_id, "result": result}

            if tool_name == "fs_delete":
                path = arguments.get("path", "")
                result = await self.delete_path(path, session_id)
                return {"jsonrpc": "2.0", "id": request_id, "result": result}

            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32601, "message": f"Unknown tool: {tool_name}"},
            }

        # Unknown method
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32601, "message": f"Unknown method: {method}"},
        }

    async def run(self):
        """Run MCP server (stdio transport)."""
        while True:
            try:
                line = await asyncio.get_event_loop().run_in_executor(
                    None, sys.stdin.readline
                )
                if not line:
                    break
                request = json.loads(line)
                response = await self.handle_request(request)
                print(json.dumps(response), flush=True)
            except json.JSONDecodeError:
                continue
            except Exception as e:
                print(f"Error: {e}", file=sys.stderr, flush=True)


async def main():
    """Main entry point."""
    import os

    bay_url = os.environ.get("SHIPYARD_BAY_URL", "http://localhost:8000")
    server = FileSystemServer(bay_url)
    await server.run()


if __name__ == "__main__":
    asyncio.run(main())
