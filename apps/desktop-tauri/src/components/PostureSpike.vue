<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import LoadingOverlay from "./LoadingOverlay.vue";
import { applyPostureRecommendation, evaluatePostureInfer, state } from "../state/session.js";
import { toContractKeypoints } from "../data/keypoints.js";
import { monitor, prefs as cameraPrefs } from "../state/postureMonitor.js";

const props = defineProps({
  inline: { type: Boolean, default: false },
  minimal: { type: Boolean, default: false },
});
const emit = defineEmits(["close"]);

const videoEl = ref(null);
const canvasEl = ref(null);
const running = ref(false);
const loading = ref(false);
const error = ref("");
const status = ref("摄像头未开启");
const fps = ref(0);
const pointCount = ref(0);
const posture = ref("undetermined");
const tilt = ref(0);
const confidence = ref(0);
const risk = ref(null);
const inferBusy = ref(false);
// 推理来源：huawei(云端) / mock(演示模型，未接真实云端) / local_fallback(端侧规则) / local_mode(本地演示)
const source = ref("local_fallback");
const latency = ref(0);
const guidanceText = ref("");
const cloudError = ref("");
const localPosture = ref("undetermined");
const localConfidence = ref(0);

const POSTURE_LABELS = {
  baseline: "基准姿态",
  lateral_tilt: "明显侧倾",
  undetermined: "未能识别",
};

const RISK_LABELS = {
  low: "低风险",
  medium: "中风险",
  high: "高风险",
  very_high: "极高风险",
};

const PLAN_LABELS = {
  maintain: "维持",
  quick: "快速",
  standard: "标准",
  intense: "强化",
};

const SOURCE_LABELS = {
  huawei: "华为云识别",
  mock: "演示模型",
  local_fallback: "端侧模式",
  local_mode: "本地演示",
};

const POSTURE_CONNECTIONS = [
  [0, 1], [1, 2], [2, 3], [3, 7], [0, 4], [4, 5], [5, 6], [6, 8],
  [9, 10], [11, 12], [11, 13], [13, 15], [15, 17], [15, 19], [15, 21],
  [17, 19], [12, 14], [14, 16], [16, 18], [16, 20], [16, 22], [18, 20],
  [11, 23], [12, 24], [23, 24], [23, 25], [25, 27], [27, 29], [29, 31],
  [27, 31], [24, 26], [26, 28], [28, 30], [30, 32], [28, 32],
];

const postureLabel = computed(() => POSTURE_LABELS[posture.value] || "未能识别");
const postureTone = computed(() => {
  if (posture.value === "baseline") return "ok";
  if (posture.value === "lateral_tilt") return "warn";
  return "muted";
});
const sourceLabel = computed(() => SOURCE_LABELS[source.value] || "端侧模式");
const sourceTone = computed(() => {
  if (source.value === "huawei") return "cloud";
  if (source.value === "mock") return "warn";
  return "muted";
});
const isCloudResult = computed(
  () => source.value === "huawei" || source.value === "mock"
);

const riskLevelLabel = computed(() => RISK_LABELS[risk.value?.risk_level] || "评估中");
const riskPlanLabel = computed(() => PLAN_LABELS[risk.value?.recommended_plan] || "—");

let stream = null;
let landmarker = null;
let rafId = 0;
let lastVideoTime = -1;
let frames = 0;
let fpsStartedAt = performance.now();
let lastInferAt = 0;
let postureSince = performance.now();
let lastPostureClass = "undetermined";
let latestLandmarks = null;

function resizeCanvas() {
  const video = videoEl.value;
  const canvas = canvasEl.value;
  if (!video || !canvas) return;
  const width = video.videoWidth || 1280;
  const height = video.videoHeight || 720;
  if (canvas.width !== width || canvas.height !== height) {
    canvas.width = width;
    canvas.height = height;
  }
}

