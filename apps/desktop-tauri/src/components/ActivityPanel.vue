<script setup>
import { computed, onBeforeUnmount, ref, watch } from "vue";
import ActionCamera from "./ActionCamera.vue";
import ErrorBanner from "./ErrorBanner.vue";
import LoadingOverlay from "./LoadingOverlay.vue";
import { resolveFraming } from "../data/actionFraming.js";
import {
  actionSession,
  finishAction,
  loadAction,
  nextStep as advanceStep,
  pauseAction,
  playAction,
  prevStep as retreatStep,
} from "../state/actionSession.js";
import { state, submitFeedback } from "../state/session.js";

const actions = computed(() => {
  if (state.pendingActions?.length) return state.pendingActions;
  return state.pending ? [state.pending] : [];
});

// 推荐动作在这一次干预里保持稳定，手动切换也不会把「推荐」搬走
const recommendedId = ref(state.pending?.id ?? null);

const actionIndex = ref(0);
const action = computed(() => actions.value[actionIndex.value] ?? null);
const steps = computed(() => {
  const list = action.value?.steps ?? [];
  return list.length ? list : ["按动作要领完成这一步"];
});
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

// 步骤时长按文字里的「秒 / 次 / 组」推算：均分会让「弹力带固定于胸前高度」
// 这种准备动作也占上两分钟，实际做下来只要十几秒。
const REP_SECONDS = 3;
const DEFAULT_STEP_SECONDS = 20;
const MIN_STEP_SECONDS = 10;
const MAX_STEP_SECONDS = 75;

function parseStepSeconds(text) {
  const source = String(text || "");
  const secs = [...source.matchAll(/(\d+)\s*秒/g)].map((match) => Number(match[1]));
  const reps = [...source.matchAll(/(\d+)\s*次/g)].map((match) => Number(match[1]));
  const rounds = /重复\s*(\d+)\s*[轮次]/.exec(source);
  const groups = /共\s*(\d+)\s*组/.exec(source);
  const sides = /左右各|各侧|两侧/.test(source) ? 2 : 1;
  const sum = (list) => list.reduce((acc, item) => acc + item, 0);
  if (secs.length && reps.length) return sum(secs) * sum(reps);
  if (secs.length) return sum(secs) * sides * (rounds ? Number(rounds[1]) : 1);
  if (reps.length) {
    return sum(reps) * sides * (groups ? Number(groups[1]) : 1) * REP_SECONDS
      * (rounds && !groups ? Number(rounds[1]) : 1);
  }
  if (rounds) return DEFAULT_STEP_SECONDS * Number(rounds[1]);
  return null;
}

// 推算值只做参考：压进 [10, 75] 秒，超出动作总时长时整体等比缩，不放大
function planStepSeconds(list, total) {
  const guessed = list.map((text) => parseStepSeconds(text));
  const raw = guessed.map((value) => Math.min(MAX_STEP_SECONDS, Math.max(MIN_STEP_SECONDS, value ?? DEFAULT_STEP_SECONDS)));
  // 「换侧，各做 2 组」这类步骤本身没有数字，按上一步的时长乘以组数
  for (let index = 1; index < list.length; index += 1) {
    if (guessed[index] !== null || !/换(侧|边)|另一(侧|边)|各做/.test(String(list[index] || ""))) continue;
    const groups = /(\d+)\s*(组|轮|次)/.exec(String(list[index]));
    raw[index] = Math.min(MAX_STEP_SECONDS, raw[index - 1] * (groups ? Number(groups[1]) : 1));
  }
  const sum = raw.reduce((acc, item) => acc + item, 0);
  if (!total || sum <= total) return raw;
  const ratio = total / sum;
  return raw.map((value) => Math.max(MIN_STEP_SECONDS, Math.floor(value * ratio)));
}

const stepSeconds = computed(() =>
  planStepSeconds(steps.value, (action.value?.duration_minutes ?? 1) * 60)
);

// 倒计时与当前步骤由 Rust 侧的动作会话推进，这里只读快照；
// 通知窗读到的是同一份数据，所以两个窗口天然同步。
const stepIndex = computed(() => {
  const total = steps.value.length;
  if (!total) return 0;
  return Math.min(Math.max(0, actionSession.index), total - 1);
});
const stepTotal = computed(() =>
  actionSession.steps[stepIndex.value]?.seconds ?? stepSeconds.value[stepIndex.value] ?? DEFAULT_STEP_SECONDS
);
const remaining = computed(() => actionSession.remaining);
const running = computed(() => actionSession.running);

