"""
TypeScript Executor MCP Server.

This server bridges to Shipyard Bay API for sandboxed TypeScript execution via tsx.

MCP Tools:
- typescript_exec: Execute TypeScript code in sandbox
"""

import asyncio
import json
import sys

import httpx


class TypeScriptExecServer:
    """TypeScript executor MCP server."""

    def __init__(self, bay_url: str = "http://localhost:8000"):
        """
        Initialize TypeScript executor server.

        Args:
            bay_url: Shipyard Bay API URL
        """
        self.bay_url = bay_url
        self.client = httpx.AsyncClient(base_url=bay_url, timeout=30.0)

    async def execute_typescript(
        self, code: str, session_id: str = "default"
    ) -> dict[str, str]:
        """
        Execute TypeScript code in sandbox via tsx.

        Args:
            code: TypeScript code to execute
            session_id: Session ID for execution context

        Returns:
            Execution result with stdout, stderr, and status
        """
        try:
            response = await self.client.post(
                f"/ship/{session_id}/typescript/execute",
                json={"code": code},
            )
            response.raise_for_status()
            return response.json()

        except httpx.HTTPError as e:
            return {
                "stdout": "",
                "stderr": f"HTTP error: {e}",
                "status": "error",
            }
        except Exception as e:
            return {
                "stdout": "",
                "stderr": f"Error: {e}",
                "status": "error",
            }

    async def handle_request(self, request: dict) -> dict:
        """Handle MCP request."""
        method = request.get("method")
        params = request.get("params", {})
        request_id = request.get("id")

        if method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "tools": [
                        {
                            "name": "typescript_exec",
                            "description": "Execute TypeScript code in sandbox via tsx",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "code": {
                                        "type": "string",
                                        "description": "TypeScript code to execute",
                                    },
                                    "session_id": {
                                        "type": "string",
                                        "description": "Session ID (default: 'default')",
                                        "default": "default",
                                    },
                                },
                                "required": ["code"],
                            },
                        }
                    ]
                },
            }

        if method == "tools/call":
            tool_name = params.get("name")
            arguments = params.get("arguments", {})

            if tool_name == "typescript_exec":
                code = arguments.get("code", "")
                session_id = arguments.get("session_id", "default")
                result = await self.execute_typescript(code, session_id)
                return {"jsonrpc": "2.0", "id": request_id, "result": result}

            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32601, "message": f"Unknown tool: {tool_name}"},
            }

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
    server = TypeScriptExecServer(bay_url)
    await server.run()


if __name__ == "__main__":
    asyncio.run(main())
