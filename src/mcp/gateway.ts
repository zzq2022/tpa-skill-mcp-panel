/**
 * dsh-skill-mcp-panel —— MCP 宿主服务（mcpManager）。
 */
import { TypertRemoteService } from "@deepseek-ai/dsh-typert-protocol";
import { fileURLToPath } from "node:url";
import { join, resolve } from "node:path";
import {
  MCP_PLUGIN_NAME,
  extractManagedRows,
  listMcpPatchRows,
  readPatchFile,
  writeManagedRows,
  type PatchRow
} from "../patch-editor.js";
import {
  DEFAULT_RECONNECT,
  DEFAULT_TOOL_CALL_TIMEOUT_MS,
  applyServerEdit,
  describeSchemaError,
  inputFromPatchRow,
  mcpServerInputSchema,
  patchRowToView,
  rowIdForServerName,
  serverNameFromRowId,
  type McpServerInput
} from "./model.js";
import { mcpRemovePayloadSchema, mcpSavePayloadSchema, mcpSetEnabledPayloadSchema, mcpTestPayloadSchema } from "./wire.js";
import { fiberPhaseOf, getLoaderEntry, mcpToolCount, waitForLoaderState } from "./status.js";
import { probeMcpServer } from "./probe.js";
import { loadBuiltinMcpPresets } from "./builtin.js";

function stripUndefined(value: any): any {
  if (Array.isArray(value)) return value.map((item) => stripUndefined(item));
  if (value !== null && typeof value === "object") {
    const out: Record<string, unknown> = {};
    for (const [key, item] of Object.entries(value)) {
      if (item === undefined) continue;
      out[key] = stripUndefined(item);
    }
    return out;
  }
  return value;
}

const MANAGED_ROW_IDS = new Set<string>();

export function isBuiltinRow(row: PatchRow): boolean {
  return (typeof row.id === "string" && row.id.startsWith("panel-builtin-mcp-")) || (row.config as any)?.isBuiltin === true;
}

function isManagedRow(row: PatchRow): boolean {
  return typeof row.id === "string" && (row.id.startsWith("panel-mcp-") || row.id.startsWith("panel-builtin-mcp-"));
}

/**
 * handler 内校验 payload：失败抛「字段：原因」的中文错误。
 * 网关边界的 codec 是宽松 schema（见 wire.ts），校验必须在这里做，
 * 否则失败会退化成宿主那句泛化的 `failed boundary validation`。
 */
function parseWirePayload(schema: { safeParse: (value: unknown) => any }, raw: unknown, label: string): any {
  const result = schema.safeParse(raw);
  if (result.success) return result.data;
  throw new Error(label + "：" + describeSchemaError(result.error));
}

export class McpManagerGateway extends TypertRemoteService {
  constructor(ctx: any) {
    super(ctx, "mcpManager");
  }

  get C(): any {
    return this.ctx as any;
  }

  patchPath(): string {
    const base = this.C.baseUrl;
    if (typeof base === "string" && base.length > 0) {
      try {
        const url = new URL(base);
        if (url.protocol === "file:") return join(fileURLToPath(url), "cordis.patch.yml");
      } catch {
        // fall through to package-location fallback
      }
    }
    const packageDir = fileURLToPath(new URL("../../", import.meta.url));
    return join(resolve(packageDir, "../.."), "cordis.patch.yml");
  }

  async readRows() {
    const path = this.patchPath();
    const raw = await readPatchFile(path);
    const managed = extractManagedRows(raw);
    const allMcp = listMcpPatchRows(raw);
    const managedIds = new Set(managed.map((row) => row.id).filter((id): id is string => typeof id === "string"));
    const external = allMcp.filter((row) => typeof row.id === "string" && !managedIds.has(row.id));
    return { path, raw, managed, external };
  }

  decorate(row: PatchRow, managed: boolean, entry: any, enabled: boolean) {
    const view: any = patchRowToView(row);
    if (view === undefined) return undefined;
    const fiberPhase = fiberPhaseOf(entry?.fiber?.state);
    return stripUndefined({
      ...view,
      enabled,
      managed,
      fiberPhase,
      toolCount: enabled ? mcpToolCount(this.C, view.serverName) : 0
    });
  }

