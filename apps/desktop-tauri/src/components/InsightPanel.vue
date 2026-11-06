<script setup>
import { computed, onMounted, watch } from "vue";
import ErrorBanner from "./ErrorBanner.vue";
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
  <m3e-card variant="elevated">
    <div class="surface-body">
      <header class="page-head">
        <h2>你的努力</h2>
        <p class="lead">汇总最近 7 天的执行记录，帮你看清趋势。</p>
      </header>

      <p class="hint" v-if="!aiEnabled">本地模式不连接云端智能体，智能问答不可用。</p>

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
              <small>干预次数</small>
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
          <p class="placeholder" v-else>完成一次干预后这里会出现建议。</p>
        </m3e-list-item>
      </m3e-list>

      <m3e-list variant="segmented" v-if="aiEnabled">
        <m3e-list-item>
          <span class="material-symbols-rounded" slot="leading">chat</span>
          智能问答
        </m3e-list-item>
        <m3e-list-item>
          <div class="body">
            <m3e-form-field variant="filled" class="ask">
              <label slot="label" for="ai-question">向智能体提问</label>
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
                依据 {{ state.ai.citations.length }} 条知识库条目
              </p>
            </div>
          </div>
        </m3e-list-item>
      </m3e-list>
    </div>
  </m3e-card>
</template>

<style scoped>
.body {
  padding: 4px 0 18px;
  border-top: 1px solid var(--md-sys-color-outline-variant);
}

.ask {
  display: block;
  margin-top: 16px;
}

.answer {
  margin-top: 14px;
  padding: 12px 14px;
  border-radius: var(--radius-sm);
  background: var(--md-sys-color-secondary-container);
  color: var(--md-sys-color-on-secondary-container);
  font-size: 13px;
  line-height: 1.75;
}

.cites {
  margin-top: 6px;
  color: var(--md-sys-color-outline);
  font-size: 11px;
}

.label {
  color: var(--md-sys-color-outline);
  font-size: 12px;
}

.stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
  margin-top: 14px;
}

.stats small {
  display: block;
  margin-bottom: 2px;
  color: var(--md-sys-color-outline);
  font-size: 11px;
}

.stats b {
  font-size: 16px;
  font-weight: 600;
}

.notes {
  margin: 14px 0 0;
  padding-left: 16px;
  color: var(--md-sys-color-on-surface-variant);
  font-size: 12px;
  line-height: 1.8;
}

.notes .muted {
  color: var(--md-sys-color-outline);
}

.placeholder {
  margin-top: 12px;
  color: var(--md-sys-color-outline);
  font-size: 12px;
}
</style>
