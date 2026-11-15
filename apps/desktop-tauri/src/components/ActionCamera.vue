<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from "vue";

import { createPoseLandmarker, prefs as cameraPrefs } from "../state/postureMonitor.js";

const props = defineProps({
  // 预留：后续动作参考图按归一化坐标给出取景框，例如 { box: { x, y, w, h }, label, image }
  reference: { type: Object, default: null },
});

const videoEl = ref(null);
const canvasEl = ref(null);
const status = ref("starting");
const aligned = ref(false);

const box = computed(
  () => props.reference?.box ?? { x: 0.26, y: 0.08, w: 0.48, h: 0.84 }
);
const guideStyle = computed(() => ({
  left: box.value.x * 100 + "%",
  top: box.value.y * 100 + "%",
  width: box.value.w * 100 + "%",
  height: box.value.h * 100 + "%",
}));
const guideLabel = computed(() =>
  aligned.value ? "对齐了" : (props.reference?.label ?? "站进框内")
);
const placeholder = computed(() => {
  if (status.value === "starting") return "正在打开摄像头";
  if (status.value === "error") return "摄像头不可用";
  return "摄像头未开启";
});

const BONES = [
  [11, 12], [11, 13], [13, 15], [12, 14], [14, 16],
  [11, 23], [12, 24], [23, 24], [23, 25], [25, 27], [24, 26], [26, 28],
];
const ALIGN_POINTS = [0, 11, 12, 23, 24];

let stream = null;
let rafId = 0;
let landmarker = null;
let lastDetectAt = 0;
let lastVideoTime = -1;

function resizeCanvas() {
  const canvas = canvasEl.value;
  const video = videoEl.value;
  if (!canvas || !video) return;
  const rect = canvas.getBoundingClientRect();
  canvas.width = Math.max(1, Math.round(rect.width));
  canvas.height = Math.max(1, Math.round(rect.height));
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

function draw(points) {
  const canvas = canvasEl.value;
  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  if (!points) return;
  ctx.strokeStyle = aligned.value ? "#88f8c8" : "rgba(255,255,255,0.75)";
  ctx.lineWidth = 2;
  ctx.lineCap = "round";
  for (const [a, b] of BONES) {
    ctx.beginPath();
    ctx.moveTo(points[a].x, points[a].y);
    ctx.lineTo(points[b].x, points[b].y);
    ctx.stroke();
  }
  ctx.fillStyle = aligned.value ? "#88f8c8" : "rgba(255,255,255,0.9)";
  for (const index of ALIGN_POINTS) {
    ctx.beginPath();
    ctx.arc(points[index].x, points[index].y, 3, 0, Math.PI * 2);
    ctx.fill();
  }
}

function checkAligned(landmarks) {
  const canvas = canvasEl.value;
  if (!canvas || !landmarks.length) return false;
  const points = project(landmarks);
  if (!points) return false;
  let inside = 0;
  for (const index of ALIGN_POINTS) {
    const nx = points[index].x / canvas.width;
    const ny = points[index].y / canvas.height;
    const { x, y, w, h } = box.value;
    if (nx >= x && nx <= x + w && ny >= y && ny <= y + h) inside += 1;
  }
  return inside >= 3;
}

function tick() {
  rafId = requestAnimationFrame(tick);
  const video = videoEl.value;
  if (!video || !landmarker || video.readyState < 2) return;
  const now = performance.now();
  if (now - lastDetectAt < 80 || video.currentTime === lastVideoTime) return;
  lastDetectAt = now;
  lastVideoTime = video.currentTime;
  const landmarks = landmarker.detectForVideo(video, now)?.landmarks?.[0];
  if (!landmarks) {
    aligned.value = false;
    draw(null);
    return;
  }
  aligned.value = checkAligned(landmarks);
  draw(project(landmarks));
}

async function start() {
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
  }
  if (videoEl.value) videoEl.value.srcObject = null;
  if (landmarker) {
    landmarker.close();
    landmarker = null;
  }
}

onMounted(() => {
  start();
  window.addEventListener("resize", resizeCanvas);
});

onBeforeUnmount(() => {
  window.removeEventListener("resize", resizeCanvas);
  release();
});
</script>

<template>
  <div class="action-camera" :class="{ aligned }">
    <video ref="videoEl" class="feed" autoplay muted playsinline v-show="status === 'ready'"></video>
    <canvas ref="canvasEl" class="skeleton" v-show="status === 'ready'"></canvas>

    <div class="guide" :style="guideStyle" aria-hidden="true">
      <i class="corner tl"></i><i class="corner tr"></i><i class="corner bl"></i><i class="corner br"></i>
    </div>
    <span class="guide-label">{{ guideLabel }}</span>

    <div v-if="status !== 'ready'" class="placeholder">
      <span class="material-symbols-rounded">videocam_off</span>
      <span>{{ placeholder }}</span>
    </div>
  </div>
</template>

<style scoped>
.action-camera {
  position: relative;
  width: 100%;
  aspect-ratio: 3 / 4;
  overflow: hidden;
  border-radius: 0.9rem;
  background: var(--md-sys-color-surface-1);
}

.feed,
.skeleton {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.skeleton {
  pointer-events: none;
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
  left: 0;
  right: 0;
  bottom: 0.5rem;
  text-align: center;
  color: var(--md-sys-color-primary-container);
  font-size: 0.7rem;
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
  gap: 0.4rem;
  color: var(--md-sys-color-outline);
  font-size: 0.72rem;
}
</style>
