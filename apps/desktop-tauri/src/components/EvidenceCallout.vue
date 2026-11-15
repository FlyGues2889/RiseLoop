<script setup>
defineProps({
  title: { type: String, default: "权威依据" },
  source: { type: String, required: true },
  url: { type: String, default: "" },
  evidenceId: { type: String, default: "" },
  dense: { type: Boolean, default: false },
});
</script>

<template>
  <m3e-callout class="evidence" :class="{ dense }" variant="surface">
    <span slot="label">{{ title }}</span>
    <p>{{ source }}</p>
    <p v-if="evidenceId || url" class="meta">
      <span v-if="evidenceId">{{ evidenceId }}</span>
      <a v-if="url" :href="url" target="_blank" rel="noreferrer">查看来源</a>
    </p>
  </m3e-callout>
</template>

<style scoped>
.evidence {
  margin-top: 1rem;
  /* 依据是参考信息，不属于当下操作：标签与图标走 tertiary，正文保持中性 */
  --m3e-callout-icon-color: var(--md-sys-color-tertiary);
  --m3e-callout-label-text-color: var(--md-sys-color-tertiary);
}

/* 放进已有 gap 的纵向布局时，不要再叠外边距 */
.evidence.dense {
  margin-top: 0;
}

.evidence p {
  margin: 0;
  line-height: 1.7;
  font-size: 0.75rem;
}

.meta {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-top: 0.375rem !important;
  color: var(--md-sys-color-outline);
  font-size: 0.688rem !important;
}

.meta a {
  color: var(--md-sys-color-outline);
}
</style>
