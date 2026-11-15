// 摄像头记录：界面上显示当前状态，同时写进本机日志文件。
import { reactive } from "vue";
import { invoke, isTauri } from "@tauri-apps/api/core";

const KEY = "riseloop.camera.log.v1";
const MAX = 120;

export const camera = reactive({
  mode: "off", // off | sampling | live
  since: null,
  last: null, // { at, kind, text }
});

export const entries = reactive(load());

let liveUsers = 0;

export function liveCameraBusy() {
  return liveUsers > 0;
}

export function setLiveCamera(on) {
  liveUsers = Math.max(0, liveUsers + (on ? 1 : -1));
}

function load() {
  try {
    const parsed = JSON.parse(localStorage.getItem(KEY) ?? "[]");
    return Array.isArray(parsed) ? parsed.slice(-MAX) : [];
  } catch {
    return [];
  }
}

function persist() {
  try {
    localStorage.setItem(KEY, JSON.stringify(entries));
  } catch {
    /* 存储不可用时只留内存 */
  }
}

function writeFile(item) {
  if (!isTauri()) return;
  const stamp = new Date(item.at).toISOString();
  invoke("camera_log", { line: item.kind + "\t" + item.text + "\t" + stamp }).catch(() => { });
}

export function record(kind, text, mode) {
  const item = { at: Date.now(), kind, text };
  entries.push(item);
  if (entries.length > MAX) entries.splice(0, entries.length - MAX);
  camera.last = item;
  if (mode) {
    camera.mode = mode;
    camera.since = item.at;
  }
  persist();
  writeFile(item);
}
