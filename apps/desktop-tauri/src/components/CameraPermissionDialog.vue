<script setup>
import { computed, nextTick, ref, watch } from "vue";

import {
  cameraErrorMessage,
  markAsked,
  monitor,
  pause,
  prefs,
  refreshDevices,
  resume,
  start,
  stop,
  switchDevice,
  ui,
} from "../state/postureMonitor.js";

const videoEl = ref(null);
const busy = ref(false);
const error = ref("");
const selected = ref("");
const wasRunning = ref(false);
const previewStream = ref(null);
let decided = false;
let opened = false;

const multi = computed(() => monitor.devices.length > 1);
const options = computed(() =>
  monitor.devices.length ? monitor.devices : [{ id: "", label: "默认摄像头" }]
);
const currentLabel = computed(() => {
  const found = monitor.devices.find((item) => item.id === selected.value);
  return found?.label ?? "当前摄像头";
});

function stopPreview() {
  if (previewStream.value) {
    previewStream.value.getTracks().forEach((track) => track.stop());
    previewStream.value = null;
  }
  if (videoEl.value) videoEl.value.srcObject = null;
}

async function openPreview(deviceId) {
  stopPreview();
  error.value = "";
  try {
    previewStream.value = await navigator.mediaDevices.getUserMedia({
      video: deviceId
        ? { deviceId: { exact: deviceId }, width: { ideal: 640 }, height: { ideal: 480 } }
        : { width: { ideal: 640 }, height: { ideal: 480 } },
      audio: false,
    });
    if (!videoEl.value) return;
    videoEl.value.srcObject = previewStream.value;
    await videoEl.value.play().catch(() => { });
    await refreshDevices();
    if (!selected.value) selected.value = monitor.devices[0]?.id ?? "";
  } catch (err) {
    error.value = cameraErrorMessage(err);
  }
}

watch(
  () => ui.dialogOpen,
  async (open) => {
    if (!open) {
      opened = false;
      return;
    }
    opened = true;
    decided = false;
    busy.value = false;
    error.value = "";
    wasRunning.value = monitor.status === "running";
    selected.value = monitor.deviceId ?? prefs.deviceId ?? "";

    if (wasRunning.value) await pause();
    await nextTick();
    await openPreview(selected.value);
    if (!selected.value && monitor.devices.length) {
      selected.value = monitor.devices[0].id;
      await openPreview(selected.value);
    }
  }
);

async function onSwitch(event) {
  const deviceId = event.target.value;
  selected.value = deviceId;
  await openPreview(deviceId);
}

async function onRefresh() {
  await refreshDevices();
  if (!monitor.devices.some((item) => item.id === selected.value)) {
    selected.value = monitor.devices[0]?.id ?? "";
  }
  await openPreview(selected.value);
}

async function turnOn() {
  busy.value = true;
  error.value = "";
  stopPreview();
  try {
    await start(selected.value || null);
    decided = true;
    markAsked(true);
    ui.dialogOpen = false;
  } catch (err) {
    error.value = cameraErrorMessage(err);
  } finally {
    busy.value = false;
  }
}

async function turnOff() {
  stopPreview();
  await stop();
  decided = true;
  ui.dialogOpen = false;
}

async function keepRunning() {
  decided = true;
  markAsked(true);
  stopPreview();
  ui.dialogOpen = false;
  if (selected.value && selected.value !== monitor.deviceId) {
    await switchDevice(selected.value).catch(() => { });
  } else if (monitor.status !== "running" && prefs.enabled) {
    await resume().catch(() => { });
  }
}

function later() {
  decided = true;
  markAsked(false);
  stopPreview();
  ui.dialogOpen = false;
  if (wasRunning.value && prefs.enabled) resume().catch(() => { });
}

function onClosed() {
  if (decided || !opened) {
    opened = false;
    return;
  }
  opened = false;
  if (wasRunning.value) {
    decided = true;
    stopPreview();
    if (prefs.enabled) resume().catch(() => { });
    return;
  }
  later();
}
</script>