async function ensureLandmarker() {
  if (landmarker) return landmarker;
  status.value = "正在准备姿势识别…";
  const { FilesetResolver, PoseLandmarker } = await import("@mediapipe/tasks-vision");
  const vision = await FilesetResolver.forVisionTasks("/mediapipe/wasm");
  const options = {
    baseOptions: {
      modelAssetPath: "/models/pose_landmarker_lite.task",
      delegate: "GPU",
    },
    runningMode: "VIDEO",
    numPoses: 1,
    minPoseDetectionConfidence: 0.5,
    minPosePresenceConfidence: 0.5,
    minTrackingConfidence: 0.5,
  };
  try {
    landmarker = await PoseLandmarker.createFromOptions(vision, options);
  } catch {
    options.baseOptions.delegate = "CPU";
    landmarker = await PoseLandmarker.createFromOptions(vision, options);
  }
  return landmarker;
}

function draw(landmarks) {
  const canvas = canvasEl.value;
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  if (!landmarks || landmarks.length === 0) return;

  const visible = (point) => (point?.visibility ?? 1) > 0.4;
  ctx.lineWidth = Math.max(2, canvas.width / 640);
  ctx.strokeStyle = "rgba(34, 211, 238, 0.9)";
  for (const [a, b] of POSTURE_CONNECTIONS) {
    const p1 = landmarks[a];
    const p2 = landmarks[b];
    if (!visible(p1) || !visible(p2)) continue;
    ctx.beginPath();
    ctx.moveTo(p1.x * canvas.width, p1.y * canvas.height);
    ctx.lineTo(p2.x * canvas.width, p2.y * canvas.height);
    ctx.stroke();
  }

  ctx.fillStyle = "rgba(244, 114, 182, 0.95)";
  for (const point of landmarks) {
    if (!visible(point)) continue;
    ctx.beginPath();
    ctx.arc(point.x * canvas.width, point.y * canvas.height, Math.max(2.5, canvas.width / 420), 0, Math.PI * 2);
    ctx.fill();
  }
}

function applyPosture(next, conf = 0, src = source.value) {
  source.value = src;
  confidence.value = conf;
  if (next !== lastPostureClass) {
    lastPostureClass = next;
    postureSince = performance.now();
  }
  posture.value = next;
}

function updateMetrics(landmarks) {
  if (!landmarks || landmarks.length === 0) {
    pointCount.value = 0;
    localPosture.value = "undetermined";
    localConfidence.value = 0;
    if (!isCloudResult.value) applyPosture("undetermined", 0, source.value);
    return;
  }
  pointCount.value = landmarks.length;
  const left = landmarks[11];
  const right = landmarks[12];
  const minVisibility = Math.min(left?.visibility ?? 0, right?.visibility ?? 0);
  if (!left || !right || minVisibility < 0.5) {
    localPosture.value = "undetermined";
    localConfidence.value = minVisibility;
    if (!isCloudResult.value) applyPosture("undetermined", minVisibility, source.value);
    return;
  }
  let degrees = (Math.atan2(right.y - left.y, right.x - left.x) * 180) / Math.PI;
  if (degrees > 90) degrees -= 180;
  if (degrees < -90) degrees += 180;
  tilt.value = Math.round(degrees * 10) / 10;
  localPosture.value = Math.abs(degrees) > 8 ? "lateral_tilt" : "baseline";
  localConfidence.value = minVisibility;
  // 云端结果优先；未拿到云端结果时才用端侧规则
  if (!isCloudResult.value) applyPosture(localPosture.value, minVisibility, source.value);
}

const REASON_TEXT = {
  timeout: "请求超时",
  endpoint_not_configured: "模型地址未配置",
  invalid_response: "返回内容不完整",
  unknown_posture_label: "结果无法识别",
};

function describeInferError(err) {
  if (err?.status === 503) {
    const reason = err.payload?.detail?.reason ?? "";
    const detail = REASON_TEXT[reason] ? `（${REASON_TEXT[reason]}）` : "";
    return `云端暂时不可用${detail}，先用端侧模式`;
  }
  if (err?.status === 0) return "连不上云端，先用端侧模式";
  if (err?.status === 422) return "关键点数据有误，先用端侧模式";
  return "云端识别没成功，先用端侧模式";
}

