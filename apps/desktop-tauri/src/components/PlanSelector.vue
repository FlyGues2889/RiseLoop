<script setup>
import { computed } from "vue";
import EvidenceCallout from "./EvidenceCallout.vue";
import { PLAN_SELECTOR_SOURCE, PLAN_SOURCE } from "../data/actionSources.js";
import { PLAN_OPTIONS } from "../config/plans.js";
import { selectPlan, state } from "../state/session.js";

const plan = computed(() => state.assessment?.plan ?? null);
const currentPlan = computed(
  () => PLAN_OPTIONS.find((item) => item.id === state.planPreference) ?? PLAN_OPTIONS[1]
);

function choose(planId) {
  if (planId) selectPlan(planId);
}
</script>

<template>
  <m3e-card variant="elevated" class="surface-card plan-card">
    <div class="surface-body">
      <header class="page-head">
        <h2>方案与节奏</h2>
        <p class="lead">
          按今天的可用时间选节奏。动作仍按状态和安全规则匹配，这里只调整推荐顺序。
        </p>
      </header>

      <m3e-selection-list variant="segmented" class="plans">
        <m3e-list-option
          v-for="item in PLAN_OPTIONS"
          :key="item.id"
          :value="item.id"
          :selected.prop="state.planPreference === item.id"
          @click="choose(item.id)"
        >
          <span class="material-symbols-rounded" slot="leading">{{ item.icon }}</span>
          {{ item.name }}
          <span slot="supporting-text">{{ item.description }}</span>
          <span slot="trailing" class="meta">{{ item.duration }}</span>
        </m3e-list-option>
      </m3e-selection-list>

      <p class="current">
        当前：<strong>{{ currentPlan.name }}</strong>
        <span v-if="state.pendingActions?.length"> · 从 {{ state.pendingActions.length }} 个动作里优选</span>
      </p>

      <section v-if="plan" class="two-week">
        <h3>两周方案</h3>
        <p>{{ plan.week1_goal }}</p>
        <p class="muted">{{ plan.week2_goal }}</p>
        <span class="mono plan-meta">提醒间隔 {{ plan.push_threshold_minutes }} 分钟</span>
        <EvidenceCallout v-bind="PLAN_SOURCE" />
      </section>

      <EvidenceCallout v-bind="PLAN_SELECTOR_SOURCE" />
    </div>
  </m3e-card>
</template>

<style scoped>
.plan-card {
  margin-top: 1rem;
}

.plans {
  display: block;
  margin-top: 0.4rem;
}

.meta {
  color: var(--md-sys-color-outline);
  font-size: 0.7rem;
  white-space: nowrap;
}

.current {
  margin: 0.6rem 0 0;
  color: var(--md-sys-color-on-surface-variant);
  font-size: 0.75rem;
}

.current strong {
  color: var(--md-sys-color-primary);
}

.two-week {
  margin-top: 1.2rem;
  padding-top: 1rem;
  border-top: 0.2rem solid var(--md-sys-color-outline-variant);
}

.two-week h3 {
  margin: 0 0 0.4rem;
  font-size: 0.95rem;
}

.two-week p {
  margin: 0 0 0.3rem;
  font-size: 0.8rem;
  line-height: 1.6;
}

.two-week .muted {
  color: var(--md-sys-color-on-surface-variant);
}

.plan-meta {
  display: inline-block;
  margin-top: 0.2rem;
  color: var(--md-sys-color-outline);
  font-size: 0.7rem;
}
</style>