  async list() {
    let patch = { path: this.patchPath(), ok: false, error: null as string | null };
    try {
      const { path, managed, external } = await this.readRows();
      patch = { path, ok: true, error: null };
      const servers: any[] = [];
      for (const row of managed) {
        if (isBuiltinRow(row)) continue;
        const entry = typeof row.id === "string" ? getLoaderEntry(this.C, row.id) : undefined;
        const view = this.decorate(row, true, entry, row.disabled !== true);
        if (view !== undefined) servers.push(view);
      }
      const externalServers: any[] = [];
      for (const row of external) {
        const entry = typeof row.id === "string" ? getLoaderEntry(this.C, row.id) : undefined;
        const view = this.decorate(row, false, entry, row.disabled !== true);
        if (view !== undefined) externalServers.push(view);
      }
      const builtinPresets = loadBuiltinMcpPresets();
      let patchChanged = false;
      for (const preset of builtinPresets) {
        let found = managed.find((r) => isBuiltinRow(r) && (r.config?.serverName === preset.name || serverNameFromRowId(r.id) === preset.name));
        if (found === undefined) {
          const isHttp = preset.type === "streamable-http" || preset.type === "streamableHttp";
          found = {
            id: "panel-builtin-mcp-" + preset.name,
            name: MCP_PLUGIN_NAME,
            disabled: false,
            config: {
              serverName: preset.name,
              transport: isHttp ? "streamable-http" : "stdio",
              url: preset.url,
              command: preset.command,
              args: preset.args ?? [],
              headers: preset.headers ?? {},
              env: preset.env ?? {},
              toolCallTimeoutMs: (preset.toolTimeout ? preset.toolTimeout * 1000 : undefined) ?? DEFAULT_TOOL_CALL_TIMEOUT_MS,
              reconnect: { ...DEFAULT_RECONNECT },
              failOnStartupError: false,
              isBuiltin: true
            }
          };
          managed.push(found);
          patchChanged = true;
        }
      }
      if (patchChanged) {
        await writeManagedRows(path, managed);
      }

      const presets = builtinPresets.map((preset) => {
        const found = managed.find((r) => isBuiltinRow(r) && (r.config?.serverName === preset.name || serverNameFromRowId(r.id) === preset.name));
        const enabled = found !== undefined ? found.disabled !== true : true;
        const entry = found && typeof found.id === "string" ? getLoaderEntry(this.C, found.id) : undefined;
        const fiberPhase = entry?.phase ?? (enabled ? "active" : null);
        const toolCount = enabled ? mcpToolCount(this.C, preset.name) : 0;
        return {
          ...preset,
          configured: true,
          enabled,
          fiberPhase,
          toolCount
        };
      });
      return { servers, externalServers, presets, patch };
    } catch (error) {
      return { servers: [], externalServers: [], presets: loadBuiltinMcpPresets().map(p => ({ ...p, configured: true, enabled: false, toolCount: 0 })), patch: { ...patch, error: error instanceof Error ? error.message : String(error) } };
    }
  }

  findRowByServerName(rows: PatchRow[], serverName: string): PatchRow | undefined {
    return rows.find((row) => serverNameFromRowId(row.id) === serverName || (row.config?.serverName === serverName && isManagedRow(row)));
  }

  configInputFromRow(row: PatchRow): McpServerInput {
    return inputFromPatchRow(row);
  }

