<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { invoke, isTauri } from "@tauri-apps/api/core";
import { revealItemInDir } from "@tauri-apps/plugin-opener";
import { toContractKeypoints } from "../data/keypoints.js";
import { createPoseLandmarker, monitor } from "../state/postureMonitor.js";

const emit = defineEmits(["close"]);

const SEGMENTS = [
  { label: "baseline", title: "自然坐正", hint: "双肩放平，头不要往前探" },
  { label: "forward_head", title: "头往前探", hint: "下巴向前伸，保持住不要低头" },
  { label: "lateral_tilt", title: "肩部侧倾", hint: "压低一侧肩膀，另一边自然抬起" },
  { label: "undetermined", title: "侧身或遮挡", hint: "侧过身，或用手挡住一侧肩膀" },
];

const LEAD_SECONDS = 3;
const SAMPLE_MS = 500;
const DEVICE = "laptop-cam";
const SCENE = "office";
const CAMERA_KEY = "riseloop.capture.camera.v1";

const tauri = isTauri();
const videoEl = ref(null);
const phase = ref("setup");
const subject = ref("s01");
const segmentSeconds = ref(30);
const cameras = ref([]);
const cameraId = ref("");
const error = ref("");
const index = ref(0);
const recording = ref(false);
const secondsToStart = ref(0);
const secondsLeft = ref(0);
const poseState = ref("none");
const live = ref({ tilt: 0, forward: 0, neck: 0 });
const counts = ref({});
const savedPath = ref("");

const segment = computed(() => SEGMENTS[index.value] ?? SEGMENTS[0]);
const totalSeconds = computed(() => segmentSeconds.value * SEGMENTS.length);
const poseHint = computed(() => {
  if (poseState.value === "ok") return "已识别，正在记录";
  if (poseState.value === "partial") return "关键点不稳，让双肩完整入画";
  return "未检测到人，请坐到镜头前、上半身入画";
});

let landmarker = null;
let stream = null;
let rafId = 0;
let lastVideoTime = -1;
let latest = null;
let nextSampleAt = 0;
let leadEndsAt = 0;
let phaseEndsAt = 0;
let pending = [];
let pausedMonitor = false;
let stopping = false;

// 采集页只做现场核对：这几个数就是云端特征，方便确认动作是否产生变化。
function measure(points) {
  const left = points[11];
  const right = points[12];
  const nose = points[0];
  const width = Math.hypot(right.x - left.x, right.y - left.y) || 0;
  if (!width) return { tilt: 0, forward: 0, neck: 0 };
  let degrees = (Math.atan2(right.y - left.y, right.x - left.x) * 180) / Math.PI;
  if (degrees > 90) degrees -= 180;
  if (degrees < -90) degrees += 180;
  const shoulderZ = (left.z + right.z) / 2;
  const shoulderY = (left.y + right.y) / 2;
  return {
    tilt: Math.round(degrees * 10) / 10,
    forward: Math.round(((shoulderZ - nose.z) / width) * 100) / 100,
    neck: Math.round(((shoulderY - nose.y) / width) * 100) / 100,
  };
}

function recordFor(points) {
  return {
    ts: new Date().toISOString(),
    device: DEVICE,
    subject: subject.value.trim() || "guest",
    scene: SCENE,
    framing: "upper_body",
    label: SEGMENTS[index.value].label,
    label_source: "human",
    origin: "capture",
    note: "desktop-capture",
    keypoints: points,
  };
}

async function flush() {
  if (!pending.length) return;
  const lines = pending.map((row) => JSON.stringify(row));
  pending = [];
  savedPath.value = await invoke("capture_append", { lines });
}

function beginSegment(next) {
  index.value = next;
  const now = performance.now();
  leadEndsAt = now + LEAD_SECONDS * 1000;
  phaseEndsAt = leadEndsAt + segmentSeconds.value * 1000;
  nextSampleAt = leadEndsAt;
  recording.value = false;
  secondsToStart.value = LEAD_SECONDS;
  secondsLeft.value = segmentSeconds.value;
  poseState.value = "none";
}

