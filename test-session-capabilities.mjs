/**
 * 会话级能力选择器（Session Capability Picker）单元与契约测试
 */
import assert from "node:assert/strict";

let failures = 0;
const check = (label, fn) => {
  try {
    fn();
    console.log("PASS  " + label);
  } catch (error) {
    failures += 1;
    console.log("FAIL  " + label + "\n      " + (error && error.message ? error.message : error));
  }
};

// ── 模拟 localStorage ────────────────────────────────────────────────────────
const mockStorage = new Map();
const localStorageStub = {
  getItem: (key) => mockStorage.get(key) ?? null,
  setItem: (key, val) => mockStorage.set(key, String(val)),
  removeItem: (key) => mockStorage.delete(key),
  clear: () => mockStorage.clear()
};

// ── 能力选择器核心逻辑 ────────────────────────────────────────────────────────
const CAP_STORAGE_PREFIX = "dsh-panel:session-capabilities:";

function getStorageKey(sessionId) {
  return CAP_STORAGE_PREFIX + (sessionId && sessionId.trim() ? sessionId.trim() : "default");
}

function readSessionCapabilities(sessionId, storage = localStorageStub) {
  try {
    const raw = storage.getItem(getStorageKey(sessionId));
    if (!raw) return { skills: [], mcps: [] };
    const parsed = JSON.parse(raw);
    return {
      skills: Array.isArray(parsed?.skills) ? parsed.skills : [],
      mcps: Array.isArray(parsed?.mcps) ? parsed.mcps : []
    };
  } catch {
    return { skills: [], mcps: [] };
  }
}

function writeSessionCapabilities(sessionId, caps, storage = localStorageStub) {
  try {
    const key = getStorageKey(sessionId);
    const skills = Array.isArray(caps?.skills) ? [...new Set(caps.skills.filter(Boolean))] : [];
    const mcps = Array.isArray(caps?.mcps) ? [...new Set(caps.mcps.filter(Boolean))] : [];
    if (skills.length === 0 && mcps.length === 0) {
      storage.removeItem(key);
    } else {
      storage.setItem(key, JSON.stringify({ skills, mcps, updatedAt: Date.now() }));
    }
  } catch {}
}

function removeCapability(sessionId, type, name, storage = localStorageStub) {
  const current = readSessionCapabilities(sessionId, storage);
  if (type === "skill") {
    current.skills = current.skills.filter((s) => s !== name);
  } else if (type === "mcp") {
    current.mcps = current.mcps.filter((m) => m !== name);
  }
  writeSessionCapabilities(sessionId, current, storage);
  return readSessionCapabilities(sessionId, storage);
}

// ── 测试用例 ────────────────────────────────────────────────────────────────

check("默认情况下读取会话能力返回空数组", () => {
  localStorageStub.clear();
  const caps = readSessionCapabilities("sess-1");
  assert.deepEqual(caps, { skills: [], mcps: [] });
});

check("写入会话能力后能正确读取，且会话之间严格隔离", () => {
  localStorageStub.clear();
  writeSessionCapabilities("sess-1", { skills: ["grill-me", "tdd"], mcps: ["github"] });
  writeSessionCapabilities("sess-2", { skills: ["hyperframes"], mcps: [] });

  const caps1 = readSessionCapabilities("sess-1");
  const caps2 = readSessionCapabilities("sess-2");
  const caps3 = readSessionCapabilities("sess-unknown");

  assert.deepEqual(caps1.skills, ["grill-me", "tdd"]);
  assert.deepEqual(caps1.mcps, ["github"]);

  assert.deepEqual(caps2.skills, ["hyperframes"]);
  assert.deepEqual(caps2.mcps, []);

  assert.deepEqual(caps3, { skills: [], mcps: [] });
});

check("单项移除能力（点击 Chip 的 ×）能够即时更新存储", () => {
  localStorageStub.clear();
  writeSessionCapabilities("sess-1", { skills: ["skill-a", "skill-b"], mcps: ["mcp-1", "mcp-2"] });

  const updated1 = removeCapability("sess-1", "skill", "skill-a");
  assert.deepEqual(updated1.skills, ["skill-b"]);
  assert.deepEqual(updated1.mcps, ["mcp-1", "mcp-2"]);

  const updated2 = removeCapability("sess-1", "mcp", "mcp-1");
  assert.deepEqual(updated2.skills, ["skill-b"]);
  assert.deepEqual(updated2.mcps, ["mcp-2"]);
});