async function maybeInfer() {
  if (!running.value || inferBusy.value) return;
  const now = performance.now();
  if (now - lastInferAt < 2000) return;
  lastInferAt = now;

  const keypoints = toContractKeypoints(latestLandmarks);
  if (!keypoints) {
    risk.value = null;
    return;
  }

  inferBusy.value = true;
  try {
    const sittingMinutes = Math.floor((state.timer?.sitting_seconds ?? 0) / 60);
    const result = await evaluatePostureInfer({
      keypoints,
      source: "mediapipe-pose-33",
      captured_at: new Date().toISOString(),
      posture_duration_minutes: Math.max(0, (now - postureSince) / 60000),
      sitting_minutes: sittingMinutes,
      daily_sitting_minutes: sittingMinutes,
      minutes_since_last_break: sittingMinutes,
      pain_score: state.assessment?.pain_score ?? 0,
      body_parts: state.assessment?.body_parts ?? [],
      plan: state.planPreference,
    });

    if (result?.localMode) {
      // 本地演示模式：不发云端请求
      source.value = "local_mode";
      cloudError.value = "";
      risk.value = null;
      applyPosture(localPosture.value, localConfidence.value, "local_mode");
      return;
    }
    if (!result) {
      // 安全短路：已切到安全提示界面，不展示姿态结论
      risk.value = null;
      return;
    }

    applyPosture(result.posture, result.confidence, result.source);
    guidanceText.value = result.guidance?.message ?? "";
    latency.value = result.latency_ms ?? 0;
    cloudError.value = "";
    risk.value = result.risk;
  } catch (err) {
    cloudError.value = describeInferError(err);
    risk.value = null;
    applyPosture(localPosture.value, localConfidence.value, "local_fallback");
  } finally {
    inferBusy.value = false;
  }
}

function adoptRisk() {
  if (state.phase !== "main") return;
  if (applyPostureRecommendation(risk.value)) emit("close");
}

function tick() {
  if (!running.value) return;
  const video = videoEl.value;
  if (video && landmarker && video.readyState >= 2 && video.currentTime !== lastVideoTime) {
    resizeCanvas();
    lastVideoTime = video.currentTime;
    try {
      const results = landmarker.detectForVideo(video, performance.now());
      const landmarks = results?.landmarks?.[0] || [];
      latestLandmarks = landmarks.length ? landmarks : null;
      draw(landmarks);
      updateMetrics(landmarks);
      void maybeInfer();
      frames += 1;
    } catch (err) {
      error.value = "识别中断了，请重新开启摄像头。";
      stop();
      return;
    }
  }
  const now = performance.now();
  if (now - fpsStartedAt >= 1000) {
    fps.value = frames;
    frames = 0;
    fpsStartedAt = now;
  }
  rafId = requestAnimationFrame(tick);
}

let pausedMonitor = false;

