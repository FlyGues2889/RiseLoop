<script setup>
import { computed } from "vue";

const props = defineProps({
  error: { type: [Object, String], default: null },
});

const view = computed(() => {
  const error = props.error;
  if (!error) return null;
  if (typeof error === "string") {
    return { title: "操作失败", message: error, detail: null, hint: null };
  }
  return {
    title: error.title || "操作失败",
    message: error.message || "",
    detail: error.detail || null,
    hint: error.hint || null,
  };
});
</script>

<template>
  <m3e-callout v-if="view" variant="error" class="error" role="alert">
    <span class="material-symbols-rounded" slot="icon">error</span>
    <strong slot="label">{{ view.title }}</strong>
    <p v-if="view.message">{{ view.hint }}</p>
    <p class="message" v-if="view.hint">{{ view.message }}</p>
    <p class="detail mono" v-if="view.detail">{{ view.detail }}</p>
  </m3e-callout>
</template>

<style scoped>
.error {
  display: block;
  margin: 12px 0 14px;
}

.message {
  font-size: small;
  margin-top: 3px;
  color: var(--md-sys-color-on-surface-variant);
  line-height: 0.8rem;
}

.detail {
  margin-top: 3px;
  color: var(--md-sys-color-outline);
  font-size: 11px;
  word-break: break-all;
}
</style>
