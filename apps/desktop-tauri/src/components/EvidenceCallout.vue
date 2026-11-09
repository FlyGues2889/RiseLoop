<script setup>
defineProps({
  title: { type: String, default: "权威依据" },
  source: { type: String, required: true },
  url: { type: String, default: "" },
  evidenceId: { type: String, default: "" },
});
</script>

<template>
  <m3e-callout class="evidence" variant="surface">
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
