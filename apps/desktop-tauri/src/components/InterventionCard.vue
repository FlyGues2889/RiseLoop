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
  { value: "same", label: "无变化" },
  { value: "worse", label: "更不舒服" },
];

const obstacleOptions = [
  { value: "busy", label: "太忙" },
  { value: "too_hard", label: "动作太难" },
  { value: "no_space", label: "没地方做" },
  { value: "forgot", label: "忘了" },
];

const transitionMeta = {
  upgrade: { label: "升级", tone: "up" },
  rollback: { label: "回退一级", tone: "back" },
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
      <ErrorBanner :error="state.error" />

      <article v-if="result">
        <header class="page-head">
          <h2>本次结果</h2>
          <p class="lead">按最近几次的完成情况调整了阶段，下面是接下来的动作。</p>
        </header>

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
            {{ result.next_action.name }}
            <m3e-chip v-if="result.next_action.desk_friendly" class="desk-tag" variant="elevated">工位可做</m3e-chip>
            <span slot="trailing">{{ result.next_action.duration_minutes }} 分钟</span>
          </m3e-list-item>
          <m3e-list-item>
            <div class="facts item-left-margin">
              <div>
                <small>阶段目标</small>
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
        <header class="page-head">
          <h2>久坐计时</h2>
          <p class="lead">连续久坐达到提醒间隔后，将按当前阶段推荐一个最短有效动作；起身后计时重新开始。</p>
        </header>

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
.primary-action {
  margin-top: 1.125rem;
}

.desk-tag {
  margin-left: 0.4rem;
  vertical-align: middle;
  --m3e-chip-container-height: 1.25rem;
  --m3e-chip-label-text-font-size: 0.625rem;
  --m3e-elevated-chip-container-color: var(--md-sys-color-secondary-container);
  --m3e-elevated-chip-elevation: 0;
  --m3e-elevated-chip-hover-elevation: 0;
  --m3e-chip-label-text-color: var(--md-sys-color-on-secondary-container);
}

.result-head {
  margin-bottom: 1.25rem;
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

.timer-slot {
  margin: 0 0 0.25rem;
}
</style>

