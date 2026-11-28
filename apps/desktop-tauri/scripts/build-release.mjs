import { spawnSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { loadEnv } from "vite";

const appDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

function fail(message) {
  console.error(`\n[build-release] ${message}\n`);
  process.exit(1);
}

const fileEnv = loadEnv("production", appDir, "VITE_");
const base = (process.env.VITE_API_BASE || fileEnv.VITE_API_BASE || "").trim();

if (!base) {
  fail(
    [
      "没有配置云端地址：发布包不允许默认连本机，会被打成一个只能在本机跑的空壳。",
      "",
      "  PowerShell:  $env:VITE_API_BASE=\"http://<ECS 公网 IP>:8000\"; pnpm tauri build",
      "  bash:        VITE_API_BASE=http://<ECS 公网 IP>:8000 pnpm tauri build",
      "",
      "地址也可以写在 apps/desktop-tauri/.env.production 里。",
    ].join("\n")
  );
}

let url;
try {
  url = new URL(base);
} catch {
  fail(`VITE_API_BASE 不是合法地址：${base}`);
}

const loopback = ["localhost", "127.0.0.1", "::1", "[::1]"].includes(url.hostname);
if (loopback && process.env.ALLOW_LOCAL_API !== "1") {
  fail(
    [
      `云端地址是本机回环地址：${base}`,
      "发布包指向本机时，装到别的机器上一定连不上。",
      "确实要做本机联调包，显式加 ALLOW_LOCAL_API=1 再构建。",
    ].join("\n")
  );
}
if (!/^https?:$/.test(url.protocol)) {
  fail(`云端地址必须是 http 或 https：${base}`);
}

console.log(`[build-release] 云端地址：${url.origin}${url.pathname === "/" ? "" : url.pathname}`);

const build = spawnSync("pnpm", ["exec", "vite", "build"], {
  cwd: appDir,
  stdio: "inherit",
  shell: process.platform === "win32",
});
process.exit(build.status ?? 1);
