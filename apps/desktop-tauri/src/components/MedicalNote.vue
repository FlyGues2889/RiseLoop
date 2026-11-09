<script setup>
defineProps({
  label: { type: String, default: "健康提示" },
});
</script>

<template>
  <m3e-callout class="medical-note" variant="surface">
    <span class="material-symbols-rounded" slot="icon">medical_information</span>
    <span slot="label">{{ label }}</span>
    <p>
      本产品为健康行为指导工具，不提供医疗诊断或治疗建议。
      如出现持续疼痛、放射痛、麻木加重、肢体无力或外伤后剧痛，请及时就医。
    </p>
  </m3e-callout>
</template>

<style scoped>
.medical-note {
  display: block;
  margin-top: 1.125rem;
  padding-top: 0.875rem;
}

.medical-note p {
  font-size: 0.75rem;
  line-height: 1.7;
  color: var(--md-sys-color-on-surface-variant);
}
</style>
