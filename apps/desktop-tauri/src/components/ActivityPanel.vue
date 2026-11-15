<script setup>
import { computed, onBeforeUnmount, ref, watch } from "vue";
import ActionCamera from "./ActionCamera.vue";
import ErrorBanner from "./ErrorBanner.vue";
import LoadingOverlay from "./LoadingOverlay.vue";
import { resolveFraming } from "../data/actionFraming.js";
import { state, submitFeedback } from "../state/session.js";

const actions = computed(() => {
  if (state.pendingActions?.length) return state.pendingActions;
  return state.pending ? [state.pending] : [];
});

const actionIndex = ref(0);
const action = computed(() => actions.value[actionIndex.value] ?? null);
const steps = computed(() => {
  const list = action.value?.steps ?? [];
  return list.length ? list : ["按上面的提示完成这个动作"];
});
const stepIndex = ref(0);
const cameraOpen = ref(true);

const framing = computed(() => resolveFraming(action.value));

const feedbackOpen = ref(false);
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

// 动作总时长均分到每一步，最后一步吃掉余数，保证总和不变
function splitSeconds(total, count) {
  const size = Math.max(1, count);
  const base = Math.floor(total / size);
  const list = Array.from({ length: size }, () => base);
  list[size - 1] = total - base * (size - 1);
  return list;
}

const stepSeconds = computed(() =>
  splitSeconds((action.value?.duration_minutes ?? 1) * 60, steps.value.length)
);
const stepTotal = computed(() => stepSeconds.value[stepIndex.value] ?? 60);
const remaining = ref(stepTotal.value);
const running = ref(false);

const progress = computed(() =>
  Math.max(0, Math.min(100, ((stepTotal.value - remaining.value) / stepTotal.value) * 100))
);
const timeText = computed(() => {
  const seconds = Math.max(0, remaining.value);
  const mm = String(Math.floor(seconds / 60)).padStart(2, "0");
  const ss = String(seconds % 60).padStart(2, "0");
  return mm + ":" + ss;
});
const counterText = computed(() => {
  const stepsPart = `第 ${stepIndex.value + 1} / ${steps.value.length} 步`;
  if (actions.value.length <= 1) return stepsPart;
  return `动作 ${actionIndex.value + 1} / ${actions.value.length} · ${stepsPart}`;
});

let timer = null;
let autoStartArmed = false;

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
  if (running.value || remaining.value <= 0 || feedbackOpen.value) return;
  running.value = true;
  timer = setInterval(() => {
    if (remaining.value <= 0) {
      stopTick();
      return;
    }
    remaining.value -= 1;
    if (remaining.value <= 0) onStepDone();
  }, 1000);
}

function resetStep() {
  remaining.value = stepSeconds.value[stepIndex.value] ?? 60;
}

function onStepDone() {
  stopTick();
  if (stepIndex.value < steps.value.length - 1) {
    stepIndex.value += 1;
    resetStep();
    startTick();
    return;
  }
  onActionDone();
}

function stepForward(auto) {
  if (stepIndex.value < steps.value.length - 1) {
    stepIndex.value += 1;
    resetStep();
    if (auto || running.value) startTick();
    return;
  }
  if (auto) {
    onActionDone();
    return;
  }
  onActionDone();
}

function onActionDone() {
  stopTick();
  if (actionIndex.value < actions.value.length - 1) {
    actionIndex.value += 1;
    stepIndex.value = 0;
    resetStep();
    startTick();
    return;
  }
  openFeedback();
}

function nextStep() {
  disarmAutoStart();
  stepForward(false);
}

function prevStep() {
  disarmAutoStart();
  if (stepIndex.value === 0) return;
  stopTick();
  stepIndex.value -= 1;
  resetStep();
}

function skipAction() {
  disarmAutoStart();
  stopTick();
  if (actionIndex.value < actions.value.length - 1) {
    actionIndex.value += 1;
    stepIndex.value = 0;
    resetStep();
    startTick();
    return;
  }
  openFeedback();
}

function openFeedback() {
  stopTick();
  disarmAutoStart();
  feedbackOpen.value = true;
}