const progress = computed(() =>
  Math.max(0, Math.min(100, ((stepTotal.value - remaining.value) / stepTotal.value) * 100))
);
const timeText = computed(() => {
  const seconds = Math.max(0, remaining.value);
  const mm = String(Math.floor(seconds / 60)).padStart(2, "0");
  const ss = String(seconds % 60).padStart(2, "0");
  return mm + ":" + ss;
});

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
  pauseAction();
}

function startTick() {
  if (feedbackOpen.value) return;
  // 会话还没载入时（首次进动作页立刻动鼠标）等载入后再开，别把这次点击丢掉
  if (!actionSession.loaded) {
    syncSession().then(() => playAction());
    return;
  }
  playAction();
}

// 把当前动作交给共享会话：步骤文字与每步秒数都由这里算好，通知窗只负责显示
async function syncSession() {
  if (!action.value) return;
  await loadAction(
    action.value.name,
    steps.value.map((text, index) => ({
      text,
      seconds: stepSeconds.value[index] ?? DEFAULT_STEP_SECONDS,
    }))
  );
}

function nextStep() {
  disarmAutoStart();
  advanceStep();
}

function prevStep() {
  disarmAutoStart();
  retreatStep();
}

async function switchTo(index, wasRunning) {
  actionIndex.value = index;
  await syncSession();
  if (wasRunning) startTick();
}

// 结束这次运动：不再自动换下一个动作，直接进反馈记录
async function endWorkout() {
  if (!action.value) return;
  disarmAutoStart();
  pauseAction();
  feedbackOpen.value = true;
  await finishAction();
}

async function pickAction(event) {
  const value = event?.target?.value;
  const index = actions.value.findIndex((item) => item.id === value);
  if (index < 0 || index === actionIndex.value) return;
  disarmAutoStart();
  const wasRunning = running.value;
  pauseAction();
  await switchTo(index, wasRunning);
}

function openFeedback() {
  pauseAction();
  disarmAutoStart();
  feedbackOpen.value = true;
}

// 一组动作跑完：还有候选动作就接着做，否则进反馈并把主窗唤到前台
watch(
  () => actionSession.done,
  (done) => {
    if (!done || feedbackOpen.value) return;
    if (actionIndex.value < actions.value.length - 1) {
      switchTo(actionIndex.value + 1, true);
      return;
    }
    openFeedback();
    finishAction();
  }
);

function indexOfRecommended() {
  const position = actions.value.findIndex((item) => item.id === recommendedId.value);
  return position >= 0 ? position : 0;
}

async function resetSequence() {
  actionIndex.value = indexOfRecommended();
  feedbackOpen.value = false;
  error.value = "";
  feeling.value = "same";
  painScore.value = state.assessment?.pain_score ?? 2;
  obstacle.value = null;
  await syncSession();
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
});
</script>

