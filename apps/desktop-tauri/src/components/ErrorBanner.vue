<script setup>
import { computed } from "vue";

const props = defineProps({
  error: { type: [Object, String], default: null },
});

const view = computed(() => {
  const error = props.error;
  if (!error) return null;
  if (typeof error === "string") {
    return { title: "这一步没完成", message: error, detail: null, hint: null };
  }
  return {
    title: error.title || "这一步没完成",
    message: error.message || "",
    detail: error.detail || null,
    hint: error.hint || null,
  };
});
</script>

<template>
  <div v-if="view" role="alert" class="error-wrap">
    <m3e-callout variant="error" class="error">
      <span class="material-symbols-rounded" slot="icon">error</span>
      <strong slot="label">{{ view.title }}</strong>
      <p v-if="view.hint" class="hint-text">{{ view.hint }}</p>
      <p v-if="view.message" class="message">{{ view.message }}</p>
      <p class="detail mono" v-if="view.detail">{{ view.detail }}</p>
    </m3e-callout>
  </div>
</template>

<style scoped>
.error {
  display: block;
  margin: 0.75rem 0 0.875rem;
}

.hint-text {
  margin-top: 0.2rem;
  font-size: 0.9rem;
  line-height: 1.55;
}

.message {
  margin-top: 0.3rem;
  font-size: 0.75rem;
  color: var(--md-sys-color-on-surface-variant);
  line-height: 1.5;
}

.detail {
  margin-top: 0.2rem;
  color: var(--md-sys-color-outline);
  font-size: 0.68rem;
  word-break: break-all;
}
</style>