<template>
  <m3e-dialog class="camera-dialog" alert :open.prop="ui.dialogOpen" @closed="onClosed">
    <h2 slot="header">{{ wasRunning ? "姿势监测" : "开启姿势监测" }}</h2>

    <template v-if="wasRunning">
      <p>开启摄像头以保证应用程序能够在始终检测人体姿势变化。</p>
    </template>
    <template v-else>
      <p>开启摄像头以保证应用程序能够在始终检测人体姿势变化。</p>
      <p class="hint">画面只在本地处理，最后将标记的 33 个骨骼坐标点上传，不会侵犯隐私。若不同意开启摄像头，可以点击 “稍后再说” 按钮。</p>
    </template>

    <div class="picker-row">
      <m3e-form-field class="picker">
        <label slot="label" for="camera-device">选择摄像头</label>
        <m3e-select id="camera-device" :value.prop="selected" @change="onSwitch">
          <m3e-option v-for="item in options" :key="item.id || 'default'" :value="item.id">
            {{ item.label }}
          </m3e-option>
        </m3e-select>
      </m3e-form-field>
      <m3e-icon-button class="refresh" variant="tonal" size="small" aria-label="重新扫描摄像头" @click="onRefresh">
        <span class="material-symbols-rounded">refresh</span>
      </m3e-icon-button>
    </div>

    <div class="preview">
      <video ref="videoEl" class="preview-video" autoplay muted playsinline></video>
      <div v-if="!previewStream" class="preview-empty">
        <span class="material-symbols-rounded">videocam_off</span>
        <span>还没有画面</span>
      </div>
    </div>

    <p class="camera-name">{{ currentLabel }}</p>


    <p v-if="error" class="error">{{ error }}</p>

    <div v-if="wasRunning" slot="actions" end class="dialog-actions">
      <m3e-button variant="text" @click="turnOff">关闭监测</m3e-button>
      <m3e-button variant="filled" :disabled.prop="busy" @click="keepRunning">完成</m3e-button>
    </div>
    <div v-else slot="actions" end class="dialog-actions">
      <m3e-button variant="text" @click="later">稍后再说</m3e-button>
      <m3e-button variant="filled" :disabled.prop="busy" @click="turnOn">
        {{ busy ? "正在开启…" : "开启监测" }}
      </m3e-button>
    </div>
  </m3e-dialog>
</template>

<style scoped>
.camera-dialog {
  --m3e-dialog-max-width: 28.75rem;
  --m3e-dialog-max-height: min(45rem, 92vh);
}

.dialog-actions {
  display: flex;
  gap: 0.5rem;
  justify-content: flex-end;
}

.camera-dialog p {
  margin: 0 0 0.75rem;
  line-height: 1.7;
  font-size: 0.92rem;
}

.camera-dialog .hint {
  color: var(--md-sys-color-on-surface-variant);
  font-size: 0.82rem;
}

.preview {
  position: relative;
  aspect-ratio: 16 / 9;
  width: 100%;
  overflow: hidden;
  border-radius: 1rem;
  background: #000;
}

.preview-video {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  transform: scaleX(-1);
}

.preview-empty {
  position: absolute;
  inset: 0;
  display: grid;
  place-content: center;
  justify-items: center;
  gap: 0.375rem;
  color: rgba(255, 255, 255, 0.65);
  font-size: 0.75rem;
}

.preview-empty .material-symbols-rounded {
  font-size: 1.75rem;
}

.camera-name {
  margin: 0.5rem 0 0.625rem !important;
  color: var(--md-sys-color-on-surface-variant);
  font-size: 0.82rem !important;
}

.picker-row {
  display: flex;
  align-items: baseline;
  gap: 0.5rem;
}

.picker {
  flex: 1 1 auto;
  min-width: 0;
}

.refresh {
  flex: none;
  --m3e-icon-button-icon-size: 1.25rem;
  color: var(--md-sys-color-on-surface-variant);
}

.error {
  margin: 0.25rem 0 0;
  color: var(--md-sys-color-error);
  font-size: 0.85rem;
}
</style>
