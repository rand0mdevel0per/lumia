/**
 * Lumia Plugin Registry - Cloudflare Worker
 *
 * Provides plugin metadata and search API for pm CLI.
 */

interface Env {
  ENVIRONMENT: string;
}

interface PluginMetadata {
  name: string;
  version: string;
  description: string;
  git_url: string;
  author: string;
  tags: string[];
}

// Mock plugin database (replace with KV or D1 in production)
const PLUGINS: PluginMetadata[] = [
  {
    name: "qq-adapter",
    version: "1.0.0",
    description: "QQ adapter for Lumia (NapCat/Lagrange + OneBot v11)",
    git_url: "https://github.com/lumia-plugins/qq-adapter.git",
    author: "lumia-team",
    tags: ["adapter", "qq", "onebot"],
  },
];

/**
 * Handle search request.
 */
function handleSearch(query: string): Response {
  const lowerQuery = query.toLowerCase();
  const results = PLUGINS.filter(
    (p) =>
      p.name.toLowerCase().includes(lowerQuery) ||
      p.description.toLowerCase().includes(lowerQuery) ||
      p.tags.some((t) => t.toLowerCase().includes(lowerQuery))
  );

  return new Response(JSON.stringify({ results }), {
    headers: {
      "Content-Type": "application/json",
      "Access-Control-Allow-Origin": "*",
    },
  });
}

/**
 * Handle plugin info request.
 */
function handlePluginInfo(name: string): Response {
  const plugin = PLUGINS.find((p) => p.name === name);

  if (!plugin) {
    return new Response(JSON.stringify({ error: "Plugin not found" }), {
      status: 404,
      headers: {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*",
      },
    });
  }

  return new Response(JSON.stringify(plugin), {
    headers: {
      "Content-Type": "application/json",
      "Access-Control-Allow-Origin": "*",
    },
  });
}

/**
 * Main fetch handler.
 */
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // Handle CORS preflight
    if (request.method === "OPTIONS") {
      return new Response(null, {
        headers: {
          "Access-Control-Allow-Origin": "*",
          "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
          "Access-Control-Allow-Headers": "Content-Type",
        },
      });
    }

    // Route requests
    if (url.pathname === "/search" && request.method === "GET") {
      const query = url.searchParams.get("q") || "";
      return handleSearch(query);
    }

    if (url.pathname.startsWith("/plugin/") && request.method === "GET") {
      const name = url.pathname.split("/")[2];
      return handlePluginInfo(name);
    }

    // Root endpoint
    if (url.pathname === "/" && request.method === "GET") {
      return new Response(
        JSON.stringify({
          name: "Lumia Plugin Registry",
          version: "0.1.0",
          endpoints: {
            search: "/search?q=<query>",
            plugin: "/plugin/<name>",
          },
        }),
        {
          headers: {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
          },
        }
      );
    }

    // 404
    return new Response(JSON.stringify({ error: "Not found" }), {
      status: 404,
      headers: {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*",
      },
    });
  },
};
