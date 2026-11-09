<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";
import ErrorBanner from "./ErrorBanner.vue";
import LoadingOverlay from "./LoadingOverlay.vue";
import { sourceForAction } from "../data/actionSources.js";
import { prefs as cameraPrefs } from "../state/postureMonitor.js";
import { selectPendingAction, state, submitFeedback } from "../state/session.js";

const actions = computed(() => {
  if (state.pendingActions?.length) return state.pendingActions;
  return state.pending ? [state.pending] : [];
});
const index = ref(0);
const action = computed(() => actions.value[index.value] ?? null);
const source = computed(() => sourceForAction(action.value?.id));

const videoEl = ref(null);
const cameraOn = ref(false);
const cameraChecked = ref(false);
let stream = null;

const remaining = ref(0);
const running = ref(false);
const finished = ref(false);
const submitting = ref(false);
const error = ref("");

const feeling = ref("same");
const painScore = ref(state.assessment?.pain_score ?? 2);
const obstacle = ref(null);

const feelingOptions = [
  { value: "better", label: "好转" },
  { value: "same", label: "没变化" },
  { value: "worse", label: "更不舒服" },
];

const obstacleOptions = [
  { value: "busy", label: "太忙" },
  { value: "too_hard", label: "动作太难" },
  { value: "no_space", label: "没地方做" },
  { value: "forgot", label: "忘了" },
];

const totalSeconds = computed(() => Math.max(1, (action.value?.duration_minutes ?? 1) * 60));
const progress = computed(() =>
  Math.max(0, Math.min(100, ((totalSeconds.value - remaining.value) / totalSeconds.value) * 100))
);
const timeText = computed(() => {
  const seconds = Math.max(0, remaining.value);
  const mm = String(Math.floor(seconds / 60)).padStart(2, "0");
  const ss = String(seconds % 60).padStart(2, "0");
  return mm + ":" + ss;
});

let timer = null;
let advanceTimer = null;
let autoStartArmed = false;

async function canUseCamera() {
  if (cameraPrefs.deviceId) return true;
  try {
    const status = await navigator.permissions.query({ name: "camera" });
    return status.state === "granted";
  } catch {
    return false;
  }
}

function closeCamera() {
  if (stream) {
    stream.getTracks().forEach((track) => track.stop());
    stream = null;
  }
  if (videoEl.value) videoEl.value.srcObject = null;
}

// 只保留一个 video：拿到已授权设备就直接出画面，不再跑关键点
async function syncCamera() {
  cameraChecked.value = false;
  cameraOn.value = false;
  if (!(await canUseCamera())) {
    cameraChecked.value = true;
    return;
  }
  try {
    const deviceId = cameraPrefs.deviceId;
    stream = await navigator.mediaDevices.getUserMedia({
      video: deviceId
        ? { deviceId: { exact: deviceId }, width: { ideal: 640 }, height: { ideal: 480 } }
        : { width: { ideal: 640 }, height: { ideal: 480 } },
      audio: false,
    });
    cameraOn.value = true;
    cameraChecked.value = true;
    await nextTick();
    if (videoEl.value) {
      videoEl.value.srcObject = stream;
      await videoEl.value.play().catch(() => { });
    }
  } catch {
    cameraOn.value = false;
    cameraChecked.value = true;
    closeCamera();
  }
}

function disarmAutoStart() {
  document.removeEventListener("pointerdown", onFirstFocus, true);
  document.removeEventListener("pointermove", onFirstFocus, true);
  window.removeEventListener("focus", onFirstFocus);
  autoStartArmed = false;
}

function onFirstFocus() {
  disarmAutoStart();
  startTick();
}

function armAutoStart() {
  if (autoStartArmed) return;
  autoStartArmed = true;
  document.addEventListener("pointerdown", onFirstFocus, true);
  document.addEventListener("pointermove", onFirstFocus, true);
  window.addEventListener("focus", onFirstFocus);
}

function stopTick() {
  running.value = false;
  if (timer) clearInterval(timer);
  timer = null;
}

function startTick() {
  if (running.value || remaining.value <= 0 || finished.value) return;
  running.value = true;
  timer = setInterval(() => {
    if (remaining.value <= 0) {
      stopTick();
      return;
    }
    remaining.value -= 1;
    if (remaining.value <= 0) onActionDone();
  }, 1000);
}

function onActionDone() {
  stopTick();
  if (index.value < actions.value.length - 1) {
    advanceTimer = setTimeout(() => {
      index.value += 1;
      remaining.value = totalSeconds.value;
      startTick();
    }, 600);
    return;
  }
  finished.value = true;
}

function resetSequence() {
  stopTick();
  if (advanceTimer) clearTimeout(advanceTimer);
  advanceTimer = null;
  index.value = 0;
  remaining.value = totalSeconds.value;
  finished.value = false;
  error.value = "";
  feeling.value = "same";
  painScore.value = state.assessment?.pain_score ?? 2;
  obstacle.value = null;
}