<template>
  <div class="activity-panel">
    <m3e-card v-if="action && !feedbackOpen" variant="elevated" class="surface-card">
      <div class="surface-body">
        <div class="step-head">
          <m3e-form-field class="picker" variant="filled" style="--md-sys-density-scale: -3">
            <m3e-select id="action-pick" :value.prop="action.id" @change="pickAction">
              <m3e-option v-for="item in actions" :key="item.id" :value="item.id">
                {{ item.name }}{{ item.id === recommendedId ? "（推荐）" : "" }}
              </m3e-option>
            </m3e-select>
          </m3e-form-field>

          <div class="head-tools">
            <m3e-button variant="text" size="small" @click="endWorkout">
              <span slot="icon" class="material-symbols-rounded">stop_circle</span>
              结束运动
            </m3e-button>
            <m3e-button variant="text" size="small" @click="cameraOpen = !cameraOpen">
              <span slot="icon" class="material-symbols-rounded">{{ cameraOpen ? "videocam_off" : "videocam" }}</span>
              {{ cameraOpen ? "收起画面" : "打开画面" }}
            </m3e-button>
          </div>
        </div>

        <div class="media-row" :class="{ 'no-camera': !cameraOpen }">
          <ActionCamera v-if="cameraOpen" :framing="framing" />

          <div class="stage">
            <p class="step-text">{{ steps[stepIndex] }}</p>
            <p class="step-progress">第 {{ stepIndex + 1 }} / {{ steps.length }} 步</p>

            <div class="timer">
              <div class="timer-head">
                <span class="mono time">{{ timeText }}</span>
                <span class="step-status">{{ running ? "进行中" : "已暂停" }}</span>
              </div>
              <m3e-linear-progress-indicator class="progress" :value.prop="progress"></m3e-linear-progress-indicator>
              <div class="timer-actions">
                <m3e-button v-if="!running" variant="filled" size="medium" @click="startTick">
                  <span slot="icon" class="material-symbols-rounded">play_arrow</span>
                  {{ remaining === stepTotal ? "开始倒计时" : "继续" }}
                </m3e-button>
                <m3e-button v-else variant="filled" size="medium" @click="stopTick">
                  <span slot="icon" class="material-symbols-rounded">pause</span>
                  暂停
                </m3e-button>

                <div class="step-nav">
                  <m3e-button-group>
                    <m3e-icon-button id="step-prev" variant="outlined" aria-label="上一步" :disabled.prop="stepIndex === 0"
                      @click="prevStep">
                      <span class="material-symbols-rounded">arrow_back</span>
                    </m3e-icon-button>
                    <m3e-icon-button id="step-next" variant="outlined" aria-label="下一步" @click="nextStep">
                      <span class="material-symbols-rounded">arrow_forward</span>
                    </m3e-icon-button>
                  </m3e-button-group>
                  <m3e-tooltip for="step-prev">上一步</m3e-tooltip>
                  <m3e-tooltip for="step-next">{{ stepIndex === steps.length - 1 ? "完成这个动作" : "下一步" }}</m3e-tooltip>
                </div>
              </div>
            </div>
          </div>
        </div>

      </div>
    </m3e-card>

    <m3e-callout v-if="action && !feedbackOpen && action.caution" variant="error" class="caution-callout">
      <span slot="icon" class="material-symbols-rounded">health_and_safety</span>
      <span slot="label">健康提示</span>
      {{ action.caution }}
    </m3e-callout>

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
            <span slot="icon" class="material-symbols-rounded">check</span>
            完成
          </m3e-button>
          <m3e-button variant="outlined" size="medium" :disabled.prop="submitting" @click="submit('partial')">
            <span slot="icon" class="material-symbols-rounded">adjust</span>
            部分完成
          </m3e-button>
          <m3e-button variant="text" size="medium" :disabled.prop="submitting" @click="submit('skipped')">
            <span slot="icon" class="material-symbols-rounded">skip_next</span>
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
  align-items: flex-start;
  justify-content: space-between;
  gap: 0.75rem;
}

.picker {
  flex: 1 1 14rem;
  max-width: 18rem;
}

.head-tools {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  flex: none;
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
  gap: 0.55rem;
}

.step-text {
  margin: 0;
  font-size: clamp(1.4rem, 2.6vw, 1.9rem);
  font-weight: 600;
  line-height: 1.5;
  letter-spacing: 0.01em;
}

.step-progress {
  margin: 0;
  color: var(--md-sys-color-on-surface-variant);
  font-size: 0.8125rem;
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
  align-items: center;
  gap: 0.5rem;
}

/* 步进按钮贴着主按钮右侧，靠右对齐 */
.step-nav {
  display: flex;
  align-items: center;
  margin-left: auto;
}

.caution-callout {
  display: block;
  /* 主题里的 error-container 是纯红，整块铺满太刺眼，这里压成浅底 + 红字 */
  --m3e-error-container-callout-container-color: color-mix(in srgb, var(--md-sys-color-error) 10%, var(--md-sys-color-surface));
  --m3e-error-container-callout-label-text-color: var(--md-sys-color-error);
  --m3e-error-container-callout-content-color: var(--md-sys-color-on-surface);
  --m3e-error-container-callout-icon-color: var(--md-sys-color-error);
  --m3e-error-container-callout-leading-accent-color: var(--md-sys-color-error);
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

  .step-head {
    flex-direction: column;
  }

  .picker {
    max-width: none;
    width: 100%;
  }
}
</style>
