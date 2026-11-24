<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from "vue";

import { record, setLiveCamera } from "../state/cameraLog.js";
import { createPoseLandmarker, prefs as cameraPrefs } from "../state/postureMonitor.js";

const props = defineProps({
  // { framing: "upper" | "full" | "none", focus: number[], hint: string }
  framing: { type: Object, default: null },
});

const SKELETON_KEY = "riseloop.camera.skeletonOnly";
const VISIBLE = 0.5;

const videoEl = ref(null);
const canvasEl = ref(null);
const status = ref("starting");
const aligned = ref(false);
const skeletonOnly = ref(readSkeletonPref());

function readSkeletonPref() {
  try {
    return window.localStorage?.getItem(SKELETON_KEY) === "1";
  } catch {
    return false;
  }
}

function toggleSkeleton() {
  skeletonOnly.value = !skeletonOnly.value;
  try {
    window.localStorage?.setItem(SKELETON_KEY, skeletonOnly.value ? "1" : "0");
  } catch {
    /* 隐私开关存不下也不阻断 */
  }
}

const mode = computed(() => props.framing?.framing ?? "upper");
const focus = computed(() => props.framing?.focus ?? []);
const needAlign = computed(() => mode.value !== "none");
const hint = computed(() => {
  if (props.framing?.hint) return props.framing.hint;
  return mode.value === "full" ? "请后退半步，使膝盖进入画面" : "请坐直，使头部与双肩位于画面内";
});

// 久坐场景默认只框上半身；只有站立动作才要求膝盖以下
const box = computed(() => {
  if (!needAlign.value) return null;
  return mode.value === "full"
    ? { x: 0.16, y: 0.04, w: 0.68, h: 0.92 }
    : { x: 0.12, y: 0.06, w: 0.76, h: 0.7 };
});

const guideStyle = computed(() => (box.value ? {
  left: box.value.x * 100 + "%",
  top: box.value.y * 100 + "%",
  width: box.value.w * 100 + "%",
  height: box.value.h * 100 + "%",
} : {}));

const label = computed(() => {
  if (!needAlign.value) return hint.value;
  return aligned.value ? "已对齐" : hint.value;
});

const placeholder = computed(() => {
  if (status.value === "starting") return "正在打开摄像头";
  if (status.value === "error") return "摄像头不可用，请按文字步骤练习";
  return "摄像头已暂停";
});

const TORSO_BONES = [
  [11, 12], [11, 13], [13, 15], [12, 14], [14, 16],
  [11, 23], [12, 24], [23, 24],
];
const LEG_BONES = [[23, 25], [25, 27], [24, 26], [26, 28]];

function bonesForMode() {
  return mode.value === "full" ? [...TORSO_BONES, ...LEG_BONES] : TORSO_BONES;
}

let stream = null;
let rafId = 0;
let landmarker = null;
let lastDetectAt = 0;
let lastVideoTime = -1;
let lastPoints = null;
let lastVisible = [];

function resizeCanvas() {
  const canvas = canvasEl.value;
  if (!canvas) return;
  const rect = canvas.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  canvas.width = Math.max(1, Math.round(rect.width * dpr));
  canvas.height = Math.max(1, Math.round(rect.height * dpr));
}

function isVisible(point) {
  if (!point) return false;
  if (point.x < -0.05 || point.x > 1.05 || point.y < -0.05 || point.y > 1.05) return false;
  return (point.visibility ?? 1) >= VISIBLE;
}

function project(points) {
  const video = videoEl.value;
  const canvas = canvasEl.value;
  const vw = video.videoWidth;
  const vh = video.videoHeight;
  if (!vw || !vh) return null;
  const scale = Math.max(canvas.width / vw, canvas.height / vh);
  const offsetX = (canvas.width - vw * scale) / 2;
  const offsetY = (canvas.height - vh * scale) / 2;
  return points.map((point) => ({
    x: point.x * vw * scale + offsetX,
    y: point.y * vh * scale + offsetY,
  }));
}

// 画面交给 canvas 自己画：视频层只负责解码。WebView2 里 <video> 与 canvas 叠加时
// 视频层会整块泛绿或变黑，改成单画布绘制既避开合成问题，「只看骨架」也有底色可用。
function schemeColor(name, fallback) {
  const styles = getComputedStyle(document.documentElement);
  return styles.getPropertyValue(name).trim() || fallback;
}

