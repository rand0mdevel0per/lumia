"""
Web Search MCP Server.

This server provides web search capabilities via SearXNG (self-hosted) or
fallback to API providers (DuckDuckGo, Brave).

MCP Tools:
- web_search: Search the web and return results
"""

import asyncio
import json
import os
import sys
from dataclasses import dataclass

import httpx


@dataclass
class SearchResult:
    """Web search result."""

    title: str
    url: str
    snippet: str
    score: float = 0.0


class WebSearchServer:
    """Web search MCP server."""

    def __init__(
        self,
        searxng_url: str | None = None,
        fallback_provider: str = "duckduckgo",
        timeout: float = 30.0,
    ):
        """
        Initialize web search server.

        Args:
            searxng_url: SearXNG instance URL (None to use fallback)
            fallback_provider: Fallback provider (duckduckgo, brave)
            timeout: Request timeout in seconds
        """
        self.searxng_url = searxng_url
        self.fallback_provider = fallback_provider
        self.client = httpx.AsyncClient(timeout=timeout)

    async def _search_searxng(
        self, query: str, num_results: int = 10
    ) -> list[SearchResult]:
        """Search using SearXNG."""
        if not self.searxng_url:
            return []

        try:
            response = await self.client.get(
                f"{self.searxng_url}/search",
                params={
                    "q": query,
                    "format": "json",
                    "pageno": 1,
                },
            )
            response.raise_for_status()
            data = response.json()

            results = []
            for item in data.get("results", [])[:num_results]:
                results.append(
                    SearchResult(
                        title=item.get("title", ""),
                        url=item.get("url", ""),
                        snippet=item.get("content", ""),
                        score=item.get("score", 0.0),
                    )
                )
            return results

        except Exception:
            return []

    async def _search_duckduckgo(
        self, query: str, num_results: int = 10
    ) -> list[SearchResult]:
        """Search using DuckDuckGo API."""
        try:
            response = await self.client.get(
                "https://api.duckduckgo.com/",
                params={
                    "q": query,
                    "format": "json",
                    "no_html": 1,
                    "skip_disambig": 1,
                },
            )
            response.raise_for_status()
            data = response.json()

            results = []

            # Add abstract if available
            if data.get("Abstract"):
                results.append(
                    SearchResult(
                        title=data.get("Heading", query),
                        url=data.get("AbstractURL", ""),
                        snippet=data.get("Abstract", ""),
                        score=1.0,
                    )
                )

            # Add related topics
            for item in data.get("RelatedTopics", [])[:num_results]:
                if isinstance(item, dict) and "Text" in item:
                    results.append(
                        SearchResult(
                            title=item.get("Text", "")[:100],
                            url=item.get("FirstURL", ""),
                            snippet=item.get("Text", ""),
                            score=0.8,
                        )
                    )

            return results[:num_results]

        except Exception:
            return []

    async def search(
        self, query: str, num_results: int = 10
    ) -> dict[str, list[dict] | str]:
        """
        Search the web.

        Args:
            query: Search query
            num_results: Number of results to return

        Returns:
            Search results with status
        """
        try:
            # Try SearXNG first if configured
            results = []
            if self.searxng_url:
                results = await self._search_searxng(query, num_results)

            # Fallback to API provider if no results
            if not results and self.fallback_provider == "duckduckgo":
                results = await self._search_duckduckgo(query, num_results)

            # Convert to dict format
            results_dict = [
                {
                    "title": r.title,
                    "url": r.url,
                    "snippet": r.snippet,
                    "score": r.score,
                }
                for r in results
            ]

            return {
                "results": results_dict,
                "status": "success",
                "query": query,
            }

        except Exception as e:
            return {
                "results": [],
                "status": "error",
                "error": f"Search error: {e}",
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
                            "name": "web_search",
                            "description": "Search the web and return results",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "query": {
                                        "type": "string",
                                        "description": "Search query",
                                    },
                                    "num_results": {
                                        "type": "integer",
                                        "description": "Number of results to return (default: 10)",
                                        "default": 10,
                                    },
                                },
                                "required": ["query"],
                            },
                        }
                    ]
                },
            }

        # Handle tools/call
        if method == "tools/call":
            tool_name = params.get("name")
            arguments = params.get("arguments", {})

            if tool_name == "web_search":
                query = arguments.get("query", "")
                num_results = arguments.get("num_results", 10)
                result = await self.search(query, num_results)
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
    searxng_url = os.environ.get("SEARXNG_URL")
    fallback_provider = os.environ.get("SEARCH_FALLBACK_PROVIDER", "duckduckgo")
    timeout = float(os.environ.get("SEARCH_TIMEOUT", "30.0"))

    server = WebSearchServer(searxng_url, fallback_provider, timeout)
    await server.run()


if __name__ == "__main__":
    asyncio.run(main())
