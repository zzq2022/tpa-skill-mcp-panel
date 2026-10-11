import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { parseWireScalar } from "./model.js";
let cachedPresets = null;
export function loadBuiltinMcpPresets() {
    if (cachedPresets !== null)
        return cachedPresets;
    try {
        const currentDir = dirname(fileURLToPath(import.meta.url));
        const assetPath = join(currentDir, "../../assets/builtin-mcp.json");
        const raw = readFileSync(assetPath, "utf8");
        cachedPresets = JSON.parse(raw);
        return cachedPresets ?? [];
    }
    catch {
        return [];
    }
}
/** 把预设转为可以直接用于 save 的 McpServerInput（支持传入自定义 credentials 覆盖占位符）。 */
export function presetToServerInput(preset, credentialOverride) {
    if (preset.type === "stdio") {
        const env = {};
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
    const headers = {};
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