  async save(rawPayload: unknown) {
    const payload = parseWirePayload(mcpSavePayloadSchema, rawPayload, "MCP 配置无效");
    const input = payload.input;
    const previousName = payload.previousServerName ?? input.serverName;
    const { managed, external } = await this.readRows();

    for (const row of external) {
      const name = row.config?.serverName;
      if (name === input.serverName) throw new Error('serverName "' + input.serverName + '" 已被 cordis.patch.yml 中的外部 MCP 行占用，请在文件中手动处理');
    }
    for (const row of managed) {
      const name = row.config?.serverName;
      if (name === input.serverName && serverNameFromRowId(row.id) !== previousName) {
        throw new Error('serverName "' + input.serverName + '" 已存在（受管行 ' + String(row.id) + "）");
      }
    }

    const previous = managed.find((row) => serverNameFromRowId(row.id) === previousName || row.config?.serverName === previousName);
    if (payload.previousServerName !== undefined && previous === undefined) {
      throw new Error('要编辑的 MCP 行不存在："' + previousName + '"');
    }
    const enabled = previous !== undefined ? previous.disabled !== true : payload.enabled;
    const nextRow = applyServerEdit(previous, input, enabled);
    const nextRows = managed.filter((row) => serverNameFromRowId(row.id) !== previousName && row.config?.serverName !== previousName);
    nextRows.push(nextRow);
    nextRows.sort((a, b) => String(a.config?.serverName ?? "").localeCompare(String(b.config?.serverName ?? "")));
    await writeManagedRows(this.patchPath(), nextRows);

    const reconciled = enabled
      ? await waitForLoaderState(this.C, nextRow.id!, (entry) => entry !== undefined && entry.disabled !== true)
      : await waitForLoaderState(this.C, nextRow.id!, (entry) => entry !== undefined && entry.disabled === true);

    const entry = getLoaderEntry(this.C, nextRow.id!);
    const server = this.decorate(nextRow, true, entry, enabled);
    if (server === undefined) throw new Error("写入成功但生成的 MCP 行无效");
    return { server, reconciled };
  }

  async removeServer(rawPayload: unknown) {
    const payload = parseWirePayload(mcpRemovePayloadSchema, rawPayload, "删除参数无效");
    if (loadBuiltinMcpPresets().some((p) => p.name === payload.serverName)) {
      throw new Error('内置 MCP 服务 "' + payload.serverName + '" 为系统内置组件，禁止删除。如需停用请关闭启用开关。');
    }
    const { managed } = await this.readRows();
    const row = managed.find((candidate) => serverNameFromRowId(candidate.id) === payload.serverName || candidate.config?.serverName === payload.serverName);
    if (row === undefined) {
      throw new Error('MCP 行 "' + payload.serverName + '" 不存在或不是面板受管行（外部行请在 cordis.patch.yml 中手动删除）');
    }
    if (isBuiltinRow(row)) {
      throw new Error('内置 MCP 服务 "' + payload.serverName + '" 为系统内置组件，禁止删除。如需停用请关闭启用开关。');
    }
    const nextRows = managed.filter((candidate) => candidate !== row);
    await writeManagedRows(this.patchPath(), nextRows);
    const reconciled = await waitForLoaderState(this.C, row.id!, (entry) => entry === undefined);
    return { ok: true, reconciled };
  }

