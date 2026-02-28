"""
Browser Automation MCP Server.

This server provides browser automation capabilities via Puppeteer with a
micro-agentic loop for high-level goal execution.

MCP Tools:
- browser_execute_goal: Execute high-level browser goal
- browser_navigate: Navigate to URL
- browser_screenshot: Take screenshot
- browser_extract: Extract page content
- browser_click: Click element
- browser_type: Type text into element
- browser_close_session: Close browser session
"""

import asyncio
import json
import sys
import time
from dataclasses import dataclass

import httpx


@dataclass
class BrowserSession:
    """Browser session information."""

    session_id: str
    created_at: float
    last_access: float
    ttl: float = 3600.0  # 1 hour default TTL


class BrowserServer:
    """Browser automation MCP server."""

    def __init__(
        self,
        bay_url: str = "http://localhost:8000",
        max_sessions: int = 5,
        default_ttl: float = 3600.0,
    ):
        """
        Initialize browser server.

        Args:
            bay_url: Shipyard Bay API URL
            max_sessions: Maximum concurrent sessions
            default_ttl: Default session TTL in seconds
        """
        self.bay_url = bay_url
        self.client = httpx.AsyncClient(base_url=bay_url, timeout=60.0)
        self.max_sessions = max_sessions
        self.default_ttl = default_ttl
        self.sessions: dict[str, BrowserSession] = {}

    def _create_session(self, session_id: str) -> BrowserSession:
        """Create new browser session."""
        now = time.time()
        session = BrowserSession(
            session_id=session_id,
            created_at=now,
            last_access=now,
            ttl=self.default_ttl,
        )
        self.sessions[session_id] = session
        return session

    def _get_session(self, session_id: str) -> BrowserSession | None:
        """Get browser session and update last access."""
        session = self.sessions.get(session_id)
        if session:
            session.last_access = time.time()
        return session

    def _cleanup_expired_sessions(self) -> None:
        """Remove expired sessions."""
        now = time.time()
        expired = [
            sid
            for sid, session in self.sessions.items()
            if now - session.last_access > session.ttl
        ]
        for sid in expired:
            del self.sessions[sid]

    async def execute_goal(
        self, goal: str, session_id: str = "default", max_steps: int = 10
    ) -> dict[str, str]:
        """
        Execute high-level browser goal using micro-agentic loop.

        Args:
            goal: High-level goal description
            session_id: Session ID
            max_steps: Maximum steps for goal execution

        Returns:
            Execution result with steps, final_state, and status
        """
        try:
            # Ensure session exists
            if session_id not in self.sessions:
                self._create_session(session_id)

            # Cleanup expired sessions
            self._cleanup_expired_sessions()

            # Execute goal via Shipyard Bay browser agent
            response = await self.client.post(
                f"/ship/{session_id}/browser/execute_goal",
                json={"goal": goal, "max_steps": max_steps},
            )
            response.raise_for_status()
            return response.json()

        except httpx.HTTPError as e:
            return {
                "steps": [],
                "final_state": "",
                "status": "error",
                "error": f"HTTP error: {e}",
            }
        except Exception as e:
            return {
                "steps": [],
                "final_state": "",
                "status": "error",
                "error": f"Error: {e}",
            }

    async def navigate(
        self, url: str, session_id: str = "default", wait_until: str = "networkidle2"
    ) -> dict[str, str]:
        """
        Navigate to URL.

        Args:
            url: Target URL
            session_id: Session ID
            wait_until: Wait condition (load, domcontentloaded, networkidle0, networkidle2)

        Returns:
            Navigation result with final_url and status
        """
        try:
            # Ensure session exists
            if session_id not in self.sessions:
                self._create_session(session_id)

            response = await self.client.post(
                f"/ship/{session_id}/browser/navigate",
                json={"url": url, "wait_until": wait_until},
            )
            response.raise_for_status()
            return response.json()

        except httpx.HTTPError as e:
            return {"final_url": "", "status": "error", "error": f"HTTP error: {e}"}
        except Exception as e:
            return {"final_url": "", "status": "error", "error": f"Error: {e}"}

    async def screenshot(
        self,
        session_id: str = "default",
        full_page: bool = False,
        selector: str | None = None,
    ) -> dict[str, str]:
        """
        Take screenshot.

        Args:
            session_id: Session ID
            full_page: Capture full page
            selector: CSS selector for element screenshot

        Returns:
            Screenshot result with base64 data and status
        """
        try:
            if session_id not in self.sessions:
                return {
                    "data": "",
                    "status": "error",
                    "error": "Session not found",
                }

            response = await self.client.post(
                f"/ship/{session_id}/browser/screenshot",
                json={"full_page": full_page, "selector": selector},
            )
            response.raise_for_status()
            return response.json()

        except httpx.HTTPError as e:
            return {"data": "", "status": "error", "error": f"HTTP error: {e}"}
        except Exception as e:
            return {"data": "", "status": "error", "error": f"Error: {e}"}

    async def extract(
        self,
        session_id: str = "default",
        selector: str | None = None,
        extract_type: str = "text",
    ) -> dict[str, str]:
        """
        Extract page content.

        Args:
            session_id: Session ID
            selector: CSS selector (None for whole page)
            extract_type: Type of extraction (text, html, markdown)

        Returns:
            Extraction result with content and status
        """
        try:
            if session_id not in self.sessions:
                return {
                    "content": "",
                    "status": "error",
                    "error": "Session not found",
                }

            response = await self.client.post(
                f"/ship/{session_id}/browser/extract",
                json={"selector": selector, "extract_type": extract_type},
            )
            response.raise_for_status()
            return response.json()

        except httpx.HTTPError as e:
            return {"content": "", "status": "error", "error": f"HTTP error: {e}"}
        except Exception as e:
            return {"content": "", "status": "error", "error": f"Error: {e}"}

    async def click(
        self, selector: str, session_id: str = "default", wait_nav: bool = False
    ) -> dict[str, str]:
        """
        Click element.

        Args:
            selector: CSS selector
            session_id: Session ID
            wait_nav: Wait for navigation after click

        Returns:
            Click result with status
        """
        try:
            if session_id not in self.sessions:
                return {"status": "error", "error": "Session not found"}

            response = await self.client.post(
                f"/ship/{session_id}/browser/click",
                json={"selector": selector, "wait_nav": wait_nav},
            )
            response.raise_for_status()
            return response.json()

        except httpx.HTTPError as e:
            return {"status": "error", "error": f"HTTP error: {e}"}
        except Exception as e:
            return {"status": "error", "error": f"Error: {e}"}

    async def type_text(
        self,
        selector: str,
        text: str,
        session_id: str = "default",
        delay: int = 0,
    ) -> dict[str, str]:
        """
        Type text into element.

        Args:
            selector: CSS selector
            text: Text to type
            session_id: Session ID
            delay: Delay between keystrokes in ms

        Returns:
            Type result with status
        """
        try:
            if session_id not in self.sessions:
                return {"status": "error", "error": "Session not found"}

            response = await self.client.post(
                f"/ship/{session_id}/browser/type",
                json={"selector": selector, "text": text, "delay": delay},
            )
            response.raise_for_status()
            return response.json()

        except httpx.HTTPError as e:
            return {"status": "error", "error": f"HTTP error: {e}"}
        except Exception as e:
            return {"status": "error", "error": f"Error: {e}"}

    async def close_session(self, session_id: str) -> dict[str, str]:
        """
        Close browser session.

        Args:
            session_id: Session ID

        Returns:
            Close result with status
        """
        try:
            if session_id not in self.sessions:
                return {"status": "error", "error": "Session not found"}

            response = await self.client.post(
                f"/ship/{session_id}/browser/close", json={}
            )
            response.raise_for_status()

            # Remove from local sessions
            del self.sessions[session_id]

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
                            "name": "browser_execute_goal",
                            "description": "Execute high-level browser goal using micro-agentic loop",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "goal": {
                                        "type": "string",
                                        "description": "High-level goal description",
                                    },
                                    "session_id": {
                                        "type": "string",
                                        "description": "Session ID (default: 'default')",
                                        "default": "default",
                                    },
                                    "max_steps": {
                                        "type": "integer",
                                        "description": "Maximum steps for goal execution (default: 10)",
                                        "default": 10,
                                    },
                                },
                                "required": ["goal"],
                            },
                        },
                        {
                            "name": "browser_navigate",
                            "description": "Navigate to URL",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "url": {
                                        "type": "string",
                                        "description": "Target URL",
                                    },
                                    "session_id": {
                                        "type": "string",
                                        "description": "Session ID (default: 'default')",
                                        "default": "default",
                                    },
                                    "wait_until": {
                                        "type": "string",
                                        "description": "Wait condition (load, domcontentloaded, networkidle0, networkidle2)",
                                        "default": "networkidle2",
                                    },
                                },
                                "required": ["url"],
                            },
                        },
                        {
                            "name": "browser_screenshot",
                            "description": "Take screenshot",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "session_id": {
                                        "type": "string",
                                        "description": "Session ID (default: 'default')",
                                        "default": "default",
                                    },
                                    "full_page": {
                                        "type": "boolean",
                                        "description": "Capture full page (default: false)",
                                        "default": False,
                                    },
                                    "selector": {
                                        "type": "string",
                                        "description": "CSS selector for element screenshot (optional)",
                                    },
                                },
                                "required": [],
                            },
                        },
                        {
                            "name": "browser_extract",
                            "description": "Extract page content",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "session_id": {
                                        "type": "string",
                                        "description": "Session ID (default: 'default')",
                                        "default": "default",
                                    },
                                    "selector": {
                                        "type": "string",
                                        "description": "CSS selector (optional, None for whole page)",
                                    },
                                    "extract_type": {
                                        "type": "string",
                                        "description": "Type of extraction (text, html, markdown)",
                                        "default": "text",
                                    },
                                },
                                "required": [],
                            },
                        },
                        {
                            "name": "browser_click",
                            "description": "Click element",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "selector": {
                                        "type": "string",
                                        "description": "CSS selector",
                                    },
                                    "session_id": {
                                        "type": "string",
                                        "description": "Session ID (default: 'default')",
                                        "default": "default",
                                    },
                                    "wait_nav": {
                                        "type": "boolean",
                                        "description": "Wait for navigation after click (default: false)",
                                        "default": False,
                                    },
                                },
                                "required": ["selector"],
                            },
                        },
                        {
                            "name": "browser_type",
                            "description": "Type text into element",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "selector": {
                                        "type": "string",
                                        "description": "CSS selector",
                                    },
                                    "text": {
                                        "type": "string",
                                        "description": "Text to type",
                                    },
                                    "session_id": {
                                        "type": "string",
                                        "description": "Session ID (default: 'default')",
                                        "default": "default",
                                    },
                                    "delay": {
                                        "type": "integer",
                                        "description": "Delay between keystrokes in ms (default: 0)",
                                        "default": 0,
                                    },
                                },
                                "required": ["selector", "text"],
                            },
                        },
                        {
                            "name": "browser_close_session",
                            "description": "Close browser session",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "session_id": {
                                        "type": "string",
                                        "description": "Session ID",
                                    },
                                },
                                "required": ["session_id"],
                            },
                        },
                    ]
                },
            }

        # Handle tools/call
        if method == "tools/call":
            tool_name = params.get("name")
            arguments = params.get("arguments", {})

            if tool_name == "browser_execute_goal":
                goal = arguments.get("goal", "")
                session_id = arguments.get("session_id", "default")
                max_steps = arguments.get("max_steps", 10)
                result = await self.execute_goal(goal, session_id, max_steps)
                return {"jsonrpc": "2.0", "id": request_id, "result": result}

            if tool_name == "browser_navigate":
                url = arguments.get("url", "")
                session_id = arguments.get("session_id", "default")
                wait_until = arguments.get("wait_until", "networkidle2")
                result = await self.navigate(url, session_id, wait_until)
                return {"jsonrpc": "2.0", "id": request_id, "result": result}

            if tool_name == "browser_screenshot":
                session_id = arguments.get("session_id", "default")
                full_page = arguments.get("full_page", False)
                selector = arguments.get("selector")
                result = await self.screenshot(session_id, full_page, selector)
                return {"jsonrpc": "2.0", "id": request_id, "result": result}

            if tool_name == "browser_extract":
                session_id = arguments.get("session_id", "default")
                selector = arguments.get("selector")
                extract_type = arguments.get("extract_type", "text")
                result = await self.extract(session_id, selector, extract_type)
                return {"jsonrpc": "2.0", "id": request_id, "result": result}

            if tool_name == "browser_click":
                selector = arguments.get("selector", "")
                session_id = arguments.get("session_id", "default")
                wait_nav = arguments.get("wait_nav", False)
                result = await self.click(selector, session_id, wait_nav)
                return {"jsonrpc": "2.0", "id": request_id, "result": result}

            if tool_name == "browser_type":
                selector = arguments.get("selector", "")
                text = arguments.get("text", "")
                session_id = arguments.get("session_id", "default")
                delay = arguments.get("delay", 0)
                result = await self.type_text(selector, text, session_id, delay)
                return {"jsonrpc": "2.0", "id": request_id, "result": result}

            if tool_name == "browser_close_session":
                session_id = arguments.get("session_id", "")
                result = await self.close_session(session_id)
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
                # Read request from stdin
                line = await asyncio.get_event_loop().run_in_executor(
                    None, sys.stdin.readline
                )
                if not line:
                    break

                # Parse request
                request = json.loads(line)

                # Handle request
                response = await self.handle_request(request)

                # Write response to stdout
                print(json.dumps(response), flush=True)

            except json.JSONDecodeError:
                continue
            except Exception as e:
                # Log error to stderr
                print(f"Error: {e}", file=sys.stderr, flush=True)


async def main():
    """Main entry point."""
    import os

    bay_url = os.environ.get("SHIPYARD_BAY_URL", "http://localhost:8000")
    max_sessions = int(os.environ.get("BROWSER_MAX_SESSIONS", "5"))
    default_ttl = float(os.environ.get("BROWSER_SESSION_TTL", "3600.0"))

    server = BrowserServer(bay_url, max_sessions, default_ttl)
    await server.run()


if __name__ == "__main__":
    asyncio.run(main())
