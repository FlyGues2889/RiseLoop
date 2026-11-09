<script setup>
import { computed, onMounted, watch } from "vue";
import ErrorBanner from "./ErrorBanner.vue";
import EvidenceCallout from "./EvidenceCallout.vue";
import LoadingOverlay from "./LoadingOverlay.vue";
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
        <h2>这 7 天的变化</h2>
        <p class="lead">汇总最近 7 天的记录，趋势一眼看清。</p>
        <p class="hint" v-if="!aiEnabled">本地模式下，智能问答不可用。</p>
      </header>

      <m3e-list variant="segmented">
        <m3e-list-item>
          <span class="material-symbols-rounded" slot="leading">timeline</span>
          追踪数据
          <span class="label" slot="trailing">最近 7 天</span>
        </m3e-list-item>

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
          <ul class="notes" v-if="hasNotes">
            <li v-for="item in state.weekly.highlights" :key="`h-${item}`">{{ item }}</li>
            <li v-for="item in state.weekly.suggestions" :key="`s-${item}`" class="muted">{{ item }}</li>
          </ul>
          <p class="placeholder" v-else-if="state.weeklyBusy">正在生成建议…</p>
          <p class="placeholder" v-else>做完一次活动后，这里会出现建议。</p>
        </m3e-list-item>
      </m3e-list>

      <EvidenceCallout v-if="hasNotes" v-bind="REVIEW_SOURCE" />

      <m3e-list variant="segmented" v-if="aiEnabled">
        <m3e-list-item>
          <span class="material-symbols-rounded" slot="leading">chat</span>
          智能问答
        </m3e-list-item>
        <m3e-list-item>
          <div class="body">
            <m3e-form-field variant="filled" class="ask">
              <label slot="label" for="ai-question">问一个问题</label>
              <input id="ai-question" v-model="state.ai.question" type="text"
                placeholder="例如：开会时颈肩紧张，怎么快速缓解？" @keyup.enter="askQuestion" />
              <m3e-button slot="suffix" variant="text" size="small"
                :disabled.prop="state.ai.busy || !state.ai.question.trim()" @click="askQuestion">
                {{ state.ai.busy ? "回答中…" : "提问" }}
              </m3e-button>
            </m3e-form-field>

            <div class="answer" v-if="state.ai.answer">
              <p>{{ state.ai.answer }}</p>
              <p class="cites" v-if="state.ai.citations.length">
                参考 {{ state.ai.citations.length }} 条文献
              </p>
            </div>
          </div>
        </m3e-list-item>
      </m3e-list>
    </div>
    <LoadingOverlay v-if="state.weeklyBusy || state.ai.busy" :label="loadingLabel" />
  </m3e-card>
</template>

<style scoped>
.insight-card {
  position: relative;
}

.body {
  padding: 0.25rem 0 1.125rem;
  border-top: 0.2rem solid var(--md-sys-color-outline-variant);
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
</style>
