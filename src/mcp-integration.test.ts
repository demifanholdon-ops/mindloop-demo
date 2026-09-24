import assert from "node:assert/strict";
import test from "node:test";
import path from "node:path";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

test("stdio server starts, lists four tools, and handles a missing key safely", async () => {
  const transport = new StdioClientTransport({
    command: process.execPath,
    args: [path.join(process.cwd(), "dist", "index.js")],
    env: { PATH: process.env.PATH ?? "" },
    stderr: "pipe",
  });
  const client = new Client({ name: "evomap-mcp-test", version: "1.0.0" });

  try {
    await client.connect(transport);
    const tools = await client.listTools();
    assert.deepEqual(
      tools.tools.map((tool) => tool.name).sort(),
      ["evomap_ingest", "evomap_my_graph", "evomap_query", "evomap_status"],
    );

    const result = await client.callTool({ name: "evomap_status", arguments: {} });
    assert.equal(result.isError, true);
    assert.match(JSON.stringify(result.content), /EVOMAP_API_KEY is not set/);
  } finally {
    await client.close();
  }
});