function pickAction(item) {
  stopTick();
  if (advanceTimer) clearTimeout(advanceTimer);
  const next = actions.value.findIndex((candidate) => candidate.id === item.id);
  selectPendingAction(item);
  index.value = next >= 0 ? next : 0;
  remaining.value = totalSeconds.value;
  finished.value = false;
  window.setTimeout(() => startTick(), 60);
}

watch(
  () => state.pending?.id,
  (id) => {
    if (!id) return;
    resetSequence();
    void syncCamera();
    armAutoStart();
  },
  { immediate: true }
);

function onPainChange(event) {
  const target = event.target;
  const value = target.thumb ? target.thumb.value : target.value;
  if (value !== null && value !== undefined && value !== "") {
    painScore.value = Number(value);
  }
}

function pickField(event, field, value) {
  field.value = value;
  const button = event?.currentTarget;
  if (button) button.selected = true;
}

async function submit(completion) {
  if (!action.value || submitting.value) return;
  submitting.value = true;
  error.value = "";
  try {
    await submitFeedback({
      action_id: action.value.id,
      completion,
      feeling: feeling.value,
      pain_score: painScore.value,
      obstacle: completion === "skipped" ? obstacle.value : null,
      next_day_worse: false,
      red_flags: [],
    });
    stopTick();
    disarmAutoStart();
  } catch {
    error.value = "提交没成功，请再试一次。";
  } finally {
    submitting.value = false;
  }
}

onBeforeUnmount(() => {
  disarmAutoStart();
  stopTick();
  closeCamera();
  if (advanceTimer) clearTimeout(advanceTimer);
});
</script>

<template>
  <div class="activity-panel">
    <div class="overlay-layout">
      <section v-if="action" class="overlay-card plan-card">
        <header class="card-head">
          <h2>{{ action.name }}</h2>
          <span class="step-count">第 {{ index + 1 }} / {{ actions.length }} 个动作</span>
        </header>

        <p class="lead">{{ action.match_reason || "按当前状态匹配" }}</p>

        <m3e-tabs v-if="actions.length > 1" class="plan-tabs">
          <m3e-tab v-for="item in actions" :key="item.id" :selected.prop="item.id === action?.id"
            @click="pickAction(item)">
            {{ item.name }}
          </m3e-tab>
        </m3e-tabs>

        <div class="plan-body">
          <div class="guide-media" aria-hidden="true">
            <span class="material-symbols-rounded">image</span>
            <span>动作示意图</span>
          </div>
          <div class="plan-text">
            <ol class="steps">
              <li v-for="(step, stepIndex) in action.steps || []" :key="stepIndex">{{ step }}</li>
            </ol>
            <p v-if="action.caution" class="caution">{{ action.caution }}</p>
          </div>
        </div>

        <div class="media-row">
          <div class="camera">
            <video v-if="cameraOn" ref="videoEl" class="camera-video" autoplay muted playsinline></video>
            <div v-else class="camera-off">
              <span class="material-symbols-rounded">videocam_off</span>
              <span>{{ cameraChecked ? "未开启" : "检查中" }}</span>
            </div>
          </div>

          <div class="timer">
            <div class="timer-head">
              <span class="mono time">{{ timeText }}</span>
              <span class="step-status">{{ finished ? "已完成" : running ? "进行中" : "准备开始" }}</span>
            </div>
            <m3e-linear-progress-indicator class="progress" :value.prop="progress"></m3e-linear-progress-indicator>
            <div class="timer-actions">
              <m3e-button v-if="!running && !finished" variant="tonal" size="small" @click="startTick">
                {{ remaining === totalSeconds ? "开始倒计时" : "继续" }}
              </m3e-button>
              <m3e-button v-else-if="running" variant="text" size="small" @click="stopTick">暂停</m3e-button>
              <span v-if="finished" class="done">全部动作已完成，请提交反馈</span>
            </div>
          </div>
        </div>
      </section>

      <section class="overlay-card feedback-card">
        <header class="card-head">
          <h3>完成反馈</h3>
        </header>

        <div class="feedback-grid">
          <div class="field">
            <span class="field-label">做完的感觉</span>
            <m3e-button-group class="segments">
              <m3e-button v-for="option in feelingOptions" :key="option.value" toggle variant="outlined"
                :selected.prop="feeling === option.value" @click="pickField($event, feeling, option.value)">
                {{ option.label }}
              </m3e-button>
            </m3e-button-group>
          </div>

          <div class="field">
            <span class="field-label">如果跳过，主要阻碍</span>
            <m3e-button-group class="segments">
              <m3e-button v-for="option in obstacleOptions" :key="option.value" toggle variant="outlined"
                :selected.prop="obstacle === option.value" @click="pickField($event, obstacle, option.value)">
                {{ option.label }}
              </m3e-button>
            </m3e-button-group>
          </div>

          <div class="field field-wide">
            <span class="field-label">疼痛评分：{{ painScore }} / 10</span>
            <m3e-slider max="10" step="1" @input="onPainChange" @change="onPainChange">
              <m3e-slider-thumb :value.prop="painScore"></m3e-slider-thumb>
            </m3e-slider>
          </div>
        </div>

        <p v-if="error" class="error">{{ error }}</p>
        <ErrorBanner :error="state.error" />

        <div class="feedback-actions">
          <m3e-button variant="filled" size="medium" :disabled.prop="submitting" @click="submit('completed')">
            完成
          </m3e-button>
          <m3e-button variant="outlined" size="medium" :disabled.prop="submitting" @click="submit('partial')">
            部分完成
          </m3e-button>
          <m3e-button variant="text" size="medium" :disabled.prop="submitting" @click="submit('skipped')">
            跳过
          </m3e-button>
        </div>
      </section>

      <LoadingOverlay v-if="submitting" label="正在提交反馈…" />
    </div>
  </div>
