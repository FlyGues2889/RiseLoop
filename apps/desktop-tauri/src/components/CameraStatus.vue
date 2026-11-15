<script setup>
import { computed, onBeforeUnmount, ref } from "vue";
import { invoke, isTauri } from "@tauri-apps/api/core";
import { camera, entries } from "../state/cameraLog.js";

const open = ref(false);
const logPath = ref("");
const now = ref(Date.now());

let ticker = null;

const label = computed(() => {
  if (camera.mode === "live") return "动作页占用";
  if (camera.mode === "preview") return "设置页预览";
  if (camera.mode === "sampling") return "采样中";
  return "摄像头关闭";
});

const modeHint = computed(() => {
  if (camera.mode === "live") return "动作页正在用画面，倒计时结束后会自动关闭。";
  if (camera.mode === "preview") return "设置页正在预览画面，关掉预览即释放。";
  if (camera.mode === "sampling") return "正在采一帧算姿态，采完立刻关。";
  return "空闲时不占用摄像头，到点才打开。";
});

const durationText = computed(() => {
  if (!camera.since) return "";
  const seconds = Math.max(0, Math.round((now.value - camera.since) / 1000));
  if (seconds < 60) return `已持续 ${seconds} 秒`;
  return `已持续 ${Math.round(seconds / 60)} 分钟`;
});

const recent = computed(() => entries.slice(-40).reverse());

function timeOf(at) {
  return new Date(at).toLocaleTimeString("zh-CN", { hour12: false });
}

function startTicker() {
  stopTicker();
  now.value = Date.now();
  ticker = setInterval(() => {
    now.value = Date.now();
  }, 5000);
}

function stopTicker() {
  if (ticker) clearInterval(ticker);
  ticker = null;
}

function show() {
  open.value = true;
  startTicker();
  if (logPath.value || !isTauri()) return;
  invoke("camera_log_path")
    .then((path) => {
      logPath.value = String(path);
    })
    .catch(() => { });
}

function close() {
  open.value = false;
  stopTicker();
}

onBeforeUnmount(stopTicker);
</script>

<template>
  <m3e-button class="camera" variant="text" @click="show">
    <span class="dot" :class="camera.mode"></span>
    {{ label }}
  </m3e-button>

  <m3e-dialog class="camera-log" :open.prop="open" @closed="close">
    <h2 slot="header">摄像头</h2>

    <section class="status" :class="camera.mode">
      <div class="status-head">
        <span class="dot" :class="camera.mode"></span>
        <span class="status-label">{{ label }}</span>
        <span v-if="durationText" class="status-time">{{ durationText }}</span>
      </div>
      <p class="status-hint">{{ modeHint }}</p>
      <p v-if="camera.last" class="status-hint">
        最近一次：{{ timeOf(camera.last.at) }} {{ camera.last.text }}
      </p>
    </section>

    <h3 class="rows-title">最近记录</h3>
    <ul class="rows">
      <li v-for="item in recent" :key="item.at + item.text">
        <span class="time">{{ timeOf(item.at) }}</span>
        <span class="kind" :class="item.kind">{{ item.text }}</span>
      </li>
    </ul>
    <p v-if="!recent.length" class="empty">还没有记录。</p>
    <p v-if="logPath" class="path">日志文件：{{ logPath }}</p>

    <div slot="actions" end>
      <m3e-button variant="text" @click="close">关闭</m3e-button>
    </div>
  </m3e-dialog>
</template>

<style scoped>
.camera {
  --m3e-button-label-text-size: 0.75rem;
  color: var(--md-sys-color-on-surface-variant);
  white-space: nowrap;
}

.dot {
  display: inline-block;
  width: 0.5rem;
  height: 0.5rem;
  margin-right: 0.35rem;
  border-radius: 50%;
  background: var(--md-sys-color-outline);
  flex: none;
}

.dot.sampling {
  background: var(--md-sys-color-tertiary);
}

.dot.live,
.dot.preview {
  background: var(--md-sys-color-primary);
}

.camera-log {
  --m3e-dialog-max-width: 30rem;
}

.status {
  display: grid;
  gap: 0.25rem;
  margin-bottom: 0.9rem;
  padding: 0.75rem 0.9rem;
  border-radius: 0.9rem;
  background: var(--md-sys-color-surface-1);
}

.status-head {
  display: flex;
  align-items: center;
  gap: 0.35rem;
}

.status-label {
  font-weight: 600;
  font-size: 0.9375rem;
}

.status-time {
  margin-left: auto;
  color: var(--md-sys-color-outline);
  font-size: 0.75rem;
  font-variant-numeric: tabular-nums;
}

.status-hint {
  margin: 0;
  color: var(--md-sys-color-on-surface-variant);
  font-size: 0.8125rem;
}

.rows-title {
  margin: 0 0 0.5rem;
  color: var(--md-sys-color-on-surface-variant);
  font-size: 0.8125rem;
  font-weight: 600;
}

.rows {
  margin: 0;
  padding: 0;
  max-height: 14rem;
  overflow-y: auto;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}

.rows li {
  display: flex;
  gap: 0.75rem;
  align-items: baseline;
  font-size: 0.8125rem;
}

.time {
  flex: none;
  color: var(--md-sys-color-outline);
  font-variant-numeric: tabular-nums;
}

.kind {
  color: var(--md-sys-color-on-surface);
}

.kind.error,
.kind.skip {
  color: var(--md-sys-color-error);
}

.empty {
  margin: 0;
  color: var(--md-sys-color-outline);
  font-size: 0.8125rem;
}

.path {
  margin: 0.75rem 0 0;
  color: var(--md-sys-color-outline);
  font-size: 0.6875rem;
  word-break: break-all;
}
</style>
