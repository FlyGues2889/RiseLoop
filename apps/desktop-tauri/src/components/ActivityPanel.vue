<script setup>
import { computed, onBeforeUnmount, ref, watch } from "vue";
import ActionCamera from "./ActionCamera.vue";
import ErrorBanner from "./ErrorBanner.vue";
import EvidenceCallout from "./EvidenceCallout.vue";
import LoadingOverlay from "./LoadingOverlay.vue";
import MedicalNote from "./MedicalNote.vue";
import { resolveFraming } from "../data/actionFraming.js";
import { actionImage } from "../data/actionImages.js";
import { sourceForAction } from "../data/actionSources.js";
import { DEFAULT_STEP_SECONDS, planStepSeconds } from "../data/stepTiming.js";
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

// S2 一轮串 2–3 条动作，合计落在 5–8 分钟；其余状态一条做完就记感受。
// 5 分钟是 intervention-engine DURATION_BY_STATE[S2] 的下限，改那边要同步这里。
const ROUND_STATE = "S2";
const ROUND_MIN_MINUTES = 5;
const ROUND_MAX_ACTIONS = 3;

const roundIds = ref([]);
const roundMinutes = ref(0);

const actionIndex = ref(0);
const action = computed(() => actions.value[actionIndex.value] ?? null);
const steps = computed(() => {
  const list = action.value?.steps ?? [];
  return list.length ? list : ["按动作要领完成这一步"];
});
const cameraOpen = ref(true);

const framing = computed(() => resolveFraming(action.value));
// 参考图跟着共享会话走，通知窗里切换步骤时这里也是同一个动作
const refImage = computed(() => actionImage(actionSession.id || action.value?.id || ""));
const refOpen = ref(false);
const actionSource = computed(() => sourceForAction(actionSession.id || action.value?.id || ""));

const feedbackOpen = ref(false);
const submitting = ref(false);
const error = ref("");

const feeling = ref("same");
const painScore = ref(state.assessment?.pain_score ?? 2);
const obstacle = ref(null);

const feelingOptions = [
  { value: "better", label: "好转" },
  { value: "same", label: "无变化" },
  { value: "worse", label: "更不舒服" },
];

const obstacleOptions = [
  { value: "busy", label: "太忙" },
  { value: "too_hard", label: "动作太难" },
  { value: "no_space", label: "没地方做" },
  { value: "forgot", label: "忘了" },
];

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
const stepLabel = computed(() => {
  const step = `第 ${stepIndex.value + 1} / ${steps.value.length} 步`;
  if (state.currentState !== ROUND_STATE || roundIds.value.length === 0) return step;
  return `本轮第 ${roundIds.value.length + 1} 条 · ${step}`;
});
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
    action.value.id,
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

// S2 一轮要把 2–3 条动作走完再记感受；其余状态一条做完就进反馈
watch(
  () => actionSession.done,
  (done) => {
    if (!done || feedbackOpen.value) return;
    if (continueRound()) return;
    openFeedback();
    finishAction();
  }
);

