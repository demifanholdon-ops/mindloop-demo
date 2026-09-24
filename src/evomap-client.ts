export type JsonObject = Record<string, unknown>;

export interface EvoMapClientOptions {
  apiKey?: string;
  baseUrl?: string;
  timeoutMs?: number;
  fetchImpl?: typeof fetch;
}

export interface EvoMapResponse {
  ok: boolean;
  status: number;
  requestId?: string;
  data: unknown;
}

const DEFAULT_BASE_URL = "https://evomap.ai";
const DEFAULT_TIMEOUT_MS = 30_000;

export class EvoMapClient {
  private readonly apiKey?: string;
  private readonly baseUrl: string;
  private readonly timeoutMs: number;
  private readonly fetchImpl: typeof fetch;

  constructor(options: EvoMapClientOptions = {}) {
    this.apiKey = options.apiKey ?? process.env.EVOMAP_API_KEY;
    this.baseUrl = (options.baseUrl ?? process.env.EVOMAP_BASE_URL ?? DEFAULT_BASE_URL).replace(/\/$/, "");
    this.timeoutMs = options.timeoutMs ?? parseTimeout(process.env.EVOMAP_TIMEOUT_MS);
    this.fetchImpl = options.fetchImpl ?? fetch;
  }

  query(query: string, type = "semantic", options: JsonObject = {}): Promise<EvoMapResponse> {
    return this.request("POST", "/kg/query", { query, type, ...options });
  }

  ingest(payload: JsonObject): Promise<EvoMapResponse> {
    return this.request("POST", "/kg/ingest", payload);
  }

  status(): Promise<EvoMapResponse> {
    return this.request("GET", "/kg/status");
  }

  myGraph(): Promise<EvoMapResponse> {
    return this.request("GET", "/kg/my-graph");
  }

  private async request(method: "GET" | "POST", path: string, body?: JsonObject): Promise<EvoMapResponse> {
    if (!this.apiKey) {
      throw new Error(
        "EVOMAP_API_KEY is not set. Add it to the local environment, then restart VS Code so Codex can inherit it.",
      );
    }
    if (!/^ek_[0-9a-f]{48}$/i.test(this.apiKey)) {
      throw new Error(
        "EVOMAP_API_KEY has the wrong format for the Knowledge Graph API. The current EvoMap documentation requires ek_ followed by 48 hexadecimal characters.",
      );
    }

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), this.timeoutMs);

    try {
      const response = await this.fetchImpl(`${this.baseUrl}${path}`, {
        method,
        headers: {
          Accept: "application/json",
          Authorization: `Bearer ${this.apiKey}`,
          ...(body ? { "Content-Type": "application/json" } : {}),
        },
        body: body ? JSON.stringify(body) : undefined,
        signal: controller.signal,
      });

      const text = await response.text();
      let data: unknown = null;
      if (text) {
        try {
          data = JSON.parse(text);
        } catch {
          data = text;
        }
      }

      return {
        ok: response.ok,
        status: response.status,
        requestId: response.headers.get("x-request-id") ?? undefined,
        data,
      };
    } catch (error) {
      if (error instanceof Error && error.name === "AbortError") {
        throw new Error(`EvoMap request timed out after ${this.timeoutMs} ms.`);
      }
      throw error;
    } finally {
      clearTimeout(timeout);
    }
  }
}

function parseTimeout(value: string | undefined): number {
  if (!value) return DEFAULT_TIMEOUT_MS;
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : DEFAULT_TIMEOUT_MS;
}
