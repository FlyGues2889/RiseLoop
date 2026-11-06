#!/usr/bin/env node
import { spawn } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const API_DIR = resolve(ROOT, "apps", "cloud-api");
const DESKTOP_DIR = resolve(ROOT, "apps", "desktop-tauri");
const HEALTH_URL = "http://127.0.0.1:8000/health/live";
const SERVICE_NAME = "Rise Loop Cloud API";
const IS_WINDOWS = process.platform === "win32";
const children = new Set();

async function probe(port = 8000) {
  const url = port === 8000 ? HEALTH_URL : `http://127.0.0.1:${port}/health/live`;
  try {
    const response = await fetch(url, { signal: AbortSignal.timeout(1500) });
    if (!response.ok) return { state: "foreign", detail: `HTTP ${response.status}` };
    const body = await response.json().catch(() => null);
    if (body?.service === SERVICE_NAME) return { state: "ready" };
    return {
      state: "foreign",
      detail: body?.service ? `占用者：${body.service}` : "占用者：非 Rise Loop 服务",
    };
  } catch {
    return { state: "down" };
  }
}

function track(child, name) {
  children.add(child);
  child.on("error", (error) => {
    console.error(`[demo] ${name} 启动失败：${error.message}`);
    if (name === "cloud-api") {
      console.error("[demo] 请确认已安装 Python 并在 PATH 中，且已执行：");
      console.error("       pip install fastapi 'uvicorn[standard]' sqlalchemy redis asyncpg");
    }
    shutdown(1);
  });
  child.on("exit", (code) => {
    children.delete(child);
    if (code && code !== 0) console.error(`[demo] ${name} 退出，代码 ${code}`);
  });
  return child;
}

function shutdown(code = 0) {
  for (const child of children) {
    try {
      child.kill();
    } catch {
      /* 进程可能已退出 */
    }
  }
  process.exit(code);
}

process.on("SIGINT", () => shutdown(0));
process.on("SIGTERM", () => shutdown(0));

const existing = await probe();
if (existing.state === "ready") {
  console.log("[demo] 复用已在 8000 端口运行的本地服务");
} else if (existing.state === "foreign") {
  console.error(`[demo] 8000 端口已被其他服务占用（${existing.detail}）。`);
  console.error("[demo] 请先释放 8000 端口，或改用 VITE_DEMO_API_BASE 指向其他端口。");
  shutdown(1);
} else {
  const python = IS_WINDOWS ? "python" : "python3";
  track(
    spawn(
      python,
      ["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"],
      {
        cwd: API_DIR,
        env: { ...process.env, RISELOOP_CLOUD_PROVIDER: "mock", RISELOOP_ENV: "demo" },
        stdio: "inherit",
        shell: IS_WINDOWS,
      }
    ),
    "cloud-api"
  );

  process.stdout.write("[demo] 启动本地数据服务");
  let ready = false;
  for (let attempt = 0; attempt < 40; attempt += 1) {
    await new Promise((done) => setTimeout(done, 500));
    if ((await probe()).state === "ready") {
      ready = true;
      break;
    }
    process.stdout.write(".");
  }
  console.log(ready ? " 就绪（mock 模式，数据不离开本机）" : "\n[demo] 启动超时");
  if (!ready) {
    console.error("[demo] 请查看上方 uvicorn 输出；常见原因：");
    console.error("       1) 缺少依赖 → pip install fastapi 'uvicorn[standard]' sqlalchemy redis asyncpg");
    console.error("       2) 8000 端口被占用 → netstat -ano | findstr :8000");
    shutdown(1);
  }
}

console.log("[demo] 启动 Rise Loop 桌面端");
track(
  spawn("pnpm", ["tauri", "dev"], {
    cwd: DESKTOP_DIR,
    stdio: "inherit",
    shell: IS_WINDOWS,
  }),
  "tauri"
);