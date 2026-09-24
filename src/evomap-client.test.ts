import assert from "node:assert/strict";
import test from "node:test";
import { EvoMapClient } from "./evomap-client.js";

test("query sends a bearer-authenticated POST request", async () => {
  const apiKey = `ek_${"a".repeat(48)}`;
  const fetchImpl: typeof fetch = async (input, init) => {
    assert.equal(input, "https://example.test/kg/query");
    assert.equal(init?.method, "POST");
    assert.equal(new Headers(init?.headers).get("authorization"), `Bearer ${apiKey}`);
    assert.deepEqual(JSON.parse(String(init?.body)), {
      query: "retry strategy",
      type: "semantic",
      limit: 3,
    });
    return Response.json({ nodes: [] }, { headers: { "x-request-id": "req-123" } });
  };

  const client = new EvoMapClient({ apiKey, baseUrl: "https://example.test", fetchImpl });
  const result = await client.query("retry strategy", "semantic", { limit: 3 });

  assert.equal(result.ok, true);
  assert.equal(result.status, 200);
  assert.equal(result.requestId, "req-123");
  assert.deepEqual(result.data, { nodes: [] });
});

test("ingest forwards the payload unchanged", async () => {
  const payload = { name: "REST API", type: "concept", description: "An interface style" };
  const fetchImpl: typeof fetch = async (_input, init) => {
    assert.deepEqual(JSON.parse(String(init?.body)), payload);
    return Response.json({ accepted: true });
  };

  const client = new EvoMapClient({ apiKey: `ek_${"b".repeat(48)}`, baseUrl: "https://example.test", fetchImpl });
  const result = await client.ingest(payload);
  assert.deepEqual(result.data, { accepted: true });
});

test("status and my-graph use GET without a request body", async () => {
  const paths: string[] = [];
  const fetchImpl: typeof fetch = async (input, init) => {
    paths.push(String(input));
    assert.equal(init?.method, "GET");
    assert.equal(init?.body, undefined);
    return Response.json({ ok: true });
  };

  const client = new EvoMapClient({ apiKey: `ek_${"c".repeat(48)}`, baseUrl: "https://example.test/", fetchImpl });
  await client.status();
  await client.myGraph();

  assert.deepEqual(paths, ["https://example.test/kg/status", "https://example.test/kg/my-graph"]);
});

test("missing API key fails without making a network request", async () => {
  const client = new EvoMapClient({ apiKey: "" });
  await assert.rejects(() => client.status(), /EVOMAP_API_KEY is not set/);
});

test("a non-KG key format fails before making a network request", async () => {
  let requested = false;
  const fetchImpl: typeof fetch = async () => {
    requested = true;
    return Response.json({});
  };
  const client = new EvoMapClient({ apiKey: "sk-evomap-not-a-kg-key", fetchImpl });

  await assert.rejects(() => client.status(), /wrong format for the Knowledge Graph API/);
  assert.equal(requested, false);
});
