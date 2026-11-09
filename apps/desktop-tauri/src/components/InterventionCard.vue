<script setup>
import { computed, ref } from "vue";
import ErrorBanner from "./ErrorBanner.vue";
import EvidenceCallout from "./EvidenceCallout.vue";
import LoadingOverlay from "./LoadingOverlay.vue";
import RiskReport from "./RiskReport.vue";
import TimeToolbar from "./TimeToolbar.vue";
import { sourceForAction } from "../data/actionSources.js";
import {
  continueAfterFeedback,
  selectPendingAction,
  state,
  submitFeedback,
} from "../state/session.js";

const completion = ref("completed");
const feeling = ref("same");
const painScore = ref(2);
const obstacle = ref(null);
const note = ref("");

const completionOptions = [
  { value: "completed", label: "完成" },
  { value: "partial", label: "部分完成" },
  { value: "skipped", label: "跳过" },
];

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

const transitionMeta = {
  upgrade: { label: "进阶", tone: "up" },
  rollback: { label: "回退一档", tone: "back" },
  degrade: { label: "强度下调", tone: "down" },
  hold: { label: "保持", tone: "hold" },
  short_circuit: { label: "安全中断", tone: "stop" },
};

const actionChoices = computed(() => {
  if (state.pendingActions?.length) return state.pendingActions;
  return state.pending ? [state.pending] : [];
});

const actionSource = computed(() => sourceForAction(state.pending?.id));

const result = computed(() => {
  const feedback = state.lastFeedback;
  if (!feedback) return null;
  const meta = transitionMeta[feedback.transition_type] || {
    label: feedback.transition_type,
    tone: "hold",
  };
  return {
    ...feedback,
    label: meta.label,
    tone: meta.tone,
    intensityText: feedback.intensity === "gentle" ? "温和" : "常规",
  };
});

function onPainChange(event) {
  const target = event.target;
  const value = target.thumb ? target.thumb.value : target.value;
  if (value !== null && value !== undefined && value !== "") {
    painScore.value = Number(value);
  }
}

function submit() {
  submitFeedback({
    action_id: state.pending.id,
    completion: completion.value,
    feeling: feeling.value,
    pain_score: painScore.value,
    obstacle: completion.value === "skipped" ? obstacle.value : null,
    next_day_worse: false,
    red_flags: [],
    note: note.value,
  });
}

// 单选组：点击后强制保持选中，避免再点一次把唯一选项取消掉
function pickField(event, field, value) {
  field.value = value;
  const button = event?.currentTarget;
  if (button) button.selected = true;
}
</script>

<template>
  <m3e-card variant="elevated" class="surface-card">
    <div class="surface-body">
      <article v-if="result">
        <div class="result-head">
          <h1 class="transition mono">
            {{ result.from_state }}<i>
              <span class="material-symbols-rounded">arrow_forward</span>
            </i>{{ result.to_state }}
          </h1>
          <p class="reason">{{ result.reason }}</p>
        </div>

        <m3e-list variant="segmented">
          <m3e-list-item>
            <span class="material-symbols-rounded" slot="leading">timeline</span>
            <span slot="overline">接下来的建议运动</span>
            {{ result.next_action.name }}
            <span slot="trailing">{{ result.next_action.duration_minutes }} 分钟</span>
          </m3e-list-item>
          <m3e-list-item>
            <div class="facts item-left-margin">
              <div>
                <small>建议时长</small>
                <span class="mono">{{ result.duration_range }}</span>
              </div>
              <div>
                <small>强度</small>
                <span>{{ result.intensityText }}</span>
              </div>
            </div>
          </m3e-list-item>
        </m3e-list>

        <m3e-button class="primary-action" variant="filled" size="medium" @click="continueAfterFeedback">继续</m3e-button>
      </article>

      <article v-else class="idle">
        <h1>保持当前节奏</h1>
        <p class="lead">
          到点会提醒你起来活动，按计时安排休息就好。<br>
          窗口最小化或收进托盘，计时都不会中断。
        </p>

        <div class="timer-slot">
          <TimeToolbar />
        </div>

        <RiskReport />
      </article>
    </div>
    <LoadingOverlay v-if="state.busy" label="正在提交反馈…" />
  </m3e-card>
</template>

