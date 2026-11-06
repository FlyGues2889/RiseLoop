<script setup>
import { computed, ref } from "vue";
import ErrorBanner from "./ErrorBanner.vue";
import {
  continueAfterFeedback,
  fastForward,
  refreshTimer,
  resetTimer,
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
  upgrade: { label: "升级", tone: "up" },
  rollback: { label: "回退", tone: "back" },
  degrade: { label: "降级", tone: "down" },
  hold: { label: "保持", tone: "hold" },
  short_circuit: { label: "安全中断", tone: "stop" },
};

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

async function demoFastForward() {
  await fastForward(state.timer.threshold_minutes);
  await refreshTimer();
}
</script>

<template>
  <m3e-card variant="elevated" class="surface-card">
    <div class="surface-body">
    <article v-if="result">
      <div class="result-head">
        <span class="tag" :class="`tag-${result.tone}`">{{ result.label }}</span>
        <h1 class="transition mono">
          {{ result.from_state }}<i>→</i>{{ result.to_state }}
        </h1>
        <p class="reason">{{ result.reason }}</p>
      </div>

      <div class="facts">
        <div>
          <small>建议时长</small>
          <span class="mono">{{ result.duration_range }}</span>
        </div>
        <div>
          <small>强度</small>
          <span>{{ result.intensityText }}</span>
        </div>
      </div>

      <div v-if="result.next_action" class="next">
        <small>下一次推荐</small>
        <strong>{{ result.next_action.name }}</strong>
        <span class="mono">{{ result.next_action.duration_minutes }} 分钟</span>
      </div>

      <m3e-button class="block" variant="filled" size="medium" @click="continueAfterFeedback">继续</m3e-button>
    </article>

    <article v-else-if="state.pending">
      <header class="head">
        <div>
          <span class="eyebrow">待执行动作</span>
          <h1>{{ state.pending.name }}</h1>
        </div>
        <span class="duration mono">{{ state.pending.duration_minutes }} 分钟</span>
      </header>

      <ol class="steps">
        <li v-for="(step, index) in state.pending.steps" :key="index">{{ step }}</li>
      </ol>

      <p class="caution" v-if="state.pending.caution">{{ state.pending.caution }}</p>

      <div class="separator"><span>完成后反馈</span></div>

      <div class="field">
        <span class="field-label">完成情况</span>
        <m3e-chip-set class="chips">
          <m3e-filter-chip
            v-for="option in completionOptions"
            :key="option.value"
            :value="option.value"
            :selected.prop="completion === option.value"
            @change="completion = option.value"
          >
            {{ option.label }}
          </m3e-filter-chip>
        </m3e-chip-set>
      </div>

      <div class="field">
        <span class="field-label">做完的感觉</span>
        <m3e-chip-set class="chips">
          <m3e-filter-chip
            v-for="option in feelingOptions"
            :key="option.value"
            :value="option.value"
            :selected.prop="feeling === option.value"
            @change="feeling = option.value"
          >
            {{ option.label }}
          </m3e-filter-chip>
        </m3e-chip-set>
      </div>

      <div class="field" v-if="completion === 'skipped'">
        <span class="field-label">主要阻碍</span>
        <m3e-chip-set class="chips">
          <m3e-filter-chip
            v-for="option in obstacleOptions"
            :key="option.value"
            :value="option.value"
            :selected.prop="obstacle === option.value"
            @change="obstacle = option.value"
          >
            {{ option.label }}
          </m3e-filter-chip>
        </m3e-chip-set>
      </div>

      <m3e-expansion-panel class="extra">
        <span slot="header">补充细节（可选）</span>
        <div class="extra-body">
          <div class="slider">
            <span class="field-label">疼痛评分：{{ painScore }} / 10</span>
            <m3e-slider
              size="medium"
              min="0"
              max="10"
              step="1"
              labelled
              discrete
              @input="onPainChange"
              @change="onPainChange"
            >
              <m3e-slider-thumb :value.prop="painScore"></m3e-slider-thumb>
            </m3e-slider>
          </div>
          <m3e-form-field variant="filled" class="note">
            <label slot="label" for="feedback-note">备注</label>
            <textarea id="feedback-note" v-model="note" rows="2" placeholder="例如：做完后肩颈更放松"></textarea>
          </m3e-form-field>
        </div>
      </m3e-expansion-panel>

      <ErrorBanner :error="state.error" />

      <m3e-button class="block" variant="filled" size="medium" :disabled.prop="state.busy" @click="submit">
        {{ state.busy ? "提交中…" : "提交反馈" }}
      </m3e-button>
    </article>

    <article v-else class="idle">
      <span class="eyebrow">等待触发</span>
      <h1>保持当前节奏</h1>
      <p class="lead">
        达到阈值后会自动推送动作。窗口最小化或关闭到托盘，计时都不会中断。
      </p>
      <div class="actions">
        <m3e-button variant="outlined" size="small" @click="resetTimer">重新计时</m3e-button>
        <m3e-button variant="text" size="small" @click="demoFastForward">演示：快进到阈值</m3e-button>
      </div>
    </article>
    </div>
  </m3e-card>
