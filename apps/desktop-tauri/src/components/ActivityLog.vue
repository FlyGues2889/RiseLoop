<script setup>
import { state } from "../state/session.js";
</script>

<template>
  <aside class="log surface-card" v-if="state.log.length">
    <m3e-expansion-panel>
      <span slot="header" class="header">
        本次会话记录
        <span class="count">{{ state.log.length }}</span>
      </span>
      <m3e-list class="list">
        <m3e-list-item v-for="(item, index) in state.log" :key="index">
          <div class="row">
            <span class="time mono">{{ item.at }}</span>
            <span class="text">{{ item.message }}</span>
          </div>
        </m3e-list-item>
      </m3e-list>
    </m3e-expansion-panel>
  </aside>
</template>

<style scoped>
.log {
  margin-top: 18px;
}

.header {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--md-sys-color-on-surface-variant);
}

.count {
  padding: 1px 7px;
  border-radius: 999px;
  background: var(--md-sys-color-surface-2);
  color: var(--md-sys-color-on-surface-variant);
  font-size: 11px;
}

.list {
  display: block;
  max-height: 190px;
  overflow-y: auto;
}

.row {
  display: flex;
  gap: 12px;
  font-size: 12px;
  color: var(--md-sys-color-on-surface-variant);
  line-height: 1.6;
}

.time {
  flex: 0 0 auto;
  color: var(--md-sys-color-outline);
  font-size: 11px;
  padding-top: 1px;
}

.text {
  min-width: 0;
}
</style>
