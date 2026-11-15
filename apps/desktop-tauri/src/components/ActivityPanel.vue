<script setup>
import { computed, onBeforeUnmount, ref, watch } from "vue";
import ActionCamera from "./ActionCamera.vue";
import ErrorBanner from "./ErrorBanner.vue";
import LoadingOverlay from "./LoadingOverlay.vue";
import { selectPendingAction, state, submitFeedback } from "../state/session.js";

const actions = computed(() => {
  if (state.pendingActions?.length) return state.pendingActions;
  return state.pending ? [state.pending] : [];
});
const index = ref(0);
const action = computed(() => actions.value[index.value] ?? null);
// 推荐动作在这一次干预里保持稳定，切换 tab 不会把「推荐」搬走
const recommendedId = ref(state.pending?.id ?? null);
const isRecommended = computed(() => action.value?.id === recommendedId.value);

// 预留给动作参考图：{ box, label, image }
const referenceGuide = ref(null);

const remaining = ref(0);
const running = ref(false);
const finished = ref(false);
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
  openFeedback();
}

function openFeedback() {
  stopTick();
  disarmAutoStart();
  feedbackOpen.value = true;
}

function skipAction() {
  finished.value = true;
  openFeedback();
}

function indexOfRecommended() {
  const position = actions.value.findIndex((item) => item.id === recommendedId.value);
  return position >= 0 ? position : 0;
}

function resetSequence() {
  stopTick();
  if (advanceTimer) clearTimeout(advanceTimer);
  advanceTimer = null;
  index.value = indexOfRecommended();
  remaining.value = totalSeconds.value;
  finished.value = false;
  feedbackOpen.value = false;
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
  () => state.pendingActions,
  () => {
    if (!state.pending?.id) return;
    recommendedId.value = state.pending.id;
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
  if (advanceTimer) clearTimeout(advanceTimer);
});
</script>
<template>
  <div class="activity-panel">
    <m3e-card v-if="action && !feedbackOpen" variant="elevated" class="surface-card">
      <div class="surface-body plan-body-wrap">
        <header class="card-head">
          <h2>
            {{ action.name }}
            <span v-if="isRecommended" class="tag">推荐</span>
          </h2>
          <span class="step-count">第 {{ index + 1 }} / {{ actions.length }} 个动作</span>
        </header>

        <m3e-tabs v-if="actions.length > 1" class="plan-tabs">
          <m3e-tab v-for="item in actions" :key="item.id" :selected.prop="item.id === action?.id"
            @click="pickAction(item)">
            {{ item.name }}<span v-if="item.id === recommendedId" class="tag-inline">推荐</span>
          </m3e-tab>
        </m3e-tabs>

        <div class="plan-body">
          <ol class="steps">
            <li v-for="(step, stepIndex) in action.steps || []" :key="stepIndex">{{ step }}</li>
          </ol>
          <p v-if="action.caution" class="caution">{{ action.caution }}</p>
        </div>

        <div class="media-row">
          <ActionCamera :reference="referenceGuide" />

          <div class="timer">
            <div class="timer-head">
              <span class="mono time">{{ timeText }}</span>
              <span class="step-status">{{ running ? "进行中" : "已暂停" }}</span>
            </div>
            <m3e-linear-progress-indicator class="progress" :value.prop="progress"></m3e-linear-progress-indicator>
            <div class="timer-actions">
              <m3e-button v-if="!running" variant="tonal" size="small" @click="startTick">
                {{ remaining === totalSeconds ? "开始倒计时" : "继续" }}
              </m3e-button>
              <m3e-button v-else variant="text" size="small" @click="stopTick">暂停</m3e-button>
              <m3e-button variant="text" size="small" @click="skipAction">跳过运动</m3e-button>
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
/* 与干预卡片同一套外观：m3e-card + surface-card / surface-body */
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

.card-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.75rem;
}

.card-head h2 {
  margin: 0;
  font-size: 1.4rem;
}

.card-head h3 {
  margin: 0;
  font-size: 1rem;
  color: var(--md-sys-color-on-surface-variant);
}

.step-count {
  color: var(--md-sys-color-outline);
  font-size: 0.72rem;
  white-space: nowrap;
}

.plan-tabs {
  margin-bottom: 0.25rem;
}

.plan-body {
  display: block;
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

.media-row {
  display: grid;
  grid-template-columns: 12rem minmax(0, 1fr);
  gap: 1rem;
  align-items: start;
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

.tag {
  margin-left: 0.5rem;
  padding: 0.1rem 0.45rem;
  border-radius: 62.438rem;
  background: var(--md-sys-color-tertiary-container);
  color: var(--md-sys-color-on-tertiary-container);
  font-size: 0.65rem;
  font-weight: 500;
  vertical-align: middle;
}

.tag-inline {
  margin-left: 0.35rem;
  color: var(--md-sys-color-tertiary);
  font-size: 0.65rem;
}

@media (max-width: 720px) {
  .media-row {
    grid-template-columns: 1fr;
  }
}
</style>
