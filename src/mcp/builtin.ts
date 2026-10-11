import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import type { McpServerInput } from "./model.js";
import { parseWireScalar } from "./model.js";

export interface McpPreset {
  id: string;
  name: string;
  displayName: string;
  category: string;
  description: string;
  requires: string;
  type: "stdio" | "streamableHttp" | "streamable-http";
  command?: string;
  args?: string[];
  url?: string;
  headers?: Record<string, string>;
  env?: Record<string, string>;
  connectTimeout?: number;
  toolTimeout?: number;
  enabledTools?: string[];
}

export interface McpPresetView extends McpPreset {
  configured: boolean;
  enabled: boolean;
}

let cachedPresets: McpPreset[] | null = null;

export function loadBuiltinMcpPresets(): McpPreset[] {
  if (cachedPresets !== null) return cachedPresets;
  try {
    const currentDir = dirname(fileURLToPath(import.meta.url));
    const assetPath = join(currentDir, "../../assets/builtin-mcp.json");
    const raw = readFileSync(assetPath, "utf8");
    cachedPresets = JSON.parse(raw);
    return cachedPresets ?? [];
  } catch {
    return [];
  }
}

/** 把预设转为可以直接用于 save 的 McpServerInput（支持传入自定义 credentials 覆盖占位符）。 */
export function presetToServerInput(preset: McpPreset, credentialOverride?: Record<string, string>): McpServerInput {
  if (preset.type === "stdio") {
    const env: Record<string, any> = {};
    for (const [k, v] of Object.entries(preset.env ?? {})) {
      env[k] = parseWireScalar(credentialOverride?.[k] ?? v);
    }
    return {
      serverName: preset.name,
      transport: "stdio",
      command: parseWireScalar(preset.command || "npx"),
      args: (preset.args || []).map((a) => parseWireScalar(a)),
      env,
      cwd: "",
      toolCallTimeoutMs: (preset.toolTimeout || 30) * 1000,
      failOnStartupError: false,
      reconnect: {
        enabled: true,
        initialDelayMs: 500,
        maxDelayMs: 30000,
        maxAttempts: 10
      }
    };
  }

  const headers: Record<string, any> = {};
  for (const [k, v] of Object.entries(preset.headers ?? {})) {
    headers[k] = parseWireScalar(credentialOverride?.[k] ?? v);
  }
  return {
    serverName: preset.name,
    transport: "streamable-http",
    url: parseWireScalar(preset.url || ""),
    headers,
    toolCallTimeoutMs: (preset.toolTimeout || 30) * 1000,
    failOnStartupError: false,
    reconnect: {
      enabled: true,
      initialDelayMs: 500,
      maxDelayMs: 30000,
      maxAttempts: 10
    }
  };
}
