<script setup>
import { state } from "../state/session.js";

function close() {
  state.logOpen = false;
}
</script>

<template>
  <m3e-dialog class="log-dialog" :open.prop="state.logOpen" @closed="close">
    <h2 slot="header">本次会话记录</h2>

    <m3e-content-pane>
      <div class="row list" v-if="state.log.length" v-for="(item, index) in state.log" :key="index">
        <span class="time mono">{{ item.at }}</span>
        <span class="text">{{ item.message }}</span>
      </div>
      <p v-else class="empty">还没有记录。操作之后，这里会留下时间线。</p>
    </m3e-content-pane>

    <div slot="actions" end class="dialog-actions">
      <m3e-button variant="outlined" @click="close">关闭</m3e-button>
    </div>
  </m3e-dialog>
</template>

<style scoped>
.log-dialog {
  --m3e-dialog-max-width: 32rem;
}

.list {
  display: block;
  overflow-y: auto;
}

.row {
  display: flex;
  gap: 1rem;
  align-items: baseline;
  font-size: 0.78rem;
  color: var(--md-sys-color-on-surface-variant);
}

.time {
  flex: 0 0 auto;
  color: var(--md-sys-color-outline);
  font-size: 0.68rem;
}

.text {
  min-width: 0;
  line-height: 1.6;
}

.empty {
  color: var(--md-sys-color-on-surface-variant);
  font-size: 0.8rem;
}

.dialog-actions {
  display: flex;
  gap: 0.5rem;
  justify-content: flex-end;
}
</style>