  async setEnabled(rawPayload: unknown) {
    const payload = parseWirePayload(mcpSetEnabledPayloadSchema, rawPayload, "启用参数无效");
    const { managed } = await this.readRows();
    const builtinPresets = loadBuiltinMcpPresets();
    const preset = builtinPresets.find((p) => p.name === payload.serverName);
    if (preset !== undefined) {
      let row = managed.find((r) => isBuiltinRow(r) && (r.config?.serverName === preset.name || serverNameFromRowId(r.id) === preset.name));
      if (row === undefined) {
        if (!payload.enabled) {
          return {
            server: {
              serverName: preset.name,
              transport: preset.type === "streamable-http" || preset.type === "streamableHttp" ? "streamable-http" : "stdio",
              enabled: false,
              envKeys: Object.keys(preset.env ?? {}),
              headerKeys: Object.keys(preset.headers ?? {}),
              toolCallTimeoutMs: (preset.toolTimeout ? preset.toolTimeout * 1000 : undefined) ?? DEFAULT_TOOL_CALL_TIMEOUT_MS,
              failOnStartupError: false,
              reconnect: { ...DEFAULT_RECONNECT },
              managed: true,
              fiberPhase: null,
              toolCount: 0
            },
            reconciled: true
          };
        }
        const isHttp = preset.type === "streamable-http" || preset.type === "streamableHttp";
        row = {
          id: "panel-builtin-mcp-" + preset.name,
          name: MCP_PLUGIN_NAME,
          disabled: false,
          config: {
            serverName: preset.name,
            transport: isHttp ? "streamable-http" : "stdio",
            url: preset.url,
            command: preset.command,
            args: preset.args ?? [],
            headers: preset.headers ?? {},
            env: preset.env ?? {},
            toolCallTimeoutMs: (preset.toolTimeout ? preset.toolTimeout * 1000 : undefined) ?? DEFAULT_TOOL_CALL_TIMEOUT_MS,
            reconnect: { ...DEFAULT_RECONNECT },
            failOnStartupError: false,
            isBuiltin: true
          }
        };
        managed.push(row);
      } else {
        row.disabled = !payload.enabled;
        const isHttp = preset.type === "streamable-http" || preset.type === "streamableHttp";
        row.config = {
          ...row.config,
          url: preset.url,
          command: preset.command,
          args: preset.args ?? [],
          headers: preset.headers ?? {},
          env: preset.env ?? {},
          isBuiltin: true
        };
      }
      await writeManagedRows(this.patchPath(), managed);
      const reconciled = payload.enabled
        ? await waitForLoaderState(this.C, row.id!, (entry) => entry !== undefined && entry.disabled !== true)
        : await waitForLoaderState(this.C, row.id!, (entry) => entry !== undefined && entry.disabled === true);
      const entry = getLoaderEntry(this.C, row.id!);
      const server = this.decorate(row, true, entry, payload.enabled);
      if (server === undefined) throw new Error("写入成功但生成的 MCP 行无效");
      return { server, reconciled };
    }

    const row = managed.find((candidate) => serverNameFromRowId(candidate.id) === payload.serverName || candidate.config?.serverName === payload.serverName);
    if (row === undefined) throw new Error('MCP 行 "' + payload.serverName + '" 不存在或不是面板受管行');
    row.disabled = !payload.enabled;
    await writeManagedRows(this.patchPath(), managed);
    const reconciled = payload.enabled
      ? await waitForLoaderState(this.C, row.id!, (entry) => entry !== undefined && entry.disabled !== true)
      : await waitForLoaderState(this.C, row.id!, (entry) => entry !== undefined && entry.disabled === true);
    const entry = getLoaderEntry(this.C, row.id!);
    const server = this.decorate(row, true, entry, payload.enabled);
    if (server === undefined) throw new Error("写入成功但生成的 MCP 行无效");
    return { server, reconciled };
  }

  async test(rawPayload: unknown) {
    const payload = parseWirePayload(mcpTestPayloadSchema, rawPayload, "测试参数无效");
    if (payload !== null && typeof payload === "object" && !("transport" in payload) && "serverName" in payload) {
      const preset = loadBuiltinMcpPresets().find((p) => p.name === payload.serverName);
      if (preset !== undefined) {
        const isHttp = preset.type === "streamable-http" || preset.type === "streamableHttp";
        return probeMcpServer({
          serverName: preset.name,
          transport: isHttp ? "streamable-http" : "stdio",
          url: preset.url,
          command: preset.command,
          args: preset.args ?? [],
          headers: preset.headers ?? {},
          env: preset.env ?? {},
          toolCallTimeoutMs: (preset.toolTimeout ? preset.toolTimeout * 1000 : undefined) ?? DEFAULT_TOOL_CALL_TIMEOUT_MS,
          reconnect: { ...DEFAULT_RECONNECT },
          failOnStartupError: false
        });
      }
      const { managed, external } = await this.readRows();
      const row = [...managed, ...external].find((candidate) => candidate.config?.serverName === payload.serverName || serverNameFromRowId(candidate.id) === payload.serverName);
      if (row !== undefined) {
        return probeMcpServer(this.configInputFromRow(row));
      }
      throw new Error('MCP 行 "' + String(payload.serverName) + '" 不存在');
    }
    return probeMcpServer(payload);
  }

  reload() {
    return this.list();
  }
}

// 供 CLI 复用：判断一个 patch 行是否由面板管理。
export { MANAGED_ROW_IDS, isManagedRow, MCP_PLUGIN_NAME };