check("清空全部能力后自动移除 localStorage key", () => {
  localStorageStub.clear();
  writeSessionCapabilities("sess-1", { skills: ["grill-me"], mcps: [] });
  assert.ok(mockStorage.has(getStorageKey("sess-1")));

  writeSessionCapabilities("sess-1", { skills: [], mcps: [] });
  assert.equal(mockStorage.has(getStorageKey("sess-1")), false);
});

check("异常 JSON 容错降级为空对象", () => {
  localStorageStub.clear();
  mockStorage.set(getStorageKey("corrupt"), "{ bad json ... ");
  const caps = readSessionCapabilities("corrupt");
  assert.deepEqual(caps, { skills: [], mcps: [] });
});

// ── 模拟菜单结构与排版测试 ──────────────────────────────────────────────────
check("菜单注入严格位于「指令」上方，且顺序为技能、MCP", () => {
  // 模拟一个包含 添加、文件、反馈、指令、压缩 的 DOM 节点树
  const createMockNode = (tag, text = "", attrs = {}) => {
    const children = [];
    return {
      nodeType: 1,
      tagName: tag.toUpperCase(),
      textContent: text,
      attributes: { ...attrs },
      children,
      parentElement: null,
      getAttribute(k) { return this.attributes[k] ?? null; },
      setAttribute(k, v) { this.attributes[k] = String(v); },
      querySelector(sel) {
        if (sel === "[data-dsh-injected-cap='true']") {
          return children.find((c) => c.getAttribute("data-dsh-injected-cap") === "true") ?? null;
        }
        if (sel === "[role='menuitem']") {
          return children.find((c) => c.getAttribute("role") === "menuitem") ?? null;
        }
        return null;
      },
      appendChild(child) {
        child.parentElement = this;
        children.push(child);
      },
      insertBefore(newChild, refChild) {
        newChild.parentElement = this;
        const idx = children.indexOf(refChild);
        if (idx >= 0) children.splice(idx, 0, newChild);
        else children.push(newChild);
      }
    };
  };

  const menu = createMockNode("div", "", { role: "menu" });
  const itemFile = createMockNode("div", "文件 file", { role: "menuitem" });
  const itemFeedback = createMockNode("div", "反馈 feedback", { role: "menuitem" });
  const headerZhiling = createMockNode("div", "指令");
  const itemCompact = createMockNode("div", "压缩 compact", { role: "menuitem" });

  menu.appendChild(itemFile);
  menu.appendChild(itemFeedback);
  menu.appendChild(headerZhiling);
  menu.appendChild(itemCompact);

  // 模拟注入逻辑：找到「指令」并向前插入
  const zhilingIndex = menu.children.indexOf(headerZhiling);
  assert.equal(zhilingIndex, 2);

  const itemSkill = createMockNode("div", "技能 skill", { role: "menuitem", "data-dsh-injected-cap": "true" });
  const itemMcp = createMockNode("div", "MCP mcp", { role: "menuitem", "data-dsh-injected-cap": "true" });

  menu.insertBefore(itemSkill, headerZhiling);
  menu.insertBefore(itemMcp, headerZhiling);

  const labels = menu.children.map((c) => c.textContent);
  assert.deepEqual(labels, [
    "文件 file",
    "反馈 feedback",
    "技能 skill",
    "MCP mcp",
    "指令",
    "压缩 compact"
  ]);

  // 验证「指令」前面的两项必须是技能与 MCP
  const newZhilingIdx = menu.children.indexOf(headerZhiling);
  assert.equal(menu.children[newZhilingIdx - 2].textContent, "技能 skill");
  assert.equal(menu.children[newZhilingIdx - 1].textContent, "MCP mcp");
});