function tick() {
  if (phase.value !== "running") return;
  const video = videoEl.value;
  const now = performance.now();

  if (video && landmarker && video.readyState >= 2 && video.currentTime !== lastVideoTime) {
    lastVideoTime = video.currentTime;
    try {
      const landmarks = landmarker.detectForVideo(video, now)?.landmarks?.[0] ?? [];
      const points = landmarks.length ? toContractKeypoints(landmarks) : null;
      if (!points) {
        latest = null;
        poseState.value = "none";
      } else {
        latest = points;
        const shoulders = Math.min(points[11].visibility, points[12].visibility);
        poseState.value = shoulders >= 0.5 ? "ok" : "partial";
        live.value = measure(points);
      }
    } catch {
      /* 单帧识别失败不中断采集 */
    }
  }

  const remaining = Math.max(0, phaseEndsAt - now);
  const started = now >= leadEndsAt;
  recording.value = started;
  secondsToStart.value = started ? 0 : Math.max(1, Math.ceil((leadEndsAt - now) / 1000));
  secondsLeft.value = Math.max(0, Math.ceil(remaining / 1000));

  if (started && now >= nextSampleAt) {
    nextSampleAt = now + SAMPLE_MS;
    if (latest) {
      const label = SEGMENTS[index.value].label;
      pending.push(recordFor(latest));
      counts.value = { ...counts.value, [label]: (counts.value[label] ?? 0) + 1 };
      if (pending.length >= 10) void flush().catch(() => { });
    }
  }

  if (remaining <= 0) {
    if (index.value + 1 < SEGMENTS.length) {
      beginSegment(index.value + 1);
    } else {
      void finish();
      return;
    }
  }

  rafId = requestAnimationFrame(tick);
}

async function loadCameras() {
  try {
    const devices = await navigator.mediaDevices.enumerateDevices();
    const list = devices
      .filter((device) => device.kind === "videoinput")
      .map((device, order) => ({
        id: device.deviceId,
        label: device.label || `摄像头 ${order + 1}`,
      }));
    cameras.value = list;
    if (!list.some((item) => item.id === cameraId.value)) {
      cameraId.value = list[0]?.id ?? "";
    }
  } catch {
    cameras.value = [];
  }
}

function rememberCamera(id) {
  try {
    localStorage.setItem(CAMERA_KEY, id);
  } catch {
    /* 存不下就只影响下次默认值 */
  }
}

async function openFolder() {
  if (!tauri || !savedPath.value) return;
  try {
    await revealItemInDir(savedPath.value);
  } catch {
    error.value = "打不开文件夹，路径可能还没生成。";
  }
}

async function start() {
  if (!tauri) {
    error.value = "采集只在桌面应用里可用。";
    return;
  }
  error.value = "";
  counts.value = {};
  savedPath.value = "";
  phase.value = "running";
  stopping = false;

  try {
    landmarker = await createPoseLandmarker();
  } catch {
    error.value = "姿态模型没加载成功，重开应用再试。";
    await cleanup();
    phase.value = "setup";
    return;
  }

  try {
    if (monitor.status === "running") {
      pausedMonitor = true;
      await monitor.pause();
    }
    stream = await navigator.mediaDevices.getUserMedia({
      video: cameraId.value
        ? { deviceId: { exact: cameraId.value }, width: { ideal: 640 }, height: { ideal: 480 } }
        : { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: "user" },
      audio: false,
    });
    void loadCameras();
    const video = videoEl.value;
    video.srcObject = stream;
    await video.play();

    // 摄像头启动有数秒黑屏，先等到第一帧有效关键点再开始计时。
    const deadline = performance.now() + 8000;
    while (!latest && performance.now() < deadline) {
      if (video.readyState >= 2 && video.videoWidth) {
        try {
          const found = landmarker.detectForVideo(video, performance.now())?.landmarks?.[0] ?? [];
          if (found.length) latest = toContractKeypoints(found);
        } catch {
          /* 预热期识别失败直接跳过 */
        }
      }
      if (!latest) await new Promise((resolve) => setTimeout(resolve, 300));
    }

    beginSegment(0);
    rafId = requestAnimationFrame(tick);
  } catch (err) {
    error.value = "打不开摄像头，检查系统权限或是否被其他程序占用。";
    await cleanup();
    phase.value = "setup";
  }
}