</template>

<style scoped>
.head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
}

.head h1 {
  margin: 6px 0 0;
}

.duration {
  color: var(--md-sys-color-outline);
  font-size: 13px;
  white-space: nowrap;
  padding-top: 4px;
}

.steps {
  margin: 20px 0;
  padding: 0;
  list-style: none;
  counter-reset: step;
  display: grid;
  gap: 10px;
}

.steps li {
  counter-increment: step;
  display: flex;
  gap: 12px;
  color: var(--md-sys-color-on-surface-variant);
  line-height: 1.7;
}

.steps li::before {
  content: counter(step);
  flex: 0 0 auto;
  width: 22px;
  height: 22px;
  margin-top: 2px;
  border-radius: 50%;
  background: var(--md-sys-color-surface-1);
  border: 1px solid var(--md-sys-color-outline-variant);
  color: var(--md-sys-color-outline);
  font-size: 11px;
  display: grid;
  place-items: center;
}

.caution {
  margin: 0 0 4px;
  padding: 9px 12px;
  border-left: 3px solid var(--md-sys-color-tertiary);
  border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
  background: var(--md-sys-color-tertiary-container);
  color: var(--md-sys-color-on-tertiary-container);
  font-size: 13px;
}

.separator {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 22px 0 16px;
  color: var(--md-sys-color-outline);
  font-size: 12px;
}

.separator::before,
.separator::after {
  content: "";
  flex: 1;
  height: 1px;
  background: var(--md-sys-color-outline-variant);
}

.field {
  display: block;
  margin-bottom: 1rem;
}

.field-label {
  display: block;
  margin-bottom: 8px;
  font-size: 13px;
  color: var(--md-sys-color-on-surface-variant);
}

.extra {
  display: block;
  margin: 4px 0 18px;
  border-top: 1px solid var(--md-sys-color-outline-variant);
}

.extra-body {
  display: grid;
  gap: 16px;
  padding: 4px 0 16px;
}

.slider {
  display: block;
}

.slider m3e-slider {
  display: block;
  width: 100%;
  margin-top: 12px;
  --m3e-slider-min-width: 100%;
  --m3e-slider-tick-size: 3px;
}

.note {
  display: block;
}

.block {
  width: 100%;
}

.transition {
  margin: 12px 0 8px;
  font-size: 30px;
  letter-spacing: 0.01em;
  color: var(--md-sys-color-primary);
}

.transition i {
  margin: 0 12px;
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
  gap: 40px;
  margin: 20px 0;
  padding: 14px 16px;
  border-radius: var(--radius-sm);
  background: var(--md-sys-color-surface-1);
}

.facts small {
  display: block;
  color: var(--md-sys-color-outline);
  font-size: 11px;
  margin-bottom: 2px;
}

.facts span {
  font-size: 14px;
  font-weight: 500;
}

.next {
  display: flex;
  align-items: baseline;
  gap: 8px;
  padding: 12px 16px;
  margin-bottom: 20px;
  border: 1px solid var(--md-sys-color-outline-variant);
  border-radius: var(--radius-sm);
}

.next small {
  color: var(--md-sys-color-outline);
  font-size: 11px;
}

.next strong {
  font-size: 14px;
}

.next span {
  margin-left: auto;
  color: var(--md-sys-color-outline);
  font-size: 12px;
}

.idle h1 {
  margin: 6px 0 10px;
}

.idle .lead {
  max-width: 420px;
}

.actions {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 22px;
}
</style>