function readSurface() {
  return schemeColor("--md-sys-color-surface-1", "#1d2521");
}

function paintBase() {
  const canvas = canvasEl.value;
  const video = videoEl.value;
  if (!canvas) return null;
  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  if (skeletonOnly.value || status.value !== "ready") {
    ctx.fillStyle = readSurface();
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    return ctx;
  }
  const vw = video?.videoWidth ?? 0;
  const vh = video?.videoHeight ?? 0;
  if (!vw || !vh) return ctx;
  const scale = Math.max(canvas.width / vw, canvas.height / vh);
  const dw = vw * scale;
  const dh = vh * scale;
  ctx.drawImage(video, (canvas.width - dw) / 2, (canvas.height - dh) / 2, dw, dh);
  return ctx;
}

function draw(ctx, points, visible) {
  if (!ctx || !points) return;
  // 压在实时画面上的线必须始终够亮：暗色主题里 primary-container 是深绿，会把骨架吞掉，
  // 所以这里固定用浅薄荷/白色，不跟主题走
  ctx.strokeStyle = aligned.value ? "#88f8c8" : "rgba(255,255,255,0.72)";
  ctx.lineWidth = 2;
  ctx.lineCap = "round";
  // 只画两端都看得见的骨头：看不到的部分留白，比画错位置更可信
  for (const [a, b] of bonesForMode()) {
    if (!visible[a] || !visible[b] || !points[a] || !points[b]) continue;
    ctx.beginPath();
    ctx.moveTo(points[a].x, points[a].y);
    ctx.lineTo(points[b].x, points[b].y);
    ctx.stroke();
  }
  ctx.fillStyle = aligned.value ? "#88f8c8" : "rgba(255,255,255,0.9)";
  for (const index of focus.value) {
    if (!visible[index] || !points[index]) continue;
    ctx.beginPath();
    ctx.arc(points[index].x, points[index].y, 3, 0, Math.PI * 2);
    ctx.fill();
  }
}

function checkAligned(points, visible) {
  if (!needAlign.value || !focus.value.length) return true;
  const canvas = canvasEl.value;
  const { x, y, w, h } = box.value;
  let inside = 0;
  let seen = 0;
  for (const index of focus.value) {
    if (!points[index]) continue;
    seen += 1;
    const nx = points[index].x / canvas.width;
    const ny = points[index].y / canvas.height;
    if (nx >= x && nx <= x + w && ny >= y && ny <= y + h) inside += 1;
  }
  if (seen === 0) return false;
  return inside / focus.value.length >= 0.6;
}

function tick() {
  rafId = requestAnimationFrame(tick);
  const ctx = paintBase();
  draw(ctx, lastPoints, lastVisible);
  const video = videoEl.value;
  if (!video || !landmarker || video.readyState < 2) return;
  const now = performance.now();
  if (now - lastDetectAt < 80 || video.currentTime === lastVideoTime) return;
  lastDetectAt = now;
  lastVideoTime = video.currentTime;
  const landmarks = landmarker.detectForVideo(video, now)?.landmarks?.[0];
  if (!landmarks) {
    aligned.value = false;
    lastPoints = null;
    lastVisible = [];
    return;
  }
  lastPoints = project(landmarks);
  lastVisible = landmarks.map((point) => isVisible(point));
  aligned.value = checkAligned(lastPoints, lastVisible);
}

async function start() {
  if (stream) return;
  status.value = "starting";
  try {
    if (!navigator.mediaDevices?.getUserMedia) {
      status.value = "error";
      return;
    }
    const deviceId = cameraPrefs.deviceId;
    stream = await navigator.mediaDevices.getUserMedia({
      video: deviceId
        ? { deviceId: { exact: deviceId }, width: { ideal: 480 }, height: { ideal: 640 } }
        : { width: { ideal: 480 }, height: { ideal: 640 }, facingMode: "user" },
      audio: false,
    });
    const video = videoEl.value;
    video.srcObject = stream;
    await video.play().catch(() => { });
    status.value = "ready";
    setLiveCamera(true);
    record("open", "动作页打开摄像头", "live");
    resizeCanvas();
    landmarker = await createPoseLandmarker().catch(() => null);
    tick();
  } catch {
    status.value = "error";
    release();
  }
}