<style scoped>
.choices {
  margin-bottom: 0.5rem;
}

.choice-meta {
  margin: 0.2rem 0 1.125rem;
  color: var(--md-sys-color-outline);
  font-size: 0.75rem;
}

.head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 1rem;
}

.head h1 {
  margin: 0.375rem 0 0;
}

.duration {
  color: var(--md-sys-color-outline);
  font-size: 0.813rem;
  white-space: nowrap;
  padding-top: 0.25rem;
}

.steps {
  margin: 1.25rem 0;
  padding: 0;
  list-style: none;
  counter-reset: step;
  display: grid;
  gap: 0.625rem;
}

.steps li {
  counter-increment: step;
  display: flex;
  gap: 0.75rem;
  color: var(--md-sys-color-on-surface-variant);
  line-height: 1.7;
}

.steps li::before {
  content: counter(step);
  flex: 0 0 auto;
  width: 1.375rem;
  height: 1.375rem;
  margin-top: 0.2rem;
  border-radius: 50%;
  background: var(--md-sys-color-surface-1);
  border: 0.2rem solid var(--md-sys-color-outline-variant);
  color: var(--md-sys-color-outline);
  font-size: 0.688rem;
  display: grid;
  place-items: center;
}

.caution {
  margin: 0 0 0.25rem;
  padding: 0.563rem 0.75rem;
  border-left: 0.2rem solid var(--md-sys-color-tertiary);
  border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
  background: var(--md-sys-color-tertiary-container);
  color: var(--md-sys-color-on-tertiary-container);
  font-size: 0.813rem;
}

.separator {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin: 1.375rem 0 1rem;
  color: var(--md-sys-color-outline);
  font-size: 0.75rem;
}

.separator::before,
.separator::after {
  content: "";
  flex: 1;
  height: 0.2rem;
  background: var(--md-sys-color-outline-variant);
}

.field {
  display: block;
  margin-bottom: 1rem;
}

.field-label {
  display: block;
  margin-bottom: 0.5rem;
  font-size: 0.813rem;
  color: var(--md-sys-color-on-surface-variant);
}

.extra {
  display: block;
  margin: 0.25rem 0 1.125rem;
  border-top: 0.2rem solid var(--md-sys-color-outline-variant);
}

.extra-body {
  display: grid;
  gap: 1rem;
  padding: 0.25rem 0 1rem;
}

.slider {
  display: block;
}

.slider m3e-slider {
  display: block;
  width: 100%;
  margin-top: 0.75rem;
  --m3e-slider-min-width: 100%;
  --m3e-slider-tick-size: 0.2rem;
}

.note {
  display: block;
}

.primary-action {
  margin-top: 1.125rem;
}

.transition {
  margin: 0.75rem 0 0.5rem;
  font-size: 1.875rem;
  letter-spacing: 0.01em;
  color: var(--md-sys-color-primary);
}

.transition i {
  margin: 0 0.75rem;
  color: var(--md-sys-color-outline);
  font-style: normal;
  font-weight: 300;
}

.reason {
  color: var(--md-sys-color-on-surface-variant);
  line-height: 1.7;
}

.result-head {
  margin-bottom: 1.25rem;
}

.facts {
  display: flex;
  gap: 2.5rem;
}

.facts small {
  display: block;
  color: var(--md-sys-color-outline);
  font-size: 0.688rem;
  margin-bottom: 0.2rem;
}

.facts span {
  font-size: 0.875rem;
  font-weight: 500;
}

.next {
  display: flex;
  align-items: baseline;
  gap: 0.5rem;
  padding: 0.75rem 1rem;
  margin-bottom: 1.25rem;
  border: 0.2rem solid var(--md-sys-color-outline-variant);
  border-radius: var(--radius-sm);
}

.next small {
  color: var(--md-sys-color-outline);
  font-size: 0.688rem;
}

.next strong {
  font-size: 0.875rem;
}

.next span {
  margin-left: auto;
  color: var(--md-sys-color-outline);
  font-size: 0.75rem;
}

.idle h1 {
  margin: 0.375rem 0 0.625rem;
}

.timer-slot {
  margin: 1.25rem 0 0.25rem;
}

.actions {
  display: flex;
  align-items: center;
  gap: 0.625rem;
  margin-top: 1.375rem;
}
</style>
