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
    <h2 slot="header">已停止运动推荐</h2>

    <template v-if="state.safety">
      <m3e-callout variant="error" class="detected">
        <span class="material-symbols-rounded" slot="icon">emergency</span>
        <span slot="label">检测到 {{ state.safety.red_flag_labels?.join("、") }}</span>
      </m3e-callout>
      <p class="body">
        这些表现超出居家行为干预的范围，继续做动作可能加重症状。请尽快到骨科或康复医学科就诊，就诊前避免负重、长时间低头与剧烈活动。
      </p>
      <p class="disclaimer">{{ state.safety.disclaimer }}</p>
    </template>

    <m3e-button slot="actions" variant="filled" size="medium" @click="closeDialog">
      我知道了
    </m3e-button>
  </m3e-dialog>
</template>

<style scoped>
.safety {
  --m3e-dialog-max-width: 460px;
}

.detected {
  display: block;
  margin: 4px 0 0;
  font-size: 13px;
}

.body {
  margin: 14px 0;
  color: var(--md-sys-color-on-surface-variant);
  line-height: 1.7;
}

.disclaimer {
  margin-bottom: 6px;
  padding-top: 14px;
  border-top: 1px solid var(--md-sys-color-outline-variant);
}
</style>