function release() {
  if (rafId) cancelAnimationFrame(rafId);
  rafId = 0;
  if (stream) {
    stream.getTracks().forEach((track) => track.stop());
    stream = null;
    setLiveCamera(false);
    record("close", "动作页关闭摄像头", "off");
  }
  if (videoEl.value) videoEl.value.srcObject = null;
  if (landmarker) {
    landmarker.close();
    landmarker = null;
  }
}

// 窗口在后台时不占着摄像头：回来再重新打开
function onVisibility() {
  if (document.hidden) {
    if (!stream) return;
    release();
    status.value = "idle";
    return;
  }
  if (status.value === "idle") start();
}

onMounted(() => {
  start();
  window.addEventListener("resize", resizeCanvas);
  document.addEventListener("visibilitychange", onVisibility);
});

onBeforeUnmount(() => {
  window.removeEventListener("resize", resizeCanvas);
  document.removeEventListener("visibilitychange", onVisibility);
  release();
});
</script>

<template>
  <div class="action-camera" :class="{ aligned, skeleton: skeletonOnly }">
    <video ref="videoEl" class="feed" autoplay muted playsinline v-show="status === 'ready'"></video>
    <canvas ref="canvasEl" class="skeleton-layer"></canvas>

    <div v-if="needAlign && status === 'ready'" class="guide" :style="guideStyle" aria-hidden="true">
      <i class="corner tl"></i><i class="corner tr"></i><i class="corner bl"></i><i class="corner br"></i>
    </div>

    <div class="top-bar">
      <m3e-button variant="text" size="small" @click="toggleSkeleton">
        {{ skeletonOnly ? "显示画面" : "只看骨架" }}
      </m3e-button>
    </div>

    <span v-if="status === 'ready'" class="guide-label">{{ label }}</span>

    <div v-if="status !== 'ready'" class="placeholder">
      <span class="material-symbols-rounded">videocam_off</span>
      <span>{{ placeholder }}</span>
      <m3e-button variant="tonal" size="small" @click="start">打开摄像头</m3e-button>
    </div>
  </div>
</template>

<style scoped>
.action-camera {
  position: relative;
  width: 100%;
  aspect-ratio: 4 / 3;
  box-sizing: border-box;
  overflow: hidden;
  border: 0.2rem solid var(--md-sys-color-outline);
  border-radius: 0.9rem;
  background: var(--md-sys-color-surface-1);
}

.feed,
.skeleton-layer {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

/* 视频只用来取帧，真正上屏的是 canvas，避免选中相机画面被合成层染色 */
.feed {
  opacity: 0;
}

.skeleton-layer {
  pointer-events: none;
}

.top-bar {
  position: absolute;
  top: 0.15rem;
  right: 0.25rem;
  z-index: 2;
}

.guide {
  position: absolute;
  border: 0.12rem dashed rgba(255, 255, 255, 0.4);
  border-radius: 0.75rem;
  transition: border-color 200ms ease-out;
}

.aligned .guide {
  border-color: transparent;
}

.corner {
  position: absolute;
  width: 0.75rem;
  height: 0.75rem;
  border: 0.15rem solid var(--md-sys-color-primary-container);
  border-radius: 0.15rem;
}

.aligned .corner {
  border-color: var(--md-sys-color-primary);
}

.corner.tl { top: -0.1rem; left: -0.1rem; border-right: 0; border-bottom: 0; }
.corner.tr { top: -0.1rem; right: -0.1rem; border-left: 0; border-bottom: 0; }
.corner.bl { bottom: -0.1rem; left: -0.1rem; border-right: 0; border-top: 0; }
.corner.br { bottom: -0.1rem; right: -0.1rem; border-left: 0; border-top: 0; }

.guide-label {
  position: absolute;
  left: 0.5rem;
  right: 0.5rem;
  bottom: 0.5rem;
  text-align: center;
  color: var(--md-sys-color-primary-container);
  font-size: 0.72rem;
  line-height: 1.4;
}

.aligned .guide-label {
  color: var(--md-sys-color-primary);
}

.placeholder {
  position: absolute;
  inset: 0;
  display: grid;
  place-content: center;
  justify-items: center;
  gap: 0.5rem;
  padding: 0.75rem;
  text-align: center;
  color: var(--md-sys-color-outline);
  font-size: 0.75rem;
}
</style>
