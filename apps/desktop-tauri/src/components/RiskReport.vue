<script setup>
import { computed } from "vue";
import EvidenceCallout from "./EvidenceCallout.vue";
import { openPosture, state } from "../state/session.js";

const POSTURE_LABELS = {
  baseline: "基准姿态",
  forward_head: "头前伸",
  lateral_tilt: "明显侧倾",
  undetermined: "未能识别",
};

const RISK_LABELS = {
  low: "低风险",
  medium: "中风险",
  high: "高风险",
  very_high: "极高风险",
};

const PLAN_LABELS = {
  maintain: "维持",
  quick: "快速",
  standard: "标准",
  intense: "强化",
};

const report = computed(() => state.postureReport);
const risk = computed(() => state.postureRisk);
const events = computed(() => state.postureEvents ?? []);

const riskLabel = computed(() => RISK_LABELS[report.value?.risk_level] || "未评估");
const planLabel = computed(() => PLAN_LABELS[report.value?.recommended_plan] || "—");
const postureLabel = computed(() => {
  const base = POSTURE_LABELS[report.value?.posture_class] || "未评估";
  const confidence = report.value?.confidence;
  return confidence ? `${base} · ${Math.round(confidence * 100)}%` : base;
});

const citationText = computed(() => {
  const items = risk.value?.citations ?? [];
  if (!items.length) return "";
  return items
    .slice(0, 2)
    .map((item) => item.key_finding || item.title)
    .join("；");
});

function postureLabelFor(value) {
  return POSTURE_LABELS[value] || value || "未评估";
}

function riskLabelFor(value) {
  return RISK_LABELS[value] || value || "—";
}

function formatTime(value) {
  try {
    return new Date(value).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  } catch {
    return "—";
  }
}
</script>

<template>
  <section class="risk-report">
    <header class="page-head">
      <h2>风险与姿势报告</h2>
      <p class="lead">
        摄像头默认只在本地提取关键点并分析记录，不会主动打扰你。<br>
        点击下方按钮即可马上检查姿势。
      </p>
    </header>

    <div v-if="report" class="status">
      <div>
        <small>风险等级</small>
        <strong class="level" :class="report.risk_level">{{ riskLabel }}</strong>
      </div>
      <div>
        <small>负荷指数</small>
        <strong class="mono">{{ report.brli.toFixed(2) }}</strong>
      </div>
      <div>
        <small>最近姿势</small>
        <strong>{{ postureLabel }}</strong>
      </div>
      <div>
        <small>建议方案</small>
        <strong>{{ planLabel }}</strong>
      </div>
    </div>

    <div v-if="events.length" class="events">
      <small>最近风险姿势</small>
      <ul>
        <li v-for="event in events.slice(0, 3)" :key="event.at">
          {{ formatTime(event.at) }} · {{ postureLabelFor(event.posture_class) }} · {{ riskLabelFor(event.risk_level) }}
        </li>
      </ul>
    </div>

    <m3e-button variant="filled" size="small" @click="openPosture">
      <span class="material-symbols-rounded" slot="icon">videocam</span>
      检查我的姿势
    </m3e-button>

    <EvidenceCallout
      v-if="risk?.citations?.length"
      title="权威依据"
      :source="citationText"
      :url="risk.citations[0].url"
      :evidence-id="risk.citations[0].evidence_id"
    />
  </section>
</template>

<style scoped>
.risk-report {
  margin-top: 2rem;
}

.status {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 0.625rem;
  margin: 0.25rem 0 0.875rem;
}

.status div {
  padding: 0.625rem 0.75rem;
  border-radius: var(--radius-sm);
  background: var(--md-sys-color-surface);
}

.status small {
  display: block;
  margin-bottom: 0.25rem;
  color: var(--md-sys-color-outline);
  font-size: 0.688rem;
}

.status strong {
  font-size: 0.875rem;
}

.level.low {
  color: var(--md-sys-color-tertiary);
}

.level.medium {
  color: #b26a00;
}

.level.high,
.level.very_high {
  color: var(--md-sys-color-error);
}

.events {
  margin: 0 0 0.875rem;
  color: var(--md-sys-color-on-surface-variant);
  font-size: 0.75rem;
}

.events small {
  color: var(--md-sys-color-outline);
}

.events ul {
  margin: 0.375rem 0 0;
  padding-left: 1rem;
  line-height: 1.8;
}

.placeholder {
  margin: 0.25rem 0 0.875rem;
  color: var(--md-sys-color-outline);
  font-size: 0.75rem;
}

@media (max-width: 4rem) {
  .status {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
