import assert from "node:assert/strict";
import { loadBuiltinMcpPresets } from "./lib/mcp/builtin.js";
import { McpManagerGateway } from "./lib/mcp/gateway.js";
import { Context } from "@deepseek-ai/cordis";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { pathToFileURL } from "node:url";

console.log("Testing builtin presets loader and gateway integration...");

// 1. Verify 11 presets load cleanly
const presets = loadBuiltinMcpPresets();
assert.equal(presets.length, 11, "Should load 11 presets from assets/builtin-mcp.json");
console.log("PASS  Loaded 11 builtin presets from assets/builtin-mcp.json");

// Verify preset fields
const ifindStock = presets.find((p) => p.name === "hexin-ifind-ds-stock-mcp");
assert.ok(ifindStock, "Should contain hexin-ifind-ds-stock-mcp");
assert.equal(ifindStock.category, "finance");
assert.equal(ifindStock.type, "streamableHttp");
assert.ok(ifindStock.requires.includes("IFIND_MCP_API_KEY"));

const playwright = presets.find((p) => p.name === "playwright");
assert.ok(playwright, "Should contain playwright");
assert.equal(playwright.type, "stdio");
assert.equal(playwright.command, "npx");
console.log("PASS  Verified preset schema properties for hexin-ifind-ds-stock-mcp & playwright");

// 2. Gateway list returns presets
const dir = await mkdtemp(join(tmpdir(), "dsh-panel-presets-"));
try {
  await writeFile(join(dir, "cordis.patch.yml"), "# profile\n[]\n");
  const ctx = new Context();
  ctx.baseUrl = pathToFileURL(dir).href + "/";
  ctx.effect = () => {};
  const gateway = new McpManagerGateway(ctx);
  const listRes = await gateway.list();
  assert.ok(Array.isArray(listRes.presets), "gateway.list() should return presets array");
  assert.equal(listRes.presets.length, 11, "gateway.list() should return 11 presets");
  assert.equal(listRes.presets[0].configured, true, "Presets are fully configured out-of-the-box");
  assert.equal(listRes.presets[0].enabled, false, "Presets should default to disabled unless activated");
  console.log("PASS  Gateway returns all 11 presets with configured=true & enabled=false status");
} finally {
  await rm(dir, { recursive: true, force: true });
}

console.log("\nALL BUILTIN PRESET TESTS PASSED!");