async function start() {
  if (running.value || loading.value) return;
  loading.value = true;
  error.value = "";

  // 常驻监测也在用摄像头时先让出，避免两路同时占用
  if (monitor.status === "running") {
    pausedMonitor = true;
    await monitor.pause();
  }
  try {
    try {
      await ensureLandmarker();
    } catch (err) {
      error.value = "姿势模型没加载成功。刷新页面再试一次。";
      status.value = "模型未加载";
      return;
    }
    if (!navigator.mediaDevices?.getUserMedia) {
      error.value = "这个环境打不开摄像头，请在桌面应用里试。";
      status.value = "摄像头未开启";
      return;
    }
    // 始终沿用用户在授权弹窗里选定的摄像头，避免各处取到不同设备
    const deviceId = cameraPrefs.deviceId;
    const baseVideo = {
      width: { ideal: 640 },
      height: { ideal: 480 },
      frameRate: { ideal: 15, max: 30 },
    };
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        video: deviceId ? { ...baseVideo, deviceId: { exact: deviceId } } : { ...baseVideo, facingMode: "user" },
        audio: false,
      });
    } catch (err) {
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          video: { ...baseVideo, facingMode: "user" },
          audio: false,
        });
      } catch (err2) {
        error.value = "打不开摄像头。先看系统权限，再确认是否被别的程序占用。";
        status.value = "摄像头未开启";
        return;
      }
    }
    const video = videoEl.value;
    video.onloadedmetadata = () => resizeCanvas();
    video.srcObject = stream;
    await video.play();
    resizeCanvas();
    running.value = true;
    lastVideoTime = -1;
    frames = 0;
    fpsStartedAt = performance.now();
    lastInferAt = 0;
    postureSince = performance.now();
    lastPostureClass = "undetermined";
    confidence.value = 0;
    risk.value = null;
    latency.value = 0;
    guidanceText.value = "";
    cloudError.value = "";
    source.value = "local_fallback";
    localPosture.value = "undetermined";
    localConfidence.value = 0;
    status.value = "画面不上传，每 2 秒上传一次关键点";
    tick();
  } catch (err) {
    error.value = "启动没成功，请重试一次。";
    status.value = "摄像头未开启";
    stop();
  } finally {
    loading.value = false;
  }
}

function stop() {
  running.value = false;
  if (pausedMonitor) {
    pausedMonitor = false;
    monitor.resume().catch(() => { });
  }
  if (rafId) cancelAnimationFrame(rafId);
  rafId = 0;
  if (stream) {
    stream.getTracks().forEach((track) => track.stop());
    stream = null;
  }
  if (videoEl.value) videoEl.value.srcObject = null;
  const canvas = canvasEl.value;
  if (canvas) canvas.getContext("2d")?.clearRect(0, 0, canvas.width, canvas.height);
  fps.value = 0;
  pointCount.value = 0;
  posture.value = "undetermined";
  lastPostureClass = "undetermined";
  confidence.value = 0;
  tilt.value = 0;
  risk.value = null;
  inferBusy.value = false;
  lastInferAt = 0;
  latestLandmarks = null;
  latency.value = 0;
  guidanceText.value = "";
  cloudError.value = "";
  source.value = "local_fallback";
  postureSince = performance.now();
  if (!error.value) status.value = "摄像头已关闭";
}

function close() {
  stop();
  if (landmarker) {
    landmarker.close();
    landmarker = null;
  }
  emit("close");
}

onMounted(() => {
  if (props.minimal) void start();
});

onBeforeUnmount(() => {
  stop();
  if (landmarker) {
    landmarker.close();
    landmarker = null;
  }
});
</script>

