import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import { EvoMapClient, type EvoMapResponse, type JsonObject } from "./evomap-client.js";

export function createServer(client = new EvoMapClient()): McpServer {
  const server = new McpServer(
    { name: "evomap", version: "1.0.0" },
    {
      instructions:
        "EvoMap Knowledge Graph tools. Query and ingest operations consume account credits; status and my-graph are free. Never place an API key in tool arguments. Use evomap_status before paid operations when account entitlement or balance is uncertain.",
    },
  );

  server.registerTool(
    "evomap_query",
    {
      title: "Query EvoMap Knowledge Graph",
      description:
        "POST /kg/query. Semantic search against the authenticated user's EvoMap knowledge graph. This operation consumes credits.",
      inputSchema: {
        query: z.string().min(1).describe("Natural-language query."),
        type: z.string().min(1).default("semantic").describe("EvoMap query type; defaults to semantic."),
        options: z
          .record(z.string(), z.unknown())
          .default({})
          .describe("Optional additional EvoMap request fields, forwarded at the top level."),
      },
    },
    async ({ query, type, options }) => asToolResult(() => client.query(query, type, options)),
  );

  server.registerTool(
    "evomap_ingest",
    {
      title: "Ingest into EvoMap Knowledge Graph",
      description:
        "POST /kg/ingest. Writes entities and relationships to the authenticated user's EvoMap graph. The payload is forwarded unchanged and this operation consumes credits.",
      inputSchema: {
        payload: z
          .record(z.string(), z.unknown())
          .describe("JSON object accepted by EvoMap /kg/ingest, such as entity or relationship fields."),
      },
    },
    async ({ payload }) => asToolResult(() => client.ingest(payload)),
  );

  server.registerTool(
    "evomap_status",
    {
      title: "Get EvoMap Knowledge Graph Status",
      description: "GET /kg/status. Returns usage, pricing, balance, and entitlement information. This operation is free.",
      inputSchema: {},
    },
    async () => asToolResult(() => client.status()),
  );

  server.registerTool(
    "evomap_my_graph",
    {
      title: "Get My EvoMap Graph",
      description:
        "GET /kg/my-graph. Returns the authenticated user's aggregated Neo4j and EvoMap platform graph. This operation is free.",
      inputSchema: {},
    },
    async () => asToolResult(() => client.myGraph()),
  );

  return server;
}

async function asToolResult(operation: () => Promise<EvoMapResponse>) {
  try {
    const response = await operation();
    const envelope: JsonObject = {
      http_status: response.status,
      ...(response.requestId ? { request_id: response.requestId } : {}),
      data: response.data,
    };

    return {
      content: [{ type: "text" as const, text: JSON.stringify(envelope, null, 2) }],
      structuredContent: envelope,
      isError: !response.ok,
    };
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    return {
      content: [{ type: "text" as const, text: message }],
      structuredContent: { error: message },
      isError: true,
    };
  }
}
