<script setup>
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { invoke, isTauri } from "@tauri-apps/api/core";
import { state } from "../state/session.js";
import { camera, entries } from "../state/cameraLog.js";

const now = ref(Date.now());
const logPath = ref("");

let ticker = null;

const cameraLabel = computed(() => {
  if (camera.mode === "live") return "动作页占用";
  if (camera.mode === "preview") return "设置页预览";
  if (camera.mode === "sampling") return "采样中";
  return "摄像头关闭";
});

const cameraHint = computed(() => {
  if (camera.mode === "live") return "动作页正在用画面，离开动作页即释放。";
  if (camera.mode === "preview") return "设置页正在预览画面，关掉预览即释放。";
  if (camera.mode === "sampling") return "正在采一帧算姿态，采完立刻关。";
  return "空闲时不占用摄像头，到点才打开，采完立刻关。";
});

const cameraDuration = computed(() => {
  if (!camera.since) return "";
  const seconds = Math.max(0, Math.round((now.value - camera.since) / 1000));
  if (seconds < 60) return `已持续 ${seconds} 秒`;
  return `已持续 ${Math.round(seconds / 60)} 分钟`;
});

const cameraRecent = computed(() => entries.slice(-30).reverse());

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

function close() {
  state.logOpen = false;
}

watch(
  () => state.logOpen,
  (open) => {
    if (open) {
      startTicker();
      if (!logPath.value && isTauri()) {
        invoke("camera_log_path")
          .then((path) => {
            logPath.value = String(path);
          })
          .catch(() => { });
      }
      return;
    }
    stopTicker();
  },
  { immediate: true }
);

onBeforeUnmount(stopTicker);
</script>

<template>
  <m3e-dialog class="log-dialog" :open.prop="state.logOpen" @closed="close">
    <h2 slot="header">会话记录</h2>

    <m3e-tabs class="log-tabs">
      <m3e-tab selected for="log-actions">
        <span slot="icon" class="material-symbols-rounded">history</span>
        操作记录
      </m3e-tab>
      <m3e-tab for="log-camera">
        <span slot="icon" class="material-symbols-rounded">videocam</span>
        摄像头
      </m3e-tab>

      <m3e-tab-panel id="log-actions">
        <div class="panel">
          <div v-if="state.log.length" class="list">
            <div v-for="(item, index) in state.log" :key="index" class="row">
              <span class="time mono">{{ item.at }}</span>
              <span class="text">{{ item.message }}</span>
            </div>
          </div>
          <p v-else class="empty">还没有记录。操作之后，这里会留下时间线。</p>
        </div>
      </m3e-tab-panel>

      <m3e-tab-panel id="log-camera">
        <div class="panel">
          <section class="status" :class="camera.mode">
            <div class="status-head">
              <span class="dot" :class="camera.mode"></span>
              <span class="status-label">{{ cameraLabel }}</span>
              <span v-if="cameraDuration" class="status-time">{{ cameraDuration }}</span>
            </div>
            <p class="status-hint">{{ cameraHint }}</p>
            <p v-if="camera.last" class="status-hint">
              最近一次：{{ timeOf(camera.last.at) }} {{ camera.last.text }}
            </p>
          </section>

          <ul v-if="cameraRecent.length" class="rows">
            <li v-for="item in cameraRecent" :key="item.at + item.text">
              <span class="time">{{ timeOf(item.at) }}</span>
              <span class="kind" :class="item.kind">{{ item.text }}</span>
            </li>
          </ul>
          <p v-else class="empty">还没有记录。</p>

          <p v-if="logPath" class="path">日志文件：{{ logPath }}</p>
        </div>
      </m3e-tab-panel>
    </m3e-tabs>

    <div slot="actions" end class="dialog-actions">
      <m3e-button variant="outlined" @click="close">关闭</m3e-button>
    </div>
  </m3e-dialog>
</template>

<style scoped>
.log-dialog {
  --m3e-dialog-max-width: 32rem;
}

.panel {
  max-height: 22rem;
  overflow-y: auto;
  padding: 0.25rem 0 0;
}

.list {
  display: grid;
  gap: 0.5rem;
}

.row {
  display: flex;
  gap: 1rem;
  align-items: baseline;
  font-size: 0.78rem;
  color: var(--md-sys-color-on-surface-variant);
}

.time {
  flex: 0 0 auto;
  color: var(--md-sys-color-outline);
  font-size: 0.68rem;
  font-variant-numeric: tabular-nums;
}

.text {
  min-width: 0;
  line-height: 1.6;
}

.empty {
  margin: 0;
  color: var(--md-sys-color-outline);
  font-size: 0.8125rem;
}

/* 摄像头状态 */
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

.dot {
  display: inline-block;
  width: 0.5rem;
  height: 0.5rem;
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

.rows {
  margin: 0;
  padding: 0;
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

.kind {
  color: var(--md-sys-color-on-surface);
}

.kind.error,
.kind.skip {
  color: var(--md-sys-color-error);
}

.path {
  margin: 0.75rem 0 0;
  color: var(--md-sys-color-outline);
  font-size: 0.6875rem;
  word-break: break-all;
}

.dialog-actions {
  display: flex;
  gap: 0.5rem;
  justify-content: flex-end;
}
</style>
