<script setup>
import { ref } from "vue";
import { dismissSafety, state } from "../state/session.js";

const dialog = ref(null);

function closeDialog() {
  dialog.value?.hide();
}

function onClosed() {
  if (state.safety) dismissSafety();
}
</script>

<template>
  <m3e-dialog
    ref="dialog"
    class="safety"
    alert
    dismissible
    :open.prop="!!state.safety"
    @closed="onClosed"
  >
    <h2 slot="header">已停止动作推荐</h2>

    <template v-if="state.safety">
      <m3e-callout variant="error" class="detected">
        <span class="material-symbols-rounded" slot="icon">emergency</span>
        <span slot="label">检测到 {{ state.safety.red_flag_labels?.join("、") }}</span>
      </m3e-callout>
      <p class="body">
        这些表现已经超出居家练习的范围。继续做动作，可能让症状加重。请尽快去骨科或康复医学科就诊。就诊前避免负重、长时间低头和剧烈活动。
      </p>
      <p class="disclaimer">{{ state.safety.disclaimer }}</p>
    </template>

    <div slot="actions" end class="dialog-actions">
      <m3e-button variant="filled" size="medium" @click="closeDialog">我了解了</m3e-button>
    </div>
  </m3e-dialog>
</template>

<style scoped>
.safety {
  --m3e-dialog-max-width: 28.75rem;
}

.detected {
  display: block;
  margin: 0.25rem 0 0;
  font-size: 0.813rem;
}

.dialog-actions {
  display: flex;
  gap: 0.5rem;
  justify-content: flex-end;
}

.body {
  margin: 0.875rem 0;
  color: var(--md-sys-color-on-surface-variant);
  line-height: 1.7;
}

.disclaimer {
  margin-bottom: 0.375rem;
  padding-top: 0.875rem;
  border-top: 0.2rem solid var(--md-sys-color-outline-variant);
}
</style>
