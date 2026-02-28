"""
Memory Query MCP Server.

This server bridges to Lumia's memory system for querying topics and instances.

MCP Tools:
- memory_query: Query memory system with RAG + spreading activation
- memory_upsert_topic: Create or update topic
- memory_upsert_instance: Create or update instance
- memory_create_edge: Create edge between topics
"""

import asyncio
import json
import sys

# Note: This server requires lumia.memory to be available
# It should be run in the same environment as the Lumia framework


class MemoryQueryServer:
    """Memory query MCP server."""

    def __init__(self):
        """Initialize memory query server."""
        # Import memory system (lazy import to avoid circular dependencies)
        try:
            from lumia.memory import MemorySystem

            self.memory = MemorySystem()
        except ImportError as e:
            print(
                f"Error: Failed to import lumia.memory: {e}",
                file=sys.stderr,
                flush=True,
            )
            self.memory = None

    async def query(
        self, query_text: str, sender_filter: str | None = None, top_k: int = 10
    ) -> dict:
        """
        Query memory system.

        Args:
            query_text: Query text
            sender_filter: Optional sender filter
            top_k: Number of results to return

        Returns:
            Query results with topics and instances
        """
        if not self.memory:
            return {
                "topics": [],
                "instances": [],
                "status": "error",
                "error": "Memory system not available",
            }

        try:
            results = self.memory.query(query_text, sender_filter)
            return {
                "topics": [
                    {
                        "id": r.topic_id,
                        "name": r.topic_name,
                        "content": r.topic_content,
                        "score": r.score,
                    }
                    for r in results[:top_k]
                ],
                "status": "success",
            }
        except Exception as e:
            return {
                "topics": [],
                "status": "error",
                "error": f"Query error: {e}",
            }

    async def upsert_topic(
        self, name: str, content: str, description: str | None = None
    ) -> dict:
        """
        Create or update topic.

        Args:
            name: Topic name
            content: Topic content
            description: Optional description

        Returns:
            Result with topic_id and status
        """
        if not self.memory:
            return {
                "topic_id": None,
                "status": "error",
                "error": "Memory system not available",
            }

        try:
            topic_id = self.memory.upsert_topic(name, content, description)
            return {"topic_id": topic_id, "status": "success"}
        except Exception as e:
            return {
                "topic_id": None,
                "status": "error",
                "error": f"Upsert error: {e}",
            }

    async def upsert_instance(
        self, topic_name: str, content: str, sender: str | None = None
    ) -> dict:
        """
        Create or update instance.

        Args:
            topic_name: Topic name
            content: Instance content
            sender: Optional sender identifier

        Returns:
            Result with instance_id and status
        """
        if not self.memory:
            return {
                "instance_id": None,
                "status": "error",
                "error": "Memory system not available",
            }

        try:
            instance_id = self.memory.upsert_instance(topic_name, content, sender)
            return {"instance_id": instance_id, "status": "success"}
        except Exception as e:
            return {
                "instance_id": None,
                "status": "error",
                "error": f"Upsert error: {e}",
            }

    async def create_edge(
        self, from_topic: str, to_topic: str, weight: float = 1.0
    ) -> dict:
        """
        Create edge between topics.

        Args:
            from_topic: Source topic name
            to_topic: Target topic name
            weight: Edge weight

        Returns:
            Result with edge_id and status
        """
        if not self.memory:
            return {
                "edge_id": None,
                "status": "error",
                "error": "Memory system not available",
            }

        try:
            edge_id = self.memory.create_edge(from_topic, to_topic, weight)
            return {"edge_id": edge_id, "status": "success"}
        except Exception as e:
            return {
                "edge_id": None,
                "status": "error",
                "error": f"Create edge error: {e}",
            }

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
                            "name": "memory_query",
                            "description": "Query memory system with RAG + spreading activation",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "query_text": {
                                        "type": "string",
                                        "description": "Query text",
                                    },
                                    "sender_filter": {
                                        "type": "string",
                                        "description": "Optional sender filter",
                                    },
                                    "top_k": {
                                        "type": "integer",
                                        "description": "Number of results (default: 10)",
                                        "default": 10,
                                    },
                                },
                                "required": ["query_text"],
                            },
                        },
                        {
                            "name": "memory_upsert_topic",
                            "description": "Create or update topic",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "name": {
                                        "type": "string",
                                        "description": "Topic name",
                                    },
                                    "content": {
                                        "type": "string",
                                        "description": "Topic content",
                                    },
                                    "description": {
                                        "type": "string",
                                        "description": "Optional description",
                                    },
                                },
                                "required": ["name", "content"],
                            },
                        },
                        {
                            "name": "memory_upsert_instance",
                            "description": "Create or update instance",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "topic_name": {
                                        "type": "string",
                                        "description": "Topic name",
                                    },
                                    "content": {
                                        "type": "string",
                                        "description": "Instance content",
                                    },
                                    "sender": {
                                        "type": "string",
                                        "description": "Optional sender identifier",
                                    },
                                },
                                "required": ["topic_name", "content"],
                            },
                        },
                        {
                            "name": "memory_create_edge",
                            "description": "Create edge between topics",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "from_topic": {
                                        "type": "string",
                                        "description": "Source topic name",
                                    },
                                    "to_topic": {
                                        "type": "string",
                                        "description": "Target topic name",
                                    },
                                    "weight": {
                                        "type": "number",
                                        "description": "Edge weight (default: 1.0)",
                                        "default": 1.0,
                                    },
                                },
                                "required": ["from_topic", "to_topic"],
                            },
                        },
                    ]
                },
            }

        # Handle tools/call
        if method == "tools/call":
            tool_name = params.get("name")
            arguments = params.get("arguments", {})

            if tool_name == "memory_query":
                query_text = arguments.get("query_text", "")
                sender_filter = arguments.get("sender_filter")
                top_k = arguments.get("top_k", 10)
                result = await self.query(query_text, sender_filter, top_k)
                return {"jsonrpc": "2.0", "id": request_id, "result": result}

            if tool_name == "memory_upsert_topic":
                name = arguments.get("name", "")
                content = arguments.get("content", "")
                description = arguments.get("description")
                result = await self.upsert_topic(name, content, description)
                return {"jsonrpc": "2.0", "id": request_id, "result": result}

            if tool_name == "memory_upsert_instance":
                topic_name = arguments.get("topic_name", "")
                content = arguments.get("content", "")
                sender = arguments.get("sender")
                result = await self.upsert_instance(topic_name, content, sender)
                return {"jsonrpc": "2.0", "id": request_id, "result": result}

            if tool_name == "memory_create_edge":
                from_topic = arguments.get("from_topic", "")
                to_topic = arguments.get("to_topic", "")
                weight = arguments.get("weight", 1.0)
                result = await self.create_edge(from_topic, to_topic, weight)
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
    server = MemoryQueryServer()
    await server.run()


if __name__ == "__main__":
    asyncio.run(main())