<template>
  <div :class="props.inline || props.minimal ? 'posture-inline' : 'posture-overlay'"
    @click.self="!props.inline && !props.minimal && close()">
    <section class="panel" :class="{ inline: props.inline, minimal: props.minimal }" role="dialog"
      :aria-modal="props.inline ? undefined : 'true'" aria-label="姿势检查">
      <header v-if="!props.inline && !props.minimal" class="head">
        <div>
          <h2>姿势检查</h2>
          <p>画面只在本地处理，不上传原始画面</p>
        </div>
        <m3e-icon-button class="close" variant="standard" size="small" aria-label="关闭" @click="close">
          <span class="material-symbols-rounded">close</span>
        </m3e-icon-button>
      </header>

      <div class="stage">
        <video ref="videoEl" class="video" autoplay playsinline muted />
        <canvas ref="canvasEl" class="canvas" />
        <LoadingOverlay v-if="loading" label="正在准备姿势识别…" />
        <div v-if="!running && !loading" class="placeholder">
          <span class="material-symbols-rounded">videocam_off</span>
          <p>{{ status }}</p>
        </div>
        <div v-if="!props.minimal" class="badges">
          <span class="badge" :class="postureTone">{{ postureLabel }}</span>
          <span class="badge" :class="sourceTone">{{ sourceLabel }}</span>
          <span class="badge">FPS {{ fps }}</span>
          <span class="badge">关键点 {{ pointCount }}</span>
        </div>
      </div>

      <div v-if="!props.minimal" class="metrics">
        <div>
          <span>肩线倾角</span>
          <strong>{{ tilt }}°</strong>
        </div>
        <div>
          <span>姿态类别</span>
          <strong>{{ postureLabel }}</strong>
        </div>
        <div>
          <span>推理来源</span>
          <strong>{{ sourceLabel }}</strong>
        </div>
        <div>
          <span>云端耗时</span>
          <strong>{{ latency ? latency + " ms" : "—" }}</strong>
        </div>
        <div>
          <span>上传策略</span>
          <strong>仅关键点 · 不传画面</strong>
        </div>
      </div>

      <section v-if="!props.minimal" class="risk">
        <div class="risk-head">
          <span>实时风险</span>
          <span class="risk-badge" :class="risk?.risk_level || 'unknown'">
            {{ risk ? riskLevelLabel : inferBusy ? "识别中…" : "等待识别" }}
          </span>
        </div>
        <template v-if="risk">
          <p class="risk-line">
            负荷指数 <b class="mono">{{ risk.brli.toFixed(2) }}</b> · 建议方案：{{ riskPlanLabel }}
          </p>
          <p class="risk-line" v-if="risk.actions?.length">
            首选动作：{{ risk.actions[0].name }}（{{ risk.actions[0].duration_minutes }} 分钟）
          </p>
          <p class="risk-line muted" v-else>{{ risk.reason }}</p>
          <p class="risk-line muted" v-if="guidanceText">{{ guidanceText }}</p>
          <p class="risk-line danger" v-if="risk.needs_medical_advice">出现明显不适，建议暂停并就医。</p>
          <m3e-button v-if="risk.actions?.length && !props.inline" class="risk-action" variant="filled" size="small"
            @click="adoptRisk">
            采用推荐方案
          </m3e-button>
        </template>
        <p v-else class="risk-line muted">
          {{ inferBusy ? "正在识别…" : "保持姿势稳定就会开始评估。云端不可用时，自动切到端侧模式。" }}
        </p>
        <p v-if="cloudError" class="risk-line warn-line">{{ cloudError }}</p>
      </section>

      <p v-if="error && !props.minimal" class="error">{{ error }}</p>

      <footer v-if="!props.minimal" class="actions">
        <m3e-button v-if="!running" variant="filled" size="small" :disabled.prop="loading" @click="start">
          {{ loading ? "加载中…" : "开启摄像头" }}
        </m3e-button>
        <m3e-button v-else variant="outlined" size="small" @click="stop">关闭摄像头</m3e-button>
        <span class="hint">关键点在本地提取，分类和风险由云端给出。演示环境还没接入云端真实模型，失败时会切到端侧模式。</span>
      </footer>
    </section>
  </div>
</template>

<style scoped>
.posture-overlay {
  position: fixed;
  inset: 0;
  z-index: 80;
  display: grid;
  place-items: center;
  padding: 1.5rem;
  background: rgba(10, 12, 16, 0.72);
  backdrop-filter: blur(0.5rem);
}

.posture-inline {
  width: 100%;
}

.panel.inline {
  width: 100%;
  max-height: none;
  padding: 0;
  background: transparent;
  box-shadow: none;
}

.panel.minimal {
  width: 100%;
  height: auto;
  max-height: none;
  padding: 0;
  overflow: hidden;
  border-radius: 0;
  background: transparent;
  box-shadow: none;
}

.panel.minimal .stage {
  position: relative;
  inset: auto;
  width: 100%;
  height: auto;
  aspect-ratio: 16 / 9;
  border-radius: 0;
}