// ── MCP 聚合与搜索契约测试 ──────────────────────────────────────────────────
function aggregateMcps(mcpsRes) {
  const mcpList = [];
  const seenMcp = new Set();

  for (const s of (Array.isArray(mcpsRes?.servers) ? mcpsRes.servers : [])) {
    const sName = s.serverName || s.name || s.id;
    if (!sName || seenMcp.has(sName)) continue;
    seenMcp.add(sName);
    mcpList.push({
      serverName: sName,
      displayName: s.displayName || sName,
      rawName: sName,
      description: s.description || "",
      transport: s.transport === "streamable-http" ? "HTTP" : (s.transport === "stdio" ? "STDIO" : (s.transport || "MCP")),
      toolCount: s.toolCount,
      scopeLabel: "自定义",
      isBuiltin: false
    });
  }

  for (const s of (Array.isArray(mcpsRes?.externalServers) ? mcpsRes.externalServers : [])) {
    const sName = s.serverName || s.name || s.id;
    if (!sName || seenMcp.has(sName)) continue;
    seenMcp.add(sName);
    mcpList.push({
      serverName: sName,
      displayName: s.displayName || sName,
      rawName: sName,
      description: s.description || "",
      transport: s.transport === "streamable-http" ? "HTTP" : (s.transport === "stdio" ? "STDIO" : (s.transport || "MCP")),
      toolCount: s.toolCount,
      scopeLabel: "外部",
      isBuiltin: false
    });
  }

  for (const p of (Array.isArray(mcpsRes?.presets) ? mcpsRes.presets : [])) {
    const sName = p.name || p.serverName || p.id;
    if (!sName || seenMcp.has(sName)) continue;
    seenMcp.add(sName);
    const isHttp = p.type === "streamable-http" || p.type === "streamableHttp";
    mcpList.push({
      serverName: sName,
      displayName: p.displayName ? `${p.displayName} (${sName})` : sName,
      rawName: p.displayName || sName,
      description: p.description || "",
      transport: isHttp ? "HTTP" : "STDIO",
      toolCount: p.toolCount,
      scopeLabel: "内置",
      isBuiltin: true
    });
  }
  return mcpList;
}

function filterMcps(allMcps, query) {
  const q = query.trim().toLowerCase();
  return allMcps.filter((m) => {
    const name = (m.serverName || "").toLowerCase();
    const disp = (m.displayName || m.rawName || "").toLowerCase();
    const desc = (m.description || "").toLowerCase();
    return name.includes(q) || disp.includes(q) || desc.includes(q);
  });
}

check("新安装插件时（servers 为空），内置与外部 MCP 均能在清单中列出", () => {
  const mcpsRes = {
    servers: [],
    externalServers: [{ serverName: "amap-maps", transport: "streamable-http", toolCount: 15 }],
    presets: [
      { id: "juyuan", name: "juyuan", displayName: "聚源智能助手", description: "金融数据分析", type: "streamableHttp" },
      { id: "playwright", name: "playwright", displayName: "Playwright", description: "浏览器自动化", type: "stdio" }
    ]
  };

  const aggregated = aggregateMcps(mcpsRes);
  assert.equal(aggregated.length, 3);
  assert.equal(aggregated[0].serverName, "amap-maps");
  assert.equal(aggregated[0].scopeLabel, "外部");
  assert.equal(aggregated[1].serverName, "juyuan");
  assert.equal(aggregated[1].scopeLabel, "内置");
  assert.equal(aggregated[1].isBuiltin, true);
  assert.equal(aggregated[2].serverName, "playwright");
  assert.equal(aggregated[2].scopeLabel, "内置");
});

check("MCP 模糊搜索支持中文名称、服务标识和描述文本匹配", () => {
  const mcpsRes = {
    servers: [{ serverName: "custom-db", displayName: "数据库查询服务", description: "MySQL/PostgreSQL 连接", transport: "stdio" }],
    externalServers: [],
    presets: [
      { id: "hexin-stock", name: "hexin-ifind-ds-stock-mcp", displayName: "同花顺 iFinD 股票", description: "A股、港股行情", type: "streamableHttp" },
      { id: "playwright", name: "playwright", displayName: "Playwright 浏览器自动化", description: "网页访问与截图", type: "stdio" }
    ]
  };

  const aggregated = aggregateMcps(mcpsRes);

  // 1. 中文名匹配
  const resZh = filterMcps(aggregated, "同花顺");
  assert.equal(resZh.length, 1);
  assert.equal(resZh[0].serverName, "hexin-ifind-ds-stock-mcp");

  // 2. 英文服务名匹配
  const resEn = filterMcps(aggregated, "playwright");
  assert.equal(resEn.length, 1);
  assert.equal(resEn[0].serverName, "playwright");

  // 3. 描述文本匹配
  const resDesc = filterMcps(aggregated, "MySQL");
  assert.equal(resDesc.length, 1);
  assert.equal(resDesc[0].serverName, "custom-db");

  // 4. 空关键词匹配全部
  const resAll = filterMcps(aggregated, "");
  assert.equal(resAll.length, 3);
});

if (failures > 0) {
  process.exit(1);
} else {
  console.log("\nALL SESSION CAPABILITY LOGIC AND DOM TESTS PASSED\n");
}

