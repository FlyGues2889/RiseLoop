<script setup>
import { computed } from "vue";
import { aiEnabled, askQuestion, loadWeeklyReview, state } from "../state/session.js";

const trendLabel = computed(() => {
  const map = { improving: "下降", stable: "平稳", worsening: "上升", unknown: "数据不足" };
  return map[state.weekly?.pain?.trend] || "—";
});

const weekly = computed(() => state.weekly);
</script>

<template>
  <m3e-expansion-panel class="insight surface-card">
    <span slot="header" class="header">
      AI 问答与周复盘
      <span class="pending" v-if="!aiEnabled">演示模式不可用</span>
    </span>

    <div class="body">
      <m3e-form-field variant="filled" class="ask">
        <label slot="label" for="ai-question">向智能体提问</label>
        <input
          id="ai-question"
          v-model="state.ai.question"
          type="text"
          :disabled="!aiEnabled"
          placeholder="例如：开会时颈肩紧张，怎么快速缓解？"
          @keyup.enter="askQuestion"
        />
        <m3e-button
          slot="suffix"
          variant="text"
          size="small"
          :disabled.prop="!aiEnabled || state.ai.busy || !state.ai.question.trim()"
          @click="askQuestion"
        >
          {{ state.ai.busy ? "回答中…" : "提问" }}
        </m3e-button>
      </m3e-form-field>

      <p class="hint" v-if="!aiEnabled">
        演示模式不连接云端智能体，问答与周复盘不可用。
      </p>

      <div class="answer" v-if="state.ai.answer">
        <p>{{ state.ai.answer }}</p>
        <p class="cites" v-if="state.ai.citations.length">
          依据 {{ state.ai.citations.length }} 条知识库条目
        </p>
      </div>

      <div class="weekly">
        <div class="weekly-head">
          <span class="label">最近 7 天</span>
          <m3e-button
            variant="text"
            size="small"
            :disabled.prop="!aiEnabled || state.weeklyBusy"
            @click="loadWeeklyReview"
          >
            {{ state.weeklyBusy ? "汇总中…" : weekly ? "刷新" : "查看复盘" }}
          </m3e-button>
        </div>

        <div class="stats" v-if="weekly">
          <div>
            <small>完成率</small>
            <b class="mono">{{ weekly.interventions.completion_rate }}%</b>
          </div>
          <div>
            <small>干预次数</small>
            <b class="mono">{{ weekly.interventions.total }}</b>
          </div>
          <div>
            <small>疼痛趋势</small>
            <b>{{ trendLabel }}</b>
          </div>
          <div>
            <small>安全中断</small>
            <b class="mono">{{ weekly.safety_events }}</b>
          </div>
        </div>

        <ul class="notes" v-if="weekly?.highlights?.length || weekly?.suggestions?.length">
          <li v-for="item in weekly.highlights" :key="`h-${item}`">{{ item }}</li>
          <li v-for="item in weekly.suggestions" :key="`s-${item}`" class="muted">{{ item }}</li>
        </ul>
      </div>
    </div>
  </m3e-expansion-panel>
</template>

<style scoped>
.header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  font-weight: 500;
  color: var(--md-sys-color-on-surface-variant);
}

.pending {
  color: var(--md-sys-color-outline);
  font-size: 11px;
  font-weight: 400;
}

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

.weekly {
  margin-top: 18px;
  padding-top: 16px;
  border-top: 1px solid var(--md-sys-color-outline-variant);
}

.weekly-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
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
  color: var(--md-sys-color-outline);
  font-size: 11px;
  margin-bottom: 2px;
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
</style>
