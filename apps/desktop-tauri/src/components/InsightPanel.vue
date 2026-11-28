<script setup>
import { computed, onMounted, watch } from "vue";
import ErrorBanner from "./ErrorBanner.vue";
import EvidenceCallout from "./EvidenceCallout.vue";
import AdviceLine from "./AdviceLine.vue";
import LoadingOverlay from "./LoadingOverlay.vue";
import MarkdownText from "./MarkdownText.vue";
import MedicalNote from "./MedicalNote.vue";
import { REVIEW_SOURCE } from "../data/actionSources.js";
import { aiEnabled, askQuestion, loadWeeklyReview, state } from "../state/session.js";

const trendLabel = computed(() => {
  const map = { improving: "下降", stable: "平稳", worsening: "上升", unknown: "数据不足" };
  return map[state.weekly?.pain?.trend] || "—";
});

const completionRate = computed(() =>
  Math.round(state.weekly?.interventions?.completion_rate ?? 0)
);

const hasNotes = computed(() =>
  Boolean(state.weekly?.highlights?.length || state.weekly?.suggestions?.length)
);

const loadingLabel = computed(() =>
  state.ai.busy ? "正在生成回答…" : "正在汇总最近 7 天…"
);

onMounted(() => {
  loadWeeklyReview();
});

watch(
  () => state.lastFeedback,
  (feedback) => {
    if (feedback) loadWeeklyReview();
  }
);
</script>

<template>
  <m3e-card variant="elevated" class="insight-card">
    <div class="surface-body">
      <header class="page-head">
        <h2>近 7 天</h2>
        <p class="lead">完成率、疼痛趋势和安全中断的变化。</p>

        <AdviceLine surface="weekly" :fallback="state.weekly?.suggestions?.[0] ?? ''"
          :context="{ completion_rate: state.weekly?.interventions?.completion_rate, trend: state.weekly?.pain?.trend, safety_events: state.weekly?.safety_events }" />
      </header>

      <m3e-list variant="segmented">
        <m3e-list-item>
          <div class="stats" v-if="state.weekly">
            <div>
              <small>完成率</small>
              <b class="mono">{{ completionRate }}%</b>
            </div>
            <div>
              <small>活动次数</small>
              <b class="mono">{{ state.weekly.interventions.total }}</b>
            </div>
            <div>
              <small>疼痛趋势</small>
              <b>{{ trendLabel }}</b>
            </div>
            <div>
              <small>安全中断</small>
              <b class="mono">{{ state.weekly.safety_events }}</b>
            </div>
          </div>
          <ErrorBanner v-else-if="state.weeklyError" :error="state.weeklyError" />
          <p class="placeholder" v-else-if="state.weeklyBusy">正在汇总…</p>
          <p class="placeholder" v-else>近 7 天暂无记录</p>
        </m3e-list-item>

        <m3e-list-item>
          <span class="material-symbols-rounded" slot="leading">lightbulb</span>
          <p class="placeholder" v-if="state.weeklyBusy">完成一次活动后，此处将显示建议。</p>
          <ul class="notes" v-else-if="hasNotes">
            <li v-for="item in state.weekly.highlights" :key="`h-${item}`">{{ item }}</li>
            <li v-for="item in state.weekly.suggestions" :key="`s-${item}`" class="muted">{{ item }}</li>
          </ul>
        </m3e-list-item>
      </m3e-list>

      <EvidenceCallout v-if="hasNotes" v-bind="REVIEW_SOURCE" />

      <header class="title-head">
        <h2>问答</h2>
      </header>

      <section v-if="aiEnabled" class="qa">
        <div class="qa-input">
          <input id="ai-question" v-model="state.ai.question" type="text" placeholder="输入你的问题..."
            @keyup.enter="askQuestion" />
          <m3e-icon-button variant="filled" :disabled.prop="state.ai.busy || !state.ai.question.trim()"
            @click="askQuestion">
            <span class="material-symbols-rounded-fill">send</span>
          </m3e-icon-button>
        </div>

        <ErrorBanner :error="state.errors.qa" />

        <div class="qa-body"v-if="!state.ai.busy">
          <MarkdownText v-if="state.ai.answer" :text="state.ai.answer" />

          <details v-if="state.ai.citations.length" class="qa-refs">
            <summary>参考 {{ state.ai.citations.length }} 条文献</summary>
            <ul>
              <li v-for="item in state.ai.citations" :key="item">{{ item }}</li>
            </ul>
          </details>
          <p class="qa-disclaimer" v-if="state.ai.disclaimer">{{ state.ai.disclaimer }}</p>
        </div>

        <m3e-loading-indicator v-if="state.ai.busy" style="margin-top: 0.5rem;align-self: center;width: 100%;height: 10vh;"></m3e-loading-indicator>
      </section>

      <MedicalNote />
    </div>
  </m3e-card>
