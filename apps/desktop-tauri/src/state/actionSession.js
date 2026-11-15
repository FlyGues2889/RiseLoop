import { reactive } from "vue";

import { invoke, isTauri } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";

/**
 * 动作会话的单一真相。
 *
 * Tauri 里计时由 Rust 推进（窗口隐藏时浏览器会节流 setInterval），页面只发命令、
 * 只渲染快照；浏览器里跑 `pnpm dev` 时退回本地秒表，接口保持一致。
 */
const tauri = isTauri();

export const ACTION_EVENT = "riseloop://action";

export const actionSession = reactive({
  loaded: false,
  id: "",
  name: "",
  steps: [],
  index: 0,
  remaining: 0,
  running: false,
  done: false,
});

let localTimer = null;
let subscribed = false;
// Rust 侧命令不可用（旧二进制、网页调试）时退回本地秒表
let fallbackLocal = !tauri;

function stepSeconds(list = actionSession.steps, index = actionSession.index) {
  const item = list[index];
  return Math.max(1, Number(item?.seconds) || 0);
}

function apply(snapshot) {
  if (!snapshot) return;
  actionSession.loaded = Boolean(snapshot.loaded);
  actionSession.id = snapshot.id ?? "";
  actionSession.name = snapshot.name ?? "";
  actionSession.steps = (snapshot.steps ?? []).map((item) => ({
    text: item?.text ?? "",
    seconds: Math.max(0, Number(item?.seconds) || 0),
  }));
  actionSession.index = Number(snapshot.index) || 0;
  actionSession.remaining = Math.max(0, Number(snapshot.remaining) || 0);
  actionSession.running = Boolean(snapshot.running);
  actionSession.done = Boolean(snapshot.done);
}

function snapshot() {
  return {
    loaded: actionSession.loaded,
    id: actionSession.id,
    name: actionSession.name,
    steps: actionSession.steps,
    index: actionSession.index,
    remaining: actionSession.remaining,
    running: actionSession.running,
    done: actionSession.done,
  };
}

/* ---------- 浏览器调试用的本地秒表，行为与 Rust 侧保持一致 ---------- */

function localStop() {
  if (localTimer) clearInterval(localTimer);
  localTimer = null;
}

function localTick() {
  if (!actionSession.loaded || !actionSession.running || actionSession.done) return;
  if (actionSession.remaining > 0) actionSession.remaining -= 1;
  if (actionSession.remaining === 0) {
    if (actionSession.index + 1 < actionSession.steps.length) {
      actionSession.index += 1;
      actionSession.remaining = stepSeconds();
    } else {
      actionSession.running = false;
      actionSession.done = true;
    }
  }
}

function localPlay() {
  if (!actionSession.loaded || actionSession.done || actionSession.remaining === 0) return;
  actionSession.running = true;
  if (!localTimer) localTimer = setInterval(localTick, 1000);
}

/* ---------- 对外接口 ---------- */

/** 监听 Rust 广播，可重复调用。 */
export async function initActionSession() {
  if (!tauri || subscribed) return;
  subscribed = true;
  try {
    apply(await invoke("action_state"));
  } catch {
    /* 还没建好会话时忽略 */
  }
  await listen(ACTION_EVENT, (event) => apply(event.payload));
}

/** 载入一组动作；steps 为 [{ text, seconds }]，单位秒。 */
function applyLocal(id, name, steps) {
  apply({
    loaded: steps.length > 0,
    id,
    name,
    steps,
    index: 0,
    remaining: steps.length ? stepSeconds(steps, 0) : 0,
    running: false,
    done: false,
  });
}

export async function loadAction(id, name, steps) {
  localStop();
  if (fallbackLocal) {
    applyLocal(id, name, steps);
    return snapshot();
  }
  try {
    apply(await invoke("action_load", { id, name, steps }));
  } catch {
    fallbackLocal = true;
    applyLocal(id, name, steps);
  }
  return snapshot();
}

async function command(name, local) {
  if (fallbackLocal) {
    local?.();
    return snapshot();
  }
  try {
    apply(await invoke(name));
  } catch {
    fallbackLocal = true;
    local?.();
  }
  return snapshot();
}

export function playAction() {
  return command("action_play", localPlay);
}

export function pauseAction() {
  return command("action_pause", () => {
    actionSession.running = false;
    localStop();
  });
}

export function toggleAction() {
  return command("action_toggle", () => {
    if (!actionSession.loaded) return;
    if (actionSession.done) {
      actionSession.index = 0;
      actionSession.remaining = stepSeconds(actionSession.steps, 0);
      actionSession.done = false;
      actionSession.running = true;
      localPlay();
      return;
    }
    if (actionSession.running) {
      actionSession.running = false;
      localStop();
      return;
    }
    localPlay();
  });
}

export function nextStep() {
  return command("action_next", () => {
    if (!actionSession.loaded || actionSession.done) return;
    if (actionSession.index + 1 < actionSession.steps.length) {
      actionSession.index += 1;
      actionSession.remaining = stepSeconds();
      return;
    }
    actionSession.remaining = 0;
    actionSession.running = false;
    actionSession.done = true;
  });
}

export function prevStep() {
  return command("action_prev", () => {
    if (!actionSession.loaded) return;
    if (actionSession.done) {
      actionSession.done = false;
      actionSession.running = false;
      actionSession.index = Math.max(0, actionSession.steps.length - 1);
    } else if (actionSession.index === 0) {
      actionSession.remaining = stepSeconds(actionSession.steps, 0);
      return;
    } else {
      actionSession.index -= 1;
    }
    actionSession.remaining = stepSeconds();
  });
}

export function restartAction() {
  return command("action_restart", () => {
    if (!actionSession.loaded) return;
    actionSession.index = 0;
    actionSession.remaining = stepSeconds(actionSession.steps, 0);
    actionSession.done = false;
    actionSession.running = true;
    localPlay();
  });
}

/** 做完这一组：唤回主窗并打开反馈（仅在 Tauri 下有意义）。 */
export async function finishAction() {
  if (!tauri) return;
  await invoke("action_finish").catch(() => { });
}