</template>

<style scoped>
/* 与干预卡片互斥显示，直接占满内容区 */
.activity-panel {
  display: grid;
  place-items: start center;
  padding: 0.5rem 0 1rem;
}

.overlay-layout {
  position: relative;
  display: grid;
  grid-template-columns: 1fr;
  gap: 1rem;
  width: min(56rem, 100%);
  max-height: 100%;
  overflow: auto;
  padding: 0.2rem;
}

.overlay-card {
  position: relative;
  padding: 1.25rem;
  border-radius: 1.25rem;
  background: var(--md-sys-color-surface-container-high, #1c1b1f);
  color: var(--md-sys-color-on-surface, #e6e1e5);
  box-shadow: 0 1rem 3rem rgba(0, 0, 0, 0.35);
}

.card-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.75rem;
  margin-bottom: 0.5rem;
}

.card-head h2 {
  margin: 0;
  font-size: 1.1rem;
}

.card-head h3 {
  margin: 0;
  font-size: 0.95rem;
  color: var(--md-sys-color-on-surface-variant);
}

.step-count {
  color: var(--md-sys-color-outline);
  font-size: 0.72rem;
  white-space: nowrap;
}

.lead {
  margin: 0 0 0.5rem;
  color: var(--md-sys-color-on-surface-variant);
  font-size: 0.8rem;
}

.plan-tabs {
  margin-bottom: 0.75rem;
}

.plan-body {
  display: grid;
  grid-template-columns: 9rem minmax(0, 1fr);
  gap: 1rem;
  align-items: start;
}

.guide-media {
  display: grid;
  place-content: center;
  justify-items: center;
  gap: 0.4rem;
  width: 9rem;
  aspect-ratio: 3 / 4;
  border: 1px dashed var(--md-sys-color-outline-variant);
  border-radius: 0.9rem;
  background: var(--md-sys-color-surface-1);
  color: var(--md-sys-color-outline);
  font-size: 0.7rem;
}

.guide-media .material-symbols-rounded {
  font-size: 1.8rem;
}

.plan-text {
  min-width: 0;
}

.steps {
  margin: 0 0 0.6rem;
  padding-left: 1.2rem;
  font-size: 0.9rem;
  line-height: 1.7;
}

.caution {
  margin: 0;
  color: var(--md-sys-color-error);
  font-size: 0.78rem;
}

/* 摄像头与倒计时同一行：宽度对齐示意图，高度跟随计时器 */
.media-row {
  display: grid;
  grid-template-columns: 9rem minmax(0, 1fr);
  gap: 1rem;
  align-items: stretch;
  margin-top: 0.9rem;
}

.camera {
  position: relative;
  width: 9rem;
  overflow: hidden;
  border-radius: 0.9rem;
  background: #000;
}

.camera-video {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
  transform: scaleX(-1);
}

.camera-off {
  display: grid;
  place-content: center;
  justify-items: center;
  gap: 0.3rem;
  height: 100%;
  color: var(--md-sys-color-outline);
  font-size: 0.68rem;
}

.camera-off .material-symbols-rounded {
  font-size: 1.4rem;
}

.timer {
  padding: 0.75rem 0.9rem;
  border-radius: 0.9rem;
  background: var(--md-sys-color-surface-1);
}

.timer-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.75rem;
}

.time {
  font-size: 1.35rem;
  font-weight: 700;
  color: var(--md-sys-color-primary);
}

.step-status {
  color: var(--md-sys-color-outline);
  font-size: 0.72rem;
}

.progress {
  margin: 0.5rem 0;
}

.timer-actions {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.done {
  color: var(--md-sys-color-tertiary);
  font-size: 0.75rem;
}

.feedback-grid {
  gap: 0.75rem 1.5rem;
}

.field {
  display: grid;
  gap: 0.35rem;
}

.field-wide {
  grid-column: 1 / -1;
}

.field-label {
  color: var(--md-sys-color-on-surface-variant);
  font-size: 0.78rem;
}

.segments {
  display: flex;
  flex-wrap: wrap;
}

.error {
  margin: 0.6rem 0 0;
  color: var(--md-sys-color-error);
  font-size: 0.8rem;
}

.feedback-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-top: 0.75rem;
}

@media (max-width: 720px) {
  .plan-body,
  .media-row {
    grid-template-columns: 1fr;
  }

  .guide-media,
  .camera {
    width: 100%;
  }
}
</style>