// 返回 true 表示这一轮还没做完，已经换到下一条动作
function continueRound() {
  if (state.currentState !== ROUND_STATE) return false;
  const current = action.value;
  if (!current || roundIds.value.includes(current.id)) return false;
  roundIds.value = [...roundIds.value, current.id];
  roundMinutes.value += current.duration_minutes ?? 1;
  if (roundIds.value.length >= ROUND_MAX_ACTIONS) return false;
  if (roundMinutes.value >= ROUND_MIN_MINUTES) return false;
  const next = actions.value.findIndex((item) => !roundIds.value.includes(item.id));
  if (next < 0) return false;
  switchTo(next, true);
  return true;
}

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
  roundIds.value = [];
  roundMinutes.value = 0;
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
    error.value = "提交未成功，请重试。";
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
        <header class="page-head action-head">
          <h2>接下来的动作</h2>
          <p class="lead">跟着步骤做，倒计时结束自动进下一步；不舒服就结束，直接记感受。</p>
        </header>

        <div class="step-head">
          <m3e-form-field class="picker" variant="filled" style="--md-sys-density-scale: -3">
            <m3e-select id="action-pick" :value.prop="action.id" @change="pickAction">
              <m3e-option v-for="item in actions" :key="item.id" :value="item.id">
                {{ item.name }}{{ item.desk_friendly ? " · 工位可做" : "" }}{{ item.id === recommendedId ? "（推荐）" : "" }}
              </m3e-option>
            </m3e-select>
          </m3e-form-field>

          <div class="head-tools">
            <m3e-button variant="text" size="small" @click="cameraOpen = !cameraOpen">
              <span slot="icon" class="material-symbols-rounded">{{ cameraOpen ? "videocam_off" : "videocam" }}</span>
              {{ cameraOpen ? "收起画面" : "打开画面" }}
            </m3e-button>
            <m3e-button variant="filled" size="small" @click="endWorkout">
              <span slot="icon" class="material-symbols-rounded">stop_circle</span>
              结束运动
            </m3e-button>
          </div>
        </div>

        <div class="media-row">
          <div class="media-col">
            <button v-if="refImage" class="ref-slot" type="button"
              aria-label="放大参考图" @click="refOpen = true">
              <img class="ref-img" :src="refImage" alt="" loading="lazy" />
              <span class="ref-cap">参考图 · 点击放大</span>
            </button>

            <ActionCamera v-if="cameraOpen" :framing="framing" />
          </div>

          <div class="stage">
            <p class="step-text">{{ steps[stepIndex] }}</p>
            <div class="step-meta">
              <p class="step-progress">{{ stepLabel }}</p>
              <m3e-chip v-if="action.desk_friendly" class="desk-chip" variant="elevated">工位可做</m3e-chip>
            </div>

            <EvidenceCallout dense title="科学依据" :source="actionSource.source"
              :url="actionSource.url" :evidence-id="actionSource.evidenceId" />

            <div class="timer">
              <div class="timer-head">
                <span class="mono time">{{ timeText }}</span>
                <span class="step-status">{{ running ? "进行中" : "已暂停" }}</span>
              </div>
              <m3e-linear-progress-indicator class="progress" :value.prop="progress"></m3e-linear-progress-indicator>
              <div class="timer-actions">
                <m3e-button v-if="!running" variant="tonal" @click="startTick">
                  <span slot="icon" class="material-symbols-rounded">play_arrow</span>
                  {{ remaining === stepTotal ? "开始倒计时" : "继续" }}
                </m3e-button>
                <m3e-button v-else variant="tonal" @click="stopTick">
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

    <m3e-callout v-if="action.caution && !feedbackOpen" variant="surface" class="caution-callout">
      <span slot="icon" class="material-symbols-rounded">info</span>
      <span slot="label">提示</span>
      <small>{{ action.caution }}</small>
    </m3e-callout>

    <m3e-dialog :open.prop="refOpen" class="ref-dialog" @closed="refOpen = false">
      <h2 slot="header">{{ action?.name }}</h2>
      <div class="ref-body">
        <img v-if="refImage" :src="refImage" alt="" />
        <p class="ref-step">第 {{ stepIndex + 1 }} 步：{{ steps[stepIndex] }}</p>
      </div>
      <div slot="actions" end class="ref-actions">
        <m3e-button variant="outlined" @click="refOpen = false">关闭</m3e-button>
      </div>
    </m3e-dialog>

    <m3e-card v-if="feedbackOpen" variant="elevated" class="surface-card">
      <div class="surface-body">
        <header class="card-head">
          <h3>完成反馈</h3>
        </header>

        <div class="feedback-grid">
          <div class="field">
            <span class="field-label">完成后的感受</span>
            <m3e-button-group class="segments">
              <m3e-button v-for="option in feelingOptions" :key="option.value" toggle variant="outlined"
                :selected.prop="feeling === option.value" @click="pickField($event, feeling, option.value)">
                {{ option.label }}
              </m3e-button>
            </m3e-button-group>
          </div>

          <div class="field">
            <span class="field-label">跳过原因</span>
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
        <ErrorBanner :error="state.errors.feedback" />

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

.action-head {
  margin-bottom: 0;
}

.action-head h2 {
  font-size: 1.05rem;
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
  align-items: stretch;
}

.media-col {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  justify-items: start;
  gap: 0.75rem;
}

.ref-slot {
  display: grid;
  width: 100%;
  padding: 0;
  border: 0;
  border-radius: 0.9rem;
  overflow: hidden;
  background: var(--md-sys-color-surface);
  cursor: zoom-in;
}

.ref-img {
  display: block;
  width: 100%;
  aspect-ratio: 4 / 3;
  object-fit: cover;
}

.ref-cap {
  display: block;
  padding: 0.35rem 0.5rem;
  color: var(--md-sys-color-on-surface-variant);
  font-size: 0.7rem;
}

.ref-dialog {
  --m3e-dialog-max-width: 44rem;
}

.ref-body {
  display: grid;
  gap: 0.75rem;
}

.ref-body img {
  display: block;
  width: 100%;
  border-radius: 0.75rem;
}

.ref-step {
  margin: 0;
  color: var(--md-sys-color-on-surface-variant);
  font-size: 0.85rem;
}

.stage {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.step-text {
  margin: 0;
  font-size: clamp(1.4rem, 2.6vw, 1.9rem);
  font-weight: 600;
  line-height: 1.5;
  letter-spacing: 0.01em;
}

.step-meta {
  display: flex;
  align-items: center;
  gap: 0.5rem;

  margin-bottom:0.5rem;
}

.desk-chip {
  --m3e-chip-container-height: 1.375rem;
  --m3e-chip-label-text-font-size: 0.6875rem;
  /* 属性标签走 secondary 容器：是说明性信息，不该和主操作抢注意力 */
  --m3e-elevated-chip-container-color: var(--md-sys-color-secondary-container);
  --m3e-elevated-chip-elevation: 0;
  --m3e-elevated-chip-hover-elevation: 0;
  --m3e-chip-label-text-color: var(--md-sys-color-on-secondary-container);
}

.step-progress {
  margin: 0;
  color: var(--md-sys-color-on-surface-variant);
  font-size: 0.8125rem;
}

.timer {
  margin-top: auto;
  padding: 0.75rem 0.9rem;
  border-radius: 0.9rem;
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
  /* 和上面的评分滑杆留出距离，别贴着 */
  margin-top: 0.5rem;
  padding-top: 0.75rem;
  border-top: 0.0625rem solid var(--md-sys-color-outline-variant);
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
