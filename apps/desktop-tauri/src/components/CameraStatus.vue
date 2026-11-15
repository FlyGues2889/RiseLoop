<script setup>
import { computed, ref } from "vue";
import { invoke, isTauri } from "@tauri-apps/api/core";
import { camera, entries } from "../state/cameraLog.js";

const open = ref(false);
const logPath = ref("");

const label = computed(() => {
  if (camera.mode === "live") return "动作页占用";
  if (camera.mode === "preview") return "设置页预览";
  if (camera.mode === "sampling") return "采样中";
  return "摄像头关闭";
});

const recent = computed(() => entries.slice(-40).reverse());

function timeOf(at) {
  return new Date(at).toLocaleTimeString("zh-CN", { hour12: false });
}

function show() {
  open.value = true;
  if (logPath.value || !isTauri()) return;
  invoke("camera_log_path")
    .then((path) => {
      logPath.value = String(path);
    })
    .catch(() => { });
}
</script>

<template>
  <m3e-button class="camera" variant="text" @click="show">
    <span class="dot" :class="camera.mode"></span>
    {{ label }}
  </m3e-button>

  <m3e-dialog class="camera-log" :open.prop="open" @closed="open = false">
    <h2 slot="header">摄像头记录</h2>
    <p class="hint">
      只在采样时打开摄像头，采完立刻关闭。以下是最近的开、关与异常记录。
    </p>

    <ul class="rows">
      <li v-for="item in recent" :key="item.at + item.text">
        <span class="time">{{ timeOf(item.at) }}</span>
        <span class="kind" :class="item.kind">{{ item.text }}</span>
      </li>
    </ul>
    <p v-if="!recent.length" class="empty">还没有记录。</p>
    <p v-if="logPath" class="path">日志文件：{{ logPath }}</p>

    <div slot="actions" end>
      <m3e-button variant="text" @click="open = false">关闭</m3e-button>
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

.hint {
  margin: 0 0 0.75rem;
  color: var(--md-sys-color-on-surface-variant);
  font-size: 0.8125rem;
}

.rows {
  margin: 0;
  padding: 0;
  max-height: 16rem;
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
