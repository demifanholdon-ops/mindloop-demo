import { execFileSync } from "node:child_process";
import { EvoMapClient } from "../dist/evomap-client.js";

let apiKey = process.env.EVOMAP_API_KEY ?? "";
let source = apiKey ? "shell" : "missing";

if (!apiKey && process.platform === "darwin") {
  try {
    apiKey = execFileSync("launchctl", ["getenv", "EVOMAP_API_KEY"], {
      encoding: "utf8",
      stdio: ["ignore", "pipe", "ignore"],
    }).trim();
    if (apiKey) source = "launchctl";
  } catch {
    // The final missing-variable result below is sufficient.
  }
}

if (!apiKey) {
  console.error("EVOMAP_API_KEY: missing (checked shell and macOS launchctl)");
  process.exit(1);
}

if (!/^ek_[0-9a-f]{48}$/i.test(apiKey)) {
  console.error(`EVOMAP_API_KEY: present via ${source}, but not a KG key (expected ek_ + 48 hexadecimal characters)`);
  process.exit(1);
}

const result = await new EvoMapClient({ apiKey }).status();
const data = result.data && typeof result.data === "object" ? result.data : {};
console.log(
  JSON.stringify({
    key_source: source,
    key_format: "valid",
    http_status: result.status,
    ok: result.ok,
    error_code: data.error ?? data.code ?? null,
    response_keys: Object.keys(data),
  }),
);
process.exit(result.ok ? 0 : 1);
