import assert from "node:assert/strict";
import { PACKAGE_NAME, currentVersion } from "./lib/version.js";

let passed = 0;
function pass(name) {
  passed += 1;
  console.log("PASS  " + name);
}

// 1. PACKAGE_NAME
assert.equal(PACKAGE_NAME, "dsh-skill-mcp-panel");
pass("PACKAGE_NAME matches package");

// 2. currentVersion
const version = currentVersion();
assert.equal(typeof version, "string");
assert.match(version, /^\d+\.\d+\.\d+/);
pass("currentVersion returns valid semver string: " + version);

console.log("\n" + passed + " passed, 0 failed");
console.log("ALL VERSION TESTS PASSED");
