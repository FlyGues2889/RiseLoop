<script setup>
import { computed } from "vue";
import { resetTimer, setThreshold, state, toggleTimer } from "../state/session.js";

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
const overdue = computed(() => state.timer.overdue);

const actionLabel = computed(() => {
  if (overdue.value) return "重新计时";
  return running.value ? "暂停" : "继续";
});

const actionIcon = computed(() => {
  if (overdue.value) return "restart_alt";
  return running.value ? "pause" : "play_arrow";
});

const leadIcon = computed(() => {
  if (overdue.value) return "notifications_active";
  return running.value ? "timer" : "pause_circle";
});

function onAction() {
  if (overdue.value) {
    resetTimer();
    return;
  }
  toggleTimer();
}

function onThreshold(event) {
  setThreshold(Number(event.target.value));
}
</script>

<template>
  <m3e-list variant="segmented" class="timer-bar" :class="{ paused: !running, overdue }">
    <m3e-list-item>
      <span slot="overline">连续久坐</span>
      <div class="time-row">
        <span class="material-symbols-rounded lead-icon">{{ leadIcon }}</span>
        <span class="time mono">{{ timeText }}</span>
        <span class="remaining">
          {{ overdue ? "已达提醒阈值" : "距提醒" }}
          <b v-if="!overdue" class="mono">{{ remainingText }}</b>
        </span>
      </div>
      <div class="progress-row">
        <m3e-linear-progress-indicator variant="wavy" class="track" :value.prop="progress"
          :max="100"></m3e-linear-progress-indicator>
      </div>
    </m3e-list-item>

    <m3e-list-item>
      提醒间隔
      <m3e-select class="threshold" :value.prop="String(state.timer.threshold_minutes)" @change="onThreshold">
        <m3e-option v-for="m in thresholdOptions" :key="m" :value="String(m)">
          {{ m }} 分钟
        </m3e-option>
      </m3e-select>

      <m3e-button variant="tonal" size="small" @click="onAction" slot="trailing">
        <span slot="icon" class="material-symbols-rounded">{{ actionIcon }}</span>
        {{ actionLabel }}
      </m3e-button>
    </m3e-list-item>
  </m3e-list>
</template>

<style scoped>
.timer-bar {
  display: block;
}

.time-row {
  display: flex;
  align-items: baseline;
  gap: 8px;
  min-width: 0;
  margin-top: 4px;
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

.remaining {
  margin-left: auto;
  color: var(--md-sys-color-on-surface-variant);
  font-size: 12px;
  white-space: nowrap;
}

.remaining b {
  color: var(--md-sys-color-on-surface);
  font-weight: 600;
}

.paused .time,
.paused .lead-icon {
  color: var(--md-sys-color-on-surface-variant);
}

.overdue .time,
.overdue .lead-icon {
  color: var(--md-sys-color-tertiary);
}

.progress-row {
  margin-top: 10px;
}

.track {
  --m3e-progress-indicator-color: var(--md-sys-color-primary);
  --m3e-progress-indicator-track-color: var(--md-sys-color-surface-container-highest);
}

.overdue .track {
  --m3e-progress-indicator-color: var(--md-sys-color-tertiary);
}

.threshold {
  display: inline-block;
  width: 108px;
  margin-left: 12px;
}
</style>