function resetSequence() {
  stopTick();
  actionIndex.value = 0;
  stepIndex.value = 0;
  feedbackOpen.value = false;
  error.value = "";
  feeling.value = "same";
  painScore.value = state.assessment?.pain_score ?? 2;
  obstacle.value = null;
  resetStep();
}

watch(
  () => state.pendingActions,
  () => {
    if (!state.pending?.id) return;
    resetSequence();
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
});
</script>
<template>
  <div class="activity-panel">
    <m3e-card v-if="action && !feedbackOpen" variant="elevated" class="surface-card">
      <div class="surface-body plan-body-wrap">
        <div class="step-head">
          <span class="step-count">{{ counterText }}</span>
          <m3e-button variant="text" size="small" @click="cameraOpen = !cameraOpen">
            {{ cameraOpen ? "收起画面" : "打开画面" }}
          </m3e-button>
        </div>

        <div class="media-row" :class="{ 'no-camera': !cameraOpen }">
          <ActionCamera v-if="cameraOpen" :framing="framing" />

          <div class="stage">
            <p class="step-text">{{ steps[stepIndex] }}</p>
            <p v-if="action.caution" class="caution">{{ action.caution }}</p>

            <div class="timer">
              <div class="timer-head">
                <span class="mono time">{{ timeText }}</span>
                <span class="step-status">{{ running ? "进行中" : "已暂停" }}</span>
              </div>
              <m3e-linear-progress-indicator class="progress" :value.prop="progress"></m3e-linear-progress-indicator>
              <div class="timer-actions">
                <m3e-button v-if="!running" variant="tonal" size="small" @click="startTick">
                  {{ remaining === stepTotal ? "开始倒计时" : "继续" }}
                </m3e-button>
                <m3e-button v-else variant="text" size="small" @click="stopTick">暂停</m3e-button>
                <m3e-button variant="text" size="small" :disabled.prop="stepIndex === 0" @click="prevStep">
                  上一步
                </m3e-button>
                <m3e-button variant="text" size="small" @click="nextStep">下一步</m3e-button>
                <m3e-button variant="text" size="small" @click="skipAction">跳过这个动作</m3e-button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </m3e-card>

    <m3e-card v-if="feedbackOpen" variant="elevated" class="surface-card">
      <div class="surface-body">
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
      </div>
      <LoadingOverlay v-if="submitting" label="正在提交反馈…" />
    </m3e-card>
  </div>
</template>

<style scoped>
.activity-panel {
  display: grid;
  gap: 1rem;
  width: min(48rem, 100%);
  margin: 0 auto;
  padding-bottom: 1.5rem;
  justify-items: stretch;
}

.activity-panel m3e-card {
  display: block;
  width: 100%;
}

.surface-body {
  display: grid;
  gap: 0.75rem;
}

.step-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
}

.step-count {
  color: var(--md-sys-color-outline);
  font-size: 0.72rem;
  white-space: nowrap;
}

.card-head h3 {
  margin: 0;
  font-size: 1rem;
  color: var(--md-sys-color-on-surface-variant);
}

.media-row {
  display: grid;
  grid-template-columns: 16rem minmax(0, 1fr);
  gap: 1.25rem;
  align-items: start;
}

.media-row.no-camera {
  grid-template-columns: minmax(0, 1fr);
}

.stage {
  display: grid;
  gap: 0.75rem;
}

.step-text {
  margin: 0;
  font-size: clamp(1.4rem, 2.6vw, 1.9rem);
  font-weight: 600;
  line-height: 1.5;
  letter-spacing: 0.01em;
}

.caution {
  margin: 0;
  color: var(--md-sys-color-error);
  font-size: 0.78rem;
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
  font-size: 1.45rem;
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
  flex-wrap: wrap;
  align-items: center;
  gap: 0.4rem;
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
  margin: 0;
  color: var(--md-sys-color-error);
  font-size: 0.8rem;
}

.feedback-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

@media (max-width: 720px) {
  .media-row {
    grid-template-columns: 1fr;
  }
}
</style>
