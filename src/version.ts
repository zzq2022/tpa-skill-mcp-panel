/**
 * dsh-skill-mcp-panel —— 版本与包名定义。
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

/** 本包名。 */
export const PACKAGE_NAME = "dsh-skill-mcp-panel";

/** 当前安装的插件版本；读取失败回退 0.0.0。 */
export function currentVersion(): string {
  try {
    const pkg = JSON.parse(readFileSync(fileURLToPath(new URL("../package.json", import.meta.url)), "utf8"));
    return typeof pkg.version === "string" ? pkg.version : "0.0.0";
  } catch {
    return "0.0.0";
  }
}

