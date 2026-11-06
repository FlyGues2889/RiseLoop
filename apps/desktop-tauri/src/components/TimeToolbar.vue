<script setup>
import { computed } from "vue";
import { setThreshold, state, toggleTimer } from "../state/session.js";

const thresholdOptions = [30, 40, 45, 50, 60];

function format(total) {
  const minutes = String(Math.floor(Math.max(0, total) / 60)).padStart(2, "0");
  const seconds = String(Math.max(0, total) % 60).padStart(2, "0");
  return `${minutes}:${seconds}`;
}

const timeText = computed(() => format(state.timer.sitting_seconds));
const remainingText = computed(() => format(state.timer.remaining_seconds));

const progress = computed(() => {
  const total = state.timer.threshold_seconds || 1;
  return Math.min(100, Math.round((state.timer.sitting_seconds / total) * 100));
});

const running = computed(() => state.timer.running);

function onThreshold(event) {
  setThreshold(Number(event.target.value));
}
</script>

<template>
  <m3e-toolbar shape="rounded" elevated class="time-bar" :class="{ paused: !running }">
    <div class="cluster">
      <span class="material-symbols-rounded lead-icon">{{ running ? "timer" : "pause_circle" }}</span>
      <span class="time mono">{{ timeText }}</span>
      <span class="caption">连续久坐</span>
    </div>

    <m3e-linear-progress-indicator class="track" :value.prop="progress" :max="100"></m3e-linear-progress-indicator>

    <span class="remaining">距提醒 <b class="mono">{{ remainingText }}</b></span>

    <m3e-icon-button class="action" variant="tonal" size="small" @click="toggleTimer" toggle>
      <span class="material-symbols-rounded-fill">{{ running ? "pause" : "play_arrow" }}</span>
    </m3e-icon-button>

    <m3e-select
      class="threshold"
      :value.prop="String(state.timer.threshold_minutes)"
      @change="onThreshold"
    >
      <m3e-option v-for="m in thresholdOptions" :key="m" :value="String(m)">
        {{ m }} 分钟提醒
      </m3e-option>
    </m3e-select>
  </m3e-toolbar>
</template>

<style scoped>
.time-bar {
  width: min(640px, calc(100vw - 40px));
  --m3e-toolbar-spacing: 12px;

  padding: 0 1rem
}

.time-bar > * {
  position: relative;
}

.cluster {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 0 0 auto;
  padding-left: 4px;
}

.lead-icon {
  font-size: 20px;
  color: var(--md-sys-color-primary);
}

.time {
  font-size: 22px;
  font-weight: 600;
  line-height: 1.1;
  letter-spacing: -0.01em;
  color: var(--md-sys-color-primary);
}

.paused .time {
  color: var(--md-sys-color-on-surface-variant);
}

.paused .lead-icon {
  color: var(--md-sys-color-on-surface-variant);
}

.caption {
  color: var(--md-sys-color-on-surface-variant);
  font-size: 12px;
  white-space: nowrap;
}

.track {
  flex: 1 1 auto;
  min-width: 80px;
  --m3e-progress-indicator-color: var(--md-sys-color-primary);
  --m3e-progress-indicator-track-color: var(--md-sys-color-surface-container-highest);
}

.remaining {
  flex: 0 0 auto;
  color: var(--md-sys-color-on-surface-variant);
  font-size: 12px;
  white-space: nowrap;
}

.remaining b {
  color: var(--md-sys-color-on-surface);
  font-weight: 600;
}

.action {
  flex: 0 0 auto;
}

.threshold {
  flex: 0 0 auto;
  display: inline-block;
  width: 132px;
}

@media (max-width: 720px) {
  .caption,
  .remaining {
    display: none;
  }
}
</style>