.panel {
  position: relative;
  width: min(55rem, 100%);
  max-height: 92vh;
  overflow: auto;
  padding: 1.25rem;
  border-radius: 1.5rem;
  background: var(--md-sys-color-surface-container-high, #1c1b1f);
  color: var(--md-sys-color-on-surface, #e6e1e5);
  box-shadow: 0 1.5rem 5rem rgba(0, 0, 0, 0.45);
}

.head {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  align-items: flex-start;
  margin-bottom: 0.875rem;
}

.head h2 {
  margin: 0 0 0.25rem;
  font-size: 1.2rem;
}

.head p {
  margin: 0;
  opacity: 0.7;
  font-size: 0.86rem;
}

.close {
  --m3e-icon-button-icon-size: 1.375rem;
  color: inherit;
}

.stage {
  position: relative;
  aspect-ratio: 16 / 9;
  overflow: hidden;
  border-radius: 1.125rem;
  background: #000;
}

.video,
.canvas {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  transform: scaleX(-1);
}

.canvas {
  pointer-events: none;
}

.placeholder {
  position: absolute;
  inset: 0;
  display: grid;
  place-content: center;
  justify-items: center;
  gap: 0.5rem;
  color: rgba(255, 255, 255, 0.7);
  font-size: 0.9rem;
}

.placeholder .material-symbols-rounded {
  font-size: 2.4rem;
}

.badges {
  position: absolute;
  left: 0.75rem;
  bottom: 0.75rem;
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.badge {
  padding: 0.25rem 0.625rem;
  border-radius: 62.438rem;
  background: rgba(0, 0, 0, 0.6);
  color: #fff;
  font-size: 0.75rem;
}

.badge.ok {
  background: rgba(16, 185, 129, 0.85);
}

.badge.warn {
  background: rgba(245, 158, 11, 0.9);
}

.badge.cloud {
  background: rgba(56, 189, 248, 0.85);
}

.badge.muted {
  background: rgba(107, 114, 128, 0.85);
}

.metrics {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.625rem;
  margin: 0.875rem 0;
}

.metrics div {
  padding: 0.625rem 0.75rem;
  border-radius: 0.875rem;
  background: rgba(255, 255, 255, 0.06);
}

.metrics span {
  display: block;
  font-size: 0.75rem;
  opacity: 0.65;
}

.metrics strong {
  display: block;
  margin-top: 0.25rem;
  font-size: 0.95rem;
}

.risk {
  margin: 0.875rem 0 0.25rem;
  padding: 0.75rem 0.875rem;
  border-radius: 0.875rem;
  background: rgba(255, 255, 255, 0.06);
}

.risk-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  font-size: 0.82rem;
  opacity: 0.85;
}

.risk-badge {
  padding: 0.2rem 0.563rem;
  border-radius: 62.438rem;
  background: rgba(107, 114, 128, 0.85);
  color: #fff;
  font-size: 0.72rem;
}

.risk-badge.low {
  background: rgba(16, 185, 129, 0.85);
}

.risk-badge.medium {
  background: rgba(245, 158, 11, 0.9);
}

.risk-badge.high {
  background: rgba(249, 115, 22, 0.92);
}

.risk-badge.very_high {
  background: rgba(239, 68, 68, 0.92);
}

.risk-line {
  margin: 0.5rem 0 0;
  font-size: 0.8rem;
  line-height: 1.6;
}

.risk-line.muted {
  opacity: 0.65;
}

.risk-line.danger {
  color: #fca5a5;
}

.risk-line.warn-line {
  color: #fcd34d;
}

.risk-action {
  margin-top: 0.625rem;
}

.error {
  margin: 0 0 0.625rem;
  padding: 0.625rem 0.75rem;
  border-radius: 0.75rem;
  background: rgba(239, 68, 68, 0.16);
  color: #fca5a5;
  font-size: 0.84rem;
}

.actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.75rem;
}

.hint {
  font-size: 0.75rem;
  opacity: 0.6;
}
</style>