async function finish() {
  if (stopping) return;
  stopping = true;
  try {
    await flush();
  } catch (err) {
    error.value = "写入本机文件失败。";
  } finally {
    await cleanup();
    phase.value = "done";
  }
}

async function stop() {
  if (stopping) return;
  stopping = true;
  try {
    await flush();
  } catch {
    error.value = "写入本机文件失败。";
  }
  await cleanup();
  phase.value = "done";
}

async function cleanup() {
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
  latest = null;
  if (pausedMonitor) {
    pausedMonitor = false;
    monitor.resume().catch(() => { });
  }
}

function reset() {
  phase.value = "setup";
  error.value = "";
  counts.value = {};
  savedPath.value = "";
  index.value = 0;
}

const totalFrames = computed(() =>
  Object.values(counts.value).reduce((sum, value) => sum + value, 0)
);

onMounted(async () => {
  try {
    const saved = localStorage.getItem(CAMERA_KEY);
    if (saved) cameraId.value = saved;
  } catch {
    /* 读不到就用默认摄像头 */
  }
  await loadCameras();
  invoke("capture_path")
    .then((path) => { savedPath.value = path; })
    .catch(() => { });
});

onBeforeUnmount(() => {
  void cleanup();
});
</script>

<template>
  <div class="view">
    <m3e-card variant="elevated" class="surface-card">
      <div class="surface-body">
        <header class="page-head">
          <div class="head-row">
            <m3e-icon-button variant="standard" size="small" aria-label="返回" @click="emit('close')">
              <span class="material-symbols-rounded">arrow_back</span>
            </m3e-icon-button>
            <h1>采集训练数据</h1>
          </div>
          <p class="lead">朋友坐到摄像头前，按提示采集几分钟；只记录 33 个关键点，数据留在本机。</p>
        </header>

        <template v-if="phase === 'setup'">
          <div class="panel">
            <label class="field">
              <span>受试者编号</span>
              <input v-model="subject" maxlength="8" />
            </label>
            <label class="field">
              <span>摄像头</span>
              <select v-model="cameraId" @change="rememberCamera(cameraId)">
                <option v-for="item in cameras" :key="item.id" :value="item.id">
                  {{ item.label }}
                </option>
                <option v-if="!cameras.length" value="">默认摄像头</option>
              </select>
            </label>
            <label class="field">
              <span>每段时长</span>
              <select v-model.number="segmentSeconds">
                <option :value="20">20 秒</option>
                <option :value="30">30 秒</option>
                <option :value="45">45 秒</option>
              </select>
            </label>
          </div>
          <p class="meta">
            {{ SEGMENTS.length }} 段共约 {{ Math.round(totalSeconds / 60) }} 分钟：{{
              SEGMENTS.map((item) => item.title).join(" → ")
            }}
          </p>
          <p v-if="error" class="state error">{{ error }}</p>
          <div class="actions">
            <m3e-button variant="filled" size="small" @click="start">开始采集</m3e-button>
          </div>
        </template>

        <template v-else-if="phase === 'running'">
          <div class="stage">
            <video ref="videoEl" class="video" autoplay playsinline muted></video>
            <div class="overlay">
              <span class="step">{{ index + 1 }} / {{ SEGMENTS.length }}</span>
              <strong class="title">{{ segment.title }}</strong>
              <span class="hint">{{ segment.hint }}</span>
              <span class="count mono">
                {{ recording ? `剩余 ${secondsLeft} 秒` : `${secondsToStart} 秒后开始` }}
              </span>
            </div>
          </div>
          <p class="status" :class="poseState">
            <span class="material-symbols-rounded">
              {{ poseState === "ok" ? "check_circle" : "error" }}
            </span>
            {{ poseHint }}
            <span class="frames mono">已采 {{ totalFrames }} 帧</span>
          </p>
          <p class="live mono">
            肩倾 {{ live.tilt }}° · 头前伸 {{ live.forward }} · 颈长比 {{ live.neck }}
          </p>
          <div class="actions">
            <m3e-button variant="outlined" size="small" @click="stop">提前结束</m3e-button>
          </div>
        </template>

        <template v-else>
          <p class="state">
            已保存 {{ totalFrames }} 帧到本机，等待上传云端训练。
          </p>
          <p class="path mono">{{ savedPath }}</p>
          <ul class="counts">
            <li v-for="item in SEGMENTS" :key="item.label">
              <span>{{ item.title }}</span>
              <b class="mono">{{ counts[item.label] ?? 0 }}</b>
            </li>
          </ul>
          <p v-if="error" class="state error">{{ error }}</p>
          <div class="actions">
            <m3e-button variant="filled" size="small" @click="reset">再采一组</m3e-button>
            <m3e-button variant="outlined" size="small" @click="openFolder">
              <span class="material-symbols-rounded" slot="icon">folder_open</span>
              打开文件夹
            </m3e-button>
          </div>
        </template>
      </div>
    </m3e-card>
  </div>
