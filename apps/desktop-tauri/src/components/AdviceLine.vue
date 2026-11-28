<script setup>
import { computed, onMounted, watch } from "vue";

import { advice, loadAdvice, state } from "../state/session.js";

const props = defineProps({
  surface: { type: String, required: true },
  fallback: { type: String, default: "" },
  context: { type: Object, default: () => ({}) },
});

// 模型没给出结果时沿用页面现有文案，不出现空位
const text = computed(() => advice[props.surface] || props.fallback);

function refresh() {
  loadAdvice(props.surface, props.fallback, props.context);
}

onMounted(refresh);
// 切大页面时重取一次，其余时间用缓存
watch(() => state.phase, refresh);
</script>

<template>
  <p v-if="text" class="advice">{{ text }}</p>
</template>

<style scoped>
.advice {
  margin: 0.5rem 0 0;
  color: var(--md-sys-color-on-surface-variant);
  font-size: 0.813rem;
  line-height: 1.7;
}
</style>