</template>

<style scoped>
.insight-card {
  position: relative;
}

.qa {
  margin-top: 0.5rem;
}

.qa-title {
  margin: 0 0 0.5rem;
  font-size: 1rem;
}

.qa-input {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.qa-input input {
  flex: 1 1 auto;
  min-width: 0;
  padding: 0.6rem 0.75rem;
  border: 0.0625rem solid var(--md-sys-color-outline-variant);
  border-radius: 999rem;
  background: var(--md-sys-color-surface-container-lowest);
  color: var(--md-sys-color-on-surface);
  font: inherit;
  font-size: 0.875rem;

  transition: border-color 0.2s ease-in-out, box-shadow 0.2s ease-in-out;
}

.qa-input input::placeholder {
  color: var(--md-sys-color-outline);
}

.qa-input input:focus {
  outline: none;
  border: 0.14rem solid var(--md-sys-color-secondary);
}

.qa-body {
  position: relative;
  margin-top: 0.75rem;
}

.qa-refs {
  margin-top: 0.5rem;
  margin-left: 0.5rem;
  color: var(--md-sys-color-tertiary);
  font-size: 0.688rem;
}

.qa-refs summary {
  cursor: pointer;
}

.qa-refs ul {
  margin: 0.25rem 0 0;
  padding-left: 1.1rem;
  line-height: 1.6;
}

.qa-disclaimer {
  margin-top: 0.375rem;
  color: var(--md-sys-color-tertiary);
  font-size: 0.688rem;
  line-height: 1.6;
}

.body {
  padding: 0.25rem 0 1.125rem;
}

.qa {
  margin-top: 1rem;
}

.ask {
  display: block;
  margin-top: 1rem;
}

.answer {
  margin-top: 0.875rem;
  padding: 0.75rem 0.875rem;
  border-radius: var(--radius-sm);
  background: var(--md-sys-color-secondary-container);
  color: var(--md-sys-color-on-secondary-container);
  font-size: 0.813rem;
  line-height: 1.75;
}

.cites {
  margin-top: 0.375rem;
  color: var(--md-sys-color-outline);
  font-size: 0.688rem;
}

.disclaimer {
  margin-top: 0.375rem;
  color: var(--md-sys-color-on-surface-variant);
  font-size: 0.688rem;
  line-height: 1.6;
}

.label {
  color: var(--md-sys-color-outline);
  font-size: 0.75rem;
}

.stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 0.625rem;
  margin-top: 0.875rem;
}

.stats small {
  display: block;
  margin-bottom: 0.2rem;
  color: var(--md-sys-color-outline);
  font-size: 0.688rem;
}

.stats b {
  font-size: 1rem;
  font-weight: 600;
}

.notes {
  margin: 0.875rem 0 0;
  padding-left: 1rem;
  color: var(--md-sys-color-on-surface-variant);
  font-size: 0.75rem;
  line-height: 1.8;
}

.notes .muted {
  color: var(--md-sys-color-outline);
}

.placeholder {
  margin-top: 0.75rem;
  color: var(--md-sys-color-outline);
  font-size: 0.75rem;
}

.title-head {
  margin-top: 1.6rem;
  padding-top: 1rem;
}
</style>