</template>

<style scoped>
.view {
  width: min(45rem, 100%);
  margin: 0 auto;
  padding: 2rem 1.5rem 2.5rem;
}

.head-row {
  display: flex;
  align-items: center;
  gap: 0.375rem;
}

.head-row h1 {
  margin: 0;
}

.panel {
  display: flex;
  gap: 1rem;
  margin-bottom: 1rem;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  font-size: 0.75rem;
  color: var(--md-sys-color-on-surface-variant);
}

.field input,
.field select {
  width: 9rem;
  padding: 0.5rem 0.625rem;
  border: none;
  border-radius: 0.75rem;
  background: var(--md-sys-color-surface-container-high);
  color: var(--md-sys-color-on-surface);
  font-size: 0.9rem;
}

.stage {
  position: relative;
  width: 100%;
  margin: 0 0 0.75rem;
  overflow: hidden;
  aspect-ratio: 4 / 3;
  border-radius: 1.25rem;
  background: #000;
}

.video {
  width: 100%;
  height: 100%;
  object-fit: cover;
  transform: scaleX(-1);
}

.overlay {
  position: absolute;
  inset: auto 0 0 0;
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
  padding: 1rem 1.25rem;
  background: linear-gradient(transparent, rgba(0, 0, 0, 0.72));
  color: #fff;
}

.step {
  font-size: 0.72rem;
  opacity: 0.75;
}

.title {
  font-size: 1.35rem;
}

.hint {
  font-size: 0.8rem;
  opacity: 0.8;
}

.count {
  margin-top: 0.25rem;
  font-size: 0.95rem;
}

.meta {
  margin: 0 0 0.75rem;
  color: var(--md-sys-color-on-surface-variant);
  font-size: 0.78rem;
}

.status {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  margin: 0 0 0.75rem;
  font-size: 0.8rem;
}

.status .material-symbols-rounded {
  font-size: 1rem;
}

.status.ok {
  color: var(--md-sys-color-primary);
}

.status.partial {
  color: var(--md-sys-color-tertiary);
}

.status.none {
  color: var(--md-sys-color-error);
}

.frames {
  margin-left: auto;
  color: var(--md-sys-color-on-surface-variant);
  font-size: 0.75rem;
}

.live {
  margin: 0 0 0.75rem;
  color: var(--md-sys-color-on-surface-variant);
  font-size: 0.72rem;
}

.actions {
  display: flex;
  gap: 0.75rem;
  margin-top: 0.75rem;
}

.state {
  margin: 0 0 0.5rem;
  font-size: 0.85rem;
}

.state.error {
  color: var(--md-sys-color-error);
}

.path {
  margin: 0 0 1rem;
  padding: 0.625rem 0.75rem;
  border-radius: 0.75rem;
  background: var(--md-sys-color-surface-container-high);
  font-size: 0.75rem;
  word-break: break-all;
}

.counts {
  display: grid;
  gap: 0.4rem;
  margin: 0 0 0.75rem;
  padding: 0;
  list-style: none;
  font-size: 0.8rem;
}

.counts li {
  display: flex;
  justify-content: space-between;
  color: var(--md-sys-color-on-surface-variant);
}
</style>
